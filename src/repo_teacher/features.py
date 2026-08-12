from __future__ import annotations

import ast
import functools
import hashlib
import itertools
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .capability_catalog import TECHNOLOGY_DIMENSIONS, discover_source_audited_capabilities
from .evidence import EvidenceStore
from .models import (
    FeatureRecord,
    FeatureStep,
    FileRecord,
    ModuleSummary,
    ProjectSnapshot,
    RelationshipRecord,
    SymbolRecord,
    TechnologyClaim,
    stable_id,
)


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
ENTRYPOINT_FILES = {
    "__main__.py",
    "main.py",
    "app.py",
    "cli.py",
    "server.py",
    "main.go",
    "main.ts",
    "main.tsx",
    "index.ts",
    "index.tsx",
    "index.js",
    "cli.ts",
    "cli.tsx",
    "server.ts",
    "server.js",
}
ENTRYPOINT_SYMBOLS = {"main", "cli", "run", "start", "serve", "run_server", "start_server"}
NON_PRODUCT_PARTS = {
    "doc", "docs", "example", "examples", "sample", "samples", "fixture", "fixtures",
    "test", "tests", "testing", "__tests__", "integration_test", "integration_tests",
    "e2e", "eval", "evals", "benchmark", "benchmarks", "demo", "demos", "playground", "generated",
}
PRODUCT_LANGUAGES = {"Python", "JavaScript", "TypeScript", "Go"}
_PYTHON_FACTORIES = {
    "fastapi.fastapi": ("http-server", "fastapi", "fastapi", "FastAPI"),
    "fastapi.apirouter": ("http-server", "fastapi", "fastapi", "APIRouter"),
    "flask.flask": ("http-server", "flask", "flask", "Flask"),
    "flask.blueprint": ("http-server", "flask", "flask", "Blueprint"),
    "starlette.applications.starlette": (
        "http-server", "starlette", "starlette.applications", "Starlette",
    ),
    "starlette.routing.router": ("http-server", "starlette", "starlette.routing", "Router"),
    "httpx.client": ("http-client", "httpx", "httpx", "Client"),
    "httpx.asyncclient": ("http-client", "httpx", "httpx", "AsyncClient"),
    "requests.session": ("http-client", "requests", "requests", "Session"),
    "requests.sessions.session": ("http-client", "requests", "requests.sessions", "Session"),
    "argparse.argumentparser": ("cli", "argparse", "argparse", "ArgumentParser"),
    "click.group": ("cli", "click", "click", "group"),
    "click.command": ("cli", "click", "click", "command"),
    "click.core.group": ("cli", "click", "click.core", "Group"),
    "typer.typer": ("cli", "typer", "typer", "Typer"),
}
_JS_HTTP_MODULES = {"express", "fastify", "@koa/router", "koa-router"}
_JS_HTTP_CLIENT_MODULES = {"axios", "got", "superagent"}
_JS_CLI_MODULES = {"commander", "yargs"}


@dataclass(frozen=True, slots=True)
class _SourceSite:
    line_start: int
    line_end: int
    snippet_sha256: str


def _source_site(source: str, line_start: int, line_end: int | None = None) -> _SourceSite:
    lines = source.splitlines()
    bounded_start = max(1, min(line_start, len(lines) or 1))
    bounded_end = max(bounded_start, min(line_end or line_start, len(lines) or bounded_start))
    snippet = "\n".join(lines[bounded_start - 1 : bounded_end])
    return _SourceSite(
        bounded_start,
        bounded_end,
        hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class _FrameworkBinding:
    kind: str
    framework: str
    module: str
    factory: str
    import_site: _SourceSite
    factory_site: _SourceSite
    owner_scope_id: int


@dataclass(frozen=True, slots=True)
class _ImportBinding:
    qualified_name: str
    source_site: _SourceSite


@dataclass(frozen=True, slots=True)
class _BindingIR:
    """Language-neutral abstract binding used by both provenance engines."""

    state: str
    value: _FrameworkBinding | _ImportBinding | None = None

    @classmethod
    def proven(cls, value: _FrameworkBinding | _ImportBinding) -> _BindingIR:
        return cls("proven", value)

    @classmethod
    def unknown(cls) -> _BindingIR:
        return cls("unknown")

    @classmethod
    def killed(cls) -> _BindingIR:
        return cls("killed")

    def resolve(self) -> _FrameworkBinding | _ImportBinding | None:
        return self.value if self.state == "proven" else None


_UNKNOWN_BINDING = _BindingIR.unknown()
_KILLED_BINDING = _BindingIR.killed()
_SCOPE_TOKEN_COUNTER = itertools.count(1)


@dataclass(slots=True)
class _ScopeIR:
    """Shared lexical scope IR; language visitors own assignment semantics."""

    parent: _ScopeIR | None
    kind: str
    values: dict[str, _BindingIR]
    local_names: set[str]
    boundary_scope: bool = False
    write_barrier: bool = False
    scope_token: int = field(default_factory=lambda: next(_SCOPE_TOKEN_COUNTER))

    def resolve_binding(self, name: str) -> _BindingIR:
        if name in self.values:
            return self.values[name]
        if name in self.local_names:
            return _UNKNOWN_BINDING
        return self.parent.resolve_binding(name) if self.parent is not None else _UNKNOWN_BINDING

    def resolve(self, name: str) -> _FrameworkBinding | _ImportBinding | None:
        return self.resolve_binding(name).resolve()


def _joined_values(
    base: dict[str, _BindingIR], outcomes: list[dict[str, _BindingIR]]
) -> dict[str, _BindingIR]:
    """Keep a value only when every reachable predecessor proves the same identity."""

    if not outcomes:
        return dict(base)
    keys = set(base).union(*(set(outcome) for outcome in outcomes))
    joined: dict[str, _BindingIR] = {}
    for name in keys:
        base_value = base.get(name, _UNKNOWN_BINDING)
        values = [outcome.get(name, base_value) for outcome in outcomes]
        # A conditional path may preserve an already-proven binding, but it may
        # not introduce new provenance.  Even identical factories in every
        # branch are distinct runtime objects and therefore remain unknown.
        joined[name] = (
            base_value if all(value == base_value for value in values) else _UNKNOWN_BINDING
        )
    return joined


@dataclass(frozen=True, slots=True)
class _Boundary:
    kind: str
    entrypoint: str
    line: int
    analyzer: str
    confirmed: bool
    provenance: _FrameworkBinding | None = None


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _python_import_reference(
    node: ast.expr, scope: _ScopeIR
) -> tuple[str, _SourceSite] | None:
    if isinstance(node, ast.Name):
        resolved = scope.resolve(node.id)
        return (
            (resolved.qualified_name.lower(), resolved.source_site)
            if isinstance(resolved, _ImportBinding)
            else None
        )
    if isinstance(node, ast.Attribute):
        parent = _python_import_reference(node.value, scope)
        return (f"{parent[0]}.{node.attr}".lower(), parent[1]) if parent else None
    return None


def _python_factory_binding(
    reference: tuple[str, _SourceSite] | None,
    factory_site: _SourceSite,
    owner_scope_id: int,
) -> _FrameworkBinding | None:
    metadata = _PYTHON_FACTORIES.get((reference[0] if reference else "").lower())
    return (
        _FrameworkBinding(*metadata, reference[1], factory_site, owner_scope_id)
        if metadata is not None and reference is not None
        else None
    )


def _python_binding_from_expr(
    node: ast.expr, scope: _ScopeIR, source: str
) -> _FrameworkBinding | _ImportBinding | None:
    if isinstance(node, ast.Name):
        return scope.resolve(node.id)
    if not isinstance(node, ast.Call):
        return None
    factory = _python_factory_binding(
        _python_import_reference(node.func, scope),
        _source_site(
            source,
            node.func.lineno,
            getattr(node.func, "end_lineno", node.func.lineno),
        ),
        scope.scope_token,
    )
    if factory is not None:
        return factory
    if isinstance(node.func, ast.Attribute) and node.func.attr == "add_subparsers":
        receiver = _python_binding_from_expr(node.func.value, scope, source)
        return receiver if isinstance(receiver, _FrameworkBinding) and receiver.kind == "cli" else None
    return None


def _python_target_names(node: ast.expr) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return {name for item in node.elts for name in _python_target_names(item)}
    return set()


class _PythonLocalCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.external: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self.names.update(_python_target_names(target))
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.names.update(_python_target_names(node.target))
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.names.update(_python_target_names(node.target))
        self.visit(node.value)

    def visit_For(self, node: ast.For) -> None:
        self.names.update(_python_target_names(node.target))
        self.visit(node.iter)
        for statement in (*node.body, *node.orelse):
            self.visit(statement)

    visit_AsyncFor = visit_For

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self.names.update(_python_target_names(item.optional_vars))
        for statement in node.body:
            self.visit(statement)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self.names.add(node.name)
        for statement in node.body:
            self.visit(statement)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self.names.update(_python_target_names(target))

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.names.update(_python_target_names(node.target))
        self.visit(node.value)

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        for case in node.cases:
            self.names.update(_python_pattern_names(case.pattern))
            if case.guard is not None:
                self.visit(case.guard)
            for statement in case.body:
                self.visit(statement)

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(alias.asname or alias.name.split(".", 1)[0] for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.names.update(alias.asname or alias.name for alias in node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Defaults are evaluated in the enclosing scope; the body is not.
        self.visit(node.args)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        for generator in node.generators:
            self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        self.visit(node.elt)

    visit_SetComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node: ast.DictComp) -> None:
        for generator in node.generators:
            self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        self.visit(node.key)
        self.visit(node.value)

    def visit_Global(self, node: ast.Global) -> None:
        self.external.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.external.update(node.names)


def _python_local_names(statements: list[ast.stmt]) -> set[str]:
    collector = _PythonLocalCollector()
    for statement in statements:
        collector.visit(statement)
    return collector.names - collector.external


def _python_expression_local_names(expression: ast.expr) -> set[str]:
    collector = _PythonLocalCollector()
    collector.visit(expression)
    return collector.names - collector.external


def _python_pattern_names(pattern: ast.pattern) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(pattern):
        if isinstance(node, ast.MatchAs) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.MatchStar) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names.add(node.rest)
    return names


def _python_argument_names(arguments: ast.arguments) -> set[str]:
    return {
        argument.arg
        for argument in (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *((arguments.vararg,) if arguments.vararg else ()),
            *((arguments.kwarg,) if arguments.kwarg else ()),
        )
    }


def _python_route_method(node: ast.Call, member: str) -> str | None:
    if member in HTTP_METHODS:
        return member.upper()
    if member not in {"route", "add_api_route", "add_url_rule"}:
        return None
    for keyword in node.keywords:
        if keyword.arg != "methods" or not isinstance(keyword.value, (ast.List, ast.Tuple)):
            continue
        methods = [
            item.value.upper()
            for item in keyword.value.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        ]
        if methods:
            return ",".join(methods)
    return "GET"


def _python_direct_boundary_call_ids(statements: list[ast.stmt]) -> set[int]:
    """Return calls executed immediately by this lexical body."""

    calls: set[int] = set()
    for statement in statements:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            calls.add(id(statement.value))
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls.update(id(item) for item in statement.decorator_list if isinstance(item, ast.Call))
    return calls


class _PythonYieldFinder(ast.NodeVisitor):
    def __init__(self) -> None:
        self.found = False

    def visit_Yield(self, node: ast.Yield) -> None:
        self.found = True

    visit_YieldFrom = visit_Yield

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_Lambda = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef


def _python_is_generator_body(statements: list[ast.stmt]) -> bool:
    finder = _PythonYieldFinder()
    for statement in statements:
        finder.visit(statement)
    return finder.found


class _PythonBoundaryVisitor(ast.NodeVisitor):
    def __init__(self, source: str) -> None:
        self.source = source
        self.scope = _ScopeIR(None, "module", {}, set(), boundary_scope=True)
        self.direct_boundary_call_ids: set[int] = set()
        self.boundaries: list[_Boundary] = []

    def visit_Module(self, node: ast.Module) -> None:
        previous = self.direct_boundary_call_ids
        self.direct_boundary_call_ids = _python_direct_boundary_call_ids(node.body)
        for statement in node.body:
            self.visit(statement)
        self.direct_boundary_call_ids = previous

    def _set_target(
        self, target: ast.expr, value: _FrameworkBinding | _ImportBinding | None
    ) -> None:
        for name in _python_target_names(target):
            self.scope.values[name] = (
                _BindingIR.proven(value) if value is not None else _UNKNOWN_BINDING
            )

    def _kill_target(self, target: ast.expr) -> None:
        for name in _python_target_names(target):
            self.scope.values[name] = _KILLED_BINDING

    def _run_path(
        self,
        statements: list[ast.stmt],
        initial: dict[str, _BindingIR],
    ) -> dict[str, _BindingIR]:
        self.scope.values = dict(initial)
        for statement in statements:
            self.visit(statement)
        return dict(self.scope.values)

    def visit_Import(self, node: ast.Import) -> None:
        site = _source_site(self.source, node.lineno, getattr(node, "end_lineno", node.lineno))
        for alias in node.names:
            local = alias.asname or alias.name.split(".", 1)[0]
            qualified = alias.name if alias.asname else alias.name.split(".", 1)[0]
            self.scope.values[local] = _BindingIR.proven(_ImportBinding(qualified, site))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            site = _source_site(self.source, node.lineno, getattr(node, "end_lineno", node.lineno))
            for alias in node.names:
                self.scope.values[alias.asname or alias.name] = _BindingIR.proven(
                    _ImportBinding(f"{node.module}.{alias.name}", site)
                )

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        value = _python_binding_from_expr(node.value, self.scope, self.source)
        for target in node.targets:
            self._set_target(target, value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self._set_target(
            node.target,
            _python_binding_from_expr(node.value, self.scope, self.source)
            if node.value is not None
            else None,
        )

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        self._set_target(node.target, None)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        target_scope = self.scope
        while target_scope.kind == "comprehension" and target_scope.parent is not None:
            target_scope = target_scope.parent
        value = _python_binding_from_expr(node.value, self.scope, self.source)
        for name in _python_target_names(node.target):
            target_scope.values[name] = (
                _BindingIR.proven(value) if value is not None else _UNKNOWN_BINDING
            )

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._kill_target(target)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        self.scope.values[node.name] = _UNKNOWN_BINDING
        argument_names = _python_argument_names(node.args)
        lexical_parent = self.scope.parent if self.scope.kind == "class" else self.scope
        parent = self.scope
        locals_ = _python_local_names(node.body) | argument_names
        is_boundary_scope = (
            isinstance(node, ast.FunctionDef)
            and parent.kind == "module"
            and not _python_is_generator_body(node.body)
        )
        self.scope = _ScopeIR(
            lexical_parent,
            "function",
            {name: _UNKNOWN_BINDING for name in argument_names},
            locals_,
            boundary_scope=is_boundary_scope,
        )
        previous_direct_calls = self.direct_boundary_call_ids
        self.direct_boundary_call_ids = (
            _python_direct_boundary_call_ids(node.body) if is_boundary_scope else set()
        )
        for statement in node.body:
            self.visit(statement)
        self.direct_boundary_call_ids = previous_direct_calls
        self.scope = parent

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        self.scope.values[node.name] = _UNKNOWN_BINDING
        parent = self.scope
        self.scope = _ScopeIR(parent, "class", {}, _python_local_names(node.body))
        for statement in node.body:
            self.visit(statement)
        self.scope = parent

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        argument_names = _python_argument_names(node.args)
        parent = self.scope.parent if self.scope.kind == "class" else self.scope
        previous = self.scope
        locals_ = _python_expression_local_names(node.body) | argument_names
        self.scope = _ScopeIR(
            parent,
            "lambda",
            {name: _UNKNOWN_BINDING for name in argument_names},
            locals_,
        )
        self.visit(node.body)
        self.scope = previous

    def _visit_comprehension(
        self,
        generators: list[ast.comprehension],
        result_nodes: tuple[ast.expr, ...],
    ) -> None:
        if not generators:
            return
        self.visit(generators[0].iter)
        previous = self.scope
        outer_scopes: list[_ScopeIR] = []
        cursor: _ScopeIR | None = previous
        while cursor is not None:
            outer_scopes.append(cursor)
            cursor = cursor.parent
        outer_base = [dict(scope.values) for scope in outer_scopes]
        self.scope = _ScopeIR(previous, "comprehension", {}, set())
        for position, generator in enumerate(generators):
            if position:
                self.visit(generator.iter)
            self._set_target(generator.target, None)
            self.scope.local_names.update(_python_target_names(generator.target))
            for condition in generator.ifs:
                self.visit(condition)
        for result_node in result_nodes:
            self.visit(result_node)
        self.scope = previous
        for scope, base in zip(outer_scopes, outer_base, strict=True):
            executed = dict(scope.values)
            scope.values = _joined_values(base, [base, executed])

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node.generators, (node.elt,))

    visit_SetComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node.generators, (node.key, node.value))

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._set_target(item.optional_vars, None)
        for statement in node.body:
            self.visit(statement)

    visit_AsyncWith = visit_With

    def _visit_branch_paths(self, paths: list[list[ast.stmt]]) -> None:
        base = dict(self.scope.values)
        outcomes: list[dict[str, _BindingIR]] = []
        for path in paths:
            outcomes.append(self._run_path(path, base))
        self.scope.values = _joined_values(base, outcomes)

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        self._visit_branch_paths([node.body, node.orelse or []])

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.test)
        self._visit_branch_paths([[], node.body, node.orelse or []])

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        base = dict(self.scope.values)
        self.scope.values = dict(base)
        self._set_target(node.target, None)
        body_outcome = self._run_path(node.body, dict(self.scope.values))
        else_outcome = self._run_path(node.orelse, base)
        self.scope.values = _joined_values(base, [base, body_outcome, else_outcome])

    visit_AsyncFor = visit_For

    def visit_Try(self, node: ast.Try) -> None:
        base = dict(self.scope.values)
        body_outcome = self._run_path(node.body, base)
        normal_outcome = self._run_path(node.orelse, body_outcome)
        outcomes = [normal_outcome]
        for handler in node.handlers:
            self.scope.values = dict(base)
            if handler.type is not None:
                self.visit(handler.type)
            if handler.name:
                self.scope.values[handler.name] = _UNKNOWN_BINDING
            handler_outcome = self._run_path(handler.body, dict(self.scope.values))
            if handler.name:
                handler_outcome[handler.name] = _KILLED_BINDING
            outcomes.append(handler_outcome)
        self.scope.values = _joined_values(base, outcomes)
        for statement in node.finalbody:
            self.visit(statement)

    visit_TryStar = visit_Try

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        base = dict(self.scope.values)
        outcomes = [dict(base)]
        for case in node.cases:
            self.scope.values = dict(base)
            for name in _python_pattern_names(case.pattern):
                self.scope.values[name] = _UNKNOWN_BINDING
            if case.guard is not None:
                self.visit(case.guard)
            outcomes.append(self._run_path(case.body, dict(self.scope.values)))
        self.scope.values = _joined_values(base, outcomes)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if not node.values:
            return
        self.visit(node.values[0])
        for value in node.values[1:]:
            skipped = dict(self.scope.values)
            self.scope.values = dict(skipped)
            self.visit(value)
            evaluated = dict(self.scope.values)
            self.scope.values = _joined_values(skipped, [skipped, evaluated])

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.visit(node.test)
        base = dict(self.scope.values)
        self.scope.values = dict(base)
        self.visit(node.body)
        body_outcome = dict(self.scope.values)
        self.scope.values = dict(base)
        self.visit(node.orelse)
        else_outcome = dict(self.scope.values)
        self.scope.values = _joined_values(base, [body_outcome, else_outcome])

    def visit_Call(self, node: ast.Call) -> None:
        if (
            id(node) in self.direct_boundary_call_ids
            and self.scope.boundary_scope
            and isinstance(node.func, ast.Attribute)
        ):
            name = node.func.attr.lower()
            first = node.args[0] if node.args else None
            provenance = _python_binding_from_expr(node.func.value, self.scope, self.source)
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and isinstance(provenance, _FrameworkBinding)
                and provenance.owner_scope_id == self.scope.scope_token
            ):
                if (
                    name in {"command", "add_parser"}
                    and provenance.kind == "cli"
                    and re.fullmatch(r"[a-zA-Z0-9_.:-]+", first.value)
                ):
                    self.boundaries.append(
                        _Boundary(
                            "cli-command", first.value, node.lineno,
                            "python-ast-call", True, provenance,
                        )
                    )
                method = _python_route_method(node, name)
                if method and provenance.kind == "http-server" and first.value.startswith("/"):
                    self.boundaries.append(
                        _Boundary(
                            "http-route", f"{method} {first.value}", node.lineno,
                            "python-ast-call", True, provenance,
                        )
                    )
        self.generic_visit(node)


def _python_boundaries(source: str) -> list[_Boundary]:
    """Return boundaries only when the receiver is proven at that lexical call site."""

    try:
        tree = ast.parse(source)
        compile(tree, "<repo-teacher-boundary>", "exec", dont_inherit=True)
    except (SyntaxError, TypeError, ValueError):
        return []
    visitor = _PythonBoundaryVisitor(source)
    visitor.visit(tree)
    return sorted(
        set(visitor.boundaries),
        key=lambda item: (item.line, item.kind, item.entrypoint, not item.confirmed),
    )


def _js_tokens(source: str) -> list[tuple[str, str, int]]:
    """Lex enough JS/TS to distinguish calls from comments/string contents.

    Strings are emitted as a single token only when they occur in source code;
    comments are discarded.  This intentionally avoids a regex fallback: a
    malformed/unsupported construct is omitted rather than promoted to a feature.
    """

    tokens: list[tuple[str, str, int]] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated JavaScript block comment")
            index = end + 2
            continue
        if char == "/" and (
            not tokens
            or tokens[-1][1] in {"(", "[", "{", ",", "=", ";", ":", "!", "?"}
            or (
                tokens[-1][0] == "identifier"
                and tokens[-1][1] in {"case", "return", "throw", "yield"}
            )
        ):
            # A slash after an expression token is division.  Only positions
            # where JavaScript grammar permits a new expression may start a
            # regex literal; its contents stay opaque to boundary discovery.
            cursor = index + 1
            in_class = False
            while cursor < length:
                if source[cursor] == "\\":
                    cursor += 2
                    continue
                if source[cursor] == "[":
                    in_class = True
                elif source[cursor] == "]":
                    in_class = False
                elif source[cursor] == "/" and not in_class:
                    cursor += 1
                    while cursor < length and source[cursor].isalpha():
                        cursor += 1
                    index = cursor
                    break
                elif source[cursor] == "\n":
                    break
                cursor += 1
            else:
                index += 1
                continue
            if index == cursor:
                continue
        if char in {'"', "'", "`"}:
            quote = char
            start = index
            index += 1
            value: list[str] = []
            interpolated = False
            closed = False
            while index < length:
                current = source[index]
                if current == "\\" and index + 1 < length:
                    value.append(source[index + 1])
                    index += 2
                    continue
                if quote == "`" and source.startswith("${", index):
                    interpolated = True
                if current == quote:
                    index += 1
                    closed = True
                    break
                value.append(current)
                index += 1
            if not closed:
                raise ValueError("unterminated JavaScript string")
            if not interpolated:
                tokens.append(("string", "".join(value), start))
            continue
        if char.isalpha() or char in {"_", "$"}:
            start = index
            index += 1
            while index < length and (source[index].isalnum() or source[index] in {"_", "$"}):
                index += 1
            tokens.append(("identifier", source[start:index], start))
            continue
        if char.isdigit():
            start = index
            index += 1
            while index < length and (
                source[index].isalnum() or source[index] in {"_", "."}
            ):
                index += 1
            tokens.append(("number", source[start:index], start))
            continue
        operator = next(
            (
                candidate
                for candidate in (
                    "...", "&&=", "||=", "??=", "=>", "&&", "||", "??",
                    "+=", "-=", "*=", "/=", "++", "--", "==", "!=", "<=", ">=",
                )
                if source.startswith(candidate, index)
            ),
            None,
        )
        if operator is not None:
            tokens.append(("punctuation", operator, index))
            index += len(operator)
            continue
        if char in ".(),=;[]{}:!?><+-*&|/%~^#":
            tokens.append(("punctuation", char, index))
            index += 1
            continue
        raise ValueError(f"unsupported JavaScript token at byte {index}: {char!r}")
    return tokens


@dataclass(frozen=True, slots=True)
class _JSImportBinding:
    module: str
    exported: str
    source_site: _SourceSite


def _js_import_bindings(
    tokens: list[tuple[str, str, int]], source: str
) -> dict[str, _BindingIR]:
    """Return hoisted ESM imports; CommonJS is resolved in execution order."""

    imports: dict[str, _BindingIR] = {}
    for position, token in enumerate(tokens):
        if token[1] != "import":
            continue
        cursor = position + 1
        imported: list[tuple[str, str]] = []
        if cursor < len(tokens) and tokens[cursor][0] == "identifier":
            imported.append((tokens[cursor][1], "default"))
            cursor += 1
        while cursor < len(tokens) and tokens[cursor][1] != "from":
            if tokens[cursor][0] == "identifier" and tokens[cursor][1] not in {"as", "type"}:
                exported = tokens[cursor][1]
                local = exported
                if cursor + 2 < len(tokens) and tokens[cursor + 1][1] == "as":
                    local = tokens[cursor + 2][1]
                    cursor += 2
                imported.append((local, exported))
            cursor += 1
        if cursor + 1 >= len(tokens) or tokens[cursor + 1][0] != "string":
            continue
        module = tokens[cursor + 1][1]
        site = _source_site(source, _line_number(source, token[2]))
        for local, exported in imported:
            imports[local] = _BindingIR.proven(_JSImportBinding(module, exported, site))
    return imports


def _js_require_binding(
    tokens: list[tuple[str, str, int]], start: int
) -> tuple[str, str, int] | None:
    if start + 3 >= len(tokens) or tokens[start][1] != "require":
        return None
    opening, module, closing = tokens[start + 1 : start + 4]
    if opening[1] != "(" or module[0] != "string" or closing[1] != ")":
        return None
    exported = "default"
    end = start + 3
    if end + 2 < len(tokens) and tokens[end + 1][1] == "." and tokens[end + 2][0] == "identifier":
        exported = tokens[end + 2][1]
        end += 2
    return module[1], exported, end


def _js_module_binding(
    module: str,
    exported: str,
    import_site: _SourceSite,
    factory_site: _SourceSite,
    owner_scope_id: int,
) -> _FrameworkBinding | None:
    normalized_module = module.lower()
    normalized_export = exported.lower()
    if normalized_module in _JS_HTTP_CLIENT_MODULES:
        return _FrameworkBinding(
            "http-client", normalized_module, module, exported, import_site, factory_site,
            owner_scope_id,
        )
    if normalized_module in _JS_HTTP_MODULES and normalized_export in {
        "default", "express", "fastify", "router",
    }:
        framework = "koa-router" if normalized_module in {"@koa/router", "koa-router"} else normalized_module
        return _FrameworkBinding(
            "http-server", framework, module, exported, import_site, factory_site,
            owner_scope_id,
        )
    if normalized_module in _JS_CLI_MODULES and normalized_export in {
        "default", "command", "commander", "yargs",
    }:
        return _FrameworkBinding(
            "cli", normalized_module, module, exported, import_site, factory_site,
            owner_scope_id,
        )
    return None


def _js_value_binding(
    tokens: list[tuple[str, str, int]],
    start: int,
    end: int,
    resolve: Callable[[str], _FrameworkBinding | _JSImportBinding | None],
    source: str,
    owner_scope_id: int,
) -> _FrameworkBinding | _JSImportBinding | None:
    """Resolve only a complete, side-effect-free alias/factory expression."""

    cursor = start
    while cursor < end and tokens[cursor][1] == "(":
        cursor += 1
    if cursor < len(tokens) and tokens[cursor][1] == "new":
        cursor += 1
    required = _js_require_binding(tokens, cursor)
    if required is not None:
        module, exported, require_end = required
        import_site = _source_site(source, _line_number(source, tokens[cursor][2]))
        if require_end + 1 < end and tokens[require_end + 1][1] == "(":
            return _js_module_binding(
                module,
                exported,
                import_site,
                _source_site(source, _line_number(source, tokens[cursor][2])),
                owner_scope_id,
            )
        return _JSImportBinding(module, exported, import_site)
    if cursor >= end or tokens[cursor][0] != "identifier":
        return None
    value = resolve(tokens[cursor][1])
    if isinstance(value, _FrameworkBinding):
        return value if cursor + 1 >= end or tokens[cursor + 1][1] not in {"(", "."} else None
    if not isinstance(value, _JSImportBinding):
        return None
    module, exported = value.module, value.exported
    if cursor + 2 < end and tokens[cursor + 1][1] == ".":
        exported = tokens[cursor + 2][1]
        cursor += 2
    if cursor + 1 < end and tokens[cursor + 1][1] == "(":
        # Reject `factory() && {}` and other compound values.  A balanced call
        # may be followed only by closing parens belonging to the initializer.
        depth = 0
        call_end = None
        for position in range(cursor + 1, end):
            if tokens[position][1] == "(":
                depth += 1
            elif tokens[position][1] == ")":
                depth -= 1
                if depth == 0:
                    call_end = position
                    break
        if call_end is None or any(
            tokens[position][1] not in {")"} for position in range(call_end + 1, end)
        ):
            return None
        return _js_module_binding(
            module,
            exported,
            value.source_site,
            _source_site(source, _line_number(source, tokens[start][2])),
            owner_scope_id,
        )
    return value if cursor + 1 == end else None


def _js_brace_pairs(tokens: list[tuple[str, str, int]]) -> dict[int, int]:
    stack: list[int] = []
    pairs: dict[int, int] = {}
    for position, token in enumerate(tokens):
        if token[1] == "{":
            stack.append(position)
        elif token[1] == "}" and stack:
            opening = stack.pop()
            pairs[opening] = position
    return pairs


def _js_pairs(tokens: list[tuple[str, str, int]]) -> tuple[dict[int, int], dict[int, int]]:
    pairs: dict[int, int] = {}
    reverse: dict[int, int] = {}
    stack: list[tuple[str, int]] = []
    closing_for = {")": "(", "]": "[", "}": "{"}
    for position, token in enumerate(tokens):
        value = token[1]
        if value in {"(", "[", "{"}:
            stack.append((value, position))
        elif value in closing_for:
            if not stack or stack[-1][0] != closing_for[value]:
                raise ValueError("mismatched JavaScript delimiters")
            _opening_value, opening = stack.pop()
            pairs[opening] = position
            reverse[position] = opening
    if stack:
        raise ValueError("unterminated JavaScript delimiters")
    return pairs, reverse


def _js_pattern_names(
    tokens: list[tuple[str, str, int]], start: int, end: int
) -> set[str]:
    names: set[str] = set()
    position = start
    while position < end:
        token = tokens[position]
        if token[0] != "identifier" or token[1] in {"const", "let", "var"}:
            position += 1
            continue
        if position + 1 < end and tokens[position + 1][1] == ":":
            if position + 2 < end and tokens[position + 2][0] == "identifier":
                names.add(tokens[position + 2][1])
                position += 3
                continue
        names.add(token[1])
        position += 1
        while position < end and tokens[position][1] == "=":
            position += 1
            while position < end and tokens[position][1] not in {",", "}", "]"}:
                position += 1
    return names


def _js_parameter_names(
    tokens: list[tuple[str, str, int]],
    start: int,
    end: int,
    pairs: dict[int, int],
) -> set[str]:
    """Read binding names from JS/TS parameters, not type annotation names."""

    modifiers = {"public", "private", "protected", "readonly", "override"}
    segments: list[tuple[int, int]] = []
    segment_start = start
    position = start
    while position < end:
        value = tokens[position][1]
        if value in {"(", "[", "{"} and position in pairs:
            position = pairs[position] + 1
            continue
        if value == ",":
            segments.append((segment_start, position))
            segment_start = position + 1
        position += 1
    segments.append((segment_start, end))

    names: set[str] = set()
    for segment_start, segment_end in segments:
        cursor = segment_start
        while cursor < segment_end and tokens[cursor][1] in {"...", *modifiers}:
            cursor += 1
        if cursor >= segment_end:
            continue
        if tokens[cursor][1] in {"{", "["}:
            closing = pairs.get(cursor)
            if closing is not None and closing < segment_end:
                names.update(_js_pattern_names(tokens, cursor, closing + 1))
            continue
        while cursor < segment_end:
            if tokens[cursor][0] == "identifier" and tokens[cursor][1] not in modifiers:
                names.add(tokens[cursor][1])
                break
            cursor += 1
    return names


class _JSBoundaryAnalyzer:
    """Conservative statement/dataflow interpreter over the shared Binding/Scope IR."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = _js_tokens(source)
        self.pairs, self.reverse_pairs = _js_pairs(self.tokens)
        imports = _js_import_bindings(self.tokens, source)
        self.scope = _ScopeIR(None, "module", imports, set(imports), boundary_scope=True)
        self.boundaries: list[_Boundary] = []

    def _scope_chain(self) -> list[_ScopeIR]:
        chain: list[_ScopeIR] = []
        scope: _ScopeIR | None = self.scope
        while scope is not None:
            chain.append(scope)
            scope = scope.parent
        return list(reversed(chain))

    def _snapshot(self) -> list[dict[str, _BindingIR]]:
        return [dict(scope.values) for scope in self._scope_chain()]

    def _restore(self, snapshot: list[dict[str, _BindingIR]]) -> None:
        chain = self._scope_chain()
        if len(chain) != len(snapshot):
            raise ValueError("JavaScript CFG scope depth changed across a branch")
        for scope, values in zip(chain, snapshot, strict=True):
            scope.values = dict(values)

    def _join_snapshots(
        self,
        base: list[dict[str, _BindingIR]],
        outcomes: list[list[dict[str, _BindingIR]]],
    ) -> None:
        chain = self._scope_chain()
        for index, scope in enumerate(chain):
            scope.values = _joined_values(
                base[index], [outcome[index] for outcome in outcomes]
            )

    def _resolve(self, name: str) -> _FrameworkBinding | _JSImportBinding | None:
        return self.scope.resolve(name)

    def _binding(self, value: _FrameworkBinding | _JSImportBinding | None) -> _BindingIR:
        return _BindingIR.proven(value) if value is not None else _UNKNOWN_BINDING

    def _declare(
        self,
        name: str,
        value: _FrameworkBinding | _JSImportBinding | None,
        declaration: str,
    ) -> None:
        target = self.scope
        if declaration == "var":
            while target.parent is not None and target.kind not in {"function", "module"}:
                target = target.parent
        target.local_names.add(name)
        target.values[name] = self._binding(value)

    def _assign(self, name: str, value: _FrameworkBinding | _JSImportBinding | None) -> None:
        origin = self.scope
        scope: _ScopeIR | None = self.scope
        while scope is not None:
            if name in scope.values or name in scope.local_names:
                if origin.write_barrier and scope is not origin:
                    origin.local_names.add(name)
                    origin.values[name] = self._binding(value)
                    return
                scope.values[name] = self._binding(value)
                return
            scope = scope.parent
        if origin.write_barrier:
            origin.local_names.add(name)
            origin.values[name] = self._binding(value)
            return
        root = self._scope_chain()[0]
        root.values[name] = self._binding(value)

    def _statement_end(self, start: int, end: int) -> int:
        position = start
        while position < end:
            value = self.tokens[position][1]
            if value in {"(", "[", "{"} and position in self.pairs:
                position = self.pairs[position] + 1
                continue
            if value == ";":
                return position
            position += 1
        return end

    def _direct_lexical_names(self, start: int, end: int) -> set[str]:
        names: set[str] = set()
        position = start
        while position < end:
            value = self.tokens[position][1]
            if value in {"(", "[", "{"} and position in self.pairs:
                position = self.pairs[position] + 1
                continue
            if value in {"let", "const"}:
                stop = self._statement_end(position + 1, end)
                assignment = next(
                    (cursor for cursor in range(position + 1, stop) if self.tokens[cursor][1] == "="),
                    stop,
                )
                names.update(
                    _js_parameter_names(
                        self.tokens, position + 1, assignment, self.pairs
                    )
                )
            elif value in {"function", "class"}:
                if position + 1 < end and self.tokens[position + 1][0] == "identifier":
                    names.add(self.tokens[position + 1][1])
            position += 1
        return names

    def _var_names(self, start: int, end: int) -> set[str]:
        names: set[str] = set()
        position = start
        while position < end:
            if self.tokens[position][1] == "var":
                stop = self._statement_end(position + 1, end)
                assignment = next(
                    (cursor for cursor in range(position + 1, stop) if self.tokens[cursor][1] == "="),
                    stop,
                )
                names.update(
                    _js_parameter_names(
                        self.tokens, position + 1, assignment, self.pairs
                    )
                )
            position += 1
        return names

    def _emit_calls(self, start: int, end: int, allow_boundary_call: bool) -> None:
        if not allow_boundary_call:
            return
        for position in range(start, max(start, end - 4)):
            receiver, dot, member, opening, value = self.tokens[position : position + 5]
            if (
                receiver[0] != "identifier"
                or dot[1] != "."
                or member[0] != "identifier"
                or opening[1] != "("
                or value[0] != "string"
            ):
                continue
            call_end = self.pairs.get(position + 3)
            if (
                call_end is None
                or call_end >= end
                or position != start
                or call_end != end - 1
            ):
                continue
            provenance = self._resolve(receiver[1])
            if (
                not self.scope.boundary_scope
                or not isinstance(provenance, _FrameworkBinding)
                or provenance.owner_scope_id != self.scope.scope_token
            ):
                continue
            member_name = member[1].lower()
            line = _line_number(self.source, receiver[2])
            if (
                member_name == "command"
                and provenance.kind == "cli"
                and re.fullmatch(r"[a-zA-Z0-9_.:-]+", value[1])
            ):
                self.boundaries.append(
                    _Boundary(
                        "cli-command", value[1], line,
                        "js-framework-binding", True, provenance,
                    )
                )
            elif (
                member_name in HTTP_METHODS
                and provenance.kind == "http-server"
                and value[1].startswith("/")
            ):
                self.boundaries.append(
                    _Boundary(
                        "http-route", f"{member_name.upper()} {value[1]}", line,
                        "js-framework-binding", True, provenance,
                    )
                )

    def _top_level_operator(
        self, start: int, end: int, operators: set[str]
    ) -> int | None:
        position = start
        while position < end:
            value = self.tokens[position][1]
            if value in {"(", "[", "{"} and position in self.pairs:
                position = self.pairs[position] + 1
                continue
            if value in operators:
                return position
            position += 1
        return None

    def _arrow_parameters(self, arrow: int, start: int) -> tuple[set[str], int]:
        closing = next(
            (
                position
                for position in range(arrow - 1, start - 1, -1)
                if self.tokens[position][1] == ")"
                and self.reverse_pairs.get(position, start - 1) >= start
            ),
            None,
        )
        if closing is not None:
            opening = self.reverse_pairs.get(closing)
            trailing = self.tokens[closing + 1][1] if closing + 1 < arrow else None
            if opening is not None and (closing + 1 == arrow or trailing == ":"):
                return (
                    _js_parameter_names(
                        self.tokens, opening + 1, closing, self.pairs
                    ),
                    opening,
                )
        if arrow > start and self.tokens[arrow - 1][0] == "identifier":
            return {self.tokens[arrow - 1][1]}, arrow - 1
        return set(), start

    def _analyze_arrow(self, start: int, end: int, arrow: int) -> None:
        parameters, _parameter_start = self._arrow_parameters(arrow, start)
        previous = self.scope
        self.scope = _ScopeIR(
            previous,
            "function",
            {name: _UNKNOWN_BINDING for name in parameters},
            set(parameters),
            write_barrier=True,
        )
        body_start = arrow + 1
        if body_start < end and self.tokens[body_start][1] == "{":
            closing = self.pairs.get(body_start)
            if closing is not None and closing <= end:
                self.scope.local_names.update(
                    self._direct_lexical_names(body_start + 1, closing)
                )
                for name in self._var_names(body_start + 1, closing):
                    self.scope.local_names.add(name)
                    self.scope.values.setdefault(name, _UNKNOWN_BINDING)
                self._analyze_range(body_start + 1, closing)
        else:
            self._analyze_expression(body_start, end)
        self.scope = previous

    def _analyze_expression(
        self, start: int, end: int, allow_boundary_call: bool = False
    ) -> None:
        while start < end and self.tokens[start][1] == "(" and self.pairs.get(start) == end - 1:
            start += 1
            end -= 1
        if start >= end:
            return
        arrow = self._top_level_operator(start, end, {"=>"})
        if arrow is not None:
            self._analyze_arrow(start, end, arrow)
            return
        logical = self._top_level_operator(start, end, {"&&", "||", "??"})
        if logical is not None:
            self._analyze_expression(start, logical)
            skipped = self._snapshot()
            self._analyze_expression(logical + 1, end)
            evaluated = self._snapshot()
            self._restore(skipped)
            self._join_snapshots(skipped, [skipped, evaluated])
            return
        question = self._top_level_operator(start, end, {"?"})
        if question is not None:
            colon = self._top_level_operator(question + 1, end, {":"})
            self._analyze_expression(start, question)
            base = self._snapshot()
            self._restore(base)
            self._analyze_expression(question + 1, colon if colon is not None else end)
            true_outcome = self._snapshot()
            self._restore(base)
            if colon is not None:
                self._analyze_expression(colon + 1, end)
            false_outcome = self._snapshot()
            self._restore(base)
            self._join_snapshots(base, [true_outcome, false_outcome])
            return
        assignment = self._top_level_operator(
            start, end, {"=", "+=", "-=", "*=", "/=", "&&=", "||=", "??="}
        )
        if assignment is not None:
            operator = self.tokens[assignment][1]
            names = _js_pattern_names(self.tokens, start, assignment)
            self._analyze_expression(assignment + 1, end)
            value = (
                _js_value_binding(
                    self.tokens, assignment + 1, end, self._resolve, self.source,
                    self.scope.scope_token,
                )
                if operator == "=" and len(names) == 1
                else None
            )
            for name in names:
                self._assign(name, value)
            return
        self._emit_calls(start, end, allow_boundary_call)

    def _analyze_declaration(self, start: int, end: int) -> int:
        declaration = self.tokens[start][1]
        stop = self._statement_end(start + 1, end)
        assignment = self._top_level_operator(start + 1, stop, {"="})
        pattern_end = assignment if assignment is not None else stop
        names = _js_parameter_names(
            self.tokens, start + 1, pattern_end, self.pairs
        )
        if assignment is None:
            for name in names:
                self._declare(name, None, declaration)
            return stop + (stop < end and self.tokens[stop][1] == ";")
        rhs_start = assignment + 1
        arrow = self._top_level_operator(rhs_start, stop, {"=>"})
        if arrow is not None:
            self._analyze_arrow(rhs_start, stop, arrow)
            for name in names:
                self._declare(name, None, declaration)
            return stop + (stop < end and self.tokens[stop][1] == ";")
        if (
            rhs_start < stop
            and self.tokens[rhs_start][1] == "{"
            and self.pairs.get(rhs_start) == stop - 1
        ):
            previous = self.scope
            self.scope = _ScopeIR(previous, "object", {}, set())
            self._analyze_range(rhs_start + 1, stop - 1)
            self.scope = previous
        else:
            self._analyze_expression(rhs_start, stop)
        if self.tokens[start + 1][1] == "{":
            required = _js_require_binding(self.tokens, rhs_start)
            if required is not None:
                module, _exported, _required_end = required
                site = _source_site(
                    self.source, _line_number(self.source, self.tokens[rhs_start][2])
                )
                opening = start + 1
                closing = self.pairs.get(opening, pattern_end)
                cursor = opening + 1
                while cursor < closing:
                    if self.tokens[cursor][0] != "identifier":
                        cursor += 1
                        continue
                    exported = self.tokens[cursor][1]
                    local = exported
                    if cursor + 2 < closing and self.tokens[cursor + 1][1] == ":":
                        local = self.tokens[cursor + 2][1]
                        cursor += 2
                    self._declare(
                        local, _JSImportBinding(module, exported, site), declaration
                    )
                    cursor += 1
            else:
                for name in names:
                    self._declare(name, None, declaration)
        else:
            value = _js_value_binding(
                self.tokens, rhs_start, stop, self._resolve, self.source,
                self.scope.scope_token,
            )
            for name in names:
                self._declare(name, value if len(names) == 1 else None, declaration)
        return stop + (stop < end and self.tokens[stop][1] == ";")

    def _function_parts(self, start: int, end: int) -> tuple[int, int, int, int] | None:
        opening = next(
            (position for position in range(start, end) if self.tokens[position][1] == "("),
            None,
        )
        if opening is None:
            return None
        closing = self.pairs.get(opening)
        if closing is None:
            return None
        body = closing + 1
        while body < end and self.tokens[body][1] not in {"{", ";"}:
            body += 1
        if body >= end or self.tokens[body][1] != "{" or body not in self.pairs:
            return None
        return opening, closing, body, self.pairs[body]

    def _analyze_function(self, start: int, end: int) -> int:
        parts = self._function_parts(start, end)
        if parts is None:
            return self._statement_end(start, end)
        opening, closing, body, body_end = parts
        if start + 1 < opening and self.tokens[start + 1][0] == "identifier":
            self._declare(self.tokens[start + 1][1], None, "let")
        parameters = _js_parameter_names(
            self.tokens, opening + 1, closing, self.pairs
        )
        previous = self.scope
        is_boundary_scope = (
            previous.kind == "module"
            and not any(self.tokens[position][1] == "*" for position in range(start + 1, opening))
        )
        self.scope = _ScopeIR(
            previous,
            "function",
            {name: _UNKNOWN_BINDING for name in parameters},
            set(parameters),
            boundary_scope=is_boundary_scope,
            write_barrier=True,
        )
        self.scope.local_names.update(self._direct_lexical_names(body + 1, body_end))
        for name in self._var_names(body + 1, body_end):
            self.scope.local_names.add(name)
            self.scope.values.setdefault(name, _UNKNOWN_BINDING)
        self._analyze_range(body + 1, body_end, allow_boundary_statements=is_boundary_scope)
        self.scope = previous
        return body_end + 1

    def _analyze_method(self, start: int, end: int) -> int | None:
        if self.tokens[start][0] != "identifier" or start + 1 >= end:
            return None
        opening = start + 1
        if self.tokens[opening][1] == "<":
            depth = 1
            opening += 1
            while opening < end and depth:
                if self.tokens[opening][1] == "<":
                    depth += 1
                elif self.tokens[opening][1] == ">":
                    depth -= 1
                opening += 1
            if depth or opening >= end:
                return None
        if self.tokens[opening][1] != "(":
            return None
        closing = self.pairs.get(opening)
        if closing is None:
            return None
        body = closing + 1
        while body < end and self.tokens[body][1] not in {"{", ";"}:
            body += 1
        if body >= end or self.tokens[body][1] != "{":
            return None
        body_end = self.pairs.get(body)
        if body_end is None:
            return None
        parameters = _js_parameter_names(
            self.tokens, opening + 1, closing, self.pairs
        )
        previous = self.scope
        parent = previous.parent if previous.kind == "class" else previous
        self.scope = _ScopeIR(
            parent,
            "function",
            {name: _UNKNOWN_BINDING for name in parameters},
            set(parameters),
            write_barrier=True,
        )
        for name in self._var_names(body + 1, body_end):
            self.scope.local_names.add(name)
            self.scope.values.setdefault(name, _UNKNOWN_BINDING)
        self._analyze_range(body + 1, body_end)
        self.scope = previous
        return body_end + 1

    def _analyze_if(self, start: int, end: int) -> int:
        opening = start + 1
        if opening >= end or self.tokens[opening][1] != "(" or opening not in self.pairs:
            return self._statement_end(start, end)
        closing = self.pairs[opening]
        self._analyze_expression(opening + 1, closing)
        base = self._snapshot()
        self._restore(base)
        then_end = self._analyze_statement(closing + 1, end)
        then_outcome = self._snapshot()
        cursor = then_end
        self._restore(base)
        if cursor < end and self.tokens[cursor][1] == "else":
            else_end = self._analyze_statement(cursor + 1, end)
            else_outcome = self._snapshot()
            cursor = else_end
        else:
            else_outcome = base
        self._restore(base)
        self._join_snapshots(base, [then_outcome, else_outcome])
        return cursor

    def _analyze_for(self, start: int, end: int) -> int:
        opening = start + 1
        if opening >= end or self.tokens[opening][1] != "(" or opening not in self.pairs:
            return self._statement_end(start, end)
        closing = self.pairs[opening]
        relation = self._top_level_operator(opening + 1, closing, {"of", "in"})
        if relation is None:
            # Classic for headers are still analyzed for assignments, but their
            # declarations remain loop-local and all outer mutations are joined
            # with the zero-iteration path.
            self._analyze_expression(opening + 1, closing)
            base = self._snapshot()
            previous = self.scope
            self.scope = _ScopeIR(previous, "loop", {}, set())
            body_end = self._analyze_statement(closing + 1, end)
            self.scope = previous
            body_outcome = self._snapshot()
            self._restore(base)
            self._join_snapshots(base, [base, body_outcome])
            return body_end

        declaration_start = opening + 1
        declaration = (
            self.tokens[declaration_start][1]
            if declaration_start < relation
            and self.tokens[declaration_start][1] in {"let", "const", "var"}
            else None
        )
        pattern_start = declaration_start + (declaration is not None)
        names = _js_parameter_names(
            self.tokens, pattern_start, relation, self.pairs
        )
        self._analyze_expression(relation + 1, closing)
        base = self._snapshot()
        previous = self.scope
        if declaration in {"let", "const"}:
            self.scope = _ScopeIR(
                previous,
                "loop",
                {name: _UNKNOWN_BINDING for name in names},
                set(names),
            )
        else:
            for name in names:
                self._assign(name, None)
        body_end = self._analyze_statement(closing + 1, end)
        self.scope = previous
        body_outcome = self._snapshot()
        self._restore(base)
        self._join_snapshots(base, [base, body_outcome])
        return body_end

    def _analyze_while(self, start: int, end: int) -> int:
        opening = start + 1
        if opening >= end or self.tokens[opening][1] != "(" or opening not in self.pairs:
            return self._statement_end(start, end)
        closing = self.pairs[opening]
        self._analyze_expression(opening + 1, closing)
        base = self._snapshot()
        previous = self.scope
        self.scope = _ScopeIR(previous, "loop", {}, set())
        body_end = self._analyze_statement(closing + 1, end)
        self.scope = previous
        body_outcome = self._snapshot()
        self._restore(base)
        self._join_snapshots(base, [base, body_outcome])
        return body_end

    def _analyze_do_while(self, start: int, end: int) -> int:
        body_end = self._analyze_statement(start + 1, end)
        if body_end >= end or self.tokens[body_end][1] != "while":
            return body_end
        opening = body_end + 1
        if opening >= end or self.tokens[opening][1] != "(" or opening not in self.pairs:
            return self._statement_end(body_end, end)
        closing = self.pairs[opening]
        self._analyze_expression(opening + 1, closing)
        cursor = closing + 1
        return cursor + (cursor < end and self.tokens[cursor][1] == ";")

    def _switch_labels(self, start: int, end: int) -> list[tuple[int, int]]:
        labels: list[tuple[int, int]] = []
        position = start
        while position < end:
            value = self.tokens[position][1]
            if value in {"(", "[", "{"} and position in self.pairs:
                position = self.pairs[position] + 1
                continue
            if value not in {"case", "default"}:
                position += 1
                continue
            colon = position + 1
            while colon < end:
                token = self.tokens[colon][1]
                if token in {"(", "[", "{"} and colon in self.pairs:
                    colon = self.pairs[colon] + 1
                    continue
                if token == ":":
                    labels.append((position, colon))
                    position = colon
                    break
                colon += 1
            position += 1
        return labels

    def _analyze_switch(self, start: int, end: int) -> int:
        opening = start + 1
        if opening >= end or self.tokens[opening][1] != "(" or opening not in self.pairs:
            return self._statement_end(start, end)
        closing = self.pairs[opening]
        body = closing + 1
        if body >= end or self.tokens[body][1] != "{" or body not in self.pairs:
            return self._statement_end(start, end)
        body_end = self.pairs[body]
        self._analyze_expression(opening + 1, closing)
        previous = self.scope
        locals_ = self._direct_lexical_names(body + 1, body_end)
        self.scope = _ScopeIR(
            previous,
            "switch",
            {name: _UNKNOWN_BINDING for name in locals_},
            locals_,
        )
        base = self._snapshot()
        outcomes = [base]
        labels = self._switch_labels(body + 1, body_end)
        for index, (label, colon) in enumerate(labels):
            self._restore(base)
            if self.tokens[label][1] == "case":
                self._analyze_expression(label + 1, colon)
            branch_end = labels[index + 1][0] if index + 1 < len(labels) else body_end
            self._analyze_range(colon + 1, branch_end)
            outcomes.append(self._snapshot())
        self._restore(base)
        self._join_snapshots(base, outcomes)
        self.scope = previous
        return body_end + 1

    def _analyze_try(self, start: int, end: int) -> int:
        body = start + 1
        if body >= end or self.tokens[body][1] != "{" or body not in self.pairs:
            return self._statement_end(start, end)
        body_end = self.pairs[body]
        base = self._snapshot()
        self._analyze_range(body + 1, body_end)
        outcomes = [self._snapshot()]
        cursor = body_end + 1
        while cursor < end and self.tokens[cursor][1] == "catch":
            opening = cursor + 1
            if opening >= end or self.tokens[opening][1] != "(" or opening not in self.pairs:
                break
            closing = self.pairs[opening]
            catch_body = closing + 1
            if catch_body >= end or self.tokens[catch_body][1] != "{" or catch_body not in self.pairs:
                break
            catch_end = self.pairs[catch_body]
            self._restore(base)
            previous = self.scope
            names = _js_pattern_names(self.tokens, opening + 1, closing)
            self.scope = _ScopeIR(
                previous,
                "catch",
                {name: _UNKNOWN_BINDING for name in names},
                set(names),
            )
            self._analyze_range(catch_body + 1, catch_end)
            self.scope = previous
            outcomes.append(self._snapshot())
            cursor = catch_end + 1
        self._restore(base)
        self._join_snapshots(base, outcomes)
        if cursor < end and self.tokens[cursor][1] == "finally":
            final_body = cursor + 1
            if final_body < end and self.tokens[final_body][1] == "{" and final_body in self.pairs:
                final_end = self.pairs[final_body]
                self._analyze_range(final_body + 1, final_end)
                cursor = final_end + 1
        return cursor

    def _analyze_class(self, start: int, end: int) -> int:
        if start + 1 < end and self.tokens[start + 1][0] == "identifier":
            self._declare(self.tokens[start + 1][1], None, "let")
        body = next(
            (
                position
                for position in range(start + 1, end)
                if self.tokens[position][1] == "{"
            ),
            None,
        )
        if body is None or body not in self.pairs:
            return self._statement_end(start, end)
        body_end = self.pairs[body]
        previous = self.scope
        self.scope = _ScopeIR(previous, "class", {}, self._direct_lexical_names(body + 1, body_end))
        self._analyze_range(body + 1, body_end)
        self.scope = previous
        return body_end + 1

    def _analyze_statement(
        self, start: int, end: int, allow_boundary_statement: bool = False
    ) -> int:
        while start < end and self.tokens[start][1] == ";":
            start += 1
        if start >= end:
            return end
        value = self.tokens[start][1]
        if value == "{":
            closing = self.pairs.get(start)
            if closing is None:
                return end
            previous = self.scope
            locals_ = self._direct_lexical_names(start + 1, closing)
            self.scope = _ScopeIR(
                previous,
                "block",
                {name: _UNKNOWN_BINDING for name in locals_},
                locals_,
            )
            self._analyze_range(start + 1, closing)
            self.scope = previous
            return closing + 1
        if value == "import":
            stop = self._statement_end(start, end)
            return stop + (stop < end and self.tokens[stop][1] == ";")
        if value == "export":
            cursor = start + 1
            if cursor < end and self.tokens[cursor][1] == "default":
                cursor += 1
            if (
                cursor + 1 < end
                and self.tokens[cursor][1] == "async"
                and self.tokens[cursor + 1][1] == "function"
            ):
                cursor += 1
            if cursor < end and self.tokens[cursor][1] == "function":
                return self._analyze_function(cursor, end)
            if cursor < end and self.tokens[cursor][1] in {"const", "let", "var"}:
                return self._analyze_declaration(cursor, end)
            if cursor < end and self.tokens[cursor][1] == "class":
                return self._analyze_class(cursor, end)
            stop = self._statement_end(start, end)
            return stop + (stop < end and self.tokens[stop][1] == ";")
        if value in {"const", "let", "var"}:
            return self._analyze_declaration(start, end)
        if value == "function":
            return self._analyze_function(start, end)
        if value == "class":
            return self._analyze_class(start, end)
        if value == "if":
            return self._analyze_if(start, end)
        if value == "for":
            return self._analyze_for(start, end)
        if value == "while":
            return self._analyze_while(start, end)
        if value == "do":
            return self._analyze_do_while(start, end)
        if value == "switch":
            return self._analyze_switch(start, end)
        if value == "try":
            return self._analyze_try(start, end)
        method_end = self._analyze_method(start, end)
        if method_end is not None:
            return method_end
        stop = self._statement_end(start, end)
        self._analyze_expression(start, stop, allow_boundary_statement)
        return stop + (stop < end and self.tokens[stop][1] == ";")

    def _analyze_range(
        self, start: int, end: int, allow_boundary_statements: bool = False
    ) -> None:
        position = start
        while position < end:
            next_position = self._analyze_statement(
                position, end, allow_boundary_statement=allow_boundary_statements
            )
            if next_position <= position:
                return
            position = next_position

    def analyze(self) -> list[_Boundary]:
        self.scope.local_names.update(self._direct_lexical_names(0, len(self.tokens)))
        for name in self._var_names(0, len(self.tokens)):
            self.scope.local_names.add(name)
            self.scope.values.setdefault(name, _UNKNOWN_BINDING)
        self._analyze_range(0, len(self.tokens), allow_boundary_statements=True)
        return sorted(
            set(self.boundaries),
            key=lambda item: (item.line, item.kind, item.entrypoint, not item.confirmed),
        )


def _find_node_runtime() -> str | None:
    """Locate Node for non-interactive CLI runs, including NVM login shells."""

    return _find_node_runtime_cached(_node_runtime_signature())


def _node_runtime_signature() -> tuple[str | None, str | None, str | None, str | None]:
    """Return the environment inputs that change Node discovery results."""

    return (
        os.environ.get("REPO_TEACHER_NODE"),
        os.environ.get("NVM_BIN"),
        os.environ.get("SHELL"),
        os.environ.get("PATH"),
    )


@functools.lru_cache(maxsize=32)
def _find_node_runtime_cached(
    signature: tuple[str | None, str | None, str | None, str | None]
) -> str | None:
    """Locate Node for one specific environment signature."""

    del signature
    candidates = [
        os.environ.get("REPO_TEACHER_NODE"),
        str(Path(os.environ["NVM_BIN"]) / "node") if os.environ.get("NVM_BIN") else None,
        shutil.which("node"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())

    shell = os.environ.get("SHELL")
    if not shell:
        return None
    shell_path = Path(shell).expanduser()
    if not shell_path.is_file() or not os.access(shell_path, os.X_OK):
        return None
    try:
        discovered = subprocess.run(
            [str(shell_path), "-ilc", "command -v node"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if discovered.returncode != 0:
        return None
    lines = [line.strip() for line in discovered.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    path = Path(lines[-1]).expanduser()
    if not path.is_file() or not os.access(path, os.X_OK):
        return None
    return str(path.resolve())


_find_node_runtime.cache_clear = _find_node_runtime_cached.cache_clear  # type: ignore[attr-defined]
_find_node_runtime.cache_info = _find_node_runtime_cached.cache_info  # type: ignore[attr-defined]


def _node_check_javascript(source: str, path: str) -> bool:
    """Parse JavaScript without executing it; absence or uncertainty fails closed."""

    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in {".js", ".mjs", ".cjs"}:
        return True
    node = _find_node_runtime()
    if node is None:
        return False
    modes = (
        ("module",)
        if suffix == ".mjs"
        else (("commonjs",) if suffix == ".cjs" else ("commonjs", "module"))
    )
    for mode in modes:
        try:
            checked = subprocess.run(
                [node, "--input-type", mode, "--check", "-"],
                input=source,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                check=False,
                env={},
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if checked.returncode == 0:
            return True
    return False


def _js_boundaries(source: str, path: str) -> list[_Boundary]:
    try:
        boundaries = _JSBoundaryAnalyzer(source).analyze()
    except (IndexError, ValueError):
        # Unsupported or structurally incomplete JS/TS remains unconfirmed.
        return []
    if boundaries and not _node_check_javascript(source, path):
        return []
    return boundaries


def _boundary_entrypoint(operation: str, value: str) -> str | None:
    normalized = operation.lower()
    if normalized in {"command", "add_parser"}:
        return value
    return f"{normalized.upper()} {value}" if normalized in HTTP_METHODS else None


def _site_overlaps(line_start: int, line_end: int, sites: tuple[_SourceSite, ...]) -> bool:
    return any(
        line_start <= site.line_end and site.line_start <= line_end
        for site in sites
    )


def _python_boundary_calls_in_sites(
    source: str, sites: tuple[_SourceSite, ...]
) -> set[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    observed: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        first = node.args[0] if node.args else None
        if not (
            isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and _site_overlaps(
                node.lineno,
                getattr(node, "end_lineno", node.lineno),
                sites,
            )
        ):
            continue
        entrypoint = _boundary_entrypoint(node.func.attr, first.value)
        if entrypoint is not None:
            observed.add(entrypoint)
    return observed


def _js_boundary_calls_in_sites(
    source: str, sites: tuple[_SourceSite, ...]
) -> set[str]:
    try:
        tokens = _js_tokens(source)
        pairs, _reverse = _js_pairs(tokens)
    except ValueError:
        return set()
    observed: set[str] = set()
    for position in range(max(0, len(tokens) - 4)):
        receiver, dot, member, opening, first = tokens[position : position + 5]
        if (
            receiver[0] != "identifier"
            or dot[1] != "."
            or member[0] != "identifier"
            or opening[1] != "("
            or first[0] != "string"
            or position + 3 not in pairs
        ):
            continue
        call_end = pairs[position + 3]
        line_start = _line_number(source, receiver[2])
        line_end = _line_number(source, tokens[call_end][2])
        if not _site_overlaps(line_start, line_end, sites):
            continue
        entrypoint = _boundary_entrypoint(member[1], first[1])
        if entrypoint is not None:
            observed.add(entrypoint)
    return observed


def _framework_evidence_is_boundary_exclusive(
    source: str, boundary: _Boundary
) -> bool:
    """Keep a line-addressed proof only when its structured calls agree."""

    provenance = boundary.provenance
    if provenance is None:
        return True
    sites = (
        provenance.import_site,
        provenance.factory_site,
        _source_site(source, boundary.line),
    )
    observed = (
        _python_boundary_calls_in_sites(source, sites)
        if boundary.analyzer == "python-ast-call"
        else _js_boundary_calls_in_sites(source, sites)
    )
    return not observed or observed == {boundary.entrypoint}


def _symbol_for_line(symbols: list[SymbolRecord], path: str, line: int) -> SymbolRecord | None:
    containing = [symbol for symbol in symbols if symbol.path == path and symbol.line <= line <= symbol.end_line]
    return max(containing, key=lambda item: item.line) if containing else None


def _is_product_source(file: FileRecord) -> bool:
    path = PurePosixPath(file.path)
    lowered_parts = {part.lower() for part in path.parts[:-1]}
    name = path.name.lower()
    return (
        file.language in PRODUCT_LANGUAGES
        and not lowered_parts.intersection(NON_PRODUCT_PARTS)
        and not name.startswith(("test_", "spec_"))
        and not any(marker in name for marker in (".test.", ".spec.", "_test.go"))
    )


def _is_test_source(path: str) -> bool:
    parsed = PurePosixPath(path)
    parts = {part.lower() for part in parsed.parts[:-1]}
    name = parsed.name.lower()
    return bool(
        parts.intersection({"test", "tests", "testing", "eval", "evals"})
        or name.startswith(("test_", "spec_"))
        or any(marker in name for marker in (".test.", ".spec.", "_test.go"))
    )


def _file_entry_declaration(file: FileRecord, source: str) -> int | None:
    """Return a source line only for an explicit executable-file boundary.

    A conventional filename by itself is not enough: for example, a library may
    contain ``server.py`` helpers without executing them.  These markers are
    intentionally narrow and describe a declaration, not a proven runtime path.
    """

    if PurePosixPath(file.path).name.lower() not in ENTRYPOINT_FILES:
        return None
    lines = source.splitlines()
    if lines and lines[0].startswith("#!"):
        return 1
    if file.language == "Python":
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return None
        for statement in tree.body:
            if isinstance(statement, ast.If):
                test = statement.test
                if (
                    isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"
                    and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.Eq)
                    and len(test.comparators) == 1
                    and isinstance(test.comparators[0], ast.Constant)
                    and test.comparators[0].value == "__main__"
                ):
                    return statement.lineno
            call = statement.value if isinstance(statement, ast.Expr) else None
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "run"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "uvicorn"
            ):
                return statement.lineno
        return None
    elif file.language in {"JavaScript", "TypeScript"}:
        try:
            tokens = _js_tokens(source)
        except ValueError:
            return None
        for position in range(len(tokens) - 3):
            receiver, dot, member, opening = tokens[position:position + 4]
            if (
                receiver[0] == "identifier"
                and receiver[1] in {"app", "server"}
                and dot[1] == "."
                and member[1] == "listen"
                and opening[1] == "("
            ):
                return _line_number(source, receiver[2])
        return None
    elif file.language == "Go":
        if not re.search(r"(?m)^\s*package\s+main\b", source):
            return None
        patterns: tuple[re.Pattern[str], ...] = (re.compile(r"^\s*func\s+main\s*\("),)
    else:
        patterns = ()
    for line_number, line in enumerate(lines, start=1):
        if any(pattern.search(line) for pattern in patterns):
            return line_number
    return None


def _command_symbol(symbols: list[SymbolRecord], command: str, path: str, line: int) -> SymbolRecord | None:
    normalized = command.replace("-", "_").lower()
    named = [
        symbol
        for symbol in symbols
        if symbol.path == path and symbol.name.lower().lstrip("_") in {normalized, f"{normalized}_command"}
    ]
    if named:
        return min(named, key=lambda item: (item.line, item.name))
    return _symbol_for_line(symbols, path, line)


def _step_for_symbol(
    symbol: SymbolRecord,
    order: int,
    evidence: EvidenceStore,
    *,
    relationship_id: str | None = None,
    relationship_endpoint: str = "target",
    exact_definition_line: bool = False,
) -> FeatureStep:
    line_end = symbol.line if exact_definition_line else min(symbol.end_line, symbol.line + 12)
    reference = evidence.add(
        symbol.path,
        symbol.line,
        line_end,
        kind="symbol-definition",
        confidence=symbol.confidence,
        analyzer=symbol.analyzer,
        symbol_id=symbol.id,
    )
    if relationship_id:
        if relationship_endpoint == "source":
            title = f"已解析调用端点：{symbol.qualified_name}"
            explanation = (
                f"静态分析将 {symbol.kind} `{symbol.qualified_name}` 识别为直接调用边的源端；"
                "这证明源码引用关系，不代表它在每次运行时都会执行。"
            )
        else:
            title = f"已解析调用目标：{symbol.qualified_name}"
            explanation = (
                f"静态分析把一个调用边解析到 {symbol.kind} `{symbol.qualified_name}`；"
                "这证明源码引用关系，不代表它在每次运行时都会执行。"
            )
    else:
        title = f"候选处理符号：{symbol.qualified_name}"
        explanation = (
            f"入口声明通过名称或源码位置关联到 {symbol.kind} `{symbol.qualified_name}`；"
            "这是继续阅读的起点，不等于已证明的运行时分发。"
        )
    return FeatureStep(
        order=order,
        title=title,
        explanation=explanation,
        path=symbol.path,
        line_start=symbol.line,
        line_end=line_end,
        evidence_ids=[reference.id],
        symbol_id=symbol.id,
        relationship_id=relationship_id,
    )


def _direct_symbol_path(
    start: SymbolRecord | None,
    symbols_by_id: dict[str, SymbolRecord],
    relationships: list[RelationshipRecord],
    evidence: EvidenceStore,
    *,
    limit: int = 8,
    exact_definition_lines: bool = False,
) -> list[FeatureStep]:
    if start is None:
        return []
    direct_calls = sorted(
        (
            relationship
            for relationship in relationships
            if relationship.kind == "calls"
            and relationship.source_id == start.id
            and relationship.target_id in symbols_by_id
        ),
        key=lambda item: (item.line, item.target_name, item.id),
    )
    steps = [
        _step_for_symbol(
            start,
            1,
            evidence,
            relationship_id=direct_calls[0].id if direct_calls else None,
            relationship_endpoint="source",
            exact_definition_line=exact_definition_lines,
        )
    ]
    seen = {start.id}
    for relationship in direct_calls:
        target = symbols_by_id.get(relationship.target_id or "")
        if target is None or target.id in seen:
            continue
        seen.add(target.id)
        steps.append(
            _step_for_symbol(
                target,
                len(steps) + 1,
                evidence,
                relationship_id=relationship.id,
                exact_definition_line=exact_definition_lines,
            )
        )
        if len(steps) >= limit:
            break
    return steps


def _test_evidence(
    start_symbol: SymbolRecord | None,
    files: list[FileRecord],
    symbols_by_id: dict[str, SymbolRecord],
    relationships: list[RelationshipRecord],
    contents: dict[str, str],
    evidence: EvidenceStore,
) -> list[str]:
    if start_symbol is None:
        return []
    identifiers: list[str] = []
    file_paths = {file.path for file in files}
    for relationship in relationships:
        if relationship.target_id != start_symbol.id:
            continue
        source_symbol = symbols_by_id.get(relationship.source_id)
        path = relationship.path
        if source_symbol is not None:
            path = source_symbol.path
        if (
            path not in file_paths
            or not _is_test_source(path)
            or relationship.kind not in {"calls", "references"}
        ):
            continue
        source = contents.get(path, "")
        line = relationship.line
        end = min(len(source.splitlines()), line + 6)
        if end >= line:
            identifiers.append(
                evidence.add(
                    path,
                    line,
                    end,
                    kind="test-reference",
                    confidence=relationship.confidence,
                    analyzer=relationship.analyzer,
                    symbol_id=source_symbol.id if source_symbol else None,
                ).id
            )
        if len(identifiers) >= 4:
            break
    return identifiers


def _build_feature(
    *,
    title: str,
    kind: str,
    entrypoint: str,
    path: str,
    line: int,
    start_symbol: SymbolRecord | None,
    files: list[FileRecord],
    symbols_by_id: dict[str, SymbolRecord],
    relationships: list[RelationshipRecord],
    modules_by_name: dict[str, ModuleSummary],
    contents: dict[str, str],
    evidence: EvidenceStore,
    boundary_confidence: str = "heuristic",
    boundary_analyzer: str = "source-pattern",
    boundary_confirmed: bool = True,
    boundary_provenance: _FrameworkBinding | None = None,
) -> FeatureRecord:
    line_count = len(contents[path].splitlines())
    entry_reference = evidence.add(
        path,
        line,
        line if boundary_provenance is not None else min(line_count, line + 5),
        kind="entry-declaration" if boundary_confirmed else "entry-candidate",
        confidence=boundary_confidence,
        analyzer=boundary_analyzer,
    )
    if boundary_provenance is not None:
        steps = _direct_symbol_path(
            start_symbol,
            symbols_by_id,
            relationships,
            evidence,
            exact_definition_lines=True,
        )
        if not steps:
            steps = [
                FeatureStep(
                    order=1,
                    title=f"保守确认调用点：{entrypoint}",
                    explanation=(
                        "该切片只证明框架实例在同一可证明作用域内被直接调用；"
                        "不证明部署可达性、动态分派或真实运行顺序。"
                    ),
                    path=path,
                    line_start=line,
                    line_end=line,
                    evidence_ids=[entry_reference.id],
                )
            ]
    else:
        steps = _direct_symbol_path(start_symbol, symbols_by_id, relationships, evidence)
    evidence_ids = [entry_reference.id]
    for step in steps:
        evidence_ids.extend(step.evidence_ids)
    test_ids = _test_evidence(start_symbol, files, symbols_by_id, relationships, contents, evidence)
    module_name = PurePosixPath(path).parts[0] if "/" in path else "root"
    component = modules_by_name.get(module_name)
    language = next((file.language for file in files if file.path == path), "Unknown")
    resolved_calls = sum(1 for step in steps if step.relationship_id)
    confidence = (
        "exact-entry"
        if boundary_confirmed and boundary_confidence == "exact"
        else ("static-entry" if boundary_confirmed else "candidate")
    )
    static_path_summary = (
        f"并找到 {resolved_calls} 条已解析静态调用边"
        if resolved_calls
        else "；下游调用尚未解析"
    )
    boundary_summary = (
        f"在 `{path}:{line}` 找到满足保守同作用域合同的静态框架调用声明；实际可达性未知"
        if boundary_confirmed and boundary_provenance is not None
        else (
            f"在 `{path}:{line}` 找到已确认的静态入口声明；实际可达性未知"
            if boundary_confirmed
            else f"在 `{path}:{line}` 精确解析到同名符号，但没有确认它是运行入口"
        )
    )
    framework_references = []
    if boundary_confirmed and boundary_provenance is not None:
        call_site = _source_site(contents[path], line)
        provenance_sites = (
            ("import", boundary_provenance.import_site),
            ("factory", boundary_provenance.factory_site),
            ("call", call_site),
        )
        for stage, site in provenance_sites:
            reference = evidence.add(
                path,
                site.line_start,
                site.line_end,
                kind="technology-claim:framework",
                confidence=boundary_confidence,
                analyzer=f"{boundary_analyzer}:{stage}",
                symbol_id=start_symbol.id if start_symbol else None,
            )
            if reference.snippet_sha256 != site.snippet_sha256:
                framework_references = []
                break
            framework_references.append(reference)
        if len(framework_references) == 3:
            evidence_ids.extend(reference.id for reference in framework_references)
        else:
            framework_references = []
    supplied_technology = {
        "parser": f"parser:{boundary_analyzer}",
        "framework": (
            f"framework:{boundary_provenance.framework}"
            if framework_references and boundary_provenance is not None
            else "framework:unknown"
        ),
        "store": "store:unknown",
        "retrieval": "retrieval:unknown",
        "llm": "llm:unknown",
        "incremental": "incremental:unknown",
        "evidence": f"evidence:{'entry-declaration' if boundary_confirmed else 'symbol-candidate'}",
        "ui": "ui:unknown",
    }
    technology_claims = []
    for dimension in TECHNOLOGY_DIMENSIONS:
        tag = supplied_technology[dimension]
        value = tag.split(":", 1)[1]
        grounded = dimension in {"parser", "evidence"} or (
            dimension == "framework" and bool(framework_references)
        )
        claim_evidence_ids = (
            [reference.id for reference in framework_references]
            if dimension == "framework" and framework_references
            else ([entry_reference.id] if grounded else [])
        )
        technology_claims.append(
            TechnologyClaim(
                dimension=dimension,
                value=value,
                claim_scope=(
                    f"仅声明 `{path}:{line}` 的静态边界由 {boundary_analyzer} 识别。"
                    if dimension == "parser"
                    else (
                        f"仅声明该功能拥有 `{path}:{line}` 的入口证据。"
                        if dimension == "evidence"
                        else (
                            f"仅声明调用点 receiver 由 module `{boundary_provenance.module}` "
                            f"的 factory `{boundary_provenance.factory}` 构造；不外推部署或运行时行为。"
                            if dimension == "framework" and boundary_provenance is not None
                            else "当前源码证据没有证明这一技术维度。"
                        )
                    )
                ),
                confidence=boundary_confidence if grounded else "unknown",
                evidence_ids=claim_evidence_ids,
                source_path=path if grounded else None,
            )
        )
    return FeatureRecord(
        id=stable_id("feature", kind, entrypoint, path, line),
        title=title,
        kind=kind,
        summary=(
            f"{boundary_summary}，关联 {len(steps)} 个源码符号{static_path_summary}。"
            "这些是静态阅读证据，不是运行时执行顺序。"
        ),
        entrypoint=entrypoint,
        confidence=confidence,
        source="evidence-bounded-static-feature-discovery",
        steps=steps,
        component_ids=[component.id] if component else [],
        evidence_ids=list(dict.fromkeys(evidence_ids)),
        test_evidence_ids=test_ids,
        technology_tags=[
            language,
            kind,
            *[supplied_technology[dimension] for dimension in TECHNOLOGY_DIMENSIONS],
            "calls:resolved" if resolved_calls else "calls:unknown",
        ],
        technology_claims=technology_claims,
        entry_symbol_id=start_symbol.id if start_symbol else None,
    )


_WAKU_COMPATIBILITY_ANCHORS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "loop",
        "Agent Loop：推理、工具调用与终止条件",
        "围绕一次 Agent 任务组织 reason → act → observe 循环，并用自然结束与最大迭代数限制停止；这是源码阅读候选，真实模型与工具行为仍需运行验证。",
        "waku/loop/agent.py",
        "run_loop",
    ),
    (
        "memory",
        "Memory：长期记忆与周期整理",
        "围绕对话批次整理长期事实与情景记录，并把是否执行 consolidation 作为显式条件；这是记忆整理候选，不代表整套记忆行为已经验证。",
        "waku/memory/consolidation.py",
        "consolidate_if_due",
    ),
    (
        "graph",
        "Graph Workflow：节点、并行波次与显式路由",
        "围绕共享状态、节点、边与路由器组织多步骤工作流，并为循环和总步数设置保护；这是图执行候选，调度语义仍需运行验证。",
        "waku/graph/engine.py",
        "run_graph",
    ),
    (
        "gateway",
        "Multi-channel Gateway：通道生命周期协调",
        "围绕后台 gateway 的启动、停止、配置指纹与健康状态做生命周期协调，可作为多通道接入层的阅读起点；具体通道可用性仍需实机验证。",
        "waku/gateway/supervisor.py",
        "GatewaySupervisor.reconcile",
    ),
    (
        "voice",
        "Voice：本地录音、语音识别与朗读输出",
        "围绕本地麦克风采集、Whisper 转写、唤醒/按键说话和 TTS 朗读组织语音 gateway；这是端到端语音候选，延迟与设备兼容性仍需实机验证。",
        "waku/gateway/voice.py",
        "main",
    ),
    (
        "tools",
        "Tools / MCP：工具注册、调用与错误隔离",
        "围绕统一 schema 注册工具，把模型发出的工具调用分派到 Python 函数，并把异常转换成可观察结果；MCP 与具体工具集合仍需按配置核验。",
        "waku/tools/registry.py",
        "ToolRegistry",
    ),
    (
        "providers",
        "Model Providers：多模型统一适配",
        "围绕统一消息形态选择模型客户端，并为 Anthropic 与 OpenAI 兼容接口提供薄适配；供应商覆盖与工具调用兼容性仍需逐个验证。",
        "waku/loop/models.py",
        "get_client",
    ),
    (
        "dashboard",
        "Dashboard / Observability：本地交互与运行观测",
        "围绕本地 Web 服务汇集聊天、会话、工具、图、记忆、数据与运行事件视图；这是可观测界面候选，不等于所有面板数据都已做行为审计。",
        "waku/ops/dashboard.py",
        "main",
    ),
    (
        "eval",
        "Eval / Release Gate：评测与发布门",
        "围绕确定性评测和模型裁判结果生成发布判定，失败时阻止发布；阈值、测试集代表性与 CI 集成仍需单独核验。",
        "waku/ops/release_gate.py",
        "main",
    ),
)


def _is_waku_compatibility_snapshot(snapshot: ProjectSnapshot | None) -> bool:
    if snapshot is None or not snapshot.is_git or not snapshot.remote:
        return False
    remote = snapshot.remote.lower().rstrip("/").removesuffix(".git")
    return remote.endswith("github.com/shenseanchen/waku-agent")


def _discover_waku_compatibility_features(
    files: list[FileRecord],
    symbols: list[SymbolRecord],
    relationships: list[RelationshipRecord],
    modules: list[ModuleSummary],
    contents: dict[str, str],
    evidence: EvidenceStore,
    snapshot: ProjectSnapshot | None,
) -> list[FeatureRecord]:
    """Teach Waku capability areas as explicit unconfirmed compatibility candidates."""

    if not _is_waku_compatibility_snapshot(snapshot):
        return []
    symbols_by_id = {symbol.id: symbol for symbol in symbols}
    modules_by_name = {module.name: module for module in modules}
    compatibility: list[FeatureRecord] = []
    for mechanism, title, description, path, qualified_name in _WAKU_COMPATIBILITY_ANCHORS:
        start = next(
            (
                symbol
                for symbol in symbols
                if symbol.path == path
                and symbol.qualified_name == qualified_name
            ),
            None,
        )
        source = contents.get(path)
        if start is None or source is None:
            continue
        feature = _build_feature(
            title=f"入口候选：{path} · {qualified_name}",
            kind="entrypoint-candidate",
            entrypoint=qualified_name,
            path=path,
            line=start.line,
            start_symbol=start,
            files=files,
            symbols_by_id=symbols_by_id,
            relationships=relationships,
            modules_by_name=modules_by_name,
            contents=contents,
            evidence=evidence,
            boundary_confidence=start.confidence,
            boundary_analyzer=start.analyzer,
            boundary_confirmed=False,
        )
        feature.technology_tags.append("compatibility-corpus:waku-not-curated")
        feature.technology_tags.append(f"compatibility-mechanism:{mechanism}")
        compatibility.append(feature)
    return compatibility


def discover_features(
    files: list[FileRecord],
    symbols: list[SymbolRecord],
    relationships: list[RelationshipRecord],
    modules: list[ModuleSummary],
    contents: dict[str, str],
    evidence: EvidenceStore,
    *,
    project_snapshot: ProjectSnapshot | None = None,
) -> list[FeatureRecord]:
    symbols_by_id = {symbol.id: symbol for symbol in symbols}
    modules_by_name = {module.name: module for module in modules}
    files_by_path = {file.path: file for file in files}
    features: list[FeatureRecord] = []
    seen: set[tuple[str, str]] = set()

    product_files = [file for file in files if _is_product_source(file)]
    for file in product_files:
        source = contents.get(file.path, "")
        if file.language == "Python":
            boundaries = _python_boundaries(source)
        elif file.language in {"JavaScript", "TypeScript"}:
            boundaries = _js_boundaries(source, file.path)
        else:
            boundaries = []
        for boundary in boundaries:
            if not _framework_evidence_is_boundary_exclusive(source, boundary):
                continue
            boundary_kind = boundary.kind
            entrypoint = boundary.entrypoint
            line = boundary.line
            boundary_analyzer = boundary.analyzer
            key = (boundary_kind, f"{file.path}:{entrypoint}")
            if key in seen:
                continue
            seen.add(key)
            if boundary_kind == "cli-command":
                start = _command_symbol(symbols, entrypoint, file.path, line)
                title = f"CLI 命令：{entrypoint}"
            else:
                start = _symbol_for_line(symbols, file.path, line)
                title = f"HTTP 接口：{entrypoint}"
            features.append(
                _build_feature(
                    title=title, kind=boundary_kind, entrypoint=entrypoint, path=file.path, line=line,
                    start_symbol=start, files=files, symbols_by_id=symbols_by_id, relationships=relationships,
                    modules_by_name=modules_by_name, contents=contents, evidence=evidence,
                    boundary_confidence=(
                        "exact"
                        if boundary.confirmed and boundary_analyzer == "python-ast-call"
                        else "heuristic"
                    ),
                    boundary_analyzer=boundary_analyzer,
                    boundary_confirmed=boundary.confirmed,
                    boundary_provenance=boundary.provenance,
                )
            )

    product_paths = {file.path for file in product_files}
    conventional_symbols = [
        symbol
        for symbol in symbols
        if symbol.path in product_paths
        and PurePosixPath(symbol.path).name.lower() in ENTRYPOINT_FILES
        and symbol.parent_id is None
        and symbol.kind in {"function", "method"}
        and symbol.name.lower() in ENTRYPOINT_SYMBOLS
    ]
    entry_symbols = [
        symbol for symbol in conventional_symbols
        if _file_entry_declaration(files_by_path[symbol.path], contents.get(symbol.path, "")) is not None
    ]
    existing_entry_symbols = {feature.entry_symbol_id for feature in features if feature.entry_symbol_id}
    for symbol in entry_symbols[:16]:
        if symbol.id in existing_entry_symbols:
            continue
        key = ("entrypoint", f"{symbol.path}:{symbol.qualified_name}")
        if key in seen:
            continue
        seen.add(key)
        features.append(
            _build_feature(
                title=f"程序入口：{symbol.path} · {symbol.qualified_name}", kind="entrypoint", entrypoint=symbol.qualified_name,
                path=symbol.path,
                line=_file_entry_declaration(files_by_path[symbol.path], contents.get(symbol.path, "")) or symbol.line,
                start_symbol=symbol, files=files, symbols_by_id=symbols_by_id,
                relationships=relationships, modules_by_name=modules_by_name, contents=contents, evidence=evidence,
                boundary_confidence="exact",
                boundary_analyzer=f"{symbol.analyzer}+executable-marker",
            )
        )

    # A conventional name proves only that the symbol exists.  Keep it as a
    # separate candidate and never upgrade it to an entry declaration.
    for symbol in conventional_symbols:
        if symbol in entry_symbols or symbol.id in existing_entry_symbols:
            continue
        key = ("entrypoint-candidate", f"{symbol.path}:{symbol.qualified_name}")
        if key in seen:
            continue
        seen.add(key)
        features.append(
            _build_feature(
                title=f"入口候选：{symbol.path} · {symbol.qualified_name}",
                kind="entrypoint-candidate",
                entrypoint=symbol.qualified_name,
                path=symbol.path,
                line=symbol.line,
                start_symbol=symbol,
                files=files,
                symbols_by_id=symbols_by_id,
                relationships=relationships,
                modules_by_name=modules_by_name,
                contents=contents,
                evidence=evidence,
                boundary_confidence=symbol.confidence,
                boundary_analyzer=symbol.analyzer,
                boundary_confirmed=False,
            )
        )

    represented_paths = {
        step.path
        for feature in features
        for step in feature.steps[:1]
        if step.path
    }
    entry_symbol_by_path = {symbol.path: symbol for symbol in entry_symbols}
    for file in product_files:
        if file.path in represented_paths:
            continue
        source = contents.get(file.path, "")
        declaration_line = _file_entry_declaration(file, source)
        if declaration_line is None:
            continue
        key = ("entrypoint", file.path)
        if key in seen:
            continue
        seen.add(key)
        start = entry_symbol_by_path.get(file.path)
        if file.language == "Go" and start is None:
            continue
        features.append(
            _build_feature(
                title=f"程序入口文件：{file.path}",
                kind="entrypoint",
                entrypoint=file.path,
                path=file.path,
                line=declaration_line,
                start_symbol=start,
                files=files,
                symbols_by_id=symbols_by_id,
                relationships=relationships,
                modules_by_name=modules_by_name,
                contents=contents,
                evidence=evidence,
                boundary_confidence="exact",
                boundary_analyzer="executable-file-marker",
            )
        )

    features.extend(
        discover_source_audited_capabilities(
            files,
            symbols,
            relationships,
            modules,
            contents,
            evidence,
            project_snapshot=project_snapshot,
        )
    )
    features.extend(
        _discover_waku_compatibility_features(
            files,
            symbols,
            relationships,
            modules,
            contents,
            evidence,
            project_snapshot,
        )
    )
    return sorted(features, key=lambda item: (item.kind, item.entrypoint, item.id))
