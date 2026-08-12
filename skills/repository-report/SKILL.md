---
name: repository-report
description: 纯 Skill 仓库讲解流水线。由当前 Codex、Claude Code 或 OpenCode agent 本体读取源码与 CodeGraph，顺序产出面向技术选型的项目定位、完整业务功能、逐功能底层运行解释、工程结构 Markdown 和单文件 HTML；功能数量不限，不调用 RepoLens 产品程序或辅助脚本。
---

# 仓库业务讲解器

直接用当前 Coding CLI agent 本体执行。不得调用 RepoLens 产品程序、CLI、渲染器、辅助脚本或旧 inventory/report 流水线；不得把本 Skill 包装成另一个程序的入口。

## 输入

从用户请求取得：

- `SOURCE`：源码仓库绝对路径；
- `OUTPUT`：输出目录绝对路径；
- `STAGE`：默认 `all`，也可停在 `context`、`project`、`capabilities`、`implementation`、`engineering` 或 `render`。

缺少 `OUTPUT` 时，在 `SOURCE` 的父目录创建 `{repository-name}-system-explainer/`。不要写入上游源码仓库。

## 固定顺序

完整读取 [pipeline.md](references/pipeline.md)，严格顺序执行：

1. 固定源码身份并探索项目，写 `stages/00-context.md`。
2. 写项目定位、核心概念和真实用户旅程到 `stages/01-project.md`。
3. 写不限数量的核心业务功能和覆盖账本到 `stages/02-capabilities.md`。
4. 对每个已选功能查询 CodeGraph 或等价符号/调用关系，写一份 `.evidence.md` 与一份融合讲解 `.md`。
5. 写前后端、进程、Worker、数据与部署的 `stages/04-engineering.md`。
6. 按“项目 → 架构总览 → 功能及其底层运行 → 工程地图 → 证据边界”组装 `stages/05-report.md`，再直接写单文件 `index.html`。

每完成一个阶段就写产物并汇报耗时。阶段产物存在且源码身份未变化时先验证后复用。没有语义审校循环、自动返修循环或固定重试次数；失败时保留已完成阶段并报告准确原因。

## 功能识别

业务功能必须来自五路并集：产品声明、用户旅程、一等业务对象、真实用户动作、运行/Worker/外部集成。CodeGraph 证明实现，不决定业务功能。

功能数量不设上限。标题必须是用户能理解的动作与结果；health、登录壳、普通 CRUD、路由注册、通用 UI、测试、example 和部署 helper 只能合并或排除，不能独立升级为核心功能。

`02-capabilities.md` 必须用 `[纳入]`、`[合并]`、`[排除]`、`[待核验]` 处置所有产品声明、旅程、业务对象、运行表面和主要工程模块。缺任何一类就停止，不能开始写功能章节。

## 每个功能怎么写

完整读取 [chapter.md](references/chapter.md)。每个功能把业务作用和底层实现写在同一章，第一句必须是：

> 简单来说，这个功能就是……

随后依次讲：用户看到什么、一次完整运行、组件分工、系统如何得到结果、状态/存储/查询/循环/路由/并发/Worker、失败边界、设计取舍、源码证据。涉及 Voice 时必须讲清采集 → VAD → ASR → LLM/Tool → TTS → 文本/音频回传与打断。

“底层如何执行”必须先用自然语言解释：每一步收到什么、做了什么、为什么这样做、把什么交给谁、最终得到什么。函数名、类名、文件路径和符号调用链只能放在解释之后作为证据，不能用 `A() → B() → C()` 冒充面向人的机制说明。

图必须是当前功能的真实组件交互，不能只是四格文字卡。Mermaid 节点使用短 ID 和带引号标签；代码路径、函数名与特殊字符只放标签，不作节点 ID。密集图改为 `flowchart TD`，并拆成主链与异常链。

## HTML

完整读取 [html.md](references/html.md)。直接把最终 Markdown 内容写进自包含 HTML；仅 Mermaid 运行库允许 CDN。必须有固定侧边栏章节导航，正文 15px，每个功能章就地包含交互图、文字解释、组件表和源码证据。不要先列一遍功能、后面再重复一遍实现。

## 完成门

在汇报完成前逐项检查：

- 非技术读者能用一句话说出项目是什么；
- 核心业务功能没有数量上限且覆盖账本闭合；
- 每个功能和对应底层运行在同一章节；
- 每张 Mermaid 都实际渲染，无 `Syntax error in text`；
- 侧边栏可跳转，源码证据路径存在；
- 输出包含阶段 Markdown、`index.html` 和 `performance.md`；
- Skill 执行过程没有调用 RepoLens 产品程序、CLI、渲染器或辅助脚本；CodeGraph 只负责源码关系取证，当前 agent 本体负责全部归纳、写作和 HTML 组装。

最终返回所有产物的绝对路径、功能数、各阶段耗时、复用项和待核验项。
