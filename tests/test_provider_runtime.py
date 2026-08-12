from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_teacher.providers import run_structured_json


class _SuccessfulCodexProcess:
    returncode = 0

    def __init__(self, command: list[str], **_kwargs: object) -> None:
        output_flag = command.index("--output-last-message")
        self.output_path = Path(command[output_flag + 1])

    def communicate(
        self, input: str | None = None, timeout: float | None = None
    ) -> tuple[str, str]:
        del input, timeout
        self.output_path.write_text('{"result":"ok"}\n', encoding="utf-8")
        return "", ""

    def kill(self) -> None:
        raise AssertionError("successful fake process must not be killed")


class ProviderRuntimePerformanceTest(unittest.TestCase):
    def test_codex_call_writes_non_secret_timing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            with (
                patch("repo_teacher.providers.runtime.shutil.which", return_value="codex"),
                patch(
                    "repo_teacher.providers.runtime.subprocess.Popen",
                    side_effect=_SuccessfulCodexProcess,
                ),
            ):
                result = run_structured_json(
                    source=root,
                    workspace=workspace,
                    schema={"type": "object"},
                    prompt="PRIVATE PROMPT CONTENT",
                    timeout=10,
                    stage_slug="capability-review",
                    progress_label="review",
                    provider="codex",
                )

            performance = json.loads(
                (workspace / "capability-review-performance.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(result, {"result": "ok"})
        self.assertEqual(performance["status"], "passed")
        self.assertEqual(performance["provider"], "codex")
        self.assertEqual(performance["stage"], "capability-review")
        self.assertGreaterEqual(performance["duration_seconds"], 0)
        self.assertGreater(performance["prompt_bytes"], 0)
        self.assertNotIn("PRIVATE PROMPT CONTENT", str(performance))


if __name__ == "__main__":
    unittest.main()
