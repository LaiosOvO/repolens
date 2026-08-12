from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from repo_teacher.pipeline.linear_pipeline import (
    LINEAR_REPORT_STAGES,
    LinearStageArtifacts,
)


class LinearPipelineTest(unittest.TestCase):
    def test_stage_contract_is_a_fixed_sequence_not_a_graph(self) -> None:
        self.assertEqual(
            LINEAR_REPORT_STAGES,
            (
                "01-source-snapshot",
                "02-code-index",
                "03-content-generation",
                "04-evidence-validation",
                "05-publication",
            ),
        )

    def test_failure_is_recorded_once_and_points_to_the_same_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifacts = LinearStageArtifacts(Path(directory))
            artifacts.pass_stage(
                "02-code-index",
                inputs={"evidence": "abc"},
                output={"capabilities": [{"id": "voice"}]},
            )
            failed = artifacts.fail_stage(
                "03-content-generation",
                inputs={"candidates": "def"},
                error="candidate partition incomplete",
            )

        self.assertEqual(failed["attempt"], 1)
        self.assertEqual(failed["stage"], "03-content-generation")
        self.assertNotIn("retry_stage", failed)

    def test_manifest_turns_passed_after_all_linear_stages_finish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifacts = LinearStageArtifacts(Path(directory))
            for stage in LINEAR_REPORT_STAGES:
                artifacts.pass_stage(
                    stage,
                    inputs={"stage": stage},
                    output={"stage": stage},
                )
            manifest = json.loads(
                (Path(directory) / "stages" / "pipeline.json").read_text(
                    encoding="utf-8"
                )
            )
            published = artifacts.published_artifacts()

        self.assertEqual(manifest["status"], "passed")
        self.assertIsNone(manifest["current_stage"])
        self.assertEqual(
            [item["stage"] for item in manifest["stages"]],
            list(LINEAR_REPORT_STAGES),
        )
        self.assertEqual(
            {f"pipeline/{stage}.json" for stage in LINEAR_REPORT_STAGES}
            | {"pipeline/pipeline.json", "pipeline/performance.json"},
            set(published),
        )

    def test_cached_stage_requires_the_same_input_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifacts = LinearStageArtifacts(Path(directory))
            artifacts.pass_stage(
                "03-content-generation",
                inputs={"packet": "one", "prompt": "v1"},
                output={"artifact": "human-report.json"},
            )

            self.assertTrue(
                artifacts.stage_passed(
                    "03-content-generation",
                    inputs={"packet": "one", "prompt": "v1"},
                )
            )
            self.assertFalse(
                artifacts.stage_passed(
                    "03-content-generation",
                    inputs={"packet": "one", "prompt": "v2"},
                )
            )


if __name__ == "__main__":
    unittest.main()
