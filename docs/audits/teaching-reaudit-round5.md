# Teaching round 5 独立复审

**结论：REQUEST CHANGES / BLOCK**

**复审性质：** 全新、只读、独立复审。除本报告外，没有修改产品代码或正式 `examples`。

**复审基线：** 当前工作树；完整阅读 `teaching-reaudit-round4.md` 与 `teaching-fix-round4.md`，并对修复声明重新做六仓冷建、构造反例、真实 Chromium 检查、专项与全量回归。

## 一句话结论

六个基准仓库的教学内容、证据闭包、总—分—总教程、CodeMap 语义分离和移动端报告均达到本轮声明的数量与展示合同；但是框架入口确认仍使用“整文件最终名称映射”，没有调用点作用域与赋值时序，因此会把未绑定、已重绑定或仅在内层作用域绑定的普通对象调用提升成已确认 HTTP/CLI 边界。该错误直接污染“项目提供什么功能”的核心结论，不能发布。

## 阻断问题

### P0 — framework provenance 仍然按文件名全局合并，作用域、时序和 reassignment 均可绕过

`_python_bindings()` 对整棵 AST 使用 `ast.walk()` 生成最终的 `name -> kind` 字典；`_python_boundaries()` 随后用这份最终字典解释文件中所有调用。JavaScript 路径同样先把整个 token 流折叠成 `_js_instance_bindings()` 的最终名称字典，再解释所有 receiver 调用。实现位置：

- `src/repo_teacher/features.py:114-158`
- `src/repo_teacher/features.py:179-208`
- `src/repo_teacher/features.py:307-391`
- `src/repo_teacher/features.py:454-499`

以下反例均被错误提升为 confirmed：

1. Python 内层函数里的 `app = FastAPI()` 使模块级、实际未绑定的 `@app.get('/unbound-py')` 变成 `exact-entry`。
2. JavaScript 函数内部的 `const app = express()` / `const program = new Command()` 使外层未绑定的 `app.get(...)` / `program.command(...)` 变成 `static-entry`。
3. `const app = express(); app = {}; app.get('/reassigned-js')` 和等价的 `program` 重绑定，仍被确认为服务端/CLI 入口。
4. 更直接的时序反例中，Python `app = httpx.Client(); app.get('/private'); app = FastAPI()` 与 JavaScript 外层 axios client、内层同名 Express block binding 均被错误确认为服务端 HTTP 边界。

简单的“完全没有框架 import”与普通 axios/plain-object 负例已经通过，ESM/CommonJS 正向召回也通过；但这只证明名称白名单存在，不能证明调用点 receiver 的真实来源。入口确认必须改成调用点可见的、保守的 binding resolution：至少携带 lexical scope、定义位置和失效/重绑定位置；无法证明时不得生成 confirmed boundary。

### P1 — relationship contract 未被消费，真实关系另一端会被写成 location-only 缺口

`AuditSliceSpec.relationship` 仍只是自由文本。`_relationships_for_audit_steps()` 没有解析该 contract 的 source role、target role 或允许 kind，而是在能力内的审计符号之间任取 incident edge；同一 edge 只挂到一个 step。实现位置：

- `src/repo_teacher/capability_catalog.py:52-59`
- `src/repo_teacher/capability_catalog.py:486-538`
- `src/repo_teacher/capability_catalog.py:549-594`
- `src/repo_teacher/artifacts.py:442-468`

六仓冷建的数量合同本身成立：18 条已选关系的两个端点都属于对应能力。然而进一步按 endpoint 复核发现，已有关系的另一端仍可能被写成“与本能力其他审计符号之间没有已解析静态边”。共发现 7 个矛盾切片，涉及 SourceBridge 的 `StoreIndexResult`、`TourStop` 与第二个 `generate_code_tour`，CodeBoarding 的 `_run_local`、`supercluster_by_modularity_peak`，以及 DeepWiki 的 `generate_codemap`、`parse_wiki_structure`。

这会让同一张教学卡同时声称“有真实静态关系”和“该精确符号没有静态边”。应把 relationship 建模为 capability-level edge，并让多个 endpoint step 引用同一 edge；人工 contract 应改成有类型的 source role、target role 与允许 kind，而不是展示字符串。

### P1 — 已确认框架来源没有进入技术 claim，技术选型仍显示 unknown

`_Boundary`/`_build_feature()` 没有保存或传递具体 framework provenance；即使 `FastAPI()`、Express、Fastify、Koa Router 或 Commander 已被用于确认边界，`_build_feature()` 仍固定写入 `framework:unknown`，且 claim 文案为“当前源码证据没有证明这一技术维度”。实现位置：

- `src/repo_teacher/features.py:72-79`
- `src/repo_teacher/features.py:739-821`

这不是单纯展示缺陷：用户的核心目标是比较每个功能的底层技术实现。确认入口时已经获得的框架证据必须作为有证据引用的 framework claim 保留下来。

### P2 — candidate 的分组和卡片 verdict 使用不同判定

`_is_unconfirmed_feature()` 正确把 `confidence=candidate` 的 legacy `http-route` 归入“未确认入口候选”，但卡片 verdict 只判断 `kind == entrypoint-candidate`。因此同一条 candidate 记录可在分组中显示“不可执行”，卡片内却显示“只确认运行边界声明”。实现位置：

- `src/repo_teacher/report.py:224-228`
- `src/repo_teacher/report.py:558-565`

卡片 verdict 应复用 `_is_unconfirmed_feature()`，不能维护第二套分类逻辑。

## 已通过的核心合同

### 六仓真实冷建与证据闭包

对以下六个当前本地 clone 逐一使用独立临时 state/output 冷建，并对源码内容重新计算范围与哈希：

| 仓库 | 能力 | 切片 | 精确 symbol | resolved relationship | location-only | 有证据 claim | validate errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sourcebridge | 3 | 11 | 10 | 6 | 5 | 8 | 0 |
| pocketflow-code2tutorial | 2 | 7 | 7 | 0 | 7 | 6 | 0 |
| openwiki | 3 | 10 | 0 | 0 | 10 | 9 | 0 |
| understand-anything | 3 | 9 | 0 | 0 | 9 | 11 | 0 |
| codeboarding | 3 | 11 | 11 | 7 | 4 | 11 | 0 |
| deepwiki-open | 5 | 18 | 10 | 5 | 13 | 14 | 0 |
| **合计** | **19** | **66** | **38** | **18** | **48** | **59** | **0** |

程序化复核结果：

- 38 个 symbol 的 path 与范围覆盖对应审计切片，切片 evidence 的 path/range/hash 与真实源码一致。
- 18 个 relationship 的 source/target 均在同一能力的审计 symbol 集合内，relationship kind 与 step 记录一致。
- 48 个 location-only step 均有显式 gap kind、claim scope 和 explanation，没有伪造 relationship id。
- 59 个已知技术 claim 均带有效 evidence；六仓 `validate_index()` 合计 0 errors。
- 四类 CodeMap 统计为 18 条 resolved-static edge、40 条 reading-order edge，二者 id 与语义分离。

### framework 正向召回与基础负例

- ESM：Express、Fastify、`@koa/router`、Commander alias 均召回为 confirmed。
- CommonJS：Express、直接 `require('fastify')()`、`koa-router`、解构 Commander alias 均召回为 confirmed。
- 完全未绑定的 `app/program/client`、普通对象和 axios client 基础样例不会被确认。

该项只在“无同名嵌套绑定、无时序变化、无重绑定”的简单文件上通过；P0 反例说明 provenance 合同仍不完整。

### ordinary tutorial 与 CodeMap

使用 `alpha -> beta -> gamma` 的临时普通仓库独立构建：tutorial 只包含入口 `alpha` 与直接解析一跳 `beta`，没有把 `gamma` 当 BFS 延伸。章节固定为：

1. `purpose-and-entry`
2. `main-implementation-chain`
3. `data-state-and-dependencies`
4. `error-and-evidence-gaps`
5. `reuse-boundary`

purpose、state、dependencies、error/gaps、reuse 均来自当前功能与源码位置；CodeMap 仅把真实 `alpha -> beta` 标为 resolved edge，reading-order 与实现关系分离。

### 真实 Chromium UI

检查对象：`/private/tmp/repo-teacher-round4-final/index.html`（deepwiki-open 当前生成报告）。

| 视口 | 横向宽度 | 首屏 | 折叠 | 结果 |
| --- | --- | --- | --- | --- |
| 1440×900 | client/scroll/body 均 1425；0 overflow offender | hero、30 秒摘要、统计卡和首个功能入口可见 | 完整路径默认关闭，可点击展开/收回 | PASS |
| 390×844 | client/scroll/body 均 375；0 overflow offender | “30 秒重点”位于 y=723，主结论 y=766–832 | 完整路径默认关闭；点击后显示，关闭截图不泄露路径 | PASS |

补充验证：报告渲染 286 个源码链接（77 个唯一 path/range），全部包含 `#Lstart-Lend`，77/77 文件存在、0 malformed。真实 Chromium 从本地 `file://` 报告点击首个链接后，导航到 `api/routers/codemap.py#L15-L36` 并显示该源码内容。

截图：

- `/private/tmp/teaching-round5-1440.png`
- `/private/tmp/teaching-round5-390.png`

## 回归与静态检查

- Teaching 专项：`28 tests`，全部通过（34.409s）。
- 全量：`214 tests`，全部通过（208.576s）。
- `ruff check src tests`：通过。
- `PYTHONPATH=src python3 -m compileall -q src tests`：通过。

现有测试全部绿色，但没有覆盖调用点 scope/time/reassignment provenance、relationship endpoint 的双向解释、framework claim 保留和 legacy candidate verdict 一致性；因此不能用绿测抵消上述反例。

## 跨模块依赖（由 core validation lane 接手）

独立 standards 审查还确认：当前 validator/warm baseline 主要校验 id/checksum 存在性，未完整校验 feature step 与 relationship endpoint、tutorial feature/count、CodeMap feature/edge 之间的语义闭包。重新计算内置 checksum 后，跨功能 relationship id、伪造 tutorial count 或不存在的 CodeMap feature/relation 仍可能通过并被 warm reuse。该问题属于 core validation/derived-artifact 完整性边界，本报告记录依赖，不在 teaching 修复 lane 重复实现。

## 解除阻断的最低条件

1. framework binding 改为调用点可见的作用域/时序模型；新增 Python decorator/call、JS ESM/CommonJS、block/function shadowing、前后重绑定、client-to-server 顺序反例。
2. `_Boundary` 保存可证 framework/module/factory，并在技术 claim 中携带源码 evidence；不确定时仍须 unknown。
3. relationship contract 类型化；一个 capability edge 可被两个 endpoint step 共同解释，location-only 文案不得否认已存在的 incident edge。
4. 所有 candidate 分组、统计、卡片 verdict 统一调用 `_is_unconfirmed_feature()`。
5. 重跑六仓冷建、专项、全量、Ruff、compileall，并保留上述 Chromium 1440/390 与源码点击验收。

在以上条件满足且由未参与实现的审计者重新复审前，本轮结论保持 **REQUEST CHANGES**。
