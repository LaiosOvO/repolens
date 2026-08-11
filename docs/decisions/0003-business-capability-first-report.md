# ADR 0003：先识别业务能力，再解释代码实现

状态：Implemented candidate，等待真实仓报告验收  
日期：2026-08-11

## 决策摘要

Repo Teacher 的一级目录不再来自入口、模块、路由、类或 example，而来自产品对外提供的业务能力；框架/SDK 的“用户”是使用框架的开发者，一级目录对应开发者能构建或控制的稳定公开行为。

每个一级能力必须同时回答：

1. `user_actor`：谁使用。
2. `user_goal`：为了什么目标。
3. `visible_outcome`：用户最终看见或得到什么。
4. `product_surface`：通过什么产品/框架界面使用。
5. `causal_flow`：从触发到结果的核心因果链。

缺少任一字段的候选不能进入人类报告。只有 README、docs、tests、examples 或 demos 证据，且没有产品实现源码的分组，也不能进入一级功能。

## 为什么原方案错了

原索引先按模块/入口分片，再直接把每个分片的可调用点写成“功能”。这会产生三种错误：

- 把健康检查、迁移、RPC 骨架、通用 UI、异常分类写成产品能力。
- 把 Pipecat 的 food-ordering、voicemail、vision 等 example 写成核心功能，却遗漏实时 Frame Pipeline、轮次控制和打断等框架能力。
- 把 Dograh 的数据库/API/鉴权与“实时通话平台、可视化工作流平台”放在同一级，读者无法建立产品心智模型。

这些内容并非无用，但位置错误。模块属于工程结构；example 属于用例；入口、符号和调用关系属于证据。

## 参考项目采用结论

| 参考 | 采用的做法 | 在 Repo Teacher 中的位置 |
|---|---|---|
| DeepWiki / OpenWiki | 层级 Wiki、先总览再下钻 | 项目定义、产品主轴、业务功能、实现章节 |
| PocketFlow 教程 | 先建立最小心智模型，再按因果顺序讲机制 | 每功能的总—分—总与 worked example |
| CodeBoarding / RepoAgent / CodeGraph | 先建立符号关系、组件和影响图 | 静态索引、候选种子、证据闭包 |
| Sourcegraph / Serena | 符号级导航和精确源码下钻 | 文件、行号、符号、已解析关系 |
| code-tour / codebase-onboarding 等 Skills | progressive disclosure | 主报告只放决策信息，源码与原始索引折叠下钻 |

不采用“仅由 LLM 自由阅读整仓后直接写文章”的方案。模型只读取有界 graph shard、产品导航和源码切片；其输出必须通过 canonical feature/evidence/path 闭包。

## 新生成管线

1. **确定性索引**：文件、符号、imports/calls/contains、模块、组件和能力图。
2. **产品导航**：只读取根 README 与项目元数据，确认作者宣称的产品类型、用户和结果；不作为实现证明。
3. **图分片候选**：从解析关系和组件局部性选择候选，不重新盲扫整仓。
4. **全局业务归并**：用五字段业务合同将跨前端、API、Worker、媒体和状态模块合成一个用户结果。
5. **角色降级**：examples/demos 归入相关功能的“仓库已有场景”；健康、构建、迁移和通用骨架进入支撑层或排除。
6. **产品主轴**：1–4 条，例如 Dograh 的“实时语音通话平台”与“可视化 Agent 工作流平台”。
7. **章节生成**：用途 → 因果运行链 → 状态/控制机制 → 难点/失败 → 取舍 → 复用 → 源码证据。
8. **发布门**：capability/evidence/source path、生成摘要和 generation 闭包全部通过后原子发布。

## HTML 信息架构

固定阅读顺序：

1. 这是什么项目。
2. 产品主轴。
3. 核心业务功能。
4. 端到端运行架构。
5. 前端、后端、Worker、媒体和状态怎样协作。
6. 每项功能的真实难点、失败方式和技术取舍。
7. 工程结构与目录职责。
8. 支撑能力（默认折叠）。
9. 源码、符号、关系和原始索引（最后下钻）。

技术选型不是由工具替用户直接给出“选 A”。报告先让用户分别理解每个项目的业务功能和实现机制；用户再决定“哪个功能参考哪个项目”。

## example 的处理规则

- 保留 example 的场景、输入、输出和组合方式。
- 把它放进对应公开能力的 worked example 或证据区。
- 不用 example 名称当一级标题。
- 只有 example 没有产品实现源码时，fail closed，不发布为产品能力。

Pipecat 中 voicemail 应成为轮次/通话控制的案例；vision 应成为多模态输入的案例；food ordering 应成为工具调用或流程控制的案例。

## 本地执行界面

`repo-teacher ui` 是 CLI 的本地薄界面，不复制分析逻辑。它只负责：

- 输入仓库、输出根目录和报告名。
- 选择 Codex 或 OpenCode。
- OpenCode 选择 DeepSeek Flash/Pro。
- 以仅当前子进程环境变量的方式传递 OpenRouter Key。
- 显示六阶段进度与日志。

所有分析、验证和发布仍调用同一个 `repo-teacher report` 命令，保证 CLI 与 UI 产物一致。

## 剩余验收

- 用 Pipecat 确认 Frame Pipeline、轮次/打断、多模态、传输与模型服务等公开能力优先，example 只作案例。
- 用 Dograh 确认实时通话和可视化工作流为两条主轴，鉴权、额度、迁移和 CLI 不抢占首屏。
- 用任务/Worker 型仓库确认提交、持久化/排队、租约、执行和事件回传被解释为一条架构主链。

