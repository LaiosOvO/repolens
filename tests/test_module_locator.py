from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_teacher.indexer import build_index
from repo_teacher.module_locator import locate_modules


class ModuleLocatorTest(unittest.TestCase):
    def _write(self, root: Path, files: dict[str, str]) -> None:
        for relative, source in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")

    def _repository(self, temporary: str, name: str, files: dict[str, str]) -> Path:
        root = Path(temporary) / name
        self._write(root, files)
        return root

    def _build_acp_repository(self, root: Path) -> dict:
        self._write(
            root,
            {
                "src/acp/router.py": (
                    "from .manager import ACPManager\n\n"
                    "def handle_request(payload):\n    return ACPManager().dispatch(payload)\n"
                ),
                "src/acp/manager.py": (
                    "import json\n\nclass ACPManager:\n"
                    "    def dispatch(self, payload):\n        return json.dumps(payload)\n"
                ),
                "src/acp/models.py": "class ACPRequest:\n    pass\n",
                "src/acp/tests/test_manager.py": (
                    "from src.acp.manager import ACPManager\n\n"
                    "def test_dispatch():\n    assert ACPManager().dispatch({}) == '{}'\n"
                ),
                "src/host/app.py": (
                    "from src.acp.router import handle_request\n\n"
                    "def main():\n    return handle_request({})\n"
                ),
            },
        )
        return build_index(root)

    def test_directory_name_exact_is_not_capability_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = locate_modules(self._build_acp_repository(root), "ACP")

            self.assertEqual(result["resolution"]["status"], "exact_name_match")
            self.assertTrue(result["resolution"]["is_exact_name_match"])
            self.assertFalse(result["resolution"]["is_exact"])
            self.assertFalse(result["resolution"]["verified_capability_surface"])
            module = result["modules"][0]
            self.assertEqual(module["path"], "src/acp")
            self.assertEqual(module["certainty"], "directory-name-exact")
            self.assertFalse(module["verified_capability_surface"])
            self.assertEqual(module["surface_kind"], "directory")
            self.assertEqual(
                {item["path"] for item in module["files"]},
                {"src/acp/router.py", "src/acp/manager.py", "src/acp/models.py"},
            )
            self.assertTrue(module["implementation_trace"])
            self.assertTrue(
                all(item["kind"] == "resolved_relationship_trace" for item in module["implementation_trace"])
            )
            self.assertTrue(
                all(item["ordering"] in {"resolved-graph-topology", "cycle-fallback"} for item in module["implementation_trace"])
            )
            self.assertTrue(module["component_boundaries"])
            self.assertTrue(
                all(item["kind"] == "heuristic_reading_order" for item in module["reading_order"])
            )
            self.assertEqual(module["tests"][0]["association"], "resolved-relationship")
            symbol = next(item for item in module["core_symbols"] if "ACPManager" in item["name"])
            self.assertTrue(symbol["source_location"]["fresh"])
            self.assertTrue(symbol["source_location"]["snippet"])
            self.assertTrue(symbol["source_location"]["snippet_sha256"])

    def test_product_directories_form_composite_and_auxiliary_name_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                {
                    "packages/a/acp/main.py": "def main():\n    return 1\n",
                    "packages/b/acp/handler.py": "def handle():\n    return 2\n",
                    "examples/acp/main.py": "def fake():\n    return 3\n",
                    "tests/acp/test_fake.py": "def test_fake():\n    pass\n",
                },
            )

            result = locate_modules(build_index(root), "acp")

            self.assertEqual(result["resolution"]["status"], "composite_candidate")
            self.assertEqual(result["resolution"]["exact_match_count"], 2)
            self.assertIn("examples/acp", result["resolution"]["excluded_auxiliary_matches"])
            slices = {item["path"] for item in result["modules"][0]["slices"]}
            self.assertEqual(slices, {"packages/a/acp", "packages/b/acp"})
            self.assertNotIn("examples/acp/main.py", {item["path"] for item in result["modules"][0]["files"]})

    def test_docs_only_exact_name_is_not_a_product_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, {"docs/FastAPI/README.md": "# FastAPI example\n"})

            result = locate_modules(build_index(root), "FastAPI")

            self.assertEqual(result["resolution"]["status"], "not_found")
            self.assertEqual(result["modules"], [])
            self.assertEqual(result["resolution"]["excluded_auxiliary_matches"], ["docs/FastAPI"])

    def test_unrelated_test_name_never_becomes_test_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                {
                    "src/acp/client.py": "class Client:\n    pass\n",
                    "tests/test_acp_unrelated.py": "def test_other():\n    assert True\n",
                },
            )

            module = locate_modules(build_index(root), "acp")["modules"][0]

            self.assertEqual(module["tests"], [])
            self.assertEqual(module["possible_tests"], [])

    def test_source_excerpt_requires_a_snapshot_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = self._build_acp_repository(root)
            manager = next(item for item in index["files"] if item["path"] == "src/acp/manager.py")
            manager.pop("sha256", None)

            module = locate_modules(index, "acp")["modules"][0]
            symbol = next(item for item in module["core_symbols"] if "ACPManager" in item["name"])

            self.assertFalse(symbol["source_location"]["fresh"])
            self.assertEqual(symbol["source_location"]["snippet"], "")

    def test_fuzzy_file_match_is_a_source_slice_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, {"src/protocols/acp_transport.py": "class ACPTransport:\n    pass\n"})

            result = locate_modules(build_index(root), "acp")

            self.assertEqual(result["resolution"]["status"], "candidate")
            self.assertFalse(result["resolution"]["is_exact_name_match"])
            self.assertEqual(result["modules"][0]["slices"][0]["kind"], "file")
            self.assertEqual(result["modules"][0]["certainty"], "source-slice-candidate")

    def test_unicode_directory_name_is_only_an_exact_name_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, {"src/任务协议/main.py": "def main():\n    return 1\n"})

            result = locate_modules(build_index(root), "任务协议")

            self.assertEqual(result["resolution"]["status"], "exact_name_match")
            self.assertFalse(result["resolution"]["verified_capability_surface"])

    def test_six_reference_repository_golden_surfaces(self) -> None:
        cases = (
            (
                "pocketflow-code2tutorial",
                "tutorial",
                {
                    "main.py": "from flow import create_tutorial_flow\n",
                    "flow.py": "def create_tutorial_flow():\n    return None\n",
                    "nodes.py": "class FetchRepo:\n    pass\n",
                    "docs/FastAPI/README.md": "# not product source\n",
                },
                {"main.py", "flow.py", "nodes.py"},
                "main.py",
            ),
            (
                "sourcebridge",
                "knowledge",
                {
                    "internal/knowledge/store.go": "package knowledge\nfunc Store() {}\n",
                    "internal/knowledge/store_test.go": "package knowledge\nfunc TestStore() {}\n",
                    "workers/knowledge/code_tour.py": "def build_tour():\n    return []\n",
                    "web/src/app/(app)/admin/knowledge/page.tsx": "export default function Page() {}\n",
                    "gen/go/knowledge/generated.go": "package knowledge\n",
                },
                {
                    "internal/knowledge/store.go",
                    "workers/knowledge/code_tour.py",
                    "web/src/app/(app)/admin/knowledge/page.tsx",
                },
                "internal/knowledge",
            ),
            (
                "openwiki",
                "visualize",
                {
                    "src/visualize/graph.ts": "export function buildGraph() {}\n",
                    "src/visualize/server.ts": "export function runVisualizeServer() {}\n",
                    "src/cli/runners.ts": "import { runVisualizeServer } from '../visualize/server';\n",
                    "test/visualize/visualize-server.test.ts": "export const testServer = true;\n",
                },
                {"src/visualize/graph.ts", "src/visualize/server.ts", "src/cli/runners.ts"},
                "src/visualize",
            ),
            (
                "understand-anything",
                "viewer",
                {
                    "understand-anything-plugin/packages/viewer/bin/viewer.mjs": "export function main() {}\n",
                    "understand-anything-plugin/packages/viewer/build.mjs": "export function build() {}\n",
                    "tests/skill/viewer/test.ts": "export const smoke = true;\n",
                },
                {
                    "understand-anything-plugin/packages/viewer/bin/viewer.mjs",
                    "understand-anything-plugin/packages/viewer/build.mjs",
                },
                "understand-anything-plugin/packages/viewer",
            ),
            (
                "codeboarding",
                "static_analyzer",
                {
                    "static_analyzer/engine/call_graph_builder.py": "class CallGraphBuilder:\n    pass\n",
                    "static_analyzer/engine/hierarchy_builder.py": "class HierarchyBuilder:\n    pass\n",
                    "static_analyzer/graph.py": "class Graph:\n    pass\n",
                    "tests/static_analyzer/test_graph.py": "def test_graph():\n    pass\n",
                },
                {
                    "static_analyzer/engine/call_graph_builder.py",
                    "static_analyzer/engine/hierarchy_builder.py",
                    "static_analyzer/graph.py",
                },
                "static_analyzer",
            ),
            (
                "deepwiki-open",
                "codemap",
                {
                    "api/services/codemap.py": "async def generate_codemap():\n    yield 'done'\n",
                    "api/routers/codemap.py": "def route():\n    return None\n",
                    "api/schemas/codemap.py": "class CodeMap:\n    pass\n",
                    "src/components/Ask.tsx": "export function Ask() {}\n",
                    "src/components/CodeMap.tsx": "export function CodeMap() {}\n",
                    "src/components/CodeViewer.tsx": "export function CodeViewer() {}\n",
                    "src/utils/websocketClient.ts": "export function openSocket() {}\n",
                },
                {
                    "api/services/codemap.py",
                    "api/routers/codemap.py",
                    "api/schemas/codemap.py",
                    "src/components/Ask.tsx",
                    "src/components/CodeMap.tsx",
                    "src/components/CodeViewer.tsx",
                    "src/utils/websocketClient.ts",
                },
                "api/services/codemap.py",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            for project, query, files, expected_files, primary_path in cases:
                with self.subTest(project=project, query=query):
                    root = self._repository(directory, project, files)
                    result = locate_modules(build_index(root), query)
                    self.assertEqual(len(result["modules"]), 1)
                    module = result["modules"][0]
                    self.assertEqual(module["path"], primary_path)
                    self.assertEqual(
                        {item["path"] for item in module["files"]},
                        expected_files,
                    )
                    # These fixtures exercise the six path shapes without a Git
                    # remote/commit/source-bundle identity.  They must never be
                    # promoted to a source-audited reference alignment.
                    self.assertIsNone(module["reference_alignment"])
                    self.assertEqual(module["reference_shape_hint"]["project"], project)
                    self.assertFalse(module["reference_shape_hint"]["source_audited"])
                    self.assertEqual(
                        module["reference_shape_hint"]["identity_status"], "unverified"
                    )
                    self.assertFalse(module["verified_capability_surface"])
                    self.assertNotIn(
                        "test",
                        {item["surface_role"] for item in module["files"]},
                    )
                    if project in {"sourcebridge", "openwiki", "understand-anything", "codeboarding"}:
                        self.assertTrue(module["possible_tests"])

    def test_partial_or_name_only_reference_shape_is_not_applied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repository(
                directory,
                "sourcebridge",
                {"internal/knowledge/store.go": "package knowledge\nfunc Store() {}\n"},
            )

            module = locate_modules(build_index(root), "knowledge")["modules"][0]

            self.assertIsNone(module["reference_alignment"])
            self.assertIsNone(module["reference_shape_hint"])
            self.assertEqual([item["path"] for item in module["slices"]], ["internal/knowledge"])

    def test_invalid_arguments_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            locate_modules({}, "")
        with self.assertRaises(ValueError):
            locate_modules({}, "acp", limit=0)
        with self.assertRaises(TypeError):
            locate_modules([], "acp")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
