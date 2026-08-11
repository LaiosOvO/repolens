# 教学 / 功能发现独立复审

日期：2026-08-10  
范围：`src/repo_teacher/features.py`、`artifacts.py`、`report.py` 与对应测试  
结论：**REQUEST CHANGES**  
架构状态：**BLOCK**  

## 一句话结论

这轮整改已经把“静态调用边”“阅读顺序”“测试静态引用”“行为覆盖”分开，并且六个真实参考仓中没有再把 `docs/tests/examples` 或内部 `run/start` 当作产品入口；但当前实现仍然是“入口探测器 + 静态 BFS 展示”，还不是生产级的“仓库功能讲解器”。它会从注释/字符串制造 HTTP 功能、把普通 `main.py:main` 宣称为已确认入口、在没有入口时把配置文件包装成模块能力；对六仓已知核心实现路径的召回只有 **5/19（26%）**。这些问题会直接污染用户的功能清单和技术选型，因此不能通过生产门。

## 审计方法与证据

1. 阅读本轮修复说明 `docs/audits/teaching-fix-reference.md`。
2. 逐行审查 `features.py`、`artifacts.py`、`report.py` 与 `test_features.py`、`test_artifacts.py`、`test_report.py`。
3. 执行完整测试：`PYTHONPATH=src python3 -m unittest discover -s tests -v`，结果为 **87/87 通过**。
4. 在六个完整参考仓上直接运行当前 `build_index`，不使用 README 推断功能。
5. 另做四个反例探针：未被调用的 `main.py:main`、字符串中的路由、注释中的路由、只有配置文件与普通源码目录的仓库。

测试通过只证明当前断言稳定，不证明这些断言符合产品语义；下面的真实仓与反例探针是本次生产门的主要依据。

## 已通过的整改点

| 检查项 | 结果 | 证据 |
|---|---|---|
| `docs/tests/examples` 不成为产品功能 | PASS | 六仓探针中违规产品路径为 0；`features.py:65-85` 有产品/测试路径隔离。 |
| 内部 `run/start` 不成为入口 | PASS | 六仓均为 0；入口符号被限制到约定入口文件和顶层符号，见 `features.py:381-410`。 |
| 入口声明、候选处理符号、静态调用、测试引用分开 | PASS（有一项 exact 语义阻塞，见 P0-3） | `entry-declaration`、首步“候选处理符号”、后续“已解析调用目标”、`test-reference` 分开生成，见 `features.py:134-173,209-251,271-315`。 |
| 测试引用不称为行为覆盖 | PASS | 报告明确写“非行为覆盖”和“这不是测试覆盖率”，见 `report.py:359-360,385-386,301-304`。 |
| 阅读顺序与解析关系分开 | PASS | CodeMap 用 `resolved_edge_ids` 与 `reading_order_edge_ids` 两套集合、实线与虚线两种语义，见 `artifacts.py:145-207`。 |
| 未知技术边界显式展示 | PASS | 框架、状态、运行时、复用与许可证无证据时列为未知，见 `report.py:249-267`。 |
| 教程 / CodeMap / 证据完整度进入 HTML | PARTIAL | 三类数据已进入功能卡片，但教程只显示开场/结尾，CodeMap 仍显示 Mermaid 源码而非可读图，见 P1-2。 |

## 六个真实参考仓探针

“核心路径召回”采用 `teaching-fix-reference.md` 自己列出的高价值参考路径作为小型真值集：只要某功能的入口证据或静态步骤链实际覆盖该路径才计为召回。它不是完整领域评测，但足以检查报告是否讲到了修复说明所宣称参考的核心机制。

| 仓库 | 当前功能记录 | 当前分组 | 已知核心路径召回 | 生产判断 |
|---|---:|---:|---:|---|
| SourceBridge | 6（5 入口 + 1 `/health`） | 6 | 0/3：未触达 `internal/graph/store.go`、`execution_path.go`、`workers/knowledge/code_tour.py` | 只看到启动边界，讲不出图存储、执行路径和代码导览。 |
| PocketFlow Code2Tutorial | 1 入口 | 1 | 2/2：触达 `flow.py`、`nodes.py` | 六仓中唯一能由入口调用链覆盖核心教学流程的仓库。 |
| OpenWiki | 2 入口文件 | 2 | 0/3：未触达 skeleton critic、link validator、ingestion | 报告无法解释概念骨架、引用校验和摄取流程。 |
| DeepWiki Open | 20 HTTP 路由 | 15 | 2/5：触达 codemap router/service，未触达 wiki structure、CodeMap/CodeViewer 视图 | 能列 API，但仍以路由清单代替产品能力；前后端能力闭环缺失。 |
| Understand Anything | 3 模块候选 | 3 | 0/3：未触达 context/onboard/explain builder | 三个候选分别落到 `eslint.config.mjs`、benchmark 脚本和 skill 辅助脚本，不能代表产品能力。 |
| CodeBoarding | 4（3 CLI + 1 main） | 2 | 1/3：只触达 full-analysis 命令，未触达 call graph builder 与 clustering | 能找到命令边界，讲不出底层图构建和组件聚类。 |

总计召回 **5/19（26%）**。当前高召回仅发生在“入口天然串起主流程”的 PocketFlow；一旦能力不直接挂在单一入口下，功能发现就基本失效。

## P0 — 必须阻塞发布

### P0-1：注释和字符串会被当成真实 HTTP 功能

- 位置：`features.py:19-26,334-379`
- 原因：路由正则直接扫描完整原始文本，没有词法层的 comment/string 排除，也没有要求装饰器/调用节点属于语法树。
- 已复现：
  - `EXAMPLE = '@app.get("/fake")'` 产生 `GET /fake`。
  - `# @app.get("/fake-comment")` 产生 `GET /fake-comment`。
- 用户影响：报告把这些结果计入“入口级记录”，并在“01 · 提供什么功能”下展示；这不只是低置信候选，而是错误的产品功能清单。
- 修复门：Python 路由必须来自 AST 装饰器/调用节点；JS/TS 至少先做词法去注释、去字符串并识别实际 call expression。正则回退结果必须进入独立“未确认候选”区，不能进入功能数和产品能力目录。

### P0-2：无入口时会把任意代表文件伪装成“模块能力”和“入口声明”

- 位置：`features.py:451-466` 调用 `_build_feature`；`features.py:271-301` 又无条件创建 `entry-declaration` 并写“找到入口声明”。
- 已复现：只有 `eslint.config.js` 与 `src/context-builder.ts` 的仓库被输出为两个 `module-capability`，两者摘要都声称“找到入口声明”。
- 真实仓影响：Understand Anything 的 3 个所谓模块能力落到 `eslint.config.mjs`、`scripts/lib/large-repo-benchmark.mjs`、`skills/.../extract-import-map.mjs`，已知 context/onboard/explain 核心能力全部未召回。
- 修复门：删除这种降级伪造，或引入独立 `module-navigation-candidate` 数据类型；它不得复用 `entry-declaration`、`entrypoint`、`FeatureRecord` 的产品功能语义，也不得进入 30 秒功能结论。

### P0-3：`exact-entry` 把“精确解析到符号”错误升级为“入口已确认”

- 位置：`features.py:381-410`，尤其 `390-393` 允许约定文件中名为 `main` 的符号在没有可执行标记时直接成为入口；`408-409` 沿用符号解析器的 `exact`；`report.py:84-94,420-425,449-453` 将其呈现为“入口已确认”“解析器确认的入口符号”。
- 已复现：仅含 `def main(): return 1`、没有 `if __name__ == '__main__'` 的 `main.py` 被标为 `exact-entry`。
- 原因：解析器精确确认的是“符号存在”，不是“它构成运行入口”。Go 的 `package main + func main` 与 Python/TS 的命名约定不是同一种证据。
- 修复门：拆分 `symbol_confidence` 与 `boundary_confidence`。只有语言语义或清单/可执行标记确认的边界可称 exact；仅文件名 + 符号名必须是候选，并在报告中明确“符号已解析、入口未确认”。

## P1 — 生产级功能缺口

### P1-1：入口发现不能替代产品能力发现，六仓核心召回仅 26%

- 位置：`features.py:320-468` 的发现来源只有 CLI 正则、HTTP 正则、约定入口和最后的模块代表文件。
- 影响：SourceBridge、OpenWiki、Understand Anything 的核心能力全部缺失；DeepWiki 被拆成 15 个 URL 前缀组；CodeBoarding 只有 CLI 表面。
- 报告放大：`report.py:180-218,395-398,427-436` 把 URL 首段/目录组称为“产品能力分组”并放入 30 秒重点，即使细节处有免责声明，首屏心智模型仍然是“这些就是产品能力”。
- 修复门：至少引入一个明确的二层模型：`entry boundary` 与 `capability cluster` 分开。capability 需要由模块/调用图/命名概念/前后端关联证据聚合，并保留 evidence；无法聚合时应显示“尚未识别领域能力”，不能把路由前缀改名为能力。

### P1-2：教程和 CodeMap 被“放进 HTML”，但还没有真正成为可教学的可视产物

- 位置：`artifacts.py:64-99` 的教程只是复制静态 BFS 步骤加开场/结尾；`report.py:276-293` 只显示教程开场/结尾，并把 Mermaid 文本放入 `<pre>`。
- 与参考差距：PocketFlow 把 abstraction、relationship analysis、chapter order、chapter writing 分开；SourceBridge 的 code tour 有选点和源码定位；当前实现没有概念抽取、章节目的、前置知识、关键权衡或导览选点。
- 用户影响：名为“教程”的区域没有独立章节内容，名为“代码地图”的区域仍需用户阅读 Mermaid 源码。用户此前已经明确反馈过原始图文本显示不可读。
- 修复门：教程 artifact 至少渲染标题、目的、逐步内容、源码证据和“为何读这一段”；CodeMap 要么用内嵌本地图形渲染，要么输出可访问的 SVG/HTML 图，同时继续保持实线/虚线语义分离。

### P1-3：技术标签诚实但不足以支撑“底层技术实现比较”

- 位置：`features.py:310-315` 只输出语言、记录类型、边界分析器、调用关系是否解析；`report.py:249-267` 其余全部列未知。
- 正面：没有无证据猜测框架、存储、并发或许可证，边界是诚实的。
- 缺口：用户要比较的是每个功能的框架/协议、状态存储、图模型、任务编排、流式/并发、错误处理、测试策略和可复用文件。当前功能卡不能回答这些问题。
- 修复门：从清单、import、构造点、接口实现、状态读写、并发原语和测试关系生成带证据的技术维度；未知项继续保留，不允许关键词命中直接升级为确定事实。

### P1-4：没有六仓真实基准回归，87 个测试会稳定错误语义

- 位置：`tests/test_features.py:155-190` 只用四个极小同构 fixture，断言的真值仅是 `main`、`GET /`、shebang，并明确不检查各仓核心能力；Understand Anything 与 CodeBoarding 没有功能真值。
- 报告/Artifact 测试也都是手工构造数据，未验证真实六仓的功能召回、错误候选率、章节质量或可视化可读性。
- 修复门：建立固定 commit 的六仓 golden set，至少包含：核心 capability、合法入口、禁止出现的伪入口、关键实现路径、能力聚合结果、技术维度证据和 HTML 首屏摘要。生产门应同时约束 precision 与 recall。

## P2 — 应在生产发布前收紧

### P2-1：非产品路径规则仍是少量精确目录名

- 位置：`features.py:46-49,65-85`
- 当前会遗漏 `__tests__`、`integration_tests`、`e2e`、`demos`、`playground` 等常见非产品目录。现有六仓没有触发，不代表通用生产输入安全。
- 建议：归一化目录类别并允许配置；真实 golden set 增加这些命名变体。

### P2-2：“最佳功能”排序不是产品价值排序

- 位置：`report.py:160-164,427-436`
- 当前按 exact、测试静态引用数、步骤数、标题排序，然后建议用户从它开始。SourceBridge 这类多入口仓容易把最深的辅助入口排在真正核心能力之前。
- 建议：只有 capability 聚合完成后才做“建议起点”；否则按“已确认入口 / 未确认候选”分层，不给价值排序。

### P2-3：五个布尔信号等权得分会制造“strong”错觉

- 位置：`artifacts.py:242-277` 与 `report.py:295-304`
- 一个入口、一个步骤、一段证据、一条测试静态引用、一条静态关系即可得到 100/100 `strong`，但仍可能是错误入口或无效测试。
- 正面：报告已明确它不是行为覆盖。
- 建议：把状态名称改为 `signals-present` 等非质量词，入口真实性作为硬前置；展示原始五项而非单一百分数，避免用户把“证据信号齐全”理解成“结论强”。

### P2-4：功能报告中的源码位置不可点击

- 位置：`report.py:339-355,381-386`
- 当前只输出 `<code>` 路径；虽然独立 module report 支持文件链接，但 feature-first 教学页不能从功能直接下钻到源码或对应模块说明。
- 建议：生成受根目录约束的 `file://` 链接，并给每个功能提供“打开模块讲解”链接；继续拒绝非本地文件协议和越界路径。

## 六仓参考完整度

这里评估的是“实现机制是否真正采用”，不是文档是否提到了参考项目。

| 参考项目 | 已采用 | 尚未采用但对本产品关键 | 评价 |
|---|---|---|---|
| SourceBridge | 显式入口、解析静态边与阅读顺序分离 | execution path 选路、code tour 选点、图存储支撑的可追溯导览 | 部分，核心教学机制未采用。 |
| PocketFlow Code2Tutorial | 教程作为独立 artifact；入口链能覆盖真实 flow/nodes | abstraction → relationship → chapter order → writing 的分阶段产物 | 部分；结构命名参考到了，教学内容生成没有实现。 |
| OpenWiki | 入口文件识别、报告有生成后证据展示 | 概念 skeleton、critic 覆盖审查、link validation、ingestion 到文档的闭环 | 很低；真实核心路径召回 0/3。 |
| DeepWiki Open | Router → service 的部分静态链 | Wiki structure、CodeMap/CodeViewer 视图闭环、grounded citation 的展示 | 部分；API 清单多于产品讲解。 |
| Understand Anything | 有界步数与“未知”边界 | 围绕目标构造 context、onboard/explain 视图、变更映射 | 很低；真实核心路径召回 0/3。 |
| CodeBoarding | 解析关系进入图；CLI 边界可见 | call graph 分阶段构建、community/component clustering、增量一致性 | 很低；底层图与聚类均未进入能力解释。 |

综合判断：参考项目“设计原则提及”较完整，但“可复用机制落地”约为 **30% 左右**。这足以作为下一轮实现路线，不足以宣称已经按六个基准项目完整参考。

## 生产门复审标准

下一次复审至少需要全部满足：

1. 注释/字符串路由、未调用 Python `main`、配置文件 fallback 三个反例不再进入已确认功能清单。
2. 六仓固定 commit golden set 同时度量 precision 与 recall；上述 19 个核心路径不能再只有 5 个被触达。
3. `entry boundary`、`capability cluster`、`candidate handler`、`resolved static edge`、`test static reference` 五类事实在 schema 和 UI 中分别建模。
4. DeepWiki/OpenWiki/SourceBridge 至少各能产出 3 个有源码证据的领域能力；PocketFlow 保持 flow/nodes 主链；Understand Anything 与 CodeBoarding 不再退化为配置/CLI 表面。
5. 教程渲染真实步骤与教学目的，CodeMap 显示为可读图而不是 Mermaid 原文；证据完整度不使用暗示质量的 `strong` 百分数。
6. 技术实现至少覆盖依赖/框架、数据与状态、调用/并发、错误处理、测试与复用文件六个维度，并允许逐项未知。
7. 再次由独立审计 Agent 在真实六仓上复跑，并对 HTML 做人工/截图可读性检查后，才可给 PASS。

## 最终裁决

**REQUEST CHANGES / Architecture BLOCK**。

整改方向是正确的，尤其是四类静态事实的语义分离和报告中的未知边界；但 P0 反例会生成错误功能，P1 真实仓召回又不足以解释核心能力。当前版本可以作为静态导航预览，不可作为生产级仓库教学、模块复用或技术选型结论来源。
