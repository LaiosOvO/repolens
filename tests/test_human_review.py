from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from repo_teacher.pipeline.human_review import (
    require_human_readability_review,
    run_human_readability_review,
)


class HumanReviewTest(unittest.TestCase):
    def test_complete_pass_is_accepted(self) -> None:
        require_human_readability_review(
            {
                "status": "passed",
                "checks": {
                    "project_positioning": "passed",
                    "chapter_coverage": "passed",
                    "interaction_explainer": "passed",
                    "implementation_depth": "passed",
                    "selection_value": "passed",
                },
                "project_overview_verdict": {
                    "status": "pass",
                    "summary": "先讲清项目本质与架构主轴。",
                    "missing_answers": [],
                    "evidence_locations": ["project-overview"],
                },
                "chapter_verdicts": [
                    {
                        "capability_id": "voice-session",
                        "status": "pass",
                        "one_liner": "这是一个实时语音会话编排能力。",
                        "thirty_second_restatement": "先收音再做状态判定，然后把文本和音频结果回传。",
                        "checks": {
                            "summary_clarity": "passed",
                            "interaction_diagram": "passed",
                            "implementation_mechanism": "passed",
                            "selection_signal": "passed",
                        },
                        "missing_answers": [],
                        "evidence_locations": ["chapters/voice-session"],
                    }
                ],
                "blocking_issues": [],
                "retry_stage": "none",
            },
            ["voice-session"],
        )

    def test_duplicate_or_missing_chapter_ids_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact capability set"):
            require_human_readability_review(
                {
                    "status": "failed",
                    "checks": {
                        "project_positioning": "passed",
                        "chapter_coverage": "failed",
                        "interaction_explainer": "passed",
                        "implementation_depth": "passed",
                        "selection_value": "passed",
                    },
                    "project_overview_verdict": {
                        "status": "pass",
                        "summary": "overview",
                        "missing_answers": [],
                        "evidence_locations": ["project-overview"],
                    },
                    "chapter_verdicts": [
                        {
                            "capability_id": "voice-session",
                            "status": "pass",
                            "one_liner": "one",
                            "thirty_second_restatement": "restatement",
                            "checks": {
                                "summary_clarity": "passed",
                                "interaction_diagram": "passed",
                                "implementation_mechanism": "passed",
                                "selection_signal": "passed",
                            },
                            "missing_answers": [],
                            "evidence_locations": ["chapters/voice-session"],
                        },
                        {
                            "capability_id": "voice-session",
                            "status": "fail",
                            "one_liner": "duplicate",
                            "thirty_second_restatement": "duplicate",
                            "checks": {
                                "summary_clarity": "failed",
                                "interaction_diagram": "passed",
                                "implementation_mechanism": "passed",
                                "selection_signal": "passed",
                            },
                            "missing_answers": ["本质没讲清"],
                            "evidence_locations": ["chapters/voice-session"],
                        },
                    ],
                    "blocking_issues": [
                        {
                            "code": "thirty-second-restatement-failed",
                            "capability_id": "voice-session",
                            "location": "chapters/voice-session",
                            "message": "重复覆盖导致无法确认章节。",
                            "retry_stage": "chapter-generation",
                        }
                    ],
                    "retry_stage": "chapter-generation",
                },
                ["voice-session", "worker-queue"],
            )

    def test_pass_with_blocking_issues_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "claimed PASS"):
            require_human_readability_review(
                {
                    "status": "passed",
                    "checks": {
                        "project_positioning": "passed",
                        "chapter_coverage": "passed",
                        "interaction_explainer": "passed",
                        "implementation_depth": "passed",
                        "selection_value": "passed",
                    },
                    "project_overview_verdict": {
                        "status": "pass",
                        "summary": "overview",
                        "missing_answers": [],
                        "evidence_locations": ["project-overview"],
                    },
                    "chapter_verdicts": [
                        {
                            "capability_id": "voice-session",
                            "status": "pass",
                            "one_liner": "one",
                            "thirty_second_restatement": "restatement",
                            "checks": {
                                "summary_clarity": "passed",
                                "interaction_diagram": "passed",
                                "implementation_mechanism": "passed",
                                "selection_signal": "passed",
                            },
                            "missing_answers": [],
                            "evidence_locations": ["chapters/voice-session"],
                        }
                    ],
                    "blocking_issues": [
                        {
                            "code": "interaction-diagram-not-concrete",
                            "capability_id": "voice-session",
                            "location": "chapters/voice-session",
                            "message": "交互图没有真实参与者。",
                            "retry_stage": "chapter-generation",
                        }
                    ],
                    "retry_stage": "none",
                },
                ["voice-session"],
            )

    def test_run_human_review_writes_artifact_and_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            app_path = source / "app.py"
            app_path.write_text(
                "def run_voice_session():\n    return 'ok'\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(app_path.read_bytes()).hexdigest()
            pack = {
                "schema_version": "repo-teacher-analysis-pack/v1",
                "project": {"path": str(source)},
                "instructions": [],
                "required_chapter_sections": [],
                "modules": [{"path": "app.py"}],
                "reading_path": [{"path": "app.py"}],
                "feature_hints": [
                    {
                        "id": "feature.voice",
                        "evidence_ids": ["evidence.voice"],
                        "path": "app.py",
                    }
                ],
                "evidence": [
                    {
                        "id": "evidence.voice",
                        "path": "app.py",
                        "line_start": 1,
                        "line_end": 2,
                        "claim": "run_voice_session returns a response.",
                    }
                ],
                "files": [{"path": "app.py", "sha256": digest}],
            }
            inventory = {
                "capabilities": [
                    {
                        "id": "voice-session",
                        "title": "实时语音会话",
                        "source_feature_ids": ["feature.voice"],
                        "evidence_ids": ["evidence.voice"],
                        "source_refs": [
                            {
                                "path": "app.py",
                                "line_start": 1,
                                "line_end": 2,
                                "claim": "Voice session entry.",
                            }
                        ],
                    }
                ]
            }
            report = {
                "project_overview": {
                    "one_liner": "语音会话项目",
                    "source_refs": [
                        {
                            "path": "app.py",
                            "line_start": 1,
                            "line_end": 2,
                            "claim": "Project overview evidence.",
                        }
                    ],
                },
                "chapters": [
                    {
                        "id": "voice-session",
                        "title": "实时语音会话",
                        "source_refs": [
                            {
                                "path": "app.py",
                                "line_start": 1,
                                "line_end": 2,
                                "claim": "Chapter evidence.",
                            }
                        ],
                    }
                ],
            }
            calls: list[dict[str, object]] = []

            def runner(**kwargs: object) -> dict[str, object]:
                calls.append(kwargs)
                return {
                    "status": "passed",
                    "checks": {
                        "project_positioning": "passed",
                        "chapter_coverage": "passed",
                        "interaction_explainer": "passed",
                        "implementation_depth": "passed",
                        "selection_value": "passed",
                    },
                    "project_overview_verdict": {
                        "status": "pass",
                        "summary": "overview ok",
                        "missing_answers": [],
                        "evidence_locations": ["project-overview"],
                    },
                    "chapter_verdicts": [
                        {
                            "capability_id": "voice-session",
                            "status": "pass",
                            "one_liner": "本质是实时语音往返。",
                            "thirty_second_restatement": "采集、处理、回传。",
                            "checks": {
                                "summary_clarity": "passed",
                                "interaction_diagram": "passed",
                                "implementation_mechanism": "passed",
                                "selection_signal": "passed",
                            },
                            "missing_answers": [],
                            "evidence_locations": ["chapters/voice-session"],
                        }
                    ],
                    "blocking_issues": [],
                    "retry_stage": "none",
                }

            workspace = root / "workspace"
            first = run_human_readability_review(
                source=source,
                pack=pack,
                inventory_payload=inventory,
                report_payload=report,
                workspace=workspace,
                provider="codex",
                timeout=30,
                runner=runner,
            )
            second = run_human_readability_review(
                source=source,
                pack=pack,
                inventory_payload=inventory,
                report_payload=report,
                workspace=workspace,
                provider="codex",
                timeout=30,
                runner=runner,
            )

            self.assertEqual(first["reviewer"], "human-report-reviewer")
            self.assertEqual(first, second)
            self.assertEqual(len(calls), 1)
            self.assertTrue(
                (
                    workspace
                    / "human-readability-review"
                    / "human-readability-review.json"
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
