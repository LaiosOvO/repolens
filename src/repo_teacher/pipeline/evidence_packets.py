"""Deterministic evidence-packet and source-slice construction stages."""

from __future__ import annotations

import copy
import hashlib
import os
import stat
from pathlib import Path
from typing import Sequence

from .module_scope import module_view_category as _module_view_category
from .module_scope import module_view_path as _module_view_path
from .paths import path_is_within_modules as _path_is_within_modules
from .paths import repo_path_parts as _repo_path_parts
from .serialization import json_artifact as _json_artifact
from .codegraph import filter_codegraph_context

def _source_paths(value: object) -> set[str]:
    paths: set[str] = set()
    if isinstance(value, list):
        for item in value:
            paths.update(_source_paths(item))
        return paths
    if not isinstance(value, dict):
        return paths
    for key, item in value.items():
        if key in {"path", "source_path", "target_path"} and isinstance(item, str):
            if _repo_path_parts(item):
                paths.add(item)
            continue
        if isinstance(item, (dict, list)):
            paths.update(_source_paths(item))
    return paths

def _feature_ids(value: object) -> set[str]:
    if not isinstance(value, dict):
        return set()
    result: set[str] = set()
    feature_id = value.get("feature_id")
    if isinstance(feature_id, str) and feature_id:
        result.add(feature_id)
    source_feature_ids = value.get("source_feature_ids")
    if isinstance(source_feature_ids, list):
        result.update(
            item for item in source_feature_ids if isinstance(item, str) and item
        )
    return result


def _hint_tags(hint: dict[str, object]) -> set[str]:
    value = hint.get("technology_tags")
    if not isinstance(value, list):
        return set()
    return {
        str(item)
        for item in value
        if isinstance(item, str) and item
    }


def _is_navigation_only_hint(hint: dict[str, object]) -> bool:
    kind = str(hint.get("kind") or "")
    confidence = str(hint.get("confidence") or "")
    tags = _hint_tags(hint)
    return (
        confidence == "graph-navigation-only"
        or kind in {"graph-source-candidate", "graph-mechanism-candidate"}
        or "candidate-only" in tags
    )

def _graph_item_matches_scope(
    item: object,
    *,
    module_paths: Sequence[str],
    selected_feature_ids: set[str],
) -> bool:
    if not isinstance(item, dict):
        return False
    if _feature_ids(item) & selected_feature_ids:
        return True
    return any(
        _path_is_within_modules(path, module_paths)
        for path in _source_paths(item)
    )

def _compact_graph_item(
    item: dict[str, object],
    *,
    node_limit: int = 12,
    edge_limit: int = 16,
) -> dict[str, object]:
    compact = copy.deepcopy(item)
    compact.pop("edge_ids", None)
    for field, limit in (
        ("seed_nodes", 12),
        ("implementation_nodes", node_limit),
        ("central_nodes", 8),
        ("resolved_edges", edge_limit),
        ("component_ids", 8),
    ):
        value = compact.get(field)
        if isinstance(value, list):
            compact[field] = value[:limit]
    return compact

def _compact_graph_candidate(item: dict[str, object]) -> dict[str, object]:
    compact = _compact_graph_item(item, node_limit=8, edge_limit=8)
    if _feature_ids(item):
        compact.pop("implementation_nodes", None)
        compact.pop("resolved_edges", None)
    return compact

def _source_path_priority(path: object) -> tuple[int, str]:
    """Prefer product implementation while retaining examples as usage evidence."""

    parts = tuple(part.casefold() for part in _repo_path_parts(path))
    if not parts:
        return (5, "")
    if any(part in {"test", "tests", "fixtures"} for part in parts):
        return (4, "/".join(parts))
    if any(part in {"docs", "doc", "spec", "specs"} for part in parts):
        return (3, "/".join(parts))
    if any(part in {"example", "examples", "demo", "demos", "sample", "samples"} for part in parts):
        return (2, "/".join(parts))
    if parts[0] in {"src", "lib", "libs", "packages", "apps", "server", "client"}:
        return (0, "/".join(parts))
    return (1, "/".join(parts))

def _compact_global_graph_context(graph: object) -> dict[str, object]:
    """Keep whole-repository topology without forwarding the full graph payload."""

    if not isinstance(graph, dict):
        return {}

    def compact_item(
        item: dict[str, object], *, node_limit: int, edge_limit: int
    ) -> dict[str, object]:
        compact = copy.deepcopy(item)
        compact.pop("edge_ids", None)
        for field, limit in (
            ("seed_nodes", node_limit),
            ("implementation_nodes", node_limit),
            ("central_nodes", node_limit),
        ):
            nodes = item.get(field)
            if isinstance(nodes, list):
                compact[field] = sorted(
                    (node for node in nodes if isinstance(node, dict)),
                    key=lambda node: (
                        _source_path_priority(node.get("path"))[0],
                        -int(node.get("in_degree") or 0),
                        _source_path_priority(node.get("path"))[1],
                        str(node.get("qualified_name") or node.get("name") or ""),
                    ),
                )[:limit]
        edges = item.get("resolved_edges")
        if isinstance(edges, list):
            compact["resolved_edges"] = sorted(
                (edge for edge in edges if isinstance(edge, dict)),
                key=lambda edge: (
                    min(
                        _source_path_priority(edge.get("source_path")),
                        _source_path_priority(edge.get("target_path")),
                    ),
                    str(edge.get("id") or ""),
                ),
            )[:edge_limit]
        components = item.get("component_ids")
        if isinstance(components, list):
            compact["component_ids"] = components[:8]
        return compact

    feature_slices = [
        compact_item(item, node_limit=10, edge_limit=12)
        for item in graph.get("feature_slices", [])
        if isinstance(item, dict)
    ]
    capability_candidates = [
        compact_item(item, node_limit=10, edge_limit=12)
        for item in graph.get("capability_candidates", [])
        if isinstance(item, dict)
    ]
    mechanism_clusters = [
        compact_item(item, node_limit=4, edge_limit=0)
        for item in graph.get("mechanism_clusters", [])
        if isinstance(item, dict)
    ]
    components = [
        compact_item(item, node_limit=3, edge_limit=0)
        for item in graph.get("components", [])
        if isinstance(item, dict)
    ]
    return {
        "schema_version": graph.get("schema_version"),
        "stats": graph.get("stats", {}),
        "feature_slices": feature_slices,
        "capability_candidates": capability_candidates,
        "mechanism_clusters": mechanism_clusters,
        "components": components,
        "module_dependencies": [
            copy.deepcopy(item)
            for item in graph.get("module_dependencies", [])[:512]
            if isinstance(item, dict)
        ],
        "unresolved_edge_examples": [
            copy.deepcopy(item)
            for item in graph.get("unresolved_edge_examples", [])[:80]
            if isinstance(item, dict)
        ],
        "interpretation_contract": graph.get("interpretation_contract", []),
    }

def _build_module_views(
    pack: dict[str, object], graph: dict[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Derive useful folder-level modules without invoking a model per folder."""

    graph_paths = _source_paths(graph)
    all_paths = {
        path
        for hint in pack.get("feature_hints", [])
        if isinstance(hint, dict)
        for path in _source_paths(hint)
    }
    grouped: dict[str, list[str]] = {}
    for path in sorted(all_paths, key=_source_path_priority):
        module_path = _module_view_path(path)
        if module_path is not None:
            grouped.setdefault(module_path, []).append(path)
    module_views: list[dict[str, object]] = []
    for module_path, paths in grouped.items():
        representatives = sorted(
            paths,
            key=lambda path: (
                0 if path in graph_paths else 1,
                _source_path_priority(path),
            ),
        )[:5]
        module_views.append(
            {
                "path": module_path,
                "category": _module_view_category(module_path),
                "file_count": len(paths),
                "representative_paths": representatives,
            }
        )
    module_views.sort(
        key=lambda item: (
            0 if item["category"] == "product-implementation" else 1,
            str(item["path"]),
        )
    )
    module_by_path = {path: _module_view_path(path) for path in all_paths}
    dependency_counts: dict[tuple[str, str, str], int] = {}
    for section in ("feature_slices", "capability_candidates"):
        for item in graph.get(section, []):
            if not isinstance(item, dict):
                continue
            for edge in item.get("resolved_edges", []):
                if not isinstance(edge, dict):
                    continue
                source_module = module_by_path.get(str(edge.get("source_path") or ""))
                target_module = module_by_path.get(str(edge.get("target_path") or ""))
                if not source_module or not target_module or source_module == target_module:
                    continue
                key = (
                    source_module,
                    target_module,
                    str(edge.get("kind") or "relationship"),
                )
                dependency_counts[key] = dependency_counts.get(key, 0) + 1
    dependencies = [
        {"source": source, "target": target, "kind": kind, "count": count}
        for (source, target, kind), count in sorted(
            dependency_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return module_views[:240], dependencies[:512]

def _build_global_business_inventory_pack(
    pack: dict[str, object],
    *,
    hint_limit: int = 320,
    codegraph_context: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build one graph-first packet for global capability decisions.

    Modules remain first-class topology evidence, but model calls are not split
    by module.  This prevents local shards from mistaking routes, helpers, or
    examples for independent product capabilities.
    """

    graph = _compact_global_graph_context(pack.get("capability_graph"))
    module_views, module_view_dependencies = _build_module_views(pack, graph)
    product_modules = [
        item
        for item in module_views
        if item.get("category") == "product-implementation"
    ]
    representative_product_paths = {
        path
        for module in product_modules
        for path in module.get("representative_paths", [])
        if isinstance(path, str)
    }
    graph_paths = _source_paths(graph)
    graph_feature_ids = {
        identifier
        for section in ("feature_slices", "capability_candidates")
        for item in graph.get(section, [])
        if isinstance(item, dict)
        for identifier in _feature_ids(item)
    }
    ranked_primary_hints: list[tuple[tuple[object, ...], dict[str, object]]] = []
    ranked_navigation_hints: list[tuple[tuple[object, ...], dict[str, object]]] = []
    for position, hint in enumerate(pack.get("feature_hints", [])):
        if not isinstance(hint, dict):
            continue
        hint_id = hint.get("id")
        hint_paths = _source_paths(hint)
        covers_product_module = bool(hint_paths & representative_product_paths)
        if (
            not covers_product_module
            and hint_id not in graph_feature_ids
            and not (hint_paths & graph_paths)
        ):
            continue
        best_path = min(
            (_source_path_priority(path) for path in hint_paths),
            default=(5, ""),
        )
        ranked = (
            (
                0
                if covers_product_module
                else 1
                if hint_id in graph_feature_ids
                else 2,
                best_path,
                position,
            ),
            hint,
        )
        if _is_navigation_only_hint(hint):
            ranked_navigation_hints.append(ranked)
        else:
            ranked_primary_hints.append(ranked)
    if not ranked_primary_hints and not ranked_navigation_hints:
        for position, hint in enumerate(pack.get("feature_hints", [])):
            if not isinstance(hint, dict):
                continue
            hint_paths = _source_paths(hint)
            ranked_navigation_hints.append(
                (
                    (
                        2,
                        min(
                            (_source_path_priority(path) for path in hint_paths),
                            default=(5, ""),
                        ),
                        position,
                    ),
                    hint,
                ),
            )
    primary_limit = hint_limit
    navigation_limit = min(24, max(8, hint_limit // 6))
    primary_selected = [
        copy.deepcopy(hint)
        for _, hint in sorted(ranked_primary_hints, key=lambda item: item[0])[:primary_limit]
    ]
    remaining_slots = max(0, hint_limit - len(primary_selected))
    supplemental_limit = min(navigation_limit, remaining_slots)
    supplemental_selected = [
        copy.deepcopy(hint)
        for _, hint in sorted(ranked_navigation_hints, key=lambda item: item[0])[:supplemental_limit]
    ]
    selected_hints = primary_selected + supplemental_selected
    evidence_ids = {
        identifier
        for hint in selected_hints
        for identifier in [
            *(
                hint.get("evidence_ids", [])
                if isinstance(hint.get("evidence_ids"), list)
                else []
            ),
            *(
                evidence_id
                for step in hint.get("steps", [])
                if isinstance(step, dict)
                for evidence_id in (
                    step.get("evidence_ids", [])
                    if isinstance(step.get("evidence_ids"), list)
                    else []
                )
            ),
        ]
        if isinstance(identifier, str)
    }
    selected_evidence = [
        copy.deepcopy(item)
        for item in pack.get("evidence", [])
        if isinstance(item, dict) and item.get("id") in evidence_ids
    ]
    modules = module_views
    module_paths = [str(item["path"]) for item in modules]
    codegraph_context = filter_codegraph_context(
        codegraph_context or {
        "source_paths": [],
        "nodes": [],
        "edges": [],
        },
        module_paths,
    )
    codegraph_paths = {
        path
        for path in codegraph_context.get("source_paths", [])
        if isinstance(path, str) and _repo_path_parts(path)
    }
    allowed_paths = (
        _source_paths(selected_hints)
        | _source_paths(selected_evidence)
        | codegraph_paths
    )
    selected_feature_ids = sorted(
        str(item["id"])
        for item in selected_hints
        if isinstance(item.get("id"), str) and item.get("id")
    )
    return {
        "schema_version": pack.get("schema_version"),
        "project": pack.get("project", {}),
        "instructions": pack.get("instructions", []),
        "required_chapter_sections": pack.get("required_chapter_sections", []),
        "inventory_strategy": {
            "decision_scope": "whole-repository-business-capabilities",
            "graph_first": True,
            "module_role": (
                "Modules are topology and implementation evidence. They do not "
                "independently define user-facing capabilities."
            ),
            "detail_parallelism": (
                "Parallel work starts only after global capability IDs are fixed."
            ),
        },
        "scope": {
            "module_paths": module_paths,
            "required_product_module_paths": [
                str(item["path"]) for item in product_modules
            ],
            "require_module_coverage": True,
            "allowed_source_paths": sorted(allowed_paths),
            "feature_ids": selected_feature_ids,
            "evidence_ids": sorted(
                str(item["id"])
                for item in selected_evidence
                if isinstance(item.get("id"), str) and item.get("id")
            ),
            "capability_candidate_ids": [
                item.get("id")
                for item in graph.get("capability_candidates", [])
                if isinstance(item, dict) and item.get("id")
            ],
            "mechanism_cluster_ids": [
                item.get("id")
                for item in graph.get("mechanism_clusters", [])
                if isinstance(item, dict) and item.get("id")
            ],
            "graph_paths_without_canonical_evidence": len(
                graph_paths - allowed_paths
            ),
            "contract": (
                "Decide capabilities once from the whole graph; use modules to "
                "explain implementation; cite only canonical allowed paths."
            ),
        },
        "capability_graph": graph,
        "codegraph_context": codegraph_context,
        "modules": modules,
        "module_view_dependencies": module_view_dependencies,
        "repository_modules": [
            copy.deepcopy(item)
            for item in pack.get("modules", [])
            if isinstance(item, dict)
        ][:200],
        "reading_path": [
            copy.deepcopy(item)
            for item in pack.get("reading_path", [])
            if isinstance(item, dict) and item.get("path") in allowed_paths
        ],
        "feature_hints": selected_hints,
        "evidence": selected_evidence,
    }

def _module_labels(module_paths: Sequence[str]) -> set[str]:
    labels: set[str] = set()
    for module_path in module_paths:
        parts = _repo_path_parts(module_path)
        if parts:
            labels.add(parts[-1])
            labels.add(parts[0])
    return labels

def _filter_graph_context(
    graph: object,
    *,
    module_paths: Sequence[str],
    selected_feature_ids: set[str],
) -> dict[str, object]:
    if not isinstance(graph, dict):
        return {}
    feature_slices = [
        _compact_graph_item(item)
        for item in graph.get("feature_slices", [])
        if isinstance(item, dict)
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=selected_feature_ids,
        )
    ]
    graph_feature_ids = set(selected_feature_ids)
    for item in feature_slices:
        graph_feature_ids.update(_feature_ids(item))
    capability_candidates = [
        _compact_graph_candidate(item)
        for item in graph.get("capability_candidates", [])
        if isinstance(item, dict)
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=graph_feature_ids,
        )
    ]
    for item in capability_candidates:
        graph_feature_ids.update(_feature_ids(item))
    if graph_feature_ids != selected_feature_ids:
        feature_slices = [
            _compact_graph_item(item)
            for item in graph.get("feature_slices", [])
            if isinstance(item, dict)
            if _graph_item_matches_scope(
                item,
                module_paths=module_paths,
                selected_feature_ids=graph_feature_ids,
            )
        ]
    mechanism_clusters = [
        _compact_graph_item(item)
        for item in graph.get("mechanism_clusters", [])
        if isinstance(item, dict)
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=graph_feature_ids,
        )
    ]
    components = [
        _compact_graph_item(item)
        for item in graph.get("components", [])
        if isinstance(item, dict)
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=graph_feature_ids,
        )
    ]
    labels = _module_labels(module_paths)
    module_dependencies = [
        item
        for item in graph.get("module_dependencies", [])
        if isinstance(item, dict)
        and (
            str(item.get("source") or "") in labels
            or str(item.get("target") or "") in labels
        )
    ]
    unresolved_edges = [
        item
        for item in graph.get("unresolved_edge_examples", [])
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=graph_feature_ids,
        )
    ]
    return {
        "schema_version": graph.get("schema_version"),
        "stats": graph.get("stats", {}),
        "feature_slices": feature_slices,
        "capability_candidates": capability_candidates,
        "mechanism_clusters": mechanism_clusters,
        "components": components,
        "module_dependencies": module_dependencies,
        "unresolved_edge_examples": unresolved_edges,
        "interpretation_contract": graph.get("interpretation_contract", []),
    }

def _build_inventory_shard_pack(
    pack: dict[str, object],
    module_paths: Sequence[str],
    *,
    codegraph_context: dict[str, object] | None = None,
    selection_scope_paths: Sequence[str] | None = None,
) -> dict[str, object]:
    per_module_fallback = 24
    selection_paths = list(selection_scope_paths or module_paths)
    graph_context = _compact_global_graph_context(pack.get("capability_graph"))
    module_views, _ = _build_module_views(pack, graph_context)
    selected_modules = [
        item
        for item in module_views
        if isinstance(item, dict)
        and item.get("path") in module_paths
    ]
    module_hints = [
        item
        for item in pack.get("feature_hints", [])
        if isinstance(item, dict)
        and any(
            _path_is_within_modules(path, selection_paths)
            for path in _source_paths(item)
        )
    ]
    selected_feature_ids = {
        str(item["id"])
        for item in module_hints
        if isinstance(item.get("id"), str) and item.get("id")
    }
    graph = _filter_graph_context(
        pack.get("capability_graph"),
        module_paths=selection_paths,
        selected_feature_ids=selected_feature_ids,
    )
    graph_feature_ids: set[str] = set()
    for section in ("feature_slices", "capability_candidates"):
        for item in graph.get(section, []):
            graph_feature_ids.update(_feature_ids(item))
    graph_paths = _source_paths(graph)
    graph_hints = [
        item
        for item in pack.get("feature_hints", [])
        if isinstance(item, dict)
        and (
            item.get("id") in graph_feature_ids
            or bool(_source_paths(item) & graph_paths)
        )
    ]
    selected_by_id = {
        str(item["id"]): item
        for item in graph_hints
        if isinstance(item.get("id"), str) and item.get("id")
    }
    codegraph_context = filter_codegraph_context(
        codegraph_context
        or {
            "source_paths": [],
            "nodes": [],
            "edges": [],
        },
        selection_paths,
    )
    codegraph_paths = {
        path
        for path in codegraph_context.get("source_paths", [])
        if isinstance(path, str) and _path_is_within_modules(path, selection_paths)
    }
    graph_connected_hints = sorted(
        (
            item
            for item in module_hints
            if _source_paths(item) & codegraph_paths
        ),
        key=lambda item: (
            min(
                (_source_path_priority(path) for path in _source_paths(item)),
                default=(99, ""),
            ),
            str(item.get("id") or ""),
        ),
    )
    for item in graph_connected_hints[:96]:
        identifier = item.get("id")
        if isinstance(identifier, str) and identifier:
            selected_by_id.setdefault(identifier, item)
    for module_path in selection_paths:
        fallback = sorted(
            (
                item
                for item in module_hints
                if any(
                    _path_is_within_modules(path, [module_path])
                    for path in _source_paths(item)
                )
            ),
            key=lambda item: (
                min(
                    (_source_path_priority(path) for path in _source_paths(item)),
                    default=(99, ""),
                ),
                str(item.get("id") or ""),
            ),
        )[:per_module_fallback]
        for item in fallback:
            identifier = item.get("id")
            if isinstance(identifier, str) and identifier:
                selected_by_id.setdefault(identifier, item)
    selected_hints = list(selected_by_id.values())
    evidence_ids = {
        identifier
        for hint in selected_hints
        for identifier in [
            *(hint.get("evidence_ids", []) if isinstance(hint.get("evidence_ids"), list) else []),
            *(
                evidence_id
                for step in hint.get("steps", [])
                if isinstance(step, dict)
                for evidence_id in (
                    step.get("evidence_ids", [])
                    if isinstance(step.get("evidence_ids"), list)
                    else []
                )
            ),
        ]
        if isinstance(identifier, str)
    }
    selected_evidence = [
        item
        for item in pack.get("evidence", [])
        if isinstance(item, dict)
        and item.get("id") in evidence_ids
    ]
    allowed_paths = set()
    for value in (selected_hints, selected_evidence, graph):
        allowed_paths.update(_source_paths(value))
    allowed_paths.update(codegraph_paths)
    selected_reading_path = [
        item
        for item in pack.get("reading_path", [])
        if isinstance(item, dict) and item.get("path") in allowed_paths
    ]
    return {
        "schema_version": pack.get("schema_version"),
        "project": pack.get("project", {}),
        "instructions": pack.get("instructions", []),
        "required_chapter_sections": pack.get("required_chapter_sections", []),
        "scope": {
            "module_paths": list(module_paths),
            "required_product_module_paths": list(module_paths),
            "selection_scope_paths": selection_paths,
            "require_module_coverage": True,
            "allowed_source_paths": sorted(allowed_paths),
            "feature_ids": sorted(
                str(item["id"])
                for item in selected_hints
                if isinstance(item.get("id"), str) and item.get("id")
            ),
            "evidence_ids": sorted(
                str(item["id"])
                for item in selected_evidence
                if isinstance(item.get("id"), str) and item.get("id")
            ),
            "capability_candidate_ids": [
                item.get("id")
                for item in graph.get("capability_candidates", [])
                if isinstance(item, dict) and item.get("id")
            ],
            "resolved_edge_ids": sorted(
                {
                    str(edge["id"])
                    for section in ("feature_slices", "capability_candidates")
                    for item in graph.get(section, [])
                    if isinstance(item, dict)
                    for edge in item.get("resolved_edges", [])
                    if isinstance(edge, dict) and edge.get("id")
                }
            ),
            "selection": {
                "candidate_hints": len(module_hints),
                "selected_hints": len(selected_hints),
                "truncated_hints": max(0, len(module_hints) - len(selected_hints)),
                "per_module_fallback": per_module_fallback,
                "codegraph_required": True,
            },
            "contract": "Only inspect allowed_source_paths; graph candidates are seeds, not final features.",
        },
        "capability_graph": graph,
        "codegraph_context": codegraph_context,
        "modules": selected_modules,
        "reading_path": selected_reading_path,
        "feature_hints": selected_hints,
        "evidence": selected_evidence,
    }

def _build_chapter_batch_pack(
    pack: dict[str, object], capabilities: Sequence[dict[str, object]]
) -> dict[str, object]:
    capability_ids = [
        str(item["id"])
        for item in capabilities
        if isinstance(item.get("id"), str) and item.get("id")
    ]
    feature_ids = {
        identifier
        for item in capabilities
        for identifier in (
            item.get("source_feature_ids", [])
            if isinstance(item.get("source_feature_ids"), list)
            else []
        )
        if isinstance(identifier, str)
    }
    evidence_ids = {
        identifier
        for item in capabilities
        for identifier in (
            item.get("evidence_ids", [])
            if isinstance(item.get("evidence_ids"), list)
            else []
        )
        if isinstance(identifier, str)
    }
    allowed_paths = {
        path
        for item in capabilities
        for source_ref in (
            item.get("source_refs", [])
            if isinstance(item.get("source_refs"), list)
            else []
        )
        if isinstance(source_ref, dict)
        for path in [source_ref.get("path")]
        if isinstance(path, str) and _repo_path_parts(path)
    }
    selected_hints = [
        item
        for item in pack.get("feature_hints", [])
        if isinstance(item, dict) and item.get("id") in feature_ids
    ]
    for hint in selected_hints:
        allowed_paths.update(_source_paths(hint))
        evidence_ids.update(
            identifier
            for identifier in hint.get("evidence_ids", [])
            if isinstance(identifier, str)
        )
    selected_evidence = [
        item
        for item in pack.get("evidence", [])
        if isinstance(item, dict) and item.get("id") in evidence_ids
    ]
    allowed_paths.update(_source_paths(selected_evidence))
    module_paths = sorted(
        {
            str(item.get("path"))
            for item in pack.get("modules", [])
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and any(
                _path_is_within_modules(path, [str(item.get("path"))])
                for path in allowed_paths
            )
        }
    )
    graph = _filter_graph_context(
        pack.get("capability_graph"),
        module_paths=module_paths,
        selected_feature_ids=feature_ids,
    )
    allowed_paths.update(_source_paths(graph))
    return {
        "schema_version": pack.get("schema_version"),
        "project": pack.get("project", {}),
        "instructions": pack.get("instructions", []),
        "required_chapter_sections": pack.get("required_chapter_sections", []),
        "scope": {
            "capability_ids": capability_ids,
            "allowed_source_paths": sorted(allowed_paths),
            "contract": "Explain only selected capabilities from this evidence closure.",
        },
        "capabilities": copy.deepcopy(list(capabilities)),
        "capability_graph": graph,
        "modules": [
            item
            for item in pack.get("modules", [])
            if isinstance(item, dict) and item.get("path") in module_paths
        ],
        "reading_path": [
            item
            for item in pack.get("reading_path", [])
            if isinstance(item, dict) and item.get("path") in allowed_paths
        ],
        "feature_hints": selected_hints,
        "evidence": selected_evidence,
    }

def _add_project_navigation(
    overview_pack: dict[str, object], full_pack: dict[str, object]
) -> dict[str, object]:
    """Add root-level product metadata as positioning-only navigation evidence."""

    enriched = copy.deepcopy(overview_pack)
    preferred_names = {
        "readme",
        "readme.md",
        "readme.rst",
        "readme.txt",
        "agents.md",
        "project.md",
        "architecture.md",
        "pyproject.toml",
        "package.json",
        "go.mod",
        "cargo.toml",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    }
    project = full_pack.get("project")
    project_path = project.get("path") if isinstance(project, dict) else None
    source_root = (
        Path(project_path).resolve()
        if isinstance(project_path, str) and project_path
        else None
    )

    def root_file_snippet(path: str) -> str | None:
        """Read positioning text from the immutable analysis source, not an index label."""

        if source_root is None or not source_root.is_dir():
            return None
        parts = _repo_path_parts(path)
        if len(parts) != 1:
            return None
        candidate = source_root.joinpath(*parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(source_root)
            if not resolved.is_file():
                return None
            with resolved.open("r", encoding="utf-8") as handle:
                snippet = handle.read(12_000)
        except (FileNotFoundError, OSError, UnicodeDecodeError, ValueError):
            return None
        return snippet if snippet.strip() else None

    selected: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for evidence in full_pack.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        path = evidence.get("path")
        if not isinstance(path, str) or path in seen_paths:
            continue
        parts = _repo_path_parts(path)
        if len(parts) != 1 or parts[0].casefold() not in preferred_names:
            continue
        copied = copy.deepcopy(evidence)
        snippet = root_file_snippet(path)
        if snippet is not None:
            copied["snippet"] = snippet
            copied["line_start"] = 1
            copied["line_end"] = max(1, snippet.count("\n") + 1)
            copied["kind"] = "product-positioning-navigation"
            copied["confidence"] = "navigation-only"
        selected.append(copied)
        seen_paths.add(path)
        if len(selected) >= 6:
            break
    if source_root is not None and source_root.is_dir() and len(selected) < 6:
        indexed_root_paths = [
            str(file_record.get("path"))
            for file_record in full_pack.get("files", [])
            if isinstance(file_record, dict)
            and isinstance(file_record.get("path"), str)
            and len(_repo_path_parts(str(file_record.get("path")))) == 1
        ]
        try:
            filesystem_root_paths = [
                child.name for child in source_root.iterdir() if child.is_file()
            ]
        except OSError:
            filesystem_root_paths = []
        for path in sorted(set(indexed_root_paths + filesystem_root_paths)):
            if path in seen_paths:
                continue
            parts = _repo_path_parts(path)
            if len(parts) != 1 or parts[0].casefold() not in preferred_names:
                continue
            snippet = root_file_snippet(path)
            if snippet is None:
                continue
            line_count = max(1, snippet.count("\n") + 1)
            selected.append(
                {
                    "id": "product-navigation-"
                    + hashlib.sha256(path.encode("utf-8")).hexdigest()[:16],
                    "path": path,
                    "line_start": 1,
                    "line_end": line_count,
                    "kind": "product-positioning-navigation",
                    "confidence": "navigation-only",
                    "snippet": snippet,
                }
            )
            seen_paths.add(path)
            if len(selected) >= 6:
                break
    enriched["product_navigation"] = selected
    scope = enriched.get("scope")
    if isinstance(scope, dict):
        allowed = {
            item
            for item in scope.get("allowed_source_paths", [])
            if isinstance(item, str)
        }
        allowed.update(seen_paths)
        scope["allowed_source_paths"] = sorted(allowed)
        scope["product_navigation_paths"] = sorted(seen_paths)
    return enriched

def _materialize_source_slice(
    source: Path,
    workspace: Path,
    allowed_paths: Sequence[str],
    expected_sha256: dict[str, str] | None = None,
) -> Path:
    """Create an immutable model slice bound to the indexed file hashes."""

    # A workspace can outlive one packet. Never add a new packet's files to a
    # previous packet's directory: that silently turns bounded context back
    # into an accumulating repository dump. The identity directory makes
    # every allowed-path/hash set immutable while retaining the
    # ``/source-slice/`` marker used to canonicalize model-authored paths.
    identity_payload = [
        [path, (expected_sha256 or {}).get(path)]
        for path in sorted(set(allowed_paths))
    ]
    slice_identity = hashlib.sha256(
        _json_artifact(identity_payload).encode("utf-8")
    ).hexdigest()[:24]
    slice_root = workspace / slice_identity / "source-slice"
    slice_root.mkdir(parents=True, exist_ok=True)
    source_root = source.resolve()
    for relative_path in sorted(set(allowed_paths)):
        parts = _repo_path_parts(relative_path)
        if not parts:
            raise ValueError(f"invalid source slice path: {relative_path}")
        candidate = source_root.joinpath(*parts)
        try:
            candidate.relative_to(source_root)
            descriptor = os.open(
                candidate,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            raise ValueError(f"source slice path escapes or is missing: {relative_path}") from error
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(
                    f"source slice path is not a regular file: {relative_path}"
                )
            chunks: list[bytes] = []
            digest = hashlib.sha256()
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                digest.update(chunk)
        finally:
            os.close(descriptor)
        actual = digest.hexdigest()
        expected = (expected_sha256 or {}).get(relative_path)
        if expected is not None and actual != expected:
            raise ValueError(
                "source changed before immutable model snapshot: "
                f"{relative_path}"
            )
        destination = slice_root.joinpath(*parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = b"".join(chunks)
        if destination.exists():
            if not destination.is_file() or hashlib.sha256(
                destination.read_bytes()
            ).hexdigest() != actual:
                raise ValueError(
                    f"cached source slice identity changed: {relative_path}"
                )
            continue
        with destination.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    return slice_root

def _indexed_file_hashes(pack: dict[str, object]) -> dict[str, str]:
    packed = pack.get("file_hashes")
    if isinstance(packed, dict):
        return {
            str(path): str(digest)
            for path, digest in packed.items()
            if isinstance(path, str) and isinstance(digest, str)
        }
    return {
        str(item["path"]): str(item["sha256"])
        for item in pack.get("files", [])
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and isinstance(item.get("sha256"), str)
    }

def _stage_model_json(
    source_slice: Path,
    filename: str,
    payload: dict[str, object],
) -> Path:
    """Place model context inside the read-only source-slice sandbox."""

    context_root = source_slice / ".repo-teacher-context"
    context_root.mkdir(parents=True, exist_ok=True)
    destination = context_root / filename
    destination.write_text(_json_artifact(payload), encoding="utf-8")
    return destination
