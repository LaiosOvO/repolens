from __future__ import annotations

import html
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def _text(value: Any, fallback: str = "") -> str:
    rendered = str(value).strip() if value is not None else ""
    return rendered or fallback


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _decimal(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _escape(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _project_root(result: dict[str, Any]) -> Path | None:
    project = result.get("project", {}) if isinstance(result.get("project"), dict) else {}
    raw = _text(project.get("path"))
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return None


def _safe_file_uri(uri: Any, project_root: Path | None) -> str | None:
    raw = _text(uri)
    if not raw or project_root is None:
        return None
    parsed = urlparse(raw)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        return None
    try:
        candidate = Path(unquote(parsed.path)).resolve(strict=False)
        if not candidate.is_relative_to(project_root):
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate.as_uri()


def _source_link(
    uri: Any,
    label: Any,
    project_root: Path | None,
    *,
    class_name: str = "source-link",
) -> str:
    safe_uri = _safe_file_uri(uri, project_root)
    safe_label = _escape(label)
    safe_class = html.escape(class_name, quote=True)
    if not safe_uri:
        return f'<code class="{safe_class} disabled">{safe_label}</code>'
    return (
        f'<a class="{safe_class}" href="{html.escape(safe_uri, quote=True)}" '
        'target="_blank" rel="noreferrer" title="打开源文件；行号由报告内源码片段锚定">'
        f'{safe_label}<span aria-hidden="true">↗</span></a>'
    )


def _location_label(location: dict[str, Any], fallback: str = "未标注路径") -> str:
    path = _text(location.get("path"), fallback)
    start = _number(location.get("line_start"))
    end = _number(location.get("line_end"), start)
    if start <= 0:
        return path
    return f"{path}:{start}" if end <= start else f"{path}:{start}-{end}"


def _render_excerpt(location: Any) -> str:
    if not isinstance(location, dict):
        return ""
    snippet = _text(location.get("snippet"))
    if not snippet:
        stale = "源码快照已变化或无法读取，未展示陈旧片段。" if not location.get("fresh") else "没有可展示片段。"
        return f'<p class="freshness warning">{_escape(stale)}</p>'
    digest = _text(location.get("snippet_sha256"))[:12]
    return (
        '<div class="source-excerpt">'
        f'<div><strong>{_escape(_location_label(location))}</strong>'
        f'<small>片段 SHA-256 {html.escape(digest)}</small></div>'
        f'<pre><code>{_escape(snippet)}</code></pre></div>'
    )


def _confidence(module: dict[str, Any]) -> tuple[str, str]:
    label = _text(module.get("confidence_label"), "low").casefold()
    if label == "high":
        return "high", "高置信源码候选"
    if label == "medium":
        return "medium", "中置信源码候选"
    return "low", "低置信源码候选"


def _render_slice(slice_record: dict[str, Any], project_root: Path | None) -> str:
    path = _text(slice_record.get("path"), ".")
    return (
        '<li class="slice-row">'
        f'<span>{_escape(slice_record.get("role") or "core")}</span>'
        f'{_source_link(slice_record.get("source_uri"), path, project_root)}'
        f'<small>{_escape(slice_record.get("kind") or "source")} · '
        f'{_escape(slice_record.get("evidence") or "candidate")}</small></li>'
    )


def _render_module_card(module: dict[str, Any], position: int) -> str:
    confidence_class, confidence_text = _confidence(module)
    search_material = " ".join(
        [
            _text(module.get("name")),
            _text(module.get("path")),
            *[
                _text(item.get("path"))
                for item in module.get("slices", [])
                if isinstance(item, dict)
            ],
            *[
                _text(symbol.get("name"))
                for symbol in module.get("core_symbols", [])
                if isinstance(symbol, dict)
            ],
        ]
    ).casefold()
    languages = " · ".join(_text(item) for item in module.get("languages", {}).keys()) or "未知语言"
    return (
        f'<a class="module-card" href="#module-{position:03d}" data-search="{html.escape(search_material, quote=True)}">'
        f'<div class="card-top"><span class="rank">{position:02d}</span>'
        f'<span class="confidence {confidence_class}">{confidence_text}</span></div>'
        f'<h3>{_escape(module.get("name") or "未命名能力")}</h3>'
        f'<code>{_number(len(module.get("slices", [])))} 个 implementation slices</code>'
        f'<p>{_number(module.get("file_count"))} 文件 · {_number(module.get("symbol_count"))} 符号</p>'
        f'<small>{_escape(languages)}</small><strong>查看候选实现面 →</strong></a>'
    )


def _render_file(file: dict[str, Any], project_root: Path | None, *, excerpt: bool = False) -> str:
    location = file.get("source_location", {}) if isinstance(file.get("source_location"), dict) else {}
    source = _source_link(file.get("source_uri"), file.get("path") or "未标注路径", project_root)
    association = _text(file.get("association"))
    association_html = (
        f'<p class="association">关联：{_escape(association)} · '
        f'{_escape(file.get("association_confidence") or "unknown")} · '
        f'{_escape(file.get("evidence_status") or "unknown")}</p>'
        if association
        else ""
    )
    excerpt_html = _render_excerpt(location) if excerpt else ""
    return (
        '<li class="file-row"><div>'
        f'{source}<p>{_escape(file.get("role_reason") or "尚未识别文件职责")}</p>'
        f'{association_html}{excerpt_html}</div>'
        f'<span class="role">{_escape(file.get("surface_role") or file.get("role") or "unknown")} · '
        f'{_escape(file.get("role_confidence") or "heuristic")}</span>'
        f'<small>{_escape(file.get("language") or "Unknown")} · {_number(file.get("lines"))} 行 · '
        f'{_number(file.get("symbol_count"))} 符号</small></li>'
    )


def _render_core_symbol(symbol: dict[str, Any], project_root: Path | None) -> str:
    location = symbol.get("source_location", {}) if isinstance(symbol.get("source_location"), dict) else {}
    signature = _text(symbol.get("signature"))
    signature_html = f'<pre class="signature">{_escape(signature)}</pre>' if signature else ""
    return (
        '<li class="symbol-row"><div><strong>'
        f'{_escape(symbol.get("name") or "未命名符号")}</strong>'
        f'<span>{_escape(symbol.get("kind") or "symbol")}</span></div>'
        f'{_source_link(symbol.get("source_uri"), _location_label(location), project_root)}'
        f'<small>{_number(symbol.get("relationship_count"))} 条相关已解析边</small>'
        f'{signature_html}{_render_excerpt(location)}</li>'
    )


def _render_relationship(relationship: dict[str, Any], project_root: Path | None) -> str:
    source = relationship.get("source", {}) if isinstance(relationship.get("source"), dict) else {}
    target = relationship.get("target", {}) if isinstance(relationship.get("target"), dict) else {}
    source_label = _location_label(source, _text(source.get("name"), "unknown"))
    target_label = _location_label(target, _text(target.get("name"), "unresolved"))
    resolved = "已解析" if relationship.get("resolved") else "未解析引用"
    return (
        '<li class="relationship-row"><div>'
        f'{_source_link(source.get("source_uri"), source_label, project_root)}'
        f'<span class="arrow">— {_escape(relationship.get("kind") or "relates")} →</span>'
        f'{_source_link(target.get("source_uri"), target_label, project_root)}</div>'
        f'<small>{_escape(resolved)} · {_escape(relationship.get("confidence") or "unknown")}</small></li>'
    )


def _render_relationship_group(
    module: dict[str, Any],
    key: str,
    title: str,
    explanation: str,
    project_root: Path | None,
) -> str:
    relationships = module.get("relationships", {}) if isinstance(module.get("relationships"), dict) else {}
    items = relationships.get(key, []) if isinstance(relationships.get(key), list) else []
    items = [item for item in items if isinstance(item, dict)]
    counts = module.get("relationship_counts", {}) if isinstance(module.get("relationship_counts"), dict) else {}
    total = _number(counts.get(key), len(items))
    rows = "".join(_render_relationship(item, project_root) for item in items[:30])
    if not rows:
        rows = '<li class="empty-row">当前索引没有发现该类关系。</li>'
    return (
        '<details class="relationship-group">'
        f'<summary><span>{_escape(title)}</span><b>{total}</b></summary>'
        f'<p>{_escape(explanation)}</p><ul>{rows}</ul></details>'
    )


def _render_trace_step(step: dict[str, Any], project_root: Path | None) -> str:
    source = step.get("source", {}) if isinstance(step.get("source"), dict) else {}
    target = step.get("target", {}) if isinstance(step.get("target"), dict) else {}
    return (
        '<li class="implementation-step">'
        f'<span class="step-index">{_number(step.get("order")):02d}</span><div>'
        f'<small>{_escape(step.get("ordering") or "resolved relationship")} · layer '
        f'{_number(step.get("topology_layer"))} · {_escape(step.get("confidence") or "unknown")}</small>'
        f'<h4>{_escape(step.get("relationship_kind") or "relationship")}</h4>'
        '<div class="trace-pair">'
        f'{_source_link(source.get("source_uri"), _location_label(source), project_root, class_name="step-file")}'
        '<span>→</span>'
        f'{_source_link(target.get("source_uri"), _location_label(target), project_root, class_name="step-file")}'
        '</div>'
        f'{_render_excerpt(source)}{_render_excerpt(target)}</div></li>'
    )


def _render_component(component: dict[str, Any], project_root: Path | None) -> str:
    file_links = "".join(
        _source_link(
            file.get("source_uri"), file.get("path"), project_root, class_name="step-file"
        )
        for file in component.get("files", [])
        if isinstance(file, dict) and _text(file.get("path"))
    )
    return (
        '<li class="reading-step"><div>'
        f'<small>{_escape(component.get("confidence") or "component-candidate")}</small>'
        f'<h4>{_number(component.get("file_count"))} 文件 · {_number(component.get("edge_count"))} 跨文件边</h4>'
        f'<div class="step-files">{file_links}</div></div></li>'
    )


def _render_reading_step(step: dict[str, Any], project_root: Path | None) -> str:
    files = step.get("files", []) if isinstance(step.get("files"), list) else []
    file_links = "".join(
        _source_link(
            file.get("source_uri"),
            file.get("path") or "未标注路径",
            project_root,
            class_name="step-file",
        )
        for file in files
        if isinstance(file, dict)
    )
    return (
        '<li class="reading-step"><div>'
        f'<small>{_escape(step.get("role") or "source")} · heuristic</small>'
        f'<h4>{_escape(step.get("title") or "阅读建议")}</h4>'
        f'<p>{_escape(step.get("explanation") or "这不是运行时顺序。")}</p>'
        f'<div class="step-files">{file_links}</div></div></li>'
    )


def _render_module_detail(
    module: dict[str, Any],
    position: int,
    project_root: Path | None,
) -> str:
    confidence_class, confidence_text = _confidence(module)
    reasons = module.get("reasons", []) if isinstance(module.get("reasons"), list) else []
    reason_html = "".join(f'<li>{_escape(reason)}</li>' for reason in reasons) or "<li>没有记录判断依据。</li>"
    slices = module.get("slices", []) if isinstance(module.get("slices"), list) else []
    files = module.get("files", []) if isinstance(module.get("files"), list) else []
    symbols = module.get("core_symbols", []) if isinstance(module.get("core_symbols"), list) else []
    trace = module.get("implementation_trace", []) if isinstance(module.get("implementation_trace"), list) else []
    reading = module.get("reading_order", []) if isinstance(module.get("reading_order"), list) else []
    components = module.get("component_boundaries", []) if isinstance(module.get("component_boundaries"), list) else []
    tests = module.get("tests", []) if isinstance(module.get("tests"), list) else []
    possible_tests = module.get("possible_tests", []) if isinstance(module.get("possible_tests"), list) else []
    entrypoints = module.get("entrypoints", []) if isinstance(module.get("entrypoints"), list) else []
    slice_html = "".join(_render_slice(item, project_root) for item in slices if isinstance(item, dict))
    entry_html = "".join(_render_file(item, project_root, excerpt=True) for item in entrypoints if isinstance(item, dict))
    entry_html = entry_html or '<li class="empty-row">未发现可证实入口；请从已解析关系和核心符号继续核对。</li>'
    trace_html = "".join(_render_trace_step(item, project_root) for item in trace if isinstance(item, dict))
    trace_html = trace_html or '<li class="empty-row warning">当前解析器未形成已解析运行时/依赖链；不会用文件名猜测替代。</li>'
    reading_html = "".join(_render_reading_step(item, project_root) for item in reading if isinstance(item, dict))
    component_html = "".join(_render_component(item, project_root) for item in components if isinstance(item, dict))
    component_html = component_html or '<li class="empty-row">没有足够的已解析边形成组件边界。</li>'
    symbol_html = "".join(_render_core_symbol(item, project_root) for item in symbols if isinstance(item, dict))
    symbol_html = symbol_html or '<li class="empty-row">当前分析器没有识别出核心符号。</li>'
    test_html = "".join(_render_file(item, project_root) for item in tests if isinstance(item, dict))
    test_html = test_html or '<li class="empty-row warning">未发现通过 import/call/reference 解析关联的测试。</li>'
    possible_html = "".join(_render_file(item, project_root) for item in possible_tests if isinstance(item, dict))
    possible_html = possible_html or '<li class="empty-row">没有额外的目录结构测试候选。</li>'
    file_html = "".join(_render_file(item, project_root) for item in files if isinstance(item, dict))
    quality = module.get("relationship_quality", {}) if isinstance(module.get("relationship_quality"), dict) else {}
    return (
        f'<article class="module-detail" id="module-{position:03d}">'
        '<header class="detail-head"><div>'
        f'<span class="eyebrow">能力实现面 {position:02d} · {_escape(module.get("certainty") or "candidate")}</span>'
        f'<h2>{_escape(module.get("name") or "未命名能力")}</h2>'
        f'<p>{_escape(module.get("surface_kind") or "surface")} · 不等同于功能语义已验证</p></div>'
        f'<span class="confidence large {confidence_class}">{_escape(confidence_text)} · '
        f'{round(_decimal(module.get("confidence")) * 100)}%</span></header>'
        '<section class="why"><h3>先看结论：这些只是源码候选依据</h3>'
        f'<ul>{reason_html}</ul></section>'
        '<section><div class="section-title"><span>01</span><div><h3>Implementation slices</h3>'
        '<p>一个功能可以横跨目录、根目录文件、后端边界和前端展示；每个切片保留独立职责。</p></div></div>'
        f'<ul class="slice-list">{slice_html}</ul></section>'
        '<section><div class="section-title"><span>02</span><div><h3>入口候选与源码锚点</h3>'
        '<p>链接只打开源文件；报告内的 path:line、片段和哈希负责精确锚定，并通过文件哈希检查新鲜度。</p></div></div>'
        f'<ul class="file-list">{entry_html}</ul></section>'
        '<section><div class="section-title"><span>03</span><div><h3>基于已解析边的组件边界</h3>'
        '<p>使用无向连通分量折叠相关文件；孤立文件保留为单独切片，不伪造聚类关系。</p></div></div>'
        f'<ol class="reading-list">{component_html}</ol></section>'
        '<section><div class="section-title"><span>04</span><div><h3>已解析实现链</h3>'
        '<p>这里只显示解析成功的 call/import/reference 等边；它与下面的启发式阅读顺序严格分离。</p></div></div>'
        f'<ol class="implementation-list">{trace_html}</ol></section>'
        '<section><div class="section-title"><span>05</span><div><h3>启发式阅读顺序</h3>'
        '<p>按路径与文件职责分组，帮助阅读，但不声称是运行时、调用或数据流。</p></div></div>'
        f'<ol class="reading-list">{reading_html}</ol></section>'
        '<section><div class="section-title"><span>06</span><div><h3>核心符号与行级片段</h3>'
        '<p>每个符号显示真实行范围、内容片段与哈希；源码变化时拒绝展示陈旧片段。</p></div></div>'
        f'<ul class="symbol-list">{symbol_html}</ul></section>'
        '<section><div class="section-title"><span>07</span><div><h3>关系证据质量</h3>'
        f'<p>已解析 {_number(quality.get("resolved"))}，未解析 {_number(quality.get("unresolved"))}，'
        f'解析率 {round(_decimal(quality.get("resolved_ratio")) * 100)}%。未解析引用不会计入依赖结论。</p></div></div>'
        '<div class="relationship-grid">'
        f'{_render_relationship_group(module, "resolved_internal", "已解析内部边", "源和目标均在实现面内。", project_root)}'
        f'{_render_relationship_group(module, "resolved_inbound", "已解析入站边", "实现面外源码解析到实现面内部。", project_root)}'
        f'{_render_relationship_group(module, "resolved_outbound", "已解析出站边", "实现面内部源码解析到外部目标。", project_root)}'
        f'{_render_relationship_group(module, "unresolved", "未解析引用（诊断）", "仅用于提示解析器缺口，不作为模块依赖结论。", project_root)}'
        '</div></section>'
        '<section><div class="section-title"><span>08</span><div><h3>测试关联，不等于测试覆盖</h3>'
        '<p>第一组要求已解析 import/call/reference；第二组仅为明确的嵌套/镜像路径规则，单独标为结构候选。</p></div></div>'
        '<h4>已解析静态关联</h4>'
        f'<ul class="file-list">{test_html}</ul><h4>结构关联候选（未验证）</h4>'
        f'<ul class="file-list">{possible_html}</ul></section>'
        '<details class="all-files"><summary>查看实现面全部产品源码文件 <b>'
        f'{len(files)}</b></summary><ul class="file-list">{file_html}</ul></details>'
        '<a class="back" href="#module-index">↑ 回到候选实现面</a></article>'
    )


def render_module_report(index: dict[str, Any], result: dict[str, Any]) -> str:
    """Render a standalone, escaped capability-surface report."""

    if not isinstance(index, dict) or not isinstance(result, dict):
        raise TypeError("index and result must be dictionaries")
    project = result.get("project", {}) if isinstance(result.get("project"), dict) else {}
    resolution = result.get("resolution", {}) if isinstance(result.get("resolution"), dict) else {}
    modules = result.get("modules", []) if isinstance(result.get("modules"), list) else []
    modules = [item for item in modules if isinstance(item, dict)]
    query = _text(result.get("query"), "未命名功能")
    status = _text(resolution.get("status"), "not_found")
    status_title = {
        "exact_name_match": "唯一产品目录名称精确命中（功能未验证）",
        "composite_candidate": "找到跨目录 / 根目录的候选实现面",
        "candidate": "找到源码候选，仍需人工核对",
        "not_found": "当前索引没有产品源码证据",
    }.get(status, "当前结果需要人工复核")
    root = _project_root(result)
    cards = "".join(_render_module_card(module, position) for position, module in enumerate(modules, start=1))
    details = "".join(
        _render_module_detail(module, position, root)
        for position, module in enumerate(modules, start=1)
    )
    if not cards:
        cards = (
            '<div class="empty-state"><strong>没有可展示的产品实现面</strong>'
            '<p>docs/tests/examples/generated 等同名目录不会被提升为产品功能实现。</p></div>'
        )
    stats = index.get("stats", {}) if isinstance(index.get("stats"), dict) else {}
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(query)} · 功能实现面定位</title>
<style>
:root{{--ink:#18211d;--muted:#66706b;--paper:#f6f3ec;--card:#fffefa;--line:#d9d7ce;--green:#175c43;--green-soft:#e3f0e8;--amber:#8a5a0a;--amber-soft:#fff0c7;--red:#9d342a;--blue:#315a88;--shadow:0 18px 50px rgba(21,35,28,.08)}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}a{{color:inherit}}code,pre{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}.wrap{{width:min(1180px,calc(100% - 40px));margin:auto}}.hero{{padding:72px 0 44px;background:linear-gradient(135deg,#193b2e,#10271e);color:white}}.hero .eyebrow,.eyebrow{{letter-spacing:.12em;text-transform:uppercase;font-weight:800;font-size:12px}}.hero h1{{font-size:clamp(38px,7vw,76px);line-height:1.04;margin:16px 0 20px}}.hero h1 em{{font-style:normal;color:#9ee0bb}}.hero p{{max-width:850px;color:#d2e3da;font-size:18px}}.summary-strip{{display:grid;grid-template-columns:2fr repeat(3,1fr);gap:1px;background:#496157;margin-top:34px;border:1px solid #496157;border-radius:16px;overflow:hidden}}.summary-strip>div{{min-width:0;background:#17382b;padding:18px 20px}}.summary-strip strong{{display:block;font-size:19px;overflow-wrap:anywhere}}.summary-strip small{{color:#b9cec4}}main{{padding:44px 0 80px}}.answer-first{{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:28px;box-shadow:var(--shadow);display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:center}}.answer-first h2{{margin:0 0 8px;font-size:28px}}.answer-first p{{margin:0;color:var(--muted)}}.status{{padding:10px 15px;border-radius:999px;background:var(--amber-soft);color:var(--amber);font-weight:800;white-space:nowrap}}.search-bar{{margin:28px 0 18px;display:flex;gap:12px;align-items:center}}.search-bar input{{min-width:0;width:100%;border:1px solid var(--line);background:var(--card);padding:15px 17px;border-radius:13px;font:inherit}}.search-bar span{{white-space:nowrap;color:var(--muted)}}.module-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}.module-card{{min-width:0;text-decoration:none;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px;min-height:230px;display:flex;flex-direction:column;box-shadow:0 4px 18px rgba(20,30,25,.04)}}.module-card:hover{{transform:translateY(-3px);border-color:#86aa97}}.module-card[hidden]{{display:none}}.card-top,.detail-head{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}}.rank{{font-weight:900;color:#94a099}}.confidence{{display:inline-flex;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:800;background:#eee}}.confidence.high{{color:var(--blue);background:#e8eef8}}.confidence.medium{{color:var(--amber);background:var(--amber-soft)}}.confidence.low{{color:var(--red);background:#f8e5e3}}.confidence.large{{font-size:14px;padding:9px 13px}}.module-card h3{{font-size:26px;margin:25px 0 4px;overflow-wrap:anywhere}}.module-card code{{color:var(--green);overflow-wrap:anywhere}}.module-card p,.module-card small{{color:var(--muted)}}.module-card strong{{margin-top:auto;color:var(--green)}}.module-detail{{min-width:0;max-width:100%;margin-top:42px;background:var(--card);border:1px solid var(--line);border-radius:24px;padding:clamp(22px,4vw,46px);box-shadow:var(--shadow);scroll-margin-top:20px}}.detail-head{{border-bottom:1px solid var(--line);padding-bottom:26px}}.detail-head>div,.section-title>div,.file-row>div,.symbol-row>div,.implementation-step>div,.reading-step>div{{min-width:0;max-width:100%}}.detail-head h2{{font-size:clamp(34px,5vw,52px);line-height:1.1;margin:8px 0;overflow-wrap:anywhere}}.detail-head p{{color:var(--muted)}}.source-link,.step-file{{min-width:0;color:var(--green);font-weight:700;text-decoration:none;overflow-wrap:anywhere}}.source-link span,.step-file span{{margin-left:5px}}.disabled{{color:var(--muted);font-weight:500}}.why{{background:#edf4ef;border-left:5px solid var(--green);padding:19px 24px;margin:28px 0;overflow-wrap:anywhere}}.why h3{{margin:0}}section{{min-width:0;max-width:100%;margin:38px 0}}.section-title{{display:flex;gap:16px;align-items:flex-start;margin-bottom:18px}}.section-title>span{{flex:0 0 38px;width:38px;height:38px;display:grid;place-items:center;background:var(--ink);color:white;border-radius:50%;font-weight:900}}.section-title h3{{margin:0;font-size:25px;overflow-wrap:anywhere}}.section-title p{{margin:2px 0 0;color:var(--muted)}}ul,ol{{padding:0}}.file-list,.symbol-list,.slice-list,.relationship-group ul,.implementation-list,.reading-list{{min-width:0;max-width:100%;list-style:none;margin:0}}.slice-row{{display:grid;grid-template-columns:140px minmax(0,1fr) auto;gap:14px;padding:13px 0;border-bottom:1px solid var(--line)}}.slice-row>span{{color:var(--blue);font:700 12px ui-monospace,monospace;text-transform:uppercase}}.slice-row small{{color:var(--muted)}}.file-row,.symbol-row{{min-width:0;max-width:100%;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px 18px;padding:15px 0;border-bottom:1px solid var(--line)}}.file-row>div p{{margin:3px 0 0;color:var(--muted);font-size:14px}}.file-row small,.symbol-row small{{grid-column:2;color:var(--muted)}}.role{{font:700 12px ui-monospace,monospace;text-transform:uppercase;color:var(--blue)}}.association{{color:var(--blue)!important}}.symbol-row>div{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}.symbol-row>div span{{font-size:12px;background:#eeece5;padding:2px 7px;border-radius:6px}}.signature{{min-width:0;max-width:100%;grid-column:1/-1;margin:5px 0;background:#f0eee7;padding:10px;border-radius:8px;overflow-x:auto}}.source-excerpt{{min-width:0;max-width:100%;grid-column:1/-1;margin-top:10px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#f4f2eb}}.source-excerpt>div{{min-width:0;display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 10px;padding:8px 12px;border-bottom:1px solid var(--line)}}.source-excerpt>div>*{{min-width:0;overflow-wrap:anywhere}}.source-excerpt small{{color:var(--muted)}}.source-excerpt pre{{min-width:0;max-width:100%;width:100%;margin:0;padding:12px;overflow-x:auto;font-size:13px;line-height:1.5}}.source-excerpt pre code{{display:block;width:max-content;min-width:100%;overflow-wrap:normal;word-break:normal}}.implementation-step{{min-width:0;max-width:100%;display:grid;grid-template-columns:45px minmax(0,1fr);gap:18px;padding:0 0 28px}}.step-index{{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;background:var(--green);color:white;font-weight:900}}.implementation-step h4,.reading-step h4{{margin:2px 0}}.implementation-step small,.reading-step small{{overflow-wrap:anywhere;color:var(--green);font-weight:800;text-transform:uppercase}}.trace-pair,.step-files{{min-width:0;max-width:100%;display:flex;gap:9px;flex-wrap:wrap;align-items:center}}.step-file{{max-width:100%;background:#eef2ed;padding:5px 9px;border-radius:7px;font-size:13px}}.reading-step{{min-width:0;max-width:100%;border-left:3px solid #b9c9bf;padding:0 0 20px 18px;margin-bottom:14px}}.reading-step p{{color:var(--muted)}}.relationship-grid{{min-width:0;max-width:100%;display:grid;gap:10px}}.relationship-group{{min-width:0;max-width:100%;border:1px solid var(--line);border-radius:12px;padding:0 16px}}.relationship-group summary,.all-files summary{{min-width:0;cursor:pointer;padding:15px 0;font-weight:800;display:flex;gap:10px;justify-content:space-between}}.relationship-group summary span,.all-files summary{{overflow-wrap:anywhere}}.relationship-group>p{{color:var(--muted)}}.relationship-row{{min-width:0;max-width:100%;padding:12px 0;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}}.relationship-row>div{{min-width:0;display:flex;gap:8px;flex-wrap:wrap}}.relationship-row small{{color:var(--muted);white-space:nowrap}}.arrow{{color:var(--muted)}}.empty-row{{list-style:none;padding:16px;color:var(--muted);background:#f1efe9;border-radius:10px;overflow-wrap:anywhere}}.warning{{color:var(--red)}}.all-files{{min-width:0;max-width:100%;margin-top:30px;border-top:1px solid var(--line)}}.back{{display:inline-block;margin-top:22px;color:var(--green);font-weight:800}}.decision{{margin-top:44px;background:#202c27;color:#fff;border-radius:22px;padding:32px}}.decision h2{{margin-top:0}}.decision ol{{padding-left:20px;color:#cbd7d1}}.empty-state{{grid-column:1/-1;background:var(--card);border:1px dashed var(--line);border-radius:18px;padding:32px;text-align:center}}
.symbol-row>div>*{{min-width:0}}.symbol-row>div strong{{max-width:100%;overflow-wrap:anywhere;word-break:break-word}}.symbol-row>div span{{flex:0 0 auto}}
@media(max-width:850px){{.summary-strip{{grid-template-columns:1fr 1fr}}.module-grid{{grid-template-columns:1fr 1fr}}.detail-head,.answer-first{{display:block}}.detail-head .confidence,.answer-first .status{{margin-top:14px}}}}
@media(max-width:580px){{.wrap{{width:min(100% - 24px,1180px)}}.hero{{padding:50px 0 34px}}.summary-strip,.module-grid{{grid-template-columns:1fr}}.module-detail{{padding:20px;border-radius:16px}}.file-row,.symbol-row,.slice-row{{display:block}}.file-row small,.symbol-row small,.slice-row>*{{display:block;margin-top:7px}}.relationship-row{{display:block}}.search-bar{{display:block}}.search-bar span{{display:block;margin-top:7px}}}}
</style></head><body>
<header class="hero"><div class="wrap"><span class="eyebrow">Repo Teacher · 功能到源码</span>
<h1>“{_escape(query)}”<br><em>候选实现面在哪里？</em></h1>
<p>目录同名只代表名称证据。报告把跨层源码切片、已解析关系链、启发式阅读顺序和测试关联分开呈现。</p>
<div class="summary-strip"><div><small>仓库</small><strong>{_escape(project.get("name") or "repository")}</strong></div>
<div><small>索引文件</small><strong>{_number(stats.get("files"))}</strong></div>
<div><small>索引符号</small><strong>{_number(stats.get("symbols"))}</strong></div>
<div><small>候选实现面</small><strong>{len(modules)}</strong></div></div></div></header>
<main class="wrap"><section class="answer-first"><div><h2>{_escape(status_title)}</h2>
<p>{_escape(resolution.get("summary") or "没有定位摘要。")}</p></div><span class="status">{_escape(status)}</span></section>
<section id="module-index"><div class="search-bar"><input id="module-search" type="search" placeholder="在源码切片、文件和核心符号中搜索…" aria-label="搜索能力实现面"><span id="search-count" aria-live="polite">{len(modules)} 个结果</span></div>
<div class="module-grid">{cards}</div></section>{details}
<section class="decision"><h2>如何正确使用这份结果</h2><ol>
<li><code>exact_name_match</code> 只表示唯一产品目录 basename 同名，绝不表示功能已确定。</li>
<li>优先看已解析实现链；启发式阅读顺序不能用来断言运行时行为。</li>
<li>测试静态关联不等于测试覆盖或通过，更不能直接证明可生产复用。</li>
</ol></section></main>
<script>(()=>{{const input=document.getElementById('module-search');const count=document.getElementById('search-count');const cards=[...document.querySelectorAll('.module-card')];if(!input||!count)return;input.addEventListener('input',()=>{{const q=input.value.trim().toLocaleLowerCase();let visible=0;for(const card of cards){{const match=!q||(card.dataset.search||'').includes(q);card.hidden=!match;if(match)visible++;}}count.textContent=visible+' 个结果';}});}})();</script>
</body></html>'''
