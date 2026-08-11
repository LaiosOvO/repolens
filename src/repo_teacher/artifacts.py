from __future__ import annotations

import copy
import html
from collections.abc import Iterable, Mapping
from typing import Any

from .difficulty import discover_difficulty_map
from .models import stable_id
from .narrative import discover_human_chapter


_COVERAGE_DIMENSIONS = (
    "entrypoint",
    "steps",
    "evidence",
    "test_evidence",
    "resolved_relationships",
)


def _items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _identifiers(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str) and value]


def _ordered_steps(feature: Mapping[str, Any]) -> list[dict[str, Any]]:
    steps = _items(feature.get("steps"))
    return sorted(
        (copy.deepcopy(step) for step in steps),
        key=lambda step: (
            step.get("order") if isinstance(step.get("order"), int) else 1_000_000,
            str(step.get("path", "")),
            step.get("line_start") if isinstance(step.get("line_start"), int) else 0,
            str(step.get("title", "")),
        ),
    )


def _deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _safe_mermaid_label(value: object) -> str:
    """Return inert text for use inside a quoted Mermaid node or edge label."""

    text = " ".join(str(value or "").split())
    escaped = html.escape(text, quote=True)
    return (
        escaped.replace("`", "&#96;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("{", "&#123;")
        .replace("}", "&#125;")
        .replace("|", "&#124;")
    )


def _valid_relationship(
    relationship_id: object,
    relationships_by_id: Mapping[str, Mapping[str, Any]],
    symbols_by_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if not isinstance(relationship_id, str) or not relationship_id:
        return None
    relationship = relationships_by_id.get(relationship_id)
    if not relationship:
        return None
    source_id = relationship.get("source_id")
    target_id = relationship.get("target_id")
    if (
        not isinstance(source_id, str)
        or not isinstance(target_id, str)
        or source_id not in symbols_by_id
        or target_id not in symbols_by_id
    ):
        return None
    return relationship


def _tutorial(
    feature: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    relationships_by_id: Mapping[str, Mapping[str, Any]],
    symbols_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    feature_id = str(feature.get("id") or stable_id("feature", feature.get("title", "unknown")))
    title = str(feature.get("title") or feature.get("entrypoint") or "未命名功能")
    entrypoint = str(feature.get("entrypoint") or "未识别入口")
    steps = _ordered_steps(feature)
    evidence_ids = _deduplicate(
        [
            *_identifiers(feature.get("evidence_ids")),
            *(identifier for step in steps for identifier in _identifiers(step.get("evidence_ids"))),
            *_identifiers(feature.get("test_evidence_ids")),
        ]
    )
    evidence_ids = [identifier for identifier in evidence_ids if identifier in evidence_by_id]
    confirmed_relationship_ids = _deduplicate(
        str(step["relationship_id"])
        for step in steps
        if _valid_relationship(
            step.get("relationship_id"), relationships_by_id, symbols_by_id
        ) is not None
    )
    source_slices: list[dict[str, Any]] = []
    for position, step in enumerate(steps, start=1):
        raw_relationship_id = step.get("relationship_id")
        relationship = _valid_relationship(
            raw_relationship_id, relationships_by_id, symbols_by_id
        )
        has_relationship = relationship is not None
        if isinstance(raw_relationship_id, str) and raw_relationship_id and not has_relationship:
            relationship_gap = (
                f"location-only: relationship id `{raw_relationship_id}` "
                "索引中不存在、端点为空或端点符号未收录。"
            )
        else:
            relationship_gap = str(
                step.get("claim_scope")
                or "没有已解析静态关系；此切片只能证明源码位置与局部职责。"
            )
        source_slices.append(
            {
            "order": position,
            "title": str(step.get("title") or f"源码切片 {position}"),
            "role": str(step.get("source_role") or "静态阅读定位"),
            "symbol": str(step.get("source_symbol") or step.get("title") or "未标注符号"),
            "purpose": (
                str(step.get("explanation") or "沿已解析静态关系核对协作职责。")
                if has_relationship
                else str(
                    step.get("explanation")
                    or "把它作为此能力的定位起点；不要从位置相邻推断运行关系。"
                )
            ),
            "path": str(step.get("path") or ""),
            "line_start": step.get("line_start"),
            "line_end": step.get("line_end"),
            "evidence_ids": _identifiers(step.get("evidence_ids")),
            "claim_scope": (
                str(
                    step.get("claim_scope")
                    or "仅证明该源码位置与声明的局部职责，不证明运行时分支。"
                )
                if has_relationship
                else relationship_gap
            ),
            "relationship_status": "resolved-static" if has_relationship else "location-only",
            "relationship_id": str(raw_relationship_id or "") if has_relationship else "",
            "relationship_kind": (
                str((relationship or {}).get("kind") or step.get("relationship_kind") or "unknown")
                if has_relationship
                else "location-only"
            ),
            "relationship_gap": "" if has_relationship else relationship_gap,
            "snippet_sha256": str(step.get("snippet_sha256") or ""),
            }
        )
    raw_claims = _items(feature.get("technology_claims"))
    technology_claims = {
        str(claim.get("dimension")): copy.deepcopy(claim)
        for claim in raw_claims
        if claim.get("dimension")
    }

    def claims_for(*dimensions: str) -> list[dict[str, Any]]:
        return [technology_claims[dimension] for dimension in dimensions if dimension in technology_claims]

    data_state_claims = claims_for("store", "retrieval", "incremental")
    dependency_claims = claims_for("parser", "framework", "llm", "ui")
    known_data_state_claims = [
        claim for claim in data_state_claims if str(claim.get("value") or "unknown") != "unknown"
    ]
    known_dependency_claims = [
        claim for claim in dependency_claims if str(claim.get("value") or "unknown") != "unknown"
    ]
    unresolved_claims = [
        copy.deepcopy(claim)
        for claim in raw_claims
        if str(claim.get("value") or "unknown") == "unknown"
    ]
    evidence_text = "\n".join(
        str(evidence_by_id[identifier].get("snippet") or "")
        for identifier in evidence_ids
        if identifier in evidence_by_id
    ).lower()
    role_text = " ".join(
        f"{step.get('title', '')} {step.get('source_role', '')} {step.get('explanation', '')}"
        for step in steps
    ).lower()
    has_error_signal = any(
        marker in f"{role_text}\n{evidence_text}"
        for marker in ("error", "exception", "retry", "rollback", "错误", "异常", "重试", "回滚")
    )
    gaps = {
        "data_flow": (
            f"{len(confirmed_relationship_ids)} 条已解析静态关系只证明局部连接；输入输出 schema、"
            "分支条件和跨边界数据变换仍需行为验证。"
            if confirmed_relationship_ids
            else f"{title} 没有已解析静态关系；当前切片不能证明端到端输入、转换与输出数据流。"
        ),
        "state": (
            "已证明的状态相关声明为 "
            + "、".join(
                f"{claim.get('dimension')}:{claim.get('value')}"
                for claim in known_data_state_claims
            )
            + "；这些窄声明不外推事务、并发和生命周期边界。"
            if known_data_state_claims
            else f"{title} 没有带独立证据的状态/检索/增量声明，状态所有权与持久化边界未知。"
        ),
        "error_path": (
            "源码切片出现错误、异常或重试信号，但失败分类、重试上限、回滚和用户可见结果仍未完整证明。"
            if has_error_signal
            else f"{title} 的证据切片没有确认错误、重试或回滚路径。"
        ),
        "runtime_order": "静态切片与关系不证明真实运行次序、并发行为或动态分派。",
    }
    if steps:
        closing = (
            f"以上 {len(steps)} 个源码切片中，包含 "
            f"{len(confirmed_relationship_ids)} 条去重后的已解析静态关系。"
            "它说明代码之间的结构关联，不证明运行时分支一定执行。"
        )
    else:
        closing = "当前索引只确认了功能入口；尚无足够的已解析调用关系生成后续阅读步骤。"
    purpose = str(feature.get("summary") or "先核对能力声明与源码证据。")
    entry = {
        "boundary": entrypoint,
        "symbol_id": str(feature.get("entry_symbol_id") or ""),
        "confidence": str(feature.get("confidence") or "heuristic"),
        "evidence_ids": _identifiers(feature.get("evidence_ids")),
    }
    data_and_state = {
        "claims": data_state_claims,
        "boundary": (
            "已确认："
            + "、".join(
                f"{claim.get('dimension')}:{claim.get('value')}"
                for claim in known_data_state_claims
            )
            + "。其余状态行为保持未知。"
            if known_data_state_claims
            else "没有带独立证据的存储、检索或增量声明；状态行为保持未知。"
        ),
    }
    dependencies = {
        "claims": dependency_claims,
        "boundary": (
            "已确认："
            + "、".join(
                f"{claim.get('dimension')}:{claim.get('value')}"
                for claim in known_dependency_claims
            )
            + "。未列出的依赖维度不猜测。"
            if known_dependency_claims
            else "没有带独立证据的解析器、框架、模型或 UI 依赖声明。"
        ),
    }
    reusable_slices = [
        (
            f"{item['role']}：`{item['symbol']}`（{item['path']}:"
            f"{item['line_start']}-{item['line_end']}，{item['relationship_status']}）"
        )
        for item in source_slices[:3]
    ]
    location_only_count = sum(
        item["relationship_status"] == "location-only" for item in source_slices
    )
    unknown_dimensions = [
        str(claim.get("dimension")) for claim in unresolved_claims if claim.get("dimension")
    ]
    reuse_boundary = {
        "reusable": reusable_slices or ["目前只有入口证据，没有可复用的实现切片。"],
        "must_reverify": _deduplicate(
            [
                *(
                    [f"{location_only_count} 个切片只有位置证据，不能当作已证明实现链。"]
                    if location_only_count
                    else []
                ),
                *(
                    ["未知技术维度：" + "、".join(unknown_dimensions) + "。"]
                    if unknown_dimensions
                    else []
                ),
                gaps["data_flow"],
                gaps["error_path"],
                "运行环境、权限、性能、许可和抽离成本。",
            ]
        ),
    }
    teaching_contract = {
        "purpose": purpose,
        "entry": entry,
        "main_chain": source_slices,
        "data_and_state": data_and_state,
        "dependencies": dependencies,
        "error_and_evidence_gaps": gaps,
        "unresolved_technology_claims": unresolved_claims,
        "reuse_boundary": reuse_boundary,
    }
    return {
        "id": stable_id("tutorial", feature_id),
        "feature_id": feature_id,
        "title": f"如何理解：{title}",
        "opening": (
            f"从 `{entrypoint}` 开始阅读。以下内容由已索引的符号、关系和源码证据确定性生成，"
            "不推断未被静态分析确认的运行时行为。"
        ),
        "steps": steps,
        "teaching_contract": teaching_contract,
        "chapters": [
            {
                "kind": "purpose-and-entry",
                "title": "先看结论：用途与入口",
                "purpose": purpose,
                "entry": entry,
            },
            {
                "kind": "main-implementation-chain",
                "title": "再拆解：主实现链与职责",
                "purpose": "按职责而不是 BFS 距离阅读源码；每个切片只承载自己的局部声明。",
                "slices": source_slices,
            },
            {
                "kind": "data-state-and-dependencies",
                "title": "数据、状态与依赖",
                "purpose": "把已证明的技术选择与未知项分开，避免从项目名称或关键词猜测。",
                "data_and_state": data_and_state,
                "dependencies": dependencies,
            },
            {
                "kind": "error-and-evidence-gaps",
                "title": "证据缺口与错误边界",
                "purpose": "这些缺口必须通过继续源码审计、行为测试或运行跟踪补齐。",
                "gaps": gaps,
            },
            {
                "kind": "reuse-boundary",
                "title": "回到结论：哪些能复用",
                "purpose": "把可直接学习的局部机制与必须重新验证的生产边界分开。",
                "reuse_boundary": reuse_boundary,
            },
        ],
        "confirmed_relationship_count": len(confirmed_relationship_ids),
        "gaps": gaps,
        "closing": closing,
        "evidence_ids": evidence_ids,
        "confidence": str(feature.get("confidence") or "heuristic"),
        "source": "deterministic-index-artifacts",
        "reading_order_semantics": (
            "purpose-entry-role-chain-data-state-dependencies-gaps-reuse; "
            + (
                "curated contract-selected slices and typed capability relationships; "
                if str(feature.get("kind") or "") == "capability-cluster"
                else "direct entry relationships only; "
            )
            + "no transitive BFS expansion; "
            "confirmed edges remain static-only; not runtime execution order"
        ),
        "runtime_behavior": "unknown without trace or behavior-level test evidence",
        "difficulty_map": discover_difficulty_map(feature, evidence_by_id),
        "human_chapter": discover_human_chapter(feature),
    }


def _codemap(
    feature: Mapping[str, Any],
    symbols_by_id: Mapping[str, Mapping[str, Any]],
    relationships_by_id: Mapping[str, Mapping[str, Any]],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    feature_id = str(feature.get("id") or stable_id("feature", feature.get("title", "unknown")))
    title = str(feature.get("title") or feature.get("entrypoint") or "未命名功能")
    steps = _ordered_steps(feature)
    node_ids: list[str] = []
    node_labels: dict[str, str] = {}
    step_node_ids: list[str] = []

    for position, step in enumerate(steps, start=1):
        symbol_id = step.get("symbol_id")
        if isinstance(symbol_id, str) and symbol_id in symbols_by_id:
            node_id = symbol_id
            symbol = symbols_by_id[symbol_id]
            label = symbol.get("qualified_name") or symbol.get("name") or step.get("title")
        else:
            node_id = stable_id(
                "codemap-node",
                feature_id,
                step.get("path", ""),
                step.get("line_start", ""),
                position,
            )
            label = step.get("title") or step.get("path") or f"步骤 {position}"
        if node_id not in node_labels:
            location = str(step.get("path") or "")
            line = step.get("line_start")
            suffix = f" · {location}:{line}" if location and isinstance(line, int) else (f" · {location}" if location else "")
            node_labels[node_id] = f"{label}{suffix}"
            node_ids.append(node_id)
        step_node_ids.append(node_id)

    if not node_ids:
        fallback_id = stable_id("codemap-node", feature_id, "entrypoint")
        node_ids.append(fallback_id)
        step_node_ids.append(fallback_id)
        node_labels[fallback_id] = str(feature.get("entrypoint") or title)

    token_by_id = {identifier: f"n{position}" for position, identifier in enumerate(node_ids, start=1)}
    edge_ids: list[str] = []
    resolved_edge_ids: list[str] = []
    reading_order_edge_ids: list[str] = []
    edge_lines: list[str] = []
    represented_relationship_ids: set[str] = set()
    resolved_pairs: set[tuple[str, str]] = set()
    readable_edges: list[dict[str, str]] = []

    for step in steps:
        relationship_id = step.get("relationship_id")
        if not isinstance(relationship_id, str):
            continue
        relationship = _valid_relationship(
            relationship_id, relationships_by_id, symbols_by_id
        )
        if relationship is None:
            continue
        source_id = relationship.get("source_id")
        target_id = relationship.get("target_id")
        if source_id not in token_by_id or target_id not in token_by_id:
            continue
        pair = (str(source_id), str(target_id))
        if relationship_id in represented_relationship_ids:
            continue
        represented_relationship_ids.add(relationship_id)
        resolved_pairs.add(pair)
        edge_ids.append(relationship_id)
        resolved_edge_ids.append(relationship_id)
        kind = _safe_mermaid_label(relationship.get("kind") or "resolved")
        edge_lines.append(f"  {token_by_id[pair[0]]} -->|{kind}| {token_by_id[pair[1]]}")
        readable_edges.append(
            {
                "id": relationship_id,
                "source_id": pair[0],
                "target_id": pair[1],
                "source": node_labels[pair[0]],
                "target": node_labels[pair[1]],
                "kind": str(relationship.get("kind") or "resolved"),
                "semantics": "resolved-static-relationship",
            }
        )

    for source_id, target_id in zip(step_node_ids, step_node_ids[1:]):
        if source_id == target_id or (source_id, target_id) in resolved_pairs:
            continue
        edge_id = stable_id("codemap-edge", feature_id, source_id, target_id, "reading-order")
        edge_ids.append(edge_id)
        reading_order_edge_ids.append(edge_id)
        resolved_pairs.add((source_id, target_id))
        edge_lines.append(
            f"  {token_by_id[source_id]} -.->|{_safe_mermaid_label('静态阅读顺序')}| {token_by_id[target_id]}"
        )
        readable_edges.append(
            {
                "id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "source": node_labels[source_id],
                "target": node_labels[target_id],
                "kind": "reading-order",
                "semantics": "suggested-reading-order; not implementation flow",
            }
        )

    node_lines = [
        f'  {token_by_id[identifier]}["{_safe_mermaid_label(node_labels[identifier])}"]'
        for identifier in node_ids
    ]
    mermaid = "\n".join(["flowchart LR", *node_lines, *edge_lines])
    evidence_ids = _deduplicate(
        [
            *_identifiers(feature.get("evidence_ids")),
            *(identifier for step in steps for identifier in _identifiers(step.get("evidence_ids"))),
        ]
    )
    relationship_gaps = [
        {
            "order": position,
            "path": str(step.get("path") or ""),
            "line_start": step.get("line_start"),
            "line_end": step.get("line_end"),
            "reason": str(
                (
                    f"relationship id `{step.get('relationship_id')}` "
                    "索引中不存在、端点为空或端点符号未收录。"
                    if step.get("relationship_id")
                    else step.get("claim_scope")
                    or "No resolved static relationship is attached to this source slice."
                )
            ),
        }
        for position, step in enumerate(steps, start=1)
        if _valid_relationship(
            step.get("relationship_id"), relationships_by_id, symbols_by_id
        ) is None
    ]
    return {
        "id": stable_id("codemap", feature_id),
        "feature_id": feature_id,
        "title": f"代码地图：{title}",
        "node_ids": node_ids,
        "edge_ids": edge_ids,
        "resolved_edge_ids": resolved_edge_ids,
        "reading_order_edge_ids": reading_order_edge_ids,
        "relationship_gaps": relationship_gaps,
        "implementation_flow_status": (
            f"{len(resolved_edge_ids)} resolved static edge(s); "
            f"{len(relationship_gaps)} location-only slice(s). "
            "Dashed edges are reading order, not implementation flow."
        ),
        "steps": steps,
        "nodes": [
            {"id": identifier, "label": node_labels[identifier], "order": position}
            for position, identifier in enumerate(node_ids, start=1)
        ],
        "edges": readable_edges,
        "mermaid": mermaid,
        "evidence_ids": [identifier for identifier in evidence_ids if identifier in evidence_by_id],
        "edge_semantics": {
            "solid": "resolved static relationship",
            "dashed": "suggested reading order only; not implementation flow; not runtime flow",
        },
    }


def _coverage(
    feature: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    relationships_by_id: Mapping[str, Mapping[str, Any]],
    symbols_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    feature_id = str(feature.get("id") or stable_id("feature", feature.get("title", "unknown")))
    steps = _ordered_steps(feature)
    evidence_ids = _deduplicate(
        [
            *_identifiers(feature.get("evidence_ids")),
            *(identifier for step in steps for identifier in _identifiers(step.get("evidence_ids"))),
        ]
    )
    valid_evidence_ids = [identifier for identifier in evidence_ids if identifier in evidence_by_id]
    test_ids = _identifiers(feature.get("test_evidence_ids"))
    valid_test_ids = [
        identifier
        for identifier in test_ids
        if identifier in evidence_by_id and evidence_by_id[identifier].get("kind") == "test-reference"
    ]
    relationship_ids = _deduplicate(
        str(step["relationship_id"])
        for step in steps
        if isinstance(step.get("relationship_id"), str) and step.get("relationship_id")
    )
    resolved_relationship_ids = [
        identifier
        for identifier in relationship_ids
        if _valid_relationship(identifier, relationships_by_id, symbols_by_id) is not None
    ]

    checks = {
        "entrypoint": bool(feature.get("entrypoint")),
        "steps": bool(steps),
        "evidence": bool(valid_evidence_ids),
        "test_evidence": bool(valid_test_ids),
        "resolved_relationships": bool(resolved_relationship_ids),
    }
    labels = {
        "entrypoint": ("已识别功能入口", "未识别功能入口"),
        "steps": ("已有静态阅读步骤", "未生成静态阅读步骤"),
        "evidence": ("已有可解析源码证据", "缺少可解析源码证据"),
        "test_evidence": (
            "已有测试源码到入口的静态引用",
            "未发现测试源码到该入口的静态引用",
        ),
        "resolved_relationships": ("已有已解析符号关系", "未发现该功能路径中的已解析符号关系"),
    }
    covered = [labels[name][0] for name in _COVERAGE_DIMENSIONS if checks[name]]
    gaps = [labels[name][1] for name in _COVERAGE_DIMENSIONS if not checks[name]]
    score = sum(20 for name in _COVERAGE_DIMENSIONS if checks[name])
    status = (
        "signals-present"
        if score >= 80
        else ("partial-signals" if score >= 40 else "minimal-signals")
    )
    return {
        "feature_id": feature_id,
        "scope": "artifact-evidence-completeness",
        "behavioral_coverage": "unknown",
        "score": score,
        "status": status,
        "quality_assessment": "not-assessed",
        "checks": checks,
        "covered": covered,
        "gaps": gaps,
        "metrics": {
            "entrypoint": int(checks["entrypoint"]),
            "steps": len(steps),
            "evidence": len(valid_evidence_ids),
            "test_evidence": len(valid_test_ids),
            "resolved_relationships": len(resolved_relationship_ids),
        },
    }


def enrich_index(index: Mapping[str, Any]) -> dict[str, Any]:
    """Copy an index and add deterministic, evidence-bounded teaching artifacts."""

    enriched = copy.deepcopy(dict(index))
    features = _items(enriched.get("features"))
    evidence = _items(enriched.get("evidence"))
    symbols = _items(enriched.get("symbols"))
    relationships = _items(enriched.get("relationships"))
    evidence_by_id = {str(item["id"]): item for item in evidence if item.get("id")}
    symbols_by_id = {str(item["id"]): item for item in symbols if item.get("id")}
    relationships_by_id = {str(item["id"]): item for item in relationships if item.get("id")}

    tutorials = [
        _tutorial(feature, evidence_by_id, relationships_by_id, symbols_by_id)
        for feature in features
    ]
    codemaps = [
        _codemap(feature, symbols_by_id, relationships_by_id, evidence_by_id)
        for feature in features
    ]
    coverage = [
        _coverage(feature, evidence_by_id, relationships_by_id, symbols_by_id)
        for feature in features
    ]
    tutorials.sort(key=lambda item: (item["title"], item["feature_id"]))
    codemaps.sort(key=lambda item: (item["title"], item["feature_id"]))
    coverage.sort(key=lambda item: item["feature_id"])

    enriched["tutorials"] = tutorials
    enriched["codemaps"] = codemaps
    enriched["coverage"] = coverage
    stats = enriched.get("stats")
    if not isinstance(stats, dict):
        stats = {}
        enriched["stats"] = stats
    stats["tutorials"] = len(tutorials)
    stats["codemaps"] = len(codemaps)
    stats["coverage"] = len(coverage)
    stats["coverage_average"] = round(
        sum(item["score"] for item in coverage) / len(coverage), 1
    ) if coverage else 0.0
    stats["evidence_completeness_average"] = stats["coverage_average"]
    return enriched
