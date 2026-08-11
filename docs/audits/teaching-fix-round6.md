# Teaching / Feature / Tutorial / CodeMap 修复记录（Round 6）

日期：2026-08-10  
范围：framework provenance、framework evidence、typed relationship、教程 / CodeMap、六仓参考说明、Waku 兼容性语料与真实浏览器验收。  
状态：实现与实现者验证已完成，产品源码已冻结；等待未参与实现的 Agent 独立复审。本文不自行给出 PASS。

## 一句话结果

本轮把 Round 6 审计发现的“按名字猜框架”“关系只绑定 symbol、不绑定切片”“同一真实边一端 resolved、一端 location-only”“报告夸大静态入口为可运行能力”改成了统一、保守且可核验的合同：只有调用点的数据流、导入 / 构造 / 调用三段证据，以及精确 source slice / callsite / target slice 同时闭合时，报告才输出确定结论；其余情况显式保持 candidate、unknown 或 evidence gap。

六个 curated 参考仓库仍固定为 19 个能力、66 个源码切片、18 条 typed resolved edge、59 条已知技术声明。Waku 作为第七个兼容性语料单独显示 memory / graph / loop / gateway，不进入六仓技术排名。

## 1. 统一 Binding / Scope / CFG IR

`features.py` 现在让 Python 与 JavaScript 两条分析路径共享同一个抽象合同：

- `_BindingIR` 只有 `proven`、`unknown`、`killed` 三种状态；值必须携带可证明的 import 或 framework provenance。
- `_ScopeIR` 显式记录 scope kind、父作用域、本地名字和当前值；本地 shadow 不会回退读取外层同名框架绑定。
- `_joined_values()` 只在所有可达前驱证明完全相同的 provenance 时保留绑定；任一分支 unknown、kill 或来源不同，join 后即 unknown。
- `_FrameworkBinding` 保存 framework、module、factory，以及 import site 与 factory site 的精确行号和 snippet hash。

这代替了“文件最终 name → framework”映射，也没有继续按单个正则反例打补丁。

### Python AST 路径

Python visitor 按定义顺序处理 import、赋值、alias、参数、删除和调用，并为 function、lambda、comprehension、class、with target、except target、match capture、walrus、try 分支和 loop 建模作用域或 join。重要边界如下：

- function / lambda 参数、comprehension target、`with ... as`、`except ... as` 和 pattern capture 会 shadow 外层同名 framework。
- class body 不会被当作 method closure；method 参数和局部绑定重新建立作用域。
- `del`、普通对象覆盖、不支持的 RHS 与分歧重赋值会 kill / unknown，不保留旧 provenance。
- `if`、`try/except/else/finally`、`match` 与 loop 合并包含未执行路径；不能在所有路径证明的绑定不会产生 confirmed boundary。
- FastAPI / APIRouter / Flask / Blueprint / Starlette / Typer / Click / argparse 的合法正例继续召回；httpx 等客户端和普通对象 fail closed。

### JavaScript / TypeScript 路径

JavaScript 使用保守 lexer 与 `_JSBoundaryAnalyzer` 建立 scope / transfer / join，而不是仅看 receiver 拼写：

- ESM 与 CommonJS 的 Express、Fastify、Koa Router、Commander 正例保留。
- function、arrow、class / object method 参数，catch、for、destructuring、default parameter 与 class field 会定义或 kill 对应名字。
- `var` 使用 function scope，`let` / `const` 使用 block scope；局部绑定不泄漏外层，function hoist 不按普通 block 处理。
- assignment、compound expression、short-circuit、brace-less conditional 与条件重赋值不能证明单一来源时，调用保持 unconfirmed。
- axios、普通对象、动态或无法可靠解析的语法不会成为 server / CLI confirmed boundary。

`tests/test_features.py` 将上述 scope、hoist、kill、join、客户端和合法 ESM / CommonJS 正例成对锁定。

## 2. Framework claim 形成三段证据闭包

已确认入口的 framework technology claim 不再只引用 route / command 调用行。每个 claim 现在分别引用：

1. import binding 的精确源码 range 与 hash；
2. factory / constructor binding 的精确源码 range 与 hash；
3. route / command callsite 的精确源码 range 与 hash。

claim 的 module 与 factory 可独立回看；任一环无法证明时，不会根据变量名补出 framework。报告因而可以说明“调用点为什么属于 FastAPI / Express / Commander”，但仍明确不证明该入口真实可达或可运行。

## 3. Typed relationship 绑定到具体 slice 与 callsite

`AuditRelationshipSpec` 现在固定：

- `source_slice_index`
- `target_slice_index`
- `callsite_line_start` / `callsite_line_end`
- `allowed_kinds`

关系解析必须同时满足：source symbol 属于指定 source slice、真实 relationship 的 path / line 落在该 slice 的 callsite contract、target symbol 属于指定 target slice、kind 在 closed set 内。重复使用同一 symbol 的其他 role 不会再被顺带标成 relationship endpoint。

SourceBridge code-tour 的 Golden 已修正为：

- source slice：`workers/knowledge/code_tour.py:75-122`
- source role：`提示词、模型调用与停止点构造`
- callsite：line 116
- target role：`结构化停止点模型`
- kind：`calls`

同一 capability 内的平行 relationship 按 relationship id 保留，不按 endpoint pair 去重；source 与 target 两个真实 endpoint 都引用同一 edge id，无关的重复 symbol slice 保持 location-only。

`tests/fixtures/reference_capabilities.json` 锁定 source / target slice index、role、callsite range、allowed kind、edge id / endpoints 和 closure hash，不能通过放宽 symbol-name 匹配使测试变绿。

## 4. Ordinary tutorial 与 CodeMap 的一致性

`artifacts.py` 统一了 tutorial、CodeMap 和 coverage 对 relationship 的解释：

- ordinary `alpha → beta → gamma` 仍只读取入口 `alpha` 和直接一跳 `beta`，不做 BFS；`alpha` 与 `beta` 都引用同一条 resolved edge。
- curated tutorial 明确写成 `contract-selected slices and typed capability relationships`；ordinary tutorial 明确写成 `direct entry relationships only`。
- CodeMap 按 relationship id 保留 `calls:r1` 与 `contains:r2` 等平行 kind；endpoint pair 只用于阻止 synthetic reading-order edge 重复覆盖真实 edge。
- dangling relationship 在 enrich 阶段同时降级为 location-only / evidence gap；tutorial、CodeMap 和 coverage 不再分别声称 resolved、0 resolved、0 gap。
- resolved-static 与 suggested reading-order 保持不同 id 和语义，阅读顺序不冒充运行时调用顺序。

## 5. 报告只陈述静态事实

报告中的入口文案统一改为：

- `静态入口声明已确认·可达性未知`
- `静态确认 HTTP/CLI 入口声明`
- `只确认静态入口声明；可运行性与实际可达性未知`

candidate 继续显示为不可执行候选。报告不再使用“可触发入口”“可直接触发”或将静态声明称作已确认运行边界。

## 6. 六个参考仓库各自贡献

每个 curated 仓库的正式 HTML 都展示完整“六仓机制对照”，并突出当前仓库；每张卡片包含机制、映射到本产品的能力、精确源码路径，以及明确未采用的边界。

| 参考仓库 | 参考机制 | 映射到本产品 | 精确源码范围 | 未照搬的边界 |
| --- | --- | --- | --- | --- |
| SourceBridge | 进程内代码图、保守执行路径、带源码门禁的 code tour | relationship 索引、能力路径、可点击证据切片 | `internal/graph/store.go:225-380`；`internal/graph/execution_path.go:22-140`；`workers/knowledge/code_tour.py:38-181` | 不照搬 Go 内存状态 / 测试注入；静态路径不叫 runtime trace |
| PocketFlow code2tutorial | 显式教程工作流、关系整理、章节合成 | 总—分—总教程与确定性阅读顺序 | `flow.py:12-33`；`nodes.py:85-116,241-287,410-470,538-620,754-830` | 不引入 PocketFlow runtime；LLM 文本不能成为无证据事实 |
| OpenWiki | skeleton critic、Wiki 链接校验、多来源摄取编排 | evidence gap、复用边界、知识产物完整性 | `src/agent/skeleton_critic.ts:7-68`；`src/agent/wiki-link-validator.ts:92-457`；`src/ingestion/ingestion.ts:63-359` | 不照搬 connector runtime 或自动写知识库行为 |
| Understand Anything | 图搜索后一跳扩展、onboarding、定点 explain | 有界上下文、入门导览、按目标解释 | `context-builder.ts:25-140`；`onboard-builder.ts:7-123`；`explain-builder.ts:22-159` | 不做无界 BFS；prompt 不视为实现证据 |
| CodeBoarding | full analysis、LSP / language call graph、component clustering | 冷索引基线、resolved relationship、模块导航 | `full_analysis.py:25-117`；`call_graph_builder.py:24-313`；`cluster_helpers.py:48-533` | 不照搬 LSP 生命周期、Leiden 依赖或增量聚类缓存 |
| DeepWiki Open | CodeMap 编排、引用落地、结构降级、源码查看器 | CodeMap、真实行号 evidence、源码定位 | `api/services/codemap.py:46-312`；`wiki/structure.py:70-180`；`CodeMap.tsx:19-154`；`CodeViewer.tsx:27-140` | 不把 RAG / 模型输出当事实；不照搬其服务端和 React app |

这张对照是“可参考什么代码机制”的教学入口，不是 Star / 热度排名，也不把六仓拼装成一个依赖集合。

## 7. Waku 是第七兼容性语料，不进入排名

只有 Git remote 精确匹配 `github.com/shenseanchen/waku-agent` 时才启用 Waku 兼容性发现。当前固定四个阅读锚点：

- memory：`waku/memory/consolidation.py · consolidate_if_due`
- graph：`waku/graph/engine.py · run_graph`
- loop：`waku/loop/agent.py · run_loop`
- gateway：`waku/gateway/supervisor.py · GatewaySupervisor.reconcile`

它们以 `entrypoint-candidate`、`confidence=candidate` 和 `compatibility-corpus:waku-not-curated` 输出；不会生成 curated `capability-cluster`。HTML 单独显示每项机制的 resolved static relationship 数和 unknown 技术维度，缺证据的关系保持 gap，不从 memory / graph / loop / gateway 名称推断运行能力。

真实 Waku 冷索引与内部 validator 已通过，四种 mechanism 全部召回；报告包含“单独验证，不进入六仓 curated 技术排名”，且不出现“六仓机制对照”。

## 8. 六仓真实冷建与 Golden

六个完整本地 clone 使用当前冻结源码冷建并执行 `validate_index()`：

| 仓库 | 能力 | slices | typed resolved edges | known claims | validate errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| SourceBridge | 3 | 11 | 6 | 8 | 0 |
| PocketFlow code2tutorial | 2 | 7 | 0 | 6 | 0 |
| OpenWiki | 3 | 10 | 0 | 9 | 0 |
| Understand Anything | 3 | 9 | 0 | 11 | 0 |
| CodeBoarding | 3 | 11 | 7 | 11 | 0 |
| DeepWiki Open | 5 | 18 | 5 | 14 | 0 |
| **合计** | **19** | **66** | **18** | **59** | **0** |

Golden 同时检查 fixed identity、精确 symbol / range、typed source / target slice、callsite、allowed kind、edge identity、endpoint closure、technology evidence 和派生 tutorial / CodeMap 闭包。本轮实测该门耗时 88 秒，全部通过。

## 9. 真实 SourceBridge 正式输出与 Chromium

使用冻结源码对完整 SourceBridge clone 重新冷建正式输出：

- 临时 HTML：`/private/tmp/repo-teacher-round6-sourcebridge.gdkTFH/index.html`
- 规模：1575 files、13956 symbols、91119 relationships、21 modules
- CLI validate：0 errors；1 条 warning 为参考仓库自身 dirty worktree，不是索引闭包错误

本机 Google Chrome + Python Playwright 对正式输出执行真实浏览器检查：

| 视口 | 横向 overflow offender | 六仓卡片 | 源码链接 | 物理交互 |
| --- | ---: | ---: | ---: | --- |
| 1440×900 | 0 | 6 | 116 | 首屏标题可见；真实 click 打开 details；真实 click 触发仓库内 source link |
| 390×844 | 0 | 6 | 116 | 首屏标题可见；真实 click 打开 details；真实 click 触发仓库内 source link |

116 个链接均由报告生成器约束在 SourceBridge 根目录内。浏览器测试在 click listener 中阻止最终导航，以便同一页面继续完成两视口断言；它验证了真实 click event、`file://` href 与根目录闭包，没有把浏览器是否允许跨 scheme 导航误报为产品能力。

`tests/test_report_mobile_browser.py` 也已升级为真实 Chrome 双视口回归：同时检查首屏、document/body scroll width、元素越界、details click 和本地 source-link click。

## 10. 验证证据与跨模块状态

- Teaching 快速专项：36 tests，全部通过；该运行使用系统 Python Playwright 和本机 Chrome，因此浏览器测试没有 skip。
- 六仓真实 Golden：19 / 66 / 18 / 59，六仓 validate 0 errors，全部通过。
- Waku 真实冷索引：memory / graph / loop / gateway 全部召回，validator 通过。
- Ruff（全部本轮授权源码、测试、fixture 相关代码）：`All checks passed!`。
- Compileall：通过。
- 一次共享树全量运行：253 tests 中 252 通过、3 项因 venv 无 Python Playwright 而 skip、1 项旧 Skill 测试因主动注入未知 feature 字段后重签名而被新的 canonical source claim 正确拒绝。该冲突不在 teaching / Skill 产品实现，而是旧测试预期；独立测试 lane 已把它改为 `EXPECT REJECT`，并报告 Skill 46 / 46 + Ruff 通过。为避免与 core 真仓门并发制造 fingerprint 中间态，本 lane 没有在其后再次启动全量；最终全量由总控在冻结树统一执行。

## 11. 修改文件

- `src/repo_teacher/features.py`
- `src/repo_teacher/capability_catalog.py`
- `src/repo_teacher/artifacts.py`
- `src/repo_teacher/report.py`
- `tests/test_features.py`
- `tests/test_artifacts.py`
- `tests/test_report.py`
- `tests/test_reference_ground_truth.py`
- `tests/test_report_mobile_browser.py`
- `tests/fixtures/reference_capabilities.json`
- `docs/audits/teaching-fix-round6.md`

## 12. 简化与未消除风险

本轮没有增加依赖，也没有引入第二套 provenance / relationship 模型。关键简化是让两种语言共用 Binding / Scope / join 合同、让 relationship identity 成为教程与 CodeMap 的唯一真实边身份、让 Waku 复用现有 candidate schema。

仍需独立复审的风险：

1. Python / JavaScript 的动态 metaprogramming、运行时 monkey patch、computed property 与无法可靠解析的语法仍会 fail closed 为 unknown；这是有意边界，但应由独立 reviewer 用更多组合反例验证没有误升格。
2. Waku 只作为兼容性语料，不具备六仓 curated commit / source bundle 的排名资格；未来若升级为 curated，必须新增独立 identity 与 Golden，不能删除当前边界标签后直接升格。
3. SourceBridge 正式烟测检测到参考 clone 自身 dirty warning；本轮没有修改、清理或提交参考仓库。
4. core / Skill / validation 的最终冻结树全量与 SourceBridge cold + warm 复验由独立 lane 负责；本文不把局部测试、实现者测试或总控口头结果替代为独立 PASS。

独立 reviewer 应重点重新构造 Python / JavaScript scope + CFG 组合、三段 framework evidence 缺环、重复 symbol 的跨 role 污染、同 endpoints 平行 kind、dangling relationship、ordinary source endpoint，以及真实 Chrome 的折叠与源码链接行为。
