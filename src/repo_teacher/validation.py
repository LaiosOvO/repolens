from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from collections import Counter, OrderedDict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit

from .analyzers import analyze_file
from .artifacts import enrich_index
from .capability_catalog import CAPABILITY_AUDIT_CONTRACTS, REFERENCE_MANIFESTS
from .indexer import (
    INDEX_SCHEMA_VERSION,
    _analysis_fingerprint,
    _build_modules,
    _build_reading_path,
    _derived_artifacts_digest,
    _ensure_unique_relationships,
    _file_analysis_digest,
    _integrity_digest,
    _record,
    build_index,
)
from .models import (
    EvidenceRef,
    FileRecord,
    SymbolRecord,
    redact_persisted_value,
    redact_sensitive_text,
    stable_id,
    to_dict,
)
from .reference_catalog import reference_identity_status
from .scanner import ScanOptions, capture_tree_manifest, scan_repository
from .snapshot import capture_snapshot


_STATIC_FEATURE_SOURCE = "evidence-bounded-static-feature-discovery"
_EXACT_ENTRY_ANALYZERS = {
    "python-ast-call",
    "executable-file-marker",
    "python-ast+executable-marker",
    "go-lexer-fallback[package=main]+executable-marker",
}
_CURATED_FEATURE_SOURCE = re.compile(
    r"^source-audited-reference-manifest:([a-z0-9-]+)@([0-9a-f]{12})$"
)
_GENERATION_ID = re.compile(r"^[0-9a-f]{32}$")
_SYMBOL_KINDS = frozenset(
    {
        "async-function",
        "class",
        "function",
        "interface",
        "interface-method",
        "method",
        "struct",
        "type",
    }
)
_RELATIONSHIP_KINDS = frozenset(
    {"calls", "contains", "import", "receiver-type", "go-import-alias"}
)
_CANONICAL_CACHE_LIMIT = 4
_CANONICAL_CLAIMS_CACHE: OrderedDict[
    tuple[str, str, str], dict[str, str]
] = OrderedDict()


def _claim_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _canonical_claim_digests(index: dict[str, Any]) -> dict[str, str]:
    """Select claims that must be identical to a clean source rebuild."""

    claims = {
        name: index.get(name)
        for name in (
            "files",
            "symbols",
            "relationships",
            "modules",
            "reading_path",
            "features",
            "evidence",
            "tutorials",
            "codemaps",
            "coverage",
            "analyzers",
        )
    }
    stats = index.get("stats") if isinstance(index.get("stats"), dict) else {}
    claims["stats"] = {
        name: stats.get(name)
        for name in (
            "files",
            "symbols",
            "relationships",
            "modules",
            "features",
            "evidence",
            "lines",
            "bytes",
            "languages",
            "confidence",
            "skipped",
            "scan_complete",
            "truncated",
            "tutorials",
            "codemaps",
            "coverage",
            "coverage_average",
            "evidence_completeness_average",
        )
    }
    return {name: _claim_digest(value) for name, value in claims.items()}


def _canonical_source_claims(
    root: Path,
    config: dict[str, Any],
    current_manifest: str,
    analysis_fingerprint: str,
) -> dict[str, str]:
    cache_key = (str(root), current_manifest, analysis_fingerprint)
    cached = _CANONICAL_CLAIMS_CACHE.get(cache_key)
    if cached is not None:
        _CANONICAL_CLAIMS_CACHE.move_to_end(cache_key)
        return cached

    excluded = config.get("excluded_paths", [])
    output_dir = (
        root / Path(*PurePosixPath(excluded[0]).parts)
        if isinstance(excluded, list)
        and len(excluded) == 1
        and isinstance(excluded[0], str)
        else None
    )
    canonical = build_index(
        root,
        output_dir=output_dir,
        max_file_size=config["max_file_size"],
        max_files=config.get("max_files"),
        max_total_bytes=config.get("max_total_bytes"),
        max_entries=config.get("max_entries"),
        deadline_seconds=config.get("deadline_seconds"),
        previous_index=None,
    )
    if canonical.get("freshness") != "complete":
        raise ValueError("canonical source rebuild was incomplete")
    claims = _canonical_claim_digests(canonical)
    _CANONICAL_CLAIMS_CACHE[cache_key] = claims
    _CANONICAL_CLAIMS_CACHE.move_to_end(cache_key)
    while len(_CANONICAL_CLAIMS_CACHE) > _CANONICAL_CACHE_LIMIT:
        _CANONICAL_CLAIMS_CACHE.popitem(last=False)
    return claims


def _issue(
    severity: str, code: str, message: str, *, entity_id: str | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if entity_id:
        result["entity_id"] = entity_id
    return result


def _duplicate_ids(records: Iterable[dict[str, Any]]) -> list[str]:
    counts = Counter(str(item.get("id")) for item in records if item.get("id"))
    return sorted(identifier for identifier, count in counts.items() if count > 1)


def _safe_source_path(root: Path, relative: str) -> Path | None:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        return None
    path = root / Path(*candidate.parts)
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return None
    return path


def _read_source_bounded(path: Path, expected_size: int, limit: int) -> bytes:
    if expected_size < 0 or limit <= 0 or expected_size > limit:
        raise ValueError("indexed source size is outside the configured read boundary")
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise OSError("source is not a regular file")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("source changed to a non-regular file")
        raw = stream.read(expected_size + 1)
        closed = os.fstat(stream.fileno())
    def identity(item: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
    if identity(before) != identity(opened) or identity(opened) != identity(closed):
        raise OSError("source metadata changed while validating")
    if len(raw) != expected_size:
        raise OSError("source size changed while validating")
    return raw


def _feature_evidence_ids(feature: dict[str, Any]) -> list[str]:
    identifiers: list[str] = []
    for key in ("evidence_ids", "test_evidence_ids"):
        values = feature.get(key)
        if isinstance(values, list):
            identifiers.extend(str(value) for value in values if isinstance(value, str))
    steps = feature.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("evidence_ids"), list):
                continue
            identifiers.extend(
                str(value)
                for value in step["evidence_ids"]
                if isinstance(value, str)
            )
    return list(dict.fromkeys(identifiers))


def _confidence_supported(
    feature: dict[str, Any], evidence: list[dict[str, Any]]
) -> bool:
    confidence = feature.get("confidence")
    if confidence == "exact-entry":
        return any(
            item.get("kind") == "entry-declaration"
            and item.get("confidence") == "exact"
            and str(item.get("analyzer")) in _EXACT_ENTRY_ANALYZERS
            for item in evidence
        )
    if confidence == "static-entry":
        return any(item.get("kind") == "entry-declaration" for item in evidence)
    if confidence == "candidate":
        return any(item.get("kind") == "entry-candidate" for item in evidence)
    if confidence == "source-audited":
        return (
            str(feature.get("source", "")).startswith(
                "source-audited-reference-manifest:"
            )
            and any(
                item.get("kind") == "capability-source-audited"
                and str(item.get("analyzer", "")).startswith("reference-manifest@")
                for item in evidence
            )
        )
    return False


def _evidence_identity_matches(item: dict[str, Any]) -> bool:
    try:
        expected = stable_id(
            "evidence",
            str(item["path"]),
            int(item["line_start"]),
            int(item["line_end"]),
            str(item["kind"]),
            str(item["confidence"]),
            str(item["analyzer"]),
            str(item.get("symbol_id") or ""),
            str(item["snippet_sha256"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return str(item.get("id") or "") == expected


def _direct_feature_evidence(
    feature: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    identifiers = feature.get("evidence_ids")
    if not isinstance(identifiers, list) or not all(
        isinstance(identifier, str) for identifier in identifiers
    ):
        return []
    return [
        evidence_by_id[identifier]
        for identifier in identifiers
        if identifier in evidence_by_id
    ]


def _framework_entry_contract(
    feature: dict[str, Any],
    entry: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
) -> tuple[bool, str | None]:
    """Recognize one source-grounded import/factory/call framework claim."""

    claims = feature.get("technology_claims")
    if not isinstance(claims, list):
        return False, None
    framework_claims = [
        item
        for item in claims
        if isinstance(item, dict) and item.get("dimension") == "framework"
    ]
    if len(framework_claims) != 1:
        return False, None
    claim = framework_claims[0]
    identifiers = claim.get("evidence_ids")
    declared = claim.get("value") not in {None, "", "unknown"} or bool(identifiers)
    if not declared:
        return False, None
    if (
        not isinstance(identifiers, list)
        or len(identifiers) != 3
        or len(set(identifiers)) != 3
        or not all(isinstance(identifier, str) for identifier in identifiers)
    ):
        return False, "framework entry must have exactly three distinct provenance stages"

    direct_identifiers = feature.get("evidence_ids")
    if not isinstance(direct_identifiers, list) or not all(
        identifier in direct_identifiers for identifier in identifiers
    ):
        return False, "framework provenance must be direct feature evidence"
    records = [evidence_by_id.get(identifier) for identifier in identifiers]
    if any(record is None for record in records):
        return False, "framework provenance evidence is missing"

    path = entry.get("path")
    line = entry.get("line_start")
    analyzer = str(entry.get("analyzer") or "")
    confidence = entry.get("confidence")
    expected_symbol_id = feature.get("entry_symbol_id")
    for stage, record in zip(("import", "factory", "call"), records, strict=True):
        assert record is not None
        if (
            record.get("kind") != "technology-claim:framework"
            or record.get("path") != path
            or record.get("confidence") != confidence
            or record.get("analyzer") != f"{analyzer}:{stage}"
            or record.get("symbol_id") != expected_symbol_id
            or not _evidence_identity_matches(record)
        ):
            return False, f"framework {stage} provenance does not close"
    call = records[-1]
    assert call is not None
    if (
        call.get("line_start") != line
        or call.get("line_end") != line
        or call.get("snippet_sha256") != entry.get("snippet_sha256")
    ):
        return False, "framework call provenance does not match the entry line"
    if (
        claim.get("source_path") != path
        or claim.get("confidence") != confidence
        or not isinstance(claim.get("claim_scope"), str)
        or not claim["claim_scope"].startswith("仅声明调用点 receiver 由 module `")
        or not claim["claim_scope"].endswith("；不外推部署或运行时行为。")
    ):
        return False, "framework technology claim is broader than its provenance"
    tags = feature.get("technology_tags")
    if not isinstance(tags, list) or tags.count(f"framework:{claim.get('value')}") != 1:
        return False, "framework technology tag does not match its claim"
    return True, None


def _static_feature_claim_mismatch(
    feature: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    symbols_by_id: dict[str, dict[str, Any]],
    files_by_path: dict[str, dict[str, Any]],
) -> str | None:
    kind = str(feature.get("kind") or "")
    if kind not in {"cli-command", "http-route", "entrypoint", "entrypoint-candidate"}:
        return f"unknown static feature kind: {kind!r}"

    direct = _direct_feature_evidence(feature, evidence_by_id)
    expected_evidence_kind = (
        "entry-candidate" if kind == "entrypoint-candidate" else "entry-declaration"
    )
    entries = [item for item in direct if item.get("kind") == expected_evidence_kind]
    if len(entries) != 1:
        return "feature must reference exactly one matching entry evidence record"
    entry = entries[0]
    identifiers = feature.get("evidence_ids")
    if not identifiers or identifiers[0] != entry.get("id"):
        return "entry evidence must be the feature's first direct evidence"
    if not _evidence_identity_matches(entry):
        return "entry evidence identity does not match its grounded fields"
    if entry.get("symbol_id") is not None:
        return "static entry evidence must not impersonate a symbol definition"

    path = str(entry.get("path") or "")
    line = entry.get("line_start")
    file = files_by_path.get(path)
    if file is None or not isinstance(line, int):
        return "entry evidence path or line is invalid"
    framework_entry, framework_mismatch = _framework_entry_contract(
        feature, entry, evidence_by_id
    )
    if framework_mismatch is not None:
        return framework_mismatch
    expected_line_end = (
        line if framework_entry else min(int(file.get("lines") or 0), line + 5)
    )
    if entry.get("line_end") != expected_line_end:
        return "entry evidence range does not match the static feature contract"

    analyzer = str(entry.get("analyzer") or "")
    evidence_confidence = str(entry.get("confidence") or "")
    if kind == "entrypoint-candidate":
        expected_confidence = "candidate"
    elif evidence_confidence == "exact" and analyzer in _EXACT_ENTRY_ANALYZERS:
        expected_confidence = "exact-entry"
    else:
        if evidence_confidence == "exact" or analyzer in _EXACT_ENTRY_ANALYZERS:
            return "entry evidence analyzer and confidence disagree"
        expected_confidence = "static-entry"
    if feature.get("confidence") != expected_confidence:
        return "feature confidence does not match its entry evidence"

    entrypoint = str(feature.get("entrypoint") or "")
    expected_id = stable_id("feature", kind, entrypoint, path, line)
    if feature.get("id") != expected_id:
        return "feature ID does not match kind, entrypoint, path, and line"

    steps = feature.get("steps")
    if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
        return "feature steps are malformed"
    first = steps[0] if steps else None
    entry_symbol_id = feature.get("entry_symbol_id")
    if framework_entry and entry_symbol_id is None:
        expected_fallback = {
            "order": 1,
            "title": f"保守确认调用点：{feature.get('entrypoint')}",
            "explanation": (
                "该切片只证明框架实例在同一可证明作用域内被直接调用；"
                "不证明部署可达性、动态分派或真实运行顺序。"
            ),
            "path": path,
            "line_start": line,
            "line_end": line,
            "evidence_ids": [entry.get("id")],
            "symbol_id": None,
            "relationship_id": None,
        }
        if first is None or len(steps) != 1 or any(
            first.get(field) != expected
            for field, expected in expected_fallback.items()
        ):
            return "framework callsite fallback does not close to its exact entry evidence"
    elif first is None:
        if entry_symbol_id is not None:
            return "entry symbol is present without an entry step"
    else:
        first_symbol_id = first.get("symbol_id")
        symbol = symbols_by_id.get(str(first_symbol_id or ""))
        if (
            not first_symbol_id
            or entry_symbol_id != first_symbol_id
            or symbol is None
            or first.get("path") != path
            or symbol.get("path") != path
            or first.get("order") != 1
        ):
            return "entry symbol, first step, and entry evidence do not close"

    if kind == "cli-command":
        expected_title = f"CLI 命令：{entrypoint}"
    elif kind == "http-route":
        expected_title = f"HTTP 接口：{entrypoint}"
    elif kind == "entrypoint-candidate":
        if first is None:
            return "entrypoint candidate has no symbol step"
        symbol = symbols_by_id[str(first["symbol_id"])]
        if symbol.get("qualified_name") != entrypoint:
            return "candidate entrypoint does not match its entry symbol"
        expected_title = f"入口候选：{path} · {symbol.get('qualified_name')}"
    elif entry_symbol_id is not None:
        symbol = symbols_by_id.get(str(entry_symbol_id))
        if symbol is None or symbol.get("qualified_name") != entrypoint:
            return "entrypoint does not match its entry symbol"
        expected_title = f"程序入口：{path} · {symbol.get('qualified_name')}"
    else:
        if entrypoint != path:
            return "file entrypoint must name its evidence path"
        expected_title = f"程序入口文件：{path}"
    if feature.get("title") != expected_title:
        return "feature title does not match its static claim"

    resolved_calls = sum(1 for step in steps if step.get("relationship_id"))
    static_path_summary = (
        f"并找到 {resolved_calls} 条已解析静态调用边"
        if resolved_calls
        else "；下游调用尚未解析"
    )
    boundary_summary = (
        f"在 `{path}:{line}` 精确解析到同名符号，但没有确认它是运行入口"
        if kind == "entrypoint-candidate"
        else (
            f"在 `{path}:{line}` 找到满足保守同作用域合同的静态框架调用声明；实际可达性未知"
            if framework_entry
            else f"在 `{path}:{line}` 找到已确认的静态入口声明；实际可达性未知"
        )
    )
    expected_summary = (
        f"{boundary_summary}，关联 {len(steps)} 个源码符号{static_path_summary}。"
        "这些是静态阅读证据，不是运行时执行顺序。"
    )
    if feature.get("summary") != expected_summary:
        return "feature summary does not match its grounded static path"
    return None


def _normalize_remote(value: object) -> str:
    remote = str(value or "").strip()
    if not remote:
        return ""
    if remote.startswith("git@") and ":" in remote:
        host, repository = remote[4:].split(":", 1)
        normalized = f"{host}/{repository}"
    else:
        parsed = urlsplit(remote)
        if not parsed.hostname or parsed.query or parsed.fragment:
            return ""
        normalized = f"{parsed.hostname}{parsed.path}"
    return normalized.lower().rstrip("/").removesuffix(".git")


def _curated_feature_claim_mismatch(
    feature: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    project: dict[str, Any],
    root: Path,
    identity: dict[str, Any],
) -> str | None:
    source_match = _CURATED_FEATURE_SOURCE.fullmatch(str(feature.get("source") or ""))
    if source_match is None:
        return "curated feature source is malformed"
    project_key, commit_prefix = source_match.groups()
    manifest = next(
        (
            item
            for item in REFERENCE_MANIFESTS
            if item.project == project_key and item.commit.startswith(commit_prefix)
        ),
        None,
    )
    if manifest is None:
        return "curated feature source is not a known pinned manifest"
    try:
        indexed_git_root = Path(str(project.get("git_root") or "")).resolve()
    except (OSError, ValueError):
        return "curated project Git root is invalid"
    if (
        project.get("is_git") is not True
        or indexed_git_root != root
        or str(project.get("commit") or "").lower() != manifest.commit
        or _normalize_remote(project.get("remote")) != manifest.canonical_remote
        or identity.get("status") != "verified"
        or identity.get("project_key") != manifest.project
    ):
        return "curated feature project identity is not the pinned source worktree"

    matches = [
        spec
        for spec in manifest.capabilities
        if feature.get("id")
        == stable_id("capability", manifest.project, spec.slug, spec.path)
    ]
    if len(matches) != 1:
        return "curated feature ID is not present in its manifest"
    spec = matches[0]
    expected_source = (
        f"source-audited-reference-manifest:{manifest.project}@{manifest.commit[:12]}"
    )
    if (
        feature.get("kind") != "capability-cluster"
        or feature.get("confidence") != "source-audited"
        or feature.get("source") != expected_source
        or feature.get("entrypoint") != spec.path
        or feature.get("title") != spec.title
        or feature.get("summary") != spec.summary
    ):
        return "curated feature metadata does not match its manifest"

    contract = CAPABILITY_AUDIT_CONTRACTS[(manifest.project, spec.slug)]
    entry_contract = contract.slices[0]
    direct = _direct_feature_evidence(feature, evidence_by_id)
    entries = [item for item in direct if item.get("kind") == "capability-source-audited"]
    if len(entries) != 1:
        return "curated feature must reference exactly one entry audit slice"
    entry = entries[0]
    identifiers = feature.get("evidence_ids")
    expected_analyzer = (
        f"reference-manifest@{manifest.project}@{manifest.commit[:12]}:role:1"
    )
    if (
        not identifiers
        or identifiers[0] != entry.get("id")
        or not _evidence_identity_matches(entry)
        or entry.get("path") != entry_contract.path
        or entry.get("line_start") != entry_contract.line_start
        or entry.get("line_end") != entry_contract.line_end
        or entry.get("confidence") != "exact"
        or entry.get("analyzer") != expected_analyzer
    ):
        return "curated entry evidence does not match its audited slice"

    steps = feature.get("steps")
    if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
        return "curated feature has no entry step"
    first = steps[0]
    if (
        first.get("order") != 1
        or first.get("path") != entry_contract.path
        or first.get("line_start") != entry_contract.line_start
        or first.get("line_end") != entry_contract.line_end
        or first.get("evidence_ids") != [entry.get("id")]
        or first.get("symbol_id") != entry.get("symbol_id")
        or feature.get("entry_symbol_id") != first.get("symbol_id")
    ):
        return "curated entry symbol, step, and evidence do not close"
    return None


def _feature_claim_mismatch(
    feature: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    symbols_by_id: dict[str, dict[str, Any]],
    files_by_path: dict[str, dict[str, Any]],
    project: dict[str, Any],
    root: Path,
    curated_identity: dict[str, Any] | None,
) -> str | None:
    source = feature.get("source")
    if source == _STATIC_FEATURE_SOURCE:
        return _static_feature_claim_mismatch(
            feature, evidence_by_id, symbols_by_id, files_by_path
        )
    if isinstance(source, str) and source.startswith(
        "source-audited-reference-manifest:"
    ):
        return _curated_feature_claim_mismatch(
            feature,
            evidence_by_id,
            project,
            root,
            curated_identity or {},
        )
    return f"unknown feature source: {source!r}"


def _normalized_local_analysis(
    symbols: list[dict[str, Any]] | list[Any],
    relationships: list[dict[str, Any]] | list[Any],
) -> str:
    """Hash claims owned by a file analyzer before project-wide resolution."""

    def value(item: object) -> dict[str, Any]:
        return item if isinstance(item, dict) else to_dict(item)

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
    payload = {
        "symbols": sorted(
            [
                {field: value(item).get(field) for field in symbol_fields}
                for item in symbols
            ],
            key=lambda item: str(item["id"]),
        ),
        # target_id is attached by project-wide resolution, so it is not an
        # analyzer-local source claim and is intentionally excluded here.
        "relationships": sorted(
            [
                {field: value(item).get(field) for field in relationship_fields}
                for item in relationships
            ],
            key=lambda item: json.dumps(item, sort_keys=True),
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_index(index: dict[str, Any], source: Path | None = None) -> dict[str, Any]:
    """Validate a complete index as a grounded local generation.

    The embedded SHA-256 is an accidental-corruption checksum, not a signature.
    This validator therefore also checks the current source tree, stable entity
    identities, graph closure, evidence hashes, and feature confidence policy.
    It does not authenticate an index supplied by an adversarial writer.
    """

    issues: list[dict[str, Any]] = []
    project = index.get("project") if isinstance(index.get("project"), dict) else {}
    root = (source or Path(str(project.get("path") or "."))).expanduser().resolve()
    if not root.is_dir():
        return {
            "valid": False,
            "source": str(root),
            "errors": 1,
            "warnings": 0,
            "issues": [
                _issue(
                    "error",
                    "source-missing",
                    f"repository source is unavailable: {root}",
                )
            ],
        }

    if index.get("schema_version") != INDEX_SCHEMA_VERSION:
        issues.append(
            _issue(
                "error",
                "schema-mismatch",
                f"expected schema {INDEX_SCHEMA_VERSION}, got {index.get('schema_version')!r}",
            )
        )
    generation_id = index.get("generation_id")
    if generation_id is not None and (
        not isinstance(generation_id, str)
        or _GENERATION_ID.fullmatch(generation_id) is None
    ):
        issues.append(
            _issue("error", "generation-id-invalid", "generation ID is malformed")
        )
    if project.get("path") != str(root):
        issues.append(
            _issue(
                "error",
                "project-path-mismatch",
                "index project path does not match the validation source",
            )
        )

    config = index.get("analysis_config")
    scan_options: ScanOptions | None = None
    current_manifest: str | None = None
    if not isinstance(config, dict):
        issues.append(_issue("error", "analysis-config-missing", "analysis configuration is missing"))
    else:
        try:
            expected_fingerprint = _analysis_fingerprint(
                config["max_file_size"],
                config.get("max_files"),
                config.get("max_total_bytes"),
                config.get("max_entries"),
                config.get("deadline_seconds"),
            )
            if not hmac.compare_digest(
                str(index.get("analysis_fingerprint") or ""), expected_fingerprint
            ):
                issues.append(
                    _issue(
                        "error",
                        "analysis-fingerprint-mismatch",
                        "analysis implementation or configuration fingerprint does not match",
                    )
                )
            excluded_paths: list[Path] = []
            for value in config.get("excluded_paths", []):
                if not isinstance(value, str) or _safe_source_path(root, value) is None:
                    raise ValueError(f"unsafe excluded path: {value!r}")
                excluded_paths.append(root / Path(*PurePosixPath(value).parts))
            scan_options = ScanOptions(
                max_file_size=config["max_file_size"],
                max_files=config.get("max_files"),
                max_total_bytes=config.get("max_total_bytes"),
                max_entries=config.get("max_entries"),
                deadline_seconds=config.get("deadline_seconds"),
                excluded_paths=tuple(excluded_paths),
            )
        except (KeyError, TypeError, ValueError) as error:
            issues.append(
                _issue(
                    "error",
                    "analysis-config-invalid",
                    f"analysis configuration is invalid: {error}",
                )
            )

    stats = index.get("stats") if isinstance(index.get("stats"), dict) else {}
    if stats.get("scan_complete") is not True or stats.get("truncated") is True:
        issues.append(
            _issue(
                "error",
                "partial-index",
                "partial or truncated indexes cannot be validated or reused as a baseline",
            )
        )
    if index.get("freshness") != "complete":
        issues.append(
            _issue("error", "freshness-not-complete", "index freshness is not complete")
        )
    if index.get("integrity_boundary") != (
        "sha256-checksum-only; controlled-local-generation; not-authenticated"
    ):
        issues.append(
            _issue(
                "error",
                "integrity-boundary-missing",
                "checksum trust boundary is missing or unknown",
            )
        )
    expected_integrity = index.get("integrity_sha256")
    try:
        actual_integrity = _integrity_digest(index)
    except (TypeError, ValueError) as error:
        actual_integrity = ""
        issues.append(
            _issue("error", "integrity-unreadable", f"cannot hash index payload: {error}")
        )
    if not isinstance(expected_integrity, str) or not hmac.compare_digest(
        expected_integrity, actual_integrity
    ):
        issues.append(
            _issue("error", "integrity-mismatch", "index checksum does not match its payload")
        )

    collection_names = (
        "files",
        "symbols",
        "relationships",
        "features",
        "evidence",
        "tutorials",
        "codemaps",
    )
    collections: dict[str, list[dict[str, Any]]] = {}
    for name in collection_names:
        raw = index.get(name)
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            issues.append(
                _issue("error", "malformed-collection", f"{name} collection is malformed")
            )
            collections[name] = []
        else:
            collections[name] = raw
        for identifier in _duplicate_ids(collections[name]):
            issues.append(
                _issue(
                    "error",
                    "duplicate-id",
                    f"duplicate {name} id: {identifier}",
                    entity_id=identifier,
                )
            )

    files_by_id = {
        str(item.get("id")): item for item in collections["files"] if item.get("id")
    }
    files_by_path = {
        str(item.get("path")): item
        for item in collections["files"]
        if item.get("path")
    }
    symbols_by_id = {
        str(item.get("id")): item
        for item in collections["symbols"]
        if item.get("id")
    }
    relationships_by_id = {
        str(item.get("id")): item
        for item in collections["relationships"]
        if item.get("id")
    }
    evidence_by_id = {
        str(item.get("id")): item
        for item in collections["evidence"]
        if item.get("id")
    }
    contents: dict[str, str] = {}

    for file in collections["files"]:
        path = str(file.get("path") or "")
        identifier = str(file.get("id") or "")
        if identifier != stable_id("file", path):
            issues.append(
                _issue("error", "unstable-file-id", f"file ID is not stable: {path}", entity_id=identifier)
            )
        source_path = _safe_source_path(root, path)
        if source_path is None:
            issues.append(
                _issue("error", "unsafe-path", f"unsafe indexed path: {path}", entity_id=identifier)
            )
            continue
        try:
            expected_size = int(file.get("size"))
            read_limit = (
                scan_options.max_file_size
                if scan_options is not None
                else max(1, expected_size)
            )
            raw = _read_source_bounded(source_path, expected_size, read_limit)
            contents[path] = raw.decode("utf-8")
        except (OSError, TypeError, ValueError, UnicodeDecodeError) as error:
            issues.append(_issue("error", "source-read-failed", f"cannot verify {path}: {error}"))
            continue
        if hashlib.sha256(raw).hexdigest() != file.get("sha256"):
            issues.append(_issue("error", "stale-file", f"source changed after indexing: {path}"))

    if scan_options is not None:
        try:
            current_scan = scan_repository(root, scan_options)
            current_manifest = capture_tree_manifest(root, scan_options)
        except (OSError, ValueError) as error:
            issues.append(
                _issue(
                    "error",
                    "validation-scan-partial",
                    f"validation source scan could not complete: {error}",
                )
            )
        else:
            indexed_manifest = index.get("source_manifest_sha256")
            if not isinstance(indexed_manifest, str) or not hmac.compare_digest(
                indexed_manifest, current_manifest
            ):
                issues.append(
                    _issue(
                        "error",
                        "tree-manifest-drift",
                        "repository tree changed after indexing",
                    )
                )
            current_hashes = {item.path: item.sha256 for item in current_scan.files}
            indexed_hashes = {
                path: str(item.get("sha256"))
                for path, item in files_by_path.items()
            }
            for path in sorted(current_hashes.keys() - indexed_hashes.keys()):
                issues.append(
                    _issue(
                        "error",
                        "unindexed-source-file",
                        f"source file was not indexed: {path}",
                    )
                )
            for path in sorted(indexed_hashes.keys() - current_hashes.keys()):
                issues.append(
                    _issue(
                        "error",
                        "indexed-source-deleted",
                        f"indexed source file disappeared: {path}",
                    )
                )
            if current_scan.truncated or any(
                item.severity == "error" for item in current_scan.diagnostics
            ):
                issues.append(
                    _issue(
                        "error",
                        "validation-scan-partial",
                        "validation source scan was incomplete",
                    )
                )

    actual_symbols_by_file: dict[str, set[str]] = {}
    for symbol in collections["symbols"]:
        identifier = str(symbol.get("id") or "")
        file_id = str(symbol.get("file_id") or "")
        path = str(symbol.get("path") or "")
        file = files_by_id.get(file_id)
        if file is None or file.get("path") != path:
            issues.append(
                _issue("error", "dangling-file-ref", f"symbol file/path closure failed: {file_id}", entity_id=identifier)
            )
            continue
        analyzer = str(symbol.get("analyzer") or "")
        if re.fullmatch(r"symbol_[0-9a-f]{16}", identifier) is None:
            issues.append(
                _issue(
                    "error",
                    "malformed-symbol-id",
                    "symbol ID is not in the stable identifier namespace",
                    entity_id=identifier,
                )
            )
        if not (
            analyzer in {"python-ast", "javascript-regex"}
            or analyzer.startswith("go-")
        ):
            issues.append(
                _issue(
                    "error",
                    "unsupported-symbol-analyzer",
                    f"unsupported symbol analyzer: {analyzer!r}",
                    entity_id=identifier,
                )
            )
        if symbol.get("kind") not in _SYMBOL_KINDS:
            issues.append(
                _issue(
                    "error",
                    "unsupported-symbol-kind",
                    f"unsupported symbol kind: {symbol.get('kind')!r}",
                    entity_id=identifier,
                )
            )
        line = symbol.get("line")
        expected_symbol_id: str | None = None
        if analyzer in {"python-ast", "javascript-regex"} and isinstance(line, int):
            expected_symbol_id = stable_id(
                "symbol",
                path,
                symbol.get("kind"),
                symbol.get("qualified_name"),
                line,
            )
        elif analyzer.startswith("go-"):
            package_match = re.search(r"\[package=([^\]]+)\]$", analyzer)
            package = package_match.group(1) if package_match else "unknown"
            expected_symbol_id = stable_id(
                "symbol",
                path,
                package,
                symbol.get("qualified_name"),
                symbol.get("kind"),
                " ".join(str(symbol.get("signature") or "").split()),
            )
        if expected_symbol_id is not None and identifier != expected_symbol_id:
            issues.append(
                _issue(
                    "error",
                    "unstable-symbol-id",
                    "symbol ID does not match its analyzer identity contract",
                    entity_id=identifier,
                )
            )
        actual_symbols_by_file.setdefault(file_id, set()).add(identifier)
        end_line = symbol.get("end_line")
        if (
            not isinstance(line, int)
            or not isinstance(end_line, int)
            or line < 1
            or end_line < line
            or end_line > int(file.get("lines") or 0)
        ):
            issues.append(_issue("error", "invalid-symbol-range", "symbol source range is invalid", entity_id=identifier))
        elif (
            path in contents
            and isinstance(symbol.get("name"), str)
            and symbol.get("confidence") in {"exact", "syntax-exact"}
        ):
            source_lines = contents[path].splitlines()
            source_slice = "\n".join(source_lines[line - 1 : end_line])
            if str(symbol["name"]) not in source_slice:
                issues.append(
                    _issue(
                        "error",
                        "ungrounded-symbol",
                        "symbol name is absent from its claimed source range",
                        entity_id=identifier,
                    )
                )
        parent_id = symbol.get("parent_id")
        if parent_id:
            parent = symbols_by_id.get(str(parent_id))
            if parent is None or parent.get("path") != path:
                issues.append(_issue("error", "dangling-parent-ref", "symbol parent is missing or cross-file", entity_id=identifier))

    for file_id, file in files_by_id.items():
        membership = file.get("symbols")
        expected = actual_symbols_by_file.get(file_id, set())
        if not isinstance(membership, list) or set(membership) != expected:
            issues.append(_issue("error", "symbol-membership-mismatch", f"file symbol membership is not closed: {file.get('path')}", entity_id=file_id))

    for relationship in collections["relationships"]:
        identifier = str(relationship.get("id") or "")
        source_id = str(relationship.get("source_id") or "")
        kind = relationship.get("kind")
        analyzer = str(relationship.get("analyzer") or "")
        if re.fullmatch(r"rel_[0-9a-f]{16}", identifier) is None:
            issues.append(
                _issue(
                    "error",
                    "malformed-relationship-id",
                    "relationship ID is not in the stable identifier namespace",
                    entity_id=identifier,
                )
            )
        if kind not in _RELATIONSHIP_KINDS:
            issues.append(
                _issue(
                    "error",
                    "unsupported-relationship-kind",
                    f"unsupported relationship kind: {kind!r}",
                    entity_id=identifier,
                )
            )
        if not (
            analyzer in {"python-ast", "javascript-regex"}
            or analyzer.startswith("go-")
        ):
            issues.append(
                _issue(
                    "error",
                    "unsupported-relationship-analyzer",
                    f"unsupported relationship analyzer: {analyzer!r}",
                    entity_id=identifier,
                )
            )
        source_record = symbols_by_id.get(source_id) or files_by_id.get(source_id)
        if source_record is None:
            issues.append(_issue("error", "dangling-source-ref", f"relationship source does not exist: {source_id}", entity_id=identifier))
        elif source_record.get("path") != relationship.get("path"):
            issues.append(_issue("error", "relationship-path-mismatch", "relationship path disagrees with its source", entity_id=identifier))
        target_id = relationship.get("target_id")
        if target_id and str(target_id) not in symbols_by_id and str(target_id) not in files_by_id:
            issues.append(_issue("error", "dangling-target-ref", f"relationship target does not exist: {target_id}", entity_id=identifier))
        if not isinstance(relationship.get("target_name"), str) or not relationship.get("target_name"):
            issues.append(_issue("error", "missing-relationship-target", "relationship target name is missing", entity_id=identifier))
        path_file = files_by_path.get(str(relationship.get("path") or ""))
        line = relationship.get("line")
        if path_file is None or not isinstance(line, int) or line < 1 or line > int(path_file.get("lines") or 0):
            issues.append(_issue("error", "invalid-relationship-range", "relationship source line is invalid", entity_id=identifier))

        if analyzer in {"python-ast", "javascript-regex"} and isinstance(line, int):
            identity_target = (
                target_id
                if kind == "contains" and target_id
                else (
                    f"{relationship.get('target_name')}\x1f{relationship.get('receiver_type_hint')}"
                    if analyzer == "python-ast"
                    and kind == "import"
                    and relationship.get("receiver_type_hint")
                    else relationship.get("target_name")
                )
            )
            expected_relationship_id = stable_id(
                "rel",
                kind,
                source_id,
                identity_target,
                relationship.get("path"),
                line,
            )
            if identifier != expected_relationship_id:
                issues.append(
                    _issue(
                        "error",
                        "unstable-relationship-id",
                        "relationship ID does not match its analyzer identity contract",
                        entity_id=identifier,
                    )
                )
        target_record = (
            symbols_by_id.get(str(target_id)) or files_by_id.get(str(target_id))
            if target_id
            else None
        )
        if kind in {"calls", "contains", "receiver-type"} and target_id:
            if str(target_id) not in symbols_by_id:
                issues.append(
                    _issue(
                        "error",
                        "relationship-target-kind-mismatch",
                        f"{kind} relationship must target a symbol",
                        entity_id=identifier,
                    )
                )
        if (
            kind == "import"
            and target_record is not None
            and str(target_id) not in files_by_id
        ):
            issues.append(
                _issue(
                    "error",
                    "relationship-target-kind-mismatch",
                    "import relationship must target a file when resolved",
                    entity_id=identifier,
                )
            )
        if kind == "go-import-alias":
            target_name = relationship.get("target_name")
            if (
                not analyzer.startswith("go-")
                or source_id not in files_by_id
                or target_id is not None
                or relationship.get("confidence") != "syntax-exact"
                or not isinstance(target_name, str)
                or re.fullmatch(r"[^=\s]+=.+", target_name) is None
            ):
                issues.append(
                    _issue(
                        "error",
                        "invalid-go-import-alias",
                        "Go import-alias edges must be exact unresolved file-to-alias claims",
                        entity_id=identifier,
                    )
                )

    semantic_mismatch = False
    symbols_by_path: dict[str, list[dict[str, Any]]] = {}
    relationships_by_path: dict[str, list[dict[str, Any]]] = {}
    for symbol in collections["symbols"]:
        symbols_by_path.setdefault(str(symbol.get("path") or ""), []).append(symbol)
    for relationship in collections["relationships"]:
        relationships_by_path.setdefault(
            str(relationship.get("path") or ""), []
        ).append(relationship)
    for file in collections["files"]:
        path = str(file.get("path") or "")
        expected = file.get("analysis_sha256")
        actual = _file_analysis_digest(
            path,
            symbols_by_path.get(path, []),
            relationships_by_path.get(path, []),
        )
        if not isinstance(expected, str) or not hmac.compare_digest(expected, actual):
            semantic_mismatch = True
        if file.get("language") == "Python" and path in contents:
            try:
                local_file = _record(FileRecord, file)
                analyzed = analyze_file(local_file, contents[path])
                normalized_relationships, _, _ = _ensure_unique_relationships(
                    analyzed.relationships
                )
                if _normalized_local_analysis(
                    symbols_by_path.get(path, []),
                    relationships_by_path.get(path, []),
                ) != _normalized_local_analysis(
                    redact_persisted_value(to_dict(analyzed.symbols)),
                    redact_persisted_value(to_dict(normalized_relationships)),
                ):
                    semantic_mismatch = True
            except (TypeError, ValueError):
                semantic_mismatch = True
    if semantic_mismatch:
        issues.append(
            _issue(
                "error",
                "analysis-semantics-mismatch",
                "persisted analyzer claims do not close against their file digest or source analyzer",
            )
        )

    derived_mismatch = False
    expected_derived_digest = index.get("derived_sha256")
    if (
        not isinstance(expected_derived_digest, str)
        or not hmac.compare_digest(
            expected_derived_digest, _derived_artifacts_digest(index)
        )
    ):
        derived_mismatch = True
    try:
        generated = enrich_index(index)
        for name in ("tutorials", "codemaps", "coverage"):
            if generated.get(name) != index.get(name):
                derived_mismatch = True
        file_records = [_record(FileRecord, item) for item in collections["files"]]
        symbol_records = [
            _record(SymbolRecord, item) for item in collections["symbols"]
        ]
        modules = _build_modules(file_records, symbol_records)
        if to_dict(modules) != index.get("modules"):
            derived_mismatch = True
        if to_dict(
            _build_reading_path(file_records, symbol_records, modules)
        ) != index.get("reading_path"):
            derived_mismatch = True
    except (KeyError, TypeError, ValueError):
        derived_mismatch = True
    expected_stats = {
        "files": len(collections["files"]),
        "symbols": len(collections["symbols"]),
        "relationships": len(collections["relationships"]),
        "modules": (
            len(index.get("modules", []))
            if isinstance(index.get("modules"), list)
            else -1
        ),
        "features": len(collections["features"]),
        "evidence": len(collections["evidence"]),
        "lines": sum(int(item.get("lines") or 0) for item in collections["files"]),
        "bytes": sum(int(item.get("size") or 0) for item in collections["files"]),
        "diagnostics": (
            len(index.get("diagnostics", []))
            if isinstance(index.get("diagnostics"), list)
            else -1
        ),
        "tutorials": len(collections["tutorials"]),
        "codemaps": len(collections["codemaps"]),
        "coverage": (
            len(index.get("coverage", []))
            if isinstance(index.get("coverage"), list)
            else -1
        ),
    }
    if any(stats.get(name) != value for name, value in expected_stats.items()):
        derived_mismatch = True
    if derived_mismatch:
        issues.append(
            _issue(
                "error",
                "derived-artifacts-mismatch",
                "modules, reading path, teaching artifacts, coverage, or stats are not deterministic and closed",
            )
        )

    valid_evidence_ids: set[str] = set()
    for item in collections["evidence"]:
        try:
            evidence = EvidenceRef(**item)
        except (TypeError, ValueError) as error:
            issues.append(_issue("error", "invalid-evidence", f"malformed evidence: {error}", entity_id=item.get("id")))
            continue
        source_content = contents.get(evidence.path)
        source_lines = source_content.splitlines() if source_content is not None else []
        if (
            evidence.line_start >= 1
            and evidence.line_end >= evidence.line_start
            and evidence.line_end <= len(source_lines)
        ):
            source_snippet = "\n".join(
                source_lines[evidence.line_start - 1 : evidence.line_end]
            )
            evidence_matches = (
                redact_sensitive_text(source_snippet) == evidence.snippet
                and hashlib.sha256(source_snippet.encode("utf-8")).hexdigest()
                == evidence.snippet_sha256
            )
        else:
            evidence_matches = False
        if evidence_matches:
            valid_evidence_ids.add(evidence.id)
        else:
            issues.append(_issue("error", "stale-evidence", f"evidence no longer matches source: {evidence.path}:{evidence.line_start}-{evidence.line_end}", entity_id=evidence.id))
        if evidence.symbol_id and evidence.symbol_id not in symbols_by_id:
            issues.append(
                _issue(
                    "error",
                    "dangling-evidence-symbol",
                    f"evidence symbol does not exist: {evidence.symbol_id}",
                    entity_id=evidence.id,
                )
            )

    has_curated_features = any(
        str(feature.get("source") or "").startswith(
            "source-audited-reference-manifest:"
        )
        for feature in collections["features"]
    )
    curated_identity = reference_identity_status(index) if has_curated_features else None

    for feature in collections["features"]:
        feature_id = str(feature.get("id") or "")
        referenced_evidence = _feature_evidence_ids(feature)
        if not referenced_evidence:
            issues.append(_issue("error", "feature-without-evidence", "feature has no source evidence", entity_id=feature_id))
        for identifier in referenced_evidence:
            if identifier not in valid_evidence_ids:
                issues.append(_issue("error", "dangling-evidence-ref", f"feature evidence is absent or invalid: {identifier}", entity_id=feature_id))
        supporting = [evidence_by_id[item] for item in referenced_evidence if item in valid_evidence_ids]
        if not _confidence_supported(feature, supporting):
            issues.append(_issue("error", "unsupported-feature-confidence", f"feature confidence is not supported by its evidence: {feature.get('confidence')!r}", entity_id=feature_id))
        claim_mismatch = _feature_claim_mismatch(
            feature,
            evidence_by_id,
            symbols_by_id,
            files_by_path,
            project,
            root,
            curated_identity,
        )
        if claim_mismatch is not None:
            issues.append(
                _issue(
                    "error",
                    "feature-claim-mismatch",
                    claim_mismatch,
                    entity_id=feature_id,
                )
            )
        steps = feature.get("steps") if isinstance(feature.get("steps"), list) else []
        entry_symbol_id = feature.get("entry_symbol_id")
        if entry_symbol_id and str(entry_symbol_id) not in symbols_by_id:
            issues.append(
                _issue(
                    "error",
                    "dangling-entry-symbol-ref",
                    f"feature entry symbol does not exist: {entry_symbol_id}",
                    entity_id=feature_id,
                )
            )
        for step in steps:
            if not isinstance(step, dict):
                issues.append(_issue("error", "malformed-feature-step", "feature step is malformed", entity_id=feature_id))
                continue
            symbol_id = step.get("symbol_id")
            relationship_id = step.get("relationship_id")
            if symbol_id and str(symbol_id) not in symbols_by_id:
                issues.append(_issue("error", "dangling-symbol-ref", f"feature symbol does not exist: {symbol_id}", entity_id=feature_id))
            if relationship_id and str(relationship_id) not in relationships_by_id:
                issues.append(_issue("error", "dangling-relationship-ref", f"feature relationship does not exist: {relationship_id}", entity_id=feature_id))

    if (
        isinstance(config, dict)
        and scan_options is not None
        and current_manifest is not None
    ):
        try:
            expected_claims = _canonical_source_claims(
                root,
                config,
                current_manifest,
                str(index.get("analysis_fingerprint") or ""),
            )
            observed_claims = _canonical_claim_digests(index)
        except (KeyError, OSError, TypeError, ValueError) as error:
            issues.append(
                _issue(
                    "error",
                    "canonical-source-rebuild-failed",
                    f"could not re-prove source claims: {error}",
                )
            )
        else:
            mismatched = sorted(
                name
                for name, expected in expected_claims.items()
                if observed_claims.get(name) != expected
            )
            if mismatched:
                issues.append(
                    _issue(
                        "error",
                        "canonical-source-claims-mismatch",
                        "persisted claims differ from a clean source rebuild: "
                        + ", ".join(mismatched),
                    )
                )

    current_snapshot = capture_snapshot(root)
    indexed_commit = project.get("commit")
    if indexed_commit and current_snapshot.commit and indexed_commit != current_snapshot.commit:
        issues.append(_issue("error", "commit-drift", f"repository moved from {indexed_commit} to {current_snapshot.commit}"))
    if current_snapshot.dirty is True:
        issues.append(_issue("warning", "dirty-worktree", "repository currently contains uncommitted changes"))
    elif project.get("is_git") and current_snapshot.dirty is None:
        issues.append(_issue("warning", "dirty-state-unknown", "Git worktree status could not be determined"))

    errors = sum(item["severity"] == "error" for item in issues)
    warnings = sum(item["severity"] == "warning" for item in issues)
    return {
        "valid": errors == 0,
        "source": str(root),
        "errors": errors,
        "warnings": warnings,
        "integrity_boundary": "checksum-only; validation is not source authentication",
        "issues": issues,
    }
