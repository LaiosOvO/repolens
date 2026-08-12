# ADR：采用阶段寻址的顺序业务能力 Pipeline

## 状态

Superseded，2026-08-13。当前决策见
[五阶段参考驱动 Pipeline](./five-stage-reference-pipeline.md)。下文作为原始方案比较记录保留，
不再是 `report` 命令的运行合同。

## 背景

RepoLens 要把任意代码仓库转成供人类技术选型使用的报告。现有方向已经具备 CodeGraph、静态索引、证据包、Inventory Agent、全局归组、语义审校、章节生成和 HTML，但仍暴露三个系统性问题：

1. 功能容易按代码模块平铺，而不是按用户目标、可见结果和完整运行链归组；
2. 缓存 identity 过宽，修改一个审校实现会让全体 shard 重跑；
3. 分片与并发更多基于目录和固定上限，无法解释为什么一次运行慢、时间花在哪里。

已读取 Understand Anything、RepoAgent、DeepWiki Open、GitDiagram 和 Repomix 当前源码，并核对 readme-ai 的官方模块边界。共同有效的模式是：确定性事实先于模型；中间 artifact 持久化；并行围绕真实依赖/社区；严格结构先验证再渲染；进度、attempt、耗时和失败阶段都是一等数据。

## 决策

采用 **分层单体 + 阶段顺序缓存 + 内容寻址**：

```text
snapshot
  → scan
  → symbol/relationship graph
  → graph-community evidence packets
  → parallel fine-grained candidates
  → deterministic merge
  → global business grouping
  → independent semantic review
  → project architecture
  → parallel capability chapters
  → readability audit（非阻断）
  → validated diagram compilation
  → atomic HTML publication
```

### 决策 1：CodeGraph/AST 是事实层，LLM 是语义层

AST/CodeGraph 负责文件、符号、入口、调用、读写、发布/消费、路由和部署关系；LLM 负责把事实解释成 actor/goal/state/outcome/capability。禁止用路径关键词或正则替代业务语义，也禁止 LLM 凭常见架构补全不存在的图边。

### 决策 2：最终主分类是业务能力，不是代码对象

Candidate shard 只产细粒度、证据闭合候选；只有 GlobalGrouping 能决定顶级业务能力。一个顶级能力必须拥有独立用户目标、可见结果、业务状态或责任边界和完整因果链。模块、路由、CRUD、登录壳、健康检查和 Example 默认是实现证据/支撑项，不是同级功能。

### 决策 3：缓存按阶段寻址，不使用全局实现 digest

每个 stage key 只绑定自身输入 artifact、实现版本、Prompt/Schema/Provider（若有）。`semantic_review.py` 变化只失效 semantic review 与必要下游；不能使 structural index、evidence packets、candidate shards 和 grouping cache 失效。

复用 cache 前仍须验证 Schema、artifact digest、evidence closure 和 snapshot binding。

### 决策 4：按关系图社区分片并有界并发

使用 resolved graph 的 dependency/call/data/message connectivity 建社区，Louvain 或确定性连通组件退化；目录仅作布局辅助。packet 按 byte/token 双预算拆分，跨社区边进入 neighbor map。

模型 shard 默认并发 4，受 provider limit 和任务数约束；global grouping/review 串行；chapter 按 capability 并发。相同 cache key 使用 single-flight。

### 决策 5：只允许最小、可证明的修复

- JSON/Schema/精确缺失 disposition：当前单元直接失败并记录问题；
- 语义错误：只允许终止性审校，不做自动回写修复；
- 相同 failure state 重复：停止，不进行无界重启；
- 核心章节缺证据：阻止发布，不生成 placeholder 冒充完成。

### 决策 6：交互图是验证后的 AST 派生产物

模型输出 nodes/edges/source bindings 的 JSON；validator 检查 endpoint、路径、ID、可达性和关系闭包；确定性 compiler 生成 Mermaid。图和文字共同解释同一 causal flow，但图不能替代文字机制。

### 决策 7：耗时与进度是一等 Artifact

每阶段记录 queue/io/model/validation/wall、packet bytes/tokens、cache hit、attempt；并发阶段计算 critical path、sum child time 和真实 speedup。CLI 与 GUI 消费同一带序号事件流；`performance.json` 永久保留。

## 影响

### 正面

- 功能识别错误可以定位到 facts、partition、candidate、grouping、review 或 chapter，而不是手改 HTML；
- 审校/样式修改不再浪费全部模型调用；
- 大仓通过图社区和预算减少碎片化与超长 prompt；
- 中断、超时和局部失败能够最小恢复；
- HTML 的每个机制、图边和选型结论都有可追溯证据；
- GUI 只做编排视图，不复制业务逻辑。

### 负面

- Artifact/Schema/contract version 数量增加；
- 必须维护精确的阶段依赖和 migration；
- 动态语言的运行时分派仍可能产生 unresolved edge，需要诚实展示证据缺口；
- 全局业务归组仍需要模型，确定性验证只能证明证据边界，不能完全证明语义最佳。

### 风险缓解

| 风险 | 缓解 |
| --- | --- |
| 阶段缓存错误复用 | identity sidecar + Schema/digest/closure/snapshot 四重重验 |
| 图社区切断真实链 | neighbor map + global candidate merge/grouping + cross-community edge audit |
| Provider 并行拥塞 | provider-aware 默认 4、queue 指标、rate-limit backoff |
| 模型语义震荡 | affected closure、冻结通过项、failure-state 去重、最多 2 个新修复状态 |
| 图与文字不一致 | chapter causal flow 与 diagram AST 同源；readability + graph validator 双审 |
| 发布混代 | immutable generation + validate-before-switch + atomic current pointer |

## 被拒绝的方案

1. **一个总 cache key**：拒绝。与阶段依赖不一致，任何实现文件变化都会造成无关重跑。
2. **每个目录/文件一次模型调用**：拒绝。慢、碎片化，并把工程结构误认成业务功能。
3. **只用向量 RAG**：拒绝。无法可靠证明调用、状态、消息和 Worker 因果链。
4. **让模型直接读整仓**：拒绝。成本不可控、边界不可审计、容易漏主链。
5. **让模型直接输出 Mermaid**：拒绝。节点/边/path 不可验证，渲染失败难局部修复。
6. **任何失败都整仓重跑**：拒绝。破坏恢复性和可预测耗时。
7. **核心章节失败后发布占位符**：拒绝。最终报告用于技术选型，缺失核心机制必须 fail closed。
8. **立即拆成微服务/消息队列**：拒绝。当前是本地 CLI/GUI，模块化单体 + durable artifact 已足够；不要为假想规模增加运维复杂度。

## 迁移顺序

1. 引入 `StageContract`/`StageCacheIdentity`，拆掉全局 packaged implementation digest；
2. 用图社区/neighbor map 替换顶层目录分片；默认 provider-aware 4 路并发；
3. 给 chapter/overview/grouping/review 补独立 identity 与复用重验；
4. 收紧语义审校为单次终止判断；
5. 固化 progress/performance v2；
6. 引入 diagram AST/validator/compiler；
7. 增加 fingerprint/freshness 和增量影响传播；
8. 最后优化 HTML 样式，不让 renderer 反向承担分析职责。

## 验证要求

- cache invalidation matrix 单测；
- graph-community partition 覆盖/不重叠/neighbor closure 单测；
- 不同产品类型的业务能力 good/bad case；
- review 终止失败不会触发回写修复测试；
- interruption/resume 与 atomic publication 集成测试；
- performance critical path/cache hit/queue time 单测；
- 真实仓库重放证明功能顺序和机制深度，而非只断言 JSON Schema。

## 参考

- [完整设计](./reference-grounded-production-pipeline-2026-08-12.md)
- [参考项目与 Skill 核验](../references/skills-and-repository-pipeline-reference-2026-08-12.md)
- [现有生产 Pipeline](./production-pipeline.md)
- [Understand Anything](/Volumes/T7/workspace/ontology/graph/repo/understand-anything)
- [DeepWiki Open](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open)
- [RepoAgent](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/RepoAgent)
- [GitDiagram](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/gitdiagram)
- [Repomix](/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/repomix)
