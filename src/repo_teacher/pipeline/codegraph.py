"""Deterministic CodeGraph evidence acquisition for report pipelines."""

from __future__ import annotations

import copy
import hashlib
import os
import shutil
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Sequence

from .paths import path_is_within_modules as _path_is_within_modules
from .paths import repo_path_parts as _repo_path_parts
from .module_scope import module_view_category as _module_view_category


def _source_paths(value: object) -> set[str]:
    """Collect path fields without depending on evidence-packet construction."""

    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "source_path", "target_path"} and isinstance(item, str):
                if _repo_path_parts(item):
                    found.add(item)
            else:
                found.update(_source_paths(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_source_paths(item))
    return found

def _find_codegraph() -> str | None:
    configured = os.environ.get("REPO_TEACHER_CODEGRAPH_BIN", "").strip()
    if configured and Path(configured).is_file():
        return configured
    discovered = shutil.which("codegraph")
    if discovered:
        return discovered
    fallback = Path.home() / ".local" / "bin" / "codegraph"
    return str(fallback) if fallback.is_file() else None


def _prepare_codegraph(source: Path) -> str:
    """Build or refresh the repository relationship graph before a report."""

    executable = _find_codegraph()
    if executable is None:
        raise ValueError(
            "CodeGraph is required for report generation but no codegraph binary was found"
        )
    database = source / ".codegraph" / "codegraph.db"
    action = "sync" if database.is_file() else "init"
    process = subprocess.run(
        [executable, action, str(source)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "CodeGraph failed").strip()
        raise ValueError(f"CodeGraph {action} failed: {detail[-2_000:]}")
    return action


def _codegraph_domain_context(
    source: Path,
    module_paths: Sequence[str],
    *,
    max_paths: int = 64,
    max_nodes: int = 192,
    max_edges: int = 384,
) -> dict[str, object]:
    """Return a bounded, structured relationship slice for one product domain.

    Selection is based on resolved graph connectivity and repository path
    containment.  Names and source text are deliberately not scored, so a
    route name, keyword, or regex match cannot promote something to a product
    capability.
    """

    database = source / ".codegraph" / "codegraph.db"
    if not database.is_file():
        raise ValueError("CodeGraph database is missing after initialization")
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        node_rows = connection.execute(
            """
            SELECT id, kind, name, qualified_name, file_path, language,
                   start_line, end_line
            FROM nodes
            ORDER BY file_path, start_line, id
            """
        ).fetchall()
        edge_rows = connection.execute(
            """
            SELECT id, source, target, kind, line
            FROM edges
            ORDER BY id
            """
        ).fetchall()

    scoped_nodes = {
        str(row["id"]): row
        for row in node_rows
        if isinstance(row["file_path"], str)
        and _path_is_within_modules(str(row["file_path"]), module_paths)
        and _module_view_category(str(row["file_path"])) == "product-implementation"
    }
    degree = {identifier: 0 for identifier in scoped_nodes}
    scoped_edges: list[sqlite3.Row] = []
    for edge in edge_rows:
        source_id = str(edge["source"])
        target_id = str(edge["target"])
        if source_id not in scoped_nodes or target_id not in scoped_nodes:
            continue
        degree[source_id] += 1
        degree[target_id] += 1
        scoped_edges.append(edge)

    path_degree: dict[str, int] = {}
    for identifier, row in scoped_nodes.items():
        path = str(row["file_path"])
        path_degree[path] = path_degree.get(path, 0) + degree[identifier]
    ranked_paths = sorted(path_degree, key=lambda path: (-path_degree[path], path))
    selected_paths = set(ranked_paths[:max_paths])
    ranked_node_ids = sorted(
        (
            identifier
            for identifier, row in scoped_nodes.items()
            if str(row["file_path"]) in selected_paths
        ),
        key=lambda identifier: (
            -degree[identifier],
            str(scoped_nodes[identifier]["file_path"]),
            int(scoped_nodes[identifier]["start_line"]),
            identifier,
        ),
    )[:max_nodes]
    selected_node_ids = set(ranked_node_ids)
    nodes = [
        {
            "id": identifier,
            "kind": str(scoped_nodes[identifier]["kind"]),
            "qualified_name": str(scoped_nodes[identifier]["qualified_name"]),
            "path": str(scoped_nodes[identifier]["file_path"]),
            "line_start": int(scoped_nodes[identifier]["start_line"]),
            "line_end": int(scoped_nodes[identifier]["end_line"]),
            "degree": degree[identifier],
        }
        for identifier in ranked_node_ids
    ]
    edges = []
    for edge in sorted(
        scoped_edges,
        key=lambda item: (
            -(degree[str(item["source"])] + degree[str(item["target"])]),
            int(item["id"]),
        ),
    ):
        source_id = str(edge["source"])
        target_id = str(edge["target"])
        if source_id not in selected_node_ids or target_id not in selected_node_ids:
            continue
        source_node = scoped_nodes[source_id]
        target_node = scoped_nodes[target_id]
        edges.append(
            {
                "id": str(edge["id"]),
                "kind": str(edge["kind"]),
                "source": str(source_node["qualified_name"]),
                "source_path": str(source_node["file_path"]),
                "target": str(target_node["qualified_name"]),
                "target_path": str(target_node["file_path"]),
                "line": int(edge["line"]) if edge["line"] is not None else None,
            }
        )
        if len(edges) >= max_edges:
            break
    return {
        "selection_basis": "resolved graph connectivity; no name or text matching",
        "module_paths": list(module_paths),
        "source_paths": sorted(selected_paths),
        "nodes": nodes,
        "edges": edges,
    }


def _augment_pack_with_codegraph_context(
    pack: dict[str, object], codegraph_context: dict[str, object]
) -> dict[str, object]:
    """Bind graph-only source paths into the same evidence closure as the index.

    These records are navigation anchors, not product capability claims.  They
    let the global model cite graph-central implementation that had no route or
    CLI seed while keeping every returned reference schema-valid downstream.
    """

    augmented = copy.deepcopy(pack)
    evidence = [
        item for item in augmented.get("evidence", []) if isinstance(item, dict)
    ]
    hints = [
        item
        for item in augmented.get("feature_hints", [])
        if isinstance(item, dict)
    ]
    evidence_paths = _source_paths(evidence)
    nodes_by_path: dict[str, list[dict[str, object]]] = {}
    for node in codegraph_context.get("nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("path"), str):
            continue
        nodes_by_path.setdefault(str(node["path"]), []).append(node)
    for path in codegraph_context.get("source_paths", []):
        if not isinstance(path, str) or not _repo_path_parts(path):
            continue
        if path in evidence_paths:
            continue
        path_nodes = nodes_by_path.get(path, [])
        starts = [
            int(node["line_start"])
            for node in path_nodes
            if isinstance(node.get("line_start"), int)
        ]
        ends = [
            int(node["line_end"])
            for node in path_nodes
            if isinstance(node.get("line_end"), int)
        ]
        line_start = min(starts, default=1)
        line_end = max(ends, default=line_start)
        digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
        evidence_id = f"evidence_codegraph_{digest}"
        feature_id = f"feature_codegraph_{digest}"
        evidence.append(
            {
                "id": evidence_id,
                "kind": "graph-navigation-slice",
                "path": path,
                "line_start": line_start,
                "line_end": line_end,
                "confidence": "navigation-only",
                "analyzer": "codegraph-resolved-connectivity",
            }
        )
        hints.append(
            {
                "id": feature_id,
                "kind": "graph-navigation-candidate",
                "source": "codegraph-navigation",
                "confidence": "navigation-only",
                "entrypoint": path,
                "evidence_ids": [evidence_id],
                "steps": [
                    {
                        "path": path,
                        "line_start": line_start,
                        "line_end": line_end,
                        "evidence_ids": [evidence_id],
                    }
                ],
            }
        )
    augmented["evidence"] = evidence
    augmented["feature_hints"] = hints
    return augmented


def filter_codegraph_context(
    context: dict[str, object], module_paths: Sequence[str]
) -> dict[str, object]:
    """Return a module-scoped CodeGraph slice with closed edge endpoints.

    A global context may be used to augment the canonical pack, but it must
    never be copied wholesale into every model shard.  Both edge endpoints
    must belong to the shard; cross-shard edges remain available in the global
    merge packet instead of being duplicated into unrelated reads.
    """

    def in_scope(path: object) -> bool:
        return isinstance(path, str) and _path_is_within_modules(path, module_paths)

    source_paths = sorted(
        {
            path
            for path in context.get("source_paths", [])
            if in_scope(path)
        }
    )
    nodes = [
        copy.deepcopy(node)
        for node in context.get("nodes", [])
        if isinstance(node, dict) and in_scope(node.get("path"))
    ]
    edges = [
        copy.deepcopy(edge)
        for edge in context.get("edges", [])
        if isinstance(edge, dict)
        and in_scope(edge.get("source_path"))
        and in_scope(edge.get("target_path"))
    ]
    return {
        "selection_basis": context.get("selection_basis"),
        "module_paths": list(module_paths),
        "source_paths": source_paths,
        "nodes": nodes,
        "edges": edges,
    }


CODEGRAPH_EXPLORE_BYTE_BUDGET = 80_000


def _bounded_explore_text(value: str) -> str:
    """Bound CodeGraph prose by UTF-8 bytes and mark every truncation."""

    encoded = value.encode("utf-8")
    if len(encoded) <= CODEGRAPH_EXPLORE_BYTE_BUDGET:
        return value
    marker = (
        "\n\n[REPOLENS: CodeGraph 输出超过证据包预算；已保留首尾窗口，"
        f"原始 {len(encoded)} bytes，included <= {CODEGRAPH_EXPLORE_BYTE_BUDGET} bytes]\n\n"
    ).encode("utf-8")
    window = (CODEGRAPH_EXPLORE_BYTE_BUDGET - len(marker)) // 2
    head = encoded[:window].decode("utf-8", errors="ignore")
    tail = encoded[-window:].decode("utf-8", errors="ignore")
    return head + marker.decode("utf-8") + tail


def _codegraph_explore_domain(source: Path, module_paths: Sequence[str]) -> str:
    """Retrieve a bounded symbol-and-call-path reading for one business domain."""

    executable = _find_codegraph()
    if executable is None:
        raise ValueError(
            "CodeGraph is required for report generation but no codegraph binary was found"
        )
    modules = ", ".join(module_paths)
    query = (
        "Trace user-facing business capabilities through real symbols and call paths in "
        f"these modules: {modules}. Identify the user action, state writes, queue or "
        "worker handoff, runtime execution, deployment, and observable result when present. "
        "Do not promote health checks, login shells, test fixtures, or route registration."
    )
    process = subprocess.run(
        [
            executable,
            "explore",
            "--path",
            str(source),
            "--max-files",
            "16",
            query,
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "CodeGraph explore failed").strip()
        raise ValueError(f"CodeGraph explore failed: {detail[-2_000:]}")
    result = process.stdout.strip()
    if not result:
        raise ValueError("CodeGraph explore returned no domain relationships")
    return _bounded_explore_text(result)
