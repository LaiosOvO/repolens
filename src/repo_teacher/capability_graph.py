from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from typing import Any

from .evidence import EvidenceStore
from .models import FeatureRecord, FeatureStep, TechnologyClaim, stable_id


GRAPH_SCHEMA = "repo-teacher-capability-graph/v1"
_GRAPH_SEED_KINDS = frozenset(
    {
        "http-route",
        "cli-command",
        "entrypoint",
        "entrypoint-candidate",
        "capability-source-audited",
        "capability-role-slice",
    }
)
_COMMON_TOP_LEVEL_PARTS = frozenset(
    {"src", "cmd", "apps", "packages", "pkg", "lib", "internal", "server", "client"}
)
_STATE_TOKENS = frozenset(
    {
        "state",
        "store",
        "storage",
        "repo",
        "repository",
        "db",
        "database",
        "cache",
        "memory",
        "session",
        "queue",
        "index",
        "record",
    }
)
_CALL_EDGE_KINDS = frozenset({"calls", "route-handler", "references"})


def _records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    rendered = str(value).strip()
    return rendered or fallback


def _split_tokens(value: str) -> list[str]:
    token = []
    tokens: list[str] = []
    previous_lower = False
    for character in value:
        if character.isalnum():
            if token and character.isupper() and previous_lower:
                tokens.append("".join(token).lower())
                token = [character]
            else:
                token.append(character)
            previous_lower = character.islower()
            continue
        if token:
            tokens.append("".join(token).lower())
            token = []
        previous_lower = False
    if token:
        tokens.append("".join(token).lower())
    return tokens


def _preferred_label_from_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "root"
    if parts[0] in _COMMON_TOP_LEVEL_PARTS and len(parts) >= 2:
        return parts[1]
    return parts[0]


def _path_tokens(path: str) -> list[str]:
    tokens: list[str] = []
    for part in path.split("/"):
        tokens.extend(_split_tokens(part))
    return tokens


def _module_for_node(node: Mapping[str, Any]) -> str:
    return _preferred_label_from_path(_text(node.get("path")))


def _node(
    identifier: str,
    *,
    symbols: Mapping[str, Mapping[str, Any]],
    files: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    symbol = symbols.get(identifier)
    if symbol is not None:
        return {
            "id": identifier,
            "kind": "symbol",
            "name": symbol.get("name"),
            "qualified_name": symbol.get("qualified_name"),
            "symbol_kind": symbol.get("kind"),
            "path": symbol.get("path"),
            "line": symbol.get("line"),
            "end_line": symbol.get("end_line"),
            "confidence": symbol.get("confidence"),
            "exported": bool(symbol.get("exported")),
        }
    file_record = files.get(identifier)
    if file_record is not None:
        return {
            "id": identifier,
            "kind": "file",
            "name": file_record.get("path"),
            "qualified_name": file_record.get("path"),
            "symbol_kind": "file",
            "path": file_record.get("path"),
            "line": 1,
            "end_line": file_record.get("lines"),
            "confidence": "exact",
            "exported": False,
        }
    return None


def _component_nodes(
    node_ids: set[str],
    undirected: Mapping[str, set[str]],
) -> list[list[str]]:
    remaining = set(node_ids)
    result: list[list[str]] = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue = deque([start])
        component: list[str] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(undirected.get(current, set())):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        result.append(sorted(component))
    return result


def _central_nodes(
    identifiers: Sequence[str],
    *,
    nodes: Mapping[str, Mapping[str, Any]],
    inbound: Mapping[str, set[str]],
    outbound: Mapping[str, set[str]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    ranked = sorted(
        identifiers,
        key=lambda identifier: (
            -(2 * len(inbound.get(identifier, set())) + len(outbound.get(identifier, set()))),
            str(nodes.get(identifier, {}).get("qualified_name") or ""),
            identifier,
        ),
    )
    return [
        {
            "node_id": identifier,
            "qualified_name": nodes[identifier].get("qualified_name"),
            "path": nodes[identifier].get("path"),
            "line": nodes[identifier].get("line"),
            "in_degree": len(inbound.get(identifier, set())),
            "out_degree": len(outbound.get(identifier, set())),
        }
        for identifier in ranked[:limit]
        if identifier in nodes
    ]


def _slice_from_seeds(
    seeds: set[str],
    *,
    adjacency: Mapping[str, set[str]],
    reverse: Mapping[str, set[str]],
    depth: int,
    node_budget: int,
) -> tuple[set[str], dict[str, int]]:
    distance = {seed: 0 for seed in seeds}
    queue = deque(sorted(seeds))
    while queue and len(distance) < node_budget:
        current = queue.popleft()
        current_depth = distance[current]
        if current_depth >= depth:
            continue
        neighbors = adjacency.get(current, set()) | reverse.get(current, set())
        for neighbor in sorted(neighbors):
            if neighbor in distance:
                continue
            distance[neighbor] = current_depth + 1
            queue.append(neighbor)
            if len(distance) >= node_budget:
                break
    return set(distance), distance


def _graph_indexes(
    graph: Mapping[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[tuple[str, str], list[dict[str, Any]]],
]:
    nodes = {
        str(item["id"]): item
        for item in _records(graph.get("nodes"))
        if item.get("id")
    }
    edges = _records(graph.get("edges"))
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        source = edge.get("source_id")
        target = edge.get("target_id")
        if isinstance(source, str) and isinstance(target, str):
            forward[source].add(target)
            reverse[target].add(source)
            by_pair[(source, target)].append(edge)
    return nodes, edges, forward, reverse, by_pair


def traverse_graph(
    graph: Mapping[str, Any],
    start_ids: Sequence[str],
    *,
    direction: str = "both",
    depth: int = 2,
    limit: int = 80,
    edge_kinds: Sequence[str] | None = None,
) -> dict[str, Any]:
    if direction not in {"forward", "reverse", "both"}:
        raise ValueError("direction must be forward, reverse or both")
    if depth < 0:
        raise ValueError("depth must be zero or greater")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    nodes, edges, forward, reverse, by_pair = _graph_indexes(graph)
    allowed_kinds = {kind for kind in edge_kinds or () if kind}

    def neighbor_ids(identifier: str) -> set[str]:
        selected: set[str] = set()
        if direction in {"forward", "both"}:
            selected.update(forward.get(identifier, set()))
        if direction in {"reverse", "both"}:
            selected.update(reverse.get(identifier, set()))
        if not allowed_kinds:
            return selected
        filtered: set[str] = set()
        for neighbor in selected:
            if direction in {"forward", "both"}:
                if any(
                    _text(edge.get("kind")) in allowed_kinds
                    for edge in by_pair.get((identifier, neighbor), [])
                ):
                    filtered.add(neighbor)
            if direction in {"reverse", "both"}:
                if any(
                    _text(edge.get("kind")) in allowed_kinds
                    for edge in by_pair.get((neighbor, identifier), [])
                ):
                    filtered.add(neighbor)
        return filtered

    seeds = [identifier for identifier in start_ids if identifier in nodes][:limit]
    visited: dict[str, int] = {identifier: 0 for identifier in seeds}
    queue = deque(seeds)
    while queue and len(visited) < limit:
        current = queue.popleft()
        if visited[current] >= depth:
            continue
        for neighbor in sorted(neighbor_ids(current)):
            if neighbor in visited:
                continue
            visited[neighbor] = visited[current] + 1
            queue.append(neighbor)
            if len(visited) >= limit:
                break
    selected = set(visited)
    selected_edges = [
        edge
        for edge in edges
        if edge.get("source_id") in selected
        and edge.get("target_id") in selected
        and (
            not allowed_kinds
            or _text(edge.get("kind")) in allowed_kinds
        )
    ]
    return {
        "start_ids": seeds,
        "direction": direction,
        "depth": depth,
        "nodes": [nodes[identifier] | {"distance": visited[identifier]} for identifier in visited],
        "edges": selected_edges,
    }


def get_callers(
    graph: Mapping[str, Any],
    identifier: str,
    *,
    depth: int = 2,
    limit: int = 40,
) -> dict[str, Any]:
    return traverse_graph(
        graph,
        [identifier],
        direction="reverse",
        depth=depth,
        limit=limit,
        edge_kinds=("calls", "route-handler"),
    )


def get_callees(
    graph: Mapping[str, Any],
    identifier: str,
    *,
    depth: int = 2,
    limit: int = 40,
) -> dict[str, Any]:
    return traverse_graph(
        graph,
        [identifier],
        direction="forward",
        depth=depth,
        limit=limit,
        edge_kinds=("calls", "route-handler"),
    )


def get_dependency_graph(
    graph: Mapping[str, Any],
    *,
    modules: Sequence[str] | None = None,
    limit: int = 120,
) -> dict[str, Any]:
    dependencies = _records(graph.get("module_dependencies"))
    wanted = {module for module in modules or () if module}
    if wanted:
        dependencies = [
            dependency
            for dependency in dependencies
            if _text(dependency.get("source")) in wanted
            or _text(dependency.get("target")) in wanted
        ]
    dependencies = dependencies[:limit]
    nodes = sorted(
        {
            module
            for dependency in dependencies
            for module in (
                _text(dependency.get("source")),
                _text(dependency.get("target")),
            )
            if module
        }
    )
    return {"modules": nodes, "dependencies": dependencies}


def analyze_impact(
    graph: Mapping[str, Any],
    start_ids: Sequence[str],
    *,
    depth: int = 2,
    limit: int = 80,
) -> dict[str, Any]:
    nodes, edges, _forward, _reverse, _by_pair = _graph_indexes(graph)
    seeds = [identifier for identifier in start_ids if identifier in nodes]
    downstream = traverse_graph(graph, seeds, direction="forward", depth=depth, limit=limit)
    upstream = traverse_graph(graph, seeds, direction="reverse", depth=depth, limit=limit)
    direct_callers = sorted(
        {
            _text(edge.get("source_id"))
            for edge in edges
            if edge.get("target_id") in seeds
            and _text(edge.get("kind")) in _CALL_EDGE_KINDS
        }
    )
    direct_callees = sorted(
        {
            _text(edge.get("target_id"))
            for edge in edges
            if edge.get("source_id") in seeds
            and _text(edge.get("kind")) in _CALL_EDGE_KINDS
        }
    )
    indirect = sorted(
        {
            item["id"]
            for item in downstream["nodes"] + upstream["nodes"]
            if isinstance(item, dict)
            and _text(item.get("id"))
            and _text(item.get("id")) not in seeds
            and int(item.get("distance") or 0) > 1
        }
    )
    return {
        "start_ids": seeds,
        "direct_callers": direct_callers,
        "direct_callees": direct_callees,
        "indirect_impact_node_ids": indirect,
        "upstream": upstream,
        "downstream": downstream,
    }


def _feature_kind(feature: Mapping[str, Any]) -> str:
    return _text(feature.get("kind"))


def _seed_features(index: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(feature.get("id")): feature
        for feature in _records(index.get("features"))
        if feature.get("id")
        and _feature_kind(feature) in _GRAPH_SEED_KINDS
    }


def _route_title(entrypoint: str, primary_module: str) -> str:
    parts = entrypoint.split(maxsplit=1)
    method = parts[0] if parts else "HTTP"
    route = parts[1] if len(parts) == 2 else ""
    segments = [part for part in route.split("/") if part and not part.startswith("{")]
    label = next(
        (segment for segment in segments if segment.lower() not in {"api", "v1", "v2", "v3"}),
        primary_module or "root",
    )
    return f"{label} API {method}"


def _candidate_title(feature: Mapping[str, Any], primary_module: str, key_nodes: Sequence[str]) -> str:
    kind = _feature_kind(feature)
    entrypoint = _text(feature.get("entrypoint"))
    if kind == "http-route":
        return _route_title(entrypoint, primary_module)
    if kind == "cli-command":
        return f"{entrypoint or primary_module} CLI 流程"
    if kind == "entrypoint-candidate":
        return f"{primary_module or 'root'} 候选执行流程"
    if kind == "entrypoint":
        return f"{primary_module or 'root'} 执行流程"
    return " / ".join(key_nodes[:2]) if key_nodes else f"{primary_module or 'root'} 协作流程"


def _state_nodes(node_ids: Sequence[str], nodes: Mapping[str, Mapping[str, Any]]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for identifier in node_ids:
        node = nodes.get(identifier)
        if node is None:
            continue
        material = " ".join(
            [
                _text(node.get("qualified_name")),
                _text(node.get("path")),
                _text(node.get("symbol_kind")),
            ]
        )
        score = sum(1 for token in _split_tokens(material) if token in _STATE_TOKENS)
        if score > 0:
            ranked.append((score, identifier))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [identifier for _score, identifier in ranked[:4]]


def _key_edges(
    edge_ids: Sequence[str],
    edges_by_id: Mapping[str, Mapping[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for edge_id in edge_ids:
        edge = edges_by_id.get(edge_id)
        if edge is None or _text(edge.get("kind")) not in _CALL_EDGE_KINDS:
            continue
        source_id = _text(edge.get("source_id"))
        target_id = _text(edge.get("target_id"))
        source = nodes.get(source_id, {})
        target = nodes.get(target_id, {})
        selected.append(
            {
                "kind": _text(edge.get("kind")),
                "source": _text(source.get("qualified_name"), source_id),
                "target": _text(target.get("qualified_name"), target_id),
            }
        )
        if len(selected) >= 4:
            break
    return selected


def build_capability_graph(
    index: Mapping[str, Any],
    *,
    max_components: int = 120,
    max_slice_nodes: int = 180,
    slice_depth: int = 4,
) -> dict[str, Any]:
    """Derive a deterministic code graph and feature slices from an index.

    The graph consumes parser-produced identities and resolved relationships.  It
    deliberately does not infer product capabilities from words in filenames or
    source text; user-facing features remain seeds, while unseeded components are
    labelled mechanism clusters for later evidence-bounded synthesis.
    """

    files = {str(item["id"]): item for item in _records(index.get("files")) if item.get("id")}
    symbols = {
        str(item["id"]): item for item in _records(index.get("symbols")) if item.get("id")
    }
    relationships = _records(index.get("relationships"))

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    adjacency: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    undirected: dict[str, set[str]] = defaultdict(set)

    for relationship in relationships:
        source_id = relationship.get("source_id")
        target_id = relationship.get("target_id")
        kind = str(relationship.get("kind") or "")
        if not isinstance(source_id, str):
            continue
        if not isinstance(target_id, str):
            unresolved.append(
                {
                    "id": relationship.get("id"),
                    "source_id": source_id,
                    "target_name": relationship.get("target_name"),
                    "kind": kind,
                    "path": relationship.get("path"),
                    "line": relationship.get("line"),
                    "confidence": relationship.get("confidence"),
                }
            )
            continue
        source = _node(source_id, symbols=symbols, files=files)
        target = _node(target_id, symbols=symbols, files=files)
        if source is None or target is None:
            continue
        nodes[source_id] = source
        nodes[target_id] = target
        edge = {
            "id": relationship.get("id"),
            "source_id": source_id,
            "target_id": target_id,
            "kind": kind,
            "path": relationship.get("path"),
            "line": relationship.get("line"),
            "confidence": relationship.get("confidence"),
        }
        edges.append(edge)
        adjacency[source_id].add(target_id)
        reverse[target_id].add(source_id)
        undirected[source_id].add(target_id)
        undirected[target_id].add(source_id)

    node_ids = set(nodes)
    raw_components = _component_nodes(node_ids, undirected)
    raw_components.sort(key=lambda component: (-len(component), component[0]))
    components: list[dict[str, Any]] = []
    component_by_node: dict[str, str] = {}
    for component in raw_components[:max_components]:
        component_id = stable_id("graph-component", *component)
        path_counts = Counter(
            str(nodes[identifier].get("path") or "").split("/", 1)[0]
            for identifier in component
        )
        edge_count = sum(
            1
            for edge in edges
            if edge["source_id"] in component and edge["target_id"] in component
        )
        record = {
            "id": component_id,
            "node_count": len(component),
            "edge_count": edge_count,
            "primary_areas": [name for name, _ in path_counts.most_common(5) if name],
            "central_nodes": _central_nodes(
                component,
                nodes=nodes,
                inbound=reverse,
                outbound=adjacency,
            ),
            "node_ids": component,
        }
        components.append(record)
        for identifier in component:
            component_by_node[identifier] = component_id

    feature_slices: list[dict[str, Any]] = []
    claimed_nodes: set[str] = set()
    for feature in _records(index.get("features")):
        seeds: set[str] = set()
        entry_symbol_id = feature.get("entry_symbol_id")
        if isinstance(entry_symbol_id, str) and entry_symbol_id in nodes:
            seeds.add(entry_symbol_id)
        for step in _records(feature.get("steps")):
            symbol_id = step.get("symbol_id")
            if isinstance(symbol_id, str) and symbol_id in nodes:
                seeds.add(symbol_id)
            relationship_id = step.get("relationship_id")
            if isinstance(relationship_id, str):
                for edge in edges:
                    if edge.get("id") == relationship_id:
                        seeds.add(str(edge["source_id"]))
                        seeds.add(str(edge["target_id"]))
        if not seeds:
            continue
        slice_nodes, distance = _slice_from_seeds(
            seeds,
            adjacency=adjacency,
            reverse=reverse,
            depth=slice_depth,
            node_budget=max_slice_nodes,
        )
        claimed_nodes.update(slice_nodes)
        slice_edges = [
            edge
            for edge in edges
            if edge["source_id"] in slice_nodes and edge["target_id"] in slice_nodes
        ]
        feature_slices.append(
            {
                "id": stable_id("graph-feature-slice", feature.get("id")),
                "feature_id": feature.get("id"),
                "title": feature.get("title"),
                "feature_kind": feature.get("kind"),
                "feature_source": feature.get("source"),
                "entrypoint": feature.get("entrypoint"),
                "confidence": feature.get("confidence"),
                "seed_node_ids": sorted(seeds),
                "node_ids": sorted(slice_nodes, key=lambda identifier: (distance[identifier], identifier)),
                "edge_ids": sorted(
                    str(edge["id"]) for edge in slice_edges if isinstance(edge.get("id"), str)
                ),
                "component_ids": sorted(
                    {
                        component_by_node[identifier]
                        for identifier in slice_nodes
                        if identifier in component_by_node
                    }
                ),
                "central_nodes": _central_nodes(
                    list(slice_nodes),
                    nodes=nodes,
                    inbound=reverse,
                    outbound=adjacency,
                ),
            }
        )

    mechanism_clusters = [
        {
            "id": stable_id("mechanism-cluster", component["id"]),
            "component_id": component["id"],
            "kind": "mechanism-cluster",
            "claim_status": "candidate-not-user-facing-until-reviewed",
            "primary_areas": component["primary_areas"],
            "central_nodes": component["central_nodes"],
            "node_count": component["node_count"],
            "edge_count": component["edge_count"],
        }
        for component in components
        if component["node_count"] >= 2
        and not any(identifier in claimed_nodes for identifier in component["node_ids"])
    ]

    file_to_module = {
        str(item.get("id")): str(item.get("module") or "root")
        for item in files.values()
    }
    symbol_to_module = {
        identifier: file_to_module.get(str(symbol.get("file_id")), "root")
        for identifier, symbol in symbols.items()
    }
    module_edges: Counter[tuple[str, str, str]] = Counter()
    for edge in edges:
        source_module = symbol_to_module.get(
            str(edge["source_id"]), file_to_module.get(str(edge["source_id"]), "root")
        )
        target_module = symbol_to_module.get(
            str(edge["target_id"]), file_to_module.get(str(edge["target_id"]), "root")
        )
        if source_module != target_module:
            module_edges[(source_module, target_module, str(edge["kind"]))] += 1

    feature_metadata = {
        str(feature.get("id")): feature
        for feature in _records(index.get("features"))
        if feature.get("id")
    }
    edges_by_id = {
        str(edge.get("id")): edge
        for edge in edges
        if edge.get("id")
    }
    capability_candidates: list[dict[str, Any]] = []
    for feature_slice in feature_slices:
        feature_id = _text(feature_slice.get("feature_id"))
        feature = feature_metadata.get(feature_id, {})
        feature_kind = _feature_kind(feature)
        if feature_kind not in _GRAPH_SEED_KINDS:
            continue
        node_ids_for_slice = [
            identifier
            for identifier in feature_slice.get("node_ids", [])
            if isinstance(identifier, str) and identifier in nodes
        ]
        if not node_ids_for_slice:
            continue
        central_nodes = feature_slice.get("central_nodes", [])
        key_node_labels = [
            _text(item.get("qualified_name"))
            for item in central_nodes
            if isinstance(item, dict) and _text(item.get("qualified_name"))
        ]
        primary_modules = list(
            dict.fromkeys(_module_for_node(nodes[identifier]) for identifier in node_ids_for_slice)
        )
        state_node_ids = _state_nodes(node_ids_for_slice, nodes)
        key_edges = _key_edges(feature_slice.get("edge_ids", []), edges_by_id, nodes)
        title = _candidate_title(
            feature,
            primary_modules[0] if primary_modules else "",
            key_node_labels,
        )
        graph_summary = {
            "trigger": _text(feature.get("entrypoint"), _text(feature.get("title"))),
            "primary_modules": primary_modules[:4],
            "key_nodes": key_node_labels[:4],
            "key_edges": key_edges,
            "state_nodes": [
                _text(nodes[identifier].get("qualified_name"), identifier)
                for identifier in state_node_ids
            ],
            "impact_radius": {
                "nodes": len(node_ids_for_slice),
                "edges": len(feature_slice.get("edge_ids", [])),
                "components": len(feature_slice.get("component_ids", [])),
                "modules": primary_modules[:6],
            },
            "source_feature_ids": [feature_id],
        }
        summary = (
            f"由 `{graph_summary['trigger']}` 触发，核心模块是 "
            f"{' / '.join(primary_modules[:3]) or 'root'}；"
            f"关键实现节点是 {' → '.join(key_node_labels[:3]) or '当前只识别到入口节点'}；"
            f"{'状态/存储点在 ' + '、'.join(graph_summary['state_nodes'][:3]) if graph_summary['state_nodes'] else '当前没有识别到独立状态/存储节点'}；"
            f"影响半径覆盖 {graph_summary['impact_radius']['nodes']} 个节点、"
            f"{graph_summary['impact_radius']['edges']} 条边。"
        )
        capability_candidates.append(
            {
                "id": stable_id("graph-capability-candidate", feature_id),
                "kind": (
                    "capability-cluster"
                    if _text(feature.get("confidence")).lower() in {"exact-entry", "source-audited"}
                    else "capability-cluster-candidate"
                ),
                "title": title,
                "summary": summary,
                "source_feature_ids": [feature_id],
                "slice_id": feature_slice.get("id"),
                "graph_summary": graph_summary,
                "seed_node_ids": feature_slice.get("seed_node_ids", []),
                "node_ids": node_ids_for_slice,
                "edge_ids": feature_slice.get("edge_ids", []),
                "component_ids": feature_slice.get("component_ids", []),
                "central_nodes": central_nodes,
            }
        )

    return {
        "schema_version": GRAPH_SCHEMA,
        "nodes": sorted(nodes.values(), key=lambda item: str(item["id"])),
        "edges": sorted(edges, key=lambda item: str(item.get("id") or "")),
        "unresolved_edges": sorted(
            unresolved,
            key=lambda item: (
                str(item.get("path") or ""),
                int(item.get("line") or 0),
                str(item.get("id") or ""),
            ),
        ),
        "components": components,
        "feature_slices": feature_slices,
        "capability_candidates": capability_candidates,
        "mechanism_clusters": mechanism_clusters,
        "module_dependencies": [
            {
                "source": source,
                "target": target,
                "kind": kind,
                "count": count,
            }
            for (source, target, kind), count in sorted(
                module_edges.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "stats": {
            "nodes": len(nodes),
            "resolved_edges": len(edges),
            "unresolved_edges": len(unresolved),
            "components": len(components),
            "feature_slices": len(feature_slices),
            "capability_candidates": len(capability_candidates),
            "mechanism_clusters": len(mechanism_clusters),
        },
    }


def explore_capability_graph(
    graph: Mapping[str, Any],
    query: str,
    *,
    depth: int = 2,
    limit: int = 80,
) -> dict[str, Any]:
    """Return CodeGraph-style callers/callees/impact context for a query."""

    normalized = query.strip().casefold()
    nodes, _edges, _forward, _reverse, _pairs = _graph_indexes(graph)
    matches = [
        identifier
        for identifier, node in nodes.items()
        if normalized
        and any(
            normalized in str(node.get(field) or "").casefold()
            for field in ("name", "qualified_name", "path")
        )
    ][:20]
    traversed = traverse_graph(graph, matches, direction="both", depth=depth, limit=limit)
    impact = analyze_impact(graph, matches, depth=depth, limit=limit)
    callers = {
        identifier: sorted(
            _text(item.get("id"))
            for item in get_callers(graph, identifier, depth=1, limit=limit)["nodes"]
            if int(item.get("distance") or 0) == 1
        )
        for identifier in matches
    }
    callees = {
        identifier: sorted(
            _text(item.get("id"))
            for item in get_callees(graph, identifier, depth=1, limit=limit)["nodes"]
            if int(item.get("distance") or 0) == 1
        )
        for identifier in matches
    }
    return {
        "query": query,
        "matched_node_ids": matches,
        "nodes": traversed["nodes"],
        "edges": traversed["edges"],
        "callers": callers,
        "callees": callees,
        "dependency_graph": get_dependency_graph(
            graph,
            modules=sorted(
                {
                    _module_for_node(nodes[identifier])
                    for identifier in matches
                    if identifier in nodes
                }
            ),
        ),
        "impact_node_ids": sorted(
            set(impact["direct_callers"])
            | set(impact["direct_callees"])
            | set(impact["indirect_impact_node_ids"])
        ),
        "impact": impact,
    }


def graph_prompt_context(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded graph-first packet for capability synthesis."""

    nodes = {
        str(item["id"]): item
        for item in _records(graph.get("nodes"))
        if item.get("id")
    }
    edges = {
        str(item["id"]): item
        for item in _records(graph.get("edges"))
        if item.get("id")
    }

    def selected_nodes(identifiers: object, limit: int = 80) -> list[dict[str, Any]]:
        if not isinstance(identifiers, list):
            return []
        return [
            nodes[identifier]
            for identifier in identifiers[:limit]
            if isinstance(identifier, str) and identifier in nodes
        ]

    def selected_edges(identifiers: object, limit: int = 160) -> list[dict[str, Any]]:
        if not isinstance(identifiers, list):
            return []
        result: list[dict[str, Any]] = []
        for identifier in identifiers[:limit]:
            if not isinstance(identifier, str) or identifier not in edges:
                continue
            edge = edges[identifier]
            source = nodes.get(str(edge.get("source_id") or ""), {})
            target = nodes.get(str(edge.get("target_id") or ""), {})
            result.append(
                {
                    "id": identifier,
                    "kind": edge.get("kind"),
                    "confidence": edge.get("confidence"),
                    "source_id": edge.get("source_id"),
                    "source_name": source.get("qualified_name") or source.get("name"),
                    "source_path": source.get("path"),
                    "source_line": source.get("line"),
                    "target_id": edge.get("target_id"),
                    "target_name": target.get("qualified_name") or target.get("name"),
                    "target_path": target.get("path"),
                    "target_line": target.get("line"),
                }
            )
        return result

    feature_slices = []
    for item in _records(graph.get("feature_slices")):
        feature_slices.append(
            {
                "id": item.get("id"),
                "feature_id": item.get("feature_id"),
                "title": item.get("title"),
                "confidence": item.get("confidence"),
                "seed_nodes": selected_nodes(item.get("seed_node_ids"), 20),
                "implementation_nodes": selected_nodes(item.get("node_ids"), 80),
                "edge_ids": list(item.get("edge_ids", []))[:240]
                if isinstance(item.get("edge_ids"), list)
                else [],
                "resolved_edges": selected_edges(item.get("edge_ids"), 160),
                "component_ids": item.get("component_ids", []),
                "central_nodes": item.get("central_nodes", []),
            }
        )
    components = [
        {
            "id": item.get("id"),
            "node_count": item.get("node_count"),
            "edge_count": item.get("edge_count"),
            "primary_areas": item.get("primary_areas", []),
            "central_nodes": item.get("central_nodes", []),
        }
        for item in _records(graph.get("components"))[:120]
    ]
    capability_candidates = [
        {
            "id": item.get("id"),
            "kind": item.get("kind"),
            "title": item.get("title"),
            "summary": item.get("summary"),
            "source_feature_ids": item.get("source_feature_ids", []),
            "graph_summary": item.get("graph_summary", {}),
            "central_nodes": item.get("central_nodes", []),
            "implementation_nodes": selected_nodes(item.get("node_ids"), 80),
            "resolved_edges": selected_edges(item.get("edge_ids"), 160),
        }
        for item in _records(graph.get("capability_candidates"))[:200]
    ]
    return {
        "schema_version": graph.get("schema_version"),
        "stats": graph.get("stats", {}),
        "feature_slices": feature_slices,
        "capability_candidates": capability_candidates,
        "mechanism_clusters": _records(graph.get("mechanism_clusters"))[:120],
        "components": components,
        "module_dependencies": _records(graph.get("module_dependencies"))[:300],
        "unresolved_edge_examples": _records(graph.get("unresolved_edges"))[:200],
        "interpretation_contract": [
            "feature_slices 是已识别用户能力的图扩展，可作为实现路径证据。",
            "capability_candidates 是由入口边界 + 调用邻域 + 模块局部性聚出的功能种子；先从这里选功能，再下钻源码。",
            "mechanism_clusters 只是结构候选，不能未经源码核对就提升为用户功能。",
            "resolved edges 可证明静态依赖；unresolved edges 只能标为缺口，不能冒充调用成功。",
            "先按 module dependency 与 component 理解边界，再为每项能力读取最短实现切片。",
        ],
    }


def derive_graph_capability_features(
    graph: Mapping[str, Any],
    *,
    evidence: EvidenceStore,
) -> list[FeatureRecord]:
    nodes, edges, _forward, _reverse, edges_by_pair = _graph_indexes(graph)
    edges_by_id = {
        _text(edge.get("id")): edge
        for edge in edges
        if _text(edge.get("id"))
    }
    features: list[FeatureRecord] = []
    for candidate in _records(graph.get("capability_candidates")):
        graph_summary = candidate.get("graph_summary", {})
        if not isinstance(graph_summary, dict):
            graph_summary = {}
        title = _text(candidate.get("title"), "未命名功能")
        summary = _text(candidate.get("summary"), "当前没有图能力摘要。")
        kind = _text(candidate.get("kind"), "capability-cluster-candidate")
        node_ids = [
            identifier
            for identifier in candidate.get("node_ids", [])
            if isinstance(identifier, str) and identifier in nodes
        ]
        edge_ids = [
            identifier
            for identifier in candidate.get("edge_ids", [])
            if isinstance(identifier, str) and identifier in edges_by_id
        ]
        if not node_ids:
            continue
        steps: list[FeatureStep] = []
        evidence_ids: list[str] = []
        role_assignments: list[tuple[str, str]] = [
            ("trigger", node_ids[0]),
            *[
                ("core", identifier)
                for identifier in node_ids[1:3]
            ],
            *[
                ("state", identifier)
                for identifier in _state_nodes(node_ids, nodes)[:2]
                if identifier not in node_ids[:3]
            ],
        ]
        seen_nodes: set[str] = set()
        for order, (role, identifier) in enumerate(role_assignments, start=1):
            if identifier in seen_nodes:
                continue
            seen_nodes.add(identifier)
            node = nodes[identifier]
            path = _text(node.get("path"))
            line_start = int(node.get("line") or 1)
            line_end = int(node.get("end_line") or line_start)
            reference = evidence.add(
                path,
                line_start,
                line_end,
                kind=f"graph-{role}-slice",
                confidence="graph-derived",
                analyzer="capability-graph",
                symbol_id=identifier if node.get("kind") == "symbol" else None,
            )
            evidence_ids.append(reference.id)
            explanation = (
                "这是触发该功能的边界或种子节点。"
                if role == "trigger"
                else (
                    "这是承接主要控制流的核心协作节点。"
                    if role == "core"
                    else "这是状态写入、缓存、存储或会话落点。"
                )
            )
            steps.append(
                FeatureStep(
                    order=len(steps) + 1,
                    title={"trigger": "触发入口", "core": "核心协作", "state": "状态/存储"}[role],
                    explanation=explanation,
                    path=path,
                    line_start=line_start,
                    line_end=line_end,
                    evidence_ids=[reference.id],
                    symbol_id=identifier if node.get("kind") == "symbol" else None,
                    source_symbol=_text(node.get("qualified_name"), identifier),
                    source_role={"trigger": "触发入口", "core": "核心协作", "state": "状态/存储"}[role],
                    claim_scope="图聚类只证明静态邻域与模块协作，不证明运行时顺序或动态分派。",
                )
            )
        for edge_id in edge_ids[:2]:
            edge = edges_by_id[edge_id]
            source_id = _text(edge.get("source_id"))
            target_id = _text(edge.get("target_id"))
            source = nodes.get(source_id, {})
            target = nodes.get(target_id, {})
            path = _text(edge.get("path"), _text(source.get("path")))
            line_start = int(edge.get("line") or source.get("line") or 1)
            reference = evidence.add(
                path,
                line_start,
                line_start,
                kind="graph-edge-slice",
                confidence="graph-derived",
                analyzer="capability-graph",
                symbol_id=source_id if source.get("kind") == "symbol" else None,
            )
            evidence_ids.append(reference.id)
            steps.append(
                FeatureStep(
                    order=len(steps) + 1,
                    title="关键依赖边",
                    explanation=(
                        f"{_text(source.get('qualified_name'), source_id)} "
                        f"通过 `{_text(edge.get('kind'))}` 连接到 "
                        f"{_text(target.get('qualified_name'), target_id)}。"
                    ),
                    path=path,
                    line_start=line_start,
                    line_end=line_start,
                    evidence_ids=[reference.id],
                    symbol_id=source_id if source.get("kind") == "symbol" else None,
                    relationship_id=edge_id,
                    source_symbol=_text(source.get("qualified_name"), source_id),
                    source_role="关键依赖边",
                    claim_scope="这里只证明静态边存在，不外推调度、并发或错误传播。",
                    relationship_kind=_text(edge.get("kind")),
                )
            )
        known_store = "stateful-component" if graph_summary.get("state_nodes") else "unknown"
        technology_claims = [
            TechnologyClaim(
                dimension="evidence",
                value="relationship-graph",
                claim_scope="该功能来自静态依赖图聚类，不是目录白名单或 README 推断。",
                confidence="graph-derived",
                evidence_ids=evidence_ids[:2],
                source_path=_text(steps[0].path) if steps else None,
            ),
            TechnologyClaim(
                dimension="incremental",
                value="static-graph",
                claim_scope="聚类依据现有 files/symbols/relationships 构造的有向图与组件局部性。",
                confidence="graph-derived",
                evidence_ids=evidence_ids[:2],
                source_path=_text(steps[0].path) if steps else None,
            ),
            TechnologyClaim(
                dimension="store",
                value=known_store,
                claim_scope=(
                    "图切片中存在显式状态/存储节点。"
                    if known_store != "unknown"
                    else "当前图切片没有识别出独立状态/存储节点。"
                ),
                confidence="graph-derived" if known_store != "unknown" else "unknown",
                evidence_ids=evidence_ids[:1] if known_store != "unknown" else [],
                source_path=_text(steps[0].path) if steps else None,
            ),
        ]
        features.append(
            FeatureRecord(
                id=_text(candidate.get("id"), stable_id("feature", kind, title)),
                title=title,
                kind=kind,
                summary=summary,
                entrypoint=_text(graph_summary.get("trigger"), _text(candidate.get("slice_id"))),
                confidence=(
                    "graph-cluster"
                    if kind == "capability-cluster"
                    else "graph-candidate"
                ),
                source="capability-graph-clustering",
                steps=steps,
                component_ids=[
                    identifier
                    for identifier in candidate.get("component_ids", [])
                    if isinstance(identifier, str)
                ],
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                technology_tags=[
                    "graph-derived",
                    f"graph-kind:{kind}",
                    f"graph-trigger:{_text(graph_summary.get('trigger'))}",
                ],
                technology_claims=technology_claims,
                graph_summary=graph_summary,
            )
        )
    return features
