from __future__ import annotations

from dataclasses import dataclass, field

from ..models import DiagnosticRecord, RelationshipRecord, SymbolRecord


@dataclass(slots=True)
class AnalysisResult:
    symbols: list[SymbolRecord] = field(default_factory=list)
    relationships: list[RelationshipRecord] = field(default_factory=list)
    diagnostics: list[DiagnosticRecord] = field(default_factory=list)

