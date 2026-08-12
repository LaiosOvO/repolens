from __future__ import annotations

import unittest

from repo_teacher.pipeline.report_outputs import build_report_output_sidecars


class ReportOutputSidecarsTest(unittest.TestCase):
    def _chapter(self) -> dict[str, object]:
        return {
            "id": "voice-runtime",
            "mechanism_model": {"plain_summary": "PCM → VAD → ASR → LLM → TTS。"},
            "runtime_story": {"steps": ["采集", "识别", "合成"]},
            "state_flow": [{"stage": "listen"}, {"stage": "speak"}],
            "source_refs": [{"path": "a.py"}, {"path": "b.py"}, {"path": "c.py"}],
            "boundary": {"supported": ["voice"], "unsupported": ["video"]},
            "reuse_plan": {
                "take": ["pipeline"],
                "adapt": ["provider"],
                "avoid": ["global state"],
                "verify": ["interrupt"],
            },
        }

    def test_real_chapter_and_validation_sidecars_are_materialized(self) -> None:
        artifacts = build_report_output_sidecars(
            narrative={"chapters": [self._chapter()]},
            source_manifest_sha256="a" * 64,
            inventory_digest="b" * 64,
        )

        chapter_paths = [path for path in artifacts if path.startswith("chapters/")]
        validation_paths = [
            path for path in artifacts if path.startswith("chapter-validation/")
        ]
        self.assertEqual(len(chapter_paths), 1)
        self.assertEqual(len(validation_paths), 1)
        self.assertEqual(artifacts[validation_paths[0]]["status"], "passed")
        self.assertEqual(
            artifacts["validation-report.json"]["checks"][
                "source_evidence_closure"
            ],
            "passed",
        )

    def test_missing_runtime_flow_fails_before_publication(self) -> None:
        chapter = self._chapter()
        chapter["runtime_story"] = {"steps": ["only-one"]}

        with self.assertRaisesRegex(ValueError, "runtime_flow"):
            build_report_output_sidecars(
                narrative={"chapters": [chapter]},
                source_manifest_sha256="a" * 64,
                inventory_digest=None,
            )

    def test_publication_has_no_readability_review_gate(self) -> None:
        artifacts = build_report_output_sidecars(
            narrative={"chapters": [self._chapter()]},
            source_manifest_sha256="a" * 64,
            inventory_digest="b" * 64,
        )

        self.assertEqual(artifacts["validation-report.json"]["status"], "passed")
        self.assertNotIn(
            "human_readability",
            artifacts["validation-report.json"]["checks"],
        )
        self.assertNotIn("human-readability-review.json", artifacts)


if __name__ == "__main__":
    unittest.main()
