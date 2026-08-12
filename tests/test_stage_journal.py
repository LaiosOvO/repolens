from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_teacher.pipeline.journal import PipelineJournal


class PipelineJournalTest(unittest.TestCase):
    def test_failure_preserves_prior_pass_and_retries_only_failed_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.journal.json"
            journal = PipelineJournal(
                path,
                pipeline="inventory",
                run_identity={"source_manifest": "abc", "model": "gpt"},
            )
            self.assertTrue(journal.start("evidence-pack", inputs={"index": "1"}))
            journal.pass_stage("evidence-pack", outputs={"pack": "2"})
            self.assertTrue(journal.start("capability-inventory", inputs={"pack": "2"}))
            journal.fail_stage(
                "capability-inventory",
                code="provider-timeout",
                message="timed out",
            )

            resumed = PipelineJournal(
                path,
                pipeline="inventory",
                run_identity={"source_manifest": "abc", "model": "gpt"},
            )
            self.assertFalse(
                resumed.start("evidence-pack", inputs={"index": "1"})
            )
            self.assertTrue(
                resumed.start("capability-inventory", inputs={"pack": "2"})
            )
            state = resumed.snapshot()

        stages = {item["id"]: item for item in state["stages"]}
        self.assertEqual(stages["evidence-pack"]["attempt"], 1)
        self.assertEqual(stages["capability-inventory"]["attempt"], 2)
        self.assertEqual(stages["capability-inventory"]["status"], "started")

    def test_identity_change_starts_a_new_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.journal.json"
            first = PipelineJournal(
                path, pipeline="report", run_identity={"prompt": "v1"}
            )
            first.start("chapters", inputs={"inventory": "a"})
            first.pass_stage("chapters", outputs={"report": "b"})

            second = PipelineJournal(
                path, pipeline="report", run_identity={"prompt": "v2"}
            )

        self.assertEqual(second.snapshot()["stages"], [])

    def test_stage_duration_seconds_persist_for_passed_and_failed_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.journal.json"
            timeline = iter(
                (
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:05+00:00",
                    "2026-01-01T00:00:05+00:00",
                    "2026-01-01T00:00:08+00:00",
                    "2026-01-01T00:00:08+00:00",
                    "2026-01-01T00:00:09+00:00",
                    "2026-01-01T00:00:09+00:00",
                    "2026-01-01T00:00:15+00:00",
                    "2026-01-01T00:00:15+00:00",
                )
            )
            with patch(
                "repo_teacher.pipeline.journal._now",
                side_effect=lambda: next(timeline),
            ):
                journal = PipelineJournal(
                    path,
                    pipeline="inventory",
                    run_identity={"source_manifest": "abc", "model": "gpt"},
                )
                journal.start("evidence-pack", inputs={"index": "1"})
                journal.pass_stage("evidence-pack", outputs={"pack": "2"})
                journal.start("capability-inventory", inputs={"pack": "2"})
                journal.fail_stage(
                    "capability-inventory",
                    code="provider-timeout",
                    message="timed out",
                )

            stages = {item["id"]: item for item in journal.snapshot()["stages"]}

        self.assertEqual(stages["evidence-pack"]["duration_seconds"], 3.0)
        self.assertEqual(stages["capability-inventory"]["duration_seconds"], 6.0)


if __name__ == "__main__":
    unittest.main()
