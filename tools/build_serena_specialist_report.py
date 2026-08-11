#!/usr/bin/env python3
"""Build a current, human-first Serena specialist report from its source tree."""

from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path
import re
import subprocess


APP_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = APP_ROOT.parents[1]
SERENA_ROOT = WORKSPACE / "repo" / "serena"
OUTPUT = WORKSPACE / "biz" / "docs" / "html" / "serena-specialist.html"


def _git(*args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(SERENA_ROOT), *args),
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result.stdout.strip()


def _source(path: str, pattern: str, *, label: str, span: int = 24) -> dict[str, object]:
    source = SERENA_ROOT / path
    lines = source.read_text(encoding="utf-8").splitlines()
    matcher = re.compile(pattern)
    start = next((position for position, line in enumerate(lines, 1) if matcher.search(line)), 0)
    if not start:
        raise RuntimeError(f"source anchor not found: {path} / {pattern}")
    end = min(len(lines), start + span)
    snippet = "\n".join(lines[start - 1 : end])
    return {
        "path": path,
        "label": label,
        "start": start,
        "end": end,
        "uri": f"{source.as_uri()}#L{start}-L{end}",
        "sha": hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
    }


def _link(item: dict[str, object]) -> str:
    return (
        f'<a class="source" href="{escape(str(item["uri"]), quote=True)}">'
        f'<b>{escape(str(item["label"]))}</b>'
        f'<code>{escape(str(item["path"]))}:{item["start"]}-{item["end"]}</code>'
        f'<small>range sha256 {escape(str(item["sha"]))}</small></a>'
    )


def build_html() -> str:
    head = _git("rev-parse", "HEAD")
    remote = _git("remote", "get-url", "origin")
    dirty = bool(_git("status", "--porcelain"))
    license_text = (SERENA_ROOT / "LICENSE").read_text(encoding="utf-8", errors="replace")
    license_name = "MIT" if "MIT License" in license_text else "未识别"

    overview = _source(
        "src/serena/tools/symbol_tools.py",
        r"^class GetSymbolsOverviewTool\b",
        label="文件级符号概览",
    )
    find_symbol = _source(
        "src/serena/tools/symbol_tools.py",
        r"^class FindSymbolTool\b",
        label="按 name path 查符号",
        span=30,
    )
    references = _source(
        "src/serena/tools/symbol_tools.py",
        r"^class FindReferencingSymbolsTool\b",
        label="查找真实代码引用",
        span=32,
    )
    implementations = _source(
        "src/serena/tools/symbol_tools.py",
        r"^class FindImplementationsTool\b",
        label="实现与声明查询",
        span=72,
    )
    replace_body = _source(
        "src/serena/tools/symbol_tools.py",
        r"^class ReplaceSymbolBodyTool\b",
        label="符号体替换",
        span=34,
    )
    rename = _source(
        "src/serena/tools/symbol_tools.py",
        r"^class RenameSymbolTool\b",
        label="语义重命名",
        span=34,
    )
    lsp = _source(
        "src/solidlsp/ls.py",
        r"^class SolidLanguageServer\b",
        label="多语言 LSP 抽象",
        span=48,
    )
    mcp = _source(
        "src/serena/mcp.py",
        r"^\s+def create_mcp_server\b",
        label="MCP 工具发布",
        span=38,
    )
    memory = _source(
        "src/serena/memories/memory_manager.py",
        r"^class MemoryManager\b",
        label="项目记忆管理（不是代码引用）",
        span=45,
    )
    security = _source(
        "docs/02-usage/070_security.md",
        r"^### A Functionality Boundary, Not a Containment Boundary",
        label="trusted project 不是沙箱",
        span=22,
    )

    mechanisms = (
        (
            "01",
            "理解一个文件与定位符号",
            "先请求文件顶层 symbol overview，再用 name path 做全仓或目录内符号搜索；结果来自语言服务器而不是文本 grep。",
            "LSP document symbols · name path · kind filters · result limits",
            "作为选定模块后的精确下钻层；不要用它代替仓库级功能发现。",
            (overview, find_symbol),
        ),
        (
            "02",
            "查询引用、声明与实现",
            "把目标符号交给语言服务器，分别请求 references、declaration 和 implementation，并返回引用所在符号与源码位置。",
            "textDocument/references · declaration · implementation · filesystem sync",
            "适合回答改动影响谁；不等于已经拥有可持久化、可跨版本比较的调用图。",
            (references, implementations),
        ),
        (
            "03",
            "符号级编辑与重构",
            "先用符号身份锁定编辑对象，再执行 replace body 或 LSP rename；编辑工具可结合 diagnostics，但仍需测试与工作区隔离。",
            "symbol identity · workspace edit · diagnostics · rename",
            "复用操作接口和失败检查；不要把编辑能力误当执行沙箱或审批系统。",
            (replace_body, rename),
        ),
        (
            "04",
            "多语言语义后端",
            "SolidLSP 统一语言服务器生命周期、文档符号缓存和不同语言适配器；每种语言仍有各自能力与准确率边界。",
            "LSP process · versioned symbol cache · per-language adapter",
            "借鉴统一接口和依赖固定策略；必须逐语言做准确率与失败降级验证。",
            (lsp,),
        ),
        (
            "05",
            "把语义工具暴露给 Agent",
            "MCP 层把经过配置筛选的 Serena tools 发布给客户端，使 Agent 可以按需调用符号查询和编辑。",
            "MCP · tool registry · project activation · tool filtering",
            "用作本地编码 Agent 的语义工具适配层；不负责动态多 Agent 编排。",
            (mcp,),
        ),
        (
            "06",
            "项目记忆与安全边界",
            "MemoryManager 管理项目/全局 Markdown 记忆和引用完整性；这不是代码 symbol reference。官方安全模型信任机器、客户端和仓库，trusted-project 只是功能门，不是 containment。",
            "Markdown memory · reference integrity · trust gating · external sandbox",
            "记忆可独立借鉴；运行 Serena 时仍需外部容器/沙箱、工具审批和网络边界。",
            (memory, security),
        ),
    )

    cards = []
    details = []
    for number, title, mechanism, technology, reuse, sources in mechanisms:
        cards.append(
            f'<a class="feature" href="#mechanism-{number}"><small>功能 {number}</small>'
            f'<h3>{escape(title)}</h3><p>{escape(mechanism)}</p><strong>查看实现与源码 →</strong></a>'
        )
        details.append(
            f'<article class="mechanism" id="mechanism-{number}"><header><small>MECHANISM {number}</small>'
            f'<h2>{escape(title)}</h2></header><div class="explain"><div><b>底层怎么做</b><p>{escape(mechanism)}</p></div>'
            f'<div><b>关键技术</b><p>{escape(technology)}</p></div><div><b>我们的采用边界</b><p>{escape(reuse)}</p></div></div>'
            f'<div class="sources">{"".join(_link(source) for source in sources)}</div></article>'
        )

    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Serena · 功能、底层实现与复用边界</title><style>
:root{{--ink:#17141d;--muted:#68616f;--line:#ded9e4;--paper:#fbfaf6;--violet:#6548a4;--soft:#f0ebfa}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}a{{color:inherit}}code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}}.shell{{width:min(1120px,100%);margin:auto;padding:44px 24px 80px}}.hero{{display:grid;grid-template-columns:1.35fr .65fr;gap:28px;padding:40px 0 54px;border-bottom:1px solid var(--line)}}.eyebrow,small{{color:var(--violet);font-weight:850;letter-spacing:.1em}}h1{{margin:15px 0;font-size:clamp(3.2rem,8vw,7rem);line-height:.88;letter-spacing:-.07em}}.lead{{max-width:760px;font-size:1.28rem}}.identity{{align-self:end;padding:22px;border:1px solid var(--line);background:var(--soft)}}.identity dl{{display:grid;grid-template-columns:70px 1fr;gap:8px;margin:0}}.identity dd{{margin:0;overflow-wrap:anywhere}}.verdict{{margin:34px 0;padding:22px;border-left:5px solid var(--violet);background:#fff}}.verdict b{{display:block;font-size:1.2rem}}.features{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:28px 0 64px}}.feature{{display:flex;min-height:260px;flex-direction:column;padding:22px;border:1px solid var(--line);background:#fff;text-decoration:none}}.feature:hover{{border-color:var(--violet);background:var(--soft)}}.feature h3{{font-size:1.35rem;line-height:1.18}}.feature p{{color:var(--muted)}}.feature strong{{margin-top:auto;color:var(--violet)}}.mechanism{{padding:54px 0;border-top:1px solid var(--line);scroll-margin-top:20px}}.mechanism h2{{margin:10px 0 25px;font-size:clamp(2rem,5vw,4rem);line-height:1}}.explain{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line)}}.explain>div{{padding:22px;background:#fff}}.explain p{{margin:8px 0 0;color:var(--muted)}}.sources{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:14px}}.source{{display:grid;min-width:0;max-width:100%;gap:5px;padding:14px;background:#1c1921;color:#f8f3ff;text-decoration:none}}.source>*{{min-width:0;max-width:100%;overflow-wrap:anywhere;word-break:break-word}}.source code{{color:#e1d5f4}}.source small{{font-size:9px;color:#aa9bbd}}footer{{margin-top:54px;padding-top:24px;border-top:1px solid var(--line);color:var(--muted)}}@media(max-width:720px){{.shell{{padding:26px 14px 60px}}.hero,.features,.explain,.sources{{grid-template-columns:1fr}}.identity{{align-self:auto}}.feature{{min-height:0}}h1{{font-size:4rem}}}}
</style></head><body><main class="shell"><section class="hero"><div><div class="eyebrow">SPECIALIST REFERENCE · LIVE SEMANTICS</div><h1>Serena</h1><p class="lead">先说它能做什么：在你已经选定功能或模块之后，用实时语言服务器精确查询符号、引用、声明、实现和诊断，并执行符号级编辑。</p></div><aside class="identity"><dl><dt>HEAD</dt><dd><code>{escape(head)}</code></dd><dt>Origin</dt><dd>{escape(remote)}</dd><dt>License</dt><dd>{escape(license_name)}</dd><dt>状态</dt><dd>{'dirty' if dirty else 'clean · full clone'}</dd></dl></aside></section>
<section class="verdict"><b>一句话技术选型结论</b>Repo Teacher 的持久索引先回答“项目有哪些功能、每个功能怎样实现”；Serena 再回答“选定模块里的符号现在在哪里、谁引用它、怎样安全修改”。采用它的开源 LSP 核心，不把它当持久代码图、动态工作流或沙箱；付费 JetBrains 能力单独评估。</section>
<section><div class="eyebrow">WHAT IT PROVIDES</div><h2>这个项目有哪些功能？</h2><div class="features">{''.join(cards)}</div></section>{''.join(details)}
<footer>固定源码版本：<code>{escape(head)}</code> · 所有判断都链接到当前完整 clone 的源码范围；range sha256 只证明该范围未漂移，不证明运行时、性能或生产安全。</footer></main></body></html>'''


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build_html(), encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
