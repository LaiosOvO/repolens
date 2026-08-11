# 代码仓库如何生成“给人看的”功能教程与技术选型报告

> 调研日期：2026-08-10  
> 目标：为 `repo_teacher` 统一生成器定义一份可实现、可验证的产物合同。  
> 证据范围：官方产品文档、官方论文、官方 GitHub 仓库，以及工作区内已完整克隆的源码。社区讨论只用于发现线索，不作为本文技术结论的证据。

## 先说结论

当前产物最根本的问题不是 HTML 样式，而是信息模型错了一层：**入口、类、函数和文件是实现证据，不是读者首先想知道的“功能”。**

一个给人看的仓库报告，首屏必须直接回答四个问题：

1. 这个项目到底提供哪些功能？
2. 每个功能底层采用什么实现机制？
3. 哪些模块值得复用，哪些只能参考，哪些不应该采用？
4. 如果我要进一步确认，应该点开哪几个文件和哪几段源码？

因此，`repo_teacher` 不应该复制某一个参考项目，而应该组合它们各自最强的部分：

| 需要解决的问题 | 最值得采用的参考 | 采用什么，不采用什么 |
|---|---|---|
| 一眼看到项目做什么 | DeepWiki 的层级 Wiki、CodeWiki 的父级综合 | 采用“总览 → 核心功能 → 子模块”的信息层级；不照搬固定的技术目录模板 |
| 把代码讲成教程 | PocketFlow / Code2Tutorial | 采用“动机 → 使用 → 运行过程 → 内部实现 → 下一章”的教学顺序；不采用全仓一次性塞进提示词 |
| 功能与源码绑定 | DeepWiki-Open CodeMap、Sourcegraph Deep Search | 采用 claim 级源码位置、来源清单、点击跳转；不接受只列文件名的宽泛引用 |
| 从代码中发现结构 | CodeWiki、RepoAgent、Sourcegraph SCIP | 采用静态结构/依赖图作为事实底座；不让 LLM 单独决定调用关系是否存在 |
| 增量更新 | RepoAgent、Sourcegraph 按 commit 建索引 | 采用 Git diff + 反向依赖影响传播 + 内容指纹；不采用只按项目名缓存整份报告 |
| 支撑技术选型 | `repo_teacher` 自己补齐 | 参考项目几乎都在“解释一个仓库”，没有把“跨仓同类功能的底层机制、复用范围和代价”做成一等产物 |

推荐的总架构不是“入口优先”，而是：

```text
源码事实层
  AST / symbols / imports / calls / routes / config / tests / commit
            ↓
语义功能层
  Capability → ImplementationSlice → Evidence → Confidence
            ↓
教学综合层
  项目总览 → 功能卡 → 功能教程 → 源码下钻
            ↓
技术选型层
  同类功能对比 → 采用/改造/放弃 → 可复用文件索引
```

这意味着：**入口仍然要分析，但入口只应出现在“这个功能如何落到源码”的证据区域，不能成为页面的开场方式。**

---

## 一、参考项目到底是怎么做的

### 1. Cognition DeepWiki：强在层级 Wiki 和可引导的页面规划

先区分两个项目：

- **DeepWiki** 是 Cognition 的官方产品，核心实现没有在 `CognitionAI/deepwiki` 仓库中开源；公开仓库主要声明 MCP 接口和刷新行为。
- **DeepWiki-Open** 是 `AsyncFuncAI/deepwiki-open` 的社区开源实现，不能把它的内部实现描述成 Cognition DeepWiki 的实现。

#### 人看到什么

官方 DeepWiki 的产物不是“文件列表”，而是带层级的 Wiki：架构图、代码库摘要、源码链接和可继续问答。官方文档还允许用 `.devin/wiki.json` 显式定义页面的 `title`、`purpose` 和 `parent`；如果给出 `pages`，会绕过默认的 cluster-based planning，严格生成指定页面。这说明它把**页面主题和父子关系**作为稳定的中间结构，而不是直接把入口函数渲染成文章。[DeepWiki 官方文档](https://docs.devin.ai/work-with-devin/deepwiki)

官方给出的组织建议也很明确：先高层总览，再用父子关系形成层级，将相关功能归组，并为每页写清楚具体目的。对于大仓库，可以先用 `repo_notes` 强调重点，只有自动覆盖仍不足时才手工声明全部页面。[DeepWiki 官方文档：Steering 与 Best Practices](https://docs.devin.ai/work-with-devin/deepwiki#steering-deepwiki)

#### 功能如何被发现和组织

官方实现细节未公开，能够确认的是：

- 默认采用 cluster-based planning；
- 用户可以通过 `repo_notes` 改变重点；
- 用户可以用 `pages` 完全覆盖自动规划；
- 页面拥有标题、用途、父级和页级备注，因此可形成面向人的主题树。

这比“扫描到什么入口就展示什么”更符合阅读目的，但也说明自动功能发现必须允许人工 steering，不能假设一次 LLM 聚类永远完整。

#### 源码引用和增量更新

官方 DeepWiki 宣称页面包含源码链接，MCP 暴露 `read_wiki_structure`、`read_wiki_contents` 和 `ask_question` 三个接口，分别服务于结构读取、内容读取和上下文问答。[DeepWiki MCP 官方文档](https://docs.devin.ai/work-with-devin/deepwiki-mcp) 官方 GitHub MCP 条目还说明：带有 DeepWiki badge 的仓库会自动刷新 Wiki。[CognitionAI/deepwiki MCP 条目](https://github.com/mcp/cognitionai/deepwiki)

但公开资料没有给出 claim 级证据验证、变更影响传播或刷新 SLA 的实现，因此不能据此声称它具有精确增量更新。

#### 对 `repo_teacher` 的启示

**直接采用：**

- 项目总览与功能页面分层；
- `title + purpose + parent + notes` 的页面规划合同；
- 自动规划可被显式 steering 覆盖；
- Wiki 结构和 Wiki 内容可分别读取。

**不能直接依赖：**

- Cognition 闭源功能发现算法；
- 没有公开证明的 claim 级验证与增量传播机制。

---

### 2. DeepWiki-Open：强在页面结构、引用后处理和问题驱动 CodeMap

本地源码版本：`AsyncFuncAI/deepwiki-open@4181daa5ebde79a1baf8e92a09dd874f8b74411b`。

#### Wiki 生成管线

已克隆源码首先把文件树和 README 交给 LLM，要求返回结构化 XML。综合模式固定提示模型考虑 Overview、System Architecture、Core Features、数据流、前后端、模型集成、部署和扩展性，并为每页返回 `title`、`description`、`importance`、`relevant_files`、`related_pages` 和所属 section。源码证据：[`api/services/wiki/prompts.py:135-260`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/prompts.py#L135-L260)。

页面生成再使用每页的 relevant files，要求正文包含：引言、逻辑分节、架构/数据流解释、关键函数和类、Mermaid、表格、可选代码、总结，以及对重要信息逐项添加文件和行号引用。源码证据：[`api/services/wiki/prompts.py:25-132`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/prompts.py#L25-L132)。

这个流程的价值在于：先生成页面规划，再生成页面内容，而不是一次提示直接产出一篇巨大报告。

#### 引用如何落到真实源码

DeepWiki-Open 会把模型产出的空链接引用转换为 GitHub、GitLab 或 Bitbucket 的真实源码 URL 和行号锚点，并重建每页的 “Relevant source files” 清单。源码证据：[`api/services/wiki/content.py:24-75`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/content.py#L24-L75)、[`api/services/wiki/content.py:93-158`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/content.py#L93-L158)。

它新增的 CodeMap 更接近“给人讲怎么工作的教程”：先用 RAG 检索与问题相关的源码，再生成包含步骤和引用的 skeleton，随后补充说明与 Mermaid。更重要的是，模型给出的行号不会被直接信任；系统使用引用中的原文 snippet 回到真实文件重新定位行号。源码证据：[`api/services/codemap.py:1-10`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/codemap.py#L1-L10)、[`api/services/codemap.py:128-148`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/codemap.py#L128-L148)、[`api/services/codemap.py:178-223`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/codemap.py#L178-L223)、[`api/services/codemap.py:225-311`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/codemap.py#L225-L311)。

这是非常值得借鉴的原则：**叙事可以由模型生成，但源码位置必须由确定性程序重新核对。**

#### 章节与故障处理

Wiki 页面有界并发生成，每页独立重试；某一页持续失败时以错误占位页降级，而不是让整份 Wiki 消失。结构规划失败则任务整体失败。源码证据：[`api/services/wiki/tasks.py:268-312`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/tasks.py#L268-L312)、[`api/services/wiki/tasks.py:315-358`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/tasks.py#L315-L358)。

#### 增量更新的缺口

当前已克隆版本的 Wiki 缓存键只有 `repo_type + owner + repo + language`，没有 commit SHA、分支、文件摘要或生成器版本。源码证据：[`api/services/wiki/io.py:26-65`](https://github.com/AsyncFuncAI/deepwiki-open/blob/4181daa5ebde79a1baf8e92a09dd874f8b74411b/api/services/wiki/io.py#L26-L65)。

因此，DeepWiki-Open 的缓存可用于加速重复请求，但**不能直接作为可信的版本新鲜度模型**。`repo_teacher` 不应复用这种缓存键。

#### 对 `repo_teacher` 的启示

**直接采用：**

- “结构规划 → 分页生成 → 引用后处理”的分阶段管线；
- CodeMap 的 “检索 → skeleton → enrich” 两段生成；
- 用真实 snippet 重新锚定模型引用；
- 单页失败可降级、整体仍可阅读。

**需要改造：**

- 固定技术目录不能替代按业务功能生成的目录；
- Mermaid 只能从已验证关系生成，不能仅依赖提示词要求“准确”；
- 缓存必须加入 commit、输入文件 digest、生成器版本和 schema 版本。

---

### 3. PocketFlow / Code2Tutorial：强在把抽象概念排成教学顺序

本地源码版本：`The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge@05b24cbbb0fe409c5e23c9791f0342f07524ffdc`。

#### 它不是从入口讲，而是先发现“核心抽象”

管线非常直接：抓取仓库 → 识别核心抽象 → 分析抽象关系 → 决定章节顺序 → 批量写章节 → 组装教程。源码证据：[`flow.py:12-33`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/flow.py#L12-L33)。

`IdentifyAbstractions` 把仓库文件内容和文件索引交给 LLM，让它挑出 5 到 N 个“最有助于新人理解代码库”的核心抽象，为每个抽象生成名称、类比式说明和相关文件索引，再对结构与索引范围做校验。源码证据：[`nodes.py:84-237`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/nodes.py#L84-L237)。

这正是当前 `repo_teacher` 缺少的一层：人应该先看到“Memory、Graph、Gateway、Agent Loop”这类功能或概念，再下钻到 `main()`、`run_graph()` 和文件路径。

#### 它如何决定章节顺序

关系分析阶段要求每个抽象至少参与一条关系，并产生项目摘要与简短关系标签；章节排序阶段再基于重要性、基础性、用户可见性和依赖顺序给出完整、不重复的章节序列。源码证据：[`nodes.py:240-407`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/nodes.py#L240-L407)、[`nodes.py:410-534`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/nodes.py#L410-L534)。

它不是“目录顺序”，而是“教学顺序”。这是应该直接移植到人类报告的核心思想。

#### 每章如何写得像教程

章节提示词要求：

- 先说明这个抽象解决什么问题；
- 用一个中心用例贯穿；
- 先非代码或少代码解释运行过程；
- 代码块控制在 10 行以内并逐段说明；
- 解释内部实现和相关文件；
- 使用简单 Mermaid；
- 使用类比；
- 与上一章、下一章形成过渡链接。

源码证据：[`nodes.py:630-743`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/nodes.py#L630-L743)。最后的首页先给项目摘要和抽象关系图，再列出按教学顺序排列的章节。源码证据：[`nodes.py:753-851`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/nodes.py#L753-L851)。

#### 技术缺口

- 功能抽象和关系主要由 LLM 从全仓上下文判断，缺少 AST/SCIP 事实约束；
- 相关文件只有文件级索引，没有 claim 级行号；
- 调用关系标签经过结构校验，但没有回到源码验证这条边真的存在；
- 它把全部文件直接拼为上下文，大仓库扩展性弱；
- LLM 缓存以完整 prompt 为 key，没有 commit 或依赖影响模型。源码证据：[`utils/call_llm.py:25-43`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/utils/call_llm.py#L25-L43)、[`utils/call_llm.py:128-156`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/05b24cbbb0fe409c5e23c9791f0342f07524ffdc/utils/call_llm.py#L128-L156)。

#### 对 `repo_teacher` 的启示

**直接采用：**

- 核心功能/抽象优先，而不是入口优先；
- 基于基础性和用户价值的教学顺序；
- 每章“为什么 → 怎么用 → 运行过程 → 内部实现 → 下一章”的结构；
- 首页项目摘要 + 功能关系图 + 章节阅读路线。

**必须换掉：**

- 全仓一次性提示；
- LLM 单独认定功能和关系；
- 只到文件、不落到符号和行号的证据。

---

### 4. RepoAgent：强在结构化源码事实和受影响文档的增量更新

官方论文将流程分成三阶段：Global Structure Analysis、Documentation Generation、Documentation Update。[RepoAgent EMNLP 2024 论文](https://aclanthology.org/2024.emnlp-demo.46/)

#### 它如何理解仓库

RepoAgent 先把 Python 文件解析为 AST，以目录、文件、类和函数形成 project tree；再用 Jedi 提取 caller/callee 双向引用，将树扩展为依赖 DAG。它把代码对象而不是自然语言猜测作为文档原子，并按子节点和依赖对象优先的自底向上拓扑顺序生成文档。[论文第 2.1–2.2 节](https://aclanthology.org/2024.emnlp-demo.46.pdf)

这对实现准确性非常有价值，但它的原子仍然是 class/function，不是产品功能。后续工作必须在对象 DAG 上再做一次**功能聚合**，否则仍会得到“函数目录”，而不是“这个项目能做什么”。

#### 它的文档合同

论文定义的对象文档包括 Functionality、Parameters、Code Description、Notes 和 Examples；上下文包含 project tree、源码片段、引用关系、对象元信息，以及可选的子节点既有文档。Markdown 层级跟随项目树，最后由 GitBook 展示。[论文第 2.2 节](https://aclanthology.org/2024.emnlp-demo.46.pdf)

这个模板适合 API/对象参考手册，但不够支撑项目级技术选型：它没有要求说明同类方案、底层机制差异、复用文件范围和采用风险。

#### 它如何增量更新

RepoAgent 用 Git pre-commit hook 发现 staged code changes，并只更新受影响对象。论文明确列出三类触发：对象源码变化、原有引用者不再引用它、对象获得新引用；文档与代码一并提交。[论文第 2.3 节](https://aclanthology.org/2024.emnlp-demo.46.pdf) 官方 README 也暴露 `run`、`diff`、`clean`，并保存全局结构记录以支持后续更新。[OpenBMB/RepoAgent 官方仓库](https://github.com/OpenBMB/RepoAgent)

#### 对 `repo_teacher` 的启示

**直接采用：**

- AST/符号/双向引用构成的确定性事实层；
- 按依赖自底向上生成，再向上综合；
- Git diff 和反向依赖驱动的选择性更新；
- 可先输出 dry-run 的“哪些报告会失效”。

**需要改造：**

- 从 Python/Jedi 扩展为多语言解析器；
- 在函数/类 DAG 之上增加功能聚类和功能 claim；
- 增量范围必须覆盖功能页、父级总览和跨项目比较单元格，而不只是对象 Markdown。

---

### 5. Sourcegraph Cody / Deep Search：强在检索、精确导航和来源审计

Sourcegraph Deep Search 不是静态 Wiki 生成器，而是一个问题驱动的代码研究 Agent。它反复调用 Code Search 和 Code Navigation 工具，逐步缩小答案；每次回复都带有详细来源清单，列出执行过的搜索和读取过的文件。答案是 Markdown，可链接文件、目录和仓库，也可以按要求生成图。[Deep Search 官方文档](https://sourcegraph.com/docs/deep-search)

#### 功能发现方式

它不预先声称“已经完整发现了项目所有功能”，而是围绕一个有边界的问题，用 agentic loop 搜索直到有把握。用户可用 search context 和 `@repo` / `@file` 缩小范围。对于清单、审计、迁移计划等大结果，它还能生成 CSV、JSON 和 SVG，并在后续问题中复用这些产物。[Deep Search 官方文档](https://sourcegraph.com/docs/deep-search)

这适合做**二次核验和补漏**，不适合作为唯一的项目首页生成策略：如果没有一组预定义的问题，它不会自然产出稳定的全仓功能目录。

#### 底层上下文和代码图

Cody 官方文档列出三类上下文源：关键词搜索、Sourcegraph Search、Code Graph。Code Graph 根据组件关系找上下文，而不是只靠文本相似度。[Cody Context 官方文档](https://sourcegraph.com/docs/cody/core-concepts/context)

Sourcegraph 的代码导航分为：

- 开箱即用的搜索式导航：文本搜索加语法启发式；
- precise navigation：使用编译期信息和 SCIP 索引，提供定义、引用、实现和跨仓导航。

[Code Navigation 官方文档](https://sourcegraph.com/docs/code-navigation) 精确索引按具体 commit 生成并上传；auto-indexing 可以根据策略定期对仓库和 commit 建索引。[Auto-indexing 官方文档](https://sourcegraph.com/docs/code-navigation/auto-indexing)

#### 对 `repo_teacher` 的启示

**直接采用：**

- 每份结论附“搜索过什么、读过哪些文件”的来源账本；
- 能从报告直接跳转定义、引用、实现；
- 用 scope 限定单个项目、功能或模块；
- 对跨仓技术选型使用结构化 CSV/JSON 中间结果，再生成可读摘要；
- 在支持语言上，优先消费 SCIP/LSP 级精确关系。

**不应照搬：**

- 只提供问答、不生成稳定的功能目录；
- 把商业 Sourcegraph 基础设施作为本地 MVP 的硬依赖。

`repo_teacher` 的合理位置是：静态功能报告负责“先告诉我该看什么”，Deep Search 式研究负责“对某个疑点继续查证”。

---

### 6. CodeWiki / CodeWikiBench：强在层级分解、父级综合和可量化评估

CodeWiki 是这次调研中最接近完整目标的信息架构参考。它先用 Tree-Sitter 抽取函数、方法、类、结构体、模块和依赖关系，再通过拓扑与语义划分形成 feature-oriented module tree；叶子模块由 Agent 生成说明、使用示例、API 和架构信息，复杂模块可以继续委派子 Agent；最后父模块从子文档、模块树和依赖图自底向上综合出架构总览、功能摘要、使用指南和图。[CodeWiki ACL 2026 论文，第 2 节](https://aclanthology.org/2026.findings-acl.288.pdf)

这正好解释为什么“直接从入口开始讲”会让人累：入口只能帮助找到高层起点，但最终产物必须经过 feature-oriented decomposition 和 parent synthesis，才能从源码对象上升到人可以理解的功能。

CodeWikiBench 还指出，BLEU/ROUGE 这类表面相似度无法判断仓库文档是否清晰、正确、完整。它从官方文档生成仓库专属层级 rubric，让多个 judge 只评具体叶子要求，再向上加权汇总并报告分歧。[CodeWikiBench 方法](https://aclanthology.org/2026.findings-acl.288.pdf)

#### 对 `repo_teacher` 的启示

**直接采用：**

- 多语言 AST/依赖图；
- feature-oriented module tree；
- 叶子模块生成、父模块综合，而不是把叶子摘要直接拼在一起；
- 跨模块引用注册表；
- 复杂度超阈值时递归拆分；
- 以项目官方文档和用户选择的功能清单形成覆盖 rubric。

**需要补强：**

- CodeWiki 仍主要解决“把一个仓库写成文档”，没有把跨仓技术选型做成核心数据模型；
- `repo_teacher` 必须进一步为每个功能产出 reuse verdict、依赖闭包、许可证边界和替代实现对比。

---

### 7. 两个补充 benchmark：Understand Anything 与 OpenWiki

这两个本地已克隆项目不替代前述主参考，但分别补上了“交互式教学路径”和“文档生命周期”的证据。

#### Understand Anything：图不是终点，guided tour 才是教学层

本地源码版本：`Egonex-AI/Understand-Anything@fe8c5bc591716aafd79b4765549328f08ef5a52e`。

官方 README 明确区分结构图和业务视图：前者展示文件、函数、类和依赖，后者把代码映射为 domain、flow 和 step；节点同时提供自然语言摘要和 guided tours。源码中的 tour builder 还把教学顺序视为独立产物，会综合非代码文件、拓扑入口和聚类结果，而不是把关系图本身当作教程。[`README.md:53-85`](https://github.com/Egonex-AI/Understand-Anything/blob/fe8c5bc591716aafd79b4765549328f08ef5a52e/README.md#L53-L85)、[`tour-builder.md:10-100`](https://github.com/Egonex-AI/Understand-Anything/blob/fe8c5bc591716aafd79b4765549328f08ef5a52e/understand-anything-plugin/agents/tour-builder.md#L10-L100)

对 `repo_teacher` 的直接启示是：结构图负责回答“哪些对象相连”，功能页和 guided tour 负责回答“为什么这样连、应该按什么顺序理解”。两者必须分层，不能用一张大图代替解释。

#### OpenWiki：纯 Markdown 所有权、可 steering 更新和图的失败降级

本地源码版本：`langchain-ai/openwiki@7531d615216e8cbccf464f66cfbbae3668871c84`。

OpenWiki 把 Wiki 作为随代码版本化的纯 Markdown，允许用 `openwiki/INSTRUCTIONS.md` 维护仓库级范围和优先级，并只维护 `AGENTS.md` / `CLAUDE.md` 中自己的 marker 区域。它还为 Mermaid 做验证：无效图会降级为带说明的文本 fence，而不是让整页出现坏图；后续更新再尝试修复。[`README.md:143-175`](https://github.com/langchain-ai/openwiki/blob/7531d615216e8cbccf464f66cfbbae3668871c84/README.md#L143-L175)

其 no-op 测试覆盖未变化运行、忽略路径、仅 Wiki 自身变化和真实源码变化，证明“没有有效输入变化就不重写产物”是一条可测试合同。[`update-noop.test.ts:55-157`](https://github.com/langchain-ai/openwiki/blob/7531d615216e8cbccf464f66cfbbae3668871c84/test/agent/update-noop.test.ts#L55-L157)

对 `repo_teacher` 的直接启示是：

- 人工 steering 应存入用户拥有、生成器不覆盖的配置文件；
- 更新必须有 no-op gate，避免每次生成制造无意义 diff；
- 图要有语法验证和可读降级；
- HTML 可以是主阅读界面，但 Markdown/JSON 必须是可移植、可版本化的源产物。

---

## 二、横向参考采用矩阵

下表评价的是“对 `repo_teacher` 目标的参考价值”，不是项目总体质量。

| 维度 | DeepWiki | DeepWiki-Open | PocketFlow / Code2Tutorial | RepoAgent | Sourcegraph / Deep Search | CodeWiki | `repo_teacher` 应采用 |
|---|---|---|---|---|---|---|---|
| 首屏是否直接讲功能 | 是，主题 Wiki | 部分，常用固定技术目录 | 是，核心抽象优先 | 弱，对象优先 | 取决于问题 | 是，父级综合功能 | **强制功能优先** |
| 功能发现 | 默认聚类，可人工 steering | 文件树 + README + LLM | 全仓文本 + LLM 抽象 | AST 对象 + 引用 DAG | 查询驱动 Agent 搜索 | AST 依赖图 + 功能模块树 | **静态候选 + LLM 聚合 + 验证 + 人工覆盖** |
| 教学顺序 | 层级导航 | 页面/section | 最强，专门排序章节 | 拓扑对象顺序 | 对话顺序 | 叶到父综合 | **价值优先，再依赖优先** |
| claim 级源码证据 | 官方宣称源码链接，细节闭源 | 强，行号后处理；CodeMap 可 snippet 回锚 | 弱，文件级 | 中，对象源码和关系上下文 | 强，详细 sources + 导航 | 论文强调图与上下文，claim 合同不如 CodeMap 清晰 | **每个关键 claim 必须绑定 source range** |
| 关系图可信度 | 未公开 | Wiki 图有 LLM 风险；CodeMap 可改善 | 关系由 LLM 生成 | Jedi caller/callee | SCIP 最强，搜索导航可回退 | Tree-Sitter 统一依赖图 | **图边必须标注 observed / inferred / unknown** |
| 大仓扩展性 | 有产品能力，细节闭源 | RAG + 分页并发 | 弱，全仓提示 | 对象级拓扑生成 | 强，搜索/索引基础设施 | 强，递归委派 | **模块树 + 检索 + 分层生成** |
| 增量更新 | badge 可自动刷新，细节未知 | 缓存不含 commit，不能保证 | prompt cache，不是影响更新 | 强，Git diff + 受影响对象 | commit 索引和策略更新 | 论文重点不是增量 | **RepoAgent 模型 + 内容寻址清单** |
| 技术选型对比 | 无 | 无 | 无 | 无 | 可按问题临时生成 | 无 | **必须自建一等实体** |
| 直接代码复用价值 | 闭源核心不可复用 | 高，MIT；可参考引用与分页管线 | 高，MIT；可参考教学编排 | 高，Apache-2.0；可参考增量与对象图 | 更适合作为协议/产品思想参考 | 高价值架构参考，需另行核对仓库许可证 | **按模块采用，不整仓照搬** |

### 机制层技术选型矩阵

这张表才是最终用户做技术选型时应该看到的对比颗粒度。

| 子问题 | 方案 A | 方案 B | 方案 C | 推荐 |
|---|---|---|---|---|
| 仓库内容选取 | PocketFlow：全文件拼接 | DeepWiki-Open：RAG chunks | Sourcegraph：搜索 + code graph | 小仓可全量；生产默认检索 + 结构图，禁止无界拼接 |
| 代码结构抽取 | RepoAgent：Python AST + Jedi | CodeWiki：Tree-Sitter 多语言依赖 | Sourcegraph：SCIP 编译期图 | Tree-Sitter 做通用底座；支持时叠加 SCIP/LSP；语言特化可补 Jedi |
| 功能主题发现 | DeepWiki：cluster planning + steering | PocketFlow：LLM 核心抽象 | CodeWiki：feature module tree | 静态候选 → LLM 聚合 → evidence validator → 人工 override |
| 文档组织 | RepoAgent：对象树 | PocketFlow：线性教程 | DeepWiki/CodeWiki：层级 Wiki | 首页总览 + 功能树；功能页内部使用线性教程 |
| 图生成 | LLM 直接写 Mermaid | 从结构化关系生成 Mermaid | SCIP/AST 图后再渲染 | 只从结构化关系生成；LLM 只写图注，不发明边 |
| 引用 | 仅文件列表 | 文件 + 行号后处理 | snippet 回到真实文件重新定位 | 使用 snippet/hash 回锚，生成 commit-pinned 链接 |
| 更新 | 整体重生成/缓存 | Git diff 对象更新 | commit 级索引 + 依赖影响 | 路径 digest + 反向依赖 + 父级/比较页失效传播 |

---

## 三、`repo_teacher` 的统一产物合同

### 3.1 产物边界

每个被分析仓库必须产出：

1. **一个可以独立阅读的主 HTML。** 读者不打开 JSON、不看日志，也能知道项目功能、实现机制、复用建议和证据。
2. 一个机器可读 `report.json`，作为 HTML 的唯一结构化来源。
3. 一个 `manifest.json`，记录 repository commit、输入摘要、生成器版本、schema 版本、生成时间和失效依赖。

JSON 是机器合同，HTML 是人的合同。不能让人类报告退化成 JSON 的平铺渲染。

### 3.2 首屏硬性合同

首屏只能按以下顺序出现：

1. 项目名称和一句话结论；
2. “它提供哪些功能”——3 到 7 张功能卡；
3. “是否值得参考/复用”——一句总判定；
4. “建议先看什么”——按用户目标给出 2 到 4 条阅读路线。

首屏禁止出现：

- “从入口开始”；
- 以 `main()`、类名、文件路径作为一级标题；
- “0 个能力”之类把内部检测指标当用户结论的文案；
- 一大段代码或 schema；
- 没有解释意义的文件数量、symbol 数量和 evidence 数量。

如果只能确认候选功能，也应该直接写：

> 源码中识别到 5 组功能候选：Memory、Graph、Gateway、Agent Loop、Voice。它们已经绑定到具体模块，但运行时行为尚未全部验证。

而不是写：

> 识别到 2 个入口和 5 个入口候选。

### 3.3 核心语义实体

统一生成器必须把下面四种对象分开：

```json
{
  "capability": {
    "id": "stable-semantic-id",
    "name": "给人看的功能名",
    "user_outcome": "用户用它完成什么",
    "mechanism_summary": "底层用什么机制完成",
    "confidence": "verified|supported|candidate|unknown",
    "implementation_slices": ["slice-id"],
    "claims": ["claim-id"],
    "reuse_decision": "adopt|adapt|reference|avoid",
    "reuse_reason": "为什么",
    "alternatives": ["其他项目中的同类实现"]
  },
  "implementation_slice": {
    "id": "slice-id",
    "module": "仓库内业务模块",
    "path": "repo/relative/path",
    "symbol": "qualified.symbol",
    "line_start": 1,
    "line_end": 20,
    "role": "entry|orchestration|domain|storage|adapter|test|config",
    "dependencies": ["slice-id"]
  },
  "claim": {
    "id": "claim-id",
    "text": "可读结论",
    "evidence": ["evidence-id"],
    "status": "verified|supported|inferred|unknown"
  },
  "evidence": {
    "id": "evidence-id",
    "repo_commit": "git sha",
    "path": "repo/relative/path",
    "line_start": 1,
    "line_end": 20,
    "snippet_hash": "sha256",
    "relation": "defines|calls|imports|configures|tests|documents"
  }
}
```

特别要注意：

- `Capability` 是给人看的功能；
- `ImplementationSlice` 是可以复用或阅读的源码边界；
- `Claim` 是报告里的具体断言；
- `Evidence` 才是文件、符号和行号；
- `EntryPoint` 只是一种 `ImplementationSlice.role`，不能替代 `Capability`。

### 3.4 主 HTML 的章节顺序

#### A. 30 秒看懂

- 一句话项目定位；
- 3–7 个核心功能；
- 适合谁、不适合谁；
- 总复用判定。

#### B. 功能地图

每张功能卡只显示：

- 功能名；
- 用户结果；
- 一句话机制；
- 证据置信度；
- 复用结论；
- “看它怎么实现”链接。

功能地图不得显示长代码，也不得以文件路径命名功能。

#### C. 技术选型摘要

每个功能用一行对比：

| 功能 | 本项目机制 | 同类项目机制 | 优点 | 代价/风险 | 建议 |
|---|---|---|---|---|---|

如果没有同类项目证据，必须显示“尚未比较”，不能自动补常识。

#### D. 功能教程

每个功能必须采用固定的教学结构：

1. **为什么需要它**：解决什么实际问题；
2. **你会得到什么**：输入、输出、可观察结果；
3. **最短运行路径**：3–7 步，不先展示代码；
4. **底层怎么实现**：模块协作图；
5. **关键源码**：按 orchestration、domain、adapter、storage、test 分组；
6. **实现边界**：没有实现什么、哪些只是候选；
7. **怎么复用**：最小文件集合、依赖闭包、配置、测试和改造点；
8. **继续阅读**：下一个功能或源码位置。

#### E. 源码证据与入口

直到这里才展示：

- 程序入口；
- 路由/CLI/公开接口；
- 类与函数；
- 文件树；
- claim 到行号的证据；
- 未解析或冲突的关系。

这一层服务于核验，不负责第一次解释项目。

#### F. 技术采用清单

每个用户选择的功能导出：

- `ADOPT.md`：为什么选它；
- `MODULE_INDEX.md`：功能 → 模块 → 文件 → 符号 → 测试；
- `DEPENDENCIES.md`：运行时、构建时和可选依赖；
- `RISKS.md`：许可证、平台、性能、安全和未验证项；
- `SKILL.md`：供后续 Agent 按该索引阅读和实现，不把整仓塞入上下文。

主 HTML 应该提供这些导出的预览和下载入口，但不能要求读者下载以后才看懂结论。

---

## 四、统一生成管线

### 阶段 1：固定版本与事实抽取

1. 固定 repository commit；
2. 读取 manifest、README、官方 docs、examples、tests、路由和 CLI；
3. 用 Tree-Sitter/语言 parser 生成 symbols、imports、calls、inheritance、routes；
4. 支持时接入 SCIP/LSP 精确关系；
5. 所有边标记来源：`parser`、`compiler_index`、`search`、`llm_inferred`；
6. 生成可重现的 `code_facts.json`。

### 阶段 2：功能候选生成

功能候选不只来自入口，应综合：

- README/官方 docs 中的显式功能标题；
- CLI command、API route、public export；
- examples 和 tests 覆盖的用户行为；
- 模块聚类和高连通组件；
- 配置开关和插件注册；
- 用户指定的重点或 override 文件。

LLM 可以合并同义候选、生成可读名称、描述用户结果，但不得独立创建没有源码/文档证据的功能。

### 阶段 3：功能验证

每个候选功能至少要有：

- 一个稳定的入口或公开表面；
- 一个实际实现模块；
- 一条跨模块关系，或明确说明它是单模块功能；
- 一个测试、example、配置或官方文档证据；
- 至少一个 claim 级源码锚点。

证据不足时保留为 `candidate`，不要混入“已确认功能”计数。

### 阶段 4：功能树与教学顺序

采用 CodeWiki 的 feature-oriented module tree 和 PocketFlow 的教学排序，排序信号建议为：

1. 用户价值/用户可见性；
2. 是否是其他功能的前置概念；
3. 是否有足够证据；
4. 是否是用户当前技术选型关注点；
5. 实现复杂度由浅入深。

不能简单使用文件路径字母序、symbol 数或入口扫描顺序。

### 阶段 5：分层生成

- 叶子 ImplementationSlice 只生成短的源码说明；
- Capability 页面从自己的 slices 和 claims 综合；
- 项目总览从 Capability 页面综合；
- 技术选型页从不同项目同类 Capability 的结构化字段综合；
- 上层只能引用下层已经验证的 claim，不能重新自由发挥。

### 阶段 6：引用回锚和图验证

借鉴 DeepWiki-Open CodeMap：

- 模型输出必须携带 snippet；
- 程序在固定 commit 的真实文件中重新定位 snippet；
- 行号匹配失败则 claim 降级，不生成可点击的“伪精确”链接；
- Mermaid 只从结构化、带 provenance 的关系生成；
- `llm_inferred` 边用虚线并显示“推断”，不得与 AST/SCIP 边混色。

### 阶段 7：HTML 综合

HTML 生成不是把所有 JSON 字段遍历打印出来，而是执行明确的 editorial policy：

- 功能卡只取决定所需字段；
- 证据默认折叠；
- 代码默认不超过 10–20 行；
- 先总结，再解释，再给证据；
- 每节结尾给出“这对技术选型意味着什么”；
- 每个图都必须有一句读图结论。

---

## 五、增量更新合同

### 5.1 manifest 必须包含

```json
{
  "repo_commit": "sha",
  "generator_version": "semver-or-sha",
  "schema_version": "vN",
  "configuration_digest": "sha256",
  "files": {
    "path": "content-sha256"
  },
  "entities": {
    "capability-id": {
      "input_evidence": ["evidence-id"],
      "depends_on": ["capability-id"],
      "output_digest": "sha256"
    }
  }
}
```

### 5.2 失效传播

当文件变化时：

1. 重新解析变化文件；
2. 比较 symbol 和 relation diff；
3. 找到直接引用这些 evidence 的 claims；
4. 失效对应 ImplementationSlices；
5. 失效包含这些 slices 的 Capability；
6. 沿反向依赖失效上游 Capability；
7. 失效项目总览中对应摘要；
8. 失效所有包含该 Capability 的跨项目比较单元格；
9. 只重新生成失效子树和其父级综合。

这综合了 RepoAgent 的受影响对象更新和 CodeWiki 的父级综合。DeepWiki-Open 那种不含 commit 的项目级缓存不能满足这个合同。

### 5.3 新鲜度必须在人类报告中可见

主 HTML 顶部显示：

- 分析 commit；
- 生成时间；
- 与当前 HEAD 是否一致；
- 是否有失效但未重建的功能；
- 本次是完整重建还是增量重建。

---

## 六、技术选型产物合同

现有参考项目都没有完整解决这一层，因此它应该成为 `repo_teacher` 的差异化能力。

### 6.1 比较单位必须是“功能机制”，不是项目名

错误方式：

> DeepWiki vs PocketFlow vs RepoAgent，哪个最好？

正确方式：

> 在“功能发现”上，DeepWiki 使用可 steering 的聚类页面规划，PocketFlow 使用 LLM 核心抽象，RepoAgent 使用 AST 对象树，CodeWiki 使用依赖图上的 feature module tree；对于本地生产级索引，应选择 Tree-Sitter/SCIP 事实底座 + LLM 聚合 + 人工 override。

### 6.2 每个比较单元格必须包含

- 实现机制；
- 证据来源；
- 适用规模；
- 准确性边界；
- 运行/运维代价；
- 可直接复用的模块；
- 需要重写的部分；
- 许可证与外部服务约束；
- 最终 verdict：`adopt / adapt / reference / avoid`。

### 6.3 最终推荐必须允许组合

技术选型不是必须选一个整仓。报告应该支持这样的结论：

> 采用 DeepWiki-Open 的引用回锚，采用 PocketFlow 的章节教学模板，采用 RepoAgent 的 Git 影响更新，采用 CodeWiki 的层级模块综合；Sourcegraph SCIP 作为可选精确索引后端。不要采用 PocketFlow 的全仓 prompt，也不要采用 DeepWiki-Open 的无 commit 缓存键。

这比“项目 A 评分 8.2，项目 B 评分 7.8”更能指导真实实现。

---

## 七、质量门：怎样证明报告真的“给人看得懂”

### 7.1 结构门

- 首个内容区必须是功能，不是入口；
- 每个项目有 3–7 个一级功能，更多功能必须分组；
- 每个功能都有用户结果、机制、源码和复用结论；
- 所有源码路径都能点击；
- 入口和文件树位于后半部分。

### 7.2 证据门

- 每个重要 claim 至少一个固定 commit 的源码证据；
- 行号必须通过真实文件回锚；
- 图中每条边都有 provenance；
- 找不到证据的内容必须标 `unknown` 或 `candidate`；
- 不允许把 README 宣称直接升级为运行时已验证事实。

### 7.3 教学门

- 让一个不了解仓库的人在 30 秒内说出“它提供哪 3–5 个主要功能”；
- 让读者在 2 分钟内找到某功能的实现机制和关键模块；
- 让读者在 5 分钟内判断这个功能是 adopt、adapt 还是 avoid；
- 每个功能教程有一个具体用例和一条最短运行路径；
- 代码片段有解释，且不是连续大段源码。

### 7.4 技术选型门

- 同类能力使用统一比较维度；
- 每个 verdict 都有证据和 trade-off；
- 支持组合采用，不强迫整仓二选一；
- 选择某模块后能导出完整源码索引与依赖闭包；
- 报告区分“可复制代码”“可参考设计”“只能使用外部服务”。

### 7.5 自动评估与人测

借鉴 CodeWikiBench，生成器应为每个项目生成层级 rubric，但 rubric 的 ground truth 由以下来源组合：

- 官方 README/docs 中显式功能；
- CLI/API/public exports；
- examples/tests；
- 用户显式选择的重点功能；
- 独立审计 Agent 的反例检查。

自动 judge 只评具体叶子要求，例如“Voice 功能页是否说明 ASR、TTS 和唤醒/按键模式各自对应的源码模块”，不要评“文档是否优秀”这种抽象问题。最终上线前仍需要真实浏览器和 3 个任务式人测，而不是只做文本快照测试。

---

## 八、建议的实施优先级

### P0：先修正产物语义，不先扩 UI

1. 增加 `Capability / ImplementationSlice / Claim / Evidence` 四层模型；
2. 页面首屏改成功能优先；
3. 每个功能生成 user outcome、mechanism、reuse verdict；
4. 入口和符号移到证据区；
5. 用真实源码回锚所有行号。

这一步完成后，用户打开 Waku 报告首先应该看到 Memory、Graph、Gateway、Agent Loop、Voice，而不是 `main()` 和入口候选。

### P1：把功能页变成真正教程

1. 引入 PocketFlow 式章节模板；
2. 从结构化关系生成模块协作图；
3. 按功能输出最小复用文件集；
4. 增加“为什么采用/为什么不采用”；
5. 支持用户 override 功能树和阅读重点。

### P2：跨项目技术选型

1. 为同类 Capability 建立标准分类；
2. 生成机制层对比矩阵；
3. 支持组合采用；
4. 导出选中模块的 `SKILL.md` 与 `MODULE_INDEX.md`；
5. 对许可证和外部服务边界做结构化检查。

### P3：生产级增量更新

1. manifest 和文件/实体指纹；
2. Git diff + 反向依赖失效；
3. Capability 父级综合的局部重建；
4. 跨项目比较单元格局部重建；
5. 支持 dry-run、失败降级和新鲜度显示。

---

## 九、明确不采用的做法

| 做法 | 不采用原因 |
|---|---|
| 只把当前 HTML 换皮 | 解决不了“入口被当成功能”的语义错误 |
| 首页从入口、类或文件开始 | 源码组织不是人类的第一阅读目标 |
| 把所有检测结果平铺 | 没有总分总、没有优先级、没有教学路线 |
| LLM 自由生成调用图 | 图看起来完整但无法证明边存在 |
| 只列“相关文件” | 不能验证具体 claim，也不能指导模块复用 |
| 用星数直接决定技术选型 | 星数不等于机制适配，也不能回答复用边界 |
| 整仓选一个参考项目照搬 | 最优方案来自多个项目的模块组合 |
| 缓存只按 repo 名称 | 无法证明报告对应哪个 commit |
| 生成完成就算质量通过 | 必须有结构门、证据门、教学门、选择门和真实人测 |

---

## 十、一手来源索引

### 官方产品与论文

- [Cognition：DeepWiki 官方文档](https://docs.devin.ai/work-with-devin/deepwiki)
- [Cognition：DeepWiki MCP 官方文档](https://docs.devin.ai/work-with-devin/deepwiki-mcp)
- [Cognition：DeepWiki 发布说明](https://cognition.com/blog/deepwiki)
- [CognitionAI/deepwiki MCP 官方条目](https://github.com/mcp/cognitionai/deepwiki)
- [RepoAgent 官方仓库](https://github.com/OpenBMB/RepoAgent)
- [RepoAgent，EMNLP 2024 官方论文页](https://aclanthology.org/2024.emnlp-demo.46/)
- [Sourcegraph Deep Search 官方文档](https://sourcegraph.com/docs/deep-search)
- [Sourcegraph Cody Context 官方文档](https://sourcegraph.com/docs/cody/core-concepts/context)
- [Sourcegraph Code Navigation 官方文档](https://sourcegraph.com/docs/code-navigation)
- [Sourcegraph Auto-indexing 官方文档](https://sourcegraph.com/docs/code-navigation/auto-indexing)
- [CodeWiki / CodeWikiBench，ACL 2026 官方论文](https://aclanthology.org/2026.findings-acl.288.pdf)

### 本地已克隆源码

- `/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open`  
  remote: `https://github.com/AsyncFuncAI/deepwiki-open.git`  
  commit: `4181daa5ebde79a1baf8e92a09dd874f8b74411b`
- `/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial`  
  remote: `https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge.git`  
  commit: `05b24cbbb0fe409c5e23c9791f0342f07524ffdc`
- `/Volumes/T7/workspace/ontology/graph/repo/understand-anything`  
  remote: `https://github.com/Egonex-AI/Understand-Anything.git`  
  commit: `fe8c5bc591716aafd79b4765549328f08ef5a52e`
- `/Volumes/T7/workspace/ontology/graph/repo/openwiki`  
  remote: `https://github.com/langchain-ai/openwiki.git`  
  commit: `7531d615216e8cbccf464f66cfbbae3668871c84`

## 最终判断

`repo_teacher` 的目标不应该是“生成更多源码说明”，而应该是：

> **先把仓库还原成一组人能理解的功能，再把每个功能还原成可以核验、比较和复用的实现切片。**

只要统一生成器仍然以 entrypoint 为第一层，它就会继续产出“机器索引”；只有把 Capability 变成一等实体，并把教学综合和技术选型做成固定合同，最终 HTML 才会成为真正给人看的产品。
