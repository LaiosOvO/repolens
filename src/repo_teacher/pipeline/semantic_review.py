"""Independent semantic review stage for capability inventories."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from ..persistence import read_json_path
from ..schemas import inventory_semantic_review_json_schema
from .cache_identity import provider_stage_identity
from .evidence_packets import (
    _add_project_navigation,
    _build_chapter_batch_pack,
    _indexed_file_hashes,
    _materialize_source_slice,
    _stage_model_json,
)
from .prompt_contracts import inventory_review_prompt
from .partitioning import INVENTORY_SOURCE_EXCERPT_BUDGET, require_packet_budget
from .report_contracts import _attach_source_excerpts
from .serialization import json_artifact


def require_inventory_semantic_review(
    payload: dict[str, object],
    capability_ids: Sequence[str],
    candidate_ids: Sequence[str] | None = None,
) -> None:
    """Validate reviewer completeness and PASS/FAIL consistency."""

    expected = list(capability_ids)
    reviewed = payload.get("reviewed_capability_ids")
    if not isinstance(reviewed, list) or sorted(reviewed) != sorted(expected):
        raise ValueError("semantic reviewer did not review the exact capability set")
    if len(reviewed) != len(set(reviewed)):
        raise ValueError("semantic reviewer returned duplicate capability ids")
    checks = payload.get("checks")
    issues = payload.get("issues")
    status = payload.get("status")
    if not isinstance(checks, dict) or not isinstance(issues, list):
        raise ValueError("semantic reviewer omitted checks or issues")
    required_checks = {
        "product_positioning",
        "business_semantics",
        "causal_evidence",
        "product_coverage",
    }
    if not required_checks <= set(checks) or any(
        checks.get(name) not in {"passed", "failed"} for name in required_checks
    ):
        raise ValueError("semantic reviewer returned invalid checks")
    known = set(expected)
    known_candidates = set(candidate_ids) if candidate_ids is not None else None
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("semantic reviewer returned a non-object issue")
        capability_id = issue.get("capability_id")
        if capability_id not in known and capability_id != "":
            raise ValueError("semantic reviewer issue references an unknown capability")
        if issue.get("retry_stage") not in {
            "evidence-pack",
            "capability-inventory",
            "global-grouping",
        }:
            raise ValueError("semantic reviewer issue has no valid retry stage")
        affected = issue.get("affected_candidate_ids")
        if (
            not isinstance(affected, list)
            or not affected
            or len(affected) != len(set(affected))
            or any(not isinstance(item, str) or not item for item in affected)
            or (
                known_candidates is not None
                and any(item not in known_candidates for item in affected)
            )
        ):
            raise ValueError(
                "semantic reviewer issue has no exact affected candidate closure"
            )
    all_passed = all(value == "passed" for value in checks.values())
    if status == "passed" and (issues or not all_passed):
        raise ValueError("semantic reviewer claimed PASS with failed checks or issues")
    if status == "failed" and (not issues or all_passed):
        raise ValueError("semantic reviewer claimed FAIL without an actionable issue")
    if status not in {"passed", "failed"}:
        raise ValueError("semantic reviewer returned an invalid status")


def _normalize_inventory_semantic_review(
    payload: dict[str, object],
) -> dict[str, object]:
    """Canonicalize lossless list noise without inventing review semantics.

    Structured model output can repeat the same candidate ID inside one issue.
    Repetition carries no additional meaning, so preserving the first occurrence
    is safe.  Unknown, missing, empty, or otherwise invalid IDs remain untouched
    and are rejected by ``require_inventory_semantic_review``.
    """

    normalized = copy.deepcopy(payload)
    issues = normalized.get("issues")
    if not isinstance(issues, list):
        return normalized
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        affected = issue.get("affected_candidate_ids")
        if not isinstance(affected, list):
            continue
        issue["affected_candidate_ids"] = list(dict.fromkeys(affected))
    return normalized


def _stable_review_packet_sha256(payload: dict[str, object]) -> str:
    stable = copy.deepcopy(payload)
    project = stable.get("project")
    if isinstance(project, dict):
        project.pop("path", None)
        project.pop("git_root", None)
    return hashlib.sha256(json_artifact(stable).encode("utf-8")).hexdigest()


def _compact_raw_candidates(
    candidate_payload: dict[str, object],
) -> tuple[list[dict[str, object]], set[str]]:
    """Keep coverage evidence without duplicating full candidate prose/graphs."""

    compact: list[dict[str, object]] = []
    source_paths: set[str] = set()
    for candidate in candidate_payload.get("capabilities", []):
        if not isinstance(candidate, dict):
            continue
        refs: list[dict[str, object]] = []
        candidate_paths: set[str] = set()
        raw_refs = candidate.get("source_refs")
        if isinstance(raw_refs, list):
            for ref in raw_refs:
                if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
                    continue
                path = str(ref["path"])
                source_paths.add(path)
                candidate_paths.add(path)
                if len(refs) >= 6:
                    continue
                refs.append(
                    {
                        key: ref[key]
                        for key in (
                            "path",
                            "line_start",
                            "line_end",
                            "symbol_id",
                            "relationship_id",
                            "evidence_id",
                        )
                        if key in ref
                    }
                )
        compact.append(
            {
                "id": candidate.get("id"),
                "title": candidate.get("title"),
                "summary": candidate.get("one_sentence_summary")
                or candidate.get("summary"),
                "source_feature_ids": candidate.get("source_feature_ids", []),
                "source_paths": sorted(candidate_paths),
                "source_refs": refs,
                "source_ref_count": len(raw_refs) if isinstance(raw_refs, list) else 0,
            }
        )
    return compact, source_paths


def run_inventory_semantic_review(
    *,
    source: Path,
    pack: dict[str, object],
    candidate_payload: dict[str, object],
    inventory_payload: dict[str, object],
    workspace: Path,
    provider: str,
    timeout: int,
    runner: Callable[..., dict[str, object]],
    stage_slug: str = "inventory-semantic-review",
    review_capability_ids: set[str] | None = None,
    review_candidate_ids: set[str] | None = None,
) -> dict[str, object]:
    """Review the full inventory once, then only locally repaired capabilities."""

    all_capabilities = [
        item
        for item in inventory_payload.get("capabilities", [])
        if isinstance(item, dict)
    ]
    all_capability_ids = {
        str(item.get("id") or "") for item in all_capabilities
    }
    if review_capability_ids is not None and (
        not review_capability_ids or not review_capability_ids <= all_capability_ids
    ):
        raise ValueError("semantic delta review references an unknown capability")
    capabilities = [
        item
        for item in all_capabilities
        if review_capability_ids is None
        or str(item.get("id") or "") in review_capability_ids
    ]
    capability_ids = [str(item.get("id") or "") for item in capabilities]
    if any(not identifier for identifier in capability_ids):
        raise ValueError("semantic review received an empty capability id")
    all_raw_candidates = [
        item
        for item in candidate_payload.get("capabilities", [])
        if isinstance(item, dict)
    ]
    all_candidate_ids = {
        str(item.get("id") or "") for item in all_raw_candidates
    }
    if review_candidate_ids is not None and (
        not review_candidate_ids or not review_candidate_ids <= all_candidate_ids
    ):
        raise ValueError("semantic delta review references an unknown raw candidate")
    raw_candidates = [
        item
        for item in all_raw_candidates
        if review_candidate_ids is None
        or str(item.get("id") or "") in review_candidate_ids
    ]
    candidate_ids = [str(item.get("id") or "") for item in raw_candidates]
    if any(not identifier for identifier in candidate_ids) or len(candidate_ids) != len(
        set(candidate_ids)
    ):
        raise ValueError("semantic review received invalid raw candidate ids")
    review_workspace = workspace / stage_slug
    review_workspace.mkdir(parents=True, exist_ok=True)
    review_path = review_workspace / "inventory-validation.json"
    identity_path = review_workspace / "inventory-validation.cache-identity.json"
    review_pack = _build_chapter_batch_pack(pack, copy.deepcopy(capabilities))
    review_pack = _add_project_navigation(review_pack, pack)
    review_pack["project_summary"] = copy.deepcopy(
        inventory_payload.get("project_summary")
    )
    # The final inventory already carries canonical evidence/feature IDs and
    # exact source refs.  Repeating the complete graph, feature hints and
    # evidence records here made the independent review packet larger than the
    # inventory it reviews.  The reviewer receives the integrity-bound source
    # slice instead and can reopen every allowed path when challenging a claim.
    review_pack.pop("capability_graph", None)
    review_pack.pop("feature_hints", None)
    review_pack.pop("evidence", None)
    review_pack["review_evidence_contract"] = (
        "Use each final capability source_ref and the isolated allowed source "
        "files; raw candidates are compact coverage leads, not accepted claims."
    )
    compact_candidates, raw_source_paths = _compact_raw_candidates(
        {"capabilities": raw_candidates}
    )
    indexed_hashes = _indexed_file_hashes(pack)
    raw_source_paths &= set(indexed_hashes)
    review_pack["raw_candidate_inventory"] = {
        "capabilities": compact_candidates,
        "candidate_count": len(raw_candidates),
    }
    if review_capability_ids is not None:
        review_pack["review_mode"] = "local-repair-delta"
        review_pack["accepted_capability_summaries"] = [
            {
                key: item.get(key)
                for key in (
                    "id",
                    "title",
                    "user_actor",
                    "user_goal",
                    "visible_outcome",
                    "product_surface",
                    "causal_flow",
                )
            }
            for item in all_capabilities
            if str(item.get("id") or "") not in review_capability_ids
        ]
    scope = review_pack.get("scope")
    if isinstance(scope, dict):
        allowed = scope.get("allowed_source_paths")
        if isinstance(allowed, list):
            scope["allowed_source_paths"] = sorted(
                {str(path) for path in allowed if isinstance(path, str)}
                | raw_source_paths
            )
    review_pack = _attach_source_excerpts(
        review_pack,
        source,
        character_budget=INVENTORY_SOURCE_EXCERPT_BUDGET,
    )
    require_packet_budget(review_pack)
    packet_path = review_workspace / "analysis-pack-review.json"
    packet_path.write_text(json_artifact(review_pack), encoding="utf-8")
    source_slice = _materialize_source_slice(
        source,
        review_workspace,
        review_pack["scope"]["allowed_source_paths"],
        indexed_hashes,
    )
    model_packet_path = _stage_model_json(
        source_slice, "analysis-pack-review.json", review_pack
    )
    model_inventory_path = _stage_model_json(
        source_slice, "capability-inventory.json", inventory_payload
    )
    review_schema = inventory_semantic_review_json_schema(
        capability_ids, candidate_ids
    )
    review_prompt = inventory_review_prompt(
        model_packet_path,
        model_inventory_path,
        source_slice,
        capability_ids,
    )
    review_identity = {
        "schema_version": "repolens-stage-cache-identity/v1",
        "stage": stage_slug,
        "provider": provider_stage_identity(provider, inventory=False),
        "packet_sha256": _stable_review_packet_sha256(review_pack),
        "inventory_sha256": hashlib.sha256(
            json_artifact(inventory_payload).encode("utf-8")
        ).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json_artifact(review_schema).encode("utf-8")
        ).hexdigest(),
        "prompt_sha256": hashlib.sha256(review_prompt.encode("utf-8")).hexdigest(),
    }
    review_identity["identity_sha256"] = hashlib.sha256(
        json_artifact(review_identity).encode("utf-8")
    ).hexdigest()
    if review_path.is_file() and identity_path.is_file():
        try:
            cached_identity = read_json_path(identity_path)
            cached = read_json_path(review_path)
            if cached_identity != review_identity:
                raise ValueError("semantic review cache identity changed")
            require_inventory_semantic_review(cached, capability_ids, candidate_ids)
            return cached
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass
    review = runner(
        source=source_slice,
        workspace=review_workspace,
        schema=review_schema,
        prompt=review_prompt,
        timeout=timeout,
        stage_slug=stage_slug,
        progress_label=f"{provider} 正在独立反证 {len(capability_ids)} 项业务功能",
        provider=provider,
    )
    review = _normalize_inventory_semantic_review(review)
    require_inventory_semantic_review(review, capability_ids, candidate_ids)
    review["schema_version"] = "repolens-inventory-validation/v1"
    review["reviewer"] = "capability-reviewer"
    review_path.write_text(json_artifact(review), encoding="utf-8")
    identity_path.write_text(json_artifact(review_identity), encoding="utf-8")
    return review
