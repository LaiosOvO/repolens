from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .capability_graph import build_capability_graph, graph_prompt_context
from .models import stable_id


PACK_SCHEMA = "repo-teacher-analysis-pack/v1"
NARRATIVE_SCHEMA = "repo-teacher-human-report/v1"
_MAX_CHAPTERS = 200
_MAX_TEXT = 12_000


def human_report_json_schema() -> dict[str, Any]:
    """Return the structured-output contract used by the CLI model adapter."""

    text = {"type": "string", "minLength": 1, "maxLength": _MAX_TEXT}
    string_list = {"type": "array", "items": text, "minItems": 1}
    object_item = {
        "type": "object",
        "properties": {"name": text, "role": text},
        "required": ["name", "role"],
        "additionalProperties": False,
    }
    state_item = {
        "type": "object",
        "properties": {"stage": text, "reads": text, "writes": text, "why_next": text},
        "required": ["stage", "reads", "writes", "why_next"],
        "additionalProperties": False,
    }
    choice_item = {
        "type": "object",
        "properties": {"choice": text, "why": text, "cost": text},
        "required": ["choice", "why", "cost"],
        "additionalProperties": False,
    }
    difficulty_item = {
        "type": "object",
        "properties": {
            "id": text,
            "title": text,
            "why_hard": text,
            "naive_failure": text,
            "reuse_question": text,
            "runtime_steps": string_list,
            "invariants": string_list,
            "failure_modes": string_list,
            "tradeoffs": string_list,
            "evidence_ids": string_list,
        },
        "required": [
            "id", "title", "why_hard", "naive_failure", "reuse_question",
            "runtime_steps", "invariants", "failure_modes", "tradeoffs", "evidence_ids",
        ],
        "additionalProperties": False,
    }
    source_ref = {
        "type": "object",
        "properties": {
            "path": text,
            "line_start": {"type": "integer", "minimum": 1},
            "line_end": {"type": "integer", "minimum": 1},
            "claim": text,
        },
        "required": ["path", "line_start", "line_end", "claim"],
        "additionalProperties": False,
    }
    chapter = {
        "type": "object",
        "properties": {
            "id": text,
            "title": text,
            "summary": text,
            "mechanism": text,
            "question": text,
            "use_when": text,
            "distinguish": text,
            "source_feature_ids": string_list,
            "evidence_ids": string_list,
            "source_refs": {"type": "array", "items": source_ref, "minItems": 1},
            "runtime_story": {
                "type": "object",
                "properties": {
                    "trigger": text, "owner": text, "output": text, "consumer": text,
                    "steps": {"type": "array", "items": text, "minItems": 3},
                },
                "required": ["trigger", "owner", "output", "consumer", "steps"],
                "additionalProperties": False,
            },
            "construction": {
                "type": "object",
                "properties": {
                    "explanation": text,
                    "objects": {"type": "array", "items": object_item, "minItems": 2},
                },
                "required": ["explanation", "objects"],
                "additionalProperties": False,
            },
            "mechanism_model": {
                "type": "object",
                "properties": {
                    "plain_summary": text,
                    "storage": text,
                    "write_path": text,
                    "read_path": text,
                    "control_loop": text,
                    "decision_rules": text,
                    "termination": text,
                    "dynamic_behavior": text,
                    "worked_example": {"type": "array", "items": text, "minItems": 3},
                },
                "required": [
                    "plain_summary", "storage", "write_path", "read_path", "control_loop",
                    "decision_rules", "termination", "dynamic_behavior", "worked_example",
                ],
                "additionalProperties": False,
            },
            "state_flow": {"type": "array", "items": state_item, "minItems": 2},
            "difficulty_map": {
                "type": "object",
                "properties": {
                    "summary": text,
                    "unknowns": {"type": "array", "items": text},
                    "items": {"type": "array", "items": difficulty_item, "minItems": 1},
                },
                "required": ["summary", "unknowns", "items"],
                "additionalProperties": False,
            },
            "design_choices": {"type": "array", "items": choice_item, "minItems": 2},
            "boundary": {
                "type": "object",
                "properties": {"supported": string_list, "unsupported": string_list},
                "required": ["supported", "unsupported"],
                "additionalProperties": False,
            },
            "reuse_plan": {
                "type": "object",
                "properties": {
                    "take": string_list, "adapt": string_list,
                    "avoid": string_list, "verify": string_list,
                },
                "required": ["take", "adapt", "avoid", "verify"],
                "additionalProperties": False,
            },
        },
        "required": [
            "id", "title", "summary", "mechanism", "question", "use_when", "distinguish",
            "source_feature_ids", "evidence_ids", "source_refs", "runtime_story", "construction", "mechanism_model", "state_flow",
            "difficulty_map", "design_choices", "boundary", "reuse_plan",
        ],
        "additionalProperties": False,
    }
    overview_component = {
        "type": "object",
        "properties": {
            "name": text,
            "responsibility": text,
            "communication": text,
            "state": text,
            "source_refs": {"type": "array", "items": source_ref, "minItems": 1},
        },
        "required": ["name", "responsibility", "communication", "state", "source_refs"],
        "additionalProperties": False,
    }
    overview_directory = {
        "type": "object",
        "properties": {
            "path": text,
            "responsibility": text,
            "layer": text,
            "boundary": text,
            "source_refs": {"type": "array", "items": source_ref, "minItems": 1},
        },
        "required": ["path", "responsibility", "layer", "boundary", "source_refs"],
        "additionalProperties": False,
    }
    overview_journey = {
        "type": "object",
        "properties": {
            "stage": text,
            "actor": text,
            "action": text,
            "state_change": text,
            "next": text,
        },
        "required": ["stage", "actor", "action", "state_change", "next"],
        "additionalProperties": False,
    }
    overview_product_axis = {
        "type": "object",
        "properties": {
            "id": text,
            "title": text,
            "one_liner": text,
            "user_outcome": text,
            "end_to_end_flow": string_list,
            "capability_ids": string_list,
            "source_refs": {"type": "array", "items": source_ref, "minItems": 1},
        },
        "required": [
            "id", "title", "one_liner", "user_outcome",
            "end_to_end_flow", "capability_ids", "source_refs",
        ],
        "additionalProperties": False,
    }
    overview_engineering_structure = {
        "type": "object",
        "properties": {
            "repository_shape": text,
            "architecture_pattern": text,
            "pattern_reasoning": text,
            "frontend_organization": text,
            "backend_organization": text,
            "worker_and_async_organization": text,
            "shared_contracts": text,
            "dependency_rule": text,
            "media_organization": text,
            "source_refs": {"type": "array", "items": source_ref, "minItems": 1},
        },
        "required": [
            "repository_shape", "architecture_pattern", "pattern_reasoning",
            "frontend_organization", "backend_organization",
            "worker_and_async_organization", "shared_contracts",
            "dependency_rule", "media_organization", "source_refs",
        ],
        "additionalProperties": False,
    }
    overview = {
        "type": "object",
        "properties": {
            "one_liner": text,
            "product_type": text,
            "primary_user": text,
            "problem": text,
            "core_journey": {"type": "array", "items": overview_journey, "minItems": 3},
            "core_product_axes": {
                "type": "array", "items": overview_product_axis,
                "minItems": 1, "maxItems": 4,
            },
            "supporting_capability_ids": {"type": "array", "items": text},
            "architecture_summary": text,
            "architecture_style": text,
            "engineering_structure": overview_engineering_structure,
            "execution_model": text,
            "runtime_components": {"type": "array", "items": overview_component, "minItems": 2},
            "frontend_backend_boundary": text,
            "data_and_state": text,
            "deployment_shape": text,
            "code_organization": {"type": "array", "items": overview_directory, "minItems": 2},
            "differentiator": text,
            "not_this": string_list,
            "source_refs": {"type": "array", "items": source_ref, "minItems": 3},
            "capability_order": string_list,
        },
        "required": [
            "one_liner", "product_type", "primary_user", "problem", "core_journey",
            "core_product_axes", "supporting_capability_ids",
            "architecture_summary", "architecture_style", "execution_model",
            "engineering_structure",
            "runtime_components", "frontend_backend_boundary", "data_and_state",
            "deployment_shape", "code_organization", "differentiator", "not_this",
            "source_refs", "capability_order",
        ],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "schema_version": {"type": "string", "const": NARRATIVE_SCHEMA},
            "project": {
                "type": "object",
                "properties": {
                    "commit": {"type": ["string", "null"]},
                    "analysis_fingerprint": text,
                    "overview": overview,
                },
                "required": ["commit", "analysis_fingerprint"],
                "additionalProperties": False,
            },
            "generator": {
                "type": "object",
                "properties": {"name": text, "method": text},
                "required": ["name", "method"],
                "additionalProperties": False,
            },
            "chapters": {"type": "array", "items": chapter, "minItems": 1, "maxItems": _MAX_CHAPTERS},
        },
        "required": ["schema_version", "project", "generator", "chapters"],
        "additionalProperties": False,
    }


def _dicts(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"human report field is required: {field}")
    result = value.strip()
    if len(result) > _MAX_TEXT:
        raise ValueError(f"human report field is too large: {field}")
    return result


def build_report_pack(
    index: Mapping[str, Any],
    capability_graph: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a bounded evidence packet for a model-authored project report.

    The packet deliberately labels deterministic features as hints.  Product
    capabilities are synthesized by the model only after it reads the evidence
    and, when necessary, the referenced source files.
    """

    project = index.get("project") if isinstance(index.get("project"), dict) else {}
    resolved_graph = (
        dict(capability_graph)
        if capability_graph is not None
        else build_capability_graph(index)
    )
    prompt_graph = graph_prompt_context(resolved_graph)
    evidence = _dicts(index.get("evidence"))
    evidence_by_id = {
        str(item.get("id")): item for item in evidence if isinstance(item.get("id"), str)
    }
    hints: list[dict[str, Any]] = []
    for feature in _dicts(index.get("features")):
        evidence_ids = _strings(feature.get("evidence_ids"))
        steps = []
        for step in _dicts(feature.get("steps")):
            steps.append(
                {
                    "title": step.get("title"),
                    "explanation": step.get("explanation"),
                    "path": step.get("path"),
                    "line_start": step.get("line_start"),
                    "line_end": step.get("line_end"),
                    "relationship_id": step.get("relationship_id"),
                    "evidence_ids": _strings(step.get("evidence_ids")),
                }
            )
        hints.append(
            {
                "id": feature.get("id"),
                "title": feature.get("title"),
                "summary": feature.get("summary"),
                "kind": feature.get("kind"),
                "confidence": feature.get("confidence"),
                "entrypoint": feature.get("entrypoint"),
                "technology_tags": _strings(feature.get("technology_tags")),
                "evidence_ids": evidence_ids,
                "steps": steps,
            }
        )
    graph_navigation_evidence: list[dict[str, Any]] = []
    files_by_path = {
        str(item.get("path")): item
        for item in _dicts(index.get("files"))
        if item.get("path")
    }
    for cluster in _dicts(resolved_graph.get("mechanism_clusters")):
        cluster_id = str(cluster.get("id") or "")
        if not cluster_id:
            continue
        steps: list[dict[str, Any]] = []
        evidence_ids: list[str] = []
        for node in _dicts(cluster.get("central_nodes"))[:4]:
            path = str(node.get("path") or "")
            file_record = files_by_path.get(path)
            if file_record is None:
                continue
            line = int(node.get("line") or 1)
            maximum = int(file_record.get("lines") or line)
            line = max(1, min(line, maximum))
            evidence_id = stable_id(
                "graph-navigation-evidence", cluster_id, path, str(line)
            )
            evidence_ids.append(evidence_id)
            graph_navigation_evidence.append(
                {
                    "id": evidence_id,
                    "path": path,
                    "line_start": line,
                    "line_end": line,
                    "kind": "graph-navigation-slice",
                    "confidence": "graph-navigation-only",
                    "snippet": (
                        "代码图将这里识别为未被现有入口功能覆盖的中心节点；"
                        "必须打开源码核对后才能提升为产品功能。"
                    ),
                }
            )
            steps.append(
                {
                    "title": "代码图候选中心",
                    "explanation": "用于发现遗漏能力的导航切片，不直接证明用户功能。",
                    "path": path,
                    "line_start": line,
                    "line_end": line,
                    "relationship_id": None,
                    "evidence_ids": [evidence_id],
                }
            )
        if len(steps) < 3:
            continue
        areas = [
            str(item)
            for item in cluster.get("primary_areas", [])
            if isinstance(item, str) and item
        ]
        hint_id = stable_id("graph-navigation-feature", cluster_id)
        hints.append(
            {
                "id": hint_id,
                "title": f"待核对机制候选：{' / '.join(areas[:3]) or cluster_id}",
                "summary": (
                    "这是代码图发现的高内聚实现区域，只用于提醒模型检查是否存在遗漏的用户能力；"
                    "不能直接作为最终章节。"
                ),
                "kind": "graph-mechanism-candidate",
                "confidence": "graph-navigation-only",
                "entrypoint": None,
                "technology_tags": ["graph-navigation", "candidate-only"],
                "evidence_ids": evidence_ids,
                "steps": steps,
            }
        )

    navigation_locations: dict[str, int] = {}
    for section in ("feature_slices", "capability_candidates", "mechanism_clusters"):
        for item in _dicts(prompt_graph.get(section)):
            node_groups = [
                item.get("seed_nodes"),
                item.get("implementation_nodes"),
                item.get("central_nodes"),
            ]
            for nodes in node_groups:
                for node in _dicts(nodes):
                    path = str(node.get("path") or "")
                    if path not in files_by_path:
                        continue
                    line = int(node.get("line") or 1)
                    maximum = int(files_by_path[path].get("lines") or line)
                    navigation_locations.setdefault(path, max(1, min(line, maximum)))
            for edge in _dicts(item.get("resolved_edges")):
                for prefix in ("source", "target"):
                    path = str(edge.get(f"{prefix}_path") or "")
                    if path not in files_by_path:
                        continue
                    line = int(edge.get(f"{prefix}_line") or 1)
                    maximum = int(files_by_path[path].get("lines") or line)
                    navigation_locations.setdefault(path, max(1, min(line, maximum)))
    for path in files_by_path:
        navigation_locations.setdefault(path, 1)
    for path, line in sorted(navigation_locations.items()):
        evidence_id = stable_id("graph-path-evidence", path, str(line))
        hint_id = stable_id("graph-path-feature", path)
        graph_navigation_evidence.append(
            {
                "id": evidence_id,
                "path": path,
                "line_start": line,
                "line_end": line,
                "kind": "graph-navigation-slice",
                "confidence": "graph-navigation-only",
                "snippet": "代码图源码锚点；最终功能和机制必须由模型打开有界源码摘录后核对。",
            }
        )
        hints.append(
            {
                "id": hint_id,
                "title": f"源码导航锚点：{path}",
                "summary": "这是报告模型的证据锚点，不是用户功能。",
                "kind": "graph-source-candidate",
                "confidence": "graph-navigation-only",
                "entrypoint": None,
                "technology_tags": ["graph-navigation", "candidate-only"],
                "evidence_ids": [evidence_id],
                "steps": [
                    {
                        "title": "代码图定位",
                        "explanation": "用于把模型选中的功能结论闭合到当前源码快照。",
                        "path": path,
                        "line_start": line,
                        "line_end": line,
                        "relationship_id": None,
                        "evidence_ids": [evidence_id],
                    }
                ],
            }
        )

    referenced_ids = list(
        dict.fromkeys(
            identifier
            for hint in hints
            for identifier in [
                *_strings(hint.get("evidence_ids")),
                *(
                    evidence_id
                    for step in _dicts(hint.get("steps"))
                    for evidence_id in _strings(step.get("evidence_ids"))
                ),
            ]
            if identifier in evidence_by_id
        )
    )
    packed_evidence = []
    for identifier in referenced_ids:
        item = evidence_by_id[identifier]
        packed_evidence.append(
            {
                "id": identifier,
                "path": item.get("path"),
                "line_start": item.get("line_start"),
                "line_end": item.get("line_end"),
                "kind": item.get("kind"),
                "confidence": item.get("confidence"),
                "snippet": str(item.get("snippet") or "")[:4_000],
            }
        )
    packed_evidence.extend(graph_navigation_evidence)
    evidence_records = {
        str(item.get("id")): item
        for item in packed_evidence
        if isinstance(item.get("id"), str)
    }
    bounded_hints: list[dict[str, Any]] = []
    bounded_evidence_ids: list[str] = []
    seen_evidence_ids: set[str] = set()
    for hint in hints:
        hint_evidence_ids = list(
            dict.fromkeys(
                identifier
                for identifier in [
                    *_strings(hint.get("evidence_ids")),
                    *(
                        evidence_id
                        for step in _dicts(hint.get("steps"))
                        for evidence_id in _strings(step.get("evidence_ids"))
                    ),
                ]
                if identifier in evidence_records
            )
        )
        new_evidence_ids = [
            identifier
            for identifier in hint_evidence_ids
            if identifier not in seen_evidence_ids
        ]
        if len(bounded_hints) >= 2_000:
            break
        if len(bounded_evidence_ids) + len(new_evidence_ids) > 2_000:
            continue
        bounded_hints.append(hint)
        bounded_evidence_ids.extend(new_evidence_ids)
        seen_evidence_ids.update(new_evidence_ids)
    bounded_evidence = [
        evidence_records[identifier] for identifier in bounded_evidence_ids
    ]
    return {
        "schema_version": PACK_SCHEMA,
        "project": {
            "name": project.get("name"),
            "path": project.get("path"),
            "commit": project.get("commit"),
            "branch": project.get("branch"),
            "analysis_fingerprint": index.get("analysis_fingerprint"),
        },
        "instructions": [
            "先读取 capability_graph：从已解析的调用/包含/导入关系理解组件、依赖和实现切片，再做功能归纳；不要重新全仓盲扫。",
            "优先从 capability_graph.capability_candidates 选择功能种子；这些种子已经绑定触发入口、关键模块、关键边、状态点和影响半径。",
            "capability_graph.feature_slices 是已识别用户能力的图扩展；mechanism_clusters 只是候选，不得直接冒充产品功能。",
            "feature_hints 是静态导航提示，入口、类和函数不能自动当作产品功能。",
            "从一个具体用户动作归纳项目能力；先回答为什么值得关心，再用 evidence id 绑定解释。",
            "每章采用总—分—总：plain_summary 是标题后的第一句总论；中间解释运行链、机制、状态和难点；结尾回到本质与复用判断。",
            "plain_summary 必须以‘<功能名> 本质是/就是……’开头，优先点明真实构造和主数据流，例如‘Agent Loop 本质是一个有终止条件的 Python for 循环’、‘Voice 本质是 PCM 采集 → ASR → LLM → TTS 的串行 pipeline’；不得先写背景、目的或问题。",
            "必须覆盖全部独立用户动作，不设固定章节数；行为、状态和机制不同的能力不能因为同目录或相邻页面而合并。",
            "按核心抽象、抽象关系和依赖教学顺序组织章节，源码路径只作为最后的下钻证据。",
            "每个功能的 plain_summary 必须直接说明它本质上是什么、实际怎样运行、又不是什么；禁止只写负责、管理、处理或编排。",
            "每个功能先讲用途、参与对象、完整数据/控制流、状态变化和真正难点；阅读顺序不能冒充运行顺序。",
            "每个功能必须显式解释 storage/write/read/control-loop/decision/termination/dynamic behavior；不涉及存储或查询时也必须明确写无独立存储层或无查询层。",
            "涉及存储与查询时，区分事实源、原始记录、派生数据/索引，并说明写入提交、失败处理、查询过滤、召回、排序、Top-K 与结果合并。",
            "涉及 Loop 时写明 for/while/事件循环等真实构造、一轮如何继续或退出；涉及 Graph 时写明构图、ready、并行屏障、状态合并、Router 输入/规则/输出与动态拓扑边界。",
            "涉及 Voice 时写明切段、ASR→Agent→TTS 交接、缓冲或流式边界、是否可打断，以及串行、半双工或全双工的事实结论。",
            "真正难点必须说明不变量、朴素实现的具体失败、当前取舍和可观察后果，不能只写代码复杂或需要测试。",
            "Spec、README 与 docs 只能导航；每章必须给至少 3 个精确 source_refs，且至少 1 个来自非文档的实现或测试源码，证明功能确实存在。",
            "无法从证据确认的行为必须写进 unsupported 或 unknowns，不能补写为事实。",
        ],
        "required_chapter_sections": [
            "这个功能为什么存在",
            "一次任务完整怎么运行",
            "核心机制怎么构建",
            "底层机制到底怎么工作",
            "状态是怎样一步步变化的",
            "真正难点与失败方式",
            "为什么这样设计",
            "它能做什么、不能做什么",
            "如果你要复用",
            "最后再看源码证据",
        ],
        "capability_graph": prompt_graph,
        "modules": _dicts(index.get("modules"))[:200],
        "reading_path": _dicts(index.get("reading_path"))[:100],
        "feature_hints": bounded_hints,
        "evidence": bounded_evidence,
    }


def _require_list(mapping: Mapping[str, Any], field: str, minimum: int = 1) -> list[Any]:
    value = mapping.get(field)
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"human report list is required: {field}")
    return value


def _validate_chapter(
    chapter: Mapping[str, Any],
    *,
    feature_ids: set[str],
    evidence_ids: set[str],
    files_by_path: Mapping[str, Mapping[str, Any]],
) -> None:
    chapter_id = _text(chapter.get("id"), field="chapters[].id")
    for field in ("title", "summary", "mechanism", "question", "use_when", "distinguish"):
        _text(chapter.get(field), field=f"{chapter_id}.{field}")
    source_feature_ids = _strings(chapter.get("source_feature_ids"))
    if not source_feature_ids:
        raise ValueError(f"human report list is required: {chapter_id}.source_feature_ids")
    unknown_features = sorted(set(source_feature_ids) - feature_ids)
    if unknown_features:
        raise ValueError(f"unknown feature in human report {chapter_id}: {unknown_features[0]}")
    chapter_evidence = _strings(chapter.get("evidence_ids"))
    if not chapter_evidence:
        raise ValueError(f"human report list is required: {chapter_id}.evidence_ids")
    unknown_evidence = sorted(set(chapter_evidence) - evidence_ids)
    if unknown_evidence:
        raise ValueError(f"unknown evidence in human report {chapter_id}: {unknown_evidence[0]}")

    source_refs = _dicts(chapter.get("source_refs"))
    for position, source_ref in enumerate(source_refs, start=1):
        path = _text(source_ref.get("path"), field=f"{chapter_id}.source_refs[{position}].path")
        claim = _text(source_ref.get("claim"), field=f"{chapter_id}.source_refs[{position}].claim")
        del claim
        file_record = files_by_path.get(path)
        if file_record is None:
            raise ValueError(f"unknown source path in human report {chapter_id}: {path}")
        line_start = source_ref.get("line_start")
        line_end = source_ref.get("line_end")
        if not isinstance(line_start, int) or not isinstance(line_end, int):
            raise ValueError(f"human report source lines are required: {chapter_id}:{path}")
        file_lines = file_record.get("lines")
        maximum = file_lines if isinstance(file_lines, int) and file_lines > 0 else line_end
        if line_start < 1 or line_end < line_start or line_end > maximum:
            raise ValueError(f"human report source range is invalid: {chapter_id}:{path}")

    story = chapter.get("runtime_story")
    if not isinstance(story, dict):
        raise ValueError(f"human report object is required: {chapter_id}.runtime_story")
    for field in ("trigger", "owner", "output", "consumer"):
        _text(story.get(field), field=f"{chapter_id}.runtime_story.{field}")
    _require_list(story, "steps", 3)

    construction = chapter.get("construction")
    if not isinstance(construction, dict):
        raise ValueError(f"human report object is required: {chapter_id}.construction")
    _text(construction.get("explanation"), field=f"{chapter_id}.construction.explanation")
    _require_list(construction, "objects", 2)

    mechanism_model = chapter.get("mechanism_model")
    if not isinstance(mechanism_model, dict):
        raise ValueError(f"human report object is required: {chapter_id}.mechanism_model")
    for field in (
        "plain_summary", "storage", "write_path", "read_path", "control_loop",
        "decision_rules", "termination", "dynamic_behavior",
    ):
        _text(mechanism_model.get(field), field=f"{chapter_id}.mechanism_model.{field}")
    _require_list(mechanism_model, "worked_example", 3)
    _require_list(chapter, "state_flow", 2)
    _require_list(chapter, "design_choices", 2)

    boundary = chapter.get("boundary")
    reuse = chapter.get("reuse_plan")
    if not isinstance(boundary, dict) or not isinstance(reuse, dict):
        raise ValueError(f"human report boundary/reuse objects are required: {chapter_id}")
    _require_list(boundary, "supported")
    _require_list(boundary, "unsupported")
    for field in ("take", "adapt", "avoid", "verify"):
        _require_list(reuse, field)

    difficulty_map = chapter.get("difficulty_map")
    if not isinstance(difficulty_map, dict):
        raise ValueError(f"human report object is required: {chapter_id}.difficulty_map")
    _text(difficulty_map.get("summary"), field=f"{chapter_id}.difficulty_map.summary")
    for difficulty in _dicts(difficulty_map.get("items")):
        difficulty_id = _text(difficulty.get("id"), field=f"{chapter_id}.difficulty.id")
        for field in ("title", "why_hard", "naive_failure", "reuse_question"):
            _text(difficulty.get(field), field=f"{chapter_id}.{difficulty_id}.{field}")
        for field in ("runtime_steps", "invariants", "failure_modes", "tradeoffs"):
            _require_list(difficulty, field)
        difficulty_evidence = _strings(difficulty.get("evidence_ids"))
        if not difficulty_evidence:
            raise ValueError(f"human report list is required: {chapter_id}.{difficulty_id}.evidence_ids")
        if not set(difficulty_evidence) <= set(chapter_evidence):
            raise ValueError(f"difficulty evidence escapes chapter evidence: {chapter_id}.{difficulty_id}")


def compose_human_report(
    index: Mapping[str, Any], narrative: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a model-authored narrative and compose a renderer-only index.

    The canonical deterministic index is not mutated.  The returned value is a
    presentation view whose capabilities come from the model narrative and
    whose citations must resolve to canonical index evidence.
    """

    if narrative.get("schema_version") != NARRATIVE_SCHEMA:
        raise ValueError("unsupported human report schema")
    project = index.get("project") if isinstance(index.get("project"), dict) else {}
    narrative_project = narrative.get("project") if isinstance(narrative.get("project"), dict) else {}
    if narrative_project.get("commit") != project.get("commit"):
        raise ValueError("human report project commit does not match index")
    if narrative_project.get("analysis_fingerprint") != index.get("analysis_fingerprint"):
        raise ValueError("human report analysis fingerprint does not match index")

    chapters = _dicts(narrative.get("chapters"))
    if not chapters or len(chapters) > _MAX_CHAPTERS:
        raise ValueError("human report must contain between 1 and 200 chapters")
    feature_by_id = {
        str(item.get("id")): item for item in _dicts(index.get("features")) if item.get("id")
    }
    evidence_by_id = {
        str(item.get("id")): item for item in _dicts(index.get("evidence")) if item.get("id")
    }
    files_by_path = {
        str(item.get("path")): item for item in _dicts(index.get("files")) if item.get("path")
    }
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    for chapter in chapters:
        _validate_chapter(
            chapter,
            feature_ids=set(feature_by_id),
            evidence_ids=set(evidence_by_id),
            files_by_path=files_by_path,
        )
        chapter_id = str(chapter["id"])
        title = str(chapter["title"])
        if chapter_id in seen_ids or title.casefold() in seen_titles:
            raise ValueError("human report chapter IDs and titles must be unique")
        seen_ids.add(chapter_id)
        seen_titles.add(title.casefold())

    composed = copy.deepcopy(dict(index))
    composed_evidence = _dicts(composed.get("evidence"))
    features: list[dict[str, Any]] = []
    tutorials: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for chapter in chapters:
        chapter_id = str(chapter["id"])
        feature_id = stable_id("human-capability", chapter_id)
        chapter_evidence_ids = _strings(chapter.get("evidence_ids"))
        steps = []
        for position, source_ref in enumerate(_dicts(chapter.get("source_refs")), start=1):
            path = str(source_ref["path"])
            line_start = int(source_ref["line_start"])
            line_end = int(source_ref["line_end"])
            evidence_id = stable_id(
                "human-source-ref", chapter_id, path, str(line_start), str(line_end)
            )
            evidence = {
                "id": evidence_id,
                "path": path,
                "line_start": line_start,
                "line_end": line_end,
                "kind": "model-selected-source-slice",
                "confidence": "source-location-validated",
                "snippet": str(source_ref["claim"]),
                "analyzer": "codex-source-inspection",
            }
            composed_evidence.append(evidence)
            steps.append(
                {
                    "order": position,
                    "title": "实现源码",
                    "explanation": str(source_ref["claim"]),
                    "path": path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "evidence_ids": [evidence_id],
                }
            )
        for position, evidence_id in enumerate(chapter_evidence_ids, start=1):
            evidence = evidence_by_id[evidence_id]
            steps.append(
                {
                    "order": len(steps) + position,
                    "title": str(evidence.get("kind") or "源码证据"),
                    "explanation": "由大模型章节引用的确定性源码证据；仅用于核对功能结论。",
                    "path": evidence.get("path"),
                    "line_start": evidence.get("line_start"),
                    "line_end": evidence.get("line_end"),
                    "evidence_ids": [evidence_id],
                }
            )
        features.append(
            {
                "id": feature_id,
                "title": str(chapter["title"]),
                "summary": str(chapter["summary"]),
                "entrypoint": str(steps[0].get("path") or "source evidence"),
                "kind": "capability-cluster",
                "confidence": "evidence-bounded-model-synthesis",
                "source": "llm-evidence-synthesis",
                "technology_tags": [
                    "human-report:model-synthesis",
                    f"mechanism:{chapter['mechanism']}",
                    "evidence:canonical-index-refs",
                ],
                "technology_claims": [],
                "source_feature_ids": _strings(chapter.get("source_feature_ids")),
                "evidence_ids": chapter_evidence_ids,
                "test_evidence_ids": [],
                "steps": steps,
            }
        )
        difficulty_map = copy.deepcopy(chapter["difficulty_map"])
        difficulty_map.setdefault(
            "method",
            "Codex synthesis over a deterministic repository evidence packet; citations validated by CLI",
        )
        difficulty_map.setdefault("unknowns", [])
        tutorials.append(
            {
                "id": stable_id("human-tutorial", chapter_id),
                "feature_id": feature_id,
                "title": f"项目功能教程：{chapter['title']}",
                "opening": str(chapter["summary"]),
                "chapters": [],
                "human_chapter": copy.deepcopy(chapter),
                "difficulty_map": difficulty_map,
                "evidence_ids": chapter_evidence_ids,
                "source": "llm-evidence-synthesis",
                "generator": copy.deepcopy(narrative.get("generator", {})),
            }
        )
        coverage.append(
            {
                "feature_id": feature_id,
                "scope": "model-narrative-evidence-closure",
                "status": "evidence-bounded",
                "score": 100,
                "checks": {"chapter": True, "evidence": True},
                "gaps": list(chapter.get("boundary", {}).get("unsupported", [])),
            }
        )
    composed["features"] = features
    composed["evidence"] = composed_evidence
    composed["tutorials"] = tutorials
    composed["codemaps"] = []
    composed["coverage"] = coverage
    composed["human_report"] = {
        "schema_version": NARRATIVE_SCHEMA,
        "generator": copy.deepcopy(narrative.get("generator", {})),
        "chapter_count": len(chapters),
        "project_overview": copy.deepcopy(narrative_project.get("overview")),
    }
    return composed
