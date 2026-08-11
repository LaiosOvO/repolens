from __future__ import annotations

import re

from ..models import FileRecord, RelationshipRecord, SymbolRecord, stable_id
from .base import AnalysisResult


IMPORT_PATTERN = re.compile(
    r"^\s*(?:import\s+(?:[^'\";]+?\s+from\s+)?|export\s+[^'\";]+?\s+from\s+)[\"'](?P<module>[^\"']+)[\"']"
    r"|^\s*(?:const|let|var)\s+\w+\s*=\s*require\([\"'](?P<require>[^\"']+)[\"']\)",
    re.MULTILINE,
)

DECLARATION_PATTERNS = (
    (
        "class",
        re.compile(r"(?m)^(?P<prefix>\s*(?:export\s+(?:default\s+)?)?)class\s+(?P<name>[A-Za-z_$][\w$]*)"),
    ),
    (
        "function",
        re.compile(
            r"(?m)^(?P<prefix>\s*(?:export\s+(?:default\s+)?)?)(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?P<signature>\([^\n{]*\))"
        ),
    ),
    (
        "function",
        re.compile(
            r"(?m)^(?P<prefix>\s*(?:export\s+)?)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?P<signature>\([^\n]*?\)|[A-Za-z_$][\w$]*)\s*=>"
        ),
    ),
)


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def analyze_javascript(file: FileRecord, source: str) -> AnalysisResult:
    result = AnalysisResult()
    for match in IMPORT_PATTERN.finditer(source):
        target = match.group("module") or match.group("require")
        line = _line_number(source, match.start())
        result.relationships.append(
            RelationshipRecord(
                id=stable_id("rel", "import", file.id, target, file.path, line),
                source_id=file.id,
                target_id=None,
                target_name=target,
                kind="import",
                path=file.path,
                line=line,
                analyzer="javascript-regex",
                confidence="heuristic",
            )
        )

    seen: set[tuple[str, int]] = set()
    for kind, pattern in DECLARATION_PATTERNS:
        for match in pattern.finditer(source):
            name = match.group("name")
            line = _line_number(source, match.start())
            if (name, line) in seen:
                continue
            seen.add((name, line))
            prefix = match.groupdict().get("prefix") or ""
            signature = match.groupdict().get("signature")
            symbol = SymbolRecord(
                id=stable_id("symbol", file.path, kind, name, line),
                file_id=file.id,
                path=file.path,
                name=name,
                qualified_name=name,
                kind=kind,
                line=line,
                end_line=line,
                analyzer="javascript-regex",
                confidence="heuristic",
                signature=signature,
                exported="export" in prefix,
            )
            result.symbols.append(symbol)
            result.relationships.append(
                RelationshipRecord(
                    id=stable_id("rel", "contains", file.id, symbol.id, file.path, line),
                    source_id=file.id,
                    target_id=symbol.id,
                    target_name=name,
                    kind="contains",
                    path=file.path,
                    line=line,
                    analyzer="javascript-regex",
                    confidence="heuristic",
                )
            )

    result.symbols.sort(key=lambda item: (item.line, item.name))
    result.relationships.sort(key=lambda item: (item.line, item.kind, item.target_name))
    return result
