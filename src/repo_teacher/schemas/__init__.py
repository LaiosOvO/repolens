"""Versioned structured-output contracts used by Repo Teacher pipelines."""

from .inventory import (
    inventory_json_schema,
    persisted_inventory_json_schema,
    require_persisted_inventory,
)
from .stages import (
    chapter_batch_json_schema,
    human_readability_review_json_schema,
    inventory_group_json_schema,
    inventory_partition_repair_json_schema,
    inventory_semantic_review_json_schema,
    project_overview_json_schema,
    source_ref_json_schema,
)

__all__ = [
    "inventory_json_schema",
    "persisted_inventory_json_schema",
    "require_persisted_inventory",
    "source_ref_json_schema",
    "inventory_group_json_schema",
    "inventory_partition_repair_json_schema",
    "inventory_semantic_review_json_schema",
    "human_readability_review_json_schema",
    "project_overview_json_schema",
    "chapter_batch_json_schema",
]
