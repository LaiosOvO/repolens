from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from repo_teacher.commands.report import _load_approved_inventory


class ApprovedInventoryTest(unittest.TestCase):
    def _write_inventory(self, root: Path, *, status: str) -> Path:
        fixture = (
            Path(__file__).parents[1]
            / "tests/fixtures/capability-inventory/capability-inventory-good.json"
        )
        inventory = json.loads(fixture.read_text(encoding="utf-8"))
        path = root / "capability-inventory.json"
        text = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8")
        issue = {
            "code": "business-outcome-missing",
            "capability_id": "agent-task-execution",
            "message": "not a user outcome",
            "retry_stage": "global-grouping",
            "affected_candidate_ids": ["agent-task-candidate"],
        }
        validation = {
            "schema_version": "repolens-inventory-validation/v1",
            "status": status,
            "source_manifest_sha256": inventory["source_manifest_sha256"],
            "inventory_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "checks": {
                "canonical_index": "passed",
                "schema": "passed",
                "product_positioning": "passed" if status == "passed" else "failed",
                "business_semantics": "passed" if status == "passed" else "failed",
                "causal_evidence": "passed",
                "product_coverage": "passed" if status == "passed" else "failed",
            },
            "reviewed_capability_ids": ["agent-task-execution"],
            "issues": [] if status == "passed" else [issue],
        }
        (root / inventory["validation_artifact"]).write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def test_only_digest_and_snapshot_bound_semantic_pass_is_approved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_inventory(Path(directory), status="passed")
            inventory, digest, validation_name = _load_approved_inventory(
                path,
                "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            )

        self.assertEqual(inventory["capabilities"][0]["id"], "agent-task-execution")
        self.assertEqual(len(digest), 64)
        self.assertEqual(validation_name, "capability-inventory.validation.json")

    def test_semantic_failure_cannot_be_used_as_approved_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_inventory(Path(directory), status="failed")
            with self.assertRaisesRegex(ValueError, "did not pass semantic review"):
                _load_approved_inventory(
                    path,
                    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                )


if __name__ == "__main__":
    unittest.main()
