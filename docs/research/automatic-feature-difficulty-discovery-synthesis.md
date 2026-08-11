# 自动识别“功能实现语义难点”能力的本地 clone 研究

## 结论

这 8 个项目里，没有一个真正把“功能实现的语义难点”做成第一类、可直接计算的输出。

它们大体分成 4 层：

1. `结构层`：抽文件、函数、类、依赖、调用图、模块树。
2. `执行流层`：追调用链、PDG、impact、flow、route、step。
3. `维护热点层`：看变更影响、聚类漂移、增量基线、覆盖率、失败/降级。
4. `LLM 摘要层`：把结构和流翻译成自然语言、导览、图注、教程。

所以，若把“语义难点”定义为“哪些实现点最容易出错、最难改、最值得先看”，这些项目多数只能**间接推断**，还没有一个把它当成独立评分目标来自动发现。最接近的是 `Understand Anything`，其次是 `GitNexus` 和 `CodeBoarding`，但它们都更像“可解释导航/影响分析”而不是“难点探测器”。

## 采用矩阵

| 项目 | 结构识别 | 执行流识别 | 维护热点 | LLM 摘要 | 是否真的自动识别语义难点 |
|---|---|---|---|---|---|
| GitNexus | 强 | 强 | 中 | 弱 | 否，偏 impact / PDG / execution flow |
| CodeBoarding | 强 | 中 | 强 | 强 | 否，偏 clustering + incremental update |
| CodeWiki | 强 | 中 | 中 | 强 | 否，偏 dependency graph + docs generation |
| DeepWiki Open | 强 | 中 | 弱 | 强 | 否，偏 codemap / wiki 结构生成 |
| PocketFlow code2tutorial | 中 | 弱 | 弱 | 强 | 否，偏 tutorial / abstraction / relationship |
| Codebase-to-Course | 中 | 弱 | 弱 | 强 | 否，纯教学编排，不是难点检测 |
| Understand Anything | 强 | 强 | 强 | 强 | 部分接近，但仍是“图 + 摘要 + impact” |
| Serena | 强 | 强（符号级） | 弱 | 弱 | 否，偏 IDE 语义工具，不做全局难点发现 |

## 逐仓库证据

### 1) GitNexus

它确实能自动抓到 `结构` 和 `执行流`，也能做一部分 `维护热点` 判断，但没有“语义难点”这个直接输出。

- `impact` 会返回上游 caller、process、risk，还支持 `--pdg` 级别的 statement 影响分析，明确是 blast radius / control-data flow 方向，不是 feature difficulty score。[`repo/gitnexus/AGENTS.md`#L120](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/AGENTS.md#L120)
- `query` / `context` / `processes` / `process/{name}` 是按 execution flow 组织检索与追踪。[`repo/gitnexus/AGENTS.md`#L124](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/AGENTS.md#L124) [`repo/gitnexus/AGENTS.md`#L140](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/AGENTS.md#L140)
- `UNKNOWN` 被明确要求当成“未解”，不是低风险。这说明它更关注分析置信度，不是自动判定难点。[`repo/gitnexus/AGENTS.md`#L123](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/AGENTS.md#L123)

判断：

- 自动发现：调用链、执行流、影响面、未解析风险。
- 不自动发现：哪一段实现“语义上更难”。

### 2) CodeBoarding

它是这组里最像“从结构推断维护难度”的项目之一，因为它把 `cluster`、`incremental update`、`changed members`、`ownership`、`collision` 这些都做成了确定性状态。

- `plan_scope_update()` 明确说：结构先由聚类推导，LLM 只负责命名；如果群组没变化且内容没变，甚至可以不生成 operation。[`repo/codeboarding/diagram_analysis/scope_plan.py`#L1](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/diagram_analysis/scope_plan.py#L1)
- `previous_ownership()` 用 method 级别的归属来避免 cluster id 重编号造成的漂移，还强调跨语言 qname 可能冲突，因此按语言和文件范围隔离 owner map。[`repo/codeboarding/diagram_analysis/scope_plan.py`#L44](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/diagram_analysis/scope_plan.py#L44)
- `ComponentJson`、`RelationJson`、`FileCoverageSummary`、`AnalysisMetadata` 都是强 schema 化的数据合同，核心字段是 cluster id、source cluster ids、method index、file coverage、source tree hash。[`repo/codeboarding/diagram_analysis/analysis_json.py`#L23](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/diagram_analysis/analysis_json.py#L23)
- `incremental_orchestrator` 体现的是 call graph 的增量重建，不是语义难点打分。[`repo/codeboarding/static_analyzer/incremental_orchestrator.py`#L1](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/static_analyzer/incremental_orchestrator.py#L1)

判断：

- 自动发现：结构簇、簇漂移、变更热点、空簇失败、跨语言碰撞。
- 不自动发现：哪些 feature 实现最难。

### 3) CodeWiki

它的核心是 `dependency graph + module clustering + LLM 文档生成`。结构和流很强，语义难点依然是间接的。

- README 直接把它定位成“repository documentation generation / architecture-aware analysis”。[`repo/codewiki/README.md`#L1](/Volumes/T7/workspace/ontology/graph/repo/codewiki/README.md#L1)
- `IDE_DRIVEN_GUIDE` 明确列出 4 个 LLM 阶段：module clustering、per-module docs、sub-module recursion、parent overview；同时说 dependency analysis / graph construction / topological sorting / Mermaid validation 不依赖 LLM。[`repo/codewiki/IDE_DRIVEN_GUIDE.md`#L18](/Volumes/T7/workspace/ontology/graph/repo/codewiki/IDE_DRIVEN_GUIDE.md#L18)
- 另一个关键点是 `analyze_repo` / `read_code_components` / `save_module_tree` 这类工具把 bulky state 写到 workspace 文件里，说明它解决的是大仓库文档编排，不是难点评分。[`repo/codewiki/IDE_DRIVEN_GUIDE.md`#L66](/Volumes/T7/workspace/ontology/graph/repo/codewiki/IDE_DRIVEN_GUIDE.md#L66)

判断：

- 自动发现：依赖结构、模块层级、文档缺口、处理顺序。
- 主要是 LLM 摘要层，不是难点检测层。

### 4) DeepWiki Open

它更像 `source-grounded wiki / codemap generator`，前置是 RAG + 结构解析，后置是 LLM 生成结构化 wiki。

- `api/services/codemap.py` 写得很直接：两步 LLM flow，先 skeleton 再 enrich；前面靠 RAG 取回代码片段，后面才写 prose/diagram。[`repo/deepwiki-open/api/services/codemap.py`#L1](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/codemap.py#L1)
- `generate_codemap()` 先做 RAG retrieval，再做 skeleton，再做 diagrams/guides；LLM 失败时会回退 skeleton，说明它优先保证“可用 codemap”，不是探测难点。[`repo/deepwiki-open/api/services/codemap.py`#L225](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/codemap.py#L225)
- `_determine_structure()` 读取本地 clone 的 file tree + README，然后问 LLM 生成 wiki structure XML；`parse_wiki_structure()` 只负责解析这个 XML。[`repo/deepwiki-open/api/services/wiki/tasks.py`#L315](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/tasks.py#L315)

判断：

- 自动发现：repo 结构、页面结构、源码证据、图注。
- 不自动发现：实现难点本身。

### 5) PocketFlow code2tutorial

它是教程生成器，不是难点探测器。它会分析抽象与关系，但目标是把代码讲成教程。

- README 说它“analyzes entire codebases to identify core abstractions and how they interact”，并把产物做成 beginner-friendly tutorials。[`repo/pocketflow-code2tutorial/README.md`#L15](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/README.md#L15)
- `main.py` 只保留输入参数和共享状态：repo/local dir、include/exclude、max_size、language、max_abstractions、cache。[`repo/pocketflow-code2tutorial/main.py`#L39](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/main.py#L39)
- `flow.py` 只是线性流程：FetchRepo → IdentifyAbstractions → AnalyzeRelationships → OrderChapters → WriteChapters → CombineTutorial。[`repo/pocketflow-code2tutorial/flow.py`#L12](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/flow.py#L12)

判断：

- 自动发现：抽象、关系、章节顺序。
- 不自动发现：语义难点排名；它只是在讲解这些抽象。

### 6) Codebase-to-Course

这份 skill 是“课程编排规则”，不是代码难点评估器。

- 它要求先读 README / 入口 / UI，提炼 actors、data flows、gotchas、tech stack，然后写课程。[`repo/codebase-to-course/SKILL.md`#L55](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md#L55)
- 课程模块的重点是“why should I care”、交互、类比、测验、英文翻译块，不是自动评分 feature difficulty。[`repo/codebase-to-course/SKILL.md`#L69](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md#L69)
- 输出是 HTML course，而不是一个结构化难点图谱。[`repo/codebase-to-course/SKILL.md`#L127](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md#L127)

判断：

- 自动发现：教学素材、流程、 gotchas。
- 不自动发现：功能实现语义难点。

### 7) Understand Anything

这是这组里最接近“语义难点发现”的项目，但它仍然没有把“难点”直接作为字段输出；它做的是 `knowledge graph + semantic search + diff impact + guided tours + layer mapping`。

- README 说它分析项目、构建文件/函数/类/依赖的知识图谱，并提供 interactive dashboard。[`repo/understand-anything/README.md`#L51](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md#L51)
- 它明确区分 `Tree-sitter (deterministic)` 和 `LLM (semantic)`：前者负责 imports/exports/call sites/inheritance，后者负责 plain-English summaries、tags、architectural layers、business-domain mapping、guided tours。[`repo/understand-anything/README.md`#L322](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md#L322)
- 它还提供 `Diff Impact Analysis`、`Layer Visualization`、`Guided Tours`、`Fuzzy & Semantic Search`。[`repo/understand-anything/README.md`#L64](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/README.md#L64)
- `generate-large-graph.mjs` 明确把 `complexity` 当测试字段，且为了避免图形库崩溃，生成边时强制 forward-only、避免 cycle，这说明 benchmark 更偏图健壮性，不是难点发现本身。[`repo/understand-anything/scripts/generate-large-graph.mjs`#L73](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/scripts/generate-large-graph.mjs#L73)
- `large-monorepo.md` 还明确写了 benchmark 不跑 LLM、不算 token、不生成 knowledge graph；它只做 deterministic harness。[`repo/understand-anything/docs/benchmarks/large-monorepo.md`#L3](/Volumes/T7/workspace/ontology/graph/repo/understand-anything/docs/benchmarks/large-monorepo.md#L3)

判断：

- 自动发现：结构、语义摘要、层级、影响面、增量变化。
- 这是最适合做“语义难点候选排序”的底座，但当前仍是间接推断。

### 8) Serena

Serena 不是难点发现器，而是 `symbol-level semantic IDE`。它擅长精确定位、重构、调试，不擅长从全局自动挑出最难功能。

- README 开头就把它定义成 semantic retrieval / editing / refactoring / debugging tool，按 symbol level 工作。[`code/serena/README.md`#L17](/Volumes/T7/workspace/ontology/graph/code/serena/README.md#L17)
- 它的 retrieval 能 find symbol、references、declaration、implementations、type hierarchy、diagnostics。[`code/serena/README.md`#L136](/Volumes/T7/workspace/ontology/graph/code/serena/README.md#L136)
- refactoring / symbolic editing 很强，但仍然是 IDE 式语义操作，不是代码库级 difficulty scoring。[`code/serena/README.md`#L156](/Volumes/T7/workspace/ontology/graph/code/serena/README.md#L156)

判断：

- 自动发现：符号关系、引用、实现、类型层级、诊断。
- 不自动发现：feature 级语义难点。

## Waku Graph 信号映射

下面按你点名的信号，回答“哪些能自动发现，靠什么层”。

| Waku 信号 | 能自动发现吗 | 主要依赖的层 | 证据最强的项目 | 说明 |
|---|---|---|---|---|
| wave | 能 | 结构 + 流程阶段 | CodeBoarding / CodeWiki / Understand Anything / DeepWiki Open | 只要系统有 wave/phase/batch/leaf-first/recursive 这类阶段，就能自动抓到；这是流程波次，不是语义难点。 |
| state collision | 部分能 | 持久状态 + ID 合同 + baseline | CodeBoarding / CodeWiki / Understand Anything | 例如 cluster id 归属、session metadata、pairId mismatch、跨语言命名冲突。 |
| join | 能 | 结构图 + 执行流图 | GitNexus / CodeBoarding / CodeWiki / Understand Anything | join 本质是 fan-in / merge point；call graph、relation graph、dependency graph 都能看见。 |
| router | 部分能 | 执行流 / route / branch | GitNexus / Understand Anything / DeepWiki Open / PocketFlow | 只要有 process/flow/step/route，就能从图里定位；但需要控制流或流程模型。 |
| cycle | 部分能 | 依赖图 / 控制流图 | Understand Anything / CodeWiki / GitNexus / CodeBoarding | 能发现环，但很多项目会刻意规避或不把它作为主输出；Understand Anything 的大图生成器甚至默认避免 cycle。 |
| fail-open | 能 | LLM 失败回退 / degraded path | DeepWiki Open / Understand Anything / CodeWiki | 这些项目都明确允许 skeleton 回退、skipped files、degraded reports；这是可自动检测的失败开放行为。 |
| checkpoint gap | 能 | 持久化基线 / session / metadata | CodeWiki / Understand Anything / CodeBoarding | 缺 metadata、缺 baseline、dirty graph、session 未关闭等，都能自动识别。 |

### 逐项落地

1. `wave` 最容易自动化，因为这些项目大多都是分阶段 pipeline，而不是一次性答案。
2. `state collision` 只有在状态是显式 schema 化的时候才好抓；靠纯 LLM 摘要抓不到。
3. `join` 和 `router` 是图分析最典型的自动信号，优先靠 graph / call graph / flow。
4. `cycle` 可以抓，但要区分“能检测”与“值得当成难点输出”；不少项目只把它当健壮性问题。
5. `fail-open` 和 `checkpoint gap` 更像系统质量信号，适合做维护热点过滤器，而不是业务语义信号。

## 推荐混合管线

如果目标真的是“自动识别功能实现的语义难点”，最稳的做法不是单一 LLM，也不是纯图算法，而是混合管线：

1. `Deterministic ingestion`
   - 抽 file / function / class / import / call / inheritance / config / route。
   - 产出稳定 ID、hash、coverage、baseline。
2. `Graph analytics`
   - 算 fan-in / fan-out、join 点、router 点、cycle、cluster drift、impact radius、changed-component wave、checkpoint gap、state collision。
3. `Hotspot ranking`
   - 先按变更面、耦合、未解析风险、跨层跳转、失败/降级路径做候选排序。
4. `LLM semantic labeling`
   - 只对 top-k 疑难子图生成 plain-English difficulty notes、gotcha summary、why-it-matters。
5. `Freshness guardrails`
   - 没有 baseline、metadata 或 graph freshness 不通过时，不给“难点已确认”的结论，只给 degraded / unknown。

### 这条管线和本地 clone 的对应关系

- `GitNexus` 提供第 2 步里最强的 impact / PDG / flow 证据。
- `CodeBoarding` 提供第 1、2、3 步里最强的结构化 cluster / incremental baseline 证据。
- `CodeWiki` 和 `DeepWiki Open` 提供第 1、4 步里最强的 LLM 结构化摘要和文档化样式。
- `Understand Anything` 是最适合做整条管线的底座，因为它同时有 deterministic parse、semantic layer、guided tour、impact analysis 和 incremental update。
- `Serena` 适合接到第 4 步之后做局部符号级精修，不适合做全局难点发现。

## 最终判断

如果你要的是“自动识别哪一块 feature 实现最难”，这 8 个项目里没有一个已经完全做到。

如果你要的是“自动找出可能难改、影响大、结构复杂、需要先看的区域”，`Understand Anything + GitNexus + CodeBoarding` 的组合最接近；`CodeWiki` 和 `DeepWiki Open` 更适合作为 LLM 摘要层；`Serena` 是精确符号工具，不是难点探测器；`Codebase-to-Course` 和 `PocketFlow code2tutorial` 本质是教学转译，不是难点识别。
