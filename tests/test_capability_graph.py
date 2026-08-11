from __future__ import annotations

import unittest

from repo_teacher.capability_graph import (
    analyze_impact,
    build_capability_graph,
    explore_capability_graph,
    get_callees,
    get_callers,
    get_dependency_graph,
    traverse_graph,
)


class CapabilityGraphTest(unittest.TestCase):
    def _index(self) -> dict[str, object]:
        return {
            "files": [
                {"id": "file_api", "path": "app/api.py", "module": "app", "lines": 20},
                {"id": "file_service", "path": "app/service.py", "module": "app", "lines": 30},
                {"id": "file_store", "path": "storage/store.py", "module": "storage", "lines": 40},
                {"id": "file_lonely", "path": "tools/lonely.py", "module": "tools", "lines": 10},
            ],
            "symbols": [
                {
                    "id": "sym_route", "file_id": "file_api", "path": "app/api.py",
                    "name": "create_task", "qualified_name": "api.create_task", "kind": "function",
                    "line": 2, "end_line": 6, "confidence": "exact", "exported": True,
                },
                {
                    "id": "sym_service", "file_id": "file_service", "path": "app/service.py",
                    "name": "enqueue", "qualified_name": "TaskService.enqueue", "kind": "method",
                    "line": 4, "end_line": 12, "confidence": "exact", "exported": True,
                },
                {
                    "id": "sym_store", "file_id": "file_store", "path": "storage/store.py",
                    "name": "insert", "qualified_name": "TaskStore.insert", "kind": "method",
                    "line": 8, "end_line": 17, "confidence": "exact", "exported": True,
                },
                {
                    "id": "sym_lonely", "file_id": "file_lonely", "path": "tools/lonely.py",
                    "name": "helper", "qualified_name": "tools.helper", "kind": "function",
                    "line": 1, "end_line": 2, "confidence": "exact", "exported": False,
                },
            ],
            "relationships": [
                {
                    "id": "rel_route_service", "source_id": "sym_route", "target_id": "sym_service",
                    "target_name": "enqueue", "kind": "calls", "path": "app/api.py", "line": 5,
                    "confidence": "syntax-exact",
                },
                {
                    "id": "rel_service_store", "source_id": "sym_service", "target_id": "sym_store",
                    "target_name": "insert", "kind": "calls", "path": "app/service.py", "line": 9,
                    "confidence": "syntax-exact",
                },
                {
                    "id": "rel_external", "source_id": "sym_store", "target_id": None,
                    "target_name": "commit", "kind": "calls", "path": "storage/store.py", "line": 16,
                    "confidence": "syntax-unresolved",
                },
            ],
            "features": [
                {
                    "id": "feature_task", "title": "创建后台任务", "confidence": "exact-entry",
                    "entry_symbol_id": "sym_route", "steps": [],
                }
            ],
        }

    def test_builds_feature_slice_components_and_module_dependencies(self) -> None:
        graph = build_capability_graph(self._index())

        self.assertEqual(graph["schema_version"], "repo-teacher-capability-graph/v1")
        self.assertEqual(graph["stats"]["resolved_edges"], 2)
        self.assertEqual(graph["stats"]["unresolved_edges"], 1)
        self.assertEqual(len(graph["feature_slices"]), 1)
        feature_slice = graph["feature_slices"][0]
        self.assertEqual(feature_slice["feature_id"], "feature_task")
        self.assertEqual(
            set(feature_slice["node_ids"]),
            {"sym_route", "sym_service", "sym_store"},
        )
        self.assertEqual(
            {(item["source"], item["target"]) for item in graph["module_dependencies"]},
            {("app", "storage")},
        )

    def test_unconnected_symbol_is_not_promoted_to_user_feature(self) -> None:
        graph = build_capability_graph(self._index())

        self.assertTrue(
            all(item["kind"] == "mechanism-cluster" for item in graph["mechanism_clusters"])
        )
        self.assertTrue(
            all(
                item["claim_status"] == "candidate-not-user-facing-until-reviewed"
                for item in graph["mechanism_clusters"]
            )
        )
        self.assertNotIn(
            "sym_lonely",
            {
                node_id
                for feature_slice in graph["feature_slices"]
                for node_id in feature_slice["node_ids"]
            },
        )

    def test_explore_returns_callers_callees_and_impact(self) -> None:
        graph = build_capability_graph(self._index())
        result = explore_capability_graph(graph, "enqueue", depth=2)

        self.assertEqual(result["matched_node_ids"], ["sym_service"])
        self.assertEqual(result["callers"]["sym_service"], ["sym_route"])
        self.assertEqual(result["callees"]["sym_service"], ["sym_store"])
        self.assertEqual(set(result["impact_node_ids"]), {"sym_route", "sym_store"})

    def test_typed_call_queries_do_not_treat_contains_as_a_caller(self) -> None:
        index = self._index()
        index["relationships"].append(
            {
                "id": "rel_file_contains_service",
                "source_id": "file_service",
                "target_id": "sym_service",
                "target_name": "enqueue",
                "kind": "contains",
                "path": "app/service.py",
                "line": 4,
                "confidence": "exact",
            }
        )
        graph = build_capability_graph(index)

        callers = get_callers(graph, "sym_service", depth=1)
        callees = get_callees(graph, "sym_service", depth=1)
        impact = analyze_impact(graph, ["sym_service"], depth=2)
        explored = explore_capability_graph(graph, "enqueue", depth=2)

        self.assertEqual(
            {item["id"] for item in callers["nodes"] if item["distance"] == 1},
            {"sym_route"},
        )
        self.assertEqual(
            {item["id"] for item in callees["nodes"] if item["distance"] == 1},
            {"sym_store"},
        )
        self.assertEqual(impact["direct_callers"], ["sym_route"])
        self.assertEqual(explored["callers"]["sym_service"], ["sym_route"])

    def test_filtered_traversal_and_module_dependency_view(self) -> None:
        graph = build_capability_graph(self._index())

        traversed = traverse_graph(
            graph,
            ["sym_route"],
            direction="forward",
            depth=1,
            edge_kinds=["calls"],
        )
        dependencies = get_dependency_graph(graph, modules=["app"])

        self.assertEqual(
            {item["id"] for item in traversed["nodes"]},
            {"sym_route", "sym_service"},
        )
        self.assertEqual(dependencies["modules"], ["app", "storage"])
        self.assertEqual(len(dependencies["dependencies"]), 1)

    def test_traversal_rejects_invalid_bounds(self) -> None:
        graph = build_capability_graph(self._index())

        with self.assertRaisesRegex(ValueError, "direction"):
            traverse_graph(graph, ["sym_route"], direction="sideways")
        with self.assertRaisesRegex(ValueError, "depth"):
            traverse_graph(graph, ["sym_route"], depth=-1)
        with self.assertRaisesRegex(ValueError, "limit"):
            traverse_graph(graph, ["sym_route"], limit=0)


if __name__ == "__main__":
    unittest.main()
