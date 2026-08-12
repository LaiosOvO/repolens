from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_teacher.evidence import EvidenceStore
from repo_teacher.features import _find_node_runtime, discover_features
from repo_teacher.indexer import build_index
from repo_teacher.models import FileRecord, ModuleSummary, RelationshipRecord, SymbolRecord, stable_id
from repo_teacher.report import render_report
from repo_teacher.validation import validate_index


class FeatureDiscoveryTest(unittest.TestCase):
    def test_node_runtime_discovery_uses_the_login_shell_for_external_nvm(self) -> None:
        _find_node_runtime.cache_clear()
        with tempfile.TemporaryDirectory() as directory:
            node = Path(directory) / "node"
            node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            node.chmod(0o755)
            completed = subprocess.CompletedProcess(
                args=["zsh"], returncode=0, stdout=f"{node}\n", stderr=""
            )
            with (
                patch.dict("repo_teacher.features.os.environ", {"SHELL": "/bin/zsh"}, clear=True),
                patch("repo_teacher.features.shutil.which", return_value=None),
                patch("repo_teacher.features.subprocess.run", return_value=completed) as run,
            ):
                discovered = _find_node_runtime()

            self.assertEqual(discovered, str(node.resolve()))
            run.assert_called_once_with(
                ["/bin/zsh", "-ilc", "command -v node"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=20.0,
                check=False,
            )
        _find_node_runtime.cache_clear()

    def test_discovers_cli_command_and_follows_resolved_call_path(self) -> None:
        cli_source = """import argparse
from .worker import run_job

def parser():
    commands = argparse.ArgumentParser().add_subparsers()
    commands.add_parser("index")

def _index():
    return run_job()
"""
        worker_source = """def run_job():
    return persist_job()

def persist_job():
    return 1
"""
        cli_file = FileRecord(stable_id("file", "cli.py"), "cli.py", "Python", len(cli_source), 9, "a")
        worker_file = FileRecord(stable_id("file", "worker.py"), "worker.py", "Python", len(worker_source), 5, "b")
        index_symbol = SymbolRecord(
            stable_id("symbol", "cli.py", "_index"), cli_file.id, "cli.py", "_index", "_index", "function", 8, 9,
            "python-ast", "exact",
        )
        worker_symbol = SymbolRecord(
            stable_id("symbol", "worker.py", "run_job"), worker_file.id, "worker.py", "run_job", "run_job", "function", 1, 2,
            "python-ast", "exact",
        )
        persist_symbol = SymbolRecord(
            stable_id("symbol", "worker.py", "persist_job"), worker_file.id, "worker.py", "persist_job", "persist_job",
            "function", 4, 5, "python-ast", "exact",
        )
        call = RelationshipRecord(
            stable_id("rel", "calls", index_symbol.id, worker_symbol.id), index_symbol.id, worker_symbol.id, "run_job",
            "calls", "cli.py", 9, "python-ast", "heuristic",
        )
        transitive_call = RelationshipRecord(
            stable_id("rel", "calls", worker_symbol.id, persist_symbol.id), worker_symbol.id, persist_symbol.id,
            "persist_job", "calls", "worker.py", 2, "python-ast", "heuristic",
        )
        contents = {"cli.py": cli_source, "worker.py": worker_source, "tests/test_cli.py": "def test_index():\n    pass\n"}
        test_file = FileRecord(stable_id("file", "tests/test_cli.py"), "tests/test_cli.py", "Python", 32, 2, "c", "tests")
        evidence = EvidenceStore(contents)

        features = discover_features(
            [cli_file, worker_file, test_file],
            [index_symbol, worker_symbol, persist_symbol],
            [call, transitive_call],
            [ModuleSummary(stable_id("module", "root"), "root", ".", 2, 2, {"Python": 2})],
            contents,
            evidence,
        )

        command = next(feature for feature in features if feature.entrypoint == "index")
        self.assertEqual(command.kind, "cli-command")
        self.assertEqual(command.confidence, "exact-entry")
        self.assertEqual(command.entry_symbol_id, index_symbol.id)
        self.assertEqual([step.symbol_id for step in command.steps[:2]], [index_symbol.id, worker_symbol.id])
        self.assertEqual(
            [step.relationship_id for step in command.steps[:2]],
            [call.id, call.id],
        )
        self.assertNotIn(persist_symbol.id, [step.symbol_id for step in command.steps])
        self.assertIn("已解析调用端点", command.steps[0].title)
        self.assertIn("已解析调用目标", command.steps[1].title)
        self.assertIn("不是运行时执行顺序", command.summary)
        self.assertTrue(command.evidence_ids)
        self.assertFalse(command.test_evidence_ids)
        self.assertTrue(all(evidence.validate(item) for item in evidence.records))

    def test_build_index_includes_routes_features_and_grounded_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                'from fastapi import FastAPI\napp = FastAPI()\n\n@app.get("/users")\ndef users():\n    return list_users()\n\ndef list_users():\n    return []\n',
                encoding="utf-8",
            )

            result = build_index(root)

            self.assertEqual(result["schema_version"], "2.0")
            route = next(feature for feature in result["features"] if feature["entrypoint"] == "GET /users")
            self.assertEqual(route["kind"], "http-route")
            self.assertTrue(route["steps"])
            evidence_by_id = {item["id"]: item for item in result["evidence"]}
            self.assertTrue(all(identifier in evidence_by_id for identifier in route["evidence_ids"]))

    def test_docs_and_tests_cannot_become_product_features(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "tests").mkdir()
            (root / "docs" / "fastapi.md").write_text('@app.post("/token")\n', encoding="utf-8")
            (root / "tests" / "test_routes.py").write_text('@app.get("/fake")\ndef fake(): pass\n', encoding="utf-8")
            (root / "app.py").write_text(
                'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/real")\ndef real(): return 1\n',
                encoding="utf-8",
            )

            result = build_index(root)
            entrypoints = {item["entrypoint"] for item in result["features"]}

            self.assertIn("GET /real", entrypoints)
            self.assertNotIn("POST /token", entrypoints)
            self.assertNotIn("GET /fake", entrypoints)
            real = next(item for item in result["features"] if item["entrypoint"] == "GET /real")
            self.assertEqual(real["confidence"], "exact-entry")
            feature_evidence = [
                item for item in result["evidence"] if item["id"] in real["evidence_ids"]
            ]
            self.assertIn("entry-declaration", {item["kind"] for item in feature_evidence})

    def test_arbitrary_run_and_start_methods_are_not_public_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "worker.py").write_text(
                "class Worker:\n    def run(self): return 1\n\ndef start(): return 2\n",
                encoding="utf-8",
            )
            (root / "server.py").write_text("def run(): return 3\n", encoding="utf-8")
            (root / "main.py").write_text("def main(): return 0\n", encoding="utf-8")

            result = build_index(root)
            entries = [item for item in result["features"] if item["kind"] == "entrypoint"]

            self.assertEqual(entries, [])
            candidates = [item for item in result["features"] if item["kind"] == "entrypoint-candidate"]
            self.assertEqual({item["entrypoint"] for item in candidates}, {"main", "run"})
            main_candidate = next(item for item in candidates if item["entrypoint"] == "main")
            self.assertEqual(main_candidate["confidence"], "candidate")
            candidate_evidence = next(
                item for item in result["evidence"]
                if item["id"] in main_candidate["evidence_ids"] and item["kind"] == "entry-candidate"
            )
            self.assertEqual(candidate_evidence["kind"], "entry-candidate")

    def test_direct_test_reference_is_not_reported_as_behavioral_coverage(self) -> None:
        app_source = "def main():\n    return 1\n"
        test_source = "from app import main\n\ndef test_main():\n    assert main() == 1\n"
        app_file = FileRecord(stable_id("file", "main.py"), "main.py", "Python", len(app_source), 2, "a")
        test_file = FileRecord(
            stable_id("file", "tests/test_main.py"), "tests/test_main.py", "Python", len(test_source), 4, "b", "tests"
        )
        main_symbol = SymbolRecord(
            stable_id("symbol", "main.py", "main"), app_file.id, "main.py", "main", "main", "function", 1, 2,
            "python-ast", "exact", exported=True,
        )
        test_symbol = SymbolRecord(
            stable_id("symbol", "tests/test_main.py", "test_main"), test_file.id, "tests/test_main.py", "test_main",
            "test_main", "function", 3, 4, "python-ast", "exact", exported=True,
        )
        reference = RelationshipRecord(
            stable_id("rel", "calls", test_symbol.id, main_symbol.id), test_symbol.id, main_symbol.id, "main", "calls",
            "tests/test_main.py", 4, "python-ast", "heuristic",
        )
        evidence = EvidenceStore({"main.py": app_source, "tests/test_main.py": test_source})

        features = discover_features(
            [app_file, test_file], [main_symbol, test_symbol], [reference],
            [ModuleSummary(stable_id("module", "root"), "root", ".", 1, 1, {"Python": 1})],
            {"main.py": app_source, "tests/test_main.py": test_source}, evidence,
        )

        entry = next(item for item in features if item.entrypoint == "main")
        self.assertEqual(len(entry.test_evidence_ids), 1)
        test_reference = next(item for item in evidence.records if item.id == entry.test_evidence_ids[0])
        self.assertEqual(test_reference.kind, "test-reference")
        self.assertEqual(test_reference.confidence, "heuristic")

    def test_reference_shaped_ground_truth_entrypoints(self) -> None:
        fixtures = {
            "sourcebridge": {
                "cmd/sourcebridge/main.go": "package main\nfunc main() { Execute() }\nfunc Execute() {}\n",
                "internal/worker/runner.go": "package worker\ntype Worker struct{}\nfunc (w Worker) Run() {}\n",
            },
            "pocketflow-code2tutorial": {
                "main.py": "def main():\n    return create_tutorial_flow()\n\nif __name__ == '__main__':\n    main()\n",
                "flow.py": "def create_tutorial_flow():\n    return object()\n",
            },
            "deepwiki-open": {
                "api/main.py": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef root():\n    return {'ok': True}\n",
                "api/services/codemap.py": "def run():\n    return 'map'\n",
            },
            "openwiki": {
                "src/cli/cli.tsx": "#!/usr/bin/env node\nconst parsed = parseCommand(process.argv);\n",
                "src/agent/index.ts": "export function run() { return 1 }\n",
            },
        }
        expected = {
            "sourcebridge": {"main"},
            "pocketflow-code2tutorial": {"main"},
            "deepwiki-open": {"GET /"},
            "openwiki": {"src/cli/cli.tsx"},
        }
        for project, files in fixtures.items():
            with self.subTest(project=project), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative, source in files.items():
                    destination = root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(source, encoding="utf-8")
                result = build_index(root)
                entrypoints = {item["entrypoint"] for item in result["features"]}
                self.assertTrue(expected[project].issubset(entrypoints))
                confirmed = {
                    item["entrypoint"] for item in result["features"]
                    if item["kind"] != "entrypoint-candidate"
                }
                self.assertNotIn("run", confirmed)

    def test_comments_and_string_literals_cannot_forge_routes_or_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                'EXAMPLE = \'@app.get("/fake-string")\'\n'
                '# @app.post("/fake-comment")\n'
                'from fastapi import FastAPI\n'
                'app = FastAPI()\n'
                '@app.get("/real")\ndef real(): return 1\n',
                encoding="utf-8",
            )
            (root / "server.ts").write_text(
                "import express from 'express';\n"
                'const example = \'router.get("/fake-js-string", handler)\';\n'
                '// router.post("/fake-js-comment", handler);\n'
                'const pattern = /router\\.delete\\(\"\\/fake-js-regex\"\\)/;\n'
                'const cliExample = \'program.command("fake-js-command")\';\n'
                'const router = express.Router();\n'
                'router.get("/real-js", handler);\n',
                encoding="utf-8",
            )

            result = build_index(root)
            entries = {item["entrypoint"] for item in result["features"]}

            self.assertIn("GET /real", entries)
            self.assertIn("GET /real-js", entries)
            self.assertNotIn("GET /fake-string", entries)
            self.assertNotIn("POST /fake-comment", entries)
            self.assertNotIn("GET /fake-js-string", entries)
            self.assertNotIn("POST /fake-js-comment", entries)
            self.assertNotIn("DELETE /fake-js-regex", entries)
            self.assertNotIn("fake-js-command", entries)

    def test_client_calls_unrelated_commands_and_wrong_go_package_are_not_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                'from fastapi import APIRouter\n'
                'from typer import Typer\n'
                'router = APIRouter()\n'
                'cli = Typer()\n'
                'requests.get("/private")\n'
                'client.post("/upload")\n'
                'database.command("vacuum")\n'
                'router.get("/real")\n'
                'cli.command("index")\n',
                encoding="utf-8",
            )
            (root / "server.ts").write_text(
                "import express from 'express'; import { Command } from 'commander';\n"
                'const router = express.Router(); const program = new Command();\n'
                'const ratio = left / right; router.get("/real-js", handler);\n'
                'const pattern = /database\\.command\\("fake"\\)/;\n'
                'database.command("compact");\n'
                'program.command("serve");\n',
                encoding="utf-8",
            )
            (root / "main.go").write_text(
                "package helper\nfunc main() {}\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entries = {item["entrypoint"] for item in result["features"]}

            self.assertIn("GET /real", entries)
            self.assertIn("GET /real-js", entries)
            self.assertIn("index", entries)
            self.assertIn("serve", entries)
            self.assertNotIn("GET /private", entries)
            self.assertNotIn("POST /upload", entries)
            self.assertNotIn("vacuum", entries)
            self.assertNotIn("compact", entries)
            self.assertNotIn("fake", entries)
            self.assertFalse(
                any(
                    item["kind"] == "entrypoint" and item["entrypoint"] == "main"
                    for item in result["features"]
                )
            )

    def test_framework_binding_not_receiver_spelling_controls_python_and_js_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "import httpx\n"
                "from fastapi import FastAPI\n"
                "from typer import Typer\n\n"
                "app = httpx.Client()\n"
                'app.get("/private")\n'
                "program = object()\n"
                'program.command("vacuum")\n'
                "service = FastAPI()\n"
                "tool = Typer()\n"
                '@service.post("/jobs")\n'
                "def jobs(): return {}\n"
                '@tool.command("sync")\n'
                "def sync(): return None\n",
                encoding="utf-8",
            )
            (root / "server.ts").write_text(
                "import express from 'express';\n"
                "import fastify from 'fastify';\n"
                "import Router from '@koa/router';\n"
                "import { Command } from 'commander';\n"
                "import axios from 'axios';\n"
                "const app = axios.create(); app.post('/upload');\n"
                "const program = database; program.command('compact');\n"
                "const service = express(); service.get('/health', handler);\n"
                "const api = fastify(); api.patch('/jobs/:id', handler);\n"
                "const router = new Router(); router.delete('/jobs/:id', handler);\n"
                "const tool = new Command(); tool.command('serve');\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entries = {item["entrypoint"]: item for item in result["features"]}

            self.assertNotIn("GET /private", entries)
            self.assertNotIn("vacuum", entries)
            self.assertNotIn("POST /upload", entries)
            self.assertNotIn("compact", entries)
            self.assertEqual(entries["POST /jobs"]["confidence"], "exact-entry")
            self.assertEqual(entries["sync"]["confidence"], "exact-entry")
            self.assertEqual(entries["GET /health"]["confidence"], "static-entry")
            self.assertEqual(entries["PATCH /jobs/:id"]["confidence"], "static-entry")
            self.assertEqual(entries["DELETE /jobs/:id"]["confidence"], "static-entry")
            self.assertEqual(entries["serve"]["confidence"], "static-entry")

    def test_unresolved_framework_shaped_calls_are_not_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text('@router.get("/maybe")\ndef maybe(): return 1\n', encoding="utf-8")
            (root / "server.ts").write_text("program.command('maybe');\n", encoding="utf-8")

            result = build_index(root)
            entrypoints = {item["entrypoint"] for item in result["features"]}

            self.assertNotIn("GET /maybe", entrypoints)
            self.assertNotIn("maybe", entrypoints)

    def test_commonjs_framework_provenance_recalls_servers_and_cli_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.js").write_text(
                "const express = require('express');\n"
                "const app = express(); app.get('/express', handler);\n"
                "const fastify = require('fastify')(); fastify.post('/fastify', handler);\n"
                "const Router = require('@koa/router'); const router = new Router(); router.get('/koa', handler);\n"
                "const { Command } = require('commander'); const program = new Command(); program.command('serve');\n"
                "const Cmd = require('commander').Command; const tool = new Cmd(); tool.command('sync');\n"
                "const axios = require('axios'); const client = axios.create(); client.get('/private');\n"
                "const ordinary = {}; ordinary.get('/ordinary', handler); ordinary.command('compact');\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entries = {item["entrypoint"]: item for item in result["features"]}

            for entrypoint in {"GET /express", "POST /fastify", "GET /koa", "serve", "sync"}:
                self.assertEqual(entries[entrypoint]["confidence"], "static-entry")
            for entrypoint in {"GET /private", "GET /ordinary", "compact"}:
                self.assertNotIn(entrypoint, entries)

    def test_framework_provenance_is_lexical_ordered_and_killed_by_reassignment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "import httpx\n"
                "from fastapi import FastAPI\n"
                "from typer import Typer\n"
                "app = httpx.Client()\n"
                "app.get('/python-client')\n"
                "def register():\n"
                "    app = FastAPI()\n"
                "    @app.get('/python-inner')\n"
                "    def inner(): return 1\n"
                "@app.get('/python-unbound')\n"
                "def unbound(): return 2\n"
                "app = FastAPI()\n"
                "@app.get('/python-live')\n"
                "def live(): return 3\n"
                "app = object()\n"
                "app.get('/python-killed')\n"
                "def configure():\n"
                "    program = Typer()\n"
                "    @program.command('python-inner-command')\n"
                "    def inner_command(): return None\n"
                "program.command('python-outer-command')\n"
                "conditional = object()\n"
                "if enabled:\n"
                "    conditional = FastAPI()\n"
                "    conditional.get('/python-branch-local')\n"
                "conditional.get('/python-conditional')\n",
                encoding="utf-8",
            )
            (root / "server.ts").write_text(
                "import express from 'express';\n"
                "import axios from 'axios';\n"
                "import { Command } from 'commander';\n"
                "const app = axios.create();\n"
                "{ const app = express(); app.get('/js-inner', handler); }\n"
                "app.get('/js-client', handler);\n"
                "let service = express(); service.get('/js-live', handler);\n"
                "service = {}; service.get('/js-killed', handler);\n"
                "function configure() { const program = new Command(); program.command('js-inner-command'); }\n"
                "program.command('js-outer-command');\n"
                "let tool = new Command(); tool.command('serve');\n"
                "tool = {}; tool.command('js-killed-command');\n"
                "let conditional = axios.create();\n"
                "if (enabled) { conditional = express(); conditional.get('/js-branch-local', handler); }\n"
                "conditional.get('/js-conditional', handler);\n"
                "const use = (app) => { app.get('/js-arrow-parameter', handler); };\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entries = {item["entrypoint"]: item for item in result["features"]}

            for entrypoint in {
                "GET /python-inner",
                "GET /python-live",
                "python-inner-command",
                "GET /js-live",
                "js-inner-command",
                "serve",
            }:
                self.assertIn(entrypoint, entries)
            for entrypoint in {
                "GET /python-client",
                "GET /python-unbound",
                "GET /python-killed",
                "python-outer-command",
                "GET /js-client",
                "GET /js-killed",
                "js-outer-command",
                "js-killed-command",
                "GET /python-conditional",
                "GET /js-conditional",
                "GET /js-arrow-parameter",
                "GET /js-inner",
                "GET /python-branch-local",
                "GET /js-branch-local",
            }:
                self.assertNotIn(entrypoint, entries)

    def test_confirmed_boundaries_keep_narrow_framework_claim_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "@app.get('/health')\n"
                "def health(): return {}\n"
                "def register():\n"
                "    local = FastAPI()\n"
                "    local.get('/python-same-function')\n"
                "late = lambda: app.get('/python-lambda-late-false')\n"
                "stored = [lambda: app.get('/python-stored-callback-false')]\n"
                "def outer():\n"
                "    nested_app = FastAPI()\n"
                "    def deferred(): nested_app.get('/python-returned-callback-false')\n"
                "    return deferred\n"
                "def generator():\n"
                "    generator_app = FastAPI()\n"
                "    generator_app.get('/python-generator-false')\n"
                "    yield 1\n"
                "app = object()\n",
                encoding="utf-8",
            )
            (root / "server.js").write_text(
                "const express = require('express');\n"
                "const app = express(); app.post('/jobs', handler);\n"
                "const { Command } = require('commander');\n"
                "const program = new Command(); program.command('serve');\n"
                "function register() { const local = express(); local.get('/js-same-function', handler); }\n"
                "const late = () => app.get('/js-arrow-late-false', handler);\n"
                "const stored = [() => app.get('/js-stored-callback-false', handler)];\n"
                "function outer() { const nested = express(); function deferred() { nested.get('/js-returned-callback-false', handler); } return deferred; }\n"
                "function* generator() { const generated = express(); generated.get('/js-generator-false', handler); yield 1; }\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entries = {item["entrypoint"]: item for item in result["features"]}
            evidence = {item["id"]: item for item in result["evidence"]}
            expected = {
                "GET /health": ("fastapi", "fastapi", "FastAPI"),
                "GET /python-same-function": ("fastapi", "fastapi", "FastAPI"),
                "POST /jobs": ("express", "express", "default"),
                "GET /js-same-function": ("express", "express", "default"),
                "serve": ("commander", "commander", "Command"),
            }
            for entrypoint, (framework, module, factory) in expected.items():
                with self.subTest(entrypoint=entrypoint):
                    claim = next(
                        item
                        for item in entries[entrypoint]["technology_claims"]
                        if item["dimension"] == "framework"
                    )
                    self.assertEqual(claim["value"], framework)
                    self.assertGreaterEqual(len(claim["evidence_ids"]), 3)
                    claim_evidence = [evidence[identifier] for identifier in claim["evidence_ids"]]
                    self.assertTrue(
                        all(item["kind"] == "technology-claim:framework" for item in claim_evidence)
                    )
                    snippets = "\n".join(item["snippet"] for item in claim_evidence)
                    self.assertIn(module, snippets)
                    self.assertIn(framework if factory == "default" else factory, snippets)
                    self.assertIn(entrypoint.split(" ", 1)[-1], snippets)
                    self.assertTrue(all(item["snippet_sha256"] for item in claim_evidence))
                    self.assertIn(f"module `{module}`", claim["claim_scope"])
                    self.assertIn(f"factory `{factory}`", claim["claim_scope"])

            false_fragments = {
                "/python-lambda-late-false",
                "/python-stored-callback-false",
                "/js-arrow-late-false",
                "/js-stored-callback-false",
                "/python-returned-callback-false",
                "/python-generator-false",
                "/js-returned-callback-false",
                "/js-generator-false",
            }
            self.assertTrue(false_fragments.isdisjoint(entries))
            all_evidence = "\n".join(item["snippet"] for item in result["evidence"])
            report = render_report(result)
            for fragment in false_fragments:
                self.assertNotIn(fragment, all_evidence)
                self.assertNotIn(fragment, report)

    def test_python_binding_ir_covers_scopes_kills_and_control_flow_joins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "from contextlib import nullcontext\n"
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "app.get('/module-live')\n"
                "shadow = lambda app: app.get('/lambda-false')\n"
                "[app.get('/comprehension-false') for app in clients]\n"
                "app.get('/after-comprehension-live')\n"
                "lambda_body = lambda: (app := object())\n"
                "app.get('/after-lambda-body-live')\n"
                "def nested_body():\n"
                "    items = [(app := object()) for item in clients]\n"
                "app.get('/after-nested-function-body-live')\n"
                "lambda_readonly = lambda: app.get('/lambda-readonly-live')\n"
                "nested_lambda_readonly = lambda: (lambda: app.get('/nested-lambda-readonly-live'))\n"
                "lambda_parent_default = lambda value=(alias := app): app.get('/lambda-parent-default-live')\n"
                "with nullcontext(object()) as app:\n"
                "    app.get('/with-false')\n"
                "app.get('/after-with-false')\n"
                "app = FastAPI()\n"
                "try:\n"
                "    raise RuntimeError()\n"
                "except RuntimeError as app:\n"
                "    app.get('/except-false')\n"
                "app.get('/after-except-false')\n"
                "app = FastAPI()\n"
                "del app\n"
                "app.get('/deleted-false')\n"
                "app = object()\n"
                "try:\n"
                "    app = FastAPI()\n"
                "except RuntimeError:\n"
                "    pass\n"
                "app.get('/try-join-false')\n"
                "app = object()\n"
                "match payload:\n"
                "    case {'enabled': True}:\n"
                "        app = FastAPI()\n"
                "app.get('/match-join-false')\n"
                "match payload:\n"
                "    case {'app': app}:\n"
                "        app.get('/match-capture-false')\n"
                "app = object()\n"
                "enabled and (app := FastAPI())\n"
                "app.get('/walrus-short-circuit-false')\n"
                "service = FastAPI()\n"
                "if enabled:\n"
                "    joined = service\n"
                "else:\n"
                "    joined = service\n"
                "joined.get('/same-provenance-live')\n"
                "class Holder:\n"
                "    app = object()\n"
                "    def register(self):\n"
                "        service.get('/class-nonclosure-live')\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entries = {item["entrypoint"] for item in result["features"]}

            for entrypoint in {
                "GET /module-live",
                "GET /after-comprehension-live",
                "GET /after-lambda-body-live",
                "GET /after-nested-function-body-live",
            }:
                self.assertIn(entrypoint, entries)
            for entrypoint in {
                "GET /lambda-false",
                "GET /comprehension-false",
                "GET /with-false",
                "GET /after-with-false",
                "GET /except-false",
                "GET /after-except-false",
                "GET /deleted-false",
                "GET /try-join-false",
                "GET /match-join-false",
                "GET /match-capture-false",
                "GET /walrus-short-circuit-false",
                "GET /lambda-readonly-live",
                "GET /nested-lambda-readonly-live",
                "GET /lambda-parent-default-live",
                "GET /same-provenance-live",
                "GET /class-nonclosure-live",
            }:
                self.assertNotIn(entrypoint, entries)

    def test_javascript_binding_ir_covers_scopes_hoists_and_control_flow_joins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.js").write_text(
                "import express from 'express';\n"
                "import { Command } from 'commander';\n"
                "const live = express();\n"
                "live.get('/module-live', handler);\n"
                "try { throw failure; } catch (live) { live.get('/catch-false', handler); }\n"
                "for (const live of clients) { live.get('/for-false', handler); }\n"
                "for (const { app } of clients) app.get('/for-destructure-false', handler);\n"
                "class Controller { method(live = express()) { live.get('/class-method-false', handler); } }\n"
                "const registry = { method(live) { live.get('/object-method-false', handler); } };\n"
                "function hoisted() {\n"
                "  live.get('/before-var-false', handler);\n"
                "  if (enabled) { var live = {}; }\n"
                "  live.get('/after-var-false', handler);\n"
                "}\n"
                "const { app: destructured } = options;\n"
                "destructured.get('/destructure-false', handler);\n"
                "let reassigned = express();\n"
                "({ reassigned } = options);\n"
                "reassigned.get('/destructure-reassign-false', handler);\n"
                "let conditional = {};\n"
                "if (enabled) conditional = express();\n"
                "conditional.get('/brace-less-if-false', handler);\n"
                "const compound = express() && {};\n"
                "compound.get('/compound-false', handler);\n"
                "const selected = enabled ? express() : {};\n"
                "selected.get('/conditional-value-false', handler);\n"
                "const arrow = (live = express()) => live.get('/arrow-default-false', handler);\n"
                "const concise = live => live.get('/arrow-expression-false', handler);\n"
                "let joined;\n"
                "const service = express();\n"
                "if (enabled) { joined = service; } else { joined = service; }\n"
                "joined.get('/same-provenance-live', handler);\n"
                "const program = new Command();\n"
                "program.command('serve');\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entries = {item["entrypoint"] for item in result["features"]}

            for entrypoint in {"GET /module-live", "serve"}:
                self.assertIn(entrypoint, entries)
            for entrypoint in {
                "GET /catch-false",
                "GET /for-false",
                "GET /for-destructure-false",
                "GET /class-method-false",
                "GET /object-method-false",
                "GET /before-var-false",
                "GET /after-var-false",
                "GET /destructure-false",
                "GET /destructure-reassign-false",
                "GET /brace-less-if-false",
                "GET /compound-false",
                "GET /conditional-value-false",
                "GET /arrow-default-false",
                "GET /arrow-expression-false",
                "GET /same-provenance-live",
            }:
                self.assertNotIn(entrypoint, entries)

    def test_combined_scope_and_cfg_adversaries_never_become_framework_features(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lambda_body_cases = {
                "direct": "(app := object())",
                "boolop": "False or (app := object())",
                "binop": "(app := 1) + 1",
                "unaryop": "not (app := object())",
                "ifexp": "(app := object()) if enabled else other",
                "dict": "{'value': (app := object())}",
                "set": "{(app := object())}",
                "list": "[(app := object())]",
                "tuple": "((app := object()),)",
                "call-arg": "consume((app := object()))",
                "call-keyword": "consume(value=(app := object()))",
                "attribute": "(app := object()).value",
                "subscript": "values[(app := 0)]",
                "slice": "values[(app := 0):]",
                "starred": "[*[(app := object())]]",
                "listcomp": "[(app := object()) for item in clients]",
                "setcomp": "{(app := object()) for item in clients}",
                "dictcomp": "{item: (app := object()) for item in clients}",
                "generator": "((app := object()) for item in clients)",
                "yield": "(yield (app := object()))",
                "yieldfrom": "(yield from (app := values))",
                "joinedstr": "f'{(app := object())}'",
                "formattedvalue": "f'{(app := object())!r:>10}'",
                "nested-call": "consume(transform([(app := object()) for item in clients]))",
                "nested-lambda-default": "(lambda value=(app := object()): value)",
                "conditional": "(app := object()) if enabled else None",
            }
            lambda_body_source = "".join(
                f"probe_{position} = lambda: "
                f"(app.get('/lambda-{label}-walrus-false'), {expression})\n"
                for position, (label, expression) in enumerate(lambda_body_cases.items())
            )
            lambda_body_source += (
                "nested_lambda = lambda: "
                "(lambda: (app.get('/lambda-nested-body-walrus-false'), "
                "(app := object())))\n"
            )
            comprehension_expressions = {
                "listcomp": "[(app := object()) for item in clients]",
                "setcomp": "{(app := object()) for item in clients}",
                "dictcomp": "{item: (app := object()) for item in clients}",
                "generator": "((app := object()) for item in clients)",
            }
            assignment_statements = {
                "assign": "value = {expression}",
                "annassign": "value: object = {expression}",
                "augassign": "value += {expression}",
                "namedexpr": "consume((value := {expression}))",
            }
            round8_matrix_parts: list[str] = []
            round8_false_entrypoints: set[str] = set()
            for assignment, statement in assignment_statements.items():
                for container, expression in comprehension_expressions.items():
                    label = f"round8-{assignment}-{container}-false"
                    round8_false_entrypoints.add(f"GET /{label}")
                    round8_matrix_parts.extend(
                        (
                            f"def case_{assignment}_{container}():\n",
                            f"    app.get('/{label}')\n",
                            f"    {statement.format(expression=expression)}\n",
                        )
                    )
            for (assignment, statement), (container, expression) in zip(
                assignment_statements.items(), comprehension_expressions.items(), strict=True
            ):
                label = f"round8-nested-call-{assignment}-false"
                nested_expression = f"consume(transform({expression}))"
                round8_false_entrypoints.add(f"GET /{label}")
                round8_matrix_parts.extend(
                    (
                        f"def case_nested_call_{assignment}():\n",
                        f"    app.get('/{label}')\n",
                        f"    {statement.format(expression=nested_expression)}\n",
                    )
                )
            for container, expression in comprehension_expressions.items():
                for context in ("default", "decorator", "class-base"):
                    label = f"round8-{context}-{container}-false"
                    round8_false_entrypoints.add(f"GET /{label}")
                    round8_matrix_parts.extend(
                        (
                            f"def case_{context.replace('-', '_')}_{container}():\n",
                            f"    app.get('/{label}')\n",
                        )
                    )
                    if context == "default":
                        round8_matrix_parts.extend(
                            (
                                f"    def nested(value={expression}):\n",
                                "        return value\n",
                            )
                        )
                    elif context == "decorator":
                        round8_matrix_parts.extend(
                            (
                                f"    @decorate({expression})\n",
                                "    def nested():\n",
                                "        return None\n",
                            )
                        )
                    else:
                        round8_matrix_parts.extend(
                            (
                                f"    class Nested(resolve({expression})):\n",
                                "        pass\n",
                            )
                        )
            round8_matrix_source = "".join(round8_matrix_parts)
            class_comprehension_cases = {
                "list": "[app.get('/class-comp-list-false') for item in clients]",
                "set": "{app.get('/class-comp-set-false') for item in clients}",
                "dict-value": "{item: app.get('/class-comp-dict-value-false') for item in clients}",
                "dict-key": "{app.get('/class-comp-dict-key-false'): item for item in clients}",
                "generator": "(app.get('/class-comp-generator-false') for item in clients)",
                "filter": "[item for item in clients if app.get('/class-comp-filter-false')]",
                "nested": "[app.get('/class-comp-nested-false') for row in rows for item in row]",
                "call": "consume([app.get('/class-comp-call-false') for item in clients])",
                "tuple": "[(item, app.get('/class-comp-tuple-false')) for item in clients]",
                "iterable": "[item for item in app.get('/class-comp-iterable-false')]",
            }
            class_comprehension_source = "".join(
                f"class ClassComp{position}:\n"
                "    app = FastAPI()\n"
                f"    values = {expression}\n"
                for position, expression in enumerate(class_comprehension_cases.values())
            )
            (root / "app.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "def register():\n"
                "    app.get('/py-before-comp-walrus-false')\n"
                "    [(app := object()) for item in clients]\n"
                "def assign_list():\n"
                "    app.get('/py-before-assign-list-walrus-false')\n"
                "    items = [(app := object()) for item in clients]\n"
                "def annotated_generator():\n"
                "    app.get('/py-before-annassign-generator-walrus-false')\n"
                "    items: object = ((app := object()) for item in clients)\n"
                "def augmented_dict():\n"
                "    app.get('/py-before-augassign-dict-walrus-false')\n"
                "    items += {item: (app := object()) for item in clients}\n"
                "def namedexpr_nested_call():\n"
                "    app.get('/py-before-namedexpr-nested-call-false')\n"
                "    consume((shadow := (app := object())))\n"
                "def set_in_default():\n"
                "    app.get('/py-before-set-default-walrus-false')\n"
                "    def nested(items={(app := object()) for item in clients}):\n"
                "        return items\n"
                "def lambda_default():\n"
                "    app.get('/py-before-lambda-default-walrus-false')\n"
                "    factory = lambda value=(app := object()): value\n"
                "[(app := object()) for item in clients]\n"
                "app.get('/py-comp-walrus-false')\n"
                + lambda_body_source
                + round8_matrix_source
                + class_comprehension_source,
                encoding="utf-8",
            )
            (root / "await_lambda.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "async def build():\n"
                "    probe = lambda: "
                "(app.get('/lambda-await-walrus-false'), await consume((app := object())))\n"
                "    readonly = lambda: "
                "(app.get('/lambda-await-readonly-invalid-false'), await consume())\n",
                encoding="utf-8",
            )
            (root / "server.ts").write_text(
                "import express from 'express';\n"
                "const app = express();\n"
                "function typed<T>(app: Client) { app.get('/ts-param-false', handler); }\n"
                "const typedArrow = (app: Client): void => app.get('/ts-arrow-return-false', handler);\n"
                "class Controller { method<T>(app: Client): void { app.get('/ts-method-false', handler); } }\n"
                "for (app of clients) { app.get('/js-for-assign-false', handler); }\n"
                "for (const app: Client of clients) { app.get('/ts-for-typed-false', handler); }\n"
                "do { const app = {}; app.get('/js-do-shadow-false', handler); } while (enabled);\n"
                "switch (mode) { case 'x': { const app = {}; app.get('/js-switch-shadow-false', handler); break; } }\n",
                encoding="utf-8",
            )
            (root / "loop.js").write_text(
                "const express = require('express');\n"
                "function register(clients) {\n"
                "  var app = express();\n"
                "  for (var app of clients) {}\n"
                "  app.get('/js-for-var-after-false', handler);\n"
                "}\n",
                encoding="utf-8",
            )
            (root / "malformed.js").write_text(
                "const express = require('express');\n"
                "const app = express();\n"
                "app.get('/js-unclosed-false'\n",
                encoding="utf-8",
            )

            result = build_index(root)
            false_entrypoints = {
                "GET /py-comp-walrus-false",
                "GET /py-before-comp-walrus-false",
                "GET /py-before-assign-list-walrus-false",
                "GET /py-before-annassign-generator-walrus-false",
                "GET /py-before-augassign-dict-walrus-false",
                "GET /py-before-namedexpr-nested-call-false",
                "GET /py-before-set-default-walrus-false",
                "GET /py-before-lambda-default-walrus-false",
                "GET /ts-param-false",
                "GET /ts-arrow-return-false",
                "GET /ts-method-false",
                "GET /js-for-assign-false",
                "GET /ts-for-typed-false",
                "GET /js-do-shadow-false",
                "GET /js-switch-shadow-false",
                "GET /js-for-var-after-false",
                "GET /js-unclosed-false",
                "GET /lambda-await-walrus-false",
                "GET /lambda-await-readonly-invalid-false",
                "GET /lambda-nested-body-walrus-false",
            }
            false_entrypoints.update(
                f"GET /lambda-{label}-walrus-false" for label in lambda_body_cases
            )
            false_entrypoints.update(
                f"GET /class-comp-{label}-false" for label in class_comprehension_cases
            )
            false_entrypoints.update(round8_false_entrypoints)
            produced_entrypoints = {
                feature["entrypoint"] for feature in result["features"]
            }

            self.assertTrue(false_entrypoints.isdisjoint(produced_entrypoints))
            self.assertEqual(
                [
                    evidence
                    for evidence in result["evidence"]
                    if evidence["kind"] == "technology-claim:framework"
                ],
                [],
            )
            validation = validate_index(result, root)
            self.assertTrue(validation["valid"], validation["issues"])
            report = render_report(result)
            for entrypoint in false_entrypoints:
                self.assertNotIn(entrypoint, report)

    def test_configuration_and_ordinary_modules_do_not_become_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "eslint.config.js").write_text("export default {};\n", encoding="utf-8")
            (root / "src" / "context-builder.ts").write_text(
                "export function buildContext() { return []; }\n", encoding="utf-8"
            )

            result = build_index(root)

            self.assertEqual(result["features"], [])
            self.assertFalse(any(item["kind"] == "entry-declaration" for item in result["evidence"]))

    def test_deferred_javascript_assignments_cannot_escape_or_reuse_scope_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.js").write_text(
                "const express = require('express');\n"
                "let leaked;\n"
                "function first() { leaked = express(); }\n"
                "function second() { leaked.get('/id-reuse-cross-scope-false', handler); }\n"
                "second();\n"
                "const arrow = () => { leaked = express(); };\n"
                "leaked.get('/arrow-write-escaped-false', handler);\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entrypoints = {feature["entrypoint"] for feature in result["features"]}

            self.assertNotIn("GET /id-reuse-cross-scope-false", entrypoints)
            self.assertNotIn("GET /arrow-write-escaped-false", entrypoints)
            self.assertTrue(validate_index(result, root)["valid"])

    def test_unsupported_javascript_token_fails_closed_for_the_whole_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.js").write_text(
                "const express = require('express');\n"
                "function register() {\n"
                "  const app = express();\n"
                "  @ app.get('/malformed-function-inside-false', handler);\n"
                "}\n",
                encoding="utf-8",
            )

            result = build_index(root)

            self.assertNotIn(
                "GET /malformed-function-inside-false",
                {feature["entrypoint"] for feature in result["features"]},
            )
            self.assertTrue(validate_index(result, root)["valid"])

    def test_framework_evidence_never_includes_deferred_sibling_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "same_line.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI(); app.get('/same-line-live'); "
                "probe = lambda: app.get('/same-line-suppressed-false')\n",
                encoding="utf-8",
            )
            (root / "multiline.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI(\n"
                "    lifespan=lambda: ghost.get('/factory-evidence-suppressed-false')\n"
                ")\n"
                "app.get('/multiline-live')\n",
                encoding="utf-8",
            )
            (root / "server.js").write_text(
                "import express from 'express';\n"
                "const app = express();\n"
                "app.get('/near-js-live', handler);\n"
                "const probe = () => app.get('/near-js-false', handler);\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entrypoints = {feature["entrypoint"] for feature in result["features"]}
            rendered = render_report(result)
            evidence_text = "\n".join(item["snippet"] for item in result["evidence"])

            self.assertIn("GET /multiline-live", entrypoints)
            self.assertIn("GET /near-js-live", entrypoints)
            for suppressed in (
                "/same-line-suppressed-false",
                "/factory-evidence-suppressed-false",
                "/near-js-false",
            ):
                self.assertNotIn(f"GET {suppressed}", entrypoints)
                self.assertNotIn(suppressed, evidence_text)
                self.assertNotIn(suppressed, rendered)
            self.assertTrue(validate_index(result, root)["valid"])

    def test_exported_esm_function_keeps_same_function_boundary_recall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.js").write_text(
                "import express from 'express';\n"
                "export function register() {\n"
                "  const app = express();\n"
                "  app.get('/exported-function', handler);\n"
                "}\n",
                encoding="utf-8",
            )

            result = build_index(root)
            feature = next(
                (
                    item for item in result["features"]
                    if item["entrypoint"] == "GET /exported-function"
                ),
                None,
            )

            self.assertIsNotNone(feature)
            self.assertTrue(validate_index(result, root)["valid"])

    def test_node_syntax_gate_rejects_supported_token_but_malformed_javascript(self) -> None:
        malformed_sources = {
            "missing-initializer.js": (
                "const express = require('express');\n"
                "const app;\n"
                "app = express();\n"
                "app.get('/round12-malformed-const-false', handler);\n"
            ),
            "bare-throw.mjs": (
                "import express from 'express';\n"
                "throw;\n"
                "const app = express();\n"
                "app.get('/round12-malformed-throw-false', handler);\n"
            ),
            "bare-private.cjs": (
                "const express = require('express');\n"
                "#;\n"
                "const app = express();\n"
                "app.get('/round12-malformed-hash-false', handler);\n"
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, source in malformed_sources.items():
                (root / name).write_text(source, encoding="utf-8")

            result = build_index(root)
            entrypoints = {feature["entrypoint"] for feature in result["features"]}
            evidence_text = "\n".join(item["snippet"] for item in result["evidence"])
            rendered = render_report(result)

            for source in malformed_sources.values():
                false_path = source.split("app.get('", 1)[1].split("'", 1)[0]
                self.assertNotIn(f"GET {false_path}", entrypoints)
                self.assertNotIn(false_path, evidence_text)
                self.assertNotIn(false_path, rendered)
            self.assertTrue(validate_index(result, root)["valid"])

    def test_node_syntax_gate_fails_closed_when_node_is_unavailable_or_times_out(self) -> None:
        source = (
            "const express = require('express');\n"
            "const app = express();\n"
            "app.get('/node-gate-uncertain-false', handler);\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.js").write_text(source, encoding="utf-8")
            (root / "server.ts").write_text(
                "import express from 'express';\n"
                "const typed: Express = express();\n"
                "typed.get('/typescript-lexical-boundary', handler);\n",
                encoding="utf-8",
            )

            with patch("repo_teacher.features._find_node_runtime", return_value=None):
                unavailable = build_index(root)
                unavailable_validation = validate_index(unavailable, root)
            with (
                patch("repo_teacher.features._find_node_runtime", return_value="/usr/bin/node"),
                patch(
                    "repo_teacher.features.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("node", 3.0),
                ),
            ):
                timed_out = build_index(root)
                timeout_validation = validate_index(timed_out, root)

            for result in (unavailable, timed_out):
                entrypoints = {feature["entrypoint"] for feature in result["features"]}
                self.assertNotIn("GET /node-gate-uncertain-false", entrypoints)
                self.assertIn("GET /typescript-lexical-boundary", entrypoints)
            self.assertTrue(unavailable_validation["valid"], unavailable_validation["issues"])
            self.assertTrue(timeout_validation["valid"], timeout_validation["issues"])

    def test_structured_js_evidence_exclusivity_sees_comment_separated_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.js").write_text(
                "import express from 'express';\n"
                "const app = express(); app.get('/round12-comment-live', handler); "
                "const probe = () => app. /*gap*/ "
                "get('/round12-comment-false', handler);\n",
                encoding="utf-8",
            )

            result = build_index(root)
            entrypoints = {feature["entrypoint"] for feature in result["features"]}
            evidence_text = "\n".join(item["snippet"] for item in result["evidence"])
            rendered = render_report(result)

            self.assertNotIn("GET /round12-comment-false", entrypoints)
            self.assertNotIn("/round12-comment-false", evidence_text)
            self.assertNotIn("/round12-comment-false", rendered)
            self.assertTrue(validate_index(result, root)["valid"])


if __name__ == "__main__":
    unittest.main()
