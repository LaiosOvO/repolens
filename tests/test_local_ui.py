from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_teacher.local_ui import (
    MODEL_OPTIONS,
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
        self.assertEqual(progress_from_line("[report 3/6] 准备证据包", 0), 28)
        self.assertEqual(progress_from_line("[report 4/6] 模块分片目录完成 3/4", 42), 64)
        self.assertEqual(progress_from_line("普通日志", 64), 64)

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


if __name__ == "__main__":
    unittest.main()
