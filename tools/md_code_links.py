#!/usr/bin/env python3
"""md_code_links.py — 把 markdown 里的 `文件:行号` 引用转成本地代码跳转链接。

用法：
    python md_code_links.py MD_FILE [REPO_ROOT] [--prefix PREFIX] [--alias NAME=PATH ...]
                             [--dry-run] [--max-line-delta N]

- MD_FILE  : 待处理的 markdown 文件（原地改写；--dry-run 只打印计划）
- REPO_ROOT: 代码仓根目录。默认 = md 所在目录向上找 .git 的第一站；
             显式给出时路径优先按仓根解析，失败再按 md 目录解析。
- --prefix : 主包目录名。仅当裸 basename 解析不到且无 alias 时尝试，
             对每个目录级联尝试 `<dir>/<prefix>/<basename>`。
- --alias  : 人工消歧，可重复。NAME=PATH 表示 "文档里写 NAME 时按 PATH 解析"。
             例：--alias driver.py=loopx/control_plane/turn_driver/driver.py
- --dry-run: 不写文件，打印每条引用的解析结果与失败清单
- --max-line-delta: 行号超界时允许的回退余量，默认 80 行

转换规则：
    `loopx/cli.py:880`  →  [`loopx/cli.py:880`](../../../loopx/cli.py#L880)

只在 VS Code / GitHub / GitLab / Typora 等支持 #L 锚点的查看器里生效。
纯文本查看器里保持原样可读。链接是普通 markdown，不影响 HTML 渲染。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# 文件引用的显式后缀——只有带这些后缀的 token 才尝试链接化
SUFFIXES = (
    ".py", ".rs", ".go", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt", ".rb",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".swift", ".scala", ".sh",
    ".sql", ".css", ".scss", ".html", ".md", ".toml", ".yaml", ".yml",
    ".json", ".jsonc", ".xml", ".txt", ".cfg", ".ini", ".lock",
)

# `path/to/file.py:12` / `file.py:12-18` / `file.py:L12` —— 整个 token 含在反引号里
REF_RE = re.compile(
    r"`((?:[A-Za-z0-9._\-]+/)*[A-Za-z0-9._\-]+\.(?:" + "|".join(
        re.escape(s.lstrip(".")) for s in SUFFIXES) + r")(?::L?\d+(?:-\d+)?)?)`"
)
# 从引用里拆出路径与行号（行号可选；支持多段 "12,23-25" / "7-9,23-32"）
PARTS_RE = re.compile(r"^(.+?)(?::L?\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)?$")

# 裸引用（无反引号）：路径 + 必须带行号（可多段），如 pyproject.toml:5-14 / README.md:7-9,23-32
PLAIN_RE = re.compile(
    r"(?<![\w`/.\-])((?:[A-Za-z0-9._\-]+/)*[A-Za-z0-9._\-]+\.(?:" + "|".join(
        re.escape(s.lstrip(".")) for s in SUFFIXES) + r"))((?::L?\d+(?:-\d+)?)(?:,\d+(?:-\d+)?)*)"
)
# 行内 code span（`...`）——PLAIN 轮要排除
CODESPAN_RE = re.compile(r"`[^`\n]*`")

# 已是 markdown 链接的引用（避免重复包链）—— `[text](url)` 或 `[`ref`](...)`
LINKED_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")


def strip_code_fences(text: str):
    """返回与 text 等长的掩码串：代码围栏/缩进代码块区间为 '#'，其余为 ' '。"""
    mask = [" "] * len(text)
    lines = text.split("\n")
    pos = 0
    in_fence = False
    fence_marker = ""
    for line in lines:
        stripped = line.lstrip()
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_marker = stripped[:3]
            for i in range(pos, pos + len(line) + 1):
                mask[i] = "#"
        elif in_fence:
            for i in range(pos, pos + len(line) + 1):
                mask[i] = "#"
            if stripped.startswith(fence_marker):
                in_fence = False
        else:
            indented_code = (len(line) - len(stripped) >= 4
                             and stripped and not stripped.startswith("#"))
            # 只遮缩进代码块的首行判定过于粗糙——本工具主战场是行内反引号引用，
            # 缩进块里出现 `file:line` 反引号的场景极少，忽略即可。
            if indented_code:
                for i in range(pos, pos + len(line) + 1):
                    mask[i] = "#"
        pos += len(line) + 1
    return "".join(mask)


class Resolver:
    def __init__(self, repo_root: Path, md_dir: Path, prefix: str | None,
                 aliases: dict[str, str], max_line_delta: int,
                 exclude_dirs: tuple[str, ...] = ("deprecate",)):
        self.root = repo_root
        self.md_dir = md_dir
        self.prefix = prefix
        self.aliases = aliases
        self.delta = max_line_delta
        self.exclude = set(exclude_dirs)
        self._basename_cache: dict[str, list[Path]] = {}
        self._resolve_cache: dict[str, tuple[str, str] | None] = {}

    def _candidate_paths(self, ref_path: str) -> list[str]:
        """给定文档里写的路径，产出按优先级排列的候选真实路径。"""
        cands: list[str] = []
        aliases = [self.aliases.get(Path(ref_path).name)] if self.aliases else []
        alias_full = self.aliases.get(ref_path)
        for a in (alias_full, *aliases):
            if a:
                cands.append(a)
        cands.append(ref_path)
        if self.prefix:
            # `dir/basename` 找不到时级联尝试 `dir/prefix/basename`
            p = Path(ref_path)
            if p.parent != Path("."):
                cands.append(str(p.parent / self.prefix / p.name))
        return cands

    def _find_by_basename(self, name: str) -> list[Path]:
        if name in self._basename_cache:
            return self._basename_cache[name]
        banned = {".git", "node_modules", *self.exclude}
        hits = [p for p in self.root.rglob(name)
                if not banned & set(p.parts)]
        self._basename_cache[name] = hits
        return hits

    def resolve(self, ref: str) -> tuple[str, str] | None:
        """解析一条引用（路径或路径:行号）→ (绝对路径, 相对路径)。alias 按完整键优先。"""
        # 0) 带行号的 alias 精确命中（如 cli.py:314=loopx/cli.py）
        if ref in self.aliases:
            p = self.root / self.aliases[ref]
            if p.is_file():
                return (str(p), self.aliases[ref])
        m = PARTS_RE.match(ref)
        if not m:
            return None
        ref_path = m.group(1)
        key = ref_path
        if key in self._resolve_cache:
            cached = self._resolve_cache[key]
            if cached is not None:
                return cached
            # None 可能只是行号超界——重算一次

        result: tuple[str, str] | None = None
        for cand in self._candidate_paths(ref_path):
            # a) 按仓根解析
            p = self.root / cand
            if p.is_file():
                result = (str(p), cand)
                break
            # b) 按 md 所在目录解析
            p = self.md_dir / cand
            if p.is_file():
                result = (str(p), cand)
                break
        if result is None:
            # c) 裸 basename（含歧义 basename）：alias > 仓根同名 > 全仓唯一
            hits = self._find_by_basename(ref_path)
            if ref_path == "README.md":
                root_readme = self.root / "README.md"
                if root_readme.is_file():
                    hits = [root_readme]
            if len(hits) == 1:
                result = (str(hits[0]), str(hits[0].relative_to(self.root)))
            elif ref_path in self.aliases and len(hits) > 1:
                # alias 未通过候选路径命中（路径不对），按文件名再试一次
                pass
        if result is None and self.md_dir.joinpath(ref_path).is_file():
            # md 所在目录兜底（处理 report/report.md 这类报告互链）
            result = (str(self.md_dir / ref_path), ref_path)

        self._resolve_cache[key] = result
        if result is None:
            return None
        # 行号越界检查：首个行号超出文件行数 + 余量则放弃（防漂移行号）
        lm = re.match(r"^.*?:L?(\d+)", ref)
        if lm:
            line = int(lm.group(1))
            try:
                total = sum(1 for _ in open(result[0], encoding="utf-8", errors="ignore"))
            except OSError:
                total = None
            if total is not None and line > total + self.delta:
                self._resolve_cache[key] = None
                return None
        return result


def make_link(absolute: Path, ref_text: str, md_file: Path, anchor_raw: str) -> str:
    """ref_text: 显示文本；anchor_raw: ':880' / ':12-18' / ':7-9,23-32' / ''"""
    rel = os.path.relpath(absolute, md_file.parent)
    if not anchor_raw:
        return f"[`{ref_text}`]({rel})"
    anchor = anchor_raw.replace(":", "#L").replace(",", "-L")
    return f"[`{ref_text}`]({rel}{anchor})"


def rewrite(text: str, md_file: Path, resolver: Resolver,
            dry_run: bool) -> tuple[str, int, list[str], set[str]]:
    mask = strip_code_fences(text)
    linked_spans = [(m.start(), m.end()) for m in LINKED_RE.finditer(text)]
    codespan_spans = [(m.start(), m.end()) for m in CODESPAN_RE.finditer(text)]

    def blocked(pos: int, *, codes: bool = True) -> bool:
        if mask[pos] == "#":
            return True
        spans = linked_spans + (codespan_spans if codes else [])
        return any(s <= pos < e for s, e in spans)

    # 轮 1：反引号引用（可无行号）。
    # 注意：不查 codespan 掩码——轮 1 的匹配本身就从反引号开始，查了必然自杀；
    # 已成链接的（[...](...)）由 linked_spans 拦截；代码围栏由 mask 拦截。
    hits: list[tuple[int, int, str, str]] = []  # start, end, ref, anchor_raw
    for m in REF_RE.finditer(text):
        if blocked(m.start(), codes=False):
            continue
        hits.append((m.start(), m.end(), m.group(1), ""))
    # 轮 2：裸引用（必须带行号）。反引号区间的 lookbehind 已排除，
    # codespan 掩码再兜底一次（防 REF_RE 未覆盖的形态）。
    for m in PLAIN_RE.finditer(text):
        s, e = m.start(1), m.end(2)
        if blocked(m.start(1)):
            continue
        hits.append((s, e, m.group(1) + m.group(2), m.group(2)))

    hits.sort()
    out: list[str] = []
    failed: list[str] = []
    done: set[str] = set()
    pos = 0
    n_linked = 0
    prev_end = -1
    for s, e, ref, anchor_raw in hits:
        if s < prev_end:
            continue
        hit = resolver.resolve(ref)  # 完整引用（含行号）——alias 可精确命中
        if hit is None:
            # 退回按裸路径解析（行号仅用于锚点）
            hm = PARTS_RE.match(ref)
            if hm:
                hit = resolver.resolve(hm.group(1))
        if hit is None:
            failed.append(ref)
            continue
        absolute, rel = hit
        out.append(text[pos:s])
        out.append(make_link(Path(absolute), ref, md_file, anchor_raw))
        pos = e
        prev_end = e
        n_linked += 1
        done.add(rel)
    out.append(text[pos:])

    new_text = "".join(out)
    return new_text, n_linked, failed, done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md_file")
    ap.add_argument("repo_root", nargs="?")
    ap.add_argument("--prefix")
    ap.add_argument("--alias", action="append", default=[],
                    help="NAME=PATH 人工消歧，可重复")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-line-delta", type=int, default=80)
    ap.add_argument("--exclude-dir", action="append", default=["deprecate"],
                    help="basename 搜索时排除的目录名，可重复（默认 deprecate）")
    args = ap.parse_args(argv)

    aliases: dict[str, str] = {}
    for a in args.alias:
        if "=" not in a:
            sys.exit(f"--alias 需要 NAME=PATH 形式，收到: {a}")
        k, v = a.split("=", 1)
        aliases[k.strip()] = v.strip()

    md_file = Path(args.md_file).expanduser().resolve()
    if not md_file.is_file():
        sys.exit(f"md 文件不存在: {md_file}")
    if args.repo_root:
        repo_root = Path(args.repo_root).expanduser().resolve()
    else:
        repo_root = md_file.parent
        for p in [md_file.parent, *md_file.parent.parents]:
            if (p / ".git").exists():
                repo_root = p
                break

    text = md_file.read_text(encoding="utf-8")
    resolver = Resolver(repo_root, md_file.parent, args.prefix, aliases,
                        args.max_line_delta, tuple(args.exclude_dir))
    new_text, n_linked, failed, done = rewrite(text, md_file, resolver, args.dry_run)

    print(f"解析成功 {n_linked} 条 / 失败 {len(failed)} 条")
    if failed:
        print("\n失败清单（保持原样未链接）:")
        for f in sorted(set(failed)):
            print(f"  - {f}")
    if done:
        print(f"\n涉及文件 {len(done)} 个:")
        for d in sorted(done):
            print(f"  - {d}")

    if args.dry_run:
        print("\n(dry-run，未写入)")
        return 0
    md_file.write_text(new_text, encoding="utf-8")
    print(f"\n已写入: {md_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
