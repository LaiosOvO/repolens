# 教学/功能发现修复：六仓参考与采用边界

日期：2026-08-10  
范围：`features.py`、`artifacts.py`、`report.py` 及专项测试  
状态：等待独立复审；本文不代表审计通过。

## 本轮要修的语义错误

上一轮实现把“静态可见”写成了“运行时已证明”：任意 `run` / `start` 方法会变成产品入口，广度优先遍历被叫作执行路径，测试文件中的源码关系被误读成行为覆盖，报告还把原始路由平铺给用户。本轮把产物拆成四种不同事实：

1. **入口声明**：源码中存在 CLI、HTTP、可执行文件标记或解析器确认的约定入口符号。
2. **候选处理符号**：入口通过名称或源码位置关联到一个符号，仍需人工核对分发语义。
3. **已解析静态关系**：分析器解析出的 `calls` 边；只证明源码引用，不证明运行时一定执行。
4. **测试静态引用**：测试符号直接引用产品入口；不等于断言有效、不等于分支覆盖、不等于行为正确。

## 六个参考仓库

### 1. SourceBridge

参考代码：

- `repo/sourcebridge/cmd/sourcebridge/main.go`：`main -> cli.Execute` 是明确的可执行边界。
- `repo/sourcebridge/internal/graph/store.go` 与 `internal/graph/execution_path.go`：把图关系作为独立数据，而不是用展示顺序冒充关系。
- `repo/sourcebridge/workers/knowledge/code_tour.py`：代码导览是独立教学产物，并保留源码定位。
- `repo/sourcebridge/workers/tests/test_code_tour.py`：代码导览有专门测试，但“有测试文件”本身不能证明每条导览路径的运行时行为。

采用：只在约定入口文件中接受顶层 `main` 等入口符号；代码地图区分解析关系和阅读顺序；报告展示源码证据与缺口。  
未采用：SourceBridge 的持久化图存储、LLM 知识工件生成和后台作业编排超出本轮教学展示范围。

### 2. PocketFlow Code2Tutorial

参考代码：

- `repo/pocketflow-code2tutorial/main.py`：单一 `main` 负责参数与流程启动。
- `repo/pocketflow-code2tutorial/flow.py`：`FetchRepo -> IdentifyAbstractions -> AnalyzeRelationships -> OrderChapters -> WriteChapters -> CombineTutorial` 把分析、排序和写作分开。
- `repo/pocketflow-code2tutorial/nodes.py`：章节顺序是显式教学编排结果，不应与源码调用图混为一谈。

采用：教程作为独立 artifact；教程结尾明确“静态阅读顺序不是运行时流”。  
未采用：LLM 章节生成、重试和 PocketFlow 运行时；当前产物保持无模型、确定性、证据有界。

### 3. OpenWiki

参考代码：

- `repo/openwiki/src/cli/cli.tsx`：shebang + 顶层命令分发构成真实 CLI 文件边界，即使没有名为 `main` 的函数。
- `repo/openwiki/src/agent/skeleton_critic.ts`：先独立盘点仓库，再按概念覆盖审查文档骨架，明确避免目录镜像。
- `repo/openwiki/src/agent/wiki-link-validator.ts`：生成内容之后再做引用完整性校验。
- `repo/openwiki/src/ingestion/ingestion.ts`：来源、综合与写入目标有清晰边界。

采用：识别可执行 shebang；HTML 先按产品能力分组，再展示入口记录；证据完整度单独列缺口。  
未采用：Agent 写作、虚拟文件系统、连接器摄取与修订循环；产品能力分组目前仍是保守的路径/边界分组，不宣称已经得到领域模型。

### 4. DeepWiki Open

参考代码：

- `repo/deepwiki-open/api/routers/codemap.py`：HTTP 边界。
- `repo/deepwiki-open/api/services/codemap.py`：CodeMap 的服务实现与路由分离。
- `repo/deepwiki-open/api/services/wiki/structure.py`：Wiki 结构生成是独立服务能力。
- `repo/deepwiki-open/src/components/CodeMap.tsx` 与 `CodeViewer.tsx`：地图和源码查看是不同视图。

采用：路由只作为“入口级记录”；报告把 `/api`、`/v1` 等通用前缀剥离后按首个业务段分组；代码地图、源码位置、教程和证据缺口分开展示。  
未采用：RAG、流式生成、前端交互式图布局；静态路由正则仍标为 `static-entry`，而不是解析器确认的 `exact-entry`。

### 5. Understand Anything

参考代码：

- `repo/understand-anything/understand-anything-plugin/src/context-builder.ts`：从图中选取相关节点/边形成有界上下文。
- `repo/understand-anything/understand-anything-plugin/src/onboard-builder.ts`：面向上手的输出与原始图数据分离。
- `repo/understand-anything/understand-anything-plugin/src/explain-builder.ts`：解释视图围绕目标节点构造，而不是输出整个仓库树。
- `repo/understand-anything/understand-anything-plugin/src/diff-analyzer.ts`：变更与图节点建立映射。

采用：每个功能只展示有界的入口、符号、关系和证据；未知技术项明确标“未知”。  
未采用：LLM 上下文生成、交互式图与增量变更解释；本轮没有改动增量索引模块。

### 6. CodeBoarding

参考代码：

- `repo/codeboarding/static_analyzer/engine/call_graph_builder.py`：调用图由分阶段静态分析构建。
- `repo/codeboarding/static_analyzer/incremental_orchestrator.py`：增量合并时维护节点和边的一致性。
- `repo/codeboarding/static_analyzer/cluster_helpers.py`：用图社区而不是原始文件列表生成更高层组件。
- `repo/codeboarding/codeboarding_cli/commands/full_analysis.py`：CLI 边界与分析器分离。

采用：只有带 `target_id` 的关系进入“已解析静态关系”；展示层把入口记录分组，降低平铺噪音。  
未采用：LSP、多语言高级解析、Leiden 聚类、增量图修复；因此当前能力分组是导航分组，不是 CodeBoarding 等级的语义聚类。

## 当前实现与参考机制的对应关系

| 当前模块 | 采用的参考机制 | 本轮实现 | 明确未证明 |
|---|---|---|---|
| `features.py` | SourceBridge 显式入口、OpenWiki 可执行 CLI、DeepWiki 路由边界 | 约定文件 + 顶层符号/显式可执行标记；测试和文档不成为产品能力 | 包管理器 console script、动态路由注册、运行时分发 |
| `artifacts.py` | PocketFlow 教程分阶段、SourceBridge code tour、CodeBoarding 关系图 | 教程、代码地图、证据完整度分开；resolved edge 与 reading-order edge 分开 | 运行时 trace、行为测试覆盖、LLM 教学质量 |
| `report.py` | OpenWiki 概念骨架、DeepWiki CodeMap/CodeViewer 分离、UA 有界上下文 | 先能力分组，再入口卡片；展示已知技术和未知项；直接展示教程/地图/缺口 | 领域模型、复用安全性、生产可用性 |

## 真实仓探针结果

在本轮代码上直接调用 `build_index`，没有读取 README 作为功能事实：

| 仓库 | 探针结果 | 解释 |
|---|---:|---|
| SourceBridge | 6 条入口级记录 | 5 个约定 `main` 程序入口 + 1 个 `/health` 路由；不再把内部 `Run` 方法当功能 |
| PocketFlow Code2Tutorial | 1 条入口级记录 | `main.py:main`，未再从 docs 中产生伪 FastAPI 功能 |
| OpenWiki | 2 条入口级记录 | `src/cli/cli.tsx` shebang 与 `src/visualize/server.ts` 显式 server boundary |
| DeepWiki Open | 20 条 HTTP 入口记录 | 报告按 `/wiki`、`/codemap`、`/chat` 等业务前缀分组；这些仍不是产品领域能力的最终语义聚类 |

单元测试另有四种同构 fixture，固定 SourceBridge `cmd/*/main.go`、PocketFlow `main.py`、DeepWiki router、OpenWiki shebang 的入口真值，且明确排除内部 `run`。

## 仍需独立复审的风险

1. Python/JS HTTP 正则可能在非常规字符串中误命中，所以只给 `static-entry`。
2. CLI `add_parser` 与处理函数的名称匹配仍是候选关联，不是框架分发解析。
3. 能力分组是路径前缀/组件的保守导航，不是图聚类或 LLM 领域建模。
4. 技术标签只报告语言、入口类型、分析器和静态调用解析状态；框架、存储、并发与复用边界无证据时保持未知。
5. 报告展示的完整度只覆盖五项静态证据信号，不能替代测试覆盖率或生产验收。

