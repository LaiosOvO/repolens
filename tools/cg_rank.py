#!/usr/bin/env python3
"""CodeGraph 排序器：基于参考实现蒸馏的加权 PageRank 文件/符号排序。

设计依据（来源与行号）：
- aider repomap.py:487-514 边权乘数——mentioned ×10、长特定名(snake/kebab/camel≥8字符) ×10、
  下划线私有 ×0.1、被 >5 文件定义 ×0.1、chat 文件 ×50、引用次数 sqrt 缩放。
- aider repomap.py:425-435 个性化向量——chat 文件/被提及文件/路径命中 ident 的文件获得 personalization。
- aider repomap.py:481-486 无引用定义补自环 weight=0.1（防零出度节点）。
- deepwiki-open codemap.py:174-180 LLM 行号不可信，用「逐字 snippet 反查真实行号」——本工具
  同样只信 DB 里的 file:line，不信任何 LLM 产出的行号。
- RepoAgent doc_meta_info.py:623-700 拓扑排序生成任务序（叶子先做，环检测 + second-best 破环）。

通用性：不包含任何仓库专用规则。输入为任意 codegraph.db。
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from collections import Counter, defaultdict


def load_graph(db_path: str):
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    # 符号定义节点（排除 import/file 等非定义节点）
    nodes = {}
    for rid, kind, name, fpath, sline, vis in db.execute(
        "SELECT id, kind, name, file_path, start_line, visibility FROM nodes "
        "WHERE kind IN ('function','method','struct','enum','trait','class','type_alias')"
    ):
        nodes[rid] = (kind, name, fpath, sline, vis)

    # 引用边：referencer(文件) --ident--> definer(文件)，借 calls/references/instantiates
    calls = defaultdict(Counter)  # (src_file) -> {dst_file: count} 聚合用
    ident_defs = defaultdict(set)  # ident_name -> {definer files}
    ident_refs = defaultdict(list)  # ident_name -> [referencer files]

    rows = db.execute(
        "SELECT source, target FROM edges WHERE kind IN ('calls','references','instantiates')"
    )
    src_kind = {}
    for src, dst in rows:
        s = nodes.get(src)
        d = nodes.get(dst)
        if not s or not d:
            continue
        src_file, dst_file = s[2], d[2]
        if src_file == dst_file:
            continue
        ident = d[1]
        ident_defs[ident].add(dst_file)
        ident_refs[ident].append(src_file)
        calls[src_file][dst_file] += 1
    db.close()
    return nodes, calls, ident_defs, ident_refs


def edge_multiplier(ident: str, num_definers: int, mentioned: set[str]) -> float:
    """aider repomap.py:487-499 的边权乘数（通用规则，无仓库特判）。"""
    mul = 1.0
    is_snake = ("_" in ident) and any(c.isalpha() for c in ident)
    is_kebab = ("-" in ident) and any(c.isalpha() for c in ident)
    is_camel = any(c.isupper() for c in ident) and any(c.islower() for c in ident)
    if ident in mentioned:
        mul *= 10
    if (is_snake or is_kebab or is_camel) and len(ident) >= 8:
        mul *= 10
    if ident.startswith("_") or ident.startswith("__"):
        mul *= 0.1
    if num_definers > 5:
        mul *= 0.1
    return mul


def build_and_rank(nodes, calls, ident_defs, ident_refs, seed_files=None, top_n=30):
    """加权 PageRank（aider personalization 版），返回文件排名与关键符号。

    工程化修正（相对 aider 原版）：超常见符号（如 Rust 的 new/Default）会因
    definers×referencers 笛卡尔积导致边数爆炸（10 万+ 边/符号）。这里对每个
    ident 设组合预算：超出时只保留引用次数最多的前 100 个 referencer——与
    aider「>5 定义处 ×0.1 降权」同一意图（低信息量引用不主导图），且把边聚
    合成 DiGraph 单边（权重相加），内存与 PageRank 耗时可控。
    """
    try:
        import networkx as nx
    except ImportError:
        sys.exit("需要 networkx：pip install networkx")

    seed_files = set(seed_files or [])
    G = nx.DiGraph()
    files = set(calls.keys())
    for c in calls.values():
        files.update(c.keys())

    # personalization：seed 文件获得权重（aider: chat_fnames → 100/len(fnames)）
    personalize = 100.0 / max(len(files), 1)
    personalization = {f: personalize for f in seed_files} or None

    COMBO_BUDGET = 2000
    TOP_REFERENCERS = 100
    agg = {}  # (src,dst) -> weight
    agg_ident = {}  # (src,dst) -> dominant ident（用于符号归因）

    for ident, definers in ident_defs.items():
        ref_counter = Counter(ident_refs.get(ident, []))
        if not ref_counter:
            for d in definers:
                key = (d, d)
                agg[key] = agg.get(key, 0.0) + 0.1  # aider 自环
                agg_ident.setdefault(key, ident)
            continue
        mul = edge_multiplier(ident, len(definers), seed_files)
        combos = len(ref_counter) * len(definers)
        referencers = ref_counter.most_common()
        if combos > COMBO_BUDGET:
            referencers = referencers[:TOP_REFERENCERS]
        for referencer, num_refs in referencers:
            for definer in definers:
                if referencer == definer:
                    continue
                w = mul * math.sqrt(num_refs)  # aider:509-514 sqrt 缩放
                key = (referencer, definer)
                agg[key] = agg.get(key, 0.0) + w
                # 记录权重最大的归因符号
                if key not in agg_ident or w > agg.get(key, 0) * 0.5:
                    agg_ident[key] = ident

    for (s, d), w in agg.items():
        G.add_edge(s, d, weight=w)

    try:
        if personalization:
            ranked = nx.pagerank(G, weight="weight", personalization=personalization,
                                 dangling=personalization)
        else:
            ranked = nx.pagerank(G, weight="weight")
    except ZeroDivisionError:
        ranked = nx.pagerank(G, weight="weight")

    # rank 分摊回符号：src_rank × edge_weight / out_total（aider:520-530），
    # 归因用该文件对上的主导 ident
    ranked_defs = defaultdict(float)
    for src in G.nodes:
        out = list(G.out_edges(src, data=True))
        if not out:
            continue
        total = sum(d["weight"] for _, _, d in out)
        for _, dst, d in out:
            ranked_defs[(dst, agg_ident.get((src, dst), "?"))] += \
                ranked[src] * d["weight"] / total

    top_files = sorted(ranked.items(), key=lambda x: -x[1])[:top_n]
    top_syms = sorted(ranked_defs.items(), key=lambda x: -x[1])[:top_n]
    return top_files, top_syms


def main():
    ap = argparse.ArgumentParser(description="codegraph 加权 PageRank 排序器（通用）")
    ap.add_argument("db", help="codegraph.db 路径")
    ap.add_argument("--seeds", nargs="*", default=[], help="入口/seed 文件（获得 personalization）")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    nodes, calls, ident_defs, ident_refs = load_graph(args.db)
    print(f"图规模：{len(nodes)} 定义节点，{sum(sum(c.values()) for c in calls.values())} 跨文件引用边",
          file=sys.stderr)
    top_files, top_syms = build_and_rank(nodes, calls, ident_defs, ident_refs,
                                         seed_files=args.seeds, top_n=args.top)
    print("\n== TOP 文件（L3 深读候选）==")
    for f, r in top_files:
        print(f"  {r:.6f}  {f}")
    print("\n== TOP 符号（进 learning.md 的关键抽象）==")
    for (f, ident), r in top_syms:
        print(f"  {r:.6f}  {f} :: {ident}")


if __name__ == "__main__":
    main()
