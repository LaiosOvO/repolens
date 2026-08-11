# Teaching / feature / tutorial / CodeMap 第四轮独立复审

日期：2026-08-10  
范围：`features.py`、`capability_catalog.py`、`artifacts.py`、`report.py`、六仓固定版本能力、真实索引与 HTML  
结论：**REQUEST CHANGES**  
架构状态：**BLOCK**

## 一句话结论

本轮把第三轮最危险的三类事实问题实质收紧了：六仓固定版本能稳定召回 19/19 个能力；66 个职责切片全部拥有精确路径、行范围、源码片段哈希和角色文案；SourceBridge `graph-store` 已完全退出 `testhelpers.go`；59/59 个已知 technology tag 也各自拥有独立、窄范围 evidence。六仓最终重新构建后均能通过 `validate_index()`，0 error。

但仍不能作为“生产级仓库教学/技术选型”发布。当前未绑定的 `app.get()` / `program.command()` 仍被生成成 `http-route` / `cli-command`，HTML 又把这两类记录不看 confidence 地计入“已确认运行边界”；常见 CommonJS Express/Fastify/Commander 实例反而完全漏报。更关键的是，66 个审计切片中有 22 个没有真实 `symbol_id`，其余还存在符号错绑/复合标签只绑定一个符号；66 个切片的 `relationship_id` 全部为空，19 张能力 CodeMap 实测是 **0 条 resolved edge + 44 条建议阅读边**。也就是说，页面展示的 `constructed-by:*` / `calls:*` 等“关系”目前是清单文案，不是索引关系闭包。

移动端已经做到 390px 无横向溢出，但首屏仍先展示完整本地路径、分支、许可证和生成时间，`sourcebridge` 路径被跨行拆分，真正的“30 秒重点”只在首屏底部出现；“源码审计清单 / 领域能力 / 运行边界 / 入口候选”也仍是实现者术语，不是普通用户能迅速做复用决策的语言。这是明确的视觉可用性改进项，不是本轮架构 BLOCK 的来源。

## 审计方法

1. 完整阅读第三轮 `REQUEST CHANGES` 与 round3 修复记录，不采信修复记录中的自报 PASS。
2. 对六个完整 clone 逐仓运行当前 `build_index()` 与 `validate_index()`，统计能力、职责切片、technology claim、symbol/relationship 闭包和 CodeMap 边类型。
3. 逐项用真实源码重新计算 66 个切片 SHA-256，检查路径、行范围、role、source symbol、testhelper 污染和 59 个 technology evidence。
4. 额外运行未写进现有测试的 Python/JS 变形反例：HTTP client、普通对象、未绑定 receiver、ESM framework、CommonJS framework。
5. 检查当前生成的 SourceBridge HTML 的 143 个源码链接（14 个唯一文件 URL）是否都指向存在的本地文件。
6. 使用真实 Codex Chromium 将同一份最新 SourceBridge 报告经 localhost 打开，分别设置 1440×900 与 390×844：检查首屏可见文本和 bounding box、页面宽度、折叠展开，以及源码 anchor 的实际点击。1440 下 `clientWidth=scrollWidth=1425`；390 下 `clientWidth=scrollWidth=375`、overflow offender 为空。首个证据折叠从 closed 点击后变为 open，并显示完整源码内容。
7. 运行教学专项、全量测试、Ruff 和 compileall。

## 验收矩阵

| 检查项 | 结果 | 独立证据 |
|---|---|---|
| 六仓 19/19 curated ability | **PASS** | 3+2+3+3+3+5，路径集合与独立 fixture 一致。 |
| 66 个职责切片的 path/range/hash/role | **PASS** | 66/66 行范围有效；重新计算的 step/evidence SHA-256 全部一致；role 全部存在。 |
| 66 个切片的 symbol closure | **FAIL** | 22/66 `symbol_id=None`；另有 SourceBridge `TourStop`、`evaluate_evidence_gate` 错绑到外层 `generate_code_tour`；8 个复合符号标签只能绑定零或一个真实 symbol ID。 |
| 66 个切片的 relationship closure | **FAIL** | 66/66 `relationship_id=None`；19 张能力图合计 0 resolved、44 reading-order。`relationship_kind` 只是清单字符串。 |
| SourceBridge graph-store 不得使用 testhelper | **PASS** | 4 个切片与 2 个技术 claim 都只落在 `internal/graph/store.go`；六仓所有 capability step/technology evidence 的 `testhelper` 命中为 0。 |
| 59/59 known technology tag 有窄证据 | **PASS** | 59 个 claim、59 个唯一 evidence ID，路径/行范围/claim scope 均存在；其余 93 个维度显式 unknown。 |
| client/普通对象不得误报 | **PASS（已绑定对象）** | `requests.Session/httpx.Client/axios.create` 与已赋值普通对象不会生成 route/CLI。 |
| 未绑定 framework 不得误报 route/CLI | **FAIL** | Python `@app.get('/maybe')` 与 JS `app.get('/maybe')` / `program.command('maybe')` 仍生成 candidate，但 kind 仍是 `http-route` / `cli-command`，HTML 计为“已确认运行边界”。 |
| 真实 framework 实例必须召回 | **PARTIAL** | FastAPI/Typer 与 ESM Express/Commander 召回；CommonJS Express/Fastify/Commander 0 召回。 |
| tutorial 总—分—总字段齐全 | **PASS（结构）** | purpose/entry/main_chain/data_and_state/dependencies/error gaps/reuse boundary 均存在。 |
| tutorial 不是 BFS 换皮 | **PARTIAL** | curated capability 的 main chain 来自审计切片；普通边界/入口仍直接包装 `_walk_symbols()` 的 BFS steps，且 gaps/reuse 内容是所有功能共用模板。 |
| CodeMap resolved 与 reading-order 分开 | **PASS（类型）/ FAIL（能力闭包）** | 数据和 UI 用 `→` / `⇢` 分开；但 19 个 curated ability 全部只有 reading-order，没有一条 resolved relation。 |
| 390px 横向溢出 | **PASS** | 真实 Chromium 390px viewport（滚动条后 layout width 375）中 clientWidth=scrollWidth=body.scrollWidth=375，offenders=[]；既有 Chrome 合成回归也是 390=390。 |
| 390px 首屏重点与普通用户可读性 | **FAIL** | 真实 SourceBridge 截图中完整路径/元数据占据首屏主体，30 秒重点在折线下方才出现；路径和 snapshot 文案严重碎行。 |
| 1440px 首屏重点 | **PASS** | 真实 Chromium 1440×900 中，标题、结论、30 秒重点、建议起点和前两张能力卡均进入首屏。 |
| 证据展开 | **PASS** | 真实 Chromium 点击首个“入口与符号源码证据 7”后，`details.open=true` 且源码正文可见。 |
| 源码链接可用 | **PARTIAL** | 当前 SourceBridge 报告 143 个 source anchors、14 个唯一 `file://` URL、missing=0，anchor 可接收真实 click；localhost 页面受 Chromium 安全边界限制，点击后 URL 不变，且 href 不携带行定位。 |
| 六仓完整索引校验 | **PASS（最终状态）** | 最终重放 6/6 `valid=True`、0 error。审计期间曾复现 analyzer allowlist 不一致；当前 validator 已接受实际生成的 executable-marker analyzer。 |

## 六仓真实重放

| 仓库 | 能力 | 切片 | 已知技术 claim | `validate_index` |
|---|---:|---:|---:|---|
| SourceBridge | 3/3 | 11 | 8 | PASS · 0 error |
| PocketFlow Code2Tutorial | 2/2 | 7 | 6 | PASS · 0 error |
| OpenWiki | 3/3 | 10 | 9 | PASS · 0 error |
| Understand Anything | 3/3 | 9 | 11 | PASS · 0 error |
| CodeBoarding | 3/3 | 11 | 11 | PASS · 0 error |
| DeepWiki Open | 5/5 | 18 | 14 | PASS · 0 error |
| **合计** | **19/19** | **66** | **59** | **6/6 PASS** |

审计期间曾按父任务线索复现 OpenWiki 两个 `unsupported-feature-confidence`，并进一步发现 SourceBridge/PocketFlow/CodeBoarding 同类问题。根因是 `features.py` 生成 `python-ast+executable-marker` / `go-lexer-fallback[package=main]+executable-marker`，而当时 validator 只接受更窄的 analyzer 名。并行修复落盘后，当前 `validation.py:70-80` 已显式接受实际生成器输出；上表是修复后的重新构建结果，不沿用旧结果。

## P0 — 阻塞发布

### P0-1：未绑定 receiver 仍被建模成 route/CLI，报告再把 candidate 统计成“已确认运行边界”

- 位置：`features.py:184-220,401-432`；`report.py:618-635`
- 当前行为：

```text
Python: @app.get("/maybe")
  -> kind=http-route, confidence=candidate

JavaScript: app.get("/maybe"); program.command("maybe")
  -> kind=http-route / cli-command, confidence=candidate
```

- 数据层虽然使用 `confidence=candidate`，但 kind 没有变成候选类型。
- 报告层的 `boundaries` 只按 kind 选择 `http-route/cli-command/entrypoint`，完全不看 confidence；`candidates` 又只接受 `entrypoint-candidate`。因此独立反例的 HTML 明确写成：

```text
源码审计清单确认 0 个领域能力；另有 1 个运行边界和 0 个未确认入口候选。
当前没有源码审计能力清单；「HTTP 接口：GET /maybe」只作为已确认运行边界阅读。
```

- 这不是措辞小问题，而是把未证明的 API/CLI 边界在“30 秒重点”里提升成已确认事实，直接违反本轮“未绑定 framework 不得误报 route/CLI”的验收要求。
- 修复门：未绑定 shape 只能进入统一 `boundary-candidate`（或不生成）；所有计数、分组、标题与推荐逻辑必须按 confidence + kind 双门校验。为 HTML 加真实反例断言，不能只断言数据层的 `confidence`。

### P0-2：能力职责没有建立真实 symbol / relationship 闭包

- 位置：`capability_catalog.py:456-540`；`artifacts.py:235-336`
- `AuditSliceSpec.relationship` 只是人工字符串，构造 `FeatureStep` 时只写入 `relationship_kind`，没有写 `relationship_id`。
- `_codemap()` 只有在 `step.relationship_id` 能解析到索引关系时才生成 resolved edge；否则相邻节点全部降为 reading-order。
- 六仓真实结果：

```text
capability steps:             66
step.relationship_id:          0
capability codemap resolved:    0
capability codemap reading:    44
```

- 22 个切片没有 `symbol_id`：OpenWiki 8、Understand Anything 6、DeepWiki UI 8。
- SourceBridge `code-tour` 中声明的 `TourStop` 和 `evaluate_evidence_gate` 都被 fallback 绑定到外层 `generate_code_tour`。这是 `_symbol_for_audit_slice()` 在 exact 为空时退回任意重叠 candidate 的直接结果。
- 8 个 `A/B` 或 `A/B/C` 复合 symbol 标签最多只能绑定一个 symbol ID；其中 `SearchContent/GetCallers/GetCallees`、`PHASE_DETAIL/activePhase`、`EXT_LANG/langOf` 没有闭包，其他复合标签只指向其中一个符号。
- 用户看到的“与能力内其他切片的关系限定为 `calls:*` / `constructs:*`”因此是清单作者的断言，不是 Repo Teacher 的静态关系证据；页面同时显示切片 hash 会放大这种错误确定感。
- 修复门：每个 role slice 必须显式绑定一个或多个真实 symbol ID；禁止 exact miss 后绑定任意 enclosing candidate。关系 contract 必须声明 source role、target role、允许的 relationship kind，并解析到真实 `RelationshipRecord.id`；无法闭合就明确 `location-only`，不得展示成已证明关系。Golden 要断言 66 个 slice 的具体 symbol set 和关系状态。

## P1 — 生产级缺口

### P1-1：CommonJS framework provenance 漏报，真实实例召回不完整

- 位置：`features.py:320-398`
- `_js_import_bindings()` 看见 `require('express')` 时只写一个 `@require:<offset>` 占位键，没有把左侧 `express` / destructured `Command` 绑定到模块；后续 `_js_factory_binding()` 按变量名查不到 module provenance。
- 独立反例：

```text
const express = require("express"); const app = express(); app.get("/ok", h);        -> []
const fastify = require("fastify")(); fastify.get("/ok", h);                       -> []
const { Command } = require("commander"); const program = new Command(); ...        -> []
```

- 同义 ESM Express/Commander 能正确得到 `static-entry`，说明问题不是有意不支持框架，而是 provenance parser 的覆盖缺口。
- 修复门：支持 default require、直接调用 require、destructured require 和 alias；保持 Axios/Got/SuperAgent client 与 server framework 隔离；加入真实 CommonJS positive/negative tests。

### P1-2：教程具备总—分—总 schema，但仍没有形成按功能定制的教学结论

- 位置：`artifacts.py:64-210`
- 正面：curated capability 的 `main_chain` 不再来自 BFS，而来自 66 个审计切片；purpose/entry/state/deps/error/gaps/reuse 字段齐全。
- 缺口：
  - 普通 route/CLI/entrypoint 的 `steps` 仍由 `_walk_symbols()` BFS 产生，`_tutorial()` 只是把同一批 steps 放进五个章节。
  - 四个 gaps 对所有功能使用同一模板；即使 SourceBridge `graph-store` 已有“状态所有权”切片和 `store:in-memory` claim，仍固定写“尚未证明状态所有权”。
  - `reuse_boundary` 对每个功能完全相同，只说“可复用已声明职责的源码切片”，没有回答本功能到底可抽哪段机制、依赖什么接口、在哪个条件下不应复用。
  - `confirmed_relationship_count` 对 19 个 curated capability 全部为 0，和页面的手写 relationship 文案形成认知冲突。
- 修复门：教程内容必须由 capability-specific teaching contract 提供 data/state/error/reuse 结论；只有证据不足的字段才进入 gaps。普通 feature 若只有 BFS 路线，应明确叫“阅读导航”，不要叫主实现教程。

### P1-3：Golden 仍不能独立证明 range、symbol、relationship 与 claim scope

- 位置：`tests/fixtures/reference_capabilities.json`；`tests/test_reference_ground_truth.py:79-183`
- fixture 已独立声明 commit、path、role 和 tag，这是进步。
- 但 fixture 没有 line range、snippet hash、expected symbol IDs/qualified names、relationship source/target/kind、claim scope 或 technology evidence range。测试对这些字段只检查“非空”或用产品输出自己的 range 重新算 hash。
- 更直接的缺口：真实六仓循环中只对 Understand Anything 调用 `validate_index()`；如果其他五仓的完整索引非法，19/19 测试仍可通过。审计期间的 analyzer allowlist 回归就是被这一缺口漏掉的，虽然后来已修复。
- 修复门：每仓都必须 `validate_index(valid=True)`；fixture 为 19 个能力声明每个 slice 的 exact range、expected symbol set、relationship status、forbidden paths 和每个 known claim 的 evidence range/scope。

## P2 — 视觉与交互改进

### P2-1：390px 已无 overflow，但首屏仍不是“30 秒得到答案”

- 证据：`docs/audits/screenshots/teaching-round3-sourcebridge-390-viewport.png`
- 截图显示：品牌与 dirty snapshot 先碎行；随后完整绝对路径、分支、许可证和生成时间占据大块卡片；路径把 `sourcebridge` 拆为 `sourcebridg` + `e`；“30 秒重点”在 844px 视口底部才刚开始，能力卡和建议起点不可见。
- `3 个领域能力 / 另有 5 个运行边界 / 0 个未确认入口候选` 的层级准确，但普通用户仍需要理解四个内部术语后才能开始阅读。
- 当前 Chrome 回归只验证 `scrollWidth == 390`，使用合成 oracle，不验证真实 SourceBridge 首屏可见内容、断词质量、折叠层级或源码链接交互。
- 这项不单独阻断架构 PASS；它是用户首屏可用性的 P2 改进。
- 建议：移动端把本地路径/branch/license/time 收进“仓库快照”折叠区；首屏顺序应是“这个项目最值得看什么 → 3 个可参考功能 → 建议先看哪个”。用普通语言替代实现术语，并为真实六仓至少选一大/一小仓加入首屏 bounding-box 与可见文本回归。

### P2-2：源码链接目标真实存在，但浏览器跳转契约仍不完整

- 143 个源码 anchor 的 14 个唯一目标文件全部存在，真实点击事件也能正常派发。
- 在 localhost 报告中点击 `file://` anchor 后 Chromium 保持当前 URL；这是浏览器的 local-file 安全边界，不是目标文件缺失。
- href 只指向文件，`22-65` 等行范围仅出现在可见文本里，不在 URL 或页面内跳转协议里。即使本地 file-origin 浏览器允许打开，也不能保证落到精确代码范围。
- 这项不改变 P0 架构 BLOCK，但生产交付应定义可验证的源码打开协议（例如受控本地 handler）并加入点击后目标/行号断言。

## 已确认通过的修复

- 六个 fixed commit 的 19/19 ability recall 稳定，非 Git 文件副本不能继承 `source-audited`。
- 66/66 切片的路径、行范围、角色和源码 hash 有效；不再用 BFS 或任意相邻文件凑第二切片。
- SourceBridge graph-store 的四个切片全部位于 `internal/graph/store.go`，没有 `testhelpers.go`。
- 59 个 known technology claim 对应 59 个唯一 evidence ID，均有准确路径、范围和窄 claim scope；93 个其余维度保持 unknown。
- `requests.Session`、`httpx.Client`、`axios.create()` 和普通已赋值对象不会被变量名 `app` / `program` 提权。
- FastAPI/Typer 与 ESM Express/Commander 的真实绑定能召回。
- CodeMap 在模型和页面上把 resolved-static 与 suggested-reading-order 分开，Mermaid 原文不出现在可见正文。
- 当前六仓重新生成后全部通过完整索引校验，0 error。
- 当前 SourceBridge 报告中的 143 个源码链接都指向存在的本地文件。
- 390px 页面级横向溢出已消除。
- 1440×900 首屏能看到 30 秒重点、建议起点和前两张能力卡；证据折叠能实际展开。

## 验证记录

专项回归：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_features tests.test_artifacts tests.test_report \
  tests.test_reference_ground_truth tests.test_report_mobile_browser -v

Ran 25 tests in 32.298s
OK
```

全量回归：

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v

Ran 188 tests in 80.527s
OK
```

静态检查：

```text
uv run ruff check src tests
All checks passed!

PYTHONPATH=src python3 -m compileall -q src tests
PASS
```

独立对抗结果：

| case | 当前结果 |
|---|---|
| `httpx.Client` 命名为 `app` | 不生成 route · PASS |
| 普通已赋值对象命名为 `program` | 不生成 CLI · PASS |
| FastAPI / Typer 真实实例 | exact-entry · PASS |
| ESM Express / Commander 真实实例 | static-entry · PASS |
| 未绑定 `app.get` / `program.command` | candidate 数据，但被 HTML 当 confirmed boundary · FAIL |
| CommonJS Express / Fastify / Commander | 0 召回 · FAIL |

## 最终裁决

**REQUEST CHANGES / Architecture BLOCK**。

本轮不是“整体失败”：curated ability、职责切片、技术 claim、testhelper 排除、移动端 overflow 和最终六仓索引合法性都取得了可验证进展。剩余阻塞也已经很具体：

1. 未绑定 receiver 不得再以 route/CLI kind 进入“已确认边界”，并补齐 CommonJS framework provenance。
2. 66 个职责切片必须形成真实 symbol/relationship closure；手写关系只能标为审计声明，不能冒充已解析关系。
3. tutorial 的 state/error/reuse 要按能力生成真实结论，不能只满足字段存在。
4. Golden 为六仓逐仓验证完整索引，并独立锁定 range/symbol/relationship/claim scope。

此外有两个不阻断架构复审、但应进入产品收尾清单的 P2 项：移动端首屏隐藏技术元数据并改用普通用户语言；定义能被浏览器验证的源码打开/精确行定位协议。

完成以上整改并新增相应反例后，才适合申请第五轮生产级复审。
