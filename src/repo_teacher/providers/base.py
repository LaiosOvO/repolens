"""Provider-independent structured generation interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StructuredGenerationRequest:
    stage: str
    source: Path
    workspace: Path
    prompt: str
    schema: dict[str, object]
    timeout_seconds: int


class StructuredModelProvider(Protocol):
    """One seam for Codex, OpenCode, DeepSeek, or deterministic test fakes."""

    @property
    def name(self) -> str: ...

    def generate(self, request: StructuredGenerationRequest) -> dict[str, object]: ...
