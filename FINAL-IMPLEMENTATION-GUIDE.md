# 代码仓库教学产品：当前最终实现建议

> 这份文档只回答一件事：Repo Teacher 第一版到底应该做什么、做到什么程度、各能力应该参考哪个项目的哪种机制。
>
> 它不是内部类设计稿，也不是数据库或服务拆分稿。

## 读者与目的

面向准备把 Repo Teacher 做成可交付产品的产品与工程负责人。

读完后，读者应该能：

1. 说清第一版的边界；
2. 判断哪些能力已经能作为稳定模块使用，哪些仍在修复或重生；
3. 给每个能力选定一个最合适的开源参考机制；
4. 把“功能 → 模块 → 源码证据 → 验证”串成一条可执行链路。

## 一、当前结论

Repo Teacher 的目标不是通用 Wiki，也不是自动铺满全仓库的文档生成器。

它要做的是：把一个固定 commit 的本地仓库，转成一份能支持人和 Agent 继续工作的教学索引。

第一版必须同时满足两件事：

1. 让第一次看到仓库的人能在短时间内说清楚它提供什么能力；
2. 让选中的一个能力可以被定位到具体模块、具体源码证据、具体验证门。

### 当前发布面

- 主阅读入口：[Repo Teacher 单页报告](../../biz/docs/html/repo-teacher.html)。
- `core index chain`：独立复审 PASS。
- `teaching HTML`：独立复审 PASS。
- `Go` 分析器、`Skill export`、`module locator`：独立复审 PASS。
- `technology comparison`：六个完整参考仓已用当前分析指纹重生，6/6 身份验证通过，48 个“仓库 × 能力”条目可从主页面下钻。
- `Waku Agent`：作为第七个非 curated 兼容性仓库，冷/暖索引与 memory / graph / loop / gateway 定位均通过；它不参与六仓排名。

核心验收证据见 [core-index-reaudit-round3.md](docs/audits/core-index-reaudit-round3.md)，教学报告验收证据见 [teaching-reaudit-round13.md](docs/audits/teaching-reaudit-round13.md)。

## 二、第一版应该输出什么

### 1. 人看的项目决策页

页面结构只保留四层：

1. **30 秒重点**：这个仓库是什么、最值得参考什么、最大风险是什么。
2. **能力地图**：把真实功能列出来，而不是复制 README 目录。
3. **黄金路径**：挑一个最重要的能力，说明它怎么从入口走到结果。
4. **取舍结论**：直接复用、改造复用、只参考，还是不采用。

页面要默认先讲结论，再展开证据。不要把源码证明、关系图和测试截图放在第一屏。

### 2. Agent 使用的证据索引

索引要回答的是：

**功能 → 模块 → 关键符号 → 关系或调用 → 测试 → 风险边界。**

如果某条结论没有源码、测试或独立审计支撑，就必须标成未验证，不能靠模型补齐。

### 3. 选择功能后的工作包

当用户选中一个功能时，导出的工作包至少应该包含：

- `SKILL.md`：告诉 Agent 先读什么、怎么实现、怎么验证；
- `module-index.md`：给人看的功能到模块路线；
- `module-index.yaml`：给工具读的结构化索引；
- `evidence.md`：事实、来源、未验证项和漂移状态；
- `feature-tour.tour`：可选的 IDE 导览。

第一版只要求“能导出一个可执行的功能包”，不要求把整个仓库都变成百科。

## 三、每个能力参考谁

| 能力 | 首选参考 | 具体借鉴 | 不照搬什么 |
| --- | --- | --- | --- |
| 仓库与符号事实 | GitHub Code Navigation、SCIP、tree-sitter、Sourcegraph | 定义、引用、符号身份、跨文件导航 | 不把检索结果直接当产品解释 |
| 大仓库上下文选择 | Aider RepoMap、SourceBridge | 相关性排序、分层理解、内容哈希、缓存 | 不把整个仓库一次塞给 LLM |
| 功能候选与代码图 | Understand Anything、CodeBoarding、SourceBridge | 文件/符号节点、imports/calls/contains、依赖层级 | 不把漂亮图形当语义正确证明 |
| 教程章节与学习顺序 | PocketFlow Tutorial | 先抽象、再关系、再排序、再分章 | 不采用无版本锚点的空泛叙述 |
| 覆盖与质量检查 | OpenWiki、GitHub Acquire Codebase Knowledge | skeleton critic、unknown-unknown 扫描、验证命令、独立 QA | 不默认生成整个 Wiki |
| IDE 逐步导览 | Microsoft CodeTour、Walkthrough | commit/file/line/pattern 锚点、逐步播放、tangent | 不让 IDE 层承担仓库分析 |
| 互动式教学 | learn-codebase | 先预测、再揭示、分级提示、主动回忆 | 不把 Prompt Skill 当索引引擎 |
| 增量更新 | OpenWiki、Understand Anything、SourceBridge | Git diff、文件指纹、失效标记、定时更新 | 第一版不追求自动修复所有旧文档 |

## 四、六个参考仓库的本地机制

这里写的是“当前实现建议”会用到的机制，不是让产品照抄代码。

| 参考仓库 | 该能力可借的机制 | 本地源码路径 |
| --- | --- | --- |
| SourceBridge | 分层理解、证据对象、Code Tour 验证、缓存与失败恢复 | `repo/sourcebridge/internal/indexer/indexer.go`、`repo/sourcebridge/internal/indexer/parser.go`、`repo/sourcebridge/internal/indexer/languages.go`、`repo/sourcebridge/workers/knowledge/evidence.py` |
| PocketFlow Code2Tutorial | 最小教程流水线、学习顺序、章节桥接 | `repo/pocketflow-code2tutorial/flow.py`、`repo/pocketflow-code2tutorial/nodes.py` |
| OpenWiki | skeleton critic、coverage critic、canonical page 与链接完整性 | `repo/openwiki` 下的 Wiki / coverage / critic 实现 |
| Understand Anything | 结构指纹、变更等级、知识图、tour、freshness preflight | `repo/understand-anything` 下的 fingerprint / change / tour 实现 |
| CodeBoarding | LSP 位置级语义、component 聚类、增量边重验证、缓存回滚 | `repo/codeboarding` 下的 `call_graph_builder.py`、`fingerprint_diff.py`、`incremental_orchestrator.py` |
| DeepWiki-Open | Wiki、Codemap、CodeViewer 的展示结构与证据引用 | `repo/deepwiki-open` 下的 Wiki / Codemap / CodeViewer 实现 |

更完整的本地克隆清单见 [参考仓库清单](docs/audits/reference-clone-inventory.md)。

## 五、第一版推进顺序

### Phase 1：先做闭环

只做这条链路：

1. 固定仓库与 commit；
2. 生成确定性索引；
3. 提炼可修正的能力候选；
4. 选择一条黄金路径；
5. 输出总—分—总 HTML；
6. 对路径、符号、测试、引用做证据校验；
7. 显示未验证项。

这一期不做 ACP 对接，不做 Codex Desktop session 列表，不做 OpenCode 派单。

### Phase 2：选择功能并导出

第二期才增加：

- 用户选中一个或多个功能；
- 导出任务型 `SKILL.md`；
- 导出人读与机读模块索引；
- 导出可选 Code Tour；
- 检测 commit 漂移并标记过期。

### Phase 3：持续维护

第三期再考虑：

- 更好的交互式追问；
- Git diff 驱动的局部更新；
- 与项目追踪系统联动；
- 把选中的功能进一步转成 Spec 和 Ticket。

## 六、最重要的质量门

### 1. 身份门

所有页面、索引、Skill 和 Tour 必须指向同一个不可变 commit。

### 2. 来源门

结论必须落到文件、符号、关系、测试或独立审计之一。

### 3. 路径门

页面里出现的文件、符号、测试必须真实存在；失效时不能继续展示成事实。

### 4. 语义门

“模型写得合理”不等于“结论正确”。必须能回答：

- 入口在哪里？
- 状态在哪里变化？
- 失败路径是什么？
- 哪个测试证明行为？

### 5. 教学门

冷读者应该能：

- 30 秒说出项目定位和最大风险；
- 3 分钟复述一条核心功能路径；
- 按页面跳到源码；
- 区分真实源码与简化示意。

## 七、第一版明确不做什么

- 不做完整 IDE；
- 不做支持所有语言的编译级代码智能；
- 不一次生成整个仓库所有知识；
- 不允许 LLM 自己决定最终产品能力而不允许人工修正；
- 不把生成的调用图直接当事实；
- 不在第一期对接 ACP、Codex Desktop session 列表或 OpenCode 派单；
- 不提前决定图数据库、向量数据库、微服务或部署拓扑。

## 八、完成标准

第一版只有同时满足以下条件才算完成：

1. 能对两个结构不同的仓库生成报告；
2. 每份报告都有可修正能力和一条黄金路径；
3. 关键结论能跳回固定 commit 的源码或测试；
4. 错误路径、无效符号和不存在测试能被发现；
5. 一个没有参与实现的人能在 3 分钟内复述核心路径；
6. 同一个流程在私有或低知名度仓库上仍然有效；
7. 用户能选择一个功能并看到未来导出包所需的完整证据；
8. 报告明确区分事实、推断和未验证内容。

## 九、当前执行建议

1. 先把 [Repo Teacher 单页报告](../../biz/docs/html/repo-teacher.html) 作为人工技术选型入口。
2. 选择具体能力后，用 `explain` 下钻到模块、源码与关系证据。
3. 需要交给编码 Agent 时，用 `export-skill` 生成受版本与闭包校验约束的工作包。
4. 用更多非 curated 仓库持续做兼容性回归；动态模式无法静态证明时保持候选或未知，不提升为事实。
5. 下一产品阶段再扩展 ACP、项目追踪和外部任务分发。

## 十、一句话结论

先用 **确定性源码事实** 建立可信底座，用 **PocketFlow 的学习顺序** 组织叙事，用 **OpenWiki 的独立 QA** 防止漏项，用 **SourceBridge 的证据和分层理解** 提升完整性，再把选中功能导出成可执行的 Skill 和模块索引。

不要寻找一个可直接照搬的“DeepWiki 平替”；当前可行路线是把已经被验证过的机制组合起来，并让每个结论都受 commit、符号、测试和冷读约束。
