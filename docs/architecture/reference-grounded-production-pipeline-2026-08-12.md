# RepoLens 参考实现驱动的顺序生产 Pipeline（2026-08-12）

> **状态：历史研究稿，已被 [五阶段参考驱动 Pipeline](./five-stage-reference-pipeline.md) 取代。**
> 下文保留参考仓库源码阅读与取舍证据，但其中 candidate/grouping/review/chapter 多模型阶段、
> 分片并发、语义修复和 readability gate 不再描述当前 `report` 命令。当前运行合同只有固定五阶段，
> 第 03 阶段一次生成完整内容，第 04 阶段确定性校验，失败不自动回跳。

## 结论先行

RepoLens 应当是一个 **CodeGraph/AST 先行、业务能力优先、证据闭合、可恢复的本地顺序 Pipeline**。它的首要产物仍然只有一个给人看的 `index.html`：先回答“这是什么产品、对外有哪些真正业务功能”，再逐项回答“用户如何触发、谁接管、状态怎样变化、Worker/外部系统怎样执行、结果怎样回到用户、失败会怎样”，源码对象和目录只放在实现证据层。
这里的“图”只指代码关系图、章节交互图和证据图，不是任务编排图；任务编排本身必须是固定顺序。

最适合拼成这条 Pipeline 的参考不是某一个项目，而是六个项目各取一段：

- Understand Anything：确定性扫描、Tree-sitter、按依赖社区分批、中间产物、合并审校、fingerprint/freshness；
- RepoAgent：对象关系、依赖拓扑调度、checkpoint 和增量刷新；
- DeepWiki Open：任务状态机、有界页面并发、逐页重试、引用链接和前端进度；
- Repomix：过滤、安全检查、代码压缩、token 预算、split output 和可复用 pack；
- GitDiagram：先生成严格 JSON 图，验证后再确定性编译 Mermaid；
- readme-ai：Provider/CLI/模板/后处理分层，但只借工程组织，不采用 README 作为分析主产物。

这意味着 RepoLens 不能再把“整个 `pipeline/*.py` 的 digest”当作一个总缓存键，也不能把业务域仅按顶层目录切片。一个审校 Prompt 的改动不应导致所有 CodeGraph、AST、14 个 inventory shard 和全局归组重跑。

## 一、目标与不可妥协约束

### 1.1 人类最终看到什么

`index.html` 固定按以下叙事顺序组织：

1. **一句话项目本质**：谁用它，以什么方式获得什么结果；明确它不是什么。
2. **核心用户旅程**：按真实使用先后列出 3–N 个顶级业务能力，不限数量。
3. **整体运行架构**：前端、API、领域服务、队列/Worker、存储、外部服务、部署边界及其交接。
4. **逐功能机制章节**：第一句先说“本质就是……”，再给真实交互图和文字解释。
5. **技术选型信号**：可直接借鉴、需要改造、不要照搬、仍需验证。
6. **工程结构**：前后端代码组织、各目录职责、DDD/分层/模块化单体/多服务等判断及证据。
7. **源码证据索引**：commit、文件、符号、行号、关系 ID；放在正文之后，不抢主叙事。

每个业务能力必须至少回答：

> 谁触发 → 入口接收什么 → 控制权交给谁 → 权威状态存在哪里 → 数据怎样转换 → 是否并发/排队/重试 → 谁执行副作用 → 进度怎样返回 → 结果由谁消费 → 失败/终止条件是什么。

### 1.2 顶级业务能力的判定合同

一个顶级能力同时满足：

- 独立的使用者或调用方；
- 独立用户目标；
- 用户可观察结果；
- 独立业务状态、运行位置或责任边界；
- 源码可证明的完整因果链。

路由、页面、登录壳、CRUD、健康检查、Bridge、Adapter、类、函数、目录和 Example 都不是天然业务能力。它们只能在确实独立交付用户结果时升级，否则必须归入某个主旅程的实现模块、支撑项或排除项。这个判断由代码图事实 + 模型语义完成，禁止用仓库名、路径关键词或正则做业务结论。

### 1.3 非功能要求

| 要求 | 生产合同 |
| --- | --- |
| 无人值守 | `repo-teacher report <repo> --output <dir>` 从冻结源码一直运行到原子发布；人工 inventory 仅为可选审阅，不是必经卡点。 |
| 正确性 | 所有实现结论必须闭合到固定 snapshot 内的 symbol/relationship/source ref；越界 fail closed。 |
| 可恢复 | 每阶段持久化；PASS 产物复用前重验 Schema、digest 和证据闭包；失败停止在当前阶段，下一次运行从最新成功阶段或用户指定阶段恢复，不做自动回跳。 |
| 通用性 | 同一 Pipeline 处理平台、框架、库、CLI、服务和多仓 Monorepo；没有仓库专用规则。 |
| 性能 | 静态分析本地确定性并行；模型按图社区有界并发；全局语义归组/审校串行；缓存按阶段独立失效。 |
| 可观察 | CLI/GUI 都接收同一事件流；生成 `performance.json`，能解释时间花在哪一阶段、哪一 shard、是否排队/命中缓存/失败。 |
| 安全 | 密钥不进入参数、Prompt、日志、cache identity 或产物；模型只读隔离 source slice。 |

## 二、真实参考源码与采用边界

### 2.1 参考版本

| 项目 | 本地源码 | 本次读取 HEAD | 完整历史状态 |
| --- | --- | --- | --- |
| Understand Anything | `/Volumes/T7/workspace/ontology/graph/repo/understand-anything` | `fe8c5bc591716aafd79b4765549328f08ef5a52e` | `is-shallow=false` |
| DeepWiki Open | `/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open` | `4181daa5ebde79a1baf8e92a09dd874f8b74411b` | `is-shallow=false` |
| RepoAgent | `/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/RepoAgent` | `825d988127d7bfd757237d9c4e8678d9104030f0` | `is-shallow=false` |
| GitDiagram | `/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/gitdiagram` | `883e3a789a28c8cae8108991b360585a2a5896e5` | `is-shallow=false` |
| Repomix | `/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/repomix` | `e3b15a406ed78d8a463620a032a059ce911bfc0e` | 当前源码树已读取；GitHub 历史补全受网络长连接中断，仍为 shallow |
| readme-ai | 目标 `/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/readme-ai` | upstream HEAD `460aea9abce3b11e35d94f0d378b04cdb95dd955` | GitHub pack 传输中断，尚未形成可验收工作树；本设计仅采用已由官方源码核验的模块边界，不依赖其实现细节 |

后两项的网络状态是本机到 GitHub pack 长连接的外部限制，不应伪称已经完成；它不影响前四个关键参考和 Repomix 当前源码树的架构判断。

### 2.2 逐项目源码结论

#### Understand Anything：主 Pipeline 骨架

关键实现：

- [`SKILL.md`](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/skills/understand/SKILL.md)：7 阶段运行、阶段/批次进度、中间产物与可选 review；
- [`scan-project.mjs`](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/skills/understand/scan-project.mjs)：语言/类别识别、忽略合同和确定性扫描；
- [`compute-batches.mjs`](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/skills/understand/compute-batches.mjs)：import graph、Louvain community、退化时确定性分批、64 路有界 I/O；
- [`extract-structure.mjs`](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/skills/understand/extract-structure.mjs)：Tree-sitter 与非代码 parser 的确定性结构/调用提取；
- [`merge-batch-graphs.py`](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/skills/understand/merge-batch-graphs.py)：跨批次合并、ID 规范化、关系修复与不可修复报告；
- [`build-fingerprints.mjs`](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/skills/understand/build-fingerprints.mjs) 与 [`staleness.ts`](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/packages/core/src/staleness.ts)：fingerprint、commit/dirty/ahead/behind/diverged freshness。

采纳：确定性 scan → 图关系索引 → 结构提取 → candidate 生成/合并 → 全局归组 → 语义审校 → 章节生成 → 编译/发布；所有阶段写固定 JSON 产物。

拒绝：把文件/符号节点直接当最终人类目录；RepoLens 必须在图之上形成业务能力层。

#### RepoAgent：依赖拓扑与恢复

关键实现：

- [`project_manager.py`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/RepoAgent/repo_agent/project_manager.py)：Jedi 项目视图和引用路径；
- [`doc_meta_info.py`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/RepoAgent/repo_agent/doc_meta_info.py)：对象树、引用关系、checkpoint 和拓扑任务；
- [`multi_task_dispatch.py`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/RepoAgent/repo_agent/multi_task_dispatch.py)：只有依赖完成的任务才可取出并行执行；
- [`runner.py`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/RepoAgent/repo_agent/runner.py)：多线程生成、每项完成后 checkpoint、文档版本绑定 commit；
- [`change_detector.py`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/RepoAgent/repo_agent/change_detector.py)：按 Git diff 定位受影响对象。

采纳：固定顺序调度、完成即 checkpoint、commit/fingerprint 驱动增量刷新。

拒绝：每个 Python 对象生成一页文档；它会把模块粒度误当产品功能粒度，并且语言覆盖不足。

#### DeepWiki Open：任务状态与引用

关键实现：

- [`tasks.py`](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/tasks.py)：`PENDING → INDEXING → DETERMINING_STRUCTURE → GENERATING → COMPLETED/FAILED`，repo task semaphore，page semaphore，页面级重试和进度；
- [`pipeline.py`](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/rag/pipeline.py)：文件过滤、chunk、line tracking、embedding 与 LocalDB；
- [`content.py`](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/content.py)：文件/行号引用后处理；
- [`structure.py`](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/structure.py)：wiki structure 解析。

采纳：明确任务状态、有界并发、引用链接、前端可轮询/订阅的进度事件；单个阶段失败后不自动倒回前序阶段。

拒绝：失败页面用 error placeholder 后仍把整个任务标成完成；RepoLens 的核心能力章节缺证据必须阻止发布。也拒绝用纯向量 RAG 代替调用关系图。

#### Repomix：证据传输层

关键实现：

- [`packager.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/repomix/src/core/packager.ts)：collect/process/security/output/metrics 并发编排；
- [`fileProcess.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/repomix/src/core/file/fileProcess.ts)：文件处理；
- [`TokenCounter.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/repomix/src/core/metrics/TokenCounter.ts) 与 [`tokenCountCache.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/repomix/src/core/metrics/tokenCountCache.ts)：token 统计与缓存；
- [`outputSplit.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/repomix/src/core/output/outputSplit.ts)：按体积切分；
- [`parseFile.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/repomix/src/core/treeSitter/parseFile.ts)：Tree-sitter 压缩；
- [`cliRun.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/repomix/src/cli/cliRun.ts)：薄 CLI 和 `--token-budget`/`--split-output`/安全边界。

采纳：过滤、安全扫描、token/byte 双预算、source slice 压缩、超预算 fail closed、pack 指标。

拒绝：把整仓拼成一个超长文本后直接问模型；Pack 是传输层，不是真相层或能力识别层。

#### GitDiagram：可信交互图

关键实现：

- [`graph-planner.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/gitdiagram/src/server/generate/graph-planner.ts)：严格 structured output、单次生成的 usage/timing/audit；
- [`graph.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/gitdiagram/src/server/generate/graph.ts)：节点/组/边/path 完整性验证；只有未知路径可局部剥离，结构错误直接失败；
- [`mermaid.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/gitdiagram/src/server/generate/mermaid.ts)：经过验证的 JSON AST 确定性编译 Mermaid；
- [`session-audit.ts`](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/gitdiagram/src/server/generate/session-audit.ts)：timeline、usage、failure stage 和持久化审计。

采纳：模型产出 diagram AST，不直接产 Mermaid；先验证节点、边和源码路径，再编译和渲染。

拒绝：只有架构图而没有逐功能文字机制；图是解释器，不是报告本身。

#### readme-ai：外围工程分层

采用其公开源码中 `cli → core/pipeline → retrievers → generators → postprocessor` 的职责分离，以及 provider/template 可替换性。

拒绝 README-centric 产物：README 可以作为作者主张导航，但不能代替 CodeGraph/AST 事实，也不能决定业务能力。

## 三、目标顺序 Pipeline

这是一条 **严格顺序的 Pipeline**，不是任务图，也不是以重试边驱动的流程图。
顺序只允许是：`snapshot → scan → structural-index → evidence-plan → candidate-shard → candidate-merge → global-grouping → semantic-review → project-architecture → chapter-generation → diagram-compile → atomic-publish`。

其中第 4、5、9、11 步内部可以做有界并发，但它们依然属于同一个固定阶段，不能因此把整条流程改写成“遇到失败就回跳”的图。

关键规则：

- 每个阶段只读上游不可变 artifact，输出一个版本化 artifact；
- 每个阶段都有固定 Schema；
- 每个阶段最多执行一次；
- 阶段失败就停止在当前阶段；
- 下一次运行只允许从最新成功阶段或用户指定恢复点继续；
- “图”只用于代码关系、章节交互和证据表达，不用于任务编排。
- 可读性审校不再是必经阶段；它只能作为发布后的附加审阅或离线检查，不能阻塞 `atomic-publish`。

## 四、阶段合同

### 00 `SourceSnapshot`

输入：本地目录或远端 URL、branch/tag/commit、include/exclude、private token handle。

输出 `source-manifest.json`（`repolens-source-manifest/v2`）：

```json
{
  "repository": "owner/repo-or-absolute-local-path",
  "requested_revision": "main",
  "resolved_commit": "abc123",
  "dirty": false,
  "files": [{"path": "src/a.ts", "sha256": "...", "bytes": 42}],
  "content_sha256": "...",
  "indexed_at": "2026-08-12T00:00:00Z"
}
```

不变量：分析期间 source slice 不得变化；任何文件 hash 变化使依赖该文件的下游失效。远端 token 只作为 secret handle 使用，不写 manifest。

### 01 `RepositoryScan`

输入：snapshot；输出 `repository-inventory.json`（`repolens-repository-inventory/v1`）。

内容：语言/框架、manifest、服务/应用/包、前后端/Worker/infra/data/docs 分类、真实 CLI/HTTP/queue/timer 入口候选、过滤结果与原因。

实现：借 UA scanner + Repomix ignore/security。过滤是文件安全/类型过滤，不做业务能力判断。默认排除依赖、构建产物、二进制、minified、密钥；tests/examples 保留为使用与行为证据，但降低读取优先级。

### 02 `StructuralIndex`

输入：scan；输出：

- `symbol-index.json`（`repolens-symbol-index/v2`）；
- `relationship-graph.json`（`repolens-relationship-graph/v2`）；
- 可选 `.codegraph/codegraph.db`。

每个 symbol：ID、language、kind、qualified name、signature、file/start/end、content hash、parser outcome。

每个 edge：ID、type、source ID、target ID、file/line、resolution quality。至少支持 `IMPORTS/CALLS/IMPLEMENTS/EXTENDS/READS/WRITES/PUBLISHES/CONSUMES/ROUTES_TO/TRIGGERS/DEPLOYS`。无法解析的动态边保留为 `unresolved`，禁止静默伪造。

实现：CodeGraph 优先；缺少 CodeGraph 时只能使用已声明支持的语言 AST/LSP parser，并在 manifest 标出 capability，不允许无提示降级为文本关键词搜索。

### 03 `EvidencePlan`

输入：图 + scan + snapshot；输出：

- `partition-plan.json`（`repolens-partition-plan/v2`）；
- `packets/candidate-<community>.json`（`repolens-evidence-packet/v2`）；
- 隔离只读 source slice。

分区算法：

1. 以 resolved relationship graph 构建弱连通/社区；
2. 使用 Louvain 或确定性连通组件形成语义社区；
3. 以路由/CLI/消息消费/定时任务/公开库 API 等真实入口作种子扩展上下游；
4. 把跨社区边写入 `neighbor_map`；
5. 以 packet byte/token 上限拆大社区，以依赖边合并小孤岛；
6. 每个 source path 只能有一个 owner shard，但可作为只读 neighbor evidence 被引用。

这替换当前仅按 `apps/packages/services` 或顶层目录分域的策略。目录只是布局信号，调用/数据/消息关系才是运行边界。

每个 packet 包含 `scope.allowed_source_paths`、symbols、edges、entry seeds、state stores、external boundaries、source excerpts、packet bytes/tokens、缺口。全文不内联；模型可在隔离 slice 中打开允许文件。

### 04 `CandidateShard`

输入：一个 evidence packet；输出 `capability-candidates/<community>.json`（`repolens-capability-candidates/v2`）。

Shard Agent 只做“细粒度、证据闭合的候选”，不决定最终报告功能层级。每项候选包含 actor/goal/visible outcome/causal flow/authority state/implementation handoffs/source refs；所有产品模块必须有 disposition。

并发：Provider-aware，默认 4；CLI 环境变量只覆盖上限。模型供应方如果有 rate limit/并行建议，则 `min(config, provider_limit, shard_count)`。不是固定 8，更不是固定 32 片。

失败：Schema/ID/path/模块 disposition 缺失直接标记 shard failed；不得自动修补、不得自动重试、不得把缺失字段默认化。若这个 shard 失败，则该阶段停止，下一次运行从恢复点重新进入该阶段。

### 05 `CandidateMerge`

纯确定性阶段。统一局部 ID、去重完全相同 evidence、闭合 disposition、保留跨 shard neighbor edges。输出 `capability-candidates.json`。它不生成业务标题，不偷偷合并语义。

### 06 `GlobalGrouping`

输入：全体候选 + README/docs 形成的 `product-navigation`（只作作者主张）+ graph global summary；输出 `capability-inventory.json`（`repolens-capability-inventory/v2`）。

模型全局比较 actor、goal、业务状态、visible outcome、因果链和运行位置：

- 同一结果的 UI/API/Worker/store 合成一个顶级能力；
- 独立动作、状态机、结果或责任边界保留为不同能力；
- supporting candidate 归入主链或排除；
- 先排 `core-journey`，再 `differentiator`、`dependent-capability`、`supporting`；同级按用户旅程先后。

`project_summary` 与 inventory 同时产生，用于约束核心优先级；但任何实现事实必须来自图/源码证据。

### 07 `SemanticReview`

独立 reviewer 只做终止性审校：反证产品定位、业务语义、因果证据、产品覆盖四件事。review 只返回 `pass/fail`、结构化 issue、以及被否定的候选 ID 列表。
review 阶段 **不允许** 回写 regroup、不允许触发局部修复、不允许把失败当作“再来一轮试试”。如果 reviewer 认为不成立，这一轮就失败停止。

这样做的第一性原理是：语义审校是在验证“现有证据是否足以支撑当前叙事”，不是在无边界地生成更多叙事。把失败改成循环会让耗时、错误收敛和证据边界都失去上限。

### 08 `ProjectArchitecture`

输入：通过审校的 inventory + graph；输出 `project-overview.json`（`repolens-project-overview/v2`）。

必须覆盖：项目本质、主要部署/运行边界、前端/后端/Worker/数据/infra 目录表、工程组织模式判断、一次核心旅程跨模块交接图、能力优先顺序。所有架构判断区分 `fact` 与 `inference`。

### 09 `ChapterGeneration`

按能力独立生成，默认 4 路并发。每个 `chapters/<capability-id>.json`（`repolens-capability-chapter/v2`）固定包含：

1. `one_sentence_essence`；
2. `user_example`；
3. `interaction_graph`（严格 JSON AST）；
4. `runtime_narrative`；
5. `state_and_storage`；
6. `control_and_routing`；
7. `concurrency_and_async`；
8. `failure_and_termination`；
9. `technology_selection`；
10. `source_refs`。

没有某种机制时写“源码未出现/不适用”，不能用常见架构脑补。

### 10 `ReadabilityReview`

以人类技术选型视角逐章节审校：第一句是否给结论、图与文字是否一致、因果链是否回答到结果消费、难点与边界是否清楚、是否把代码模块重新提升成业务功能。
但这个审校不再作为阻断发布的自动修复循环存在：它只产出审校结果，发布是否继续由上游阶段是否通过决定。若该阶段失败，当前运行停止；如果用户要继续，只能从恢复点重新运行。

### 11 `DiagramCompile`

`interaction_graph` Schema：actors/components/stores/queues/external systems 为 node；trigger/call/read/write/publish/consume/progress/result/failure 为 edge；每个 implementation edge 绑定 relation/source ref。

先校验 endpoint 存在、ID 唯一、路径存在、关键链从 trigger 可达 visible outcome。未知可选源码 link 可以局部移除；断链/未知节点直接判定该章节失败。通过后确定性编译 Mermaid，不让模型直接吐 Mermaid 文本。

### 12 `AtomicPublish`

输出目录：

```text
generated-report/
├── index.html
├── human-report.json
├── capability-inventory.json
├── project-overview.json
├── chapters/
├── diagrams/
├── source-evidence/
├── run-manifest.json
├── performance.json
└── pipeline/
```

先生成 immutable generation，验证所有文件后原子切换 current pointer。`index.html` 内的源码链接必须在新页打开，或提供固定返回报告的导航；不能破坏读者返回路径。
发布阶段只接受已经通过前序顺序阶段的最终 artifact，不承担修复、补洞或重跑职责。

## 五、阶段级缓存：修复当前全局失效根因

### 5.1 当前问题

当前 [`cache_identity.py`](/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/pipeline/cache_identity.py) 的 `packaged_contract_digests()` 会遍历整个 `repo_teacher.pipeline/*.py`、providers、renderers、schemas 并放进同一个 run identity。结果是只改 `semantic_review.py` 也会产生新的 model workspace，导致所有 inventory shard 和 grouping 重跑。

这是缓存隔离错误，不是正确性需要。

### 5.2 正确的阶段缓存键链

每个阶段独立计算：

```text
stage_cache_key = sha256(
  stage_name + stage_contract_version +
  sorted(input_artifact_digests) +
  stage_implementation_digest +
  prompt_digest? + response_schema_digest? +
  provider_model_identity?
)
```

| 阶段 | 只应包含的 identity | 不应包含 |
| --- | --- | --- |
| snapshot | resolved commit、tracked+dirty content manifest、exclusions | Prompt、renderer |
| scan | snapshot digest、scanner/ignore/security versions | review/chapter code |
| structural-index | scan digest、parser/CodeGraph/language config versions | LLM model、Prompt |
| evidence-plan | graph digest、partition algorithm version、byte/token budgets | grouping/review Prompt |
| candidate-shard | 单 shard packet digest、inventory Prompt/Schema、该阶段 model/effort | semantic review、chapter、renderer |
| candidate-merge | ordered shard artifact digests、merge version | Provider |
| grouping | candidate digest、product-navigation digest、group Prompt/Schema/model | reviewer/chapter/HTML |
| semantic-review | **inventory public semantic fields + refs digest**、review packet、review Prompt/Schema/model | shard Prompt、renderer |
| overview | approved inventory digest、overview packet/Prompt/Schema/model | chapter/renderer |
| single chapter | one capability digest、chapter packet/Prompt/Schema/model | 其他 chapter；review implementation |
| diagram compile | diagram AST digest、compiler/validator version | model |
| renderer | validated human-report digest、template/assets/renderer version | parser/indexer/reviewer code |

因此修改 `semantic_review.py` 的期望失效范围是：`semantic-review → overview/chapters/readability/renderer`；`candidate-shard`、`candidate-merge`、初次 `grouping` 缓存保持有效。若 review 仍通过，甚至 overview/chapter 可继续命中，因为批准 inventory digest 未变。

缓存 artifact 必须与 identity sidecar 同目录，复用前执行：Schema validation → artifact digest → evidence closure → source snapshot binding。只检查“文件存在”不够。

## 六、失败、重试和恢复

| 故障 | 处理 | 最小重试点 |
| --- | --- | --- |
| snapshot 中途变化 | 中止，不发布混合世代 | source-snapshot |
| parser 不支持/失败 | 记录 outcome；若影响必需语言则 fail closed | structural-index |
| packet 超预算 | 确定性拆分社区；单文件仍超限则报告明确 blocker | evidence-plan |
| Provider timeout/rate limit | 指数退避 + jitter，遵守 Retry-After；单次 model call 失败则当前阶段停止 | 当前 model call |
| JSON/Schema 非法 | 一次带 validator feedback 仍非法则当前阶段停止 | 当前 shard/chapter |
| ID/path/evidence 越界 | 不接受；返回准确问题 | 当前阶段 |
| shard module disposition 漏项 | 记录精确 missing paths；当前阶段停止 | 当前 shard |
| semantic mixed boundary/漏能力 | 记录问题并停止，不做局部回写 | global-grouping |
| 相同语义失败状态重复 | 终止震荡，保存诊断和最后有效 artifact | semantic-review |
| 单章节可读性失败 | 只重写该 overview/chapter | chapter-generation |
| 图结构断链 | 带 validator issue 重做该章 diagram AST | diagram compile |
| 发布失败 | current pointer 保持上一世代 | atomic-publish |

Journal 至少记录 `stage/status/started_at/completed_at/duration/inputs/outputs/cache_key/cache_hit/issues/recovery_point`。像 RepoAgent 一样，单元完成立即 checkpoint；像 DeepWiki 一样暴露清晰状态；比二者更严格的是核心章节缺失绝不降级成 placeholder 后发布。

## 七、并发、耗时预算和可观察性

### 7.1 并发策略

- 本地扫描/I/O：64 个有界读取槽可作为上限参考，但 CPU-bound Tree-sitter 按语言 parser 能力调节；
- CodeGraph/AST：本地确定性并行，不与模型请求占同一池；
- Candidate shards：默认 4；provider-aware；以图社区和 token budget 决定数量；
- Global grouping / semantic review：串行，因为需要整仓一致判断；
- Chapters：默认 4，单 capability cache；
- Diagram compile/render：本地并行；
- 相同 stage cache key：single-flight，第二个调用订阅同一任务而不是重复付费。

若一次 Coze 运行出现 14 个 113–345 KB packet，8 路并发并不等于更快：会造成 provider 排队、长 prompt ingestion、速率限制和尾延迟。优化顺序应是减少重复上下文 → 图社区合并/拆分 → 缩小 packet → cache 命中 → 最后才提高并发。

### 7.2 `performance.json`

Schema `repolens-pipeline-performance/v2`：

```json
{
  "wall_seconds": 120.3,
  "critical_path_seconds": 109.1,
  "cache_hit_ratio": 0.72,
  "model_calls": 9,
  "model_retries": 1,
  "longest_stage": "candidate-shards",
  "stages": [{
    "stage": "candidate-shard/domain-03",
    "queue_seconds": 2.1,
    "io_seconds": 0.3,
    "model_seconds": 21.4,
    "validation_seconds": 0.1,
    "validation_seconds": 0.0,
    "wall_seconds": 23.9,
    "packet_bytes": 182311,
    "estimated_tokens": 45578,
    "cache_hit": false,
    "attempts": 1
  }]
}
```

必须区分 `queue/model/validation/io`，否则只能看到“总共很慢”却不知道该减 packet、降并发还是改缓存。并发阶段同时记录 `sum_child_seconds / parallel_wall_seconds` 的实际 speedup 和 critical path；不要把并发子任务耗时简单相加当墙钟时间。

### 7.3 GUI/CLI 统一事件

事件 Schema `repolens-progress-event/v2`：

```json
{
  "run_id": "...",
  "seq": 42,
  "stage": "candidate-shards",
  "unit": "domain-03",
  "status": "started|progress|cache-hit|passed|failed",
  "current": 4,
  "total": 9,
  "elapsed_seconds": 31.2,
  "eta_seconds": 44.0,
  "message": "正在归纳业务域 4/9",
  "metrics": {"packet_bytes": 182311, "queue_seconds": 2.1}
}
```

GUI 只订阅事件并读 journal/performance，不复制 Pipeline 状态机。断线后用 `seq` 续接；取消请求传播 cancel token 到未启动 future 和 Provider，已完成 artifact 保留供恢复。

## 八、索引与在线问答的边界

离线报告的主链必须是精确文件/符号/关系图 + 有界源码包；它不需要为了生成一次 HTML 先维护向量数据库。

若后续增加“问这个仓库”功能，再建立独立检索层：全文索引 + 向量索引 + 符号索引 + 关系图。查询先识别 capability/symbol/module，全文/向量召回后沿图扩上下游，再 rerank 和回答。向量搜索不能替代 `Route → Controller → Service → Repository → DB/Queue/Worker` 的确定性扩展。

## 九、当前实现的通用差距与执行顺序

### P0：直接影响速度和功能正确性

1. 把总 `run-identity` 拆成 stage cache identities；先修复 review 改动导致所有 shard 重跑。
2. `_inventory_module_shards` 从顶层路径 bundling 改为 relationship graph community + neighbor map；路径只作辅助。
3. inventory 默认并发从硬编码 8 改为 provider-aware 4；把 queue/model/token 指标用于调优。
4. 语义修复从 8 次降为 bounded issue-state loop：最多 2 次新状态，相同状态立即 fail。
5. chapter cache 加入 prompt/schema/model/单 capability/packet identity，不能只凭 expected IDs 复用。

### P1：解释质量和图可信度

1. chapter 输出严格 interaction graph AST，并用 graph/source validator；
2. 项目 overview 固定目录职责表与跨模块核心旅程；
3. 可读性审校只作为离线检查，不阻塞发布；
4. HTML 从 `human-report.json` 纯渲染，绝不在 renderer 重新判断业务功能。

### P2：增量与在线检索

1. 加 UA 式 fingerprint/freshness 和受影响社区传播；
2. 加 single-flight task registry 和 GUI event stream；
3. 有实际问答需求时才加全文/向量混合检索。

## 十、验收标准

生产实现完成必须同时证明：

- 改 `semantic_review.py` 后，candidate shard cache 全命中；只执行 review 及必要下游；
- 两个不同产品类型的仓库都不会把 health/login/route/CRUD/example 独立提升为核心功能；
- 任一能力都能从 user trigger 沿关系/源码走到 visible result 或明确证据缺口；
- 每个 diagram edge 都可回到 graph relation 或 source ref；
- 中途中断后从最小失败阶段恢复，不重跑已通过 shard；
- `performance.json` 可解释 queue/model/validation/cache/packet；
- `index.html` 第一屏先说项目本质和核心业务旅程，不从 CLI 入口或文件列表讲起；
- `index.html`、JSON、source evidence、run manifest 属于同一 generation，失败发布不污染上一版。

## 十一、采纳/拒绝总表

| 参考 | 采纳 | 明确拒绝 |
| --- | --- | --- |
| Understand Anything | deterministic scan、Tree-sitter、community batch、merge/review、fingerprint/freshness | 文件/符号就是最终产品目录；skill 自身承担生产事务 |
| RepoAgent | 依赖拓扑、checkpoint、commit 增量、完成即持久化 | 每对象一次 LLM、Python-only、对象文档当业务功能 |
| DeepWiki Open | task state、bounded page concurrency、citation、progress | 纯向量 RAG 作 truth；核心页失败 placeholder 后仍发布 |
| Repomix | ignore/security、compress、token budget、split pack、metrics | 整仓拼接成一个 prompt；pack 决定业务功能 |
| GitDiagram | strict graph AST、validation、deterministic Mermaid、audit/timing | 模型直接输出不可验证 Mermaid；只有图没有文字机制 |
| readme-ai | CLI/pipeline/provider/generator/postprocessor 分层、模板后处理 | README 作为主产物或业务能力真相 |

这个组合保持产品简单：用户只需给仓库和输出目录，最后读 `index.html`；复杂性被封装在可测试、可缓存、可恢复的内部顺序 Pipeline 中，而不是转嫁给用户反复口头指出报告漏了什么。
