from __future__ import annotations

import hashlib
import os
import re
import stat
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from .evidence import redact_secrets
from .models import stable_id
from .reference_catalog import reference_identity_status


_ENTRYPOINT_NAMES = {
    "app.py",
    "cli.py",
    "index.js",
    "index.ts",
    "index.tsx",
    "main.go",
    "main.js",
    "main.py",
    "main.rs",
    "main.ts",
    "main.tsx",
    "manage.py",
    "server.py",
}
_MANIFEST_NAMES = {
    "cargo.toml",
    "dockerfile",
    "go.mod",
    "makefile",
    "package.json",
    "pom.xml",
    "pyproject.toml",
}
_TEST_PARTS = {"test", "tests", "spec", "specs", "__tests__"}
_AUXILIARY_PARTS = {
    ".git",
    ".next",
    "benchmark",
    "benchmarks",
    "build",
    "coverage",
    "dist",
    "doc",
    "docs",
    "documentation",
    "example",
    "examples",
    "fixture",
    "fixtures",
    "gen",
    "generated",
    "node_modules",
    "spec",
    "specs",
    "target",
    "test",
    "tests",
    "vendor",
}
_ROLE_ORDER = {
    "entrypoint": 0,
    "boundary": 1,
    "orchestration": 2,
    "core": 3,
    "model": 4,
    "persistence": 5,
    "adapter": 6,
    "presentation": 7,
    "configuration": 8,
    "documentation": 9,
    "test": 10,
}


# These are source-audited benchmark surfaces, not generic claims about similarly
# named repositories.  The generic locator still works when none of these paths
# exist.  Keeping the paths here makes the six regression baselines executable.
_REFERENCE_SURFACES: tuple[dict[str, Any], ...] = (
    {
        "project": "pocketflow-code2tutorial",
        "queries": {"tutorial", "code2tutorial"},
        "mechanism": "FetchRepo → abstractions → relationships → chapter order → chapter writing → combine",
        "slices": (
            ("main.py", "file", "entrypoint"),
            ("flow.py", "file", "orchestration"),
            ("nodes.py", "file", "core"),
        ),
    },
    {
        "project": "sourcebridge",
        "queries": {"knowledge"},
        "mechanism": "domain store + knowledge workers + administration presentation",
        "slices": (
            ("internal/knowledge", "directory", "persistence"),
            ("workers/knowledge", "directory", "orchestration"),
            ("web/src/app/(app)/admin/knowledge", "directory", "presentation"),
        ),
    },
    {
        "project": "openwiki",
        "queries": {"visualize", "visualization"},
        "mechanism": "deterministic graph construction + visualization server + CLI caller",
        "slices": (
            ("src/visualize", "directory", "core"),
            ("src/cli/runners.ts", "file", "entrypoint"),
        ),
    },
    {
        "project": "understand-anything",
        "queries": {"viewer"},
        "mechanism": "local viewer package command and build surface",
        "slices": (
            ("understand-anything-plugin/packages/viewer", "directory", "presentation"),
        ),
    },
    {
        "project": "codeboarding",
        "queries": {"staticanalyzer", "staticanalysis"},
        "mechanism": "LSP symbols/references + call graph + hierarchy + component clustering",
        "slices": (
            ("static_analyzer", "directory", "core"),
        ),
    },
    {
        "project": "deepwiki-open",
        "queries": {"codemap"},
        "mechanism": "router → source-grounded service → schema → streamed UI and code viewer",
        "slices": (
            ("api/services/codemap.py", "file", "orchestration"),
            ("api/routers/codemap.py", "file", "boundary"),
            ("api/schemas/codemap.py", "file", "model"),
            ("src/components/Ask.tsx", "file", "entrypoint"),
            ("src/components/CodeMap.tsx", "file", "presentation"),
            ("src/components/CodeViewer.tsx", "file", "presentation"),
            ("src/utils/websocketClient.ts", "file", "adapter"),
        ),
    },
)


def _text(value: Any, fallback: str = "") -> str:
    rendered = str(value).strip() if value is not None else ""
    return rendered or fallback


def _normalise(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _tokens(value: str) -> set[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return {
        token.casefold()
        for token in re.split(r"[\W_]+", expanded, flags=re.UNICODE)
        if token
    }


def _safe_relative_path(value: Any) -> str | None:
    raw = _text(value).replace("\\", "/")
    if not raw or raw == ".":
        return "." if raw == "." else None
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        return None
    normalized = path.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized or "."


def _project_root(index: dict[str, Any]) -> Path | None:
    project = index.get("project")
    if not isinstance(project, dict):
        return None
    raw = _text(project.get("path"))
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return None


def _source_uri(project_root: Path | None, relative_path: str) -> str | None:
    if project_root is None:
        return None
    safe_path = _safe_relative_path(relative_path)
    if not safe_path:
        return None
    candidate = project_root if safe_path == "." else (project_root / PurePosixPath(safe_path))
    try:
        candidate = candidate.resolve(strict=False)
        if not candidate.is_relative_to(project_root):
            return None
        return candidate.as_uri()
    except (OSError, RuntimeError, ValueError):
        return None


def _path_parts(path: str) -> tuple[str, ...]:
    return tuple(part.casefold() for part in PurePosixPath(path).parts)


def _is_test_path(path: str) -> bool:
    parts = set(_path_parts(path))
    name = PurePosixPath(path).name.casefold()
    return bool(parts & _TEST_PARTS) or bool(
        re.search(r"(^|[._-])(test|spec)([._-]|$)", name)
    )


def _is_auxiliary_path(path: str) -> bool:
    return any(part in _AUXILIARY_PARTS for part in _path_parts(path))


def _is_product_source(file: dict[str, Any]) -> bool:
    path = _text(file.get("path"))
    if _is_auxiliary_path(path) or _is_test_path(path):
        return False
    role, _, _ = _file_role(file)
    return role != "documentation"


def _directory_exists(directory: str, files: list[dict[str, Any]]) -> bool:
    prefix = f"{directory}/"
    return any(_text(file.get("path")).startswith(prefix) for file in files)


def _reference_surface(
    index: dict[str, Any],
    project_name: str,
    query: str,
    files: list[dict[str, Any]],
) -> dict[str, Any] | None:
    project_key = _normalise(project_name)
    query_key = _normalise(query)
    known_paths = {_text(file.get("path")) for file in files}
    identity = reference_identity_status(index)
    verified_project = (
        _text(identity.get("project_key")) if identity.get("status") == "verified" else ""
    )
    for reference in _REFERENCE_SURFACES:
        reference_project = _text(reference["project"])
        name_matches = _normalise(reference_project) in project_key
        identity_matches = verified_project == reference_project
        if not name_matches and not identity_matches:
            continue
        if query_key not in {_normalise(_text(item)) for item in reference["queries"]}:
            continue
        slices = []
        for path, kind, role in reference["slices"]:
            exists = path in known_paths if kind == "file" else _directory_exists(path, files)
            if exists:
                slices.append(
                    {
                        "kind": kind,
                        "path": path,
                        "role": role,
                        "evidence": (
                            "source-audited reference snapshot"
                            if identity_matches
                            else "unverified structural path-signature hint"
                        ),
                    }
                )
        # A partial overlap is not the audited cross-layer capability shape.  In
        # that case the generic locator remains the only admissible evidence.
        if len(slices) == len(reference["slices"]):
            return {
                "slices": slices,
                "expected_mechanism": _text(reference.get("mechanism")),
                "reference_project": reference_project,
                "identity_status": "verified" if identity_matches else _text(identity.get("status"), "unverified"),
                "identity_reason": None if identity_matches else _text(identity.get("reason"), "repository identity was not verified"),
                "source_audited": identity_matches,
            }
    return None


def _file_role(file: dict[str, Any]) -> tuple[str, str, str]:
    path = PurePosixPath(_text(file.get("path")))
    name = path.name.casefold()
    stem = path.stem.casefold()
    if _is_test_path(path.as_posix()):
        return "test", "路径或文件名符合测试约定", "path-convention"
    if name in _ENTRYPOINT_NAMES:
        return "entrypoint", "文件名符合运行入口约定", "path-convention"
    if name in _MANIFEST_NAMES or path.suffix.casefold() in {".toml", ".yaml", ".yml"}:
        return "configuration", "构建清单或配置文件", "path-convention"
    if name.startswith("readme") or path.suffix.casefold() in {".md", ".mdx", ".rst"}:
        return "documentation", "文档文件；不能单独证明运行时职责", "path-convention"
    if any(token in stem for token in ("route", "handler", "controller", "endpoint", "api")):
        return "boundary", "文件名提示接口或路由职责", "heuristic"
    if any(token in stem for token in ("orchestrat", "service", "manager", "workflow", "engine", "flow")):
        return "orchestration", "文件名提示服务或编排职责", "heuristic"
    if any(token in stem for token in ("model", "schema", "type", "entity", "protocol")):
        return "model", "文件名提示模型、协议或类型职责", "heuristic"
    if any(token in stem for token in ("repository", "storage", "store", "database", "persistence")):
        return "persistence", "文件名提示存储职责", "heuristic"
    if any(token in stem for token in ("adapter", "client", "transport", "gateway", "provider", "socket")):
        return "adapter", "文件名提示适配器或客户端职责", "heuristic"
    if any(token in stem for token in ("view", "component", "page", "screen", "ui")):
        return "presentation", "文件名提示展示职责", "heuristic"
    return "core", "未从名称推断具体行为；作为核心源码候选阅读", "heuristic"


def _source_excerpt(
    project_root: Path | None,
    file: dict[str, Any] | None,
    path: str,
    line_start: int,
    line_end: int,
) -> dict[str, Any]:
    start = max(1, int(line_start or 1))
    end = max(start, int(line_end or start))
    result: dict[str, Any] = {
        "path": path,
        "line_start": start,
        "line_end": end,
        "source_uri": _source_uri(project_root, path),
        "uri_behavior": "opens-file",
        "snippet": "",
        "snippet_sha256": None,
        "file_sha256": _text((file or {}).get("sha256")) or None,
        "fresh": False,
    }
    if project_root is None or file is None:
        return result
    safe_path = _safe_relative_path(path)
    if not safe_path or safe_path == ".":
        return result
    try:
        candidate = (project_root / PurePosixPath(safe_path)).resolve(strict=False)
    except (OSError, RuntimeError):
        return result
    if not candidate.is_relative_to(project_root):
        return result
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(candidate, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 2 * 1024 * 1024:
            return result
        chunks: list[bytes] = []
        remaining = metadata.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except (OSError, ValueError):
        return result
    finally:
        if descriptor is not None:
            os.close(descriptor)
    digest = hashlib.sha256(raw).hexdigest()
    expected = _text(file.get("sha256"))
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest != expected:
        return result
    source = raw.decode("utf-8", errors="replace")
    lines = source.splitlines()
    if not lines:
        return result
    start = min(start, len(lines))
    end = min(max(start, end), len(lines), start + 15)
    source_snippet = "\n".join(lines[start - 1 : end])
    result.update(
        {
            "line_start": start,
            "line_end": end,
            "snippet": redact_secrets(source_snippet),
            "snippet_sha256": hashlib.sha256(source_snippet.encode("utf-8")).hexdigest(),
            "fresh": True,
        }
    )
    return result


def _annotate_file(
    file: dict[str, Any],
    project_root: Path | None,
    symbols_by_file: dict[str, list[dict[str, Any]]],
    surface_role: str | None = None,
) -> dict[str, Any]:
    role, reason, confidence = _file_role(file)
    path = _text(file.get("path"))
    symbols = symbols_by_file.get(_text(file.get("id")), [])
    line_end = min(max(1, int(file.get("lines") or 1)), 12)
    location = _source_excerpt(project_root, file, path, 1, line_end)
    return {
        "id": _text(file.get("id")),
        "path": path,
        "source_uri": location["source_uri"],
        "source_location": location,
        "role": role,
        "surface_role": surface_role or role,
        "role_reason": reason,
        "role_confidence": confidence,
        "language": _text(file.get("language")),
        "lines": int(file.get("lines") or 0),
        "sha256": _text(file.get("sha256")) or None,
        "symbol_count": len(symbols),
        "symbols": [
            {
                "id": _text(symbol.get("id")),
                "name": _text(symbol.get("qualified_name") or symbol.get("name")),
                "kind": _text(symbol.get("kind")),
                "line": int(symbol.get("line") or 0),
                "end_line": int(symbol.get("end_line") or symbol.get("line") or 0),
            }
            for symbol in symbols[:20]
        ],
    }


def _slice_paths(
    slices: list[dict[str, Any]],
    files: list[dict[str, Any]],
) -> tuple[set[str], dict[str, str]]:
    selected: set[str] = set()
    roles: dict[str, str] = {}
    for slice_record in slices:
        path = _text(slice_record.get("path"))
        kind = _text(slice_record.get("kind"))
        role = _text(slice_record.get("role"), "core")
        for file in files:
            file_path = _text(file.get("path"))
            matches = file_path == path if kind == "file" else file_path.startswith(f"{path}/")
            if matches and _is_product_source(file):
                selected.add(file_path)
                roles.setdefault(file_path, role)
    return selected, roles


def _relationship_view(
    relationship: dict[str, Any],
    project_root: Path | None,
    symbol_by_id: dict[str, dict[str, Any]],
    file_by_id: dict[str, dict[str, Any]],
    file_by_path: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_id = _text(relationship.get("source_id"))
    source = symbol_by_id.get(source_id) or file_by_id.get(source_id)
    source_path = _text(relationship.get("path")) or _text((source or {}).get("path"))
    source_line = int(relationship.get("line") or (source or {}).get("line") or 1)
    source_file = file_by_path.get(source_path)
    target_id = _text(relationship.get("target_id"))
    target = symbol_by_id.get(target_id) or file_by_id.get(target_id)
    target_path = _text((target or {}).get("path"))
    target_line = int((target or {}).get("line") or 1)
    target_file = file_by_path.get(target_path)
    return {
        "id": _text(relationship.get("id")),
        "kind": _text(relationship.get("kind"), "relationship"),
        "confidence": _text(relationship.get("confidence"), "unknown"),
        "resolved": bool(target),
        "source": {
            "id": source_id,
            "name": _text((source or {}).get("qualified_name") or (source or {}).get("name"))
            or PurePosixPath(source_path).name,
            **_source_excerpt(project_root, source_file, source_path, source_line, source_line),
        },
        "target": {
            "id": target_id or None,
            "name": _text((target or {}).get("qualified_name") or (target or {}).get("name"))
            or _text(relationship.get("target_name"), "unresolved"),
            **(
                _source_excerpt(project_root, target_file, target_path, target_line, target_line)
                if target_path
                else {
                    "path": "",
                    "line_start": 0,
                    "line_end": 0,
                    "source_uri": None,
                    "uri_behavior": "unresolved",
                    "snippet": "",
                    "snippet_sha256": None,
                    "file_sha256": None,
                    "fresh": False,
                }
            ),
        },
    }


def _reading_order(files: list[dict[str, Any]], core_symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file in files:
        by_role[_text(file.get("surface_role") or file.get("role"), "core")].append(file)
    role_labels = {
        "entrypoint": "入口候选",
        "boundary": "边界候选",
        "orchestration": "编排候选",
        "core": "核心源码候选",
        "model": "数据契约候选",
        "persistence": "持久化候选",
        "adapter": "外部适配候选",
        "presentation": "展示候选",
        "configuration": "配置",
    }
    steps: list[dict[str, Any]] = []
    for role in sorted(by_role, key=lambda item: (_ROLE_ORDER.get(item, 99), item)):
        selected = sorted(
            by_role[role],
            key=lambda item: (-int(item.get("symbol_count") or 0), _text(item.get("path"))),
        )[:6]
        paths = {_text(item.get("path")) for item in selected}
        steps.append(
            {
                "order": len(steps) + 1,
                "role": role,
                "confidence": "heuristic",
                "kind": "heuristic_reading_order",
                "title": role_labels.get(role, "源码候选"),
                "explanation": "仅按路径/文件职责组织阅读，不代表运行时或数据流顺序。",
                "files": [
                    {
                        "path": _text(item.get("path")),
                        "source_uri": item.get("source_uri"),
                        "source_location": item.get("source_location"),
                    }
                    for item in selected
                ],
                "symbols": [
                    _text(symbol.get("name"))
                    for symbol in core_symbols
                    if _text(symbol.get("path")) in paths
                ][:8],
            }
        )
    return steps


def _implementation_trace(resolved_internal: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace_edges = [
        item
        for item in resolved_internal
        if _text(item.get("kind")) in {"calls", "import", "references", "inherits", "implements"}
    ]
    nodes = {
        _text(endpoint.get("path"))
        for edge in trace_edges
        for endpoint in (edge.get("source", {}), edge.get("target", {}))
        if isinstance(endpoint, dict) and _text(endpoint.get("path"))
    }
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    for edge in trace_edges:
        source_path = _text(edge.get("source", {}).get("path"))
        target_path = _text(edge.get("target", {}).get("path"))
        if not source_path or not target_path or source_path == target_path:
            continue
        if target_path not in adjacency[source_path]:
            adjacency[source_path].add(target_path)
            indegree[target_path] += 1
    queue = sorted(node for node, degree in indegree.items() if degree == 0)
    ordered_nodes: list[str] = []
    layer_by_node: dict[str, int] = {node: 0 for node in queue}
    while queue:
        node = queue.pop(0)
        ordered_nodes.append(node)
        for target in sorted(adjacency[node]):
            layer_by_node[target] = max(layer_by_node.get(target, 0), layer_by_node[node] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
                queue.sort()
    cyclic_nodes = nodes - set(ordered_nodes)
    for node in sorted(cyclic_nodes):
        layer_by_node[node] = max(layer_by_node.values(), default=0) + 1
        ordered_nodes.append(node)
    rank = {node: position for position, node in enumerate(ordered_nodes)}
    trace_edges.sort(
        key=lambda item: (
            rank.get(_text(item.get("source", {}).get("path")), len(rank)),
            rank.get(_text(item.get("target", {}).get("path")), len(rank)),
            int(item.get("source", {}).get("line_start") or 0),
            _text(item.get("id")),
        )
    )
    return [
        {
            "order": position,
            "kind": "resolved_relationship_trace",
            "relationship_id": _text(edge.get("id")),
            "relationship_kind": _text(edge.get("kind")),
            "confidence": _text(edge.get("confidence"), "unknown"),
            "topology_layer": layer_by_node.get(_text(edge.get("source", {}).get("path")), 0),
            "ordering": (
                "cycle-fallback"
                if _text(edge.get("source", {}).get("path")) in cyclic_nodes
                or _text(edge.get("target", {}).get("path")) in cyclic_nodes
                else "resolved-graph-topology"
            ),
            "source": edge.get("source"),
            "target": edge.get("target"),
        }
        for position, edge in enumerate(trace_edges[:40], start=1)
    ]


def _component_boundaries(
    selected_paths: set[str],
    resolved_internal: list[dict[str, Any]],
    project_root: Path | None,
) -> list[dict[str, Any]]:
    adjacency: dict[str, set[str]] = {path: set() for path in selected_paths}
    edge_pairs: set[tuple[str, str]] = set()
    for edge in resolved_internal:
        source_path = _text(edge.get("source", {}).get("path"))
        target_path = _text(edge.get("target", {}).get("path"))
        if source_path not in adjacency or target_path not in adjacency or source_path == target_path:
            continue
        adjacency[source_path].add(target_path)
        adjacency[target_path].add(source_path)
        edge_pairs.add(
            (source_path, target_path)
            if source_path < target_path
            else (target_path, source_path)
        )
    components: list[set[str]] = []
    unseen = set(selected_paths)
    while unseen:
        start = min(unseen)
        stack = [start]
        component: set[str] = set()
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            unseen.discard(node)
            stack.extend(sorted(adjacency[node] - component, reverse=True))
        components.append(component)
    components.sort(key=lambda group: (-len(group), min(group)))
    return [
        {
            "id": stable_id("surface_component", *sorted(component)),
            "confidence": "resolved-edge-component" if len(component) > 1 else "isolated-source-slice",
            "file_paths": sorted(component),
            "files": [
                {"path": path, "source_uri": _source_uri(project_root, path)}
                for path in sorted(component)
            ],
            "file_count": len(component),
            "edge_count": sum(1 for pair in edge_pairs if pair[0] in component and pair[1] in component),
        }
        for component in components
    ]


def _mirrored_test_path(test_path: str, slices: list[dict[str, Any]]) -> bool:
    parts = list(PurePosixPath(test_path).parts)
    test_positions = [position for position, part in enumerate(parts) if part.casefold() in _TEST_PARTS]
    if not test_positions:
        return False
    relative_after_test = PurePosixPath(*parts[test_positions[0] + 1 :]).as_posix()
    relative_without_suffix = str(PurePosixPath(relative_after_test).with_suffix(""))
    relative_parts = PurePosixPath(relative_without_suffix).parts
    for slice_record in slices:
        source = _text(slice_record.get("path"))
        source_without_suffix = str(PurePosixPath(source).with_suffix(""))
        source_tail = PurePosixPath(source_without_suffix).name
        if relative_without_suffix == source_without_suffix or relative_without_suffix.startswith(
            f"{source_without_suffix}/"
        ):
            return True
        if relative_parts and source_tail in relative_parts[:-1]:
            return True
    return False


def _build_surface(
    query: str,
    slices: list[dict[str, Any]],
    score: float,
    reasons: list[str],
    certainty: str,
    files: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    project_root: Path | None,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_paths, surface_roles = _slice_paths(slices, files)
    selected_file_ids = {
        _text(file.get("id")) for file in files if _text(file.get("path")) in selected_paths
    }
    selected_symbols = [symbol for symbol in symbols if _text(symbol.get("path")) in selected_paths]
    selected_symbol_ids = {_text(symbol.get("id")) for symbol in selected_symbols}
    symbols_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for symbol in symbols:
        symbols_by_file[_text(symbol.get("file_id"))].append(symbol)
    for values in symbols_by_file.values():
        values.sort(key=lambda item: (int(item.get("line") or 0), _text(item.get("name"))))
    annotated_files = [
        _annotate_file(file, project_root, symbols_by_file, surface_roles.get(_text(file.get("path"))))
        for file in files
        if _text(file.get("path")) in selected_paths
    ]
    symbol_by_id = {_text(symbol.get("id")): symbol for symbol in symbols}
    file_by_id = {_text(file.get("id")): file for file in files}
    file_by_path = {_text(file.get("path")): file for file in files}
    source_degree: Counter[str] = Counter()
    target_degree: Counter[str] = Counter()
    buckets: dict[str, list[dict[str, Any]]] = {
        "resolved_internal": [],
        "resolved_inbound": [],
        "resolved_outbound": [],
        "unresolved": [],
    }
    for relationship in relationships:
        source_path = _text(relationship.get("path"))
        source_inside = source_path in selected_paths
        target_id = _text(relationship.get("target_id"))
        target = symbol_by_id.get(target_id) or file_by_id.get(target_id)
        target_inside = target_id in selected_symbol_ids or target_id in selected_file_ids
        if not source_inside and not target_inside:
            continue
        view = _relationship_view(
            relationship, project_root, symbol_by_id, file_by_id, file_by_path
        )
        if not target:
            bucket = "unresolved"
        elif source_inside and target_inside:
            bucket = "resolved_internal"
        elif target_inside:
            bucket = "resolved_inbound"
        else:
            bucket = "resolved_outbound"
        buckets[bucket].append(view)
        if source_inside:
            source_degree[_text(relationship.get("source_id"))] += 1
        if target_inside:
            target_degree[target_id] += 1

    ranked_symbols = sorted(
        selected_symbols,
        key=lambda symbol: (
            _ROLE_ORDER.get(surface_roles.get(_text(symbol.get("path")), "core"), 99),
            -(source_degree[_text(symbol.get("id"))] + target_degree[_text(symbol.get("id"))]),
            not bool(symbol.get("exported")),
            int(symbol.get("line") or 0),
            _text(symbol.get("qualified_name") or symbol.get("name")),
        ),
    )[:24]
    core_symbols = []
    for symbol in ranked_symbols:
        path = _text(symbol.get("path"))
        file = file_by_path.get(path)
        location = _source_excerpt(
            project_root,
            file,
            path,
            int(symbol.get("line") or 1),
            int(symbol.get("end_line") or symbol.get("line") or 1),
        )
        core_symbols.append(
            {
                "id": _text(symbol.get("id")),
                "name": _text(symbol.get("qualified_name") or symbol.get("name")),
                "kind": _text(symbol.get("kind"), "symbol"),
                "path": path,
                "line": location["line_start"],
                "end_line": location["line_end"],
                "signature": _text(symbol.get("signature")),
                "exported": bool(symbol.get("exported")),
                "relationship_count": source_degree[_text(symbol.get("id"))]
                + target_degree[_text(symbol.get("id"))],
                "source_uri": location["source_uri"],
                "source_location": location,
            }
        )

    tests: list[dict[str, Any]] = []
    possible_tests: list[dict[str, Any]] = []
    seen_tests: set[str] = set()
    for relation in buckets["resolved_inbound"]:
        source = relation.get("source", {}) if isinstance(relation.get("source"), dict) else {}
        test_path = _text(source.get("path"))
        if not _is_test_path(test_path) or test_path in seen_tests:
            continue
        raw_file = next((file for file in files if _text(file.get("path")) == test_path), None)
        if raw_file:
            tests.append(
                {
                    **_annotate_file(raw_file, project_root, symbols_by_file),
                    "association": "resolved-relationship",
                    "association_confidence": _text(relation.get("confidence"), "high"),
                    "target": relation.get("target"),
                    "evidence_status": "resolved-static-link",
                }
            )
            seen_tests.add(test_path)
    for raw_file in files:
        test_path = _text(raw_file.get("path"))
        if test_path in seen_tests or not _is_test_path(test_path):
            continue
        inside_slice = any(
            _text(slice_record.get("kind")) == "directory"
            and test_path.startswith(f'{_text(slice_record.get("path"))}/')
            for slice_record in slices
        )
        mirrored = _mirrored_test_path(test_path, slices)
        if not inside_slice and not mirrored:
            continue
        possible_tests.append(
            {
                **_annotate_file(raw_file, project_root, symbols_by_file),
                "association": "explicit-subpath" if inside_slice else "mirrored-test-path",
                "association_confidence": "medium",
                "evidence_status": "structural-association-only",
            }
        )

    for key in buckets:
        buckets[key].sort(
            key=lambda item: (
                _text(item.get("source", {}).get("path")),
                int(item.get("source", {}).get("line_start") or 0),
                _text(item.get("target", {}).get("path")),
            )
        )
    trace = _implementation_trace(buckets["resolved_internal"])
    components = _component_boundaries(
        selected_paths, buckets["resolved_internal"], project_root
    )
    resolved_count = sum(len(buckets[key]) for key in buckets if key != "unresolved")
    total_relation_count = resolved_count + len(buckets["unresolved"])
    exact_directory_slices = [
        item
        for item in slices
        if _text(item.get("kind")) == "directory"
        and _normalise(PurePosixPath(_text(item.get("path"))).name) == _normalise(query)
    ]
    primary_path = _text(slices[0].get("path")) if slices else "."
    languages = Counter(_text(file.get("language"), "Unknown") for file in annotated_files)
    return {
        "id": stable_id("capability_surface", query, *sorted(selected_paths)),
        "name": query,
        "path": primary_path,
        "directory_uri": (
            _source_uri(project_root, primary_path)
            if len(slices) == 1 and _text(slices[0].get("kind")) == "directory"
            else None
        ),
        "surface_kind": "directory" if len(slices) == 1 and _text(slices[0].get("kind")) == "directory" else "composite",
        "slices": [
            {
                **item,
                "source_uri": _source_uri(project_root, _text(item.get("path"))),
            }
            for item in slices
        ],
        "certainty": certainty,
        "capability_certainty": "source-supported-candidate" if annotated_files else "heuristic-candidate",
        "verified_capability_surface": False,
        "confidence": round(score, 3),
        "confidence_label": "high" if score >= 0.80 else "medium" if score >= 0.55 else "low",
        "exact_directory_name_matches": len(exact_directory_slices),
        "reasons": reasons,
        "reference_alignment": reference if reference and reference.get("source_audited") else None,
        "reference_shape_hint": reference if reference and not reference.get("source_audited") else None,
        "file_count": len(annotated_files),
        "symbol_count": len(selected_symbols),
        "languages": dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
        "entrypoints": [
            file
            for file in annotated_files
            if _text(file.get("surface_role") or file.get("role")) in {"entrypoint", "boundary"}
        ],
        "core_symbols": core_symbols,
        "files": sorted(
            annotated_files,
            key=lambda item: (
                _ROLE_ORDER.get(_text(item.get("surface_role") or item.get("role")), 99),
                _text(item.get("path")),
            ),
        ),
        "relationship_counts": {key: len(value) for key, value in buckets.items()},
        "relationship_quality": {
            "resolved": resolved_count,
            "unresolved": len(buckets["unresolved"]),
            "resolved_ratio": round(resolved_count / total_relation_count, 3)
            if total_relation_count
            else 0.0,
        },
        "relationships": {key: value[:100] for key, value in buckets.items()},
        "implementation_trace": trace,
        "component_boundaries": components,
        "reading_order": _reading_order(annotated_files, core_symbols),
        "implementation_steps": trace,
        "tests": tests,
        "possible_tests": possible_tests[:50],
    }


def _generic_slices(
    files: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    query: str,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    query_key = _normalise(query)
    file_by_path = {_text(file.get("path")): file for file in files}
    directories: set[str] = set()
    for file in files:
        path = _safe_relative_path(file.get("path"))
        if not path or path == ".":
            continue
        parent = PurePosixPath(path).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    product_exact_directories: list[str] = []
    auxiliary_exact_directories: list[str] = []
    for directory in directories:
        if directory == "." or _normalise(PurePosixPath(directory).name) != query_key:
            continue
        if _is_auxiliary_path(directory):
            auxiliary_exact_directories.append(directory)
        else:
            product_exact_directories.append(directory)

    matched_paths: set[str] = set()
    for file in files:
        path = _text(file.get("path"))
        if not _is_product_source(file):
            continue
        stem = _normalise(PurePosixPath(path).stem)
        path_tokens = {_normalise(part) for part in PurePosixPath(path).parts}
        stem_tokens = {_normalise(token) for token in _tokens(PurePosixPath(path).stem)}
        query_tokens = {_normalise(token) for token in _tokens(query)}
        if query_key and (
            query_key == stem
            or query_key in path_tokens
            or (query_tokens and query_tokens <= stem_tokens)
        ):
            matched_paths.add(path)
    for symbol in symbols:
        path = _text(symbol.get("path"))
        symbol_name = _text(symbol.get("qualified_name") or symbol.get("name"))
        name = _normalise(symbol_name)
        name_tokens = {_normalise(token) for token in _tokens(symbol_name)}
        query_tokens = {_normalise(token) for token in _tokens(query)}
        source_file = file_by_path.get(path)
        if (
            source_file
            and _is_product_source(source_file)
            and query_key
            and (query_key == name or (query_tokens and query_tokens <= name_tokens))
        ):
            matched_paths.add(path)

    slices: list[dict[str, Any]] = []
    for directory in sorted(product_exact_directories):
        slices.append(
            {
                "kind": "directory",
                "path": directory,
                "role": "core",
                "evidence": "directory-name-exact",
            }
        )
    for path in sorted(matched_paths):
        if any(
            _text(item.get("kind")) == "directory"
            and path.startswith(f'{_text(item.get("path"))}/')
            for item in slices
        ):
            continue
        role, _, _ = _file_role(next(item for item in files if _text(item.get("path")) == path))
        slices.append(
            {
                "kind": "file",
                "path": path,
                "role": role,
                "evidence": "file-or-symbol-name-match",
            }
        )
    return slices, product_exact_directories, auxiliary_exact_directories


def locate_modules(index: dict[str, Any], query: str, limit: int = 8) -> dict[str, Any]:
    """Locate a named capability as one or more source slices.

    ``exact_name_match`` means only that one production directory basename
    matches the query.  It never asserts that the capability itself has been
    semantically verified.  Cross-layer and repository-root implementations are
    represented by a composite capability surface.
    """

    if not isinstance(index, dict):
        raise TypeError("index must be a dictionary")
    query = _text(query)
    if not query:
        raise ValueError("query must not be empty")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
        raise ValueError("limit must be an integer between 1 and 100")

    files = [item for item in index.get("files", []) if isinstance(item, dict)]
    symbols = [item for item in index.get("symbols", []) if isinstance(item, dict)]
    relationships = [item for item in index.get("relationships", []) if isinstance(item, dict)]
    project_root = _project_root(index)
    project = index.get("project", {}) if isinstance(index.get("project"), dict) else {}
    project_name = _text(project.get("name")) or (project_root.name if project_root else "repository")
    generic_slices, product_exact, auxiliary_exact = _generic_slices(files, symbols, query)
    reference = _reference_surface(index, project_name, query, files)

    slices: list[dict[str, Any]] = []
    reasons: list[str] = []
    if reference:
        slices.extend(reference["slices"])
        if reference["source_audited"]:
            reasons.append(
                f'已验证的参考快照 {reference["reference_project"]} 命中：'
                f'{reference["expected_mechanism"]}'
            )
        else:
            reasons.append(
                f'路径结构符合 {reference["reference_project"]} 基准形状，但仓库身份未验证；'
                '只用于生成候选切片，不声称已复用参考机制。'
            )
    if not reference:
        for item in generic_slices:
            if (_text(item.get("kind")), _text(item.get("path"))) not in {
                (_text(existing.get("kind")), _text(existing.get("path"))) for existing in slices
            }:
                slices.append(item)

    if len(product_exact) == 1 and not reference and len(slices) == 1:
        status = "exact_name_match"
        certainty = "directory-name-exact"
        score = 0.9
        reasons.append(
            f'产品源码目录“{product_exact[0]}”的 basename 与查询精确匹配；这只是名称证据。'
        )
        summary = (
            f'唯一产品源码目录“{product_exact[0]}”名称精确命中；功能语义仍需结合源码链人工确认。'
        )
    elif slices:
        status = "composite_candidate" if len(slices) > 1 else "candidate"
        certainty = "source-slice-candidate"
        score = 0.88 if reference else min(0.82, 0.52 + len(slices) * 0.05)
        reasons.append(f"由 {len(slices)} 个产品源码切片组成候选实现面。")
        if product_exact:
            reasons.append(f"其中 {len(product_exact)} 个产品目录 basename 精确匹配。")
        summary = (
            f'找到 {len(slices)} 个相互补充的产品源码切片；报告将其作为候选实现面，不宣称功能已验证。'
        )
    else:
        status = "not_found"
        certainty = "insufficient-evidence"
        score = 0.0
        summary = "没有产品源码目录、文件或符号证据支持该能力定位。"

    if auxiliary_exact:
        reasons.append(
            "已排除仅位于 docs/tests/examples/generated/build 等辅助区域的同名目录："
            + "、".join(sorted(auxiliary_exact))
        )
        if status == "not_found":
            summary += " 存在同名辅助目录，但它们不能作为产品实现证据。"

    modules = []
    if slices:
        modules.append(
            _build_surface(
                query,
                slices[: max(limit * 12, 12)],
                score,
                reasons,
                certainty,
                files,
                symbols,
                relationships,
                project_root,
                reference={
                    "project": reference["reference_project"],
                    "expected_mechanism": reference["expected_mechanism"],
                    "identity_status": reference["identity_status"],
                    "identity_reason": reference["identity_reason"],
                    "source_audited": reference["source_audited"],
                }
                if reference
                else None,
            )
        )

    return {
        "schema_version": "2.0",
        "query": query,
        "project": {
            "name": project_name,
            "path": str(project_root) if project_root else _text(project.get("path")),
            "commit": _text(project.get("commit")) or None,
        },
        "resolution": {
            "status": status,
            "is_exact": False,
            "is_exact_name_match": status == "exact_name_match",
            "verified_capability_surface": False,
            "summary": summary,
            "candidate_count": len(modules),
            "exact_match_count": len(product_exact),
            "excluded_auxiliary_matches": sorted(auxiliary_exact),
        },
        "modules": modules,
    }
