"""Business capability inventory schema.

This module is intentionally independent from the CLI.  Model providers,
pipeline stages, tests, and external integrations all consume the same
contract instead of duplicating a prompt-specific shape.
"""

from __future__ import annotations

from pathlib import PurePosixPath


_SUMMARY_FIELDS = {
    "product_type",
    "primary_actor",
    "primary_outcome",
    "main_runtime",
    "not_the_product",
}
_CAPABILITY_FIELDS = {
    "id",
    "title",
    "summary",
    "mechanism",
    "question",
    "use_when",
    "distinguish",
    "plain_summary",
    "importance",
    "user_actor",
    "user_goal",
    "visible_outcome",
    "product_surface",
    "causal_flow",
    "why_one_capability",
    "implementation_modules",
    "source_feature_ids",
    "evidence_ids",
    "source_refs",
}
_MODULE_FIELDS = {"path", "classification", "responsibility", "handoff"}
_SOURCE_REF_FIELDS = {"path", "line_start", "line_end", "claim"}
_DISPOSITION_FIELDS = {"path", "disposition", "capability_ids", "reason"}
_PROJECT_FIELDS = {"name", "path", "commit", "branch", "analysis_fingerprint"}
_GENERATOR_FIELDS = {"name", "method"}
_TOP_LEVEL_FIELDS = {
    "schema_version",
    "grouping_complete",
    "generator",
    "project",
    "source_manifest_sha256",
    "cache_key",
    "validation_artifact",
    "project_summary",
    "capabilities",
    "module_dispositions",
}


def _require_object(value: object, *, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_exact_fields(
    value: dict[str, object], expected: set[str], *, path: str
) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing:
        raise ValueError(f"{path} omitted required fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"{path} contains unsupported fields: {', '.join(sorted(extra))}")


def _require_text(value: object, *, path: str, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 12_000:
        raise ValueError(f"{path} must be non-empty text")
    return value


def _require_text_list(
    value: object, *, path: str, allow_empty: bool = False
) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{path} must be a non-empty list")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(str(_require_text(item, path=f"{path}/{index}")))
    return result


def _require_relative_path(value: object, *, path: str) -> str:
    text = _require_text(value, path=path)
    assert isinstance(text, str)
    candidate = PurePosixPath(text)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in text:
        raise ValueError(f"{path} must be a repository-relative POSIX path")
    return text


def _source_ref_schema() -> dict[str, object]:
    text = {"type": "string", "minLength": 1, "maxLength": 12_000}
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


def inventory_json_schema() -> dict[str, object]:
    """Return a fresh JSON Schema for one approved capability inventory."""

    text = {"type": "string", "minLength": 1, "maxLength": 12_000}
    string_list = {"type": "array", "items": text, "minItems": 1}
    implementation_module = {
        "type": "object",
        "properties": {
            "path": text,
            "classification": {"type": "string", "enum": ["core", "supporting"]},
            "responsibility": text,
            "handoff": text,
        },
        "required": ["path", "classification", "responsibility", "handoff"],
        "additionalProperties": False,
    }
    capability = {
        "type": "object",
        "properties": {
            "id": text,
            "title": text,
            "summary": text,
            "mechanism": text,
            "question": text,
            "use_when": text,
            "distinguish": text,
            "plain_summary": text,
            "importance": {
                "type": "string",
                "enum": [
                    "core-journey",
                    "differentiator",
                    "dependent-capability",
                    "supporting",
                ],
            },
            "user_actor": text,
            "user_goal": text,
            "visible_outcome": text,
            "product_surface": text,
            "causal_flow": text,
            "why_one_capability": text,
            "implementation_modules": {
                "type": "array",
                "items": implementation_module,
                "minItems": 1,
            },
            "source_feature_ids": string_list,
            "evidence_ids": string_list,
            "source_refs": {
                "type": "array",
                "items": _source_ref_schema(),
                "minItems": 3,
            },
        },
        "required": [
            "id",
            "title",
            "summary",
            "mechanism",
            "question",
            "use_when",
            "distinguish",
            "plain_summary",
            "importance",
            "user_actor",
            "user_goal",
            "visible_outcome",
            "product_surface",
            "causal_flow",
            "why_one_capability",
            "implementation_modules",
            "source_feature_ids",
            "evidence_ids",
            "source_refs",
        ],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "project_summary": {
                "type": "object",
                "properties": {
                    "product_type": text,
                    "primary_actor": text,
                    "primary_outcome": text,
                    "main_runtime": text,
                    "not_the_product": {"type": "array", "items": text},
                },
                "required": [
                    "product_type",
                    "primary_actor",
                    "primary_outcome",
                    "main_runtime",
                    "not_the_product",
                ],
                "additionalProperties": False,
            },
            "capabilities": {
                "type": "array",
                "items": capability,
                "minItems": 1,
            },
            "module_dispositions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "path": text,
                        "disposition": {
                            "type": "string",
                            "enum": ["core-capability", "supporting", "excluded"],
                        },
                        "capability_ids": {"type": "array", "items": text},
                        "reason": text,
                    },
                    "required": [
                        "path",
                        "disposition",
                        "capability_ids",
                        "reason",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["project_summary", "capabilities", "module_dispositions"],
        "additionalProperties": False,
    }


def persisted_inventory_json_schema() -> dict[str, object]:
    """Return the public contract for the user-facing inventory artifact."""

    schema = inventory_json_schema()
    text = {"type": "string", "minLength": 1, "maxLength": 12_000}
    optional_text = {"type": ["string", "null"], "maxLength": 12_000}
    properties = schema["properties"]
    assert isinstance(properties, dict)
    properties.update(
        {
            "schema_version": {
                "type": "string",
                "const": "repo-teacher-capability-inventory/v1",
            },
            "grouping_complete": {"type": "boolean", "const": True},
            "generator": {
                "type": "object",
                "properties": {"name": text, "method": text},
                "required": ["name", "method"],
                "additionalProperties": False,
            },
            "project": {
                "type": "object",
                "properties": {
                    "name": text,
                    "path": text,
                    "commit": optional_text,
                    "branch": optional_text,
                    "analysis_fingerprint": text,
                },
                "required": [
                    "name",
                    "path",
                    "commit",
                    "branch",
                    "analysis_fingerprint",
                ],
                "additionalProperties": False,
            },
            "source_manifest_sha256": {
                "type": "string",
                "minLength": 64,
                "maxLength": 64,
            },
            "cache_key": text,
            "validation_artifact": text,
        }
    )
    required = schema["required"]
    assert isinstance(required, list)
    required.extend(
        [
            "schema_version",
            "grouping_complete",
            "generator",
            "project",
            "source_manifest_sha256",
            "cache_key",
            "validation_artifact",
        ]
    )
    schema["$id"] = "https://repolens.local/schemas/capability-inventory-v1.schema.json"
    schema["title"] = "RepoLens Capability Inventory v1"
    return schema


def require_persisted_inventory(payload: dict[str, object]) -> None:
    """Fail closed on the cross-stage invariants not expressible as shape alone."""

    _require_exact_fields(payload, _TOP_LEVEL_FIELDS, path="/")
    if payload.get("schema_version") != "repo-teacher-capability-inventory/v1":
        raise ValueError("capability inventory schema_version is missing or unsupported")
    if payload.get("grouping_complete") is not True:
        raise ValueError("capability inventory is not globally grouped")
    summary = _require_object(payload.get("project_summary"), path="/project_summary")
    _require_exact_fields(summary, _SUMMARY_FIELDS, path="/project_summary")
    for field in _SUMMARY_FIELDS - {"not_the_product"}:
        _require_text(summary.get(field), path=f"/project_summary/{field}")
    _require_text_list(
        summary.get("not_the_product"),
        path="/project_summary/not_the_product",
        allow_empty=True,
    )
    generator = _require_object(payload.get("generator"), path="/generator")
    _require_exact_fields(generator, _GENERATOR_FIELDS, path="/generator")
    for field in _GENERATOR_FIELDS:
        _require_text(generator.get(field), path=f"/generator/{field}")
    project = _require_object(payload.get("project"), path="/project")
    _require_exact_fields(project, _PROJECT_FIELDS, path="/project")
    _require_text(project.get("name"), path="/project/name")
    _require_text(project.get("path"), path="/project/path")
    _require_text(project.get("commit"), path="/project/commit", nullable=True)
    _require_text(project.get("branch"), path="/project/branch", nullable=True)
    _require_text(
        project.get("analysis_fingerprint"), path="/project/analysis_fingerprint"
    )
    manifest = _require_text(
        payload.get("source_manifest_sha256"), path="/source_manifest_sha256"
    )
    assert isinstance(manifest, str)
    if len(manifest) != 64:
        raise ValueError("source_manifest_sha256 must contain 64 hexadecimal characters")
    try:
        int(manifest, 16)
    except ValueError as error:
        raise ValueError(
            "source_manifest_sha256 must contain 64 hexadecimal characters"
        ) from error
    _require_text(payload.get("cache_key"), path="/cache_key")
    _require_relative_path(
        payload.get("validation_artifact"), path="/validation_artifact"
    )
    capabilities = payload.get("capabilities")
    dispositions = payload.get("module_dispositions")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("capability inventory contains no capabilities")
    if not isinstance(dispositions, list) or not dispositions:
        raise ValueError("capability inventory contains no module dispositions")
    capability_ids: set[str] = set()
    implementation_paths: set[str] = set()
    for index, raw_item in enumerate(capabilities):
        item = _require_object(raw_item, path=f"/capabilities/{index}")
        _require_exact_fields(item, _CAPABILITY_FIELDS, path=f"/capabilities/{index}")
        item_id = _require_text(item.get("id"), path=f"/capabilities/{index}/id")
        assert isinstance(item_id, str)
        capability_ids.add(item_id)
        for field in _CAPABILITY_FIELDS - {
            "id",
            "importance",
            "implementation_modules",
            "source_feature_ids",
            "evidence_ids",
            "source_refs",
        }:
            _require_text(item.get(field), path=f"/capabilities/{index}/{field}")
        if item.get("importance") not in {
            "core-journey",
            "differentiator",
            "dependent-capability",
            "supporting",
        }:
            raise ValueError(f"/capabilities/{index}/importance is unsupported")
        _require_text_list(
            item.get("source_feature_ids"),
            path=f"/capabilities/{index}/source_feature_ids",
        )
        _require_text_list(
            item.get("evidence_ids"), path=f"/capabilities/{index}/evidence_ids"
        )
        modules = item.get("implementation_modules")
        if not isinstance(modules, list) or not modules:
            raise ValueError(
                f"/capabilities/{index}/implementation_modules must be non-empty"
            )
        for module_index, raw_module in enumerate(modules):
            module = _require_object(
                raw_module,
                path=f"/capabilities/{index}/implementation_modules/{module_index}",
            )
            _require_exact_fields(
                module,
                _MODULE_FIELDS,
                path=f"/capabilities/{index}/implementation_modules/{module_index}",
            )
            module_path = _require_relative_path(
                module.get("path"),
                path=f"/capabilities/{index}/implementation_modules/{module_index}/path",
            )
            implementation_paths.add(module_path)
            if module.get("classification") not in {"core", "supporting"}:
                raise ValueError("implementation module classification is unsupported")
            for field in ("responsibility", "handoff"):
                _require_text(
                    module.get(field),
                    path=f"/capabilities/{index}/implementation_modules/{module_index}/{field}",
                )
        refs = item.get("source_refs")
        if not isinstance(refs, list) or len(refs) < 3:
            raise ValueError(f"capability {item_id} must contain at least three source_refs")
        for ref_index, raw_ref in enumerate(refs):
            ref = _require_object(
                raw_ref, path=f"/capabilities/{index}/source_refs/{ref_index}"
            )
            _require_exact_fields(
                ref,
                _SOURCE_REF_FIELDS,
                path=f"/capabilities/{index}/source_refs/{ref_index}",
            )
            _require_relative_path(
                ref.get("path"),
                path=f"/capabilities/{index}/source_refs/{ref_index}/path",
            )
            start = ref.get("line_start")
            end = ref.get("line_end")
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start < 1
                or end < start
            ):
                raise ValueError(
                    f"/capabilities/{index}/source_refs/{ref_index} has an invalid range"
                )
            _require_text(
                ref.get("claim"),
                path=f"/capabilities/{index}/source_refs/{ref_index}/claim",
            )
    if len(capability_ids) != len(capabilities):
        raise ValueError("capability inventory has empty or duplicate capability ids")
    disposition_paths: set[str] = set()
    for index, raw_disposition in enumerate(dispositions):
        disposition = _require_object(
            raw_disposition, path=f"/module_dispositions/{index}"
        )
        _require_exact_fields(
            disposition, _DISPOSITION_FIELDS, path=f"/module_dispositions/{index}"
        )
        disposition_path = _require_relative_path(
            disposition.get("path"), path=f"/module_dispositions/{index}/path"
        )
        if disposition_path in disposition_paths:
            raise ValueError("module disposition paths must be unique")
        disposition_paths.add(disposition_path)
        disposition_kind = disposition.get("disposition")
        if disposition_kind not in {"core-capability", "supporting", "excluded"}:
            raise ValueError("module disposition kind is unsupported")
        members = disposition.get("capability_ids")
        if not isinstance(members, list) or any(
            not isinstance(member, str) or member not in capability_ids
            for member in members
        ):
            raise ValueError("module disposition references an unknown capability id")
        if disposition_kind == "core-capability" and not members:
            raise ValueError("core module disposition must reference a capability id")
        _require_text(
            disposition.get("reason"), path=f"/module_dispositions/{index}/reason"
        )
    missing_dispositions = implementation_paths - disposition_paths
    if missing_dispositions:
        raise ValueError(
            "implementation modules have no disposition: "
            + ", ".join(sorted(missing_dispositions))
        )
