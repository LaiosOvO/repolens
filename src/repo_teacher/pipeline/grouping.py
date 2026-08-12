"""Model-assisted grouping of evidence-closed candidates into human capabilities."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Sequence

from ..persistence import read_json_path
from ..prompts import render_prompt
from ..providers import run_structured_json
from ..schemas import (
    inventory_group_json_schema,
)
from .cache_identity import provider_stage_identity
from .paths import repo_path_parts as _repo_path_parts
from .serialization import json_artifact as _json_artifact
from .timeouts import remaining_model_timeout


_PROJECT_SUMMARY_FIELDS = {
    "product_type",
    "primary_actor",
    "primary_outcome",
    "main_runtime",
    "not_the_product",
}


def _valid_project_summary(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == _PROJECT_SUMMARY_FIELDS
        and all(
            isinstance(value.get(field), str) and str(value[field]).strip()
            for field in _PROJECT_SUMMARY_FIELDS - {"not_the_product"}
        )
        and isinstance(value.get("not_the_product"), list)
        and bool(value["not_the_product"])
        and all(
            isinstance(item, str) and item.strip()
            for item in value["not_the_product"]
        )
    )


def _grouping_partition_feedback(
    grouped: dict[str, object], input_ids: set[str]
) -> dict[str, object] | None:
    groups = grouped.get("groups")
    exclusions = grouped.get("excluded_supporting_items")
    if not isinstance(groups, list) or not isinstance(exclusions, list):
        return {
            "code": "grouping-partition-invalid",
            "message": "groups and excluded_supporting_items must both be arrays",
        }
    seen: list[str] = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("member_ids"), list):
            return {
                "code": "grouping-partition-invalid",
                "message": "every group must contain a member_ids array",
            }
        seen.extend(
            identifier
            for identifier in group["member_ids"]
            if isinstance(identifier, str)
        )
    seen.extend(
        str(item["member_id"])
        for item in exclusions
        if isinstance(item, dict) and isinstance(item.get("member_id"), str)
    )
    seen_set = set(seen)
    duplicates = sorted({identifier for identifier in seen if seen.count(identifier) > 1})
    missing = sorted(input_ids - seen_set)
    unknown = sorted(seen_set - input_ids)
    if not missing and not unknown and not duplicates and len(seen) == len(input_ids):
        return None
    return {
        "code": "grouping-partition-incomplete",
        "message": "Every candidate ID must appear exactly once in a group or exclusion.",
        "missing_ids": missing,
        "unknown_ids": unknown,
        "duplicate_ids": duplicates,
    }


def _group_inventory_for_humans(
    payload: dict[str, object],
    *,
    source: Path,
    workspace: Path,
    deadline: float,
    provider: str,
    product_navigation: Sequence[dict[str, object]] = (),
) -> dict[str, object]:
    capabilities = [
        item for item in payload.get("capabilities", []) if isinstance(item, dict)
    ]
    if not capabilities:
        raise ValueError("capability grouping requires at least one candidate")
    cache_path = workspace / "grouped-capability-inventory.json"
    cache_identity_path = workspace / "grouped-capability-inventory.cache-identity.json"
    cache_identity = {
        "schema_version": "repolens-grouping-cache-identity/v1",
        "provider": provider_stage_identity(provider, inventory=False),
        "input_sha256": hashlib.sha256(
            _json_artifact(
                {
                    "capabilities": capabilities,
                    "product_navigation": product_navigation,
                }
            ).encode("utf-8")
        ).hexdigest(),
        "prompt_sha256": hashlib.sha256(
            Path(__file__)
            .parent.parent.joinpath("prompts", "inventory-grouping-v1.md")
            .read_bytes()
        ).hexdigest(),
        "schema_sha256": hashlib.sha256(
            _json_artifact(
                inventory_group_json_schema(
                    allow_empty=False,
                    approved_capability_ids=[],
                )
            ).encode("utf-8")
        ).hexdigest(),
    }
    if cache_path.is_file():
        try:
            if (
                not cache_identity_path.is_file()
                or read_json_path(cache_identity_path) != cache_identity
            ):
                raise ValueError("grouping cache identity changed")
            cached = read_json_path(cache_path)
            cached_capabilities = cached.get("capabilities")
            cached_dispositions = cached.get("module_dispositions")
            cached_membership = cached.get("grouping_membership")
            cached_output_ids = {
                str(item.get("id"))
                for item in (
                    cached_capabilities if isinstance(cached_capabilities, list) else []
                )
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            if (
                _valid_project_summary(cached.get("project_summary"))
                and
                isinstance(cached_capabilities, list)
                and bool(cached_capabilities)
                and isinstance(cached_dispositions, list)
                and cached_dispositions
                and all(
                    isinstance(item, dict)
                    and item.get("importance")
                    in {
                        "core-journey",
                        "differentiator",
                        "dependent-capability",
                        "supporting",
                    }
                    for item in cached_capabilities
                )
                and isinstance(cached_membership, dict)
                and set(cached_membership) == cached_output_ids
            ):
                print(
                    f"[report 4/6] 复用面向人类阅读的功能分组缓存，共 {len(cached_capabilities)} 章",
                    flush=True,
                )
                return cached
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass
    compact = []
    for item in capabilities:
        compact_refs = [
            {
                "path": ref.get("path"),
                "line_start": ref.get("line_start"),
                "line_end": ref.get("line_end"),
                "claim": str(ref.get("claim") or "")[:240],
            }
            for ref in item.get("source_refs", [])
            if isinstance(ref, dict) and isinstance(ref.get("path"), str)
        ][:8]
        compact.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "plain_summary": item.get("plain_summary"),
            "mechanism": item.get("mechanism"),
            "importance": item.get("importance"),
            "user_actor": item.get("user_actor"),
            "user_goal": item.get("user_goal"),
            "visible_outcome": item.get("visible_outcome"),
            "product_surface": item.get("product_surface"),
            "causal_flow": item.get("causal_flow"),
            "implementation_modules": [
                module
                for module in item.get("implementation_modules", [])
                if isinstance(module, dict)
            ],
            "paths": list(
                dict.fromkeys(
                    str(ref.get("path"))
                    for ref in item.get("source_refs", [])
                    if isinstance(ref, dict)
                    and isinstance(ref.get("path"), str)
                )
            )[:16],
            "source_refs": compact_refs,
        })
    compact_by_id = {
        str(item["id"]): item
        for item in compact
        if isinstance(item.get("id"), str)
    }
    del compact_by_id
    positioning = [
        {
            "path": item.get("path"),
            "snippet": str(item.get("snippet") or "")[:12_000],
        }
        for item in product_navigation
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]
    prompt = render_prompt(
        "inventory-grouping-v1.md",
        product_navigation_json=json.dumps(
            positioning, ensure_ascii=False, separators=(",", ":")
        ),
        inventory_json=json.dumps(
            compact, ensure_ascii=False, separators=(",", ":")
        ),
        review_feedback_json="{}",
        approved_capabilities_json="[]",
    )
    cache_identity_sha256 = hashlib.sha256(
        _json_artifact(cache_identity).encode("utf-8")
    ).hexdigest()[:24]
    grouping_workspace = workspace / f"grouping-{cache_identity_sha256}"
    grouping_source = grouping_workspace / "source-slice"
    grouping_source.mkdir(parents=True, exist_ok=True)
    grouped = run_structured_json(
        source=grouping_source,
        workspace=grouping_workspace,
        schema=inventory_group_json_schema(
            allow_empty=False,
            approved_capability_ids=[],
        ),
        prompt=prompt,
        timeout=remaining_model_timeout(deadline),
        stage_slug="capability-grouping",
        progress_label=f"Codex 正在把 {len(capabilities)} 个细粒度条目组织成人类功能章节",
        provider=provider,
    )
    if not _valid_project_summary(grouped.get("project_summary")):
        raise ValueError("capability grouping omitted the structured product contract")
    by_id = {
        str(item.get("id")): item
        for item in capabilities
        if isinstance(item.get("id"), str)
    }
    partition_feedback = _grouping_partition_feedback(grouped, set(by_id))
    if partition_feedback is not None:
        raise ValueError(
            "capability grouping must place every candidate exactly once: "
            + _json_artifact(partition_feedback).strip()
        )
    assigned: set[str] = set()
    excluded: set[str] = set()
    member_to_group: dict[str, str] = {}
    result: list[dict[str, object]] = []
    importance_rank = {
        "core-journey": 0,
        "differentiator": 1,
        "dependent-capability": 2,
        "supporting": 3,
    }
    groups = grouped.get("groups")
    if not isinstance(groups, list):
        groups = []
    exclusions = grouped.get("excluded_supporting_items")
    if not isinstance(exclusions, list):
        exclusions = []
    for exclusion in exclusions:
        if not isinstance(exclusion, dict):
            raise ValueError("capability grouping produced an invalid exclusion")
        member_id = exclusion.get("member_id")
        reason = exclusion.get("reason")
        if (
            not isinstance(member_id, str)
            or member_id not in by_id
            or not isinstance(reason, str)
            or not reason.strip()
            or member_id in excluded
        ):
            raise ValueError("capability grouping produced an invalid exclusion")
        excluded.add(member_id)
    for position, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            continue
        raw_member_ids = group.get("member_ids")
        if not isinstance(raw_member_ids, list):
            raise ValueError("capability grouping produced invalid member_ids")
        member_ids = [identifier for identifier in raw_member_ids if isinstance(identifier, str)]
        if (
            len(member_ids) != len(raw_member_ids)
            or any(identifier not in by_id for identifier in member_ids)
            or any(identifier in assigned or identifier in excluded for identifier in member_ids)
        ):
            raise ValueError("capability grouping did not produce an exact id partition")
        if not member_ids:
            raise ValueError("capability grouping produced an empty group")
        assigned.update(member_ids)
        merge_target = str(group.get("merge_into_capability_id") or "__new__")
        if merge_target != "__new__":
            raise ValueError("capability grouping targeted an unknown approved capability")
        group_id = str(group.get("id") or f"capability-group-{position}")
        member_to_group.update(
            {member_id: group_id for member_id in member_ids}
        )
        members = [by_id[identifier] for identifier in member_ids]
        implementation_refs = [
            source_ref
            for member in members
            for source_ref in member.get("source_refs", [])
            if isinstance(source_ref, dict)
            and isinstance(source_ref.get("path"), str)
            and not any(
                part.casefold() in {
                    "docs", "specs", "examples", "example", "demo", "demos",
                    "sample", "samples", "test", "tests", "fixtures",
                }
                for part in _repo_path_parts(str(source_ref.get("path")))
            )
        ]
        if not implementation_refs:
            raise ValueError(
                "capability grouping promoted an example/document/test without product implementation evidence"
            )
        title = str(group.get("title") or "").strip() or f"业务功能 {position}"
        user_actor = str(group.get("user_actor") or "").strip()
        user_goal = str(group.get("user_goal") or "").strip()
        visible_outcome = str(group.get("visible_outcome") or "").strip()
        product_surface = str(group.get("product_surface") or "").strip()
        causal_flow = str(group.get("causal_flow") or "").strip()
        if not all((user_actor, user_goal, visible_outcome, product_surface, causal_flow)):
            raise ValueError("capability grouping omitted business capability semantics")
        source_refs: list[dict[str, object]] = []
        seen_refs: set[tuple[object, ...]] = set()
        for member in members:
            for source_ref in member.get("source_refs", []):
                if not isinstance(source_ref, dict):
                    continue
                key = (
                    source_ref.get("path"),
                    source_ref.get("line_start"),
                    source_ref.get("line_end"),
                )
                if key in seen_refs:
                    continue
                seen_refs.add(key)
                source_refs.append(copy.deepcopy(source_ref))
        mechanisms = list(
            dict.fromkeys(
                str(member.get("mechanism") or "")
                for member in members
                if member.get("mechanism")
            )
        )
        importance = str(group.get("importance") or "")
        if importance not in importance_rank:
            importance = min(
                (
                    str(member.get("importance") or "supporting")
                    for member in members
                ),
                key=lambda value: importance_rank.get(value, 3),
                default="supporting",
            )
        implementation_by_path: dict[str, dict[str, object]] = {}
        evidenced_paths = {
            str(source_ref["path"])
            for member in members
            for source_ref in member.get("source_refs", [])
            if isinstance(source_ref, dict)
            and isinstance(source_ref.get("path"), str)
        }
        for member in members:
            for module in member.get("implementation_modules", []):
                if not isinstance(module, dict) or not isinstance(module.get("path"), str):
                    continue
                path = str(module["path"])
                if not any(
                    evidence_path == path
                    or evidence_path.startswith(f"{path.rstrip('/')}/")
                    for evidence_path in evidenced_paths
                ):
                    # A model may infer a plausible handoff module from the
                    # graph, but final mechanism prose may only expose modules
                    # covered by canonical source refs. The reviewer can then
                    # request a new evidence-pack instead of auditing a claim
                    # that the report cannot prove.
                    continue
                current = implementation_by_path.get(path)
                if current is None:
                    implementation_by_path[path] = copy.deepcopy(module)
                    continue
                if module.get("classification") == "core":
                    current["classification"] = "core"
                for field in ("responsibility", "handoff"):
                    old = str(current.get(field) or "").strip()
                    new = str(module.get(field) or "").strip()
                    if new and new not in old:
                        current[field] = f"{old}；{new}" if old else new
        grouped_capability = {
                "id": group_id,
                "title": title,
                "summary": (
                    f"{user_actor}为了{user_goal}使用{product_surface}，最终得到{visible_outcome}。"
                ),
                "mechanism": " + ".join(mechanisms[:8]) or "multi-stage-capability",
                "importance": importance,
                "user_actor": user_actor,
                "user_goal": user_goal,
                "visible_outcome": visible_outcome,
                "product_surface": product_surface,
                "causal_flow": causal_flow,
                "why_one_capability": str(group.get("why_one_capability") or "").strip(),
                "implementation_modules": list(implementation_by_path.values()),
                "question": f"{causal_flow}在源码中怎样跨模块完成，并在哪些状态与失败边界收束？",
                "use_when": f"当你需要复用“{visible_outcome}”这项完整产品结果时。",
                "distinguish": (
                    "这是用户可感知的业务/框架能力；组成它的目录、API、适配器与示例只作为实现证据。"
                ),
                "plain_summary": (
                    f"{title} 本质上是{causal_flow}；它交付的是{visible_outcome}，"
                    "不是某个入口、目录或示例脚本。"
                ),
                "source_feature_ids": list(
                    dict.fromkeys(
                        identifier
                        for member in members
                        for identifier in member.get("source_feature_ids", [])
                        if isinstance(identifier, str)
                    )
                ),
                "evidence_ids": list(
                    dict.fromkeys(
                        identifier
                        for member in members
                        for identifier in member.get("evidence_ids", [])
                        if isinstance(identifier, str)
                    )
                ),
                # Preserve at least one canonical source ref for every member.
                # A fixed 16-ref prefix silently erased late providers in a
                # multi-provider capability while prose still named them.
                "source_refs": source_refs,
            }
        result.append(grouped_capability)
    if assigned | excluded != set(by_id):
        raise ValueError("capability grouping omitted input ids")
    result.sort(key=lambda item: importance_rank[str(item["importance"])])
    if excluded:
        print(
            f"[report 4/6] 排除 {len(excluded)} 个仅承载、运维或测试用途的支撑项；不作为产品功能章节",
            flush=True,
        )
    if not result:
        raise ValueError("capability grouping excluded every candidate")
    grouped_dispositions: dict[str, dict[str, object]] = {}
    raw_dispositions = payload.get("module_dispositions")
    if isinstance(raw_dispositions, list):
        for raw in raw_dispositions:
            if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
                continue
            path = str(raw["path"])
            raw_members = raw.get("capability_ids")
            mapped_members = list(
                dict.fromkeys(
                    member_to_group[member]
                    for member in (raw_members if isinstance(raw_members, list) else [])
                    if isinstance(member, str) and member in member_to_group
                )
            )
            disposition = str(raw.get("disposition") or "supporting")
            if disposition == "core-capability" and not mapped_members:
                disposition = "supporting"
            copied = {
                "path": path,
                "disposition": disposition,
                "capability_ids": mapped_members,
                "reason": str(raw.get("reason") or "实现模块随全局业务功能重新归组。"),
            }
            existing = grouped_dispositions.get(path)
            if existing is None:
                grouped_dispositions[path] = copied
                continue
            existing["capability_ids"] = list(
                dict.fromkeys(
                    [
                        *existing.get("capability_ids", []),
                        *mapped_members,
                    ]
                )
            )
            if mapped_members and existing.get("disposition") != "excluded":
                existing["disposition"] = "core-capability"

    for capability in result:
        capability_id = str(capability["id"])
        for module in capability.get("implementation_modules", []):
            if not isinstance(module, dict) or not isinstance(module.get("path"), str):
                continue
            path = str(module["path"])
            disposition = grouped_dispositions.setdefault(
                path,
                {
                    "path": path,
                    "disposition": "core-capability",
                    "capability_ids": [],
                    "reason": "该模块直接参与已确认业务功能的端到端实现。",
                },
            )
            members = disposition.get("capability_ids")
            if not isinstance(members, list):
                members = []
                disposition["capability_ids"] = members
            if capability_id not in members:
                members.append(capability_id)
            if disposition.get("disposition") != "excluded":
                disposition["disposition"] = "core-capability"

    if not grouped_dispositions:
        raise ValueError("capability grouping produced no module disposition closure")
    grouped_payload = {
        "schema_version": "repo-teacher-capability-inventory/v1",
        "grouping_complete": True,
        "project_summary": copy.deepcopy(grouped["project_summary"]),
        "capabilities": result,
        "module_dispositions": [
            grouped_dispositions[path] for path in sorted(grouped_dispositions)
        ],
        "grouping_membership": {
            group_id: sorted(
                member
                for member, mapped_group_id in member_to_group.items()
                if mapped_group_id == group_id
            )
            for group_id in sorted(set(member_to_group.values()))
        },
        "excluded_candidate_ids": sorted(excluded),
    }
    cache_path.write_text(_json_artifact(grouped_payload), encoding="utf-8")
    cache_identity_path.write_text(
        _json_artifact(cache_identity), encoding="utf-8"
    )
    print(
        f"[report 4/6] 细粒度目录组织为 {len(result)} 个可读功能章节；没有丢弃输入条目",
        flush=True,
    )
    return grouped_payload
