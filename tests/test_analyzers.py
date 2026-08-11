from __future__ import annotations

import unittest
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from repo_teacher.analyzers import analyze_file, resolve_go_relationships
from repo_teacher.analyzers.go_semantic import GoplsAdapter, GoplsSymbol
from repo_teacher.models import FileRecord, RelationshipRecord, SymbolRecord
from repo_teacher.scanner import ScanOptions, scan_repository


def file_record(path: str, language: str) -> FileRecord:
    return FileRecord(
        id=f"file:{path}",
        path=path,
        language=language,
        size=0,
        lines=0,
        sha256="fixture",
    )


class AnalyzersTest(unittest.TestCase):
    def test_python_ast_extracts_definitions_imports_contains_and_calls(self) -> None:
        source = """\
import os
from package.tools import helper as imported_helper

class Greeter:
    def greet(self, name: str) -> str:
        return helper(name)

def helper(value):
    return os.fspath(value)
"""
        result = analyze_file(file_record("src/app.py", "Python"), source)

        symbols = {symbol.qualified_name: symbol for symbol in result.symbols}
        self.assertEqual(set(symbols), {"Greeter", "Greeter.greet", "helper"})
        self.assertEqual(symbols["Greeter.greet"].parent_id, symbols["Greeter"].id)
        self.assertIn("name: str", symbols["Greeter.greet"].signature or "")
        self.assertIn("import", {relationship.kind for relationship in result.relationships})
        calls = {relationship.target_name for relationship in result.relationships if relationship.kind == "calls"}
        self.assertIn("helper", calls)
        self.assertIn("os.fspath", calls)
        self.assertFalse(result.diagnostics)

    def test_python_syntax_error_becomes_diagnostic(self) -> None:
        result = analyze_file(file_record("broken.py", "Python"), "def broken(:\n")

        self.assertFalse(result.symbols)
        self.assertEqual(result.diagnostics[0].code, "python-syntax-error")

    def test_typescript_extracts_exports_declarations_and_imports(self) -> None:
        source = """\
import { client } from './client'
export class Worker {}
export async function run(value: string) { return client(value) }
const helper = (value: number) => value + 1
"""
        result = analyze_file(file_record("web/main.ts", "TypeScript"), source)

        symbols = {symbol.name: symbol for symbol in result.symbols}
        self.assertEqual(set(symbols), {"Worker", "run", "helper"})
        self.assertTrue(symbols["Worker"].exported)
        self.assertTrue(symbols["run"].exported)
        self.assertFalse(symbols["helper"].exported)
        imports = [relationship for relationship in result.relationships if relationship.kind == "import"]
        self.assertEqual(imports[0].target_name, "./client")
        self.assertEqual(symbols["run"].confidence, "heuristic")

    def test_go_extracts_types_functions_methods_imports_contains_and_calls(self) -> None:
        source = """\
package service

import (
    "context"
    "fmt"
)

type Store struct {
    name string
}

type Runner interface {
    Run(context.Context) error
}

type ID string

func NewStore(name string) *Store {
    helper(name)
    _ = int(1)
    return &Store{name: fmt.Sprint(name)}
}

func (store *Store) Save(ctx context.Context) error {
    store.validate()
    return persist(ctx)
}
"""
        result = analyze_file(file_record("internal/service/store.go", "Go"), source)

        symbols = {symbol.qualified_name: symbol for symbol in result.symbols}
        self.assertEqual(
            set(symbols),
            {"Store", "Runner", "Runner.Run", "ID", "NewStore", "Store.Save"},
        )
        self.assertEqual(symbols["Store"].kind, "struct")
        self.assertEqual(symbols["Runner"].kind, "interface")
        self.assertEqual(symbols["Runner.Run"].kind, "interface-method")
        self.assertEqual(symbols["Runner.Run"].parent_id, symbols["Runner"].id)
        self.assertEqual(symbols["ID"].kind, "type")
        self.assertEqual(symbols["Store.Save"].kind, "method")
        self.assertIsNone(symbols["Store.Save"].parent_id)
        self.assertGreater(symbols["Store"].end_line, symbols["Store"].line)
        self.assertGreater(symbols["NewStore"].end_line, symbols["NewStore"].line)
        self.assertIn("func (store *Store) Save", symbols["Store.Save"].signature or "")
        self.assertTrue(symbols["Store"].exported)

        imports = {
            relationship.target_name
            for relationship in result.relationships
            if relationship.kind == "import"
        }
        self.assertEqual(imports, {"context", "fmt"})
        calls = {
            relationship.target_name: relationship
            for relationship in result.relationships
            if relationship.kind == "calls"
        }
        self.assertEqual(set(calls), {"helper", "fmt.Sprint", "store.validate", "persist"})
        self.assertTrue(
            all(
                call.confidence
                in {
                    "syntax-scoped",
                    "heuristic-unresolved",
                    "syntax-shadowed-unresolved",
                }
                for call in calls.values()
            )
        )
        contains = [relationship for relationship in result.relationships if relationship.kind == "contains"]
        method_contains = next(item for item in contains if item.target_id == symbols["Store.Save"].id)
        self.assertEqual(
            method_contains.source_id,
            file_record("internal/service/store.go", "Go").id,
        )
        self.assertFalse(result.diagnostics)

    def test_go_grouped_types_and_stable_ids(self) -> None:
        source = """\
package model

type (
    User struct {
        Name string
    }
    Reader interface {
        Read() error
    }
    UserID = string
)
"""
        first = analyze_file(file_record("model/types.go", "Go"), source)
        second = analyze_file(file_record("model/types.go", "Go"), source)

        self.assertEqual(
            [
                (symbol.name, symbol.kind)
                for symbol in first.symbols
                if symbol.kind != "interface-method"
            ],
            [("User", "struct"), ("Reader", "interface"), ("UserID", "type")],
        )
        self.assertEqual(
            [symbol.id for symbol in first.symbols],
            [symbol.id for symbol in second.symbols],
        )

    def test_go_unterminated_comment_becomes_diagnostic(self) -> None:
        result = analyze_file(file_record("broken.go", "Go"), "package broken\n/* unfinished")

        self.assertFalse(result.symbols)
        self.assertEqual(result.diagnostics[0].code, "go-unterminated-comment")

    def test_go_symbol_ids_survive_unrelated_line_shift(self) -> None:
        source = "package p\n\ntype Store struct{}\nfunc New() *Store { return &Store{} }\n"
        shifted = "// unrelated comment\n\n" + source
        first = analyze_file(file_record("p/store.go", "Go"), source)
        second = analyze_file(file_record("p/store.go", "Go"), shifted)

        self.assertEqual(
            {item.qualified_name: item.id for item in first.symbols},
            {item.qualified_name: item.id for item in second.symbols},
        )

    def test_go_repeated_same_line_calls_preserve_occurrences(self) -> None:
        result = analyze_file(
            file_record("p/main.go", "Go"),
            "package p\nfunc target() {}\nfunc run(){ target(); target() }\n",
        )
        calls = [
            item
            for item in result.relationships
            if item.kind == "calls" and item.target_name == "target"
        ]
        self.assertEqual(len(calls), 2)
        self.assertEqual(len({item.id for item in calls}), 2)

    def test_go_package_resolver_is_callable_only_and_external_safe(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "go.mod").write_text("module example.test/project\n", encoding="utf-8")
            main_file = file_record("cmd/main.go", "Go")
            util_file = file_record("internal/util/util.go", "Go")
            main = analyze_file(
                main_file,
                '''package main
import (
  "context"
  "fmt"
  helper "example.test/project/internal/util"
)
func run(){ fmt.Println("x"); context.WithCancel(nil); helper.Work(); helper.Data() }
''',
            )
            util = analyze_file(
                util_file,
                "package util\ntype Data string\nfunc Work() {}\n",
            )
            foreign = SymbolRecord(
                id="typescript-print",
                file_id="ts",
                path="web/a.ts",
                name="Println",
                qualified_name="Println",
                kind="function",
                line=1,
                end_line=1,
                analyzer="javascript-regex",
                confidence="heuristic",
            )
            symbols = [*main.symbols, *util.symbols, foreign]
            relationships = [*main.relationships, *util.relationships]
            stats = resolve_go_relationships(
                relationships,
                symbols,
                [main_file, util_file],
                project_root=root,
            )

            calls = {
                item.target_name: item
                for item in relationships
                if item.kind == "calls"
            }
            self.assertIsNone(calls["fmt.Println"].target_id)
            self.assertIsNone(calls["context.WithCancel"].target_id)
            self.assertEqual(
                calls["helper.Work"].target_id,
                next(item.id for item in util.symbols if item.name == "Work"),
            )
            self.assertIsNone(calls["helper.Data"].target_id)
            external_imports = {
                item.target_name: item.target_id
                for item in relationships
                if item.kind == "import"
            }
            self.assertIsNone(external_imports["context"])
            self.assertIsNone(external_imports["fmt"])
            self.assertIsNotNone(external_imports["example.test/project/internal/util"])
            self.assertEqual(stats.calls_resolved, 1)

    def test_go_receiver_type_links_across_same_package_files(self) -> None:
        type_file = file_record("p/type.go", "Go")
        method_file = file_record("p/method.go", "Go")
        type_result = analyze_file(type_file, "package p\ntype Store struct{}\n")
        method_result = analyze_file(
            method_file, "package p\nfunc (store *Store) Save() {}\n"
        )
        symbols = [*type_result.symbols, *method_result.symbols]
        relationships = [*type_result.relationships, *method_result.relationships]

        stats = resolve_go_relationships(
            relationships, symbols, [type_file, method_file]
        )
        store = next(item for item in symbols if item.name == "Store")
        save = next(item for item in symbols if item.name == "Save")
        self.assertIsNone(save.parent_id)
        contains = next(item for item in relationships if item.target_id == save.id)
        self.assertEqual(contains.source_id, method_file.id)
        receiver_type = next(
            item for item in relationships if item.kind == "receiver-type"
        )
        self.assertEqual(receiver_type.source_id, save.id)
        self.assertEqual(receiver_type.target_id, store.id)
        self.assertEqual(receiver_type.path, method_file.path)
        self.assertEqual(stats.receiver_types_linked, 1)

    def test_go_unqualified_and_package_calls_never_target_methods_or_interfaces(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "go.mod").write_text(
                "module example.test/project\n", encoding="utf-8"
            )
            caller_file = file_record("caller/caller.go", "Go")
            dependency_file = file_record("dependency/dependency.go", "Go")
            caller = analyze_file(
                caller_file,
                '''package caller
import dependency "example.test/project/dependency"
type Local struct{}
func (Local) Execute() {}
type Contract interface { Dispatch() }
func caller(){ Execute(); Dispatch(); dependency.Execute(); dependency.Dispatch() }
''',
            )
            dependency = analyze_file(
                dependency_file,
                '''package dependency
type Worker struct{}
func (Worker) Execute() {}
type Contract interface { Dispatch() }
''',
            )
            symbols = [*caller.symbols, *dependency.symbols]
            relationships = [*caller.relationships, *dependency.relationships]

            resolve_go_relationships(
                relationships,
                symbols,
                [caller_file, dependency_file],
                project_root=root,
            )

            calls = [item for item in relationships if item.kind == "calls"]
            self.assertEqual(
                {item.target_name for item in calls},
                {"Execute", "Dispatch", "dependency.Execute", "dependency.Dispatch"},
            )
            self.assertTrue(all(item.target_id is None for item in calls))

    def test_go_shadowed_function_values_remain_unresolved(self) -> None:
        source = '''package p
func run() {}
func parameter(run func()){ run() }
func local(){ run := func(){}; run() }
func packageCall(){ run() }
'''
        file = file_record("p/functions.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        symbols_by_id = {item.id: item for item in result.symbols}
        calls = {
            symbols_by_id[item.source_id].name: item
            for item in relationships
            if item.kind == "calls"
        }
        self.assertIsNone(calls["parameter"].target_id)
        self.assertEqual(calls["parameter"].confidence, "syntax-shadowed-unresolved")
        self.assertIsNone(calls["local"].target_id)
        self.assertEqual(calls["local"].confidence, "syntax-shadowed-unresolved")
        self.assertEqual(
            calls["packageCall"].target_id,
            next(item.id for item in result.symbols if item.name == "run"),
        )

    def test_go_multiname_and_function_literal_bindings_shadow_package_calls(self) -> None:
        source = '''package p
func run() {}
func maker() (func(), func()) { return nil, nil }
func varDecl(){ var other, run func(); run(); _ = other }
func shortDecl(){ run, other := maker(); run(); _ = other }
func literal(){ _ = func(run func()){ run() } }
'''
        file = file_record("p/shadow.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        symbols_by_id = {item.id: item for item in result.symbols}
        calls_by_source: dict[str, list[RelationshipRecord]] = {}
        for item in relationships:
            if item.kind != "calls" or item.target_name != "run":
                continue
            calls_by_source.setdefault(symbols_by_id[item.source_id].name, []).append(item)

        self.assertEqual(set(calls_by_source), {"varDecl", "shortDecl", "literal"})
        for calls in calls_by_source.values():
            self.assertTrue(all(item.target_id is None for item in calls))
            self.assertTrue(
                all(item.confidence == "syntax-shadowed-unresolved" for item in calls)
            )

    def test_go_nested_bindings_do_not_shadow_calls_outside_their_scope(self) -> None:
        source = '''package p
func run() {}
func scoped(){ run(); _ = func(run func()){ run() }; run() }
'''
        file = file_record("p/scopes.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        calls = [
            item
            for item in relationships
            if item.kind == "calls" and item.target_name == "run"
        ]
        self.assertEqual(len(calls), 3)
        self.assertIsNotNone(calls[0].target_id)
        self.assertIsNone(calls[1].target_id)
        self.assertEqual(calls[1].confidence, "syntax-shadowed-unresolved")
        self.assertIsNotNone(calls[2].target_id)

    def test_go_local_binding_shadowing_type_name_never_uses_type_fallback(self) -> None:
        source = '''package p
type Store struct{}
type Other struct{}
func (Store) Save(){}
func (Other) Save(){}
func outer(){ Store := Other{}; Store.Save() }
'''
        file = file_record("p/type_shadow.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        outer = next(item for item in result.symbols if item.name == "outer")
        call = next(
            item
            for item in relationships
            if item.kind == "calls" and item.source_id == outer.id
        )
        self.assertEqual(call.target_name, "Store.Save")
        self.assertIsNone(call.target_id)
        self.assertEqual(call.confidence, "syntax-shadowed-unresolved")

    def test_go_receiver_selector_requires_explicit_local_type_evidence(self) -> None:
        source = '''package p
type Store struct{}
func (store *Store) Save() {}
func receiver(store *Store){ store.Save() }
func methodExpression(store *Store){ Store.Save(store) }
func unknown(other any){ other.Save() }
'''
        file = file_record("p/store.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])
        symbols_by_id = {item.id: item for item in result.symbols}
        calls = {
            symbols_by_id[item.source_id].name: item
            for item in relationships
            if item.kind == "calls"
        }
        save_id = next(item.id for item in result.symbols if item.name == "Save")
        self.assertEqual(calls["receiver"].target_id, save_id)
        self.assertEqual(calls["methodExpression"].target_id, save_id)
        self.assertIsNone(calls["unknown"].target_id)

    def test_go_nested_shadow_uses_innermost_receiver_binding_only(self) -> None:
        source = '''package p
type Store struct{}
type Other struct{}
func (Store) Save(){}
func (Other) Save(){}
func block(store *Store) {
    { store := Other{}; store.Save() }
    store.Save()
}
func literal(store *Store) {
    _ = func(store *Other){ store.Save() }
    store.Save()
}
func typeNamedStore(Store *Other) { Store.Save() }
'''
        file = file_record("p/receiver_shadow.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        methods = {
            item.qualified_name: item.id
            for item in result.symbols
            if item.kind == "method"
        }
        symbols = {item.id: item for item in result.symbols}
        calls: dict[str, list[RelationshipRecord]] = {}
        for relationship in relationships:
            if relationship.kind == "calls" and relationship.target_name == "store.Save":
                calls.setdefault(symbols[relationship.source_id].name, []).append(
                    relationship
                )

        self.assertEqual(len(calls["block"]), 2)
        self.assertIsNone(calls["block"][0].target_id)
        self.assertEqual(calls["block"][0].confidence, "syntax-shadowed-unresolved")
        self.assertEqual(calls["block"][1].target_id, methods["Store.Save"])
        self.assertEqual(calls["literal"][0].target_id, methods["Other.Save"])
        self.assertEqual(calls["literal"][1].target_id, methods["Store.Save"])
        type_named_call = next(
            item
            for item in relationships
            if item.kind == "calls" and item.target_name == "Store.Save"
        )
        self.assertEqual(type_named_call.target_id, methods["Other.Save"])

    def test_go_method_receiver_shadow_does_not_leak_out_of_nested_block(self) -> None:
        source = '''package p
type Store struct{}
func (Store) Save(){}
func (store *Store) Work(){
    { store := any(nil); store.Save() }
    store.Save()
}
'''
        file = file_record("p/method_receiver.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        save = next(item for item in result.symbols if item.qualified_name == "Store.Save")
        calls = [
            item
            for item in relationships
            if item.kind == "calls" and item.target_name == "store.Save"
        ]
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0].target_id)
        self.assertEqual(calls[1].target_id, save.id)

    def test_go_named_results_shadow_package_functions_but_unnamed_do_not(self) -> None:
        source = '''package p
func run(){}
func stop(){}
func one() (run func()){ run(); return nil }
func many() (run, stop func()){ run(); stop(); return nil, nil }
func unnamed() (func(), error){ run(); return nil, nil }
'''
        file = file_record("p/results.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        symbols = {item.id: item for item in result.symbols}
        package_run = next(
            item.id
            for item in result.symbols
            if item.kind == "function" and item.name == "run"
        )
        calls = {
            (symbols[item.source_id].name, item.target_name): item
            for item in relationships
            if item.kind == "calls" and item.target_name in {"run", "stop"}
        }
        self.assertIsNone(calls[("one", "run")].target_id)
        self.assertIsNone(calls[("many", "run")].target_id)
        self.assertIsNone(calls[("many", "stop")].target_id)
        self.assertEqual(calls[("unnamed", "run")].target_id, package_run)

    def test_go_statement_initializer_scope_ends_after_if(self) -> None:
        source = '''package p
func run(){}
func maker() func(){ return nil }
func f(){ if run := maker(); run != nil { run() }; run() }
'''
        file = file_record("p/if_scope.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        package_run = next(
            item.id
            for item in result.symbols
            if item.kind == "function" and item.name == "run"
        )
        calls = [
            item
            for item in relationships
            if item.kind == "calls" and item.target_name == "run"
        ]
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0].target_id)
        self.assertEqual(calls[1].target_id, package_run)

    def test_go_short_declaration_rhs_precedes_new_binding_scope(self) -> None:
        source = '''package p
func run() func() { return nil }
func maker() any { return nil }
func single(){
    run := run();
    run()
}
func multiple(){
    run, other := run(), maker();
    run()
    _ = other
}
'''
        file = file_record("p/short_rhs.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        symbols = {item.id: item for item in result.symbols}
        package_run = next(
            item.id
            for item in result.symbols
            if item.kind == "function" and item.name == "run"
        )
        by_source: dict[str, list[RelationshipRecord]] = {}
        for item in relationships:
            if item.kind == "calls" and item.target_name == "run":
                by_source.setdefault(symbols[item.source_id].name, []).append(item)
        for calls in by_source.values():
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0].target_id, package_run)
            self.assertIsNone(calls[1].target_id)

    def test_go_for_initializer_scope_covers_header_and_body_but_not_after(self) -> None:
        source = '''package p
func run() func() bool { return nil }
func maker() func() bool { return nil }
func values() []func() bool { return nil }
func f(){
    for run := run();
        run();
        run = maker() {
        run()
    }
    run()
}
func rangeLoop(){
    for _, values := range values() {
        values()
    }
    values()
}
'''
        file = file_record("p/for_scope.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        package_run = next(
            item.id
            for item in result.symbols
            if item.kind == "function" and item.name == "run"
        )
        calls = [
            item
            for item in relationships
            if item.kind == "calls" and item.target_name == "run"
        ]
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0].target_id, package_run)
        self.assertTrue(all(item.target_id is None for item in calls[1:3]))
        self.assertEqual(calls[3].target_id, package_run)

        package_values = next(
            item.id
            for item in result.symbols
            if item.kind == "function" and item.name == "values"
        )
        values_calls = [
            item
            for item in relationships
            if item.kind == "calls" and item.target_name == "values"
        ]
        self.assertEqual(len(values_calls), 3)
        self.assertEqual(values_calls[0].target_id, package_values)
        self.assertIsNone(values_calls[1].target_id)
        self.assertEqual(values_calls[2].target_id, package_values)

    def test_go_switch_and_type_switch_bindings_end_after_statement(self) -> None:
        source = '''package p
func run() func() bool { return nil }
func maker() func() bool { return nil }
func value() any { return nil }
func expressionSwitch(){
    switch run := run(); run() {
    default:
        run()
    }
    run()
}
func typeSwitch(){
    switch value := value().(type) {
    case func():
        value()
    }
    value()
}
'''
        file = file_record("p/switch_scope.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        symbols = {item.id: item for item in result.symbols}
        package_run = next(
            item.id
            for item in result.symbols
            if item.kind == "function" and item.name == "run"
        )
        package_value = next(
            item.id
            for item in result.symbols
            if item.kind == "function" and item.name == "value"
        )
        by_source: dict[tuple[str, str], list[RelationshipRecord]] = {}
        for item in relationships:
            if item.kind == "calls" and item.target_name in {"run", "value"}:
                key = (symbols[item.source_id].name, item.target_name)
                by_source.setdefault(key, []).append(item)
        expression_calls = by_source[("expressionSwitch", "run")]
        self.assertEqual(len(expression_calls), 4)
        self.assertEqual(expression_calls[0].target_id, package_run)
        self.assertTrue(all(item.target_id is None for item in expression_calls[1:3]))
        self.assertEqual(expression_calls[3].target_id, package_run)

        type_switch_calls = by_source[("typeSwitch", "value")]
        self.assertEqual(len(type_switch_calls), 3)
        self.assertEqual(type_switch_calls[0].target_id, package_value)
        self.assertIsNone(type_switch_calls[1].target_id)
        self.assertEqual(type_switch_calls[2].target_id, package_value)

    def test_go_function_literal_named_results_have_literal_scope(self) -> None:
        source = '''package p
func run(){}
func stop(){}
func one(){
    _ = func() (run func()){
        run()
        return nil
    }
    run()
}
func many(){
    _ = func() (run, stop func()){
        run()
        stop()
        return nil, nil
    }
    run()
    stop()
}
func unnamed(){
    _ = func() (func(), error){
        run()
        return nil, nil
    }
}
'''
        file = file_record("p/literal_results.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        symbols = {item.id: item for item in result.symbols}
        package_functions = {
            item.name: item.id
            for item in result.symbols
            if item.kind == "function" and item.name in {"run", "stop"}
        }
        by_source: dict[str, list[RelationshipRecord]] = {}
        for item in relationships:
            if item.kind == "calls" and item.target_name in {"run", "stop"}:
                by_source.setdefault(symbols[item.source_id].name, []).append(item)

        self.assertIsNone(by_source["one"][0].target_id)
        self.assertEqual(by_source["one"][1].target_id, package_functions["run"])
        self.assertTrue(all(item.target_id is None for item in by_source["many"][:2]))
        self.assertEqual(by_source["many"][2].target_id, package_functions["run"])
        self.assertEqual(by_source["many"][3].target_id, package_functions["stop"])
        self.assertEqual(by_source["unnamed"][0].target_id, package_functions["run"])

    def test_go_function_literal_named_result_overrides_outer_receiver_type(self) -> None:
        source = '''package p
type Store struct{}
type Other struct{}
func (Store) Save(){}
func (Other) Save(){}
func receiver(store *Store){
    _ = func() (store *Other){ store.Save(); return nil }
    store.Save()
}
'''
        file = file_record("p/literal_receiver_result.go", "Go")
        result = analyze_file(file, source)
        relationships = list(result.relationships)
        resolve_go_relationships(relationships, result.symbols, [file])

        methods = {
            item.qualified_name: item.id
            for item in result.symbols
            if item.kind == "method"
        }
        calls = [
            item
            for item in relationships
            if item.kind == "calls" and item.target_name == "store.Save"
        ]
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].target_id, methods["Other.Save"])
        self.assertEqual(calls[1].target_id, methods["Store.Save"])

    def test_go_malformed_delimiters_are_diagnostic(self) -> None:
        result = analyze_file(
            file_record("p/broken.go", "Go"), "package p\nfunc Good(){ Target()\n"
        )
        self.assertIn("go-unclosed-delimiter", {item.code for item in result.diagnostics})

    def test_analyzer_exception_isolated_to_one_file(self) -> None:
        with patch("repo_teacher.analyzers.analyze_go", side_effect=RuntimeError("boom")):
            result = analyze_file(file_record("p/broken.go", "Go"), "package p")
        self.assertFalse(result.symbols)
        self.assertEqual(result.diagnostics[0].code, "analyzer-file-failure")

    def test_gopls_adapter_is_explicit_and_absence_is_safe(self) -> None:
        adapter = GoplsAdapter("/definitely/missing/gopls")
        report = adapter.differential(Path("p.go"), (), workspace=Path("."))
        self.assertFalse(report.available)
        self.assertEqual(report.fallback_count, 0)

    def test_gopls_differential_preserves_same_leaf_declaration_occurrences(self) -> None:
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            source_file = workspace / "p.go"
            source_file.write_text(
                '''package p
type Reader interface {
    Run()
}
type Writer interface {
    Run()
}
''',
                encoding="utf-8",
            )
            fallback = analyze_file(
                file_record("p.go", "Go"), source_file.read_text(encoding="utf-8")
            ).symbols
            path = "p.go"
            uri = source_file.resolve().as_uri()
            semantic = [
                GoplsSymbol("Reader", "Reader", "interface", 2, 6, 2, 12, 0, path, uri),
                GoplsSymbol("Run", "Reader.Run", "interface-method", 3, 5, 3, 8, 1, path, uri),
                GoplsSymbol("Writer", "Writer", "interface", 5, 6, 5, 12, 0, path, uri),
                GoplsSymbol("Run", "Writer.Run", "interface-method", 6, 5, 6, 8, 1, path, uri),
            ]
            adapter = GoplsAdapter(sys.executable)
            with patch.object(adapter, "document_symbols", return_value=semantic):
                report = adapter.differential(
                    source_file, fallback, workspace=workspace
                )

            self.assertEqual(report.gopls_count, 4)
            self.assertEqual(report.fallback_count, 4)
            self.assertEqual(report.matched, 4)
            self.assertEqual(report.missing, ())
            self.assertEqual(report.extra, ())
            self.assertEqual(report.sample_manifest[0].path, "p.go")
            self.assertEqual(report.sample_manifest[0].matched, 4)

            with patch.object(adapter, "document_symbols", return_value=semantic[:-1]):
                missing_occurrence = adapter.differential(
                    source_file, fallback, workspace=workspace
                )
            self.assertEqual(missing_occurrence.gopls_count, 3)
            self.assertEqual(missing_occurrence.fallback_count, 4)
            self.assertEqual(missing_occurrence.matched, 3)
            self.assertIn("Writer.Run", missing_occurrence.extra[0])

    def test_gopls_spread_sample_is_deterministic_and_keeps_boundaries(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = [root / f"{index:03}.go" for index in range(100)]
            sample = GoplsAdapter.spread_sample(files, size=30)

            self.assertEqual(len(sample), 30)
            self.assertEqual(sample[0], files[0].resolve())
            self.assertEqual(sample[-1], files[-1].resolve())
            self.assertEqual(sample, GoplsAdapter.spread_sample(files, size=30))

    def test_sourcebridge_30_file_gopls_occurrence_golden(self) -> None:
        root = Path("/Volumes/T7/workspace/ontology/graph/repo/sourcebridge")
        adapter = GoplsAdapter("gopls", timeout=30)
        if not (root / ".git").exists() or not adapter.available:
            self.skipTest("SourceBridge reference clone or gopls is unavailable")

        scan = scan_repository(root, ScanOptions())
        go_files = [item for item in scan.files if item.language == "Go"]
        sample_paths = adapter.spread_sample(
            [root / item.path for item in go_files], size=30
        )
        sample_relative = {
            item.relative_to(root).as_posix() for item in sample_paths
        }
        fallback: list[SymbolRecord] = []
        for file in go_files:
            if file.path not in sample_relative:
                continue
            fallback.extend(analyze_file(file, scan.contents[file.path]).symbols)

        report = adapter.differential_sample(
            sample_paths,
            fallback,
            workspace=root,
            size=30,
        )

        self.assertEqual(len(report.sample_manifest), 30)
        self.assertEqual(report.gopls_count, 451)
        self.assertEqual(report.fallback_count, 451)
        self.assertEqual(report.matched, 451)
        self.assertEqual(report.missing, ())
        self.assertEqual(report.extra, ())


if __name__ == "__main__":
    unittest.main()
