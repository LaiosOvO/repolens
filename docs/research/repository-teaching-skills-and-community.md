# 代码仓库“给人看懂”研究：Skills、DeepWiki、PocketFlow 与社区证据

> 调研日期：2026-08-10  
> 目标：不是继续生成更多代码清单，而是确定“代码索引最终应如何变成人能快速理解、还能用于技术选型的 HTML”。  
> 证据口径：优先产品官方文档、上游源码和 Skill 原文；X / Hacker News 只作为需求信号与失败案例，不作为功能已经实现的证明。GitHub Star 为调研当日快照，只反映传播度，不代表代码质量。

## 先给结论

当前最值得采用的不是某一个完整项目，而是四类能力的组合：

1. **PocketFlow 的“核心抽象 → 关系 → 教学顺序 → 分章”生成流程**，用于把仓库从文件列表提升为概念地图。
2. **CodeBoarding / RepoAgent / Codebase Memory 的静态分析与源码校验**，用于约束 LLM，不让“看起来合理”的架构说明替代源码事实。
3. **`codebase-to-course` 与 `walkthrough` 的人类教学结构**，用于先说“项目有哪些功能、为什么值得看”，再通过交互图和代码翻译下钻。
4. **DeepWiki / CodeTour 的来源链接与追问路径**，用于让每个结论都能回到文件、符号、行号和固定版本。

对现有 `repo-teacher` 的直接产品判断是：

- 首页必须先回答 **“这个项目能做什么，我该看哪几个功能”**，不能从入口、类、函数或候选符号开始。
- 第二层必须回答 **“每个功能底层采用什么技术机制，核心源码在哪”**。
- 第三层才展示入口、调用关系、代码片段和置信度。
- 面向技术选型还必须增加 **跨项目、同功能的实现对比**；只有单仓教学页，仍不能完成用户的最终决策任务。

推荐的最终信息架构：

```text
一屏结论
  ├─ 这个项目提供哪些功能
  ├─ 最值得复用的 3 个模块
  └─ 不建议复用 / 尚未证实的部分

功能地图
  └─ 每个功能：用户价值 → 技术机制 → 关键模块 → 实现流程 → 证据 → 局限

技术选型矩阵
  └─ 同一功能在不同项目中的实现方式、依赖、成熟度、复用成本和推荐结论

源码证据
  └─ 文件 / 符号 / 行号 / 调用关系 / 测试 / Git 版本 / 置信度

教学模式（可选）
  └─ 交互图、代码↔白话、逐步导览、术语表、练习与追问
```

这套结构与用户当前的不满直接对应：**入口是证据，不是答案；代码路径是下钻，不是首页；HTML 是决策界面，不是 Markdown 的平铺渲染。**

## 一、参考产品到底实现了什么

### 1. DeepWiki：自动 Wiki、架构图、源码链接和上下文问答

[DeepWiki 官方文档](https://docs.devin.ai/work-with-devin/deepwiki)明确列出的能力包括：自动索引仓库、生成 Wiki 与架构图、链接源码，以及基于仓库上下文回答复杂问题。公开仓库版本提供基础文档与问答，完整 Devin 体验还会结合高级代码搜索、规划和会话。

最值得复用的不是页面样式，而是以下产品约束：

- **分层目录**：Overview → Architecture → 子系统 → 具体实现，允许用户先宽后深。
- **每页相关源码**：内容旁边列出 Relevant source files，而不是把文件目录当正文。
- **文档后继续追问**：静态报告只是入口，用户可针对当前页面继续问具体问题。
- **可人工引导生成重点**：官方支持 `.devin/wiki.json`；维护者可通过 `repo_notes` 和 `pages` 指定重要目录、页面标题、用途和父子层级。提供 `pages` 后，会绕过默认聚类规划，保证大型仓库的重要部分不会被自动算法跳过。[配置说明](https://docs.devin.ai/work-with-devin/deepwiki#steering-deepwiki)

它没有解决好的问题也非常明确：

- 自动聚类不一定等于用户关心的产品功能。
- 自动说明可能把存在于仓库中的次要或历史机制误判成主机制。
- 生成内容可能过度解释琐碎实现，同时略过真正的技术权衡。
- 如果没有版本、证据强弱和漂移提示，用户容易把生成文档当成源码事实。

因此 DeepWiki 适合作为“Wiki 导航 + 追问”基准，不应作为“无需证据校验的真相生成器”。

### 2. PocketFlow Codebase Knowledge：把仓库转为有顺序的教程

[PocketFlow-Tutorial-Codebase-Knowledge](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge) 是本次最相关的开源生成流程。项目在调研日约 12.6k Stars，MIT 许可，支持 GitHub 或本地目录、文件过滤、输出语言和 LLM 缓存。

它已经实现的流水线来自其真实源码：

```text
FetchRepo
  → IdentifyAbstractions
  → AnalyzeRelationships
  → OrderChapters
  → WriteChapters (BatchNode)
  → CombineTutorial
```

证据：[`flow.py`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/main/flow.py)、[`nodes.py`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/main/nodes.py)、[`docs/design.md`](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/main/docs/design.md)。

各阶段的实际作用：

| 阶段 | 已实现能力 | 对当前产品的价值 |
|---|---|---|
| FetchRepo | 读取 GitHub / 本地仓库，按 include、exclude、大小过滤文件 | 可复用输入与过滤思路 |
| IdentifyAbstractions | 让 LLM 从全仓识别 5–10 个核心抽象，并绑定相关文件索引 | 把“文件索引”提升为“概念索引” |
| AnalyzeRelationships | 生成项目摘要与抽象之间的有向关系 | 形成可视化功能/机制地图 |
| OrderChapters | 按基础性、重要性、依赖关系安排教学顺序 | 避免按目录或入口顺序讲解 |
| WriteChapters | 为每个抽象批量写初学者友好的章节，并带入前文摘要 | 形成总—分—总的连续教程 |
| CombineTutorial | 输出总览、Mermaid 关系图、章节目录和独立章节 | 可借鉴文档装配协议 |

它的章节内容也体现了正确的人类教学顺序：先说“这个抽象解决什么问题”，再用类比建立心智模型，再讲它如何与其他抽象协作，最后给出简化源码和引用文件。例如其 [Browser Use 教程](https://the-pocket.github.io/PocketFlow-Tutorial-Codebase-Knowledge/Browser%20Use/01_agent.html) 先解释 Agent 的职责和用户场景，再下钻执行循环。

但是它不能原样作为生产级索引底座：

- `IdentifyAbstractions` 会把所选文件内容拼入一个大上下文，大仓库容易遇到上下文成本和重点稀释。
- 抽象与关系主要由 LLM 生成，虽然校验 YAML 结构和文件索引范围，但没有用 AST / 调用图验证关系真实性。
- 关系只绑定到文件索引，不是精确的符号、行号和可复现调用链。
- 输出主要是 Markdown 教程，不是面向技术选型的交互式单 HTML。
- 没有跨仓同功能比较、复用成本、成熟度与风险结论。

正确复用方式：保留六阶段“教学编排”，把其前面的仓库理解替换为本项目已有的确定性索引、符号证据和静态关系；把其后面的 Markdown 章节替换为决策型 HTML 模板。

### 3. CodeBoarding：静态分析先行，LLM 负责命名与解释

[CodeBoarding](https://github.com/CodeBoarding/CodeBoarding) 在调研日约 2.3k Stars，MIT 许可。官方描述和实现目标是把静态分析与 LLM 推理结合，产出分层架构图、组件文档和可导航页面，并支持全量、增量和单组件更新。

值得直接参考的机制：

- 使用语言服务器和控制流/调用关系构建结构事实。
- LLM 对静态结构做组件聚类、命名和叙述，不让 LLM 独立发明所有关系。
- 架构图从高层向组件递归下钻，而不是一张挤满节点的大图。
- 将组件文档持久化到 `.codeboarding/`，便于 IDE、CI 和文档共用。
- 支持 `full`、`incremental`、`partial --component-id`，把更新成本限制在受影响范围。

其 [HN 作者讨论](https://news.ycombinator.com/item?id=44737689) 也明确说明：LLM 单独处理大仓库会套用并不存在的熟悉架构，因此从控制流图开始，再用静态分析验证 LLM 结果。这个思路比单纯改 Prompt 更接近生产要求。

对本项目的意义：**静态分析决定“关系是否存在”，LLM 决定“这个关系如何向人解释”。**

### 4. RepoAgent：AST、双向调用关系与增量文档维护

[OpenBMB/RepoAgent](https://github.com/OpenBMB/RepoAgent) 在调研日约 1k Stars，Apache-2.0。它已经实现：Git 变更检测、AST 分析、对象级文档、对象间双向调用关系、增量替换 Markdown、多线程生成和 pre-commit 更新。

对当前产品最有价值的不是它的 GitBook 展示，而是：

- 文档单元与代码对象绑定。
- 先保存全局层级记录，再生成对象文档。
- Git 变更只触发相关文档更新。
- `repoagent diff` 可在更新前显示哪些文档会变化。

它适合借鉴“文档持续维护”与“代码变化影响文档”的机制；其输出仍偏对象级 API 文档，不足以单独回答“项目有哪些产品功能、这些功能为何值得复用”。

### 5. GitDiagram：严格图契约、路径校验和安全渲染

[GitDiagram](https://github.com/ahmedkhaleel2004/gitdiagram) 在调研日约 15.9k Stars，MIT 许可。它的生产生成链路非常值得照抄思想：

1. 获取默认分支、递归树和 README，先拒绝截断或超限输入。
2. 第一阶段生成白话架构解释。
3. 第二阶段生成有大小限制的严格 graph AST，而不是直接生成 Mermaid 字符串。
4. 校验 ID、连通性、数量限制和每条仓库路径；失败时带聚焦反馈重试。
5. 用确定性编译器把已验证 AST 转成 Mermaid。
6. 浏览器再次清洗输入、SVG 和链接白名单。
7. 保存成功产物与终态审计状态。

这个模式可用于现有 HTML 图：**LLM 输出结构化图模型，程序校验，程序渲染；不要让 LLM 直接拼任意 HTML / Mermaid 并相信它。**

### 6. OpenDeepWiki：自托管 Wiki 外壳，而非最优分析内核

[OpenDeepWiki](https://github.com/AIDotNet/OpenDeepWiki) 已实现本地/ZIP/Git 仓库输入、增量更新、Wiki 目录与正文分模型、中文/英文、聊天、Mermaid / Graphify 可视化、SQLite/PostgreSQL 与 Docker 部署。

它可以参考：

- 完整的本地部署与多用户 Wiki 产品外壳。
- 目录模型与正文模型分离，降低不同阶段的模型耦合。
- 多语言与并发生成配置。
- 文档、聊天、知识库共用一个 Web 产品。

但对“人类快速看懂并技术选型”而言，仍需额外加上功能优先、源码证据等级和跨仓比较层。它更像可部署容器，不是答案模板。

## 二、可直接复用或借鉴的 Skills

### 推荐级别一览

| Skill | 已实现输出 | 适合直接复用什么 | 明显缺口 | 许可/使用边界 |
|---|---|---|---|---|
| [`code-tour`](https://github.com/github/awesome-copilot/tree/main/skills/code-tour) | 面向 20 类角色的 `.tour`，精确链接文件/行号，带校验脚本 | persona、叙事步骤、真实路径/行号校验、下一导览 | 依赖 VS Code CodeTour；不是 HTML；默认仍从代码阅读路径出发 | `github/awesome-copilot` 为 MIT，可直接复用并改造成 HTML 导览 |
| [`codebase-memory-mcp`](https://github.com/github/awesome-copilot/tree/main/skills/codebase-memory-mcp) | 图支持的架构、符号、caller/callee、路径、影响分析 | 图仅作加速器、源码二次确认、索引覆盖检查、分页与漂移处理 | 本身不生成人类报告；依赖已配置 MCP | MIT；非常适合作为证据查询协议 |
| [`codebase-onboarding`](https://github.com/affaan-m/ECC/blob/main/skills/codebase-onboarding/SKILL.md) | Overview、技术栈、架构、目录、请求生命周期、约定、Where to Look | 两分钟可扫读、任务到目录映射、未知项显式标注 | 偏开发者入职；技术选型与功能复用较弱 | ECC 为 MIT；可复用结构，不应照搬入口优先顺序 |
| [`learn-codebase`](https://github.com/ktaletsk/learn-codebase) | 苏格拉底提问、预测、挑战、主动回忆、学习日志 | 作为“学懂这个模块”的可选交互模式 | 不适合作为首次自动报告；会增加用户阅读/回答成本 | MIT；适合二期教学模式 |
| 本地 `$gsd-map-codebase` | STACK、INTEGRATIONS、ARCHITECTURE、STRUCTURE、CONVENTIONS、TESTING、CONCERNS | 可直接作为后台事实草稿和质量维度输入 | 输出为规划文档，不是人类产品页；没有功能教学与跨仓技术选型 | 已安装本地 Skill；用于索引后台，不用于直接展示 |
| [`walkthrough`](https://github.com/alexanderop/walkthrough) | 单 HTML、5–12 个概念、可点 Mermaid、详情板、源码路径和短代码 | 两分钟心智模型、TL;DR、概念节点、点击下钻、代码片段 | 固定黑紫视觉；没有技术选型矩阵；仓库未声明 License | 可运行作参考；未澄清许可前，不应复制其代码/模板进可分发产品 |
| [`codebase-to-course`](https://github.com/zarazhangrui/codebase-to-course) | 4–6 模块课程、代码↔白话、动画、测验、术语提示 | 最符合“先说产品功能，再讲底层”的课程设计；交互模式丰富 | 生成目录而非真正单文件；过度面向零基础；强制互动可能拖慢技术选型 | 仓库未声明 License；只借鉴思想，复制资产前必须取得许可 |

### 最值得采用的 Skill 组合

#### A. 默认“技术选型报告”

```text
$gsd-map-codebase / 本地索引
  + codebase-memory-mcp 的证据规则
  + codebase-onboarding 的两分钟摘要
  + codebase-to-course 的产品优先教学顺序
  + walkthrough 的可点概念图
  + code-tour 的真实源码锚点与校验
```

默认页面不要启用测验或苏格拉底追问，因为用户的第一目标是快速判断“要不要参考这个项目”。

#### B. 用户选择某个模块后的“深度学习模式”

```text
功能卡片
  → 点击“学懂实现”
  → walkthrough 式交互图
  → code-tour 式逐步源码路径
  → learn-codebase 式预测 / 问答 / 主动回忆
```

#### C. Agent 使用的“模块复用 Skill”

当用户选择要复用的模块后，导出的 Skill 不应只是自然语言摘要，而应包含：

- 模块能力与非目标。
- 固定仓库、commit SHA、License。
- 核心文件、符号、入口与测试索引。
- 前置依赖与外部集成。
- 一条已验证的执行/数据流。
- 可复用的最小文件集合与必须重写的部分。
- 已知风险、平台假设和未证实项。
- 实现任务开始前必须重读的源码路径。

`codebase-memory-mcp` 的“图结论必须用源码片段确认”和 `code-tour` 的“所有路径/行号必须校验”应成为这个导出 Skill 的硬规则。

## 三、应该抄的不是样式，而是输出模板

### 页面 0：一屏决策结论

```text
[项目名] 是什么
一句人话：它解决谁的什么问题。

已确认功能：N 个
最值得复用：A / B / C
不建议直接复用：D（原因）
适合你的目标：高 / 中 / 低

如果只看 5 分钟：
1. 先看功能 A
2. 再比较功能 B 的两种底层方案
3. 最后看风险与许可证
```

这里不出现入口点数量，不先出现 `main.py`，不把“索引到多少符号”当作用户价值。

### 页面 1：功能地图

每个功能卡必须用同一结构：

| 字段 | 必须回答的问题 |
|---|---|
| 功能 | 用户能用它完成什么？ |
| 使用场景 | 在什么任务中会需要？ |
| 底层机制 | 它采用 VAD/ASR/LLM/TTS、事件循环、图执行、队列还是其他方案？ |
| 核心模块 | 哪个目录/包负责这个能力？ |
| 主流程 | 输入经过哪些组件得到输出？ |
| 源码证据 | 文件、符号、行号、调用/数据关系和测试是什么？ |
| 复用结论 | 直接复用、局部借鉴、只做对照还是不建议？ |
| 限制 | 哪些能力没有实现、没有运行验证或仅来自 README？ |

### 页面 2：单功能总—分—总

```text
结论：这个功能采用什么技术路线，为什么重要

1. 用户看到的行为
2. 实际执行流程图（5–9 个概念节点）
3. 每个节点做什么、为什么存在
4. 关键代码 ↔ 白话翻译
5. 失败、重试、状态和边界条件
6. 关键源码与测试

小结：哪些可以复用，哪些必须自己实现
```

“入口”只在第 6 节作为证据出现，除非入口本身就是项目提供给用户的公共 API。

### 页面 3：跨项目技术选型矩阵

这是现有教程型项目普遍缺少、但当前用户明确需要的页面：

| 功能 | 项目 | 技术路线 | 核心模块 | 本地/云 | 实时性 | 状态持久化 | 失败恢复 | 许可证 | 复用成本 | 证据等级 | 推荐 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 语音交互 | 项目 A | VAD→ASR→LLM→TTS | `voice/...` | 本地 | 流式 | 会话存储 | 可打断/重试 | MIT | 中 | 源码+测试 | 作为主参考 |
| 语音交互 | 项目 B | 全双工语音模型 | `audio/...` | 本地 | 双向流 | 未确认 | 未确认 | Apache-2.0 | 高 | README+源码候选 | 做对照 |

排序默认按“适合当前目标”而不是 Star。每个推荐必须说明权衡，不得只给分数。

### 页面 4：证据与可信度

建议统一四级：

| 等级 | 含义 | 页面措辞 |
|---|---|---|
| A | 源码调用链 + 测试/可运行验证 + 固定 commit | 已验证实现 |
| B | 源码符号与静态关系闭合，但未运行 | 源码确认，运行待验证 |
| C | README/文档声明且找到候选模块 | 项目声明，源码候选 |
| D | LLM 推断或社区转述 | 假设，不用于选型结论 |

每页固定展示：仓库 URL、commit SHA、生成时间、License、索引覆盖、未解析语言/文件、是否运行测试、文档是否可能漂移。

### 页面 5：人类导航

- 顶部提供三个模式：**先看结论 / 比较技术 / 查看源码**。
- 功能卡点击后打开同页详情，而不是把用户直接扔到 GitHub。
- 每段最多表达一个决定；大段源码默认折叠。
- 所有图支持点击、返回、前进和自主节奏；不自动播放。
- 移动端优先呈现结论卡和列表，图可横向缩放或切换为步骤视图。
- 专有名词第一次出现有一句话解释，完整术语表放页尾。
- 允许用户把“这个功能加入选型清单”，最后自动形成比较页。

## 四、社区真正反复提到的做法

### Hacker News：有效信号

1. **从用户场景、示例和测试进入，比从文件入口进入更容易形成心智模型。** 经典的 [How do you familiarize yourself with a new codebase](https://news.ycombinator.com/item?id=9784008) 讨论建议先看如何使用项目、示例和单元测试，再沿具体行为向下追踪；同时维护超链接术语表，并用小改动或调试验证假设。
2. **教程必须让读者控制节奏。** [Codeflow 讨论](https://news.ycombinator.com/item?id=22238821) 中的反馈明确反对自动播放：阅读代码时需要停顿、前进、后退；小屏幕还要自动把当前解释带入视口。
3. **DeepWiki 的价值与风险同时存在。** [DeepWiki 讨论](https://news.ycombinator.com/item?id=45002092) 中，有维护者把它用于引导志愿者熟悉复杂仓库，也有人报告它把次要构建配置误认为主构建系统、遗漏关键技术机制、内容冗长或过时。结论不是“不能用 LLM”，而是必须给生成内容版本、来源、优先级和验证状态。
4. **静态分析必须参与验证。** [CodeBoarding 讨论](https://news.ycombinator.com/item?id=44737689) 的作者把控制流图作为起点，再让 LLM 聚合与命名；这是应对大仓幻觉的直接工程手段。
5. **文档与源码要有可检查的双向关系。** [lat.md 讨论](https://news.ycombinator.com/item?id=47561496) 强调，散落 Markdown 的问题不是数量少，而是没有绑定到源码、重命名后无从发现漂移；其价值来自显式引用和自动完整性检查。讨论也提醒，不要让维护上下文的工作本身超过实际开发价值。

### X / Twitter：方向信号，不是实现证明

| 信号 | 社区表达的重点 | 对当前产品的启示 |
|---|---|---|
| [Alex Prompter 的 codebase discovery 模板](https://x.com/alex_prompter/status/2032067884248416516) | 先定义项目目的、技术栈、关键组件和三条用户旅程；文件直链、组件短代码和高层图 | 人类报告需要角色与任务导向；图要高层、文件要可点 |
| [Rohan Paul 介绍 OpenRepoWiki](https://x.com/rohanpaul_ai/status/1875912480658161854) | Wiki、文件结构、代码功能和直接跳转到引用代码块 | “结论 → 原代码”是基本交互，不是附加项 |
| [Cognition 的 Agent Trace 帖子](https://x.com/cognition/status/2017057457332506846) | 把代码行映射回生成它的上下文图 | 未来可记录“哪次 agent 调研/决策产生了哪个模块”；它是邻接能力，不是仓库教学本身 |
| [Nainsi Dwivedi 的项目结构帖](https://x.com/NainsiDwiv50980/status/2037922742364987630) | `why / map / rules / workflows`，短主说明 + 按需加载的模块文档 | HTML 首页同样应短，把深度内容延迟到用户点击后加载 |

[Agent Trace 官方规范](https://github.com/cursor/agent-trace) 已实现的是代码归因数据格式：记录版本控制 revision、文件、行范围、会话 URL、贡献者类型和内容哈希。它不负责解释仓库，但可以在本项目后续“项目追踪 → session → 产出代码”链路中补齐 provenance。

## 五、最佳实现建议：三层模型，而不是一份大报告

### 层 1：Repository Evidence Graph（机器事实层）

保存：

- 文件、符号、定义、引用、调用、继承、导入、配置和测试关系。
- 仓库、branch、commit、License 和索引时间。
- 每条边的提取器、证据位置和覆盖状态。
- Git diff 与受影响组件。

优先参考 CodeBoarding、RepoAgent、GitDiagram 和 `codebase-memory-mcp`。这一层不写漂亮结论，只负责可验证。

### 层 2：Capability & Mechanism Model（功能与技术机制层）

将源码事实聚合为：

```yaml
capability: 实时语音交互
user_outcome: 用户可以边说边获得可打断的语音回复
mechanism:
  pattern: vad_asr_llm_tts_pipeline
  variants:
    - full_duplex_speech_model
    - cascaded_streaming_pipeline
components:
  - vad
  - asr
  - dialogue_orchestrator
  - tts
evidence:
  - file: ...
    symbol: ...
    relation: calls
confidence: B
unknowns:
  - 是否支持真实打断
```

PocketFlow 的抽象识别与关系排序可作用于这一层，但每个抽象必须回填证据图，不能只接受 LLM 生成的关系。

### 层 3：Human Decision HTML（人类决策层）

同一份结构化数据生成三种视图：

- **了解项目**：功能地图与五分钟阅读路径。
- **技术选型**：同功能跨项目机制比较。
- **复用实现**：模块边界、文件索引、依赖、测试和导出 Skill。

教学互动不是首页默认负担，而是用户点击某个能力后的深度模式。

## 六、当前产品与参考方案的明确差距

| 缺口 | 为什么用户仍看不懂 | 应补的能力 | 主要参考 |
|---|---|---|---|
| 入口/符号优先 | 用户还不知道项目能做什么，入口没有决策意义 | 产品功能摘要与功能地图先于代码 | codebase-to-course、PocketFlow 教程 |
| 单仓平铺 | 无法判断同一功能哪种底层方案更适合 | 跨仓机制矩阵与推荐理由 | 本项目必须新增；现有参考都不完整 |
| LLM 叙述和源码证据混在一起 | 用户无法知道哪些是真的、哪些是推断 | A–D 证据等级、来源、commit、运行验证 | CodeBoarding、codebase-memory-mcp、GitDiagram |
| 图只是展示 | 节点不能成为阅读与选型入口 | 点击节点打开功能解释、代码和测试 | walkthrough、DeepWiki、GitDiagram |
| 文件列表没有“为什么” | 用户看见路径，仍不知复用价值 | 每个模块写用户价值、机制、边界、复用结论 | codebase-to-course、code-tour persona |
| 文档会漂移 | 一次生成后很快失真 | Git diff、局部重建、引用完整性检查 | RepoAgent、CodeBoarding、lat.md 信号 |
| 报告没有阅读任务 | 用户不知道先看什么 | 五分钟路径、角色模式、功能收藏清单 | codebase-onboarding、code-tour |
| 缺少学习闭环 | 看完不一定真的理解 | 可选预测、测验、主动回忆和学习日志 | learn-codebase |

## 七、技术选型与复用决策

### 可以直接采用

1. **`github/awesome-copilot` 的 `code-tour`**：采用 persona、步骤叙事、真实文件/行号校验；将 `.tour` 渲染思想改成现有单 HTML 的侧栏导览。
2. **`codebase-memory-mcp` 的证据协议**：图用于发现，源码用于确认；覆盖不全、分页未完成或索引陈旧时禁止做穷尽性结论。
3. **PocketFlow 的六段教程编排**：重写底层输入，让抽象与关系来自本项目证据模型，而不是全仓 Prompt。
4. **GitDiagram 的 graph AST → 校验 → 确定性 Mermaid 编译**：用于生产级交互图。
5. **RepoAgent / CodeBoarding 的增量更新思想**：Git diff 触发受影响功能和页面重建。

### 只借鉴设计，不复制实现

1. **`codebase-to-course`**：产品优先、课程弧线、代码↔白话和交互方式非常适合；但仓库没有明确 License。
2. **`walkthrough`**：两分钟 TL;DR、5–12 个概念、点击图和详情板很适合；但仓库没有明确 License。
3. **DeepWiki 页面组织**：可作为 UX 基准，但核心实现不是开源复用合同。

### 不建议作为单独底座

- 只使用 PocketFlow：教学顺序好，但证据与大仓可扩展性不足。
- 只使用 DeepWiki/OpenDeepWiki：Wiki 完整，但无法保证功能优先和技术选型视角。
- 只使用 CodeBoarding：图与证据强，但人类教学、产品功能和跨项目比较不足。
- 只使用 CodeTour：源码路径精确，但需要用户已经知道想学哪个功能。
- 只生成 README/Markdown：没有交互层级、比较工作台和阅读路径，仍会回到“平铺只叙”。

## 八、验收标准：什么叫“人能直接看懂”

下一版 HTML 至少满足以下可测试条件：

1. 打开后第一屏直接说出项目的 3–7 个主要功能，不出现“先看入口”。
2. 用户在 30 秒内能回答：这个项目做什么、最值得看什么、不适合什么。
3. 每个功能都能看到一个明确的底层技术路线，而不是只有文件名。
4. 每个技术路线都至少有一条可点击、固定 commit 的源码证据。
5. 页面清楚区分“运行验证、静态确认、项目声明、模型推断”。
6. 用户可以把两个不同项目的同一功能放进同一个比较表。
7. 比较表能给出推荐与理由，而不是只列参数。
8. 用户点击某个功能后，能在不离开页面的情况下看到流程图、模块、代码白话和测试。
9. 所有文件、行号、锚点与图链接有自动校验。
10. Git 版本变化后能标记页面过时，并只重建受影响部分。
11. 1440px 与手机宽度下，结论和功能列表都优先可读；图不会成为唯一导航方式。
12. 没有 License 的参考资产不进入产品代码。

## 九、建议的近期实施顺序

1. **先改生成数据契约**：从 `Feature/Entrypoint` 主模型升级为 `Capability → Mechanism → Component → Evidence`。
2. **再改 HTML 信息架构**：实现“结论 / 技术比较 / 源码证据”三种视图，功能卡排第一。
3. **接入确定性关系**：调用/依赖/测试关系必须来自现有索引或静态分析，LLM 只做聚类与解释。
4. **增加跨仓比较集合**：用户选择能力后，把各项目相同机制聚合到一个选型表。
5. **增加增量与漂移**：页面记录 commit，Git diff 后标记并局部刷新。
6. **最后增加教学模式**：交互图、代码↔白话、CodeTour 式步骤与可选的主动回忆。

## 十、2026-08-10 扩展检索：新增 GitHub / X 候选

这一轮不是按 Star 直接选底座，而是分别核对了项目定位、源码结构、许可证、更新状态，以及 X 上的正反使用信号。Star 和浏览量只表示关注度，不表示代码质量或结论可靠。

### 10.1 新增高价值候选

| 项目 / Skill | 2026-08-10 快照 | 真正值得参考的部分 | 许可证与采用结论 |
|---|---:|---|---|
| [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) | 1,532 Star；最近更新 2026-08-08 | 动态层级分解；leaf-first 生成；父页面读取子页面再综合；变更向父级级联失效；模块树覆盖缺口 | 仓库根目录没有许可证。**只借鉴算法与产物合同，不复制实现或模板。** |
| [abhigyanpatwari/GitNexus](https://github.com/abhigyanpatwari/GitNexus) | 45,220 Star；最近更新 2026-08-09 | `query/context/impact/trace` 四类图查询；process/cluster 资源；inline staleness；改代码前先算 blast radius | PolyForm Noncommercial 1.0.0。**生产商业项目只作行为基准和协议参考，不复制代码。** |
| [codegraph-ai/CodeGraph](https://github.com/codegraph-ai/CodeGraph) | 55 Star；最近更新 2026-08-10 | Rust 多语言解析层、结构图、MCP 工具和 IDE 下钻；适合作为低 Star 但工程完整的语义图候选 | Apache-2.0。**可以做图后端 PoC，但它不负责把图讲成人类功能或技术选型。** |
| [zarazhangrui/codebase-to-course](https://github.com/zarazhangrui/codebase-to-course) | 5,358 Star | 从用户动作开始；4–6 模块课程弧线；code ↔ English；预抽取 module brief；最后才进入代码 | 无许可证。**只采用信息架构和教学原则，不复制 CSS、JS、模板或 Skill 内容。** |
| [ktaletsk/learn-codebase](https://github.com/ktaletsk/learn-codebase) | 39 Star；MIT | 预测后揭示、主动回忆、分级提示、学习日志、间隔复习 | MIT。**适合做“阅读报告后的可选教学 Skill”，不应阻塞默认技术选型页。** |
| [github/awesome-copilot](https://github.com/github/awesome-copilot) | 37,621 Star；MIT | `code-tour`、`acquire-codebase-knowledge`、`codebase-memory-mcp` 的路径核验、地图和证据协议 | 可采用，但上游质量报告指出 `code-tour` 过长、`acquire-codebase-knowledge` 引用层级不合规。**拆成聚焦 Skill，不原样照搬。** |
| [oraios/serena](https://github.com/oraios/serena) | MIT；最新版完整 clone HEAD `946ad9817875` | live LSP 的 symbol overview、find symbol/reference/declaration/implementation、diagnostics、rename 与 symbol body edit；给 Codex/OpenCode 等客户端提供 MCP 工具 | **作为在线语义操作专项层采用。** 不替代持久调用图、功能教学、工作流编排或执行沙箱；付费 JetBrains 后端能力必须和开源 LSP 能力分开。 |

五个新增完整 clone 已放在本地：

- `/Volumes/T7/workspace/ontology/graph/repo/codewiki`
- `/Volumes/T7/workspace/ontology/graph/repo/gitnexus`
- `/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai`
- `/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course`
- `/Volumes/T7/workspace/ontology/graph/repo/learn-codebase`
- `/Volumes/T7/workspace/ontology/graph/repo/serena`

全部为 non-shallow、工作树 clean 的完整 Git clone。它们是补充研究语料，不自动进入原六仓 curated 排名。

### 10.2 X / Twitter 社区信号：需求很强，但必须防止“图带来的假确定性”

正向信号：

- [Karpathy 关于 DeepWiki 的长文](https://x.com/karpathy/status/2021633574089416993)把价值从“读文档”推进到让软件更可塑：先通过 Wiki 理解系统，再讨论修改。这支持首页先讲产品能力和架构，而不是先列文件。
- [`codebase-to-course` 的社区展示](https://x.com/GitHub_Daily/status/2067185499530473731)强调单文件离线课程、代码白话和交互教学；它验证了“人看得懂”是独立产品目标，不只是报告样式。
- [GitNexus 的社区介绍](https://x.com/AiwithYasir/status/2047589529650176333)把依赖、调用链和执行流视为 Agent 的结构上下文；这支持我们的 `Mechanism → Component → Evidence` 下钻。
- [learn-codebase 的发布说明](https://x.com/ricardodantas/status/2085982091477389525)强调生成 `CODEBASE_OVERVIEW.md` 和真实 build/run/test 命令；这支持把报告结果持久化为后续会话可复用的上下文。
- [Wiki Memory 讨论](https://x.com/hwchase17/status/2071963622298050997)及其[人工审核补充](https://x.com/hwchase17/status/2072019041418682699)表明 Wiki 也可以成为长期 Agent memory，但写入应有人审或至少有来源与新鲜度门禁。

反向信号：

- [一条多工具审查实测](https://x.com/RNR_0/status/2077518628388327529)指出 GitNexus、graphify 类工具和 codebase-memory 的高置信回答可能把审查 Agent 引离真正的问题。它不是系统性 benchmark，但明确提醒：**图只能缩小阅读范围，不能替代源码重证、行为测试和反例搜索。**
- X 上围绕 CodeWiki、DeepWiki 的高互动帖子大量使用“自动理解整个仓库”之类营销措辞。它们可以证明需求，不足以证明事实准确率；最终采用必须回到固定 commit、源码范围、关系端点和验证结果。

因此当前产品的证据等级不能只是视觉徽章，而必须约束页面措辞：

1. 图发现的能力先标 C（候选）；
2. 绑定源码、符号和关系后升到 B（静态确认）；
3. 有行为级测试或真实运行证据才升到 A；
4. 任一索引过期、证据缺失或关系悬空时自动降级，禁止继续显示“推荐复用”。

### 10.3 对当前产品的新增采用决策

1. **首页与单仓报告**采用 CodeWiki 的层级思想，但层级对象改成产品 Capability，而不是目录；每个父能力只能综合有闭包的子能力证据。
2. **功能详情**采用 codebase-to-course 的“为什么关心 → 用户动作 → 角色 → 数据流 → 失败 → 代码白话”，但所有内容由本项目结构化证据生成，不复制其无许可证模板。
3. **技术选型**采用 GitNexus 的 impact/process/staleness 思想：每个候选不仅列实现机制，还列变更影响、索引新鲜度和不能证明的部分。
4. **图后端 PoC**新增 CodeGraph 候选，与现有 CodeBoarding / SourceBridge 做语言覆盖、关系精度、增量和资源成本对比。
5. **可选学习模式**直接参考 MIT 的 learn-codebase：报告读完后才进入预测、测验和学习日志；默认报告不强迫用户上课。
6. **Skill 拆分**遵循 awesome-copilot 质量反馈：拆成 `repo-capability-map`、`repo-implementation-tour`、`repo-tech-selection` 三个短 Skill，核心 `SKILL.md` 只保留顺序与门禁，详细格式放一层 references。
7. **代码智能分层**增加 Serena：持久索引负责离线事实、影响图和新鲜度；Serena 只在用户或 Agent 选定功能后提供 live symbol/reference/diagnostics/refactor。它的 `trusted project` 不是隔离边界，shell 与语言服务器仍应运行在受控 worktree 或容器中。

## 证据索引

### 官方 / 上游

- [DeepWiki 官方文档](https://docs.devin.ai/work-with-devin/deepwiki)
- [PocketFlow Codebase Knowledge](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge)
- [PocketFlow 生成流程源码](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/main/flow.py)
- [PocketFlow 节点实现](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/main/nodes.py)
- [CodeBoarding](https://github.com/CodeBoarding/CodeBoarding)
- [RepoAgent](https://github.com/OpenBMB/RepoAgent)
- [GitDiagram](https://github.com/ahmedkhaleel2004/gitdiagram)
- [OpenDeepWiki](https://github.com/AIDotNet/OpenDeepWiki)
- [GitHub Awesome Copilot：Code Tour](https://github.com/github/awesome-copilot/tree/main/skills/code-tour)
- [GitHub Awesome Copilot：Codebase Memory MCP](https://github.com/github/awesome-copilot/tree/main/skills/codebase-memory-mcp)
- [Walkthrough Skill](https://github.com/alexanderop/walkthrough)
- [Codebase-to-Course Skill](https://github.com/zarazhangrui/codebase-to-course)
- [Learn Codebase Skill](https://github.com/ktaletsk/learn-codebase)
- [ECC Codebase Onboarding Skill](https://github.com/affaan-m/ECC/blob/main/skills/codebase-onboarding/SKILL.md)
- [Agent Trace 规范](https://github.com/cursor/agent-trace)
- [CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki)
- [GitNexus](https://github.com/abhigyanpatwari/GitNexus)
- [CodeGraph](https://github.com/codegraph-ai/CodeGraph)
- [GitHub Awesome Copilot Skill 质量报告](https://github.com/github/awesome-copilot/discussions/1913)
- [Serena](https://github.com/oraios/serena)

### 社区反馈

- [HN：如何熟悉陌生代码库](https://news.ycombinator.com/item?id=9784008)
- [HN：DeepWiki 评价与错误案例](https://news.ycombinator.com/item?id=45002092)
- [HN：Codeflow 教学交互反馈](https://news.ycombinator.com/item?id=22238821)
- [HN：CodeBoarding 静态分析 + LLM](https://news.ycombinator.com/item?id=44737689)
- [HN：lat.md 与文档漂移](https://news.ycombinator.com/item?id=47561496)
- [X：Codebase discovery / onboarding 模板](https://x.com/alex_prompter/status/2032067884248416516)
- [X：OpenRepoWiki 介绍](https://x.com/rohanpaul_ai/status/1875912480658161854)
- [X：Cognition Agent Trace](https://x.com/cognition/status/2017057457332506846)
- [X：why / map / rules / workflows](https://x.com/NainsiDwiv50980/status/2037922742364987630)
- [X：Karpathy 谈 DeepWiki](https://x.com/karpathy/status/2021633574089416993)
- [X：codebase-to-course 社区展示](https://x.com/GitHub_Daily/status/2067185499530473731)
- [X：GitNexus 社区展示](https://x.com/AiwithYasir/status/2047589529650176333)
- [X：图/记忆工具高置信误导的反例](https://x.com/RNR_0/status/2077518628388327529)
- [X：Wiki Memory](https://x.com/hwchase17/status/2071963622298050997)
- [X：Wiki Memory 人工审核](https://x.com/hwchase17/status/2072019041418682699)
