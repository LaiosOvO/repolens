#!/usr/bin/env python3
"""Build one offline HTML that preserves the repository-teaching research."""

from __future__ import annotations

from html import escape
from pathlib import Path

import markdown


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
OUTPUT = WORKSPACE / "biz" / "docs" / "html" / "repository-teaching-research.html"
SOURCES = (
    ROOT / "docs" / "research" / "human-readable-repository-teaching.md",
    ROOT / "docs" / "research" / "repository-teaching-skills-and-community.md",
)


def _render_markdown(path: Path) -> str:
    return markdown.markdown(
        path.read_text(encoding="utf-8"),
        extensions=("tables", "fenced_code", "toc", "sane_lists"),
        output_format="html5",
    )


def build() -> Path:
    reports = []
    for position, source in enumerate(SOURCES, start=1):
        reports.append(
            f'<details class="report" {"open" if position == 1 else ""}>'
            f'<summary>研究报告 {position} · {escape(source.stem)}</summary>'
            f'<div class="report-body">{_render_markdown(source)}</div></details>'
        )
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>代码仓库教学与技术选型 · 研究总览</title>
<style>
:root{{--ink:#14201b;--muted:#5b6861;--line:#d8ded9;--paper:#fbfaf5;--green:#175b46;--orange:#d86b31;--soft:#edf4ef}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.72 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
a{{color:var(--green);overflow-wrap:anywhere}}code,pre{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}.shell{{max-width:1180px;margin:auto;padding:44px 24px 80px}}
.hero{{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr);gap:30px;padding:38px 0 48px;border-bottom:1px solid var(--line)}}.eyebrow{{color:var(--orange);font-weight:850;letter-spacing:.12em;text-transform:uppercase;font-size:12px}}h1{{font-size:clamp(2.45rem,6vw,5.7rem);line-height:.98;letter-spacing:-.06em;margin:18px 0}}.lead{{font-size:clamp(1.05rem,2vw,1.35rem);color:var(--muted);max-width:760px}}
.verdict{{align-self:end;padding:24px;border:1px solid var(--line);border-radius:20px;background:var(--soft)}}.verdict b{{display:block;font-size:1.25rem;margin-bottom:9px}}.verdict p{{margin:0;color:var(--muted)}}
.section{{padding:54px 0;border-bottom:1px solid var(--line)}}h2{{font-size:clamp(1.8rem,4vw,3.3rem);letter-spacing:-.04em;margin:0 0 18px}}.cards{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}.card{{padding:22px;border:1px solid var(--line);border-radius:18px;background:#fff}}.card span{{color:var(--orange);font-size:11px;font-weight:850;letter-spacing:.08em}}.card h3{{margin:10px 0 8px;font-size:1.15rem}}.card p{{margin:0;color:var(--muted)}}
.matrix-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:18px;background:#fff}}table{{border-collapse:collapse;width:100%;min-width:780px}}th,td{{padding:15px 17px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{font-size:12px;color:var(--muted);background:#f2f4f0}}tr:last-child td{{border-bottom:0}}.adopt{{color:var(--green);font-weight:850}}.reference{{color:#8a552d;font-weight:850}}
.report{{margin:14px 0;border:1px solid var(--line);border-radius:18px;background:#fff;overflow:hidden}}.report>summary{{cursor:pointer;padding:20px 22px;font-weight:850;background:#f3f5f1}}.report-body{{padding:26px;min-width:0;max-width:100%;overflow-x:auto;overscroll-behavior-inline:contain}}.report-body table{{width:max-content;max-width:none}}.report-body h1{{font-size:2.5rem;line-height:1.08}}.report-body h2{{font-size:1.75rem;margin-top:50px}}.report-body h3{{margin-top:34px}}.report-body pre{{padding:16px;overflow:auto;background:#14201b;color:#f3f5f1;border-radius:12px}}.report-body blockquote{{margin:18px 0;padding:1px 18px;border-left:4px solid var(--orange);color:var(--muted)}}.report-body img{{max-width:100%}}
.sources{{display:flex;flex-wrap:wrap;gap:9px}}.sources a{{padding:9px 12px;border:1px solid var(--line);border-radius:999px;background:#fff;text-decoration:none;font-size:13px}}
@media(max-width:820px){{.hero,.cards{{grid-template-columns:1fr}}.shell{{padding:28px 14px 64px}}.report-body{{padding:18px}}h1{{font-size:2.7rem}}}}
</style></head><body><main class="shell">
<section class="hero"><div><div class="eyebrow">Repository Teaching Research · 2026-08-10</div><h1>先讲功能，再讲代码。</h1><p class="lead">这不是给生成器换皮肤。新的产品合同把代码仓库索引重排为：产品功能 → 底层机制 → 复用与限制 → 源码证据 → 跨项目技术选型。</p></div><aside class="verdict"><b>最终采用组合</b><p>DeepWiki / CodeWiki 的层级组织 + PocketFlow 的教学顺序 + CodeBoarding / CodeGraph 的静态证据 + GitNexus / RepoAgent 的影响与增量 + learn-codebase 的可选主动学习。</p></aside></section>
<section class="section"><div class="eyebrow">What changes</div><h2>入口不再冒充产品功能</h2><div class="cards">
<article class="card"><span>01 · CAPABILITY</span><h3>先回答项目能做什么</h3><p>首屏只展示 3–9 个主要功能、用户价值和适用边界；main、route、class 退到证据层。</p></article>
<article class="card"><span>02 · MECHANISM</span><h3>再说明底层怎么实现</h3><p>每个功能必须有数据流、组件角色、关键技术、失败路径和未知项，不能只有文件列表。</p></article>
<article class="card"><span>03 · DECISION</span><h3>最后支持技术选型</h3><p>同一功能跨仓比较主方案、备选方案、复用成本、不采用边界，并可回到固定源码行。</p></article>
</div></section>
<section class="section"><div class="eyebrow">Adoption matrix</div><h2>哪些能用，哪些只能参考</h2><div class="matrix-wrap"><table><thead><tr><th>参考</th><th>采用什么</th><th>不要误用</th><th>结论</th></tr></thead><tbody>
<tr><td>SourceBridge / CodeBoarding / CodeGraph</td><td>符号、调用、组件与证据下钻</td><td>图不是产品功能，也不证明运行时</td><td class="adopt">可做证据底座</td></tr>
<tr><td>PocketFlow / DeepWiki / CodeWiki</td><td>教学顺序、层级页面、父子综合</td><td>LLM 聚类必须回填源码闭包</td><td class="reference">组合采用</td></tr>
<tr><td>GitNexus / RepoAgent</td><td>impact、process、staleness、增量失效</td><td>GitNexus 为非商业许可；高置信图结论可能误导</td><td class="reference">协议参考</td></tr>
<tr><td>codebase-to-course</td><td>用户动作、代码白话、课程弧线</td><td>无许可证，不复制模板资产</td><td class="reference">UX 参考</td></tr>
<tr><td>learn-codebase / awesome-copilot</td><td>主动回忆、学习日志、Code Tour、短 Skill</td><td>教学是可选模式；过长 Skill 要拆分</td><td class="adopt">可复用 Skill 思路</td></tr>
<tr><td>Serena</td><td>选定模块后的 live symbol、reference、diagnostics 与语义编辑</td><td>项目记忆不是代码引用；trusted project 不是沙箱；不替代持久代码图</td><td class="adopt">专项采用 MIT LSP 核心</td></tr>
</tbody></table></div></section>
<section class="section"><div class="eyebrow">Local evidence</div><h2>完整研究报告</h2>{''.join(reports)}</section>
<section class="section"><div class="eyebrow">Open source references</div><h2>本轮新增项目</h2><div class="sources">
<a href="https://github.com/FSoft-AI4Code/CodeWiki">CodeWiki</a><a href="https://github.com/abhigyanpatwari/GitNexus">GitNexus</a><a href="https://github.com/codegraph-ai/CodeGraph">CodeGraph</a><a href="https://github.com/zarazhangrui/codebase-to-course">codebase-to-course</a><a href="https://github.com/ktaletsk/learn-codebase">learn-codebase</a><a href="https://github.com/github/awesome-copilot">awesome-copilot</a><a href="https://github.com/oraios/serena">Serena</a>
</div></section></main></body></html>"""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    print(build())
