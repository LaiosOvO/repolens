# ADR 0003：先发现实现难点，再生成面向人的功能教程

状态：已实现（Waku Agent 为首个兼容性验收仓）

## 用户问题

仓库报告不能只回答“有哪些入口和文件”。用户先要知道项目提供哪些功能，再理解每项功能真正难在哪里、运行时怎样工作、哪些不变量必须保持、天真实现为什么会失败，最后才进入源码做技术选型。

## 参考项目结论

| 参考 | 采用 | 不采用 |
|---|---|---|
| GitNexus | entrypoint、execution flow、分支/循环、sink、影响范围作为难点候选信号 | 不把图中心性或调用次数直接等同实现难度 |
| CodeBoarding | 调用图、组件边界、结构拆分与增量重证 | 不引入其 LSP 生命周期和聚类依赖作为本轮前提 |
| Serena | 精确符号、引用、实现和测试定位，用于证据下钻 | 不把 live LSP 当成持久索引或难点判定器 |
| PocketFlow Code2Tutorial | 先结论、再关系、再章节的教学编排 | 不让 LLM 无证据地发明关系或难点 |
| DeepWiki Open | 层级页面、citation/source viewer 和逐层下钻 | 不把 RAG 文本块或生成 Wiki 当源码事实 |
| Understand Anything | 有界图上下文、guided tour、impact 与 freshness | 不采用无证据的 simple/moderate/complex 标签 |

研究证据：

- `docs/research/automatic-feature-difficulty-discovery-projects.md`
- `docs/research/automatic-feature-difficulty-discovery-synthesis.md`

## 决策

采用“候选发现 → 证据门 → 教学编译”三段式，而不是让一个 LLM 直接写长报告。

1. 索引层继续产生 Feature、Symbol、Relationship、Evidence。
2. `difficulty.py` 只根据功能身份、执行流/状态/控制/失败信号和已绑定证据生成 Difficulty Map；LOC 和文件数量不能单独构成难点。
3. 每个难点固定输出：
   - 为什么难
   - 运行时到底怎么走
   - 必须成立的不变量
   - 天真实现与失败模式
   - 设计取舍
   - 源码/测试证据
   - 迁移前必须回答的问题
   - 未知项与置信度
4. `artifacts.py` 把 Difficulty Map 嵌入每个 tutorial，`report.py` 在源码入口之前渲染，保证阅读顺序是“功能 → 难点 → 实现 → 证据”。
5. 没有证据的项只能标为 `inferred-gap`，不能写成已确认事实；LLM 只能讲解既有记录，不能添加难点。

## Waku Graph 首个验收合同

Graph Workflow 必须稳定识别五项：

1. `wave-barrier`：同波共享波前状态，整波结束后确定性提交。
2. `state-collision`：并行分支写同 key 必须失败，不能静默 last-write-wins。
3. `fan-in-join`：gather 是图上的同步边界；`asyncio.gather` 只等待，不提供拓扑、提交和路由语义。
4. `routing-and-cycles`：代码 router、声明式 targets、`max_visits` 与 `max_steps`。
5. `durability-boundary`：明确它是进程内执行器；checkpoint、恢复与幂等尚未实现。

其他八个 Waku 功能每项至少输出两个机制难点，不能只复述入口。

## 实现位置

- 难点发现与解释合同：`src/repo_teacher/difficulty.py`
- 派生产物接入：`src/repo_teacher/artifacts.py`
- 人类报告渲染：`src/repo_teacher/report.py`
- 分析版本指纹：`src/repo_teacher/indexer.py`
- 端到端验收：`tests/test_reference_ground_truth.py`
- HTML 内容验收：`tests/test_report.py`

## 边界

当前 Waku 是固定 Git 身份的 compatibility profile，因此可提供项目级语义难点；对任意未知仓库，只有静态信号时应输出候选或未知。后续要升级为跨仓自动判定，需要增加运行 trace、历史 churn、行为测试和恢复证据，不能用更激进的文案代替证据。
