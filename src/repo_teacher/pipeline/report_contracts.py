"""Human-report chapter closure and project overview contracts."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Sequence

from .paths import path_is_within_modules as _path_is_within_modules
from .paths import repo_path_parts as _repo_path_parts

def _close_chapter_evidence(
    payload: dict[str, object],
    batch_pack: dict[str, object],
    capabilities: Sequence[dict[str, object]],
    source: Path | None = None,
) -> dict[str, object]:
    """Close model-authored difficulty evidence over the canonical batch packet."""

    scope = batch_pack.get("scope")
    allowed_paths = {
        value
        for value in (
            scope.get("allowed_source_paths", []) if isinstance(scope, dict) else []
        )
        if isinstance(value, str)
    }
    allowed_evidence = {
        evidence.get("id")
        for evidence in batch_pack.get("evidence", [])
        if isinstance(evidence, dict) and isinstance(evidence.get("id"), str)
    }
    excerpt_ranges: dict[str, list[tuple[int, int]]] = {}
    for excerpt in batch_pack.get("source_excerpts", []):
        if not isinstance(excerpt, dict):
            continue
        path = excerpt.get("path")
        start = excerpt.get("line_start")
        end = excerpt.get("line_end")
        if isinstance(path, str) and isinstance(start, int) and isinstance(end, int):
            excerpt_ranges.setdefault(path, []).append((start, end))
    inventory_by_id = {
        str(item.get("id")): item
        for item in capabilities
        if isinstance(item.get("id"), str)
    }
    chapters = payload.get("chapters")
    if not isinstance(chapters, list):
        return payload
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        inventory = inventory_by_id.get(str(chapter.get("id") or ""))
        if inventory is None:
            continue
        chapter["title"] = inventory.get("title")
        chapter["source_feature_ids"] = [
            value
            for value in inventory.get("source_feature_ids", [])
            if isinstance(value, str)
        ]
        for source_ref in chapter.get("source_refs", []):
            if not isinstance(source_ref, dict):
                continue
            raw_path = source_ref.get("path")
            if not isinstance(raw_path, str):
                continue
            normalized_path = raw_path.replace("\\", "/")
            marker = "/source-slice/"
            if marker in normalized_path:
                normalized_path = normalized_path.split(marker, 1)[1]
            while normalized_path.startswith("./"):
                normalized_path = normalized_path[2:]
            if normalized_path in allowed_paths:
                source_ref["path"] = normalized_path
                ranges = excerpt_ranges.get(normalized_path, [])
                if ranges:
                    requested_start = source_ref.get("line_start")
                    requested_end = source_ref.get("line_end")
                    overlap = next(
                        (
                            (max(requested_start, start), min(requested_end, end))
                            for start, end in ranges
                            if isinstance(requested_start, int)
                            and isinstance(requested_end, int)
                            and requested_start <= end
                            and requested_end >= start
                        ),
                        None,
                    )
                    resolved_start, resolved_end = overlap or ranges[0]
                    source_ref["line_start"] = resolved_start
                    source_ref["line_end"] = resolved_end
                elif source is not None:
                    parts = _repo_path_parts(normalized_path)
                    if parts:
                        candidate = source.joinpath(*parts)
                        try:
                            line_count = len(
                                candidate.read_text(encoding="utf-8").splitlines()
                            )
                        except (OSError, UnicodeDecodeError):
                            line_count = 0
                        if line_count:
                            requested_start = source_ref.get("line_start")
                            requested_end = source_ref.get("line_end")
                            resolved_start = (
                                min(max(1, requested_start), line_count)
                                if isinstance(requested_start, int)
                                else 1
                            )
                            resolved_end = (
                                min(max(resolved_start, requested_end), line_count)
                                if isinstance(requested_end, int)
                                else resolved_start
                            )
                            source_ref["line_start"] = resolved_start
                            source_ref["line_end"] = resolved_end
        # Inventory evidence has already passed the full-pack closure gate.  A
        # chapter shard may omit unrelated evidence records for prompt size,
        # but it must never erase the inventory's canonical evidence contract.
        inventory_evidence = [
            value
            for value in inventory.get("evidence_ids", [])
            if isinstance(value, str)
        ]
        chapter_evidence = [
            value
            for value in chapter.get("evidence_ids", [])
            if isinstance(value, str) and value in allowed_evidence
        ]
        difficulties = chapter.get("difficulty_map")
        items = difficulties.get("items") if isinstance(difficulties, dict) else []
        for difficulty in items if isinstance(items, list) else []:
            if not isinstance(difficulty, dict):
                continue
            difficulty_evidence = [
                value
                for value in difficulty.get("evidence_ids", [])
                if isinstance(value, str) and value in allowed_evidence
            ]
            if not difficulty_evidence:
                difficulty_evidence = inventory_evidence[:1]
            difficulty["evidence_ids"] = list(dict.fromkeys(difficulty_evidence))
            chapter_evidence.extend(difficulty_evidence)
        chapter["evidence_ids"] = list(
            dict.fromkeys([*inventory_evidence, *chapter_evidence])
        )
    return payload

def _require_source_ref_quality(chapters: Sequence[dict[str, object]]) -> None:
    for chapter in chapters:
        source_refs = chapter.get("source_refs")
        if not isinstance(source_refs, list) or len(source_refs) < 3:
            raise ValueError("Codex report chapter requires at least three source_refs")
        implementation_refs = []
        for source_ref in source_refs:
            if not isinstance(source_ref, dict):
                continue
            path = str(source_ref.get("path") or "")
            lowered = path.casefold()
            parts = tuple(part.casefold() for part in Path(path).parts)
            if (
                lowered.endswith(".md")
                or "docs" in parts
                or "specs" in parts
                or Path(path).name.casefold().startswith("readme")
            ):
                continue
            implementation_refs.append(source_ref)
        if not implementation_refs:
            raise ValueError(
                "Codex report chapter requires non-document implementation evidence"
            )

def _chunk_capabilities(
    capabilities: Sequence[dict[str, object]], batch_size: int
) -> list[list[dict[str, object]]]:
    return [
        list(capabilities[index : index + batch_size])
        for index in range(0, len(capabilities), batch_size)
    ]

def _ranges_overlap(
    first_start: int, first_end: int, second_start: int, second_end: int
) -> bool:
    return not (first_end < second_start or second_end < first_start)

def _inventory_from_manifest(
    manifest: object, pack: dict[str, object]
) -> dict[str, object]:
    if isinstance(manifest, dict) and isinstance(manifest.get("capabilities"), list):
        return manifest
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("inventory must be a capability list or a manifest capability array")
    evidence_by_path: dict[str, list[dict[str, object]]] = {}
    for evidence in pack.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        path = evidence.get("path")
        if not isinstance(path, str) or not path:
            continue
        evidence_by_path.setdefault(path, []).append(evidence)
    capabilities: list[dict[str, object]] = []
    for raw_item in manifest:
        if not isinstance(raw_item, dict):
            raise ValueError("inventory manifest entries must be objects")
        item_id = raw_item.get("id")
        title = raw_item.get("title")
        user_action = raw_item.get("user_action")
        mechanism_question = raw_item.get("mechanism_question")
        distinguish = raw_item.get("distinguish")
        source_refs = raw_item.get("source_refs")
        coverage_notes = raw_item.get("coverage_notes")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (item_id, title, user_action, mechanism_question, distinguish)
        ):
            raise ValueError("inventory manifest entry is missing required text fields")
        if not isinstance(source_refs, list) or len(source_refs) < 3:
            raise ValueError(
                f"inventory manifest entry requires at least three source_refs: {item_id}"
            )
        normalized_refs: list[dict[str, object]] = []
        matched_evidence_ids: list[str] = []
        for source_ref in source_refs:
            if not isinstance(source_ref, dict):
                raise ValueError(f"inventory manifest source_ref must be an object: {item_id}")
            path = source_ref.get("path")
            line_start = source_ref.get("line_start")
            line_end = source_ref.get("line_end")
            claim = source_ref.get("claim")
            if (
                not isinstance(path, str)
                or not path
                or not isinstance(line_start, int)
                or not isinstance(line_end, int)
                or line_start < 1
                or line_end < line_start
                or not isinstance(claim, str)
                or not claim.strip()
            ):
                raise ValueError(f"inventory manifest source_ref is invalid: {item_id}")
            normalized_ref = {
                "path": path,
                "line_start": line_start,
                "line_end": line_end,
                "claim": claim.strip(),
            }
            normalized_refs.append(normalized_ref)
            for evidence in evidence_by_path.get(path, []):
                evidence_id = evidence.get("id")
                evidence_start = evidence.get("line_start")
                evidence_end = evidence.get("line_end")
                if (
                    isinstance(evidence_id, str)
                    and isinstance(evidence_start, int)
                    and isinstance(evidence_end, int)
                    and _ranges_overlap(line_start, line_end, evidence_start, evidence_end)
                    and evidence_id not in matched_evidence_ids
                ):
                    matched_evidence_ids.append(evidence_id)
        if not matched_evidence_ids:
            raise ValueError(
                f"inventory manifest could not map to canonical evidence: {item_id}"
            )
        matched_feature_ids: list[str] = []
        for feature in pack.get("feature_hints", []):
            if not isinstance(feature, dict):
                continue
            feature_id = feature.get("id")
            if not isinstance(feature_id, str) or not feature_id:
                continue
            feature_evidence = feature.get("evidence_ids")
            if isinstance(feature_evidence, list) and any(
                isinstance(evidence_id, str) and evidence_id in matched_evidence_ids
                for evidence_id in feature_evidence
            ):
                if feature_id not in matched_feature_ids:
                    matched_feature_ids.append(feature_id)
                continue
            for step in feature.get("steps", []):
                if not isinstance(step, dict):
                    continue
                step_path = step.get("path")
                step_start = step.get("line_start")
                step_end = step.get("line_end")
                for source_ref in normalized_refs:
                    if (
                        step_path == source_ref["path"]
                        and isinstance(step_start, int)
                        and isinstance(step_end, int)
                        and _ranges_overlap(
                            int(source_ref["line_start"]),
                            int(source_ref["line_end"]),
                            step_start,
                            step_end,
                        )
                    ):
                        if feature_id not in matched_feature_ids:
                            matched_feature_ids.append(feature_id)
                        break
                if feature_id in matched_feature_ids:
                    break
        if not matched_feature_ids:
            raise ValueError(
                f"inventory manifest could not map to canonical features: {item_id}"
            )
        distinguish_text = distinguish.strip()
        if isinstance(coverage_notes, str) and coverage_notes.strip():
            distinguish_text = f"{distinguish_text} 审计覆盖：{coverage_notes.strip()}"
        summary = user_action.strip()
        capabilities.append(
            {
                "id": item_id.strip(),
                "title": title.strip(),
                "summary": summary,
                "mechanism": "source-audited-capability",
                "question": mechanism_question.strip(),
                "use_when": f"当你要判断“{title.strip()}”这项能力是否值得复用时。",
                "distinguish": distinguish_text,
                "plain_summary": (
                    f"{summary} 这是一项已由源码切片审计过的独立能力，不是入口函数或页面名。"
                ),
                "source_feature_ids": matched_feature_ids,
                "evidence_ids": matched_evidence_ids,
                "source_refs": normalized_refs,
            }
        )
    return {"capabilities": capabilities}

def _source_locations(value: object) -> dict[str, list[tuple[int, int]]]:
    result: dict[str, list[tuple[int, int]]] = {}

    def add(path: object, start: object, end: object) -> None:
        if not isinstance(path, str) or not _repo_path_parts(path):
            return
        if not isinstance(start, int) or start < 1:
            return
        resolved_end = end if isinstance(end, int) and end >= start else start
        result.setdefault(path, []).append((start, resolved_end))

    def visit(item: object) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        add(
            item.get("path"),
            item.get("line_start", item.get("line")),
            item.get("line_end", item.get("end_line")),
        )
        add(item.get("source_path"), item.get("source_line"), item.get("source_line"))
        add(item.get("target_path"), item.get("target_line"), item.get("target_line"))
        for child in item.values():
            if isinstance(child, (dict, list)):
                visit(child)

    visit(value)
    return result

def _attach_source_excerpts(
    packet: dict[str, object],
    source: Path,
    *,
    character_budget: int = 240_000,
) -> dict[str, object]:
    enriched = copy.deepcopy(packet)
    locations = _source_locations(packet)
    allowed_paths = set(
        packet.get("scope", {}).get("allowed_source_paths", [])
        if isinstance(packet.get("scope"), dict)
        else []
    )
    excerpts: list[dict[str, object]] = []
    used = 0
    source_root = source.resolve()
    for path in sorted(locations):
        if path not in allowed_paths:
            continue
        parts = _repo_path_parts(path)
        if not parts:
            continue
        candidate = source_root.joinpath(*parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(source_root)
            if not resolved.is_file():
                continue
            lines = resolved.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        ranges = sorted(
            {
                (
                    max(1, start - 8),
                    min(len(lines), max(end, start) + 12, start + 159),
                )
                for start, end in locations[path]
                if start <= len(lines)
            }
        )
        merged: list[tuple[int, int]] = []
        for start, end in ranges:
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        for start, end in merged[:6]:
            content = "\n".join(
                f"{line_number:>6}  {lines[line_number - 1]}"
                for line_number in range(start, end + 1)
            )
            if used + len(content) > character_budget:
                break
            excerpts.append(
                {
                    "path": path,
                    "line_start": start,
                    "line_end": end,
                    "content": content,
                }
            )
            used += len(content)
        if used >= character_budget:
            break
    enriched["source_excerpts"] = excerpts
    scope = enriched.get("scope")
    if isinstance(scope, dict):
        scope["source_excerpt_count"] = len(excerpts)
        scope["source_excerpt_characters"] = used
        scope["source_excerpt_truncated"] = used >= character_budget
    return enriched

def _normalize_project_overview(
    payload: dict[str, object],
    packet: dict[str, object],
    capabilities: Sequence[dict[str, object]],
    source: Path,
) -> dict[str, object]:
    overview = payload.get("project_overview")
    if not isinstance(overview, dict):
        raise ValueError("project overview is missing")
    expected_ids = [
        str(item["id"])
        for item in capabilities
        if isinstance(item.get("id"), str) and item.get("id")
    ]
    order = overview.get("capability_order")
    if (
        not isinstance(order, list)
        or any(not isinstance(item, str) for item in order)
        or len(order) != len(expected_ids)
        or len(set(order)) != len(order)
        or set(order) != set(expected_ids)
    ):
        raise ValueError("project overview capability_order must be an exact permutation")
    scope = packet.get("scope")
    allowed_paths = set(
        scope.get("allowed_source_paths", [])
        if isinstance(scope, dict) and isinstance(scope.get("allowed_source_paths"), list)
        else []
    )
    source_root = source.resolve()

    def normalize_refs(owner: dict[str, object], field: str, *, minimum: int) -> None:
        refs = owner.get("source_refs")
        if not isinstance(refs, list) or len(refs) < minimum:
            raise ValueError(f"project overview {field} requires source_refs")
        for ref in refs:
            if not isinstance(ref, dict):
                raise ValueError(f"project overview {field} has invalid source_ref")
            path = ref.get("path")
            line_start = ref.get("line_start")
            line_end = ref.get("line_end")
            claim = ref.get("claim")
            if (
                not isinstance(path, str)
                or path not in allowed_paths
                or not isinstance(line_start, int)
                or not isinstance(line_end, int)
                or line_start < 1
                or line_end < line_start
                or not isinstance(claim, str)
                or not claim.strip()
            ):
                raise ValueError(f"project overview {field} escaped source scope")
            candidate = source_root.joinpath(*_repo_path_parts(path))
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(source_root)
                line_count = len(resolved.read_text(encoding="utf-8").splitlines())
            except (FileNotFoundError, OSError, UnicodeDecodeError, ValueError) as error:
                raise ValueError(
                    f"project overview {field} references unreadable source: {path}"
                ) from error
            if line_count < 1:
                raise ValueError(f"project overview {field} references empty source: {path}")
            ref["line_start"] = min(line_start, line_count)
            ref["line_end"] = min(max(int(ref["line_start"]), line_end), line_count)
            ref["claim"] = claim.strip()

    normalize_refs(overview, "project", minimum=3)
    axes = overview.get("core_product_axes")
    if not isinstance(axes, list) or not 1 <= len(axes) <= 4:
        raise ValueError("project overview requires one to four core product axes")
    supporting = overview.get("supporting_capability_ids")
    if not isinstance(supporting, list) or any(
        not isinstance(item, str) or item not in expected_ids for item in supporting
    ):
        raise ValueError("project overview supporting capability ids are invalid")
    supporting_set = set(supporting)
    # Structured-output models sometimes repeat the complete supporting bucket as
    # a final "product axis" even though the same IDs are correctly listed as
    # supporting.  The duplicated axis carries no additional classification: drop
    # only that exact, all-supporting bucket.  Mixed overlap remains an error.
    axes = [
        axis
        for axis in axes
        if not (
            isinstance(axis, dict)
            and isinstance(axis.get("capability_ids"), list)
            and axis.get("capability_ids")
            and set(axis["capability_ids"]).issubset(supporting_set)
        )
    ]
    if not axes:
        raise ValueError("project overview requires at least one core product axis")
    overview["core_product_axes"] = axes
    assigned_ids: list[str] = []
    axis_ids: set[str] = set()
    for position, axis in enumerate(axes, start=1):
        if not isinstance(axis, dict):
            raise ValueError("project overview product axis is invalid")
        axis_id = axis.get("id")
        member_ids = axis.get("capability_ids")
        if not isinstance(axis_id, str) or not axis_id or axis_id in axis_ids:
            raise ValueError("project overview product axis ids must be unique")
        if not isinstance(member_ids, list) or not member_ids or any(
            not isinstance(item, str) or item not in expected_ids for item in member_ids
        ):
            raise ValueError("project overview product axis has invalid capability ids")
        axis_ids.add(axis_id)
        assigned_ids.extend(member_ids)
        normalize_refs(axis, f"core_product_axes[{position}]", minimum=1)
    if len(set(assigned_ids)) != len(assigned_ids):
        raise ValueError("project overview assigns a capability to multiple product axes")
    if set(assigned_ids) & set(supporting):
        raise ValueError("project overview core and supporting capabilities overlap")
    if set(assigned_ids) | set(supporting) != set(expected_ids):
        raise ValueError("project overview capability hierarchy must cover every capability")
    # The hierarchy is the reader's table of contents.  Make it authoritative so
    # model-provided order cannot interleave supporting mechanics with the core
    # product journey.
    canonical_order = list(dict.fromkeys(assigned_ids + list(supporting)))
    canonical_order.extend(
        identifier for identifier in expected_ids if identifier not in canonical_order
    )
    overview["capability_order"] = canonical_order
    engineering_structure = overview.get("engineering_structure")
    if not isinstance(engineering_structure, dict):
        raise ValueError("project overview engineering_structure is missing")
    normalize_refs(engineering_structure, "engineering_structure", minimum=1)
    for field in ("runtime_components", "code_organization"):
        items = overview.get(field)
        if not isinstance(items, list) or len(items) < 2:
            raise ValueError(f"project overview {field} is incomplete")
        for position, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"project overview {field} item is invalid")
            if field == "code_organization":
                directory = item.get("path")
                parts = _repo_path_parts(directory)
                if not parts or not any(
                    _path_is_within_modules(path, [str(directory)])
                    for path in allowed_paths
                ):
                    raise ValueError(
                        f"project overview code directory is outside source scope: {directory}"
                    )
            normalize_refs(item, f"{field}[{position}]", minimum=1)
    return copy.deepcopy(overview)
