# 六仓技术选型模块修复与参考映射

日期：2026-08-10  
修复范围：`reference_catalog.py`、`comparison.py`、`comparison_report.py` 与专项测试。  
状态：实现与本地验证完成，**等待新的独立 Agent 复审；本文不替代复审结论。**

## 1. 审计阻断项如何消除

| 原问题 | 修复后的约束 | 验证 |
|---|---|---|
| 同名目录可冒充 audited 仓 | curated 身份必须同时匹配 canonical remote、40 位固定 commit、全部 curated 源文件的 bundle fingerprint；并逐文件读取当前工作树字节与 index SHA 对比 | `test_same_name_or_path_cannot_impersonate_*`、`test_wrong_commit_missing_path_and_tampered_hash_fail_closed` |
| 只剩一个预置路径仍拿完整结论 | 每个项目的 8 项 claim 共用一组完整的必需源码 bundle；少任一文件、index hash 错误或工作树被修改都 fail closed | 缺文件、改 index hash、索引后修改文件三种回归均通过 |
| `evidence_ids` 实际装 symbol ID | `evidence_ids` 只从结构合法且 ID 唯一的 `index.evidence` 获取；`symbol_ids`、`file_id` 与 `source_references` 独立表达 | 真实六仓输出 dangling EvidenceRef = 0；非法 evidence 被拒绝 |
| DeepWiki 3 项事实错误 | code-graph 明确标为“guided tour、不是调用图”；evidence 写明 Codemap citation + snippet 反查校正行号，同时限定 Wiki 正文不是逐 claim；UI 写明 sections → steps → CitationChip → CodeViewer | 固定回归锁定 `api/schemas/codemap.py`、`api/services/codemap.py`、`CodeMap.tsx`、`CodeViewer.tsx` |
| 主观整数伪装自动精确分 | 历史整数强制量化到公开的 0/25/50/75/100 reviewer rubric；输出 `score_basis`、不确定性、场景 profile 和并列规则；页面明确“不是 benchmark” | 量表值域测试与 HTML 文案回归 |
| 不同技术对象混成总榜 | 每个 option 带 `comparison_class`；推荐只在同类路线内形成 co-candidates，不再产生脱离场景的唯一冠军 | 48 项均有 class；Graph 与 Workflow 的异构路线已拆开 |
| HTML 不能下钻 | 每张项目卡链接 `projects/<slug>/index.html`；每条源码引用链接本地绝对 `file://` 路径，并显示行范围、EvidenceRef/symbol 数 | 真实六仓 HTML：48 个项目报告链接、176 个源码链接 |
| license/commit 藏在 JSON | 卡片正文显示 remote、commit、license；架构参考价值与直接代码复用状态分开，未知许可证强制 `needs-license-review` | HTML 链接与许可证回归 |
| 生成物无版本/方法信息 | comparison schema 升至 2.0，写入 UTC `generated_at`、catalog revision、项目 identity status、index integrity、完整评分方法 | JSON shape 回归与真实六仓探针 |

## 2. 固定身份

| 项目 | Canonical remote | 固定 commit | curated 文件 bundle |
|---|---|---|---|
| SourceBridge | `github.com/sourcebridge-ai/sourcebridge` | `2a128bf0c8461fae91d2b424d9168ddf205bb11b` | 33 个唯一文件，SHA-256 `fb80cf…b1ed` |
| PocketFlow Code2Tutorial | `github.com/the-pocket/pocketflow-tutorial-codebase-knowledge` | `05b24cbbb0fe409c5e23c9791f0342f07524ffdc` | 6 个唯一文件，SHA-256 `180472…f61` |
| OpenWiki | `github.com/langchain-ai/openwiki` | `7531d615216e8cbccf464f66cfbbae3668871c84` | 18 个唯一文件，SHA-256 `eb56af…88b7` |
| Understand Anything | `github.com/egonex-ai/understand-anything` | `fe8c5bc591716aafd79b4765549328f08ef5a52e` | 28 个唯一文件，SHA-256 `e44979…d0ee` |
| CodeBoarding | `github.com/codeboarding/codeboarding` | `8c3f2218c3ecab1294902db5914f5e526f78524d` | 34 个唯一文件，SHA-256 `e31448…52c5` |
| DeepWiki Open | `github.com/asyncfuncai/deepwiki-open` | `4181daa5ebde79a1baf8e92a09dd874f8b74411b` | 18 个唯一文件，SHA-256 `34eee7…af8` |

bundle 算法是对排序后的 `repository-relative path + NUL + current file SHA-256` 求总 SHA-256。它不是由项目名推断；比较时还会读取工作树文件重新计算 SHA，防止伪造 index JSON。

## 3. 48 项事实复核账本

图例：`F` = 固定源码事实；`J` = reviewer judgment；`N` = 明确的负能力/限制。每项的完整路径集合位于 `REFERENCE_CATALOG[project][capability].source_paths`，运行时必须全部通过身份 bundle 验证。

| 项目 | 解析 | 图/关系 | 组件 | 教程/Wiki | 证据 | 增量 | Codemap/UI | Workflow |
|---|---|---|---|---|---|---|---|---|
| SourceBridge | F Tree-sitter registry/parser | F symbol/call graph + federation | F 静态图后置分层摘要 | F 多 knowledge workers | F 独立 evidence/threshold gate | F ChangeWatch + fingerprint/staleness | F Tour + Mermaid 双视图 | F job state/stream/retry 控制面 |
| PocketFlow | N 文本抓取、无 AST/LSP | N LLM 概念关系、非调用图 | F 单次 LLM abstractions | F 固定六步 DAG/BatchNode | N 仅文件序号校验 | N 全量重生成，仅 prompt cache | F 静态教程 Mermaid | F 固定 Node DAG、非动态 planner |
| OpenWiki | N Agent 按需读文件、无符号表 | F 文档/OKF 导航图、非调用图 | F skeleton + 独立 critic（部分 prompt-enforced） | F linked Wiki + OKF 校验 | F 过程审查/链接/QA，非逐 claim | F 文档元数据与幂等 index sync | F 文档关系图 + Mermaid | F Deep Agents/subagents/skills/checkpoint |
| Understand Anything | F Tree-sitter 插件注册表 | F 语义知识图/normalize/persistence | F layer detector + LLM + reviewer | F knowledge graph → Tour/skills | F entity/file provenance，N 无统一 claim gate | F fingerprint/classifier/staleness hook | F graph dashboard/path/Tour | F Skill + 专职 Agent + graph merge/review |
| CodeBoarding | F 多语言 LSP adapters | F symbol table/edge/call graph | F Leiden + specialist agents | F 架构文档 renderer，N 非渐进教程 | F source locations + scoped tools | F diff/analysis cache/copy-forward/cluster delta | F diagram coverage/shape/delta | F 固定代码分析多 Agent + repair |
| DeepWiki | N 文本 RAG、无 AST/LSP | **F guided sections/steps/citation；N 不是图** | F LLM Wiki structure | F 异步逐页 RAG Wiki | **F Codemap file/snippet/line 校正；N Wiki 非逐 claim** | N task persistence + 全量重生成 | **F section/step/CitationChip/CodeViewer** | F 长任务 API/stream，N 非动态图 Agent |

### 关键补证路径

- SourceBridge cross-repo claim 增加 `internal/graph/federation.go`，避免只拿普通 graph store 支撑 federation。
- CodeBoarding incremental claim 增加 `static_analyzer/analysis_cache.py` 与 `diagram_analysis/cluster_delta.py`；Codemap/delta claim 也加入 `cluster_delta.py`。
- DeepWiki 修订绑定：
  - `api/schemas/codemap.py:6-56`：`CodeMapCitation → CodeMapStep → CodeMapSection → CodeMap.sections`；
  - `api/services/codemap.py:128-148`：检索 chunk 带真实文件/行范围；
  - `api/services/codemap.py:178-222,305-309`：snippet 反查并覆盖模型行号；
  - `src/components/CodeMap.tsx:53-63,113-137`：section/step 和 CitationChip；
  - `src/components/CodeViewer.tsx:8-24,49-80`：文件与行范围高亮。

## 4. 评分契约

评分字段名保留为兼容机器消费者，但语义改为 `reviewer-rubric-signal`：

- `0`：未发现实现，或源码明确显示不具备；
- `25`：相邻机制/实验实现，不能承担该能力；
- `50`：基础链路存在，但覆盖、可靠性或复用边界不足；
- `75`：主要链路完整，有结构化契约或测试；仍需场景 PoC；
- `100`：固定快照中形成完整生产链路；仍不代表性能 benchmark。

提供四组可调整场景权重：精确静态分析、本地优先产品、代码教学体验、动态 Agent 运行时。默认不确定性为 ±5；落在不确定性内的是并列候选。不同 `comparison_class` 从不互相宣布胜负。

## 5. 实际验证结果

```text
专项测试：15 passed
Ruff（限本模块与测试）：All checks passed
真实六仓 identity：6/6 verified
comparison shape：8 capabilities / 48 options / 48 curated
source references：176
dangling EvidenceRef：0
HTML project report links：48
HTML local source links：176
link targets：0 missing project reports / 0 missing source files / 0 invalid ranges
visual self-verdict（无像素级参考图）：92 / pass（首屏摘要、量表、8 张路线矩阵、折叠源码卡、末尾决策交接；仍待独立复审）
```

仍需独立复审确认：人工 48 项解释是否存在新的语义遗漏、line/file 粒度是否足以支持实际阅读，以及页面在浏览器中的视觉/交互质量。
