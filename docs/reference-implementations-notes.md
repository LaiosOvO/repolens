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

## 六、遗留 / 下一步

- [ ] cg_rank.py 在 codex 仓的实测结果核对（跑完后把 TOP 文件/符号 vs 手工选的 L3 清单对比）；
- [ ] networkx/numpy 已装入 workbuddy venv（envs/default），SKILL.md 引用工具路径；
- [ ] RepoAgent 完整 tarball 因网络限速未拉全（core 目录部分缺），但关键机制（拓扑序/环处理/增量）已从已解压部分取齐；
- [ ] 候选：deepwiki 的「页面强制 ≥5 源文件引用 + `<details>` 引用块」是否吸收进报告章节合同。
