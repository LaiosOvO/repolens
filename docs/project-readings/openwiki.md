# OpenWiki

## 固定版本身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/openwiki`
- origin：`https://github.com/langchain-ai/openwiki.git`
- HEAD：`7531d615216e8cbccf464f66cfbbae3668871c84`
- 工作树：clean
- 许可证：MIT，见 [LICENSE](/Volumes/T7/workspace/ontology/graph/repo/openwiki/LICENSE:1)
- 版本字段：见 [package.json](/Volumes/T7/workspace/ontology/graph/repo/openwiki/package.json:3)

## 一句话定位
它不是“CLI 包了一堆命令”，而是一个会本地生成、持续维护、还能给人看图的代码/知识 Wiki 产品。

## 产品形态判断
- 形态：独立项目 + CLI 优先，附带本地可视化器。
- 不像“薄 skill”：它自己管理初始化、更新、连接器、图形浏览、CI 更新和 agent 提示片段。
- 对你的启示：更适合参考“本地知识库产品”这一面，不适合直接照搬成“只是一条 skill 提示词”。

## 先看结论
- 最值得你借的不是命令分发，而是“本地文档资产如何自维护”。
- 它把 `init/update`、`AGENTS.md/CLAUDE.md` 提示块、CI 定时刷新、无变更跳过、坏链接/坏 Mermaid 自动降级、可视化浏览，连成了一个完整闭环。
- 如果你要做“技术选型 + 代码仓库讲解 + 长期知识管理”，OpenWiki 更像是你的“文档资产层”参考，而不是多 agent 协作层参考。

## 功能清单

### 1. 本地代码 Wiki 初始化与更新
- 提供什么：为当前仓库建立 `openwiki/` 文档目录，并在后续更新时只在必要时重跑。
- 触发到输出：用户执行 `openwiki --init` / `openwiki --update` -> 运行配置与忽略规则加载 -> 必要时进入 agent 生成 -> 输出或刷新 `openwiki/`。
- 谁消费：本地开发者、后续 coding agent、CI。
- 底层机制：运行入口先做 provider/env/load/ignore/no-op 判断，真正 agent 运行在 `runOpenWikiAgent` 主流程里；`update` 前先看是否可以跳过。
- 关键源码：
  [README 初始化与 update](/Volumes/T7/workspace/ontology/graph/repo/openwiki/README.md:47)
  [runOpenWikiAgent](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/index.ts:142)
  [update no-op 分支](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/index.ts:174)
- 真实测试：
  [update-noop.test.ts](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/agent/update-noop.test.ts:55)
  [startup.test.ts](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/cli/startup.test.ts:1)
- 复用判断：`复用`
- 为什么能用：你的系统也需要“仓库讲解结果是长期资产，而不是一次性回答”；这套 init/update/no-op 闭环很适合变成你的知识索引层。

### 2. 自维护的 AGENTS/CLAUDE 提示片段
- 提供什么：每次 code mode 运行时，自动在仓库根目录维护 `AGENTS.md` 和 `CLAUDE.md` 的受管片段，把 agent 指向生成好的 Wiki。
- 触发到输出：`init` 或 code mode setup -> `ensureCodeModeRepoSetup` -> `writeCodeModeAgentSnippets` -> 若文件不存在就创建，存在就只替换 `OPENWIKI` 管理块。
- 谁消费：Codex、Claude Code、后续 repo agent。
- 底层机制：只维护 `<!-- OPENWIKI:START --> ... <!-- OPENWIKI:END -->` 之间的块；如果 marker 异常或重复则拒绝写入，避免破坏人工内容。
- 关键源码：
  [README 对 AGENTS/CLAUDE 的描述](/Volumes/T7/workspace/ontology/graph/repo/openwiki/README.md:145)
  [ensureCodeModeRepoSetup](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/ingestion/code-mode.ts:36)
  [prepareCodeModeAgentSnippet](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/ingestion/code-mode.ts:188)
- 真实测试：
  [创建两个文件](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/ingestion/code-mode.test.ts:38)
  [保留手写内容只刷新受管块](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/ingestion/code-mode.test.ts:53)
  [坏 marker 直接拒绝](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/ingestion/code-mode.test.ts:105)
- 复用判断：`复用`
- 为什么能用：你后面要做“模块选型后给本地编码代理派任务”，这类受管提示块是很实用的桥接方式。

### 3. 定时 CI 更新与本地/CI 双场景共用
- 提供什么：本地先生成，CI 再定时刷新并发 PR，不把“本地文档系统”锁死在手工触发上。
- 触发到输出：用户在 init 时要求创建 workflow -> 生成 `.github/workflows/openwiki-update.yml` -> 后续 CI 执行 `openwiki code --update --print` -> 自动提交 PR。
- 谁消费：团队仓库、长期维护流程。
- 底层机制：workflow 只在缺失时生成，不覆盖自定义工作流；同时把 `openwiki`、`AGENTS.md`、`CLAUDE.md`、workflow 自己都放入 PR add-paths。
- 关键源码：
  [README CI 用法](/Volumes/T7/workspace/ontology/graph/repo/openwiki/README.md:53)
  [ensureCodeModeWorkflow](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/ingestion/code-mode.ts:54)
  [createCodeModeWorkflow](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/ingestion/code-mode.ts:231)
- 真实测试：
  [workflow add-paths 包含 agent 文件](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/ingestion/code-mode.test.ts:166)
  [保留自定义 workflow](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/ingestion/code-mode.test.ts:228)
- 复用判断：`需改造`
- 怎么改：你未来不一定用 GitHub Actions，但“本地先算、CI 只做刷新与审计”的分层很值得保留。

### 4. 生成前的 skeleton critic
- 提供什么：在正式写 Wiki prose 前，先起一个只读 critic 去审查“目录骨架是否覆盖主要模块和关键边界”。
- 触发到输出：`init` 且 `repository` 模式 -> 注入 `skeleton_critic` 子代理 -> 它先独立扫源码/测试，再判定骨架是否 `PASS` 或 `CHANGES_REQUESTED`。
- 谁消费：主生成 agent；最终受益人是读 Wiki 的人。
- 底层机制：critic 不准写文件，只能审读；要求先做独立 repo inventory，再比对 skeleton，避免被草稿带偏。
- 关键源码：
  [critic 描述](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/skeleton_critic.ts:4)
  [critic 审查协议](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/skeleton_critic.ts:16)
  [何时启用 critic](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/skeleton_critic.ts:62)
- 真实测试：
  `未看到 skeleton_critic 的独立测试；这一层更多靠主流程集成约束。`
- 复用判断：`复用`
- 为什么能用：这很适合你的“先技术决策、再产出讲解”的需求。你完全可以把它变成“仓库讲解大纲审计 agent”。

### 5. 无变更跳过与运行元数据
- 提供什么：如果仓库没有发生对文档有意义的变化，更新直接 short-circuit，不浪费模型成本，也不制造 PR 噪音。
- 触发到输出：`update` -> 读取 Git HEAD、上次更新元数据、忽略规则 -> 如果只有 OpenWiki 自己的元数据变化，则返回 `noop`。
- 谁消费：本地运行、CI、遥测。
- 底层机制：`getUpdateNoopStatus` 对比当前 HEAD、工作树、上次更新记录和 ignore 结果；结果写入 telemetry context/outcome。
- 关键源码：
  [README no-op 说明](/Volumes/T7/workspace/ontology/graph/repo/openwiki/README.md:147)
  [noop 判定入口](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/index.ts:174)
  [run metadata 持久化调用点](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/index.ts:564)
- 真实测试：
  [clean HEAD 直接 skip](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/agent/update-noop.test.ts:56)
  [只改 openwiki 文件仍 skip](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/agent/update-noop.test.ts:115)
  [telemetry 记录 noop](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/telemetry/with-run-telemetry.test.ts:47)
- 复用判断：`复用`
- 为什么能用：你后面要跑大量 repo 索引和知识更新，这个机制直接决定成本和噪音是否可控。

### 6. 生成后的结构/链接/图表校验与自动降级
- 提供什么：生成出的 Wiki 不是“写完就算”，还会做 OKF frontmatter 规范化、内部链接校验、Mermaid 语法校验；坏图不会直接炸掉页面，而是降级成可读文本。
- 触发到输出：Wiki 页面生成后 -> OKF 规范化 -> index 同步 -> internal link validation -> Mermaid validate/degrade -> 输出可继续被下一轮修复的文档。
- 谁消费：最终人类读者、后续 agent、可视化器。
- 底层机制：
  OKF 迁移与目录 index 重建在 `index-sync.ts`；
  内链校验会在坏链接上插注释 stamp；
  Mermaid 可走真 parser，也可走保守 heuristic fallback。
- 关键源码：
  [migrateWikiToOkf](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/okf/index-sync.ts:82)
  [synchronizeWikiIndexes](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/okf/index-sync.ts:61)
  [validateWikiInternalLinks](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/wiki-link-validator.ts:92)
  [findInvalidMermaidFences](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/mermaid/validate.ts:94)
  [degradeInvalidMermaidFences](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/mermaid/validate.ts:173)
- 真实测试：
  [index-sync-errors.test.ts](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/okf/index-sync-errors.test.ts:49)
  [wiki-link-validator.test.ts](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/agent/wiki-link-validator.test.ts:27)
  [mermaid-validate.test.ts](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/mermaid/mermaid-validate.test.ts:37)
- 复用判断：`复用`
- 为什么能用：你的目标是“给人看的结构化输出”，这类后处理比“再写一段 prompt”更重要。

### 7. 本地可视化器：图 + Markdown 联动浏览
- 提供什么：把 Wiki 变成一个本地 loopback 网页，左边图、右边文档，文件改动后自动重建图。
- 触发到输出：`openwiki visualize` -> 本地 HTTP server 只监听 `127.0.0.1` -> 提供 `index.html`、`/api/graph`、`/events` -> 浏览器端加载 graph 和 markdown reader。
- 谁消费：人类读者。
- 底层机制：服务端固定路由，不从 URL 派生文件路径；SSE 推送 reload；graph 由本地 markdown/frontmatter/link 解析生成。
- 关键源码：
  [README visualizer 说明](/Volumes/T7/workspace/ontology/graph/repo/openwiki/README.md:73)
  [runVisualizeServer](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/visualize/server.ts:66)
  [createRequestHandler](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/visualize/server.ts:172)
  [WikiGraph 定义](/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/visualize/graph.ts:105)
- 真实测试：
  [server.test.ts](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/visualize/server.test.ts:85)
  [visualize-graph.test.ts](/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/visualize/visualize-graph.test.ts:1)
- 复用判断：`需改造`
- 怎么改：你的最终目标不是“只看 Wiki 图”，而是“按项目看功能、实现、证据、模块索引”。可保留本地 server + graph/SSE 思路，但前端信息架构要重做。

## 对你产品形态的直接启示
- 对“独立项目”：强烈支持。OpenWiki 本身就是一个独立产品，不像单条 skill。
- 对“CLI 优先”：强烈支持。初始化、更新、批量跑仓库、产证据都适合 CLI。
- 对“主 HTML + report/evidence/modules 附件”：强烈支持。OpenWiki 已证明“主阅读面 + 结构化文档资产 + 校验后处理”是可持续的。
- 对“二期薄 Skill”：支持。Skill 更适合做你系统的入口包装，而不是承载核心索引逻辑。

## 不建议直接照搬的部分
- 不建议把它的 CLI 命令结构原样搬进你的产品。你的核心不是“维护自己的 wiki”，而是“讲清楚别人的项目有什么功能、怎么实现、哪些模块可复用”。
- 不建议直接沿用它的页面信息架构。OpenWiki 的阅读对象仍偏 agent memory + wiki browse，不是技术选型报告。

## 事实 / 推断 / 未知
- 事实：它确实覆盖本地初始化、更新、AGENTS/CLAUDE 片段维护、CI workflow、no-op、OKF/link/Mermaid 校验、visualizer，本地测试也很全。
- 推断：它最适合做你的“知识资产层”和“生成后校验层”参考。
- 未知：真实大仓库上的生成质量与多轮更新漂移，需要跑真实仓库才知道；单从源码无法证明文档质量一定稳定。
