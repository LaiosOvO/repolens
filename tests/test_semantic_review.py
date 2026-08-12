from __future__ import annotations

import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from repo_teacher.pipeline.semantic_review import (
    _stable_review_packet_sha256,
    _compact_raw_candidates,
    _normalize_inventory_semantic_review,
    require_inventory_semantic_review,
    run_inventory_semantic_review,
)


class SemanticReviewTest(unittest.TestCase):
    def test_review_identity_ignores_ephemeral_snapshot_location(self) -> None:
        first = {
            "project": {"commit": "abc", "path": "/tmp/snapshot-a/repo"},
            "scope": {"allowed_source_paths": ["src/task.py"]},
        }
        second = {
            "project": {"commit": "abc", "path": "/tmp/snapshot-b/repo"},
            "scope": {"allowed_source_paths": ["src/task.py"]},
        }

        self.assertEqual(
            _stable_review_packet_sha256(first),
            _stable_review_packet_sha256(second),
        )

    def test_normalization_deduplicates_candidate_ids_without_hiding_unknowns(self) -> None:
        normalized = _normalize_inventory_semantic_review(
            {
                "issues": [
                    {
                        "affected_candidate_ids": ["candidate-a", "candidate-a"]
                    }
                ]
            }
        )

        self.assertEqual(
            normalized["issues"][0]["affected_candidate_ids"], ["candidate-a"]
        )

        with self.assertRaisesRegex(ValueError, "exact affected candidate closure"):
            require_inventory_semantic_review(
                {
                    "status": "failed",
                    "checks": {
                        "product_positioning": "passed",
                        "business_semantics": "failed",
                        "causal_evidence": "passed",
                        "product_coverage": "passed",
                    },
                    "reviewed_capability_ids": ["capability-a"],
                    "issues": [
                        {
                            "code": "business-outcome-missing",
                            "capability_id": "capability-a",
                            "message": "missing outcome",
                            "retry_stage": "global-grouping",
                            "affected_candidate_ids": ["unknown-candidate"],
                        }
                    ],
                },
                ["capability-a"],
                ["candidate-a"],
            )

    def test_raw_candidate_coverage_packet_is_bounded_and_drops_full_prose(self) -> None:
        references = [
            {"path": f"backend/domain/file-{index}.go", "line_start": index + 1}
            for index in range(12)
        ]
        compact, paths = _compact_raw_candidates(
            {
                "capabilities": [
                    {
                        "id": "candidate-task",
                        "title": "任务执行",
                        "one_sentence_summary": "提交任务并等待 Worker 回传结果。",
                        "mechanism": "x" * 200_000,
                        "source_feature_ids": ["feature-task"],
                        "source_refs": references,
                    }
                ]
            }
        )

        self.assertEqual(len(compact), 1)
        self.assertNotIn("mechanism", compact[0])
        self.assertEqual(compact[0]["source_ref_count"], 12)
        self.assertEqual(len(compact[0]["source_refs"]), 6)
        self.assertEqual(len(paths), 12)

    def test_complete_pass_is_accepted(self) -> None:
        require_inventory_semantic_review(
            {
                "status": "passed",
                "checks": {
                    "product_positioning": "passed",
                    "business_semantics": "passed",
                    "causal_evidence": "passed",
                    "product_coverage": "passed",
                },
                "reviewed_capability_ids": ["task"],
                "issues": [],
            },
            ["task"],
        )

    def test_semantic_false_positive_has_stable_failure_issue(self) -> None:
        review = {
            "status": "failed",
            "checks": {
                "product_positioning": "failed",
                    "business_semantics": "failed",
                "causal_evidence": "failed",
                "product_coverage": "passed",
            },
            "reviewed_capability_ids": ["health"],
            "issues": [
                {
                    "code": "business-outcome-missing",
                    "capability_id": "health",
                    "message": "健康检查没有独立用户结果。",
                    "retry_stage": "global-grouping",
                    "affected_candidate_ids": ["health-candidate"],
                }
            ],
        }

        require_inventory_semantic_review(review, ["health"])
        self.assertEqual(review["issues"][0]["code"], "business-outcome-missing")

    def test_pass_with_issues_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "claimed PASS"):
            require_inventory_semantic_review(
                {
                    "status": "passed",
                    "checks": {
                        "product_positioning": "passed",
                    "business_semantics": "passed",
                        "causal_evidence": "passed",
                        "product_coverage": "passed",
                    },
                    "reviewed_capability_ids": ["health"],
                    "issues": [
                        {
                            "code": "business-outcome-missing",
                            "capability_id": "health",
                            "message": "not a business outcome",
                            "retry_stage": "global-grouping",
                            "affected_candidate_ids": ["health-candidate"],
                        }
                    ],
                },
                ["health"],
            )

    def test_delta_review_packet_excludes_frozen_source_and_candidates(self) -> None:
        pack = {
            "project": {},
            "files": [
                {"path": "src/stable.py", "sha256": "a" * 64, "lines": 1},
                {"path": "src/fixed.py", "sha256": "b" * 64, "lines": 1},
            ],
            "scope": {},
        }
        inventory = {
            "capabilities": [
                {
                    "id": "stable",
                    "title": "稳定能力",
                    "source_refs": [
                        {"path": "src/stable.py", "line_start": 1, "line_end": 1}
                    ],
                },
                {
                    "id": "fixed",
                    "title": "返修能力",
                    "source_refs": [
                        {"path": "src/fixed.py", "line_start": 1, "line_end": 1}
                    ],
                },
            ]
        }
        candidates = {
            "capabilities": [
                {
                    "id": "raw-stable",
                    "source_refs": [{"path": "src/stable.py"}],
                },
                {
                    "id": "raw-fixed",
                    "source_refs": [{"path": "src/fixed.py"}],
                },
            ]
        }
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {
                "status": "passed",
                "checks": {
                    "product_positioning": "passed",
                    "business_semantics": "passed",
                    "causal_evidence": "passed",
                    "product_coverage": "passed",
                },
                "reviewed_capability_ids": ["fixed"],
                "issues": [],
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "src").mkdir()
            (source / "src/stable.py").write_text("stable\n", encoding="utf-8")
            (source / "src/fixed.py").write_text("fixed\n", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            with (
                patch(
                    "repo_teacher.pipeline.semantic_review._build_chapter_batch_pack",
                    side_effect=lambda value, capabilities: {
                        **value,
                        "scope": {
                            "allowed_source_paths": [
                                ref["path"]
                                for capability in capabilities
                                for ref in capability["source_refs"]
                            ]
                        },
                    },
                ),
                patch(
                    "repo_teacher.pipeline.semantic_review._indexed_file_hashes",
                    return_value={"src/stable.py": "a", "src/fixed.py": "b"},
                ),
                patch(
                    "repo_teacher.pipeline.semantic_review._attach_source_excerpts",
                    side_effect=lambda value, _source, **_kwargs: value,
                ),
                patch(
                    "repo_teacher.pipeline.semantic_review._materialize_source_slice",
                    return_value=source,
                ),
                patch(
                    "repo_teacher.pipeline.semantic_review._stage_model_json",
                    side_effect=lambda _slice, name, _payload: source / name,
                ),
                patch("repo_teacher.pipeline.semantic_review.require_packet_budget"),
            ):
                run_inventory_semantic_review(
                    source=source,
                    pack=pack,
                    candidate_payload=candidates,
                    inventory_payload=inventory,
                    workspace=workspace,
                    provider="codex",
                    timeout=60,
                    runner=runner,
                    review_capability_ids={"fixed"},
                    review_candidate_ids={"raw-fixed"},
                )

            review_pack = json.loads(
                (workspace / "inventory-semantic-review/analysis-pack-review.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(review_pack["review_mode"], "local-repair-delta")
        self.assertEqual(
            [item["id"] for item in review_pack["raw_candidate_inventory"]["capabilities"]],
            ["raw-fixed"],
        )
        self.assertEqual(review_pack["scope"]["allowed_source_paths"], ["src/fixed.py"])
        self.assertEqual(review_pack["accepted_capability_summaries"][0]["id"], "stable")
        self.assertIn("schema", captured)

    def test_cache_is_reused_only_for_identical_inventory_and_contract(self) -> None:
        pack = {
            "project": {},
            "files": [{"path": "src/task.py", "sha256": "a" * 64, "lines": 1}],
            "scope": {},
        }
        candidates = {
            "capabilities": [
                {"id": "raw-task", "source_refs": [{"path": "src/task.py"}]}
            ]
        }
        inventory = {
            "project_summary": {
                "product_type": "任务工具",
                "primary_actor": "用户",
                "primary_outcome": "完成任务",
                "main_runtime": "本地",
                "not_the_product": ["健康检查"],
            },
            "capabilities": [
                {
                    "id": "task",
                    "title": "执行任务",
                    "source_refs": [
                        {"path": "src/task.py", "line_start": 1, "line_end": 1}
                    ],
                }
            ],
        }
        calls = 0

        def runner(**_kwargs: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {
                "status": "passed",
                "checks": {
                    "product_positioning": "passed",
                    "business_semantics": "passed",
                    "causal_evidence": "passed",
                    "product_coverage": "passed",
                },
                "reviewed_capability_ids": ["task"],
                "issues": [],
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "src").mkdir()
            (source / "src/task.py").write_text("task\n", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            patches = (
                patch(
                    "repo_teacher.pipeline.semantic_review._build_chapter_batch_pack",
                    side_effect=lambda value, capabilities: {
                        **value,
                        "scope": {"allowed_source_paths": ["src/task.py"]},
                        "capabilities": capabilities,
                    },
                ),
                patch(
                    "repo_teacher.pipeline.semantic_review._indexed_file_hashes",
                    return_value={"src/task.py": "a"},
                ),
                patch(
                    "repo_teacher.pipeline.semantic_review._attach_source_excerpts",
                    side_effect=lambda value, _source, **_kwargs: value,
                ),
                patch(
                    "repo_teacher.pipeline.semantic_review._materialize_source_slice",
                    return_value=source,
                ),
                patch(
                    "repo_teacher.pipeline.semantic_review._stage_model_json",
                    side_effect=lambda _slice, name, _payload: source / name,
                ),
                patch("repo_teacher.pipeline.semantic_review.require_packet_budget"),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                for _ in range(2):
                    run_inventory_semantic_review(
                        source=source,
                        pack=pack,
                        candidate_payload=candidates,
                        inventory_payload=inventory,
                        workspace=workspace,
                        provider="codex",
                        timeout=60,
                        runner=runner,
                    )
                changed = json.loads(json.dumps(inventory))
                changed["project_summary"]["primary_outcome"] = "得到不同结果"
                run_inventory_semantic_review(
                    source=source,
                    pack=pack,
                    candidate_payload=candidates,
                    inventory_payload=changed,
                    workspace=workspace,
                    provider="codex",
                    timeout=60,
                    runner=runner,
                )

        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
