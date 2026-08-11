from __future__ import annotations

import html
import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Any, Iterable

from .persistence import OutputLock, SecureDirectory, _rename_noreplace
from .skill_validation import (
    GENERATOR_ID,
    MARKER_NAME,
    MARKER_SCHEMA_VERSION,
    PAYLOAD_SCHEMA_VERSION,
    REQUIRED_FILES,
    render_openai_yaml,
    render_skill_markdown,
    sha256_bytes,
    validate_exported_skill,
    validate_skill_payload,
)


def _skill_name(project_name: str, requested: str | None = None) -> str:
    raw = requested or f"understand-{project_name}"
    normalized = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return (normalized or "understand-repository")[:64].rstrip("-")


def _selected_features(index: dict[str, Any], feature_ids: Iterable[str] | None) -> list[dict[str, Any]]:
    features = [item for item in index.get("features", []) if isinstance(item, dict)]
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in features:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("feature record is missing an id")
        if identifier in by_id:
            raise ValueError(f"duplicate feature id: {identifier}")
        by_id[identifier] = item
        order.append(identifier)

    requested = list(dict.fromkeys(str(item) for item in (feature_ids or []) if item))
    if not requested:
        return [by_id[identifier] for identifier in order]
    missing = sorted(set(requested) - set(by_id))
    if missing:
        raise ValueError(f"unknown feature id(s): {', '.join(missing)}")
    return [by_id[identifier] for identifier in requested]


def _index_map(index: dict[str, Any], name: str) -> dict[str, dict[str, Any]]:
    value = index.get(name, [])
    if not isinstance(value, list):
        raise ValueError(f"invalid index collection: {name}")
    result: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"invalid record in index collection: {name}")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"{name} record is missing an id")
        if identifier in result:
            raise ValueError(f"duplicate {name} id: {identifier}")
        result[identifier] = item
    return result


def _artifact_records(index: dict[str, Any], name: str, feature_ids: set[str]) -> list[dict[str, Any]]:
    value = index.get(name, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"invalid index collection: {name}")
    selected = [item for item in value if str(item.get("feature_id")) in feature_ids]
    seen: set[str] = set()
    for item in selected:
        feature_id = str(item.get("feature_id"))
        if feature_id in seen:
            raise ValueError(f"duplicate {name} artifact for feature: {feature_id}")
        seen.add(feature_id)
    return selected


def _id_list(value: object, context: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"invalid identifier list: {context}")
    return value


def _step_records(value: object, context: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"invalid steps collection: {context}")
    return value


_PUBLIC_FIELDS: dict[str, tuple[str, ...]] = {
    "project": (
        "name",
        "path",
        "git_root",
        "is_git",
        "commit",
        "branch",
        "dirty",
        "remote",
        "license",
        "analyzed_at",
    ),
    "feature": (
        "id",
        "title",
        "kind",
        "summary",
        "entrypoint",
        "confidence",
        "source",
        "steps",
        "component_ids",
        "evidence_ids",
        "test_evidence_ids",
        "technology_tags",
        "entry_symbol_id",
    ),
    "module": (
        "id",
        "name",
        "path",
        "file_count",
        "symbol_count",
        "languages",
        "entrypoints",
    ),
    "file": ("id", "path", "language", "size", "lines", "sha256", "module", "symbols"),
    "symbol": (
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
    ),
    "relationship": (
        "id",
        "source_id",
        "target_id",
        "target_name",
        "kind",
        "path",
        "line",
        "analyzer",
        "confidence",
    ),
    "evidence": (
        "id",
        "path",
        "line_start",
        "line_end",
        "snippet",
        "snippet_sha256",
        "kind",
        "confidence",
        "analyzer",
        "symbol_id",
    ),
    "tutorial": (
        "id",
        "feature_id",
        "title",
        "opening",
        "steps",
        "closing",
        "evidence_ids",
        "confidence",
        "source",
    ),
    "codemap": (
        "id",
        "feature_id",
        "title",
        "node_ids",
        "edge_ids",
        "steps",
        "mermaid",
        "evidence_ids",
    ),
    "coverage": ("feature_id", "score", "status", "covered", "gaps", "metrics"),
    "step": (
        "order",
        "title",
        "explanation",
        "path",
        "line_start",
        "line_end",
        "evidence_ids",
        "symbol_id",
        "relationship_id",
    ),
}


def _project_record(kind: str, record: object) -> dict[str, Any]:
    """Copy only bounded, documented fields into the untrusted reference bundle."""

    if not isinstance(record, dict):
        raise ValueError(f"invalid {kind} record")
    projected = {field: record[field] for field in _PUBLIC_FIELDS[kind] if field in record}
    if "steps" in projected:
        projected["steps"] = [
            _project_record("step", step)
            for step in _step_records(projected["steps"], f"{kind} steps")
        ]
    return projected


def _reference_payload(index: dict[str, Any], features: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a fail-closed transitive closure for the selected feature subgraph."""

    feature_ids = {str(item["id"]) for item in features}
    modules_by_id = _index_map(index, "modules") if index.get("modules") else {}
    files_by_id = _index_map(index, "files")
    symbols_by_id = _index_map(index, "symbols") if index.get("symbols") else {}
    relationships_by_id = _index_map(index, "relationships") if index.get("relationships") else {}
    evidence_by_id = _index_map(index, "evidence") if index.get("evidence") else {}
    files_by_path = {
        str(item.get("path")): item for item in files_by_id.values() if isinstance(item.get("path"), str)
    }
    if len(files_by_path) != len(files_by_id):
        raise ValueError("files contain missing or duplicate source paths")
    modules_by_name = {
        str(item.get("name")): item for item in modules_by_id.values() if isinstance(item.get("name"), str)
    }
    tutorials = _artifact_records(index, "tutorials", feature_ids)
    codemaps = _artifact_records(index, "codemaps", feature_ids)
    coverage = _artifact_records(index, "coverage", feature_ids)

    module_ids: set[str] = set()
    file_ids: set[str] = set()
    symbol_ids: set[str] = set()
    relationship_ids: set[str] = set()
    evidence_ids: set[str] = set()
    paths: set[str] = set()

    def add_ids(target: set[str], value: object, context: str) -> None:
        target.update(_id_list(value, context))

    def collect_steps(value: object, context: str) -> None:
        for step in _step_records(value, context):
            path = step.get("path")
            if not isinstance(path, str) or not path:
                raise ValueError(f"{context} step is missing its source path")
            paths.add(path)
            symbol_id = step.get("symbol_id")
            relationship_id = step.get("relationship_id")
            if symbol_id is not None:
                if not isinstance(symbol_id, str) or not symbol_id:
                    raise ValueError(f"{context} step has an invalid symbol id")
                symbol_ids.add(symbol_id)
            if relationship_id is not None:
                if not isinstance(relationship_id, str) or not relationship_id:
                    raise ValueError(f"{context} step has an invalid relationship id")
                relationship_ids.add(relationship_id)
            add_ids(evidence_ids, step.get("evidence_ids", []), f"{context} step evidence")

    for feature in features:
        feature_id = str(feature["id"])
        entrypoint = feature.get("entrypoint")
        if isinstance(entrypoint, str) and entrypoint in files_by_path:
            paths.add(entrypoint)
        add_ids(module_ids, feature.get("component_ids", []), f"feature {feature_id} modules")
        add_ids(evidence_ids, feature.get("evidence_ids", []), f"feature {feature_id} evidence")
        add_ids(evidence_ids, feature.get("test_evidence_ids", []), f"feature {feature_id} test evidence")
        entry_symbol_id = feature.get("entry_symbol_id")
        if entry_symbol_id is not None:
            if not isinstance(entry_symbol_id, str) or not entry_symbol_id:
                raise ValueError(f"feature {feature_id} has an invalid entry symbol")
            symbol_ids.add(entry_symbol_id)
        collect_steps(feature.get("steps", []), f"feature {feature_id}")
    for tutorial in tutorials:
        add_ids(evidence_ids, tutorial.get("evidence_ids", []), f"tutorial {tutorial.get('id')} evidence")
        collect_steps(tutorial.get("steps", []), f"tutorial {tutorial.get('id')}")
    for codemap in codemaps:
        add_ids(evidence_ids, codemap.get("evidence_ids", []), f"codemap {codemap.get('id')} evidence")
        collect_steps(codemap.get("steps", []), f"codemap {codemap.get('id')}")
        for node_id in _id_list(codemap.get("node_ids", []), f"codemap {codemap.get('id')} nodes"):
            if node_id in symbols_by_id:
                symbol_ids.add(node_id)
            elif node_id in files_by_id:
                file_ids.add(node_id)
            elif not node_id.startswith("codemap-node_"):
                raise ValueError(f"codemap refers to missing node: {node_id}")
        for edge_id in _id_list(codemap.get("edge_ids", []), f"codemap {codemap.get('id')} edges"):
            if edge_id in relationships_by_id:
                relationship_ids.add(edge_id)
            elif not edge_id.startswith("codemap-edge_"):
                raise ValueError(f"codemap refers to missing edge: {edge_id}")

    missing_modules = sorted(module_ids - set(modules_by_id))
    missing_symbols = sorted(symbol_ids - set(symbols_by_id))
    missing_relationships = sorted(relationship_ids - set(relationships_by_id))
    missing_evidence = sorted(evidence_ids - set(evidence_by_id))
    if missing_modules:
        raise ValueError(f"selected features refer to missing modules: {', '.join(missing_modules)}")
    if missing_symbols:
        raise ValueError(f"selected features refer to missing symbols: {', '.join(missing_symbols)}")
    if missing_relationships:
        raise ValueError(f"selected features refer to missing relationships: {', '.join(missing_relationships)}")
    if missing_evidence:
        raise ValueError(f"selected features refer to missing evidence: {', '.join(missing_evidence)}")

    # Evidence can point at a symbol and always points at a source or test file.
    for evidence_id in list(evidence_ids):
        item = evidence_by_id[evidence_id]
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError(f"evidence {evidence_id} is missing its source path")
        paths.add(path)
        symbol_id = item.get("symbol_id")
        if symbol_id is not None:
            if not isinstance(symbol_id, str) or symbol_id not in symbols_by_id:
                raise ValueError(f"evidence {evidence_id} refers to missing symbol: {symbol_id}")
            symbol_ids.add(symbol_id)

    # Relationship endpoints are part of the subgraph, even when no display step mentions them.
    for relationship_id in list(relationship_ids):
        relationship = relationships_by_id[relationship_id]
        path = relationship.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError(f"relationship {relationship_id} is missing its source path")
        paths.add(path)
        for endpoint_name in ("source_id", "target_id"):
            endpoint = relationship.get(endpoint_name)
            if endpoint is None and endpoint_name == "target_id":
                continue
            if endpoint in symbols_by_id:
                symbol_ids.add(str(endpoint))
            elif endpoint in files_by_id:
                file_ids.add(str(endpoint))
            else:
                raise ValueError(f"relationship {relationship_id} refers to missing {endpoint_name}: {endpoint}")

    # Every selected symbol closes over its lexical parent and defining file.
    pending_symbols = list(symbol_ids)
    visited_symbols: set[str] = set()
    while pending_symbols:
        symbol_id = pending_symbols.pop()
        if symbol_id in visited_symbols:
            continue
        visited_symbols.add(symbol_id)
        symbol = symbols_by_id[symbol_id]
        parent_id = symbol.get("parent_id")
        if parent_id is not None:
            if not isinstance(parent_id, str) or parent_id not in symbols_by_id:
                raise ValueError(f"symbol {symbol_id} refers to missing parent symbol: {parent_id}")
            if parent_id not in symbol_ids:
                symbol_ids.add(parent_id)
                pending_symbols.append(parent_id)
        file_id = symbol.get("file_id")
        if not isinstance(file_id, str) or file_id not in files_by_id:
            raise ValueError(f"symbol {symbol_id} refers to missing file: {file_id}")
        file_ids.add(file_id)
        path = symbol.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError(f"symbol {symbol_id} is missing its source path")
        paths.add(path)

    for path in paths:
        file = files_by_path.get(path)
        if file is None:
            raise ValueError(f"selected feature subgraph refers to missing file path: {path}")
        file_ids.add(str(file["id"]))

    # Preserve module navigation for every included file as well as explicit feature components.
    for file_id in list(file_ids):
        module_name = files_by_id[file_id].get("module")
        if isinstance(module_name, str) and module_name:
            module = modules_by_name.get(module_name)
            if modules_by_id and module is None:
                raise ValueError(f"file {file_id} refers to missing module: {module_name}")
            if module is not None:
                module_ids.add(str(module["id"]))

    selected_files = [item for identifier, item in files_by_id.items() if identifier in file_ids]
    selected_symbols = [
        item for identifier, item in symbols_by_id.items() if identifier in symbol_ids
    ]
    selected_paths = {str(item["path"]) for item in selected_files}
    selected_symbol_ids = {str(item["id"]) for item in selected_symbols}
    symbol_counts: dict[str, int] = {}
    for symbol in selected_symbols:
        file_id = str(symbol["file_id"])
        symbol_counts[file_id] = symbol_counts.get(file_id, 0) + 1

    # Project every record onto the public payload schema.  In addition to
    # dropping prompt-like unknown fields, shrink embedded navigation arrays to
    # references that are actually present in this feature subgraph.
    projected_files: list[dict[str, Any]] = []
    for item in selected_files:
        projected = _project_record("file", item)
        projected["symbols"] = [
            identifier
            for identifier in _id_list(item.get("symbols", []), f"file {item['id']} symbols")
            if identifier in selected_symbol_ids
        ]
        projected_files.append(projected)

    projected_modules: list[dict[str, Any]] = []
    for identifier, item in modules_by_id.items():
        if identifier not in module_ids:
            continue
        projected = _project_record("module", item)
        module_name = str(item.get("name"))
        module_files = [file for file in selected_files if str(file.get("module")) == module_name]
        projected["file_count"] = len(module_files)
        projected["symbol_count"] = sum(symbol_counts.get(str(file["id"]), 0) for file in module_files)
        languages: dict[str, int] = {}
        for file in module_files:
            language = str(file.get("language") or "Unknown")
            languages[language] = languages.get(language, 0) + 1
        projected["languages"] = dict(sorted(languages.items()))
        projected["entrypoints"] = [
            path
            for path in _id_list(item.get("entrypoints", []), f"module {identifier} entrypoints")
            if path in selected_paths
        ]
        projected_modules.append(projected)

    payload = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "project": _project_record("project", index.get("project", {})),
        "features": [_project_record("feature", item) for item in features],
        "modules": projected_modules,
        "files": projected_files,
        "symbols": [_project_record("symbol", item) for item in selected_symbols],
        "relationships": [
            _project_record("relationship", item)
            for identifier, item in relationships_by_id.items()
            if identifier in relationship_ids
        ],
        "evidence": [
            _project_record("evidence", item)
            for identifier, item in evidence_by_id.items()
            if identifier in evidence_ids
        ],
        "tutorials": [_project_record("tutorial", item) for item in tutorials],
        "codemaps": [_project_record("codemap", item) for item in codemaps],
        "coverage": [_project_record("coverage", item) for item in coverage],
    }
    record_count = sum(
        len(value) for value in payload.values() if isinstance(value, list)
    )
    if record_count > 250_000:
        raise ValueError("selected Skill payload exceeds the 250000-record safety budget")
    encoded_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if encoded_size > 64 * 1024 * 1024:
        raise ValueError("selected Skill payload exceeds the 64 MiB safety budget")
    validate_skill_payload(payload)
    return payload


def _markdown_text(value: object, fallback: str = "") -> str:
    text = " ".join(str(value if value is not None else fallback).replace("\0", "").split())
    text = html.escape(text, quote=True)
    return re.sub(r"([\\`*_{}\[\]()#+!|<>])", r"\\\1", text)


def _location(path: object, line_start: object, line_end: object) -> str:
    return _markdown_text(f"{path}:{line_start}-{line_end}")


def _reference_markdown(payload: dict[str, Any]) -> str:
    project = payload.get("project", {})
    lines = [
        "# 功能与代码索引",
        "",
        f"项目：{_markdown_text(project.get('name'), 'unknown')}",
        f"快照：{_markdown_text(project.get('commit'), 'working-tree')}",
        "",
        "每个结论都必须回到 code-index.json 的 evidence 与原始源码核对。",
        "",
    ]
    evidence_by_id = {item.get("id"): item for item in payload.get("evidence", [])}
    for feature in payload.get("features", []):
        lines.extend(
            [
                f"## {_markdown_text(feature.get('title') or feature.get('id'), '未命名功能')}",
                "",
                _markdown_text(feature.get("summary"), "暂无摘要。"),
                "",
                f"入口：{_markdown_text(feature.get('entrypoint'), 'unknown')}  ",
                f"可信度：{_markdown_text(feature.get('confidence'), 'unknown')}",
                "",
                "### 执行链",
                "",
            ]
        )
        for step in feature.get("steps", []):
            lines.append(
                f"{int(step.get('order', 0))}. **{_markdown_text(step.get('title'), '步骤')}** — "
                f"{_location(step.get('path'), step.get('line_start'), step.get('line_end'))}"
            )
            if step.get("explanation"):
                lines.append(f"   {_markdown_text(step['explanation'])}")
        lines.extend(["", "### 直接证据", ""])
        for evidence_id in [*feature.get("evidence_ids", []), *feature.get("test_evidence_ids", [])]:
            evidence = evidence_by_id.get(evidence_id)
            if evidence:
                lines.append(
                    f"- {_location(evidence.get('path'), evidence.get('line_start'), evidence.get('line_end'))} "
                    f"({_markdown_text(evidence.get('confidence'), 'unknown')})"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _validate_source(index: dict[str, Any]) -> None:
    project = index.get("project")
    required_identity = {
        "name",
        "path",
        "git_root",
        "is_git",
        "commit",
        "branch",
        "dirty",
        "remote",
        "license",
        "analyzed_at",
    }
    if not isinstance(project, dict) or not required_identity.issubset(project):
        missing = sorted(required_identity - set(project if isinstance(project, dict) else ()))
        raise ValueError(
            "index project identity is incomplete; rebuild the index before export "
            f"(missing: {', '.join(missing)})"
        )
    project_path = project.get("path") if isinstance(project, dict) else None
    if not project_path:
        raise ValueError("index has no source repository path; rebuild the index before export")
    source = Path(str(project_path)).expanduser()
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"source repository is missing or unsafe: {source}")
    from .validation import validate_index

    validation = validate_index(index, source)
    errors = [item for item in validation.get("issues", []) if item.get("severity") == "error"]
    dirty = [item for item in validation.get("issues", []) if item.get("code") == "dirty-worktree"]
    if not validation.get("valid") or errors:
        codes = ", ".join(str(item.get("code")) for item in errors) or "validation-failed"
        raise ValueError(f"index is stale or internally inconsistent; run index again ({codes})")
    if dirty:
        raise ValueError("source repository has a dirty working tree; commit/stash changes and re-index before export")

    from .scanner import scan_repository
    from .snapshot import capture_snapshot

    snapshot = capture_snapshot(source)
    if project["name"] != snapshot.name or Path(str(project["path"])).expanduser().resolve() != Path(
        snapshot.path
    ).expanduser().resolve():
        raise ValueError("index project identity differs from the source; freshness cannot be proven")
    indexed_is_git = project["is_git"]
    if not isinstance(indexed_is_git, bool):
        raise ValueError("index project is_git identity must be a boolean")
    if indexed_is_git != snapshot.is_git:
        raise ValueError("index Git identity differs from the source; freshness cannot be proven")
    if snapshot.is_git:
        indexed_commit = project["commit"]
        if (
            not isinstance(indexed_commit, str)
            or not indexed_commit
            or snapshot.commit is None
            or indexed_commit != snapshot.commit
        ):
            raise ValueError("index Git commit differs from the source; freshness cannot be proven")
        indexed_git_root = project["git_root"]
        if (
            not isinstance(indexed_git_root, str)
            or not indexed_git_root
            or snapshot.git_root is None
            or Path(indexed_git_root).expanduser().resolve()
            != Path(snapshot.git_root).expanduser().resolve()
        ):
            raise ValueError("index Git root differs from the source; freshness cannot be proven")
        if snapshot.dirty is None:
            raise ValueError("source Git status is unavailable; freshness cannot be proven")
        if snapshot.dirty:
            raise ValueError(
                "source repository has a dirty working tree; commit/stash changes and re-index before export"
            )
        return

    if project["commit"] is not None or project["git_root"] is not None:
        raise ValueError("non-Git index contains contradictory Git identity metadata")

    # Non-Git sources have no commit/status oracle.  Re-scan the entire default
    # indexable file set and compare both membership and content digests.
    scan = scan_repository(source)
    if scan.truncated or any(
        item.severity == "error" for item in scan.diagnostics
    ):
        raise ValueError("non-Git source could not be fully rescanned; freshness cannot be proven")
    indexed_files = index.get("files")
    if not isinstance(indexed_files, list) or any(not isinstance(item, dict) for item in indexed_files):
        raise ValueError("index files collection is malformed")
    expected = {
        str(item.get("path")): str(item.get("sha256"))
        for item in indexed_files
        if isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str)
    }
    if len(expected) != len(indexed_files):
        raise ValueError("index file manifest is incomplete; freshness cannot be proven")
    actual = {item.path: item.sha256 for item in scan.files}
    if actual != expected:
        added = sorted(set(actual) - set(expected))
        deleted = sorted(set(expected) - set(actual))
        modified = sorted(
            path for path in set(actual) & set(expected) if actual[path] != expected[path]
        )
        summary = ", ".join(
            part
            for part in (
                f"added={added[:3]}" if added else "",
                f"deleted={deleted[:3]}" if deleted else "",
                f"modified={modified[:3]}" if modified else "",
            )
            if part
        )
        raise ValueError(f"non-Git source changed after indexing; rebuild the index ({summary})")


def _reject_tree_symlinks(path: Path) -> None:
    if path.is_symlink():
        raise OSError(f"refusing to replace symbolic link: {path}")
    if not path.exists():
        return
    if not path.is_dir():
        return
    for current, directories, files in os.walk(path, followlinks=False):
        base = Path(current)
        for name in (*directories, *files):
            candidate = base / name
            if candidate.is_symlink():
                raise OSError(f"refusing to replace directory containing symbolic link: {candidate}")


def _owned_target(path: Path) -> bool:
    if not path.is_dir():
        return False
    marker = path / MARKER_NAME
    if not marker.is_file() or marker.is_symlink():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if payload.get("generator") != GENERATOR_ID or payload.get("schema_version") != MARKER_SCHEMA_VERSION:
        return False
    try:
        validate_exported_skill(path)
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    return True


_PRIVATE_STATE_SCHEMA = "1.0"
_PRIVATE_MARKER = ".repo-teacher-private-state.json"
_TRANSACTION_SCHEMA = "4.0"
_TRANSACTION_JOURNAL = "transaction.json"
_TRANSACTION_MARKER = ".repo-teacher-transaction.json"
_TRANSACTION_PHASES = ("PREPARED", "BACKED_UP", "PUBLISHED", "VERIFIED", "COMMITTED")
_JSON_CONTROL_MAX_BYTES = 64 * 1024
_IDENTITY_KEYS = {"generation_id", "marker_sha256", "tree_sha256"}


def _entry_identity_record(identity: tuple[int, int, int]) -> dict[str, int]:
    return {"device": identity[0], "inode": identity[1], "type": identity[2]}


def _entry_identity_tuple(value: object, label: str) -> tuple[int, int, int]:
    if not isinstance(value, dict) or set(value) != {"device", "inode", "type"}:
        raise OSError(f"Skill export transaction has an invalid {label}")
    fields = (value.get("device"), value.get("inode"), value.get("type"))
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in fields):
        raise OSError(f"Skill export transaction has an invalid {label}")
    identity = (fields[0], fields[1], fields[2])
    if identity[2] != stat.S_IFDIR:
        raise OSError(f"Skill export transaction {label} is not a directory")
    return identity


def _generation_identity(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != _IDENTITY_KEYS:
        raise OSError(f"Skill export transaction has an invalid {label}")
    if (
        not isinstance(value.get("generation_id"), str)
        or re.fullmatch(r"[0-9a-f]{32}", value["generation_id"]) is None
        or any(
            not isinstance(value.get(key), str)
            or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None
            for key in ("marker_sha256", "tree_sha256")
        )
    ):
        raise OSError(f"Skill export transaction has an invalid {label}")
    return value


def _transaction_hash(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "record_sha256"}
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(encoded)


def _state_name(target_name: str) -> str:
    digest = hashlib.sha256(target_name.encode("utf-8")).hexdigest()[:20]
    return f".repo-teacher-skill-private-{digest}"


def _closed_set_snapshot(
    directory: SecureDirectory,
    expected_types: dict[str, int],
    *,
    label: str,
) -> dict[str, tuple[int, int, int]]:
    """Capture an exact directory entry set and bracket every entry identity."""

    directory.assert_unchanged()
    names = set(os.listdir(directory.descriptor))
    expected_names = set(expected_types)
    if names != expected_names:
        raise OSError(
            f"{label} has an unexpected closed set "
            f"(extra={sorted(names - expected_names)}, missing={sorted(expected_names - names)})"
        )
    identities: dict[str, tuple[int, int, int]] = {}
    for name, expected_type in expected_types.items():
        identity = directory.child_identity(name)
        if identity is None or identity[2] != expected_type:
            raise OSError(f"{label} contains an unexpected entry type: {name}")
        identities[name] = identity
    if set(os.listdir(directory.descriptor)) != names:
        raise OSError(f"{label} changed while its closed set was inspected")
    for name, identity in identities.items():
        directory.assert_child_identity(name, identity)
    directory.assert_unchanged()
    return identities


def _read_identity_file(
    parent: SecureDirectory,
    name: str,
    expected: tuple[int, int, int],
    *,
    total_bytes: int,
) -> tuple[bytes, int]:
    """Read one digest input through a held parent fd and preserve its identity."""

    parent.assert_child_identity(name, expected)
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent.descriptor,
    )
    try:
        before = os.fstat(descriptor)
        opened = _identity_from_stat(before)
        if opened != expected or opened[2] != stat.S_IFREG:
            raise OSError(f"Skill identity contains an unexpected file: {parent.child_path(name)}")
        new_total = total_bytes + before.st_size
        if before.st_size > 64 * 1024 * 1024 or new_total > 96 * 1024 * 1024:
            raise OSError(f"transaction tree exceeds its bounded file budget: {parent.path}")
        raw = bytearray()
        while len(raw) < before.st_size:
            chunk = os.read(descriptor, min(65536, before.st_size - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        stable_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        stable_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if len(raw) != before.st_size or stable_after != stable_before:
            raise OSError(f"Skill identity file changed while read: {parent.child_path(name)}")
    finally:
        os.close(descriptor)
    parent.assert_child_identity(name, expected)
    return bytes(raw), new_total


def _tree_digest(path: Path) -> str:
    """Validate and hash the exact Skill tree through identity-bound directory fds."""

    validate_exported_skill(path)
    digest = hashlib.sha256(b"directory\0")
    for directory in ("agents", "references"):
        digest.update(b"d\0" + directory.encode("utf-8") + b"\0")
    root_types = {
        MARKER_NAME: stat.S_IFREG,
        "SKILL.md": stat.S_IFREG,
        "agents": stat.S_IFDIR,
        "references": stat.S_IFDIR,
    }
    agent_types = {"openai.yaml": stat.S_IFREG}
    reference_types = {
        "code-index.json": stat.S_IFREG,
        "code-index.md": stat.S_IFREG,
    }
    with SecureDirectory(path) as root:
        root_entries = _closed_set_snapshot(root, root_types, label="Skill root")
        with (
            SecureDirectory(root.child_path("agents")) as agents,
            SecureDirectory(root.child_path("references")) as references,
        ):
            if _identity_from_stat(os.fstat(agents.descriptor)) != root_entries["agents"]:
                raise OSError("Skill agents directory changed before digest")
            if _identity_from_stat(os.fstat(references.descriptor)) != root_entries["references"]:
                raise OSError("Skill references directory changed before digest")
            agent_entries = _closed_set_snapshot(
                agents, agent_types, label="Skill agents directory"
            )
            reference_entries = _closed_set_snapshot(
                references, reference_types, label="Skill references directory"
            )
            inputs = {
                MARKER_NAME: (root, MARKER_NAME, root_entries[MARKER_NAME]),
                "SKILL.md": (root, "SKILL.md", root_entries["SKILL.md"]),
                "agents/openai.yaml": (
                    agents,
                    "openai.yaml",
                    agent_entries["openai.yaml"],
                ),
                "references/code-index.json": (
                    references,
                    "code-index.json",
                    reference_entries["code-index.json"],
                ),
                "references/code-index.md": (
                    references,
                    "code-index.md",
                    reference_entries["code-index.md"],
                ),
            }
            total_bytes = 0
            for relative in sorted((*REQUIRED_FILES, MARKER_NAME)):
                parent, name, identity = inputs[relative]
                raw, total_bytes = _read_identity_file(
                    parent, name, identity, total_bytes=total_bytes
                )
                digest.update(b"f\0" + relative.encode("utf-8") + b"\0")
                digest.update(raw)
            if _closed_set_snapshot(root, root_types, label="Skill root") != root_entries:
                raise OSError("Skill root entries changed during digest")
            if (
                _closed_set_snapshot(agents, agent_types, label="Skill agents directory")
                != agent_entries
            ):
                raise OSError("Skill agents entries changed during digest")
            if (
                _closed_set_snapshot(
                    references, reference_types, label="Skill references directory"
                )
                != reference_entries
            ):
                raise OSError("Skill references entries changed during digest")
            root.assert_child_identity("agents", root_entries["agents"])
            root.assert_child_identity("references", root_entries["references"])
    return digest.hexdigest()


def _marker_identity(path: Path) -> dict[str, str]:
    validation = validate_exported_skill(path)
    if not validation.get("valid"):
        raise ValueError(f"Skill generation is invalid: {path}")
    marker_path = path / MARKER_NAME
    with SecureDirectory(marker_path.parent) as parent:
        descriptor = os.open(
            marker_path.name,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent.descriptor,
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _JSON_CONTROL_MAX_BYTES:
                raise OSError("Skill ownership marker is not a bounded regular file")
            marker_raw = bytearray()
            while len(marker_raw) < metadata.st_size:
                chunk = os.read(descriptor, metadata.st_size - len(marker_raw))
                if not chunk:
                    break
                marker_raw.extend(chunk)
            if len(marker_raw) != metadata.st_size:
                raise OSError("Skill ownership marker changed while read")
        finally:
            os.close(descriptor)
    raw = bytes(marker_raw)
    marker = json.loads(raw)
    return {
        "generation_id": str(marker["generation_id"]),
        "marker_sha256": sha256_bytes(raw),
        "tree_sha256": _tree_digest(path),
    }


def _identity_matches(path: Path, expected: dict[str, Any] | None) -> bool:
    if expected is None or path.is_symlink() or not path.is_dir():
        return False
    try:
        return _marker_identity(path) == expected
    except (OSError, UnicodeDecodeError, ValueError):
        return False


def _assert_generation_identity(
    parent: SecureDirectory,
    name: str,
    entry_identity: tuple[int, int, int],
    generation_identity: dict[str, Any],
) -> None:
    """Bracket path-based content validation with the same entry identity."""

    parent.assert_child_identity(name, entry_identity)
    if not _identity_matches(parent.child_path(name), generation_identity):
        raise OSError(f"Skill generation content identity changed: {parent.child_path(name)}")
    parent.assert_child_identity(name, entry_identity)


def _identity_from_stat(metadata: os.stat_result) -> tuple[int, int, int]:
    return (metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode))


def _exclusive_text_at(parent_fd: int, name: str, content: str) -> tuple[int, int, int]:
    """Create an immutable direct child using only an already-held directory fd."""

    if not name or name in {".", ".."} or "/" in name or os.sep in name:
        raise OSError(f"unsafe exclusive child name: {name}")
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=parent_fd,
    )
    try:
        identity = _identity_from_stat(os.fstat(descriptor))
        if identity[2] != stat.S_IFREG:
            raise OSError(f"exclusive child is not a regular file: {name}")
        encoded = content.encode("utf-8")
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise OSError(f"exclusive child write made no progress: {name}")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    current = _identity_from_stat(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
    if current != identity:
        raise OSError(f"exclusive child name changed while written: {name}")
    os.fsync(parent_fd)
    return identity


def _exclusive_json_at(parent_fd: int, name: str, value: Any) -> tuple[int, int, int]:
    return _exclusive_text_at(
        parent_fd, name, json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )


def _mkdir_unique_at(parent_fd: int, prefix: str) -> tuple[str, int, tuple[int, int, int]]:
    """Create and hold an unpredictable private directory before writing to it."""

    for _ in range(128):
        name = f"{prefix}{uuid.uuid4().hex}"
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        identity = _identity_from_stat(os.fstat(descriptor))
        current = _identity_from_stat(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        if identity != current or identity[2] != stat.S_IFDIR:
            os.close(descriptor)
            raise OSError(f"private directory changed immediately after creation: {name}")
        os.fsync(parent_fd)
        return name, descriptor, identity
    raise FileExistsError("could not allocate a private transaction directory")


def _open_private_state(parent: SecureDirectory, target_name: str) -> SecureDirectory:
    state_name = _state_name(target_name)
    state_path = parent.child_path(state_name)
    identity = parent.child_identity(state_name)
    if identity is None:
        init_name, init_fd, init_identity = _mkdir_unique_at(
            parent.descriptor, f".{state_name}-init-"
        )
        try:
            _exclusive_json_at(
                init_fd,
                _PRIVATE_MARKER,
                {
                    "schema_version": _PRIVATE_STATE_SCHEMA,
                    "generator": GENERATOR_ID,
                    "target_name": target_name,
                    "state_id": uuid.uuid4().hex,
                },
            )
        finally:
            os.close(init_fd)
        parent.replace_to(
            init_name,
            parent,
            state_name,
            expected_source=init_identity,
            expected_target=None,
        )
        identity = init_identity
    parent.assert_child_identity(state_name, identity)
    metadata = os.stat(state_name, dir_fd=parent.descriptor, follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise OSError("Skill private transaction state has an unsafe owner or type")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise OSError("Skill private transaction state is not private")
    state = SecureDirectory(state_path)
    state.__enter__()
    try:
        opened_identity = _identity_from_stat(os.fstat(state.descriptor))
        if opened_identity != identity:
            raise OSError("Skill private transaction state changed before it was opened")
        marker = _read_json_child(state, _PRIVATE_MARKER, "Skill private state marker")
        parent.assert_child_identity(state_name, identity)
    except BaseException:
        state.__exit__(None, None, None)
        raise
    state_id = marker.get("state_id")
    if (
        set(marker) != {"schema_version", "generator", "target_name", "state_id"}
        or marker.get("schema_version") != _PRIVATE_STATE_SCHEMA
        or marker.get("generator") != GENERATOR_ID
        or marker.get("target_name") != target_name
        or not isinstance(state_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", state_id) is None
    ):
        state.__exit__(None, None, None)
        raise OSError("Skill private transaction state is not owned by this destination")
    state.state_id = state_id
    return state


def _read_json_child(directory: SecureDirectory, name: str, label: str) -> dict[str, Any]:
    expected = directory.child_identity(name)
    if expected is None:
        raise OSError(f"{label} is unreadable or missing")
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory.descriptor,
        )
    except OSError as error:
        raise OSError(f"{label} is unreadable or missing") from error
    try:
        metadata = os.fstat(descriptor)
        opened = _identity_from_stat(metadata)
        if opened != expected:
            raise OSError(f"{label} changed before it was opened")
        if opened[2] != stat.S_IFREG or metadata.st_size > _JSON_CONTROL_MAX_BYTES:
            raise OSError(f"{label} is not a bounded regular file")
        raw = bytearray()
        while len(raw) <= _JSON_CONTROL_MAX_BYTES:
            chunk = os.read(descriptor, min(65536, _JSON_CONTROL_MAX_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) != metadata.st_size:
            raise OSError(f"{label} changed while it was read")
        value = json.loads(bytes(raw).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OSError(f"{label} is unreadable") from error
    finally:
        os.close(descriptor)
    directory.assert_child_identity(name, expected)
    if not isinstance(value, dict):
        raise OSError(f"{label} is malformed")
    return value


def _child_names(directory: SecureDirectory) -> set[str]:
    directory.assert_unchanged()
    names = set(os.listdir(directory.descriptor))
    identities: dict[str, tuple[int, int, int]] = {}
    for name in names:
        identity = directory.child_identity(name)
        if identity is None or identity[2] not in {stat.S_IFREG, stat.S_IFDIR}:
            raise OSError(f"Skill transaction contains a non-regular object: {name}")
        identities[name] = identity
    if set(os.listdir(directory.descriptor)) != names:
        raise OSError("Skill transaction closed set changed while it was inspected")
    for name, identity in identities.items():
        directory.assert_child_identity(name, identity)
    directory.assert_unchanged()
    return names


def _assert_exact_children(directory: SecureDirectory, expected: set[str], *, label: str) -> None:
    actual = _child_names(directory)
    if actual != expected:
        raise OSError(
            f"{label} has an unexpected closed set; preserving it for manual inspection "
            f"(extra={sorted(actual - expected)}, missing={sorted(expected - actual)})"
        )


def _safe_transaction_child(value: object, transaction_id: str) -> str:
    pattern = rf"transaction-{transaction_id}-[0-9a-f]{{16}}(?:[0-9a-f]{{16}})?"
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise OSError("Skill export transaction marker contains an unsafe path")
    return value


def _phase_filename(phase: str) -> str:
    return f"phase-{phase}.json"


def _validate_transaction(
    transaction: dict[str, Any], target_name: str, state_id: str
) -> tuple[str, str, tuple[int, int, int], tuple[int, int, int]]:
    expected_keys = {
        "schema_version", "generator", "state_id", "transaction_id",
        "transaction_dir", "target_name", "phase", "force_authorized",
        "previous_owned", "previous_transaction_id", "workspace_identity",
        "stage_identity", "previous_entry_identity", "new_identity",
        "previous_identity", "record_sha256",
    }
    if set(transaction) != expected_keys:
        raise OSError("Skill export transaction marker has an unexpected schema")
    transaction_id = transaction.get("transaction_id")
    previous_transaction_id = transaction.get("previous_transaction_id")
    if (
        transaction.get("schema_version") != _TRANSACTION_SCHEMA
        or transaction.get("generator") != GENERATOR_ID
        or transaction.get("state_id") != state_id
        or transaction.get("target_name") != target_name
        or not isinstance(transaction_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None
        or transaction.get("phase") not in _TRANSACTION_PHASES
        or not isinstance(transaction.get("force_authorized"), bool)
        or not isinstance(transaction.get("previous_owned"), bool)
        or transaction.get("record_sha256") != _transaction_hash(transaction)
        or (
            previous_transaction_id is not None
            and (
                not isinstance(previous_transaction_id, str)
                or re.fullmatch(r"[0-9a-f]{32}", previous_transaction_id) is None
            )
        )
    ):
        raise OSError("Skill export transaction marker does not match its destination")
    transaction_dir = _safe_transaction_child(transaction.get("transaction_dir"), transaction_id)
    workspace_identity = _entry_identity_tuple(transaction.get("workspace_identity"), "workspace_identity")
    stage_identity = _entry_identity_tuple(transaction.get("stage_identity"), "stage_identity")
    _generation_identity(transaction.get("new_identity"), "new_identity")

    previous_owned = transaction["previous_owned"]
    previous_entry = transaction.get("previous_entry_identity")
    previous_identity = transaction.get("previous_identity")
    if previous_owned:
        if not transaction["force_authorized"]:
            raise OSError("Skill export transaction replaced a prior generation without force authorization")
        _entry_identity_tuple(previous_entry, "previous_entry_identity")
        _generation_identity(previous_identity, "previous_identity")
    elif any(value is not None for value in (previous_entry, previous_identity, previous_transaction_id)):
        raise OSError("Skill export transaction previous ownership is contradictory")
    return transaction_id, transaction_dir, workspace_identity, stage_identity


def _same_transaction(left: dict[str, Any], right: dict[str, Any]) -> bool:
    ignored = {"phase", "record_sha256"}
    return {k: v for k, v in left.items() if k not in ignored} == {
        k: v for k, v in right.items() if k not in ignored
    }


def _inspect_workspace(
    state: SecureDirectory,
    transaction_dir: str,
    target_name: str,
) -> tuple[dict[str, Any], str]:
    transaction_path = state.child_path(transaction_dir)
    with SecureDirectory(transaction_path) as workspace:
        marker = _read_json_child(workspace, _TRANSACTION_MARKER, "transaction marker")
        journal = _read_json_child(workspace, _TRANSACTION_JOURNAL, "transaction journal")
        transaction_id, recorded_dir, workspace_identity, stage_identity = _validate_transaction(
            journal, target_name, str(getattr(state, "state_id", ""))
        )
        if recorded_dir != transaction_dir or marker != journal or journal["phase"] != "PREPARED":
            raise OSError("Skill export transaction ownership marker does not match its journal")
        actual_workspace = state.child_identity(transaction_dir)
        if actual_workspace != workspace_identity:
            raise OSError("Skill export transaction workspace identity changed; preserving all content")

        latest = "PREPARED"
        event_names: set[str] = set()
        missing_seen = False
        for phase in _TRANSACTION_PHASES[1:]:
            filename = _phase_filename(phase)
            exists = workspace.child_identity(filename) is not None
            if not exists:
                missing_seen = True
                continue
            if missing_seen:
                raise OSError("Skill export transaction phase history is not contiguous")
            event = _read_json_child(workspace, filename, f"transaction phase {phase}")
            _validate_transaction(event, target_name, str(getattr(state, "state_id", "")))
            if event["phase"] != phase or not _same_transaction(journal, event):
                raise OSError("Skill export transaction phase record is inconsistent")
            latest = phase
            event_names.add(filename)

        expected = {_TRANSACTION_MARKER, _TRANSACTION_JOURNAL, *event_names}
        phase_index = _TRANSACTION_PHASES.index(latest)
        if phase_index < _TRANSACTION_PHASES.index("PUBLISHED"):
            expected.add("stage")
            _assert_generation_identity(
                workspace, "stage", stage_identity, journal["new_identity"]
            )
        if journal["previous_owned"] and phase_index >= _TRANSACTION_PHASES.index("BACKED_UP"):
            expected.add("backup")
            previous_entry = _entry_identity_tuple(
                journal["previous_entry_identity"], "previous_entry_identity"
            )
            _assert_generation_identity(
                workspace, "backup", previous_entry, journal["previous_identity"]
            )
        _assert_exact_children(workspace, expected, label="Skill export transaction workspace")
        workspace.assert_unchanged()
        state.assert_child_identity(transaction_dir, workspace_identity)
    return journal, latest


def _inspect_transactions(
    parent: SecureDirectory,
    state: SecureDirectory,
    target: Path,
) -> str | None:
    """Validate the append-only history and reject every unfinished state."""

    try:
        state_id = str(getattr(state, "state_id", ""))
        private_marker = _read_json_child(
            state, _PRIVATE_MARKER, "Skill private state marker"
        )
        if (
            set(private_marker) != {"schema_version", "generator", "target_name", "state_id"}
            or private_marker.get("schema_version") != _PRIVATE_STATE_SCHEMA
            or private_marker.get("generator") != GENERATOR_ID
            or private_marker.get("target_name") != target.name
            or private_marker.get("state_id") != state_id
        ):
            raise OSError("Skill private state marker changed or has an unexpected schema")
        names = _child_names(state)
    except OSError as error:
        raise OSError(
            "Skill private state is not provably regular; preserve and inspect "
            f"{state.path}: {error}"
        ) from error
    transaction_dirs = names - {_PRIVATE_MARKER}
    for name in transaction_dirs:
        identity = state.child_identity(name)
        if not name.startswith("transaction-") or identity is None or identity[2] != stat.S_IFDIR:
            raise OSError(
                "Skill private transaction state has an unexpected closed set; preserve and "
                f"inspect {state.child_path(name)}"
            )
    records: dict[str, tuple[dict[str, Any], str]] = {}
    directory_by_id: dict[str, str] = {}
    for transaction_dir in sorted(transaction_dirs):
        try:
            record, phase = _inspect_workspace(state, transaction_dir, target.name)
        except OSError as error:
            raise OSError(
                "Skill export transaction is not provably valid; preserving it for manual "
                f"inspection at {state.child_path(transaction_dir)}: {error}"
            ) from error
        transaction_id = str(record["transaction_id"])
        if transaction_id in records:
            raise OSError("Skill export transaction history contains a duplicate id")
        records[transaction_id] = (record, phase)
        directory_by_id[transaction_id] = transaction_dir
    incomplete = [
        (identifier, phase) for identifier, (_, phase) in records.items() if phase != "COMMITTED"
    ]
    if incomplete:
        identifier, phase = incomplete[0]
        raise OSError(
            "unfinished Skill export transaction preserved for manual inspection at "
            f"{state.child_path(directory_by_id[identifier])} (phase={phase})"
        )
    if not records:
        if _child_names(state) != names:
            raise OSError("Skill private state changed while its history was inspected")
        if _read_json_child(state, _PRIVATE_MARKER, "Skill private state marker") != private_marker:
            raise OSError("Skill private state marker changed while history was inspected")
        return None

    child_by_parent: dict[str, str] = {}
    roots: list[str] = []
    for identifier, (record, _) in records.items():
        previous_id = record["previous_transaction_id"]
        if previous_id is None:
            roots.append(identifier)
            continue
        if previous_id not in records or previous_id in child_by_parent:
            raise OSError("Skill export transaction history is not a single proven chain")
        parent_record = records[previous_id][0]
        if (
            record["previous_identity"] != parent_record["new_identity"]
            or record["previous_entry_identity"] != parent_record["stage_identity"]
        ):
            raise OSError("Skill export transaction history generation link is inconsistent")
        child_by_parent[previous_id] = identifier
    if len(roots) != 1:
        raise OSError("Skill export transaction history does not have exactly one root")
    cursor = roots[0]
    visited: set[str] = set()
    while cursor in child_by_parent:
        visited.add(cursor)
        cursor = child_by_parent[cursor]
    visited.add(cursor)
    if visited != set(records):
        raise OSError("Skill export transaction history contains a branch or cycle")
    tail = records[cursor][0]
    _assert_generation_identity(
        parent,
        target.name,
        _entry_identity_tuple(tail["stage_identity"], "stage_identity"),
        tail["new_identity"],
    )
    for transaction_dir in sorted(transaction_dirs):
        rechecked_record, rechecked_phase = _inspect_workspace(
            state, transaction_dir, target.name
        )
        transaction_id = str(rechecked_record["transaction_id"])
        if records.get(transaction_id) != (rechecked_record, rechecked_phase):
            raise OSError("Skill export transaction changed while history was inspected")
    if _child_names(state) != names:
        raise OSError("Skill private state changed while its history was inspected")
    if _read_json_child(state, _PRIVATE_MARKER, "Skill private state marker") != private_marker:
        raise OSError("Skill private state marker changed while history was inspected")
    _assert_generation_identity(
        parent,
        target.name,
        _entry_identity_tuple(tail["stage_identity"], "stage_identity"),
        tail["new_identity"],
    )
    return cursor


def _write_transaction(
    state: SecureDirectory,
    workspace: SecureDirectory,
    transaction: dict[str, Any],
    phase: str,
) -> dict[str, Any]:
    del state  # The workspace is the immutable journal boundary.
    if phase not in _TRANSACTION_PHASES:
        raise ValueError(f"invalid Skill export transaction phase: {phase}")
    updated = {**transaction, "phase": phase}
    updated["record_sha256"] = _transaction_hash(updated)
    _validate_transaction(updated, str(updated["target_name"]), str(updated["state_id"]))
    if phase == "PREPARED":
        _exclusive_json_at(workspace.descriptor, _TRANSACTION_MARKER, updated)
        _exclusive_json_at(workspace.descriptor, _TRANSACTION_JOURNAL, updated)
    else:
        _exclusive_json_at(workspace.descriptor, _phase_filename(phase), updated)
    workspace.assert_unchanged()
    return updated


def _publish_subdirectory_at(
    parent_fd: int,
    final_name: str,
    files: dict[str, str],
) -> None:
    init_name, init_fd, init_identity = _mkdir_unique_at(
        parent_fd, f".{final_name}-init-"
    )
    try:
        for filename, content in files.items():
            _exclusive_text_at(init_fd, filename, content)
    finally:
        os.close(init_fd)
    current = _identity_from_stat(os.stat(init_name, dir_fd=parent_fd, follow_symlinks=False))
    if current != init_identity:
        raise OSError(f"Skill subdirectory changed before publication: {init_name}")
    _rename_noreplace(
        init_name,
        final_name,
        source_fd=parent_fd,
        target_fd=parent_fd,
    )
    os.fsync(parent_fd)
    published = _identity_from_stat(
        os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
    )
    if published != init_identity:
        raise OSError(f"Skill subdirectory changed during publication: {final_name}")


def _write_staged_skill(stage_fd: int, name: str, payload: dict[str, Any]) -> None:
    skill_text = render_skill_markdown(name)
    agent_text = render_openai_yaml(name)
    payload_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    reference_text = _reference_markdown(payload)
    _exclusive_text_at(stage_fd, "SKILL.md", skill_text)
    _publish_subdirectory_at(stage_fd, "agents", {"openai.yaml": agent_text})
    _publish_subdirectory_at(
        stage_fd,
        "references",
        {"code-index.json": payload_text, "code-index.md": reference_text},
    )
    content = {
        "SKILL.md": skill_text,
        "agents/openai.yaml": agent_text,
        "references/code-index.json": payload_text,
        "references/code-index.md": reference_text,
    }
    hashes = {
        relative: sha256_bytes(content[relative].encode("utf-8")) for relative in REQUIRED_FILES
    }
    _exclusive_json_at(
        stage_fd,
        MARKER_NAME,
        {
            "schema_version": MARKER_SCHEMA_VERSION,
            "generator": GENERATOR_ID,
            "skill_name": name,
            "files": hashes,
            "generation_id": uuid.uuid4().hex,
            "payload_sha256": hashes["references/code-index.json"],
        },
    )
    os.fsync(stage_fd)


def export_skill(
    index: dict[str, Any],
    destination: Path,
    *,
    feature_ids: Iterable[str] | None = None,
    name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    features = _selected_features(index, feature_ids)
    if not features:
        raise ValueError("index contains no features to export")
    _validate_source(index)
    project_name = str(index.get("project", {}).get("name") or "repository")
    normalized_name = _skill_name(project_name, name)
    payload = _reference_payload(index, features)
    lexical_target = Path(os.path.abspath(destination.expanduser()))
    if lexical_target == lexical_target.parent or not lexical_target.name:
        raise OSError(f"refusing unsafe Skill destination: {lexical_target}")

    with SecureDirectory(lexical_target.parent, create=True) as parent:
        target = parent.child_path(lexical_target.name)
        with OutputLock(parent.path):
            parent.assert_unchanged()
            state = _open_private_state(parent, target.name)
            try:
                previous_transaction_id = _inspect_transactions(parent, state, target)
                _reject_tree_symlinks(target)
                target_identity = parent.child_identity(target.name)
                target_exists = target_identity is not None
                target_owned = target_exists and _owned_target(target)
                if target_exists and not target_owned:
                    raise FileExistsError(
                        "refusing to overwrite a directory not generated by Repo Teacher: "
                        f"{target}; --force never deletes or replaces unowned content"
                    )
                if target_exists and not force:
                    raise FileExistsError(
                        f"refusing to replace the existing generated Skill without --force: {target}"
                    )
                previous_identity: dict[str, str] | None = None
                if target_exists:
                    parent.assert_child_identity(target.name, target_identity)
                    previous_identity = _marker_identity(target)
                    parent.assert_child_identity(target.name, target_identity)

                transaction_id = uuid.uuid4().hex
                transaction_dir, transaction_fd, workspace_identity = _mkdir_unique_at(
                    state.descriptor, f"transaction-{transaction_id}-"
                )
                transaction_path = state.child_path(transaction_dir)
                try:
                    workspace = SecureDirectory.from_open_descriptor(
                        transaction_path, transaction_fd, workspace_identity
                    )
                    with workspace:
                        stage_init, stage_fd, stage_entry_identity = _mkdir_unique_at(
                            workspace.descriptor, ".stage-init-"
                        )
                        try:
                            _write_staged_skill(stage_fd, normalized_name, payload)
                        finally:
                            os.close(stage_fd)
                        workspace.replace_to(
                            stage_init,
                            workspace,
                            "stage",
                            expected_source=stage_entry_identity,
                            expected_target=None,
                        )
                        stage = workspace.child_path("stage")
                        workspace.assert_child_identity("stage", stage_entry_identity)
                        staged_validation = validate_exported_skill(stage)
                        workspace.assert_child_identity("stage", stage_entry_identity)
                        new_identity = _marker_identity(stage)
                        workspace.assert_child_identity("stage", stage_entry_identity)
                        _validate_source(index)
                        transaction: dict[str, Any] = {
                            "schema_version": _TRANSACTION_SCHEMA,
                            "generator": GENERATOR_ID,
                            "state_id": str(getattr(state, "state_id", "")),
                            "transaction_id": transaction_id,
                            "transaction_dir": transaction_dir,
                            "target_name": target.name,
                            "phase": "PREPARED",
                            "force_authorized": bool(force),
                            "previous_owned": bool(target_owned),
                            "previous_transaction_id": previous_transaction_id,
                            "workspace_identity": _entry_identity_record(workspace_identity),
                            "stage_identity": _entry_identity_record(stage_entry_identity),
                            "previous_entry_identity": (
                                _entry_identity_record(target_identity)
                                if target_identity is not None
                                else None
                            ),
                            "new_identity": new_identity,
                            "previous_identity": previous_identity,
                        }
                        transaction = _write_transaction(
                            state, workspace, transaction, "PREPARED"
                        )
                        if target_identity is not None:
                            parent.replace_to(
                                target.name,
                                workspace,
                                "backup",
                                expected_source=target_identity,
                                expected_target=None,
                            )
                            _assert_generation_identity(
                                workspace,
                                "backup",
                                target_identity,
                                previous_identity,
                            )
                        transaction = _write_transaction(
                            state, workspace, transaction, "BACKED_UP"
                        )
                        workspace.assert_child_identity("stage", stage_entry_identity)
                        workspace.replace_to(
                            "stage",
                            parent,
                            target.name,
                            expected_source=stage_entry_identity,
                            expected_target=None,
                        )
                        transaction = _write_transaction(
                            state, workspace, transaction, "PUBLISHED"
                        )
                        _assert_generation_identity(
                            parent, target.name, stage_entry_identity, new_identity
                        )
                        final_validation = validate_exported_skill(target)
                        parent.assert_child_identity(target.name, stage_entry_identity)
                        _validate_source(index)
                        transaction = _write_transaction(
                            state, workspace, transaction, "VERIFIED"
                        )
                        _write_transaction(state, workspace, transaction, "COMMITTED")
                        committed_tail = _inspect_transactions(parent, state, target)
                        if committed_tail != transaction_id:
                            raise OSError("committed transaction is not the public history tail")
                        final_validation = validate_exported_skill(target)
                        _assert_generation_identity(
                            parent, target.name, stage_entry_identity, new_identity
                        )
                        committed_tail = _inspect_transactions(parent, state, target)
                        if committed_tail != transaction_id:
                            raise OSError("committed transaction is not the final public history tail")
                except BaseException as error:
                    raise OSError(
                        "Skill export failed; no automatic rollback or cleanup was attempted. "
                        f"Inspect the preserved transaction at {transaction_path}: {error}"
                    ) from error
                parent.assert_unchanged()
            finally:
                state.__exit__(None, None, None)

    return {
        "name": normalized_name,
        "path": str(target),
        "feature_ids": [item.get("id") for item in features],
        "files": len(payload["files"]),
        "evidence": len(payload["evidence"]),
        "validation": final_validation,
        "staged_validation": staged_validation,
    }
