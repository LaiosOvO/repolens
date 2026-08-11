from __future__ import annotations

from ..models import DiagnosticRecord, FileRecord
from .base import AnalysisResult
from .go import GoResolutionStats, analyze_go, resolve_go_relationships
from .javascript import analyze_javascript
from .python import analyze_python


def analyze_file(file: FileRecord, source: str) -> AnalysisResult:
    """Analyze one file without allowing a parser defect to abort a scan."""

    try:
        if file.language == "Python":
            return analyze_python(file, source)
        if file.language in {"JavaScript", "TypeScript"}:
            return analyze_javascript(file, source)
        if file.language == "Go":
            return analyze_go(file, source)
        return AnalysisResult()
    except Exception as exc:  # noqa: BLE001 - this is the file isolation boundary
        return AnalysisResult(
            diagnostics=[
                DiagnosticRecord(
                    path=file.path,
                    severity="error",
                    code="analyzer-file-failure",
                    message=(
                        f"{file.language} analyzer failed for this file; "
                        f"the repository scan continued ({type(exc).__name__}: {exc})"
                    ),
                    line=None,
                )
            ]
        )


__all__ = [
    "AnalysisResult",
    "GoResolutionStats",
    "analyze_file",
    "analyze_go",
    "resolve_go_relationships",
]
