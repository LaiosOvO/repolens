"""Explicit, optional gopls probes for Go differential validation.

The repository indexer does not import or invoke this module implicitly. A
caller must opt in by constructing :class:`GoplsAdapter`; absence of ``gopls``
therefore never changes the conservative lexer fallback or triggers a download.

The differential API compares declaration *occurrences*, not leaf-name sets.
Its identity contains file URI/path, source range, normalized qualified name,
and declaration kind so duplicate method names cannot hide missing declarations.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..models import DiagnosticRecord, SymbolRecord


_SYMBOL_LINE = re.compile(
    r"^(?P<indent>\s*)(?P<name>\S+)\s+(?P<kind>\S+)\s+"
    r"(?P<line>\d+):(?P<column>\d+)-(?P<end_line>\d+):(?P<end_column>\d+)$"
)
_DIAGNOSTIC_LINE = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+):(?P<column>\d+)-(?P<end_line>\d+):(?P<end_column>\d+):\s*(?P<message>.*)$"
)
_ACCEPTED_KINDS = frozenset(
    {"function", "interface", "interface-method", "method", "struct", "type"}
)


@dataclass(frozen=True, slots=True)
class GoplsSymbol:
    name: str
    qualified_name: str
    kind: str
    line: int
    column: int
    end_line: int
    end_column: int
    depth: int
    path: str
    uri: str


@dataclass(frozen=True, slots=True)
class DeclarationOccurrence:
    path: str
    uri: str
    line: int
    column: int
    end_line: int
    end_column: int
    kind: str
    qualified_name: str

    @property
    def label(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.column}-"
            f"{self.end_line}:{self.end_column} "
            f"{self.kind} {self.qualified_name}"
        )


@dataclass(frozen=True, slots=True)
class GoplsSampleManifest:
    path: str
    uri: str
    expected: int
    observed: int
    matched: int
    missing: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GoplsDifferential:
    available: bool
    executable: str | None
    gopls_count: int
    fallback_count: int
    matched: int
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    sample_manifest: tuple[GoplsSampleManifest, ...] = ()

    @property
    def recall(self) -> float:
        return self.matched / self.gopls_count if self.gopls_count else 1.0


def _display_path(file: Path, workspace: Path) -> str:
    resolved = file.resolve()
    try:
        return resolved.relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _normalize_qualified_name(raw: str) -> str:
    receiver = re.match(r"^\(\*?(?P<receiver>[^)]+)\)\.(?P<name>.+)$", raw)
    if receiver:
        receiver_name = receiver.group("receiver").split("[", 1)[0]
        return f"{receiver_name}.{receiver.group('name')}"
    return raw


def _normalize_kind(
    raw: str,
    parent_kind: str | None = None,
    *,
    source_line: str = "",
    name: str = "",
) -> str:
    lowered = raw.casefold()
    if lowered == "class":
        return "type"
    if lowered == "function" and re.match(
        rf"^\s*type\s+{re.escape(name)}\b", source_line
    ):
        # gopls uses the LSP Function SymbolKind for a named function type.
        # The fallback (and Go syntax) correctly model the declaration as type.
        return "type"
    if lowered == "method" and parent_kind == "interface":
        return "interface-method"
    return lowered


def _counter_difference(
    left: Counter[DeclarationOccurrence], right: Counter[DeclarationOccurrence]
) -> tuple[str, ...]:
    labels: list[str] = []
    for occurrence, count in sorted(
        (left - right).items(), key=lambda item: item[0].label
    ):
        labels.extend([occurrence.label] * count)
    return tuple(labels)


class GoplsAdapter:
    """Bounded command adapter used only when a caller explicitly opts in."""

    def __init__(self, executable: str | None = None, *, timeout: float = 20.0) -> None:
        if executable and not Path(executable).is_absolute() and "/" not in executable:
            self.executable = shutil.which(executable)
        else:
            self.executable = executable or shutil.which("gopls")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.executable and Path(self.executable).is_file())

    def _run(
        self, arguments: Sequence[str], *, cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        if not self.available:
            raise FileNotFoundError("gopls is not available; lexer fallback remains active")
        return subprocess.run(
            [str(self.executable), *arguments],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

    def document_symbols(self, file: Path, *, workspace: Path) -> list[GoplsSymbol]:
        completed = self._run(["symbols", str(file)], cwd=workspace)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "gopls symbols failed")
        path = _display_path(file, workspace)
        uri = file.resolve().as_uri()
        try:
            source_lines = file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            source_lines = []
        symbols: list[GoplsSymbol] = []
        hierarchy: list[GoplsSymbol] = []
        for line in completed.stdout.splitlines():
            match = _SYMBOL_LINE.match(line)
            if not match:
                continue
            indent = match.group("indent")
            depth = len(indent.expandtabs(2)) // 2
            while hierarchy and hierarchy[-1].depth >= depth:
                hierarchy.pop()
            raw_name = match.group("name")
            parent = hierarchy[-1] if hierarchy else None
            line_number = int(match.group("line"))
            source_line = (
                source_lines[line_number - 1]
                if 0 < line_number <= len(source_lines)
                else ""
            )
            kind = _normalize_kind(
                match.group("kind"),
                parent.kind if parent else None,
                source_line=source_line,
                name=raw_name,
            )
            qualified_name = _normalize_qualified_name(raw_name)
            if (
                "." not in qualified_name
                and parent is not None
                and kind == "interface-method"
            ):
                qualified_name = f"{parent.qualified_name}.{qualified_name}"
            symbol = GoplsSymbol(
                name=raw_name.rsplit(".", 1)[-1],
                qualified_name=qualified_name,
                kind=kind,
                line=line_number,
                column=int(match.group("column")),
                end_line=int(match.group("end_line")),
                end_column=int(match.group("end_column")),
                depth=depth,
                path=path,
                uri=uri,
            )
            symbols.append(symbol)
            hierarchy.append(symbol)
        return symbols

    def definition(
        self,
        file: Path,
        line: int,
        column: int,
        *,
        workspace: Path,
    ) -> dict[str, object] | None:
        completed = self._run(
            ["definition", "-json", f"{file}:{line}:{column}"], cwd=workspace
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        value = json.loads(completed.stdout)
        return value if isinstance(value, dict) else None

    def diagnostics(self, file: Path, *, workspace: Path) -> list[DiagnosticRecord]:
        completed = self._run(["check", str(file)], cwd=workspace)
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        diagnostics: list[DiagnosticRecord] = []
        for line in output.splitlines():
            match = _DIAGNOSTIC_LINE.match(line)
            if not match:
                continue
            diagnostics.append(
                DiagnosticRecord(
                    path=match.group("path"),
                    severity="warning",
                    code="gopls-diagnostic",
                    message=match.group("message"),
                    line=int(match.group("line")),
                )
            )
        return diagnostics

    @staticmethod
    def spread_sample(files: Sequence[Path], *, size: int = 30) -> tuple[Path, ...]:
        """Choose an auditable deterministic sample across sorted source paths."""

        if size <= 0:
            raise ValueError("sample size must be greater than zero")
        ordered = tuple(sorted({file.resolve() for file in files}, key=lambda item: item.as_posix()))
        if len(ordered) <= size:
            return ordered
        if size == 1:
            return (ordered[0],)
        indices = [round(index * (len(ordered) - 1) / (size - 1)) for index in range(size)]
        return tuple(ordered[index] for index in indices)

    @staticmethod
    def _semantic_occurrences(
        symbols: Sequence[GoplsSymbol],
    ) -> tuple[DeclarationOccurrence, ...]:
        return tuple(
            DeclarationOccurrence(
                path=item.path,
                uri=item.uri,
                line=item.line,
                column=item.column,
                end_line=item.end_line,
                end_column=item.end_column,
                kind=item.kind,
                qualified_name=item.qualified_name,
            )
            for item in symbols
            if item.kind in _ACCEPTED_KINDS
        )

    @staticmethod
    def _fallback_occurrences(
        file: Path,
        fallback: Sequence[SymbolRecord],
        *,
        workspace: Path,
    ) -> tuple[DeclarationOccurrence, ...]:
        try:
            lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        path = _display_path(file, workspace)
        uri = file.resolve().as_uri()
        occurrences: list[DeclarationOccurrence] = []
        for item in fallback:
            if (
                item.path != path
                or item.kind not in _ACCEPTED_KINDS
                or item.line <= 0
                or item.line > len(lines)
            ):
                continue
            source_line = lines[item.line - 1]
            if item.kind == "method":
                declaration = re.search(
                    rf"\bfunc\s*\([^)]*\)\s*{re.escape(item.name)}\b",
                    source_line,
                )
                matches = (
                    list(re.finditer(rf"\b{re.escape(item.name)}\b", declaration.group(0)))
                    if declaration
                    else []
                )
                offset = declaration.start() if declaration else 0
            else:
                matches = list(re.finditer(rf"\b{re.escape(item.name)}\b", source_line))
                offset = 0
            if not matches:
                continue
            match = matches[-1] if item.kind == "method" else matches[0]
            start = offset + match.start()
            column = len(source_line[:start].encode("utf-8")) + 1
            end_column = column + len(item.name.encode("utf-8"))
            occurrences.append(
                DeclarationOccurrence(
                    path=path,
                    uri=uri,
                    line=item.line,
                    column=column,
                    end_line=item.line,
                    end_column=end_column,
                    kind=item.kind,
                    qualified_name=_normalize_qualified_name(item.qualified_name),
                )
            )
        return tuple(occurrences)

    def differential(
        self,
        file: Path,
        fallback: Sequence[SymbolRecord],
        *,
        workspace: Path,
    ) -> GoplsDifferential:
        if not self.available:
            return GoplsDifferential(
                False, self.executable, 0, len(fallback), 0, (), (), ()
            )
        semantic = self._semantic_occurrences(
            self.document_symbols(file, workspace=workspace)
        )
        observed = self._fallback_occurrences(file, fallback, workspace=workspace)
        expected_counter = Counter(semantic)
        observed_counter = Counter(observed)
        matched = sum((expected_counter & observed_counter).values())
        missing = _counter_difference(expected_counter, observed_counter)
        extra = _counter_difference(observed_counter, expected_counter)
        path = _display_path(file, workspace)
        manifest = GoplsSampleManifest(
            path=path,
            uri=file.resolve().as_uri(),
            expected=len(semantic),
            observed=len(observed),
            matched=matched,
            missing=missing,
            extra=extra,
        )
        return GoplsDifferential(
            available=True,
            executable=self.executable,
            gopls_count=len(semantic),
            fallback_count=len(observed),
            matched=matched,
            missing=missing,
            extra=extra,
            sample_manifest=(manifest,),
        )

    def differential_sample(
        self,
        files: Sequence[Path],
        fallback: Sequence[SymbolRecord],
        *,
        workspace: Path,
        size: int = 30,
    ) -> GoplsDifferential:
        """Run occurrence-aware differentials for a deterministic file sample."""

        sample = self.spread_sample(files, size=size)
        fallback_by_path: dict[str, list[SymbolRecord]] = {}
        for item in fallback:
            fallback_by_path.setdefault(item.path, []).append(item)
        if not self.available:
            sampled_paths = {_display_path(file, workspace) for file in sample}
            observed = sum(
                len(values)
                for path, values in fallback_by_path.items()
                if path in sampled_paths
            )
            return GoplsDifferential(
                False, self.executable, 0, observed, 0, (), (), ()
            )

        reports: list[GoplsDifferential] = []
        for file in sample:
            path = _display_path(file, workspace)
            reports.append(
                self.differential(
                    file,
                    fallback_by_path.get(path, ()),
                    workspace=workspace,
                )
            )
        return GoplsDifferential(
            available=True,
            executable=self.executable,
            gopls_count=sum(item.gopls_count for item in reports),
            fallback_count=sum(item.fallback_count for item in reports),
            matched=sum(item.matched for item in reports),
            missing=tuple(value for item in reports for value in item.missing),
            extra=tuple(value for item in reports for value in item.extra),
            sample_manifest=tuple(
                value for item in reports for value in item.sample_manifest
            ),
        )


__all__ = [
    "DeclarationOccurrence",
    "GoplsAdapter",
    "GoplsDifferential",
    "GoplsSampleManifest",
    "GoplsSymbol",
]
