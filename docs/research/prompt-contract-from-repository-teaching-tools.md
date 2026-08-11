# 仓库教学工具的 prompt 契约研究

调研日期：2026-08-10  
目标：把“仓库索引/仓库教学”类工具里真正可复用的输出契约抽出来，变成 `repo-teacher` 的 prompt 条款，而不是继续堆一个万能大 prompt。

## 结论

最值得复用的不是某个项目的 UI 风格，而是它们对“先讲什么、必须输出什么证据、怎样从功能讲到底层链路”的硬约束。

这次核验下来，最该吸收的分成三层：

1. **结构层**：先讲使用路径、真实入口、主脊柱调用链，再讲模块和源码证据。
2. **机制层**：每个功能必须回答“触发什么、谁接管、如何流转、哪里终止、失败怎么表现”。
3. **证据层**：每个结论必须落到文件、符号、行号、测试、图或中间产物；不允许用 regex/模糊规则冒充功能判断。

## 采用矩阵

| 来源 | 核验到的核心输出契约 | 可以直接写进 prompt 的条款 | 采用 |
|---|---|---|---|
| [`tutorial-gen`](/Users/admin/.codex/skills/tutorial-gen/SKILL.md) | 先讲 usage，再讲真实入口和主脊柱调用链；函数/方法级切片；完整源码必须跟在片段后；图表、双链、噪音目录排除 | “章节顺序固定为 usage → overview → 真实入口 → 主脊柱 → 模块分层 → 数据流 → 扩展点；每段解释必须给函数级证据和完整源码。” | 采用 |
| [`tutorial-gen-pure`](/Users/admin/.codex/skills/tutorial-gen-pure/SKILL.md) | 章节拆分不能机械分文件数，必须按入口、主脊柱、模块边界、数据流和 usage 路线 | “不许按目录平均切章；必须由功能入口和调用链驱动分章。” | 采用 |
| [`tutorial-gen-full`](/Users/admin/.codex/skills/tutorial-gen-full/SKILL.md) | 单一入口、全能力纯 skill，强调从零生成、先讲怎么用、再讲入口/主脊柱/模块 | “如果是 fresh generate，必须声明从空目录重建；不要把旧目录复制后假装新生成。” | 采用 |
| [`Serena`](/Volumes/T7/workspace/ontology/graph/repo/serena/README.md) + [`workflow`](/Volumes/T7/workspace/ontology/graph/repo/serena/docs/02-usage/040_workflow.md) + [`memories`](/Volumes/T7/workspace/ontology/graph/repo/serena/docs/02-usage/045_memories.md) | 以符号级工具和记忆系统为核心；文档结构固定为 what / key types / primary call paths / invariants / failure modes / dependencies / rationale / gaps | “每个功能页都要有：是什么、关键类型、主调用链、不变量、失败模式、依赖、设计理由、已知缺口。” | 采用 |
| [`SourceBridge`](https://github.com/sourcebridge-ai/sourcebridge) + [`cliff notes`](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/workers/knowledge/prompts/cliff_notes.py) + [`learning path`](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/workers/knowledge/prompts/learning_path.py) + [`code tour`](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/workers/knowledge/prompts/code_tour.py) + [`workflow story`](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/workers/knowledge/prompts/workflow_story.py) | 直接规定 JSON 结构、证据字段、章节顺序、受众语气；工程师/产品/操作员有不同 voice；不允许空泛总结 | “按受众切 voice：工程师看文件/符号/调用链，产品看结果和 tradeoff，操作员看指标、故障和 recovery。” | 采用 |
| [`SourceBridge` voice profiles](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/prompts/audience/for-engineers.md) / [`for-product`](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/prompts/audience/for-product.md) / [`for-operators`](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/prompts/audience/for-operators.md) | 工程师 70/30，产品 20/80，操作员先给可执行内容；都要求具体名词、可验证事实、显式 tradeoff | “同一个功能要按 audience 输出不同版本，不能用一套泛化叙述混过去。” | 采用 |
| [`CodeBoarding`](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md) + [`summary-interactive`](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/docs/summary-interactive.md) + [`orchestration`](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_workflows/orchestration.py) | 静态分析先行，LLM 只负责解释/命名；统一中间产物 `analysis.json`；full / incremental / partial 分层更新 | “先产结构化中间件，再渲染人类页面；增量更新必须基于 baseline 和受影响范围。” | 采用 |
| [`DeepWiki-Open`](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/README.md) + [`API README`](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/README.md) | 自动 wiki、源码链接、视觉图、codemap guided tours、问答；以 repo 为单位组织层级内容 | “首页必须先给导航和源链接，子页必须能回到源码证据；支持继续追问。” | 采用 |
| [`DeepWiki`](https://docs.devin.ai/work-with-devin/deepwiki) | 自动索引、自动 wiki、架构图、相关源码、继续追问、可通过 `pages` / `repo_notes` steering | “允许人工 steering，但生成内容必须可回溯到 source files 和固定页面层级。” | 采用 |
| [`PocketFlow-Tutorial-Codebase-Knowledge`](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/README.md) + [`design`](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/docs/design.md) + [`flow.py`](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/flow.py) + [`nodes.py`](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py) | FetchRepo → IdentifyAbstractions → AnalyzeRelationships → OrderChapters → WriteChapters → CombineTutorial；章节顺序由抽象/依赖驱动 | “先识别核心抽象，再分析关系，再排序，再写章节，最后合并；不要按文件树平均切章。” | 采用 |
| [`Understand Anything`](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/understand-anything-plugin/skills/understand/SKILL.md) | 产出 `knowledge-graph.json`；有 full / incremental / review；有 freshness / stale；chat / diff / explain / onboard 使用不同上下文构造 | “如果有图谱，就明确 freshness；如果有多个上下文 builder，就不要用一个万能 prompt。” | 采用 |
| [`code-tour`](https://github.com/github/awesome-copilot/tree/main/skills/code-tour) | 真实 file/line stop，按故事顺序组织，面向不同角色生成导览 | “导览不是文件清单，必须是带真实锚点的故事线。” | 采用 |
| [`codebase-onboarding`](https://github.com/affaan-m/ECC/blob/main/skills/codebase-onboarding/SKILL.md) | overview / tech stack / architecture / directories / lifecycle / conventions / where to look | “首屏要让新读者快速定位系统是什么、目录怎么走、生命周期怎么跑。” | 采用 |
| [`learn-codebase`](https://github.com/ktaletsk/learn-codebase) | 用苏格拉底式提问、主动回忆、学习记录来深化理解 | “只作为深度学习模式，不作为默认首屏；默认报告必须先给结论和证据。” | 采用 |
| [`RepoAgent`](https://github.com/OpenBMB/RepoAgent) | 既有研究笔记显示其重点在 AST、对象级文档、双向调用关系、增量更新 | “对象文档必须绑定 AST/调用关系/增量变更，不能只做文本摘要。” | 部分采用 |

## 不采用项

| 不采用 | 原因 |
|---|---|
| 用正则识别“功能是什么” | 你已经明确禁止；而且它会把语义判断偷换成字符串判断，和仓库教学目标冲突。 |
| 一个万能 prompt 同时承担 overview、深挖、教学、运维、选型 | 这些读者、结构和证据粒度不同，混在一起只会把首页写糊。 |
| 只输出 Markdown 平铺总结 | 需要可导航页、可回溯证据、可增量更新的结构化产物。 |
| 先做巨大的架构总图，再回头补功能链路 | 这会把“看懂项目”变成“看懂图”，不利于陌生仓库入口。 |
| 把核心逻辑做成 skill 壳 | 核心能力应该是独立项目/独立索引，skill 只做薄适配。 |

## 可以直接复制的 prompt 条款

### 1. 首屏顺序

- 先讲用户能做什么，再讲它为什么存在，再讲它如何工作。
- 每个功能节必须按这个顺序回答：`What it does` → `Why it exists` → `What it affects` → `Behavioral contract` → `Mechanism` → `Call chain` → `Failure modes` → `Dependencies` → `Tests` → `Sources`。
- 不要把“目录浏览”当成理解；先给使用路径和真实入口。

### 2. Voice 规则

- 工程师页必须以文件、符号、调用链、失败模式和不变量为主。
- 产品页必须以用户结果、约束、tradeoff 和影响面为主，不能出现方法签名或包路径。
- 操作页必须以指标、日志字段、告警、恢复步骤和升级路径为主。
- 如果一句话不能说明“谁触发、谁接管、谁产出、谁消费”，就不能直接放进正文。

### 3. Voice 链路必须讲清楚

- `Voice` 章节必须显式写成链路，而不是一句“本地录音、语音识别与朗读输出”。
- 标准链路要写清：`本地录音/唤醒` → `语音切段/转写` → `转写文本归一化` → `agent loop/模型决策` → `朗读输出/TTS`。
- 每一步都必须说明输入、输出、失败点、fallback、以及它在整条链里的职责。
- 不允许把中间环节省略成“语音交互”这种空词。

### 4. Agent loop 必须是循环

- 如果代码里确实是循环，就必须明确写出是 `while`、事件循环、队列 drain，还是递归调度，不能只写“会反复执行”。
- 每次迭代必须写清：当前输入状态、模型产出、工具调用、观测回填、下一轮如何决定。
- 必须写清终止条件：正常完成、预算耗尽、外部取消、工具错误、守卫触发，分别是什么。
- 如果存在 tool budget / evidence budget / max iterations，必须把数值、作用和触发后的行为写出来。

### 5. Graph / router 必须讲具体作用

- 不能只写“router 决定下一步”；必须写 router 读了什么 state、看了什么条件、返回了什么分支、为什么这么分。
- 如果图是动态的，必须说明动态边界在哪里、谁有权扩图、谁负责合并状态、谁决定 join。
- 如果 router 只是纯函数，也要明确它不持久化、不执行副作用，只做分支选择。

### 6. 证据规则

- 每个重要结论必须有文件、符号、行号、测试或中间产物证据。
- 不允许使用 synthetic labels、空泛的“repository_summary”式占位词，或自造模块名。
- 不允许说“根据经验看起来像”；必须说“从哪些文件/符号/测试能看到”。
- 不能把没有证据的推断写成事实，推断必须显式标成 inferred。

### 7. 章节与输出规则

- 章节拆分必须按入口、主脊柱、模块边界、数据流和使用路径来分。
- 不允许按文件数平均切章，也不允许按目录树机械切章。
- 教程类输出必须包含图、路径和源码片段；如果是 repo teaching，至少要有 architecture、capability、call chain、datamodel 四类图中的相关部分。
- 如果是章节型输出，必须先给章节顺序，再给正文，再给证据附件。

### 8. 增量与 freshness

- 如果工具支持增量更新，必须说明 baseline、commit hash、受影响范围和 stale/fresh 状态。
- 不能把一次性生成写成持续维护工具；如果有 freshness 机制，要明确谁触发刷新、何时标 stale、何时重算。

### 9. 禁止 regex 做功能实现

- `regex` 不能用于判断某个功能、机制或章节该不该出现。
- `regex` 不能作为仓库理解、路由选择、模块分类或证据筛选的最终决策层。
- 只有当它是明确的文本工具，而不是功能判断机制时，才允许出现。
- 任何“靠正则猜功能”的实现都应视为不合格。

### 10. Skill / 项目边界

- 核心理解能力必须是独立项目；skill 只能做薄入口或导出壳。
- 如果一个 skill 既要负责索引、又要负责教学、又要负责更新，那就说明边界错了。
- 导出的 skill 必须能回指到固定仓库、固定 commit、固定证据，而不是漂浮的自然语言总结。

## 最终建议

如果要把这些规则压成 `repo-teacher` 的实际 prompt，我建议用下面这个顺序：

1. 先定义读者和输出目标。
2. 再定义每个功能节的固定模板。
3. 然后补 Voice / loop / router 的专门链路条款。
4. 最后加证据、增量、freshness 和禁止 regex 的约束。

这样 prompt 会更像一个可执行合同，而不是一段“请好好解释”的泛化请求。
