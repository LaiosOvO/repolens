# 生产版参考项目与复用边界

> 固定日期：2026-08-10。所有仓库均完整 clone 到 `/Volumes/T7/workspace/ontology/graph/repo`，不是 shallow clone；表中 SHA 与本地 HEAD 一致。

## 结论

生产版不直接拼装六套运行时，而是在 Repo Teacher 内建立一套统一的数据合同和流水线。MIT 项目的结构与算法模式可以依法借鉴；SourceBridge 为 AGPL-3.0，只做行为与接口层面的干净重写，不复制源码。每个生成结论必须回到本地文件、行范围、符号或测试证据。

| 项目 | 固定 SHA | 许可证 | 借鉴能力 | 关键源码 | 采用方式 |
| --- | --- | --- | --- | --- | --- |
| SourceBridge | `2a128bf0c846` | AGPL-3.0 | EvidenceRef、分层摘要、Learning Path、Code Tour、证据门 | `workers/knowledge/types.py`、`evidence.py`、`code_tour.py`、`workers/comprehension/hierarchical.py` | 只借鉴合同与质量门，干净重写 |
| PocketFlow Code2Tutorial | `05b24cbbb0fe` | MIT | 抽象识别→关系→章节排序→并行写章→合并教程 | `flow.py`、`nodes.py` | 采用流水线顺序；用确定性图和可选 LLM 取代全仓拼接 |
| OpenWiki | `7531d615216e` | MIT | 先 skeleton 后 prose、独立覆盖 critic、增量文档影响计划、确定性目录索引 | `src/agent/prompts/code.ts`、`skeleton_critic.ts`、`src/okf/index-sync.ts` | 采用覆盖检查和 canonical page 原则 |
| Understand Anything | `fe8c5bc59171` | MIT | Tree-sitter 知识图、结构指纹、变更等级、启发式 tour、自动更新 | `graph-builder.ts`、`fingerprint.ts`、`tour-generator.ts` | 采用指纹、图与 tour 模式；解析器做可插拔适配 |
| CodeBoarding | `8c3f2218c3ec` | MIT | LSP 调用图、call site 坐标、cluster→component、full/incremental/partial | `call_graph_builder.py`、`fingerprint_diff.py`、`agent_responses.py`、`orchestration.py` | 采用精确位置、增量 baseline 和组件合同；LSP 留作适配器 |
| DeepWiki-Open | `4181daa5ebde` | MIT | Wiki/Codemap/Workshop 形态、citation snippet grounding、结构化页面树 | `api/services/wiki/*`、`api/services/codemap.py`、`api/schemas/codemap.py` | 采用 citation 重定位与 Codemap 数据结构 |

## 能力迁移清单

### 直接进入生产版

1. 固定到 Git commit 的仓库快照。
2. 文件内容哈希、结构指纹、added/changed/deleted 变更摘要。
3. 文件、符号、关系、组件、功能、教程、Codemap、EvidenceRef 统一 schema。
4. 所有教程步骤带文件、行范围、snippet hash 和置信度。
5. 先生成 feature/component skeleton，再做覆盖 critic，最后写教程。
6. 功能阅读路线按依赖关系排序，不按目录平铺。
7. 选择功能或模块后导出 `SKILL.md`、references、快照验证脚本和 Agent 元数据。
8. 独立 HTML 中实现总—分—总、功能选择、证据下钻和导出提示。

### 通过适配器进入

- Tree-sitter、SCIP、LSP：生产数据合同预留 analyzer、confidence、external_identity；未安装时使用内建 Python AST 与保守 JS/TS 分析。
- 本地 LLM：通过 OpenAI-compatible HTTP 接口启用；不可用时仍生成确定性教程，不能阻断索引。
- Mermaid：生成源码和纯文本边列表；浏览器不依赖 CDN，避免离线报告失效。

### 明确不照搬

- 不采用 SourceBridge 的 AGPL 源码或 SurrealDB/多服务部署。
- 不把 PocketFlow 的全仓源码直接拼进一次 LLM 请求。
- 不把 LLM 输出的关系当作精确调用图。
- 不让 Codemap citation 在找不到 snippet 时静默保留。
- 不以页面数量、图数量或 stars 代替覆盖率与正确性。

## 本地仓库位置

```text
/Volumes/T7/workspace/ontology/graph/repo/
├── sourcebridge/
├── pocketflow-code2tutorial/
├── openwiki/
├── understand-anything/
├── codeboarding/
└── deepwiki-open/
```

