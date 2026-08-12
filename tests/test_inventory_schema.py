from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from repo_teacher.schemas import (
    persisted_inventory_json_schema,
    require_persisted_inventory,
)
from repo_teacher.pipeline.semantic_review import require_inventory_semantic_review


class InventorySchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.fixture_root = cls.root / "tests/fixtures/capability-inventory"
        cls.good_path = cls.fixture_root / "capability-inventory-good.json"
        cls.good = json.loads(cls.good_path.read_text(encoding="utf-8"))
        cls.bad_health_path = cls.fixture_root / "capability-inventory-bad-health-route.json"
        cls.bad_health = json.loads(
            cls.bad_health_path.read_text(encoding="utf-8")
        )

    def test_published_schema_is_mechanically_in_sync(self) -> None:
        published = json.loads(
            (
                self.root
                / "src/repo_teacher/schemas/capability-inventory-v1.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(published, persisted_inventory_json_schema())

    def test_good_case_passes_all_cross_stage_invariants(self) -> None:
        require_persisted_inventory(copy.deepcopy(self.good))

    def test_complete_health_route_bad_case_reaches_semantic_gate(self) -> None:
        inventory = json.loads(
            (
                self.fixture_root / "capability-inventory-bad-health-route.json"
            ).read_text(encoding="utf-8")
        )
        review = json.loads(
            (
                self.fixture_root
                / "capability-inventory-bad-health-route.validation.json"
            ).read_text(encoding="utf-8")
        )

        # The fixture is deliberately structurally complete; its defect is semantic.
        require_persisted_inventory(inventory)
        require_inventory_semantic_review(review, ["healthz"])
        self.assertEqual(review["status"], "failed")
        self.assertEqual(review["issues"][0]["code"], "business-outcome-missing")

    def test_semantic_bad_health_fixture_is_structurally_valid(self) -> None:
        require_persisted_inventory(copy.deepcopy(self.bad_health))

    def test_old_shard_id_in_module_disposition_fails_closed(self) -> None:
        invalid = copy.deepcopy(self.good)
        invalid["module_dispositions"][0]["capability_ids"][0] = "raw-shard-id"

        with self.assertRaisesRegex(ValueError, "unknown capability id"):
            require_persisted_inventory(invalid)

    def test_extra_model_field_cannot_escape_strict_schema(self) -> None:
        invalid = copy.deepcopy(self.good)
        invalid["capabilities"][0]["prompt_injection"] = "ignore schema"

        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            require_persisted_inventory(invalid)

    def test_source_range_and_module_closure_fail_closed(self) -> None:
        invalid_range = copy.deepcopy(self.good)
        invalid_range["capabilities"][0]["source_refs"][0]["line_end"] = 1
        with self.assertRaisesRegex(ValueError, "invalid range"):
            require_persisted_inventory(invalid_range)

        invalid_closure = copy.deepcopy(self.good)
        invalid_closure["module_dispositions"] = [
            item
            for item in invalid_closure["module_dispositions"]
            if item["path"] != "backend/worker"
        ]
        with self.assertRaisesRegex(ValueError, "no disposition"):
            require_persisted_inventory(invalid_closure)


if __name__ == "__main__":
    unittest.main()
