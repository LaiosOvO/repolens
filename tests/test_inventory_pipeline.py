from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_teacher.pipeline.inventory import CapabilityInventoryStage, InventoryStageRequest
from repo_teacher.providers import CallableStructuredModelProvider


class CapabilityInventoryStageTest(unittest.TestCase):
    def _request(self, root: Path) -> InventoryStageRequest:
        return InventoryStageRequest(
            source=root / "source",
            workspace=root / "workspace",
            packet={"scope": {"allowed_source_paths": ["src/app.py"]}},
            packet_path=root / "workspace" / "pack.json",
            prompt="analyze",
            schema={"type": "object"},
            timeout_seconds=30,
        )

    def test_valid_cache_is_rechecked_and_skips_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._request(root)
            request.workspace.mkdir()
            (request.workspace / "capability-inventory.json").write_text(
                '{"capabilities": [{"id": "voice"}]}', encoding="utf-8"
            )
            calls: list[str] = []
            provider = CallableStructuredModelProvider(
                "fake", lambda model_request: calls.append(model_request.stage) or {}
            )
            stage = CapabilityInventoryStage(provider)
            validations: list[str] = []

            payload, reused = stage.run(
                request,
                normalize=lambda value, packet: value,
                validate=lambda value, packet: validations.append(
                    str(value["capabilities"][0]["id"])
                ),
            )

        self.assertTrue(reused)
        self.assertEqual(payload["capabilities"][0]["id"], "voice")
        self.assertEqual(validations, ["voice"])
        self.assertEqual(calls, [])

    def test_invalid_cache_runs_provider_and_atomically_replaces_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._request(root)
            request.workspace.mkdir()
            cache = request.workspace / "capability-inventory.json"
            cache.write_text("not-json", encoding="utf-8")
            calls: list[str] = []
            provider = CallableStructuredModelProvider(
                "fake",
                lambda model_request: calls.append(model_request.stage)
                or {"capabilities": [{"id": "worker"}]},
            )
            stage = CapabilityInventoryStage(provider)

            payload, reused = stage.run(
                request,
                normalize=lambda value, packet: value,
                validate=lambda value, packet: None,
            )

            persisted = cache.read_text(encoding="utf-8")
            leftovers = list(request.workspace.glob("*.tmp"))

        self.assertFalse(reused)
        self.assertEqual(payload["capabilities"][0]["id"], "worker")
        self.assertEqual(calls, ["capability-inventory"])
        self.assertIn('"worker"', persisted)
        self.assertEqual(leftovers, [])

    def test_invalid_output_is_not_persisted_or_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._request(root)
            request.workspace.mkdir()
            stage = CapabilityInventoryStage(
                CallableStructuredModelProvider(
                    "fake", lambda _request: {"module_dispositions": []}
                )
            )
            def validate(_value: dict[str, object], _packet: dict[str, object]) -> None:
                raise ValueError("still invalid")

            with self.assertRaisesRegex(ValueError, "still invalid"):
                stage.run(
                    request,
                    normalize=lambda value, _packet: value,
                    validate=validate,
                )

            self.assertFalse(
                (request.workspace / "capability-inventory.json").exists()
            )


if __name__ == "__main__":
    unittest.main()
