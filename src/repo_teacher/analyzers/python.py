from __future__ import annotations

import ast

from ..models import DiagnosticRecord, FileRecord, RelationshipRecord, SymbolRecord, stable_id
from .base import AnalysisResult


def _attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attribute_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, file: FileRecord) -> None:
        self.file = file
        self.result = AnalysisResult()
        self.scope: list[SymbolRecord] = []

    @property
    def source_id(self) -> str:
        return self.scope[-1].id if self.scope else self.file.id

    def _relationship(
        self,
        kind: str,
        target_name: str,
        line: int,
        *,
        target_id: str | None = None,
        confidence: str = "exact",
        source_id: str | None = None,
        receiver_type_hint: str | None = None,
    ) -> None:
        source = source_id or self.source_id
        identity_target = (
            f"{target_name}\x1f{receiver_type_hint}"
            if kind == "import" and receiver_type_hint
            else target_id or target_name
        )
        self.result.relationships.append(
            RelationshipRecord(
                id=stable_id(
                    "rel", kind, source, identity_target, self.file.path, line
                ),
                source_id=source,
                target_id=target_id,
                target_name=target_name,
                kind=kind,
                path=self.file.path,
                line=line,
                analyzer="python-ast",
                confidence=confidence,
                receiver_type_hint=receiver_type_hint,
            )
        )

    def _define(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> SymbolRecord:
        parent = self.scope[-1] if self.scope else None
        qualified_name = f"{parent.qualified_name}.{node.name}" if parent else node.name
        symbol = SymbolRecord(
            id=stable_id("symbol", self.file.path, kind, qualified_name, node.lineno),
            file_id=self.file.id,
            path=self.file.path,
            name=node.name,
            qualified_name=qualified_name,
            kind=kind,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
            analyzer="python-ast",
            confidence="exact",
            parent_id=parent.id if parent else None,
            signature=ast.unparse(node.args) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None,
            exported=not node.name.startswith("_"),
        )
        self.result.symbols.append(symbol)
        self._relationship(
            "contains",
            qualified_name,
            node.lineno,
            target_id=symbol.id,
            source_id=parent.id if parent else self.file.id,
        )
        return symbol

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        symbol = self._define(node, "class")
        self.scope.append(symbol)
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        kind = "method" if self.scope and self.scope[-1].kind == "class" else "function"
        symbol = self._define(node, kind)
        self.scope.append(symbol)
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        kind = "method" if self.scope and self.scope[-1].kind == "class" else "async-function"
        symbol = self._define(node, kind)
        self.scope.append(symbol)
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".", 1)[0]
            self._relationship(
                "import",
                alias.name,
                node.lineno,
                receiver_type_hint=f"binding:{local_name}",
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            target = f"{module}.{alias.name}".strip(".") if module else alias.name
            self._relationship(
                "import",
                target,
                node.lineno,
                receiver_type_hint=f"binding:{alias.asname or alias.name}",
            )

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        target = _attribute_name(node.func)
        if target:
            self._relationship("calls", target, node.lineno, confidence="heuristic")
        self.generic_visit(node)


def analyze_python(file: FileRecord, source: str) -> AnalysisResult:
    try:
        tree = ast.parse(source, filename=file.path)
    except SyntaxError as exc:
        return AnalysisResult(
            diagnostics=[
                DiagnosticRecord(
                    path=file.path,
                    severity="warning",
                    code="python-syntax-error",
                    message=exc.msg,
                    line=exc.lineno,
                )
            ]
        )
    visitor = _PythonVisitor(file)
    visitor.visit(tree)
    visitor.result.symbols.sort(key=lambda item: (item.line, item.qualified_name))
    visitor.result.relationships.sort(key=lambda item: (item.line, item.kind, item.target_name))
    return visitor.result
