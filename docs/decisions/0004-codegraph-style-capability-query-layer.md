# ADR 0004：采用 CodeGraph 风格的能力图查询层

状态：Accepted  
日期：2026-08-11

## 决策

Repo Teacher 在 canonical index 之上生成一份确定性的 `capability-graph.json`，并提供：

- typed node / typed edge；
- bounded traversal；
- callers / callees；
- module dependency graph；
- change impact context；
- capability slice 与 connected component；
- `repo-teacher graph <index.json> [query]` 查询命令。

图层只产生**供模型审阅的结构候选和源码上下文**。它不能把目录、符号簇或入口自动升级成人类功能；最终功能仍由模型结合源码证据归纳，并由本地证据闭包校验。

## 为什么采用

原流程把文件、符号和 relationship 交给模型，但缺少稳定的“某个能力周围有哪些实现节点、调用者、下游依赖和影响范围”查询面。模型容易退化成顺序读取文件，或只看入口。

CodeGraph 的价值不在 UI，而在于先把这些关系变成可重复查询的图合同。Repo Teacher 复用这个合同后，模型看到的是 feature slice、模块依赖、caller/callee 和影响上下文，不是无边界的文件清单。

## 一手参考

本机完整参考仓：`/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai`

- AI query engine：`/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/crates/codegraph-server/src/ai_query/engine.rs`
  - `get_callers` / `get_callees`
  - `traverse_graph`
  - impact-related query
- index state：`/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/crates/codegraph-server/src/index_state.rs`
- 工具合同总览：`/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/README.md`

## 实现映射

| CodeGraph 机制 | Repo Teacher 实现 | 采用程度 |
|---|---|---|
| typed graph | `src/repo_teacher/capability_graph.py::build_capability_graph` | 已采用 |
| bounded traversal | `traverse_graph` | 已采用；校验方向、深度和数量 |
| callers / callees | `get_callers` / `get_callees` | 已采用；只有 call-like edge，`contains` 不冒充调用 |
| dependency graph | `get_dependency_graph` | 已采用；聚合模块间 resolved edge |
| impact query | `analyze_impact` | 已采用；返回直接上下游和受影响模块 |
| natural-language explore | `explore_capability_graph` | 已采用轻量本地查询；无 embedding |
| graph context for LLM | `graph_prompt_context` | 已采用；候选只进入模型上下文 |
| persistent graph store | 无 | 不采用 |
| Rust server / 38 languages | 无 | 不采用 |
| MCP / IDE server | 无 | 延后 |
| embedding / semantic search | 无 | 延后 |

## 产物与命令

建立索引会在同一 immutable generation 发布：

```text
index.json
index.html
capability-graph.json
generation-manifest.json
```

查询示例：

```bash
repo-teacher graph output/index.json memory --depth 2 --output memory-graph.json
```

结果同时包含 query matches、callers、callees、dependency view 和 impact context，便于模型或人继续下钻。

## 明确拒绝

- 拒绝用 connected component 的名字直接生成产品功能：结构相连不等于用户能力相同。
- 拒绝把 `contains` 当作 caller/callee：父子声明关系不是调用。
- 拒绝为首期引入独立图数据库、远程服务和 embedding：canonical index 已经拥有足够事实，先证明报告价值。
- 拒绝复制 CodeGraph UI：当前主产品是人类功能报告和 CLI 查询，不是 IDE 插件。

## 验证

- `tests/test_capability_graph.py`：6 tests PASS。
- `tests/test_cli.py::test_index_publishes_capability_graph_and_graph_query`：PASS。
- 全量：295 tests PASS（1 项可选 gopls skip）。
- Waku 正式报告从 212 files / 1,557 symbols / 9,879 relationships 的验证索引生成。

## 剩余风险

- 当前图按运行时内存构建，超大仓的 graph JSON 大小和查询内存仍需 benchmark。
- JavaScript/Go/Python 的 resolved edge 质量决定图质量；unknown edge 必须保持 unknown。
- capability candidate 仍需要模型阅读源码；图只能缩小搜索面，不能代替语义理解。
