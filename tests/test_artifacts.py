from __future__ import annotations

import unittest

from repo_teacher.artifacts import enrich_index


class ArtifactGenerationTest(unittest.TestCase):
    def test_waku_tutorials_include_human_chapters_for_all_product_mechanisms(self) -> None:
        mechanisms = (
            "loop", "memory", "graph", "gateway", "voice",
            "tools", "providers", "dashboard", "eval",
        )
        enriched = enrich_index(
            {
                "features": [
                    {
                        "id": mechanism,
                        "title": f"raw entry {mechanism}",
                        "entrypoint": f"raw_{mechanism}",
                        "technology_tags": [
                            "compatibility-corpus:waku-not-curated",
                            f"compatibility-mechanism:{mechanism}",
                        ],
                    }
                    for mechanism in mechanisms
                ],
                "symbols": [],
                "relationships": [],
                "evidence": [],
            }
        )

        chapters = {
            tutorial["human_chapter"]["mechanism"]: tutorial["human_chapter"]
            for tutorial in enriched["tutorials"]
        }
        self.assertEqual(set(chapters), set(mechanisms))
        for mechanism in mechanisms:
            chapter = chapters[mechanism]
            self.assertTrue(chapter["question"])
            self.assertGreaterEqual(len(chapter["runtime_story"]["steps"]), 5)
            self.assertGreaterEqual(len(chapter["construction"]["objects"]), 4)
            self.assertGreaterEqual(len(chapter["state_flow"]), 3)
            self.assertGreaterEqual(len(chapter["design_choices"]), 3)
            self.assertTrue(chapter["reuse_plan"]["take"])
            self.assertTrue(chapter["boundary"]["unsupported"])
            mechanism_model = chapter["mechanism_model"]
            self.assertTrue(mechanism_model["plain_summary"])
            self.assertTrue(mechanism_model["storage"])
            self.assertTrue(mechanism_model["write_path"])
            self.assertTrue(mechanism_model["read_path"])
            self.assertTrue(mechanism_model["control_loop"])
            self.assertTrue(mechanism_model["decision_rules"])
            self.assertTrue(mechanism_model["termination"])
            self.assertTrue(mechanism_model["dynamic_behavior"])
            self.assertGreaterEqual(len(mechanism_model["worked_example"]), 3)

        graph = chapters["graph"]
        self.assertIn("运行前", graph["distinguish"])
        self.assertIn("运行中", graph["distinguish"])
        self.assertIn("整波完成", " ".join(graph["runtime_story"]["steps"]))
        self.assertIn("gather node", [item["name"] for item in graph["construction"]["objects"]])
        self.assertIn("deps", graph["mechanism_model"]["read_path"])
        self.assertIn("label", graph["mechanism_model"]["decision_rules"])
        self.assertIn("运行中", graph["mechanism_model"]["dynamic_behavior"])

        memory = chapters["memory"]["mechanism_model"]
        self.assertIn("state.db", memory["storage"])
        self.assertIn("FTS5", memory["read_path"])
        self.assertIn("retrieval gate", memory["decision_rules"])

        loop = chapters["loop"]["mechanism_model"]
        self.assertIn("Python for 循环", loop["plain_summary"])
        self.assertIn("不是 while", loop["plain_summary"])
        self.assertIn("for iteration", loop["control_loop"])
        self.assertIn("tool_uses", loop["decision_rules"])
        self.assertIn("max_iterations", loop["termination"])

        voice = chapters["voice"]["mechanism_model"]
        self.assertIn("录音结束", voice["plain_summary"])
        self.assertIn("ASR → Agent → TTS", voice["plain_summary"])

        self.assertIn("Router 不是执行节点", graph["mechanism_model"]["plain_summary"])

        expected_specific_terms = {
            "gateway": "fingerprint",
            "voice": "PCM",
            "tools": "ToolRegistry",
            "providers": "provider",
            "dashboard": "observer",
            "eval": "evaluation record",
        }
        for mechanism, term in expected_specific_terms.items():
            rendered = " ".join(
                str(value)
                for value in chapters[mechanism]["mechanism_model"].values()
            )
            self.assertIn(term, rendered)

    def test_empty_index_produces_empty_artifacts_without_mutating_input(self) -> None:
        source = {"stats": {"files": 0}, "features": []}

        enriched = enrich_index(source)

        self.assertEqual(enriched["tutorials"], [])
        self.assertEqual(enriched["codemaps"], [])
        self.assertEqual(enriched["coverage"], [])
        self.assertEqual(enriched["stats"]["coverage_average"], 0.0)
        self.assertNotIn("tutorials", source)
        self.assertEqual(source, {"stats": {"files": 0}, "features": []})

    def test_generates_grounded_tutorial_codemap_and_coverage(self) -> None:
        index = {
            "stats": {"features": 1},
            "symbols": [
                {"id": "symbol_entry", "name": "run", "qualified_name": 'cli.run\"]\nBAD --> X'},
                {"id": "symbol_work", "name": "work", "qualified_name": "service.work"},
            ],
            "relationships": [
                {
                    "id": "rel_call",
                    "source_id": "symbol_entry",
                    "target_id": "symbol_work",
                    "kind": "calls",
                }
            ],
            "evidence": [
                {"id": "ev_entry", "kind": "feature-entrypoint"},
                {"id": "ev_run", "kind": "symbol-definition"},
                {"id": "ev_work", "kind": "symbol-definition"},
                {"id": "ev_test", "kind": "test-reference"},
            ],
            "features": [
                {
                    "id": "feature_run",
                    "title": 'CLI 命令：run\"]\nBAD --> X',
                    "entrypoint": "run",
                    "confidence": "exact",
                    "summary": "执行命令并调用核心工作函数。",
                    "technology_claims": [
                        {
                            "dimension": "framework",
                            "value": "argparse",
                            "claim_scope": "CLI 边界声明",
                            "confidence": "source-audited",
                            "evidence_ids": ["ev_entry"],
                            "source_path": "cli.py",
                        },
                        {
                            "dimension": "store",
                            "value": "unknown",
                            "claim_scope": "未发现独立证据",
                            "confidence": "unknown",
                            "evidence_ids": [],
                            "source_path": None,
                        },
                    ],
                    "evidence_ids": ["ev_entry", "dangling"],
                    "test_evidence_ids": ["ev_test"],
                    "steps": [
                        {
                            "order": 1,
                            "title": "进入 run",
                            "path": "cli.py",
                            "line_start": 10,
                            "line_end": 12,
                            "symbol_id": "symbol_entry",
                            "relationship_id": "rel_call",
                            "evidence_ids": ["ev_run"],
                        },
                        {
                            "order": 2,
                            "title": "进入 work",
                            "path": "service.py",
                            "line_start": 2,
                            "line_end": 4,
                            "symbol_id": "symbol_work",
                            "relationship_id": "rel_call",
                            "evidence_ids": ["ev_work"],
                        },
                    ],
                }
            ],
        }

        enriched = enrich_index(index)

        tutorial = enriched["tutorials"][0]
        self.assertEqual(tutorial["feature_id"], "feature_run")
        self.assertEqual([step["order"] for step in tutorial["steps"]], [1, 2])
        self.assertEqual(tutorial["evidence_ids"], ["ev_entry", "ev_run", "ev_work", "ev_test"])
        self.assertIn("不推断", tutorial["opening"])
        self.assertIn("不证明运行时", tutorial["closing"])
        self.assertEqual([chapter["kind"] for chapter in tutorial["chapters"]], [
            "purpose-and-entry", "main-implementation-chain", "data-state-and-dependencies",
            "error-and-evidence-gaps", "reuse-boundary",
        ])
        contract = tutorial["teaching_contract"]
        self.assertEqual(contract["purpose"], "执行命令并调用核心工作函数。")
        self.assertEqual(contract["entry"]["boundary"], "run")
        self.assertEqual(len(contract["main_chain"]), 2)
        self.assertEqual(contract["dependencies"]["claims"][0]["value"], "argparse")
        self.assertEqual(contract["unresolved_technology_claims"][0]["dimension"], "store")
        self.assertTrue(contract["reuse_boundary"]["must_reverify"])
        self.assertIn("cli.py:10-12", contract["reuse_boundary"]["reusable"][0])
        self.assertEqual(tutorial["confirmed_relationship_count"], 1)
        self.assertEqual(set(tutorial["gaps"]), {"data_flow", "state", "error_path", "runtime_order"})
        self.assertEqual(tutorial["chapters"][1]["slices"][1]["relationship_status"], "resolved-static")
        self.assertIn("not runtime", tutorial["reading_order_semantics"])
        self.assertEqual(tutorial["runtime_behavior"], "unknown without trace or behavior-level test evidence")

        codemap = enriched["codemaps"][0]
        self.assertEqual(codemap["node_ids"], ["symbol_entry", "symbol_work"])
        self.assertEqual(codemap["edge_ids"], ["rel_call"])
        self.assertEqual(codemap["resolved_edge_ids"], ["rel_call"])
        self.assertEqual(codemap["reading_order_edge_ids"], [])
        self.assertEqual(len(codemap["relationship_gaps"]), 0)
        self.assertIn("not implementation flow", codemap["implementation_flow_status"])
        self.assertIn("not runtime", codemap["edge_semantics"]["dashed"])
        self.assertIn("n1 -->|calls| n2", codemap["mermaid"])
        self.assertNotIn("\nBAD --> X", codemap["mermaid"])
        self.assertIn("&quot;", codemap["mermaid"])
        self.assertEqual(len(codemap["nodes"]), 2)
        self.assertEqual(codemap["edges"][0]["semantics"], "resolved-static-relationship")

        coverage = enriched["coverage"][0]
        self.assertEqual(coverage["score"], 100)
        self.assertEqual(coverage["status"], "signals-present")
        self.assertEqual(coverage["quality_assessment"], "not-assessed")
        self.assertTrue(all(coverage["checks"].values()))
        self.assertEqual(coverage["scope"], "artifact-evidence-completeness")
        self.assertEqual(coverage["behavioral_coverage"], "unknown")
        self.assertEqual(coverage["gaps"], [])
        self.assertEqual(coverage["metrics"]["resolved_relationships"], 1)
        self.assertEqual(enriched["stats"]["coverage_average"], 100.0)
        self.assertEqual(enriched["stats"]["evidence_completeness_average"], 100.0)

    def test_reading_order_edges_remain_distinct_from_resolved_call_edges(self) -> None:
        enriched = enrich_index(
            {
                "features": [
                    {
                        "id": "feature_read",
                        "title": "Read",
                        "entrypoint": "read",
                        "steps": [
                            {"order": 1, "path": "a.py", "line_start": 1, "symbol_id": "a", "evidence_ids": []},
                            {"order": 2, "path": "b.py", "line_start": 1, "symbol_id": "b", "evidence_ids": []},
                        ],
                    }
                ],
                "symbols": [
                    {"id": "a", "qualified_name": "a"},
                    {"id": "b", "qualified_name": "b"},
                ],
                "relationships": [],
                "evidence": [],
            }
        )

        codemap = enriched["codemaps"][0]
        self.assertEqual(codemap["resolved_edge_ids"], [])
        self.assertEqual(len(codemap["reading_order_edge_ids"]), 1)
        self.assertIn("静态阅读顺序", codemap["mermaid"])
        self.assertEqual(len(codemap["relationship_gaps"]), 2)
        self.assertTrue(
            all(edge["semantics"].endswith("not implementation flow") for edge in codemap["edges"])
        )

    def test_parallel_relationship_kinds_are_preserved_by_identity(self) -> None:
        enriched = enrich_index(
            {
                "features": [
                    {
                        "id": "feature_parallel",
                        "title": "Parallel",
                        "kind": "capability-cluster",
                        "entrypoint": "a.py",
                        "steps": [
                            {
                                "order": 1,
                                "symbol_id": "a",
                                "relationship_id": "r_calls",
                                "path": "a.py",
                                "line_start": 1,
                                "evidence_ids": [],
                            },
                            {
                                "order": 2,
                                "symbol_id": "b",
                                "relationship_id": "r_contains",
                                "path": "b.py",
                                "line_start": 1,
                                "evidence_ids": [],
                            },
                        ],
                    }
                ],
                "symbols": [
                    {"id": "a", "qualified_name": "a"},
                    {"id": "b", "qualified_name": "b"},
                ],
                "relationships": [
                    {"id": "r_calls", "source_id": "a", "target_id": "b", "kind": "calls"},
                    {"id": "r_contains", "source_id": "a", "target_id": "b", "kind": "contains"},
                ],
                "evidence": [],
            }
        )

        tutorial = enriched["tutorials"][0]
        codemap = enriched["codemaps"][0]
        coverage = enriched["coverage"][0]
        self.assertEqual(tutorial["confirmed_relationship_count"], 2)
        self.assertEqual(codemap["resolved_edge_ids"], ["r_calls", "r_contains"])
        self.assertEqual([edge["kind"] for edge in codemap["edges"]], ["calls", "contains"])
        self.assertEqual(coverage["metrics"]["resolved_relationships"], 2)

    def test_dangling_relationship_degrades_to_one_consistent_gap(self) -> None:
        enriched = enrich_index(
            {
                "features": [
                    {
                        "id": "feature_dangling",
                        "title": "Dangling",
                        "kind": "http-route",
                        "entrypoint": "GET /dangling",
                        "steps": [
                            {
                                "order": 1,
                                "symbol_id": "a",
                                "relationship_id": "missing",
                                "path": "a.py",
                                "line_start": 1,
                                "claim_scope": "resolved-static: stale",
                                "evidence_ids": [],
                            }
                        ],
                    }
                ],
                "symbols": [{"id": "a", "qualified_name": "a"}],
                "relationships": [],
                "evidence": [],
            }
        )

        tutorial = enriched["tutorials"][0]
        codemap = enriched["codemaps"][0]
        coverage = enriched["coverage"][0]
        source_slice = tutorial["teaching_contract"]["main_chain"][0]
        self.assertEqual(tutorial["confirmed_relationship_count"], 0)
        self.assertEqual(source_slice["relationship_status"], "location-only")
        self.assertEqual(source_slice["relationship_id"], "")
        self.assertIn("索引中不存在", source_slice["relationship_gap"])
        self.assertEqual(codemap["resolved_edge_ids"], [])
        self.assertEqual(len(codemap["relationship_gaps"]), 1)
        self.assertEqual(coverage["metrics"]["resolved_relationships"], 0)

    def test_relationship_with_missing_source_degrades_consistently(self) -> None:
        for label, source_id, target_id in (
            ("empty-source", "", "target"),
            ("ghost-source", "ghost", "target"),
            ("ghost-target", "target", "ghost"),
        ):
            with self.subTest(label=label):
                enriched = enrich_index(
                    {
                        "features": [
                            {
                                "id": "feature_missing_source",
                                "title": "Missing source",
                                "entrypoint": "GET /missing-source",
                                "steps": [
                                    {
                                        "order": 1,
                                        "symbol_id": "target",
                                        "relationship_id": "missing_source",
                                        "path": "target.py",
                                        "line_start": 1,
                                        "evidence_ids": [],
                                    }
                                ],
                            }
                        ],
                        "symbols": [{"id": "target", "qualified_name": "target"}],
                        "relationships": [
                            {
                                "id": "missing_source",
                                "source_id": source_id,
                                "target_id": target_id,
                                "kind": "calls",
                            }
                        ],
                        "evidence": [],
                    }
                )

                tutorial = enriched["tutorials"][0]
                codemap = enriched["codemaps"][0]
                coverage = enriched["coverage"][0]
                source_slice = tutorial["teaching_contract"]["main_chain"][0]
                self.assertEqual(tutorial["confirmed_relationship_count"], 0)
                self.assertEqual(source_slice["relationship_status"], "location-only")
                self.assertEqual(source_slice["relationship_id"], "")
                self.assertIn("端点符号未收录", source_slice["relationship_gap"])
                self.assertEqual(codemap["resolved_edge_ids"], [])
                self.assertEqual(len(codemap["relationship_gaps"]), 1)
                self.assertFalse(coverage["checks"]["resolved_relationships"])
                self.assertEqual(coverage["metrics"]["resolved_relationships"], 0)

    def test_curated_and_ordinary_tutorials_describe_different_reading_semantics(self) -> None:
        base = {
            "symbols": [{"id": "a", "qualified_name": "a"}],
            "relationships": [],
            "evidence": [],
        }
        curated = enrich_index(
            {
                **base,
                "features": [
                    {
                        "id": "curated",
                        "kind": "capability-cluster",
                        "title": "Curated",
                        "entrypoint": "a.py",
                        "steps": [{"order": 1, "symbol_id": "a", "path": "a.py", "line_start": 1}],
                    }
                ],
            }
        )["tutorials"][0]
        ordinary = enrich_index(
            {
                **base,
                "features": [
                    {
                        "id": "ordinary",
                        "kind": "http-route",
                        "title": "Ordinary",
                        "entrypoint": "GET /x",
                        "steps": [{"order": 1, "symbol_id": "a", "path": "a.py", "line_start": 1}],
                    }
                ],
            }
        )["tutorials"][0]

        self.assertIn("curated contract-selected slices", curated["reading_order_semantics"])
        self.assertNotIn("direct entry relationships only", curated["reading_order_semantics"])
        self.assertIn("direct entry relationships only", ordinary["reading_order_semantics"])

    def test_tutorial_state_gap_respects_narrow_evidence_backed_store_claim(self) -> None:
        enriched = enrich_index(
            {
                "features": [
                    {
                        "id": "feature_store",
                        "title": "Store",
                        "summary": "维护进程内索引。",
                        "entrypoint": "store.py",
                        "technology_claims": [
                            {
                                "dimension": "store",
                                "value": "in-memory",
                                "claim_scope": "只证明进程内 map。",
                                "confidence": "source-audited",
                                "evidence_ids": ["ev_store"],
                                "source_path": "store.py",
                            }
                        ],
                        "evidence_ids": ["ev_store"],
                        "steps": [
                            {
                                "order": 1,
                                "title": "状态所有权",
                                "source_role": "状态所有权",
                                "source_symbol": "Store",
                                "path": "store.py",
                                "line_start": 1,
                                "line_end": 5,
                                "claim_scope": "location-only: 没有已解析静态边",
                                "relationship_kind": "location-only",
                                "evidence_ids": ["ev_store"],
                            }
                        ],
                    }
                ],
                "symbols": [],
                "relationships": [],
                "evidence": [
                    {
                        "id": "ev_store",
                        "kind": "technology-claim:store",
                        "snippet": "cache = {}",
                    }
                ],
            }
        )

        tutorial = enriched["tutorials"][0]
        self.assertIn("store:in-memory", tutorial["gaps"]["state"])
        self.assertNotIn("没有带独立证据", tutorial["gaps"]["state"])
        self.assertEqual(
            tutorial["teaching_contract"]["main_chain"][0]["relationship_status"],
            "location-only",
        )
        self.assertIn("没有已解析静态边", tutorial["teaching_contract"]["main_chain"][0]["relationship_gap"])

    def test_coverage_lists_every_missing_static_signal(self) -> None:
        enriched = enrich_index(
            {
                "features": [{"id": "feature_unknown", "title": "Unknown", "steps": []}],
                "evidence": [],
                "symbols": [],
                "relationships": [],
            }
        )

        coverage = enriched["coverage"][0]
        self.assertEqual(coverage["score"], 0)
        self.assertEqual(coverage["status"], "minimal-signals")
        self.assertEqual(len(coverage["gaps"]), 5)
        self.assertEqual(
            coverage["metrics"],
            {"entrypoint": 0, "steps": 0, "evidence": 0, "test_evidence": 0, "resolved_relationships": 0},
        )


if __name__ == "__main__":
    unittest.main()
