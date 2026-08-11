# 六仓技术选型比较第二次独立复审

**结论：REQUEST CHANGES**  
**日期：2026-08-10**  
**范围：** `reference_catalog.py`、`comparison.py`、`comparison_report.py`、CLI `compare`、专项测试，以及真实六仓生成物。  
**审计方式：** 只读检查与独立重放；未修改产品代码。

## 一句话结论

上一轮两个最危险的错误已经被实质修复：同名目录不会仅凭名字获得 curated 身份，必需源码发生变化会 fail closed；`evidence_ids` 也不再混入 symbol ID。六个固定仓库的 remote、commit 和必需源码 bundle 当前全部通过，48 个 curated 方案能重新生成，119 次 EvidenceRef 引用没有 dangling。

但当前版本仍不适合直接交付给用户做生产技术选型，原因有三类：

1. **用户实际打开的持久化 HTML/JSON 仍是旧版本。** `examples/reference-selection/technology-selection.*` 仍为 schema 1.0，仍显示“当前推荐/自动评分”，没有项目和源码下钻链接。
2. **176 个源码链接中，只有 20 个链接条目由 EvidenceRef 定位；156 个只是首个 symbol 或整文件。** 链接都能打开且行号不越界，但常常没有定位到支撑结论的实现。例如 DeepWiki 的 citation grounding 被展示为 `api/services/codemap.py:29-31`，实际关键实现位于 `201-222` 与 `305-309`。
3. **场景权重没有参与用户可见决策。** 系统计算了四组 `scenario_scores`，页面却不展示也不能选择场景；由于大多数 `comparison_class` 只有一个项目，首屏把 5–6 个项目全部标成“路线内候选”，仍没有回答“这个需求应先看哪条技术路线、为什么”。

因此本轮没有 P0，但仍有阻断交付的 P1。

## 30 秒验收表

| 验收项 | 实测 | 结论 |
|---|---:|---|
| curated 条目 | 6 仓 × 8 能力 = **48** | PASS |
| 固定身份 | canonical remote + 40 位 commit + 完整必需源码 bundle，**6/6 verified** | PASS（普通 CLI 路径） |
| 同名伪仓 / 错 remote | curated 拒绝，降为 heuristic 或无结果 | PASS |
| 错 commit / 缺必需路径 / index hash 篡改 / 索引后修改必需文件 | curated fail closed | PASS |
| EvidenceRef 语义 | `evidence_ids` 与 `symbol_ids`、`file_id` 分离 | PASS |
| EvidenceRef dangling | 119 次 option 引用、72 个 project/evidence 对，**0 dangling** | PASS |
| 源码引用 | **176** 条，0 缺文件、0 越界、0 root escape | PASS（存在定位质量问题） |
| 源码引用类型 | EvidenceRef 20 / symbol fallback 118 / whole-file fallback 38 | PARTIAL |
| 项目下钻 | 48 个 option 均有项目报告链接；页面实际渲染 96 次（矩阵 + 卡片），6 个目标均存在 | PASS |
| 源码下钻 | 176 个 `file://` 链接均可打开文件 | PARTIAL：显示行范围，但链接本身不能跳到行，且多数范围不是 claim 位置 |
| DeepWiki 三项修订 | guided tour、citation grounding、sections/steps/CitationChip/CodeViewer 均与源码吻合 | PASS |
| rubric | 0/25/50/75/100 公开，标明 reviewer judgment、非 benchmark、±5 | PASS |
| 场景 profile | 4 组权重存在且各自和为 1.0 | PARTIAL：不参与页面推荐或交互 |
| 并列规则 | 同一 comparison class 内应用不确定性并列，不跨类宣布唯一冠军 | PASS |
| 首屏重点 | 每能力显示 5–6 个候选项目，未先给路线/适用场景 | FAIL |
| 当前持久化示例 | schema 1.0、0 项目链接、0 源码链接、旧“自动评分”文案 | FAIL |
| 专项测试 / lint | 16 tests OK；Ruff OK；compileall OK | PASS，但缺真实六仓 golden gate |

## P0

本轮未发现 P0。上一轮 P0-1（仅同名/单路径即可冒充）和 P0-2（symbol ID 冒充 EvidenceRef）已关闭。

## P1

### P1-1：当前持久化六仓报告没有重新生成，用户仍看到上一轮失败版本

当前代码可以渲染 schema 2.0 报告，但仓库中的实际交付物仍是旧版本：

- `examples/reference-selection/technology-selection.json` 为 schema `1.0`，没有 `generated_at`、`tool.catalog_revision`、`score_methodology`、`project.identity_status`、`source_references`、`symbol_ids` 或场景分数。
- `examples/reference-selection/technology-selection.html` 仍包含“当前推荐”和“自动评分”，不包含 `SCORING CONTRACT`、路线内候选说明或 decision handoff。
- 持久化 HTML 中 `href="projects/` 为 0、`href="file://` 为 0。

这不是代码层的潜在问题，而是用户当前真实打开页面就会遇到的问题。修复必须包含从固定六仓重新执行 `compare`、原子替换生成物，并对生成物做 schema/catalog/identity/link golden 校验。

### P1-2：链接“能打开”不等于结论“能下钻”；156/176 个引用不是 claim-level EvidenceRef

`comparison.py:309-358` 会优先使用该文件的第一条 EvidenceRef；没有 EvidenceRef 时使用该文件的第一个 symbol；再没有 symbol 时把整文件作为行范围。这个策略保证链接不为空，却不能保证范围支撑当前 summary、data flow、strength、limitation 或 reuse verdict。

真实六仓分布：

| `reference_scope` | 数量 | 能证明什么 |
|---|---:|---|
| `evidence` | 20 | snippet hash 与工作树行范围一致，但仍未绑定具体 claim |
| `symbol` | 118 | 该 curated 文件存在某个符号；不证明这个符号与当前 claim 有关 |
| `file` | 38 | 只证明固定 bundle 中存在这个文件 |

最清楚的反例是 DeepWiki：

- catalog 对 `evidence-grounding` 的描述是 snippet 反查并校正行号，事实正确；
- 当前生成的 `api/services/codemap.py` 下钻范围却是 `29-31`，内容只是 `_event()`；
- 真正支撑结论的是 `_format_context`（`128-148`）、`_locate_snippet` / `_ground_citations`（`178-222`）和生成后 grounding 调用（`305-309`）。

同样，`CodeMap.tsx` 与 `CodeViewer.tsx` 退化成整文件范围。报告展示了行号，但 `file://` URL 只打开文件，不带可消费的行锚点。用户仍需自己二次搜索。

验收门槛：catalog 的原子 claim 必须显式绑定 `path + line_start + line_end + snippet_sha256`，不能从“该文件第一条 evidence/symbol”推断；至少 summary、关键 data-flow step、关键限制和复用结论各有准确 source ref。项目报告需要支持稳定的 file/symbol/line anchor，比较页应链接到该 anchor，而不只是裸 `file://`。

### P1-3：场景权重是机器字段，不是可用的技术选型流程

`comparison.py:182-228` 定义了四组场景权重，`_profile_scores()` 也为每个 option 计算结果；但推荐仍只使用 capability 默认 `score`，见 `_recommendation_groups()` 与 `build_technology_comparison()`。`comparison_report.py` 只把 profile 名称渲染成四个 tag，没有展示场景分数、没有场景切换，也没有用 profile 选择路线。

其后果可由真实六仓重放直接看到：

- `agent-workflow` 的 `dynamic-agent-runtime` 场景分数里，CodeBoarding 为 92、OpenWiki 为 72；但二者属于不同 class，分数本来不应该用于回答同一个路线问题。
- 由于 `agent-workflow` 六个项目恰好是六种 class，每个 singleton 都自动成为“同类路线候选”，首屏最终列出六个项目。
- `code-parsing` 也列出五个候选；8 个能力里多数首屏卡片列出 5–6 个项目。

避免“跨类唯一冠军”是正确修复，但不能把选择责任全部退回给用户。首屏应先展示“需求场景 → 推荐 comparison class → 首选源码项目 → 为什么 → 关键代价”，项目分数只用于同一路线内比较。CLI 至少应支持显式 profile，或 HTML 支持选择场景后重算；末尾应给出本产品的推荐组合和 PoC 顺序，而不是仅给通用四步说明。

### P1-4：remote/commit 仍来自 index 元数据，而不是从工作树 Git 状态独立读取

`reference_catalog.py:788-810` 对 remote 与 commit 做严格字符串比对，并对必需源码重算 bundle；这已经阻止同名伪仓和源码篡改。但 remote/commit 本身仍直接取自传入 index。

独立探针创建了一个**没有 `.git` 的普通目录**，复制 SourceBridge 33 个必需文件，再在 index 中伪造 canonical remote 与固定 commit；结果仍为 `verified`。修改任一必需文件后会正确变为 `stale`。

在正常 `compare` CLI 中，index 由 `build_index()` 现场构建，因此风险被调用链降低；但公共函数接受外部 index，报告又声称“绑定 remote、commit”，所以身份语义仍比实际保证更强。建议在 identity gate 内从 `project.path` 重新读取 Git root、HEAD 与 origin；非 Git 目录只能称为 `content-equivalent-snapshot`，不能称为 canonical remote/commit verified。

## P2

### P2-1：48 项事实文本已明显改善，但仍有 3 项参考路径/保证边界不完整

逐项复核没有再发现 DeepWiki 的旧错误；上一轮要求增加的 Understand Anything detector 和 CodeBoarding cache/cluster delta 路径已经加入。但仍有三个部分通过项：

1. **SourceBridge / code-graph**：summary 写“提供跨仓关联”，source bundle 增加的 `internal/graph/federation.go` 只定义 `RepoLink` / `CrossRepoRef` 数据类型；同时列入的 `internal/graph/store.go:2102-2138` 明确返回 `federation not supported in in-memory store`。实际 SurrealDB 实现位于 `internal/db/store_federation.go`，却未进入该 claim 的 source paths。
2. **SourceBridge / tutorial-generation**：summary 明确列出 workflow story，但 source paths 没有 `workers/knowledge/workflow_story.py`；“质量 gate 与持久化”也没有精确绑定对应 servicer/state 文件。
3. **OpenWiki / component-discovery**：“最多一次 critic 修订”由 `src/agent/prompts/code.ts:133-136` 和 critic prompt 约定，不是 runtime 状态机硬限制。catalog 应明确标记为 prompt-enforced，避免把流程建议写成执行保证。

这些问题不会改变总体路线判断，但会让“点进去看它怎么实现”落到不完整或错误的文件。

### P2-2：链接安全对正常 CLI 输入足够，但 renderer 对外部 JSON 的边界仍偏宽

- curated bundle 会 resolve 路径并拒绝逃出 repo root，真实 176 个引用均未逃逸。
- 报告正确拒绝非 `file://` source URI，并对 HTML/embedded JSON 做安全转义。
- 但 heuristic `_safe_source_uri()` 只检查 `..` 和绝对相对路径，没有 resolve 后再次检查 symlink；项目链接只检查 `startswith("projects/")`。若未来 renderer 接收不可信 JSON，应再做 canonical path 与相对链接规范化。

当前 CLI 自己生成 slug、scanner 跳过 symlink，因此这是 defense-in-depth，不是当前交付阻断项。

### P2-3：测试已经锁住负向身份，但没有把真实六仓产物变成 CI 门禁

专项 16 个测试全部通过，覆盖了：同名/错 remote、错 commit、缺路径、index hash 篡改、索引后源码篡改、EvidenceRef 与 symbol 分离、HTML 转义和基本链接。

仍缺少：

- 固定六仓的 `6/6 verified` 集成测试；
- 48 项 claim 行范围 golden；
- 176 个 link target 与行锚点集成测试；
- 生成物 schema/catalog revision 新鲜度检查；
- 场景 profile 实际改变路线/候选的测试；
- 浏览器宽屏、窄屏、打印态的可用性回归。

当前 `test_all_48_entries_point_to_files...` 只证明文件存在，不能发现 SourceBridge federation 指到了 stub、DeepWiki grounding 指到了 `_event()` 或示例仍停留在 schema 1.0。

## 六仓覆盖复核

说明：这里区分“catalog 事实是否与源码一致”和“页面是否下钻到精确 claim 行”。路径全部存在并不等于 claim 证据完整。

| 仓库 | 固定身份 | 8 项事实复核 | 本轮结论 |
|---|---|---|---|
| SourceBridge | verified | 6 通过、2 部分通过 | 核心路线准确；code-graph 的 federation 实现路径和 tutorial 的 workflow story 路径仍需补齐。当前许可证显示 unknown，直接代码复用正确标为 `needs-license-review`。 |
| PocketFlow Code2Tutorial | verified | 8 通过 | 固定六步 DAG、文本抓取、LLM abstractions/relations、文件序号校验、全量生成等边界准确。 |
| OpenWiki | verified | 7 通过、1 部分通过 | Deep Agents、OKF、linked Wiki、skills/connectors/checkpoint 路线准确；critic 次数属于 prompt-enforced，需明确保证边界。 |
| Understand Anything | verified | 8 通过 | Tree-sitter、GraphBuilder、layer detector、fingerprint/staleness、Tour/Dashboard/Skill 路线与补充路径一致。 |
| CodeBoarding | verified | 8 通过 | LSP/call graph/Leiden、analysis cache、incremental merge、cluster delta、diagram validation 和固定多 Agent repair 边界均有源码支撑。 |
| DeepWiki Open | verified | 8 通过 | 三个旧错误已修正：它是 guided sections/steps tour，不是调用图；Codemap 有 snippet 行号校正；UI 为 CitationChip → CodeViewer。页面自动选择的行范围仍不精确。 |

合计：**45 通过、3 部分通过、0 明显错误**。这比上一轮的 3 个 DeepWiki 错误有实质提升；剩余问题主要是 source-path/保证粒度，而不是路线分类反转。

### DeepWiki 三项专项证据

| 能力 | catalog 当前说法 | 源码复核 | 结论 |
|---|---|---|---|
| code-graph | sections → steps guided tour，不是源码调用图 | `api/schemas/codemap.py:6-56` 定义 Citation/Step/Section/CodeMap；`api/services/codemap.py` 两阶段生成并可降级 skeleton | PASS |
| evidence-grounding | Codemap 保存 file/snippet/line，用真实源码反查并覆盖模型行号；Wiki 非逐 claim | `_format_context:128-148`、`_locate_snippet:178-198`、`_ground_citations:201-222`、调用点 `305-309` | PASS |
| codemap-visualization | CodeMap 渲染 section/step，CitationChip 打开 CodeViewer 并高亮行 | `CodeMap.tsx:53-64,113-137`；`CodeViewer.tsx:49-80` | PASS |

## 评分与推荐契约复核

### 已通过

- 48 项维度值全部量化到 `0/25/50/75/100`。
- 页面明确写明 reviewer judgment、不是 benchmark。
- option 公开 `score_basis`、`score_uncertainty`、`comparison_class`、license、commit、architecture reference 与 code reuse status。
- 并列只在同一 class 形成 group，不再跨技术对象宣布唯一第一名。
- 四组场景权重各自和为 1.0。

### 仍未通过

- 每个维度为什么是 25/50/75/100 仍没有逐维证据或 reviewer 记录；量化降低了伪精确，但没有变成可复核测量。
- 加权结果仍显示为精确整数，真正的保护来自“人工信号 ±5”文案，而非统计不确定性。
- scenario score 不参与 HTML 的候选、摘要或交互；profile 目前只是元数据。
- singleton comparison class 自动入选，导致“候选”接近“列出所有路线”，首屏没有筛选价值。

## HTML 信息架构与视觉复核

### 当前代码重新渲染后的优点

- 结构已经形成 **摘要 → 量表 → 8 个功能路线矩阵 → 折叠实现/源码卡 → decision handoff**，不再是 48 张大卡平铺。
- 每个功能先显示六仓路线表，详细卡片默认折叠，信息密度明显改善。
- 宽屏下主视觉、功能编号、颜色层级和表格结构清楚；移动端 CSS 会把双列卡片降为单列。
- 正文显式显示 commit、license、人工信号、不确定性、复用边界和源码引用类型。

### 当前代码重新渲染后的问题

- “30 SECOND BRIEF” 每格列出 5–6 个项目名，项目名换行很多，用户看不到路线、适用场景或 trade-off；它更像全量索引而不是重点摘要。
- 功能区的绿色推荐框重复同一批项目名；当 6 个 class 都是 singleton 时，“6 个路线内候选”没有决策含义。
- 场景只显示四个静态标签，用户无法看到“选择动态 Agent 后为何应优先读 OpenWiki，而不是 CodeBoarding 的固定分析 workflow”。
- 末尾 handoff 是通用步骤，没有给出本产品建议组合、冲突、PoC 顺序与尚待验证结论。
- 打印态把项目候选挤进窄列并发生大量断行；打印时详细 `<details>` 的 summary 被隐藏，但闭合 details 的内容不会自动展开，可能丢失源码卡。

`visual-verdict` skill 要求至少一张参考图才能给严格像素对照分数；本任务没有参考图，因此本轮没有伪造 90+ 的正式视觉分。独立截图与 15 页打印预览支持上述可用性结论。

## 独立重放记录

### 专项测试

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_reference_catalog \
  tests.test_comparison \
  tests.test_comparison_report \
  tests.test_cli.CliTest.test_compare_command_writes_feature_first_report -v

Ran 16 tests ... OK
Ruff: All checks passed
compileall: OK
```

### 真实六仓身份

```text
SourceBridge               2a128bf0c846...  verified
PocketFlow Code2Tutorial   05b24cbbb0fe...  verified
OpenWiki                   7531d615216e...  verified
Understand Anything        fe8c5bc59171...  verified
CodeBoarding               8c3f2218c3ec...  verified
DeepWiki Open              4181daa5ebde...  verified
```

SourceBridge 工作树仍有用户已有的 `D LICENSE`；本次没有恢复或修改。必需源码 bundle 未包含该删除文件，因此 identity 仍 verified；项目 license 为 unknown，HTML 正确要求 license review。

### 当前函数基于真实六仓索引重建

```text
projects: 6
capabilities: 8
options: 48
curated options: 48
identity: 6/6 verified
source references: 176
source reference scope: evidence 20 / symbol 118 / file 38
EvidenceRef occurrences: 119
unique project/evidence pairs: 72
dangling EvidenceRef: 0
missing project reports: 0
missing source files: 0
invalid line ranges: 0
repo-root escapes: 0
rendered project hrefs: 96 (48 options × matrix/card)
rendered source hrefs: 176
```

### 负向身份重放

```text
same basename + wrong remote              -> unverified / no curated
canonical remote + wrong commit           -> stale / no curated
missing one required source path           -> no curated
tampered index file SHA                    -> no curated
modified required file after indexing      -> stale / no curated
plain non-Git directory + copied exact
bundle + spoofed remote/commit metadata     -> verified (residual P1-4)
```

## 通过复审前的验收门槛

1. 从真实固定六仓重新生成并提交 schema 2.0 的 HTML/JSON；CI 拒绝 schema/catalog/identity 过期的示例。
2. curated claim 使用显式行范围与 snippet hash，不再把“第一个 evidence/symbol/整文件”当成 claim 下钻。
3. DeepWiki grounding 链接直接落到 `128-148`、`178-222`、`305-309` 等实现；其余 48 项按同一标准建立 golden。
4. SourceBridge code-graph 增加实际 `internal/db/store_federation.go` 实现并明确 in-memory store 的 stub 限制；tutorial 增加 workflow story 实现路径。
5. OpenWiki critic 次数明确标注 prompt-enforced，而不是 runtime guarantee。
6. 让用户显式选择场景，按“场景 → comparison class → 同类候选”形成真正推荐；scenario score 必须进入可见决策或删除，不能只存在 JSON。
7. 首屏每个能力只展示 1–3 条路线建议及适用/不适用条件，不再把 5–6 个项目名全部当重点。
8. 末尾输出与本产品目标对应的推荐组合、PoC 顺序、许可证/部署风险和未决项。
9. identity gate 对 remote/commit 从工作树 Git 重新读取；如果只验证内容 bundle，状态名称必须诚实降为 `content-equivalent-snapshot`。
10. 加入固定六仓端到端 golden：6/6 identity、48 facts、claim refs、0 dangling、176 link target/anchor、HTML 摘要结构和生成物新鲜度。

## 最终判断

**REQUEST CHANGES。**

这次修复不是“没做”：两个 P0 已关闭，DeepWiki 三个错误事实已纠正，异构技术对象不再被强行选唯一冠军，license/commit/不确定性也已进入正文。当前代码已经是一个可靠得多的“六仓阅读导航生成器”。

仍未达到的，是用户真正要的“轻松完成技术选型”：交付 HTML 还是旧版；新页面的首屏几乎把所有项目都列为候选；大多数源码范围不能直接证明当前结论；场景权重没有进入可见决策。完成上述四类修复并重新生成真实产物后，再进行第三次独立复审。
