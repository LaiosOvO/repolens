# Repo Teacher 人类可读报告与技术选型终审

> 审计日期：2026-08-10  
> 审计身份：未参与本轮实现的独立审计 Agent  
> 审计范围：单仓人类可读 HTML、六仓跨项目选型、Waku 兼容性报告、Serena 专项层、GitHub/X/Skills 研究总览  
> 最终结论：**REQUEST CHANGES**  
> 架构状态：**BLOCK**

## 结论先行

本轮已经把主叙事从“入口和文件清单”改成了“功能 → 底层机制 → 关键技术 → 复用/不要照搬 → 源码证据”。六个 curated 仓库的正式页面都先讲功能，主 HTML 也已经把 Serena 正确定位为 **live LSP 语义操作专项层**，而不是持久调用图、工作流编排器或执行沙箱。Waku 的九项功能顺序和 GitHub/X/Skills 研究、许可证边界也基本正确。

但目前还不能签发 PASS，存在两个直接破坏用户核心路径的阻断：

1. Waku 首屏九张功能卡全部链接到不存在的详情锚点，点击“查看它如何实现”没有任何下钻结果。
2. 主 HTML 虽展示 Serena 当前完整 clone 的 `946ad9817875`，其“打开 Serena 独立分析”却跳到基于旧提交 `281e9db2ebb9` 的报告；该旧报告还把“符号检索”落到 `query_project_tools.py`、`jquery.min.js` 和 CLI，把代码 reference 查询落到 memory reference 模块，不能作为当前技术选型证据。

因此，“直接看到功能并点击进入实现模块”的主合同尚未闭合。

## 验收合同

本审计按以下用户合同判断：

- 单仓 HTML 首先直接回答“有哪些功能”，入口、类、函数只在后面作为证据。
- 每项功能同时给出底层机制、关键技术、可复用部分、不要照搬的边界和源码证据。
- 主 HTML 能做跨项目技术选型，而不是按 Star 或项目名选赢家。
- Waku 九项功能能逐项点击进入实现与证据详情。
- Serena 是 live LSP semantic operations 专项层；不进入六仓 curated 排名，不冒充持久图、编排器或沙箱。
- 研究 HTML 覆盖 GitHub、X、Skills，并明确许可证和证据等级。
- 1440px 与 390px 真实浏览器下可读、可操作，本地链接闭合。

## 阻断问题

### HIGH-1：Waku 九张功能卡的详情链接全部悬空

**证据**

- `src/repo_teacher/report.py:468-475` 为每张功能卡生成 `href="#feature-NNN"`，并明确写着“查看它如何实现与证据边界”。
- `src/repo_teacher/report.py:1141-1157` 在 `waku_features` 分支只生成 `confidence_summary` 与 `recommendation`；真正调用 `_render_features(...)` 并生成 `id="feature-NNN"` 的逻辑只在 `elif features` 分支执行。Waku 因此不会输出任何 `.feature-card` 详情节点。
- 正式产物 `/Volumes/T7/workspace/ontology/graph/dev/repo/examples/compatibility/waku-agent/index/index.html` 含 9 个 `.human-capability`，但没有 `feature-001` 至 `feature-011` 的目标节点。
- 真实 1440px Chromium 探针：20 个 `href="#feature-*"` 全部找不到目标。点击第一张 Agent Loop 卡后，URL 变成 `#feature-011`，`document.querySelector(location.hash) === null`，`scrollY` 仍为 `0`。
- `tests/test_report.py:549-612` 验证了 Waku 文案、顺序和 curated 边界，但没有验证每个 hash link 都存在目标；因此 16 项相关测试全绿仍未捕获该回归。

**影响**

用户可以看到九项功能和选型表，却无法从卡片进入“这项功能怎样实现”的详情。这正是本轮最核心的产品动作，属于发布阻断。

**通过条件**

- Waku 也输出九项对应的实现详情节点，或者把卡片改成真实存在且能解释机制的源码/模块页面链接。
- 对正式 Waku HTML 加 DOM 链接闭包测试：所有内部 `#...` 链接都必须命中唯一元素。
- 真实浏览器逐项抽查卡片点击后滚动到对应详情，并能看到实现路径、未知项、复用边界和源码位置。

### HIGH-2：Serena 主页面与独立报告的提交、功能证据不一致

**证据**

- 当前完整 clone 位于 `/Volumes/T7/workspace/ontology/graph/repo/serena`：
  - origin：`https://github.com/oraios/serena.git`
  - HEAD：`946ad9817875cbf46b308423296c33eb65e3e728`
  - `git rev-parse --is-shallow-repository`：`false`
  - 工作树：clean
  - 根许可证：MIT
- `tools/build_single_report.py:315-345` 的主 HTML Serena 区域展示 `HEAD 946ad9817875`，并正确链接到当前 clone 的：
  - `src/serena/tools/symbol_tools.py`
  - `src/solidlsp/`
  - `src/serena/mcp.py`
  - `src/serena/memories/memory_manager.py`
  - `docs/02-usage/070_security.md`
- 同一段代码在 `tools/build_single_report.py:338-341` 把“打开 Serena 独立分析”链接到 `/Volumes/T7/workspace/ontology/graph/biz/docs/html/project-code-serena.html`。
- 该独立报告的可见事实却是 `Commit 281e9db2ebb9`，并明确声明其证据固定在旧提交；其源码链接也指向另一个 clone `/Volumes/T7/workspace/ontology/graph/code/serena`，该 clone 的 HEAD 确为 `281e9db2ebb96cc7be7d7ef752dd2dbbabfb034f`。
- 更严重的是，该旧报告“符号检索”的实现证据指向：
  - `src/serena/tools/query_project_tools.py`
  - `src/serena/resources/dashboard/jquery.min.js`
  - `src/serena/cli.py`
  这些不是当前 Serena 的符号级 LSP 检索核心。
- 当前 `src/serena/tools/symbol_tools.py` 的直接源码证据为：
  - `GetSymbolsOverviewTool`：第 36 行起
  - `FindSymbolTool`：第 134 行起
  - `FindReferencingSymbolsTool`：第 252 行起
  - `FindImplementationsTool`：第 342 行起
  - `FindDeclarationTool`：第 399 行起
  - diagnostics：第 484 行起
  - `ReplaceSymbolBodyTool`：第 585 行起
  - `RenameSymbolTool`：第 670 行起
  - `SafeDeleteSymbol`：第 698 行起
- 旧报告的“reference 查询”还使用 `memory_reference_analysis.py` 作为关键入口，把“记忆文件引用完整性”与“代码符号引用查询”混在同一个术语下。

**影响**

主页面的 Serena 一页结论本身是准确的，但用户点击“独立分析”后会进入旧提交、旧目录和错误模块映射。技术选型最需要的“功能 → 底层实现文件”在这个动作后变得不可信。

**通过条件**

- 用 `/Volumes/T7/workspace/ontology/graph/repo/serena@946ad981...` 重新生成 Serena 独立报告。
- 明确区分 code symbol references 与 memory references。
- 每项能力至少绑定当前提交中的直接实现文件和行范围；符号检索/编辑必须以 `symbol_tools.py` 与 SolidLSP 调用边界为核心证据。
- 主 HTML 与独立报告共享同一 identity manifest；提交、remote、dirty、license 任一不一致时链接必须降级为“旧快照”而不是“当前独立分析”。

## 非阻断但必须修正的问题

### MEDIUM-1：Serena 身份在生成器中是硬编码，未进入与六仓相同的身份门

`tools/build_single_report.py:183-211` 会对六个 curated 仓库执行正式 `reference_identity_status` 核验；但 Serena 的 `MIT` 与 `HEAD 946ad9817875` 在 `tools/build_single_report.py:341` 直接写死。当前值经过本轮 shell 核验是正确的，但 clone 更新、变脏或许可证变化后，页面仍会继续显示“专项完整 clone”。HIGH-2 已经展示了跨产物漂移的真实后果。

建议让 Serena 使用同级但独立于 curated 六仓的 specialist identity 记录，并显示 HEAD、remote、dirty、license 与分析时间。

### MEDIUM-2：研究 HTML 的 Markdown 表格在 390px 下被裁切

`tools/build_repository_teaching_research_html.py:48` 把表格设为 `min-width:780px`；`tools/build_repository_teaching_research_html.py:49` 的 `.report` 使用 `overflow:hidden`，`.report-body` 没有横向滚动容器。

真实 390px Chromium 中：

- `.report-body` 可视宽度为 `360px`，实际 `scrollWidth` 分别达到 `866px` 与 `962px`。
- 内部表格右边界达到 `813px`/`881px`，外层 `.report` 将其裁掉。
- 页面全局 `scrollWidth` 仍为 `390px`，用户没有可见的横向滚动入口。

建议为 `.report-body` 提供可操作的横向滚动，或把 Markdown 表格在移动端重排成卡片；验收应覆盖列标题、最后一列和许可证结论均可访问。

### MEDIUM-3：六仓正式 HTML 尚未重生为当前 renderer 的移动版合同

当前 `src/repo_teacher/report.py:1192` 已包含 390px 下把 `.decision-table`、`tbody`、`tr`、`th`、`td` 重排为块级卡片的规则，但六个正式项目 HTML 的该媒体查询在 `.codemap-edges` 后结束，缺少这段新规则。内存中用当前 `render_report(index.json)` 重新渲染，六个文件均与正式 HTML 不同；差异除 generation meta 外，包含这段移动端 CSS。

旧正式产物仍能通过 `.decision-table-wrap` 横向滚动，不会造成全页横向溢出，所以此项不单独阻断；但正式产物并不是当前生成器的最终移动形态，修复 HIGH 项后应统一重生。

### LOW-1：研究总览首屏采用矩阵没有 Serena 行

Serena 已存在于嵌入的完整研究报告和主 HTML 中，许可证、HEAD 与采用边界也都清楚；但 `tools/build_repository_teaching_research_html.py:59-65` 的首屏 adoption matrix 没有 Serena。用户需要展开并滚动到第二份长报告末段才能看见它。建议新增“Serena / live LSP semantic operations / MIT / 不替代持久图与沙箱”一行。

## 已通过项

### Waku 九项功能与证据措辞

正式 Waku HTML 首屏顺序符合合同：

1. Agent Loop
2. Memory
3. Graph Workflow
4. Multi-channel Gateway
5. Voice
6. Tools / MCP
7. Model Providers
8. Dashboard / Observability
9. Eval / Release Gate

`src/repo_teacher/features.py:2539-2603` 的九个兼容性锚点都能在固定 Waku HEAD `75b0a6d27a19009b0482c877def3eb124181f121` 中找到相应符号。页面把它们标为 `C · 固定源码候选`，并反复说明静态证据不等于运行、性能或生产可用性验证；没有把 Waku 放进六仓 curated 排名。Voice 也明确写成串联式 ASR/Agent/TTS 参考，不冒充原生全双工语音模型。

### 六个 curated 单仓页面

六个正式页面均满足以下结构：

- 第一块为“这个项目有哪些功能？”
- 紧接“技术选型怎么用？”
- 再进入功能目录、静态入口、六仓机制对照和源码证据
- 所有内部 hash link 闭合，抽查结果为 0 个缺失目标

功能数量：SourceBridge 3、CodeBoarding 3、Understand Anything 3、OpenWiki 3、DeepWiki Open 5、PocketFlow 2。六仓没有用入口数量或 Star 冒充功能价值。

### 主 HTML 的 Serena 定位

除独立报告漂移外，主 HTML 自身的 Serena 判断通过：

- 明确标为 `SPECIALIST / LIVE SEMANTICS`
- 明确说明持久索引与 Serena 是前后两层，不是二选一
- 展示 symbol/reference/declaration/implementation、diagnostics、rename、symbol editing
- 明确“不负责功能聚类、教程生成、长任务编排或沙箱”
- 明确区分开源 LSP 与付费 JetBrains backend
- 五个本地源码链接都存在，并指向 `/repo/serena@946ad981...`

### GitHub / X / Skills 与许可证

研究 HTML 保留了两份完整 Markdown 报告，实测包含 74 个 GitHub 链接、21 个 X 链接以及 Skills 对照。以下边界表达清楚：

- CodeWiki：无仓库许可证，只借鉴算法与产物合同
- GitNexus：PolyForm Noncommercial 1.0.0，只作行为/协议参考
- codebase-to-course：无许可证，只借鉴信息架构，不复制模板资产
- learn-codebase：MIT，可参考主动学习 Skill
- CodeGraph：Apache-2.0，可做语义图 PoC
- Serena：MIT，作为 live LSP 专项层；JetBrains 付费能力分开

研究报告也收录了 X 上的反向证据：高置信图/记忆答案可能把审查 Agent 引离真正问题，因此图只能缩小阅读范围，不能替代源码重证和行为测试。社区帖子被明确当作需求/使用信号，而不是技术事实证明。

### 真实浏览器与链接闭包

- 1440px：主 HTML、Waku、研究 HTML 和六个单仓页面均无全页横向溢出；主 HTML 的 Serena 区域可见且源码链接存在。
- 390px：主 HTML、Waku 和六仓页面全局宽度均保持 `390px`；主 HTML 的选型表已转成移动卡片。研究 HTML 表格裁切问题见 MEDIUM-2。
- 主 HTML：262 个链接中本地目标 238 个，0 个缺失。
- 六仓技术选型 HTML：483 个链接，本地目标 347 个，0 个缺失。
- Waku：9 个本地源码文件目标存在，但内部详情 hash link 缺失，见 HIGH-1。

## 自动验证

以下命令在本轮审计中退出码均为 0：

```bash
PYTHONPATH=src python3 -m unittest tests.test_report tests.test_reference_ground_truth
ruff check src/repo_teacher/report.py src/repo_teacher/features.py \
  tools/build_single_report.py tools/build_repository_teaching_research_html.py
python3 -m compileall -q src/repo_teacher \
  tools/build_single_report.py tools/build_repository_teaching_research_html.py
```

相关测试共 16 项。它们证明现有文案合同与六仓 ground truth 没有回归，但不能覆盖 HIGH-1 的 DOM 目标闭包，也不能证明 Serena 跨产物快照一致。

尝试启动额外 `code-reviewer` 与 `architect` 独立复核通道时，当前 ChatGPT 账户环境拒绝其固定 `gpt-5-codex` 模型，两个通道都未产出证据。按审计规则，这不能用当前审计者自行替代为“额外双通道 PASS”；不过本报告已经基于可复现的浏览器与源码证据签发 **REQUEST CHANGES / BLOCK**，不会因通道不可用而错误批准。

## 最终门禁

只有同时满足以下条件，下一轮才可改为 PASS：

1. Waku 九张功能卡全部能下钻到存在的详情节点，DOM hash link closure 为 0 缺失。
2. Serena 独立报告更新到 `946ad981...`，功能到源码映射改为当前真实实现，并和主 HTML 使用同一身份门。
3. 研究 HTML 的 390px 表格可完整访问。
4. 六仓、Waku、主 HTML、研究 HTML 和 Serena 独立报告使用当前生成器统一重生。
5. 重跑 16 项相关测试、Ruff、compileall、本地链接闭包与真实 1440/390 浏览器验收。

**最终结论：REQUEST CHANGES。**
