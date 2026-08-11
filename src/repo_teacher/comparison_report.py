from __future__ import annotations

import html
import json
import math
from collections.abc import Iterable, Mapping
from typing import Any


def _escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _safe_json(value: Any) -> str:
    """Serialize data for an application/json script without creating HTML tokens."""

    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _items(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Mapping):
        return list(value.values())
    if isinstance(value, Iterable):
        return list(value)
    return [value]


def _display(value: object) -> str:
    if isinstance(value, Mapping):
        preferred = [value.get(key) for key in ("title", "name", "step", "description")]
        parts = [str(part) for part in preferred if part not in (None, "")]
        return " — ".join(dict.fromkeys(parts)) if parts else json.dumps(value, ensure_ascii=False, default=str)
    return str(value if value is not None else "")


def _score(value: object) -> float:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(result):
        return 0.0
    return min(100.0, max(0.0, result))


def _score_label(value: object) -> str:
    score = _score(value)
    return str(int(score)) if score.is_integer() else f"{score:.1f}"


def _render_tags(value: object) -> str:
    tags = [item for item in (_display(raw).strip() for raw in _items(value)) if item]
    if not tags:
        return '<span class="empty-inline">未标注技术栈</span>'
    return "".join(f'<span class="tag">{_escape(tag)}</span>' for tag in tags)


def _render_list(value: object, empty: str, *, ordered: bool = False, css_class: str = "") -> str:
    values = [item for item in (_display(raw).strip() for raw in _items(value)) if item]
    if not values:
        return f'<p class="empty-inline">{_escape(empty)}</p>'
    tag = "ol" if ordered else "ul"
    class_name = f' class="{css_class}"' if css_class else ""
    return f"<{tag}{class_name}>" + "".join(f"<li>{_escape(item)}</li>" for item in values) + f"</{tag}>"


_DIMENSION_LABELS = {
    "semantic_precision": "语义精度",
    "semantic-precision": "语义精度",
    "evidence": "证据可追溯",
    "evidence_quality": "证据质量",
    "evidence_traceability": "证据可追溯",
    "tutorial_quality": "教程表达",
    "incremental": "增量更新",
    "incremental_efficiency": "增量效率",
    "visualization": "可视化",
    "production_readiness": "生产准备度",
    "reuse_value": "架构参考价值",
    "deployability": "部署成本",
    "reuse": "复用价值",
    "maintainability": "可维护性",
    "test_coverage": "测试保障",
}


def _render_dimensions(value: object) -> str:
    if not isinstance(value, Mapping) or not value:
        return '<p class="empty-inline">暂无分维度评分</p>'
    rows: list[str] = []
    for raw_name, raw_score in value.items():
        name = str(raw_name)
        label = _DIMENSION_LABELS.get(name.lower(), name.replace("_", " "))
        score = _score(raw_score)
        rows.append(
            '<div class="dimension">'
            f'<span>{_escape(label)}</span><i aria-hidden="true"><b style="width:{score:g}%"></b></i>'
            f'<strong>{_score_label(raw_score)}</strong>'
            "</div>"
        )
    return "".join(rows)


def _render_source_paths(option: Mapping[str, Any]) -> str:
    references = _records(option.get("source_references"))
    if not references:
        paths = [item for item in (_display(raw).strip() for raw in _items(option.get("source_paths"))) if item]
        references = [{"path": path} for path in paths]
    if not references:
        return '<p class="empty-inline">尚未绑定源码入口</p>'
    rows: list[str] = []
    for reference in references:
        path = reference.get("path") or "未标注路径"
        start = reference.get("line_start")
        end = reference.get("line_end")
        location = str(path)
        if isinstance(start, int) and start > 0:
            location += f":{start}" + (f"-{end}" if isinstance(end, int) and end != start else "")
        uri = reference.get("source_uri")
        source_link = (
            f'<a href="{_escape(uri)}" title="打开本地源码"><code>{_escape(location)}</code></a>'
            if isinstance(uri, str) and uri.startswith("file://")
            else f'<code>{_escape(location)}</code>'
        )
        evidence_count = len(_items(reference.get("evidence_ids")))
        symbol_count = len(_items(reference.get("symbol_ids")))
        scope = reference.get("reference_scope") or "file"
        evidence_scope = reference.get("evidence_scope") or "context"
        claim = reference.get("claim") or "未声明该范围支持的具体事实。"
        digest = reference.get("snippet_sha256")
        claim_id = reference.get("claim_evidence_id")
        support = "可支撑该条 claim" if reference.get("supports_claim") else "仅作上下文，不等价于事实证据"
        digest_html = f" · sha256 {_escape(str(digest)[:12])}" if digest else ""
        claim_html = f" · Claim EvidenceRef {_escape(claim_id)}" if claim_id else ""
        rows.append(
            f'<li>{source_link}<p>{_escape(claim)}</p><small>{_escape(scope)} / {_escape(evidence_scope)} · '
            f'{_escape(support)}{digest_html}{claim_html} · index EvidenceRef {evidence_count} · symbol {symbol_count}</small></li>'
        )
    return '<ul class="source-list">' + "".join(rows) + "</ul>"


def _render_option(option: Mapping[str, Any], candidate: bool) -> str:
    project_name = option.get("project_name") or option.get("title") or "未命名方案"
    score = _score_label(option.get("score"))
    recommendation_badge = '<span class="recommended">默认场景首选</span>' if candidate else ""
    confidence = option.get("confidence")
    confidence_html = f'<span class="confidence">{_escape(confidence)}</span>' if confidence else ""
    summary = option.get("summary") or "暂无方案摘要。"
    approach = option.get("approach") or "尚未归纳技术路线。"
    verdict = option.get("architecture_reference") or option.get("reuse_verdict") or "尚未形成架构参考结论。"
    report_href = option.get("project_report_href")
    project_title = (
        f'<a href="{_escape(report_href)}">{_escape(project_name)}</a>'
        if isinstance(report_href, str) and report_href.startswith("projects/")
        else _escape(project_name)
    )
    comparison_class = option.get("comparison_class") or "未分类技术对象"
    uncertainty = option.get("score_uncertainty")
    signal_label = f"人工信号 ±{_escape(uncertainty)}" if uncertainty is not None else "人工信号"
    remote = option.get("remote") or "未记录 remote"
    commit = option.get("commit") or "未记录 commit"
    license_name = option.get("license") or "未知"
    code_reuse_status = option.get("code_reuse_status") or "needs-license-review"
    return f'''<article class="option-card{' winner' if candidate else ''}">
      <div class="option-head"><div>{recommendation_badge}<p class="option-kicker">{_escape(comparison_class)}</p><h3>{project_title}</h3></div><div class="score"><strong>{score}</strong><span>{signal_label}</span></div></div>
      <p class="summary">{_escape(summary)}</p>
      <div class="snapshot"><span>{_escape(remote)}</span><code>{_escape(commit)}</code><b>License: {_escape(license_name)}</b></div>
      <section class="option-block route"><h4>底层技术路线</h4><p>{_escape(approach)}</p>{_render_list(option.get('data_flow'), '暂无数据流说明', ordered=True, css_class='data-flow')}</section>
      <section class="option-block"><h4>关键技术</h4><div class="tag-list">{_render_tags(option.get('technology_tags'))}</div></section>
      <section class="option-block"><h4>源码落点（可点击）</h4>{_render_source_paths(option)}</section>
      <div class="pros-cons"><section><h4>优势</h4>{_render_list(option.get('strengths'), '暂无优势说明')}</section><section><h4>局限</h4>{_render_list(option.get('limitations'), '暂无局限说明')}</section></div>
      <section class="option-block dimensions"><h4>人工 rubric 判断（不是 benchmark）</h4>{_render_dimensions(option.get('dimension_scores'))}</section>
      <section class="verdict"><span>架构参考价值</span><p>{_escape(verdict)}</p><small>直接代码复用：{_escape(code_reuse_status)}</small>{confidence_html}</section>
    </article>'''


def _option_lookup(comparison: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    raw_lookup = comparison.get("options_by_id")
    if isinstance(raw_lookup, Mapping):
        for key, value in raw_lookup.items():
            if isinstance(value, Mapping):
                lookup[str(key)] = dict(value)
    for option in _records(comparison.get("options")):
        identifier = option.get("id")
        if identifier is not None:
            lookup.setdefault(str(identifier), option)
    return lookup


def _capability_options(capability: Mapping[str, Any], lookup: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [str(item) for item in _items(capability.get("option_ids"))]
    options = [lookup[identifier] for identifier in ids if identifier in lookup]
    if options:
        return options
    slug = capability.get("slug")
    return [option for option in lookup.values() if option.get("capability_slug") == slug]


def _candidate_ids(capability: Mapping[str, Any], options: list[dict[str, Any]]) -> set[str]:
    requested = {str(item) for item in _items(capability.get("recommendation_option_ids"))}
    if requested:
        return requested
    legacy = capability.get("recommendation_option_id")
    if legacy is not None:
        return {str(legacy)}
    winner = max(options, key=lambda option: _score(option.get("score")), default=None)
    return {str(winner.get("id"))} if winner else set()


def _scenario_records(capability: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = capability.get("scenario_recommendations")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): dict(value) for key, value in raw.items() if isinstance(value, Mapping)}


def _render_module_plan(value: object) -> str:
    rows: list[str] = []
    for item in _records(value):
        paths = [str(path) for path in _items(item.get("source_paths")) if str(path)]
        source_references = _records(item.get("source_references"))
        source_links: list[str] = []
        for reference in source_references:
            path = str(reference.get("path") or "")
            uri = reference.get("source_uri")
            start = reference.get("line_start")
            end = reference.get("line_end")
            location = path
            if isinstance(start, int) and start > 0:
                location += f":{start}" + (f"-{end}" if isinstance(end, int) and end != start else "")
            scope = reference.get("evidence_scope") or "context"
            source_links.append(
                f'<a href="{_escape(uri)}"><code>{_escape(location)}</code></a><small>{_escape(scope)}</small>'
                if isinstance(uri, str) and uri.startswith("file://")
                else f"<code>{_escape(location)}</code><small>{_escape(scope)}</small>"
            )
        rows.append(
            '<li><strong>{role} · {project}</strong>{paths}</li>'.format(
                role=_escape(item.get("role") or "参考"),
                project=_escape(item.get("project_name") or "未命名"),
                paths=(
                    "".join(source_links)
                    if source_links
                    else "".join(f"<code>{_escape(path)}</code>" for path in paths)
                    if paths
                    else '<span class="empty-inline">暂无模块路径</span>'
                ),
            )
        )
    return '<ul class="module-plan">' + "".join(rows) + "</ul>" if rows else '<p class="empty-inline">暂无模块借鉴计划</p>'


def _render_scenario_panes(capability: Mapping[str, Any], default_scenario: str) -> str:
    recommendations = _scenario_records(capability)
    if not recommendations:
        return ""
    panes: list[str] = []
    for scenario, recommendation in recommendations.items():
        hidden = "" if scenario == default_scenario else " hidden"
        panes.append(
            f'<div class="scenario-recommendation" data-scenario-pane="{_escape(scenario)}"{hidden}>'
            f'<div class="scenario-route"><span>推荐路线</span><strong>{_escape(recommendation.get("preferred_class") or "待判断")}</strong>'
            f'<em>{_escape(recommendation.get("confidence") or "需 PoC")}</em></div>'
            f'<div><span>首选 / 备选</span><strong>{_escape(recommendation.get("primary_projects") or "证据不足")}</strong>'
            f'<p>备选：{_escape(recommendation.get("alternative_projects") or "暂无")}</p></div>'
            f'<div><span>为什么</span><p>{_escape(recommendation.get("why") or "暂无解释")}</p>'
            f'<p class="tradeoff">关键限制：{_escape(recommendation.get("tradeoff") or "需 PoC")}</p></div>'
            f'<div class="scenario-modules"><span>建议借鉴的模块</span>{_render_module_plan(recommendation.get("module_plan"))}</div>'
            "</div>"
        )
    return "".join(panes)


def _render_route_matrix(options: list[dict[str, Any]], candidate_ids: set[str]) -> str:
    rows: list[str] = []
    for option in options:
        project = option.get("project_name") or "未命名项目"
        href = option.get("project_report_href")
        project_html = (
            f'<a href="{_escape(href)}">{_escape(project)}</a>'
            if isinstance(href, str) and href.startswith("projects/")
            else _escape(project)
        )
        candidate = '<span class="matrix-candidate">默认场景首选</span>' if str(option.get("id")) in candidate_ids else ""
        license_name = option.get("license") or "未知"
        rows.append(
            "<tr>"
            f"<td><strong>{project_html}</strong>{candidate}</td>"
            f"<td><code>{_escape(option.get('comparison_class') or '未分类')}</code></td>"
            f"<td>{_escape(option.get('summary') or '暂无方案摘要')}</td>"
            f"<td><b>{_score_label(option.get('score'))}</b><small>±{_escape(option.get('score_uncertainty') or '—')}</small></td>"
            f"<td>{_escape(license_name)}</td>"
            "</tr>"
        )
    if not rows:
        return '<p class="capability-empty">暂无路线摘要。</p>'
    return (
        '<div class="route-table-wrap"><table class="route-table"><thead><tr>'
        '<th>项目</th><th>技术对象</th><th>一句话路线</th><th>人工信号</th><th>License</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def _render_capability(
    capability: Mapping[str, Any],
    lookup: Mapping[str, dict[str, Any]],
    index: int,
) -> tuple[str, list[dict[str, Any]]]:
    options = _capability_options(capability, lookup)
    candidate_ids = _candidate_ids(capability, options)
    candidates = [option for option in options if str(option.get("id")) in candidate_ids]
    title = capability.get("title") or capability.get("slug") or f"功能 {index}"
    description = capability.get("description") or "暂无能力说明。"
    recommendation = capability.get("recommendation") or "先选择同类技术路线，再做源码核验和 PoC。"
    factors = _render_tags(capability.get("decision_factors"))
    cards = "".join(_render_option(option, str(option.get("id")) in candidate_ids) for option in options)
    if not cards:
        cards = '<div class="capability-empty">尚未找到与此功能绑定的实现方案。</div>'
    class_count = len({str(option.get("comparison_class") or "未分类") for option in options})
    candidate_names = " / ".join(str(option.get("project_name") or "未命名") for option in candidates) or "待补证据"
    matrix = _render_route_matrix(options, candidate_ids)
    default_scenario = str(capability.get("default_scenario") or "local-first-product")
    scenario_panes = _render_scenario_panes(capability, default_scenario)
    body = f'''<section class="capability" id="capability-{index}">
      <div class="capability-title"><span>{index:02d}</span><div><p>CAPABILITY</p><h2>{_escape(title)}</h2><div class="description">{_escape(description)}</div></div></div>
      <aside class="recommendation"><div><span>默认场景首选</span><strong>{_escape(candidate_names)}</strong><em>{class_count} 类技术对象</em></div><p>{_escape(recommendation)}</p><div class="factor-list">{factors}</div></aside>
      <div class="scenario-stack">{scenario_panes}</div>
      {matrix}
      <details class="option-details"><summary>展开具体实现、源码证据与复用边界 <span>{len(options)} 个方案</span></summary><div class="comparison-strip">{cards}</div></details>
    </section>'''
    return body, candidates


def render_comparison_report(comparison: dict[str, Any]) -> str:
    """Render a standalone, feature-first Chinese technology selection report."""

    data: Mapping[str, Any] = comparison if isinstance(comparison, Mapping) else {}
    capabilities = _records(data.get("capabilities"))
    lookup = _option_lookup(data)
    projects = _records(data.get("projects"))

    sections: list[str] = []
    recommendations: list[tuple[dict[str, Any], list[dict[str, Any]], int]] = []
    for index, capability in enumerate(capabilities, 1):
        section, candidates = _render_capability(capability, lookup, index)
        sections.append(section)
        recommendations.append((capability, candidates, index))

    nav = "".join(
        f'<a href="#capability-{index}"><b>{index:02d}</b><span>{_escape(capability.get("title") or capability.get("slug") or "未命名功能")}</span></a>'
        for capability, _, index in recommendations
    ) or '<span class="nav-empty">暂无功能维度</span>'
    project_names = [str(project.get("name") or project.get("path") or "未命名项目") for project in projects]
    project_line = " · ".join(project_names) if project_names else "暂无项目元数据"
    schema = data.get("schema_version") or "unknown"
    methodology = data.get("score_methodology") if isinstance(data.get("score_methodology"), Mapping) else {}
    rubric = methodology.get("levels") if isinstance(methodology.get("levels"), Mapping) else {}
    rubric_html = "".join(
        f'<li><strong>{_escape(level)}</strong><span>{_escape(description)}</span></li>'
        for level, description in rubric.items()
    ) or '<li><strong>未提供</strong><span>当前数据没有评分量表，不应据此排名。</span></li>'
    profiles = methodology.get("scenario_profiles") if isinstance(methodology.get("scenario_profiles"), Mapping) else {}
    default_scenario = str(methodology.get("default_scenario") or "local-first-product")
    profile_html = "".join(
        '<button class="scenario-button{active}" type="button" data-scenario-button="{key}" '
        'aria-pressed="{pressed}">{title}</button>'.format(
            active=" active" if str(key) == default_scenario else "",
            key=_escape(key),
            pressed="true" if str(key) == default_scenario else "false",
            title=_escape(value.get("title") if isinstance(value, Mapping) else key),
        )
        for key, value in profiles.items()
    ) or '<span class="empty-inline">未提供场景权重</span>'
    scenario_brief_groups: list[str] = []
    for scenario in profiles or {default_scenario: {}}:
        cards: list[str] = []
        for capability, candidates, index in recommendations:
            scenario_recommendation = _scenario_records(capability).get(str(scenario), {})
            primary = scenario_recommendation.get("primary_projects") or (
                " / ".join(str(item.get("project_name") or "未命名") for item in candidates) or "证据不足"
            )
            route = scenario_recommendation.get("preferred_class") or "路线待判断"
            cards.append(
                '<a class="decision-card" href="#capability-{index}"><span>{title}</span><strong>{primary}</strong>'
                '<small>{route}</small><em>{confidence}</em></a>'.format(
                    index=index,
                    title=_escape(capability.get("title") or capability.get("slug") or "未命名功能"),
                    primary=_escape(primary),
                    route=_escape(route),
                    confidence=_escape(scenario_recommendation.get("confidence") or "待评估"),
                )
            )
        hidden = "" if str(scenario) == default_scenario else " hidden"
        scenario_brief_groups.append(
            f'<div class="decision-grid" data-scenario-pane="{_escape(scenario)}"{hidden}>{"".join(cards)}</div>'
        )
    recommendation_cards = "".join(scenario_brief_groups) or '<p class="empty-state">当前没有可比较的功能。请先生成 capability 与 option 数据。</p>'
    catalog_revision = data.get("tool", {}).get("catalog_revision") if isinstance(data.get("tool"), Mapping) else None
    body_sections = "".join(sections)
    embedded_json = _safe_json(comparison)

    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>功能技术选型报告</title>
  <style>
    :root{{--paper:#f5f0e6;--sheet:#fffdf7;--ink:#132728;--muted:#667273;--line:#d6d1c5;--teal:#006e68;--teal-soft:#dcefeb;--orange:#dc5a2a;--orange-soft:#fbe7d9;--navy:#18334b;--shadow:0 28px 90px rgba(18,39,40,.11)}}
    *{{box-sizing:border-box}}html{{scroll-behavior:smooth;background:var(--paper)}}body{{margin:0;color:var(--ink);background:linear-gradient(90deg,transparent 49.9%,rgba(19,39,40,.035) 50%,transparent 50.1%),var(--paper);font:15px/1.68 "Songti SC","Noto Serif CJK SC",Georgia,serif}}a{{color:inherit}}code,.mono,.score,.capability-title>span,.option-kicker,.confidence{{font-family:"SFMono-Regular",Menlo,Consolas,monospace}}.shell{{width:min(1500px,100%);margin:auto;background:var(--sheet);box-shadow:var(--shadow)}}
    .topbar{{display:flex;justify-content:space-between;gap:20px;padding:14px 4vw;border-bottom:1px solid var(--line);font:750 11px/1.4 "SFMono-Regular",Menlo,monospace;letter-spacing:.1em}}.topbar span:last-child{{color:var(--muted)}}
    .hero{{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(250px,.5fr);gap:5vw;padding:70px 4vw 50px;border-bottom:1px solid var(--line)}}.eyebrow{{margin:0 0 18px;color:var(--orange);font:800 12px/1.4 "SFMono-Regular",Menlo,monospace;letter-spacing:.14em}}h1,h2,h3,h4,p{{overflow-wrap:anywhere}}h1{{max-width:950px;margin:0;font-size:clamp(3rem,7vw,6.8rem);line-height:.96;letter-spacing:-.075em}}.hero-copy{{max-width:780px;margin:28px 0 0;color:var(--muted);font-size:clamp(1rem,1.8vw,1.3rem)}}.hero-meta{{align-self:end;padding:22px;border-left:4px solid var(--orange);background:var(--orange-soft)}}.hero-meta strong{{display:block;font-size:2.8rem;line-height:1}}.hero-meta span{{display:block;margin-top:8px;color:var(--muted)}}.hero-meta p{{margin:18px 0 0;font-size:12px}}
    .quick{{padding:48px 4vw 56px;background:var(--navy);color:#f8f2e7}}.section-label{{margin:0 0 8px;color:#93cec5;font:800 11px/1.4 "SFMono-Regular",Menlo,monospace;letter-spacing:.15em}}.quick h2{{max-width:900px;margin:0;font-size:clamp(2rem,4vw,4rem);line-height:1.05;letter-spacing:-.045em}}.decision-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin-top:34px;background:rgba(255,255,255,.17);border:1px solid rgba(255,255,255,.17)}}.decision-card{{position:relative;min-height:185px;padding:20px;text-decoration:none;background:var(--navy);transition:background .2s,transform .2s}}.decision-card:hover,.decision-card:focus-visible{{z-index:1;background:#21445f;transform:translateY(-3px);outline:2px solid #93cec5}}.decision-card span,.decision-card strong,.decision-card small,.decision-card em{{display:block}}.decision-card span{{color:#aebfc8;font-size:12px}}.decision-card strong{{margin-top:18px;font-size:1.25rem}}.decision-card small{{margin-top:9px;color:#93cec5;font:700 10px/1.4 "SFMono-Regular",Menlo,monospace;overflow-wrap:anywhere}}.decision-card em{{position:absolute;right:18px;bottom:15px;left:18px;color:#f4a17f;font:700 10px/1.4 "SFMono-Regular",Menlo,monospace;font-style:normal}}
    .method{{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:40px;padding:45px 4vw;border-bottom:1px solid var(--line);background:#edf3ef}}.method h2{{margin:0;font-size:2rem}}.method p:not(.section-label){{color:var(--muted)}}.method ol{{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;margin:0;padding:1px;background:var(--line);list-style:none}}.method li{{padding:14px;background:var(--sheet)}}.method li strong,.method li span{{display:block}}.method li strong{{font:800 1.4rem/1 "SFMono-Regular",Menlo,monospace;color:var(--orange)}}.method li span{{margin-top:8px;font-size:11px;color:var(--muted)}}.scenario-button{{padding:8px 11px;border:1px solid #a4c9c2;background:#eef7f4;color:#075a57;font:750 11px/1.2 inherit;cursor:pointer}}.scenario-button.active{{background:var(--teal);color:#fff}}
    .feature-nav{{position:sticky;top:0;z-index:10;display:flex;gap:1px;overflow-x:auto;padding:0 4vw;border-bottom:1px solid var(--line);background:rgba(255,253,247,.96);backdrop-filter:blur(12px)}}.feature-nav a{{display:flex;flex:0 0 auto;gap:9px;align-items:center;padding:16px 18px;text-decoration:none;border-left:1px solid var(--line)}}.feature-nav a:last-child{{border-right:1px solid var(--line)}}.feature-nav b{{color:var(--orange);font:700 11px/1 "SFMono-Regular",Menlo,monospace}}.feature-nav span{{font-weight:750;white-space:nowrap}}.feature-nav a:hover,.feature-nav a:focus-visible{{background:var(--teal-soft);outline:none}}.nav-empty{{padding:16px;color:var(--muted)}}
    main{{padding:0 4vw 90px}}.capability{{scroll-margin-top:72px;padding:75px 0;border-bottom:1px solid var(--line)}}.capability-title{{display:grid;grid-template-columns:56px minmax(0,1fr);gap:20px;align-items:start}}.capability-title>span{{color:var(--orange);font-weight:800}}.capability-title p{{margin:0 0 8px;color:var(--teal);font:800 11px/1.4 "SFMono-Regular",Menlo,monospace;letter-spacing:.14em}}.capability-title h2{{margin:0;font-size:clamp(2.2rem,5vw,5rem);line-height:1;letter-spacing:-.06em}}.description{{max-width:800px;margin-top:16px;color:var(--muted);font-size:1.08rem}}
    .recommendation{{display:grid;grid-template-columns:minmax(180px,.32fr) minmax(260px,.68fr);gap:24px;margin:34px 0 12px;padding:20px 24px;border:1px solid #a4c9c2;background:var(--teal-soft)}}.recommendation>div:first-child{{display:grid;grid-template-columns:1fr auto;column-gap:12px}}.recommendation span,.scenario-recommendation span{{grid-column:1/-1;color:var(--teal);font-size:11px;font-weight:850;letter-spacing:.1em}}.recommendation strong{{font-size:1.35rem}}.recommendation em{{align-self:center;color:var(--orange);font:800 12px/1 "SFMono-Regular",Menlo,monospace;font-style:normal}}.recommendation p{{margin:0}}.factor-list{{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px;padding-top:14px;border-top:1px solid rgba(0,110,104,.18)}}.scenario-stack{{margin-bottom:26px}}.scenario-recommendation{{display:grid;grid-template-columns:.8fr .8fr 1.2fr 1.2fr;gap:1px;border:1px solid var(--line);background:var(--line)}}.scenario-recommendation>div{{padding:16px;background:#fff}}.scenario-recommendation strong{{display:block;margin-top:6px}}.scenario-recommendation p{{margin:6px 0 0;color:var(--muted);font-size:12px}}.scenario-recommendation .tradeoff{{color:#9a4526}}.scenario-route em{{display:block;margin-top:8px;color:var(--orange);font-size:10px;font-style:normal}}.module-plan{{margin:8px 0 0;padding:0;list-style:none}}.module-plan li+li{{margin-top:9px}}.module-plan strong,.module-plan code{{display:block}}.module-plan code{{margin-top:4px;padding:3px 5px;background:#f0eee7;font-size:9px;overflow-wrap:anywhere}}.module-plan small{{display:block;color:var(--muted);font:8px/1.3 "SFMono-Regular",Menlo,monospace}}
    .route-table-wrap{{overflow-x:auto;border:1px solid var(--line);background:#fff}}.route-table{{width:100%;min-width:850px;border-collapse:collapse}}.route-table th,.route-table td{{padding:13px 14px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}.route-table th{{background:#f0eee7;color:var(--teal);font-size:10px;letter-spacing:.08em}}.route-table td{{font-size:12px}}.route-table tbody tr:last-child td{{border-bottom:0}}.route-table td:first-child{{min-width:145px}}.route-table td:nth-child(2){{max-width:220px}}.route-table td:nth-child(3){{min-width:300px;color:var(--muted)}}.route-table td:nth-child(4) b,.route-table td:nth-child(4) small{{display:block}}.route-table td:nth-child(4) b{{color:var(--orange);font:800 1.2rem/1 "SFMono-Regular",Menlo,monospace}}.route-table td:nth-child(4) small{{margin-top:4px;color:var(--muted)}}.matrix-candidate{{display:block;width:max-content;margin-top:5px;padding:2px 5px;background:var(--teal-soft);color:var(--teal);font-size:9px;font-weight:800}}.option-details{{margin-top:16px;border:1px solid var(--line);background:#f6f4ed}}.option-details>summary{{display:flex;justify-content:space-between;gap:20px;padding:16px 18px;cursor:pointer;font-weight:800}}.option-details>summary span{{color:var(--muted);font:700 10px/1.5 "SFMono-Regular",Menlo,monospace}}.option-details[open]>summary{{border-bottom:1px solid var(--line)}}.comparison-strip{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;padding:16px}}.option-card{{display:flex;min-width:0;flex-direction:column;padding:26px;border:1px solid var(--line);background:#fff;box-shadow:0 10px 30px rgba(19,39,40,.045)}}.option-card.winner{{border-top:5px solid var(--teal);padding-top:22px}}.option-head{{display:flex;justify-content:space-between;gap:18px;align-items:start}}.recommended{{display:inline-flex;margin-bottom:10px;padding:4px 8px;background:var(--teal);color:white;font-size:10px;font-weight:850}}.option-kicker{{margin:0;color:var(--muted);font-size:10px;letter-spacing:.08em}}.option-head h3{{margin:5px 0 0;font-size:1.8rem;line-height:1.05;letter-spacing:-.04em}}.option-head h3 a{{text-decoration-thickness:1px;text-underline-offset:4px}}.score{{flex:0 0 auto;text-align:right;color:var(--orange)}}.score strong{{display:block;font-size:2rem;line-height:1}}.score span{{display:block;max-width:86px;margin-top:5px;font-size:9px;line-height:1.25}}.summary{{min-height:52px;margin:20px 0 4px;color:var(--muted)}}.snapshot{{display:grid;gap:4px;margin:12px 0;padding:10px;background:#f4f1e9;font:10px/1.45 "SFMono-Regular",Menlo,monospace}}.snapshot span,.snapshot code{{overflow-wrap:anywhere}}.snapshot b{{color:var(--teal)}}
    .option-block{{padding:18px 0;border-top:1px solid var(--line)}}.option-block h4,.pros-cons h4{{margin:0 0 9px;color:var(--teal);font-size:11px;letter-spacing:.08em}}.option-block p{{margin:0}}.data-flow{{position:relative;margin:16px 0 0;padding:0;list-style:none;counter-reset:flow}}.data-flow li{{position:relative;margin:0 0 0 12px;padding:0 0 17px 31px;border-left:1px solid #a9c9c4;counter-increment:flow}}.data-flow li:last-child{{padding-bottom:0}}.data-flow li::before{{content:counter(flow);position:absolute;left:-12px;top:0;display:grid;width:23px;height:23px;place-items:center;border-radius:50%;background:var(--teal);color:white;font:750 10px/1 "SFMono-Regular",Menlo,monospace}}.tag-list,.factor-list{{display:flex;flex-wrap:wrap;gap:6px}}.tag{{display:inline-flex;padding:5px 8px;border:1px solid #a4c9c2;background:#eef7f4;color:#075a57;font-size:11px;font-weight:750}}.source-list{{margin:0;padding:0;list-style:none}}.source-list li+li{{margin-top:6px}}.source-list a{{display:block;text-decoration:none}}.source-list a:hover code,.source-list a:focus-visible code{{background:var(--teal-soft);outline:2px solid var(--teal)}}.source-list code{{display:block;padding:7px 9px;background:#f0eee7;color:#253e4a;font-size:11px;line-height:1.5;overflow-wrap:anywhere}}.source-list p{{margin:4px 0;font-size:11px}}.source-list small{{display:block;margin:3px 0 0;color:var(--muted);font:9px/1.4 "SFMono-Regular",Menlo,monospace}}.pros-cons{{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:18px 0;border-top:1px solid var(--line)}}.pros-cons section{{padding:14px;background:#f3f5ef}}.pros-cons section:last-child{{background:#fbefea}}.pros-cons ul{{margin:0;padding-left:18px}}.pros-cons li+li{{margin-top:5px}}
    .dimension{{display:grid;grid-template-columns:minmax(95px,.8fr) minmax(80px,1fr) 34px;gap:9px;align-items:center;margin-top:8px;font-size:12px}}.dimension i{{height:6px;overflow:hidden;background:#e8e5dc}}.dimension i b{{display:block;height:100%;background:var(--orange)}}.dimension strong{{text-align:right;font:700 11px/1 "SFMono-Regular",Menlo,monospace}}.verdict{{position:relative;margin-top:auto;padding:18px;background:var(--navy);color:white}}.verdict>span{{color:#93cec5;font-size:10px;font-weight:850;letter-spacing:.12em}}.verdict p{{margin:8px 0 0}}.verdict small{{display:block;margin-top:10px;color:#c4d3d9}}.confidence{{display:inline-flex;margin-top:12px;padding:4px 7px;background:rgba(255,255,255,.1);font-size:10px}}.empty-inline,.empty-state,.capability-empty{{color:var(--muted)}}.empty-inline{{margin:0;font-size:12px}}.empty-state,.capability-empty{{padding:32px;border:1px dashed currentColor}}.closing{{margin-top:70px;padding:40px;background:var(--orange-soft)}}.closing h2{{margin:0;font-size:2.4rem}}.closing ol{{margin:20px 0 0;padding-left:22px}}.closing li+li{{margin-top:8px}}footer{{padding:22px 4vw;border-top:1px solid var(--line);color:var(--muted);font-size:12px}}
    [data-scenario-pane][hidden]{{display:none!important}}
    @media(max-width:1050px){{.decision-grid{{grid-template-columns:repeat(2,1fr)}}.hero{{grid-template-columns:1fr}}.hero-meta{{max-width:420px}}.method{{grid-template-columns:1fr}}.comparison-strip{{grid-template-columns:1fr}}.scenario-recommendation{{grid-template-columns:1fr 1fr}}}}
    @media(max-width:700px){{.topbar{{padding-inline:18px}}.topbar span:last-child{{text-align:right}}.hero,.quick,.method,main{{padding-left:20px;padding-right:20px}}h1{{font-size:3.25rem}}.decision-grid{{grid-template-columns:1fr}}.decision-card{{min-height:155px}}.method ol{{grid-template-columns:1fr}}.feature-nav{{padding-inline:0}}.capability{{padding:52px 0}}.capability-title{{grid-template-columns:36px 1fr}}.recommendation{{grid-template-columns:1fr;padding:18px}}.recommendation .factor-list{{grid-column:1}}.comparison-strip{{grid-template-columns:1fr;padding:10px}}.pros-cons,.scenario-recommendation{{grid-template-columns:1fr}}}}
    @media print{{body{{background:white}}.shell{{box-shadow:none}}.feature-nav{{display:none}}.quick{{background:white;color:var(--ink);border-bottom:2px solid var(--ink)}}.decision-card{{background:white;color:var(--ink);border:1px solid var(--line)}}.option-details{{border:0}}.option-details>summary{{display:none}}.comparison-strip{{display:block}}.option-card{{break-inside:avoid;margin:16px 0}}}}
  </style>
</head>
<body><div class="shell">
  <header class="topbar"><span>REPO TEACHER / TECHNOLOGY REVIEW</span><span>SCHEMA {_escape(schema)} · FEATURE FIRST</span></header>
  <section class="hero"><div><p class="eyebrow">从功能出发，而不是从项目出发</p><h1>技术选型<br>一眼看明白</h1><p class="hero-copy">每个功能先给出场景匹配的技术路线、首选/备选项目、可借鉴模块和关键限制；再展开人工 rubric 与源码证据。整文件或普通符号入口会明确标作上下文，不能冒充 claim 证据。</p></div><aside class="hero-meta"><strong>{len(capabilities)}</strong><span>个功能维度 · {len(lookup)} 个实现方案 · {len(projects)} 个参考项目</span><p>{_escape(project_line)}</p><p>Catalog {_escape(catalog_revision or 'unknown')}</p></aside></section>
  <section class="quick"><p class="section-label">30 SECOND BRIEF · DEFAULT {_escape(default_scenario)}</p><h2>每个能力先告诉你：选哪条路线、借哪些模块、为什么。</h2><div class="tag-list">{profile_html}</div>{recommendation_cards}</section>
  <section class="method"><div><p class="section-label">SCORING CONTRACT</p><h2>量表、场景与不确定性</h2><p>所有 curated 分值来自固定源码快照上的 reviewer judgment，不是性能实测。相差不超过声明不确定性的方案并列；不同 comparison class 不做总排名。</p><div class="tag-list">{profile_html}</div></div><ol>{rubric_html}</ol></section>
  <nav class="feature-nav" aria-label="功能导航">{nav}</nav>
  <main>{body_sections}<section class="closing"><p class="section-label">DECISION HANDOFF</p><h2>最后怎么用这份报告</h2><ol><li>先确定需求属于哪一种 comparison class，不跨类比较高低。</li><li>打开项目报告和具体源码文件，验证数据流、依赖与测试边界。</li><li>许可证未知时只做架构参考；直接复制代码前必须完成兼容性审查。</li><li>对仓库规模、语言、延迟与资源成本做小型 PoC，再记录最终 ADR。</li></ol></section></main>
  <footer>curated 身份直接读取源码根目录的真实 Git origin、HEAD 与必需源码 worktree bundle；不信任导入 JSON 的 remote/commit。人工 rubric 信号只用于缩小阅读范围；动态行为、性能和许可证必须单独验证。</footer>
</div><script id="comparison-data" type="application/json">{embedded_json}</script><script>
  (() => {{
    const buttons = [...document.querySelectorAll('[data-scenario-button]')];
    const panes = [...document.querySelectorAll('[data-scenario-pane]')];
    for (const button of buttons) {{
      button.addEventListener('click', () => {{
        const scenario = button.getAttribute('data-scenario-button');
        for (const peer of buttons) {{
          const active = peer.getAttribute('data-scenario-button') === scenario;
          peer.classList.toggle('active', active);
          peer.setAttribute('aria-pressed', String(active));
        }}
        for (const pane of panes) pane.hidden = pane.getAttribute('data-scenario-pane') !== scenario;
      }});
    }}
  }})();
</script></body>
</html>'''
