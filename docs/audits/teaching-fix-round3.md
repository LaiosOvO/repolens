# Teaching / capability discovery round 3 修复记录

> 状态：实现与本地验证已完成，等待独立 Agent 复审。本文不自行宣告审计 PASS。

## 结果摘要

- Python / JavaScript 的 HTTP、CLI 入口现在由 import、constructor 和 framework binding 共同确认，不再依赖 `app`、`program` 等变量名。
- `requests.Session` / `httpx.Client` 命名为 `app` 不会成为 route；普通 object 命名为 `program` 不会成为 CLI。FastAPI、Flask、Typer、argparse、Express、Fastify、Commander、Yargs 只有在框架绑定成立时才确认；未解析的形状降为 candidate。
- 6 个固定版本仓库的 19 项能力共有 66 个显式职责切片，每项至少 2 个。每个切片都包含精确路径、行范围、符号、职责、局部关系、claim scope 和源码片段 SHA-256。
- 59 个已知 technology tag 均生成自己的 `technology-claim:<dimension>` evidence ID、source path 和 claim scope；未知维度保持 `unknown` 且不关联伪证据。
- 教程产物改为“用途与入口 → 职责链 → 数据/状态与依赖 → 错误/证据缺口 → 复用边界”的总分总 contract，不再把 BFS 阅读步骤换皮当教程。
- 390px 真实 Chromium 视口验证：`documentElement.clientWidth=390`、`scrollWidth=390`、`body.scrollWidth=390`、越界元素 `[]`。

## 19 项能力的职责切片

| 项目 | 能力 | 切片数 | 显式职责 | 已知技术证据 |
| --- | --- | ---: | --- | --- |
| SourceBridge | graph-store | 4 | 状态所有权 / 内存索引初始化 / 索引结果写入 / 图与内容查询 | `store:in-memory`, `retrieval:graph-query` |
| SourceBridge | execution-path | 4 | 路径编排 / 上游调用者回溯 / 候选邻居评分 / 源码定位投影 | `store:graph`, `retrieval:execution-path`, `evidence:source-location` |
| SourceBridge | code-tour | 3 | 提示词与模型调用 / 结构化停止点映射 / 路径与证据门禁 | `llm:provider-adapter`, `retrieval:graph-context`, `evidence:source-citation` |
| PocketFlow | tutorial-flow | 2 | 工作流节点实例化 / 节点顺序与 Flow 起点 | `framework:pocketflow`, `llm:workflow-nodes` |
| PocketFlow | tutorial-nodes | 5 | 仓库上下文组装 / 抽象关系上下文 / 章节排序输入 / 章节写作批次 / 教程与图合并 | `parser:repository-context`, `framework:pocketflow`, `llm:prompted-generation`, `evidence:file-reference` |
| OpenWiki | skeleton-critic | 3 | 独立源码审查流程 / 结构化裁决与通过门 / 子 Agent 注册条件 | `llm:subagent`, `evidence:coverage-critique` |
| OpenWiki | wiki-link-validator | 3 | 扫描、校验与回写编排 / Markdown 链接与锚点提取 / 锚点规范化与路径解析 | `parser:markdown`, `retrieval:repository-files`, `evidence:link-validation` |
| OpenWiki | ingestion | 4 | 连接器注册与逐源编排 / 拉取、Agent 更新与错误收敛 / 摄取源筛选 / 跨源写入策略 | `framework:connector-registry`, `store:backend-adapter`, `incremental:ingestion-window`, `llm:agent-run` |
| Understand Anything | context-builder | 3 | 搜索与一跳扩展 / 节点、边与层聚合 / 提示上下文格式化 | `store:knowledge-graph`, `retrieval:search-and-neighbor-expansion`, `llm:prompt-context` |
| Understand Anything | onboard-builder | 3 | 项目与架构层导览 / 概念与 tour 渐进阅读 / 文件地图与复杂度提示 | `store:knowledge-graph`, `retrieval:layered-tour`, `evidence:file-node` |
| Understand Anything | explain-builder | 3 | 路径或符号目标解析 / 子节点与一跳邻居聚合 / 定点解释提示格式化 | `parser:path-and-symbol-target`, `store:knowledge-graph`, `retrieval:connected-subgraph`, `llm:explain-prompt`, `evidence:target-node` |
| CodeBoarding | full-analysis | 3 | 全量分析 CLI 参数 / 本地与远程分发 / 本地分析与文档渲染 | `framework:cli-workflow`, `incremental:full-baseline`, `evidence:analysis-artifacts` |
| CodeBoarding | call-graph | 4 | LSP/适配器/符号表边界 / 构图流水线 / documentSymbol 采集 / 调用边后处理 | `parser:language-adapter`, `store:call-graph`, `retrieval:definition-resolution`, `evidence:call-sites` |
| CodeBoarding | component-clustering | 4 | 逐语言聚类 / 跨簇加权图 / Leiden 模块度分组 / 增量身份延续 | `store:call-graph`, `retrieval:leiden-clustering`, `incremental:cluster-cache`, `evidence:cluster-file-map` |
| DeepWiki | codemap-router | 3 | WebSocket NDJSON 边界 / HTTP 流式回退 / 源码文件 API | `framework:fastapi`, `evidence:request-schema` |
| DeepWiki | codemap-service | 4 | 流式模型与重试 / 检索片段格式化 / 引用定位 / 检索与阶段事件编排 | `framework:service-layer`, `llm:codemap-generation`, `evidence:citations` |
| DeepWiki | wiki-structure | 3 | XML 页面映射 / 正则降级解析 / 严格与降级编排 | `parser:xml-and-regex-fallback`, `evidence:page-source` |
| DeepWiki | codemap-ui | 4 | 生成阶段状态 / 可点击引用 / 空数据反馈 / 章节、图与源码展示 | `framework:react`, `evidence:citation-chip`, `ui:codemap` |
| DeepWiki | code-viewer | 4 | 语言映射 / 源码请求缓存 / 高亮区间滚动 / 行号与区间高亮 | `framework:react`, `retrieval:file-content-api`, `evidence:line-highlight`, `ui:code-viewer` |

SourceBridge `graph-store` 的 4 个切片全部位于 `internal/graph/store.go`；独立 oracle 显式禁止 `testhelper` / `testhelpers.go` 出现在任何能力步骤或技术证据中。

## 教学 contract

每个 tutorial 都带有可机器读取的 `teaching_contract`：

1. `purpose` 与 `entry`：先给出能力用途、入口、置信度与入口证据。
2. `main_chain`：只由显式职责切片组成，每个切片自带 role、symbol、claim scope、relationship 和 hash。
3. `data_and_state` / `dependencies`：仅展示有独立 technology evidence 的声明。
4. `error_and_evidence_gaps`：显式标出数据流、状态所有权、异常/重试/回滚和运行次序缺口。
5. `reuse_boundary`：分开可学习的局部机制和必须重新验证的数据契约、版本、错误、并发、权限、性能与许可边界。

HTML 端会展示上述结构，并在每个已知 technology tag 下展示 claim scope、evidence ID 数量与可点击源码路径。

## 视觉与移动端验证

- 浏览器：本地 Google Chrome，由 Python Playwright 驱动。
- 视口：390 × 844。
- 真实 SourceBridge 报告：索引 1,575 个文件、13,956 个符号、91,119 条关系。
- 宽度断言：`viewport=390`、`document.scrollWidth=390`、`body.scrollWidth=390`、`offenders=[]`。
- 截图：[`screenshots/teaching-round3-sourcebridge-390-viewport.png`](screenshots/teaching-round3-sourcebridge-390-viewport.png)。
- Visual Verdict 记录：`.omx/state/teaching-round3/ralph-progress.json`，布局 94、字体 92、信息层级 94、响应式 100，综合 95。

## 验证证据

| 验证 | 结果 |
| --- | --- |
| `tests.test_features` | 11/11；包含错误变量名诱导、真实框架绑定和 unresolved candidate 对抗样例 |
| `tests.test_reference_ground_truth` 六仓真实探针 | PASS，19/19 能力，66 职责切片，59 个已知 tag |
| `tests.test_report_mobile_browser` | PASS，真实 390px Chromium 宽度与越界元素断言 |
| 专项回归 | `test_report + test_artifacts + test_features` 22/22 |
| 全量回归 | 179/179，86.668s |
| Ruff | `uv run ruff check src tests` — All checks passed |
| Compileall | `PYTHONPATH=src python3 -m compileall -q src tests` — PASS |

## 变更范围

- `src/repo_teacher/features.py`：框架 provenance 与入口边界确认。
- `src/repo_teacher/capability_catalog.py`：19 项能力的职责切片 contract 与 59 个独立 technology claim。
- `src/repo_teacher/models.py`：教学切片与 technology claim 字段。
- `src/repo_teacher/artifacts.py`：总分总 teaching contract。
- `src/repo_teacher/report.py`：职责/声明边界/技术证据展示与移动端布局。
- `tests/fixtures/reference_capabilities.json`：与产品 contract 解耦的 19 项语义职责 oracle。
- `tests/test_features.py`、`tests/test_artifacts.py`、`tests/test_report.py`、`tests/test_reference_ground_truth.py`、`tests/test_report_mobile_browser.py`：对抗、教学、技术证据、真实仓库与移动端回归。

## 仍需独立复审

1. 从用户阅读视角判断“总分总”章节是否真比原 BFS 步骤更容易得出复用决策。
2. 抽样复核 59 个 claim scope 是否都足够狭，没有把局部机制扩大成项目级结论。
3. 用独立命令重跑六仓与 390px 浏览器验证，不复用本文的 PASS 描述作为证据。
