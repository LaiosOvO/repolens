# 陌生代码仓库如何被讲成可学习、可复用的教学页面

> 研究日期：2026-08-10  
> 范围：只研究既有产品、开源项目、论文和公开 Agent Skills 的做法；不包含本项目的具体模块设计。  
> 证据优先级：官方产品文档／官方 GitHub 源码／论文原文。社区文章和二手评测不作为核心结论依据。

## 1. 先给结论

现有方案并不是同一种“代码库讲解器”，而是五种互补的教学形态：

1. **符号导航**：GitHub、Sourcegraph Code Navigation。擅长从某一行跳到定义、引用和实现；证据最硬，但不会自动形成一堂课。
2. **问题驱动探索**：Cody、Sourcegraph Deep Search、DeepWiki Q&A。读者先提出任务，系统检索相关代码再回答；适合临时理解，不天然形成稳定课程。
3. **自动 Wiki**：Devin DeepWiki、DeepWiki-Open。先生成仓库目录和主题页，再提供源码链接、图和问答；覆盖面广，但页面分类不等于学习顺序。
4. **顺序教程**：Code2Tutorial（官方仓库名为 PocketFlow Tutorial Codebase Knowledge）。先抽象核心概念和关系，再按前置依赖排序章节；“总—分—总”和初学者叙事最强，但源码锚点比导航工具弱。
5. **任务化导览**：Microsoft CodeTour 与公开 `code-tour` Skill。围绕某个角色或任务，逐步打开真实文件和行号；最接近“读者做什么”，但通常依赖人工或 Agent 先选出正确路径。

没有一个现成方案同时可靠完成以下四件事：**自动选出值得学习的功能、生成教学 Skill、建立稳定的符号级模块索引、持续验证两种产物始终指向同一版本源码**。公开方案通常只覆盖其中一到两个环节。

## 2. 方法对比总表

| 方案 | 主要信息架构 | “总—分—总” | 功能到源码映射 | 调用／流程图 | 渐进展开 | 典型读者任务 | 核心优点 | 明显缺点 |
|---|---|---|---|---|---|---|---|---|
| GitHub Code Navigation | 文件 → 符号 → 定义／引用 | 弱；是局部导航，不是课程 | 符号级，映射可靠；功能路径要读者自己串 | 无仓库级自动流程图 | 很强：文件内符号、定义、引用逐级打开 | 查一个函数在哪里定义、被谁使用 | 零配置、直接回到真实源码 | 只有名称／符号关系，没有业务功能叙事和学习顺序 |
| GitHub 官方学习指南 | 仓库定向 → 选一个功能 → 搜索 → 顺藤摸瓜 → 小改动 | 强，且明确反对一开始理解整个仓库 | 手工从可观察特征追到实现文件 | 无自动图 | 强：先 README，再特征搜索，再具体代码 | 从后端到前端追一个功能并实验 | 教学策略简单、可迁移 | 不是自动化系统，证据链靠读者维护 |
| Sourcegraph Code Navigation / Cody | 搜索／@ 上下文 → 代码图／片段 → 回答 | 中；单次回答可总分，但没有固定课程树 | 精确索引可到定义、引用、实现；Cody 以检索片段支撑回答 | 可按问题生成图，但不是固定产物 | 强：先问题，再相关上下文，再追问和源码 | 跨仓库查实现、影响面、调用者 | 多仓库、精确索引和问答结合 | 精确导航需要索引；回答质量依赖问题范围与检索召回 |
| Sourcegraph Deep Search | 自然语言任务 → agentic search loop → 答案＋来源清单 | 中；答案有总结和证据，非持久化课程 | 来源列出搜索和已读文件，可链接目录／仓库 | 可提示生成流程图 | 很强：迭代搜索、追问、缩小 scope | 追请求流、做跨仓审计、解释历史变更 | 来源清单透明，可处理跨仓和大结果集 | 企业产品；共享会话权限有官方警告；输出仍是问题态而非稳定教材 |
| Devin DeepWiki | Wiki 总览 → 父子页面 → 源码链接 → Q&A | 强；官方建议从 overview 到分层细页 | 页面带 source links，页面 purpose 可指定目录／文件／概念 | 内建 architecture diagrams；Codemaps 提供可视探索 | 强：目录 → 页面 → 追问；MCP 也是 structure → contents → question | 快速了解陌生仓库和特定组件 | 自动目录、图、源码链接、问答合一 | 生成实现闭源；默认 cluster planning 不透明；大仓会漏页，需要 `wiki.json` 人工 steering |
| DeepWiki-Open | 文件树＋README → Wiki 结构 → 并发生成页面 → Ask／Codemap／Workshop | 很强；页面 prompt 明确要求简介、细节、总结 | Wiki 页强制 source list 和行号格式；Codemap 是每步一个源码 citation | Wiki 广泛使用 Mermaid；Codemap 每节生成 Mermaid | 很强：可折叠 Wiki 树、重要度、问答、按任务 Codemap、练习型 Workshop | 从浏览架构到按 how-to 追真实代码，再做练习 | 开源且教学形态最完整；源码查看器可从 citation 回跳 | 结构初判主要依赖文件树＋README；“至少 5 个文件”可能造成凑引用；未匹配到原文的 citation 不会被强制判失败 |
| RepoAgent | 仓库树 → 文件 → class／function 对象文档 | 中；层级清楚，但不是连续课程 | AST 对象级，Jedi caller／callee 关系进入生成上下文 | 关系用于生成，默认产物不是流程图教程 | 中：GitBook 层级从仓库下钻到对象 | 查函数用途、参数、注意事项和示例；维护文档 | 结构化对象文档、引用关系、Git 增量更新 | 目前仅 Python；循环依赖被忽略；面向 API reference 多于功能故事；论文承认需人工复核 |
| Code2Tutorial | 项目总览＋抽象关系图 → 有顺序的概念章节 → 章节总结／下一章 | 最强；生成 prompt 明确编码此叙事 | 每个抽象绑定若干文件，章节引用路径；无行号级可验证 citation | 总览关系图＋章节 sequence diagram | 强：先核心概念、再底层；章节间显式前后链接 | 初学者按顺序理解核心抽象和内部调用 | 类比、用例、短代码、流程、章节衔接完整 | 主要靠 LLM 从拼接源码识别抽象和关系；无 AST／SCIP 校验；简化代码可能不是原文；大仓上下文风险 |
| `acquire-codebase-knowledge` Skill | 7 份固定参考文档：栈、结构、架构、约定、集成、测试、风险 | 中；最终汇总，但主体是参考手册 | 每个非平凡事实需 evidence 路径 | 仅当文档作者生成，不是内建合同 | 强：核心区必填，可选扩展按复杂度加载；focus mode | 新成员先获得项目地图 | 证据纪律、未知标 TODO、意图与现实分开 | 不选择具体功能，不输出连贯教程，不建立符号索引 |
| `code-tour` Skill ＋ CodeTour | 角色／目标 → 定向 → 高层地图 → 核心路径 → 下一步 | 强；明确要求 narrative arc | 精确到文件、行、selection 或 regex pattern | 可嵌图，但不是自动调用图 | 很强：逐步打开源码；可串联多条 tour | 新人、修 bug、审 PR、安全审查、解释功能等 | persona 驱动，任务相关性高，路径可验证 | 线性，无条件分支；选错路径仍会生成“精确但无关”的导览；符号重命名后行号易漂移 |
| GitHub 官方 onboarding prompt | Foundation → Exploration → Integration | 强，三阶段首尾完整 | 通过 README、测试、脚本、issues 间接落源码 | 无 | 强；按背景个性化、从阅读到实践 | 新成员完成环境、探索和第一次贡献 | 强调 hands-on 和早期成功 | 是 prompt 模板，不负责源码级证据或自动验证 |

## 3. GitHub：可靠的微观导航，加上“只追一个功能”的教学原则

### 3.1 Code Navigation 本身怎样组织信息

GitHub 官方文档把基本阅读路径定义为：打开文件 → Symbols 面板 → 选中类／函数 → Definition／References → 在引用之间移动。其导航数据由开源 `tree-sitter` 提取，支持的仓库无需额外配置；官方也明确写明只对 active branches 生效，且仓库须少于 100,000 个文件。[官方 Code Navigation 文档](https://docs.github.com/en/enterprise-cloud@latest/repositories/working-with-files/using-files/navigating-code-on-github)

这是一种证据强、叙事弱的信息架构：读者看到的是“这个名字在哪里定义、在哪里出现”，而不是“登录功能为什么存在、从 UI 到数据库依次发生什么”。它适合作为教学页的源码落点，不适合单独承担课程目录。

### 3.2 GitHub 官方真正推荐的学习顺序

GitHub 的官方学习指南给出了比产品 UI 更重要的教学原则：**不要试图理解整个项目；挑一个功能或函数，沿代码从后端追到前端**。完整流程是：找合适仓库 → 先读 README 和内部文档定向 → 搜索某个可观察特征 → 解释具体行 → 做小改动并运行 → 总结和迁移。[Finding and understanding example code](https://docs.github.com/en/get-started/learning-to-code/finding-and-understanding-example-code)

这是“读者任务”设计最清楚的一手证据。它的“总—分—总”不是文档模板，而是学习行为：先有项目地图，中间只深挖一条功能链，最后通过修改和复述验证理解。

## 4. Sourcegraph／Cody：从固定页面转向问题驱动的证据探索

### 4.1 精确导航与上下文检索是两层能力

Sourcegraph 官方把 Code Navigation 分成两类：

- Search-based navigation：文本搜索＋语法级启发式，开箱即用，但没有语言级语义。
- Precise navigation：使用编译期信息，支持跨仓库定义、引用、实现等精确导航。[Code Navigation](https://sourcegraph.com/docs/code-navigation)

Cody 的上下文则可能来自关键词搜索、Sourcegraph Search 和 Code Graph；Code Graph 包含 definitions、references、symbols、doc comments，由 indexer 生成并上传或自动索引。Cody prompt 由 prefix、user input、context 三部分组成。[Cody Context](https://sourcegraph.com/docs/cody/core-concepts/context) · [Code Graph](https://sourcegraph.com/docs/cody/core-concepts/code-graph)

因此它不是先生成完整教材再让用户浏览，而是读者用 `@` 指向仓库、文件或符号，系统为当前问题取回最相关的片段。优势是任务相关性和多仓能力；弱点是知识结构随问题变化，难以保证不同读者得到同一条学习路径。

### 4.2 Deep Search 的页面形态

Sourcegraph 当前的 Deep Search 是 agentic loop：反复使用 Code Search 和 Code Navigation 工具，直到有足够证据，再返回 Markdown 答案。每次响应都带详细 sources 列表，显示做过的搜索和读过的文件；可继续追问，也可按提示生成图。[Deep Search 官方文档](https://sourcegraph.com/docs/deep-search)

其自然信息架构是：**问题 → 逐步检索 → 综合回答 → 来源 → 追问**。这比固定 Wiki 更接近研究笔记，不像课程。官方最佳实践也要求问题范围合理，并主动检查 sources；这说明来源透明不等于答案自动完整。

一个重要的产品边界是：官方说明 Deep Search 的小型 Lua 分析脚本运行在无网络、无系统和无通用文件系统访问的沙箱中，而且不执行仓库代码。另一个风险是官方明确警告：共享 Deep Search 会话的查看并不强制仓库权限。

## 5. Devin DeepWiki：树状 Wiki、源码链接和问答

DeepWiki 官方定位就是为仓库自动生成架构图、文档、摘要和源码链接，并用 Wiki 信息帮助 Ask Devin 找上下文；公共版还允许提交公开 GitHub 仓库并问复杂问题。[DeepWiki 官方文档](https://docs.devin.ai/work-with-devin/deepwiki)

### 5.1 信息架构与“总—分—总”

`.devin/wiki.json` 暴露了 DeepWiki 的内容模型：

- `repo_notes` 说明仓库优先级和语境；
- `pages` 指定页面 title、purpose、parent、page_notes；
- 一旦提供 `pages`，系统会绕过默认 cluster-based planning，严格只生成列出的页面；
- 官方建议先 high-level overview，再用 parent-child 建层级，把相关功能归组，并在 purpose 中写清具体目录、文件或概念。

官方示例直接使用 `Architecture Overview → Frontend → React Components／State Management` 和 `Architecture Overview → Backend → API Endpoints` 的父子结构。这是标准的“总览—子系统—实现细节”。单页是否有总结并非官方文档合同，但 Wiki 全局天然支持从总览下钻，再回到相关页或问答。[Steering DeepWiki 与层级示例](https://docs.devin.ai/work-with-devin/deepwiki)

### 5.2 渐进展开

DeepWiki MCP 只暴露三个核心读工具：`read_wiki_structure`、`read_wiki_contents`、`ask_question`。这个工具顺序本身就是渐进展开：先看目录，再读相关页，最后只对剩余疑问问答。[DeepWiki MCP](https://docs.devin.ai/work-with-devin/deepwiki-mcp)

### 5.3 风险

默认聚类规划和生成实现没有公开，无法从源码判断主题聚类、引用验证和图生成怎样工作。官方故障排查承认大仓可能只覆盖部分目录或漏掉重要组件，并要求通过 `wiki.json` 补足；因此“自动生成 Wiki”不能被视为覆盖完整性的证明。

## 6. DeepWiki-Open：目前开源项目里教学页面形态最完整的组合

以下结论来自官方仓库在审计时的提交 `4181daa5`（2026-08-08）。项目 README 将其描述为可为 GitHub、GitLab、Bitbucket 仓库生成 Wiki、图和 Codemap，许可证为 MIT。[官方仓库](https://github.com/AsyncFuncAI/deepwiki-open) · [README（固定提交）](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/README.md)

### 6.1 Wiki 生成链

源码显示的实际路径是：

1. 本地 clone／索引仓库；
2. 从仓库文件树和第一个匹配到的 README 构造结构 prompt；
3. LLM 返回 XML Wiki 结构；comprehensive 模式预设 Overview、System Architecture、Core Features、Data Flow、Frontend、Backend、Model Integration、Deployment、Extensibility 等类目；
4. 解析为 sections、pages、importance、related pages 和每页 `filePaths`；
5. 每一页复用 RAG chat pipeline 并发生成；
6. 后处理空 citation，把仓库相对路径和行号转成真实代码托管链接；
7. 前端用可折叠的 Wiki tree 浏览，点击页后再逐步展开内容。

证据：[结构读取与 XML 解析](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/structure.py) · [结构／页面 prompts](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/prompts.py) · [后台任务链](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/tasks.py) · [Wiki Tree UI](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/src/components/WikiTreeView.tsx)

### 6.2 单页为什么接近“总—分—总”

页面 prompt 写死了教学结构：最前面是 Relevant source files 折叠块，然后 H1；正文先用 1–2 段解释目的、范围和高层位置，再以 H2／H3 展开架构、组件、数据流、函数、类、API 和配置；大量使用 Mermaid 和汇总表；重要事实、图和表要求带 `path:start-end` citation；最后可用简短 summary 收束。[页面 prompt](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/prompts.py)

这套结构的优点是页面模板稳定、证据意识强。风险也来自同一 prompt：它硬性要求至少使用 5 个源文件，即使主题实际上只需两三个文件，也可能诱导检索和模型添加边缘相关材料。

### 6.3 Codemap：最接近“功能／how-to → 源码路径”

当前源码的 Codemap 不是普通问答，而是两次 LLM 调用：

1. RAG 按用户 how-to 问题取回带真实文件路径和行范围的 chunks；
2. 第一次生成 numbered sections 和 `1a/1b/...` steps，每步包含示例代码和一个 citation；citation 的 snippet 必须从上下文逐字复制；
3. 第二次在不改变步骤和引用的前提下，为每节补 2–4 句 guide 和 Mermaid diagram；
4. 后端用 snippet 回到真实 clone 中重定位行号，UI citation chip 可打开源码查看器。

证据：[Codemap prompts](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/prompts.py) · [生成与 snippet grounding](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/codemap.py) · [Codemap schema](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/schemas/codemap.py) · [Codemap UI](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/src/components/CodeMap.tsx)

这里有一个必须保留的事实边界：`_ground_citations` 在找到 snippet 时会纠正行号，但找不到文件或 snippet 时只是保留原 citation，不会让整个 Codemap 失败。因此它比纯 LLM 行号可靠，却不是强制通过的引用验证器。

### 6.4 Workshop：从“读懂”推进到“做会”

项目还会基于已生成 Wiki 请求一份 workshop，固定包含 3–4 个递进练习、step-by-step 指令、预期结果、challenge、折叠 solution、final project 和 next steps，并要求练习和代码来自真实仓库。[Workshop prompt 源码](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/src/app/%5Bowner%5D/%5Brepo%5D/workshop/page.tsx)

这是所审项目中唯一把 Wiki、按任务源码路径和练习页同时放在同一仓库里的实现。它的练习内容仍由 Wiki 摘要驱动，没有看到自动运行练习或校验成功标准的代码合同。

## 7. RepoAgent：最强项是“对象文档持续跟代码更新”，不是课程叙事

RepoAgent 论文和源码把系统分为 Global Structure Analysis、Documentation Generation、Documentation Update 三段。[论文原文](https://arxiv.org/html/2402.16667) · [官方仓库](https://github.com/OpenBMB/RepoAgent)

### 7.1 真实实现路径

- 只处理 Python；AST 递归抽取 class／function 的类型、名称、代码片段等元信息，加入仓库目录树。
- Jedi 提取 caller 和 callee 双向引用，挂到对象节点；论文称其形成 DAG，并明确说明循环依赖被简单忽略。
- 按自底向上的拓扑顺序生成对象文档，使子节点和所引用节点先有文档。
- 每个对象的文档格式包含 Functionality、Parameters、Code Description、Notes，以及有返回值时的 Examples。
- Git pre-commit 根据 staged diff 找受影响对象，只更新最小影响范围。
- Markdown 按仓库／目录／文件／对象层级生成，再交给 GitBook 浏览。

源码证据：[Runner 与拓扑任务](https://github.com/OpenBMB/RepoAgent/blob/825d988127d7bfd757237d9c4e8678d9104030f0/repo_agent/runner.py) · [对象元数据／拓扑](https://github.com/OpenBMB/RepoAgent/blob/825d988127d7bfd757237d9c4e8678d9104030f0/repo_agent/doc_meta_info.py) · [生成 prompt](https://github.com/OpenBMB/RepoAgent/blob/825d988127d7bfd757237d9c4e8678d9104030f0/repo_agent/prompt.py) · [Git 变更检测](https://github.com/OpenBMB/RepoAgent/blob/825d988127d7bfd757237d9c4e8678d9104030f0/repo_agent/change_detector.py)

### 7.2 教学意义与边界

RepoAgent 的信息架构是 API reference：从目录和文件逐步下钻到对象，每个对象说明“做什么、参数、代码、注意事项、例子”。这对复用单个函数和维护文档很好，但不会自动形成“用户点击登录按钮后经历哪些模块”的功能故事；caller／callee 是生成上下文，不是面向读者的顺序图。

论文自己列出的限制包括：只适用于 Python、仍需人工复核、受后端模型能力影响、缺乏统一文档评测标准，以及远程模型带来的隐私风险。论文的人类偏好试验是对抽样对象文档的评估，不能外推成“完整仓库教学覆盖率”。

## 8. Code2Tutorial：顺序教程和章节内教学设计最值得研究

“Code2Tutorial”对应的开源代码仓库是 [The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge)，README 将其称为把代码库转成 beginner-friendly tutorials 的 AI Codebase Knowledge Builder，MIT 许可。以下源码核对基于提交 `05b24cbb`（2026-05-30）。

### 8.1 六段流水线

[`flow.py`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/flow.py) 明确串起六个节点：

`FetchRepo → IdentifyAbstractions → AnalyzeRelationships → OrderChapters → WriteChapters → CombineTutorial`

[`nodes.py`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/nodes.py) 显示：

- 拉取包含／排除规则过滤后的源码，并为文件分配 index；
- LLM 选出 5 到指定上限个核心抽象，每个抽象带新手描述和相关 `file_indices`；
- 再让 LLM输出项目 summary 和抽象关系，强制每个抽象至少参与一条关系；
- 依据基础性、用户可见性和依赖顺序排序所有章节；
- 逐章写作时提供相关文件、完整目录、前后章信息和已经写完的前文；
- 最后生成 `index.md`、Mermaid 抽象关系图和按序章节文件。

### 8.2 它怎样编码“总—分—总”

总览页是项目用途摘要＋核心抽象关系图＋有序章节目录。每一章又固定使用以下叙事：

1. 从上一章过渡；
2. 用一个最小、具体的中心 use case 解释动机；
3. 用类比说明概念；
4. 解释怎样使用它解决该 use case，并给输入／输出；
5. 先非代码地分步解释内部实现；
6. 用最多 5 个参与者的 sequence diagram 表示调用；
7. 再下钻到文件和简短代码；
8. 总结所学并链接下一章。

官方仓库内的生成示例也体现了该结构，例如 [Codex 总览](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/docs/Codex/index.md) 和 [Agent Loop 章节](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/docs/Codex/03_agent_loop.md)。

### 8.3 风险

它没有 AST、SCIP 或编译器级索引。核心抽象、关系和排序都来自 LLM 对拼接文件内容的判断；每章只有文件级上下文，没有强制行号 citation，也没有把生成的简化代码与仓库原文做 substring 校验。prompt 还主动要求“高度简化”代码，因此示例适合教学，不应默认当作可直接复制的真实实现。

另外，识别抽象阶段会把纳入的文件内容拼成一个大 context；大仓虽可用 include／exclude／max-size 控制，但没有源码显示自动 token budgeting 或分层归纳。它最值得借鉴的是**课程编排和章节叙事**，不是证据索引精度。

## 9. 公开 Agent Skills 与 CodeTour

### 9.1 `acquire-codebase-knowledge`

GitHub 维护的社区合集 `github/awesome-copilot` 中，[`acquire-codebase-knowledge`](https://github.com/github/awesome-copilot/blob/ab7544d03d4c49fdd07f5958e1888ad39c4118e2/skills/acquire-codebase-knowledge/SKILL.md) 要求恰好生成七份文档：

`STACK / STRUCTURE / ARCHITECTURE / CONVENTIONS / INTEGRATIONS / TESTING / CONCERNS`

它最有价值的不是文档标题，而是证据合同：每个 claim 必须能回溯到文件、配置或命令输出；未知标 `[TODO]`，需要团队意图的标 `[ASK USER]`；先读 PRD／TRD／README／ROADMAP／SPEC／DESIGN 总结“宣称意图”，再读源码找“现实”，最后反复验证七份文档。Focus mode 也必须先做完整初扫，只把非重点文档标为 TODO。

它适合生成仓库参考地图，不适合直接生成某功能的顺序课程。七类文档按知识域切分，读者仍需自己把一个请求流跨 ARCHITECTURE、INTEGRATIONS、TESTING 串起来。

### 9.2 `code-tour` Skill 与 Microsoft CodeTour

[Microsoft CodeTour](https://github.com/microsoft/codetour) 是在 VS Code 内录制和播放 guided tours 的扩展；`.tour` 步骤可指向文件和行。`awesome-copilot` 的 [`code-tour` Skill](https://github.com/github/awesome-copilot/blob/ab7544d03d4c49fdd07f5958e1888ad39c4118e2/skills/code-tour/SKILL.md) 在此之上加入 Agent 工作流：

- 按 persona 选内容：new joiner、bug fixer、RCA、feature explainer、architect、PR reviewer、security reviewer 等；
- 对 feature explainer 明确要求追 `UI → API → backend → storage`；
- 大仓不读全部，只先读 entry points 和 5–7 个模块，再为 persona 深挖 2–3 个模块；
- Narrative arc 固定为：有源码锚点的 opening → 1–3 个高层地图步骤 → core path → 告诉读者现在能做什么的 closing；
- 支持 file／line、selection、regex pattern、directory、URI、VS Code commands、view、branch ref、`nextTour`；
- validator 检查 JSON、真实路径、行号边界、pattern 命中、nextTour 引用和叙事首尾。

它是现成 Skills 中最接近“选一个功能后导出可学习路径”的方案。优势是 persona 和目标驱动，并能强制每个步骤落到真实源码；不足是 `.tour` 本质上线性、没有条件分支，且 line anchor 会随代码移动。`pattern` 比固定行号更抗漂移，但它仍不是稳定的语言级 symbol ID。

### 9.3 GitHub 官方 onboarding prompt

GitHub 官方定制库的 [Onboarding plan](https://docs.github.com/en/copilot/tutorials/customization-library/prompt-files/onboarding-plan) 按用户背景生成三阶段计划：Foundation（环境和先读文档）、Exploration（README、测试／脚本、适合新人的任务）、Integration（团队流程和第一次贡献），并明确要求 hands-on practice 优先于只读理论。

它提供的是学习节奏和任务闭环，不提供代码图或来源验证。适合作为“课程外框”的证据，不是 repository analysis 引擎。

## 10. “选功能 → 导出 Skill＋符号级模块索引”的现成覆盖与缺口

本节只判断公开方案已经覆盖什么，不提出本项目的具体实现模块。

### 10.1 已覆盖

| 能力 | 可直接参考的现成方案 | 覆盖程度 |
|---|---|---|
| 从一个明确功能／任务出发 | GitHub feature-first 指南；Sourcegraph Deep Search；DeepWiki-Open Codemap；`code-tour` persona map | **较强**。当用户已经说出功能时，能沿任务取上下文或组织步骤 |
| 自动提出仓库核心主题 | DeepWiki／DeepWiki-Open Wiki structure；Code2Tutorial IdentifyAbstractions | **中等**。能得到主题／抽象候选，但主要依赖 LLM 和文件树，缺少统一质量标准 |
| 生成可安装／可执行的教学 Skill | `acquire-codebase-knowledge`、`code-tour` 提供公开 Skill 模板和验证脚本 | **部分**。能输出文档或 `.tour`，但没有现成方案把任意选中功能自动封装成通用 Agent Skill 包 |
| 文件／行级教学锚点 | DeepWiki-Open Codemap；CodeTour／`code-tour` Skill | **较强**。Codemap 用 snippet 重定位，CodeTour validator 校验路径和行号 |
| 符号级定义／引用／实现 | GitHub Code Navigation；Sourcegraph precise navigation／SCIP 数据 | **强**。这是成熟的代码智能能力 |
| 调用关系作为生成上下文 | RepoAgent Jedi caller／callee；Sourcegraph Code Graph | **强但形态不同**。前者 Python-only，后者依赖索引器／平台 |
| 教学叙事和章节顺序 | Code2Tutorial；`code-tour` narrative arc；Onboarding plan | **强**。总览、用例、内部流程、总结和下一步均有可复用模式 |
| 练习／实践任务 | DeepWiki-Open Workshop；GitHub onboarding prompt | **中等**。会生成练习和挑战，但通常不自动运行或验收 |
| 增量文档更新 | RepoAgent | **局部强**。Python AST 对象文档可按 Git diff 更新；不覆盖通用 Skill 与跨语言符号索引 |

### 10.2 核心缺口

1. **“选功能”没有稳定定义。** Code2Tutorial 选的是核心抽象，DeepWiki 选的是 Wiki 主题，Deep Search／Codemap 依赖用户先给问题，CodeTour 依赖 persona 和 focus。公开方案没有统一把“可观察用户功能”绑定到 entrypoint、跨层调用链、测试和配置的算法合同。
2. **教学 Skill 与符号索引是两个世界。** Skills 和 CodeTour 多用 Markdown、路径、行号、regex；GitHub／Sourcegraph 使用符号定义、引用和编译期索引。没有一手资料显示某个开源方案会在 Skill 内保存稳定 symbol identity，并在每次使用时解析到当前 commit。
3. **缺少双向一致性校验。** DeepWiki-Open 能纠正找到的 snippet 行号，CodeTour 能验证路径和行边界，RepoAgent 能按对象更新文档；但没有方案同时证明“每个教学步骤所声明的功能语义、调用边、代码锚点、练习”都与符号图一致。
4. **版本／快照身份普遍不完整。** CodeTour 可设置 branch／tag／commit ref，RepoAgent 保存文档版本，部分产品页面链接源码；但自动 Wiki 和问答输出通常没有把每个页面、图、Skill、符号索引共同锁定到同一不可变 commit 的公开合同。
5. **业务功能到测试证据没有闭环。** GitHub 指南建议做小改动，Workshop 生成练习，`acquire-codebase-knowledge` 单列测试文档；但它们不自动把功能链绑定到可执行的最小测试，并用测试结果证明读者理解或复用成功。
6. **多语言、动态调用和生成代码仍是断点。** GitHub／Sourcegraph 的精度取决于语言支持和 indexer；RepoAgent 只支持 Python；LLM 型 Wiki 对反射、依赖注入、运行时注册和代码生成容易漏边。
7. **完整性评估缺少基准。** DeepWiki 官方承认会漏目录，RepoAgent 论文承认缺少统一文档评估标准。现有“页面很多”或“图很漂亮”不能证明关键功能、异常路径和权限边界被覆盖。

### 10.3 可作为 Skill 候选直接研究的公开资产

按与本研究目标的接近程度分组：

- **功能路径／角色化教学首选**：[`code-tour` Skill](https://github.com/github/awesome-copilot/tree/main/skills/code-tour)；配套 [Microsoft CodeTour](https://github.com/microsoft/codetour)。
- **仓库地图和证据纪律首选**：[`acquire-codebase-knowledge` Skill](https://github.com/github/awesome-copilot/tree/main/skills/acquire-codebase-knowledge)。
- **顺序教程 prompt 与流水线首选**：[PocketFlow Tutorial Codebase Knowledge](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge)。
- **开源 Wiki＋行号 Codemap＋Workshop 首选**：[DeepWiki-Open](https://github.com/AsyncFuncAI/deepwiki-open)。
- **Python 对象文档＋引用图＋增量更新专项参考**：[RepoAgent](https://github.com/OpenBMB/RepoAgent)。
- **符号级索引语义参考**：[Sourcegraph Code Navigation](https://sourcegraph.com/docs/code-navigation) 与 [SCIP](https://github.com/sourcegraph/scip)；它们不是教学 Skill。
- **个性化 onboarding 外框**：[GitHub Onboarding plan prompt](https://docs.github.com/en/copilot/tutorials/customization-library/prompt-files/onboarding-plan)。

## 11. 跨方案观察：优秀教学页面反复出现的结构

这不是本项目设计，而是对上述一手资料的归纳：

1. **先说读者要完成什么。** GitHub 选一个功能；Deep Search 先给 scoped question；CodeTour 先选 persona；Workshop 先列学习结果。
2. **先给小地图，不给全仓库倾倒。** README／overview／5–7 个模块足够进入下一层。
3. **主线必须是一条真实路径。** 最有用的不是目录介绍，而是 UI → API → backend → storage，或输入 → 调度 → 工具 → 输出。
4. **抽象解释与源码证据交替。** Code2Tutorial 的类比和用例解决“为什么”，CodeTour／Codemap 的路径和行号解决“凭什么”。两者任何一个单独存在都不完整。
5. **复杂调用用图，但图必须可回源。** DeepWiki-Open 要求图后 citation；Codemap 把图和带 citation 的步骤放在同一 section。只画 LLM 推断图而没有源码锚点，可信度有限。
6. **逐层展开。** Wiki 树、MCP structure → content → question、CodeTour step、顺序章节，都避免首次加载所有细节。
7. **结尾交给读者一个动作。** GitHub 让读者做小改动，Workshop 给练习，CodeTour closing 说明现在能做什么，Onboarding plan 连接第一次贡献。

## 12. 明确的事实／推断边界

### 12.1 直接事实

- GitHub 的 tree-sitter 导航方式、支持条件和 100,000 文件限制来自 GitHub 官方文档。
- Sourcegraph 的 search-based／precise navigation、Code Graph 数据、Deep Search agent loop、sources 和沙箱边界来自 Sourcegraph 官方文档。
- DeepWiki 的自动 Wiki、source links、architecture diagrams、`wiki.json`、层级页面和 MCP 三工具来自 Devin 官方文档。
- DeepWiki-Open、RepoAgent、Code2Tutorial、`awesome-copilot` Skills 的流水线、prompt、schema 和验证行为来自上述固定提交源码。
- RepoAgent 的研究设计、评估和限制来自论文原文；源码当前提交时间和 Python-only 状态与论文一致。

### 12.2 研究推断

- 表格中“总—分—总强弱”“最适合的读者任务”“最接近某目标”等属于基于信息架构和源码行为的比较判断，不是项目官方自评。
- “DeepWiki-Open 是形态最完整的开源组合”是指本次覆盖范围内同时存在 Wiki、Codemap、源码查看器和 Workshop，不代表其生成准确率最高。
- “Code2Tutorial 的课程叙事最强”是对 prompt 和生成示例的结构判断，不代表其源码证据最可靠。
- “没有现成方案完整覆盖选功能→Skill＋符号索引”是根据已审方案公开能力做出的缺口判断；闭源内部实现可能具备未公开能力。

### 12.3 未验证或不应外推

- 没有运行各项目对同一大型仓库做质量基准，因此不比较准确率、成本、延迟或幻觉率。
- 没有把产品营销中的“grounded”直接等同于逐条事实正确；只有源码可见的 citation／snippet／symbol 校验被具体描述。
- 没有用 stars 代替教学质量，也没有依据社交媒体热度排序。
- 没有把 RepoAgent 对对象文档的偏好实验外推为完整教程效果。

## 13. 主来源索引

- GitHub：[Code Navigation](https://docs.github.com/en/enterprise-cloud@latest/repositories/working-with-files/using-files/navigating-code-on-github) · [Finding and understanding example code](https://docs.github.com/en/get-started/learning-to-code/finding-and-understanding-example-code) · [Onboarding plan](https://docs.github.com/en/copilot/tutorials/customization-library/prompt-files/onboarding-plan)
- Sourcegraph：[Code Navigation](https://sourcegraph.com/docs/code-navigation) · [Cody Context](https://sourcegraph.com/docs/cody/core-concepts/context) · [Code Graph](https://sourcegraph.com/docs/cody/core-concepts/code-graph) · [Deep Search](https://sourcegraph.com/docs/deep-search)
- Devin：[DeepWiki](https://docs.devin.ai/work-with-devin/deepwiki) · [DeepWiki MCP](https://docs.devin.ai/work-with-devin/deepwiki-mcp)
- DeepWiki-Open：[仓库](https://github.com/AsyncFuncAI/deepwiki-open) · [Wiki prompts](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/prompts.py) · [Codemap service](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/codemap.py)
- RepoAgent：[仓库](https://github.com/OpenBMB/RepoAgent) · [论文](https://arxiv.org/html/2402.16667)
- Code2Tutorial／PocketFlow：[仓库](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge) · [Flow](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/flow.py) · [Nodes](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/nodes.py)
- Agent Skills／CodeTour：[`acquire-codebase-knowledge`](https://github.com/github/awesome-copilot/tree/main/skills/acquire-codebase-knowledge) · [`code-tour`](https://github.com/github/awesome-copilot/tree/main/skills/code-tour) · [Microsoft CodeTour](https://github.com/microsoft/codetour)

## 14. 扩展样本：最终产物、流水线与可复用边界

本节继续沿用“固定提交源码优先”的口径。表中的“教学强项”和“复用判断”是研究判断；产物、流水线、锚点和更新机制则来自列出的源码或官方说明。

| 项目 | 最终产物 | 主要教学形态 | 证据粒度 | 更新机制 | 本次定位 |
|---|---|---|---|---|---|
| Understand Anything | `.ua/knowledge-graph.json`、dashboard、guided tours、onboarding Markdown | 依赖顺序导览、架构分层、角色自适应浏览 | 文件、符号、`lineRange`、图节点／边 | 文件指纹增量、Git commit、可选 post-commit hook | 符号图＋交互导览专项基准 |
| OpenWiki | repo-local `openwiki/` Markdown、`quickstart.md`、OKF metadata、Mermaid | 任务路由、概念页、工作流页、变更手册 | `source_paths`、`test_paths`、稳定路径／符号名、验证命令 | diff impact plan、Git HEAD／内容 hash、定时 CI PR | 可维护 repo-to-wiki 核心基准 |
| CodeBoarding | `.codeboarding/analysis.json`、组件文档、HTML／Mermaid 图 | 先架构图、再组件、再源码下钻 | qualified symbol、文件、起止行、调用点行列 | fingerprint baseline、incremental／partial | LSP 图与架构教学专项基准 |
| learn-codebase | 交互问答与 `.claude/learning-journal.md` | 苏格拉底问答、预测、主动回忆、间隔复习 | 人工引导读者查看文件／行；无自动索引 | 持久化学习状态；不感知代码漂移 | 教学交互 Skill 基准 |
| PocketFlow Code2Tutorial | `output/<repo>/index.md` 与顺序章节 | 类比、用例、章节过渡、序列图 | 文件级输入；无符号／逐句引用 | 整体重跑；无一等增量机制 | 课程叙事专项基准 |
| SourceBridge | cliff notes、code tour、learning path、workflow story、架构说明 | 多形态、层级理解树、文件／符号下钻 | 文件／符号 EvidenceRef、行范围、理由、图关系 | 内容 hash／Merkle、cache invalidation、stale 状态 | 高价值低星综合基准 |
| Tour-de-Code-AI | CodeTour 兼容 `.tour` | 按文件＋行播放的 IDE 导览 | 路径＋正整数行；校验较弱 | 未见源码漂移失效／自动重生 | 交互形态观察样本 |
| walkthrough-plugin | IntelliJ 行旁 walkthrough popup、历史、Markdown 导出 | IDE 内逐步讲解、追问、tangent | 文件＋行；diff 模式另有左右 commit | 保存会话；普通锚点不感知漂移 | IDE 展示适配层专项基准 |

### 14.1 Egonex-AI/Understand-Anything

**固定快照：** `fe8c5bc591716aafd79b4765549328f08ef5a52e`；MIT。

- **最终产物。** 核心持久化产物是可提交共享的 `.ua/knowledge-graph.json`（文档也提到旧目录兼容），消费者包括交互式 dashboard、guided tours、搜索／问答和 Markdown onboarding guide。它更接近“可浏览的仓库知识图谱”，而不是传统静态文档站。
- **生成流水线。** `/understand` Skill 把处理分成扫描、语义批处理、并行文件分析、图装配／复核、架构分层、tour 生成、确定性校验与保存。Tree-sitter 负责 imports／exports／functions／classes／call sites／inheritance 等结构事实；LLM 补 summaries、tags、layers、domain 与 tour。这里的“混合”边界比纯提示词 Wiki 清楚。
- **证据锚点。** 函数、类等图节点携带 `filePath` 与 `lineRange`，关系边指向节点身份，tour step 指向 node ID。它明显强于只给文件路径的教程；但确定性校验主要证明引用节点存在、图可连接，不等于逐句自然语言陈述都已被语义验证。
- **更新机制。** 默认按 Tree-sitter 结构事实／内容 hash 生成指纹，只重跑 changed files，并重算全局架构视图；图记录 Git commit。`--auto-update` 可以安装 post-commit hook。这是本批项目中较完整的增量新鲜度方案。
- **教学方法。** guided tour 按依赖／拓扑顺序组织，dashboard 可按 persona 调整解释，并提供 architecture layers、key concepts、getting started、file map 与 complexity hotspots 等 onboarding 入口。
- **适合复用。** 符号感知的交互导览、增量图、变更影响说明、新人 onboarding 页面。
- **不适合直接复用。** 把 LLM 语义结论当权威证据、需要编译器级跨语言符号身份或严格逐句 citation 的场景。动态调用、反射和 Tree-sitter 覆盖外语言也会形成盲区；初次全仓语义分析有 token 成本。

源码锚点：[README](https://github.com/Egonex-AI/Understand-Anything/blob/fe8c5bc591716aafd79b4765549328f08ef5a52e/README.md) · [主 Skill](https://github.com/Egonex-AI/Understand-Anything/blob/fe8c5bc591716aafd79b4765549328f08ef5a52e/understand-anything-plugin/skills/understand/SKILL.md) · [graph builder](https://github.com/Egonex-AI/Understand-Anything/blob/fe8c5bc591716aafd79b4765549328f08ef5a52e/understand-anything-plugin/packages/core/src/analyzer/graph-builder.ts) · [fingerprint](https://github.com/Egonex-AI/Understand-Anything/blob/fe8c5bc591716aafd79b4765549328f08ef5a52e/understand-anything-plugin/packages/core/src/fingerprint.ts) · [tour generator](https://github.com/Egonex-AI/Understand-Anything/blob/fe8c5bc591716aafd79b4765549328f08ef5a52e/understand-anything-plugin/packages/core/src/analyzer/tour-generator.ts)

### 14.2 langchain-ai/openwiki

**固定快照：** `7531d615216e8cbccf464f66cfbbae3668871c84`；MIT。

- **最终产物。** repo-local `openwiki/`（或个人 Wiki 目录）的 Markdown 文档，以 `quickstart.md` 和层级 `index.md` 为入口，覆盖 architecture、domain、workflow、operations 等页面；`_skeleton.md` 是建站计划，`_plan.md` 是更新影响计划。页面使用 Open Knowledge Format front matter，并允许 Mermaid 图。
- **生成流水线。** agent 先盘点 manifests、entrypoints、tests、history，生成完整 skeleton；一个独立只读 `skeleton_critic` 自己重新映射仓库后再批评骨架；随后形成 evidence briefs、修补缺口、写页、做 unknown-unknown coverage pass，最后由 OKF middleware 规范 metadata、同步索引并检查内部链接／Mermaid。
- **证据锚点。** prompt 要求重要结论落在 source、tests、docs 或 Git history；页面 metadata 可记录 `source_paths`、`test_paths`、invariants、validation commands。`quickstart.md` 的任务路由表把“我要做什么”映射到 Wiki 页面、源码入口／符号、测试和最小验证命令。它偏好稳定路径与符号名而非脆弱行号，但没有编译器 symbol ID，也没有证明逐句 citation 被程序校验。
- **更新机制。** update 读取 commit range／diff 并生成文档影响计划；保存 Git HEAD 与内容 hash，无内容变化可 no-op，中断状态会要求重试。初始化可创建定时 GitHub workflow；`.openwikiignore` 同时是读取边界。更新后还检查链接与图。
- **教学方法。** 重点不是“从第一章学到最后一章”，而是给工程师和 agent 提供任务路由、改动配方、source／test／validation 闭环；属于总览 → 子系统 → 工作流 → 测试／运维的文档工程。
- **适合复用。** repo-to-wiki 的 docs-as-code 目录协议、critic／unknown-unknown 质量门、变更驱动更新、任务到源码／测试的路由表。
- **不适合直接复用。** 新手连续课程、主动回忆训练、强符号图。它的证据质量仍依赖 agent 遵守提示词，稳定符号名只是字符串锚点。

源码锚点：[README](https://github.com/langchain-ai/openwiki/blob/7531d615216e8cbccf464f66cfbbae3668871c84/README.md) · [code workflow prompt](https://github.com/langchain-ai/openwiki/blob/7531d615216e8cbccf464f66cfbbae3668871c84/src/agent/prompts/code.ts) · [skeleton critic](https://github.com/langchain-ai/openwiki/blob/7531d615216e8cbccf464f66cfbbae3668871c84/src/agent/skeleton_critic.ts) · [OKF middleware](https://github.com/langchain-ai/openwiki/blob/7531d615216e8cbccf464f66cfbbae3668871c84/src/agent/okf-middleware.ts) · [index sync](https://github.com/langchain-ai/openwiki/blob/7531d615216e8cbccf464f66cfbbae3668871c84/src/okf/index-sync.ts)

### 14.3 CodeBoarding/CodeBoarding

**固定快照：** `8c3f2218c3ecab1294902db5914f5e526f78524d`；MIT。

- **最终产物。** `.codeboarding/analysis.json`、`fingerprint.json`、组件／总览 Markdown、Mermaid 架构图和浏览器 explorer，可进入 IDE、CI 与 Web 展示。
- **生成流水线。** 扫描源码后由语言服务器／LSP 取得 document symbols 与 references，构造 call graph、inheritance 与 package dependencies；再用 Leiden clustering 聚类，LLM 把 cluster 聚合成有业务意义的 component 并写说明，最后渲染分层图和文档。支持 full、incremental、partial 三种路径。
- **证据锚点。** `SourceCodeReference` 保存 qualified name、file、可选 start／end lines；关系可保存 source／target 与 call-site line／column。调用关系因此能从静态图生成，而不是完全依赖 LLM 猜测。组件命名、分组与高层描述仍可能受模型误差影响。
- **更新机制。** 对全树做内容 hash fingerprint diff；incremental 要求有效 baseline，缺失时失败而不是悄悄伪装增量；partial 可按 component 局部刷新，也有 GitHub Action 路径。
- **教学方法。** “先看系统地图，再点组件，再下钻到方法／类”，非常适合大仓架构 onboarding；但不是连续课程，也没有学习者状态或主动练习。
- **适合复用。** LSP call graph、cluster → component 抽象、带源码位置的边、增量 baseline 与可点击架构图。
- **不适合直接复用。** 轻量嵌入场景：语言服务器安装和 Python 运行环境较重；自动聚类不应直接当作领域边界真相。

源码锚点：[README](https://github.com/CodeBoarding/CodeBoarding/blob/8c3f2218c3ecab1294902db5914f5e526f78524d/README.md) · [orchestration](https://github.com/CodeBoarding/CodeBoarding/blob/8c3f2218c3ecab1294902db5914f5e526f78524d/codeboarding_workflows/orchestration.py) · [call graph builder](https://github.com/CodeBoarding/CodeBoarding/blob/8c3f2218c3ecab1294902db5914f5e526f78524d/static_analyzer/engine/call_graph_builder.py) · [fingerprint diff](https://github.com/CodeBoarding/CodeBoarding/blob/8c3f2218c3ecab1294902db5914f5e526f78524d/repo_utils/fingerprint_diff.py) · [response schema](https://github.com/CodeBoarding/CodeBoarding/blob/8c3f2218c3ecab1294902db5914f5e526f78524d/agents/agent_responses.py)

### 14.4 ktaletsk/learn-codebase

**固定快照：** `cbc0304609e76041f7f29b3ae9a1e3f1a16e07ad`；MIT。

- **最终产物。** 它不是 Wiki 生成器，而是一个 Agent Skill：运行中维护 `.claude/learning-journal.md`，记录 Focus／Goals、🟢🟡🔴 mastery、open questions、review queue、aha moments 与 session log。
- **生成流水线。** 加载／新建 journal → 询问兴趣和目标 → 确认 focus → 要求读者先预测 → 通过 trace／design／comparison／error 问题探索代码 → 最多三级渐进提示 → 更新掌握度、提示次数与复习日期 → 总结下一步。
- **证据锚点。** Skill 会把读者带到实际文件／行并要求“从代码给证据”，且学习过程只读；但它不生成符号索引、调用图或静态 citation manifest。因此它校准的是读者理解，不是自动证明讲解正确。
- **更新机制。** journal 在显著时刻或约 10–15 分钟保存，复习节奏为 1 天／3 天／1 周／2 周。它能跨会话追踪学习状态，但不检测源码是否改变，旧 journal 可能漂移。
- **教学方法。** 本批最明确的教学法实现：Socratic questioning、prediction before revelation、active recall、spaced repetition，以及维持约 60–80% 成功率的 ZPD 调节；还约束短回复、一次一个概念、不要提前泄露答案。
- **适合复用。** 教学 Skill 的对话契约、学习者模型、分级提示、间隔复习和 evidence questions。
- **不适合直接复用。** repo 分析／索引／Wiki 底座、无人值守文档更新和代码事实验证；路径与工具假设也偏 Claude 环境。

源码锚点：[README](https://github.com/ktaletsk/learn-codebase/blob/cbc0304609e76041f7f29b3ae9a1e3f1a16e07ad/README.md) · [SKILL.md](https://github.com/ktaletsk/learn-codebase/blob/cbc0304609e76041f7f29b3ae9a1e3f1a16e07ad/SKILL.md) · [journal template](https://github.com/ktaletsk/learn-codebase/blob/cbc0304609e76041f7f29b3ae9a1e3f1a16e07ad/JOURNAL-TEMPLATE.md) · [question patterns](https://github.com/ktaletsk/learn-codebase/blob/cbc0304609e76041f7f29b3ae9a1e3f1a16e07ad/QUESTION-PATTERNS.md)

## 15. PocketFlow Code2Tutorial：产物、新鲜度与 HN 反馈

**固定快照：** `05b24cbbb0fe409c5e23c9791f0342f07524ffdc`。本节补充第 8 节未展开的最终产物和社区评价。

### 15.1 源码可确认的事实

- **最终产物。** `output/<project>/index.md` 汇总简介、Mermaid 抽象关系图和有序章节；编号章节以 use case／analogy 开场，逐步解释源码与序列图，并用 summary／next chapter 串联。其“总—分—总”与章节转场是本次样本中最接近成书式教程的产物。
- **生成流水线。** `FetchRepo → IdentifyAbstractions → AnalyzeRelationships → OrderChapters → WriteChapters → CombineTutorial`。先选择文件，再抽象概念、建关系、定学习顺序、并行或顺序写章，最后合并索引。
- **证据锚点。** chapter writer 能拿到选中文件的 index／path，并可嵌入简化代码；没有行号、symbol ID、逐句引用或 snippet 与源文件一致性校验。为了教学而简化代码是被允许的，因此它适合作为解释层，不适合作为 provenance 层。
- **更新机制。** 固定快照中未见一等增量更新、源码漂移探测或自动教程 CI；当前可靠方式是重新运行整条生成流水线。

### 15.2 Hacker News：有价值的反例与边界

[官方讨论串](https://news.ycombinator.com/item?id=43739456) 在抓取时显示 923 points、172 comments（2025-04-19）。以下只表示公开用户反馈和作者回复，不是统一基准测试。

- **教程性。** 正面反馈认为它能快速给出“系统地图”和继续阅读的位置，也有人特别认可 DSPy 示例对难概念的解释。反面观点来自技术写作者：真正 tutorial 应带读者从可执行动作走到结果，而部分生成内容只是把代码改写成人话；测试和真实使用路径应成为主线。这支持“叙事导览”和“任务教程”应分层，而非混为一谈。
- **正确性。** 有用户称在几个熟悉的雇主仓库试用后，抽查教程没有发现明显错误；也有人指出生成了仓库本身没有的术语，或“部分不准但仍可当地图”。另有“细节可能对、顶层目的可能错”的评论是在讨论 AI 摘要的一般风险，不应冒充 PocketFlow 专项测评。所有这些都是轶事证据。
- **语气。** 多条评论不喜欢过度热情、类比过多、感叹号密集或“给初学者过度简化”的口吻，也有人指出不应默认所有图都是 sequence diagram。作者回复提示词可调。这说明 tone／persona／diagram type 应是显式配置，而不是把默认 prompt 当教学标准。
- **文档漂移。** 讨论中有人追问代码示例失效后的维护；作者提出“小改动参考 commit history 修补，大架构改动重写”，社区也建议定时 GitHub Action 重生教程。固定快照没有实现这些完整机制，所以报告只把它们记为方向建议，不写成现有功能。

**复用结论：** 复用其抽象排序、章节模板、类比／用例／转场和总—分—总输出；不要把它承担源码证据、增量新鲜度或正确性裁判职责。

## 16. 三个低星项目：代码质量不能由 stars 代替

Stars 是采用／传播信号，不是架构、测试或可复用性的充分指标。以下 stars 数字沿用本轮核验时的快照（SourceBridge 14、Tour-de-Code-AI 17、walkthrough-plugin 10），会随时间变化；质量判断来自固定提交源码、测试和 CI。

### 16.1 sourcebridge-ai/sourcebridge：高价值低星综合基准

**固定快照：** `2a128bf0c8461fae91d2b424d9168ddf205bb11b`；AGPL-3.0-or-later。

- **最终产物。** repo／file／symbol scope 的 cliff notes、code tours、learning paths、workflow stories、architecture diagrams 与 system explanation，通过 Web、VS Code、MCP／GraphQL 暴露。
- **生成流水线。** Go indexer 用 Tree-sitter 建符号／关系图并写入 SurrealDB；Python comprehension layer 可选择 bottom-up hierarchical、long-context 或 single-shot 策略。层级策略先摘要 leaf／file，再聚合 package／root，最后由各 artifact renderer／prompt 生成不同教学形态。支持 Ollama、vLLM、llama.cpp、SGLang、LM Studio 等本地推理接口，也可接云模型。
- **证据锚点。** `EvidenceRef` 区分 file／symbol／requirement／doc，保存 source ID、file path、line start／end 和 rationale；quality gate 会识别过泛或缺少支持的结论。它把符号图与讲解证据放在同一数据路径，是三个低星样本里最完整的 provenance 设计。
- **更新机制。** 内容 hash／Merkle fingerprint、cache invalidation、change watch 与 freshness／stale 状态共同驱动重新理解；living wiki 能显示过期并继续未完成任务。源码支持“可识别、可恢复的新鲜度”，但不能据此推断每条自然语言 claim 都可完美局部更新。
- **教学方法。** 同一证据图生成速读、顺序 tour、分阶段 learning path 与端到端 workflow story；hierarchical comprehension tree 让读者从系统层逐层下钻。
- **代码质量证据。** 本地固定快照计得约 343 个 Go `_test.go`、73 个 Python test files、57 个 TS／TSX tests、67 个 benchmark files。CI 覆盖 Go race tests、Python pytest／coverage、Web／extension tests、lint 与 buf，并有多条 workflow。14 stars 并不支持“低质量”结论；相反，它是本轮应保留的高价值低星基准。
- **适合复用。** 完整 comprehension／evidence／freshness 架构、层级摘要、多教学产物、符号证据和本地模型接口。
- **不适合直接复用。** AGPL 的网络 copyleft 是实质集成约束，需法律评审；Go＋Python＋Next＋SurrealDB（以及可选 Redis）运维较重。README 对 OSS 部署的单租户／repo 隔离提示也不应忽略，不能把它当一个轻量 library 嵌入。

源码锚点：[README](https://github.com/sourcebridge-ai/sourcebridge/blob/2a128bf0c8461fae91d2b424d9168ddf205bb11b/README.md) · [hierarchical comprehension](https://github.com/sourcebridge-ai/sourcebridge/blob/2a128bf0c8461fae91d2b424d9168ddf205bb11b/workers/comprehension/hierarchical.py) · [knowledge types](https://github.com/sourcebridge-ai/sourcebridge/blob/2a128bf0c8461fae91d2b424d9168ddf205bb11b/workers/knowledge/types.py) · [evidence](https://github.com/sourcebridge-ai/sourcebridge/blob/2a128bf0c8461fae91d2b424d9168ddf205bb11b/workers/knowledge/evidence.py) · [code tour](https://github.com/sourcebridge-ai/sourcebridge/blob/2a128bf0c8461fae91d2b424d9168ddf205bb11b/workers/knowledge/code_tour.py) · [Go parser](https://github.com/sourcebridge-ai/sourcebridge/blob/2a128bf0c8461fae91d2b424d9168ddf205bb11b/internal/indexer/parser.go) · [CI](https://github.com/sourcebridge-ai/sourcebridge/blob/2a128bf0c8461fae91d2b424d9168ddf205bb11b/.github/workflows/ci.yml)

### 16.2 Tour-de-Code-AI：保留 `.tour` 形态，不采用当前底座

**固定快照：** `85f5718629d63083f2bdb83a2072a223be8a6a02`；MIT。

- **最终产物。** `.tours/*.tour`，由 VS Code CodeTour 播放，适合演示“按心智模型依次跳到文件／行”的交互。
- **实际流水线。** 当前活跃 `TourGenerator` 使用自定义 Repomix-style 文件扫描／XML packing，加入行号后排序、分 batch 交给 LLM，再检查文件存在和基本字段并写 `.tour`。仓库仍有 `treesitter-analyzer.ts` 遗留文件，但当前生成器明确不再调用 Tree-sitter。因此“Repomix ＋ Tree-sitter ＋ LLM”不是当前实现的准确描述。
- **证据锚点。** 生成结果的 path 必须来自已打包文件，line 只需为正整数；未见校验 line 是否在文件范围内、目标 snippet 是否匹配。schema 虽支持 ref／pattern／selection，当前生成主路径主要使用 file＋line。
- **更新机制。** 未见源代码漂移 invalidator 或自动重生现有 tour 的机制。
- **教学方法。** 最有价值的是 CodeTour 播放形态和先后顺序，不是知识生成质量。
- **代码质量证据与风险。** 本轮未发现测试，GitHub Actions 只有 release workflow，未见 PR CI；release 仍使用较旧的 `actions/checkout@v2`、`setup-node@v1`／Node 14。README／日志称 XML 只在内存，但 `RepomixService.generateSummary()` 会向 workspace 写 `repomix-debug.xml`，是文档与行为漂移，也带来隐私清理风险。
- **适合复用。** `.tour` 交换格式、IDE 顺序导览、mental-model ordering 的产品原型。
- **不适合直接复用。** parser、provenance、增量更新或生产核心。17 stars 不是否定理由；缺 tests／PR CI 和实现漂移才是降级理由。

源码锚点：[README](https://github.com/Tour-de-Code-AI/Tour-de-Code-AI/blob/85f5718629d63083f2bdb83a2072a223be8a6a02/README.md) · [tour generator](https://github.com/Tour-de-Code-AI/Tour-de-Code-AI/blob/85f5718629d63083f2bdb83a2072a223be8a6a02/src/generator/tour-generator.ts) · [batch generator](https://github.com/Tour-de-Code-AI/Tour-de-Code-AI/blob/85f5718629d63083f2bdb83a2072a223be8a6a02/src/generator/batch-generator.ts) · [Repomix service](https://github.com/Tour-de-Code-AI/Tour-de-Code-AI/blob/85f5718629d63083f2bdb83a2072a223be8a6a02/src/repomix/repomix-service.ts) · [schema](https://github.com/Tour-de-Code-AI/Tour-de-Code-AI/blob/85f5718629d63083f2bdb83a2072a223be8a6a02/schema.json) · [release workflow](https://github.com/Tour-de-Code-AI/Tour-de-Code-AI/blob/85f5718629d63083f2bdb83a2072a223be8a6a02/.github/workflows/release.yml)

### 16.3 forketyfork/walkthrough-plugin：测试充分的 IDE 适配层

**固定快照：** `697d5643d75f6285fc7cc13d5001c4902051bff5`；MIT。

- **最终产物。** IntelliJ 编辑器中锚定 file＋line 的 Compose／Jewel popup，支持上一条／下一条、历史记录、重放和导出 Markdown；diff walkthrough 可固定 left／right commits。popup 还能收集追问并插入 tangent child steps。
- **生成流水线。** agent 通过 MCP `show_walkthrough_items` 发送 `{text,file,line}` 或 diff descriptor；plugin 校验 payload、解析文件并显示 popup／connector；session registry 保存历史，`await_walkthrough_question` 与 `insert_walkthrough_tangents` 形成追问循环。
- **证据锚点。** tool instruction 要求 agent 先核对 1-based line，plugin 验证结构和路径可解析；普通 walkthrough 的 file＋line 仍会随代码移动而漂移，diff mode 的 commit identity 更稳定。它展示证据，不发现符号、不生成知识图，也不验证讲解内容。
- **更新机制。** 会话可持久化与重放，但没有仓库级 drift updater。不能把 history 等同于文档新鲜度。
- **教学方法。** 把源码、讲解和追问放在 IDE 同一注意力空间，tangent 允许读者临时深入再回主线。
- **代码质量证据。** 固定快照约 9 个 Kotlin tests；build CI 执行 Nix checks、Detekt、tests、plugin build、compatibility verifier，另有 Qodana SARIF 与带版本校验的 release 流程。10 stars 不能掩盖这些工程证据。
- **适合复用。** MCP → IDE 的展示协议、行旁 popup、追问／tangent、diff commit anchoring；可作为上游知识引擎的 presentation adapter。
- **不适合直接复用。** repo analysis、symbol graph、教程生成或新鲜度底座；还要求较新的 IntelliJ 平台与 JetBrains MCP 环境。

源码锚点：[README](https://github.com/forketyfork/walkthrough-plugin/blob/697d5643d75f6285fc7cc13d5001c4902051bff5/README.md) · [`show_walkthrough_items`](https://github.com/forketyfork/walkthrough-plugin/blob/697d5643d75f6285fc7cc13d5001c4902051bff5/src/main/kotlin/com/forketyfork/walkthrough/ShowWalkthroughItemsToolset.kt) · [item schema](https://github.com/forketyfork/walkthrough-plugin/blob/697d5643d75f6285fc7cc13d5001c4902051bff5/src/main/kotlin/com/forketyfork/walkthrough/WalkthroughItem.kt) · [orchestrator](https://github.com/forketyfork/walkthrough-plugin/blob/697d5643d75f6285fc7cc13d5001c4902051bff5/src/main/kotlin/com/forketyfork/walkthrough/WalkthroughOrchestrator.kt) · [build CI](https://github.com/forketyfork/walkthrough-plugin/blob/697d5643d75f6285fc7cc13d5001c4902051bff5/.github/workflows/build.yml) · [Qodana](https://github.com/forketyfork/walkthrough-plugin/blob/697d5643d75f6285fc7cc13d5001c4902051bff5/.github/workflows/qodana.yml)

## 17. X 社区信号：只用于发现问题

已记录的 X 讨论给出两个有用方向：repo map 应显式列出 source of truth、验证命令、危险文件和 done criteria；definitions／usages／impact 的图索引比纯 grep 更适合变更任务。参见 [nykdotdev](https://x.com/nykdotdev/status/2080156702280925222) 与 [goon_nguyen](https://x.com/goon_nguyen/status/2074646267485884675)。

这些帖子只作为需求发现信号：本报告不以 X 帖证明任何项目已经实现相关功能，也不据转发／点赞判断质量。项目能力仍以固定提交、官方文档、测试与 CI 为证据。HN 的 PocketFlow 部分同样是社区体验样本，不是准确率基准。

## 18. 更新后的复用结论：选功能 → Skill＋符号索引

### 18.1 现成方案覆盖了什么

- **选功能与限定范围：** GitHub／Sourcegraph 提供符号跳转和 references；OpenWiki 的 task-routing table、Deep Search 的 scoped question、SourceBridge 的 artifact scope 都能把问题压到可处理范围。
- **生成教学 Skill：** `learn-codebase` 已覆盖苏格拉底提问、学习者状态、分级提示与间隔复习；PocketFlow 覆盖课程章节；CodeTour／walkthrough-plugin 覆盖 IDE 播放。
- **符号级模块索引：** Understand Anything 的 Tree-sitter 图、CodeBoarding 的 LSP call graph、SourceBridge 的 symbol graph／EvidenceRef 最接近可导出的符号索引。
- **持续更新：** OpenWiki 的 diff plan／CI、Understand Anything 的 fingerprints／hook、CodeBoarding 的 baseline diff、SourceBridge 的 freshness 状态提供互补方案。

### 18.2 仍然没有被一个现成 Skill 闭环覆盖的部分

仍未发现单个公开 Skill 同时完成：从自然语言功能选择开始，解析成可验证入口和执行路径；导出可移植教学 Skill；同时附稳定 symbol identity、定义／引用／调用边、source ranges、测试与 Git commit；再在源码变化时判断哪些讲解、练习和掌握度需要失效或重算。

最关键的缺口不是“再写一个总结 prompt”，而是四类契约没有被统一：

1. **功能选择契约：** 一个功能可能跨 UI、API、worker、storage 和 tests，需要证据支持的 scope，而不是只靠关键词搜索。
2. **符号身份契约：** 文件＋行适合显示，不能长期标识符号；需要 SCIP／LSP／Tree-sitter 等索引的统一 ID 与 commit snapshot。
3. **教学产物契约：** Wiki、tour、learning path、Socratic Skill 与练习需要共享同一 evidence manifest，而不是各自重新让 LLM 猜源码。
4. **失效契约：** 源码变更既可能让引用失效，也可能让“学习者已掌握”失效；现有工具通常只更新文档或只更新学习日志，未把两者连接。

因此，现成项目适合按层借鉴，而不是寻找一个全能平替：SourceBridge／Understand Anything／CodeBoarding 提供证据和符号图基准，OpenWiki 提供可维护文档工作流，PocketFlow 提供章节叙事，`learn-codebase` 提供教学 Skill，walkthrough-plugin／CodeTour 提供呈现。Tour-de-Code-AI 只保留交互原型价值。以上是能力组合判断，不是本报告在设计具体实现模块。

## 19. 本轮补充来源与事实边界

### 19.1 直接事实

- 项目产物、调用路径、schema、license、测试与 CI 结论来自上述固定提交源码和仓库文件。
- SourceBridge 的测试文件数量是固定快照本地文件统计，不等同于测试覆盖率或全部通过证明。
- Tour-de-Code 当前生成器不调用 Tree-sitter、会写 `repomix-debug.xml`，来自当前实现；这优先于 README／遗留文件所暗示的架构。
- walkthrough-plugin 的测试／CI 存在证明工程流程较完整，不证明所有 IDE／MCP 组合都无缺陷。
- PocketFlow 没有一等增量机制，是对固定快照可见实现的判断；HN 中的 Git history／scheduled Action 是建议，不是现状。

### 19.2 推断与未验证项

- “核心基准”“专项基准”“高价值低星”是本次围绕教学页面与证据链的适配性判断，不是项目官方定位。
- 未对八个项目运行同仓、同模型、同预算的准确率／成本／延迟基准；不能由架构完整度推出生成内容一定更正确。
- 未以 stars 排名。stars 数字是会变化的时间点快照，license 和源码边界才影响复用决策。
- 未把自然语言 quality gate 等同于形式验证；即使有 EvidenceRef，LLM 也可能从真实证据得出错误解释。
