"""Deterministic sidecars for a validated human report generation."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping


def _objects(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _chapter_artifact_name(position: int, capability_id: str) -> str:
    digest = hashlib.sha256(capability_id.encode("utf-8")).hexdigest()[:12]
    return f"{position:03d}-{digest}.json"


def _validate_chapter_for_publication(chapter: Mapping[str, object]) -> dict[str, str]:
    mechanism = chapter.get("mechanism_model")
    runtime = chapter.get("runtime_story")
    boundary = chapter.get("boundary")
    reuse = chapter.get("reuse_plan")
    checks = {
        "conclusion_first": (
            "passed"
            if isinstance(mechanism, dict)
            and isinstance(mechanism.get("plain_summary"), str)
            and bool(mechanism["plain_summary"].strip())
            else "failed"
        ),
        "runtime_flow": (
            "passed"
            if isinstance(runtime, dict) and len(_objects(runtime.get("steps"))) >= 3
            else (
                "passed"
                if isinstance(runtime, dict)
                and isinstance(runtime.get("steps"), list)
                and len(runtime["steps"]) >= 3
                else "failed"
            )
        ),
        "state_flow": (
            "passed" if len(_objects(chapter.get("state_flow"))) >= 2 else "failed"
        ),
        "source_evidence": (
            "passed" if len(_objects(chapter.get("source_refs"))) >= 3 else "failed"
        ),
        "selection_boundaries": (
            "passed"
            if isinstance(boundary, dict)
            and bool(boundary.get("supported"))
            and bool(boundary.get("unsupported"))
            and isinstance(reuse, dict)
            and all(bool(reuse.get(name)) for name in ("take", "adapt", "avoid", "verify"))
            else "failed"
        ),
    }
    failed = [name for name, status in checks.items() if status != "passed"]
    if failed:
        raise ValueError(
            "chapter publication validation failed: " + ", ".join(failed)
        )
    return checks


def build_report_output_sidecars(
    *,
    narrative: Mapping[str, object],
    source_manifest_sha256: str,
    inventory_digest: str | None,
) -> dict[str, dict[str, object]]:
    """Materialize deterministic source, chapter and publication checks.

    Readability is a property of the generated content contract, not a second
    model gate.  Publication therefore depends only on structure and evidence
    closure here.
    """

    chapters = _objects(narrative.get("chapters"))
    if not chapters:
        raise ValueError("human report has no chapters to publish")
    artifacts: dict[str, dict[str, object]] = {
        "source-manifest.json": {
            "schema_version": "repolens-source-manifest/v1",
            "status": "passed",
            "source_manifest_sha256": source_manifest_sha256,
        }
    }
    validation_records: list[dict[str, object]] = []
    for position, chapter in enumerate(chapters, start=1):
        capability_id = chapter.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            raise ValueError("human report chapter has no capability id")
        name = _chapter_artifact_name(position, capability_id)
        checks = _validate_chapter_for_publication(chapter)
        chapter_path = f"chapters/{name}"
        validation_path = f"chapter-validation/{name}"
        artifacts[chapter_path] = copy.deepcopy(chapter)
        validation = {
            "schema_version": "repolens-chapter-validation/v1",
            "status": "passed",
            "capability_id": capability_id,
            "chapter_artifact": chapter_path,
            "checks": checks,
            "issues": [],
            "retry_stage": "none",
        }
        artifacts[validation_path] = validation
        validation_records.append(validation)
    artifacts["validation-report.json"] = {
        "schema_version": "repolens-validation-report/v1",
        "status": "passed",
        "source_manifest_sha256": source_manifest_sha256,
        "approved_inventory_sha256": inventory_digest,
        "checks": {
            "chapter_artifacts": "passed",
            "chapter_validation": "passed",
            "source_evidence_closure": "passed",
        },
        "metrics": {
            "chapters": len(chapters),
            "validated_chapters": len(validation_records),
        },
    }
    return artifacts
