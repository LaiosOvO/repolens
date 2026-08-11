from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
from pathlib import Path, PurePosixPath
from typing import Any

from .models import stable_id
from .evidence import redact_secrets
from .reference_catalog import (
    CATALOG_REVISION,
    SCORE_RUBRIC,
    curated_implementation,
    reference_identity_status,
)


@dataclass(frozen=True, slots=True)
class CapabilityRule:
    slug: str
    title: str
    description: str
    keywords: tuple[str, ...]


CAPABILITY_RULES = (
    CapabilityRule(
        "code-parsing",
        "代码解析与符号索引",
        "如何从源码提取文件、符号、定义、引用与调用位置。",
        ("parser", "analyzer", "tree-sitter", "treesitter", "lsp", "scip", "indexer", "symbol"),
    ),
    CapabilityRule(
        "code-graph",
        "代码图与调用关系",
        "如何把符号、调用、继承、导入或组件关系组织成可查询图。",
        ("graph_builder", "graph-builder", "call_graph", "call-graph", "knowledge_graph", "relation_edge"),
    ),
    CapabilityRule(
        "component-discovery",
        "架构组件与功能抽象",
        "如何从文件和符号图识别组件、领域、功能或核心抽象。",
        ("abstraction", "component", "cluster", "architecture", "feature_discovery", "identifyabstractions"),
    ),
    CapabilityRule(
        "tutorial-generation",
        "教程与 Wiki 生成",
        "如何把代码事实组织成总览、章节、学习路线和可维护 Wiki。",
        ("tutorial", "write_chapters", "writechapters", "wiki", "chapter", "learning_path", "learning-path", "cliff_notes"),
    ),
    CapabilityRule(
        "evidence-grounding",
        "证据、引用与事实校验",
        "如何把说明绑定到文件、行号、snippet 和可验证来源。",
        ("evidence", "citation", "ground_citation", "source_reference", "sourcecodereference", "snippet"),
    ),
    CapabilityRule(
        "incremental-update",
        "增量更新与新鲜度",
        "如何识别代码变化、复用旧结果并标记失效文档。",
        ("fingerprint", "incremental", "change_detector", "change-detector", "fingerprint_diff", "index-sync"),
    ),
    CapabilityRule(
        "codemap-visualization",
        "Codemap、Tour 与可视化",
        "如何把功能执行链呈现为图、步骤、代码 Tour 或交互视图。",
        ("codemap", "code_map", "code_tour", "code-tour", "tour_generator", "tour-generator", "diagram", "mermaid"),
    ),
    CapabilityRule(
        "agent-workflow",
        "Agent 工作流与 Skill",
        "如何编排分析步骤、保存上下文并把知识交给下一位 Agent。",
        ("skill", "agent", "workflow", "orchestration", "task_registry", "taskregistry"),
    ),
)


def _text(value: object) -> str:
    return str(value or "").lower().replace(" ", "_")


def _matching_paths(index: dict[str, Any], rule: CapabilityRule) -> tuple[list[str], list[str]]:
    path_scores: dict[str, int] = {}
    symbol_ids: list[str] = []
    for file in index.get("files", []):
        path = str(file.get("path", ""))
        haystack = _text(path)
        score = sum(3 for keyword in rule.keywords if keyword in haystack)
        if score:
            path_scores[path] = path_scores.get(path, 0) + score
    for symbol in index.get("symbols", []):
        path = str(symbol.get("path", ""))
        haystack = " ".join((_text(path), _text(symbol.get("name")), _text(symbol.get("qualified_name"))))
        score = sum(5 for keyword in rule.keywords if keyword in haystack)
        if score:
            path_scores[path] = path_scores.get(path, 0) + score
            if symbol.get("id"):
                symbol_ids.append(str(symbol["id"]))
    ordered = sorted(path_scores, key=lambda path: (-path_scores[path], path))
    return ordered[:8], sorted(set(symbol_ids))[:16]


def _technology_tags(index: dict[str, Any], paths: list[str]) -> list[str]:
    tags = list(index.get("stats", {}).get("languages", {}).keys())[:4]
    combined = " ".join(path.lower() for path in paths)
    special = {
        "Tree-sitter": ("tree-sitter", "treesitter"),
        "LSP": ("lsp", "language_server"),
        "SCIP": ("scip",),
        "Mermaid": ("mermaid",),
        "Git fingerprint": ("fingerprint", "change_detector", "incremental"),
    }
    for label, needles in special.items():
        if any(needle in combined for needle in needles):
            tags.append(label)
    return list(dict.fromkeys(tags))


_SCORE_WEIGHTS: dict[str, dict[str, float]] = {
    "code-parsing": {
        "semantic_precision": 0.32,
        "evidence_traceability": 0.20,
        "incremental_efficiency": 0.10,
        "production_readiness": 0.20,
        "reuse_value": 0.18,
    },
    "code-graph": {
        "semantic_precision": 0.25,
        "evidence_traceability": 0.25,
        "incremental_efficiency": 0.05,
        "visualization": 0.10,
        "production_readiness": 0.15,
        "reuse_value": 0.20,
    },
    "component-discovery": {
        "semantic_precision": 0.25,
        "evidence_traceability": 0.20,
        "tutorial_quality": 0.15,
        "incremental_efficiency": 0.05,
        "production_readiness": 0.15,
        "reuse_value": 0.20,
    },
    "tutorial-generation": {
        "evidence_traceability": 0.25,
        "tutorial_quality": 0.30,
        "visualization": 0.10,
        "production_readiness": 0.15,
        "reuse_value": 0.20,
    },
    "evidence-grounding": {
        "semantic_precision": 0.20,
        "evidence_traceability": 0.40,
        "production_readiness": 0.20,
        "reuse_value": 0.20,
    },
    "incremental-update": {
        "semantic_precision": 0.05,
        "evidence_traceability": 0.15,
        "incremental_efficiency": 0.40,
        "production_readiness": 0.20,
        "reuse_value": 0.20,
    },
    "codemap-visualization": {
        "evidence_traceability": 0.20,
        "tutorial_quality": 0.15,
        "visualization": 0.40,
        "production_readiness": 0.10,
        "reuse_value": 0.15,
    },
    "agent-workflow": {
        "semantic_precision": 0.15,
        "evidence_traceability": 0.15,
        "tutorial_quality": 0.10,
        "incremental_efficiency": 0.10,
        "production_readiness": 0.25,
        "reuse_value": 0.25,
    },
}

SCENARIO_PROFILES: dict[str, dict[str, Any]] = {
    "precise-static-analysis": {
        "title": "精确静态分析",
        "weights": {
            "semantic_precision": 0.30,
            "evidence_traceability": 0.25,
            "incremental_efficiency": 0.15,
            "production_readiness": 0.15,
            "reuse_value": 0.10,
            "visualization": 0.05,
        },
    },
    "local-first-product": {
        "title": "本地优先产品",
        "weights": {
            "semantic_precision": 0.10,
            "evidence_traceability": 0.10,
            "tutorial_quality": 0.05,
            "incremental_efficiency": 0.20,
            "visualization": 0.05,
            "production_readiness": 0.25,
            "reuse_value": 0.25,
        },
    },
    "teaching-experience": {
        "title": "代码教学体验",
        "weights": {
            "semantic_precision": 0.10,
            "evidence_traceability": 0.25,
            "tutorial_quality": 0.30,
            "visualization": 0.20,
            "production_readiness": 0.05,
            "reuse_value": 0.10,
        },
    },
    "dynamic-agent-runtime": {
        "title": "动态 Agent 运行时",
        "weights": {
            "semantic_precision": 0.10,
            "evidence_traceability": 0.20,
            "tutorial_quality": 0.10,
            "incremental_efficiency": 0.10,
            "production_readiness": 0.25,
            "reuse_value": 0.25,
        },
    },
}

DEFAULT_SCENARIO = "local-first-product"

# Scenario weights rank implementations *within* a technical object.  This
# separate route prior answers the earlier, more important question: which
# technical object matches the stated job?  It prevents six singleton classes
# from all being presented as recommendations merely because each won itself.
SCENARIO_ROUTE_PRIORITIES: dict[str, dict[str, tuple[str, ...]]] = {
    "precise-static-analysis": {
        "code-parsing": ("deterministic-syntax-index", "type-aware-lsp-index"),
        "code-graph": ("deterministic-code-fact-graph", "semantic-knowledge-graph"),
        "component-discovery": ("graph-clustering-plus-specialist-agents", "static-analysis-plus-llm-review"),
        "tutorial-generation": ("multi-artifact-knowledge-workers", "knowledge-graph-code-tour"),
        "evidence-grounding": ("claim-evidence-gates", "code-entity-provenance"),
        "incremental-update": ("dependency-aware-incremental-rebuild", "fingerprint-staleness-trigger"),
        "codemap-visualization": ("code-tour-plus-architecture-diagram", "validated-architecture-diagram"),
        "agent-workflow": ("fixed-analysis-multi-agent-workflow", "reliable-domain-job-orchestration"),
    },
    "local-first-product": {
        "code-parsing": ("deterministic-syntax-index", "type-aware-lsp-index"),
        "code-graph": ("deterministic-code-fact-graph", "semantic-knowledge-graph"),
        "component-discovery": ("static-graph-plus-hierarchical-llm", "graph-clustering-plus-specialist-agents"),
        "tutorial-generation": ("multi-artifact-knowledge-workers", "fixed-tutorial-dag"),
        "evidence-grounding": ("claim-evidence-gates", "code-entity-provenance"),
        "incremental-update": ("dependency-aware-incremental-rebuild", "fingerprint-staleness-trigger"),
        "codemap-visualization": ("guided-sections-with-citations", "code-tour-plus-architecture-diagram"),
        "agent-workflow": ("dynamic-planner-subagent-runtime", "reliable-domain-job-orchestration"),
    },
    "teaching-experience": {
        "code-parsing": ("deterministic-syntax-index", "text-rag-index"),
        "code-graph": ("guided-code-tour-not-graph", "deterministic-code-fact-graph"),
        "component-discovery": ("static-graph-plus-hierarchical-llm", "llm-wiki-structure-planning"),
        "tutorial-generation": ("fixed-tutorial-dag", "multi-artifact-knowledge-workers"),
        "evidence-grounding": ("claim-evidence-gates", "codemap-snippet-citations"),
        "incremental-update": ("fingerprint-staleness-trigger", "dependency-aware-incremental-rebuild"),
        "codemap-visualization": ("guided-sections-with-citations", "knowledge-graph-dashboard"),
        "agent-workflow": ("fixed-generation-dag", "dynamic-planner-subagent-runtime"),
    },
    "dynamic-agent-runtime": {
        "code-parsing": ("agent-on-demand-reading", "deterministic-syntax-index"),
        "code-graph": ("deterministic-code-fact-graph", "document-navigation-graph"),
        "component-discovery": ("agent-plus-independent-critic", "graph-clustering-plus-specialist-agents"),
        "tutorial-generation": ("agent-written-linked-wiki", "multi-artifact-knowledge-workers"),
        "evidence-grounding": ("process-review-and-link-validation", "claim-evidence-gates"),
        "incremental-update": ("document-metadata-sync", "dependency-aware-incremental-rebuild"),
        "codemap-visualization": ("document-relationship-graph", "guided-sections-with-citations"),
        "agent-workflow": ("dynamic-planner-subagent-runtime", "fixed-analysis-multi-agent-workflow"),
    },
}

# A route order alone explains what the selector did, not why that route is a
# good fit for a product scenario.  Keep the decision contract beside the
# priorities so JSON consumers and the HTML renderer receive the same audited
# rationale instead of inventing prose at presentation time.
SCENARIO_GOALS: dict[str, str] = {
    "precise-static-analysis": "优先得到可重复、可定位到源码的静态事实，尽量减少 LLM 猜测",
    "local-first-product": "优先形成可离线运行、可增量维护且便于产品集成的最小闭环",
    "teaching-experience": "优先让读者沿任务路径理解代码，并能从解释回跳到源码证据",
    "dynamic-agent-runtime": "优先让运行时按任务动态规划、调用工具、复核结果并控制执行边界",
}

SCENARIO_ROUTE_RATIONALES: dict[str, dict[str, dict[str, str]]] = {
    "precise-static-analysis": {
        "code-parsing": {
            "route_fit": "确定性语法索引保留符号、位置和语法结构，适合作为后续事实层",
            "alternative_trigger": "必须解析跨模块类型、重命名或编译器语义",
            "signal_dimension": "semantic_precision",
        },
        "code-graph": {
            "route_fit": "确定性代码事实图能把节点与边回溯到解析结果，便于重复验证",
            "alternative_trigger": "需要跨仓业务实体、文档概念或长期知识关系",
            "signal_dimension": "evidence_traceability",
        },
        "component-discovery": {
            "route_fit": "图聚类先划定候选边界，再由专门 Agent 复核，可降低单次生成的遗漏",
            "alternative_trigger": "仓库规模较小且更看重低成本的一次性静态审阅",
            "signal_dimension": "semantic_precision",
        },
        "tutorial-generation": {
            "route_fit": "多产物知识 Worker 将事实提取、叙事和质量门分开，便于逐段验真",
            "alternative_trigger": "教程必须围绕知识图谱中的实体和关系组织",
            "signal_dimension": "evidence_traceability",
        },
        "evidence-grounding": {
            "route_fit": "claim 证据门把结论绑定到行范围、摘要和置信度，能直接拒绝无依据文字",
            "alternative_trigger": "系统已经有稳定的代码实体 provenance，可直接沿实体链追溯",
            "signal_dimension": "evidence_traceability",
        },
        "incremental-update": {
            "route_fit": "依赖感知重建只刷新受影响事实，能保持大仓库索引的一致性和可解释性",
            "alternative_trigger": "允许整批重算，且只需判断快照是否过期",
            "signal_dimension": "incremental_efficiency",
        },
        "codemap-visualization": {
            "route_fit": "代码游览与架构图并列展示，可以同时核对局部路径和整体结构",
            "alternative_trigger": "只需要经过校验的单张架构图，不需要交互式代码路径",
            "signal_dimension": "evidence_traceability",
        },
        "agent-workflow": {
            "route_fit": "固定分析工作流便于重放步骤、比较产物并定位哪个 Agent 引入偏差",
            "alternative_trigger": "任务更依赖持久队列、重试和领域作业生命周期",
            "signal_dimension": "production_readiness",
        },
    },
    "local-first-product": {
        "code-parsing": {
            "route_fit": "确定性语法索引可内嵌本地进程并离线生成稳定入口，部署面最小",
            "alternative_trigger": "产品必须提供 IDE 级跨文件类型推断和重命名精度",
            "signal_dimension": "production_readiness",
        },
        "code-graph": {
            "route_fit": "确定性事实图能以本地数据结构承载符号与调用边，便于增量持久化",
            "alternative_trigger": "主要价值转向跨代码与文档的语义知识导航",
            "signal_dimension": "incremental_efficiency",
        },
        "component-discovery": {
            "route_fit": "静态图先压缩搜索空间，分层 LLM 再命名组件，能控制本地推理成本",
            "alternative_trigger": "超大仓库需要图聚类和多个专家并行处理",
            "signal_dimension": "reuse_value",
        },
        "tutorial-generation": {
            "route_fit": "多产物 Worker 可独立更新摘要、教程和故事页，适合持续演进的产品内容",
            "alternative_trigger": "只需要一种固定教程产物，且更重视流程简单可预测",
            "signal_dimension": "production_readiness",
        },
        "evidence-grounding": {
            "route_fit": "claim 级证据门能在本地发布前阻止无源码支撑的结论进入知识库",
            "alternative_trigger": "产品已有统一代码实体库，需要复用其 provenance 模型",
            "signal_dimension": "evidence_traceability",
        },
        "incremental-update": {
            "route_fit": "依赖感知更新可缩短编辑后的反馈时间，并避免每次扫描整个仓库",
            "alternative_trigger": "仓库很小或更新很少，指纹失效后整批重建更经济",
            "signal_dimension": "incremental_efficiency",
        },
        "codemap-visualization": {
            "route_fit": "带引用的引导章节直接对应用户阅读任务，比先展示完整关系图更易落地",
            "alternative_trigger": "用户必须同时理解跨模块架构和多条代码游览路径",
            "signal_dimension": "visualization",
        },
        "agent-workflow": {
            "route_fit": "动态 Planner 可按每次需求组装子任务和工具，无需为新问题预置固定 DAG",
            "alternative_trigger": "生产可靠性要求持久作业、幂等重试和明确队列语义优先",
            "signal_dimension": "reuse_value",
        },
    },
    "teaching-experience": {
        "code-parsing": {
            "route_fit": "确定性语法索引提供稳定符号锚点，使讲解中的名称和行号可以点击核对",
            "alternative_trigger": "课程以自然语言检索为主，不要求精确符号和调用关系",
            "signal_dimension": "evidence_traceability",
        },
        "code-graph": {
            "route_fit": "引导式代码游览按学习顺序组织路径，避免把完整图结构直接压给读者",
            "alternative_trigger": "需要教学调用关系、依赖拓扑或可计算的代码事实",
            "signal_dimension": "tutorial_quality",
        },
        "component-discovery": {
            "route_fit": "静态图提供边界，分层 LLM 把组件转成读者能理解的业务与技术层次",
            "alternative_trigger": "目标是生成整站 Wiki 目录而不是解释真实组件边界",
            "signal_dimension": "tutorial_quality",
        },
        "tutorial-generation": {
            "route_fit": "固定教程 DAG 保证从概览到模块再到源码的学习顺序一致且可重复",
            "alternative_trigger": "需要多种受众、故事页或独立质量 Worker 并行产出",
            "signal_dimension": "tutorial_quality",
        },
        "evidence-grounding": {
            "route_fit": "claim 级证据门让每段教学结论都能回到源码范围，减少看似合理的误导",
            "alternative_trigger": "重点是代码片段级交互引用，而不是对所有自然语言 claim 做门禁",
            "signal_dimension": "evidence_traceability",
        },
        "incremental-update": {
            "route_fit": "指纹失效触发能明确提示教程已过期，适合低频更新的教学产物",
            "alternative_trigger": "教程需要跟随频繁提交只更新受影响章节",
            "signal_dimension": "incremental_efficiency",
        },
        "codemap-visualization": {
            "route_fit": "带引用的引导章节把阅读步骤、代码片段和跳转位置放在同一界面",
            "alternative_trigger": "读者需要自由探索实体关系，而不是按预设章节学习",
            "signal_dimension": "tutorial_quality",
        },
        "agent-workflow": {
            "route_fit": "固定生成 DAG 让课程结构和质量检查顺序稳定，便于比较不同版本",
            "alternative_trigger": "访谈过程中需要按读者追问动态改变讲解计划",
            "signal_dimension": "tutorial_quality",
        },
    },
    "dynamic-agent-runtime": {
        "code-parsing": {
            "route_fit": "Agent 按需读取只为当前任务取上下文，可避免预先索引与问题无关的仓库区域",
            "alternative_trigger": "多个 Agent 必须共享稳定符号 ID、调用边或可重复事实",
            "signal_dimension": "reuse_value",
        },
        "code-graph": {
            "route_fit": "确定性事实图给动态规划器提供可查询边界，避免运行时完全依赖语言模型记忆",
            "alternative_trigger": "运行时主要在文档、任务和会话之间导航，而非分析源码调用关系",
            "signal_dimension": "semantic_precision",
        },
        "component-discovery": {
            "route_fit": "独立 critic 能在 Agent 提议组件后再次查证，适合开放式任务中的动态纠错",
            "alternative_trigger": "超大仓库需要先用图聚类固定分区，再并行调度专家",
            "signal_dimension": "production_readiness",
        },
        "tutorial-generation": {
            "route_fit": "Agent 编写链接 Wiki 可根据任务临时扩展页面与关系，不受固定产物集合限制",
            "alternative_trigger": "需要稳定的多产物管线、统一阈值和批量质量门",
            "signal_dimension": "reuse_value",
        },
        "evidence-grounding": {
            "route_fit": "过程复核和链接校验可嵌入每次 Agent 行动，及时拦截失效引用",
            "alternative_trigger": "结论必须以行范围、摘要和置信度形成可审计 claim 包",
            "signal_dimension": "production_readiness",
        },
        "incremental-update": {
            "route_fit": "文档元数据同步适合 Agent 持续增删页面和关系，不必重建完整代码索引",
            "alternative_trigger": "底层代码事实变化需要沿依赖图精确传播",
            "signal_dimension": "incremental_efficiency",
        },
        "codemap-visualization": {
            "route_fit": "文档关系图能直接呈现 Agent 新建的页面、任务与知识连接",
            "alternative_trigger": "用户更需要逐步代码讲解与行级引用，而不是自由关系浏览",
            "signal_dimension": "visualization",
        },
        "agent-workflow": {
            "route_fit": "动态 Planner 可在运行时选择角色、工具和执行顺序，直接匹配开放式委派",
            "alternative_trigger": "任务必须可预测重放，且固定分析阶段比运行时适配更重要",
            "signal_dimension": "production_readiness",
        },
    },
}

_SIGNAL_LABELS = {
    "semantic_precision": "语义精度",
    "evidence_traceability": "证据可追溯",
    "tutorial_quality": "教程表达",
    "incremental_efficiency": "增量效率",
    "visualization": "可视化",
    "production_readiness": "生产准备度",
    "reuse_value": "架构参考价值",
}

SCORE_UNCERTAINTY = 5


def _weighted_score(capability_slug: str, dimensions: dict[str, int]) -> int:
    weights = _SCORE_WEIGHTS[capability_slug]
    return round(sum(dimensions.get(dimension, 0) * weight for dimension, weight in weights.items()))


def _profile_scores(dimensions: dict[str, int]) -> dict[str, int]:
    return {
        slug: round(sum(dimensions.get(dimension, 0) * weight for dimension, weight in profile["weights"].items()))
        for slug, profile in SCENARIO_PROFILES.items()
    }


def _valid_evidence_records(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    project = index.get("project", {}) if isinstance(index.get("project"), dict) else {}
    root = Path(str(project.get("path") or ""))
    resolved_root = root.resolve() if root.is_absolute() and root.is_dir() else None
    for raw in index.get("evidence", []):
        if not isinstance(raw, dict):
            continue
        identifier = raw.get("id")
        path = raw.get("path")
        start = raw.get("line_start")
        end = raw.get("line_end")
        digest = raw.get("snippet_sha256")
        if not (
            isinstance(identifier, str)
            and identifier
            and isinstance(path, str)
            and path
            and isinstance(start, int)
            and isinstance(end, int)
            and 1 <= start <= end
            and isinstance(digest, str)
            and len(digest) == 64
        ):
            continue
        relative = PurePosixPath(path)
        if resolved_root is None or relative.is_absolute() or ".." in relative.parts:
            continue
        candidate = (resolved_root / Path(*relative.parts)).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        if end > len(lines):
            continue
        source_snippet = "\n".join(lines[start - 1 : end])
        actual_digest = hashlib.sha256(source_snippet.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual_digest, digest) or redact_secrets(source_snippet) != raw.get("snippet"):
            continue
        if identifier in records:
            duplicate_ids.add(identifier)
        records[identifier] = raw
    for identifier in duplicate_ids:
        records.pop(identifier, None)
    return records


def _safe_source_uri(project_path: object, source_path: str) -> str | None:
    relative = PurePosixPath(source_path)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    root = Path(str(project_path or ""))
    if not root.is_absolute() or not root.is_dir():
        return None
    resolved_root = root.resolve()
    candidate = (resolved_root / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return candidate.as_uri() if candidate.is_file() else None


def _claim_reference(index: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any] | None:
    """Build a hash-bound claim reference from an audited catalog line range."""

    project = index.get("project", {}) if isinstance(index.get("project"), dict) else {}
    root = Path(str(project.get("path") or ""))
    path = str(raw.get("path") or "")
    start = raw.get("line_start")
    end = raw.get("line_end")
    claim = str(raw.get("claim") or "").strip()
    if not root.is_absolute() or not isinstance(start, int) or not isinstance(end, int) or not claim:
        return None
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts or start < 1 or end < start:
        return None
    resolved_root = root.resolve()
    candidate = (resolved_root / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return None
    try:
        lines = candidate.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    if end > len(lines):
        return None
    snippet = "\n".join(lines[start - 1 : end])
    digest = hashlib.sha256(snippet.encode("utf-8")).hexdigest()
    return {
        "path": path,
        "line_start": start,
        "line_end": end,
        "source_uri": candidate.as_uri(),
        "source_location": f"{path}:{start}-{end}",
        "reference_scope": "claim-evidence",
        "evidence_scope": "claim",
        "supports_claim": True,
        "supports_option_claim": True,
        "claim": claim,
        "claim_evidence_id": stable_id("catalog-claim", resolved_root, path, start, end, digest, claim),
        "snippet": redact_secrets(snippet),
        "snippet_sha256": digest,
        "evidence_ids": [],
        "symbol_ids": [],
    }


def _source_references(
    index: dict[str, Any], paths: list[str], claims: list[dict[str, Any]] | None = None
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    files = {
        str(item.get("path")): item
        for item in index.get("files", [])
        if isinstance(item, dict) and item.get("path")
    }
    symbols_by_path: dict[str, list[dict[str, Any]]] = {}
    for symbol in index.get("symbols", []):
        if isinstance(symbol, dict) and symbol.get("path") and symbol.get("id"):
            symbols_by_path.setdefault(str(symbol["path"]), []).append(symbol)
    evidence = _valid_evidence_records(index)
    evidence_by_path: dict[str, list[dict[str, Any]]] = {}
    for record in evidence.values():
        evidence_by_path.setdefault(str(record["path"]), []).append(record)

    references: list[dict[str, Any]] = []
    evidence_ids: set[str] = set()
    symbol_ids: set[str] = set()
    project_path = index.get("project", {}).get("path") if isinstance(index.get("project"), dict) else None
    claims_by_path: dict[str, list[dict[str, Any]]] = {}
    for raw_claim in claims or []:
        if isinstance(raw_claim, dict) and raw_claim.get("path"):
            claims_by_path.setdefault(str(raw_claim["path"]), []).append(raw_claim)
    for path in paths:
        file = files.get(path)
        if file is None:
            continue
        path_symbols = sorted(symbols_by_path.get(path, []), key=lambda item: (item.get("line", 0), str(item["id"])))
        path_evidence = sorted(
            evidence_by_path.get(path, []),
            key=lambda item: (item["line_start"], item["line_end"], item["id"]),
        )
        current_evidence_ids = [str(item["id"]) for item in path_evidence]
        current_symbol_ids = [str(item["id"]) for item in path_symbols]
        evidence_ids.update(current_evidence_ids)
        symbol_ids.update(current_symbol_ids)
        claim_references = [
            reference
            for raw_claim in claims_by_path.get(path, [])
            if (reference := _claim_reference(index, raw_claim)) is not None
        ]
        if claim_references:
            for reference in claim_references:
                reference["file_id"] = file.get("id")
                reference["file_sha256"] = file.get("sha256")
            references.extend(claim_references)
            continue
        first_evidence = path_evidence[0] if path_evidence else None
        first_symbol = path_symbols[0] if path_symbols else None
        line_start = int(first_evidence["line_start"]) if first_evidence else int(first_symbol.get("line", 1) if first_symbol else 1)
        line_end = int(first_evidence["line_end"]) if first_evidence else int(first_symbol.get("end_line", line_start) if first_symbol else file.get("lines", 1) or 1)
        evidence_scope = "index-evidence-context" if first_evidence else (
            "symbol-definition" if first_symbol else "whole-file-context"
        )
        digest = first_evidence.get("snippet_sha256") if first_evidence else None
        if first_symbol and not digest:
            contextual = _claim_reference(
                index,
                {
                    "path": path,
                    "line_start": max(1, line_start),
                    "line_end": max(max(1, line_start), line_end),
                    "claim": f"源码在此定义符号 {first_symbol.get('qualified_name') or first_symbol.get('name') or 'unknown'}；此范围只证明入口存在。",
                },
            )
            digest = contextual.get("snippet_sha256") if contextual else None
        references.append(
            {
                "path": path,
                "file_id": file.get("id"),
                "file_sha256": file.get("sha256"),
                "line_start": max(1, line_start),
                "line_end": max(max(1, line_start), line_end),
                "source_uri": _safe_source_uri(project_path, path),
                "source_location": f"{path}:{max(1, line_start)}-{max(max(1, line_start), line_end)}",
                "evidence_ids": current_evidence_ids,
                "symbol_ids": current_symbol_ids[:24],
                "reference_scope": "index-evidence" if path_evidence else ("symbol-context" if path_symbols else "file-context"),
                "evidence_scope": evidence_scope,
                "supports_claim": False,
                "supports_option_claim": False,
                "claim": "上下文入口；此范围不单独证明该方案的自然语言结论。",
                "snippet_sha256": digest,
            }
        )
    return references, sorted(evidence_ids), sorted(symbol_ids)


def _license_decision(value: object) -> tuple[str, str]:
    license_name = str(value or "").strip()
    if not license_name or license_name.lower() in {"unknown", "none", "not-detected"}:
        return "unknown", "needs-license-review"
    return "declared", "requires-compatibility-review"


def _curated_option(
    index: dict[str, Any], rule: CapabilityRule, entry: dict[str, Any], project_report_href: str
) -> dict[str, Any]:
    project = index.get("project", {})
    name = str(project.get("name") or entry["project_key"])
    paths = list(entry["source_paths"])
    dimensions = dict(entry["dimension_scores"])
    source_references, evidence_ids, symbol_ids = _source_references(index, paths, list(entry.get("source_claims", [])))
    claim_evidence_ids = [
        str(reference["claim_evidence_id"])
        for reference in source_references
        if reference.get("claim_evidence_id")
    ]
    license_status, code_reuse_status = _license_decision(project.get("license"))
    identifier = stable_id("option", name, project.get("commit") or project.get("path"), rule.slug)
    return {
        "id": identifier,
        "project_id": stable_id("project", name, project.get("path", "")),
        "project_key": entry["project_key"],
        "project_name": name,
        "project_path": project.get("path"),
        "project_report_href": project_report_href,
        "remote": f"https://{entry['identity']['remote']}.git",
        "commit": entry["identity"]["commit"],
        "license": project.get("license"),
        "capability_slug": rule.slug,
        "title": f"{name} 的{rule.title}实现",
        "summary": entry["summary"],
        "approach": entry["approach"],
        "data_flow": list(entry["data_flow"]),
        "technology_tags": list(entry["technology_tags"]),
        "source_paths": paths,
        "source_references": source_references,
        "evidence_ids": evidence_ids,
        "claim_evidence_ids": claim_evidence_ids,
        "symbol_ids": symbol_ids,
        "strengths": list(entry["strengths"]),
        "limitations": list(entry["limitations"]),
        "reuse_verdict": entry["reuse_verdict"],
        "dimension_scores": dimensions,
        "score": _weighted_score(rule.slug, dimensions),
        "scenario_scores": _profile_scores(dimensions),
        "score_basis": "reviewer-rubric-signal",
        "score_uncertainty": SCORE_UNCERTAINTY,
        "confidence": "source-audited",
        "source": entry["source"],
        "comparison_class": entry["comparison_class"],
        "catalog_revision": entry["catalog_revision"],
        "identity": entry["identity"],
        "license_status": license_status,
        "architecture_reference": entry["reuse_verdict"],
        "code_reuse_status": code_reuse_status,
    }


def _option(
    index: dict[str, Any], rule: CapabilityRule, paths: list[str], matched_symbol_ids: list[str], project_report_href: str
) -> dict[str, Any]:
    project = index.get("project", {})
    name = str(project.get("name") or "Unnamed")
    exact_symbols = sum(
        1
        for symbol in index.get("symbols", [])
        if symbol.get("path") in paths and symbol.get("confidence") == "exact"
    )
    test_paths = [path for path in paths if "test" in path.lower()]
    score = min(100, 35 + min(30, len(paths) * 4) + min(25, exact_symbols * 3) + min(10, len(test_paths) * 5))
    dimensions = {
        "semantic_precision": min(75, 30 + exact_symbols * 5),
        "evidence_traceability": min(75, 30 + exact_symbols * 4 + len(paths) * 2),
        "tutorial_quality": 35,
        "incremental_efficiency": 30,
        "visualization": 35,
        "production_readiness": min(70, 35 + len(test_paths) * 8),
        "reuse_value": min(70, 35 + len(paths) * 3),
    }
    identifier = stable_id("option", name, project.get("commit") or project.get("path"), rule.slug)
    source_references, evidence_ids, source_symbol_ids = _source_references(index, paths)
    symbol_ids = sorted(set(matched_symbol_ids) | set(source_symbol_ids))
    license_status, code_reuse_status = _license_decision(project.get("license"))
    identity_status = reference_identity_status(index)
    return {
        "id": identifier,
        "project_id": stable_id("project", name, project.get("path", "")),
        "project_name": name,
        "project_path": project.get("path"),
        "project_report_href": project_report_href,
        "remote": project.get("remote"),
        "commit": project.get("commit"),
        "license": project.get("license"),
        "capability_slug": rule.slug,
        "title": f"{name} 的{rule.title}实现",
        "summary": f"从 {len(paths)} 个源码入口观察 {name} 如何实现{rule.title}；结论需沿下列路径继续核对。",
        "approach": "以命中的文件和符号为入口，沿定义、导入与调用证据还原实现链。",
        "data_flow": ["关键词命中", "源码入口", "定义/导入/调用证据", "人工核对"],
        "technology_tags": _technology_tags(index, paths),
        "source_paths": paths,
        "source_references": source_references,
        "evidence_ids": evidence_ids,
        "claim_evidence_ids": [],
        "symbol_ids": symbol_ids,
        "strengths": ["存在可回到源码的实现入口"] + (["命中精确符号证据"] if exact_symbols else []),
        "limitations": ["自动分类只证明存在相关实现，不等于完整覆盖动态行为"],
        "reuse_verdict": "优先阅读源码入口；在确认许可证、测试和依赖边界后决定直接复用或干净重写。",
        "score": score,
        "dimension_scores": dimensions,
        "scenario_scores": _profile_scores(dimensions),
        "score_basis": "heuristic-signal",
        "score_uncertainty": 15,
        "confidence": "heuristic-with-exact-symbols" if exact_symbols else "heuristic",
        "source": "heuristic-index-match",
        "comparison_class": "unclassified-heuristic-match",
        "curated_identity_status": identity_status,
        "license_status": license_status,
        "architecture_reference": "仅作为源码阅读入口；需人工验证完整实现链。",
        "code_reuse_status": code_reuse_status,
    }


def _project_report_hrefs(indexes: list[dict[str, Any]]) -> dict[int, str]:
    hrefs: dict[int, str] = {}
    used: set[str] = set()
    for index in indexes:
        project = index.get("project", {}) if isinstance(index.get("project"), dict) else {}
        source_name = Path(str(project.get("path") or "repository")).name
        base = "".join(character if character.isalnum() or character in "-_" else "-" for character in source_name)
        base = base or "repository"
        slug = base
        counter = 2
        while slug in used:
            slug = f"{base}-{counter}"
            counter += 1
        used.add(slug)
        hrefs[id(index)] = f"projects/{slug}/index.html"
    return hrefs


def _recommendation_groups(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for option in options:
        grouped.setdefault(str(option.get("comparison_class") or "unclassified"), []).append(option)
    recommendations: list[dict[str, Any]] = []
    for comparison_class, members in sorted(grouped.items()):
        best = max((int(item.get("score", 0)) for item in members), default=0)
        uncertainty = max((int(item.get("score_uncertainty", SCORE_UNCERTAINTY)) for item in members), default=0)
        candidate_ids = [
            str(item["id"])
            for item in sorted(members, key=lambda item: (-int(item.get("score", 0)), str(item.get("project_name", ""))))
            if best - int(item.get("score", 0)) <= uncertainty
        ]
        recommendations.append(
            {
                "comparison_class": comparison_class,
                "candidate_option_ids": candidate_ids,
                "top_signal": best,
                "uncertainty": uncertainty,
                "basis": "reviewer-rubric-signal",
            }
        )
    return recommendations


def _first_text(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return fallback


def _decision_reason(
    capability_slug: str,
    scenario: str,
    preferred_class: str,
    primary: list[dict[str, Any]],
    alternative: list[dict[str, Any]],
    priorities: tuple[str, ...],
) -> tuple[dict[str, Any], str]:
    rationale = SCENARIO_ROUTE_RATIONALES.get(scenario, {}).get(capability_slug, {})
    scenario_goal = SCENARIO_GOALS.get(
        scenario,
        f"在 {SCENARIO_PROFILES.get(scenario, {}).get('title', scenario)} 场景中缩小实现路线",
    )
    intended_route = priorities[0] if priorities else preferred_class
    route_fit = rationale.get(
        "route_fit",
        f"{preferred_class} 是当前候选中与场景信号最接近的可验证技术对象",
    )
    if intended_route != preferred_class:
        route_fit = (
            f"目标路线 {intended_route} 当前没有可用候选；"
            f"{preferred_class} 作为现有证据中最接近的替代起点"
        )
    signal_dimension = rationale.get("signal_dimension", "production_readiness")
    signal_label = _SIGNAL_LABELS.get(signal_dimension, signal_dimension.replace("_", " "))
    primary_option = primary[0] if primary else {}
    primary_strength = _first_text(
        primary_option.get("strengths"),
        _first_text(
            primary_option.get("approach"),
            _first_text(primary_option.get("summary"), "已有源码入口可继续验证"),
        ),
    )
    dimensions = primary_option.get("dimension_scores")
    signal_value = dimensions.get(signal_dimension) if isinstance(dimensions, dict) else None
    signal_source = "dimension_scores"
    if not isinstance(signal_value, int):
        scenario_scores = primary_option.get("scenario_scores")
        signal_value = scenario_scores.get(scenario) if isinstance(scenario_scores, dict) else None
        signal_source = "scenario_scores"
    if not isinstance(signal_value, int):
        signal_value = int(primary_option.get("score", 0))
        signal_source = "overall_reviewer_signal"
    critical_limit = _first_text(primary_option.get("limitations"), "动态行为、性能与许可证仍需 PoC")
    alternative_trigger = rationale.get(
        "alternative_trigger", "首选路线不能满足生产约束或源码验证未通过"
    )
    alternative_option = alternative[0] if alternative else {}
    alternative_class = str(alternative_option.get("comparison_class") or "暂无可比较路线")
    primary_names = " / ".join(str(item.get("project_name") or "未命名") for item in primary) or "证据不足"
    alternative_names = " / ".join(
        str(item.get("project_name") or "未命名") for item in alternative
    ) or "暂无"
    reason = {
        "scenario_goal": scenario_goal,
        "preferred_mechanism": preferred_class,
        "route_fit": route_fit,
        "primary_strength": primary_strength,
        "primary_signal": {
            "dimension": signal_dimension,
            "label": signal_label,
            "value": signal_value,
            "source": signal_source,
        },
        "critical_limit": critical_limit,
        "alternative_trigger": alternative_trigger,
        "alternative_mechanism": alternative_class,
        "alternative_projects": alternative_names,
    }
    signal_text = f"{signal_label} {signal_value}/100"
    if scenario == "precise-static-analysis":
        why = (
            f"为了{scenario_goal}，{route_fit}。{primary_names} 以“{primary_strength}”提供首选依据"
            f"（{signal_text}）；当前先验证“{critical_limit}”。若{alternative_trigger}，"
            f"切换到 {alternative_class}（{alternative_names}）。"
        )
    elif scenario == "local-first-product":
        why = (
            f"产品落地要{scenario_goal}，所以{route_fit}；{primary_names} 凭“{primary_strength}”"
            f"和 {signal_text} 成为首选。落地前必须处理“{critical_limit}”；当{alternative_trigger}时，"
            f"改看 {alternative_class}（{alternative_names}）。"
        )
    elif scenario == "teaching-experience":
        why = (
            f"教学目标是{scenario_goal}。{route_fit}；{primary_names} 的“{primary_strength}”"
            f"与 {signal_text} 最匹配。遇到{alternative_trigger}时，用 {alternative_class}"
            f"（{alternative_names}）补足，同时保留对“{critical_limit}”的验证。"
        )
    else:
        why = (
            f"运行时要{scenario_goal}，此时{route_fit}比跨路线总分更关键。{primary_names} 因“{primary_strength}”"
            f"及 {signal_text} 入选；若{alternative_trigger}，转向 {alternative_class}（{alternative_names}），"
            f"并把“{critical_limit}”设为执行门。"
        )
    return reason, why


def _scenario_recommendation(
    capability_slug: str, options: list[dict[str, Any]], scenario: str
) -> dict[str, Any]:
    priorities = SCENARIO_ROUTE_PRIORITIES.get(scenario, {}).get(capability_slug, ())
    classes = {str(option.get("comparison_class") or "unclassified") for option in options}
    preferred_class = next((route for route in priorities if route in classes), None)
    if preferred_class is None:
        preferred_class = str(max(options, key=lambda item: item.get("scenario_scores", {}).get(scenario, 0)).get("comparison_class"))
    members = [option for option in options if option.get("comparison_class") == preferred_class]
    ordered = sorted(
        members,
        key=lambda item: (-int(item.get("scenario_scores", {}).get(scenario, 0)), str(item.get("project_name", ""))),
    )
    top = int(ordered[0].get("scenario_scores", {}).get(scenario, 0)) if ordered else 0
    uncertainty = max((int(item.get("score_uncertainty", SCORE_UNCERTAINTY)) for item in ordered), default=0)
    primary = [item for item in ordered if top - int(item.get("scenario_scores", {}).get(scenario, 0)) <= uncertainty]

    alternative: list[dict[str, Any]] = []
    for route in priorities:
        if route == preferred_class:
            continue
        candidates = [option for option in options if option.get("comparison_class") == route]
        if candidates:
            alternative = [
                max(candidates, key=lambda item: int(item.get("scenario_scores", {}).get(scenario, 0)))
            ]
            break
    if not alternative:
        remaining = [option for option in options if option.get("comparison_class") != preferred_class]
        if remaining:
            alternative = [max(remaining, key=lambda item: int(item.get("scenario_scores", {}).get(scenario, 0)))]

    primary_names = " / ".join(str(item.get("project_name") or "未命名") for item in primary) or "证据不足"
    alternative_names = " / ".join(str(item.get("project_name") or "未命名") for item in alternative) or "暂无"
    module_plan = [
        {
            "role": "首选路线",
            "project_name": item.get("project_name"),
            "source_paths": list(item.get("source_paths", []))[:3],
            "source_references": [
                dict(reference) for reference in list(item.get("source_references") or [])[:3] if isinstance(reference, dict)
            ],
        }
        for item in primary
    ] + [
        {
            "role": "备选/补充路线",
            "project_name": item.get("project_name"),
            "source_paths": list(item.get("source_paths", []))[:2],
            "source_references": [
                dict(reference) for reference in list(item.get("source_references") or [])[:2] if isinstance(reference, dict)
            ],
        }
        for item in alternative
    ]
    route_size = len(members)
    confidence = "并列：差值落在人工信号不确定性内" if len(primary) > 1 else (
        "路线仅有一个参考实现，需用 PoC 验证" if route_size == 1 else "路线内首选，仍需 PoC"
    )
    decision_reason, why = _decision_reason(
        capability_slug,
        scenario,
        preferred_class,
        primary,
        alternative,
        priorities,
    )
    return {
        "scenario": scenario,
        "scenario_title": SCENARIO_PROFILES.get(scenario, {}).get("title", scenario),
        "preferred_class": preferred_class,
        "primary_option_ids": [str(item["id"]) for item in primary],
        "alternative_option_ids": [str(item["id"]) for item in alternative],
        "primary_projects": primary_names,
        "alternative_projects": alternative_names,
        "top_signal": top,
        "uncertainty": uncertainty,
        "confidence": confidence,
        "decision_reason": decision_reason,
        "why": why,
        "tradeoff": str((primary[0].get("limitations") or ["动态行为、性能与许可仍需独立验证"])[0]) if primary else "证据不足",
        "module_plan": module_plan,
    }


def _scenario_recommendations(capability_slug: str, options: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        scenario: _scenario_recommendation(capability_slug, options, scenario)
        for scenario in SCENARIO_PROFILES
    }


def build_technology_comparison(indexes: list[dict[str, Any]]) -> dict[str, Any]:
    options: list[dict[str, Any]] = []
    capabilities: list[dict[str, Any]] = []
    report_hrefs = _project_report_hrefs(indexes)
    for rule in CAPABILITY_RULES:
        rule_options: list[dict[str, Any]] = []
        for index in indexes:
            project_href = report_hrefs[id(index)]
            curated = curated_implementation(index, rule.slug)
            if curated is not None:
                rule_options.append(_curated_option(index, rule, curated, project_href))
                continue
            paths, symbol_ids = _matching_paths(index, rule)
            if paths:
                rule_options.append(_option(index, rule, paths, symbol_ids, project_href))
        if not rule_options:
            continue
        rule_options.sort(key=lambda item: (-item["score"], item["project_name"]))
        options.extend(rule_options)
        recommendation_groups = _recommendation_groups(rule_options)
        scenario_recommendations = _scenario_recommendations(rule.slug, rule_options)
        selected = scenario_recommendations[DEFAULT_SCENARIO]
        candidate_ids = list(selected["primary_option_ids"])
        capabilities.append(
            {
                "id": stable_id("capability", rule.slug),
                "slug": rule.slug,
                "title": rule.title,
                "description": rule.description,
                "option_ids": [item["id"] for item in rule_options],
                "recommendation_option_ids": candidate_ids,
                "recommendation_groups": recommendation_groups,
                "default_scenario": DEFAULT_SCENARIO,
                "scenario_recommendations": scenario_recommendations,
                "selected_recommendation": selected,
                "recommendation": selected["why"],
                "decision_factors": ["源码证据完整度", "调用关系精度", "增量能力", "测试与 CI", "许可证与部署成本"],
            }
        )
    options.sort(key=lambda item: (item["capability_slug"], -item["score"], item["project_name"]))
    claim_evidence_by_id: dict[str, dict[str, Any]] = {}
    for option in options:
        for reference in option.get("source_references", []):
            claim_id = reference.get("claim_evidence_id") if isinstance(reference, dict) else None
            if not claim_id:
                continue
            claim_evidence_by_id.setdefault(
                str(claim_id),
                {
                    "id": str(claim_id),
                    "project_id": option["project_id"],
                    "option_id": option["id"],
                    "capability_slug": option["capability_slug"],
                    "path": reference["path"],
                    "line_start": reference["line_start"],
                    "line_end": reference["line_end"],
                    "snippet": reference["snippet"],
                    "snippet_sha256": reference["snippet_sha256"],
                    "claim": reference["claim"],
                    "kind": "catalog-claim",
                    "confidence": "source-audited",
                },
            )
    projects: list[dict[str, Any]] = []
    for index in indexes:
        project = dict(index.get("project", {})) if isinstance(index.get("project"), dict) else {}
        project["report_href"] = report_hrefs[id(index)]
        identity_status = reference_identity_status(index)
        project["identity_status"] = identity_status
        if identity_status.get("status") == "verified":
            project["remote"] = f"https://{identity_status['remote']}.git"
            project["commit"] = identity_status["head"]
        project["integrity_sha256"] = index.get("integrity_sha256")
        projects.append(project)
    return {
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": {"name": "repo-teacher", "catalog_revision": CATALOG_REVISION},
        "score_methodology": {
            "kind": "reviewer-rubric-signal",
            "objective_benchmark": False,
            "levels": SCORE_RUBRIC,
            "uncertainty": SCORE_UNCERTAINTY,
            "capability_weights": _SCORE_WEIGHTS,
            "scenario_profiles": SCENARIO_PROFILES,
            "default_scenario": DEFAULT_SCENARIO,
            "scenario_route_priorities": SCENARIO_ROUTE_PRIORITIES,
            "scenario_goals": SCENARIO_GOALS,
            "scenario_route_rationales": SCENARIO_ROUTE_RATIONALES,
            "tie_policy": "scores within the declared uncertainty are co-candidates",
        },
        "projects": projects,
        "capabilities": capabilities,
        "options": options,
        "options_by_id": {item["id"]: item for item in options},
        "claim_evidence": sorted(claim_evidence_by_id.values(), key=lambda item: item["id"]),
    }
