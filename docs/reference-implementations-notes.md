# 开源同类实现精读笔记与落地记录

> 2026-08-23。动机：用户要求「clone 开源同类项目，基于真实实现来落地」，而不是只看 README 做二手描述。
> 物料：`/Volumes/T7/kb/repo/参考实现/` 下 deepwiki-open（完整）、RepoAgent（部分提取）、aider（关键文件 jsDelivr 拉取）。
> 所有行号对应当日 main 分支。

## 一、aider repomap.py（867 行，`aider/repomap.py`）

### 数据结构
- `Tag = namedtuple("Tag", "rel_fname fname line name kind")`（:38）——定义/引用统一为标签五元组；
- 双层 diskcache + sqlite 按文件 mtime 缓存 tags（:110-140）。

### 符号提取（get_tags_raw，:291-350）
- tree-sitter + 每语言 `.scm` 查询文件（`aider/queries/tree-sitter-language-pack/*.scm`）；
- 标签只分两类：`name.definition.*` → kind="def"，`name.reference.*` → kind="ref"（:315-325）；
- rust-tags.scm 的定义模式：struct/enum/union/type→definition.class、fn→definition.function、trait→definition.interface、mod→definition.module、macro→definition.macro；引用模式：call_expression/macro_invocation→reference.call、impl_item→reference.implementation；
- **兜底**：只有 def 没有 ref 的语言（如 cpp 的 scm 不含引用模式），用 pygments lexer 抽 Name token 补引用（:333-350）。

### 图构建与加权（get_ranked_tags，:361-514）
- `defines[ident] = {文件}`、`references[ident] = [引用文件...]`（:448-452）；
- 个性化向量：chat 文件 +（chat 中提到的文件路径/ident 命中的文件）获得 100/N 的 personalization（:425-435）；
- **边权乘数（:487-499）**：
  - ident 被用户提到 ×10；
  - 长特定名（snake/kebab/camel 且 ≥8 字符）×10；
  - 下划线私有 ×0.1；
  - 被超过 5 个文件定义 ×0.1（超常见符号降权）；
  - 引用方在 chat 文件里 ×50；
  - 引用次数 `sqrt(num_refs)` 缩放（高频低价值引用不主导）。
- 无引用定义补自环 weight=0.1（:481-486）。

### 排序与渲染（:516-580, to_tree :748-780）
- `nx.pagerank(G, weight="weight", personalization=…, dangling=personalization)`；
- rank 从文件分摊回符号：`src_rank × edge_weight / out_total`（:520-530）；
- 排序后渲染：每文件列 lois（lines of interest），用 TreeContext 输出「定义行上下文树」，token 超预算截断。

## 二、deepwiki-open（Next.js + FastAPI）

### wiki 生成三步（api/services/wiki/）
1. **structure.py（251 行）**：文件树 + README 喂给 LLM → 输出 `<wiki_structure>` XML（section/page 两级，page 含 importance、relevant_files、related_pages）。解析有**两层兜底**：严格 XML 失败 → 正则逐块恢复；响应截断（缺 `</wiki_structure>`）→ 从开标签抢救到文本尾 + 合成闭标签（:194-205）。comprehensive 模式 8-12 页，concise 4-6 页（prompts.py:223）。
2. **content.py（151 行）**：逐页生成，页内必须 ≥5 个源文件引用、页首 `<details>` 列引用文件（prompts.py:36-49）。
3. **prompts.py 页面级强制**：Mermaid 图规范（TD 方向、sequenceDiagram 8 种箭头、box/loop/alt 结构）、引用格式 `Sources: [path:line]()`（空括号由前端解析为真链接）、「只准基于给定文件，不准外部知识」（:108-120）。

### codemap 两段式（api/services/codemap.py，298 行）
- **RAG 检索 → skeleton（骨架 JSON）→ enrich（补图和 guide）**，NDJSON 流式进度；
- **JSON 鲁棒解析**（:64-126）：剥 ``` 围栏 → 平衡括号扫描出第一个顶层对象 → 常见 glitch 修复（尾逗号、`" "key":`）→ 失败重试（新 streamer 再试 3 次）；
- **引用行号接地**（_ground_citations :189-213）：LLM 给的行号不可信，但 snippet 是逐字复制的——**在真实文件里反查 snippet 位置得到真行号**，覆盖 LLM 猜的行号；
- enrich 失败降级用 skeleton，不整体失败（:268-275）。

### RAG 层（api/rag/pipeline.py，493 行）
- adalflow TextSplitter → ToEmbeddings → LocalDB pickle 持久化；
- LineTrackingTextSplitter（:174-208）：给每个 chunk 标注真实 1-based 起止行（后续引用行号接地、上下文呈现都靠它）；
- 超大文件（>8192×10 token）直接跳过（:126-130）。

## 三、RepoAgent（runner.py 628 + doc_meta_info.py 1026 + chat_engine.py 132）

### 核心：对象级依赖拓扑生成
- AST 解析每个 py 文件 → DocItem 树（file→class→function→sub），记录 `reference_who`（我调用谁）/`who_reference_me`（谁调用我）（doc_meta_info.py:560-608）；
- **get_task_manager（:622-700）**：拓扑排序生成文档任务序——叶子节点先做（父文档要引用子文档的生成结果做上下文）；**真实环引用处理**：bind 类接口会成环，取 second_best_break_level 最小的节点先做并打印警告（:646-663 注释里举了 ChatDev 五子棋 on-click/show-winner/restart 成环实例）；
- 生成时 prompt 同时带上「我调用的对象的文档 + 调用我的对象的文档」（chat_engine.py:40-66）——文档也按依赖序生成，引用方文档引用被引用方已生成的文档。

### 增量与多线程
- ChangeDetector 按 git diff 找变更文件（file_handler.py:114-），只重生成受影响对象；.project_hierarchy checkpoint 目录持久化全部 DocItem 树与文档版本（runner.py:41-54）；
- ThreadPoolExecutor + TaskManager 依赖感知调度（multi_task_dispatch.py）。

## 四、三家对比 → repolens 落地决策

| 维度 | deepwiki-open | aider | RepoAgent |
|---|---|---|---|
| 覆盖保证 | ❌ RAG 相似度召回，无 exact-once | ✅ 全文件入图 | ✅ 全对象入拓扑 |
| 重要性排序 | ❌ 无 | ✅ 加权 PageRank + 个性化 | ❌ 深度优先（叶子先做） |
| 行号可信 | chunk 自标行 + snippet 反查接地 | tree-sitter 精确 | AST 精确 |
| 产物形态 | wiki 页 + codemap（最接近教学产物） | 无文档产物 | 对象级 md 文档树 |
| 鲁棒解析 | 两层 XML 兜底 + JSON 修复重试 | — | — |

**落地结论**：
1. **采纳 aider 加权 PageRank 做机械层排序**——写 `tools/cg_rank.py`：直接读 codegraph.db（nodes/edges 表），把 aider 的边权乘数、sqrt 缩放、自环、personalization 全部移植，把「tree-sitter 抽符号」替换为「codegraph 已建好的符号图」。**工程化修正**：per-ident 笛卡尔积加边会爆炸（`new` 这种符号 100 定义文件 × 500 引用文件），加 COMBO_BUDGET=2000 + TOP_REFERENCERS=100 截断，并把 MultiDiGraph 聚合成 DiGraph。
2. **采纳 deepwiki 的 snippet 反查接地**进 skill 合同——已写进 cg_rank.py 头注；LLM 行号一律不信，逐字 snippet 在真实文件反查（repolens 报告合同的「行号只对快照有效」再加一层防伪）。
3. **采纳 RepoAgent 拓扑序**为后续候选——若 repolens 做对象级批量生成，按依赖拓扑排任务序（叶子先做）+ 环用 second-best 破环，不引入 RepoAgent 的 AST 重解析（codegraph 已有）。
4. **不采纳 embedding RAG**：与 exact-once 覆盖合同冲突（上轮已定，本轮读完实现更确认——它的 retrieval 只保证「相似」，不保证「全量」）。

## 五、cg_rank.py 在 codex 仓的对照实测（2026-08-23）

图规模：57,489 定义节点 / 214,172 跨文件引用边，耗时 ~30 分钟（T7 外接盘 sqlite 扫描 ~1ms/行占大头）。

**无 seed（纯 PageRank）TOP5**：utils/path-uri、utils/absolute-path、context-fragments/fragment、http-client/request、core/internal_model_context——**全是通用工具函数**（starts_with/into/as_bytes/to_path_buf），业务文件全军覆没。

**带入口 seed（cli/main.rs + core/codex.rs + app-server/lib.rs，aider personalization ×50 语义）TOP 变化**：
- seeds 自身按预期登顶（app-server/lib.rs 0.097、cli/main.rs 0.096）；
- **用户可见路径上的业务文件浮出**：`core/src/config/mod.rs :: find_codex_home`、`login/src/auth/manager.rs :: shared_from_config`、`protocol/src/protocol.rs`、`core-plugins/src/marketplace.rs`、`http-client/src/outbound_proxy.rs :: HttpClientFactory`——无 seed 版这些全部被通用工具压住。

**结论**：验证了 aider personalization 的必要性（这也是它"chat 文件 ×50"存在的原因）；同时通用工具仍会渗入 TOP（它们确实被处处引用）——所以合同定为「cg_rank.py 机械产出候选 + agent 语义复核（入口可达/状态机/算法信号）」，机器排序是候选清单不是最终答案。

## 七、PocketFlow-Tutorial-Codebase-Knowledge（教程型产物，最对口参考）

> 物料：`/Volumes/T7/kb/repo/参考实现/pocketflow-tck/`（nodes.py 880 行全文 + docs/ 20+ 仓库已生成教程样例）。

管线五步（nodes.py）：FetchRepo → IdentifyAbstractions（5–10 个抽象，带 file_indices）→ AnalyzeRelationships（mermaid 图边）→ OrderChapters（教学排序）→ WriteChapters（逐章生成）→ CombineTutorial（index.md + 关系图）。

### md 效果核心手法（WriteChapters prompt，nodes.py:678-725）
1. **每章一个中心用例**：「Start with a central use case as a concrete example. The whole chapter should guide the reader to understand how to solve this use case」——全章围绕一个具体用例展开，不是功能罗列；
2. **代码块 <10 行**：「Each code block should be BELOW 10 lines! If longer code blocks are needed, break them down into smaller pieces and walk through them one-by-one. Aggressively simplify」+ 每个代码块后紧跟一段新手友好解释；
3. **先无码走查再有码深潜**：「First provide a non-code or code-light walkthrough on what happens step-by-step」→ 再「dive deeper into code with references to files」；
4. **章节互链**：提及其他抽象必须用 Markdown 链接 `[Chapter Title](filename.md)`；
5. **前文摘要续写**：写第 N 章时把已写章节全文作为上下文注入，开篇「brief transition from the previous chapter」——避免章节间信息孤岛和重复；
6. **序列图 ≤5 参与者**：sequenceDiagram「keep it minimal with at most 5 participants」；
7. **大量类比**：「Heavily use analogies and examples throughout」；
8. **全抽象覆盖校验**：OrderChapters 输出必须含全部索引，缺一即 ValueError 重试（nodes.py:524-527）——覆盖完整性靠结构化校验兜底，不靠 prompt 祈祷。

### 实际生成样例（docs/Codex/03_agent_loop.md，339 行）
- 开篇即上一章链接 + 回顾 + 「where does that input *go*?」悬念式过渡；
- "What's the Big Idea?" 一节用「私人助理接任务」类比引入；
- mermaid 图先给全流程，代码块带 `// File: ... (Highly Simplified)` 标注 + 简化注释；
- 全文代码块均在 10-20 行内且紧跟解释段。

## 八、OpenDeepWiki（AIDotNet，.NET 9 + SK，wiki 型产物）

> 物料：`/Volumes/T7/kb/repo/参考实现/opendeepwiki/`（4 个 prompt 模板全文：catalog-generator 215 行 / content-generator 1217 行 / incremental-updater 915 行 / mindmap-generator 181 行）。
> Prompt 即外部 md 模板（FilePromptPlugin.cs：`{{变量}}` 替换），系统 prompt 跨仓库不变——「runtime context 当任务数据」模式。

### catalog-generator.md：目录质量规则（与 BF 账本同源的问题）
- **按读者心智模型组织，不按文件树**（rules 1）："Organize from the reader's mental model, not from the file tree"；
- **右尺寸覆盖，禁固定页数**（rule 2）："Decide catalog size from repository complexity... Do not use numeric page targets, lower bounds, upper bounds, quotas, or caps"；
- **禁过度压缩**（rule 3）：把多个独立系统藏进几个超大章 = 失败，哪怕每章很长；
- **禁文件/类页面**（rule 8）：不因文件/类存在就建页——与 repolens「顶级业务功能四要件」同构；
- **父节点只做导航**：有 children 的父节点不生成正文，内容只在叶子节点；「Avoid parent nodes with only one child unless the grouping materially improves navigation」；
- **定稿前自检**："Does this page combine unrelated capabilities that deserve separate deep dives? If yes, split them"；
- 反模式清单：按代码结构组织而非按产品/工作流、过度压缩、薄页列表、生成前不读入口、README 提到的大功能遗漏。

### content-generator.md：正文质量规则（1217 行，最重的单文件 prompt）
- **8 条绝对规则**：禁止编造代码示例；每个代码块必须紧跟 Source 引用块（文件名 + 运行时基 URL + 行锚点）；禁止猜 API 签名；写前必须读实现；工具调用强制；mermaid 必须反映真实（组件名与真实类名一致）；信息缺失诚实声明；强制三阶段 Gather→Think→Write；
- **结构模板**（§6.1）：H1 标题 → 一句话简介 → **Purpose and Scope（本页覆盖什么/兄弟页负责什么）** → Overview → Architecture（≥1 mermaid）→ 主体分节 → Core Flow（sequenceDiagram）→ Data Model → Usage Examples → Configuration 表 → API Reference → **Failure Modes/Edge Cases/Concurrency** → Performance/Operations → Extension Points → Tests → Related Links；
- **增量写长文档**：WriteDoc 写头几节 → AppendDoc 逐节追加——绕开单响应 token 上限；
- **深度优先**："A thin or summary-level page is a FAILURE" / "prefer MORE depth"；但**边界内深**（"Depth Without Over-Broadening"）：不吸收兄弟页主题；
- **mermaid 语法细则**（§7.3）：subgraph ID 加 `sg_` 前缀防与节点 ID 撞、标签必须引号包裹、classDiagram 用 `}` 不用 `end`、ER 标识符只用字母数字下划线——全是渲染炸掉的实测坑；
- **长度遵循实质**："Length follows substance... Never truncate coverage to save space"；
- **代码标识符不翻译**（§10.2）：变量/函数/类名、文件路径、配置键、API 端点、命令行参数一律原文。

### incremental-updater.md（915 行，增量更新）
按 git diff 找变更 → 判定影响页（直接/间接依赖）→ 只重写受影响文档，与 RepoAgent ChangeDetector 同思路；含「翻译/脑图/Graphify 工件」等后续 worker 排队机制。

## 九、五家对比 → md 效果保证条款落地（2026-08-24 追加）

| 维度 | PocketFlow-TCK | OpenDeepWiki | deepwiki-open | repolens 现状 | 落地 |
|---|---|---|---|---|---|
| 覆盖 | 章序=抽象全排列校验 | 目录自检反模式清单 | RAG 召回（无保证） | ✅ exact-once 账本 | 保持 |
| 编造防护 | — | Source 引用块强制 + 禁猜签名 | 只准基于给定文件 | ✅ 行号接地 | 保持 + 吸收「Source: 文件名+行锚点」格式 |
| 中心用例驱动 | ✅ 每章一个中心用例 | — | — | 部分（痛点开头） | **吸收**：每节以具体用例贯穿 |
| 代码块纪律 | ✅ <10 行 + 拆小逐段讲 | 无长度限制（引用真实源） | 无 | 无明确纪律 | **吸收**：<10 行优先，超长拆段 |
| 章节衔接 | ✅ 前文摘要注入 + 过渡段 + 互链 | Related Links + For X see Y | related_pages | 弱 | **吸收**：前后章过渡 + 互链 |
| mermaid 规范 | ≤5 参与者 | sg_ 前缀/引号/语法细则 + 类型选型表 | TD+箭头规范 | 无细则 | **吸收**：语法细则 + 图型选型表 |
| 目录组织 | 抽象驱动 | 读者心智模型 + 右尺寸 + 反模式 | section/page 两级 | BF 账本 | **吸收**：读者心智模型原则 |
| 深度承诺 | 新手向 | "thin page is a FAILURE" | — | 无显式承诺 | **吸收**：薄页即失败 |
| 逐节增量写 | — | WriteDoc+AppendDoc | — | — | 参考（agent 无单响应上限问题时不必） |

**落地改动**（已写入 SKILL.md 阶段三）：
1. **每节一个中心用例**：核心功能小节以「一个真实可跑的具体用例」贯穿（输入→命令→输出），不罗列特性；
2. **代码块纪律**：<10 行优先；超过必须拆成小段逐段讲；每个代码块标注 `文件:行号` 或注释 `// File: path`；
3. **章节衔接**：非首节开头一句上节回顾 + 链接；提及其他功能/其他章必须互链；
4. **Mermaid 语法细则**：节点/子图 ID 防撞（sg_ 前缀）、标签必引号、classDiagram 用 `}`、ER 标识符限字母数字下划线；每图配 5-15 节点 + 类型选型（架构 flowchart / 流程 sequenceDiagram / 数据 erDiagram / 状态 stateDiagram-v2）；
5. **读者心智模型**：目录/功能编排按使用者旅程而非文件树；「把多个独立能力藏进一章 = 失败」反模式自检；
6. **薄页禁令**：每个核心功能小节至少有中心用例+逐跳因果+边界坑；只有标题式一句话的小节必须合并或深化。

## 十、遗留 / 下一步

- [ ] cg_rank.py 在 codex 仓的实测结果核对（跑完后把 TOP 文件/符号 vs 手工选的 L3 清单对比）；
- [ ] networkx/numpy 已装入 workbuddy venv（envs/default），SKILL.md 引用工具路径；
- [ ] RepoAgent 完整 tarball 因网络限速未拉全（core 目录部分缺），但关键机制（拓扑序/环处理/增量）已从已解压部分取齐；
- [ ] deepwiki 的「页面强制 ≥5 源文件引用 + `<details>` 引用块」是否吸收进报告章节合同——OpenDeepWiki 的 Source 引用块格式已吸收，≥5 源文件下限待定；
- [ ] OpenDeepWiki 的 mindmap-generator.md（181 行）与 Graphify 工件尚未精读（优先级低，wiki 布局产物，与 repolens 教学产物形态不同）。
