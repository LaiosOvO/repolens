"""Capability inventory normalization, scope closure and merge contracts."""

from __future__ import annotations

import copy
import json
from typing import Sequence

from .evidence_packets import (
    _build_module_views,
    _compact_global_graph_context,
    _source_paths,
)
from .paths import path_is_within_modules as _path_is_within_modules
from .paths import repo_path_parts as _repo_path_parts
from .paths import canonical_source_slice_path as _canonical_source_slice_path
from .report_contracts import _ranges_overlap

def _require_inventory_scope(
    payload: dict[str, object],
    packet: dict[str, object],
) -> None:
    scope = packet.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("inventory packet has no scope")
    allowed_paths = set(scope.get("allowed_source_paths", []))
    allowed_features = set(scope.get("feature_ids", []))
    allowed_evidence = set(scope.get("evidence_ids", []))
    allowed_modules = set(scope.get("module_paths", []))
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("Codex inventory did not produce capabilities")
    capability_ids = {
        str(item.get("id"))
        for item in capabilities
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    implementation_memberships: set[tuple[str, str]] = set()
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ValueError("Codex inventory produced a non-object capability")
        capability_id = str(capability.get("id") or "unknown")
        source_feature_ids = capability.get("source_feature_ids", [])
        evidence_ids = capability.get("evidence_ids", [])
        source_refs = capability.get("source_refs", [])
        if not isinstance(source_feature_ids, list) or not set(source_feature_ids) <= allowed_features:
            raise ValueError(f"Codex inventory escaped feature scope: {capability_id}")
        if not isinstance(evidence_ids, list) or not set(evidence_ids) <= allowed_evidence:
            raise ValueError(f"Codex inventory escaped evidence scope: {capability_id}")
        if not isinstance(source_refs, list):
            raise ValueError(f"Codex inventory has invalid source refs: {capability_id}")
        escaped_paths = sorted(
            {
                str(item.get("path") or "<missing>")
                for item in source_refs
                if not isinstance(item, dict) or item.get("path") not in allowed_paths
            }
        )
        if escaped_paths:
            raise ValueError(
                f"Codex inventory escaped source scope: {capability_id}: {escaped_paths[0]}"
            )
        implementation_modules = capability.get("implementation_modules")
        if implementation_modules is not None:
            if not isinstance(implementation_modules, list) or not implementation_modules:
                raise ValueError(
                    f"Codex inventory has no implementation modules: {capability_id}"
                )
            for module in implementation_modules:
                if not isinstance(module, dict):
                    raise ValueError(
                        f"Codex inventory has invalid implementation module: {capability_id}"
                    )
                path = module.get("path")
                if path not in allowed_modules:
                    raise ValueError(
                        f"Codex inventory escaped module scope: {capability_id}: {path}"
                    )
                if module.get("classification") not in {"core", "supporting"}:
                    raise ValueError(
                        f"Codex inventory has invalid module classification: {capability_id}"
                    )
                implementation_memberships.add((str(path), capability_id))

    if not scope.get("require_module_coverage"):
        return
    required_product_modules = {
        path
        for path in scope.get("required_product_module_paths", [])
        if isinstance(path, str)
    }
    dispositions = payload.get("module_dispositions")
    if not isinstance(dispositions, list):
        raise ValueError("Codex inventory omitted module dispositions")
    disposition_by_path: dict[str, dict[str, object]] = {}
    disposition_memberships: set[tuple[str, str]] = set()
    for disposition in dispositions:
        if not isinstance(disposition, dict):
            raise ValueError("Codex inventory has an invalid module disposition")
        path = disposition.get("path")
        status = disposition.get("disposition")
        members = disposition.get("capability_ids")
        reason = disposition.get("reason")
        if (
            not isinstance(path, str)
            or path not in required_product_modules
            or path in disposition_by_path
        ):
            raise ValueError("Codex inventory has an invalid module disposition path")
        if status not in {"core-capability", "supporting", "excluded"}:
            raise ValueError("Codex inventory has an invalid module disposition status")
        if (
            not isinstance(members, list)
            or any(not isinstance(item, str) or item not in capability_ids for item in members)
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise ValueError("Codex inventory has an invalid module disposition closure")
        if status == "core-capability" and not members:
            raise ValueError("Codex inventory left a core module without a capability")
        disposition_by_path[path] = disposition
        disposition_memberships.update((path, member) for member in members)
    missing = sorted(required_product_modules - set(disposition_by_path))
    if missing:
        raise ValueError(
            f"Codex inventory left unreviewed product modules: {missing[0]}"
        )
    if set(disposition_by_path) - required_product_modules:
        raise ValueError("Codex inventory reviewed modules outside the product scope")
    missing_memberships = sorted(
        membership
        for membership in implementation_memberships - disposition_memberships
        if membership[0] in required_product_modules
    )
    if missing_memberships:
        path, capability_id = missing_memberships[0]
        raise ValueError(
            "Codex inventory module disposition does not reference capability: "
            f"{path}: {capability_id}"
        )

def _canonicalize_inventory_payload(
    payload: dict[str, object], packet: dict[str, object]
) -> dict[str, object]:
    normalized = copy.deepcopy(payload)
    evidence_by_path: dict[str, list[dict[str, object]]] = {}
    for evidence in packet.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        path = evidence.get("path")
        if isinstance(path, str):
            evidence_by_path.setdefault(path, []).append(evidence)
    hints = [
        item for item in packet.get("feature_hints", []) if isinstance(item, dict)
    ]
    # CodeGraph relationships are canonical facts too. A business capability
    # may cite a downstream implementation node that is not repeated in its
    # structural entry hint, so derive feature ownership from graph slices and
    # candidates before deciding that the capability is ungrounded.
    graph_feature_paths: dict[str, set[str]] = {}
    capability_graph = packet.get("capability_graph")
    if isinstance(capability_graph, dict):
        for key in ("feature_slices", "capability_candidates"):
            for graph_item in capability_graph.get(key, []):
                if not isinstance(graph_item, dict):
                    continue
                feature_ids = [
                    value
                    for value in [
                        graph_item.get("feature_id"),
                        *(
                            graph_item.get("source_feature_ids", [])
                            if isinstance(graph_item.get("source_feature_ids"), list)
                            else []
                        ),
                    ]
                    if isinstance(value, str) and value
                ]
                paths = _source_paths(graph_item)
                for feature_id in feature_ids:
                    graph_feature_paths.setdefault(feature_id, set()).update(paths)
    capabilities = normalized.get("capabilities")
    if not isinstance(capabilities, list):
        return normalized
    scope = packet.get("scope")
    allowed_paths = set(
        scope.get("allowed_source_paths", [])
        if isinstance(scope, dict)
        else _source_paths(packet)
    )
    allowed_module_paths = {
        value
        for value in (
            scope.get("module_paths", []) if isinstance(scope, dict) else []
        )
        if isinstance(value, str)
    }
    if not allowed_module_paths:
        module_views, _ = _build_module_views(
            packet, _compact_global_graph_context(packet.get("capability_graph"))
        )
        allowed_module_paths = {
            str(item["path"])
            for item in module_views
            if isinstance(item.get("path"), str)
        }
    accepted: list[dict[str, object]] = []
    rejected_examples: list[str] = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        refs = [
            item
            for item in capability.get("source_refs", [])
            if isinstance(item, dict)
        ]
        for source_ref in refs:
            canonical_path = _canonical_source_slice_path(
                source_ref.get("path"), allowed_paths
            )
            if canonical_path is not None:
                source_ref["path"] = canonical_path
        if not refs or any(item.get("path") not in allowed_paths for item in refs):
            rejected_examples.append(
                f"{capability.get('id') or 'unknown'}:"
                f"{next((item.get('path') for item in refs if item.get('path') not in allowed_paths), '<none>')}"
            )
            continue
        matched_evidence: list[str] = []
        for source_ref in refs:
            path = source_ref.get("path")
            start = source_ref.get("line_start")
            end = source_ref.get("line_end")
            if not isinstance(path, str) or not isinstance(start, int) or not isinstance(end, int):
                continue
            for evidence in evidence_by_path.get(path, []):
                evidence_id = evidence.get("id")
                evidence_start = evidence.get("line_start")
                evidence_end = evidence.get("line_end")
                if (
                    isinstance(evidence_id, str)
                    and isinstance(evidence_start, int)
                    and isinstance(evidence_end, int)
                    and (
                        _ranges_overlap(start, end, evidence_start, evidence_end)
                        or evidence.get("kind") == "graph-navigation-slice"
                    )
                    and evidence_id not in matched_evidence
                ):
                    matched_evidence.append(evidence_id)
        matched_features: list[str] = []
        for hint in hints:
            hint_id = hint.get("id")
            if not isinstance(hint_id, str):
                continue
            hint_evidence = {
                identifier
                for identifier in hint.get("evidence_ids", [])
                if isinstance(identifier, str)
            }
            if hint_evidence & set(matched_evidence):
                matched_features.append(hint_id)
                continue
            hint_paths = _source_paths(hint)
            if any(source_ref.get("path") in hint_paths for source_ref in refs):
                matched_features.append(hint_id)
                continue
            graph_paths = graph_feature_paths.get(hint_id, set())
            if any(source_ref.get("path") in graph_paths for source_ref in refs):
                matched_features.append(hint_id)
        if not matched_evidence and matched_features:
            matched_feature_set = set(matched_features)
            matched_evidence.extend(
                identifier
                for hint in hints
                if hint.get("id") in matched_feature_set
                for identifier in hint.get("evidence_ids", [])
                if isinstance(identifier, str)
            )
        if not matched_evidence or not matched_features:
            rejected_examples.append(
                f"{capability.get('id') or 'unknown'}:no-canonical-anchor"
            )
            continue
        raw_modules = capability.get("implementation_modules")
        if isinstance(raw_modules, list):
            normalized_modules: dict[str, dict[str, object]] = {}
            for module in raw_modules:
                if not isinstance(module, dict):
                    continue
                raw_path = module.get("path")
                if not isinstance(raw_path, str):
                    continue
                resolved_path = raw_path if raw_path in allowed_module_paths else None
                if resolved_path is None:
                    candidates = [
                        module_path
                        for module_path in allowed_module_paths
                        if _path_is_within_modules(raw_path, [module_path])
                    ]
                    if candidates:
                        resolved_path = max(
                            candidates, key=lambda value: len(_repo_path_parts(value))
                        )
                if resolved_path is None:
                    continue
                normalized_module = copy.deepcopy(module)
                normalized_module["path"] = resolved_path
                existing = normalized_modules.get(resolved_path)
                if existing is None:
                    normalized_modules[resolved_path] = normalized_module
                    continue
                for field in ("responsibility", "handoff"):
                    old = str(existing.get(field) or "").strip()
                    new = str(normalized_module.get(field) or "").strip()
                    if new and new not in old:
                        existing[field] = f"{old}；{new}" if old else new
                if module.get("classification") == "core":
                    existing["classification"] = "core"
            capability["implementation_modules"] = list(normalized_modules.values())
        capability["evidence_ids"] = matched_evidence
        capability["source_feature_ids"] = list(dict.fromkeys(matched_features))
        accepted.append(capability)
    if not accepted:
        detail = rejected_examples[0] if rejected_examples else "no-capabilities"
        raise ValueError(
            f"inventory produced no capability with canonical source closure ({detail})"
        )
    dispositions = normalized.get("module_dispositions")
    if isinstance(dispositions, list):
        accepted_capability_ids = {
            str(item["id"])
            for item in accepted
            if isinstance(item.get("id"), str) and item.get("id")
        }
        disposition_by_path: dict[str, dict[str, object]] = {}
        disposition_rank = {"excluded": 0, "supporting": 1, "core-capability": 2}
        for item in dispositions:
            if not isinstance(item, dict):
                continue
            raw_path = item.get("path")
            if not isinstance(raw_path, str):
                continue
            resolved_path = raw_path if raw_path in allowed_module_paths else None
            if resolved_path is None:
                candidates = [
                    module_path
                    for module_path in allowed_module_paths
                    if _path_is_within_modules(raw_path, [module_path])
                ]
                if candidates:
                    resolved_path = max(
                        candidates, key=lambda value: len(_repo_path_parts(value))
                    )
            if resolved_path is None:
                continue
            copied = copy.deepcopy(item)
            copied["path"] = resolved_path
            raw_members = copied.get("capability_ids")
            copied["capability_ids"] = [
                member
                for member in (raw_members if isinstance(raw_members, list) else [])
                if isinstance(member, str) and member in accepted_capability_ids
            ]
            if (
                copied.get("disposition") == "core-capability"
                and not copied["capability_ids"]
            ):
                copied["disposition"] = "supporting"
                reason = str(copied.get("reason") or "").strip()
                copied["reason"] = (
                    f"{reason}；没有独立通过源码证据闭包的产品能力，保留为支撑模块。"
                    if reason
                    else "没有独立通过源码证据闭包的产品能力，保留为支撑模块。"
                )
            existing = disposition_by_path.get(resolved_path)
            if existing is None:
                disposition_by_path[resolved_path] = copied
                continue
            old_status = str(existing.get("disposition") or "excluded")
            new_status = str(copied.get("disposition") or "excluded")
            if disposition_rank.get(new_status, -1) > disposition_rank.get(
                old_status, -1
            ):
                existing["disposition"] = new_status
            existing_members = existing.get("capability_ids")
            new_members = copied.get("capability_ids")
            if isinstance(existing_members, list) and isinstance(new_members, list):
                existing["capability_ids"] = list(
                    dict.fromkeys([*existing_members, *new_members])
                )
            old_reason = str(existing.get("reason") or "").strip()
            new_reason = str(copied.get("reason") or "").strip()
            if new_reason and new_reason not in old_reason:
                existing["reason"] = (
                    f"{old_reason}；{new_reason}" if old_reason else new_reason
                )
        normalized["module_dispositions"] = [
            disposition_by_path[path]
            for path in sorted(disposition_by_path)
        ]
        for capability in accepted:
            capability_id = capability.get("id")
            if not isinstance(capability_id, str):
                continue
            for module in capability.get("implementation_modules", []):
                if not isinstance(module, dict):
                    continue
                disposition = disposition_by_path.get(module.get("path"))
                if not isinstance(disposition, dict):
                    continue
                members = disposition.get("capability_ids")
                if (
                    isinstance(members, list)
                    and capability_id not in members
                    and disposition.get("disposition") != "excluded"
                ):
                    members.append(capability_id)
    normalized["capabilities"] = accepted
    return normalized

def _require_inventory_against_pack(
    payload: dict[str, object], pack: dict[str, object]
) -> None:
    module_views, _ = _build_module_views(
        pack, _compact_global_graph_context(pack.get("capability_graph"))
    )
    module_paths = [
        item.get("path")
        for item in module_views
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and item.get("path") != "."
    ]
    require_module_coverage = isinstance(payload.get("module_dispositions"), list)
    packet = {
        "scope": {
            "allowed_source_paths": sorted(_source_paths(pack)),
            "module_paths": module_paths,
            "required_product_module_paths": [
                str(item["path"])
                for item in module_views
                if item.get("category") == "product-implementation"
            ],
            "require_module_coverage": require_module_coverage,
            "feature_ids": [
                item.get("id")
                for item in pack.get("feature_hints", [])
                if isinstance(item, dict) and item.get("id")
            ],
            "evidence_ids": [
                item.get("id")
                for item in pack.get("evidence", [])
                if isinstance(item, dict) and item.get("id")
            ],
        }
    }
    _require_inventory_scope(payload, packet)

def _inventory_module_shards(
    pack: dict[str, object], *, max_shards: int = 6
) -> list[list[str]]:
    """Partition product topology into a small number of business-domain reads.

    The old symbol-count partition could create 32 tiny model calls and taught
    each call to mistake a folder for a feature.  The report pipeline instead
    groups graph-derived module views by their product root, then balances at
    most ``max_shards`` domain bundles.  Modules remain evidence boundaries;
    the later global grouping pass is the only place that decides final user
    capabilities.
    """

    graph = _compact_global_graph_context(pack.get("capability_graph"))
    module_views, _ = _build_module_views(pack, graph)
    product_modules = [
        item
        for item in module_views
        if item.get("category") == "product-implementation"
        and isinstance(item.get("path"), str)
        and item.get("path") != "."
    ]
    if not product_modules:
        return []

    domain_modules: dict[str, list[dict[str, object]]] = {}
    for module in product_modules:
        path = str(module["path"])
        parts = _repo_path_parts(path)
        if not parts:
            continue
        domain = (
            "/".join(parts[:2])
            if parts[0].casefold() in {"apps", "packages", "services"}
            and len(parts) > 1
            else parts[0]
        )
        domain_modules.setdefault(domain, []).append(module)

    domain_units = [
        (
            domain,
            sorted(str(item["path"]) for item in modules),
            sum(max(1, int(item.get("file_count") or 1)) for item in modules),
        )
        for domain, modules in domain_modules.items()
    ]
    domain_units.sort(key=lambda item: item[0])
    if len(domain_units) <= max_shards:
        return [paths for _, paths, _ in domain_units]

    shard_count = max(1, min(max_shards, len(domain_units)))
    shards: list[list[str]] = [[] for _ in range(shard_count)]
    shard_weights = [0 for _ in range(shard_count)]
    for _, paths, weight in sorted(
        domain_units, key=lambda item: (-item[2], item[0])
    ):
        shard_index = min(
            range(shard_count), key=lambda index: (shard_weights[index], index)
        )
        shards[shard_index].extend(paths)
        shard_weights[shard_index] += weight
    return [sorted(shard) for shard in shards if shard]

def _merge_inventory_shards(
    shard_results: Sequence[tuple[str, dict[str, object]]],
) -> dict[str, object]:
    """Join domain inventories without allowing local IDs to collide."""

    capabilities: list[dict[str, object]] = []
    dispositions: list[dict[str, object]] = []
    for shard_label, payload in shard_results:
        id_map: dict[str, str] = {}
        raw_capabilities = payload.get("capabilities")
        if not isinstance(raw_capabilities, list):
            raise ValueError("inventory shard omitted capabilities")
        for item in raw_capabilities:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ValueError("inventory shard produced an invalid capability")
            old_id = str(item["id"])
            new_id = f"{shard_label}--{old_id}"
            if old_id in id_map:
                previous = next(
                    (
                        capability
                        for capability in capabilities
                        if capability.get("id") == new_id
                    ),
                    None,
                )
                candidate = copy.deepcopy(item)
                candidate["id"] = new_id
                if previous is None or json.dumps(
                    previous, ensure_ascii=False, sort_keys=True
                ) != json.dumps(candidate, ensure_ascii=False, sort_keys=True):
                    raise ValueError(
                        "inventory shard produced conflicting duplicate capability ids"
                    )
                # Structured providers occasionally repeat one byte-identical
                # object.  Repetition adds no semantics, and its existing ID
                # still closes every module disposition, so collapse it before
                # the cross-shard namespace is applied.
                continue
            id_map[old_id] = new_id
            copied = copy.deepcopy(item)
            copied["id"] = new_id
            capabilities.append(copied)
        raw_dispositions = payload.get("module_dispositions")
        if not isinstance(raw_dispositions, list):
            raise ValueError("inventory shard omitted module dispositions")
        for item in raw_dispositions:
            if not isinstance(item, dict):
                raise ValueError("inventory shard produced an invalid disposition")
            copied = copy.deepcopy(item)
            members = copied.get("capability_ids")
            if not isinstance(members, list) or any(
                not isinstance(member, str) or member not in id_map
                for member in members
            ):
                raise ValueError("inventory shard disposition escaped its capability set")
            copied["capability_ids"] = [id_map[member] for member in members]
            dispositions.append(copied)
    if not capabilities:
        raise ValueError("business-domain inventory produced no capabilities")
    consolidated: dict[str, dict[str, object]] = {}
    priority = {"excluded": 0, "supporting": 1, "core-capability": 2}
    for item in dispositions:
        path = item.get("path")
        kind = item.get("disposition")
        members = item.get("capability_ids")
        reason = item.get("reason")
        if (
            not isinstance(path, str)
            or kind not in priority
            or not isinstance(members, list)
            or not isinstance(reason, str)
        ):
            raise ValueError("inventory shard produced an invalid disposition")
        existing = consolidated.get(path)
        if existing is None:
            consolidated[path] = copy.deepcopy(item)
            continue
        existing_members = existing.get("capability_ids")
        assert isinstance(existing_members, list)
        existing["capability_ids"] = list(
            dict.fromkeys([*existing_members, *members])
        )
        existing_kind = str(existing.get("disposition") or "excluded")
        if priority[str(kind)] > priority[existing_kind]:
            existing["disposition"] = kind
        reasons = [part for part in str(existing.get("reason") or "").split("；") if part]
        if reason not in reasons:
            reasons.append(reason)
        existing["reason"] = "；".join(reasons)
    return {
        "capabilities": capabilities,
        "module_dispositions": [consolidated[path] for path in sorted(consolidated)],
    }
