# 六仓技术选型比较模块独立审计

**结论：REQUEST CHANGES**  
**审计日期：2026-08-10**  
**范围：** `reference_catalog.py`、`comparison.py`、`comparison_report.py`、CLI `compare`、相关测试与 `examples/reference-selection`。  
**只读基准：** SourceBridge `2a128bf0c846`、PocketFlow Code2Tutorial `05b24cbbb0fe`、OpenWiki `7531d615216e`、Understand Anything `fe8c5bc59171`、CodeBoarding `8c3f2218c3ec`、DeepWiki Open `4181daa5ebde` 的当前本地源码工作树。

## 一句话结论

这个模块已经具备“按 8 个功能横向摆出 6 个项目、给出数据流与源码入口”的产品骨架，`48` 个预置方案和 `171` 个路径引用也都能在当前六仓找到；但它现在还不能作为生产级技术选型依据。核心原因不是页面不够漂亮，而是：**系统会把仅同名、仅剩一个匹配路径的任意目录认证为 `source-audited`，输出的 `evidence_ids` 实际上又是 symbol ID；同时评分是人工主观整数，却以自动分数和单一“第一名”呈现。** DeepWiki 还有 3 个与当前源码明显不符的能力描述。因此现阶段应把报告视为“阅读导航初稿”，不能视为“已审计事实库”或直接据此决定复用代码。

## 30 秒总览

| 检查项 | 结果 | 判断 |
|---|---:|---|
| curated 方案数量 | 6 仓 × 8 能力 = **48** | PASS |
| curated 路径引用 | **171** 次，当前工作树全部存在 | PASS（仅证明文件存在） |
| 实际六仓重新索引 | 6 仓、8 能力、48 方案，均生成 | PASS |
| 当前重新索引后的空证据方案 | 0/48 | PASS（但 ID 类型错误） |
| 已提交 example 的空证据方案 | SourceBridge 3 项 | FAIL，示例已过期 |
| 源码事实准确性 | 45 项可接受，3 项错误/过期 | FAIL，集中在 DeepWiki |
| 评分可复现性 | 权重可复现，基础分不可复现 | FAIL |
| 仓库身份与版本绑定 | 未绑定 remote/commit/hash | FAIL（P0） |
| 从比较页点击到实现源码 | 不支持 | FAIL |
| 页面“总—分—总” | 有开头摘要和分项，无决策收束 | PARTIAL |

当前固定权重计算出的 8 个“第一名”是：代码解析 CodeBoarding 88、代码图 CodeBoarding 88、组件发现 CodeBoarding 87、教程生成 SourceBridge 86、证据追溯 SourceBridge 91、增量更新 CodeBoarding 93、Codemap SourceBridge 88、Agent workflow CodeBoarding 88。**这些只是在未说明量表下，对人工录入基础分做加权的结果，不是实测基准，也不是针对用户场景的确定性结论。**

## 阻断问题

### P0-1：同名目录可冒充已审计仓库，且只命中一个路径就保留完整分数和 `source-audited`

`identify_reference_project()` 只比较项目显示名和目录 basename，不检查 Git remote、完整 commit、源码哈希或 catalog 版本；`curated_implementation()` 对一个能力只要任意一个预置路径存在就返回条目，并静默删除其他缺失路径；随后 `_curated_option()` 不降分、不降置信度，直接标记 `source-audited`。

- 身份识别：`src/repo_teacher/reference_catalog.py:609-628`
- 任一路径通过：`src/repo_teacher/reference_catalog.py:631-647`
- 无条件认证：`src/repo_teacher/comparison.py:186-215`

真实探针使用 `/tmp/unrelated/sourcebridge`、伪 commit `not-the-audited-commit`，只放入 `internal/indexer/parser.go` 一个文件；系统仍返回 code-parsing 85 分、`confidence="source-audited"`、`source="curated-source-audit"`。这意味着换版本、同名 fork、被删掉大多数实现的目录，甚至人为构造的索引都可继承六仓的结论。对生产级技术选型来说，这是事实可信边界失效。

**修复门槛：** catalog 必须绑定 canonical remote、已审 commit（或受控 commit range）和 catalog revision；每条 claim 绑定必需文件及内容 hash/行范围。身份或源码不一致时应标记 `stale`/`unverified`，不能继续使用 `source-audited`；缺少必需路径必须拒绝该方案或显著降级，不能只过滤列表。

### P0-2：`evidence_ids` 存放的是 symbol ID，不是证据 ID

`_evidence_ids_for_paths()` 从 `index["symbols"]` 取 `symbol["id"]`（`comparison.py:177-183`），却将结果写入名为 `evidence_ids` 的字段（`comparison.py:207`）。项目自身模型已把 `EvidenceRef` 定义为带路径、起止行和内容校验信息的独立对象（`models.py:119-123`），验证器也用 `index["evidence"]` 建立 `evidence_by_id` 并检查引用（`validation.py:63,102-124`）。

因此机器输出中的 `evidence_ids` 无法证明 summary、data_flow、优缺点、复用结论或分数，且若沿用现有验证语义会成为 dangling evidence。页面也没有解析或显示这些 ID。此问题与 P0-1 叠加后，`source-audited` 实际没有可机器复核的 claim-level 证据。

**修复门槛：** 每条原子事实使用真实 `EvidenceRef`（仓库、commit、path、line range、snippet hash）；比较方案引用这些 evidence ID。symbol 可以另放 `symbol_ids`，不得复用证据字段。

## 高优先级问题

### P1-1：DeepWiki 的 3/8 条描述与当前源码不符

catalog 将 DeepWiki Codemap 描述为“节点/边 schema、前端图、node selection”，并把它归入 `code-graph`；还断言它“没有逐 claim 文件/行号证据层”（`reference_catalog.py:523-532,556-565,578-587`）。当前源码显示：

- `api/schemas/codemap.py:6-56` 定义的是 `CodeMapCitation → CodeMapStep → CodeMapSection → CodeMap.sections`，没有 node/edge schema。
- `api/services/codemap.py:128,201-218,305-309` 格式化检索上下文，并把 citation snippet 反查到真实源码行后覆盖模型行号。
- `src/components/CodeMap.tsx:53-63,113-137` 展示 section/step 和可点击的文件/行号 citation chip；不是节点选择。
- `src/components/CodeViewer.tsx` 接收引用并展示源码。

逐项结论：

1. `code-graph`：**错误分类和错误数据模型**。它是面向问题的 guided code tour/codemap，不是代码图。
2. `evidence-grounding`：**明显低估**。它不是通用“每个 claim 都证明”的证据系统，但 Codemap 确实有 file/snippet/line citation 与真实行号校正。
3. `codemap-visualization`：**错误交互描述**。应写 sections/steps/citation selection，不是 nodes/edges/node selection。

这三项目前没有赢得对应榜首，但会直接误导用户判断 DeepWiki 哪部分可复用。

### P1-2：基础分是无量表的人工整数，页面却给出精确“自动评分”和唯一第一名

每个方案的 7 个维度分数都硬编码在 `REFERENCE_CATALOG`；`comparison.py:172-174` 只是按公开权重加总。审计未找到：每个分值的量表定义、测量过程、benchmark、证据、置信区间、评审人或更新记录。权重之和均为 1.0，只能证明算术正确，不能证明输入客观。

报告顶部直接展示“当前推荐”和精确分数，footer 又称“自动评分”（`comparison_report.py:166-172,194-197,221-229,266`）。用户容易把 88 对 87 理解成实测差异；实际上它可能只是作者判断。尤其 `agent-workflow` 以 CodeBoarding 为第一，但 catalog 自己承认它是固定代码分析流程、不是任意需求动态图编排器；若目标是动态 planner/subagent/checkpoint，OpenWiki 的运行时路线反而更贴近需求。

**修复门槛：** 公布每一维 0/25/50/75/100 的可验证量表和逐项证据；区分 `fact`、`reviewer_judgment`、`benchmark`；显示不确定性。按场景给出 profile（如精确静态分析、本地部署、动态 Agent、内容产品），允许不同权重产生不同推荐，不再输出脱离场景的唯一“最佳项目”。

### P1-3：能力桶混入不可直接比较的技术对象

`code-graph` 当前同时比较：SourceBridge/CodeBoarding 的确定性 symbol/call graph、Understand Anything 的知识图谱、OpenWiki 的文档链接图、PocketFlow 的 LLM 概念关系，以及被误分类的 DeepWiki guided tour。`agent-workflow` 同时比较固定 DAG、异步任务流水线、Deep Agents 动态 subagent runtime 和 Skill 包装。

这些对象解决的问题、真实性保证和生产边界不同，单一排名不具备同类可比性。

**修复门槛：** 至少拆分“确定性代码事实图 / 语义知识图 / 文档导航图 / guided tour”和“固定生成流水线 / 动态 planner+subagent runtime / 长任务控制面 / Skill 分发”。总榜只在同一决策问题内比较。

### P1-4：比较页不能点击到项目索引或具体实现，未达到用户要求的“点进去看模块怎么实现”

CLI 确实为每仓写出 `projects/<slug>/index.html`（`cli.py:203-207`），但比较页把源码路径渲染成纯 `<code>`（`comparison_report.py:115-119`），没有到项目页、文件、symbol 或行范围的链接。对生成 HTML 的探针确认：没有 `projects/` 链接，也没有 `file://` 链接。

因此报告虽然列了 171 个路径，却仍需要用户手动找仓库和文件；这不是可操作的代码索引。

**修复门槛：** 每个项目名链接到 `projects/<slug>/index.html`；每条源码落点至少链接到项目索引中的文件锚点，理想状态是 claim 对应的行范围。链接必须使用相对路径并有集成测试逐一验证目标存在。

### P1-5：已提交示例不是当前分析器的可追溯产物

`examples/reference-selection` 的比较 JSON 仍有 6 仓、8 能力、48 方案，但 SourceBridge 项目索引只记录 Python AST 与 JavaScript regex analyzer，未解析当前 Go 核心路径，导致 SourceBridge 3 个 curated 方案 `evidence_ids=[]`，仍显示 `source-audited` 并在三个能力上推荐第一。示例索引还缺少当前可用于追踪生成状态的 `analysis_fingerprint`、`integrity_sha256`、`generated_at`，比较顶层也没有生成时间、工具版本或 catalog revision。

重新用当前 analyzer 对真实六仓做内存索引，48 个方案均得到非空关联；这进一步证明示例是过期快照，而不是代码本身无法解析。

**修复门槛：** 从已固定的六仓 commits 重新生成示例；写入 tool/catalog revision、生成时间、仓库 remote+commit、索引完整性 hash；CI 检查样例与当前 schema/catalog 一致，出现空证据时禁止标记 source-audited。

### P1-6：许可证只藏在 JSON，且不参与“可复用”结论

option 中保存了 license 和 commit（`comparison.py:198-199`），但 HTML 正文不展示，两者只存在于页面底部嵌入 JSON。SourceBridge 当前工作树无许可证信息，仍可成为教程、证据、Codemap 三项第一名并给出高复用结论。用户已明确允许“参考”SourceBridge，但“架构思路参考”和“直接复制/分发代码”仍需在产品中分开。

**修复门槛：** 正文显式显示 remote、commit、license 状态；将复用结论拆成“架构参考价值”和“直接代码复用状态”。许可证未知时允许继续阅读和架构比较，但直接代码复用必须显示 `needs-license-review`，不能用普通 `high reuse` 混过去。

### P1-7：测试只证明数据形状，没有锁定六仓事实

相关 11 个单元测试全部通过，但只覆盖 catalog schema、路径过滤、通用 heuristic 与 HTML escaping/基本内容。没有测试：

- remote/commit/hash 身份不匹配；
- 只剩一个路径仍被认证；
- 真实 EvidenceRef 的可解析性；
- 48 条 claim 与源码行的对应；
- 分数量表和推荐理由；
- 六仓固定版本集成；
- 比较页到项目/文件锚点的可点击性；
- 示例是否过期。

现有测试会稳定通过上述 P0/P1 问题，不能承担“每完成一个模块就审计参考程度”的质量门禁。

## 中优先级问题

### P2-1：页面只有“总—分”，缺少可执行的“总”

页面开头有 30 秒摘要，分项卡也包含路线、data flow、优缺点和复用结论，这一点比平铺文档明显进步。但末尾只有一句免责声明，没有：场景化最终建议、互补组合、冲突项、风险、下一步源码阅读顺序或决策待办。因此结构更接近“摘要—48 张卡片”，还不是完整“结论—证据—最终决策”。

推荐用一张不横滚的主表先回答：每个能力的候选路线、适合场景、事实等级、许可状态、推荐阅读模块；卡片作为下钻。末尾给出“推荐组合 + 为什么 + 哪些结论仍待验证 + 下一步 PoC”。

### P2-2：六张大卡横向滚动，跨仓差异难以扫读

每个能力以固定最小宽度 370px 的横向卡片流展示（`comparison_report.py:252`）。单卡可读，但技术选型需要比较同一字段；横滚使用户难以同时看 6 个项目的底层路线、证据强度和许可。建议主表按“路线/数据源/确定性/增量/可复用/风险”对齐，点击再展开卡片。

### P2-3：维度标签不完整

`_DIMENSION_LABELS` 没有覆盖实际 catalog 使用的 `evidence_traceability`、`incremental_efficiency`、`visualization`、`production_readiness`、`reuse_value`，页面会混出英文空格标签（`comparison_report.py:84-105`）。不影响计算，但降低中文报告的扫读质量。

## 逐仓参考完整度

说明：下表统计的是 8 条 curated 描述与当前源码的对应程度，不是对上游项目质量打分；“路径存在率”六仓均为 100%，不能替代 claim 证据。

| 仓库 | 路径引用 | 8 项事实审计 | 参考完整度结论 |
|---|---:|---|---|
| SourceBridge | 33 次 / 32 个唯一文件 | 7 通过，1 部分通过 | **高**。解析、教程/证据、增量、Codemap、workflow 基本有直接源码支撑；`code-graph` 提到 cross-repo linkage，但列出的 source paths 未包含实际 federation 实现，属于 bundle-level 而非 claim-level 证据。另需单独处理当前许可证未知状态。 |
| PocketFlow Code2Tutorial | 19 次 / 6 个唯一文件 | 8 通过 | **高**。六个核心文件反复覆盖固定 6-step PocketFlow DAG、abstraction/relationship、BatchNode 写章节、prompt cache 与静态 Mermaid；“不是 AST/LSP、不是动态图 planner”的限制描述准确。文件少是项目集中，不是覆盖不足。 |
| OpenWiki | 29 次 / 18 个唯一文件 | 7 通过，1 部分通过 | **高**。Deep Agents 文件调查、doc-link graph、OKF frontmatter/link 校验、SQLite checkpointer、skills/connectors/subagents 均有源码基础；组件 skeleton critic 的“一次 retry”等约束部分由 prompt 约定而非强状态机，需要明确“prompt-enforced”。 |
| Understand Anything | 31 次 / 28 个唯一文件 | 7 通过，1 部分通过 | **高**。Tree-sitter、GraphBuilder、call/import edge、聚类/分层、Tour、fingerprint/staleness、Dashboard 与 Skill 角色均吻合；component flow 写了 framework detection，但列出的该条 source paths 没落到对应 detector，证据粒度不完整。 |
| CodeBoarding | 32 次 / 32 个唯一文件 | 6 通过，2 部分通过 | **高**，且是确定性代码分析路线最强参考。LSP adapters/client、CallGraphBuilder、EdgeBuilder、symbol table、Leiden、validation/repair 均吻合；incremental 和 Codemap 描述包含 cluster delta/copy-forward，但对应条目的 source paths 未列 `cluster_delta.py` / analysis cache 等关键落点。 |
| DeepWiki Open | 27 次 / 18 个唯一文件 | 5 通过，3 不通过 | **中/需修订**。文本 RAG、Wiki structure、异步任务、全量再生成和固定长任务链路基本准确；code-graph、evidence-grounding、codemap-visualization 三项与当前 sections/steps/citations 实现冲突。 |

### 48 项状态矩阵

图例：✅ 当前描述可接受；⚠️ 结论大体正确但 source path/保证边界不完整；❌ 与当前源码实质冲突。

| 仓库 | 解析 | 代码图 | 组件发现 | 教程 | 证据 | 增量 | Codemap | Workflow |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| SourceBridge | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| PocketFlow Code2Tutorial | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| OpenWiki | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Understand Anything | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CodeBoarding | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ✅ |
| DeepWiki Open | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ |

## 分类与技术路线的实际选择建议

在修复评分前，更可靠的使用方式不是“选总分第一”，而是先选问题类型：

| 目标 | 首要源码参考 | 补充参考 | 当前证据支持的理由 |
|---|---|---|---|
| 精确代码解析、调用图、增量影响分析 | CodeBoarding | SourceBridge、Understand Anything | CodeBoarding 的 LSP、call graph、incremental merge/cluster delta 最完整；SourceBridge 的 tree-sitter 与 change-watch 控制面互补。 |
| 证据化教程与 Codemap | SourceBridge | DeepWiki、PocketFlow | SourceBridge 的可追溯报告管线最接近目标；DeepWiki 适合 guided tour + citation UI，PocketFlow 适合极简固定生成 DAG。 |
| 动态 Agent 调研/写作流程 | OpenWiki | CodeBoarding | OpenWiki 的 Deep Agents、subagents、skills/connectors/checkpoint 更接近动态运行时；CodeBoarding 适合借鉴确定性分析之上的角色/工具/repair 边界。 |
| 本地知识图谱与 Tour | Understand Anything | OpenWiki、DeepWiki | Understand Anything 提供解析—图—分层—Tour—Dashboard 闭环；OpenWiki 补文档组织，DeepWiki 补问答与引导式阅读。 |
| 长任务 API 与前端状态反馈 | DeepWiki | OpenWiki | DeepWiki 的异步任务、stream/UI 链路清楚，但不等于通用多 Agent planner。 |

这张表是基于源码能力类型的审计判断，不是 benchmark 排名；真正进入产品选型前仍需按目标仓规模、语言、延迟、资源消耗和许可证做 PoC。

## 真实探针与复现实验

### 1. 单元测试

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_reference_catalog \
  tests.test_comparison \
  tests.test_comparison_report -v

Ran 11 tests ... OK
```

结论：实现满足现有测试，但测试不足以证明源码事实和生产可信度。

### 2. Catalog 数量与路径存在性

```text
entries: 48
path references: 171
unique project/path pairs: 134
missing paths in current six worktrees: 0
```

分仓：SourceBridge 8/33，PocketFlow 8/19，OpenWiki 8/29，Understand Anything 8/31，CodeBoarding 8/32，DeepWiki 8/27（前一数字为方案数，后一数字为路径引用次数）。

### 3. 当前 analyzer 的真实六仓内存索引

```text
sourcebridge              1575 files / 13442 symbols / 82349 relationships
pocketflow-code2tutorial   197 files /    40 symbols /   564 relationships
openwiki                   321 files /   833 symbols /  3069 relationships
understand-anything        457 files /   904 symbols /  3788 relationships
codeboarding               383 files /  4542 symbols / 31057 relationships
deepwiki-open              149 files /   529 symbols /  3761 relationships

comparison: 6 projects / 8 capabilities / 48 options
curated options with empty generated IDs: 0
```

注意：最后一行只说明关联到路径内 symbol；由于 P0-2，这些仍不是 claim-level EvidenceRef。

### 4. HTML 可操作性探针

```text
capability sections: 8
option cards: 48
links containing projects/: 0
file:// source links: 0
visible score rubric/methodology: absent
visible commit/license: absent
```

## 上线前验收标准

以下条件全部通过后，才能把结论从 REQUEST CHANGES 改为 PASS：

1. 同名伪仓、不同 remote、未审 commit、源码 hash 不一致时，不能返回 `source-audited`。
2. 任一必需路径缺失或 claim 对应 snippet 改变时，该 claim 明确变为 stale/unverified；不得保留原分和原置信度。
3. `evidence_ids` 全部解析到真实 `index.evidence`，并可校验 path、line range、snippet hash；symbol ID 使用独立字段。
4. 修正 DeepWiki 三项描述，并把 guided tour 从确定性 code graph 比较中拆出。
5. 48 项每个 summary、关键 data-flow step、strength/limitation、reuse verdict 至少有一条 claim-level 证据或显式标注 reviewer judgment。
6. 公开评分量表、权重、场景 profile、置信度和分值依据；相同输入可重复得到相同分值，且不再把人工基础分表述为自动实测。
7. HTML 首屏能看到场景、推荐路线、关键 trade-off、license/commit/置信度；底部有组合建议、风险和下一步 PoC，形成真正“总—分—总”。
8. 48 个方案均可从比较页点击到对应项目页，再点击到具体文件/行；CI 验证所有链接目标存在。
9. 固定六仓版本的端到端 golden 测试覆盖：48 条目、claim evidence、推荐理由、过期检测、页面链接和示例再生成。
10. SourceBridge 等许可证未知项目必须区分“可参考架构”与“可直接复用代码”，未知状态不能被普通高复用标签覆盖。

## 最终判断

**REQUEST CHANGES。**

可以保留并继续迭代的部分：功能优先的信息架构、48 方案骨架、data flow/优缺点/复用结论字段、CLI 一次生成六仓索引和比较页、HTML escaping，以及 PocketFlow/OpenWiki/Understand Anything/CodeBoarding/SourceBridge 的大多数人工源码分析。

必须先修复的部分：仓库版本与证据可信边界、EvidenceRef 语义、DeepWiki 错误事实、评分/推荐的主观性披露、能力分类可比性、源码下钻链接、示例和六仓集成测试。在这些完成前，报告适合指导“下一步读哪些代码”，不适合给出生产技术选型的确定第一名。
