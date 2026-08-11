from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from ..models import DiagnosticRecord, FileRecord, RelationshipRecord, SymbolRecord, stable_id
from .base import AnalysisResult


_GO_KEYWORDS = frozenset(
    {
        "break",
        "case",
        "chan",
        "const",
        "continue",
        "default",
        "defer",
        "else",
        "fallthrough",
        "for",
        "func",
        "go",
        "goto",
        "if",
        "import",
        "interface",
        "map",
        "package",
        "range",
        "return",
        "select",
        "struct",
        "switch",
        "type",
        "var",
    }
)

_GO_BUILTINS = frozenset(
    {
        "append",
        "cap",
        "clear",
        "close",
        "complex",
        "copy",
        "delete",
        "imag",
        "len",
        "make",
        "max",
        "min",
        "new",
        "panic",
        "print",
        "println",
        "real",
        "recover",
    }
)

_GO_PREDECLARED_TYPES = frozenset(
    {
        "any",
        "bool",
        "byte",
        "comparable",
        "complex64",
        "complex128",
        "error",
        "float32",
        "float64",
        "int",
        "int8",
        "int16",
        "int32",
        "int64",
        "rune",
        "string",
        "uint",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "uintptr",
    }
)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    start: int
    end: int
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class _FunctionDecl:
    symbol: SymbolRecord
    body_start: int | None
    body_end: int | None
    receiver_start: int | None = None
    receiver_end: int | None = None
    parameters_start: int | None = None
    parameters_end: int | None = None
    results_start: int | None = None
    results_end: int | None = None


@dataclass(frozen=True, slots=True)
class _LocalBinding:
    name: str
    start: int
    end: int
    type_name: str | None = None


@dataclass(frozen=True, slots=True)
class GoResolutionStats:
    calls_resolved: int = 0
    calls_unresolved: int = 0
    imports_resolved: int = 0
    imports_unresolved: int = 0
    receiver_types_linked: int = 0


_ANALYZER = "go-lexer-fallback"
_CALLABLE_KINDS = frozenset({"function", "method", "interface-method"})


def _analyzer_for(package: str) -> str:
    return f"{_ANALYZER}[package={package}]"


def _symbol_package(symbol: SymbolRecord) -> str:
    match = re.search(r"\[package=([^\]]+)\]$", symbol.analyzer)
    return match.group(1) if match else "unknown"


def _column(source: str, offset: int) -> int:
    """Return a one-based byte-independent source column."""

    return offset - source.rfind("\n", 0, offset)


def _symbol_id(
    file: FileRecord,
    package: str,
    kind: str,
    qualified_name: str,
    signature: str,
) -> str:
    """Build a declaration identity that survives unrelated line movement.

    Go disallows overloads, but the normalized signature is retained as a
    deterministic disambiguator for malformed/incomplete source and interface
    contracts.  The semantic key intentionally contains no source position.
    """

    return stable_id(
        "symbol",
        file.path,
        package,
        qualified_name,
        kind,
        _compact(signature),
    )


def _tokenize(source: str, path: str) -> tuple[list[_Token], list[DiagnosticRecord]]:
    """Tokenize the small Go subset needed by the conservative analyzer.

    Comments are discarded and literal contents stay opaque. Offsets and line
    numbers still refer to the original source, so declaration ranges remain
    suitable for evidence links.
    """

    tokens: list[_Token] = []
    diagnostics: list[DiagnosticRecord] = []
    index = 0
    line = 1
    length = len(source)

    while index < length:
        character = source[index]
        if character.isspace():
            if character == "\n":
                line += 1
            index += 1
            continue

        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            if newline < 0:
                break
            index = newline
            continue

        if source.startswith("/*", index):
            start_line = line
            closing = source.find("*/", index + 2)
            if closing < 0:
                diagnostics.append(
                    DiagnosticRecord(
                        path=path,
                        severity="warning",
                        code="go-unterminated-comment",
                        message="unterminated block comment",
                        line=start_line,
                    )
                )
                break
            line += source.count("\n", index, closing + 2)
            index = closing + 2
            continue

        if character in {'"', "'", "`"}:
            quote = character
            start = index
            start_line = line
            index += 1
            escaped = False
            terminated = False
            while index < length:
                current = source[index]
                if current == "\n":
                    line += 1
                if quote != "`" and escaped:
                    escaped = False
                    index += 1
                    continue
                if quote != "`" and current == "\\":
                    escaped = True
                    index += 1
                    continue
                index += 1
                if current == quote:
                    terminated = True
                    break
            tokens.append(
                _Token(
                    "string",
                    source[start:index],
                    start,
                    index,
                    start_line,
                    _column(source, start),
                )
            )
            if not terminated:
                diagnostics.append(
                    DiagnosticRecord(
                        path=path,
                        severity="warning",
                        code="go-unterminated-literal",
                        message="unterminated string, rune, or raw string literal",
                        line=start_line,
                    )
                )
                break
            continue

        if character == "_" or character.isalpha():
            start = index
            index += 1
            while index < length and (source[index] == "_" or source[index].isalnum()):
                index += 1
            tokens.append(
                _Token(
                    "identifier",
                    source[start:index],
                    start,
                    index,
                    line,
                    _column(source, start),
                )
            )
            continue

        tokens.append(
            _Token(
                "punctuation",
                character,
                index,
                index + 1,
                line,
                _column(source, index),
            )
        )
        index += 1

    return tokens, diagnostics


def _depths(tokens: list[_Token]) -> tuple[list[int], list[int], list[int]]:
    curly_depth = 0
    paren_depth = 0
    bracket_depth = 0
    curlies: list[int] = []
    parens: list[int] = []
    brackets: list[int] = []
    for token in tokens:
        curlies.append(curly_depth)
        parens.append(paren_depth)
        brackets.append(bracket_depth)
        if token.value == "{":
            curly_depth += 1
        elif token.value == "}":
            curly_depth = max(0, curly_depth - 1)
        elif token.value == "(":
            paren_depth += 1
        elif token.value == ")":
            paren_depth = max(0, paren_depth - 1)
        elif token.value == "[":
            bracket_depth += 1
        elif token.value == "]":
            bracket_depth = max(0, bracket_depth - 1)
    return curlies, parens, brackets


def _delimiter_diagnostics(tokens: list[_Token], path: str) -> list[DiagnosticRecord]:
    pairs = {"(": ")", "[": "]", "{": "}"}
    closers = {value: key for key, value in pairs.items()}
    stack: list[_Token] = []
    diagnostics: list[DiagnosticRecord] = []
    for token in tokens:
        if token.value in pairs:
            stack.append(token)
            continue
        opener = closers.get(token.value)
        if opener is None:
            continue
        if not stack or stack[-1].value != opener:
            diagnostics.append(
                DiagnosticRecord(
                    path=path,
                    severity="warning",
                    code="go-mismatched-delimiter",
                    message=f"unexpected closing delimiter {token.value!r}",
                    line=token.line,
                )
            )
            continue
        stack.pop()
    diagnostics.extend(
        DiagnosticRecord(
            path=path,
            severity="warning",
            code="go-unclosed-delimiter",
            message=f"unclosed delimiter {token.value!r}",
            line=token.line,
        )
        for token in stack
    )
    return diagnostics


def _package_name(tokens: list[_Token], path: str) -> tuple[str, list[DiagnosticRecord]]:
    for index, token in enumerate(tokens[:-1]):
        if token.value == "package" and tokens[index + 1].kind == "identifier":
            return tokens[index + 1].value, []
    return (
        "unknown",
        [
            DiagnosticRecord(
                path=path,
                severity="warning",
                code="go-missing-package",
                message="Go source has no parseable package clause; semantic links are disabled",
                line=1,
            )
        ],
    )


def _matching(
    tokens: list[_Token],
    start: int,
    opener: str,
    closer: str,
    *,
    limit: int | None = None,
) -> int | None:
    if start >= len(tokens) or tokens[start].value != opener:
        return None
    depth = 0
    stop = len(tokens) if limit is None else min(limit, len(tokens))
    for index in range(start, stop):
        if tokens[index].value == opener:
            depth += 1
        elif tokens[index].value == closer:
            depth -= 1
            if depth == 0:
                return index
    return None


def _compact(fragment: str) -> str:
    return re.sub(r"\s+", " ", fragment).strip()


def _exported(name: str) -> bool:
    return bool(name and name[0].isupper())


def _relationship(
    file: FileRecord,
    kind: str,
    source_id: str,
    target_name: str,
    line: int,
    *,
    column: int = 1,
    ordinal: int = 0,
    target_id: str | None = None,
    confidence: str = "syntax-exact",
    receiver_type_hint: str | None = None,
) -> RelationshipRecord:
    return RelationshipRecord(
        id=stable_id(
            "rel",
            kind,
            source_id,
            target_id or target_name,
            file.path,
            line,
            column,
            ordinal,
        ),
        source_id=source_id,
        target_id=target_id,
        target_name=target_name,
        kind=kind,
        path=file.path,
        line=line,
        analyzer=_ANALYZER,
        confidence=confidence,
        receiver_type_hint=receiver_type_hint,
    )


def _type_spec(
    file: FileRecord,
    source: str,
    tokens: list[_Token],
    start: int,
    limit: int,
    *,
    package: str,
    type_keyword: int,
    grouped: bool = False,
) -> tuple[SymbolRecord | None, int]:
    if start >= limit or tokens[start].kind != "identifier" or tokens[start].value in _GO_KEYWORDS:
        return None, start + 1

    name_token = tokens[start]
    position = start + 1
    if position < limit and tokens[position].value == "[":
        closing = _matching(tokens, position, "[", "]", limit=limit)
        if closing is None:
            return None, position
        position = closing + 1
    if position < limit and tokens[position].value == "=":
        position += 1

    kind = "type"
    end_line = name_token.line
    next_position = position
    signature_end = name_token.end
    confidence = "heuristic"
    if position < limit and tokens[position].value in {"struct", "interface"}:
        kind = tokens[position].value
        signature_end = tokens[position].end
        if position + 1 < limit and tokens[position + 1].value == "{":
            closing = _matching(tokens, position + 1, "{", "}", limit=limit)
            if closing is not None:
                end_line = tokens[closing].line
                next_position = closing + 1
                confidence = "exact"
            else:
                next_position = position + 2
    else:
        # Semicolons are normally inserted by the Go scanner. The source lexer
        # deliberately does not synthesize them, so a simple type expression is
        # bounded to its physical line and marked heuristic.
        local_parens = 0
        local_brackets = 0
        local_curlies = 0
        previous_line = name_token.line
        while next_position < limit:
            token = tokens[next_position]
            if not grouped and token.line > name_token.line:
                break
            if token.value == ";" and local_parens == local_brackets == local_curlies == 0:
                next_position += 1
                break
            if (
                grouped
                and token.line > previous_line
                and local_parens == local_brackets == local_curlies == 0
                and token.kind == "identifier"
            ):
                break
            signature_end = token.end
            if token.value == "(":
                local_parens += 1
            elif token.value == ")":
                local_parens = max(0, local_parens - 1)
            elif token.value == "[":
                local_brackets += 1
            elif token.value == "]":
                local_brackets = max(0, local_brackets - 1)
            elif token.value == "{":
                local_curlies += 1
            elif token.value == "}":
                local_curlies = max(0, local_curlies - 1)
            previous_line = token.line
            next_position += 1

    keyword_token = tokens[type_keyword]
    if keyword_token.line == name_token.line:
        signature_start = keyword_token.start
    else:
        signature_start = name_token.start
    signature = _compact(source[signature_start:signature_end])
    qualified_name = name_token.value
    symbol = SymbolRecord(
        id=_symbol_id(file, package, kind, qualified_name, signature),
        file_id=file.id,
        path=file.path,
        name=name_token.value,
        qualified_name=qualified_name,
        kind=kind,
        line=name_token.line,
        end_line=end_line,
        analyzer=_analyzer_for(package),
        confidence="syntax-exact" if confidence == "exact" else "syntax-heuristic",
        signature=signature,
        exported=_exported(name_token.value),
    )
    return symbol, max(next_position, start + 1)


def _extract_types(
    file: FileRecord,
    source: str,
    tokens: list[_Token],
    curlies: list[int],
    parens: list[int],
    package: str,
) -> list[SymbolRecord]:
    symbols: list[SymbolRecord] = []
    index = 0
    while index < len(tokens):
        if tokens[index].value != "type" or curlies[index] != 0 or parens[index] != 0:
            index += 1
            continue
        if index + 1 >= len(tokens):
            break
        if tokens[index + 1].value == "(":
            closing = _matching(tokens, index + 1, "(", ")")
            if closing is None:
                index += 2
                continue
            position = index + 2
            while position < closing:
                symbol, next_position = _type_spec(
                    file,
                    source,
                    tokens,
                    position,
                    closing,
                    package=package,
                    type_keyword=index,
                    grouped=True,
                )
                if symbol is not None:
                    symbols.append(symbol)
                position = max(position + 1, next_position)
            index = closing + 1
            continue
        symbol, next_position = _type_spec(
            file,
            source,
            tokens,
            index + 1,
            len(tokens),
            package=package,
            type_keyword=index,
        )
        if symbol is not None:
            symbols.append(symbol)
        index = max(index + 1, next_position)
    return symbols


def _extract_interface_methods(
    file: FileRecord,
    source: str,
    tokens: list[_Token],
    curlies: list[int],
    package: str,
    types: list[SymbolRecord],
) -> list[SymbolRecord]:
    """Extract interface contracts as first-class callable declarations."""

    interfaces = [item for item in types if item.kind == "interface"]
    methods: list[SymbolRecord] = []
    for interface in interfaces:
        interface_token: int | None = None
        for index, token in enumerate(tokens):
            if token.value != "interface" or not (interface.line <= token.line <= interface.end_line):
                continue
            window = tokens[max(0, index - 12) : index]
            if any(candidate.value == interface.name for candidate in window):
                interface_token = index
                break
        if interface_token is None or interface_token + 1 >= len(tokens):
            continue
        brace = interface_token + 1
        if tokens[brace].value != "{":
            continue
        closing = _matching(tokens, brace, "{", "}")
        if closing is None:
            continue
        body_depth = curlies[brace] + 1
        index = brace + 1
        while index < closing:
            token = tokens[index]
            if (
                curlies[index] != body_depth
                or token.kind != "identifier"
                or token.value in _GO_KEYWORDS
                or (index > brace + 1 and tokens[index - 1].value == ".")
                or index + 1 >= closing
                or tokens[index + 1].value != "("
            ):
                index += 1
                continue
            parameters_end = _matching(tokens, index + 1, "(", ")", limit=closing)
            if parameters_end is None:
                index += 1
                continue
            signature_end_index = parameters_end
            position = parameters_end + 1
            if position < closing and tokens[position].value == "(":
                results_end = _matching(tokens, position, "(", ")", limit=closing)
                if results_end is not None:
                    signature_end_index = results_end
                    position = results_end + 1
            else:
                while (
                    position < closing
                    and tokens[position].line == tokens[parameters_end].line
                    and tokens[position].value != ";"
                ):
                    signature_end_index = position
                    position += 1
            signature = _compact(source[token.start : tokens[signature_end_index].end])
            qualified_name = f"{interface.name}.{token.value}"
            methods.append(
                SymbolRecord(
                    id=_symbol_id(
                        file,
                        package,
                        "interface-method",
                        qualified_name,
                        signature,
                    ),
                    file_id=file.id,
                    path=file.path,
                    name=token.value,
                    qualified_name=qualified_name,
                    kind="interface-method",
                    line=token.line,
                    end_line=tokens[signature_end_index].line,
                    analyzer=_analyzer_for(package),
                    confidence="syntax-exact",
                    parent_id=interface.id,
                    signature=signature,
                    exported=_exported(token.value),
                )
            )
            index = max(index + 1, position)
    return methods


def _receiver_type(receiver: list[_Token], known_types: dict[str, SymbolRecord]) -> str | None:
    # For `(receiver *Type[T])`, ignoring tokens from the type-argument list
    # leaves Type as the final identifier. This fallback cannot be type-checked.
    before_type_arguments: list[str] = []
    bracket_depth = 0
    for token in receiver:
        if token.value == "[":
            bracket_depth += 1
        elif token.value == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif token.kind == "identifier" and bracket_depth == 0:
            before_type_arguments.append(token.value)
    known = [name for name in before_type_arguments if name in known_types]
    if known:
        return known[-1]
    return before_type_arguments[-1] if before_type_arguments else None


def _find_function_body(tokens: list[_Token], position: int) -> tuple[int | None, int | None]:
    while position < len(tokens):
        token = tokens[position]
        if token.value == "{" and position > 0 and tokens[position - 1].value in {"struct", "interface"}:
            closing_type = _matching(tokens, position, "{", "}")
            if closing_type is None:
                return None, None
            position = closing_type + 1
            continue
        if token.value == "{":
            return position, _matching(tokens, position, "{", "}")
        # A later top-level declaration means this is a valid body-less function
        # (commonly implemented in assembly), or malformed input.
        if position > 0 and token.line > tokens[position - 1].line and token.value in {
            "const",
            "func",
            "import",
            "type",
            "var",
        }:
            break
        position += 1
    return None, None


def _extract_functions(
    file: FileRecord,
    source: str,
    tokens: list[_Token],
    curlies: list[int],
    parens: list[int],
    known_types: dict[str, SymbolRecord],
    package: str,
) -> list[_FunctionDecl]:
    declarations: list[_FunctionDecl] = []
    index = 0
    while index < len(tokens):
        if tokens[index].value != "func" or curlies[index] != 0 or parens[index] != 0:
            index += 1
            continue
        position = index + 1
        receiver_tokens: list[_Token] = []
        receiver_start: int | None = None
        receiver_end: int | None = None
        receiver_type: str | None = None
        if position < len(tokens) and tokens[position].value == "(":
            receiver_end = _matching(tokens, position, "(", ")")
            if receiver_end is None:
                index += 1
                continue
            receiver_start = position
            receiver_tokens = tokens[position + 1 : receiver_end]
            receiver_type = _receiver_type(receiver_tokens, known_types)
            position = receiver_end + 1
        if position >= len(tokens) or tokens[position].kind != "identifier":
            index += 1
            continue
        name_token = tokens[position]
        position += 1
        if position < len(tokens) and tokens[position].value == "[":
            type_parameters_end = _matching(tokens, position, "[", "]")
            if type_parameters_end is None:
                index += 1
                continue
            position = type_parameters_end + 1
        if position >= len(tokens) or tokens[position].value != "(":
            index += 1
            continue
        parameters_end = _matching(tokens, position, "(", ")")
        if parameters_end is None:
            index += 1
            continue

        results_start: int | None = None
        results_end: int | None = None
        after_parameters = parameters_end + 1
        if after_parameters < len(tokens) and tokens[after_parameters].value == "(":
            candidate_end = _matching(tokens, after_parameters, "(", ")")
            if candidate_end is not None:
                results_start = after_parameters
                results_end = candidate_end
        body_start, body_end = _find_function_body(tokens, after_parameters)
        if body_start is not None:
            signature_end = tokens[body_start].start
            end_line = tokens[body_end].line if body_end is not None else name_token.line
            confidence = "exact" if body_end is not None else "heuristic"
        else:
            signature_end = tokens[parameters_end].end
            scan = parameters_end + 1
            while scan < len(tokens) and tokens[scan].line == tokens[parameters_end].line:
                signature_end = tokens[scan].end
                scan += 1
            end_line = name_token.line
            confidence = "heuristic"

        kind = "method" if receiver_tokens else "function"
        local_qualified_name = (
            f"{receiver_type}.{name_token.value}" if receiver_type else name_token.value
        )
        qualified_name = local_qualified_name
        signature = _compact(source[tokens[index].start:signature_end])
        symbol = SymbolRecord(
            id=_symbol_id(file, package, kind, qualified_name, signature),
            file_id=file.id,
            path=file.path,
            name=name_token.value,
            qualified_name=qualified_name,
            kind=kind,
            line=tokens[index].line,
            end_line=end_line,
            analyzer=_analyzer_for(package),
            confidence="syntax-exact" if confidence == "exact" else "syntax-heuristic",
            # Go receiver methods are package-level declarations, not lexical
            # children of their receiver type. Project resolution emits a
            # dedicated ``receiver-type`` edge instead.
            parent_id=None,
            signature=signature,
            exported=_exported(name_token.value),
        )
        declarations.append(
            _FunctionDecl(
                symbol,
                body_start,
                body_end,
                receiver_start=receiver_start,
                receiver_end=receiver_end,
                parameters_start=position,
                parameters_end=parameters_end,
                results_start=results_start,
                results_end=results_end,
            )
        )
        index = (body_end + 1) if body_end is not None else parameters_end + 1
    return declarations


def _extract_imports(
    file: FileRecord,
    tokens: list[_Token],
    curlies: list[int],
    parens: list[int],
) -> list[RelationshipRecord]:
    relationships: list[RelationshipRecord] = []
    ordinal = 0

    def append_import(module_token: _Token, alias_token: _Token | None) -> None:
        nonlocal ordinal
        module = module_token.value[1:-1]
        alias = (
            alias_token.value
            if alias_token is not None
            else module.rstrip("/").rsplit("/", 1)[-1]
        )
        relationships.append(
            _relationship(
                file,
                "import",
                file.id,
                module,
                module_token.line,
                column=module_token.column,
                ordinal=ordinal,
                confidence="syntax-exact-unresolved",
            )
        )
        relationships.append(
            _relationship(
                file,
                "go-import-alias",
                file.id,
                f"{alias}={module}",
                module_token.line,
                column=module_token.column,
                ordinal=ordinal,
                confidence="syntax-exact",
            )
        )
        ordinal += 1

    for index, token in enumerate(tokens):
        if token.value != "import" or curlies[index] != 0 or parens[index] != 0:
            continue
        position = index + 1
        if position < len(tokens) and tokens[position].kind == "string":
            append_import(tokens[position], None)
            continue
        if (
            position + 1 < len(tokens)
            and tokens[position].value in {"_", "."}
            or position + 1 < len(tokens)
            and tokens[position].kind == "identifier"
            and tokens[position + 1].kind == "string"
        ):
            append_import(tokens[position + 1], tokens[position])
            continue
        if position >= len(tokens) or tokens[position].value != "(":
            continue
        closing = _matching(tokens, position, "(", ")")
        if closing is None:
            continue
        for imported_index in range(position + 1, closing):
            imported = tokens[imported_index]
            if imported.kind != "string":
                continue
            alias_token = None
            if imported_index > position + 1:
                previous = tokens[imported_index - 1]
                if previous.value in {"_", "."} or previous.kind == "identifier":
                    alias_token = previous
            append_import(imported, alias_token)
    return relationships


def _extract_calls(
    file: FileRecord,
    tokens: list[_Token],
    declaration: _FunctionDecl,
    local_functions: dict[str, SymbolRecord],
    known_types: set[str],
) -> list[RelationshipRecord]:
    if declaration.body_start is None or declaration.body_end is None:
        return []
    relationships: list[RelationshipRecord] = []
    local_bindings = _local_bindings(tokens, declaration, known_types)
    occurrence = 0
    index = declaration.body_start + 1
    stop = declaration.body_end
    while index < stop:
        token = tokens[index]
        if (
            token.kind != "identifier"
            or token.value in _GO_KEYWORDS
            or token.value in _GO_BUILTINS
            or token.value in _GO_PREDECLARED_TYPES
        ):
            index += 1
            continue
        if index > declaration.body_start + 1 and tokens[index - 1].value == ".":
            index += 1
            continue
        parts = [token.value]
        position = index + 1
        while position + 1 < stop and tokens[position].value == "." and tokens[position + 1].kind == "identifier":
            parts.append(tokens[position + 1].value)
            position += 2
        if position < stop and tokens[position].value == "[":
            type_arguments_end = _matching(tokens, position, "[", "]", limit=stop)
            if type_arguments_end is not None:
                position = type_arguments_end + 1
        if position >= stop or tokens[position].value != "(":
            index += 1
            continue
        target_name = ".".join(parts)
        active_bindings = [
            binding
            for binding in local_bindings
            if binding.name == parts[0]
            and binding.start <= index < binding.end
        ]
        active_binding = (
            max(active_bindings, key=lambda item: (item.start, -item.end))
            if active_bindings
            else None
        )
        root_is_shadowed = active_binding is not None
        target = (
            local_functions.get(target_name)
            if len(parts) == 1 and not root_is_shadowed
            else None
        )
        relationships.append(
            _relationship(
                file,
                "calls",
                declaration.symbol.id,
                target_name,
                token.line,
                column=token.column,
                ordinal=occurrence,
                target_id=target.id if target else None,
                confidence=(
                    "syntax-shadowed-unresolved"
                    if root_is_shadowed
                    else "syntax-scoped"
                    if target
                    else "heuristic-unresolved"
                ),
                receiver_type_hint=(
                    active_binding.type_name
                    if len(parts) == 2 and active_binding is not None
                    else None
                ),
            )
        )
        occurrence += 1
        index = position + 1
    return relationships


def _top_level_segments(
    tokens: list[_Token], start: int, end: int
) -> list[list[_Token]]:
    """Split a parenthesized Go declaration list without entering nested types."""

    segments: list[list[_Token]] = []
    current: list[_Token] = []
    paren = bracket = curly = 0
    for token in tokens[start:end]:
        if token.value == "," and paren == bracket == curly == 0:
            segments.append(current)
            current = []
            continue
        current.append(token)
        if token.value == "(":
            paren += 1
        elif token.value == ")":
            paren = max(0, paren - 1)
        elif token.value == "[":
            bracket += 1
        elif token.value == "]":
            bracket = max(0, bracket - 1)
        elif token.value == "{":
            curly += 1
        elif token.value == "}":
            curly = max(0, curly - 1)
    segments.append(current)
    return segments


def _parameter_names(tokens: list[_Token], start: int, end: int) -> set[str]:
    """Return conservatively inferred named parameters.

    A false positive only leaves a call unresolved, which is the safe outcome
    for the zero-dependency fallback.  The routine intentionally recognizes
    the common ``run func(...)`` and ``a, b *Type`` forms required to prevent
    package functions from winning over local function values.
    """

    segments = _top_level_segments(tokens, start, end)
    names: set[str] = set()
    pending_singletons: list[str] = []
    for segment in segments:
        identifiers = [
            token.value
            for token in segment
            if token.kind == "identifier" and token.value not in _GO_KEYWORDS
        ]
        if len(segment) == 1 and len(identifiers) == 1:
            pending_singletons.append(identifiers[0])
            continue
        if not identifiers:
            pending_singletons.clear()
            continue

        first = identifiers[0]
        has_explicit_type = (
            len(identifiers) >= 2
            or any(
                token.value in {"*", "[", "...", "<-"}
                or token.value in {"chan", "func", "interface", "map", "struct"}
                for token in segment[1:]
            )
        )
        if has_explicit_type:
            names.update(pending_singletons)
            names.add(first)
        pending_singletons.clear()
    return names


def _binding_names_before(
    tokens: list[_Token], operator: int, lower_bound: int
) -> list[str]:
    """Return the identifier-only LHS immediately before an assignment."""

    names: list[str] = []
    position = operator - 1
    expect_identifier = True
    while position >= lower_bound:
        token = tokens[position]
        if expect_identifier:
            if token.kind != "identifier" or token.value in _GO_KEYWORDS:
                break
            names.append(token.value)
            expect_identifier = False
        else:
            if token.value != ",":
                break
            expect_identifier = True
        position -= 1
    if expect_identifier:
        return []
    names.reverse()
    return [name for name in names if name != "_"]


def _var_spec_names(
    tokens: list[_Token], start: int, stop: int
) -> tuple[list[str], int]:
    """Read the identifier list at the start of one Go VarSpec."""

    names: list[str] = []
    position = start
    expect_identifier = True
    while position < stop:
        token = tokens[position]
        if expect_identifier:
            if token.kind != "identifier" or token.value in _GO_KEYWORDS:
                break
            names.append(token.value)
            expect_identifier = False
            position += 1
            continue
        if token.value != ",":
            break
        expect_identifier = True
        position += 1
    if expect_identifier:
        names.pop() if names else None
    return [name for name in names if name != "_"], position


def _brace_pairs(tokens: list[_Token], start: int, stop: int) -> dict[int, int]:
    stack: list[int] = []
    pairs: dict[int, int] = {}
    for index in range(start, stop + 1):
        if tokens[index].value == "{":
            stack.append(index)
        elif tokens[index].value == "}" and stack:
            opening = stack.pop()
            pairs[opening] = index
    return pairs


def _typed_parameter_bindings(
    tokens: list[_Token], start: int, end: int, known_types: set[str]
) -> dict[str, str]:
    """Return only parameter names with an explicit local concrete type."""

    bindings: dict[str, str] = {}
    pending_singletons: list[str] = []
    for segment in _top_level_segments(tokens, start, end):
        identifiers = [
            (index, token)
            for index, token in enumerate(segment)
            if token.kind == "identifier"
            and token.value not in _GO_KEYWORDS
            and token.value not in _GO_PREDECLARED_TYPES
        ]
        if len(segment) == 1 and len(identifiers) == 1:
            pending_singletons.append(identifiers[0][1].value)
            continue

        type_entry: tuple[int, _Token] | None = None
        paren = bracket = curly = 0
        for index, token in enumerate(segment):
            if (
                token.kind == "identifier"
                and token.value in known_types
                and paren == bracket == curly == 0
                and not (index > 0 and segment[index - 1].value == ".")
            ):
                prior_identifiers = [
                    prior_index
                    for prior_index, prior in enumerate(segment[:index])
                    if prior.kind == "identifier"
                    and prior.value not in _GO_KEYWORDS
                    and prior.value not in _GO_PREDECLARED_TYPES
                ]
                if prior_identifiers:
                    # Only a direct named type or pointer to it proves method
                    # ownership. ``[]Store``, ``map[K]Store`` and
                    # ``func() Store`` contain Store but are not Store values.
                    name_index = prior_identifiers[0]
                    type_prefix = segment[name_index + 1 : index]
                    if all(part.value == "*" for part in type_prefix):
                        type_entry = (index, token)
                        break
            if token.value == "(":
                paren += 1
            elif token.value == ")":
                paren = max(0, paren - 1)
            elif token.value == "[":
                bracket += 1
            elif token.value == "]":
                bracket = max(0, bracket - 1)
            elif token.value == "{":
                curly += 1
            elif token.value == "}":
                curly = max(0, curly - 1)
        if type_entry is None:
            pending_singletons.clear()
            continue

        type_index, type_token = type_entry
        names = [
            token.value for index, token in identifiers if index < type_index
        ]
        for name in [*pending_singletons, *names]:
            if name != "_":
                bindings[name] = type_token.value
        pending_singletons.clear()
    return bindings


def _statement_scope(
    tokens: list[_Token],
    operator: int,
    scope_open: int,
    default_end: int,
    pairs: dict[int, int],
    curlies: list[int],
) -> tuple[int | None, int]:
    """Return the body start and lexical end for a header declaration."""

    base_depth = curlies[operator]
    owner: str | None = None
    for position in range(operator - 1, scope_open, -1):
        token = tokens[position]
        if token.value == "}" and curlies[position] == base_depth + 1:
            break
        if curlies[position] != base_depth:
            continue
        if token.value in {"if", "for", "switch"}:
            owner = token.value
            break
    if owner is None:
        return None, default_end

    body_start = next(
        (
            position
            for position in range(operator + 1, default_end)
            if tokens[position].value == "{" and curlies[position] == base_depth
        ),
        None,
    )
    if body_start is None:
        return None, default_end
    body_end = pairs.get(body_start, default_end)
    if owner != "if":
        return body_start, body_end

    # The initializer is also visible in every else/else-if branch.
    position = body_end + 1
    while position < default_end and tokens[position].value == "else":
        position += 1
        if position < default_end and tokens[position].value == "if":
            position += 1
            next_body = next(
                (
                    candidate
                    for candidate in range(position, default_end)
                    if tokens[candidate].value == "{"
                    and curlies[candidate] == base_depth
                ),
                None,
            )
        elif position < default_end and tokens[position].value == "{":
            next_body = position
        else:
            break
        if next_body is None:
            break
        body_end = pairs.get(next_body, body_end)
        position = body_end + 1
    return body_start, body_end


def _short_declaration_scope_start(
    tokens: list[_Token],
    operator: int,
    default_end: int,
    statement_body_start: int | None,
    curlies: list[int],
    parens: list[int],
    brackets: list[int],
) -> int:
    """Start a short binding only after its declaration has completed."""

    base_depths = (curlies[operator], parens[operator], brackets[operator])
    limit = statement_body_start if statement_body_start is not None else default_end
    for position in range(operator + 2, limit):
        if (
            tokens[position].value == ";"
            and (curlies[position], parens[position], brackets[position])
            == base_depths
        ):
            return position + 1

    if statement_body_start is not None:
        # Range clauses and type-switch guards have no header semicolon. Their
        # declared names begin in the body, never in the expression on the RHS.
        return statement_body_start + 1

    statement_end_values = {")", "]", "}", "++", "--"}
    for position in range(operator + 3, default_end):
        previous = tokens[position - 1]
        if (
            tokens[position].line > previous.line
            and (curlies[position], parens[position], brackets[position])
            == base_depths
            and (
                previous.kind in {"identifier", "string"}
                or previous.value in statement_end_values
            )
        ):
            return position
    return default_end


def _local_bindings(
    tokens: list[_Token], declaration: _FunctionDecl, known_types: set[str]
) -> list[_LocalBinding]:
    """Build conservative lexical binding intervals for call-root safety.

    This is intentionally not a Go type checker. It models the binding forms
    that can disprove a name-only call edge: receivers, parameters, multi-name
    ``var`` declarations, identifier-only assignments/short declarations, and
    nested function-literal parameters. Unknown forms remain unresolved rather
    than being promoted to a package function or type.
    """

    if declaration.body_start is None or declaration.body_end is None:
        return []
    body_start = declaration.body_start
    body_end = declaration.body_end
    bindings: list[_LocalBinding] = []

    for group_start, group_end in (
        (declaration.receiver_start, declaration.receiver_end),
        (declaration.parameters_start, declaration.parameters_end),
        (declaration.results_start, declaration.results_end),
    ):
        if group_start is None or group_end is None:
            continue
        typed = _typed_parameter_bindings(
            tokens, group_start + 1, group_end, known_types
        )
        bindings.extend(
            _LocalBinding(name, body_start + 1, body_end, typed.get(name))
            for name in _parameter_names(tokens, group_start + 1, group_end)
        )

    pairs = _brace_pairs(tokens, body_start, body_end)
    curlies, parens, brackets = _depths(tokens)
    scope_stack: list[int] = [body_start]
    index = body_start + 1
    while index < body_end:
        token = tokens[index]
        if token.value == "{":
            scope_stack.append(index)
            index += 1
            continue
        if token.value == "}":
            if len(scope_stack) > 1:
                scope_stack.pop()
            index += 1
            continue
        scope_end = pairs.get(scope_stack[-1], body_end)

        if token.value == "func" and index + 1 < body_end and tokens[index + 1].value == "(":
            parameters_end = _matching(tokens, index + 1, "(", ")", limit=body_end)
            if parameters_end is not None:
                results_start: int | None = None
                results_end: int | None = None
                after_parameters = parameters_end + 1
                if (
                    after_parameters < body_end
                    and tokens[after_parameters].value == "("
                ):
                    candidate_end = _matching(
                        tokens, after_parameters, "(", ")", limit=body_end
                    )
                    if candidate_end is not None:
                        results_start = after_parameters
                        results_end = candidate_end
                literal_start, literal_end = _find_function_body(
                    tokens, after_parameters
                )
                if (
                    literal_start is not None
                    and literal_end is not None
                    and literal_end <= body_end
                ):
                    for group_start, group_end in (
                        (index + 1, parameters_end),
                        (results_start, results_end),
                    ):
                        if group_start is None or group_end is None:
                            continue
                        typed = _typed_parameter_bindings(
                            tokens, group_start + 1, group_end, known_types
                        )
                        bindings.extend(
                            _LocalBinding(
                                name,
                                literal_start + 1,
                                literal_end,
                                typed.get(name),
                            )
                            for name in _parameter_names(
                                tokens, group_start + 1, group_end
                            )
                        )

        if token.value == "var" and index + 1 < body_end:
            position = index + 1
            if tokens[position].value == "(":
                closing = _matching(tokens, position, "(", ")", limit=body_end)
                if closing is not None:
                    candidate = position + 1
                    while candidate < closing:
                        names, after_names = _var_spec_names(tokens, candidate, closing)
                        bindings.extend(
                            _LocalBinding(name, after_names, scope_end) for name in names
                        )
                        current_line = tokens[candidate].line
                        candidate = max(candidate + 1, after_names)
                        while (
                            candidate < closing
                            and tokens[candidate].line == current_line
                        ):
                            candidate += 1
                    index = closing + 1
                    continue
            names, after_names = _var_spec_names(tokens, position, body_end)
            bindings.extend(
                _LocalBinding(name, after_names, scope_end) for name in names
            )

        is_short = token.value == ":" and index + 1 < body_end and tokens[index + 1].value == "="
        if is_short:
            names = _binding_names_before(tokens, index, scope_stack[-1] + 1)
            statement_body_start, binding_end = _statement_scope(
                tokens,
                index,
                scope_stack[-1],
                scope_end,
                pairs,
                curlies,
            )
            binding_start = _short_declaration_scope_start(
                tokens,
                index,
                scope_end,
                statement_body_start,
                curlies,
                parens,
                brackets,
            )
            bindings.extend(
                _LocalBinding(name, binding_start, binding_end) for name in names
            )
        index += 1
    return bindings


def _module_roots(project_root: Path | None) -> list[tuple[str, PurePosixPath]]:
    if project_root is None or not project_root.is_dir():
        return []
    roots: list[tuple[str, PurePosixPath]] = []
    for go_mod in sorted(project_root.rglob("go.mod")):
        if any(part in {".git", "vendor", "node_modules"} for part in go_mod.parts):
            continue
        try:
            lines = go_mod.read_text(encoding="utf-8", errors="replace").splitlines()
            module = next(
                (
                    line.split(None, 1)[1].strip()
                    for line in lines
                    if line.strip().startswith("module ")
                ),
                "",
            )
            relative = PurePosixPath(go_mod.parent.relative_to(project_root).as_posix())
        except (OSError, ValueError, IndexError):
            continue
        if module:
            roots.append((module, relative))
    return sorted(roots, key=lambda item: len(item[0]), reverse=True)


def _local_import_directory(
    target: str,
    module_roots: list[tuple[str, PurePosixPath]],
) -> PurePosixPath | None:
    for module, relative_root in module_roots:
        if target == module:
            return relative_root
        prefix = f"{module}/"
        if target.startswith(prefix):
            return relative_root / PurePosixPath(target.removeprefix(prefix))
    return None


def resolve_go_relationships(
    relationships: list[RelationshipRecord],
    symbols: list[SymbolRecord],
    files: Iterable[FileRecord],
    *,
    project_root: Path | None = None,
) -> GoResolutionStats:
    """Resolve only relationships justified by Go package/import syntax.

    This project-level pass is intentionally conservative. It clears any
    pre-existing Go call/import target before resolution, isolates Go symbols
    from every other language, permits only callable call targets, and never
    maps standard-library/third-party imports into a coincidentally named local
    file. Receiver selectors resolve only when the declaration signature proves
    a local concrete type; assignment inference and dynamic dispatch remain
    unresolved because the lexer has no type checker.

    The caller must exclude Go relationships from any later global name-only
    resolver. A gopls result may supersede these syntax-scoped links.
    """

    go_symbols = [item for item in symbols if item.analyzer.startswith("go-")]
    symbols_by_id = {item.id: item for item in go_symbols}
    file_list = [item for item in files if item.language == "Go"]
    files_by_directory: dict[PurePosixPath, list[FileRecord]] = {}
    for file in file_list:
        directory = PurePosixPath(file.path).parent
        files_by_directory.setdefault(directory, []).append(file)
    for values in files_by_directory.values():
        values.sort(key=lambda item: (item.path.endswith("_test.go"), item.path))

    package_by_file: dict[str, str] = {}
    for symbol in go_symbols:
        package_by_file.setdefault(symbol.path, _symbol_package(symbol))

    function_index: dict[tuple[PurePosixPath, str, str], list[SymbolRecord]] = {}
    method_index: dict[
        tuple[PurePosixPath, str, str, str], list[SymbolRecord]
    ] = {}
    type_index: dict[tuple[PurePosixPath, str, str], list[SymbolRecord]] = {}
    for symbol in go_symbols:
        key = (
            PurePosixPath(symbol.path).parent,
            _symbol_package(symbol),
            symbol.name,
        )
        if symbol.kind == "function":
            function_index.setdefault(key, []).append(symbol)
        if symbol.kind == "method" and "." in symbol.qualified_name:
            receiver = symbol.qualified_name.rsplit(".", 1)[0].rsplit(".", 1)[-1]
            method_index.setdefault((*key[:2], receiver, symbol.name), []).append(
                symbol
            )
        if symbol.kind in {"type", "struct", "interface"}:
            type_index.setdefault(key, []).append(symbol)

    local_types_by_scope: dict[tuple[PurePosixPath, str], set[str]] = {}
    for (directory, package, _), values in type_index.items():
        local_types_by_scope.setdefault((directory, package), set()).update(
            item.name for item in values
        )
    # A Go method is declared at package scope. Its receiver is semantic type
    # ownership, not lexical containment, so keep ``parent_id`` empty and emit
    # a dedicated method -> receiver edge whose path belongs to the method
    # source. Existing warm-cache edges are re-proved here after target IDs are
    # cleared during hydration.
    receiver_links = 0
    file_by_path = {item.path: item for item in file_list}
    receiver_edges = {
        item.source_id: item
        for item in relationships
        if item.analyzer.startswith("go-") and item.kind == "receiver-type"
    }
    for edge in receiver_edges.values():
        edge.target_id = None
        edge.confidence = "syntax-exact-unresolved"
    for symbol in go_symbols:
        if symbol.kind != "method" or "." not in symbol.qualified_name:
            continue
        symbol.parent_id = None
        receiver = symbol.qualified_name.rsplit(".", 1)[0].rsplit(".", 1)[-1]
        candidates = type_index.get(
            (PurePosixPath(symbol.path).parent, _symbol_package(symbol), receiver),
            [],
        )
        unique = {item.id: item for item in candidates}
        if len(unique) != 1:
            continue
        receiver_type = next(iter(unique.values()))
        edge = receiver_edges.get(symbol.id)
        if edge is None:
            source_file = file_by_path.get(symbol.path)
            if source_file is None:
                continue
            edge = _relationship(
                source_file,
                "receiver-type",
                symbol.id,
                receiver_type.qualified_name,
                symbol.line,
                target_id=receiver_type.id,
                confidence="syntax-scoped",
            )
            relationships.append(edge)
            receiver_edges[symbol.id] = edge
        else:
            edge.target_id = receiver_type.id
            edge.target_name = receiver_type.qualified_name
            edge.confidence = "syntax-scoped"
        receiver_links += 1

    import_aliases: dict[str, dict[str, str]] = {}
    for relationship in relationships:
        if (
            relationship.analyzer.startswith("go-")
            and relationship.kind == "go-import-alias"
            and "=" in relationship.target_name
        ):
            alias, module = relationship.target_name.split("=", 1)
            import_aliases.setdefault(relationship.path, {})[alias] = module

    module_roots = _module_roots(project_root)
    calls_resolved = calls_unresolved = imports_resolved = imports_unresolved = 0
    for relationship in relationships:
        if not relationship.analyzer.startswith("go-"):
            continue
        if relationship.kind not in {"calls", "import"}:
            continue

        was_shadowed = relationship.confidence == "syntax-shadowed-unresolved"
        # Never trust a target hydrated by a previous index or global resolver.
        relationship.target_id = None
        relationship.confidence = (
            "syntax-shadowed-unresolved" if was_shadowed else "heuristic-unresolved"
        )

        if relationship.kind == "import":
            target_directory = _local_import_directory(
                relationship.target_name, module_roots
            )
            candidates = files_by_directory.get(target_directory, []) if target_directory else []
            if candidates:
                relationship.target_id = candidates[0].id
                relationship.confidence = "syntax-scoped"
                imports_resolved += 1
            else:
                imports_unresolved += 1
            continue

        source = symbols_by_id.get(relationship.source_id)
        if source is None:
            calls_unresolved += 1
            continue
        source_directory = PurePosixPath(source.path).parent
        source_package = _symbol_package(source)
        parts = relationship.target_name.split(".")
        if was_shadowed and len(parts) == 1:
            calls_unresolved += 1
            continue
        candidates: list[SymbolRecord] = []
        if len(parts) == 1:
            candidates = function_index.get(
                (source_directory, source_package, parts[0]), []
            )
        elif len(parts) == 2:
            imported_module = (
                None
                if was_shadowed
                else import_aliases.get(relationship.path, {}).get(parts[0])
            )
            target_directory = (
                _local_import_directory(imported_module, module_roots)
                if imported_module
                else None
            )
            if target_directory is not None:
                target_packages = {
                    package_by_file.get(file.path, "unknown")
                    for file in files_by_directory.get(target_directory, [])
                }
                for target_package in target_packages:
                    candidates.extend(
                        function_index.get(
                            (target_directory, target_package, parts[1]), []
                        )
                    )
            else:
                local_types = local_types_by_scope.get(
                    (source_directory, source_package), set()
                )
                receiver_type = relationship.receiver_type_hint
                if (
                    receiver_type is None
                    and not was_shadowed
                    and parts[0] in local_types
                ):
                    # Go method expression: ``Type.Method(receiver, ...)``.
                    receiver_type = parts[0]
                if receiver_type is not None:
                    candidates.extend(
                        method_index.get(
                            (
                                source_directory,
                                source_package,
                                receiver_type,
                                parts[1],
                            ),
                            [],
                        )
                    )

        unique = {
            item.id: item
            for item in candidates
            if item.kind in _CALLABLE_KINDS
            and not item.path.endswith("_test.go")
        }
        if len(unique) == 1:
            relationship.target_id = next(iter(unique))
            relationship.confidence = "syntax-scoped"
            calls_resolved += 1
        else:
            calls_unresolved += 1

    return GoResolutionStats(
        calls_resolved=calls_resolved,
        calls_unresolved=calls_unresolved,
        imports_resolved=imports_resolved,
        imports_unresolved=imports_unresolved,
        receiver_types_linked=receiver_links,
    )


def analyze_go(file: FileRecord, source: str) -> AnalysisResult:
    """Extract conservative Go syntax with explicitly unresolved semantics.

    This is the no-dependency fallback.  It never claims type-checker quality;
    project-level callers should run :func:`resolve_go_relationships`, and may
    optionally validate/replace results with the gopls adapter.
    """

    tokens, diagnostics = _tokenize(source, file.path)
    diagnostics.extend(_delimiter_diagnostics(tokens, file.path))
    package, package_diagnostics = _package_name(tokens, file.path)
    diagnostics.extend(package_diagnostics)
    curlies, parens, _ = _depths(tokens)
    types = _extract_types(file, source, tokens, curlies, parens, package)
    known_types = {symbol.name: symbol for symbol in types}
    interface_methods = _extract_interface_methods(
        file, source, tokens, curlies, package, types
    )
    functions = _extract_functions(
        file, source, tokens, curlies, parens, known_types, package
    )

    result = AnalysisResult(
        symbols=[*types, *interface_methods, *(item.symbol for item in functions)],
        diagnostics=diagnostics,
    )

    # Invalid Go may contain exact duplicate declarations. Preserve both with
    # a declaration-order disambiguator, and surface the fact instead of
    # silently emitting duplicate graph identities.
    seen_symbol_ids: dict[str, int] = {}
    for symbol in result.symbols:
        occurrence = seen_symbol_ids.get(symbol.id, 0)
        seen_symbol_ids[symbol.id] = occurrence + 1
        if occurrence == 0:
            continue
        symbol.id = stable_id(symbol.id, "duplicate", occurrence)
        result.diagnostics.append(
            DiagnosticRecord(
                path=file.path,
                severity="warning",
                code="go-duplicate-declaration",
                message=f"duplicate declaration preserved with disambiguator: {symbol.qualified_name}",
                line=symbol.line,
            )
        )

    result.relationships.extend(_extract_imports(file, tokens, curlies, parens))
    for symbol in result.symbols:
        parent_id = symbol.parent_id or file.id
        result.relationships.append(
            _relationship(
                file,
                "contains",
                parent_id,
                symbol.qualified_name,
                symbol.line,
                column=1,
                target_id=symbol.id,
                confidence="syntax-exact",
            )
        )

    local_functions = {
        item.symbol.name: item.symbol
        for item in functions
        if item.symbol.kind == "function"
    }
    for declaration in functions:
        result.relationships.extend(
            _extract_calls(
                file,
                tokens,
                declaration,
                local_functions,
                set(known_types),
            )
        )

    result.symbols.sort(key=lambda item: (item.line, item.qualified_name))
    result.relationships.sort(key=lambda item: (item.line, item.kind, item.id))
    return result


__all__ = ["GoResolutionStats", "analyze_go", "resolve_go_relationships"]
