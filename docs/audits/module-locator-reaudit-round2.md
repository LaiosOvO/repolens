# 命名功能 / ACP → 模块实现详情：最终独立复审（Round 2）

- 复审日期：2026-08-10
- 复审范围：`module_locator.py`、`module_report.py`、`explain` CLI、TypeScript import resolver、对应测试
- 基线：SourceBridge、OpenWiki、Understand Anything、CodeBoarding、DeepWiki-Open、PocketFlow Code2Tutorial 六个完整本地 clone
- 约束：本复审不修改产品代码或正式 examples
- 最终判定：**REQUEST CHANGES**

## 结论先行

功能定位的核心正确性门已经通过：六仓严格 golden 从 5/6 提升到 **6/6**；OpenWiki `src/cli/runners.ts:33` 中的 `../visualize/server.js` 已通过受控 `.js → .ts/.tsx` 规则解析到 `src/visualize/server.ts`，并真正进入 confirmed implementation trace，六个文件也合并成一个已解析 component。完整重建的六仓结果均能定位真实跨目录 surface/slices；同名、模糊、不存在、根目录和辅助目录查询均保持 fail-safe，没有把名称证据提升为“功能已验证”。

但当前仍不能标记为生产完成：

1. 六份真实 HTML 在 390px 视口下有 **5/6 页面级横向溢出**，最严重的 SourceBridge 页宽达 1515px。这不是字段密度建议，而是用户在手机上必须横向滚动才能阅读的可用性缺陷。
2. 最新的 validator 收紧后，当前重建的 SourceBridge、CodeBoarding 和 PocketFlow 索引分别有 5、1、1 个 `unsupported-feature-confidence` 错误；OpenWiki 原有的 `executable-file-marker` 合同问题已修复并复验为 0 errors。这三仓的错误不改变模块定位结果，但与本轮“当前索引 validate”发布门冲突，因此不能隐藏。

## 六仓完整重建矩阵

本轮直接对 `/Volumes/T7/workspace/ontology/graph/repo/*` 调用当前 `build_index()`，没有复用正式 examples 里的旧 JSON。

| 仓库 / 查询 | 真实实现面 | 已解析链 / component | 测试证据 | 当前 validate | 功能 golden |
|---|---|---:|---:|---:|---|
| SourceBridge / `knowledge` | `internal/knowledge` + `workers/knowledge` + admin knowledge UI；39 个产品文件 | 40 / 10 | 42 resolved / 0 structural | 5 errors，1 dirty-worktree warning | **PASS** |
| OpenWiki / `visualize` | `src/visualize` + `src/cli/runners.ts`；6 文件 | 6 / 1 | 5 / 1 | **0 errors, 0 warnings** | **PASS** |
| Understand Anything / `viewer` | `understand-anything-plugin/packages/viewer`；3 文件 | 0 / 3 isolated | 0 / 1 | **0 / 0** | **PASS（诚实降级）** |
| CodeBoarding / `static_analyzer` | 唯一产品目录；48 文件 | 40 / 1 | 68 / 4 | 1 error | **PASS** |
| DeepWiki-Open / `codemap` | service、router、schema、Ask、CodeMap、CodeViewer、WebSocket；7 slices | 28 / 3 | 0 / 0 | **0 / 0** | **PASS** |
| PocketFlow / `tutorial` | 根目录 `main.py + flow.py + nodes.py` | 18 / 1 | 0 / 0 | 1 error | **PASS** |

六个结果的 `verified_capability_surface` 均为 false。这是正确的保守合同：它们是有源码证据的候选实现面，不是系统自动宣称功能语义已被证明。

### OpenWiki 上一轮阻断已关闭

- 真实源码：`src/cli/runners.ts:33` import `../visualize/server.js`；`src/visualize/server.ts` 为仓内真实源文件。
- resolver：`indexer.py:749-785` 仅对同仓 JavaScript/TypeScript 相对 import 尝试 `.ts/.tsx/.js/.jsx/index.*` 受控替代。
- 真实重放：`runners.ts:33 → visualize/server.ts:1` 以 `import / resolved-graph-topology` 进入 trace；component 由原先 2 个合并为 1 个。
- 合成回归：`tests/test_indexer.py:649-670` 直接断言 `.js` specifier 的 target path 为 `.ts` 源文件。

## P0

**无功能定位 P0。**

上两轮的三个 P0 仍保持关闭：

- `exact_name_match` 仅为唯一产品目录 basename 证据，`is_exact=false` 且 `verified_capability_surface=false`（`module_locator.py:993-1115`）。
- 实现面支持 directory/file/root-file/跨前后端 slices；六仓基准映射在 `module_locator.py:81-144`，并且只有身份验证通过时才进入 `reference_alignment`（`module_locator.py:236-283`）。
- 测试分为 resolved relationship 和 structural-only 两组，没有纯名称匹配充当测试证据（`module_locator.py:785-824`）。

## P1 — 发布阻断

### P1-1 六仓真实模块报告在 390px 下 5/6 出现页面级横向溢出

Playwright 使用本机 Chrome、viewport `390×844` 打开六份本轮现场渲染的 HTML，并比较 `documentElement.clientWidth / scrollWidth`：

| HTML | viewport | page scrollWidth | 结果 |
|---|---:|---:|---|
| SourceBridge knowledge | 390 | **1515** | FAIL |
| CodeBoarding static_analyzer | 390 | **999** | FAIL |
| DeepWiki codemap | 390 | **748** | FAIL |
| PocketFlow tutorial | 390 | **717** | FAIL |
| OpenWiki visualize | 390 | **592** | FAIL |
| Understand Anything viewer | 390 | 390 | PASS |

溢出集中在 trace 和 source excerpt：`.implementation-step` 使用 `grid-template-columns:45px 1fr`，右侧 grid item 保留了内容的 intrinsic minimum width；长路径、hash header 和代码片段因而把整页撑宽。`pre { overflow:auto }` 并不能抵消父 grid item 的 `min-width:auto`。相关 CSS 集中在 `module_report.py:398-400`。

修复不应只加 `body{overflow-x:hidden}` 遮盖问题。至少需要：

1. 将 trace grid 改为 `45px minmax(0,1fr)`，并对关键 grid/flex 子项设置 `min-width:0`；
2. 路径、hash 和关系摘要允许断行，`pre` 只在自身内滚动；
3. 增加一条真正用 `render_module_report()` + headless browser 的 390px 页面级 overflow 回归，不能只断言 HTML 里存在 `@media`。当前 `tests/test_module_report.py:50` 仅检查媒体查询字符存在，没有验证布局行为。

### P1-2 当前六仓索引只有 3/6 通过 validator

最后一次完整重建的现行结果：

- OpenWiki、Understand Anything、DeepWiki：0 errors；
- SourceBridge：5 个 `unsupported-feature-confidence` + dirty-worktree warning；
- CodeBoarding：1 个 `unsupported-feature-confidence`；
- PocketFlow：1 个 `unsupported-feature-confidence`。

失败证据均是 `confidence='exact-entry'`，但 evidence analyzer 为 `go-lexer-fallback[package=...]+executable-marker` 或 `python-ast+executable-marker`，不在当前 validator 的精确允许合同内。这是 feature/validation 边界而非 module locator 排序错误；但本轮验收明确要求“当前索引 validate”，因此在 6/6 归零前不能标记生产 PASS。

## 已通过的专项检查

### 功能与失败安全

- 六个完整 clone 的期望跨目录 surface/slices：**6/6**。
- 辅助目录：PocketFlow `docs` 和 `FastAPI` 均为 `not_found`，同名 docs 只记录到 `excluded_auxiliary_matches`。
- 不存在查询与根目录 `.`：均为 `not_found`。
- 重复 basename：两个产品 `acp` 目录返回 `composite_candidate`，不是 exact；`examples/acp` 被排除。
- 模糊文件名：只返回 `candidate`，`verified_capability_surface=false`。

### 证据、URI 和报告语义

- 六仓核心文件全部通过当前文件 hash freshness gate；本轮采样的所有 `source_uri` 均为无 authority 的 `file:` URI、位于对应项目根目录内且目标存在。
- 卡片 `#module-001` 与详情 id 成对；六仓 HTML 的内部锚点没有 broken target。
- 源码链接只打开文件；`path:line` 由报告中的 snippet + file/snippet SHA-256 锚定，文案没有伪装成编辑器行跳转。
- 入站、出站、内部和 unresolved 关系分开展示；unresolved 不计入依赖结论。
- 没有符号、trace 或测试的 slice 会显示缺口，不会伪造。DeepWiki 的两个 TSX slice 当前无可用符号；Understand Anything viewer 没有跨文件 trace，这些都被诚实降级。

## 六仓参考机制采用结论

| 参考仓 | 本地已进入执行路径的机制 | 未实现的边界 | 判定 |
|---|---|---|---|
| SourceBridge | 文件+行范围、真实路径限制、hash freshness gate | 完整 LLM Code Tour 质量门 | 核心证据合同已采用 |
| PocketFlow | slices → relationships → topological trace → render | LLM 章节生成 | 结构流程已采用 |
| OpenWiki | stable IDs、links/backlinks 分桶、root-safe URI、CLI→server 真实 import 链 | 交互式 graph UI | 点名关键链已闭环 |
| Understand Anything | Kahn 拓扑排序、cycle fallback、isolated node 诚实降级 | 完整 ontology/tour 产品模型 | 算法思路已采用 |
| CodeBoarding | symbol relationship graph + connected components | LSP lifecycle、hierarchy、Leiden clustering | 轻量替代，不是完整复用 |
| DeepWiki | 跨层 composite surface + 真实 snippet grounding | 问题驱动 RAG、skeleton→enrich | 数据合同部分采用 |

## 测试证据

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_module_locator tests.test_module_report tests.test_cli \
  tests.test_indexer.IndexerTest.test_typescript_js_import_specifier_resolves_to_repository_ts_source -v
=> 21 tests, OK
```

这 21 个测试覆盖 exact-name 语义、辅助目录排除、多切片、根目录功能、测试关联、hash freshness、URI containment、HTML escaping、CLI 生成以及 `.js → .ts` resolver。

## 下一轮 PASS 条件

1. 六份真实模块 HTML 在 390px 下都满足 `documentElement.scrollWidth == clientWidth == 390`，并将这一浏览器断言加入测试。
2. 修复 grid/flex 的 intrinsic-width 问题；长路径、trace、hash 和 snippet 在卡片内断行或局部滚动，不允许用隐藏 body overflow 伪通过。
3. SourceBridge、CodeBoarding、PocketFlow 的当前索引恢复 0 validation errors；SourceBridge 的 dirty-worktree warning 可以保留，但不得是 error。
4. 修复后重跑六仓完整 clone 而不只跑合成 fixture，并保持 OpenWiki confirmed import edge、6/6 surface 与所有 URI/anchor 检查不回归。

在上述条件满足前，本模块可作为**源码证据充分的功能候选定位器**使用；但由于手机阅读及全链路 validation 尚未达到发布门，不能对外声称“生产级完成”。
