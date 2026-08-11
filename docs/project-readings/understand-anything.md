# Understand Anything 阅读笔记

## 固定身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/understand-anything`
- origin：`https://github.com/Egonex-AI/Understand-Anything.git`
- HEAD：`fe8c5bc591716aafd79b4765549328f08ef5a52e`
- 工作树：clean
- 许可证：MIT

## 一句话定位
Understand Anything 的主张不是“生成一套固定文档”，而是“把代码库、知识库、文档先变成 interactive knowledge graph，再把 chat、diff、explain、onboarding、dashboard、skill workflow 都建立在这张图上”。

## 产品形态判断
- 形态：插件/skill 产品族，不是单一 CLI。
- 接口面：`/understand`、`/understand-dashboard`、`/understand-diff`、`/understand-explain`、`/understand-onboard`、`/understand-knowledge` 等命令，以及 viewer/dashboard。
- 对我们的价值：它更适合作为“知识图谱 + dashboard + 多 skill 工作流”的参考，而不是一期主框架。

## 先看什么
如果你的目标是“快速理解项目、并且以后还能把知识管理做起来”，这个仓库最值得看的 6 个点是：

1. knowledge graph 本体
2. incremental / fresh / stale 机制
3. chat / diff / explain 三类上下文构造
4. onboarding / guided tours
5. dashboard / viewer
6. skill / plugin 多平台分发

## 人类可感知功能

### 1. Knowledge Graph 本体
- 提供什么：把代码库、知识库或文档抽成统一图谱，节点包含文件、函数、类、层、tour、summary 等信息。
- 触发 -> 接管 -> 输出 -> 消费：
  用户执行 `/understand` 或知识库命令 -> 多 agent 管线接管 -> 产出 `.ua/knowledge-graph.json` -> chat、dashboard、diff、explain、onboard、viewer 全都消费它。
- 底层机制/技术：
  README 明确说初次分析会生成 `.ua/knowledge-graph.json`；`buildChatContext`、`buildDiffContext`、`buildExplainContext` 都直接从 `KnowledgeGraph` 取节点、边、层。
- 关键证据：
  - 产品定位与 knowledge graph：[README.md](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md:51)
  - `/understand` 产出 `.ua/knowledge-graph.json`：[README.md](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md:122)
  - package 依赖里直接引入 `graphology`：[understand-anything-plugin/package.json](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/package.json:11)
  - ChatContext 从 graph 构建：[understand-anything-plugin/src/context-builder.ts](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/src/context-builder.ts:20)
- 真实相关测试：
  - viewer 直接读取 `knowledge-graph.json`：[tests/skill/viewer/test_viewer.test.mjs](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/tests/skill/viewer/test_viewer.test.mjs:120)
- 可复用：这正好对应你要的“本地知识管理”和“长时间 context engine”底座。
- 改造使用：我们可以借“统一图谱 + 多消费器”的组织方式，但图谱 schema 改成更适合技术选型和项目讲解。
- 不照搬：不要把所有能力都压成 skill 命令再反推产品。
- 未知：超大项目上图谱大小与交互性能。

### 2. Fresh / Dirty / Stale / Incremental
- 提供什么：首次全量分析后，后续只分析变化文件，并把图谱 freshness 状态显式暴露给 viewer/dashboard。
- 触发 -> 接管 -> 输出 -> 消费：
  重新运行 `/understand` 或自动更新 -> 变更检测接管 -> 更新图谱与 staleness 状态 -> dashboard/viewer 展示 fresh / stale / dirty。
- 底层机制/技术：
  README 明确说后续默认 incremental；viewer 提供 `staleness.json`；viewer 测试验证 graph commit 和 HEAD commit 对比。
- 关键证据：
  - README 的 incremental 说明：[README.md](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md:128)
  - auto-update / commit hook：[README.md](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md:177)
  - viewer 的 freshness 报告测试：[tests/skill/viewer/test_viewer.test.mjs](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/tests/skill/viewer/test_viewer.test.mjs:133)
- 真实相关测试：
  - `staleness.json` 返回 `fresh` 状态和 commit hash：[tests/skill/viewer/test_viewer.test.mjs](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/tests/skill/viewer/test_viewer.test.mjs:143)
- 可复用：你后面要做“长期研究/本地知识更新”，这部分值得借。
- 改造使用：一期先记录 repo commit + 产物 commit；二期再做 stale 页面和自动更新。
- 不照搬：不必一期就做完整 viewer freshness API。
- 未知：复杂工作树 dirty 状态如何影响其判断。

### 3. Chat / Diff / Explain 上下文构造
- 提供什么：不是直接把整张图喂给模型，而是按用途裁切成 chat、diff、explain 三种上下文。
- 触发 -> 接管 -> 输出 -> 消费：
  用户提问 / 看 diff / 深挖文件 -> 对应 builder 接管 -> 返回裁剪后的 nodes / edges / layers / prompt -> LLM 或前端消费。
- 底层机制/技术：
  `buildChatContext` 先 search 再扩一跳；`buildDiffContext` 用 changed files 找 ripple effect；`buildExplainContext` 支持 file 和 file:function 两种定位。
- 关键证据：
  - 统一导出入口：[understand-anything-plugin/src/index.ts](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/src/index.ts:1)
  - chat context：[understand-anything-plugin/src/context-builder.ts](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/src/context-builder.ts:25)
  - diff context：[understand-anything-plugin/src/diff-analyzer.ts](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/src/diff-analyzer.ts:18)
  - explain context：[understand-anything-plugin/src/explain-builder.ts](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/src/explain-builder.ts:18)
- 真实相关测试：
  - 本轮阅读里我没有逐个展开 builder 的独立单测；当前更强证据是源码本身和 viewer/skill 端到端测试。
- 可复用：这是很强的参考，因为你后面不仅要“项目讲解”，还要“选了模块后继续往下问”。
- 改造使用：我们可以把 repo-teacher 也拆成 `overview context`、`feature context`、`module context` 三类，而不是一个万能 prompt。
- 不照搬：不要先上太多交互命令；一期先把“读项目”这个主闭环做顺。
- 未知：不同 builder 在极大图上的压缩效果。

### 4. Guided Tours / Onboarding
- 提供什么：给新人一条有顺序的阅读路径，而不是只给一张图。
- 触发 -> 接管 -> 输出 -> 消费：
  用户执行 `/understand-onboard` 或点击 tour -> `buildOnboardingGuide` 接管 -> 输出 Markdown onboarding guide，带架构层、key concepts、tour、file map、复杂点提示 -> 人类直接阅读。
- 底层机制/技术：
  onboarding 是从 graph 的 project、layers、tour、nodes、edges 中组装出结构化 Markdown。
- 关键证据：
  - README 的 Guided Tours / onboarding 功能：[README.md](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md:79)
  - `/understand-onboard` 命令说明：[README.md](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md:168)
  - onboarding builder：[understand-anything-plugin/src/onboard-builder.ts](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/src/onboard-builder.ts:3)
- 真实相关测试：
  - 本轮没有定位到单独 onboarding builder 测试；当前依据是 builder 源码。
- 可复用：这和你一直强调的“别堆文字，要有叙述逻辑”完全同向。
- 改造使用：我们的主入口页就应该借它这个思路，先给“阅读路径”，再给“所有细节附件”。
- 不照搬：不要输出长篇 README 风格文本，应改成短主线 + 可点开的附件结构。
- 未知：tour 生成顺序的质量和稳定性。

### 5. Dashboard / Viewer
- 提供什么：把图谱变成可搜索、可点击、可查看源码、可看 freshness 的本地浏览体验。
- 触发 -> 接管 -> 输出 -> 消费：
  用户执行 `/understand-dashboard` 或启动 viewer -> dashboard/viewer 接管 -> 暴露首页、graph、staleness、file content -> 人类在浏览器里探索。
- 底层机制/技术：
  viewer 有 token gate；只允许读取图中出现过的文件；同时兼容 `.ua/` 与旧 `.understand-anything/` 目录。
- 关键证据：
  - dashboard 命令与描述：[README.md](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md:148)
  - viewer 提供首页：[tests/skill/viewer/test_viewer.test.mjs](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/tests/skill/viewer/test_viewer.test.mjs:114)
  - token gate：[tests/skill/viewer/test_viewer.test.mjs](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/tests/skill/viewer/test_viewer.test.mjs:120)
  - file-content allowlist：[tests/skill/viewer/test_viewer.test.mjs](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/tests/skill/viewer/test_viewer.test.mjs:154)
  - 兼容旧目录 `.understand-anything/`：[tests/skill/viewer/test_viewer.test.mjs](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/tests/skill/viewer/test_viewer.test.mjs:181)
- 真实相关测试：
  - viewer 这一层的测试是我这次阅读里最完整的一组端到端证据。
- 可复用：对你未来“本地知识管理 + 图谱 dashboard”很有参考价值。
- 改造使用：我们可以先做轻量 HTML 附件页，后续再升级成本地 viewer。
- 不照搬：不要一期就做完整 dashboard + file server + token gate。
- 未知：前端图交互在超大图上的体验。

### 6. Skill / Plugin / 多平台工作流
- 提供什么：同一套理解能力可以装到 Claude Code、Codex、Cursor、Copilot、OpenCode、Hermes 等环境里。
- 触发 -> 接管 -> 输出 -> 消费：
  用户安装插件/skill -> 各平台命令调用 -> skill 读取本地图谱与构建器 -> 输出解释、dashboard、diff、knowledge 流程。
- 底层机制/技术：
  README 明确给多平台安装；测试中还专门检查 skill 命令片段的 quoting 和安全性。
- 关键证据：
  - 多平台安装区：[README.md](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md:189)
  - Codex 安装与 `$understand` 约定：[README.md](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md:216)
  - skill 安全回归测试：[tests/skill/understand/test_skill_security_snippets.test.mjs](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/tests/skill/understand/test_skill_security_snippets.test.mjs:13)
- 真实相关测试：
  - skill 片段 quoting、路径和不可信输入提示：[tests/skill/understand/test_skill_security_snippets.test.mjs](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/tests/skill/understand/test_skill_security_snippets.test.mjs:35)
- 可复用：这说明你的二期“薄 skill 壳”路线是可行的。
- 改造使用：一期核心应该先做独立项目，二期再把主能力挂到 Codex/Opencode/Hermes。
- 不照搬：不要从一开始就以 skill 为第一等公民。
- 未知：各平台分发的一致性维护成本。

## 对我们产品形态的直接启示

### 该借什么
- 借“统一 knowledge graph + 多个上下文 builder + dashboard/viewer”的三层分离。
- 借 onboarding / guided tour 这种“先给阅读路径”的表达方式。
- 借 viewer 测试里的 freshness 和 file-content allowlist 思路。

### 该改成什么
- 我们的一期主产物不该是一整张交互图，而应是：
  - 主叙述页：定位、重点功能、阅读顺序。
  - 项目附件页：功能卡片。
  - 模块附件页：源码索引。
  - 机器附件：graph/report/evidence JSON。
- 如果后面做本地知识管理和数字分身，Understand Anything 可以成为那部分的主要参考之一。

### 明确不照搬
- 不把一期产品直接做成 plugin/skill 集合。
- 不先做多平台安装器。
- 不先做重型 dashboard 再回头补“人类能看懂的叙述页”。

## 事实 / 推断 / 未知

### 事实
- 这是一个以 knowledge graph 为核心、skill/plugin 为分发面的项目。
- 它有 chat、diff、explain、onboard、dashboard、knowledge wiki 多条真实能力线。
- viewer 与 skill 侧都有真实测试，不只是 README 宣传。

### 推断
- 它对你未来“本地知识库 + 图谱 + 数字分身 + long context”价值很高。
- 但对你当前一期“快速技术选型的 repo teaching”来说，它更适合作为二期知识层参考，而不是一期主骨架。

### 未知
- 图谱规模增长后的交互与性能上限。
- 多平台分发维护是否会侵蚀核心产品开发速度。

## 对“独立项目 + CLI + 主叙述页 + 附件页 + 二期薄 Skill”的结论
- Understand Anything 不支持“先做 skill 再说”，反而更说明核心能力要独立出来。
- 它最值得借的是知识图谱、onboarding、dashboard/viewer 和多上下文 builder。
- 对你当前阶段，最佳吸收方式是：
  - 一期借它的“guided reading / knowledge graph 思维”
  - 二期再借它的 dashboard、knowledge、skill/plugin 分发
