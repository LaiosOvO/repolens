# RepoLens 五阶段参考驱动 Pipeline
## 目标

RepoLens 只解决一个问题：把固定版本的代码仓库转换为给人做技术选型的报告。主产物是
`index.html`，内容依次回答：这是什么项目、有哪些核心业务功能、每项功能怎样运行、底层
如何实现、工程代码怎样组织、哪些结论有源码证据。

`report` 是严格顺序 Pipeline，不是任务图，不包含自动语义返修循环：

```text
01 固定源码
  → 02 CodeGraph/AST 索引
  → 03 一次生成完整报告内容
  → 04 确定性证据校验
  → 05 原子发布
```

任何阶段失败都停在该阶段。再次执行时，只有输入 identity 完全相同且已通过的阶段才能复用。

## 五个参考项目怎样落地

| 参考 | 采用的机制 | RepoLens 中的实现 |
| --- | --- | --- |
| Understand Anything | 固定阶段、中间产物、内容指纹缓存 | `LinearStageArtifacts` 写出五个固定 JSON；输入 digest 不同即失效 |
| RepoAgent / CodeGraph | 符号和关系是事实，模型只做解释 | 第 02 阶段建立文件、符号、调用、导入、包含和能力图；第 03 阶段只能引用这些事实 |
| Repomix | 有界上下文，不把整仓交给模型 | 证据包最大 640KB；按优先级裁剪；再复制 `allowed_source_paths` 到只读 source slice |
| DeepWiki | 先项目、再功能、再实现证据 | `project.overview → chapters → source_refs` 是 Schema 的固定阅读层次 |
| GitDiagram | 结构化数据先于图形 | `runtime_story` 和 `state_flow` 同时生成文字与交互图，renderer 不再猜边 |

## 阶段合同

### 01 固定源码

输入是本地仓库路径。输出是不可变临时快照和 `source_manifest_sha256`。已初始化 Git submodule
的实际源码也属于快照；随机临时目录不进入语义缓存键。

### 02 CodeGraph/AST 索引

先运行 CodeGraph，再建立 RepoLens 的确定性索引。输出至少包含文件、符号、关系、模块、
能力候选、证据和 capability graph。目录名、README、正则关键词都不能单独产生最终业务功能。

### 03 一次生成完整内容

模型只调用一次，一次输出完整 `human-report.json`：

1. 项目定位和核心用户旅程；
2. 按产品重要性排序的业务功能；
3. 每项功能的运行故事、状态流、存储/读写、循环/路由/并发、终止和失败；
4. 前端、后端、Worker、共享协议、数据和部署的工程组织；
5. 每个判断的 canonical feature/evidence/source refs。

健康检查、登录壳、CRUD、路由、UI primitive、目录和 example 默认只能作为实现证据。模型输出
Schema 不合法时本阶段失败；不会启动 Reviewer 再写一次。

本阶段 cache identity 绑定：源码内容、分析 fingerprint、有界 packet、完整 Prompt SHA、完整
Schema SHA、provider、model 和 reasoning effort。

### 04 确定性证据校验

这里不调用模型，只检查：

- JSON Schema；
- 项目 commit 与分析 fingerprint；
- chapter/overview ID 闭包；
- evidence ID、source path、行号范围；
- 每章运行链、状态流、选型边界和至少三条源码引用；
- 图文均来自同一份 `runtime_story/state_flow`。

校验失败不发布，不自动修改文字。

### 05 原子发布

将 JSON、HTML、能力图、章节、校验报告写入新的 immutable generation，全部成功后只切换一次
`current`。旧 generation 保留，因此发布失败不会产生新旧 HTML/JSON 混合。

## 报告内容顺序

```text
项目一句话结论
  → 核心用户旅程与产品主轴
  → 工程组织和运行组件
  → 按重要性排序的业务功能
      → 第一行机制结论
      → 真实交互图
      → 状态/数据流
      → 存储、查询、循环、路由、并发、终止
      → 难点、失败方式和取舍
      → 复用建议与不采用边界
      → 源码文件、行号和证据
```

对语音系统，报告必须说明音频采集、切段/VAD、ASR、Agent/Flow、Tool、TTS、文本/音频回传、
播放和打断。对工作流系统，必须说明构图时机、ready 条件、Router 的输入/规则/输出、状态合并
和动态拓扑边界。对 Worker 平台，必须说明提交的任务、队列、执行位置、产物、部署和状态回传。

## 可观察性与恢复

`.<report-name>.pipeline/stages/` 固定包含五个阶段 JSON 和一个 `pipeline.json`；
`<report-name>.performance.json` 给出各阶段 wall time、模型调用次数和最长阶段。GUI 和 CLI
消费同一五阶段进度文本。

恢复不是“循环返修”：发布失败后重跑时，第 03 阶段只有在源码、索引、Prompt、Schema 和模型
identity 全部相同的情况下复用；随后直接重新执行确定性校验和发布。

## 不采用

- 不采用整仓 RAG 或把全部源码拼成一个超长 prompt；
- 不采用每目录一次模型调用；
- 不采用功能清单 → Reviewer → regroup → Reviewer 的循环；
- 不采用 LLM 直接输出不可验证的 Mermaid；
- 不让 HTML renderer 承担功能识别或补写内容；
- 不让非阻断可读性意见卡住已经通过事实校验的发布。
