from __future__ import annotations

import ast
import inspect
import unittest
from importlib.resources import files

import repo_teacher.cli as cli
from repo_teacher.agents import load_agent_spec
from repo_teacher.prompts import render_prompt
from repo_teacher.providers import run_structured_json


class PromptArchitectureTest(unittest.TestCase):
    def test_cli_contains_no_embedded_model_prompt(self) -> None:
        source = inspect.getsource(cli)
        tree = ast.parse(source)
        long_strings = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and len(node.value) > 1_000
        ]

        self.assertEqual(long_strings, [])
        self.assertNotIn("def _inventory_group_json_schema", source)
        self.assertNotIn("def _project_overview_json_schema", source)
        self.assertNotIn("def _chapter_batch_json_schema", source)
        self.assertNotIn("你是代码库技术教师", source)
        self.assertNotIn("上一次响应无法解析", source)
        self.assertNotIn("只输出一个符合下面 JSON Schema", source)
        self.assertNotIn("def _run_deepseek_json", source)
        self.assertNotIn("def _run_opencode_json", source)
        self.assertNotIn("from urllib.request import", source)
        self.assertNotIn("def _synthesize_with_codex", source)
        self.assertNotIn("ThreadPoolExecutor", source)
        self.assertLess(len(source.splitlines()), 400)

        functions = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(functions, {"_positive_int", "_parser", "main"})
        imported_modules = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertEqual(imported_modules, {"__future__", "typing", "commands.entrypoints"})

    def test_every_agent_prompt_is_a_packaged_versioned_resource(self) -> None:
        prompt_root = files("repo_teacher.prompts")
        for name in (
            "project-context-analyzer",
            "business-capability-analyst",
            "inventory-closure-repairer",
            "capability-partition-repairer",
            "chapter-writer",
        ):
            with self.subTest(name=name):
                prompt_name = load_agent_spec(name).prompt
                self.assertIsNotNone(prompt_name)
                assert prompt_name is not None
                self.assertRegex(prompt_name, r"-v\d+\.md$")
                self.assertTrue(prompt_root.joinpath(prompt_name).is_file())

    def test_prompt_renderer_rejects_missing_contract_variables(self) -> None:
        with self.assertRaises(KeyError):
            render_prompt("inventory-shard-v1.md", pack_path="pack-only")

    def test_provider_runtime_rejects_unknown_provider_before_execution(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported narrative provider"):
            run_structured_json(
                source=files("repo_teacher"),
                workspace=files("repo_teacher"),
                schema={"type": "object"},
                prompt="unused",
                timeout=1,
                stage_slug="test",
                progress_label="test",
                provider="unknown",
            )


if __name__ == "__main__":
    unittest.main()
