from __future__ import annotations

import unittest

from repo_teacher.schemas import (
    chapter_batch_json_schema,
    inventory_group_json_schema,
    inventory_partition_repair_json_schema,
    project_overview_json_schema,
)


class StageSchemaTest(unittest.TestCase):
    def test_project_overview_capability_order_is_exactly_bounded(self) -> None:
        schema = project_overview_json_schema(7)
        order = schema["properties"]["project_overview"]["properties"][
            "capability_order"
        ]

        self.assertEqual(order["minItems"], 7)
        self.assertEqual(order["maxItems"], 7)

    def test_grouping_schema_requires_exact_partition_outputs(self) -> None:
        schema = inventory_group_json_schema()

        self.assertEqual(
            schema["required"],
            ["project_summary", "groups", "excluded_supporting_items"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["project_summary"]["required"],
            [
                "product_type",
                "primary_actor",
                "primary_outcome",
                "main_runtime",
                "not_the_product",
            ],
        )
        group = schema["properties"]["groups"]["items"]
        self.assertIn("importance", group["required"])

    def test_partition_repair_new_group_requires_product_importance(self) -> None:
        schema = inventory_partition_repair_json_schema(["candidate"], [])
        new_group = schema["properties"]["assignments"]["items"]["properties"][
            "new_group"
        ]

        self.assertIn("importance", new_group["required"])

    def test_chapter_batch_schema_respects_requested_batch_limit(self) -> None:
        schema = chapter_batch_json_schema(3)
        chapters = schema["properties"]["chapters"]

        self.assertEqual(chapters["minItems"], 1)
        self.assertEqual(chapters["maxItems"], 3)

    def test_dynamic_schema_factories_reject_empty_stage_requests(self) -> None:
        with self.assertRaises(ValueError):
            project_overview_json_schema(0)
        with self.assertRaises(ValueError):
            chapter_batch_json_schema(0)


if __name__ == "__main__":
    unittest.main()
