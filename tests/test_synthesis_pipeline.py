from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_teacher.pipeline.synthesis import (
    SEMANTIC_REVIEW_CALLS_PER_RUN,
    _adopt_valid_inventory_cache,
    _bind_report_chapter_ids,
    _model_workspace_for_pack,
    _packet_sha256,
    _review_and_repair_inventory,
    _synthesize_with_codex,
)
from repo_teacher.pipeline.codegraph import (
    _augment_pack_with_codegraph_context,
    filter_codegraph_context,
)
from repo_teacher.pipeline.evidence_packets import (
    _build_global_business_inventory_pack,
)
from repo_teacher.pipeline.partitioning import (
    expand_oversized_module_scopes,
    require_packet_budget,
    split_shards_by_budget,
)


class SynthesisPipelineTest(unittest.TestCase):
    @staticmethod
    def _passed_review(capability_id: str) -> dict[str, object]:
        return {
            "status": "passed",
            "checks": {
                "product_positioning": "passed",
                    "business_semantics": "passed",
                "causal_evidence": "passed",
                "product_coverage": "passed",
            },
            "reviewed_capability_ids": [capability_id],
            "issues": [],
        }

    def test_inventory_shards_split_by_packet_budget_without_losing_modules(self) -> None:
        sizes = {
            ("a", "b", "c", "d"): 900,
            ("a", "b"): 400,
            ("c", "d"): 440,
        }
        shards, metrics = split_shards_by_budget(
            [["a", "b", "c", "d"]],
            measure=lambda modules: sizes[tuple(modules)],
            byte_budget=500,
            token_budget=500,
            max_shards=4,
        )
        self.assertEqual(shards, [["a", "b"], ["c", "d"]])
        self.assertEqual([item["packet_bytes"] for item in metrics], [400, 440])
        self.assertEqual(
            sorted(module for shard in shards for module in shard),
            ["a", "b", "c", "d"],
        )

    def test_semantic_review_is_a_single_terminal_stage(self) -> None:
        self.assertEqual(SEMANTIC_REVIEW_CALLS_PER_RUN, 1)

    def test_packet_identity_ignores_execution_only_project_metadata(self) -> None:
        first = {
            "project": {
                "commit": "abc",
                "path": "/tmp/random-snapshot-a/repo",
                "git_root": "/tmp/random-snapshot-a/repo",
                "analysis_fingerprint": "analyzer-build-a",
            },
            "evidence": [{"path": "src/main.py"}],
        }
        second = {
            "project": {
                "commit": "abc",
                "path": "/tmp/random-snapshot-b/repo",
                "git_root": "/tmp/random-snapshot-b/repo",
                "analysis_fingerprint": "analyzer-build-b",
            },
            "evidence": [{"path": "src/main.py"}],
        }

        self.assertEqual(_packet_sha256(first), _packet_sha256(second))

        second["evidence"][0]["path"] = "src/changed.py"
        self.assertNotEqual(_packet_sha256(first), _packet_sha256(second))

    def test_direct_report_ids_are_bound_to_canonical_feature_anchors(self) -> None:
        report = {
            "project": {
                "overview": {
                    "capability_order": ["voice", "workflow"],
                    "supporting_capability_ids": ["workflow"],
                    "core_product_axes": [
                        {"capability_ids": ["voice", "workflow"]}
                    ],
                }
            }
        }
        chapters = [
            {
                "id": "voice",
                "title": "实时语音会话",
                "source_feature_ids": ["feature_transport", "feature_pipeline"],
            },
            {
                "id": "workflow",
                "title": "对话流程编排",
                "source_feature_ids": ["feature_flow"],
            },
        ]

        bound = _bind_report_chapter_ids(report, chapters)

        identifiers = [item["id"] for item in bound]
        self.assertTrue(all(str(item).startswith("capability_") for item in identifiers))
        self.assertEqual(
            report["project"]["overview"]["capability_order"], identifiers
        )
        self.assertEqual(
            report["project"]["overview"]["supporting_capability_ids"],
            [identifiers[1]],
        )
        self.assertEqual(
            report["project"]["overview"]["core_product_axes"][0]["capability_ids"],
            identifiers,
        )

    def test_direct_report_workspace_identity_changes_with_prompt_or_provider(self) -> None:
        canonical = {
            "source_manifest_sha256": "manifest",
            "files": [{"path": "src/main.py", "sha256": "abc"}],
        }
        pack = {
            "project": {
                "commit": "deadbeef",
                "analysis_fingerprint": "fp-1",
            }
        }

        _, workspace = _model_workspace_for_pack(
            Path("/repo"),
            pack,
            canonical,
            "codex",
        )
        first = json.loads(
            (workspace / "run-identity.json").read_text(encoding="utf-8")
        )

        with patch(
            "repo_teacher.pipeline.synthesis._model_prompt",
            return_value="prompt changed",
        ):
            _, workspace = _model_workspace_for_pack(
                Path("/repo"),
                pack,
                canonical,
                "codex",
            )
        second = json.loads(
            (workspace / "run-identity.json").read_text(encoding="utf-8")
        )

        _, workspace = _model_workspace_for_pack(
            Path("/repo"),
            pack,
            canonical,
            "deepseek",
        )
        third = json.loads(
            (workspace / "run-identity.json").read_text(encoding="utf-8")
        )

        self.assertNotEqual(first["identity_sha256"], second["identity_sha256"])
        self.assertNotEqual(first["identity_sha256"], third["identity_sha256"])

    def test_global_business_pack_prioritizes_business_hints_over_navigation_only_hints(
        self,
    ) -> None:
        pack = {
            "schema_version": "test",
            "project": {},
            "instructions": [],
            "required_chapter_sections": [],
            "modules": [],
            "reading_path": [],
            "capability_graph": {
                "schema_version": "graph",
                "stats": {},
                "feature_slices": [
                    {
                        "id": "slice-1",
                        "seed_nodes": [{"path": "src/core.py"}],
                        "implementation_nodes": [{"path": "src/core.py"}],
                        "central_nodes": [],
                        "resolved_edges": [],
                        "component_ids": [],
                        "source_feature_ids": ["feature-business-1"],
                    },
                    {
                        "id": "slice-2",
                        "seed_nodes": [{"path": "src/voice.py"}],
                        "implementation_nodes": [{"path": "src/voice.py"}],
                        "central_nodes": [],
                        "resolved_edges": [],
                        "component_ids": [],
                        "source_feature_ids": ["feature-business-2"],
                    },
                ],
                "capability_candidates": [],
                "mechanism_clusters": [],
                "components": [],
                "module_dependencies": [],
                "unresolved_edge_examples": [],
                "interpretation_contract": [],
            },
            "feature_hints": [
                {
                    "id": "graph-path-feature-a",
                    "kind": "graph-source-candidate",
                    "confidence": "graph-navigation-only",
                    "title": "源码导航锚点：src/a.py",
                    "technology_tags": ["graph-navigation", "candidate-only"],
                    "evidence_ids": ["e-nav-a"],
                    "steps": [{"path": "src/a.py", "evidence_ids": ["e-nav-a"]}],
                },
                {
                    "id": "graph-path-feature-b",
                    "kind": "graph-source-candidate",
                    "confidence": "graph-navigation-only",
                    "title": "源码导航锚点：src/b.py",
                    "technology_tags": ["graph-navigation", "candidate-only"],
                    "evidence_ids": ["e-nav-b"],
                    "steps": [{"path": "src/b.py", "evidence_ids": ["e-nav-b"]}],
                },
                {
                    "id": "feature-business-1",
                    "kind": "http-route",
                    "title": "实时语音会话",
                    "evidence_ids": ["e-business-1"],
                    "steps": [{"path": "src/core.py", "evidence_ids": ["e-business-1"]}],
                },
                {
                    "id": "feature-business-2",
                    "kind": "entrypoint-candidate",
                    "title": "工作流构建与发布",
                    "evidence_ids": ["e-business-2"],
                    "steps": [{"path": "src/voice.py", "evidence_ids": ["e-business-2"]}],
                },
            ],
            "evidence": [
                {
                    "id": "e-nav-a",
                    "path": "src/a.py",
                    "line_start": 1,
                    "line_end": 1,
                },
                {
                    "id": "e-nav-b",
                    "path": "src/b.py",
                    "line_start": 1,
                    "line_end": 1,
                },
                {
                    "id": "e-business-1",
                    "path": "src/core.py",
                    "line_start": 10,
                    "line_end": 20,
                },
                {
                    "id": "e-business-2",
                    "path": "src/voice.py",
                    "line_start": 30,
                    "line_end": 40,
                },
            ],
        }

        bounded = _build_global_business_inventory_pack(pack, hint_limit=2)
        selected_ids = [item["id"] for item in bounded["feature_hints"]]

        self.assertEqual(
            selected_ids,
            ["feature-business-1", "feature-business-2"],
        )

    def test_stage_cache_adoption_revalidates_old_inventory(self) -> None:
        packet = {
            "scope": {
                "allowed_source_paths": ["src/main.py"],
                "feature_ids": ["feature-1"],
                "evidence_ids": ["evidence-1"],
                "module_paths": ["src"],
                "require_module_coverage": False,
            },
            "feature_hints": [
                {
                    "id": "feature-1",
                    "evidence_ids": ["evidence-1"],
                    "steps": [{"path": "src/main.py"}],
                }
            ],
            "evidence": [
                {
                    "id": "evidence-1",
                    "path": "src/main.py",
                    "line_start": 1,
                    "line_end": 3,
                }
            ],
        }
        inventory = {
            "capabilities": [
                {
                    "id": "capability-1",
                    "source_feature_ids": ["feature-1"],
                    "evidence_ids": ["evidence-1"],
                    "source_refs": [
                        {"path": "src/main.py", "line_start": 1, "line_end": 3}
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as raw:
            stage_root = Path(raw)
            old = stage_root / "old"
            target = stage_root / "new"
            old.mkdir()
            target.mkdir()
            (old / "capability-inventory.json").write_text(
                json.dumps(inventory), encoding="utf-8"
            )

            self.assertTrue(
                _adopt_valid_inventory_cache(
                    stage_root=stage_root,
                    target_workspace=target,
                    packet=packet,
                )
            )
            self.assertTrue((target / "capability-inventory.json").is_file())

    def test_inventory_shard_fails_closed_when_one_module_exceeds_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "one indivisible module"):
            split_shards_by_budget(
                [["oversized"]],
                measure=lambda _modules: 900,
                byte_budget=500,
                token_budget=500,
            )

    def test_materialized_packet_budget_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "after CodeGraph materialization"):
            require_packet_budget(
                {"codegraph_exploration": "x" * 101},
                byte_budget=100,
                token_budget=100,
            )

    def test_default_budget_accepts_closed_domain_but_rejects_legacy_megapacket(
        self,
    ) -> None:
        accepted = require_packet_budget({"packet": "x" * 450_000})
        self.assertLessEqual(accepted["packet_bytes"], 500_000)
        with self.assertRaisesRegex(ValueError, "after CodeGraph materialization"):
            require_packet_budget({"packet": "x" * 893_000})

    def test_oversized_module_splits_by_real_child_paths_and_keeps_owner(self) -> None:
        scopes, owners = expand_oversized_module_scopes(
            ["backend/internal"],
            source_paths=[
                "backend/internal/domain/a.go",
                "backend/internal/httpapi/b.go",
                "backend/internal/root.go",
            ],
            measure=lambda selected: 900 if selected == ["backend/internal"] else 300,
            byte_budget=500,
            token_budget=500,
        )

        self.assertEqual(
            scopes,
            [
                "backend/internal/domain",
                "backend/internal/httpapi",
                "backend/internal/root.go",
            ],
        )
        self.assertEqual(set(owners.values()), {"backend/internal"})

    def test_indivisible_source_scope_within_hard_packet_limit_is_accepted(self) -> None:
        scopes, owners = expand_oversized_module_scopes(
            ["api/errors/failure.py"],
            source_paths=["api/errors/failure.py"],
            measure=lambda _selected: 407_511,
            byte_budget=500_000,
            token_budget=125_000,
        )

        self.assertEqual(scopes, ["api/errors/failure.py"])
        self.assertEqual(owners, {"api/errors/failure.py": "api/errors/failure.py"})

    def test_coze_scale_partition_keeps_every_packet_below_budget(self) -> None:
        modules = [f"domain-{index:02d}" for index in range(11)]
        shards, metrics = split_shards_by_budget(
            [modules],
            measure=lambda selected: 35_000 + 95_000 * len(selected),
            byte_budget=520_000,
            token_budget=130_000,
            max_shards=12,
        )

        self.assertEqual(
            sorted(module for shard in shards for module in shard), modules
        )
        self.assertTrue(all(item["packet_bytes"] <= 520_000 for item in metrics))
        self.assertTrue(all(item["estimated_tokens"] <= 130_000 for item in metrics))
        self.assertGreater(len(shards), 2)

    def test_codegraph_context_is_filtered_per_shard_with_closed_edges(self) -> None:
        filtered = filter_codegraph_context(
            {
                "selection_basis": "graph",
                "module_paths": ["backend", "frontend"],
                "source_paths": ["backend/a.py", "frontend/b.ts"],
                "nodes": [
                    {"id": "a", "path": "backend/a.py"},
                    {"id": "b", "path": "frontend/b.ts"},
                ],
                "edges": [
                    {
                        "id": "inside",
                        "source_path": "backend/a.py",
                        "target_path": "backend/c.py",
                    },
                    {
                        "id": "cross",
                        "source_path": "backend/a.py",
                        "target_path": "frontend/b.ts",
                    },
                ],
            },
            ["backend"],
        )

        self.assertEqual(filtered["source_paths"], ["backend/a.py"])
        self.assertEqual([item["id"] for item in filtered["nodes"]], ["a"])
        self.assertEqual([item["id"] for item in filtered["edges"]], ["inside"])
        self.assertEqual(filtered["module_paths"], ["backend"])

    def test_codegraph_context_augmentation_is_copy_on_write_and_closed(self) -> None:
        pack = {"evidence": [], "feature_hints": []}
        augmented = _augment_pack_with_codegraph_context(
            pack,
            {
                "source_paths": ["src/runtime.py"],
                "nodes": [
                    {
                        "path": "src/runtime.py",
                        "line_start": 4,
                        "line_end": 12,
                    }
                ],
            },
        )

        self.assertEqual(pack, {"evidence": [], "feature_hints": []})
        self.assertEqual(augmented["evidence"][0]["path"], "src/runtime.py")
        evidence_id = augmented["evidence"][0]["id"]
        self.assertEqual(augmented["feature_hints"][0]["evidence_ids"], [evidence_id])

    def test_inventory_only_uses_one_analyst_call_plus_independent_review(self) -> None:
        inventory = {
            "capabilities": [
                {
                    "id": "agent-worker",
                    "title": "服务端 Agent 任务执行",
                }
            ],
            "module_dispositions": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            workspace = root / "workspace"
            source.mkdir()
            workspace.mkdir()
            packet = {
                "scope": {
                    "allowed_source_paths": [],
                    "required_product_module_paths": [],
                }
            }
            with (
                patch("repo_teacher.pipeline.synthesis._inventory_module_shards", return_value=[["src"]]),
                patch(
                    "repo_teacher.pipeline.synthesis._codegraph_domain_context",
                    return_value={"source_paths": [], "nodes": [], "edges": []},
                ),
                patch(
                    "repo_teacher.pipeline.synthesis._augment_pack_with_codegraph_context",
                    side_effect=lambda value, context: value,
                ),
                patch(
                    "repo_teacher.pipeline.synthesis._build_global_business_inventory_pack",
                    return_value=packet,
                ),
                patch(
                    "repo_teacher.pipeline.synthesis._add_project_navigation",
                    side_effect=lambda value, full: value,
                ),
                patch(
                    "repo_teacher.pipeline.synthesis._attach_source_excerpts",
                    side_effect=lambda value, root, **_kwargs: value,
                ),
                patch("repo_teacher.pipeline.synthesis._codegraph_explore_domain", return_value="graph"),
                patch(
                    "repo_teacher.pipeline.synthesis._materialize_source_slice", return_value=source
                ),
                patch(
                    "repo_teacher.pipeline.synthesis._stage_model_json",
                    return_value=source / "analysis-pack-inventory.json",
                ),
                patch("repo_teacher.pipeline.synthesis._run_codex_json", return_value=inventory) as model,
                patch(
                    "repo_teacher.pipeline.synthesis.run_inventory_semantic_review",
                    return_value=self._passed_review("agent-worker"),
                ) as reviewer,
                patch(
                    "repo_teacher.pipeline.synthesis._canonicalize_inventory_payload",
                    side_effect=lambda value, full: value,
                ),
                patch("repo_teacher.pipeline.synthesis._require_inventory_scope"),
                patch("repo_teacher.pipeline.synthesis._require_inventory_against_pack"),
                patch("repo_teacher.pipeline.synthesis._group_inventory_for_humans") as grouping,
            ):
                result = _synthesize_with_codex(
                    source,
                    {},
                    workspace,
                    60,
                    provider="codex",
                    inventory_only=True,
                )

        self.assertEqual(result["capabilities"][0]["id"], "agent-worker")
        model.assert_called_once()
        reviewer.assert_called_once()
        grouping.assert_not_called()

    def test_large_inventory_uses_bounded_business_domain_pipeline(self) -> None:
        grouped = {
            "capabilities": [{"id": "task", "title": "数字员工任务执行"}],
            "grouping_complete": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            workspace = root / "workspace"
            source.mkdir()
            workspace.mkdir()
            with (
                patch(
                    "repo_teacher.pipeline.synthesis._inventory_module_shards",
                    return_value=[["frontend"], ["backend"], ["worker"]],
                ),
                patch(
                    "repo_teacher.pipeline.synthesis._codegraph_domain_context",
                    return_value={"source_paths": [], "nodes": [], "edges": []},
                ),
                patch(
                    "repo_teacher.pipeline.synthesis._augment_pack_with_codegraph_context",
                    side_effect=lambda value, context: value,
                ),
                patch(
                    "repo_teacher.pipeline.synthesis._synthesize_inventory_shards",
                    return_value=(
                        {"capabilities": [{"id": "raw"}], "module_dispositions": []},
                        {"product_type": "数字员工平台"},
                    ),
                ) as domains,
                patch(
                    "repo_teacher.pipeline.synthesis._add_project_navigation",
                    return_value={"product_navigation": []},
                ),
                patch(
                    "repo_teacher.pipeline.synthesis._group_inventory_for_humans",
                    return_value=grouped,
                ) as grouping,
                patch(
                    "repo_teacher.pipeline.synthesis._canonicalize_inventory_payload",
                    side_effect=lambda value, full: value,
                ),
                patch("repo_teacher.pipeline.synthesis._require_inventory_against_pack"),
                patch(
                    "repo_teacher.pipeline.synthesis.run_inventory_semantic_review",
                    return_value=self._passed_review("task"),
                ) as reviewer,
                patch("repo_teacher.pipeline.synthesis._run_codex_json") as global_model,
            ):
                result = _synthesize_with_codex(
                    source,
                    {},
                    workspace,
                    60,
                    provider="codex",
                    inventory_only=True,
                )

        domains.assert_called_once()
        grouping.assert_called_once()
        global_model.assert_not_called()
        reviewer.assert_called_once()
        self.assertEqual(result["project_summary"]["product_type"], "数字员工平台")
        self.assertEqual(result["capabilities"][0]["id"], "task")

    def test_failed_semantic_review_stops_without_regrouping(self) -> None:
        failed = {
            "status": "failed",
            "checks": {
                "product_positioning": "failed",
                    "business_semantics": "failed",
                "causal_evidence": "passed",
                "product_coverage": "passed",
            },
            "reviewed_capability_ids": ["health"],
            "issues": [
                {
                    "code": "business-outcome-missing",
                    "capability_id": "health",
                    "message": "健康接口不是独立业务能力",
                    "retry_stage": "global-grouping",
                    "affected_candidate_ids": ["raw"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with (
                patch(
                    "repo_teacher.pipeline.synthesis.run_inventory_semantic_review",
                    return_value=failed,
                ) as reviewer,
                patch(
                    "repo_teacher.pipeline.synthesis._group_inventory_for_humans",
                ) as regroup,
                patch(
                    "repo_teacher.pipeline.synthesis._canonicalize_inventory_payload",
                    side_effect=lambda value, _pack: value,
                ),
                patch("repo_teacher.pipeline.synthesis._require_inventory_against_pack"),
            ):
                with self.assertRaisesRegex(
                    ValueError, "failed independent semantic review"
                ):
                    _review_and_repair_inventory(
                        source=workspace,
                        pack={},
                        candidate_payload={"capabilities": [{"id": "raw"}]},
                        inventory_payload={"capabilities": [{"id": "health"}]},
                        workspace=workspace,
                        deadline=10**12,
                        provider="codex",
                        product_navigation=[],
                    )

        reviewer.assert_called_once()
        regroup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
