"""Structured-output contracts for model-facing production stages."""

from __future__ import annotations

import copy

from ..human_report import human_report_json_schema
from .inventory import inventory_json_schema


def _text() -> dict[str, object]:
    return {"type": "string", "minLength": 1, "maxLength": 12_000}


def source_ref_json_schema() -> dict[str, object]:
    text = _text()
    return {
        "type": "object",
        "properties": {
            "path": text,
            "line_start": {"type": "integer", "minimum": 1},
            "line_end": {"type": "integer", "minimum": 1},
            "claim": text,
        },
        "required": ["path", "line_start", "line_end", "claim"],
        "additionalProperties": False,
    }


def inventory_group_json_schema(
    *,
    allow_empty: bool = False,
    approved_capability_ids: list[str] | None = None,
) -> dict[str, object]:
    text = _text()
    approved_ids = list(approved_capability_ids or [])
    if len(approved_ids) != len(set(approved_ids)):
        raise ValueError("grouping schema requires unique approved capability ids")
    project_summary = copy.deepcopy(
        inventory_json_schema()["properties"]["project_summary"]
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "project_summary": project_summary,
            "groups": {
                "type": "array",
                "minItems": 0 if allow_empty else 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": text,
                        "title": text,
                        "user_actor": text,
                        "user_goal": text,
                        "visible_outcome": text,
                        "product_surface": text,
                        "causal_flow": text,
                        "why_one_capability": text,
                        "importance": {
                            "type": "string",
                            "enum": [
                                "core-journey",
                                "differentiator",
                                "dependent-capability",
                                "supporting",
                            ],
                        },
                        "merge_into_capability_id": {
                            "type": "string",
                            "enum": ["__new__", *approved_ids],
                        },
                        "member_ids": {
                            "type": "array",
                            "items": text,
                            "minItems": 1,
                        },
                    },
                    "required": [
                        "id",
                        "title",
                        "user_actor",
                        "user_goal",
                        "visible_outcome",
                        "product_surface",
                        "causal_flow",
                        "why_one_capability",
                        "importance",
                        "merge_into_capability_id",
                        "member_ids",
                    ],
                    "additionalProperties": False,
                },
            },
            "excluded_supporting_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"member_id": text, "reason": text},
                    "required": ["member_id", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["project_summary", "groups", "excluded_supporting_items"],
        "additionalProperties": False,
    }


def inventory_partition_repair_json_schema(
    member_ids: list[str], group_ids: list[str]
) -> dict[str, object]:
    """Constrain a structural grouping repair to the exact unresolved IDs."""

    if not member_ids or len(member_ids) != len(set(member_ids)):
        raise ValueError("partition repair requires unique unresolved member ids")
    if len(group_ids) != len(set(group_ids)):
        raise ValueError("partition repair requires unique existing group ids")
    text = _text()
    new_group = {
        "type": "object",
        "properties": {
            "id": text,
            "title": text,
            "user_actor": text,
            "user_goal": text,
            "visible_outcome": text,
            "product_surface": text,
            "causal_flow": text,
            "why_one_capability": text,
            "importance": {
                "type": "string",
                "enum": [
                    "core-journey",
                    "differentiator",
                    "dependent-capability",
                    "supporting",
                ],
            },
        },
        "required": [
            "id",
            "title",
            "user_actor",
            "user_goal",
            "visible_outcome",
            "product_surface",
            "causal_flow",
            "why_one_capability",
            "importance",
        ],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "minItems": len(member_ids),
                "maxItems": len(member_ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "member_id": {"type": "string", "enum": member_ids},
                        "decision": {
                            "type": "string",
                            "enum": ["attach", "exclude", "new-group"],
                        },
                        "target_group_id": {
                            "type": "string",
                            "enum": [*group_ids, "__none__"],
                        },
                        "reason": text,
                        "new_group": new_group,
                    },
                    "required": [
                        "member_id",
                        "decision",
                        "target_group_id",
                        "reason",
                        "new_group",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["assignments"],
        "additionalProperties": False,
    }


def inventory_semantic_review_json_schema(
    capability_ids: list[str], candidate_ids: list[str] | None = None,
) -> dict[str, object]:
    """Schema for the independent post-grouping business semantics review."""

    if not capability_ids or len(capability_ids) != len(set(capability_ids)):
        raise ValueError("semantic review requires unique capability ids")
    if candidate_ids is not None and (
        not candidate_ids or len(candidate_ids) != len(set(candidate_ids))
    ):
        raise ValueError("semantic review requires unique raw candidate ids")
    text = _text()
    issue = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "enum": [
                    "business-outcome-missing",
                    "causal-evidence-incomplete",
                    "supporting-surface-promoted",
                    "capability-mixed-boundaries",
                    "capability-coverage-missing",
                    "unsupported-product-claim",
                    "capability-priority-invalid",
                ],
            },
            "capability_id": {"type": "string"},
            "message": text,
            "retry_stage": {
                "type": "string",
                "enum": ["evidence-pack", "capability-inventory", "global-grouping"],
            },
            "affected_candidate_ids": {
                "type": "array",
                "minItems": 1,
                "items": (
                    {"type": "string", "enum": candidate_ids}
                    if candidate_ids is not None
                    else text
                ),
            },
        },
        "required": [
            "code",
            "capability_id",
            "message",
            "retry_stage",
            "affected_candidate_ids",
        ],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["passed", "failed"]},
            "checks": {
                "type": "object",
                "properties": {
                    "product_positioning": {
                        "type": "string",
                        "enum": ["passed", "failed"],
                    },
                    "business_semantics": {
                        "type": "string",
                        "enum": ["passed", "failed"],
                    },
                    "causal_evidence": {
                        "type": "string",
                        "enum": ["passed", "failed"],
                    },
                    "product_coverage": {
                        "type": "string",
                        "enum": ["passed", "failed"],
                    },
                },
                "required": [
                    "product_positioning",
                    "business_semantics",
                    "causal_evidence",
                    "product_coverage",
                ],
                "additionalProperties": False,
            },
            "reviewed_capability_ids": {
                "type": "array",
                "items": {"type": "string", "enum": capability_ids},
                "minItems": len(capability_ids),
                "maxItems": len(capability_ids),
            },
            "issues": {"type": "array", "items": issue},
        },
        "required": ["status", "checks", "reviewed_capability_ids", "issues"],
        "additionalProperties": False,
    }


def human_readability_review_json_schema(
    capability_ids: list[str],
) -> dict[str, object]:
    """Schema for the independent human readability review stage."""

    if not capability_ids or len(capability_ids) != len(set(capability_ids)):
        raise ValueError("human readability review requires unique capability ids")
    text = _text()
    checklist = {
        "type": "object",
        "properties": {
            "summary_clarity": {"type": "string", "enum": ["passed", "failed"]},
            "interaction_diagram": {"type": "string", "enum": ["passed", "failed"]},
            "implementation_mechanism": {
                "type": "string",
                "enum": ["passed", "failed"],
            },
            "selection_signal": {"type": "string", "enum": ["passed", "failed"]},
        },
        "required": [
            "summary_clarity",
            "interaction_diagram",
            "implementation_mechanism",
            "selection_signal",
        ],
        "additionalProperties": False,
    }
    chapter_verdict = {
        "type": "object",
        "properties": {
            "capability_id": {"type": "string", "enum": capability_ids},
            "status": {"type": "string", "enum": ["pass", "fail"]},
            "one_liner": text,
            "thirty_second_restatement": text,
            "checks": checklist,
            "missing_answers": {"type": "array", "items": text},
            "evidence_locations": {"type": "array", "items": text, "minItems": 1},
        },
        "required": [
            "capability_id",
            "status",
            "one_liner",
            "thirty_second_restatement",
            "checks",
            "missing_answers",
            "evidence_locations",
        ],
        "additionalProperties": False,
    }
    project_overview_verdict = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["pass", "fail"]},
            "summary": text,
            "missing_answers": {"type": "array", "items": text},
            "evidence_locations": {"type": "array", "items": text, "minItems": 1},
        },
        "required": [
            "status",
            "summary",
            "missing_answers",
            "evidence_locations",
        ],
        "additionalProperties": False,
    }
    blocking_issue = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "enum": [
                    "project-essence-missing",
                    "chapter-summary-not-one-liner",
                    "thirty-second-restatement-failed",
                    "interaction-diagram-not-concrete",
                    "implementation-mechanism-missing",
                    "technology-selection-missing",
                    "evidence-location-missing",
                ],
            },
            "capability_id": {"type": "string"},
            "location": text,
            "message": text,
            "retry_stage": {
                "type": "string",
                "enum": ["project-overview", "chapter-generation", "renderer"],
            },
        },
        "required": ["code", "capability_id", "location", "message", "retry_stage"],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["passed", "failed"]},
            "checks": {
                "type": "object",
                "properties": {
                    "project_positioning": {
                        "type": "string",
                        "enum": ["passed", "failed"],
                    },
                    "chapter_coverage": {
                        "type": "string",
                        "enum": ["passed", "failed"],
                    },
                    "interaction_explainer": {
                        "type": "string",
                        "enum": ["passed", "failed"],
                    },
                    "implementation_depth": {
                        "type": "string",
                        "enum": ["passed", "failed"],
                    },
                    "selection_value": {
                        "type": "string",
                        "enum": ["passed", "failed"],
                    },
                },
                "required": [
                    "project_positioning",
                    "chapter_coverage",
                    "interaction_explainer",
                    "implementation_depth",
                    "selection_value",
                ],
                "additionalProperties": False,
            },
            "project_overview_verdict": project_overview_verdict,
            "chapter_verdicts": {
                "type": "array",
                "items": chapter_verdict,
                "minItems": len(capability_ids),
                "maxItems": len(capability_ids),
            },
            "blocking_issues": {"type": "array", "items": blocking_issue},
            "retry_stage": {
                "type": "string",
                "enum": ["none", "project-overview", "chapter-generation", "renderer"],
            },
        },
        "required": [
            "status",
            "checks",
            "project_overview_verdict",
            "chapter_verdicts",
            "blocking_issues",
            "retry_stage",
        ],
        "additionalProperties": False,
    }


def project_overview_json_schema(capability_count: int) -> dict[str, object]:
    if capability_count < 1:
        raise ValueError("project overview requires at least one capability")
    text = _text()
    string_list = {"type": "array", "items": text, "minItems": 1}
    source_refs = {
        "type": "array",
        "items": source_ref_json_schema(),
        "minItems": 1,
    }
    runtime_component = {
        "type": "object",
        "properties": {
            "name": text,
            "responsibility": text,
            "communication": text,
            "state": text,
            "source_refs": source_refs,
        },
        "required": [
            "name",
            "responsibility",
            "communication",
            "state",
            "source_refs",
        ],
        "additionalProperties": False,
    }
    directory = {
        "type": "object",
        "properties": {
            "path": text,
            "responsibility": text,
            "layer": text,
            "boundary": text,
            "source_refs": source_refs,
        },
        "required": ["path", "responsibility", "layer", "boundary", "source_refs"],
        "additionalProperties": False,
    }
    journey_step = {
        "type": "object",
        "properties": {
            "stage": text,
            "actor": text,
            "action": text,
            "state_change": text,
            "next": text,
        },
        "required": ["stage", "actor", "action", "state_change", "next"],
        "additionalProperties": False,
    }
    product_axis = {
        "type": "object",
        "properties": {
            "id": text,
            "title": text,
            "one_liner": text,
            "user_outcome": text,
            "end_to_end_flow": string_list,
            "capability_ids": string_list,
            "source_refs": source_refs,
        },
        "required": [
            "id",
            "title",
            "one_liner",
            "user_outcome",
            "end_to_end_flow",
            "capability_ids",
            "source_refs",
        ],
        "additionalProperties": False,
    }
    engineering_structure = {
        "type": "object",
        "properties": {
            "repository_shape": text,
            "architecture_pattern": text,
            "pattern_reasoning": text,
            "frontend_organization": text,
            "backend_organization": text,
            "worker_and_async_organization": text,
            "shared_contracts": text,
            "dependency_rule": text,
            "media_organization": text,
            "source_refs": source_refs,
        },
        "required": [
            "repository_shape",
            "architecture_pattern",
            "pattern_reasoning",
            "frontend_organization",
            "backend_organization",
            "worker_and_async_organization",
            "shared_contracts",
            "dependency_rule",
            "media_organization",
            "source_refs",
        ],
        "additionalProperties": False,
    }
    overview = {
        "type": "object",
        "properties": {
            "one_liner": text,
            "product_type": text,
            "primary_user": text,
            "problem": text,
            "core_journey": {"type": "array", "items": journey_step, "minItems": 3},
            "core_product_axes": {
                "type": "array",
                "items": product_axis,
                "minItems": 1,
                "maxItems": 4,
            },
            "supporting_capability_ids": {"type": "array", "items": text},
            "architecture_summary": text,
            "architecture_style": text,
            "engineering_structure": engineering_structure,
            "execution_model": text,
            "runtime_components": {
                "type": "array",
                "items": runtime_component,
                "minItems": 2,
            },
            "frontend_backend_boundary": text,
            "data_and_state": text,
            "deployment_shape": text,
            "code_organization": {
                "type": "array",
                "items": directory,
                "minItems": 2,
            },
            "differentiator": text,
            "not_this": string_list,
            "source_refs": {
                "type": "array",
                "items": source_ref_json_schema(),
                "minItems": 3,
            },
            "capability_order": {
                "type": "array",
                "items": text,
                "minItems": capability_count,
                "maxItems": capability_count,
            },
        },
        "required": [
            "one_liner",
            "product_type",
            "primary_user",
            "problem",
            "core_journey",
            "core_product_axes",
            "supporting_capability_ids",
            "architecture_summary",
            "architecture_style",
            "engineering_structure",
            "execution_model",
            "runtime_components",
            "frontend_backend_boundary",
            "data_and_state",
            "deployment_shape",
            "code_organization",
            "differentiator",
            "not_this",
            "source_refs",
            "capability_order",
        ],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"project_overview": overview},
        "required": ["project_overview"],
        "additionalProperties": False,
    }


def chapter_batch_json_schema(max_items: int) -> dict[str, object]:
    if max_items < 1:
        raise ValueError("chapter batch requires at least one item")
    chapter_item = copy.deepcopy(
        human_report_json_schema()["properties"]["chapters"]["items"]
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "chapters": {
                "type": "array",
                "items": chapter_item,
                "minItems": 1,
                "maxItems": max_items,
            }
        },
        "required": ["chapters"],
        "additionalProperties": False,
    }
