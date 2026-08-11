from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import hmac
import json
import posixpath
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from .analyzers import analyze_file, resolve_go_relationships
from .artifacts import enrich_index
from .evidence import EvidenceStore
from .features import discover_features
from .models import (
    ChangeSummary,
    DiagnosticRecord,
    ModuleSummary,
    ReadingStep,
    RelationshipRecord,
    SymbolRecord,
    redact_persisted_value,
    stable_id,
    to_dict,
)
from .persistence import VerifiedPublishedJson
from .scanner import ScanOptions, capture_tree_manifest, scan_repository
from .snapshot import capture_snapshot


ENTRYPOINT_NAMES = {
    "main.py",
    "app.py",
    "cli.py",
    "server.py",
    "manage.py",
    "main.ts",
    "main.tsx",
    "index.ts",
    "index.tsx",
    "main.js",
    "index.js",
    "main.go",
    "main.rs",
}

MANIFEST_NAMES = {
    "pyproject.toml",
    "package.json",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "makefile",
}

INDEX_SCHEMA_VERSION = "2.0"
SUPPORTED_ANALYZER_LANGUAGES = frozenset({"Python", "JavaScript", "TypeScript", "Go"})


def _analysis_fingerprint(
    max_file_size: int,
    max_files: int | None,
    max_total_bytes: int | None,
    max_entries: int | None = 250_000,
    deadline_seconds: float | None = 120.0,
) -> str:
    package = Path(__file__).parent
    sources = [
        package / "artifacts.py",
        package / "capability_catalog.py",
        package / "difficulty.py",
        package / "evidence.py",
        package / "features.py",
        package / "indexer.py",
        package / "models.py",
        package / "narrative.py",
        package / "scanner.py",
        package / "snapshot.py",
    ]
    sources.extend(sorted((package / "analyzers").glob("*.py")))
    digest = hashlib.sha256()
    digest.update(INDEX_SCHEMA_VERSION.encode("utf-8"))
    digest.update(
        json.dumps(
            {
                "max_file_size": max_file_size,
                "max_files": max_files,
                "max_total_bytes": max_total_bytes,
                "max_entries": max_entries,
                "deadline_seconds": deadline_seconds,
                "python_implementation": sys.implementation.name,
                "python_version": list(sys.version_info[:3]),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    )
    for source in sources:
        digest.update(source.relative_to(package).as_posix().encode("utf-8"))
        digest.update(source.read_bytes())
    return digest.hexdigest()


def _integrity_digest(index: dict[str, Any]) -> str:
    # This checksum detects accidental corruption.  It is deliberately not
    # described as a signature: a writer that controls both the payload and the
    # digest remains inside the local generation trust boundary.
    payload = {key: value for key, value in index.items() if key != "integrity_sha256"}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantic_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_analysis_digest(
    path: str,
    symbols: list[dict[str, Any]] | list[SymbolRecord],
    relationships: list[dict[str, Any]] | list[RelationshipRecord],
) -> str:
    """Seal every persisted analyzer claim owned by one source file."""

    def materialize(value: dict[str, Any] | SymbolRecord | RelationshipRecord) -> dict[str, Any]:
        return value if isinstance(value, dict) else to_dict(value)

    symbol_fields = (
        "id",
        "file_id",
        "path",
        "name",
        "qualified_name",
        "kind",
        "line",
        "end_line",
        "analyzer",
        "confidence",
        "parent_id",
        "signature",
        "exported",
    )
    relationship_fields = (
        "id",
        "source_id",
        "target_id",
        "target_name",
        "kind",
        "path",
        "line",
        "analyzer",
        "confidence",
        "receiver_type_hint",
    )
    materialized_symbols: list[dict[str, Any]] = []
    for item in symbols:
        record = materialize(item)
        if record.get("path") == path:
            materialized_symbols.append(
                {field: record.get(field) for field in symbol_fields}
            )
    materialized_relationships: list[dict[str, Any]] = []
    for item in relationships:
        record = materialize(item)
        if record.get("path") == path:
            materialized_relationships.append(
                {field: record.get(field) for field in relationship_fields}
            )
    payload = {
        "symbols": sorted(
            materialized_symbols,
            key=lambda item: str(item["id"]),
        ),
        "relationships": sorted(
            materialized_relationships,
            key=lambda item: str(item["id"]),
        ),
    }
    return _semantic_digest(payload)


def _normalized_local_analysis(
    symbols: list[dict[str, Any]] | list[SymbolRecord],
    relationships: list[dict[str, Any]] | list[RelationshipRecord],
) -> str:
    """Hash analyzer-owned claims before project-wide target resolution."""

    def materialize(value: object) -> dict[str, Any]:
        return value if isinstance(value, dict) else to_dict(value)

    symbol_fields = (
        "id",
        "file_id",
        "path",
        "name",
        "qualified_name",
        "kind",
        "line",
        "end_line",
        "analyzer",
        "confidence",
        "parent_id",
        "signature",
        "exported",
    )
    relationship_fields = (
        "source_id",
        "target_name",
        "kind",
        "path",
        "line",
        "analyzer",
        "confidence",
        "receiver_type_hint",
    )

    def relationship_claim(item: object) -> dict[str, Any]:
        record = materialize(item)
        claim = {field: record.get(field) for field in relationship_fields}
        if str(record.get("analyzer") or "").startswith("go-") and record.get(
            "kind"
        ) in {"calls", "import", "receiver-type"}:
            # The Go project resolver raises/lowers confidence with target
            # availability.  That is current graph state, not a changed claim
            # in the unchanged source file.
            claim["confidence"] = "project-resolved"
        return claim

    payload = {
        "symbols": sorted(
            [
                {field: materialize(item).get(field) for field in symbol_fields}
                for item in symbols
            ],
            key=lambda item: str(item["id"]),
        ),
        "relationships": sorted(
            [relationship_claim(item) for item in relationships],
            key=lambda item: json.dumps(item, sort_keys=True),
        ),
    }
    return _semantic_digest(payload)


def _derived_artifacts_digest(index: dict[str, Any]) -> str:
    return _semantic_digest(
        {
            name: index.get(name)
            for name in (
                "modules",
                "reading_path",
                "features",
                "evidence",
                "tutorials",
                "codemaps",
                "coverage",
                "stats",
            )
        }
    )


def _record(record_type: type[Any], value: dict[str, Any]) -> Any:
    names = {field.name for field in dataclasses.fields(record_type)}
    return record_type(**{key: item for key, item in value.items() if key in names})


def _baseline_rejection_reason(
    previous_index: object,
    *,
    root: Path,
    analysis_fingerprint: str,
    current_scan: Any,
) -> str | None:
    if not isinstance(previous_index, dict):
        return "baseline is not a JSON object"
    if previous_index.get("schema_version") != INDEX_SCHEMA_VERSION:
        return "schema version does not match"
    if previous_index.get("analysis_fingerprint") != analysis_fingerprint:
        return "analysis configuration or implementation fingerprint does not match"
    project = previous_index.get("project")
    if not isinstance(project, dict) or project.get("path") != str(root):
        return "baseline belongs to a different project path"
    stats = previous_index.get("stats")
    if not isinstance(stats, dict) or stats.get("scan_complete") is not True:
        return "baseline scan was incomplete or its completeness is unknown"
    expected_integrity = previous_index.get("integrity_sha256")
    if not isinstance(expected_integrity, str) or len(expected_integrity) != 64:
        return "baseline has no valid integrity digest"
    try:
        actual_integrity = _integrity_digest(previous_index)
    except (TypeError, ValueError):
        return "baseline core records are not JSON serializable"
    if not hmac.compare_digest(expected_integrity, actual_integrity):
        return "baseline integrity digest does not match its core records"

    record_types = {
        "symbols": SymbolRecord,
        "relationships": RelationshipRecord,
        "diagnostics": DiagnosticRecord,
    }
    files = previous_index.get("files")
    if not isinstance(files, list):
        return "baseline files collection is malformed"
    current_files = {item.path: item for item in current_scan.files}
    current_contents = current_scan.contents
    seen_paths: set[str] = set()
    file_ids: dict[str, str] = {}
    baseline_files_by_path: dict[str, dict[str, Any]] = {}
    declared_symbol_ids: dict[str, set[str]] = {}
    for item in files:
        if not isinstance(item, dict):
            return "baseline contains a malformed file record"
        path = item.get("path")
        sha256 = item.get("sha256")
        if not isinstance(path, str) or not path or path in seen_paths:
            return "baseline contains an invalid or duplicate file path"
        if not isinstance(sha256, str) or len(sha256) != 64:
            return "baseline contains an invalid file digest"
        expected_file_id = stable_id("file", path)
        if item.get("id") != expected_file_id:
            return f"baseline file ID is not stable for {path}"
        current = current_files.get(path)
        if current is not None and current.sha256 == sha256 and current.id != item.get("id"):
            return f"baseline file identity does not match the source scan for {path}"
        symbols_for_file = item.get("symbols")
        if not isinstance(symbols_for_file, list) or not all(
            isinstance(value, str) and value for value in symbols_for_file
        ):
            return f"baseline file has malformed symbol membership for {path}"
        file_ids[str(item["id"])] = path
        baseline_files_by_path[path] = item
        declared_symbol_ids[path] = set(symbols_for_file)
        seen_paths.add(path)
    symbol_items = previous_index.get("symbols")
    if not isinstance(symbol_items, list):
        return "baseline symbols collection is malformed"
    seen_symbol_ids: set[str] = set()
    symbols_by_id: dict[str, dict[str, Any]] = {}
    actual_symbols_by_path: dict[str, set[str]] = defaultdict(set)
    semantic_symbols_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in symbol_items:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            return "baseline contains a malformed symbols record"
        record_id = item.get("id")
        path = item["path"]
        if not isinstance(record_id, str) or not record_id or record_id in seen_symbol_ids:
            return "baseline contains an invalid or duplicate symbols ID"
        if path not in seen_paths or item.get("file_id") not in file_ids:
            return f"baseline symbol {record_id} refers to a missing file"
        if file_ids[str(item.get("file_id"))] != path:
            return f"baseline symbol {record_id} path and file_id disagree"
        try:
            _record(SymbolRecord, item)
        except (TypeError, ValueError):
            return "baseline contains an incompatible symbols record"
        line = item.get("line")
        end_line = item.get("end_line")
        current = current_files.get(path)
        max_lines = baseline_files_by_path[path].get("lines")
        if (
            not isinstance(line, int)
            or not isinstance(end_line, int)
            or line < 1
            or end_line < line
            or (max_lines is not None and end_line > max_lines)
        ):
            return f"baseline symbol {record_id} has an invalid source range"
        analyzer = str(item.get("analyzer") or "")
        if analyzer == "python-ast" or analyzer == "javascript-regex":
            expected_symbol_id = stable_id(
                "symbol", path, item.get("kind"), item.get("qualified_name"), line
            )
            if record_id != expected_symbol_id:
                return f"baseline symbol {record_id} has a non-stable ID"
        elif analyzer.startswith("go-"):
            package_match = re.search(r"\[package=([^\]]+)\]$", analyzer)
            package = package_match.group(1) if package_match else "unknown"
            expected_symbol_id = stable_id(
                "symbol",
                path,
                package,
                item.get("qualified_name"),
                item.get("kind"),
                " ".join(str(item.get("signature") or "").split()),
            )
            if record_id != expected_symbol_id:
                return f"baseline Go symbol {record_id} has a non-stable ID"
        source = (
            current_contents.get(path)
            if current is not None
            and current.sha256 == baseline_files_by_path[path].get("sha256")
            else None
        )
        name = item.get("name")
        if (
            source is not None
            and isinstance(name, str)
            and item.get("confidence") in {"exact", "syntax-exact"}
        ):
            source_lines = source.splitlines()
            source_slice = "\n".join(source_lines[line - 1 : end_line])
            if name not in source_slice:
                return f"baseline symbol {record_id} is not grounded in its source range"
        seen_symbol_ids.add(record_id)
        symbols_by_id[record_id] = item
        actual_symbols_by_path[path].add(record_id)
        semantic_symbols_by_path[path].append(item)
    for path, memberships in declared_symbol_ids.items():
        if memberships != actual_symbols_by_path.get(path, set()):
            return f"baseline file symbol membership is not closed for {path}"
    for record_id, item in symbols_by_id.items():
        parent_id = item.get("parent_id")
        if parent_id:
            parent = symbols_by_id.get(str(parent_id))
            if parent is None or parent.get("path") != item.get("path"):
                return f"baseline symbol {record_id} has an invalid parent"

    semantic_relationships_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for collection, record_type in record_types.items():
        if collection == "symbols":
            continue
        values = previous_index.get(collection)
        if not isinstance(values, list):
            return f"baseline {collection} collection is malformed"
        seen_ids: set[str] = set()
        for item in values:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                return f"baseline contains a malformed {collection} record"
            if collection in {"symbols", "relationships"}:
                record_id = item.get("id")
                if (
                    not isinstance(record_id, str)
                    or not record_id
                    or record_id in seen_ids
                ):
                    return f"baseline contains an invalid or duplicate {collection} ID"
                seen_ids.add(record_id)
            path = item.get("path")
            if path != "." and path not in seen_paths:
                return f"baseline {collection} record refers to an unknown path: {path}"
            if collection == "relationships":
                source_id = str(item.get("source_id") or "")
                if source_id not in symbols_by_id and source_id not in file_ids:
                    return f"baseline relationship {record_id} has a dangling source"
                source_path = (
                    symbols_by_id[source_id]["path"]
                    if source_id in symbols_by_id
                    else file_ids[source_id]
                )
                if source_path != path:
                    return f"baseline relationship {record_id} path and source disagree"
                target_id = item.get("target_id")
                if target_id and str(target_id) not in symbols_by_id and str(target_id) not in file_ids:
                    return f"baseline relationship {record_id} has a dangling target"
                line = item.get("line")
                current = current_files.get(str(path))
                if not isinstance(line, int) or line < 1 or (
                    current is not None and line > current.lines
                ):
                    return f"baseline relationship {record_id} has an invalid source line"
            try:
                _record(record_type, item)
            except (TypeError, ValueError):
                return f"baseline contains an incompatible {collection} record"
            if collection == "relationships":
                semantic_relationships_by_path[str(path)].append(item)
    for path, item in baseline_files_by_path.items():
        expected_analysis = item.get("analysis_sha256")
        if (
            not isinstance(expected_analysis, str)
            or len(expected_analysis) != 64
            or not hmac.compare_digest(
                expected_analysis,
                _file_analysis_digest(
                    path,
                    semantic_symbols_by_path.get(path, []),
                    semantic_relationships_by_path.get(path, []),
                ),
            )
        ):
            return f"baseline analyzer semantics digest does not match for {path}"
    expected_derived = previous_index.get("derived_sha256")
    if (
        not isinstance(expected_derived, str)
        or len(expected_derived) != 64
        or not hmac.compare_digest(
            expected_derived, _derived_artifacts_digest(previous_index)
        )
    ):
        return "baseline derived artifacts digest does not match"

    canonical_symbols: list[SymbolRecord] = []
    canonical_relationships: list[RelationshipRecord] = []
    for current in current_scan.files:
        if current.language not in SUPPORTED_ANALYZER_LANGUAGES:
            continue
        analysis = analyze_file(current, current_contents[current.path])
        canonical_symbols.extend(analysis.symbols)
        canonical_relationships.extend(analysis.relationships)
    canonical_relationships, _, _ = _ensure_unique_relationships(
        canonical_relationships
    )
    resolve_go_relationships(
        canonical_relationships,
        canonical_symbols,
        current_scan.files,
        project_root=root,
    )
    _resolve_relationships(
        canonical_relationships, canonical_symbols, current_scan.files
    )
    canonical_symbols_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    canonical_relationships_by_path: dict[
        str, list[dict[str, Any]]
    ] = defaultdict(list)
    for symbol in canonical_symbols:
        canonical_symbols_by_path[symbol.path].append(
            redact_persisted_value(to_dict(symbol))
        )
    for relationship in canonical_relationships:
        canonical_relationships_by_path[relationship.path].append(
            redact_persisted_value(to_dict(relationship))
        )
    for path, item in baseline_files_by_path.items():
        current = current_files.get(path)
        if current is None or current.sha256 != item.get("sha256"):
            continue
        if _normalized_local_analysis(
            semantic_symbols_by_path.get(path, []),
            semantic_relationships_by_path.get(path, []),
        ) != _normalized_local_analysis(
            canonical_symbols_by_path.get(path, []),
            canonical_relationships_by_path.get(path, []),
        ):
            return f"baseline analyzer claims differ from source for {path}"
    return None


def _baseline_publication_rejection_reason(
    previous_index: object,
    *,
    output: Path | None,
) -> str | None:
    """Require provenance from the verified current-generation disk reader."""

    if not isinstance(previous_index, VerifiedPublishedJson):
        return "baseline has no verified current-generation disk provenance"
    if output is None or previous_index.publication_output != output:
        return "baseline publication is not bound to the requested output directory"
    if previous_index.publication_relative != "index.json":
        return "baseline is not the published repository index artifact"
    if previous_index.get("generation_id") != previous_index.publication_generation_id:
        return "baseline generation identity does not match its verified publication"
    return None


def _python_structural_digest(source: str) -> tuple[str | None, bool]:
    """Hash Python's public structural contract, not implementation bodies."""

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None, False

    records: list[tuple[object, ...]] = []

    def walk_body(body: list[ast.stmt], scope: tuple[str, ...] = ()) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                records.append(
                    (
                        "function",
                        ".".join((*scope, node.name)),
                        ast.dump(node.args, include_attributes=False),
                        ast.unparse(node.returns) if node.returns is not None else None,
                        tuple(ast.unparse(item) for item in node.decorator_list),
                        not node.name.startswith("_"),
                    )
                )
            elif isinstance(node, ast.ClassDef):
                qualified = ".".join((*scope, node.name))
                records.append(
                    (
                        "class",
                        qualified,
                        tuple(ast.unparse(item) for item in node.bases),
                        tuple(
                            (keyword.arg, ast.unparse(keyword.value))
                            for keyword in node.keywords
                        ),
                        tuple(ast.unparse(item) for item in node.decorator_list),
                        not node.name.startswith("_"),
                    )
                )
                for child in node.body:
                    if isinstance(child, (ast.Assign, ast.AnnAssign)):
                        targets = (
                            child.targets
                            if isinstance(child, ast.Assign)
                            else [child.target]
                        )
                        annotation = (
                            ast.unparse(child.annotation)
                            if isinstance(child, ast.AnnAssign)
                            else None
                        )
                        for target in targets:
                            if isinstance(target, ast.Name):
                                records.append(
                                    ("property", qualified, target.id, annotation)
                                )
                walk_body(node.body, (*scope, node.name))
            elif isinstance(node, ast.Import):
                records.append(
                    (
                        "import",
                        tuple((alias.name, alias.asname) for alias in node.names),
                    )
                )
            elif isinstance(node, ast.ImportFrom):
                records.append(
                    (
                        "import-from",
                        node.level,
                        node.module,
                        tuple((alias.name, alias.asname) for alias in node.names),
                    )
                )

    walk_body(tree.body)
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), True


def _assign_structural_fingerprint(file: Any, source: str) -> None:
    if file.language == "Python":
        file.structural_sha256, file.has_structural_analysis = (
            _python_structural_digest(source)
        )
    else:
        # Regex/lexical analyzers do not prove a complete public contract.
        file.structural_sha256 = None
        file.has_structural_analysis = False


def _group_records_by_path(
    values: list[dict[str, Any]],
    record_type: type[Any],
    *,
    clear_relationship_targets: bool = False,
) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for item in values:
        value = (
            {**item, "target_id": None}
            if clear_relationship_targets
            and item.get("kind") in {"calls", "import", "receiver-type"}
            else item
        )
        grouped[item["path"]].append(_record(record_type, value))
    return dict(grouped)


def _relationship_semantics(relationship: RelationshipRecord) -> tuple[object, ...]:
    return (
        relationship.source_id,
        relationship.target_id,
        relationship.target_name,
        relationship.kind,
        relationship.path,
        relationship.line,
        relationship.analyzer,
        relationship.confidence,
        relationship.receiver_type_hint,
    )


def _ensure_unique_relationships(
    relationships: list[RelationshipRecord],
) -> tuple[list[RelationshipRecord], int, int]:
    """Deduplicate identical edges and deterministically repair true ID collisions."""

    normalized: list[RelationshipRecord] = []
    by_id: dict[str, RelationshipRecord] = {}
    deduplicated = 0
    collisions = 0
    for relationship in relationships:
        existing = by_id.get(relationship.id)
        if existing is None:
            by_id[relationship.id] = relationship
            normalized.append(relationship)
            continue
        if _relationship_semantics(existing) == _relationship_semantics(relationship):
            deduplicated += 1
            continue
        collisions += 1
        occurrence = collisions
        candidate = stable_id(
            "rel", relationship.id, occurrence, *_relationship_semantics(relationship)
        )
        while candidate in by_id:
            occurrence += 1
            candidate = stable_id(
                "rel",
                relationship.id,
                occurrence,
                *_relationship_semantics(relationship),
            )
        relationship.id = candidate
        by_id[candidate] = relationship
        normalized.append(relationship)
    return normalized, deduplicated, collisions


def _snapshot_identity(snapshot: Any) -> tuple[object, ...]:
    return (
        snapshot.name,
        snapshot.path,
        snapshot.git_root,
        snapshot.is_git,
        snapshot.commit,
        snapshot.branch,
        snapshot.dirty,
        snapshot.remote,
        snapshot.license,
    )


def _scan_identity(scan: Any) -> tuple[object, ...]:
    files = tuple((file.path, file.size, file.sha256) for file in scan.files)
    return files, tuple(sorted(scan.skipped.items())), scan.truncated


def _source_is_stable(
    root: Path,
    before: Any,
    first_scan: Any,
    options: ScanOptions,
    initial_manifest: str,
) -> bool:
    """Verify one coherent source state without claiming filesystem snapshot isolation.

    A second scan catches changed, deleted, and newly added analyzable files in
    both Git and non-Git directories. Capturing Git metadata after that scan
    additionally catches a branch/commit/worktree-state transition.
    """

    manifest_before_verification = capture_tree_manifest(root, options)
    verification_scan = scan_repository(root, options)
    after = capture_snapshot(root)
    final_snapshot = capture_snapshot(root)
    # The manifest is deliberately the final source observation.  In
    # particular, a non-Git tree can acquire a new file immediately after the
    # final metadata snapshot; placing this full-tree check last closes that
    # previously unobserved tail window.
    final_manifest = capture_tree_manifest(root, options)
    return (
        initial_manifest == manifest_before_verification == final_manifest
        and _scan_identity(first_scan) == _scan_identity(verification_scan)
        and _snapshot_identity(before)
        == _snapshot_identity(after)
        == _snapshot_identity(final_snapshot)
    )


def _structural_signatures_by_path(
    symbols: list[SymbolRecord],
    relationships: list[RelationshipRecord],
) -> dict[str, tuple[tuple[object, ...], tuple[object, ...]]]:
    symbols_by_path: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    relationships_by_path: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    source_names = {symbol.id: symbol.qualified_name for symbol in symbols}
    for symbol in symbols:
        symbols_by_path[symbol.path].append(
            (
                symbol.qualified_name,
                symbol.kind,
                symbol.signature,
                symbol.exported,
            )
        )
    for relationship in relationships:
        if relationship.kind in {"calls", "import", "contains"}:
            relationships_by_path[relationship.path].append(
                (
                    source_names.get(relationship.source_id, "<file>"),
                    relationship.kind,
                    relationship.target_name,
                )
            )
    return {
        path: (
            tuple(sorted(symbols_by_path.get(path, []))),
            tuple(sorted(relationships_by_path.get(path, []))),
        )
        for path in symbols_by_path.keys() | relationships_by_path.keys()
    }


def _classify_changes(
    *,
    baseline_status: str,
    current_files: dict[str, Any],
    previous_files: dict[str, dict[str, Any]],
    current_symbols: list[SymbolRecord],
    previous_symbols: list[SymbolRecord],
    current_relationships: list[RelationshipRecord],
    previous_relationships: list[RelationshipRecord],
    added: list[str],
    changed: list[str],
    deleted: list[str],
) -> dict[str, Any]:
    if baseline_status != "compatible":
        return {
            "baseline_status": baseline_status,
            "action": "FULL_REINDEX",
            "confidence": "conservative",
            "structural": [],
            "implementation_only": [],
            "reasons": [
                "No compatible baseline was available; structural scope cannot be proven."
            ],
        }

    structural: list[str] = sorted([*added, *deleted])
    implementation_only: list[str] = []
    reasons: list[str] = []
    old_signatures = _structural_signatures_by_path(
        previous_symbols, previous_relationships
    )
    new_signatures = _structural_signatures_by_path(
        current_symbols, current_relationships
    )
    for path in changed:
        current = current_files[path]
        previous = previous_files[path]
        previous_language = previous.get("language")
        if (
            current.language not in SUPPORTED_ANALYZER_LANGUAGES
            or previous_language != current.language
            or current.has_structural_analysis is not True
            or previous.get("has_structural_analysis") is not True
            or not current.structural_sha256
            or not previous.get("structural_sha256")
        ):
            structural.append(path)
            reasons.append(
                f"{path}: complete structural analysis could not be proven"
            )
            continue
        old_signature = (
            previous.get("structural_sha256"),
            old_signatures.get(path, ((), ())),
        )
        new_signature = (
            current.structural_sha256,
            new_signatures.get(path, ((), ())),
        )
        if old_signature == new_signature:
            implementation_only.append(path)
        else:
            structural.append(path)
            reasons.append(
                f"{path}: symbols, signatures, imports, or call edges changed"
            )

    structural = sorted(set(structural))
    implementation_only.sort()
    changed_count = len(structural)
    previous_count = len(previous_files)
    prior_modules = {
        PurePosixPath(path).parts[0] for path in previous_files if "/" in path
    }
    current_modules = {
        PurePosixPath(path).parts[0] for path in current_files if "/" in path
    }
    directory_change = prior_modules != current_modules
    if not structural:
        action = "SKIP_GRAPH_UPDATE"
    elif changed_count > 30 or (
        previous_count > 0 and changed_count / previous_count > 0.5
    ):
        action = "FULL_REINDEX"
    elif directory_change or changed_count > 10:
        action = "REBUILD_ARCHITECTURE"
    else:
        action = "PARTIAL_REINDEX"
    if added or deleted:
        reasons.append(f"file set changed: {len(added)} added, {len(deleted)} deleted")
    if directory_change:
        reasons.append("top-level module set changed")
    if implementation_only:
        reasons.append(
            f"{len(implementation_only)} changed file(s) retained the same supported structural fingerprint"
        )
    if not reasons:
        reasons.append("No content changes were detected.")
    return {
        "baseline_status": baseline_status,
        "action": action,
        "confidence": "conservative",
        "structural": structural,
        "implementation_only": implementation_only,
        "reasons": reasons,
    }


def _resolve_relationships(
    relationships: list[RelationshipRecord],
    symbols: list[SymbolRecord],
    files: list[Any],
) -> None:
    symbols_by_name: dict[str, list[SymbolRecord]] = defaultdict(list)
    symbols_by_id: dict[str, SymbolRecord] = {}
    for symbol in symbols:
        symbols_by_id[symbol.id] = symbol
        symbols_by_name[symbol.name].append(symbol)
        symbols_by_name[symbol.qualified_name].append(symbol)

    file_by_module: dict[str, str] = {}
    file_by_path = {file.path: file.id for file in files}
    language_by_path = {file.path: file.language for file in files}
    for file in files:
        path = PurePosixPath(file.path)
        without_suffix = str(path.with_suffix(""))
        dotted = without_suffix.replace("/", ".")
        file_by_module[dotted] = file.id
        file_by_module[path.stem] = file.id
        if dotted.endswith(".__init__"):
            file_by_module[dotted.removesuffix(".__init__")] = file.id

    # Resolve imports before calls: Python call resolution may use the local
    # binding carried by an import edge as explicit module evidence.
    for relationship in relationships:
        if relationship.target_id or relationship.kind != "import":
            continue
        if relationship.analyzer.startswith("go-"):
            # Go resolution is package/receiver aware.  The language-agnostic
            # unique-name fallback below would reconnect deliberately
            # unresolved Go edges to an unrelated package.
            continue
        target = relationship.target_name
        if target.startswith("."):
            source_parent = PurePosixPath(relationship.path).parent
            normalized = posixpath.normpath(f"{source_parent.as_posix()}/{target}")
            suffix = PurePosixPath(normalized).suffix.lower()
            stem = str(PurePosixPath(normalized).with_suffix("")) if suffix else normalized
            source_language = language_by_path.get(relationship.path)
            if source_language in {"JavaScript", "TypeScript"}:
                # TypeScript commonly imports emitted `.js` paths while the
                # repository contains `.ts`/`.tsx` source.  Asset imports must
                # not fall through to a same-stem implementation file.
                if not suffix:
                    candidates = (
                        normalized,
                        f"{stem}.ts",
                        f"{stem}.tsx",
                        f"{stem}.js",
                        f"{stem}.jsx",
                        f"{stem}.mjs",
                        f"{stem}.cjs",
                        f"{stem}/index.ts",
                        f"{stem}/index.tsx",
                        f"{stem}/index.js",
                        f"{stem}/index.jsx",
                        f"{stem}/index.mjs",
                        f"{stem}/index.cjs",
                    )
                elif suffix in {".js", ".jsx", ".mjs", ".cjs"}:
                    candidates = (normalized, f"{stem}.ts", f"{stem}.tsx")
                else:
                    candidates = (normalized,)
                allowed_languages = {"JavaScript", "TypeScript"}
            else:
                candidates = (normalized, f"{stem}.py", f"{stem}/__init__.py")
                allowed_languages = {source_language}
            relationship.target_id = next(
                (
                    file_by_path[item]
                    for item in candidates
                    if item in file_by_path
                    and language_by_path.get(item) in allowed_languages
                )
                , None
            )
        else:
            parts = target.split(".")
            for end in range(len(parts), 0, -1):
                candidate = ".".join(parts[:end])
                if candidate in file_by_module:
                    relationship.target_id = file_by_module[candidate]
                    break

    python_bindings: dict[tuple[str, str], str] = {}
    for relationship in relationships:
        hint = relationship.receiver_type_hint or ""
        if (
            relationship.analyzer == "python-ast"
            and relationship.kind == "import"
            and relationship.target_id
            and hint.startswith("binding:")
        ):
            python_bindings[(relationship.path, hint.removeprefix("binding:"))] = (
                relationship.target_id
            )

    for relationship in relationships:
        if relationship.target_id or relationship.kind != "calls":
            continue
        if relationship.analyzer.startswith("go-"):
            continue
        if relationship.analyzer == "python-ast":
            parts = relationship.target_name.split(".")
            candidates: list[SymbolRecord] = []
            if len(parts) == 1:
                imported_file_id = python_bindings.get(
                    (relationship.path, parts[0])
                )
                if imported_file_id:
                    candidates = [
                        item
                        for item in symbols_by_name.get(parts[0], [])
                        if item.file_id == imported_file_id
                    ]
                else:
                    candidates = symbols_by_name.get(parts[0], [])
            elif len(parts) == 2 and parts[0] in {"self", "cls"}:
                source = symbols_by_id.get(relationship.source_id)
                parent_id = source.parent_id if source is not None else None
                if parent_id:
                    candidates = [
                        item
                        for item in symbols_by_name.get(parts[1], [])
                        if item.parent_id == parent_id
                    ]
            elif len(parts) == 2:
                imported_file_id = python_bindings.get(
                    (relationship.path, parts[0])
                )
                if imported_file_id:
                    candidates = [
                        item
                        for item in symbols_by_name.get(parts[1], [])
                        if item.file_id == imported_file_id
                    ]
            # Multi-level selectors such as self.model.transcribe carry no
            # receiver type proof in the Python AST and remain unresolved.
        else:
            candidates = symbols_by_name.get(relationship.target_name, [])
            if not candidates:
                candidates = symbols_by_name.get(
                    relationship.target_name.rsplit(".", 1)[-1], []
                )
        unique = {candidate.id: candidate for candidate in candidates}
        if len(unique) == 1:
            relationship.target_id = next(iter(unique))


def _build_modules(
    files: list[Any], symbols: list[SymbolRecord]
) -> list[ModuleSummary]:
    files_by_module: dict[str, list[Any]] = defaultdict(list)
    symbols_by_file: Counter[str] = Counter(symbol.file_id for symbol in symbols)
    for file in files:
        files_by_module[file.module].append(file)

    modules: list[ModuleSummary] = []
    for name, module_files in files_by_module.items():
        languages = Counter(file.language for file in module_files)
        entrypoints = [
            file.path
            for file in module_files
            if PurePosixPath(file.path).name.lower() in ENTRYPOINT_NAMES
        ]
        modules.append(
            ModuleSummary(
                id=stable_id("module", name),
                name=name,
                path="." if name == "root" else name,
                file_count=len(module_files),
                symbol_count=sum(symbols_by_file[file.id] for file in module_files),
                languages=dict(
                    sorted(languages.items(), key=lambda item: (-item[1], item[0]))
                ),
                entrypoints=sorted(entrypoints),
            )
        )
    return sorted(
        modules, key=lambda item: (item.name != "root", -item.symbol_count, item.name)
    )


def _build_reading_path(
    files: list[Any], symbols: list[SymbolRecord], modules: list[ModuleSummary]
) -> list[ReadingStep]:
    by_path = {file.path: file for file in files}
    symbols_by_file: dict[str, list[SymbolRecord]] = defaultdict(list)
    for symbol in symbols:
        symbols_by_file[symbol.file_id].append(symbol)
    chosen: set[str] = set()
    steps: list[ReadingStep] = []

    def add(path: str, title: str, reason: str, confidence: str = "heuristic") -> None:
        if path in chosen or path not in by_path or len(steps) >= 12:
            return
        chosen.add(path)
        file_symbols = symbols_by_file.get(by_path[path].id, [])
        primary = next(
            (symbol for symbol in file_symbols if symbol.exported),
            file_symbols[0] if file_symbols else None,
        )
        steps.append(
            ReadingStep(
                order=len(steps) + 1,
                title=title,
                path=path,
                reason=reason,
                symbol_id=primary.id if primary else None,
                confidence=confidence,
            )
        )

    readmes = sorted(
        (
            file.path
            for file in files
            if PurePosixPath(file.path).name.lower().startswith("readme")
        ),
        key=lambda path: (path.count("/"), path),
    )
    if readmes:
        add(
            readmes[0],
            "先理解项目意图",
            "README 通常说明项目目标、运行方式和用户边界。",
            "exact",
        )

    manifests = sorted(
        file.path
        for file in files
        if PurePosixPath(file.path).name.lower() in MANIFEST_NAMES
    )
    for path in manifests[:2]:
        add(path, "确认运行与依赖", "构建清单暴露语言、入口、脚本和外部依赖。", "exact")

    entrypoints = sorted(
        (
            file.path
            for file in files
            if PurePosixPath(file.path).name.lower() in ENTRYPOINT_NAMES
        ),
        key=lambda path: (path.count("/"), path),
    )
    for path in entrypoints[:4]:
        add(
            path,
            "进入执行主线",
            "文件名和位置表明它可能是运行入口；需要结合测试继续核对。",
        )

    file_symbol_counts = Counter(symbol.file_id for symbol in symbols)
    files_by_module: dict[str, list[Any]] = defaultdict(list)
    for file in files:
        files_by_module[file.module].append(file)
    for module in sorted(modules, key=lambda item: (-item.symbol_count, item.name)):
        if len(steps) >= 12:
            break
        module_files = [
            file
            for file in files_by_module.get(module.name, [])
            if file.path not in chosen
        ]
        if not module_files:
            continue
        representative = max(
            module_files,
            key=lambda file: (file_symbol_counts[file.id], -file.lines, file.path),
        )
        add(
            representative.path,
            f"理解 {module.name} 模块",
            f"该模块包含 {module.file_count} 个文件和 {module.symbol_count} 个已识别符号。",
        )
    return steps


def build_index(
    path: Path,
    *,
    output_dir: Path | None = None,
    max_file_size: int = 1_000_000,
    max_files: int | None = 100_000,
    max_total_bytes: int | None = 1_000_000_000,
    max_entries: int | None = 250_000,
    deadline_seconds: float | None = 120.0,
    cancelled: Callable[[], bool] | None = None,
    previous_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = path.expanduser().resolve()
    resolved_output = output_dir.expanduser().resolve() if output_dir else None
    if resolved_output is not None and (
        resolved_output == root or root.is_relative_to(resolved_output)
    ):
        raise ValueError(
            "output directory cannot be the repository root or one of its ancestors"
        )
    snapshot = capture_snapshot(root)
    excluded = (resolved_output,) if resolved_output else ()
    scan_options = ScanOptions(
        max_file_size=max_file_size,
        max_files=max_files,
        max_total_bytes=max_total_bytes,
        max_entries=max_entries,
        deadline_seconds=deadline_seconds,
        excluded_paths=excluded,
        cancelled=cancelled,
    )
    initial_manifest = capture_tree_manifest(root, scan_options)
    scan = scan_repository(root, scan_options)
    for file in scan.files:
        _assign_structural_fingerprint(file, scan.contents[file.path])
    symbols: list[SymbolRecord] = []
    relationships: list[RelationshipRecord] = []
    diagnostics = list(scan.diagnostics)

    analysis_fingerprint = _analysis_fingerprint(
        max_file_size,
        max_files,
        max_total_bytes,
        max_entries,
        deadline_seconds,
    )
    rejection_reason: str | None = None
    if previous_index is not None:
        rejection_reason = _baseline_publication_rejection_reason(
            previous_index, output=resolved_output
        )
        if rejection_reason is None:
            rejection_reason = _baseline_rejection_reason(
                previous_index,
                root=root,
                analysis_fingerprint=analysis_fingerprint,
                current_scan=scan,
            )
    baseline_status = (
        "absent"
        if previous_index is None
        else "rejected"
        if rejection_reason
        else "compatible"
    )
    if rejection_reason:
        diagnostics.append(
            DiagnosticRecord(
                ".",
                "warning",
                "baseline-rejected",
                f"incremental baseline was not reused: {rejection_reason}",
            )
        )
    baseline = (
        previous_index
        if baseline_status == "compatible" and isinstance(previous_index, dict)
        else {}
    )
    previous_files = {
        str(item.get("path")): item
        for item in baseline.get("files", [])
        if item.get("path")
    }
    current_files = {file.path: file for file in scan.files}
    unchanged_paths = {
        path
        for path, file in current_files.items()
        if path in previous_files and previous_files[path].get("sha256") == file.sha256
    }
    previous_symbols = _group_records_by_path(baseline.get("symbols", []), SymbolRecord)
    previous_relationships = _group_records_by_path(
        baseline.get("relationships", []),
        RelationshipRecord,
        clear_relationship_targets=True,
    )
    previous_diagnostics = _group_records_by_path(
        baseline.get("diagnostics", []), DiagnosticRecord
    )

    for file in scan.files:
        if file.path in unchanged_paths:
            reused_symbols = previous_symbols.get(file.path, [])
            file.symbols = [symbol.id for symbol in reused_symbols]
            symbols.extend(reused_symbols)
            relationships.extend(previous_relationships.get(file.path, []))
            diagnostics.extend(previous_diagnostics.get(file.path, []))
        else:
            analysis = analyze_file(file, scan.contents[file.path])
            file.symbols = [symbol.id for symbol in analysis.symbols]
            symbols.extend(analysis.symbols)
            relationships.extend(analysis.relationships)
            diagnostics.extend(analysis.diagnostics)
            if file.language not in SUPPORTED_ANALYZER_LANGUAGES:
                diagnostics.append(
                    DiagnosticRecord(
                        file.path,
                        "info",
                        "unsupported-analyzer",
                        f"no semantic analyzer is registered for {file.language}; metadata was indexed without symbols",
                    )
                )

    symbols.sort(key=lambda item: (item.path, item.line, item.qualified_name))
    relationships, deduplicated_relationships, repaired_relationship_ids = (
        _ensure_unique_relationships(relationships)
    )
    if deduplicated_relationships or repaired_relationship_ids:
        diagnostics.append(
            DiagnosticRecord(
                ".",
                "info",
                "duplicate-relationships-normalized",
                "normalized relationship IDs: "
                f"{deduplicated_relationships} semantically identical duplicate(s) removed, "
                f"{repaired_relationship_ids} true collision(s) assigned deterministic IDs",
            )
        )
    go_resolution = resolve_go_relationships(
        relationships, symbols, scan.files, project_root=root
    )
    _resolve_relationships(relationships, symbols, scan.files)
    relationships.sort(
        key=lambda item: (item.path, item.line, item.kind, item.target_name)
    )
    current_paths = set(current_files)
    previous_paths = set(previous_files)
    added_paths = sorted(current_paths - previous_paths)
    changed_paths = sorted(
        path for path in current_paths & previous_paths if path not in unchanged_paths
    )
    deleted_paths = sorted(previous_paths - current_paths)
    # Derived teaching claims are intentionally rebuilt even on a no-op warm
    # run.  A verified manifest proves bytes, not semantic truth; recomputation
    # prevents a fully re-signed tutorial/codemap/feature forgery from entering
    # a new generation through the incremental cache.
    reusable_primary_artifacts = False
    modules = _build_modules(scan.files, symbols)
    reading_path = _build_reading_path(scan.files, symbols, modules)
    evidence = EvidenceStore(scan.contents)
    features = discover_features(
        scan.files,
        symbols,
        relationships,
        modules,
        scan.contents,
        evidence,
        project_snapshot=snapshot,
    )
    modules_data = to_dict(modules)
    reading_path_data = to_dict(reading_path)
    features_data = to_dict(features)
    evidence_data = to_dict(evidence.records)
    scan_complete = not scan.truncated and not any(
        item.code
        in {
            "walk-error",
            "read-error",
            "stat-error",
            "file-changed-while-reading",
            "scan-cancelled",
            "scan-deadline-exceeded",
            "max-entries-exceeded",
            "max-files-exceeded",
            "max-total-bytes-exceeded",
        }
        for item in scan.diagnostics
    )
    if not scan_complete and not reusable_primary_artifacts:
        for feature in features:
            feature.confidence = "partial-unvalidated"
        features_data = to_dict(features)
    confidence = Counter(item.confidence for item in [*symbols, *relationships])
    changes = ChangeSummary(
        baseline_commit=baseline.get("project", {}).get("commit"),
        current_commit=snapshot.commit,
        added=added_paths,
        changed=changed_paths,
        deleted=deleted_paths,
        unchanged=sorted(unchanged_paths),
        reused_files=len(unchanged_paths),
        reanalyzed_files=len(current_paths - unchanged_paths),
    )
    previous_symbol_records = [
        item for group in previous_symbols.values() for item in group
    ]
    previous_relationship_records = [
        item for group in previous_relationships.values() for item in group
    ]
    change_classification = _classify_changes(
        baseline_status=baseline_status,
        current_files=current_files,
        previous_files=previous_files,
        current_symbols=symbols,
        previous_symbols=previous_symbol_records,
        current_relationships=relationships,
        previous_relationships=previous_relationship_records,
        added=added_paths,
        changed=changed_paths,
        deleted=deleted_paths,
    )

    result = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "analysis_fingerprint": analysis_fingerprint,
        "analysis_config": {
            "max_file_size": max_file_size,
            "max_files": max_files,
            "max_total_bytes": max_total_bytes,
            "max_entries": max_entries,
            "deadline_seconds": deadline_seconds,
            "excluded_paths": (
                [resolved_output.relative_to(root).as_posix()]
                if resolved_output is not None
                and resolved_output.is_relative_to(root)
                else []
            ),
        },
        "integrity_boundary": "sha256-checksum-only; controlled-local-generation; not-authenticated",
        "source_manifest_sha256": initial_manifest,
        "freshness": "complete" if scan_complete else "partial-unvalidated",
        "project": to_dict(snapshot),
        "stats": {
            "files": len(scan.files),
            "symbols": len(symbols),
            "relationships": len(relationships),
            "modules": len(modules_data),
            "features": len(features_data),
            "evidence": len(evidence_data),
            "lines": sum(file.lines for file in scan.files),
            "bytes": sum(file.size for file in scan.files),
            "languages": scan.language_counts,
            "confidence": dict(sorted(confidence.items())),
            "skipped": scan.skipped,
            "scan_complete": scan_complete,
            "truncated": scan.truncated,
            "visited_entries": scan.visited_entries,
            "visited_files": scan.visited_files,
            "declared_bytes": scan.declared_bytes,
            "diagnostics": len(diagnostics),
            "reused_files": changes.reused_files,
            "reanalyzed_files": changes.reanalyzed_files,
        },
        "analyzers": [
            {
                "id": "go-lexer-fallback",
                "enabled": bool(scan.language_counts.get("Go")),
                "implicit": True,
                "mode": "precision-first-syntax-fallback",
                "symbols": sum(
                    item.analyzer.startswith("go-lexer-fallback") for item in symbols
                ),
                "relationships": sum(
                    item.analyzer.startswith("go-lexer-fallback")
                    for item in relationships
                ),
                "resolution": to_dict(go_resolution),
                "boundary": (
                    "unqualified and package-selector calls resolve only to package "
                    "functions; receiver selectors require explicit local type evidence; "
                    "Go methods remain package-level declarations linked to receiver "
                    "types by receiver-type edges, never cross-file lexical parents"
                ),
            },
            {
                "id": "go-semantic-gopls",
                "enabled": False,
                "implicit": False,
                "mode": "explicit-opt-in-differential-only",
                "symbols": 0,
                "relationships": 0,
                "boundary": (
                    "the default index never invokes or downloads gopls and does not "
                    "claim semantic-exact call edges"
                ),
            },
        ],
        "modules": modules_data,
        # Every build returns an independent value snapshot. A no-op warm run
        # may reuse prior analysis, but must not share caller-mutable records.
        "files": to_dict(scan.files),
        "symbols": to_dict(symbols),
        "relationships": to_dict(relationships),
        "reading_path": reading_path_data,
        "features": features_data,
        "evidence": evidence_data,
        "changes": to_dict(changes),
        "change_classification": change_classification,
        "diagnostics": to_dict(diagnostics),
    }
    # All source-derived records and evidence have been materialized. The
    # final stability scan compares file identities rather than source text, so
    # release the first scan's contents and hydrated warm caches before loading
    # the verification scan. This keeps a large JSON baseline from overlapping
    # two full source copies plus two object graphs of symbols/relationships.
    scan.contents.clear()
    symbols.clear()
    relationships.clear()
    diagnostics.clear()
    previous_symbols.clear()
    previous_relationships.clear()
    previous_diagnostics.clear()
    if not _source_is_stable(
        root, snapshot, scan, scan_options, initial_manifest
    ):
        raise ValueError(
            "repository changed while it was being indexed; retry from a stable working tree"
        )
    if reusable_primary_artifacts:
        # Reused artifacts are semantically unchanged, but these containers
        # remain caller-mutable and therefore require an ownership boundary.
        result["modules"] = copy.deepcopy(baseline["modules"])
        result["reading_path"] = copy.deepcopy(baseline["reading_path"])
        result["features"] = copy.deepcopy(baseline["features"])
        result["evidence"] = copy.deepcopy(baseline["evidence"])
        result["tutorials"] = copy.deepcopy(baseline["tutorials"])
        result["codemaps"] = copy.deepcopy(baseline["codemaps"])
        result["coverage"] = copy.deepcopy(baseline["coverage"])
        prior_stats = baseline.get("stats", {})
        for name in (
            "tutorials",
            "codemaps",
            "coverage",
            "coverage_average",
            "evidence_completeness_average",
        ):
            result["stats"][name] = prior_stats.get(name, 0)
        result["stats"]["reused_derived_artifacts"] = True
    else:
        result = enrich_index(result)
        result["stats"]["reused_derived_artifacts"] = False
    result = redact_persisted_value(result)
    # Redaction is part of the persisted representation.  Seal that exact
    # representation rather than the pre-redaction analyzer objects; otherwise
    # a harmless secret-shaped signature or relationship label makes an honest
    # index fail its own semantic-closure check.
    persisted_symbols_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    persisted_relationships_by_path: dict[str, list[dict[str, Any]]] = defaultdict(
        list
    )
    for symbol in result["symbols"]:
        persisted_symbols_by_path[str(symbol.get("path") or "")].append(symbol)
    for relationship in result["relationships"]:
        persisted_relationships_by_path[
            str(relationship.get("path") or "")
        ].append(relationship)
    for file in result["files"]:
        path = str(file.get("path") or "")
        file["analysis_sha256"] = _file_analysis_digest(
            path,
            persisted_symbols_by_path.get(path, []),
            persisted_relationships_by_path.get(path, []),
        )
    result["derived_sha256"] = _derived_artifacts_digest(result)
    result["integrity_sha256"] = _integrity_digest(result)
    return result
