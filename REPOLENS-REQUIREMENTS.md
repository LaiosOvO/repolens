# RepoLens（仓库能力透镜）产品需求与工程交接

> 文档状态：可执行交接规格  
> 面向读者：在另一台电脑上接手实现与验证的工程 Agent  
> 读完后的动作：继续完成 RepoLens，并只用 Pipecat 验证第一版报告质量

## 1. 项目是什么

RepoLens 是一个面向技术选型的通用代码仓库理解系统。

它接收任意本地代码仓库，先建立确定性的代码图，再由大模型把代码关系归纳成面向人的业务能力或框架能力，最后生成以 `index.html` 为主的结构化项目报告。

它不是 API 清单、文件树浏览器、入口调用链查看器，也不是自动替用户做最终技术选型的打分器。

用户先分别阅读不同项目的报告，理解每个项目：

1. 是什么产品或框架；
2. 对外提供哪些主要能力；
3. 每项能力如何跨模块运行；
4. 底层采用什么数据结构、控制结构和技术机制；
5. 真正的实现难点、边界和代价是什么；
6. 哪些实现值得借鉴，哪些不能直接照搬。

用户在理解这些项目之后，再自行决定“某个功能参考哪个项目”。

## 2. 核心用户需求

### 2.1 首要目标

对每个代码仓库生成一份第一次阅读就能看懂的项目介绍报告，让技术决策者快速了解项目功能及实现方式。

### 2.2 核心阅读顺序

报告必须遵循以下顺序，不能从 `main`、路由、类或文件开始讲：

1. 这是什么项目；
2. 它服务谁，解决什么问题；
3. 最核心的产品主轴是什么；
4. 用户可以完成哪些对外业务或框架动作；
5. 每项功能由哪些模块共同实现；
6. 一次真实运行如何从触发走到结果；
7. 底层机制、状态变化、难点和失败方式；
8. 最后才提供源码、符号和关系证据下钻。

### 2.3 功能必须是对外能力

一级功能必须对应用户或框架使用者能感知的结果。

不能把以下内容直接当作一级功能：

- `GET /healthz`、ready、metrics 等运维探针；
- 静态首页和文档页；
- 单个 HTTP 路由、RPC handler、CLI 入口；
- 通用 UI primitive、Toast、Theme、Context；
- 构建、发布、迁移和测试脚本；
- fixture、smoke test；
- example、demo、sample 场景；
- 某个文件夹、类或函数。

这些内容可以作为工程支撑、实现模块或使用示例出现，但不能与核心产品能力并列。

### 2.4 示例的正确位置

example、demo 和 sample 不能成为项目核心功能。

它们只能放在某项真实能力下面，作为：

- 组合使用示例；
- 已有场景；
- 接入方式；
- 测试或验证证据。

例如，Pipecat 的 food ordering、voicemail、RAG 或 provider 示例不能各自成为一级功能；它们应证明实时媒体管线、工具调用、上下文管理或 provider 适配怎样被组合使用。

## 3. 报告信息架构

每个仓库至少输出：

- `index.html`：主要人类阅读入口；
- `index.json`：机器可读完整产物；
- `capability-graph.json`：代码图与能力图；
- `manifest.json` 或等价 generation manifest：产物哈希与版本闭包；
- 可选的模块报告、对比报告、Skill 导出和审计记录。

### 3.1 第 0 章：一句话说明这是什么项目

第一句话必须包含：

- 项目类型；
- 主要用户；
- 用户最终获得的结果。

例如：

> Pipecat 是给开发者构建实时语音和多模态 Agent 的流式处理框架；它把媒体传输、轮次检测、模型服务和处理器组织成可运行的帧管线。

不能写：

> 这是一个包含多个模块、入口和服务的系统。

### 3.2 第 1 章：产品主轴与端到端旅程

报告先给 1–4 条产品主轴，而不是十几个平级小卡片。

平台型项目应优先展示完整用户旅程。例如：

`提交任务 → 持久化/排队 → 调度或租约 → Worker 执行 → 事件与结果回传`

实时语音平台应优先展示：

`接入通话 → 媒体传输 → 轮次/VAD → STT 或语音模型 → Agent/工具 → TTS → 播放与打断`

### 3.3 第 2 章：整体架构与工程组织

必须说明：

- 仓库是单包、monorepo、多服务还是混合形态；
- 更接近 DDD、分层、模块化单体、端到端 feature slice、插件式、事件驱动、控制面/数据面还是混合架构；
- 为什么这样判断，不能只贴标签；
- 前端、后端、Worker、媒体层、共享协议和数据层怎样组织；
- 主要目录分别封装什么；
- 依赖方向和边界；
- 模块之间通过函数调用、消息、队列、事件、网络协议还是共享状态交接。

### 3.4 第 3 章：核心功能地图

功能必须按重要性排序：

1. 核心用户旅程和项目差异化能力；
2. 核心能力直接依赖的业务能力；
3. 接入、配置和管理能力；
4. 工程支撑能力折叠展示。

不得限制为固定 10 项。功能数量由源码证据和独立用户结果决定。

### 3.5 每个功能章节的总—分—总合同

每项功能必须按以下结构生成。

#### 第一行：一句话讲本质

第一句话必须直接说明真实构造和主数据流。

示例：

- `Agent Loop 本质是一个带终止条件的循环：每轮把消息交给模型，遇到工具调用就执行并把结果写回下一轮，否则返回最终文本。`
- `Voice 本质是 PCM 采集 → 语音边界判断 → ASR/实时语音模型 → Agent → TTS → 播放的媒体 pipeline。`
- `Graph Workflow 本质是一个由节点和边组成的内存执行图：依赖满足的节点进入 ready 集合，同一波并发执行，结果合并后再由 router 选择下一跳。`

不能先讲背景、价值或入口。

#### 中间：详细实现

必须回答：

- 谁触发；
- 谁负责；
- 输入是什么；
- 中间状态在哪里；
- 哪一步改变了什么状态；
- 输出是什么；
- 谁消费输出；
- 何时继续、分支、等待、重试或结束。

#### 结尾：复用判断

必须回答：

- 可直接借鉴什么；
- 需要改造什么；
- 不要照搬什么；
- 迁移前必须验证什么。

### 3.6 功能与模块的双向映射

模块视角必须保留，但不能取代业务功能视角。

每项功能必须列出：

- 核心模块；
- 支撑模块；
- 每个模块的职责；
- 模块之间交接的数据或控制权；
- 跨模块调用和状态流。

关系是多对多：

- 一个功能可以跨多个模块；
- 一个模块可以支撑多个功能；
- 未被核心功能使用的模块进入“工程支撑模块”，不能自动成为功能。

点击模块后，应能看到它包含的关键文件、符号、入边、出边、关联测试和它参与的功能。

## 4. 机制讲解的最低要求

### 4.1 存储与查询

只要功能涉及存储或查询，就必须说明：

- 事实源在哪里；
- 原始事件、派生事实、episode、索引和缓存怎样区分；
- 写入何时提交；
- 失败是否回滚；
- 查询是否经过 gate；
- 如何 filter、recall、rank、Top-K、merge、deduplicate；
- 没有独立存储或检索层时明确写“没有”。

### 4.2 Agent Loop

必须明确：

- 它是否真的是循环；
- 具体是 `for`、`while`、事件循环还是递归；
- 一轮读取什么；
- 模型结果怎样决定直接返回或调用工具；
- 工具结果怎样写回下一轮；
- `continue`、`break`、`return`、最大轮数和异常分别怎样终止。

### 4.3 Graph / Workflow

必须明确：

- 节点、边和 router 在何时构建；
- 图是静态定义、运行前动态生成，还是运行中可变；
- 节点何时进入 ready；
- wave 的含义；
- 并发的最小单位；
- barrier 等待什么；
- 多节点结果怎样合并；
- 状态冲突怎样处理；
- router 读取哪份状态；
- router 输出 label、目标节点还是下一步命令；
- router 只选路还是也执行工作；
- 没有 ready 节点时怎样结束；
- 运行中修改拓扑是否安全。

### 4.4 Voice / 实时媒体

必须明确：

- PCM 或媒体帧从哪里采集；
- VAD、turn detection 或其他边界如何切段；
- ASR、LLM/Agent、TTS 的先后关系；
- 阶段之间传完整缓冲还是增量流；
- 播放时是否仍监听；
- 是否支持打断；
- 是串行、半双工还是真全双工；
- 背压、取消和错误在哪层处理；
- 视频的采集、信令、房间、P2P/SFU/服务端中转和渲染链。

仅写“连接 STT/LLM/TTS”不合格。

### 4.5 Router / Dispatcher

必须明确输入、规则、输出、调用时机和消费者，并区分：

- 选择下一步；
- 执行下一步。

仅写“Router 决定路由”不合格。

### 4.6 并发

必须解释为什么任务彼此独立才可以并发，以及：

- 使用 `gather`、线程池、任务队列还是其他构造；
- 等待点在哪里；
- 共享状态何时可见；
- 结果合并顺序；
- 冲突处理；
- 失败和取消如何传播。

## 5. 技术路线决策

### 5.1 交付形态：CLI 为核心，Skill 为语义层，本地网页为操作面

RepoLens 不应只做成 Skill，也不应只做成网页。

最终形态：

- **CLI 核心**：负责扫描、解析、代码图、缓存、验证、原子发布和批处理；
- **Skill / Prompt 合同**：负责业务功能归纳、叙事组织、难点识别和机制讲解；
- **本地网页 UI**：负责填写参数、选择模型、查看日志和进度；
- **HTML 报告**：主要阅读产物。

理由：

- 纯 Skill 无法可靠承担长任务、增量缓存、原子发布和产物验证；
- 纯静态代码无法可靠判断“什么是用户功能”；
- 纯正则会把路由、入口、example 和 helper 误当功能；
- CLI + 代码图 + 受证据约束的大模型最适合这个任务。

### 5.2 功能识别流程

正确流程必须是：

1. 确定性扫描仓库；
2. 用 AST、语言服务或解析器建立文件、符号、调用、包含、导入和模块依赖；
3. 构建整仓 CodeGraph；
4. 从图中生成候选能力、机制簇、组件、模块视图和证据切片；
5. 只进行一次整仓业务能力判断；
6. 固定最终 capability ID 和排序；
7. 按已确定的 capability 并发生成详细章节；
8. 校验证据、路径、行号、模块归属和产物闭包；
9. 原子发布 HTML/JSON。

禁止流程：

`每个模块分别调用模型 → 每个模块各自猜功能 → 再合并`

原因：它既慢，又会把模块边界错误地提升成产品功能边界。

### 5.3 模块的正确作用

模块用于：

- 帮助整仓功能判断；
- 解释工程组织；
- 展示功能如何跨模块实现；
- 控制功能确定后的章节证据包大小；
- 支持模块下钻和影响分析。

模块不用于独立发明功能。

### 5.4 禁止用正则识别功能

功能识别不能以路由名、文件名或关键字正则作为事实来源。

允许的确定性基础：

- AST；
- Tree-sitter；
- LSP / gopls / tsserver 等语言服务；
- 构建工具元数据；
- CodeGraph 关系；
- Git 版本与变更；
- 测试和源码证据。

大模型负责语义归纳，但每个结论必须回到确定性证据。

## 6. 性能与并发要求

### 6.1 全局功能判断

- 每个仓库只允许一次全局功能判断模型调用；
- 输入是压缩后的整仓图拓扑、模块视图、产品定位和代表性源码证据；
- 目标包体应小于 600KB；
- 不把完整源码或全部关系直接塞进模型；
- 功能判断不能按 32 个模块分片调用模型。

### 6.2 章节生成

- 只有 capability 列表固定后才并发；
- 每批 2–4 个 capability；
- 默认并发 2，可配置；
- 每批只接收该 capability 的模块、源码和证据闭包；
- 失败批次可单独重试并复用其他缓存。

### 6.3 进度日志

CLI 和 UI 都必须显示：

- 当前阶段；
- 已扫描文件数、符号数、关系数和模块数；
- 全局功能判断耗时；
- 已识别功能数；
- 章节批次 `完成数/总数`；
- 当前模型与 provider；
- 缓存命中；
- 验证状态；
- 最终输出路径。

不得长时间只显示“运行中”。至少每 30 秒输出心跳。

## 7. CLI 与本地界面

### 7.1 CLI 必须支持

```text
repolens report <repository> --output <directory> --provider <provider>
repolens index <repository> --output <directory>
repolens graph <index> --query <symbol-or-capability>
repolens explain <repository> <capability-or-module>
repolens compare <report-a> <report-b> ...
repolens validate <index-or-report> --source <repository>
repolens ui
```

现有包名和命令可以暂时保留 `repo-teacher`，产品名称统一展示为 RepoLens；后续再做兼容重命名。

### 7.2 本地 UI 参数

界面必须可以填写：

- 仓库路径；
- HTML 输出目录；
- 报告名称；
- provider：Codex、OpenCode、DeepSeek；
- OpenCode 后端模型；
- DeepSeek Flash 或 Pro；
- 模型超时；
- 章节并发数；
- 是否打开报告。

界面必须展示实时日志、阶段进度、错误和最终报告链接。

### 7.3 密钥安全

- API key 只能通过密码输入框、进程环境变量或系统钥匙串传入；
- 不写入源码、HTML、JSON、日志、缓存或 Git；
- 不在文档中保存真实 key；
- 子进程结束后不持久化 key；
- 输出前扫描常见 token 和 credential 形态。

## 8. 证据与质量门

每项 capability 至少需要：

- 3 个源码引用；
- 至少 1 个非 README/docs/spec 的实现证据；
- canonical feature ID；
- canonical evidence ID；
- 真实仓库相对路径；
- 有效起止行；
- 至少一个核心模块；
- 模块职责与交接说明。

质量等级：

- **A**：语言语义关系、源码、测试和运行证据闭合；
- **B**：源码与静态关系闭合；
- **C**：合理推断，必须明确标注；
- **D**：仅文档或名称导航，不得提升为已实现功能。

任何以下情况必须 fail closed：

- 引用不存在的路径或行；
- 引用未知 evidence ID；
- 把 relationship ID 当 evidence ID；
- 模型越出允许源码范围；
- 把示例或探针提升为核心功能；
- 产物跨 generation 混合；
- 源码在分析中途变化；
- 模型缓存与分析指纹不匹配。

## 9. HTML 可读性要求

- 首屏先回答“这是什么项目”；
- 核心产品主轴在首屏可见；
- 核心功能优先，支撑能力默认折叠；
- 每项功能第一句是本质总结；
- 长解释分层折叠，不铺满同级卡片；
- 运行链优先用步骤、状态表或小图；
- 模块关系优先用模块图或映射表；
- 源码证据放章节后部；
- 点击源码后必须提供返回报告的方式；
- 桌面与移动端都不能出现页面级横向溢出；
- 无外部运行时依赖，`file://` 可直接打开；
- 所有本地链接和 fragment 必须可验证。

## 10. 技术选型的使用方式

第一阶段不是自动给项目排名。

正确方式：

1. 每个项目生成独立介绍报告；
2. 用户阅读各项目的核心功能和实现；
3. 用户选择感兴趣的功能；
4. 系统再生成跨项目机制对比；
5. 对比每个项目的底层技术、状态模型、扩展点、代价和适用边界；
6. 最后由用户做技术选型。

跨项目对比必须能回答：

- 同一功能分别由什么机制实现；
- 哪个项目适合直接借鉴；
- 哪个项目只适合参考思路；
- 哪些模块可以迁移；
- 哪些许可、运行时和基础设施限制需要考虑。

## 11. 参考项目与采用结论

### DeepWiki / DeepWiki-Open

采用：层级 Wiki、项目总览到章节下钻、引用回源码。  
不采用：把 Wiki 页面结构直接当成功能真相。

### PocketFlow Code2Tutorial

采用：先心智模型、再依赖顺序、再教程章节的教学编排。  
不采用：只围绕单一路径写故事而忽略整仓覆盖。

### CodeBoarding

采用：代码图、模块/调用关系、架构图和源码下钻。  
不采用：把代码结构图本身当成人类功能目录。

### CodeGraph / GitNexus

采用：整仓符号关系、调用链、组件和影响分析，作为功能判断前置事实层。  
不采用：只按中心度或目录名自动命名产品功能。

### SourceBridge

采用：claim 级证据、精确源码位置和结构化技术比较。  
不采用：未经验证的描述或只靠文件上下文的强结论。

### CodeWiki

采用：功能树、层级分解、父级综合和质量 rubric。  
不采用：没有证据闭包的自由生成。

### Understand Anything

采用：guided tour、从概览到实现的阅读路线、版本新鲜度。  
不采用：缓存与源码版本不匹配时继续展示旧结果。

### Serena

采用：LSP 语义符号查找、references 和精确编辑导航，作为实时语义补充层。  
不采用：把 Serena 当作持久化项目 Wiki 或业务功能归纳器。

### OpenWiki

采用：仓库 Wiki 生成、图验证、无法确认时保守降级。  
需要继续评估：其页面组织和更新策略是否优于当前章节生成器。

### codebase-to-course / learn-codebase

采用：面向人的课程化结构、阅读任务和学习路径。  
不采用：缺少明确 License 的模板资产不能直接复制。

## 12. 验收场景：只用 Pipecat

在第一版报告内容获得用户认可前，只用 Pipecat 做端到端测试，不批量索引其他仓库。

Pipecat 报告必须首先把它定义为：

> 用于构建语音 Agent、多模态应用和实时 AI 的开源框架。

核心功能至少需要从整仓证据判断并覆盖以下方向；最终数量不得硬编码：

- 帧驱动的实时处理管线；
- 音频、视频或多模态传输；
- VAD、轮次和打断；
- STT / LLM / TTS 或 speech-to-speech 服务适配；
- 对话上下文和聚合；
- 工具调用；
- pipeline task、runner、worker 和生命周期；
- 观测、metrics、tracing；
- 序列化、事件或消息总线；
- 扩展接入和项目初始化；
- 评测能力可以作为开发工具能力，但不能压过框架主能力。

失败示例：报告只输出 CLI、project init、eval run、eval suite。即使这些有源码证据，也说明全局能力发现被入口候选绑架，没有覆盖 Pipecat 的主框架能力。

验收时检查：

1. 不出现独立 health 功能；
2. example 不成为一级功能；
3. 第一屏先讲框架定位；
4. 每项功能第一句讲本质；
5. 每项功能列核心/支撑模块和交接；
6. 运行链不是源码阅读顺序；
7. Voice、Loop、Graph、Router、并发和存储机制按本规格讲清楚；
8. 源码链接可下钻并可返回；
9. root/current JSON 均通过验证；
10. HTML 在真实浏览器桌面与移动视口通过。

## 13. 当前工程交接

### 13.1 当前代码位置

当前实现位于：

`/Volumes/T7/workspace/ontology/graph/dev/repo`

主要模块：

- `src/repo_teacher/indexer.py`：确定性索引与增量复用；
- `src/repo_teacher/capability_graph.py`：能力图和图查询；
- `src/repo_teacher/human_report.py`：模型证据包与报告 schema；
- `src/repo_teacher/cli.py`：报告编排、模型 provider、证据闭包和 CLI；
- `src/repo_teacher/report.py`：HTML 渲染；
- `src/repo_teacher/local_ui.py`：本地参数和进度界面；
- `usage.md`：现有使用说明。

### 13.2 已实现

- 多语言静态索引；
- 文件、符号、调用、包含、导入、模块和证据；
- CodeGraph 与能力图；
- 增量缓存与分析指纹；
- 原子 generation 发布；
- 人类报告 schema 和 HTML；
- Codex、OpenCode、DeepSeek provider；
- 本地 UI；
- report、graph、explain、compare、validate、export-skill 等命令；
- 证据、路径、行号和源码新鲜度校验。

### 13.3 当前正在修改

正在把旧流程：

`32 个模块模型分片 → 合并候选`

替换为：

`一次整仓图谱功能判断 → 固定功能 → 并发章节`

已经加入：

- 全局压缩图谱包；
- 业务语义字段；
- 功能到核心/支撑模块的映射；
- 模块视图和模块间关系；
- 候选入口不等于项目功能的 prompt 约束。

### 13.4 当前已知阻断

最新一次 Pipecat 全局调用只输出了四项：CLI、项目初始化、单场景评测、评测套件。

这次结果被模块路径安全门拒绝，没有发布，因此原报告没有被覆盖。

根因：

- 旧 capability candidates 主要来自入口，过度偏向 CLI；
- 组件中心节点的排序曾被路径字典序影响；
- 顶层 module 只有 `src/tests/examples`，模块粒度太粗；
- 模型把文件路径填进模块字段。

当前候选修复已经：

- 改为同类源码节点先按图中心度排序；
- 从源码路径确定性派生细粒度模块视图；
- 明确要求 capability candidates 只是不完整种子；
- 模块文件路径归一到最长匹配模块目录；
- 要求覆盖主数据流、传输、轮次、处理器、服务适配和 Worker。

该候选尚未完成完整测试和新一轮 Pipecat 生成，接手者必须先验证，不能直接宣称完成。

## 14. 新电脑上的接手步骤

1. 克隆 RepoLens 工程和参考仓库；
2. 安装 Python 3.11+；
3. 安装 Node 22，可用 NVM；
4. 安装 Codex CLI；需要时安装 OpenCode；
5. 运行 focused tests；
6. 检查全局证据包体积与模块覆盖；
7. 只对 Pipecat 跑一次完整报告；
8. 先人工审阅功能目录，不急着修移动端或批量索引；
9. 功能目录通过后再看每章机制讲解；
10. 内容通过后再做浏览器、链接、移动端和批量仓库验证。

建议命令：

```bash
PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_human_report -v
PYTHONPATH=src python3 -m compileall -q src tests
uvx --offline ruff check src tests

PYTHONPATH=src python3 -m repo_teacher report \
  /path/to/pipecat \
  --output /path/to/output/pipecat \
  --provider codex \
  --model-timeout 3600
```

## 15. 参考仓库清单

换电脑后按下列 URL 重新克隆，不依赖原机器绝对路径：

- <https://github.com/CodeBoarding/CodeBoarding>
- <https://github.com/codegraph-ai/CodeGraph>
- <https://github.com/FSoft-AI4Code/CodeWiki>
- <https://github.com/AsyncFuncAI/deepwiki-open>
- <https://github.com/abhigyanpatwari/GitNexus>
- <https://github.com/langchain-ai/openwiki>
- <https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge>
- <https://github.com/oraios/serena>
- <https://github.com/sourcebridge-ai/sourcebridge>
- <https://github.com/Egonex-AI/Understand-Anything>
- <https://github.com/zarazhangrui/codebase-to-course>
- <https://github.com/ktaletsk/learn-codebase>
- <https://github.com/ShenSeanChen/waku-agent>
- <https://github.com/pipecat-ai/pipecat>
- <https://github.com/livekit/livekit>
- <https://github.com/livekit/agents>
- <https://github.com/TEN-framework/ten-framework>
- <https://github.com/dograh-hq/dograh>
- <https://github.com/voxa-code/voxa>

## 16. 完成定义

只有同时满足以下条件才能宣称 RepoLens 第一阶段完成：

- Pipecat 功能目录由整仓图谱一次判断产生；
- 模块参与功能判断，但不单独发明功能；
- Pipecat 核心框架能力覆盖正确，CLI/评测不喧宾夺主；
- 每个功能章节总—分—总；
- 关键机制解释达到本规格最低要求；
- example 仅作为示例；
- 功能与模块双向映射可读；
- HTML 人工内容审阅通过；
- CLI、JSON、HTML、日志和本地 UI 可用；
- 测试、Ruff、compileall、validator 和真实浏览器检查通过；
- 没有已知 P0/P1 阻断。
