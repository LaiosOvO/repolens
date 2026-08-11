# 命名功能 / 模块定位修复与六仓机制对照

- 修复日期：2026-08-10
- 修复范围：`module_locator.py`、`module_report.py`、模块/HTML/CLI 测试
- 对应审计：`docs/audits/module-locator-audit.md`
- 当前状态：**已提交独立复审，本文不声明生产完成**

## 结论先行

本轮把领域对象从“一个功能等于一个目录”改成了 `CapabilitySurface` 风格的候选实现面：一个结果可包含 directory、file、root-file 和跨前后端的多个 implementation slices。`exact_name_match` 现在只表示“唯一产品源码目录 basename 同名”，机器字段和 HTML 均明确 `verified_capability_surface=false`，不再将名称证据提升成功能已确定。

报告同时分开四类信息：

1. source slices：候选实现边界；
2. component boundaries：仅由已解析边构造的连通分量；
3. implementation trace：仅由已解析 call/import/reference 等边做拓扑排序，cycle 单独标记 fallback；
4. heuristic reading order：按文件职责组织的阅读建议，明确不是运行时/调用/数据流。

测试也分成“已解析静态关联”和“明确镜像/嵌套路径候选”。纯字符串 `name-match` 已删除，任何一组都不再被描述成测试覆盖或测试已通过。

## P0 / P1 修复映射

| 原审计项 | 修复 | 本地实现 | 回归证据 |
|---|---|---|---|
| P0-1 名称 exact 被提升成功能确定 | 状态改成 `exact_name_match`；增加 `verified_capability_surface=false`；docs/tests/generated 等辅助路径不能 exact | `module_locator.py:220-227,855-967`；`module_report.py:349-397` | `test_directory_name_exact_is_not_capability_verification`、`test_docs_only_exact_name_is_not_a_product_result` |
| P0-2 单目录模型 | `slices[]` 支持 directory/file/root-file；六仓基线可组合跨层实现面 | `module_locator.py:81-158,389-418,563-787` | `test_product_directories_form_composite_and_auxiliary_name_is_excluded`、六仓 golden |
| P0-3 测试误绑 | 删除 name-match；只保留 resolved relationship，或单列 explicit-subpath / mirrored-test-path 结构候选 | `module_locator.py:542-560,672-716`；`module_report.py:329-334` | `test_unrelated_test_name_never_becomes_test_evidence` |
| P1-1 固定阅读顺序冒充实现 | 新增已解析 trace；阅读顺序保持 `heuristic_reading_order` 并单独展示 | `module_locator.py:466-513,515-594`；`module_report.py:311-321` | ACP trace/reading kind assertions；HTML semantic assertions |
| P1-2 unresolved 混入依赖 | 分为 resolved_internal / inbound / outbound / unresolved；报告给 resolved ratio，unresolved 只作诊断 | `module_locator.py:602-636,736-765`；`module_report.py:321-328` | ACP relationship bucket assertions、六仓真实探针 |
| P1-3 path:line 只开文件 | 明确链接行为是 opens-file；报告内保存行范围、源码片段、snippet hash/file hash freshness gate | `module_locator.py:305-355,421-466`；`module_report.py:43-100,174-187` | `test_report_separates_name_match_trace_reading_and_test_association` |
| P1-4 六仓机制未落地 | 增加六仓 source-audited surface、图组件边界、拓扑 trace、真实片段 grounding 与稳定 ID | `module_locator.py:81-158,515-640` | `test_six_reference_repository_golden_surfaces` + 真实六仓索引探针 |

## 六个参考仓库的具体机制与采用程度

### 1. SourceBridge：行级 Code Tour 合同与 evidence gate

- 参考源码：`workers/knowledge/code_tour.py:37-49` 的 `file_path + line_start + line_end`；`workers/knowledge/code_tour.py:128-180` 的真实路径过滤和 evidence gate。
- 本地采用：每个核心符号与关系端点保存 `path/line_start/line_end/snippet/snippet_sha256/file_sha256/fresh`。只有文件哈希仍匹配索引快照才展示片段；路径被规范化并限制在 project root。
- 差异：本地模块定位是确定性静态分析，不生成 LLM code-tour 文案，所以没有照搬它的 LLM confidence floor。

### 2. PocketFlow Code2Tutorial：能力抽象 → 关系 → 顺序

- 参考源码：`flow.py:12-32` 的 `FetchRepo → IdentifyAbstractions → AnalyzeRelationships → OrderChapters → WriteChapters → CombineTutorial`。
- 本地采用：先确定 source slices，再分析已解析关系、构造 component、拓扑排序 trace，最后渲染 HTML；`tutorial` 的能力面明确包含根目录 `main.py / flow.py / nodes.py`。
- 差异：本地不调用 LLM 写教程章节；它输出的是可复核的源码定位证据。

### 3. OpenWiki：稳定图节点与 links/backlinks

- 参考源码：`src/visualize/graph.ts:37-75` 的稳定页面节点；`graph.ts:245-269` 的安全树遍历。
- 本地采用：能力面、组件均用稳定 ID；关系显式拆成 internal/inbound/outbound，相当于可追溯 links/backlinks；本地 URI 在 renderer 再次校验 authority 与 project-root containment。
- 差异：本地不复用 OpenWiki 的 D3 交互层，只参考确定性图数据合同与安全路径边界。

### 4. Understand Anything：拓扑 Tour 与 cycle fallback

- 参考源码：`tour-generator.ts:122-165` 的 Kahn topological sort；`tour-generator.ts:250-299` 的未分层节点与顺序收尾。
- 本地采用：implementation trace 对已解析跨文件边执行 Kahn 排序，记录 `topology_layer`；cycle 节点以 `cycle-fallback` 明示降级，不把固定角色顺序冒充调用链。
- 差异：本地 trace 的节点是源码文件/关系端点，不是其完整知识图 ontology layer。

### 5. CodeBoarding：symbol/reference 图与 component 边界

- 参考源码：`static_analyzer/engine/call_graph_builder.py:24-134` 的 LSP symbols/references、definition/reference 两类建边和 hierarchy；cluster/component 输出用于组件边界。
- 本地采用：消费 Repo Teacher 已解析 symbol relationships，并以无向连通分量生成 `component_boundaries`；孤立文件单独标记，避免伪造聚类关系。
- 差异：本地未嵌入 CodeBoarding 的 LSP server 生命周期或 Leiden clustering；分析器精度由 Repo Teacher analyzer 决定，并通过 `resolved_ratio` 暴露缺口。

### 6. DeepWiki-Open：跨层 Codemap 与 citation grounding

- 参考源码：`api/services/codemap.py:201-222` 用真实 snippet 回查行号；`codemap.py:265-309` 的 skeleton → enrich → ground；功能本身横跨 router/service/schema/UI/WebSocket。
- 本地采用：`codemap` golden surface 的 primary 是 `api/services/codemap.py`，并组合 router、schema、Ask、CodeMap、CodeViewer、WebSocket client；源码片段与文件哈希做 grounding。
- 差异：本地不生成 LLM skeleton/enrichment 内容，只复用“结构化跨层实现面 + 真实源码 grounding”的机制。

## 六仓真实索引探针

探针直接读取 `examples/reference-selection/projects/*/index.json` 并调用当前 `locate_modules()`；不是 synthetic fixture。

```json
{"project":"pocketflow-code2tutorial","query":"tutorial","status":"composite_candidate","primary":"main.py","slices":["main.py","flow.py","nodes.py"],"files":3,"trace":18}
{"project":"sourcebridge","query":"knowledge","status":"composite_candidate","primary":"internal/knowledge","slices":["internal/knowledge","workers/knowledge","web/src/app/(app)/admin/knowledge"],"files":39,"trace":40}
{"project":"openwiki","query":"visualize","status":"composite_candidate","primary":"src/visualize","slices":["src/visualize","src/cli/runners.ts"],"files":6,"trace":5}
{"project":"understand-anything","query":"viewer","status":"candidate","primary":"understand-anything-plugin/packages/viewer","files":3,"trace":0}
{"project":"codeboarding","query":"static_analyzer","status":"candidate","primary":"static_analyzer","files":48,"trace":40}
{"project":"deepwiki-open","query":"codemap","status":"composite_candidate","primary":"api/services/codemap.py","files":7,"trace":26}
```

`Understand Anything viewer` 的 trace 为 0 是诚实结果：当前索引未解析出这个小 package 的跨文件 call/import 链，因此 HTML 显示“没有已解析实现链”，不会用文件名推断补造行为。

## 验证范围与剩余边界

- 专项单测覆盖：命名 exact 语义、辅助目录排除、多切片、根目录功能、测试关联、行级片段、URI containment、六仓 golden。
- 真实探针覆盖：六个完整参考索引的路径/切片/trace/测试关联结果。
- 独立复审：待新的审计 Agent 执行；在复审 PASS 前本模块不标记为生产完成。
- 分析器边界：LSP/跨语言 resolver 不是本模块职责。报告用 resolved ratio 和 unresolved diagnostics 暴露精度，而不是隐藏缺口。
