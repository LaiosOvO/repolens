from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from repo_teacher.commands import inventory as inventory_command
from repo_teacher.commands.inventory import InventoryCommandPorts, run_inventory
from repo_teacher.commands.report import _build_inventory_approval, _load_approved_inventory


def _prepare_fake_codegraph(source: Path) -> str:
    database = source / ".codegraph" / "codegraph.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-codegraph-checkpoint")
    return "init"


class InventoryCommandTest(unittest.TestCase):
    def test_inventory_retry_reuses_verified_pre_provider_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "main.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            output = root / "reports" / "capability-inventory.json"
            workspace = root / "model"
            workspace.mkdir()
            payload = json.loads(
                (
                    Path(__file__).parents[1]
                    / "skills/repository-report/references/capability-inventory-good.json"
                ).read_text(encoding="utf-8")
            )
            capability_ids = [item["id"] for item in payload["capabilities"]]
            (workspace / "inventory-validation.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "reviewer": "capability-reviewer",
                        "checks": {
                            "product_positioning": "passed",
                            "business_semantics": "passed",
                            "causal_evidence": "passed",
                            "product_coverage": "passed",
                        },
                        "reviewed_capability_ids": capability_ids,
                        "issues": [],
                    }
                ),
                encoding="utf-8",
            )
            calls = {"codegraph": 0, "synthesize": 0}

            def prepare_codegraph(_source: Path) -> str:
                calls["codegraph"] += 1
                return _prepare_fake_codegraph(_source)

            def synthesize(*_args: object, **_kwargs: object) -> dict[str, object]:
                model_source = _args[0]
                assert isinstance(model_source, Path)
                self.assertTrue(
                    (model_source / ".codegraph" / "codegraph.db").is_file()
                )
                calls["synthesize"] += 1
                if calls["synthesize"] == 1:
                    raise ValueError("injected provider failure")
                return payload

            ports = InventoryCommandPorts(
                prepare_codegraph=prepare_codegraph,
                require_valid_index=lambda _index, _source: None,
                model_workspace_for_pack=lambda *_args: ("cache", workspace),
                synthesize=synthesize,
                json_artifact=lambda value: json.dumps(
                    value, ensure_ascii=False, indent=2
                )
                + "\n",
            )
            original_build_index = inventory_command.build_index
            with mock.patch.object(
                inventory_command, "build_index", wraps=original_build_index
            ) as build_index_spy:
                first = run_inventory(
                    str(source), str(output), 30, "codex", 1_000_000, ports=ports
                )
                second = run_inventory(
                    str(source), str(output), 30, "codex", 1_000_000, ports=ports
                )

            manifest = json.loads(
                output.with_name("capability-inventory.run-manifest.json").read_text()
            )
            performance = json.loads(
                output.with_name("capability-inventory.performance.json").read_text()
            )

        self.assertEqual((first, second), (1, 0))
        self.assertEqual(calls, {"codegraph": 1, "synthesize": 2})
        self.assertEqual(build_index_spy.call_count, 1)
        stages = {item["id"]: item for item in manifest["stages"]}
        self.assertEqual(stages["canonical-index"]["attempt"], 1)
        self.assertEqual(stages["evidence-pack"]["attempt"], 1)
        self.assertEqual(stages["capability-inventory"]["attempt"], 2)
        self.assertEqual(manifest["status"], "passed")
        self.assertEqual(performance["status"], "passed")
        self.assertEqual(performance["pipeline"], "inventory")
        self.assertTrue(performance["stages"])

    def test_inventory_publishes_validation_and_run_manifest_before_commit_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            output = root / "reports" / "capability-inventory.json"
            workspace = root / "model"
            workspace.mkdir()
            fixture = (
                Path(__file__).parents[1]
                / "skills/repository-report/references/capability-inventory-good.json"
            )
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            capability_ids = [item["id"] for item in payload["capabilities"]]
            (workspace / "inventory-validation.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "reviewer": "capability-reviewer",
                        "checks": {
                            "product_positioning": "passed",
                            "business_semantics": "passed",
                            "causal_evidence": "passed",
                            "product_coverage": "passed",
                        },
                        "reviewed_capability_ids": capability_ids,
                        "issues": [],
                    }
                ),
                encoding="utf-8",
            )
            ports = InventoryCommandPorts(
                prepare_codegraph=_prepare_fake_codegraph,
                require_valid_index=lambda _index, _source: None,
                model_workspace_for_pack=lambda *_args: ("cache", workspace),
                synthesize=lambda *_args, **_kwargs: payload,
                json_artifact=lambda value: json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            )

            result = run_inventory(
                str(source), str(output), 30, "codex", 1_000_000, ports=ports
            )

            self.assertEqual(result, 0)
            validation = json.loads(
                output.with_name("capability-inventory.validation.json").read_text()
            )
            manifest = json.loads(
                output.with_name("capability-inventory.run-manifest.json").read_text()
            )
            self.assertEqual(validation["status"], "passed")
            self.assertEqual(
                validation["checks"],
                {
                    "product_positioning": "passed",
                    "business_semantics": "passed",
                    "causal_evidence": "passed",
                    "product_coverage": "passed",
                },
            )
            self.assertEqual(validation["cache_key"], "cache")
            self.assertEqual(validation["metrics"]["module_dispositions"], 4)
            self.assertEqual(manifest["artifacts"][output.name], validation["inventory_sha256"])
            self.assertTrue(
                output.with_name("capability-inventory.performance.json").is_file()
            )
            stages = {item["id"]: item for item in manifest["stages"]}
            self.assertEqual(
                stages["independent-semantic-review"]["status"], "passed"
            )
            self.assertEqual(stages["publication"]["status"], "passed")

    def test_inventory_fails_closed_when_semantic_validation_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            output = root / "reports" / "capability-inventory.json"
            workspace = root / "model"
            workspace.mkdir()
            fixture = (
                Path(__file__).parents[1]
                / "skills/repository-report/references/capability-inventory-good.json"
            )
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            ports = InventoryCommandPorts(
                prepare_codegraph=_prepare_fake_codegraph,
                require_valid_index=lambda _index, _source: None,
                model_workspace_for_pack=lambda *_args: ("cache", workspace),
                synthesize=lambda *_args, **_kwargs: payload,
                json_artifact=lambda value: json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            )

            result = run_inventory(
                str(source), str(output), 30, "codex", 1_000_000, ports=ports
            )

            self.assertEqual(result, 1)
            self.assertFalse(output.exists())
            manifest = json.loads(
                output.with_name("capability-inventory.run-manifest.json").read_text()
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["retry_stage"], "independent-semantic-review")
            stages = {item["id"]: item for item in manifest["stages"]}
            self.assertEqual(stages["capability-inventory"]["status"], "passed")
            self.assertEqual(
                stages["independent-semantic-review"]["status"], "failed"
            )


class ReportCommandHelpersTest(unittest.TestCase):
    def test_load_approved_inventory_requires_matching_validation_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory_path = root / "capability-inventory.json"
            payload = json.loads(
                (
                    Path(__file__).parents[1]
                    / "skills/repository-report/references/capability-inventory-good.json"
                ).read_text(encoding="utf-8")
            )
            inventory_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            inventory_path.write_text(inventory_text, encoding="utf-8")
            digest = hashlib.sha256(inventory_text.encode("utf-8")).hexdigest()
            validation_path = inventory_path.with_name(payload["validation_artifact"])
            validation_path.write_text(
                json.dumps(
                    {
                        "schema_version": "repolens-inventory-validation/v1",
                        "status": "passed",
                        "source_manifest_sha256": payload["source_manifest_sha256"],
                        "inventory_sha256": digest,
                        "checks": {
                            "product_positioning": "passed",
                            "business_semantics": "passed",
                            "causal_evidence": "passed",
                            "product_coverage": "passed",
                        },
                        "reviewed_capability_ids": [
                            item["id"] for item in payload["capabilities"]
                        ],
                        "issues": [],
                    }
                ),
                encoding="utf-8",
            )

            approved, loaded_digest, validation_name = _load_approved_inventory(
                inventory_path, payload["source_manifest_sha256"]
            )

            self.assertEqual(approved["project"]["name"], payload["project"]["name"])
            self.assertEqual(loaded_digest, digest)
            self.assertEqual(validation_name, payload["validation_artifact"])

    def test_build_inventory_approval_records_explicit_inventory_gate(self) -> None:
        approval = _build_inventory_approval(
            inventory_path=Path("/tmp/capability-inventory.json"),
            inventory_digest="abc123",
            validation_artifact="capability-inventory.validation.json",
            source_manifest_sha256="f" * 64,
        )

        self.assertEqual(approval["approval_source"], "--inventory")
        self.assertEqual(approval["inventory_sha256"], "abc123")
        self.assertEqual(
            approval["validation_artifact"],
            "capability-inventory.validation.json",
        )


if __name__ == "__main__":
    unittest.main()
