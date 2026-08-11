from __future__ import annotations

import dataclasses
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_OPAQUE_SECRETS = (
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", re.IGNORECASE),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b(?:sk|rk)-(?:live|test|proj)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?im)(\b(?:[A-Za-z][A-Za-z0-9]*[_-])*(?:"
    r"api[_-]?key|client[_-]?secret|secret(?:[_-]access)?[_-]?key|"
    r"access[_-]?token|auth[_-]?token|refresh[_-]?token|token|"
    r"database[_-]?url|connection[_-]?string|password|passwd|"
    r"private[_-]?key|credential)s?\b\s*[:=]\s*)"
    r"(?P<quote>[\"']?)(?P<value>[^\r\n,;#\"']+)(?P=quote)"
)
_BEARER = re.compile(r"(?i)(\b(?:authorization\s*:\s*)?bearer\s+)[^\s,;]+")
_CREDENTIAL_URL = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)([^\s/@:]+):([^\s/@]+)@"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?"
    r"-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
)
_FULL_REDACTION_FIELDS = frozenset(
    {
        "description",
        "explanation",
        "license",
        "message",
        "notes",
        "purpose",
        "reason",
        "remote",
        "signature",
        "snippet",
        "summary",
        "text",
    }
)


def _redact_opaque_text(text: str) -> str:
    redacted = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    redacted = _CREDENTIAL_URL.sub(r"\1[REDACTED]@", redacted)
    redacted = _BEARER.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
    for pattern in _OPAQUE_SECRETS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_sensitive_text(text: str) -> str:
    """Return a fail-closed display copy for every persisted text surface."""

    redacted = _redact_opaque_text(text)
    redacted = _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}[REDACTED]", redacted
    )
    for pattern in _OPAQUE_SECRETS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_persisted_value(value: Any, *, field_name: str | None = None) -> Any:
    """Sanitize JSON values without rewriting graph identity/structure fields.

    Opaque credential families are unsafe in every string.  Assignment-style
    detection is intentionally limited to human-readable/source-bearing
    fields: applying ``credential=...`` matching to a Go import-alias edge
    would silently rewrite a valid package selector and poison disk-warm graph
    resolution.
    """

    if isinstance(value, str):
        if (field_name or "").casefold() in _FULL_REDACTION_FIELDS:
            return redact_sensitive_text(value)
        return _redact_opaque_text(value)
    if isinstance(value, dict):
        return {
            key: redact_persisted_value(item, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_persisted_value(item, field_name=field_name) for item in value]
    if isinstance(value, tuple):
        return tuple(
            redact_persisted_value(item, field_name=field_name) for item in value
        )
    return value


def stable_id(namespace: str, *parts: object) -> str:
    """Return a compact repeatable ID for an entity inside an index snapshot."""

    material = "\x1f".join(str(part) for part in (namespace, *parts))
    digest = hashlib.sha1(material.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"{namespace}_{digest}"


def to_dict(value: Any) -> Any:
    """Recursively convert index records into JSON-safe Python primitives."""

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_dict(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): to_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_dict(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass(slots=True)
class ProjectSnapshot:
    name: str
    path: str
    git_root: str | None
    is_git: bool
    commit: str | None
    branch: str | None
    dirty: bool | None
    remote: str | None
    license: str | None
    analyzed_at: str


@dataclass(slots=True)
class FileRecord:
    id: str
    path: str
    language: str
    size: int
    lines: int
    sha256: str
    module: str = "root"
    symbols: list[str] = field(default_factory=list)
    structural_sha256: str | None = None
    has_structural_analysis: bool = False
    analysis_sha256: str | None = None


@dataclass(slots=True)
class SymbolRecord:
    id: str
    file_id: str
    path: str
    name: str
    qualified_name: str
    kind: str
    line: int
    end_line: int
    analyzer: str
    confidence: str
    parent_id: str | None = None
    signature: str | None = None
    exported: bool = False


@dataclass(slots=True)
class RelationshipRecord:
    id: str
    source_id: str
    target_id: str | None
    target_name: str
    kind: str
    path: str
    line: int
    analyzer: str
    confidence: str
    receiver_type_hint: str | None = None


@dataclass(slots=True)
class DiagnosticRecord:
    path: str
    severity: str
    code: str
    message: str
    line: int | None = None


@dataclass(slots=True)
class ModuleSummary:
    id: str
    name: str
    path: str
    file_count: int
    symbol_count: int
    languages: dict[str, int]
    entrypoints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReadingStep:
    order: int
    title: str
    path: str
    reason: str
    symbol_id: str | None = None
    confidence: str = "heuristic"


@dataclass(slots=True)
class EvidenceRef:
    id: str
    path: str
    line_start: int
    line_end: int
    snippet: str
    snippet_sha256: str
    kind: str = "source"
    confidence: str = "exact"
    analyzer: str = "source-lines"
    symbol_id: str | None = None


@dataclass(slots=True)
class FeatureStep:
    order: int
    title: str
    explanation: str
    path: str
    line_start: int
    line_end: int
    evidence_ids: list[str] = field(default_factory=list)
    symbol_id: str | None = None
    relationship_id: str | None = None
    source_symbol: str | None = None
    source_role: str | None = None
    claim_scope: str | None = None
    snippet_sha256: str | None = None
    relationship_kind: str | None = None


@dataclass(slots=True)
class TechnologyClaim:
    dimension: str
    value: str
    claim_scope: str
    confidence: str
    evidence_ids: list[str] = field(default_factory=list)
    source_path: str | None = None


@dataclass(slots=True)
class FeatureRecord:
    id: str
    title: str
    kind: str
    summary: str
    entrypoint: str
    confidence: str
    source: str
    steps: list[FeatureStep] = field(default_factory=list)
    component_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    test_evidence_ids: list[str] = field(default_factory=list)
    technology_tags: list[str] = field(default_factory=list)
    technology_claims: list[TechnologyClaim] = field(default_factory=list)
    entry_symbol_id: str | None = None
    graph_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TutorialRecord:
    id: str
    feature_id: str
    title: str
    opening: str
    steps: list[FeatureStep]
    closing: str
    evidence_ids: list[str]
    confidence: str = "heuristic"
    source: str = "deterministic"


@dataclass(slots=True)
class CodeMapRecord:
    id: str
    feature_id: str
    title: str
    node_ids: list[str]
    edge_ids: list[str]
    steps: list[FeatureStep]
    mermaid: str
    evidence_ids: list[str]


@dataclass(slots=True)
class ChangeSummary:
    baseline_commit: str | None
    current_commit: str | None
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    reused_files: int = 0
    reanalyzed_files: int = 0


@dataclass(slots=True)
class CoverageReport:
    score: int
    status: str
    covered: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    metrics: dict[str, int | float] = field(default_factory=dict)
