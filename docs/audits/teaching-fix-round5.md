# Teaching / Feature / Tutorial / CodeMap 修复记录（Round 5）

日期：2026-08-10  
范围：`features.py`、`capability_catalog.py`、`artifacts.py`、`report.py`、对应回归测试与六仓 Golden。  
状态：修复与验证已完成，等待未参与实现的 Agent 独立复审；本文不自行给出 PASS。

## 1. 本轮修复结果

本轮关闭 `teaching-reaudit-round5.md` 中四类 teaching 阻断：

1. Python 与 JavaScript 的 framework provenance 改为调用点可见的 lexical scope、definition order 与保守 reassignment dataflow；名字相同不再等于来源相同。
2. 已证明的 framework / module / factory provenance 保留到 `_Boundary`，并生成带源码 evidence 的窄 technology claim，不再把已知框架降级为 `framework:unknown`。
3. curated capability 的 relationship contract 改为有类型的 source role、target role 与 allowed kinds；同一 capability edge 可被两端切片共同引用，不再把真实 endpoint 写成 location-only。
4. candidate 分组、计数和卡片 verdict 统一使用 `_is_unconfirmed_feature()`，不再出现同一记录在组内“不可执行”、卡片内却“已确认”的矛盾。

普通仓库教程仍只展示入口与直接解析的一跳；六仓固定身份、19 个能力、66 个切片、59 个有证据技术 claim、18 条唯一真实关系均未退化。

## 2. 调用点 Framework provenance

### Python

Python 路径现在按语句顺序维护作用域绑定：

- `import` / `from ... import ...` 保存模块与 factory 来源。
- constructor / factory 调用只在当前调用点可证明时生成 server、router、CLI 或 client binding。
- 函数、类与分支使用独立 lexical scope；局部同名绑定不会泄漏或反向污染外层。
- reassignment、删除以及不能证明来源的赋值会 kill 旧 provenance。
- 分支合并采用保守交集：不同分支不能共同证明同一绑定时，后续调用 fail closed。
- decorator 与普通调用都在出现位置解析 receiver，而不是读取“文件最终 name→kind map”。

以下旧反例已锁成回归并通过：

- `app = httpx.Client(); app.get('/private'); app = FastAPI()` 不会把 client 调用确认为服务端入口。
- 先构造 FastAPI、后重绑定普通对象，再调用 `app.get(...)` 不会继续确认。
- 内层函数或类中的同名 FastAPI / CLI binding 不会确认外层未绑定 receiver。
- 普通对象、未绑定对象与 client receiver 均 fail closed。

FastAPI、APIRouter、Flask、Blueprint、Starlette Router、Typer、Click 与 argparse 的合法来源仍可召回。

### JavaScript / TypeScript

JavaScript 路径增加 token 级 lexical scope 与赋值时序：

- 同时支持 ESM 与 CommonJS import / require provenance。
- block、function、arrow function 参数与局部声明具有独立作用域。
- `let` / `const` / `var` 的赋值、重绑定和普通对象覆盖都会在调用点失效旧 provenance。
- axios、got、superagent 和普通对象不会生成服务端边界。

正向回归覆盖 ESM 与 CommonJS 的 Express、Fastify、Koa Router、Commander；外层 axios + 内层同名 Express、以及 server/CLI reassignment 负例均通过。

## 3. Framework technology claim 闭包

`_Boundary` 现在携带可证的 `framework`、`module`、`factory`。构建 feature 时会：

- 生成 `technology-claim:framework` evidence，范围绑定实际 import / factory / boundary 源码；
- 写入 `framework:<具体框架>` tag 与同维度 technology claim；
- 在 claim scope 中保留 module / factory 限定，避免把“某文件引入过框架”扩大成整项目结论；
- 来源无法证明时继续使用 unknown，不根据 receiver 拼写猜测。

因此 FastAPI、Express、Fastify、Koa Router 与 Commander 的 confirmed boundary 不再显示 `framework:unknown`。

## 4. Typed relationship contract 与 endpoint 闭包

`CapabilityAuditContract.relationships` 现在由 `AuditRelationshipSpec` 构成，每条 contract 固定：

- `source_role`
- `target_role`
- `allowed_kinds`

关系选择只接受同时满足角色端点和允许 kind 的真实索引边；contract 中缺少匹配边时直接失败，不再在能力符号之间任取 incident edge。关系本身是 capability-level edge，step 只是引用该 edge，因此 source 与 target 两端都能说明同一条已解析实现关系。

本轮消除了上一轮发现的 7 个矛盾切片：SourceBridge 的 `StoreIndexResult`、`TourStop` 与重复 `generate_code_tour`，CodeBoarding 的 `_run_local`、`supercluster_by_modularity_peak`，DeepWiki 的 `generate_codemap`、`parse_wiki_structure`。结果为：

- 18 条唯一 resolved-static capability edge，identity / kind / source / target 均由 Golden 锁定；
- 25 个 endpoint step 引用这些 edge；
- 其余 41 个 step 保持显式、诚实的 location-only gap；
- tutorial 的 resolved relationship 数按唯一 edge 计数，不因两端共同引用而重复统计；
- CodeMap 的 resolved-static 与 suggested reading-order 继续分离。

`tests/fixtures/reference_capabilities.json` 新增每项能力的 typed relationship contract 和完整 resolved edge identity；Golden 同时锁定每个 step 的 relationship 引用与 closure hash，不能通过放宽断言绕过。

## 5. Candidate 展示一致性

报告的候选分组、统计与 feature card verdict 现在共同调用 `_is_unconfirmed_feature()`。`kind=entrypoint-candidate` 与 legacy `confidence=candidate` route 都统一显示为不可执行候选，不再进入“已确认运行边界”语义。

## 6. 六仓真实冷建与 Golden

对六个完整本地 clone 使用当前源码重新冷建、重新读取固定 Git identity，并运行 `validate_index()` 与 Golden：

| 仓库 | 能力 | 切片 | 唯一真实关系 | 有证据技术 claim | validate errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| SourceBridge | 3 | 11 | 6 | 8 | 0 |
| PocketFlow code2tutorial | 2 | 7 | 0 | 6 | 0 |
| OpenWiki | 3 | 10 | 0 | 9 | 0 |
| Understand Anything | 3 | 9 | 0 | 11 | 0 |
| CodeBoarding | 3 | 11 | 7 | 11 | 0 |
| DeepWiki Open | 5 | 18 | 5 | 14 | 0 |
| **合计** | **19** | **66** | **18** | **59** | **0** |

专项 Golden：`tests.test_reference_ground_truth.ReferenceGroundTruthTest.test_version_pinned_six_repository_capability_recall`，六仓全部通过。Golden 同时验证：

- exact repository identity、commit 与受审源码对象；
- symbol path / range 对切片的覆盖；
- typed relationship contract 与真实 edge kind / endpoints；
- 每个 incident endpoint step 都引用能力关系；
- evidence path / range / snippet hash；
- technology claim dimension / value / scope / evidence；
- tutorial / CodeMap 派生闭包以及六仓 `validate_index()` 零错误。

## 7. 真实 Chromium 验收

验收对象不是旧的正式 example，而是当前产品代码对 SourceBridge 冷索引生成的临时报告：

- HTML：`/private/tmp/repo-teacher-render.DumVU4/index.html`
- 索引规模：1575 files、13956 symbols、91119 relationships、21 modules。

使用本机 Google Chrome 的真实 headless Chromium DevTools Protocol 检查：

| 视口 | document scrollWidth | viewport clientWidth | 横向溢出 | 首个 feature card |
| --- | ---: | ---: | --- | --- |
| 1440×900 | 1425 | 1425 | 无 | 宽 1164px，正常显示 |
| 390×844 | 375 | 375 | 无 | 宽 347px，正常显示 |

另外使用 `Input.dispatchMouseEvent` 对首个 `.source-link` 做真实鼠标点击，Chromium 触发 `Page.frameNavigated` 并进入：

`file:///Volumes/T7/workspace/ontology/graph/repo/sourcebridge/internal/graph/execution_path.go#L22-L65`

目标以 `text/plain` 加载，证明本地源码链接不仅存在于 DOM，而且真实可点击导航。测试完成后已停止本轮临时 Chrome 进程。

## 8. 测试与静态检查证据

最终稳定树验证：

- Teaching scoped：`30 tests`，全部通过，`1` 项仅因 Python Playwright 环境缺失而跳过；该 UI 合同已由上述真实 Chromium 手工/CDP 验收覆盖。
- 全量：`231 tests`，全部通过，`3` 项因 Playwright / local browser Python binding 缺失跳过；耗时 `167.552s`。
- 六仓 cold build + validate + Golden：`6/6` 仓库、`19/19` 能力、`66/66` 切片、`59/59` 有证据 claim、`18/18` 唯一关系，全部通过。
- `ruff check src tests`：`All checks passed!`。
- `python -m compileall -q src tests`：通过。

全量第一次运行时，恰逢共享工作区的 core / Skill lane 处于中间态，Skill export 的 `derived-artifacts-mismatch` 出现一次；该用例随后单独 `1/1` 通过，并在当前稳定树的第二次全量运行中再次通过，因此不构成稳定 teaching 回归。

## 9. 修改文件

- `src/repo_teacher/features.py`
- `src/repo_teacher/capability_catalog.py`
- `src/repo_teacher/artifacts.py`
- `src/repo_teacher/report.py`
- `tests/test_features.py`
- `tests/test_artifacts.py`
- `tests/test_report.py`
- `tests/test_reference_ground_truth.py`
- `tests/fixtures/reference_capabilities.json`
- `docs/audits/teaching-fix-round5.md`

## 10. 独立复审关注点

下一位未参与实现的审计者应重点重新构造：Python decorator / call 的前后重绑定与嵌套作用域，JavaScript ESM / CommonJS 的 block / function shadowing，以及 typed relationship endpoint / allowed-kind 变形；并以当前生成报告复核 1440 / 390 computed style 与源码链接点击。本文仅陈述实现和验证证据，不替代独立 verdict。
