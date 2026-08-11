# Human Report Readability Audit

Audit target:
- `/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects/voxmesh-references/pipecat-human-v2/index.html`
- `/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects/coze-feature-inventory/index.html`

Tested viewports:
- 1440 x 900
- 390 x 844

Method:
- Opened both reports in real Chrome.
- Read the first fold, the project-positioning block, the project-function map, and one representative core feature chapter in each report.
- Checked horizontal overflow by comparing document/body width with viewport width.

## Verdict

**PASS**

Both reports now read like human-facing technical selection material instead of code listings.
The core business capabilities are clearly promoted above scaffolding/support items, and the runtime stories answer the question “how does it actually run?” with both diagrams and explanatory text.

## Scorecard

| Report | Score | Verdict |
|---|---:|---|
| Pipecat | 92 / 100 | PASS |
| Coze | 90 / 100 | PASS |

## Pipecat

### What works

- The opening line is immediately understandable: `实时语音与多模态 Agent 开发者用 Pipecat 把流式音视频会话接成可运行的对话 Agent...`
- The next section, `先看前端、后端、Worker、媒体与共享协议怎样组织。`, gives the reader an architecture lens before any chapter detail.
- The core chapter `实时语音会话运行时` does the right thing for a human reader:
  - first sentence states the essence,
  - the interaction card shows `Pipeline -> Transport -> VAD/turn -> PipelineWorker`,
  - the prose below explains the control flow in plain language.
- The feature order is sensible for selection work:
  - core runtime and orchestration are first,
  - transport and phone support follow,
  - CLI / eval / support capabilities are visibly demoted.
- Mobile at 390 px does not overflow horizontally.

### Problems

#### MEDIUM

- The first fold is still quite tall on 390 px because the hero title, intro paragraph, and metadata card all compete for attention before the first concrete feature card appears.
  - This is readable, but it slows down “what is this project?” scanning for a first-time reader.

#### LOW

- Some mechanism paragraphs are still dense, especially in the middle of feature chapters.
  - They are understandable, but they ask for more attention than the average selection memo ideally should.

### Evidence seen in the page

- `实时语音与多模态 Agent 开发者用 Pipecat...`
- `实时语音会话运行时`
- `把媒体采集、流式传输、信号预处理和轮次判断接成一条可实时说话的会话链。`
- `Pipeline 把 processors 串成上下行 frame 链`
- `Transport 把房间或 socket 媒体映射成输入/输出 frame`
- `VAD/turn analyzer`
- `PipelineWorker 持续驱动 frame`

## Coze

### What works

- The opening line is specific and useful:
  - `面向本地联调操作者的 Coze 桌面复刻工作台...`
  - it tells the reader it is a desktop workbench, not just a generic SaaS clone.
- The product axis is clear:
  - `桌面工作台与受控任务执行`
  - `本地登录与会话工作台`
  - `专家模板驱动的任务创建与执行追踪`
  - `本地项目运行时与沙箱发布`
  - `项目沙箱部署与可访问端点发布`
- The chapter structure is aligned with the user’s selection needs:
  - what the product is,
  - how the engineering stack is organized,
  - how tasks flow to workers,
  - how deployment becomes a local Docker URL.
- On 390 px there is no horizontal overflow.

### Problems

#### MEDIUM

- The first fold is still dense on mobile because the project statement, metadata card, and first product-axis card all occupy substantial vertical space.
  - A reader can still understand it, but the first concrete task-flow evidence appears after a meaningful scroll.

#### LOW

- Some support-capability content remains fairly prominent in the full map, even though it is demoted correctly relative to the core product axes.
  - This is not misleading, but it still costs a little scan effort.

### Evidence seen in the page

- `面向本地联调操作者的 Coze 桌面复刻工作台...`
- `桌面工作台与受控任务执行`
- `本地登录与会话工作台`
- `专家模板驱动的任务创建与执行追踪`
- `本地项目运行时与代码沙箱`
- `项目沙箱部署与可访问端点发布`
- `本地 AgentTaskWorker`
- `Worker 从 agent_tasks 里 claim 最早的 queued 任务`
- `把项目版本文件物化、构建 Docker 镜像、启动容器并探活`

## Final judgment

The two reports now satisfy the human-reading goal:

1. They tell the reader what each project is within the first screen.
2. They separate business capabilities from scaffolding/support layers.
3. They explain how the important features actually run, with diagrams and prose.

The remaining issues are polish-level, not comprehension-blocking.
