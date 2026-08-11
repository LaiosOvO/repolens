from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

from .models import EvidenceRef, stable_id


_OPAQUE_SECRET_PATTERNS = (
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", re.IGNORECASE),
    re.compile(r"\b(?:sk|rk)-(?:live|test|proj)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)
_BEARER = re.compile(r"(?i)(\b(?:authorization\s*:\s*)?bearer\s+)[^\s,;]+")
_CREDENTIAL_URL = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)([^\s/@:]+):([^\s/@]+)@"
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?im)(\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|"
    r"refresh[_-]?token|github[_-]?token|database[_-]?url|connection[_-]?string|"
    r"secret|password|passwd|private[_-]?key|credential)s?\b\s*[:=]\s*)"
    r"(?P<quote>[\"']?)(?P<value>[^\r\n,;#\"']+)(?P=quote)"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?"
    r"-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
)


def redact_secrets(text: str) -> str:
    """Fail closed for credential-shaped text before it enters JSON or HTML.

    The source hash is still calculated from the original text.  This function
    only controls the display copy: it intentionally favors hiding a harmless
    configuration value over persisting a credential.
    """

    redacted = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    redacted = _CREDENTIAL_URL.sub(r"\1[REDACTED]@", redacted)
    redacted = _BEARER.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
    redacted = _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}[REDACTED]", redacted
    )
    for pattern in _OPAQUE_SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


class EvidenceStore:
    """Create and validate immutable source-line evidence for one snapshot."""

    def __init__(self, contents: dict[str, str]) -> None:
        self._contents = {self._normalize(path): content for path, content in contents.items()}
        self._records: dict[str, EvidenceRef] = {}

    @staticmethod
    def _normalize(path: str) -> str:
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise ValueError(f"evidence path must be repository-relative: {path}")
        normalized = candidate.as_posix()
        if normalized in {"", "."}:
            raise ValueError(f"evidence path must name a file: {path}")
        return normalized

    @property
    def records(self) -> list[EvidenceRef]:
        return sorted(self._records.values(), key=lambda item: (item.path, item.line_start, item.line_end, item.id))

    def add(
        self,
        path: str,
        line_start: int,
        line_end: int,
        *,
        kind: str = "source",
        confidence: str = "exact",
        analyzer: str = "source-lines",
        symbol_id: str | None = None,
    ) -> EvidenceRef:
        normalized = self._normalize(path)
        if normalized not in self._contents:
            raise ValueError(f"evidence path was not indexed: {normalized}")
        lines = self._contents[normalized].splitlines()
        if line_start < 1 or line_end < line_start or line_end > len(lines):
            raise ValueError(
                f"invalid evidence range {normalized}:{line_start}-{line_end}; file has {len(lines)} lines"
            )
        source_snippet = "\n".join(lines[line_start - 1 : line_end])
        snippet = redact_secrets(source_snippet)
        snippet_sha256 = hashlib.sha256(source_snippet.encode("utf-8")).hexdigest()
        identifier = stable_id(
            "evidence", normalized, line_start, line_end, kind, confidence, analyzer, symbol_id or "", snippet_sha256
        )
        record = EvidenceRef(
            id=identifier,
            path=normalized,
            line_start=line_start,
            line_end=line_end,
            snippet=snippet,
            snippet_sha256=snippet_sha256,
            kind=kind,
            confidence=confidence,
            analyzer=analyzer,
            symbol_id=symbol_id,
        )
        self._records.setdefault(identifier, record)
        return self._records[identifier]

    def validate(self, evidence: EvidenceRef) -> bool:
        try:
            path = self._normalize(evidence.path)
        except ValueError:
            return False
        content = self._contents.get(path)
        if content is None:
            return False
        lines = content.splitlines()
        if evidence.line_start < 1 or evidence.line_end < evidence.line_start or evidence.line_end > len(lines):
            return False
        source_snippet = "\n".join(lines[evidence.line_start - 1 : evidence.line_end])
        digest = hashlib.sha256(source_snippet.encode("utf-8")).hexdigest()
        return redact_secrets(source_snippet) == evidence.snippet and digest == evidence.snippet_sha256
