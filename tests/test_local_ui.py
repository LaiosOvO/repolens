from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_teacher.local_ui import (
    MODEL_OPTIONS,
    _UI_HTML,
    JobManager,
    build_report_command,
    progress_from_line,
    validate_job_request,
)


class LocalUiTest(unittest.TestCase):
    def test_request_builds_report_command_without_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            config = validate_job_request(
                {
                    "source": str(source),
                    "output_root": str(root / "reports"),
                    "name": "voice-agent",
                    "backend": "opencode",
                    "model": "deepseek-pro",
                    "model_timeout": 7200,
                }
            )
            command = build_report_command(config)

        self.assertIn("report", command)
        self.assertIn("opencode", command)
        self.assertNotIn("--auto-inventory", command)
        self.assertNotIn("sk-secret", " ".join(command))
        self.assertEqual(MODEL_OPTIONS["deepseek-pro"], "openrouter/deepseek/deepseek-v4-pro")

    def test_request_rejects_output_name_that_escapes_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            with self.assertRaisesRegex(ValueError, "路径分隔符"):
                validate_job_request(
                    {
                        "source": str(source),
                        "output_root": directory,
                        "name": "../outside",
                        "backend": "codex",
                    }
                )

    def test_progress_uses_pipeline_phase_and_shard_completion(self) -> None:
        self.assertEqual(progress_from_line("[report 02/05] 准备证据包", 0), 28)
        self.assertEqual(progress_from_line("[report 03/05] 生成内容", 0), 58)
        self.assertEqual(progress_from_line("[report 04/05] 校验证据", 58), 84)
        self.assertEqual(progress_from_line("普通日志", 84), 84)

    def test_public_job_state_never_contains_api_key(self) -> None:
        manager = JobManager()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            with patch.object(manager, "_run", return_value=None):
                job = manager.start(
                    {
                        "source": str(source),
                        "output_root": str(root / "reports"),
                        "name": "report",
                        "backend": "opencode",
                        "model": "deepseek-flash",
                        "model_timeout": 600,
                    },
                    "sk-secret",
                )
            public = str(job.public())

        self.assertNotIn("sk-secret", public)

    def test_completed_job_exposes_stage_performance_without_secrets(self) -> None:
        manager = JobManager()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "reports" / "demo"
            output.mkdir(parents=True)
            performance_path = output.with_name(
                f"{output.name}.performance.json"
            )
            performance_path.write_text(
                '{"schema_version":"repolens-pipeline-performance/v1",'
                '"pipeline":"report","status":"passed",'
                '"wall_duration_seconds":12.5,"longest_stage":{"id":"03-capability-inventory",'
                '"duration_seconds":9.0},"stages":[]}',
                encoding="utf-8",
            )
            from repo_teacher.local_ui import ReportJob

            job = ReportJob(
                identifier="job",
                config={
                    "output": output,
                    "backend": "codex",
                    "model": "deepseek-flash",
                },
                status="completed",
            )
            manager._jobs[job.identifier] = job

            public = job.public()

        self.assertEqual(public["performance"]["wall_duration_seconds"], 12.5)
        self.assertEqual(public["performance"]["longest_stage"]["id"], "03-capability-inventory")

    def test_ui_displays_live_stage_timing(self) -> None:
        self.assertIn('id="timing"', _UI_HTML)
        self.assertIn("阶段耗时", _UI_HTML)
        self.assertIn("wall_duration_seconds", _UI_HTML)

    def test_running_job_derives_live_timing_from_authoritative_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "reports" / "demo"
            output.parent.mkdir(parents=True)
            output.with_name(f"{output.name}.run-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "repolens-pipeline-journal/v1",
                        "pipeline": "report",
                        "status": "started",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:07+00:00",
                        "current_stage": "03-capability-inventory",
                        "retry_stage": "03-capability-inventory",
                        "stages": [
                            {
                                "id": "03-capability-inventory",
                                "status": "started",
                                "attempt": 1,
                                "started_at": "2026-01-01T00:00:02+00:00",
                                "completed_at": None,
                                "issues": [],
                                "retry_stage": "03-capability-inventory",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            from repo_teacher.local_ui import ReportJob

            public = ReportJob(
                identifier="job",
                config={
                    "output": output,
                    "backend": "codex",
                    "model": "deepseek-flash",
                },
                status="running",
            ).public()

        self.assertEqual(public["performance"]["current_stage"], "03-capability-inventory")
        self.assertEqual(public["performance"]["wall_duration_seconds"], 7.0)


if __name__ == "__main__":
    unittest.main()
