#!/usr/bin/env python3
"""Build the single-file, decision-first Repo Teacher report.

The product keeps JSON, Markdown, and per-project reports as evidence artifacts,
but this page is the human entry point.  It deliberately embeds the curated
catalog so the reader never has to navigate between reports to compare the
reference implementations.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from html import escape
import json
from pathlib import Path
import sys


APP_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = APP_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from repo_teacher.reference_catalog import (  # noqa: E402
    AUDITED_CLAIMS,
    REFERENCE_CATALOG,
    REFERENCE_IDENTITIES,
    reference_identity_status,
)


REPO_ROOT = APP_ROOT.parents[1] / "repo"

PROJECTS = {
    "sourcebridge": {
        "label": "SourceBridge",
        "role": "生产索引与证据基准",
        "focus": "证据门、增量重证、语言隔离",
        "accent": "#e45d31",
        "featured": ("evidence-grounding", "incremental-update", "code-parsing"),
        "verdict": "重点参考证据门、增量状态机与多语言解析边界；不整体搬运服务层。",
    },
    "codeboarding": {
        "label": "CodeBoarding",
        "role": "调用图与组件发现基准",
        "focus": "LSP 调用图、Leiden 聚类、变更失效",
        "accent": "#2d6cdf",
        "featured": ("code-graph", "component-discovery", "incremental-update"),
        "verdict": "重点参考 LSP 图、Leiden 聚类和变更失效；Agent 文案层不作为事实层。",
    },
    "understand-anything": {
        "label": "Understand Anything",
        "role": "新鲜度与交互图基准",
        "focus": "fingerprint、staleness、Skill freshness",
        "accent": "#7c55c7",
        "featured": ("incremental-update", "codemap-visualization", "agent-workflow"),
        "verdict": "重点参考 fingerprint、staleness、Skills 和 Dashboard；避免绑定其插件运行时。",
    },
    "openwiki": {
        "label": "OpenWiki",
        "role": "Wiki 规划与独立评审基准",
        "focus": "skeleton critic、coverage critic、canonical page",
        "accent": "#258567",
        "featured": ("component-discovery", "evidence-grounding", "tutorial-generation"),
        "verdict": "重点参考先调查、再拟骨架、独立 critic、链接校验；prompt 约束不能冒充运行时保证。",
    },
    "deepwiki-open": {
        "label": "DeepWiki Open",
        "role": "Codemap 与源码跳转基准",
        "focus": "Codemap、CodeViewer、citation chain",
        "accent": "#b07715",
        "featured": ("codemap-visualization", "tutorial-generation", "agent-workflow"),
        "verdict": "重点参考 sections → steps → citation 与源码高亮；不把 RAG 文本块当符号事实。",
    },
    "pocketflow-code2tutorial": {
        "label": "PocketFlow Code2Tutorial",
        "role": "教程叙事流程基准",
        "focus": "六阶段总分总教程流",
        "accent": "#c43f68",
        "featured": ("tutorial-generation", "component-discovery", "agent-workflow"),
        "verdict": "重点参考六阶段总分总教程流；文本全量输入和 LLM 推断关系只作候选层。",
    },
}

CAPABILITY_LABELS = {
    "code-parsing": "代码解析与符号索引",
    "code-graph": "调用图与代码关系",
    "component-discovery": "组件与功能发现",
    "tutorial-generation": "教程与解释生成",
    "evidence-grounding": "证据与事实约束",
    "incremental-update": "增量更新与新鲜度",
    "codemap-visualization": "Codemap 与源码跳转",
    "agent-workflow": "Agent 工作流",
}

DECISIONS = (
    {
        "capability": "code-parsing",
        "primary": "codeboarding",
        "secondary": "sourcebridge",
        "adopt": "LSP 与 Tree-sitter 共同产生符号和位置事实。",
        "reject": "不采用纯文本抓取或 LLM 猜测调用关系。",
    },
    {
        "capability": "code-graph",
        "primary": "codeboarding",
        "secondary": "sourcebridge",
        "adopt": "先构建可验证关系，再供教学与组件发现消费。",
        "reject": "不把概念关系图当作源码调用图。",
    },
    {
        "capability": "component-discovery",
        "primary": "codeboarding",
        "secondary": "openwiki",
        "adopt": "图聚类产候选，独立 critic 对照源码收敛边界。",
        "reject": "不采用一次 LLM 调用直接命名全仓组件。",
    },
    {
        "capability": "tutorial-generation",
        "primary": "sourcebridge",
        "secondary": "pocketflow-code2tutorial",
        "adopt": "共享证据快照配合六阶段总分总教程结构。",
        "reject": "不把无行级证据的生成文案当成事实。",
    },
    {
        "capability": "evidence-grounding",
        "primary": "sourcebridge",
        "secondary": "openwiki",
        "adopt": "claim、文件、行范围和片段 hash 分开持久化。",
        "reject": "不把存在的文件路径自动升级为 claim proof。",
    },
    {
        "capability": "incremental-update",
        "primary": "sourcebridge",
        "secondary": "understand-anything",
        "adopt": "fingerprint、staleness、watermark 与依赖失效共同决定重建。",
        "reject": "不以 prompt cache 代替文件和结构失效判断。",
    },
    {
        "capability": "codemap-visualization",
        "primary": "deepwiki-open",
        "secondary": "understand-anything",
        "adopt": "导览步骤、关系图与源码行互相校验。",
        "reject": "不把静态阅读顺序冒充运行时调用流。",
    },
    {
        "capability": "agent-workflow",
        "primary": "openwiki",
        "secondary": "codeboarding",
        "adopt": "Planner 与 critic 分工，事实输入来自静态索引。",
        "reject": "不照搬固定 DAG 作为动态多 Agent 控制面。",
    },
)

WAKU_METRICS = (
    ("212", "索引文件"),
    ("1,557", "符号"),
    ("9,879", "关系"),
    ("13", "模块"),
    ("212 / 212", "暖索引复用"),
    ("0", "错误自调用"),
)


def source_link(project: str, relative: str, *, label: str = "相关模块") -> str:
    path = REPO_ROOT / project / relative
    href = path.as_uri()
    state = label if path.exists() else "路径缺失"
    return f'<a class="source" href="{escape(href, quote=True)}">{escape(relative)}<span>{escape(state)}</span></a>'


def project_index(project: str) -> dict:
    path = APP_ROOT / "examples" / "reference-selection" / "projects" / project / "index.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def identity_badge(project: str) -> tuple[str, bool]:
    index = project_index(project)
    analysis_fingerprint = str(index.get("analysis_fingerprint") or "")
    analyzed_at = str(index.get("project", {}).get("analyzed_at") or "")
    artifact_meta = (
        f'<code>analysis {escape(analysis_fingerprint[:12])}</code>'
        f'<code>generated {escape(analyzed_at[:19])}</code>'
        if analysis_fingerprint and analyzed_at
        else '<code>analysis artifact unavailable</code>'
    )
    status = reference_identity_status(index) if index else {
        "status": "unverified",
        "reason": "正式索引尚未生成",
    }
    expected = REFERENCE_IDENTITIES[project]
    if status.get("status") == "verified":
        dirty = " · 工作树有非审计文件变化" if status.get("dirty") else ""
        return (
            '<span class="identity verified">身份已验证</span>'
            f'<code>audited HEAD {escape(expected["commit"][:12])}</code>'
            f'<code>bundle {escape(expected["source_bundle_sha256"][:12])}</code>'
            f'{artifact_meta}{escape(dirty)}',
            True,
        )
    reason = str(status.get("reason") or "身份不匹配")
    return (
        '<span class="identity unverified">身份未验证</span>'
        f'<code>expected HEAD {escape(expected["commit"][:12])}</code>{artifact_meta} · {escape(reason)}',
        False,
    )


def claim_proofs(project: str, slug: str, *, verified: bool) -> str:
    claims = AUDITED_CLAIMS.get((project, slug), ())
    if not claims:
        return '<p class="claim-empty">本项暂无行级审计 claim；下面的文件仅是相关模块，不作为文案结论的直接证明。</p>'
    if not verified:
        return '<p class="claim-empty">仓库身份未通过审计门；原有 claim 已降级，暂不作为证明展示。</p>'
    rendered: list[str] = []
    for claim in claims:
        relative = str(claim["path"])
        line_start = int(claim["line_start"])
        line_end = int(claim["line_end"])
        path = REPO_ROOT / project / relative
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            snippet = "\n".join(lines[line_start - 1 : line_end])
            digest = hashlib.sha256(snippet.encode("utf-8")).hexdigest()
        except OSError:
            digest = "unavailable"
        href = f"{path.as_uri()}#L{line_start}-L{line_end}"
        rendered.append(
            '<li class="claim-proof">'
            f'<p>{escape(str(claim["claim"]))}</p>'
            f'<a href="{escape(href, quote=True)}">{escape(relative)}:{line_start}-{line_end}</a>'
            f'<code title="{escape(digest, quote=True)}">range sha256 {escape(digest[:12])}</code>'
            "</li>"
        )
    return '<div class="claim-block"><h5>行级审计证据</h5><ul>' + "".join(rendered) + "</ul></div>"


def capability_card(project: str, slug: str, entry: dict, featured: bool, *, verified: bool) -> str:
    data_flow = " → ".join(escape(step) for step in entry["data_flow"])
    sources = "".join(source_link(project, path) for path in entry["source_paths"])
    strengths = "".join(f"<li>{escape(item)}</li>" for item in entry["strengths"])
    limitations = "".join(f"<li>{escape(item)}</li>" for item in entry["limitations"])
    tags = "".join(f"<span class=\"tag\">{escape(tag)}</span>" for tag in entry["technology_tags"])
    return f"""
      <details id="capability-{escape(project)}--{escape(slug)}" class="mechanism {'is-featured' if featured else 'is-secondary'}" data-capability="{escape(slug)}" data-featured="{str(featured).lower()}" {'open' if featured else ''}>
        <summary>
          <h4 class="mechanism-title">{escape(CAPABILITY_LABELS[slug])}</h4>
          <span class="mechanism-signal">{'重点参考' if featured else '展开查看'}</span>
        </summary>
        <div class="mechanism-body">
          <p class="mechanism-summary">{escape(entry['summary'])}</p>
          <div class="approach"><b>实现方法</b><span>{escape(entry['approach'])}</span></div>
          <div class="flow"><b>实现流</b><span>{data_flow}</span></div>
          <div class="tags">{tags}</div>
          <div class="two-col">
            <div><h5>值得复用</h5><ul>{strengths}</ul></div>
            <div><h5>明确边界</h5><ul>{limitations}</ul></div>
          </div>
          <p class="reuse"><b>我们的判断：</b>{escape(entry['reuse_verdict'])}</p>
          {claim_proofs(project, slug, verified=verified)}
          <div class="sources"><h5>相关模块 / 继续阅读</h5>{sources}</div>
        </div>
      </details>"""


def project_section(project: str, metadata: dict) -> str:
    catalog = REFERENCE_CATALOG[project]
    featured = set(metadata["featured"])
    ordered = list(metadata["featured"]) + [key for key in CAPABILITY_LABELS if key not in featured]
    identity, verified = identity_badge(project)
    cards = "".join(
        capability_card(project, slug, catalog[slug], slug in featured, verified=verified)
        for slug in ordered
    )
    report = APP_ROOT / "examples" / "reference-selection" / "projects" / project / "index.html"
    return f"""
    <article class="project" id="project-{escape(project)}" data-project="{escape(project)}" style="--project:{metadata['accent']}">
      <header class="project-head">
        <div>
          <span class="eyebrow">REFERENCE 0{list(PROJECTS).index(project) + 1}</span>
          <h3>{escape(metadata['label'])}</h3>
          <p>{escape(metadata['role'])} · {escape(metadata['focus'])}</p>
          <p class="identity-line">{identity}</p>
        </div>
        <a class="open-report" href="{escape(report.as_uri(), quote=True)}">打开该仓完整索引 ↗</a>
      </header>
      <div class="project-verdict"><b>一句话采用边界</b><span>{escape(metadata['verdict'])}</span></div>
      <div class="mechanisms">{cards}</div>
    </article>"""


def decision_row(decision: dict[str, str]) -> str:
    slug = decision["capability"]
    primary = decision["primary"]
    secondary = decision["secondary"]
    primary_label = PROJECTS[primary]["label"]
    secondary_label = PROJECTS[secondary]["label"]
    primary_module = REFERENCE_CATALOG[primary][slug]["source_paths"][0]
    secondary_module = REFERENCE_CATALOG[secondary][slug]["source_paths"][0]
    return f"""<tr>
      <th>{escape(CAPABILITY_LABELS[slug])}</th>
      <td data-label="主参考"><a href="#capability-{escape(primary)}--{escape(slug)}"><b>{escape(primary_label)}</b></a></td>
      <td data-label="辅助参考"><a href="#capability-{escape(secondary)}--{escape(slug)}">{escape(secondary_label)}</a></td>
      <td data-label="复用模块"><a href="{escape((REPO_ROOT / primary / primary_module).as_uri(), quote=True)}">{escape(primary_module)}</a><br><a href="{escape((REPO_ROOT / secondary / secondary_module).as_uri(), quote=True)}">{escape(secondary_module)}</a></td>
      <td data-label="采用 / 不采用"><b>采用：</b>{escape(decision['adopt'])}<br><b>不采用：</b>{escape(decision['reject'])}</td>
    </tr>"""


def serena_decision_row() -> str:
    symbol_tools = REPO_ROOT / "serena" / "src" / "serena" / "tools" / "symbol_tools.py"
    language_layer = REPO_ROOT / "serena" / "src" / "solidlsp"
    return f"""<tr>
      <th>在线语义查询与重构</th>
      <td data-label="主参考"><a href="#serena"><b>Serena</b></a></td>
      <td data-label="辅助参考">CodeGraph + 持久代码索引</td>
      <td data-label="复用模块"><a href="{escape(symbol_tools.as_uri(), quote=True)}">src/serena/tools/symbol_tools.py</a><br><a href="{escape(language_layer.as_uri(), quote=True)}">src/solidlsp/</a></td>
      <td data-label="采用 / 不采用"><b>采用：</b>选定功能后，按需调用 live LSP 的 symbol、reference、diagnostics、rename 与 symbol edit。<br><b>不采用：</b>不把 Serena 当持久调用图、工作流编排器或执行沙箱；开源 LSP 与付费 JetBrains 能力分开。</td>
    </tr>"""


def serena_section() -> str:
    links = "".join(
        source_link("serena", path, label=label)
        for label, path in (
            ("符号/引用/诊断/编辑", "src/serena/tools/symbol_tools.py"),
            ("LSP 抽象与语言适配", "src/solidlsp"),
            ("MCP 接入", "src/serena/mcp.py"),
            ("项目记忆", "src/serena/memories/memory_manager.py"),
            ("安全边界", "docs/02-usage/070_security.md"),
        )
    )
    report = APP_ROOT.parents[1] / "biz" / "docs" / "html" / "serena-specialist.html"
    return f"""
    <article class="project" id="serena" data-specialist="serena" style="--project:#6b4cb5">
      <header class="project-head"><div><span class="eyebrow">SPECIALIST / LIVE SEMANTICS</span><h3>Serena</h3><p>在线 LSP 语义查询、诊断与符号级重构专项参考</p><p class="identity-line"><span class="identity specialist">专项完整 clone · MIT</span><code>HEAD 946ad9817875</code></p></div><a class="open-report" href="{escape(report.as_uri(), quote=True)}">打开 Serena 当前源码专项分析 ↗</a></header>
      <div class="project-verdict"><b>一句话采用边界</b><span>持久索引先回答“有哪些功能、怎样实现、改动影响谁”；Serena 在功能选定后回答“这个符号现在的声明、引用、诊断和安全编辑是什么”。二者是前后两层，不是二选一。</span></div>
      <div class="outcome-grid"><div class="outcome"><small>01 / RETRIEVAL</small><h3>符号级检索</h3><p>overview、find symbol、reference、declaration、implementation；比文本搜索更适合精确下钻。</p></div><div class="outcome"><small>02 / EDIT</small><h3>语义编辑</h3><p>rename、replace body、insert、safe delete；执行前仍要绑定 commit、worktree 与测试门。</p></div><div class="outcome"><small>03 / BACKEND</small><h3>多语言 LSP</h3><p>SolidLSP 统一不同语言服务器；不同语言的准确率和能力不能假定相同。</p></div><div class="outcome"><small>04 / BOUNDARY</small><h3>不是控制面</h3><p>不负责功能聚类、教程生成、长任务编排或沙箱；JetBrains 高级能力不属于 MIT LSP 核心。</p></div></div>
      <div class="sources"><h5>功能对应源码</h5>{links}</div>
    </article>"""


def build_html() -> str:
    project_nav = "".join(
        f'<button class="project-filter" type="button" data-target="{escape(key)}" aria-pressed="false"><i style="--dot:{value["accent"]}"></i>{escape(value["label"])}</button>'
        for key, value in PROJECTS.items()
    )
    snapshot_cards = "".join(
        f'<a class="snapshot-card" href="#project-{escape(key)}"><small>REFERENCE 0{idx}</small><h3>{escape(value["label"])}</h3><p>{escape(value["focus"])}</p><strong>{escape(value["role"])} → 查看独立贡献</strong></a>'
        for idx, (key, value) in enumerate(PROJECTS.items(), 1)
    )
    snapshot_cards += (
        '<a class="snapshot-card compat" href="#waku">'
        '<small>07 / COMPATIBILITY</small><h3>Waku Agent</h3>'
        '<p>不参加六仓选型。它只负责验证索引器、模块定位和本地运行时兼容性。</p>'
        '<strong>兼容性项目 → 查看证据</strong></a>'
    )
    decision_rows = "".join(decision_row(decision) for decision in DECISIONS) + serena_decision_row()
    project_sections = "".join(project_section(project, metadata) for project, metadata in PROJECTS.items()) + serena_section()
    waku_stats = "".join(f"<div><strong>{value}</strong><span>{label}</span></div>" for value, label in WAKU_METRICS)
    waku_sources = (
        ("Agent loop", "waku/loop/agent.py"),
        ("本地记忆", "waku/memory/__init__.py"),
        ("Graph engine", "waku/graph/engine.py"),
        ("Gateway", "waku/gateway/runner.py"),
        ("本地语音", "waku/gateway/voice.py"),
    )
    waku_links = "".join(source_link("waku-agent", path, label="兼容语料源码") for _, path in waku_sources)
    waku_report_root = APP_ROOT / "examples" / "compatibility" / "waku-agent"
    waku_reports = "".join(
        f'<a class="source" href="{escape(path.as_uri(), quote=True)}">{escape(label)}<span>正式报告</span></a>'
        for label, path in (
            ("Waku 完整索引", waku_report_root / "index" / "index.html"),
            ("Memory 模块", waku_report_root / "memory" / "modules" / "memory.html"),
            ("Graph 模块", waku_report_root / "graph" / "modules" / "graph.html"),
            ("Loop 模块", waku_report_root / "loop" / "modules" / "loop.html"),
            ("Gateway 模块", waku_report_root / "gateway" / "modules" / "gateway.html"),
        )
    )
    original_audit_href = (APP_ROOT / "docs" / "audits" / "waku-agent-index-compatibility.md").as_uri()
    final_audit_href = (APP_ROOT / "docs" / "audits" / "core-index-reaudit-round3.md").as_uri()
    teaching_audit_href = (APP_ROOT / "docs" / "audits" / "teaching-reaudit-round13.md").as_uri()
    research_href = (
        APP_ROOT.parents[1] / "biz" / "docs" / "html" / "repository-teaching-research.html"
    ).as_uri()
    architecture_adr_href = (
        APP_ROOT / "docs" / "decisions" / "0001-go-project-cli-and-human-project-report.md"
    ).as_uri()
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Repo Teacher — 一个 HTML 看懂代码索引技术选型</title>
  <style>
    :root{{--ink:#191916;--muted:#68665e;--paper:#f4f0e7;--panel:#fffdf7;--line:#d8d0c0;--accent:#e45d31;--accent-text:#943112;--green:#26705e;--shadow:0 22px 60px rgba(48,40,25,.10)}}
    *{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;background:var(--paper);color:var(--ink);font-family:"Avenir Next","PingFang SC","Noto Sans CJK SC",sans-serif;line-height:1.65}}
    body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.18;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.16'/%3E%3C/svg%3E")}}
    a{{color:inherit}} button{{font:inherit}} .shell{{max-width:1480px;margin:auto;padding:22px 30px 80px}} .topbar{{display:flex;justify-content:space-between;align-items:center;padding:10px 0 26px;border-bottom:1px solid var(--line);font-size:13px;letter-spacing:.08em}} .brand{{font-weight:900}} .status{{display:flex;gap:8px;align-items:center;color:var(--green);font-weight:800}} .status:before{{content:"";width:8px;height:8px;background:var(--green);border-radius:50%;box-shadow:0 0 0 5px #26705e22}}
    .hero{{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.55fr);gap:70px;padding:88px 0 46px}} .kicker,.eyebrow{{font-size:11px;letter-spacing:.2em;font-weight:800;color:var(--accent-text)}} h1{{font-family:"Songti SC","STSong",serif;font-size:clamp(50px,7vw,108px);line-height:.92;letter-spacing:-.065em;margin:15px 0 30px;max-width:980px}} .hero-copy{{font-size:clamp(18px,2vw,25px);max-width:800px;margin:0;color:#3e3c37}} .hero-copy b{{color:var(--ink)}} .hero-aside{{align-self:end;border-left:1px solid var(--line);padding-left:30px}} .hero-aside h2{{font-size:14px;margin:0 0 20px}} .hero-aside ol{{margin:0;padding:0;list-style:none;counter-reset:item}} .hero-aside li{{counter-increment:item;display:grid;grid-template-columns:38px 1fr;gap:10px;padding:13px 0;border-top:1px solid var(--line);font-size:14px}} .hero-aside li:before{{content:"0" counter(item);font-variant-numeric:tabular-nums;color:var(--accent-text);font-weight:800}}
    .architecture{{padding:0 0 64px}}.architecture-banner{{display:grid;grid-template-columns:1.2fr .8fr;gap:32px;padding:34px;background:#171b18;color:#f6f4ed}}.architecture-banner h2{{margin:8px 0 14px;font-family:"Songti SC","STSong",serif;font-size:clamp(34px,5vw,64px);line-height:1}}.architecture-banner p{{margin:0;color:#bdc7c0}}.architecture-banner strong{{color:#8bd2b2}}.architecture-flow{{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:#ffffff24;align-self:end}}.architecture-flow span{{padding:13px 9px;background:#202823;font-size:11px;text-align:center}}.architecture-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:10px}}.architecture-card{{padding:20px;border:1px solid var(--line);background:var(--panel)}}.architecture-card small{{color:var(--accent);font-weight:900}}.architecture-card h3{{margin:20px 0 8px;font-size:19px}}.architecture-card p{{margin:0;color:var(--muted);font-size:13px}}.architecture-card b{{display:block;margin-top:14px;font-size:12px}}.architecture-adr{{display:inline-block;margin-top:18px;color:#8bd2b2;font-weight:800}}
    .snapshot{{padding:0 0 46px}} .snapshot-head{{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:18px}} .snapshot-head h2{{font-family:"Songti SC","STSong",serif;font-size:clamp(28px,4vw,50px);line-height:1;margin:0;letter-spacing:-.04em}} .snapshot-head p{{margin:0;color:var(--muted);max-width:44rem}} .snapshot-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}} .snapshot-card{{display:flex;flex-direction:column;justify-content:space-between;min-height:170px;padding:18px 18px 16px;border:1px solid var(--line);background:linear-gradient(180deg,var(--panel),#f8f3e8);box-shadow:var(--shadow);text-decoration:none;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}} .snapshot-card:hover{{transform:translateY(-2px)}} .snapshot-card small{{font-size:11px;font-weight:900;letter-spacing:.18em;color:var(--accent)}} .snapshot-card h3{{font-family:"Songti SC","STSong",serif;font-size:28px;line-height:1.03;margin:10px 0 8px}} .snapshot-card p{{margin:0;color:var(--muted);font-size:14px}} .snapshot-card strong{{margin-top:16px;font-size:12px;letter-spacing:.08em}} .snapshot-card.compat{{grid-column:span 2;background:linear-gradient(135deg,#141715,#202824);border-color:#3f4a44;color:#eef0e9}} .snapshot-card.compat p{{color:#bdc7c0}} .snapshot-card.compat strong{{color:#8bd2b2}}
    .section{{padding:74px 0;border-top:1px solid var(--line)}} .section-head{{display:grid;grid-template-columns:220px 1fr;gap:30px;margin-bottom:36px}} .section-head span{{font-size:12px;font-weight:900;letter-spacing:.16em;color:var(--accent-text)}} .section-head h2{{font-family:"Songti SC","STSong",serif;font-size:clamp(34px,5vw,68px);line-height:1;margin:0;letter-spacing:-.04em}} .section-intro{{max-width:800px;color:var(--muted);font-size:16px;margin:18px 0 0}}
    .outcome-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line)}} .outcome{{background:var(--panel);padding:28px;min-height:220px}} .outcome small{{color:var(--accent);font-weight:900}} .outcome h3{{font-size:21px;margin:38px 0 10px}} .outcome p{{font-size:14px;color:var(--muted);margin:0}}
    .decision-wrap{{overflow:auto;border:1px solid var(--line);background:var(--panel)}} table{{border-collapse:collapse;width:100%;min-width:1080px}} th,td{{text-align:left;padding:19px 18px;border-bottom:1px solid var(--line);vertical-align:top}} th{{font-size:14px}} td{{font-size:13px;color:var(--muted)}} td b{{color:var(--ink)}} tr:last-child>*{{border-bottom:0}} .decision-wrap a{{overflow-wrap:anywhere;word-break:break-word;text-underline-offset:3px}}
    .filterbar{{position:sticky;top:0;z-index:10;display:flex;gap:7px;overflow:auto;padding:12px;background:#f4f0e7ed;backdrop-filter:blur(14px);border:1px solid var(--line);margin-bottom:18px}} .project-filter{{border:1px solid var(--line);background:var(--panel);padding:9px 13px;white-space:nowrap;cursor:pointer;font-size:12px;font-weight:700}} .project-filter i{{display:inline-block;width:7px;height:7px;background:var(--dot);border-radius:50%;margin-right:8px}} .project-filter.active{{background:var(--ink);color:white;border-color:var(--ink)}} .focus-toggle{{background:#fff6ea}} .focus-toggle[aria-pressed="true"]{{background:var(--accent);border-color:var(--accent);color:#fff}} .focus-toggle[aria-pressed="true"] i{{background:#fff}}
    .project{{background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow);margin:0 0 28px;padding:32px;scroll-margin-top:80px}} .project.hidden{{display:none}} .project-head{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;border-top:6px solid var(--project);padding-top:24px}} .project-head h3{{font-family:"Songti SC","STSong",serif;font-size:42px;line-height:1;margin:8px 0}} .project-head p{{margin:0;color:var(--muted)}} .identity-line{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px!important;font-size:11px}} .identity{{font-weight:900;padding:3px 7px;border-radius:999px}} .identity.verified{{background:#dff1e8;color:#165943}} .identity.unverified{{background:#f6dfd8;color:#842d1b}} .identity-line code{{font-size:10px}} .open-report{{font-size:12px;font-weight:800;text-decoration:none;border-bottom:1px solid;padding:7px 0}} .project-verdict{{display:grid;grid-template-columns:180px 1fr;gap:20px;margin:28px 0;padding:20px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);font-size:14px}} .project-verdict span{{color:var(--muted)}} .project-head b{{display:inline-block;margin-top:12px;padding:4px 8px;border:1px solid var(--line);font-size:11px;letter-spacing:.12em;text-transform:uppercase;background:#fff8ef}}
    .mechanism{{border-bottom:1px solid var(--line);scroll-margin-top:90px}} .mechanism summary{{list-style:none;cursor:pointer;display:flex;justify-content:space-between;gap:20px;padding:18px 3px;font-weight:800}} .mechanism summary::-webkit-details-marker{{display:none}} .mechanism-title{{font:inherit;margin:0}} .mechanism-title:before{{content:"＋";margin-right:13px;color:var(--project)}} .mechanism[open] .mechanism-title:before{{content:"—"}} .mechanism-signal{{font-size:11px;letter-spacing:.09em;color:var(--muted)}} .mechanism-body{{padding:5px 34px 28px}} .mechanism-summary{{font-family:"Songti SC","STSong",serif;font-size:21px;max-width:900px}} .approach,.flow{{display:grid;grid-template-columns:90px 1fr;gap:10px;padding:14px 16px;font-size:13px}} .approach{{border:1px solid var(--line);border-bottom:0}} .flow{{background:#efebe2}} .tags{{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0}} .tag{{font-size:11px;border:1px solid var(--line);padding:3px 8px;border-radius:999px}} .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:26px}} h5{{margin:15px 0 5px;font-size:12px;letter-spacing:.08em}} ul{{margin:5px 0;padding-left:18px;color:var(--muted);font-size:13px}} .reuse{{font-size:14px;border-left:3px solid var(--project);padding-left:14px}} .claim-block{{margin:18px 0;padding:16px;background:#f5eee1;border:1px solid #d9c6a5}} .claim-block h5{{margin-top:0}} .claim-proof{{margin:12px 0}} .claim-proof p{{margin:0;color:#2e2d29}} .claim-proof a,.claim-proof code{{display:inline-block;margin:5px 9px 0 0;font-size:11px}} .claim-empty{{font-size:12px;color:var(--muted);border-left:3px solid var(--line);padding-left:12px}} .sources{{display:flex;gap:7px;flex-wrap:wrap;align-items:center}} .sources h5{{width:100%}} .source{{display:inline-flex;align-items:center;gap:8px;max-width:100%;font-family:"SFMono-Regular","Cascadia Code",monospace;font-size:11px;text-decoration:none;background:#1e1e1b;color:#f6f1e7;padding:9px;overflow-wrap:anywhere}} .source span{{color:#d4a37e;font-family:inherit;font-size:9px;white-space:nowrap}}
    body.focus-mode .mechanism.is-secondary{{display:none}} body.focus-mode .project{{margin-bottom:20px}} body.focus-mode .snapshot-card:not(.compat){{opacity:.92}} body.focus-mode .filterbar{{border-color:#d7bf9b}}
    .waku{{background:#151916;color:#eef0e9;padding:clamp(26px,5vw,68px);display:grid;grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr);gap:60px}} .waku .kicker{{color:#8bd2b2}} .waku h3{{font-family:"Songti SC","STSong",serif;font-size:clamp(42px,6vw,76px);line-height:1;margin:12px 0 22px}} .waku p{{color:#b8c0b8}} .stats{{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid #ffffff24}} .stats div{{padding:18px;border-right:1px solid #ffffff24;border-bottom:1px solid #ffffff24}} .stats strong{{font-size:22px;display:block}} .stats span{{font-size:11px;color:#a6afa7}} .waku .source{{background:#eff4ec;color:#161a16}} .waku .source span{{color:#5c795f}} .defects{{margin-top:25px;border-top:1px solid #ffffff2b}} .defect{{padding:14px 0;border-bottom:1px solid #ffffff2b;font-size:13px}} .defect b{{color:#ffb48f}} .audit-link{{display:inline-block;color:#8bd2b2;margin-top:22px;font-size:13px}}
    .handoff{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--line);border:1px solid var(--line)}} .handoff>div{{background:var(--panel);padding:30px}} .handoff h3{{font-size:23px;margin-top:0}} .handoff code{{display:block;background:#20201d;color:#f4ead8;padding:15px;overflow:auto;font-size:12px}} footer{{display:flex;justify-content:space-between;gap:20px;padding-top:32px;color:var(--muted);font-size:11px}} .project-filter:focus-visible,.open-report:focus-visible,.source:focus-visible,.snapshot-card:focus-visible,.audit-link:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}
    @media(max-width:900px){{.shell{{padding:12px 15px 60px}}.hero{{grid-template-columns:1fr;gap:36px;padding:60px 0}}.hero-aside{{border-left:0;padding-left:0}}.architecture-banner{{grid-template-columns:1fr}}.architecture-flow{{grid-template-columns:repeat(3,1fr)}}.architecture-grid{{grid-template-columns:1fr 1fr}}.snapshot-head{{flex-direction:column;align-items:flex-start}}.snapshot-grid{{grid-template-columns:1fr 1fr}}.snapshot-card.compat{{grid-column:span 2}}.section-head{{grid-template-columns:1fr;gap:8px}}.outcome-grid{{grid-template-columns:1fr 1fr}}.project{{padding:20px}}.project-head{{display:block}}.open-report{{display:inline-block;margin-top:18px}}.project-verdict{{grid-template-columns:1fr;gap:6px}}.two-col,.waku,.handoff{{grid-template-columns:1fr}}.mechanism-body{{padding-left:5px;padding-right:5px}}.flow{{grid-template-columns:1fr}}}}
    @media(max-width:520px){{h1{{font-size:52px}}.topbar{{align-items:flex-start;gap:12px}}.status{{text-align:right}}.architecture-grid{{grid-template-columns:1fr}}.architecture-flow{{grid-template-columns:1fr 1fr}}.snapshot-grid{{grid-template-columns:1fr}}.snapshot-card.compat{{grid-column:auto}}.outcome-grid{{grid-template-columns:1fr}}.outcome{{min-height:0}}.project-head h3{{font-size:34px}}.stats{{grid-template-columns:1fr 1fr}}.two-col{{grid-template-columns:1fr}}.mechanism summary{{align-items:flex-start}}.mechanism-signal{{display:none}}.source{{width:100%}}footer{{display:block}}.project-filter{{min-height:48px}}.decision-wrap{{overflow:visible;border:0;background:none}}.decision-wrap table,.decision-wrap tbody,.decision-wrap tr,.decision-wrap th,.decision-wrap td{{display:block;min-width:0;width:100%}}.decision-wrap thead{{display:none}}.decision-wrap tr{{margin-bottom:14px;border:1px solid var(--line);background:var(--panel);padding:14px}}.decision-wrap th,.decision-wrap td{{border:0;padding:7px 0}}.decision-wrap td:before{{content:attr(data-label);display:block;font-size:10px;font-weight:900;letter-spacing:.1em;color:var(--accent-text)}}}}
    @media(prefers-reduced-motion:no-preference){{.project,.outcome{{animation:rise .55s both}}@keyframes rise{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}}}
  </style>
</head>
<body>
  <main class="shell">
    <nav class="topbar"><span class="brand">REPO TEACHER / ONE PAGE</span><span class="status">生产验收 PASS · 单页为唯一阅读入口</span></nav>
    <header class="hero">
      <div><span class="kicker">DECISION-FIRST CODEBASE INTELLIGENCE</span><h1>先定技术，<br>再写系统。</h1><p class="hero-copy">目标不是生成仓库百科，而是让你快速完成技术选型：<b>功能 → 底层机制 → 推荐路线 → 参考模块 → 采用/不采用 → 源码证据。</b></p></div>
      <aside class="hero-aside"><h2>阅读顺序</h2><ol><li>先看 Go 最终技术路线</li><li>再看每项功能参考谁</li><li>Waku 唯一验收仓</li><li>最后按需打开源码证据</li></ol></aside>
    </header>

    <section class="architecture" id="architecture"><div class="architecture-banner"><div><span class="kicker">00 / ACCEPTED ARCHITECTURE</span><h2>Go 模块化单体，<br>HTML 是主产品。</h2><p><strong>现有 Python 只保留为研究原型。</strong>最终实现用 Go 本地单二进制；参考仓只贡献机制；端到端只用 Waku 验收。</p><a class="architecture-adr" href="{escape(architecture_adr_href, quote=True)}">打开完整 ADR 与取舍记录 ↗</a></div><div class="architecture-flow"><span>Git 快照</span><span>Tree-sitter</span><span>事实图</span><span>功能语义</span><span>技术决策</span><span>单 HTML</span></div></div><div class="architecture-grid">
      <article class="architecture-card"><small>01 / RUNTIME</small><h3>Go 单二进制</h3><p>一个 CLI、一个进程、模块化单体；不先做微服务和远程控制面。</p><b>参考 SourceBridge 的 Go 边界，不复制其服务层。</b></article>
      <article class="architecture-card"><small>02 / PARSING</small><h3>Tree-sitter 事实层</h3><p>Waku 首期只启用 Python grammar；syntax fact 与推断严格分层。</p><b>选官方 Go binding；Serena 只做后置 live 语义层。</b></article>
      <article class="architecture-card"><small>03 / STORAGE</small><h3>SQLite 本地事实库</h3><p>快照、symbol、relation、evidence 与失效图放进单文件；源码只存范围和 hash。</p><b>不采用 SurrealDB / Neo4j 作为首期依赖。</b></article>
      <article class="architecture-card"><small>04 / SEMANTICS</small><h3>证据先于 LLM</h3><p>确定性候选先闭合证据；模型只能命名和归纳，不能生成代码事实。</p><b>证据不足就显示未知，不输出高置信幻觉。</b></article>
      <article class="architecture-card"><small>05 / HUMAN HTML</small><h3>先看决策，再下钻</h3><p>首屏只放功能、路线、取舍和复用边界；入口、文件、类退到证据层。</p><b>采用 PocketFlow 教学顺序与 DeepWiki 层级组织。</b></article>
      <article class="architecture-card"><small>06 / FRESHNESS</small><h3>内容寻址增量</h3><p>commit + file hash + analyzer fingerprint 决定复用，JSON/DB/HTML 同代原子发布。</p><b>参考 Understand Anything / RepoAgent 的 staleness。</b></article>
      <article class="architecture-card"><small>07 / TEST</small><h3>只测 Waku</h3><p>九类功能必须全部生成机制、技术、采用/不采用和可点击源码证据。</p><b>六仓与 Serena 只作为参考，不进入首期回归矩阵。</b></article>
      <article class="architecture-card"><small>08 / LATER</small><h3>延后非核心能力</h3><p>Serena adapter、Skill 导出、第二语言和第二测试仓放到 Waku 通过之后。</p><b>不让外围能力阻塞第一个可用产品。</b></article>
    </div></section>

    <section class="snapshot" id="snapshot">
      <div class="snapshot-head">
        <div>
          <span class="kicker">30 SECOND MAP</span>
          <h2>先读摘要层，<br>再决定要展开哪一块。</h2>
        </div>
        <p>六个参考项目各自承担一个独立贡献，Waku 只负责兼容性验证。这里不做堆叠式罗列，而是先把阅读路径压缩成一屏。</p>
      </div>
      <div class="snapshot-grid">{snapshot_cards}</div>
    </section>

    <section class="section" id="conclusion"><div class="section-head"><span>00 / 先看结论</span><div><h2>不选一个赢家，<br>组合四层事实。</h2><p class="section-intro">底层语义事实、功能边界、教学叙事和证据校验是四类不同问题。让同一个项目或同一个 LLM 同时负责四层，会让页面看起来完整，却无法判断结论真假。</p></div></div>
      <div class="outcome-grid"><div class="outcome"><small>01 / FACTS</small><h3>确定性代码事实</h3><p>CodeBoarding 与 SourceBridge：解析、符号、调用、依赖、位置。</p></div><div class="outcome"><small>02 / BOUNDARY</small><h3>功能与组件边界</h3><p>静态图先聚类，OpenWiki 式独立评审再命名，不让模型凭感觉划模块。</p></div><div class="outcome"><small>03 / TEACHING</small><h3>总分总教学</h3><p>SourceBridge 多产物证据层 + PocketFlow 六阶段叙事结构。</p></div><div class="outcome"><small>04 / PROOF</small><h3>分级证据</h3><p>已审计 claim 回到固定行范围和 hash；其余文件链接明确只是相关模块上下文。</p></div></div>
    </section>

    <section class="section" id="decisions"><div class="section-head"><span>01 / 功能选型</span><div><h2>九个功能，<br>九组明确参考。</h2><p class="section-intro">下表是实现路线，不是 star 排名。每一行都区分主参考、辅助参考、复用模块与明确不采用的边界；Serena 专门负责功能选定后的 live 语义操作。</p></div></div><div class="decision-wrap"><table><thead><tr><th>目标功能</th><th>主参考</th><th>辅助参考</th><th>复用模块</th><th>采用 / 不采用</th></tr></thead><tbody>{decision_rows}</tbody></table></div></section>

    <section class="section" id="projects"><div class="section-head"><span>02 / 项目下钻</span><div><h2>每个项目，<br>都有独立贡献。</h2><p class="section-intro">默认展开每个项目最有价值的三项机制。行级 claim proof 与“相关模块 / 继续阅读”严格分栏；其余五项按需展开。</p></div></div><div class="filterbar"><button class="project-filter focus-toggle" type="button" data-focus-toggle aria-pressed="false"><i style="--dot:#b27724"></i>只看重点</button><button class="project-filter active" type="button" data-target="all" aria-pressed="true">全部项目</button>{project_nav}</div>{project_sections}</section>

    <section class="section" id="waku"><div class="waku"><div><span class="kicker">07 / COMPATIBILITY CORPUS</span><h3>Waku Agent</h3><p>Waku 不参加六仓技术排名。它是第七个真实兼容性仓库，用本地 Agent loop、memory、graph、gateway 和 voice 验证索引器没有只记住六个参考答案。</p><div class="stats">{waku_stats}</div><div class="defects"><div class="defect"><b>原始发现：</b>root/current 校验不一致。<br><b>关闭：</b>两种稳定入口现在都经 verified generation reader；独立复验 PASS。</div><div class="defect"><b>原始发现：</b>未生成产物也创建悬空 compatibility link。<br><b>关闭：</b>链接集合由 generation manifest 推导并可在下一次写锁自愈；独立复验 PASS。</div><div class="defect"><b>原始发现：</b><code>self.model.transcribe</code> 曾错连为本地自调用。<br><b>关闭：</b>Waku 冷/暖索引错误边均为 0；独立复验 PASS。</div></div><a class="audit-link" href="{escape(final_audit_href, quote=True)}">查看修复后独立 PASS 审计 ↗</a><br><a class="audit-link" href="{escape(original_audit_href, quote=True)}">查看修复前 Waku 发现记录 ↗</a></div><div><h4>正式兼容性产物</h4><div class="sources">{waku_reports}</div><h4>五个真实实现入口</h4><div class="sources">{waku_links}</div><p><code>audited HEAD 75b0a6d27a19</code></p><p>测试结论：212 个文件冷建后，磁盘暖启动 212/212 复用、0 重算；memory / graph / loop / gateway 保持候选功能，不进入六仓 curated 排名。</p></div></div></section>

    <section class="section" id="handoff"><div class="section-head"><span>03 / 使用方式</span><div><h2>一个入口，<br>证据仍可追溯。</h2></div></div><div class="handoff"><div><h3>你主要看这个文件</h3><p>本页包含选型、六仓参考、Waku 兼容性和源码跳转。详细 JSON、Markdown 与分仓页面只作为证据附件。</p><p><a href="{escape(research_href, quote=True)}"><b>查看 GitHub / X / Skills 完整研究与采用矩阵</b></a></p><p><a href="{escape(final_audit_href, quote=True)}">核心索引独立 PASS 审计</a> · <a href="{escape(teaching_audit_href, quote=True)}">教学报告独立 PASS 审计</a></p><code>biz/docs/html/repo-teacher.html</code></div><div><h3>给 Agent 的执行方式</h3><p>选择功能后，导出对应能力的 Skill 与源码索引；Agent 先读入口和关系，再决定修改范围。</p><code>repo-teacher explain /path/to/repo &lt;功能名&gt; -o output</code></div></div></section>
    <footer><span>Generated by Repo Teacher · {escape(timestamp)}</span><span>事实 / 推断 / 未知项严格分层</span></footer>
  </main>
  <script>
    const buttons=[...document.querySelectorAll('.project-filter')];
    const projects=[...document.querySelectorAll('.project')];
    const focusToggle=document.querySelector('[data-focus-toggle]');
    const setFocusMode=(enabled)=>{{
      document.body.classList.toggle('focus-mode',enabled);
      if(focusToggle){{
        focusToggle.setAttribute('aria-pressed',String(enabled));
        focusToggle.lastChild.nodeValue=enabled?'显示全部':'只看重点';
      }}
    }};
    buttons.forEach(button=>button.addEventListener('click',()=>{{
      if(button===focusToggle){{
        setFocusMode(!document.body.classList.contains('focus-mode'));
        return;
      }}
      buttons.forEach(item=>{{item.classList.remove('active');if(item!==focusToggle)item.setAttribute('aria-pressed','false')}});button.classList.add('active');button.setAttribute('aria-pressed','true');
      const target=button.dataset.target;projects.forEach(project=>project.classList.toggle('hidden',target!=='all'&&project.dataset.project!==target));
      if(target!=='all') document.querySelector('#project-'+target)?.scrollIntoView({{behavior:'smooth',block:'start'}});
    }}));
  </script>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=APP_ROOT.parents[1] / "biz" / "docs" / "html" / "repo-teacher.html",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
