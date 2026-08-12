from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Literal


_REFERENCE_CONTRIBUTIONS: tuple[dict[str, str], ...] = (
    {
        "project": "sourcebridge",
        "mechanism": "进程内代码图、保守执行路径与带源码门禁的 code tour",
        "mapping": "映射到本产品的关系索引、能力路径与可点击证据切片",
        "paths": (
            "internal/graph/store.go:225-380 · internal/graph/execution_path.go:22-140 · "
            "workers/knowledge/code_tour.py:38-181"
        ),
        "boundary": "采用静态图与证据门禁；未照搬 Go 内存状态、测试注入接口，也不把静态路径称为运行时 trace。",
    },
    {
        "project": "pocketflow-code2tutorial",
        "mechanism": "显式教程工作流、抽象关系整理与章节合成",
        "mapping": "映射到本产品的总—分—总教程结构与确定性阅读顺序",
        "paths": "flow.py:12-33 · nodes.py:85-116,241-287,410-470,538-620,754-830",
        "boundary": "采用阶段化教学职责；未引入 PocketFlow 运行时，也不让 LLM 生成未经源码证据约束的事实。",
    },
    {
        "project": "openwiki",
        "mechanism": "知识骨架 critic、Wiki 链接校验与多来源摄取编排",
        "mapping": "映射到本产品的证据缺口、复用边界与知识产物完整性检查",
        "paths": (
            "src/agent/skeleton_critic.ts:7-68 · src/agent/wiki-link-validator.ts:92-457 · "
            "src/ingestion/ingestion.ts:63-359"
        ),
        "boundary": "采用审查与链接闭包思想；未照搬连接器运行时或自动写入知识库的 Agent 行为。",
    },
    {
        "project": "understand-anything",
        "mechanism": "知识图搜索后一跳扩展、分层 onboarding 与定点 explain 上下文",
        "mapping": "映射到本产品的有界上下文、入门导览与按目标解释",
        "paths": (
            "understand-anything-plugin/src/context-builder.ts:25-140 · "
            "understand-anything-plugin/src/onboard-builder.ts:7-123 · "
            "understand-anything-plugin/src/explain-builder.ts:22-159"
        ),
        "boundary": "采用一跳有界图上下文；未采用无界 BFS，也不把提示文本当作已验证实现结论。",
    },
    {
        "project": "codeboarding",
        "mechanism": "全量 CLI 基线、LSP/语言适配调用图与组件聚类",
        "mapping": "映射到本产品的冷索引基线、resolved relationship 与模块导航",
        "paths": (
            "codeboarding_cli/commands/full_analysis.py:25-117 · "
            "static_analyzer/engine/call_graph_builder.py:24-313 · "
            "static_analyzer/cluster_helpers.py:48-533"
        ),
        "boundary": "采用调用点与定义闭包；未照搬 LSP 服务生命周期、Leiden 依赖或增量聚类缓存。",
    },
    {
        "project": "deepwiki-open",
        "mechanism": "CodeMap 服务编排、引用重新落地、结构降级解析与源码查看器",
        "mapping": "映射到本产品的代码地图、真实行号证据与可点击源码定位",
        "paths": (
            "api/services/codemap.py:46-312 · api/services/wiki/structure.py:70-180 · "
            "src/components/CodeMap.tsx:19-154 · src/components/CodeViewer.tsx:27-140"
        ),
        "boundary": "采用引用落地与 UI 定位；未把 RAG/模型输出直接视为事实，也未照搬其服务端与 React 应用。",
    },
)


def _safe_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def _human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    rendered = str(value).strip()
    return rendered or fallback


def _render_languages(languages: dict[str, int]) -> str:
    if not languages:
        return '<span class="muted">未识别源码语言</span>'
    cleaned = {str(language): max(0, _as_int(count)) for language, count in languages.items()}
    maximum = max(cleaned.values(), default=0) or 1
    parts = []
    for language, count in cleaned.items():
        width = max(8, round(count / maximum * 100))
        parts.append(
            f'<div class="language-row"><span>{html.escape(language)}</span>'
            f'<i><b style="width:{width}%"></b></i><strong>{count}</strong></div>'
        )
    return "".join(parts)


def _render_modules(modules: list[dict[str, Any]]) -> str:
    if not modules:
        return '<p class="muted">没有可显示模块。</p>'
    cards = []
    for module in modules[:12]:
        entrypoints = " · ".join(str(item) for item in module.get("entrypoints", [])) or "暂无明显入口"
        languages = " / ".join(str(item) for item in module.get("languages", {}).keys()) or "未知"
        cards.append(
            '<article class="module-card">'
            f'<span>{html.escape(_text(module.get("path"), "."))}</span>'
            f'<h3>{html.escape(_text(module.get("name"), "未命名模块"))}</h3>'
            f'<p>{_as_int(module.get("file_count"))} 文件 · {_as_int(module.get("symbol_count"))} 符号 · {html.escape(languages)}</p>'
            f'<small>{html.escape(entrypoints)}</small>'
            '</article>'
        )
    return "".join(cards)


def _render_reference_position(project_directory: str, features: list[dict[str, Any]]) -> str:
    normalized = project_directory.lower()
    curated = {item["project"] for item in _REFERENCE_CONTRIBUTIONS}
    if normalized in curated:
        cards = []
        for item in _REFERENCE_CONTRIBUTIONS:
            current = item["project"] == normalized
            cards.append(
                f'<article class="reference-card{" current" if current else ""}">'
                f'<span>{"当前仓库" if current else "参考仓库"} · {html.escape(item["project"])}</span>'
                f'<h3>{html.escape(item["mechanism"])}</h3>'
                f'<p><strong>映射：</strong>{html.escape(item["mapping"])}</p>'
                f'<code>{html.escape(item["paths"])}</code>'
                f'<p><strong>差异 / 未采用：</strong>{html.escape(item["boundary"])}</p>'
                "</article>"
            )
        return (
            '<section class="reference-position"><div class="section-head">'
            '<span class="kicker">六仓机制对照</span>'
            '<h2>分别借鉴什么，以及明确没有照搬什么。</h2></div>'
            '<p class="semantic-warning">这是机制与源码证据对照，不是按 Star、热度或项目名称做技术排名。</p>'
            f'<div class="reference-grid">{"".join(cards)}</div></section>'
        )
    if normalized in {"waku", "waku-agent"}:
        items = []
        for feature in features:
            tags = feature.get("technology_tags", [])
            if not isinstance(tags, list) or "compatibility-corpus:waku-not-curated" not in tags:
                continue
            mechanism = next(
                (
                    str(tag).split(":", 1)[1]
                    for tag in tags
                    if isinstance(tag, str)
                    and tag.startswith("compatibility-mechanism:")
                ),
                "unknown",
            )
            steps = [step for step in feature.get("steps", []) if isinstance(step, dict)]
            resolved = len(
                {
                    step.get("relationship_id")
                    for step in steps
                    if step.get("relationship_id")
                }
            )
            unknown = sum(
                1
                for claim in feature.get("technology_claims", [])
                if isinstance(claim, dict) and claim.get("value") == "unknown"
            )
            locations = ", ".join(
                dict.fromkeys(
                    str(step.get("path"))
                    for step in steps
                    if step.get("path")
                )
            ) or "未定位源码切片"
            items.append(
                '<li><strong>'
                f'Waku 兼容性语料：{html.escape(mechanism)}</strong> · '
                f'{resolved} 条已解析静态关系 · {unknown} 个未知技术维度 · '
                f'<code>{html.escape(locations)}</code></li>'
            )
        return (
            '<section class="reference-position"><div class="section-head">'
            '<span class="kicker">兼容性语料</span><h2>Waku：单独验证，不进入六仓 curated 技术排名。</h2></div>'
            '<p class="semantic-warning">页面中的功能只按当前固定版本索引证据展示；'
            '已解析静态关系与未知项必须分开，不能从名称推断运行能力。</p>'
            f'<ul class="compatibility-list">{"".join(items) if items else "<li>当前没有可验证的功能记录。</li>"}</ul></section>'
        )
    return ""


_WAKU_FUNCTION_ORDER = (
    "loop",
    "memory",
    "graph",
    "gateway",
    "voice",
    "tools",
    "providers",
    "dashboard",
    "eval",
)

_WAKU_HUMAN_GUIDE: dict[str, tuple[str, str]] = {
    "loop": (
        "Agent Loop：推理、工具调用与终止条件——一个有上限的 Python for 循环",
        "每轮让模型选择直接回答或调用工具；工具结果写回 messages 后再进入下一轮，直到自然结束或达到最大迭代数。",
    ),
    "memory": (
        "Memory：长期记忆与周期整理",
        "按对话批次提炼长期事实与情景记录，并显式判断本轮是否需要执行 consolidation。",
    ),
    "graph": (
        "Graph Workflow：节点、并行波次与显式路由——内存依赖图与 Router 分支选择",
        "节点按依赖组成 wave；Router 不执行任务，只在状态提交后把 label 映射到下一条预注册分支。",
    ),
    "gateway": (
        "Multi-channel Gateway：通道生命周期协调",
        "统一管理后台通道的启动、停止、配置变化和健康状态，作为 CLI、Web 与消息通道的协调层。",
    ),
    "voice": (
        "Voice：本地录音、语音识别与朗读输出——录音 → ASR → Agent → TTS 的轮次链",
        "一段录音结束后才开始转写，文本再交给 Agent，最终回复再合成播放；播放结束后才恢复监听。",
    ),
    "tools": (
        "Tools / MCP：工具注册、调用与错误隔离",
        "用统一 schema 注册工具，把模型的工具调用分派给 Python 函数，并把异常转成模型可观察的结果。",
    ),
    "providers": (
        "Model Providers：多模型统一适配",
        "把不同供应商收敛到统一消息形态，并对 Anthropic 与 OpenAI 兼容接口做薄适配。",
    ),
    "dashboard": (
        "Dashboard / Observability：本地交互与运行观测",
        "在本地 Web 界面汇集聊天、会话、工具、图、记忆、数据和运行事件。",
    ),
    "eval": (
        "Eval / Release Gate：评测与发布门",
        "组合确定性评测与模型裁判结果，失败时关闭发布门并保存评测记录。",
    ),
}

_WAKU_DECISION_GUIDE: dict[str, dict[str, str]] = {
    "loop": {
        "mechanism": "同步 reason → tool call → observation 循环；无工具调用或达到迭代上限时停止。",
        "technology": "Python · Anthropic Messages API · ToolRegistry · observer/stream 回调",
        "reuse": "局部借鉴循环骨架、工具结果回填和双终止条件。",
        "caution": "供应商类型直接进入函数签名；重试、取消和并发任务隔离需重新设计。",
    },
    "memory": {
        "mechanism": "按未整理聊天数量触发批量总结，把事实与 episode 分写到两个 SQLite store。",
        "technology": "Python · SQLite · JSON 结构化提取 · 小模型批量 consolidation",
        "reuse": "局部借鉴“达到阈值再整理”和失败不丢原始聊天的边界。",
        "caution": "事实冲突、删除、隐私和长期记忆质量没有在该切片中闭合。",
    },
    "graph": {
        "mechanism": "共享 dict 状态按 wave 执行就绪节点；代码 router 选边，并用写冲突与步数门限保护。",
        "technology": "Python · ThreadPoolExecutor · 显式 Node/Edge/Router · observer 事件",
        "reuse": "优先借鉴确定性 wave、并行写冲突检测和 max_visits/max_steps。",
        "caution": "进程内线程模型不等于持久化工作流；恢复、分布式调度和耐久状态需重写。",
    },
    "gateway": {
        "mechanism": "Supervisor 对通道配置做指纹比较，统一协调启动、停止、重建与健康状态。",
        "technology": "Python · supervisor/reconcile loop · 多通道 runner · 配置指纹",
        "reuse": "借鉴单一生命周期协调面和通道适配器边界。",
        "caution": "具体消息通道、认证、断线恢复与多设备行为必须实机验证。",
    },
    "voice": {
        "mechanism": "麦克风录音经过本地 Whisper 转写，进入 Agent，再由 TTS 朗读；支持唤醒或按键说话。",
        "technology": "本地录音 · Whisper ASR · Agent pipeline · TTS",
        "reuse": "可作为串联式 VAD/ASR/LLM/TTS 的轻量参考入口。",
        "caution": "不是原生全双工语音模型；打断、回声消除、端到端延迟和设备兼容性待测。",
    },
    "tools": {
        "mechanism": "ToolRegistry 保存名称、描述、JSON schema 与 Python callable，并把异常转成模型可见文本。",
        "technology": "Python registry · JSON Schema · callable dispatch · observer progress",
        "reuse": "可复用最小工具契约、schema 输出和错误隔离思路。",
        "caution": "权限、沙箱、幂等、超时与远程 MCP 生命周期不在该注册表内。",
    },
    "providers": {
        "mechanism": "把不同模型供应商收敛到统一消息形态，在客户端选择层做薄适配。",
        "technology": "Provider adapter · Anthropic/OpenAI-compatible clients · message normalization",
        "reuse": "借鉴供应商适配放在循环外的边界。",
        "caution": "流式事件、工具调用、推理块和错误语义需要逐供应商兼容测试。",
    },
    "dashboard": {
        "mechanism": "本地 Web 入口汇总会话、工具、图、记忆、数据和运行事件视图。",
        "technology": "Python local web service · static dashboard · event/trace views",
        "reuse": "参考把运行观测与 Agent 核心解耦、通过 observer 取数的方式。",
        "caution": "页面存在不代表所有指标、权限和多用户隔离已经生产验证。",
    },
    "eval": {
        "mechanism": "组合确定性检查与模型裁判结果形成 release gate，失败时阻止发布并保留记录。",
        "technology": "Python CLI · deterministic checks · model judge · persisted evaluation record",
        "reuse": "借鉴“评测结果直接控制发布门”的产品边界。",
        "caution": "阈值、测试集代表性、裁判稳定性与 CI 接入需要自己的评测协议。",
    },
}


def _waku_mechanism(feature: dict[str, Any]) -> str:
    tags = feature.get("technology_tags", [])
    if not isinstance(tags, list) or "compatibility-corpus:waku-not-curated" not in tags:
        return ""
    return next(
        (
            _text(tag).split(":", 1)[1]
            for tag in tags
            if _text(tag).startswith("compatibility-mechanism:")
        ),
        "",
    )


def _waku_compatibility_features(features: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    order = {name: position for position, name in enumerate(_WAKU_FUNCTION_ORDER)}
    selected = [
        (position, feature)
        for position, feature in enumerate(features, start=1)
        if _waku_mechanism(feature)
    ]
    return sorted(selected, key=lambda item: (order.get(_waku_mechanism(item[1]), 999), item[0]))


def _human_copy(feature: dict[str, Any]) -> tuple[str, str]:
    mechanism = _waku_mechanism(feature)
    if mechanism:
        return _WAKU_HUMAN_GUIDE.get(
            mechanism,
            (_text(feature.get("title"), "未命名功能"), _text(feature.get("summary"), "当前没有功能说明。")),
        )
    return (
        _text(feature.get("title"), "未命名功能"),
        _text(feature.get("summary"), "当前没有功能说明。"),
    )


def _chapter_conclusion(value: object, title: str, fallback: str) -> str:
    """Return a standalone human conclusion without repeating UI scaffolding."""
    conclusion = _text(value, fallback).strip()
    for prefix in ("简单来说，这个功能就是：", "简单来说，这个功能就是:", "简单来说，这个功能就是"):
        if conclusion.startswith(prefix):
            conclusion = conclusion[len(prefix):].lstrip()
            break
    if title and conclusion.startswith(title):
        remainder = conclusion[len(title):].lstrip(" ：:—-·，,")
        if remainder:
            conclusion = remainder
    return conclusion or fallback


def _known_technology(feature: dict[str, Any]) -> list[str]:
    claims = feature.get("technology_claims", [])
    known = [
        f"{_text(claim.get('dimension'))}:{_text(claim.get('value'))}"
        for claim in claims
        if isinstance(claim, dict)
        and _text(claim.get("dimension"))
        and _text(claim.get("value"), "unknown") != "unknown"
    ] if isinstance(claims, list) else []
    if known:
        return list(dict.fromkeys(known))
    tags = feature.get("technology_tags", [])
    return list(dict.fromkeys(
        _text(tag)
        for tag in tags
        if isinstance(tags, list)
        and ":" in _text(tag)
        and not _text(tag).endswith(":unknown")
        and not _text(tag).startswith(("compatibility-", "calls:"))
    ))


def _reuse_boundary(tutorial: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    if tutorial is None:
        return [], []
    contract = tutorial.get("teaching_contract", {})
    contract = contract if isinstance(contract, dict) else {}
    boundary = contract.get("reuse_boundary", {})
    boundary = boundary if isinstance(boundary, dict) else {}
    reusable = boundary.get("reusable", [])
    reverify = boundary.get("must_reverify", [])
    return (
        [_text(item) for item in reusable if _text(item)] if isinstance(reusable, list) else [],
        [_text(item) for item in reverify if _text(item)] if isinstance(reverify, list) else [],
    )


def _render_human_decision_guide(
    features: list[dict[str, Any]],
    tutorials: list[dict[str, Any]],
    project_directory: str,
    project_root: str,
    project_overview: dict[str, Any] | None = None,
) -> str:
    is_waku = project_directory.lower() in {"waku", "waku-agent"}
    selected = (
        _waku_compatibility_features(features)
        if is_waku
        else [
            (position, feature)
            for position, feature in enumerate(features, start=1)
            if _text(feature.get("kind")) == "capability-cluster"
        ]
    )
    if not selected:
        return (
            '<section id="semantic-gap" class="semantic-gap">'
            '<div class="section-head"><span class="kicker">先说清楚当前报告能回答什么</span>'
            '<h2>尚未形成可用于技术选型的功能语义层。</h2></div>'
            '<p>入口、类和函数只能作为证据，不能自动等同于产品功能。当前页面会把它们保留在后面的'
            '“静态边界与源码证据”中；需要先建立 Capability → Mechanism → Component → Evidence 绑定，'
            '才会在这里给出功能与复用结论。</p></section>'
        )

    tutorial_by_feature = {
        _text(item.get("feature_id")): item
        for item in tutorials
        if isinstance(item, dict) and _text(item.get("feature_id"))
    }
    axes = (
        [item for item in project_overview.get("core_product_axes", []) if isinstance(item, dict)]
        if isinstance(project_overview, dict)
        else []
    )
    supporting_order = list(dict.fromkeys(
        _text(item)
        for item in (
            project_overview.get("supporting_capability_ids", [])
            if isinstance(project_overview, dict)
            and isinstance(project_overview.get("supporting_capability_ids"), list)
            else []
        )
        if _text(item)
    ))
    supporting_ids = set(supporting_order)
    axis_by_capability = {
        _text(capability_id): axis
        for axis in axes
        for capability_id in (
            axis.get("capability_ids", [])
            if isinstance(axis.get("capability_ids"), list)
            else []
        )
        if _text(capability_id)
    }
    records: list[dict[str, str]] = []
    for display_position, (feature_position, feature) in enumerate(selected, start=1):
        mechanism = _waku_mechanism(feature)
        human_title, human_summary = _human_copy(feature)
        steps = feature.get("steps", []) if isinstance(feature.get("steps", []), list) else []
        first_step = next((step for step in steps if isinstance(step, dict) and step.get("path")), {})
        source_path = _text(first_step.get("path"), "未定位源码")
        start = _as_int(first_step.get("line_start"))
        end = _as_int(first_step.get("line_end"), start)
        roles = list(dict.fromkeys(
            _text(step.get("source_role"), _text(step.get("title")))
            for step in steps
            if isinstance(step, dict) and _text(step.get("source_role"), _text(step.get("title")))
        ))
        tutorial = tutorial_by_feature.get(_text(feature.get("id")))
        reusable, reverify = _reuse_boundary(tutorial)
        waku_decision = _WAKU_DECISION_GUIDE.get(mechanism, {})
        claim_scopes = [
            _text(claim.get("claim_scope"))
            for claim in feature.get("technology_claims", [])
            if isinstance(claim, dict)
            and _text(claim.get("value"), "unknown") != "unknown"
            and _text(claim.get("claim_scope"))
        ] if isinstance(feature.get("technology_claims", []), list) else []
        default_implementation = " → ".join(roles[:4]) or "当前只确认实现中心，完整数据流仍需继续核对。"
        if claim_scopes:
            default_implementation += "；" + "；".join(dict.fromkeys(claim_scopes))
        human_chapter = tutorial.get("human_chapter", {}) if isinstance(tutorial, dict) else {}
        chapter_id = _text(human_chapter.get("id"), _text(feature.get("id")))
        hierarchy_label = (
            "扩展业务功能"
            if chapter_id in supporting_ids
            else "核心子功能" if chapter_id in axis_by_capability else "功能"
        )
        mechanism_model = human_chapter.get("mechanism_model", {}) if isinstance(human_chapter, dict) else {}
        human_mechanism = "；".join(
            value for value in (
                _text(mechanism_model.get("storage")) if isinstance(mechanism_model, dict) else "",
                _text(mechanism_model.get("control_loop")) if isinstance(mechanism_model, dict) else "",
            ) if value
        )
        implementation = human_mechanism or _text(
            waku_decision.get("mechanism"), default_implementation
        )
        technology = _text(
            waku_decision.get("technology"),
            " · ".join(_known_technology(feature)) or "未知：没有独立、可审计的技术声明。",
        )
        reuse = _text(
            waku_decision.get("reuse"),
            reusable[0] if reusable else "局部借鉴源码职责；直接复用前先核对依赖、测试与许可证。",
        )
        caution = _text(
            waku_decision.get("caution"),
            reverify[0] if reverify else "运行路径、异常、并发、性能和生产边界仍需验证。",
        )
        source = _source_anchor(project_root, source_path, start, end)
        grade = "C · 固定源码候选" if mechanism else "B · 源码静态确认"
        card = (
            f'<a class="human-capability" href="#feature-{feature_position:03d}">'
            f'<span>{html.escape(hierarchy_label)} {display_position:02d} · {html.escape(grade)}</span>'
            f'<h3>{html.escape(human_title)}</h3>'
            f'<p>{html.escape(human_summary)}</p>'
            '<dl><dt>底层机制</dt>'
            f'<dd>{html.escape(implementation)}</dd><dt>关键技术</dt>'
            f'<dd>{html.escape(technology)}</dd><dt>源码</dt><dd><code>{html.escape(source_path)}</code></dd></dl>'
            '<strong>查看它如何实现与证据边界 →</strong></a>'
        )
        row = (
            '<tr>'
            f'<th>{html.escape(human_title)}</th>'
            f'<td data-label="底层机制">{html.escape(implementation)}</td>'
            f'<td data-label="关键技术">{html.escape(technology)}</td>'
            f'<td data-label="复用建议"><b>{html.escape(reuse)}</b><br><span>{html.escape(caution)}</span></td>'
            f'<td data-label="源码证据">{source}<small>{html.escape(grade)}</small></td>'
            '</tr>'
        )
        records.append({"chapter_id": chapter_id, "card": card, "row": row})

    records_by_chapter = {item["chapter_id"]: item for item in records}
    hierarchy_sections: list[str] = []
    core_rows: list[str] = []
    rendered_ids: set[str] = set()
    for position, axis in enumerate(axes, start=1):
        member_ids = [
            _text(item)
            for item in axis.get("capability_ids", [])
            if _text(item) and _text(item) in records_by_chapter
        ] if isinstance(axis.get("capability_ids"), list) else []
        if not member_ids:
            continue
        rendered_ids.update(member_ids)
        axis_cards = "".join(records_by_chapter[item]["card"] for item in member_ids)
        core_rows.extend(records_by_chapter[item]["row"] for item in member_ids)
        hierarchy_sections.append(
            '<section class="product-capability-group"><header><span>产品主轴 '
            + f'{position:02d}</span><h3>{html.escape(_text(axis.get("title")))}</h3><p>'
            + html.escape(_text(axis.get("one_liner")))
            + '</p><strong>用户得到：' + html.escape(_text(axis.get("user_outcome")))
            + '</strong></header><div class="human-capability-grid">' + axis_cards
            + '</div></section>'
        )

    supporting_records = [
        records_by_chapter[item]
        for item in supporting_order
        if item in records_by_chapter
    ]
    rendered_ids.update(item["chapter_id"] for item in supporting_records)
    unclassified_records = [
        item for item in records if item["chapter_id"] not in rendered_ids
    ]
    if axes:
        supporting_records.extend(unclassified_records)
        supporting_html = (
            '<section class="secondary-capabilities"><header><span>扩展业务功能</span><b>'
            + str(len(supporting_records))
            + ' 项独立用户能力</b><small>阅读优先级较低，但全部直接展示</small>'
            + '</header><div class="human-capability-grid">'
            + "".join(item["card"] for item in supporting_records)
            + '</div></section>'
            if supporting_records
            else ""
        )
        capability_html = "".join(hierarchy_sections) + supporting_html
        rows_html = "".join(item["row"] for item in records)
        intro = (
            f'先看 <b>{len(hierarchy_sections)} 条产品主轴</b>建立分类，再逐项看 '
            f'<b>{len(records)} 个独立业务功能</b>；主轴不是功能数量，所有功能都直接展示。'
        )
    else:
        capability_html = '<div class="human-capability-grid">' + "".join(
            item["card"] for item in records
        ) + '</div>'
        rows_html = "".join(item["row"] for item in records)
        intro = (
            f'从当前固定版本源码可以先读出 <b>{len(selected)} '
            f'{"组功能候选" if is_waku else "个源码审计功能"}</b>；'
            '下面先讲功能与作用，再把入口、符号和静态关系放到后面作为证据。'
        )
    return (
        '<section id="project-functions" class="human-overview">'
        '<div class="section-head"><span class="kicker">先回答人最关心的问题</span>'
        '<h2>这个项目有哪些功能？</h2></div>'
        f'<p class="human-intro">{intro}</p>'
        + capability_html
        + '<p class="semantic-warning">功能说明与静态证据分层展示；B/C 级结论都不等于运行、性能或生产可用性已经验证。</p>'
        '<div class="section-head selection-head"><span class="kicker">用于技术选型</span>'
        '<h2>技术选型怎么用？</h2></div>'
        '<p class="human-intro">先比较机制与复用边界，再打开源码。不要用入口数量、符号数量或 Star 代替技术判断。</p>'
        '<div class="decision-table-wrap"><table class="decision-table"><thead><tr>'
        '<th>功能</th><th>底层机制</th><th>关键技术</th><th>复用建议 / 不要照搬</th><th>源码证据</th>'
        '</tr></thead><tbody>' + rows_html + '</tbody></table></div>'
        '</section>'
    )


def _render_project_overview(
    overview: dict[str, Any] | None,
    project_root: str,
) -> str:
    if not isinstance(overview, dict):
        return ""

    def refs(value: object) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def first_source(item: dict[str, Any]) -> str:
        source_refs = refs(item.get("source_refs"))
        if not source_refs:
            return '<span class="muted">暂无源码锚点</span>'
        source_ref = source_refs[0]
        return _source_anchor(
            project_root,
            _text(source_ref.get("path")),
            _as_int(source_ref.get("line_start")),
            _as_int(source_ref.get("line_end")),
        )

    journey = refs(overview.get("core_journey"))
    journey_html = "".join(
        '<li><b>' + f"{position:02d}" + '</b><div><span>'
        + html.escape(_text(step.get("stage"), "阶段"))
        + '</span><h4>' + html.escape(_text(step.get("actor"), "系统")) + ' · '
        + html.escape(_text(step.get("action"), "执行")) + '</h4><p><strong>状态变化：</strong>'
        + html.escape(_text(step.get("state_change"), "未说明")) + '</p><small>下一步：'
        + html.escape(_text(step.get("next"), "未说明")) + '</small></div></li>'
        for position, step in enumerate(journey, start=1)
    )
    components = refs(overview.get("runtime_components"))
    component_html = "".join(
        '<article><header><span>运行组件</span><h4>'
        + html.escape(_text(component.get("name"), "未命名组件"))
        + '</h4></header><p>' + html.escape(_text(component.get("responsibility")))
        + '</p><dl><dt>如何通信</dt><dd>' + html.escape(_text(component.get("communication")))
        + '</dd><dt>持有什么状态</dt><dd>' + html.escape(_text(component.get("state")))
        + '</dd></dl>' + first_source(component) + '</article>'
        for component in components
    )
    directories = refs(overview.get("code_organization"))
    directory_html = "".join(
        '<tr><th><code>' + html.escape(_text(directory.get("path"), "unknown"))
        + '</code><small>' + html.escape(_text(directory.get("layer"), "未分类"))
        + '</small></th><td>' + html.escape(_text(directory.get("responsibility")))
        + '</td><td>' + html.escape(_text(directory.get("boundary")))
        + '</td><td>' + first_source(directory) + '</td></tr>'
        for directory in directories
    )
    not_this = "".join(
        f'<li>{html.escape(_text(item))}</li>'
        for item in overview.get("not_this", [])
        if isinstance(item, str) and item.strip()
    )
    overview_sources = "".join(
        '<li>'
        + _source_anchor(
            project_root,
            _text(source_ref.get("path")),
            _as_int(source_ref.get("line_start")),
            _as_int(source_ref.get("line_end")),
        )
        + '<span>' + html.escape(_text(source_ref.get("claim"))) + '</span></li>'
        for source_ref in refs(overview.get("source_refs"))
    )
    engineering = (
        overview.get("engineering_structure")
        if isinstance(overview.get("engineering_structure"), dict)
        else {}
    )
    engineering_source = first_source(engineering) if engineering else ""
    product_axes = refs(overview.get("core_product_axes"))

    def flow_diagram(steps: object, *, class_name: str, label: str) -> str:
        values = [
            _text(item)
            for item in steps
            if isinstance(item, str) and _text(item)
        ] if isinstance(steps, list) else []
        if not values:
            return '<p class="muted compact">当前证据不足以画出交互过程。</p>'
        nodes = "".join(
            '<li><span>' + f"{position:02d}" + '</span><p>'
            + html.escape(value) + '</p></li>'
            for position, value in enumerate(values, start=1)
        )
        return (
            f'<div class="{html.escape(class_name)}" role="group" '
            f'aria-label="{html.escape(label)}"><b>{html.escape(label)}</b>'
            f'<ol>{nodes}</ol></div>'
        )

    axes_html = "".join(
        '<article><header><span>产品主轴 ' + f"{position:02d}" + '</span><b>'
        + html.escape(_text(axis.get("title"), "未命名主轴"))
        + '</b></header><h3>' + html.escape(_text(axis.get("one_liner")))
        + '</h3>'
        + flow_diagram(
            axis.get("end_to_end_flow"),
            class_name="axis-interaction",
            label="交互图 · 数据、控制权与状态怎样移动",
        )
        + '<p class="axis-outcome"><strong>用户最终得到：</strong>'
        + html.escape(_text(axis.get("user_outcome"))) + '</p><footer><span>'
        + f'{len(axis.get("capability_ids", [])) if isinstance(axis.get("capability_ids"), list) else 0} 个子能力'
        + '</span>' + first_source(axis) + '</footer></article>'
        for position, axis in enumerate(product_axes, start=1)
    )

    engineering_rows = (
        ("前端代码", engineering.get("frontend_organization"), overview.get("frontend_backend_boundary")),
        ("后端代码", engineering.get("backend_organization"), engineering.get("dependency_rule")),
        ("Worker / 异步执行", engineering.get("worker_and_async_organization"), overview.get("execution_model")),
        ("共享协议 / 类型", engineering.get("shared_contracts"), engineering.get("dependency_rule")),
        ("语音 / 视频代码组织", engineering.get("media_organization"), overview.get("data_and_state")),
    )
    engineering_rows_html = "".join(
        '<tr><th>' + html.escape(label) + '</th><td>'
        + html.escape(_text(organization, "未发现独立实现。")) + '</td><td>'
        + html.escape(_text(boundary, "当前证据没有证明额外交接边界。")) + '</td></tr>'
        for label, organization, boundary in engineering_rows
    )
    supporting_count = len(
        overview.get("supporting_capability_ids", [])
        if isinstance(overview.get("supporting_capability_ids"), list)
        else []
    )
    return (
        '<section id="project-overview" class="project-overview">'
        '<div class="section-head"><span class="kicker">00 · 先讲这是什么项目</span>'
        '<h2>' + html.escape(_text(overview.get("one_liner"), "项目定位尚未生成")) + '</h2></div>'
        '<div class="project-definition"><article><span>项目类型</span><strong>'
        + html.escape(_text(overview.get("product_type")))
        + '</strong></article><article><span>主要用户</span><strong>'
        + html.escape(_text(overview.get("primary_user")))
        + '</strong></article><article><span>解决的问题</span><strong>'
        + html.escape(_text(overview.get("problem")))
        + '</strong></article><article><span>最不同的地方</span><strong>'
        + html.escape(_text(overview.get("differentiator")))
        + '</strong></article></div>'
        '<div class="section-head architecture-head"><span class="kicker">01 · 项目工程结构</span>'
        '<h2>先看前端、后端、Worker、媒体与共享协议怎样组织。</h2></div>'
        '<div class="engineering-structure"><div class="engineering-verdict"><span>仓库形态</span><strong>'
        + html.escape(_text(engineering.get("repository_shape"), "未确认"))
        + '</strong><span>架构模式</span><strong>'
        + html.escape(_text(engineering.get("architecture_pattern"), "未确认"))
        + '</strong><p>' + html.escape(_text(engineering.get("pattern_reasoning")))
        + '</p>' + engineering_source + '</div><div class="engineering-table-wrap">'
        '<table class="engineering-layer-table"><thead><tr><th>工程层</th><th>代码怎样组织 / 负责什么</th>'
        '<th>和谁交接 / 依赖边界</th></tr></thead><tbody>' + engineering_rows_html
        + '</tbody></table></div></div>'
        '<div class="section-head architecture-head product-axis-head"><span class="kicker">02 · 产品主轴与交互</span></div>'
        '<div class="product-axis-grid">' + axes_html + '</div>'
        '<p class="supporting-count">另有 <b>' + str(supporting_count)
        + '</b> 个运维、治理或通用支撑能力，放到核心主轴之后阅读。</p>'
        '<div class="section-head architecture-head"><span class="kicker">03 · 核心任务怎样跑完</span>'
        '<h2>先沿一条真实用户旅程看清控制权和状态怎样移动。</h2></div>'
        '<ol class="project-journey">' + journey_html + '</ol>'
        '<div class="architecture-summary"><article><span>整体架构</span><h3>'
        + html.escape(_text(overview.get("architecture_style")))
        + '</h3><p>' + html.escape(_text(overview.get("architecture_summary")))
        + '</p></article><article><span>执行模型</span><h3>任务由谁接管、怎样结束</h3><p>'
        + html.escape(_text(overview.get("execution_model")))
        + '</p></article><article><span>前后端边界</span><p>'
        + html.escape(_text(overview.get("frontend_backend_boundary")))
        + '</p></article><article><span>数据与状态</span><p>'
        + html.escape(_text(overview.get("data_and_state")))
        + '</p></article><article><span>部署形态</span><p>'
        + html.escape(_text(overview.get("deployment_shape")))
        + '</p></article></div>'
        '<div class="section-head architecture-head"><span class="kicker">04 · 运行时组件</span>'
        '<h2>谁负责什么、怎样通信、状态放在哪里。</h2></div>'
        '<div class="runtime-component-grid">' + component_html + '</div>'
        '<div class="section-head architecture-head"><span class="kicker">05 · 代码目录怎么组织</span>'
        '<h2>目录是职责边界，不是文件树清单。</h2></div>'
        '<div class="code-organization-wrap"><table class="code-organization"><thead><tr>'
        '<th>目录 / 层</th><th>封装的职责</th><th>边界</th><th>源码</th></tr></thead><tbody>'
        + directory_html + '</tbody></table></div>'
        '<div class="overview-boundary"><div><strong>不要把它误解成</strong><ul>'
        + not_this + '</ul></div><details><summary>项目定位与架构证据</summary><ol>'
        + overview_sources + '</ol></details></div></section>'
    )


def _render_quick_grid(
    *,
    capabilities: int,
    boundaries: int,
    candidates: int,
    evidence: int,
    waku_features: list[tuple[int, dict[str, Any]]],
) -> str:
    if waku_features:
        relationship_count = len(
            {
                step.get("relationship_id")
                for _position, feature in waku_features
                for step in feature.get("steps", [])
                if isinstance(step, dict) and step.get("relationship_id")
            }
        )
        cards = (
            (len(waku_features), "组功能候选（先读它们做什么）"),
            (boundaries, "个启动入口（放在功能之后核对）"),
            (relationship_count, "条已解析静态关系（不冒充运行时流）"),
            (evidence, "条源码证据（可点击回看）"),
        )
    else:
        cards = (
            (capabilities, "固定版本源码审计能力（核心功能）"),
            (boundaries, "静态确认入口声明（可运行性与实际可达性未知）"),
            (candidates, "未确认入口候选（不可执行）"),
            (evidence, "源码证据（可回看）"),
        )
    return '<div class="quick-grid">' + "".join(
        f'<article class="quick-card"><b>{count:,}</b><span>{html.escape(label)}</span></article>'
        for count, label in cards
    ) + "</div>"


def _render_reading_path(steps: list[dict[str, Any]]) -> str:
    if not steps:
        return '<p class="muted">当前没有足够证据生成阅读路线。</p>'
    items = []
    for step in steps:
        items.append(
            '<article class="reading-step">'
            f'<b>{_as_int(step.get("order"), len(items) + 1):02d}</b><div><span>{html.escape(_text(step.get("title"), "阅读步骤"))}</span>'
            f'<h3>{html.escape(_text(step.get("path"), "未标注路径"))}</h3><p>{html.escape(_text(step.get("reason"), "请结合源码核对。"))}</p></div>'
            f'<em>{html.escape(_text(step.get("confidence"), "heuristic"))}</em>'
            '</article>'
        )
    return "".join(items)


def _confidence_label(value: Any) -> tuple[str, str]:
    confidence = _text(value, "unknown").lower()
    if confidence == "exact":
        return "exact", "确定性事实"
    if confidence == "exact-entry":
        return "exact", "静态入口声明已确认·可达性未知"
    if confidence == "source-audited":
        return "exact", "固定版本源码已审计"
    if confidence == "static-entry":
        return "heuristic", "静态入口模式·语义待核对"
    if confidence == "heuristic":
        return "heuristic", "启发式识别"
    if confidence == "candidate":
        return "unknown", "符号已解析·入口未确认"
    return "unknown", confidence


def _evidence_location(evidence: dict[str, Any]) -> str:
    path = _text(evidence.get("path"), "未标注路径")
    start = _as_int(evidence.get("line_start"))
    end = _as_int(evidence.get("line_end"), start)
    if start <= 0:
        return path
    return f"{path}:{start}" if end <= start else f"{path}:{start}-{end}"


def _source_anchor(project_root: str, path: str, start: int = 0, end: int = 0) -> str:
    location = path if start <= 0 else (f"{path}:{start}" if end <= start else f"{path}:{start}-{end}")
    if not project_root:
        return f'<code>{html.escape(location)}</code>'
    try:
        root = Path(project_root).expanduser().resolve()
        candidate = (root / path).resolve()
        candidate.relative_to(root)
        href = candidate.as_uri()
        if start > 0:
            href += f"#L{start}" if end <= start else f"#L{start}-L{end}"
    except (OSError, ValueError):
        return f'<code>{html.escape(location)}</code>'
    return (
        f'<a class="source-link" href="{html.escape(href, quote=True)}" '
        f'target="_blank" rel="noopener"><code>{html.escape(location)}</code></a>'
    )


def _render_evidence_refs(
    evidence_ids: list[Any], evidence_by_id: dict[str, dict[str, Any]], *, empty_message: str,
    project_root: str = "",
) -> str:
    seen: set[str] = set()
    items: list[str] = []
    for raw_id in evidence_ids:
        evidence_id = _text(raw_id)
        if not evidence_id or evidence_id in seen:
            continue
        seen.add(evidence_id)
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            items.append(
                '<li class="evidence-missing">'
                f'<code>{html.escape(evidence_id)}</code><span>索引中未找到该证据</span></li>'
            )
            continue
        kind = _text(evidence.get("kind"), "source")
        snippet = _text(evidence.get("snippet"))
        confidence_class, confidence_text = _confidence_label(evidence.get("confidence"))
        snippet_html = f'<pre>{html.escape(snippet)}</pre>' if snippet else ""
        items.append(
            '<li class="evidence-item">'
            f'<div>{_source_anchor(project_root, _text(evidence.get("path"), "unknown"), _as_int(evidence.get("line_start")), _as_int(evidence.get("line_end")))}'
            f'<span class="pill {confidence_class}">{html.escape(confidence_text)}</span>'
            f'<span class="evidence-kind">{html.escape(kind)}</span></div>{snippet_html}</li>'
        )
    if not items:
        return f'<p class="muted compact">{html.escape(empty_message)}</p>'
    return f'<ul class="evidence-list">{"".join(items)}</ul>'


def _render_feature_steps(
    steps: list[dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    project_root: str,
) -> str:
    if not steps:
        return '<p class="muted compact">当前只能确定功能入口，还没有解析出稳定的下游调用链。</p>'
    rendered: list[str] = []
    for position, step in enumerate(steps, start=1):
        order = _as_int(step.get("order"), position)
        path = _text(step.get("path"), "未标注路径")
        start = _as_int(step.get("line_start"))
        end = _as_int(step.get("line_end"), start)
        evidence_ids = step.get("evidence_ids", []) if isinstance(step.get("evidence_ids", []), list) else []
        resolved = sum(1 for item in evidence_ids if _text(item) in evidence_by_id)
        role = _text(step.get("source_role"), "静态阅读定位")
        symbol = _text(step.get("source_symbol"), _text(step.get("title"), "未标注符号"))
        claim_scope = _text(
            step.get("claim_scope"),
            "仅证明该位置的局部职责，不证明运行时路径。",
        )
        relationship = (
            f"resolved-static:{_text(step.get('relationship_kind'), 'unknown')}"
            if step.get("relationship_id")
            else "location-only（未证明实现流）"
        )
        digest = _text(step.get("snippet_sha256"))
        rendered.append(
            '<li class="feature-step">'
            f'<span class="step-number">{order:02d}</span><div><h4>{html.escape(_text(step.get("title"), "实现步骤"))}</h4>'
            f'<p>{html.escape(_text(step.get("explanation"), "请结合该处源码理解。"))}</p>'
            f'<dl class="source-contract"><dt>职责</dt><dd>{html.escape(role)}</dd>'
            f'<dt>符号</dt><dd><code>{html.escape(symbol)}</code></dd>'
            f'<dt>关系</dt><dd>{html.escape(relationship)}</dd>'
            f'<dt>声明边界</dt><dd>{html.escape(claim_scope)}</dd></dl>'
            f'{_source_anchor(project_root, path, start, end)}'
            f'<small>{resolved} 条已解析证据'
            f'{" · 切片 SHA-256 " + html.escape(digest) if digest else ""}</small></div></li>'
        )
    return f'<ol class="feature-steps">{"".join(rendered)}</ol>'


def _feature_rank(feature: dict[str, Any]) -> tuple[int, int, int, str]:
    exact = 2 if _text(feature.get("confidence")).lower() == "source-audited" else (
        1 if _text(feature.get("confidence")).lower() in {"exact", "exact-entry"} else 0
    )
    tests = len(feature.get("test_evidence_ids", [])) if isinstance(feature.get("test_evidence_ids"), list) else 0
    steps = len(feature.get("steps", [])) if isinstance(feature.get("steps"), list) else 0
    return exact, tests, steps, _text(feature.get("title"))


def _feature_path(feature: dict[str, Any]) -> str:
    steps = feature.get("steps", []) if isinstance(feature.get("steps", []), list) else []
    for step in steps:
        if isinstance(step, dict) and _text(step.get("path")):
            return _text(step.get("path"))
    entrypoint = _text(feature.get("entrypoint"))
    if "/" in entrypoint and entrypoint.rsplit(".", 1)[-1].lower() in {
        "go", "js", "jsx", "py", "ts", "tsx",
    }:
        return entrypoint
    return ""


def _is_unconfirmed_feature(feature: dict[str, Any]) -> bool:
    return (
        _text(feature.get("kind")) == "entrypoint-candidate"
        or _text(feature.get("confidence")).lower() == "candidate"
    )


def _capability_group(feature: dict[str, Any], modules_by_id: dict[str, dict[str, Any]]) -> str:
    kind = _text(feature.get("kind"), "capability")
    if kind == "capability-cluster":
        return "源码审计能力"
    if _is_unconfirmed_feature(feature):
        return "未确认入口候选"
    if kind == "http-route":
        parts = _text(feature.get("entrypoint")).split(maxsplit=1)
        route = parts[1] if len(parts) == 2 else ""
        segments = [part for part in route.split("/") if part and not part.startswith("{")]
        segment = next((part for part in segments if part.lower() not in {"api", "v1", "v2", "v3"}), "root")
        return f"静态确认 HTTP 入口声明 · /{segment}"
    if kind == "cli-command":
        return "静态确认 CLI 入口声明"
    component_ids = feature.get("component_ids", []) if isinstance(feature.get("component_ids", []), list) else []
    component_names = [
        _text(modules_by_id.get(_text(identifier), {}).get("name"))
        for identifier in component_ids
        if _text(modules_by_id.get(_text(identifier), {}).get("name"))
    ]
    source_path = _feature_path(feature)
    path_parts = [part for part in source_path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] in {"cmd", "src", "apps", "packages"}:
        path_component = "/".join(path_parts[:2])
    elif path_parts:
        path_component = path_parts[0]
    else:
        path_component = ""
    component = path_component or (component_names[0] if component_names else "root")
    if kind == "entrypoint":
        return f"已确认程序入口 · {component}"
    return f"静态导航候选 · {component}"


def _group_features(
    features: list[dict[str, Any]], modules_by_id: dict[str, dict[str, Any]]
) -> list[tuple[str, list[tuple[int, dict[str, Any]]]]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for position, feature in enumerate(features, start=1):
        grouped.setdefault(_capability_group(feature, modules_by_id), []).append((position, feature))

    def group_rank(item: tuple[str, list[tuple[int, dict[str, Any]]]]) -> tuple[int, str]:
        kinds = {_text(feature.get("kind")) for _position, feature in item[1]}
        if "capability-cluster" in kinds:
            return 0, item[0]
        if all(_is_unconfirmed_feature(feature) for _position, feature in item[1]):
            return 2, item[0]
        return 1, item[0]

    return sorted(grouped.items(), key=group_rank)


def _render_feature_directory(
    features: list[dict[str, Any]],
    modules_by_id: dict[str, dict[str, Any]],
    *,
    tutorial_mode: bool = False,
) -> str:
    if not features:
        return (
            '<div class="feature-empty"><strong>尚未识别出可独立讲解的功能</strong>'
            '<p>这份索引仍可用于查看阅读路线、模块和源码证据；重新生成 schema 2.0 索引后会出现功能视图。</p></div>'
        )
    if tutorial_mode:
        items = []
        for position, feature in enumerate(features, start=1):
            human_title, human_summary = _human_copy(feature)
            items.append(
                f'<a class="feature-nav" href="#feature-{position:03d}"><b>{position:02d}</b><span>'
                f'<strong>{html.escape(human_title)}</strong>'
                f'<small>{html.escape(human_summary)}</small></span>'
                '<em class="pill exact">完整教程</em></a>'
            )
        return (
            '<div class="capability-directory"><section class="capability-directory-group">'
            '<header><h3>项目功能地图</h3><span>先读功能，再看源码</span></header>'
            f'<div class="feature-directory">{"".join(items)}</div></section></div>'
        )

    groups: list[str] = []
    for group_name, members in _group_features(features, modules_by_id):
        items: list[str] = []
        for position, feature in members:
            confidence_class, confidence_text = _confidence_label(feature.get("confidence"))
            tests = feature.get("test_evidence_ids", []) if isinstance(feature.get("test_evidence_ids", []), list) else []
            human_title, _human_summary = _human_copy(feature)
            items.append(
                f'<a class="feature-nav" href="#feature-{position:03d}"><b>{position:02d}</b><span>'
                f'<strong>{html.escape(human_title)}</strong>'
                f'<small>{html.escape(_text(feature.get("kind"), "capability"))} · {len(tests)} 条静态测试引用</small>'
                f'</span><em class="pill {confidence_class}">{html.escape(confidence_text)}</em></a>'
            )
        groups.append(
            '<section class="capability-directory-group">'
            f'<header><h3>{html.escape(group_name)}</h3><span>{len(members)} 条分层记录</span></header>'
            f'<div class="feature-directory">{"".join(items)}</div></section>'
        )
    return f'<div class="capability-directory">{"".join(groups)}</div>'


def _render_technology_assessment(
    feature: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    project_root: str,
) -> str:
    tags = feature.get("technology_tags", []) if isinstance(feature.get("technology_tags", []), list) else []
    dimensions = ("parser", "framework", "store", "retrieval", "llm", "incremental", "evidence", "ui")
    by_dimension = {
        _text(tag).split(":", 1)[0]: _text(tag).split(":", 1)[1]
        for tag in tags
        if ":" in _text(tag) and _text(tag).split(":", 1)[0] in dimensions
    }
    labels = {
        "parser": "解析器", "framework": "框架", "store": "数据/状态",
        "retrieval": "检索/图算法", "llm": "LLM", "incremental": "增量策略",
        "evidence": "证据机制", "ui": "交互界面",
    }
    raw_claims = feature.get("technology_claims", [])
    claims = {
        _text(claim.get("dimension")): claim
        for claim in raw_claims
        if isinstance(raw_claims, list) and isinstance(claim, dict) and _text(claim.get("dimension"))
    } if isinstance(raw_claims, list) else {}
    rows = []
    for dimension in dimensions:
        value = by_dimension.get(dimension, "unknown")
        claim = claims.get(dimension, {})
        if claim:
            value = _text(claim.get("value"), value)
        css = "unknown-tech" if value == "unknown" else ""
        evidence_ids = claim.get("evidence_ids", []) if isinstance(claim.get("evidence_ids", []), list) else []
        resolved_evidence = [evidence_by_id[_text(identifier)] for identifier in evidence_ids if _text(identifier) in evidence_by_id]
        first_evidence = resolved_evidence[0] if resolved_evidence else {}
        source_path = _text(claim.get("source_path"), _text(first_evidence.get("path")))
        source = (
            _source_anchor(
                project_root,
                source_path,
                _as_int(first_evidence.get("line_start")),
                _as_int(first_evidence.get("line_end")),
            )
            if source_path
            else '<span class="muted">无独立源码路径</span>'
        )
        evidence_labels = "".join(
            f'<code>{html.escape(_text(identifier))}</code>' for identifier in evidence_ids if _text(identifier)
        )
        evidence_status = (
            f'{len(resolved_evidence)}/{len(evidence_ids)} 条独立证据 {evidence_labels}'
            if evidence_ids
            else "无证据；保持未知"
        )
        rows.append(
            '<li class="technology-claim"><div>'
            f'<b>{html.escape(labels[dimension])}</b>'
            f'<span class="{css}">{html.escape(value if value != "unknown" else "未知")}</span></div>'
            f'<p>{html.escape(_text(claim.get("claim_scope"), "没有可独立审计的声明，不作猜测。"))}</p>'
            f'<small>{html.escape(evidence_status)}</small>{source}</li>'
        )
    return (
        '<div class="technology-assessment"><div><strong>八类底层实现信号</strong>'
        f'<ul class="technology-dimensions">{"".join(rows)}</ul></div><div><strong>证据边界</strong>'
        '<p>每个已知标签必须有自己的 evidence ID、源码路径和声明边界；标为“未知”的维度不用关键词补齐。'
        '静态调用边仍不能证明运行时分支、异常与并发行为。</p></div></div>'
    )


def _render_teaching_artifacts(
    tutorial: dict[str, Any] | None,
    codemap: dict[str, Any] | None,
    completeness: dict[str, Any] | None,
) -> str:
    codemap_label = "代码地图"
    tutorial_html = (
        '<p class="muted compact">尚未生成教程。</p>'
        if tutorial is None
        else _render_tutorial_chapters(tutorial)
    )
    if codemap is None:
        codemap_html = '<p class="muted compact">尚未生成代码地图。</p>'
    else:
        nodes = codemap.get("nodes", []) if isinstance(codemap.get("nodes", []), list) else []
        edges = codemap.get("edges", []) if isinstance(codemap.get("edges", []), list) else []
        node_html = "".join(
            f'<li><b>{_as_int(node.get("order"), position):02d}</b><span>{html.escape(_text(node.get("label"), "未命名节点"))}</span></li>'
            for position, node in enumerate(nodes, start=1) if isinstance(node, dict)
        )
        edge_html = "".join(
            '<li><span>' + html.escape(_text(edge.get("source"), "?")) + '</span>'
            + ('<b>→</b>' if _text(edge.get("semantics")) == "resolved-static-relationship" else '<b>⇢</b>')
            + '<span>' + html.escape(_text(edge.get("target"), "?")) + '</span>'
            + '<small>' + html.escape(_text(edge.get("kind"), "unknown")) + '</small></li>'
            for edge in edges if isinstance(edge, dict)
        )
        if not edges:
            codemap_label = "单点源码定位"
        codemap_html = (
            f'<div class="codemap-graph"><ol class="codemap-nodes">{node_html}</ol>'
            f'<ul class="codemap-edges">{edge_html or "<li>尚无可显示的节点关系。</li>"}</ul></div>'
            '<small>→ 表示已解析静态关系；⇢ 只表示建议阅读顺序。图形不声明运行时先后。</small>'
        )
    if completeness is None:
        completeness_html = '<p class="muted compact">尚未计算证据完整度。</p>'
    else:
        gaps = completeness.get("gaps", []) if isinstance(completeness.get("gaps", []), list) else []
        gap_html = "".join(f'<li>{html.escape(_text(gap, "未知缺口"))}</li>' for gap in gaps)
        checks = completeness.get("checks", {}) if isinstance(completeness.get("checks", {}), dict) else {}
        check_html = "".join(
            f'<li><b>{"✓" if present else "○"}</b><span>{html.escape(str(name))}</span></li>'
            for name, present in checks.items()
        )
        completeness_html = (
            f'<p><b>{html.escape(_text(completeness.get("status"), "unknown"))}</b> · 只表示静态信号</p>'
            f'<ul class="signal-checks">{check_html}</ul>'
            f'{f"<ul>{gap_html}</ul>" if gap_html else "<p>当前五项静态证据信号均存在。</p>"}'
            '<small>这不是测试覆盖率；行为覆盖、正确性和生产可用性仍为未知。</small>'
        )
    return (
        '<div class="artifact-grid"><section><strong>教程</strong>'
        f'{tutorial_html}</section><section><strong>{codemap_label}</strong>{codemap_html}</section>'
        f'<section><strong>证据完整度与缺口</strong>{completeness_html}</section></div>'
    )


def _render_difficulty_map(
    tutorial: dict[str, Any] | None,
    evidence_by_id: dict[str, dict[str, Any]],
    project_root: str,
) -> str:
    """Render the mechanism-level teaching layer before source-navigation details.

    Difficulty records are derived artifacts.  They are deliberately separate
    from the feature summary: a reader first learns what the capability does,
    then the invariants and failure modes that make its implementation hard.
    """

    if tutorial is None:
        return '<p class="muted compact">尚未生成实现难点；不要从文件大小或函数数量猜测。</p>'
    difficulty_map = tutorial.get("difficulty_map", {})
    if not isinstance(difficulty_map, dict):
        return '<p class="muted compact">尚未生成实现难点；不要从文件大小或函数数量猜测。</p>'
    items = difficulty_map.get("items", [])
    items = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    if not items:
        return '<p class="muted compact">当前证据不足以确认机制难点；保留为未知，不用通用文案补齐。</p>'

    def bullet_list(values: object, empty: str) -> str:
        normalized = [_text(value) for value in values if _text(value)] if isinstance(values, list) else []
        if not normalized:
            return f'<p class="muted compact">{html.escape(empty)}</p>'
        return '<ol>' + ''.join(f'<li>{html.escape(value)}</li>' for value in normalized) + '</ol>'

    rendered: list[str] = []
    for position, item in enumerate(items, start=1):
        evidence_ids = item.get("evidence_ids", [])
        evidence_ids = [_text(value) for value in evidence_ids if _text(value)] if isinstance(evidence_ids, list) else []
        source_locations: list[tuple[str, int, int]] = []
        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if not evidence:
                continue
            source_locations.append(
                (
                    _text(evidence.get("path"), "unknown"),
                    _as_int(evidence.get("line_start")),
                    _as_int(evidence.get("line_end")),
                )
            )
        source_html = ''.join(
            _source_anchor(project_root, path, start, end)
            for path, start, end in list(dict.fromkeys(source_locations))[:6]
        ) or '<span class="muted">没有独立源码证据，保持候选。</span>'
        confidence = _text(item.get("confidence"), "candidate")
        rendered.append(
            '<details class="difficulty-card">'
            '<summary><span>'
            f'{position:02d} · {html.escape(_text(item.get("category"), "mechanism"))}</span>'
            '<div><strong>'
            f'{html.escape(_text(item.get("title"), "未命名难点"))}</strong>'
            f'<small>{html.escape(_text(item.get("why_hard"), "当前证据尚未解释复杂性来源。"))}</small>'
            f'</div><em>{html.escape(confidence)}</em></summary>'
            '<div class="difficulty-body"><div class="difficulty-sequence">'
            '<section><b>1 · 运行时到底怎么走</b>'
            f'{bullet_list(item.get("runtime_steps"), "运行次序未知。")}</section>'
            '<section><b>2 · 必须一直成立的不变量</b>'
            f'{bullet_list(item.get("invariants"), "尚未确认不变量。")}</section>'
            '<section><b>3 · 如果天真实现会怎样</b>'
            f'<p>{html.escape(_text(item.get("naive_failure"), "尚未确认反例。"))}</p>'
            f'{bullet_list(item.get("failure_modes"), "尚未确认失败模式。")}</section>'
            '<section><b>4 · 为什么采用这个取舍</b>'
            f'{bullet_list(item.get("tradeoffs"), "尚未确认取舍。")}</section>'
            '</div>'
            '<details class="difficulty-proof"><summary>查看源码证据、迁移问题与未知项</summary>'
            '<div class="difficulty-footer"><div><b>源码 / 测试证据</b>'
            f'<div class="source-locations">{source_html}</div></div>'
            '<div><b>迁移前先回答</b>'
            f'<p>{html.escape(_text(item.get("reuse_question"), "你的约束是否与该项目一致？"))}</p></div></div>'
            f'{bullet_list(item.get("unknowns"), "这一机制暂未列出额外未知项。")}'
            '</details></div></details>'
        )
    global_unknowns = difficulty_map.get("unknowns", [])
    unknown_html = bullet_list(global_unknowns, "没有额外的全局未知项。")
    return (
        '<div class="difficulty-intro"><strong>真正需要先理解的实现难点</strong>'
        f'<p>{html.escape(_text(difficulty_map.get("summary"), "按机制、状态与失败边界阅读，不按代码行数排名。"))}</p>'
        '<small>难点必须由源码、测试或已解析关系支持；LLM 只能讲解，不能凭空增加。</small></div>'
        f'<div class="difficulty-stack">{"".join(rendered)}</div>'
        '<aside class="difficulty-unknowns"><b>仍未证明</b>' + unknown_html + '</aside>'
    )


def _human_list(values: object, empty: str) -> str:
    items = [_text(value) for value in values if _text(value)] if isinstance(values, list) else []
    if not items:
        return f'<p class="muted compact">{html.escape(empty)}</p>'
    return '<ol class="human-list">' + ''.join(
        f'<li>{html.escape(value)}</li>' for value in items
    ) + '</ol>'


def _render_human_feature_chapter(
    feature: dict[str, Any],
    tutorial: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    project_root: str,
    position: int,
    hierarchy_label: str = "业务功能",
) -> str:
    chapter = tutorial.get("human_chapter", {})
    if not isinstance(chapter, dict) or not chapter:
        return ""
    human_title, human_summary = _human_copy(feature)
    story = chapter.get("runtime_story", {}) if isinstance(chapter.get("runtime_story"), dict) else {}
    construction = chapter.get("construction", {}) if isinstance(chapter.get("construction"), dict) else {}
    mechanism_model = chapter.get("mechanism_model", {}) if isinstance(chapter.get("mechanism_model"), dict) else {}
    boundary = chapter.get("boundary", {}) if isinstance(chapter.get("boundary"), dict) else {}
    reuse = chapter.get("reuse_plan", {}) if isinstance(chapter.get("reuse_plan"), dict) else {}
    objects = construction.get("objects", []) if isinstance(construction.get("objects"), list) else []
    state_flow = chapter.get("state_flow", []) if isinstance(chapter.get("state_flow"), list) else []
    choices = chapter.get("design_choices", []) if isinstance(chapter.get("design_choices"), list) else []

    object_html = ''.join(
        '<article><b>' + html.escape(_text(item.get("name"), "核心对象")) + '</b><p>'
        + html.escape(_text(item.get("role"), "职责待确认")) + '</p></article>'
        for item in objects if isinstance(item, dict)
    )
    state_rows = ''.join(
        '<tr><th>' + html.escape(_text(item.get("stage"), "阶段")) + '</th>'
        '<td data-label="读取">' + html.escape(_text(item.get("reads"), "未知")) + '</td>'
        '<td data-label="写入">' + html.escape(_text(item.get("writes"), "未知")) + '</td>'
        '<td data-label="为什么进入下一步">' + html.escape(_text(item.get("why_next"), "未知")) + '</td></tr>'
        for item in state_flow if isinstance(item, dict)
    )
    choice_html = ''.join(
        '<article><h5>' + html.escape(_text(item.get("choice"), "设计选择")) + '</h5>'
        '<dl><dt>为什么</dt><dd>' + html.escape(_text(item.get("why"), "未知")) + '</dd>'
        '<dt>代价</dt><dd>' + html.escape(_text(item.get("cost"), "未知")) + '</dd></dl></article>'
        for item in choices if isinstance(item, dict)
    )
    mechanism_fields = (
        ("存什么 / 数据结构", "storage"),
        ("如何写入", "write_path"),
        ("如何读取 / 查询", "read_path"),
        ("核心循环", "control_loop"),
        ("决策 / 路由规则", "decision_rules"),
        ("何时结束", "termination"),
        ("哪些可以动态变化", "dynamic_behavior"),
    )
    mechanism_html = ''.join(
        '<article><b>' + html.escape(label) + '</b><p>'
        + html.escape(_text(mechanism_model.get(field), "当前证据表明没有独立机制，或仍需确认。"))
        + '</p></article>'
        for label, field in mechanism_fields
    )
    plain_summary = _chapter_conclusion(
        mechanism_model.get("plain_summary"),
        human_title,
        "当前证据还不足以概括这个功能的本质。",
    )
    visible_outcome = _chapter_conclusion(
        story.get("output"),
        human_title,
        "当前证据还不足以确认用户最终得到什么。",
    )
    runtime_steps = story.get("steps", []) if isinstance(story.get("steps"), list) else []
    readable_steps = [_text(step) for step in runtime_steps if _text(step)]
    if len(readable_steps) >= 2:
        runtime_preview = f"开始：{readable_steps[0]} 最后：{readable_steps[-1]}"
    elif readable_steps:
        runtime_preview = readable_steps[0]
    else:
        runtime_preview = "当前没有足够证据还原运行过程。"
    interaction_roles = (
        ("触发", story.get("trigger")),
        ("运行时接管", story.get("owner")),
        ("产生", story.get("output")),
        ("交给", story.get("consumer")),
    )
    interaction_nodes = [
        '<article class="interaction-node"><span>' + f"{role_position:02d}" + '</span><div><b>'
        + html.escape(label) + '</b><p>'
        + html.escape(_text(value, "未知")) + '</p></div></article>'
        for role_position, (label, value) in enumerate(interaction_roles, start=1)
    ]
    interaction_arrow = (
        '<svg class="interaction-arrow" viewBox="0 0 52 24" aria-hidden="true" '
        'focusable="false"><path d="M2 12H43"/><path d="m36 5 8 7-8 7"/></svg>'
    )
    interaction_flow_html = interaction_arrow.join(interaction_nodes)
    activity_nodes = [
        '<article class="activity-node"><span>' + f"{step_position:02d}" + '</span><p>'
        + html.escape(_text(step)) + '</p></article>'
        for step_position, step in enumerate(runtime_steps, start=1)
        if _text(step)
    ]
    activity_connector = (
        '<svg class="activity-connector" viewBox="0 0 24 42" aria-hidden="true" '
        'focusable="false"><path d="M12 2V33"/><path d="m5 27 7 8 7-8"/></svg>'
    )
    activity_flow_html = activity_connector.join(activity_nodes)
    worked_example = mechanism_model.get("worked_example")
    take_items = reuse.get("take", []) if isinstance(reuse.get("take"), list) else []
    adapt_items = reuse.get("adapt", []) if isinstance(reuse.get("adapt"), list) else []
    final_take = (
        _text(take_items[0], "当前没有可以直接复用的结论。")
        if take_items else "当前没有可以直接复用的结论。"
    )
    final_adapt = (
        _text(adapt_items[0], "复用前仍需补充验证。")
        if adapt_items else "复用前仍需补充验证。"
    )
    return (
        f'<article class="feature-card human-feature-card" id="feature-{position:03d}">'
        '<div class="feature-card-head"><div>'
        f'<span class="feature-index">功能 {position:02d} · {html.escape(hierarchy_label)} · 源码静态确认</span>'
        f'<h3>{html.escape(human_title)}</h3>'
        '<p class="feature-thesis"><span>先说结论</span><strong>简单来说，这个功能就是：'
        f'{html.escape(plain_summary)}</strong></p>'
        f'<p class="chapter-question">{html.escape(_text(chapter.get("question"), human_summary))}</p>'
        '</div><span class="confidence-badge exact">功能级源码讲解</span></div>'
        '<section class="human-glance"><span class="answer-label">先用 30 秒理解</span>'
        '<div class="glance-grid"><article class="glance-primary"><b>用户最终得到什么</b>'
        f'<strong>{html.escape(visible_outcome)}</strong></article>'
        '<article><b>一次怎么跑</b>'
        f'<p>{html.escape(runtime_preview)}</p></article>'
        '<article><b>和相邻功能有什么不同</b>'
        f'<p>{html.escape(_text(chapter.get("distinguish"), "差异尚未确认"))}</p>'
        f'<small>适用：{html.escape(_text(chapter.get("use_when"), "使用边界未知"))}</small></article></div></section>'
        '<section class="human-run"><span class="answer-label">一次任务完整怎么运行</span>'
        '<div class="interaction-diagram" role="group" aria-label="一次任务的 UML 活动图" '
        'data-diagram-skill="markdown-viewer/uml" data-diagram-type="activity">'
        '<div class="interaction-diagram-head"><b>运行时活动图</b><span>节点和箭头表示真实交接，不是四栏摘要</span></div>'
        f'<div class="interaction-flow">{interaction_flow_html}</div>'
        '<div class="interaction-detail"><b>内部活动与先后关系</b>'
        '<div class="activity-flow"><span class="activity-terminal start">START</span>'
        f'{activity_connector if activity_nodes else ""}{activity_flow_html}'
        f'{activity_connector if activity_nodes else ""}'
        '<span class="activity-terminal end">END</span></div></div></div>'
        '<div class="interaction-explanation"><b>为什么要这样串起来</b><p>'
        f'{html.escape(_text(construction.get("explanation"), "当前证据没有解释模块之间为什么这样交接。"))}'
        '</p><dl><dt>持续推进靠什么</dt><dd>'
        f'{html.escape(_text(mechanism_model.get("control_loop"), "未确认"))}</dd>'
        '<dt>谁决定下一步</dt><dd>'
        f'{html.escape(_text(mechanism_model.get("decision_rules"), "未确认"))}</dd>'
        '<dt>何时结束或打断</dt><dd>'
        f'{html.escape(_text(mechanism_model.get("termination"), "未确认"))}</dd>'
        '<dt>运行中能否改变</dt><dd>'
        f'{html.escape(_text(mechanism_model.get("dynamic_behavior"), "未确认"))}</dd></dl></div>'
        '<div class="visible-example"><b>比如，一次真实交互会这样发生</b>'
        f'{_human_list(worked_example, "当前没有足够证据给出完整例子。")}</div></section>'
        '<details class="human-deep-dive mechanism-details"><summary><span>01</span><div><b>底层机制到底怎么工作</b>'
        '<small>数据、控制循环、路由、结束条件与状态变化</small></div></summary><div class="human-deep-body">'
        '<div class="mechanism-verdict"><span>先说结论</span><strong>'
        f'{html.escape(plain_summary)}'
        '</strong></div>'
        f'<div class="mechanism-grid">{mechanism_html}</div>'
        '<h4>核心机制怎么构建</h4>'
        f'<p class="chapter-lead">{html.escape(_text(construction.get("explanation"), "构建方式未知。"))}</p>'
        f'<div class="object-grid">{object_html}</div>'
        '<h4>状态是怎样一步步变化的</h4>'
        '<div class="state-table-wrap"><table class="state-flow-table"><thead><tr><th>阶段</th><th>读取</th><th>写入</th><th>为什么进入下一步</th></tr></thead>'
        f'<tbody>{state_rows}</tbody></table></div></div></details>'
        '<details class="human-deep-dive difficulty-details"><summary><span>02</span><div><b>真正难点与失败方式</b>'
        '<small>先看为什么难，再看不变量、失败模式与设计取舍</small></div></summary><div class="human-deep-body">'
        f'{_render_difficulty_map(tutorial, evidence_by_id, project_root)}'
        '<h4>为什么这样设计</h4>'
        f'<div class="choice-grid">{choice_html}</div></div></details>'
        '<details class="human-deep-dive reuse-details"><summary><span>03</span><div><b>边界、复用与技术选型</b>'
        '<small>它能做什么、不能做什么，以及哪些代码值得借鉴</small></div></summary><div class="human-deep-body">'
        '<h4>它能做什么、不能做什么</h4>'
        '<div class="boundary-grid"><article class="supported"><b>当前代码已经提供</b>'
        f'{_human_list(boundary.get("supported"), "未确认支持项。")}</article>'
        '<article class="unsupported"><b>不要误以为已经提供</b>'
        f'{_human_list(boundary.get("unsupported"), "未确认缺口。")}</article></div>'
        '<h4>如果你要复用</h4><div class="reuse-grid"><article><b>可以拿走</b>'
        f'{_human_list(reuse.get("take"), "暂无建议。")}</article><article><b>必须改造</b>'
        f'{_human_list(reuse.get("adapt"), "暂无建议。")}</article><article><b>不要照搬</b>'
        f'{_human_list(reuse.get("avoid"), "暂无建议。")}</article><article><b>先验证</b>'
        f'{_human_list(reuse.get("verify"), "暂无建议。")}</article></div></div></details>'
        '<aside class="human-recap"><span>最后记住</span>'
        f'<strong>{html.escape(plain_summary)}</strong>'
        f'<p><b>复用：</b>{html.escape(final_take)} <b>先改：</b>{html.escape(final_adapt)}</p></aside>'
    )


def _render_tutorial_chapters(tutorial: dict[str, Any]) -> str:
    chapters = tutorial.get("chapters", []) if isinstance(tutorial.get("chapters", []), list) else []
    if not chapters:
        return f'<p>{html.escape(_text(tutorial.get("opening"), "未提供教程内容。"))}</p>'
    rendered: list[str] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        kind = _text(chapter.get("kind"))
        slices = chapter.get("slices", []) if isinstance(chapter.get("slices", []), list) else []
        gaps = chapter.get("gaps", {}) if isinstance(chapter.get("gaps", {}), dict) else {}
        slice_html = "".join(
            '<li><b>' + html.escape(_text(item.get("role"), _text(item.get("title"), "源码切片"))) + '</b>'
            '<span>' + html.escape(_text(item.get("symbol"), "未标注符号")) + '</span>'
            '<code>' + html.escape(
                f'{_text(item.get("path"), "unknown")}:{_as_int(item.get("line_start"))}'
            ) + '</code><span>' + html.escape(_text(item.get("claim_scope"), _text(item.get("purpose"), "核对源码职责。"))) + '</span></li>'
            for item in slices if isinstance(item, dict)
        )
        gap_html = "".join(
            f'<li><b>{html.escape(str(name))}</b><span>{html.escape(_text(value))}</span></li>'
            for name, value in gaps.items()
        )
        entry = chapter.get("entry", {}) if isinstance(chapter.get("entry", {}), dict) else {}
        entry_html = (
            '<dl class="tutorial-contract"><dt>入口</dt><dd><code>'
            + html.escape(_text(entry.get("boundary"), "未确认"))
            + '</code></dd><dt>置信度</dt><dd>'
            + html.escape(_text(entry.get("confidence"), "unknown")) + '</dd></dl>'
            if entry else ""
        )
        data_and_state = chapter.get("data_and_state", {}) if isinstance(chapter.get("data_and_state", {}), dict) else {}
        dependencies = chapter.get("dependencies", {}) if isinstance(chapter.get("dependencies", {}), dict) else {}

        def claim_list(section: dict[str, Any], label: str) -> str:
            section_claims = section.get("claims", []) if isinstance(section.get("claims", []), list) else []
            items = "".join(
                '<li><b>' + html.escape(_text(claim.get("dimension"), label)) + '</b><span>'
                + html.escape(_text(claim.get("value"), "unknown")) + ' · '
                + html.escape(_text(claim.get("claim_scope"), "未标注声明边界")) + '</span></li>'
                for claim in section_claims if isinstance(claim, dict)
            )
            boundary = _text(section.get("boundary"))
            return (f'<ul>{items}</ul>' if items else f'<p class="muted">{html.escape(label)}：未知</p>') + (
                f'<small>{html.escape(boundary)}</small>' if boundary else ""
            )

        data_html = claim_list(data_and_state, "数据/状态") if kind == "data-state-and-dependencies" else ""
        dependency_html = claim_list(dependencies, "依赖") if kind == "data-state-and-dependencies" else ""
        reuse = chapter.get("reuse_boundary", {}) if isinstance(chapter.get("reuse_boundary", {}), dict) else {}
        reusable = reuse.get("reusable", []) if isinstance(reuse.get("reusable", []), list) else []
        must_reverify = reuse.get("must_reverify", []) if isinstance(reuse.get("must_reverify", []), list) else []
        reuse_html = ""
        if reuse:
            reusable_html = "".join(f'<li>{html.escape(_text(item))}</li>' for item in reusable)
            reverify_html = "".join(f'<li>{html.escape(_text(item))}</li>' for item in must_reverify)
            reuse_html = (
                f'<div class="reuse-boundary"><b>可学习/复用</b><ul>{reusable_html}</ul>'
                f'<b>必须重新验证</b><ul>{reverify_html}</ul></div>'
            )
        rendered.append(
            '<section class="tutorial-chapter"><h4>' + html.escape(_text(chapter.get("title"), "教程章节"))
            + '</h4><p>' + html.escape(_text(chapter.get("purpose"), "")) + '</p>'
            + entry_html
            + (f'<ol>{slice_html}</ol>' if slice_html else "")
            + data_html + dependency_html
            + (f'<ul>{gap_html}</ul>' if gap_html else "") + reuse_html + '</section>'
        )
    return "".join(rendered) + '<small>教程按“用途与入口 → 职责链 → 数据/依赖 → 缺口 → 复用边界”组织，不是 BFS 运行轨迹。</small>'


def _render_features(
    features: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    tutorials: list[dict[str, Any]],
    codemaps: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    modules_by_id: dict[str, dict[str, Any]],
    project_root: str,
    project_overview: dict[str, Any] | None = None,
) -> str:
    if not features:
        return ""
    evidence_by_id = {
        _text(item.get("id")): item for item in evidence if isinstance(item, dict) and _text(item.get("id"))
    }
    tutorial_by_feature = {_text(item.get("feature_id")): item for item in tutorials if _text(item.get("feature_id"))}
    codemap_by_feature = {_text(item.get("feature_id")): item for item in codemaps if _text(item.get("feature_id"))}
    coverage_by_feature = {_text(item.get("feature_id")): item for item in coverage if _text(item.get("feature_id"))}
    supporting_ids = {
        _text(item)
        for item in (
            project_overview.get("supporting_capability_ids", [])
            if isinstance(project_overview, dict)
            and isinstance(project_overview.get("supporting_capability_ids"), list)
            else []
        )
        if _text(item)
    }
    core_ids = {
        _text(capability_id)
        for axis in (
            project_overview.get("core_product_axes", [])
            if isinstance(project_overview, dict)
            and isinstance(project_overview.get("core_product_axes"), list)
            else []
        )
        if isinstance(axis, dict)
        for capability_id in (
            axis.get("capability_ids", [])
            if isinstance(axis.get("capability_ids"), list)
            else []
        )
        if _text(capability_id)
    }
    cards_by_position: dict[int, str] = {}
    for position, feature in enumerate(features, start=1):
        steps = feature.get("steps", []) if isinstance(feature.get("steps", []), list) else []
        evidence_ids = feature.get("evidence_ids", []) if isinstance(feature.get("evidence_ids", []), list) else []
        test_ids = feature.get("test_evidence_ids", []) if isinstance(feature.get("test_evidence_ids", []), list) else []
        confidence_class, confidence_text = _confidence_label(feature.get("confidence"))
        tags = feature.get("technology_tags", []) if isinstance(feature.get("technology_tags", []), list) else []
        tag_html = "".join(f'<span>{html.escape(_text(tag, "unknown"))}</span>' for tag in tags if _text(tag))
        entry_symbol = _text(feature.get("entry_symbol_id"))
        entry_symbol_html = f'<small>符号 ID：<code>{html.escape(entry_symbol)}</code></small>' if entry_symbol else ""
        direct_locations: list[tuple[str, int, int]] = []
        for evidence_id in evidence_ids:
            item = evidence_by_id.get(_text(evidence_id))
            if item:
                direct_locations.append(
                    (_text(item.get("path"), "unknown"), _as_int(item.get("line_start")), _as_int(item.get("line_end")))
                )
        for step in steps:
            if not isinstance(step, dict):
                continue
            path = _text(step.get("path"))
            if path:
                start = _as_int(step.get("line_start"))
                end = _as_int(step.get("line_end"), start)
                direct_locations.append((path, start, end))
        locations = list(dict.fromkeys(direct_locations))
        location_html = "".join(_source_anchor(project_root, path, start, end) for path, start, end in locations[:12])
        if not location_html:
            location_html = '<span class="muted">暂无可解析源码位置</span>'
        source_evidence = _render_evidence_refs(
            evidence_ids, evidence_by_id, empty_message="功能记录尚未关联独立源码证据。", project_root=project_root
        )
        test_evidence = _render_evidence_refs(
            test_ids, evidence_by_id, empty_message="未发现测试源码到该入口的已解析引用；不能据此判断行为已覆盖。", project_root=project_root
        )
        feature_id = _text(feature.get("id"))
        feature_kind = _text(feature.get("kind"))
        human_title, human_summary = _human_copy(feature)
        if feature_kind == "capability-cluster":
            verdict = "能力与核心源码切片来自固定版本人工审计；数据流、异常和运行时行为仍需继续验证。"
        elif _is_unconfirmed_feature(feature):
            verdict = "只确认同名符号存在，尚无可执行标记证明它是运行入口。"
        else:
            verdict = (
                "只确认静态入口声明；可运行性与实际可达性未知，"
                "调用顺序、错误路径和行为测试仍需源码审计。"
            )
        tutorial = tutorial_by_feature.get(feature_id)
        chapter = tutorial.get("human_chapter", {}) if isinstance(tutorial, dict) else {}
        chapter_id = _text(chapter.get("id")) if isinstance(chapter, dict) else ""
        hierarchy_label = (
            "支撑能力"
            if chapter_id in supporting_ids
            else "核心功能" if chapter_id in core_ids else "业务功能"
        )
        human_feature = _render_human_feature_chapter(
            feature, tutorial, evidence_by_id, project_root, position, hierarchy_label
        ) if tutorial is not None else ""
        if human_feature:
            cards_by_position[position] = (
                human_feature
                + '<details class="evidence-chapter"><summary><span class="answer-label">10 · 最后再看源码证据</span>'
                + '<strong>入口、调用关系、技术标签与代码位置</strong><em>展开核验</em></summary>'
                + '<div class="evidence-chapter-body">'
                + '<p class="semantic-warning">下面的入口、符号和静态关系只用于核对上面的功能讲解；它们不再充当功能定义。</p>'
                + '<div class="evidence-entry"><b>实现定位起点</b>'
                + f'<code class="entrypoint">{html.escape(_text(feature.get("entrypoint"), "未标注入口"))}</code>'
                + entry_symbol_html
                + f'<p class="source-method">发现方式：{html.escape(_text(feature.get("source"), "unknown"))}</p></div>'
                + '<div class="implementation-block"><b>静态源码阅读路径</b>'
                + '<p class="semantic-warning">这是阅读顺序；只有标明 resolved 的边才是已解析静态关系，仍不等于真实运行轨迹。</p>'
                + _render_feature_steps(
                    [item for item in steps if isinstance(item, dict)], evidence_by_id, project_root
                ) + '</div>'
                + '<div class="source-block"><b>底层技术证据与未知项</b>'
                + _render_technology_assessment(feature, evidence_by_id, project_root) + '</div>'
                + '<div class="source-block"><b>直接源码位置</b>'
                + f'<div class="source-locations">{location_html}</div></div>'
                + '<div class="source-block"><b>代码地图与证据缺口</b>'
                + _render_teaching_artifacts(
                    tutorial,
                    codemap_by_feature.get(feature_id),
                    coverage_by_feature.get(feature_id),
                ) + '</div>'
                + f'<div class="evidence-columns"><details><summary>源码证据 <b>{len(evidence_ids)}</b></summary>{source_evidence}</details>'
                + f'<details><summary>测试静态引用（非行为覆盖） <b>{len(test_ids)}</b></summary>{test_evidence}</details></div>'
                + '</div></details><a class="back-link" href="#feature-index">↑ 回到功能目录</a></article>'
            )
            continue
        cards_by_position[position] = (
            f'<article class="feature-card" id="feature-{position:03d}">'
            '<div class="feature-card-head"><div>'
            f'<span class="feature-index">功能 {position:02d} · {html.escape(_text(feature.get("kind"), "capability"))}</span>'
            f'<h3>{html.escape(human_title)}</h3></div>'
            f'<span class="confidence-badge {confidence_class}">{html.escape(confidence_text)}</span></div>'
            '<div class="feature-answer-grid">'
            '<section class="answer-block"><span class="answer-label">01 · 提供什么功能</span>'
            f'<p class="feature-summary">{html.escape(human_summary)}</p>'
            f'<div class="tag-list">{tag_html}</div></section>'
            '<section class="answer-block"><span class="answer-label">02 · 从哪里进入</span>'
            f'<code class="entrypoint">{html.escape(_text(feature.get("entrypoint"), "未标注入口"))}</code>{entry_symbol_html}'
            f'<p class="source-method">发现方式：{html.escape(_text(feature.get("source"), "unknown"))}</p></section></div>'
            '<div class="difficulty-block"><span class="answer-label">03 · 实现难点与运行时约束</span>'
            f'{_render_difficulty_map(tutorial, evidence_by_id, project_root)}</div>'
            '<div class="implementation-block"><span class="answer-label">04 · 静态实现阅读路径</span>'
            '<p class="semantic-warning">以下顺序用于阅读，不声明真实运行时先后。</p>'
            f'{_render_feature_steps([item for item in steps if isinstance(item, dict)], evidence_by_id, project_root)}</div>'
            '<div class="source-block"><span class="answer-label">05 · 技术证据与未知项</span>'
            f'{_render_technology_assessment(feature, evidence_by_id, project_root)}</div>'
            '<div class="source-block"><span class="answer-label">06 · 源码位置</span>'
            f'<div class="source-locations">{location_html}</div></div>'
            '<div class="source-block"><span class="answer-label">07 · 教程、代码地图与证据缺口</span>'
            f'{_render_teaching_artifacts(tutorial, codemap_by_feature.get(feature_id), coverage_by_feature.get(feature_id))}</div>'
            f'<div class="evidence-columns"><details><summary>入口与符号源码证据 <b>{len(evidence_ids)}</b></summary>'
            f'{source_evidence}</details><details><summary>测试到入口的静态引用（非行为覆盖） <b>{len(test_ids)}</b></summary>{test_evidence}</details></div>'
            '<div class="feature-verdict"><strong>阅读结论</strong>'
            f'<p>当前结论为“{html.escape(confidence_text)}”：'
            f'{html.escape(verdict)}</p></div>'
            '<a class="back-link" href="#feature-index">↑ 回到功能目录</a></article>'
        )
    if features and all(_waku_mechanism(feature) for feature in features):
        return '<div class="feature-stack">' + ''.join(
            cards_by_position[position] for position in sorted(cards_by_position)
        ) + '</div>'

    groups: list[str] = []
    for group_name, members in _group_features(features, modules_by_id):
        group_kind = "源码审计能力" if group_name == "源码审计能力" else "边界 / 候选分组"
        groups.append(
            '<section class="capability-detail-group">'
            f'<div class="capability-group-head"><span>{html.escape(group_kind)}</span><h3>{html.escape(group_name)}</h3>'
            f'<p>{len(members)} 条记录；静态入口声明、源码审计能力与未确认候选不会互相冒充。</p></div>'
            f'<div class="feature-stack">{"".join(cards_by_position[position] for position, _feature in members)}</div>'
            '</section>'
        )
    return "".join(groups)


def render_report(
    index: dict[str, Any],
    *,
    variant: Literal["auto", "canonical", "human", "compatibility"] = "auto",
) -> str:
    if variant not in {"auto", "canonical", "human", "compatibility"}:
        raise ValueError(f"unsupported report variant: {variant}")
    project = index.get("project", {}) if isinstance(index.get("project", {}), dict) else {}
    stats = index.get("stats", {}) if isinstance(index.get("stats", {}), dict) else {}
    features = [item for item in index.get("features", []) if isinstance(item, dict)] if isinstance(index.get("features", []), list) else []
    evidence = [item for item in index.get("evidence", []) if isinstance(item, dict)] if isinstance(index.get("evidence", []), list) else []
    tutorials = [item for item in index.get("tutorials", []) if isinstance(item, dict)] if isinstance(index.get("tutorials", []), list) else []
    codemaps = [item for item in index.get("codemaps", []) if isinstance(item, dict)] if isinstance(index.get("codemaps", []), list) else []
    coverage = [item for item in index.get("coverage", []) if isinstance(item, dict)] if isinstance(index.get("coverage", []), list) else []
    modules = [item for item in index.get("modules", []) if isinstance(item, dict)] if isinstance(index.get("modules", []), list) else []
    modules_by_id = {_text(item.get("id")): item for item in modules if _text(item.get("id"))}
    project_name = html.escape(str(project.get("name") or "Unnamed repository"))
    commit = project.get("commit")
    snapshot_label = str(commit)[:12] if commit else "NO GIT SNAPSHOT"
    dirty_label = " · 工作区有未提交修改" if project.get("dirty") else ""
    license_label = project.get("license") or "未识别"
    branch = project.get("branch") or "detached / none"
    project_path = str(project.get("path") or "unknown")
    project_directory = Path(project_path).name or project_name
    tested_features = sum(
        1 for feature in features
        if isinstance(feature.get("test_evidence_ids", []), list) and feature.get("test_evidence_ids")
    )
    capabilities = [feature for feature in features if _text(feature.get("kind")) == "capability-cluster"]
    boundaries = [
        feature for feature in features
        if _text(feature.get("kind")) in {"http-route", "cli-command", "entrypoint"}
        and not _is_unconfirmed_feature(feature)
    ]
    candidates = [feature for feature in features if _is_unconfirmed_feature(feature)]
    inferred_human = bool(index.get("human_report")) and all(
        _text(feature.get("source")) == "llm-evidence-synthesis"
        for feature in features
    )
    is_human_report = variant == "human" or (variant == "auto" and inferred_human)
    is_waku = variant == "compatibility" or (
        variant == "auto"
        and not is_human_report
        and str(project_directory).lower() in {"waku", "waku-agent"}
    )
    waku_features = _waku_compatibility_features(features) if is_waku else []
    human_report_meta = (
        index.get("human_report") if isinstance(index.get("human_report"), dict) else {}
    )
    project_overview = (
        human_report_meta.get("project_overview")
        if isinstance(human_report_meta.get("project_overview"), dict)
        else None
    )
    display_features = [feature for _position, feature in waku_features] if waku_features else features
    best_feature = capabilities[0] if capabilities else (max(boundaries, key=_feature_rank) if boundaries else None)
    if is_human_report:
        positioning = _text(
            project_overview.get("one_liner") if project_overview else None,
            (
                f"这是一份面向人的项目功能说明。当前从固定版本源码归纳出 {len(features)} 个真实功能；"
                "先讲用途、运行过程、核心机制、难点与复用边界，入口和调用关系只作为最后的核验证据。"
            ),
        )
        feature_headline = "核心用户旅程排在最前，接入与管理能力随后。"
        action_line = "阅读顺序：项目定位与架构 → 核心用户旅程 → 关键功能 → 难点与取舍 → 复用边界 → 源码证据。"
    elif waku_features:
        positioning = (
            "这是一个本地优先的个人 AI 助手代码库。"
            f"当前固定版本可先按 {len(waku_features)} 组功能候选理解它，"
            "而不是从启动入口和符号列表反推产品。"
        )
        feature_headline = "先理解功能，再核对实现入口与源码证据。"
        action_line = "阅读顺序：功能作用 → 实现思路 → 关键源码 → 证据边界；启动入口只是最后的核验信息。"
    elif best_feature:
        best_title = _text(best_feature.get("title"), "首个已识别功能")
        positioning = (
            f"已从固定版本源码核验 {len(capabilities)} 个核心功能（源码审计能力）；"
            f"另有 {len(boundaries)} 个静态确认入口声明（可运行性与实际可达性未知），以及 "
            f"{len(candidates)} 个未确认入口候选（尚不可执行）。"
        )
        feature_headline = f"先看 {len(capabilities)} 个源码审计能力，再按需下钻边界与候选。"
        action_line = (
            f"建议起点：「{best_title}」。"
            if capabilities
            else f"当前没有源码审计能力清单；「{best_title}」只作为静态确认入口声明阅读。"
        )
    else:
        positioning = "当前索引还没有功能级结论；请先把它当作确定性代码导航，不要直接用于技术选型。"
        feature_headline = "先确认索引缺口，再进入模块与证据。"
        action_line = "建议下一步：使用 schema 2.0 重新索引，补齐功能入口和调用链。"
    feature_details = ""
    if is_human_report:
        feature_details = (
            '<section id="feature-details" class="feature-details">'
            '<div class="section-head"><span class="kicker">逐个讲清楚</span>'
            '<h2>每个功能都是一章完整的人类教程。</h2></div>'
            f'<div class="capability-detail-stack">{_render_features(display_features, evidence, tutorials, codemaps, coverage, modules_by_id, _text(project.get("path")), project_overview)}</div></section>'
        )
        confidence_summary = (
            f"这份报告讲清了 {len(features)} 个功能；所有功能结论都绑定到确定性索引证据，"
            "但性能、异常恢复与生产规模仍需实际运行验证。"
        )
        recommendation = (
            "先根据功能、机制、难点和边界选择值得借鉴的部分；"
            "只有需要核验结论时，才展开最后的源码证据。"
        )
    elif waku_features:
        feature_details = (
            '<section id="feature-details" class="feature-details">'
            '<div class="section-head"><span class="kicker">逐个讲清楚</span>'
            '<h2>每个功能都是一章完整教程，代码入口只放在最后核验。</h2></div>'
            f'<div class="capability-detail-stack">{_render_features(display_features, evidence, tutorials, codemaps, coverage, modules_by_id, _text(project.get("path")))}</div></section>'
        )
        confidence_summary = (
            f"Waku 当前展示 {len(waku_features)} 组功能候选和 {len(boundaries)} 个静态启动入口；"
            "它适合作为本地 Agent 的可读参考实现，但所有运行时结论仍需实机验证。"
        )
        recommendation = (
            "先按功能挑选要学习的模块，再进入对应源码卡核对实现与限制；"
            "不要因为存在同名类或函数，就直接判定可以生产复用。"
        )
    elif features:
        feature_details = (
            '<section id="feature-details" class="feature-details">'
            '<div class="section-head"><span class="kicker">逐个讲清楚</span>'
            '<h2>每个功能都回答“是什么”与“怎么做”。</h2></div>'
            f'<div class="capability-detail-stack">{_render_features(features, evidence, tutorials, codemaps, coverage, modules_by_id, _text(project.get("path")))}</div></section>'
        )
    if features and not waku_features and not is_human_report:
        confidence_summary = (
            f"共 {len(capabilities)} 个固定版本源码审计能力、{len(boundaries)} 个静态确认入口声明、"
            f"{len(candidates)} 个未确认候选；{tested_features} 条记录找到测试到入口的静态引用。"
        )
        recommendation = (
            "入口、静态调用链和测试引用只是定位证据；完成模块级源码审计前，不自动给出“可直接复用”结论。"
        )
    elif not is_human_report and not waku_features:
        confidence_summary = "当前没有可用的功能级证据覆盖。"
        recommendation = "不建议在这份旧索引上做复用结论；下方的模块和符号仅供定位。"
    template = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>__TITLE__ · Repository Index</title>
  <style>
    :root{--bg:#f2f0e9;--paper:#fffefa;--ink:#18201b;--muted:#667068;--line:#d9ddd7;--green:#0b6b4c;--green-soft:#e3f2eb;--orange:#d85d2a;--orange-soft:#fff0e7;--blue:#285fa8;--blue-soft:#eaf1fb;--shadow:0 24px 80px rgba(30,44,35,.08)}
    *{box-sizing:border-box}html{max-width:100%;scroll-behavior:smooth;background:var(--bg)}body{max-width:100%;margin:0;overflow-x:hidden;color:var(--ink);background:var(--bg);font:15px/1.65 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans SC",sans-serif}.shell{width:min(1240px,100%);max-width:100%;min-height:100vh;margin:auto;background:var(--paper);box-shadow:var(--shadow)}
    :where(main,section,article,aside,header,footer,details,summary,div,ol,ul,li,dl,dd){min-width:0;max-width:100%}:where(p,li,dd,small,strong,span,a,code){overflow-wrap:anywhere;word-break:break-word}pre{max-width:100%;overflow-x:auto;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}table{display:block;max-width:100%;overflow-x:auto}img,svg,video{max-width:100%;height:auto}
    header{position:sticky;top:0;z-index:10;display:flex;justify-content:space-between;align-items:center;gap:20px;padding:13px 38px;border-bottom:1px solid var(--line);background:rgba(255,254,250,.94);backdrop-filter:blur(12px)}.brand{font:850 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.12em}.snapshot{color:var(--muted);font:700 12px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace}
    main{padding:0 38px 72px}.hero{display:grid;grid-template-columns:1.25fr .75fr;gap:46px;padding:62px 0 48px;border-bottom:1px solid var(--line)}.eyebrow{margin:0 0 18px;color:var(--green);font-size:12px;font-weight:850;letter-spacing:.14em;text-transform:uppercase}h1,h2,h3{line-height:1.14;letter-spacing:-.03em}h1{margin:0;font-size:clamp(2.7rem,5vw,4.8rem);overflow-wrap:anywhere}.lead{max-width:760px;margin:20px 0 0;color:var(--ink);font-size:1.18rem}.identity{align-self:end;padding:23px;border:1px solid var(--line);border-radius:20px;background:var(--orange-soft)}.identity dl{display:grid;grid-template-columns:82px 1fr;gap:7px 12px;margin:0}.identity dt{color:var(--muted)}.identity dd{margin:0;font-weight:750;overflow-wrap:anywhere}.identity-more{margin-top:12px;padding-top:10px;border-top:1px solid rgba(216,93,42,.24)}.identity-more summary{cursor:pointer;color:var(--muted);font-size:12px;font-weight:750}.identity-more code{display:block;margin-top:8px;font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}
    section{padding-top:58px}.section-head{display:grid;grid-template-columns:.3fr 1fr;gap:28px;margin-bottom:24px}.kicker{color:var(--orange);font:850 12px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase}h2{margin:0;font-size:clamp(1.8rem,3.5vw,3rem)}
    .human-intro{max-width:900px;margin:-4px 0 22px;font-size:1.08rem}.human-capability-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.human-capability{display:flex;min-height:360px;flex-direction:column;padding:22px;border:1px solid var(--line);border-radius:20px;background:#fafaf6;color:var(--ink);text-decoration:none;transition:.16s ease}.human-capability:hover{border-color:var(--green);background:var(--green-soft);transform:translateY(-2px)}.human-capability>span{color:var(--orange);font:850 11px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.06em}.human-capability h3{margin:14px 0 10px;font-size:1.35rem}.human-capability p{margin:0 0 16px;color:var(--muted)}.human-capability dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:5px 10px;margin:auto 0 18px;padding-top:14px;border-top:1px solid var(--line);font-size:11px}.human-capability dt{color:var(--muted)}.human-capability dd{margin:0}.human-capability code{white-space:normal;overflow-wrap:anywhere}.human-capability>strong{color:var(--green);font-size:12px}.selection-head{margin-top:46px}.decision-table-wrap{max-width:100%;overflow-x:auto;border:1px solid var(--line);border-radius:18px}.decision-table{display:table;width:100%;min-width:980px;border-collapse:collapse;background:#fff}.decision-table th,.decision-table td{padding:16px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}.decision-table thead th{background:#18201b;color:#fff;font-size:11px;letter-spacing:.04em}.decision-table tbody th{width:17%;font-size:1rem}.decision-table td:nth-child(2){width:24%}.decision-table td:nth-child(3){width:20%;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px}.decision-table td:nth-child(4){width:25%}.decision-table td span,.decision-table td small{display:block;margin-top:6px;color:var(--muted)}.decision-table .source-link{display:block}.semantic-gap{margin-top:36px;padding:28px!important;border:1px dashed var(--orange);border-radius:20px;background:var(--orange-soft)}.semantic-gap .section-head{margin-bottom:12px}.semantic-gap p{max-width:900px;margin:0;color:#63311c}.quick-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.quick-card{padding:20px;border:1px solid var(--line);border-radius:18px;background:#fafaf6}.quick-card b{display:block;font-size:2rem;line-height:1}.quick-card span{display:block;margin-top:9px;color:var(--muted);font-size:12px}.action-line{margin:14px 0 0;padding:15px 18px;border-left:4px solid var(--orange);border-radius:0 12px 12px 0;background:var(--orange-soft);font-weight:750}.capability-directory{display:grid;gap:16px;margin-top:24px}.capability-directory-group{padding:18px!important;border:1px solid var(--line);border-radius:18px;background:#fafaf6}.capability-directory-group>header{display:flex;justify-content:space-between;gap:16px;align-items:baseline}.capability-directory-group h3{margin:0;font-size:1.15rem}.capability-directory-group header span{color:var(--muted);font-size:11px}.feature-directory{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:13px}.feature-nav{display:grid;grid-template-columns:38px 1fr auto;gap:12px;align-items:center;padding:17px;border:1px solid var(--line);border-radius:16px;background:#fff;color:var(--ink);text-decoration:none;transition:.15s ease}.feature-nav:hover{border-color:var(--green);background:var(--green-soft);transform:translateY(-1px)}.feature-nav>b{color:var(--orange);font:850 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace}.feature-nav span{min-width:0}.feature-nav strong,.feature-nav small{display:block}.feature-nav strong{overflow-wrap:anywhere}.feature-nav small{margin-top:4px;color:var(--muted)}.feature-nav em{font-style:normal;white-space:nowrap}.feature-empty{padding:28px;border:1px dashed var(--line);border-radius:18px;background:#fafaf6}.feature-empty strong{font-size:1.2rem}.feature-empty p{margin:8px 0 0;color:var(--muted)}
    .reference-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.reference-card{display:grid;gap:10px;padding:20px;border:1px solid var(--line);border-radius:18px;background:#fafaf6}.reference-card.current{border-color:var(--green);background:var(--green-soft)}.reference-card>span{color:var(--orange);font:850 11px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace}.reference-card h3,.reference-card p{margin:0}.reference-card code{padding:9px;border-radius:8px;background:#f0efea;overflow-wrap:anywhere;white-space:normal}.compatibility-list{display:grid;gap:8px;padding-left:20px}.compatibility-list code{overflow-wrap:anywhere}.capability-detail-stack{display:grid;gap:42px}.capability-detail-group{padding:0!important}.capability-group-head{margin-bottom:16px;padding:22px;border-left:5px solid var(--orange);border-radius:0 16px 16px 0;background:var(--orange-soft)}.capability-group-head span{color:var(--orange);font:850 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.1em}.capability-group-head h3{margin:8px 0 5px;font-size:1.65rem}.capability-group-head p{margin:0;color:var(--muted)}.feature-stack{display:grid;gap:26px}.feature-card{scroll-margin-top:70px;padding:30px;border:1px solid var(--line);border-radius:24px;background:#fff;box-shadow:0 16px 46px rgba(30,44,35,.05)}.feature-card-head{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;padding-bottom:22px;border-bottom:1px solid var(--line)}.feature-card-head h3{margin:8px 0 0;font-size:clamp(1.65rem,3vw,2.35rem)}.feature-index,.answer-label{color:var(--orange);font:850 11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em;text-transform:uppercase}.confidence-badge{padding:7px 10px;border-radius:999px;background:var(--blue-soft);color:var(--blue);font-size:11px;font-weight:850;white-space:nowrap}.confidence-badge.exact{background:var(--green-soft);color:var(--green)}.confidence-badge.unknown{background:#f0efeb;color:var(--muted)}.feature-answer-grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,.8fr);gap:12px;margin-top:12px}.answer-block{padding:22px!important;border:1px solid var(--line);border-radius:16px;background:#fafaf6}.feature-summary{margin:12px 0 0;font-size:1.08rem}.tag-list{display:flex;flex-wrap:wrap;gap:6px;margin-top:16px}.tag-list span{padding:4px 8px;border-radius:999px;background:var(--blue-soft);color:var(--blue);font-size:11px;font-weight:750}.tag-list .unknown-tech{background:#f0efeb;color:var(--muted)}.entrypoint{display:block;max-width:100%;margin:14px 0 8px;color:var(--green);font:800 1.05rem/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:normal;overflow-wrap:anywhere}.answer-block small{display:block;color:var(--muted);overflow-wrap:anywhere}.source-method{margin:14px 0 0;color:var(--muted);font-size:12px}.implementation-block,.source-block{margin-top:12px;padding:22px;border:1px solid var(--line);border-radius:16px}.semantic-warning{margin:12px 0;padding:10px 12px;border-radius:10px;background:var(--orange-soft);color:#8a3b1c;font-weight:700}.feature-steps{position:relative;display:grid;gap:0;margin:20px 0 0;padding:0;list-style:none}.feature-step{display:grid;grid-template-columns:44px minmax(0,1fr);gap:14px;padding-bottom:22px}.feature-step:last-child{padding-bottom:0}.step-number{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;background:var(--green);color:#fff;font:800 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace}.feature-step h4{margin:0 0 5px;font-size:1rem}.feature-step p{margin:0 0 8px;color:var(--muted)}.feature-step code,.source-locations code{display:inline;margin:0 7px 7px 0;padding:5px 8px;border-radius:7px;background:#f0efea;font:700 11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:normal;overflow-wrap:anywhere}.source-contract,.tutorial-contract{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 10px;margin:8px 0}.source-contract dt,.tutorial-contract dt{color:var(--muted);font-size:11px}.source-contract dd,.tutorial-contract dd{margin:0}.feature-step small{display:block;color:var(--muted);font-size:10px}.source-locations{margin-top:16px}.technology-assessment{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;margin-top:14px}.technology-assessment>div{padding:14px;border-radius:12px;background:#fafaf6}.technology-assessment p{margin:9px 0 0;color:var(--muted)}.artifact-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}.artifact-grid>section{padding:15px!important;border-radius:12px;background:#fafaf6}.artifact-grid p{margin:10px 0}.artifact-grid small{display:block;color:var(--muted)}.artifact-grid ul{margin:8px 0;padding-left:20px}.codemap-source{max-height:220px;margin:10px 0;padding:12px;overflow:auto;border-radius:8px;background:#171c19;color:#eaf2ed;font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap}.evidence-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:12px}.evidence-columns details{padding:18px;border:1px solid var(--line);border-radius:16px;background:#fafaf6}.evidence-columns summary{cursor:pointer;font-weight:800;overflow-wrap:anywhere}.evidence-columns summary b{color:var(--green)}.evidence-list{display:grid;gap:8px;margin:14px 0 0;padding:0;list-style:none}.evidence-item,.evidence-missing{padding:10px;border-radius:10px;background:#fff}.evidence-item>div{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.evidence-item code,.evidence-missing code{overflow-wrap:anywhere}.evidence-item pre{max-height:220px;margin:9px 0 0;padding:12px;overflow:auto;border-radius:8px;background:#171c19;color:#eaf2ed;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap}.evidence-kind{color:var(--muted);font-size:10px}.evidence-missing{display:grid;color:var(--muted);font-size:11px}.compact{margin:14px 0 0}.feature-verdict{display:grid;grid-template-columns:120px minmax(0,1fr);gap:16px;margin-top:12px;padding:18px;border-radius:14px;background:var(--green-soft)}.feature-verdict strong{color:var(--green)}.feature-verdict p{margin:0}.back-link{display:inline-block;margin-top:18px;color:var(--green);font-weight:750;text-decoration:none}
    .chapter-question{max-width:860px;margin:14px 0 0;color:var(--green);font:700 clamp(1.05rem,2vw,1.3rem)/1.55 Georgia,"Songti SC",serif}.human-chapter{margin-top:14px;padding:25px!important;border:1px solid var(--line);border-radius:18px;background:#fff}.human-chapter>.answer-label{display:block;margin-bottom:13px}.purpose-chapter{background:#fafaf6}.mechanism-chapter{border-color:#96b9a6;background:linear-gradient(180deg,#edf6f1,#fff)}.chapter-lead{margin:0 0 17px;font-size:1.12rem}.two-column-explanation,.runtime-contract,.object-grid,.choice-grid,.boundary-grid,.reuse-grid,.mechanism-grid{display:grid;gap:10px}.two-column-explanation,.boundary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.runtime-contract,.object-grid,.reuse-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.mechanism-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.mechanism-grid article:last-child{grid-column:1/-1}.choice-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.two-column-explanation article,.runtime-contract article,.object-grid article,.choice-grid article,.boundary-grid article,.reuse-grid article,.mechanism-grid article{padding:15px;border:1px solid var(--line);border-radius:13px;background:#fafaf6}.two-column-explanation p,.runtime-contract p,.object-grid p,.mechanism-grid p{margin:7px 0 0}.runtime-contract b,.object-grid b,.boundary-grid b,.reuse-grid b,.mechanism-grid b,.worked-example>b{color:var(--green)}.worked-example{margin-top:14px;padding:17px;border-left:5px solid var(--green);border-radius:10px;background:#fff}.worked-example .human-list{margin-top:10px}.human-list{display:grid;gap:8px;margin:18px 0 0;padding-left:28px}.human-list li{padding-left:5px}.state-table-wrap{max-width:100%;overflow-x:auto}.state-flow-table{display:table;width:100%;min-width:760px;border-collapse:collapse}.state-flow-table th,.state-flow-table td{padding:13px;border:1px solid var(--line);text-align:left;vertical-align:top}.state-flow-table thead th{background:#18201b;color:#fff}.state-flow-table tbody th{color:var(--orange)}.choice-grid h5{margin:0 0 10px;font-size:1rem}.choice-grid dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:5px 8px;margin:0}.choice-grid dt{color:var(--muted)}.choice-grid dd{margin:0}.supported{border-left:5px solid var(--green)!important}.unsupported{border-left:5px solid var(--orange)!important}.reuse-grid article:nth-child(3){background:var(--orange-soft)}.difficulty-chapter{border-color:#bfd7ca;background:linear-gradient(180deg,#f1f8f4,#fff)}.difficulty-chapter .difficulty-intro{margin-top:0}.evidence-chapter{margin-top:14px;border:1px solid var(--line);border-radius:18px;background:#fafaf6}.evidence-chapter>summary{display:grid;grid-template-columns:190px minmax(0,1fr) auto;gap:12px;align-items:center;padding:22px;cursor:pointer;list-style:none}.evidence-chapter>summary::-webkit-details-marker{display:none}.evidence-chapter>summary em{color:var(--green);font-style:normal;font-weight:800}.evidence-chapter-body{padding:0 22px 22px;border-top:1px solid var(--line)}.evidence-entry{margin-top:16px;padding:16px;border-radius:12px;background:#fff}
    .difficulty-block{margin-top:12px;padding:22px;border:1px solid #bfd7ca;border-radius:18px;background:linear-gradient(180deg,#f1f8f4,#fff)}.difficulty-intro{display:grid;gap:6px;margin:14px 0 18px}.difficulty-intro strong{font-size:1.35rem}.difficulty-intro p,.difficulty-intro small{margin:0;color:var(--muted)}.difficulty-stack{display:grid;gap:10px}.difficulty-card{padding:0!important;border:1px solid var(--line);border-radius:14px;background:#fff}.difficulty-card>summary{display:grid;grid-template-columns:150px minmax(0,1fr) auto;gap:14px;align-items:center;padding:17px;cursor:pointer;list-style:none}.difficulty-card>summary::-webkit-details-marker{display:none}.difficulty-card>summary span{color:var(--orange);font:800 10px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;text-transform:uppercase}.difficulty-card>summary strong{font-size:1.05rem}.difficulty-card>summary em{padding:5px 8px;border-radius:999px;background:var(--green-soft);color:var(--green);font-size:10px;font-style:normal;font-weight:800}.difficulty-body{padding:0 17px 18px;border-top:1px solid var(--line)}.difficulty-lead{padding:17px 0 8px!important}.difficulty-lead p{margin:7px 0 0;font-size:1.05rem}.difficulty-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.difficulty-grid>section{padding:14px!important;border-radius:12px;background:#fafaf6}.difficulty-grid b,.difficulty-footer b{color:var(--green)}.difficulty-grid p,.difficulty-grid ol{margin:8px 0 0}.difficulty-grid ol{padding-left:19px}.difficulty-footer{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px;padding:14px;border-radius:12px;background:var(--orange-soft)}.difficulty-footer p{margin:7px 0 0}.difficulty-footer .source-link{display:block}.difficulty-unknowns{margin-top:12px;padding:14px;border-left:4px solid var(--orange);background:#fff}.difficulty-unknowns ol{margin:8px 0 0;padding-left:20px}.technology-dimensions,.signal-checks,.codemap-nodes,.codemap-edges{display:grid;gap:7px;padding:0!important;list-style:none}.technology-dimensions .technology-claim{display:grid;gap:5px;padding:8px 0;border-bottom:1px solid var(--line)}.technology-claim>div{display:flex;justify-content:space-between;gap:12px}.technology-claim span,.technology-claim code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.technology-claim small,.technology-claim .source-link{display:block}.technology-claim p{margin:0}.tutorial-chapter{padding:10px 0!important;border-bottom:1px solid var(--line)}.tutorial-chapter:last-of-type{border-bottom:0}.tutorial-chapter h4{margin:0}.tutorial-chapter li{display:grid;gap:3px;margin:8px 0}.tutorial-chapter code{white-space:normal;overflow-wrap:anywhere}.reuse-boundary{display:grid;gap:4px}.codemap-graph{display:grid;gap:12px}.codemap-nodes li{display:grid;grid-template-columns:28px minmax(0,1fr);gap:8px}.codemap-nodes b{color:var(--orange)}.codemap-edges li{display:grid;grid-template-columns:minmax(0,1fr) 24px minmax(0,1fr);gap:6px;align-items:center;padding:8px;border-radius:9px;background:#fff}.codemap-edges b{text-align:center;color:var(--green)}.codemap-edges small{grid-column:1/-1}.signal-checks li{display:flex;gap:7px}.codemap-source{display:none}.decision-summary{display:grid;grid-template-columns:.3fr minmax(0,1fr);gap:28px;margin-top:58px;padding:28px!important;border-radius:20px;background:#18201b;color:#fff}.decision-summary .kicker{color:#82d4b3}.decision-summary h2{font-size:clamp(1.5rem,3vw,2.35rem)}.decision-summary p{margin:12px 0 0;color:#c9d2cc}.deep-dive-wrap{padding-top:58px}.deep-dive{border-top:1px solid var(--line)}.deep-dive>summary{display:flex;justify-content:space-between;gap:20px;padding:26px 0;cursor:pointer;font-size:1.25rem;font-weight:850;list-style:none}.deep-dive>summary::-webkit-details-marker{display:none}.deep-dive>summary span{color:var(--muted);font-size:13px;font-weight:500}.deep-dive>summary:after{content:"+";color:var(--orange);font-size:1.5rem}.deep-dive[open]>summary:after{content:"−"}.drill-content{padding-bottom:10px}.drill-content>section:first-child{padding-top:28px}
    .metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.metric{padding:20px;border:1px solid var(--line);border-radius:18px}.metric b{display:block;font-size:clamp(1.6rem,3vw,2.4rem);line-height:1.1}.metric span{color:var(--muted);font-size:12px}.overview{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.panel{padding:24px;border:1px solid var(--line);border-radius:20px}.panel h3{margin:0 0 18px;font-size:1.2rem}.confidence-note{background:var(--green-soft)}.confidence-note p{margin:8px 0;color:var(--muted)}.confidence-note strong{color:var(--green)}
    .language-row{display:grid;grid-template-columns:120px 1fr 34px;align-items:center;gap:10px;margin:10px 0}.language-row span{overflow:hidden;text-overflow:ellipsis}.language-row i{height:8px;border-radius:999px;background:#edf0ec;overflow:hidden}.language-row i b{display:block;height:100%;border-radius:inherit;background:var(--green)}.language-row strong{text-align:right;font:700 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace}
    .reading-list{display:grid;gap:10px}.reading-step{display:grid;grid-template-columns:48px 1fr auto;gap:16px;align-items:start;padding:19px;border:1px solid var(--line);border-radius:16px}.reading-step>b{color:var(--orange);font:850 12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.reading-step span{font-size:12px;color:var(--green);font-weight:800}.reading-step h3{margin:4px 0 5px;font-size:1.08rem;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}.reading-step p{margin:0;color:var(--muted)}.reading-step em{padding:4px 7px;border-radius:99px;background:var(--blue-soft);color:var(--blue);font-size:10px;font-style:normal}
    .module-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.module-card{padding:22px;border:1px solid var(--line);border-radius:18px}.module-card>span{color:var(--green);font:750 11px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace}.module-card h3{margin:16px 0 8px;font-size:1.35rem}.module-card p{margin:0;color:var(--muted)}.module-card small{display:block;margin-top:16px;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);overflow-wrap:anywhere}
    .explorer{border:1px solid var(--line);border-radius:20px;overflow:hidden}.toolbar{display:flex;flex-wrap:wrap;gap:8px;padding:14px;border-bottom:1px solid var(--line);background:#f5f6f1}.toolbar button,.toolbar input,.toolbar select{min-height:40px;border:1px solid var(--line);border-radius:10px;background:var(--paper);color:var(--ink);font:inherit}.toolbar button{padding:0 13px;cursor:pointer;font-weight:750}.toolbar button.active{border-color:var(--green);background:var(--green-soft);color:var(--green)}.toolbar input{min-width:220px;flex:1;padding:0 13px}.toolbar select{padding:0 12px}.result-meta{display:flex;justify-content:space-between;gap:12px;padding:13px 18px;color:var(--muted);font-size:12px;border-bottom:1px solid var(--line)}.rows{display:grid}.row{display:grid;grid-template-columns:1.15fr .85fr .5fr;gap:18px;padding:16px 18px;border-bottom:1px solid var(--line);align-items:start}.row:last-child{border-bottom:0}.row strong,.row code{overflow-wrap:anywhere}.row code{font:700 12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.row p{margin:4px 0 0;color:var(--muted);font-size:12px}.pill{display:inline-flex;padding:4px 7px;border-radius:999px;background:var(--blue-soft);color:var(--blue);font-size:10px;font-weight:800}.pill.exact{background:var(--green-soft);color:var(--green)}.empty{padding:48px 20px;text-align:center;color:var(--muted)}.muted{color:var(--muted)}footer{margin-top:64px;padding-top:22px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
    @media(max-width:900px){header,main{padding-left:20px;padding-right:20px}.hero,.section-head,.overview,.decision-summary{grid-template-columns:1fr}.human-capability-grid,.quick-grid{grid-template-columns:1fr 1fr}.feature-directory,.feature-answer-grid,.evidence-columns,.technology-assessment,.artifact-grid,.reference-grid,.runtime-contract,.object-grid,.reuse-grid,.choice-grid{grid-template-columns:1fr 1fr}.metrics{grid-template-columns:repeat(3,1fr)}.module-grid{grid-template-columns:1fr 1fr}.row{grid-template-columns:1fr}.identity{align-self:auto}}
    @media(max-width:560px){header,main{padding-left:14px;padding-right:14px}header{align-items:flex-start}.snapshot{max-width:140px;text-align:right}.hero{padding-top:40px}.human-capability-grid{grid-template-columns:1fr}.human-capability{min-height:0}.quick-grid{grid-template-columns:1fr 1fr}.feature-nav{grid-template-columns:30px minmax(0,1fr)}.feature-nav em{grid-column:2;justify-self:start}.feature-card{padding:16px}.feature-card-head{display:grid}.implementation-block,.source-block,.answer-block,.human-chapter{padding:15px!important}.feature-verdict{grid-template-columns:1fr}.metrics{grid-template-columns:1fr 1fr}.module-grid{grid-template-columns:1fr}.reading-step{grid-template-columns:36px minmax(0,1fr)}.reading-step em{grid-column:2}.toolbar button{flex:1}.toolbar input{flex-basis:100%;min-width:0}.row{gap:8px}.source-contract,.tutorial-contract{grid-template-columns:1fr}.two-column-explanation,.runtime-contract,.object-grid,.choice-grid,.boundary-grid,.reuse-grid,.mechanism-grid{grid-template-columns:1fr}.mechanism-grid article:last-child{grid-column:auto}.codemap-edges li{grid-template-columns:minmax(0,1fr) 18px minmax(0,1fr)}.evidence-chapter>summary{grid-template-columns:1fr}.evidence-chapter>summary em{justify-self:start}.decision-table-wrap{overflow:visible;border:0}.decision-table,.decision-table tbody,.decision-table tr,.decision-table th,.decision-table td{display:block;width:100%;min-width:0}.decision-table thead{display:none}.decision-table tr{margin-bottom:14px;padding:15px;border:1px solid var(--line);border-radius:16px;background:#fff}.decision-table th,.decision-table td{padding:7px 0;border:0;overflow-wrap:anywhere}.decision-table td:before{content:attr(data-label);display:block;margin-bottom:2px;color:var(--orange);font-size:10px;font-weight:850;letter-spacing:.06em}}
    .source-link{display:inline;max-width:100%;margin:0 7px 7px 0;color:var(--green);text-decoration:none;white-space:normal;overflow-wrap:anywhere}.source-link:hover{text-decoration:underline}
    .project-overview{padding:54px 0 18px}.project-overview>.section-head{margin-bottom:22px}.project-definition{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;overflow:hidden;border:1px solid var(--line);border-radius:20px;background:var(--line)}.project-definition article{display:grid;gap:9px;padding:24px;background:#fff}.project-definition span,.architecture-summary span,.runtime-component-grid header span{color:var(--orange);font:850 10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em;text-transform:uppercase}.project-definition strong{font:750 1.12rem/1.55 Georgia,"Songti SC",serif}.architecture-head{margin-top:52px}.project-journey{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1px;margin:0;padding:1px;list-style:none;border-radius:20px;background:var(--green);overflow:hidden}.project-journey li{display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;padding:22px;background:#fff}.project-journey>li>b{color:var(--orange);font:850 11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.project-journey span{color:var(--green);font-size:11px;font-weight:850}.project-journey h4{margin:6px 0 10px;font-size:1rem}.project-journey p,.project-journey small{margin:0;color:var(--muted)}.architecture-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px;min-width:0}.architecture-summary article{min-width:0;padding:22px;border:1px solid var(--line);border-radius:17px;background:#fafaf6;overflow-wrap:anywhere}.architecture-summary article:first-child{grid-column:span 2;background:var(--green-soft)}.architecture-summary h3{max-width:100%;margin:10px 0 8px;font:750 1.25rem/1.35 Georgia,"Songti SC",serif;overflow-wrap:anywhere}.architecture-summary p{margin:8px 0 0;color:var(--muted);overflow-wrap:anywhere}.runtime-component-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.runtime-component-grid article{padding:22px;border:1px solid var(--line);border-radius:18px}.runtime-component-grid h4{margin:8px 0 12px;font-size:1.2rem}.runtime-component-grid p{color:var(--muted)}.runtime-component-grid dl{display:grid;grid-template-columns:92px minmax(0,1fr);gap:8px 12px}.runtime-component-grid dt{color:var(--green);font-size:12px;font-weight:800}.runtime-component-grid dd{margin:0}.code-organization-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:18px}.code-organization{width:100%;min-width:780px;border-collapse:collapse;background:#fff}.code-organization th,.code-organization td{padding:16px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}.code-organization th{width:20%}.code-organization th code,.code-organization th small{display:block;overflow-wrap:anywhere}.code-organization th small{margin-top:6px;color:var(--orange)}.overview-boundary{display:grid;grid-template-columns:.8fr 1.2fr;gap:12px;margin-top:14px}.overview-boundary>div,.overview-boundary details{padding:20px;border:1px solid var(--line);border-radius:17px;background:#fafaf6}.overview-boundary ul,.overview-boundary ol{margin-bottom:0;padding-left:20px}.overview-boundary details summary{cursor:pointer;color:var(--green);font-weight:850}.overview-boundary details li{margin:10px 0}.overview-boundary details li span{display:block;margin-top:4px;color:var(--muted)}
    .product-axis-head{display:block}.product-axis-grid{display:grid;grid-template-columns:1fr;gap:14px}.product-axis-grid>article{display:grid;gap:15px;padding:26px;border:1px solid var(--line);border-radius:20px;background:var(--green-soft)}.product-axis-grid header{position:static;display:grid;gap:7px;padding:0;border:0;background:transparent;backdrop-filter:none}.product-axis-grid header span,.product-capability-group>header>span{color:var(--orange);font:850 10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em;text-transform:uppercase}.product-axis-grid header b{font:750 1.45rem/1.35 Georgia,"Songti SC",serif}.product-axis-grid h3,.product-axis-grid p{margin:0}.product-axis-grid h3{max-width:920px;font-size:1.08rem}.axis-interaction{padding:18px;border:1px solid rgba(11,107,76,.2);border-radius:16px;background:#fff}.axis-interaction>b{display:block;margin-bottom:13px;color:var(--green);font-size:.82rem}.axis-interaction ol{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:28px;margin:0;padding:0;list-style:none}.axis-interaction li{position:relative;min-width:0;padding:14px;border:1px solid var(--line);border-radius:12px;background:#fafaf6}.axis-interaction li:not(:last-child):after{position:absolute;right:-22px;top:50%;content:"→";color:var(--orange);font-weight:900;transform:translateY(-50%)}.axis-interaction li span{color:var(--orange);font:850 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace}.axis-interaction li p{margin-top:7px;overflow-wrap:anywhere}.axis-outcome{padding-top:12px;border-top:1px solid rgba(11,107,76,.18)}.product-axis-grid footer{display:flex;justify-content:space-between;gap:12px;align-items:center;margin:0;padding-top:13px;border-top:1px solid rgba(11,107,76,.18);color:var(--muted)}.supporting-count{margin:14px 0 0;color:var(--muted)}.product-capability-group{margin:26px 0 0;padding:0}.product-capability-group>header{position:static;display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 20px;margin-bottom:13px;padding:20px 22px;border:1px solid var(--line);border-left:6px solid var(--green);border-radius:0 17px 17px 0;background:var(--green-soft);backdrop-filter:none}.product-capability-group>header>span{grid-row:1/4}.product-capability-group>header h3,.product-capability-group>header p{margin:0}.product-capability-group>header h3{font-size:1.5rem}.product-capability-group>header p{color:var(--muted)}.product-capability-group>header strong{font-size:.9rem}.supporting-capabilities{margin-top:26px;border:1px solid var(--line);border-radius:18px;background:#fafaf6}.supporting-capabilities>summary{display:grid;grid-template-columns:max-content minmax(0,1fr) auto;gap:12px;align-items:center;padding:20px 22px;cursor:pointer;list-style:none}.supporting-capabilities>summary::-webkit-details-marker{display:none}.supporting-capabilities>summary span{color:var(--orange);font:850 10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em}.supporting-capabilities>summary small{color:var(--muted)}.supporting-capabilities>.human-capability-grid{padding:0 18px 18px}.engineering-structure{display:grid;grid-template-columns:.65fr 1.35fr;gap:12px}.engineering-verdict,.engineering-table-wrap{min-width:0;border:1px solid var(--line);border-radius:18px;background:#fff}.engineering-verdict{display:grid;align-content:start;gap:8px;padding:24px;background:var(--green-soft)}.engineering-verdict>span{color:var(--orange);font:850 10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em;text-transform:uppercase}.engineering-verdict strong{margin-bottom:12px;font:750 1.2rem/1.4 Georgia,"Songti SC",serif}.engineering-verdict p{color:var(--muted)}.engineering-table-wrap{overflow-x:auto}.engineering-layer-table{width:100%;min-width:720px;border-collapse:collapse}.engineering-layer-table th,.engineering-layer-table td{padding:16px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.engineering-layer-table thead th{background:#18201b;color:#fff;font-size:.78rem}.engineering-layer-table tbody th{width:18%;color:var(--green)}.engineering-layer-table td:nth-child(2){width:46%}.engineering-layer-table tr:last-child th,.engineering-layer-table tr:last-child td{border-bottom:0}
    .secondary-capabilities{margin-top:28px;padding:22px!important;border:1px solid var(--line);border-radius:20px;background:#fafaf6}.secondary-capabilities>header{position:static;display:grid;grid-template-columns:max-content minmax(0,1fr) auto;gap:10px 16px;margin:0 0 16px;padding:0;border:0;background:transparent;backdrop-filter:none}.secondary-capabilities>header span{color:var(--orange);font:850 10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em}.secondary-capabilities>header small{color:var(--muted)}
    .mechanism-verdict{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:14px;align-items:start;margin-bottom:18px;padding:18px;border-left:6px solid var(--orange);border-radius:0 14px 14px 0;background:#fff}.mechanism-verdict span{color:var(--orange);font:850 11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em}.mechanism-verdict strong{font-size:1.18rem;line-height:1.65}
    .feature-thesis{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:11px 16px;align-items:start;margin:18px 0 0;padding:18px 20px;border-left:5px solid var(--orange);border-radius:0 14px 14px 0;background:var(--orange-soft)}.feature-thesis span{padding-top:4px;color:var(--orange);font:850 10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em}.feature-thesis strong{font:750 1.2rem/1.58 Georgia,"Songti SC",serif}.chapter-question{margin:13px 0 0;color:var(--muted)}.human-glance{margin-top:18px;padding:24px!important;border-radius:20px;background:#18201b;color:#fff}.human-glance>.answer-label{color:#ff9a70}.glance-grid{display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:1px;margin-top:16px;overflow:hidden;border-radius:14px;background:#3b443f}.glance-grid article{display:grid;align-content:start;gap:9px;padding:20px;background:#202923}.glance-grid article b{color:#8bd5b4;font-size:.78rem}.glance-grid article strong{font:700 1.18rem/1.55 Georgia,"Songti SC",serif}.glance-grid article p,.glance-grid article small{margin:0;color:#d5ddd8}.human-run{margin-top:14px;padding:22px!important;border:1px solid var(--line);border-radius:18px;background:#fafaf6}.human-run>.answer-label{display:block;margin-bottom:12px}.interaction-diagram{overflow:hidden;border:1px solid var(--line);border-radius:16px;background:#fff}.interaction-diagram-head{display:flex;justify-content:space-between;gap:16px;padding:15px 17px;background:#18201b;color:#fff}.interaction-diagram-head b{color:#8bd5b4}.interaction-diagram-head span{color:#d5ddd8;font-size:.8rem}.interaction-roles{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:0!important;margin:0!important;padding:0!important;list-style:none!important;counter-reset:none!important}.interaction-roles li{display:grid;grid-template-columns:28px minmax(0,1fr);gap:9px;padding:16px!important;border:0!important;border-right:1px solid var(--line)!important}.interaction-roles li:last-child{border-right:0!important}.interaction-roles li:before{content:none!important}.interaction-roles li span{color:var(--orange);font:850 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace}.interaction-roles li b{color:var(--green)}.interaction-roles li p{margin:5px 0 0}.interaction-detail{padding:17px;border-top:1px solid var(--line);background:#fafaf6}.interaction-detail>b{color:var(--green)}.interaction-detail ol{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:1px;margin:13px 0 0;padding:1px;list-style:none;background:var(--line)}.interaction-detail li{display:grid;grid-template-columns:28px minmax(0,1fr);gap:8px;padding:13px;background:#fff}.interaction-detail li span{color:var(--orange);font:850 10px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.interaction-detail li p{margin:0}.interaction-explanation{margin-top:12px;padding:18px;border-left:5px solid var(--green);border-radius:0 14px 14px 0;background:#fff}.interaction-explanation>b{color:var(--green)}.interaction-explanation>p{margin:8px 0 14px}.interaction-explanation dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:7px 14px;margin:0}.interaction-explanation dt{color:var(--orange);font-weight:800}.interaction-explanation dd{margin:0}.visible-example{margin-top:12px;padding:18px;border-radius:14px;background:var(--orange-soft)}.visible-example>b{color:var(--green)}.visible-example .human-list{grid-template-columns:repeat(3,minmax(0,1fr));gap:0;margin-top:10px;padding:0;counter-reset:example-step;list-style:none}.visible-example .human-list li{position:relative;padding:13px 14px 13px 42px;border-top:1px solid rgba(221,84,43,.2);counter-increment:example-step}.visible-example .human-list li:before{position:absolute;left:10px;content:counter(example-step,decimal-leading-zero);color:var(--orange);font:850 11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.human-deep-dive{margin-top:12px;border:1px solid var(--line);border-radius:18px;background:#fff;overflow:hidden}.human-deep-dive>summary{display:grid;grid-template-columns:42px minmax(0,1fr) 24px;gap:15px;align-items:center;padding:20px 22px;cursor:pointer;list-style:none}.human-deep-dive>summary::-webkit-details-marker{display:none}.human-deep-dive>summary>span{color:var(--orange);font:850 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace}.human-deep-dive>summary b,.human-deep-dive>summary small{display:block}.human-deep-dive>summary b{font-size:1.12rem}.human-deep-dive>summary small{margin-top:5px;color:var(--muted)}.human-deep-dive>summary:after{content:"+";color:var(--green);font-size:1.4rem}.human-deep-dive[open]>summary:after{content:"−"}.human-deep-dive[open]>summary{background:#fafaf6}.human-deep-body{padding:22px;border-top:1px solid var(--line)}.human-deep-body>h4{margin:26px 0 13px;font-size:1.15rem}.human-deep-body>h4:first-child{margin-top:0}.human-recap{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:8px 16px;align-items:baseline;margin-top:14px;padding:18px 20px;border-radius:16px;background:var(--green-soft)}.human-recap>span{grid-row:1/3;color:var(--green);font:850 10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em}.human-recap strong{font:750 1rem/1.55 Georgia,"Songti SC",serif}.human-recap p{margin:0;color:var(--muted);font-size:.88rem}.human-recap p b{color:var(--ink)}
    .interaction-flow{display:grid;grid-template-columns:minmax(0,1fr) 52px minmax(0,1fr) 52px minmax(0,1fr) 52px minmax(0,1fr);align-items:stretch;padding:18px}.interaction-node{display:grid;grid-template-columns:28px minmax(0,1fr);gap:9px;padding:16px;border:1px solid var(--line);border-radius:14px;background:#fff}.interaction-node>span,.activity-node>span{color:var(--orange);font:850 10px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.interaction-node b{color:var(--green)}.interaction-node p,.activity-node p{margin:5px 0 0}.interaction-arrow{align-self:center;width:52px;height:24px;overflow:visible}.interaction-arrow path,.activity-connector path{fill:none;stroke:var(--orange);stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}.activity-flow{display:grid;justify-items:center;margin-top:14px}.activity-terminal{display:grid;place-items:center;min-width:86px;padding:7px 16px;border-radius:999px;background:#18201b;color:#fff;font:850 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.12em}.activity-terminal.end{background:var(--green)}.activity-node{display:grid;grid-template-columns:32px minmax(0,1fr);gap:10px;width:min(760px,100%);padding:16px 18px;border:1px solid var(--line);border-left:5px solid var(--green);border-radius:12px;background:#fff}.activity-connector{width:24px;height:42px;overflow:visible}
    .difficulty-card>summary div{display:grid;gap:5px}.difficulty-card>summary small{display:block;color:var(--muted);font-weight:500;line-height:1.5}.difficulty-sequence{display:grid;gap:0}.difficulty-sequence>section{display:grid;grid-template-columns:minmax(150px,.28fr) minmax(0,1fr);gap:20px;padding:18px 0!important;border-bottom:1px solid var(--line)}.difficulty-sequence>section:last-child{border-bottom:0}.difficulty-sequence b,.difficulty-footer b{color:var(--green)}.difficulty-sequence p,.difficulty-sequence ol{margin:0}.difficulty-sequence ol{padding-left:20px}.difficulty-proof{margin-top:8px;padding:14px;border-radius:12px;background:var(--orange-soft)}.difficulty-proof>summary{cursor:pointer;color:var(--green);font-weight:800}.difficulty-proof>ol{margin-bottom:0}.difficulty-footer{margin-top:14px}
    @media(max-width:560px){.mechanism-verdict{grid-template-columns:1fr;gap:5px;padding:14px}.mechanism-verdict strong{font-size:1.05rem}}
    @media(max-width:900px){.glance-grid{grid-template-columns:1fr}.interaction-roles{grid-template-columns:1fr 1fr!important}.interaction-roles li:nth-child(2){border-right:0!important}.interaction-roles li{border-bottom:1px solid var(--line)!important}.visible-example .human-list{grid-template-columns:1fr 1fr}.runtime-component-grid,.architecture-summary,.overview-boundary{grid-template-columns:1fr}.architecture-summary article:first-child{grid-column:auto}}
    @media(max-width:900px){.interaction-flow{grid-template-columns:1fr;justify-items:center}.interaction-node{width:100%}.interaction-arrow{transform:rotate(90deg);margin:8px 0}.secondary-capabilities>header{grid-template-columns:1fr}}
    @media(max-width:900px){.engineering-structure{grid-template-columns:1fr}}
    @media(max-width:560px){.product-axis-grid{grid-template-columns:1fr}.axis-interaction ol{grid-template-columns:1fr;gap:10px}.axis-interaction li:not(:last-child):after{right:auto;top:auto;left:50%;bottom:-15px;transform:translateX(-50%) rotate(90deg)}.product-capability-group>header{grid-template-columns:1fr}.product-capability-group>header>span{grid-row:auto}.supporting-capabilities>summary{grid-template-columns:1fr}.engineering-table-wrap{overflow:visible}.engineering-layer-table,.engineering-layer-table tbody,.engineering-layer-table tr,.engineering-layer-table th,.engineering-layer-table td{display:block;width:100%;min-width:0}.engineering-layer-table thead{display:none}.engineering-layer-table tr{padding:13px;border-bottom:1px solid var(--line)}.engineering-layer-table th,.engineering-layer-table td{padding:5px 0;border:0}.engineering-layer-table td:last-child{color:var(--muted)}}
    @media(max-width:560px){.feature-thesis,.human-recap{grid-template-columns:1fr;padding:15px}.human-recap>span{grid-row:auto}.human-glance,.human-run,.human-deep-body{padding:16px!important}.interaction-diagram-head{display:grid}.interaction-roles{grid-template-columns:1fr!important}.interaction-roles li{border-right:0!important}.interaction-explanation dl{grid-template-columns:1fr;gap:3px}.interaction-explanation dd{margin-bottom:8px}.visible-example .human-list{grid-template-columns:1fr}.human-deep-dive>summary{grid-template-columns:30px minmax(0,1fr) 20px;padding:17px 15px}.difficulty-card>summary{grid-template-columns:1fr auto}.difficulty-card>summary>span{grid-column:1/-1}.difficulty-sequence>section{grid-template-columns:1fr;gap:8px}.difficulty-footer{grid-template-columns:1fr}.project-definition{grid-template-columns:1fr}.project-overview{padding-top:34px}.project-journey{grid-template-columns:1fr}.code-organization,.code-organization tbody,.code-organization tr,.code-organization th,.code-organization td{display:block;width:100%;min-width:0}.code-organization thead{display:none}.code-organization tr{padding:14px;border-bottom:1px solid var(--line)}.code-organization th,.code-organization td{padding:6px 0;border:0}}
  </style>
</head>
<body><div class="shell">
  <header><span class="brand">REPO / TEACHER</span><span class="snapshot">__SNAPSHOT____DIRTY__</span></header>
  <main>
    <section class="hero">
      <div><p class="eyebrow">Feature-first repository guide · schema __SCHEMA__</p><h1>__PROJECT__</h1><p class="lead">__POSITIONING__</p></div>
      <aside class="identity"><dl><dt>项目目录</dt><dd>__DIRECTORY__</dd><dt>分支</dt><dd>__BRANCH__</dd><dt>许可证</dt><dd>__LICENSE__</dd><dt>生成时间</dt><dd>__ANALYZED__</dd></dl><details class="identity-more"><summary>查看完整路径</summary><code>__FULL_PATH__</code></details></aside>
    </section>
    __PRIMARY_OVERVIEW__
    <section id="feature-index"><div class="section-head"><span class="kicker">30 秒重点</span><h2>__FEATURE_HEADLINE__</h2></div>
      __QUICK_GRID__
      <p class="action-line">__ACTION_LINE__</p>__FEATURE_DIRECTORY__
    </section>
    __REFERENCE_POSITION__
    __FEATURE_DETAILS__
    <section class="decision-summary"><span class="kicker">最后结论</span><div><h2>__CONFIDENCE_SUMMARY__</h2><p>__RECOMMENDATION__</p></div></section>
    <section class="deep-dive-wrap"><details class="deep-dive"><summary>继续下钻：规模、阅读路线、模块与原始证据 <span>只在核验功能结论时展开</span></summary><div class="drill-content">
    <section><div class="section-head"><span class="kicker">仓库规模</span><h2>用于评估阅读成本，不代表功能价值。</h2></div>
      <div class="metrics"><div class="metric"><b>__FILES__</b><span>文件</span></div><div class="metric"><b>__SYMBOLS__</b><span>符号</span></div><div class="metric"><b>__RELATIONSHIPS__</b><span>关系</span></div><div class="metric"><b>__MODULES__</b><span>模块</span></div><div class="metric"><b>__LINES__</b><span>代码 / 文档行</span></div><div class="metric"><b>__BYTES__</b><span>已索引文本</span></div></div>
      <div class="overview"><article class="panel"><h3>语言分布</h3>__LANGUAGES__</article><article class="panel confidence-note"><h3>如何理解准确度</h3><p><strong>exact</strong>：Git、文件和 Python AST 等确定性事实。</p><p><strong>heuristic</strong>：JS/TS 声明、调用解析与阅读优先级，需要结合源码继续核对。</p><p>诊断 __DIAGNOSTICS__ 项 · 跳过 __SKIPPED__ 项。</p></article></div>
    </section>
    <section><div class="section-head"><span class="kicker">建议阅读顺序</span><h2>先沿一条小路线进入项目。</h2></div><div class="reading-list">__READING_PATH__</div></section>
    <section><div class="section-head"><span class="kicker">模块地图</span><h2>从主要目录进入，而不是一次看完整文件树。</h2></div><div class="module-grid">__MODULES_HTML__</div></section>
    <section><div class="section-head"><span class="kicker">证据浏览器</span><h2>搜索文件、符号、关系和诊断。</h2></div>
      <div class="explorer"><div class="toolbar"><button class="active" data-view="files">文件</button><button data-view="symbols">符号</button><button data-view="relationships">关系</button><button data-view="diagnostics">诊断</button><input id="search" type="search" placeholder="搜索路径、符号或目标…"><select id="language"><option value="">全部语言</option></select></div><div class="result-meta"><span id="result-count">0 项</span><span>点击搜索结果前请核对 confidence</span></div><div id="rows" class="rows"></div></div>
    </section>
    </div></details></section>
    <footer>Repository Teacher · 功能结论固定到生成时的仓库状态；静态阅读顺序不等于运行时流，证据完整度不等于测试覆盖率。</footer>
  </main>
</div>
<script id="repo-data" type="application/json">__DATA__</script>
<script>
(() => {
  const data = JSON.parse(document.getElementById('repo-data').textContent);
  const rows = document.getElementById('rows');
  const count = document.getElementById('result-count');
  const search = document.getElementById('search');
  const language = document.getElementById('language');
  const buttons = [...document.querySelectorAll('[data-view]')];
  let view = 'files';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const confidence = value => `<span class="pill ${value === 'exact' ? 'exact' : ''}">${esc(value || 'n/a')}</span>`;
  const collection = name => Array.isArray(data[name]) ? data[name] : [];
  const sourceName = id => collection('symbols').find(item => item.id === id)?.qualified_name || collection('files').find(item => item.id === id)?.path || id;
  const renderers = {
    files: item => `<article class="row"><div><strong>${esc(item.path)}</strong><p>${esc(item.module)} · ${Number(item.lines || 0)} lines · ${Number(item.size || 0)} bytes</p></div><code>${esc(item.language)}</code><div><span class="pill exact">exact</span> ${Array.isArray(item.symbols) ? item.symbols.length : 0} symbols</div></article>`,
    symbols: item => `<article class="row"><div><strong>${esc(item.qualified_name)}</strong><p>${esc(item.path)}:${item.line}-${item.end_line}</p></div><code>${esc(item.kind)} ${esc(item.signature || '')}</code><div>${confidence(item.confidence)}<p>${esc(item.analyzer)}</p></div></article>`,
    relationships: item => `<article class="row"><div><strong>${esc(sourceName(item.source_id))}</strong><p>${esc(item.path)}:${item.line}</p></div><code>${esc(item.kind)} → ${esc(item.target_name)}</code><div>${confidence(item.confidence)}<p>${item.target_id ? 'resolved' : 'unresolved'}</p></div></article>`,
    diagnostics: item => `<article class="row"><div><strong>${esc(item.code)}</strong><p>${esc(item.path)}${item.line ? ':' + item.line : ''}</p></div><code>${esc(item.message)}</code><div><span class="pill">${esc(item.severity)}</span></div></article>`
  };
  const haystack = item => Object.values(item).filter(value => typeof value !== 'object').join(' ').toLowerCase();
  function render() {
    const query = search.value.trim().toLowerCase();
    const selectedLanguage = language.value;
    const allItems = collection(view);
    const items = allItems.filter(item => (!query || haystack(item).includes(query)) && (view !== 'files' || !selectedLanguage || item.language === selectedLanguage));
    count.textContent = `${items.length} / ${allItems.length} 项`;
    rows.innerHTML = items.length ? items.slice(0, 500).map(renderers[view]).join('') : '<div class="empty">没有匹配结果。</div>';
  }
  Object.keys(data.stats?.languages || {}).forEach(name => { const option = document.createElement('option'); option.value = name; option.textContent = name; language.append(option); });
  buttons.forEach(button => button.addEventListener('click', () => { view = button.dataset.view; buttons.forEach(item => item.classList.toggle('active', item === button)); language.hidden = view !== 'files'; render(); }));
  search.addEventListener('input', render); language.addEventListener('change', render); render();
})();
</script>
</body></html>'''
    replacements = {
        "__TITLE__": project_name,
        "__PROJECT__": project_name,
        "__SNAPSHOT__": html.escape(snapshot_label),
        "__DIRTY__": html.escape(dirty_label),
        "__SCHEMA__": html.escape(str(index.get("schema_version", "unknown"))),
        "__DIRECTORY__": html.escape(str(project_directory)),
        "__FULL_PATH__": html.escape(project_path),
        "__BRANCH__": html.escape(str(branch)),
        "__LICENSE__": html.escape(str(license_label)),
        "__ANALYZED__": html.escape(str(project.get("analyzed_at") or "unknown")),
        "__POSITIONING__": html.escape(positioning),
        "__PRIMARY_OVERVIEW__": (
            _render_project_overview(project_overview, project_path)
            + _render_human_decision_guide(
                features,
                tutorials,
                str(project_directory),
                project_path,
                project_overview,
            )
        ),
        "__FEATURE_HEADLINE__": html.escape(feature_headline),
        "__FEATURE_COUNT__": f"{len(features):,}",
        "__CAPABILITY_COUNT__": f"{len(capabilities):,}",
        "__BOUNDARY_COUNT__": f"{len(boundaries):,}",
        "__CANDIDATE_COUNT__": f"{len(candidates):,}",
        "__EVIDENCE_COUNT__": f"{len(evidence):,}",
        "__QUICK_GRID__": _render_quick_grid(
            capabilities=len(capabilities),
            boundaries=len(boundaries),
            candidates=len(candidates),
            evidence=len(evidence),
            waku_features=waku_features,
        ),
        "__ACTION_LINE__": html.escape(action_line),
        "__FEATURE_DIRECTORY__": _render_feature_directory(
            display_features,
            modules_by_id,
            tutorial_mode=is_human_report or bool(waku_features),
        ),
        "__REFERENCE_POSITION__": _render_reference_position(
            str(project_directory), features
        ),
        "__FEATURE_DETAILS__": feature_details,
        "__CONFIDENCE_SUMMARY__": html.escape(confidence_summary),
        "__RECOMMENDATION__": html.escape(recommendation),
        "__FILES__": f'{_as_int(stats.get("files")):,}',
        "__SYMBOLS__": f'{_as_int(stats.get("symbols")):,}',
        "__RELATIONSHIPS__": f'{_as_int(stats.get("relationships")):,}',
        "__MODULES__": f'{_as_int(stats.get("modules")):,}',
        "__LINES__": f'{_as_int(stats.get("lines")):,}',
        "__BYTES__": _human_bytes(_as_int(stats.get("bytes"))),
        "__DIAGNOSTICS__": str(_as_int(stats.get("diagnostics"))),
        "__SKIPPED__": str(
            sum(_as_int(value) for value in stats.get("skipped", {}).values())
            if isinstance(stats.get("skipped", {}), dict) else 0
        ),
        "__LANGUAGES__": _render_languages(stats.get("languages", {}) if isinstance(stats.get("languages", {}), dict) else {}),
        "__READING_PATH__": _render_reading_path(
            [item for item in index.get("reading_path", []) if isinstance(item, dict)]
            if isinstance(index.get("reading_path", []), list) else []
        ),
        "__MODULES_HTML__": _render_modules(
            [item for item in index.get("modules", []) if isinstance(item, dict)]
            if isinstance(index.get("modules", []), list) else []
        ),
        "__DATA__": _safe_json(index),
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    return template
