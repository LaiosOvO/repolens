# SourceBridge 阅读笔记

## 固定身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`
- origin：`https://github.com/sourcebridge-ai/sourcebridge.git`
- HEAD：`2a128bf0c8461fae91d2b424d9168ddf205bb11b`
- 工作树：dirty。当前本地状态是 `D LICENSE`，不能写成 clean。
- 许可证事实：README 徽标声明 AGPL-3.0，源码文件头普遍写 `SPDX-License-Identifier: AGPL-3.0-or-later`。本地 `LICENSE` 文件被删，但不能据此写“无许可证”。

## 一句话定位
SourceBridge 不是“代码搜索器”，而是“面向陌生代码库的 field guide 平台”：先把仓库建成结构化索引，再持续生成 cliff notes、learning path、code tour、workflow story、需求追踪、impact report、review 和 MCP/VS Code 消费面。

## 产品形态判断
- 形态：独立产品，不是单一 skill，也不是纯 CLI。
- 接口面：Web UI + CLI + MCP + VS Code 扩展 + GraphQL/API。
- 对我们项目的启示：它更像你未来二期“大系统”的参考，而不是一期 `repo-teacher` 直接照搬的实现壳。

## 先看什么
如果你的目标是“快速技术选型，看每个系统到底提供什么功能、底层怎么做”，SourceBridge 最值得先看的不是入口命令，而是下面 6 组能力：

1. 代码索引与增量更新
2. Field guide 生成链路
3. 语义搜索与图检索消费面
4. requirements / impact / review
5. MCP + Web + VS Code 多入口接入
6. freshness / stale / worker 常驻执行

## 人类可感知功能

### 1. 代码索引
- 提供什么：把仓库解析成文件、符号、关系、模块，作为后续一切 field guide / review / ask 的底座。
- 触发 -> 接管 -> 输出 -> 消费：
  用户执行 `sourcebridge index <path>` -> CLI `runIndex` 接管 -> 产出 `IndexResult` 并写入图存储 -> Web、MCP、worker、review、requirements 全都消费这份底座。
- 底层机制/技术：
  Go CLI 调 `internal/indexer.Indexer`；解析层是 tree-sitter；持久化批量写到 SurrealDB 的 `ca_file` / `ca_symbol` / `ca_calls` / `ca_module` 等表。
- 关键证据：
  - 产品宣称与能力边界：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:19)
  - 功能列表里的 Code Indexing：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:47)
  - CLI 入口 `sourcebridge index`：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:346)
  - 索引命令实现：[cli/index.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/cli/index.go:18)
  - 增量索引/branch freshness 入口 `IndexFiles`：[internal/indexer/indexer.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/internal/indexer/indexer.go:60)
  - 批量落库 `buildIndexBatch`：[internal/db/index_result.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/internal/db/index_result.go:33)
- 真实相关测试：
  - CLI telemetry 测试基座：[cli/main_test.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/cli/main_test.go:13)
- 可复用：`repo-teacher` 可以借它“索引先行、消费面统一吃索引”的思路。
- 改造使用：我们应把“索引”收窄成 repo teaching 所需的 symbol/module/evidence 索引，而不是复制整套数据库 schema。
- 不照搬：SurrealDB schema 和整套平台化存储层太重，不适合一期。
- 未知：全量索引在超大 monorepo 的资源上限和维护成本。

### 2. Field Guide 生成
- 提供什么：自动生成 cliff notes、learning paths、code tours、workflow stories、architecture diagrams 等“人类读得懂”的知识产物。
- 触发 -> 接管 -> 输出 -> 消费：
  用户在 Web / VS Code / CLI 请求 guide -> API/worker 调知识生成链路 -> 产出结构化 artifact 和分段 evidence -> Web、MCP、VS Code 面板消费。
- 底层机制/技术：
  worker 常驻做 AI reasoning；知识产物按 scope 存储，artifact 有 status / stale / readiness 状态；cliff notes 有专门测试。
- 关键证据：
  - README 的产品定位和 field guide 列表：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:19)
  - Key Features 里的 Field Guides：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:50)
  - worker 职责说明：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:252)
  - GraphQL 知识生成功能守卫：[internal/api/graphql/knowledge_generation.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/internal/api/graphql/knowledge_generation.go:14)
  - MCP 读取 cliff notes：[internal/api/rest/mcp.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/internal/api/rest/mcp.go:1817)
- 真实相关测试：
  - Cliff notes 结构/证据测试：[workers/tests/test_cliff_notes.py](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/workers/tests/test_cliff_notes.py:190)
- 可复用：这正是你要的“不是平铺直叙，而是能让人快速理解”的方向。
- 改造使用：我们可以借“artifact + evidence + stale 状态”的内容模型，但输出格式改成我们的一主页多附件。
- 不照搬：不要一期就复制其多类 artifact 与 worker RPC 全家桶。
- 未知：不同 artifact 的 prompt、刷新策略、质量控制成本。

### 3. 语义搜索与图检索
- 提供什么：按名字搜，也按语义搜；结果仍然回到“符号/代码证据/相关层级”的结构化输出。
- 触发 -> 接管 -> 输出 -> 消费：
  用户搜索或 ask -> MCP `search_symbols` / ask 路由 -> hybrid retrieval / graph search -> 返回 symbol 命中、references、上下文层。
- 底层机制/技术：
  README 明确有 semantic search；MCP 层的 `search_symbols` 会走 `searchSvc.Search` 的 hybrid 路径，但最终保持稳定的 symbol-only 响应形状。
- 关键证据：
  - README 截图与语义搜索描述：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:40)
  - embeddings/freshness 配置：[config.toml.example](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/config.toml.example:74)
  - MCP `search_symbols` 和 hybrid search：[internal/api/rest/mcp.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/internal/api/rest/mcp.go:1313)
- 真实相关测试：
  - 这里我没有在本次阅读里定位到专门的 `search_symbols` 回归测试文件；这是当前阅读边界，不等于功能不存在。
- 可复用：对我们的一期产物，真正可借的是“搜索结果仍然服务于人类教学页”，而不是只吐 JSON hit 列表。
- 改造使用：可以把 search 当成二期增强，而不是一期必做。
- 不照搬：不要先上复杂的 hybrid retrieval，再反过来找展示目标。
- 未知：它的召回/排序质量和索引体积代价。

### 4. Requirements / Impact / Review
- 提供什么：把需求、代码、影响范围、review 放到同一张图上。
- 触发 -> 接管 -> 输出 -> 消费：
  导入 requirement 或发起 review / impact -> CLI/API/MCP 接管 -> 产出 linked requirements、impact report、AI review -> Web、VS Code、MCP 消费。
- 底层机制/技术：
  `import` 命令把 Markdown/CSV requirement 写入图；`review` 命令做结构化审查；MCP 直接暴露 `get_requirements`、`get_impact_report`、`review_diff_against_requirements`、`impact_summary`。
- 关键证据：
  - README 功能列表里的 Requirement Tracing / Code Review / Impact Analysis：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:51)
  - requirements 导入实现：[cli/import.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/cli/import.go:21)
  - review 命令实现：[cli/review.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/cli/review.go:19)
  - MCP requirements / impact / review 工具注册：[internal/api/rest/mcp.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/internal/api/rest/mcp.go:593)
- 真实相关测试：
  - review walker 防止把构建产物当源码审查：[cli/review_walker_test.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/cli/review_walker_test.go:14)
- 可复用：这是你后面“从调研 -> 决策 -> 需求 -> ticket”的重要参考层。
- 改造使用：一期 repo-teacher 只需做“功能 -> 模块 -> 源码证据”索引，不必立刻做 requirement tracing。
- 不照搬：先别把需求管理、影响分析、review 全压进一期教学产品。
- 未知：requirements 数据模型是否适合你的本地知识库体系。

### 5. MCP / Web / VS Code 多入口
- 提供什么：同一份系统能力可以被 Web、MCP 客户端、VS Code 扩展和 CLI 共用。
- 触发 -> 接管 -> 输出 -> 消费：
  用户从 Web/IDE/Agent 发起请求 -> API/MCP 路由 -> worker/graph/search 层 -> 返回结构化结果与状态。
- 底层机制/技术：
  Go API server 暴露 REST/GraphQL/MCP；Web 探测 MCP 能力；VS Code 通过树视图、状态栏、code lens、ask commands 消费。
- 关键证据：
  - 总体架构图：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:219)
  - Web/CLI/MCP/GraphQL 客户端层：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:224)
  - MCP handler 与工具注册：[internal/api/rest/mcp.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/internal/api/rest/mcp.go:329)
  - Web 端 MCP probe：[web/src/lib/use-server-capabilities.ts](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/web/src/lib/use-server-capabilities.ts:42)
  - VS Code 功能清单：[plugins/vscode/README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/plugins/vscode/README.md:10)
  - VS Code 扩展激活与多树视图注册：[plugins/vscode/src/extension.ts](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/plugins/vscode/src/extension.ts:48)
- 真实相关测试：
  - VS Code 可见常量与配置回归我在本轮 grep 中看到测试存在，但未逐一深读；当前最直接的功能证据仍以扩展 README 和入口代码为准。
- 可复用：这说明你的最终系统应该是“核心能力层 + 多入口壳”，不是“一个 skill 里塞完所有逻辑”。
- 改造使用：一期先做独立项目 + CLI/HTML 输出；二期再做薄 skill 和 agent/IDE 入口。
- 不照搬：不要一期就做完整 VS Code 插件或完整 MCP server。
- 未知：多入口一致性维护成本。

### 6. Incremental / Freshness / Worker 常驻
- 提供什么：仓库变更后，不是把所有知识重算一遍，而是区分 branch、stale、refresh、auto-regen、worker concurrency。
- 触发 -> 接管 -> 输出 -> 消费：
  仓库 reindex / 文件变化 -> `IndexFiles` 或后台 freshness 逻辑接管 -> 旧 artifact 标 stale、新 artifact 排队刷新 -> Web/MCP/VS Code 展示最新状态。
- 底层机制/技术：
  `IndexFiles` 只重算受影响文件并重建聚合；`config.toml.example` 明确有 stale 标记、auto-regen、每 repo 限流、并发上限；Python worker 常驻做推理任务。
- 关键证据：
  - 增量索引与 branch mismatch/freshness 注释：[internal/indexer/indexer.go](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/internal/indexer/indexer.go:60)
  - freshness / stale / auto-regen 配置：[config.toml.example](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/config.toml.example:119)
  - worker 进程在系统中的位置：[README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md:417)
- 真实相关测试：
  - cliff notes 高置信 canary 等 freshness/quality 线索在 `workers/tests/test_cliff_notes.py` 可见，但本轮没有把整套 freshness 回归测试逐一展开。
- 可复用：这部分非常值得借，因为你也明确要 long context / local loops / graph engineering / 多 agent freshness。
- 改造使用：一期可以先只做“生成时记录 commit/hash/evidence”；二期再做 stale 与自动刷新。
- 不照搬：别把 branch-scoped freshness、redis、队列限流一口气搬进 repo-teacher。
- 未知：它的 stale 粒度和自动重生策略在你“知识库 + 项目教学”场景里是否过重。

## 对我们产品形态的直接启示

### 该借什么
- 借“先索引，再生成人类导向产物，再给多个入口消费”的总顺序。
- 借“artifact + evidence + stale/freshness”的内容模型。
- 借“同一个功能既能给 Web 看，也能给 agent/MCP/IDE 看”的分层意识。

### 该改成什么
- 我们一期不做 SourceBridge 这种完整平台，而是做一个独立项目，主接口先定为 CLI。
- 主输出不该只有一个巨大 HTML，而应是：
  - 一个主入口页：只讲这个项目的定位、该先看哪些功能、推荐阅读顺序。
  - 若干附件：`project overview`、`feature cards`、`evidence/modules`、`code path index`。
  - 机器附件：`report.json`、`evidence.json`、`module-index.json`。

### 明确不照搬
- 不复制它的数据库与多服务部署壳。
- 不复制其 AGPL 代码到我们的核心实现里。
- 不把 requirements/review/impact/MCP/VS Code 一期全做完。

## 事实 / 推断 / 未知

### 事实
- SourceBridge 自己把自己定义成 requirement-aware code comprehension platform，核心卖点是 field guides、requirements、reviews、impact、MCP、VS Code。
- 它是 Web + CLI + MCP + VS Code + worker 的完整产品，不是单一 skill。
- 索引、field guide、MCP、review、freshness 都有真实代码和测试/文档证据。

### 推断
- 对你的目标而言，SourceBridge 最有价值的不是“某个具体 UI”，而是“内容产物模型”和“多入口消费层”的设计。
- 它更适合作为二期/三期平台能力参考，不适合作为一期 repo-teacher 的直接壳。

### 未知
- 其 semantic retrieval 质量、artifact 生成成本、生产环境运维复杂度。
- 哪些知识产物类型在你的项目里是真正高频刚需，哪些只是“看起来很全”。

## 对“独立项目 + CLI + 主叙述页 + 附件页 + 二期薄 Skill”的结论
- SourceBridge 支持我们把产品做成“独立项目”，而不是先写一个 skill。
- CLI 适合做一期执行入口，但最终不能停留在 CLI 本身，必须输出给人看的主叙述页。
- 主叙述页应该只讲“项目定位 / 关键功能 / 先看哪里 / 哪些代码模块负责这些功能”。
- 附件页再承接“模块索引 / 源码证据 / 关系图 / 机器输出”。
- skill 最适合二期做薄壳：只负责调用生成、导航和按需展开，不负责承载全部核心逻辑。
