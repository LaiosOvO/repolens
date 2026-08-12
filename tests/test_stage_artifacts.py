from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_teacher.pipeline import build_report_stage_artifacts
from repo_teacher.pipeline.journal import PipelineJournal


class StageArtifactsTest(unittest.TestCase):
    def test_report_ledger_names_every_stage_and_preserves_module_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = PipelineJournal(
                Path(directory) / "report.run-manifest.json",
                pipeline="report",
                run_identity={"source_manifest": "manifest"},
            )
            for stage_id in (
                "01-graph-index",
                "02-evidence-pack",
                "03-capability-inventory",
                "04-project-overview",
                "05-chapter-generation",
                "06-validation",
            ):
                journal.start(stage_id, inputs={"stage": stage_id})
                journal.pass_stage(stage_id, outputs={"stage": stage_id})
            artifacts = build_report_stage_artifacts(
                canonical={
                    "stats": {"files": 3, "symbols": 4, "relationships": 5, "modules": 2},
                    "evidence": [{"id": "e1"}, {"id": "e2"}],
                },
                pack={"feature_hints": [{"id": "f1"}], "evidence": [{"id": "e1"}], "reading_path": []},
                inventory={
                    "capabilities": [{"id": "tasks"}],
                    "module_dispositions": [{"path": "worker", "capability_ids": ["tasks"]}],
                },
                narrative={
                    "project_overview": {"project_thesis": "任务平台"},
                    "chapters": [{"id": "tasks", "title": "任务执行", "source_refs": [{"path": "worker.go"}]}],
                },
                provider="codex",
                inventory_digest="abc",
                source_manifest_sha256="manifest",
                journal=journal.snapshot(),
                authoritative_journal="../report.run-manifest.json",
            )

        self.assertEqual(len(artifacts["run-manifest.json"]["stages"]), 6)
        self.assertEqual(
            artifacts["pipeline/03-capability-inventory.json"]["metrics"]["module_dispositions"],
            1,
        )
        self.assertEqual(
            artifacts["pipeline/05-chapter-index.json"]["chapters"][0]["title"],
            "任务执行",
        )
        self.assertEqual(
            artifacts["pipeline/06-validation-report.json"]["status"], "passed"
        )


if __name__ == "__main__":
    unittest.main()
