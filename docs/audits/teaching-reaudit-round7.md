# Teaching / Feature / Tutorial / CodeMap Round 7 独立复审

**结论：REQUEST CHANGES / BLOCK**  
**Architecture status：BLOCK**

日期：2026-08-10  
复审性质：未参与 Round 6 实现的独立只读复审。除本报告外，未修改产品源码、测试、fixture 或 examples。

## 一句话结论

Round 6 已将上轮列出的直接反例、三段 framework evidence、slice/callsite typed edge、ordinary 双端标注、parallel kind、报告静态语义和六仓/Waku 展示表面修好；固定六仓 Golden 也保持 **19 个能力 / 66 个 slices / 18 条 typed resolved edge / 59 条已知 technology claim**。但共享 Binding/Scope/CFG 模型仍没有覆盖 Python comprehension walrus 的外层写入，也没有覆盖 TypeScript 类型参数、JavaScript 无声明 `for..of` target、`var` loop 作用域、`do..while`、`switch` 与未闭合语法。这些普通对象调用仍会被升格为 FastAPI/Express 静态入口，并且能获得看似完整的 import/factory/call 三段 evidence、通过 `validate_index()` 并进入 HTML。因此不能发布。

## 阻断问题

### P0 — Python comprehension walrus 会越过 kill/join，复活已被普通对象覆盖的 framework binding

关键位置：

- `src/repo_teacher/features.py:436-440`：`NamedExpr` 总是写入当前 `self.scope`。
- `src/repo_teacher/features.py:501-520`：comprehension 创建临时 scope，完成后直接恢复外层 scope。

最小反例：

```python
from fastapi import FastAPI
app = FastAPI()
[(app := object()) for item in clients]
app.get('/py-comp-walrus-false')
```

Python 的 comprehension 内 walrus target 绑定到包围作用域。`clients` 非空时，调用点 receiver 已是 `object()`；静态分析至少必须 join 为 unknown。当前结果却是：

```text
PY comprehension-walrus-kill [('GET /py-comp-walrus-false', True)]
```

该伪入口在端到端 `build_index()` 中成为 `exact-entry`，framework claim 为 `fastapi`，三段 evidence 分别是 import、`app = FastAPI()` 和伪 callsite。三段数量完整，但 factory 证据所属的 provenance 已在 callsite 前被覆盖，所以 evidence chain 在语义上不闭合。

### P0 — JavaScript/TypeScript 的 scope/transfer 仍可让普通 receiver 借用外层 Express provenance

关键位置：

- `src/repo_teacher/features.py:953-974`：`_js_pattern_names()` 把所有 `name: identifier` 当作 destructuring rename，无法区分 TypeScript 类型标注。
- `src/repo_teacher/features.py:1318-1329` 和 `1347-1359`：function/method scope 完全依赖上述 pattern name 集。
- `src/repo_teacher/features.py:1385-1421`：`for` 只对带 `let/const/var` 的 header 建立 loop names；无声明 target 没有 assignment/kill，而 `var` 又被错放在 loop scope。
- `src/repo_teacher/features.py:1484-1525`：statement dispatch 没有 `do` 和 `switch`。未支持的整段最终会进入通用 expression call scan。
- `src/repo_teacher/features.py:925-950` 和 `1093-1130`：bracket pair 构建不拒绝未闭合 token stream；一个 `receiver . member ( string` 前缀就足以生成 confirmed boundary。

独立最小反例与当前结果：

| 构造 | 反例核心 | 应有结果 | 实际结果 |
| --- | --- | --- | --- |
| TypeScript typed parameter | `function f(app: Client) { app.get('/ts-param-false') }` | 参数 shadow，不确认 | `GET /ts-param-false`, confirmed |
| bare `for..of` target | `for (app of clients) { app.get('/js-for-assign-false') }` | target 每轮被 client 覆盖，不确认 | confirmed |
| `var` function scope | function 内 `for (var app of clients)` 后调用 `app.get(...)` | 包含 0/多次路径，join unknown | confirmed |
| `do..while` block shadow | `do { const app = {}; app.get('/js-do-shadow-false') } while (...)` | 局部普通对象，不确认 | confirmed |
| `switch` block shadow | `case 'x': { const app = {}; app.get('/js-switch-shadow-false') }` | 局部普通对象，不确认 | confirmed |
| malformed call | 未闭合 `app.get('/js-unclosed-false'` | 非法语法 fail closed | confirmed |

直接调用当前 `_js_boundaries()` 的输出：

```text
JS typescript-typed-param [('GET /ts-param-false', True)]
JS for-assignment-target [('GET /js-for-assign-false', True)]
JS for-var-function-scope [('GET /js-for-var-after-false', True)]
JS do-while-shadow [('GET /js-do-shadow-false', True)]
JS switch-shadow [('GET /js-switch-shadow-false', True)]
JS malformed-unclosed-call [('GET /js-unclosed-false', True)]
```

将 Python walrus 和前四个合法 JS/TS 反例放入同一个临时仓库后：

```text
false_feature_count 5
GET /js-do-shadow-false static-entry express 3
GET /js-for-assign-false static-entry express 3
GET /js-switch-shadow-false static-entry express 3
GET /py-comp-walrus-false exact-entry fastapi 3
GET /ts-param-false static-entry express 3
validate True errors 0
report_contains_false_entries True
```

每个伪功能都获得 3 条 `technology-claim:framework` evidence。例如 `do..while` 记录的三段分别是外层 `import express`、外层 `const app = express()` 和内层 `const app = {}; app.get(...)`。这正是将两个不同 binding identity 错拼成 evidence chain。`validate_index()` 当前也会重放同一分析结果，因此无法独立拒绝。

### P2 — dangling relationship 缺 source 时，tutorial / CodeMap / coverage 仍不一致

关键位置：

- `src/repo_teacher/artifacts.py:64-73`：tutorial/CodeMap 共用的 `_valid_relationship()` 要求 source 和 target 都存在。
- `src/repo_teacher/artifacts.py:540-549`：coverage 只检查 relationship id 存在且 `target_id` 非空，漏了 `source_id`。

最小输入中使用 `{"id":"r","source_id":"","target_id":"a","kind":"calls"}`，同一次 `enrich_index()` 的结果是：

```text
missing-source {
  tutorial_count: 0,
  tutorial_status: 'location-only',
  codemap_resolved: [],
  codemap_gaps: 1,
  coverage_resolved: 1,
  coverage_check: True
}
```

缺 target 的对称输入会正确降级为 coverage 0。核心 validator 会拒绝这类输入，所以本项单独不高于 P2；但 Round 6 明确声明 enrich 层已经“同时降级”，该声明仍不成立。

## 已通过的上轮合同

### 原 Round 6 直接反例与派生对象

- `tests.test_features` 中的 Python lambda/comprehension target/with/except/del/try/match/short-circuit 和 JavaScript catch/declared for/class/object method/destructuring/brace-less if/compound/default arrow 矩阵全部通过。这证明 Round 6 修好了列出的直接样例，但不能覆盖上述新组合反例。
- 正常 FastAPI / Express / Commander 的 framework claim 都有 import、factory、callsite 至少 3 条独立 evidence，snippet 与 hash 通过。
- ordinary `alpha -> beta` 的 source/target step 引用同一 relationship id，不会 BFS 扩展到 `gamma`。
- CodeMap 按 relationship id 保留同 endpoint 的 `calls` 和 `contains` 平行 kind。
- dangling **missing id** 用例可在 tutorial/CodeMap/coverage 一致降级；本报告的 P2 是另一个“id 存在但 source 空”分支。
- 报告主要入口文案使用“静态确认入口声明（可运行性与实际可达性未知）”，不包含“可触发入口”、“可直接触发”或“运行边界已确认”。本轮没有发现 HTML 文案独立宣称 runtime reachability；阻断在于上游伪静态入口仍会被报告忠实展示。

### Typed relationship 的 slice/callsite 闭包

`AuditRelationshipSpec` 已固定 `source_slice_index` / `target_slice_index` / callsite range / allowed kinds，解析时同时检查：

- callsite contract 在 source slice 范围内；
- relationship 的 source/target id 精确对应两个 audited slice symbol；
- relationship path 与 source slice path 相同；
- relationship line 落在精确 callsite range；
- kind 属于 allowed closed set。

六仓 Golden 重放中，SourceBridge code-tour 使用 `workers/knowledge/code_tour.py:75-122` 的“提示词、模型调用与停止点构造” slice，callsite 为 line 116，target 为 `TourStop`；重复 `generate_code_tour` symbol 的“路径与证据门禁” slice 没有因 symbol 相同而被借用为该 edge 的 typed endpoint。该项通过。

## 六仓、独立参考贡献与 Waku

### 六仓真实 Golden

对 `/Volumes/T7/workspace/ontology/graph/repo` 下六个完整 clone 执行正式 `test_version_pinned_six_repository_capability_recall`：

| 合同 | 实测结果 |
| --- | ---: |
| 固定 Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationship identities | 18 |
| known technology claims | 59 |
| 逐仓 `validate_index()` | 6 / 6 valid |

Golden 还逐能力检查了 source/target slice、exact callsite、allowed kind、relationship identity、endpoint symbol 闭包、technology evidence range/hash 和 tutorial/CodeMap 派生闭包。该项用时 75.152s，通过。

### 每个参考项目的独立贡献

使用当前 `render_report()` 分别渲染 SourceBridge、PocketFlow code2tutorial、OpenWiki、Understand Anything、CodeBoarding 和 DeepWiki Open：

- 每份 HTML 都有恰好 6 张独立参考机制卡；
- 每份 HTML 只有 1 张“当前仓库”卡；
- 每张卡都区分机制、本产品映射、精确源码范围和未采用边界；
- 6 个项目卡列出的全部源码文件在各自固定 clone 中存在。

该项满足“不同项目各自参考”的展示合同，不是只用一个仓库的机制覆盖全部卡片。

### Waku 仅作兼容性项目

真实 Waku cold index 与 validator 结果：

```text
validate True
gateway entrypoint-candidate candidate unknown 6
memory  entrypoint-candidate candidate unknown 6
graph   entrypoint-candidate candidate unknown 6
loop    entrypoint-candidate candidate unknown 6
separate_heading True
six_repo_section False
```

memory / graph / loop / gateway 全部是 `entrypoint-candidate` + `confidence=candidate`，都保留 6 个 unknown 技术维度。Waku HTML 有“单独验证，不进入六仓 curated 技术排名”标题，不出现“六仓机制对照”。该项通过。

## 浏览器验证

先运行真实 Chrome 回归 `tests.test_report_mobile_browser`，1 / 1 通过。随后用当前源码新建 SourceBridge cold index，validator valid，现场渲染临时 HTML 并在本机 Google Chrome 中检查：

| viewport | document width | page/body width | overflow offenders | 六仓卡 | source links | details click |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1440×900 | 1440 | 1440 / 1440 | 0 | 6 | 116 | open=true |
| 390×844 | 390 | 390 / 390 | 0 | 6 | 116 | open=true |

首个 source link 在两个 viewport 下都是受控的仓库内 `file://` 路径。本轮没有更改 Chrome 安全策略、没有加跨 scheme 绕过参数，也没有把源码物理导航声称为独立 PASS。

## 测试与静态检查

| 命令 / 门 | 结果 |
| --- | --- |
| `PYTHONPATH=src .venv/bin/python -m unittest -v tests.test_features tests.test_artifacts tests.test_report` | 35 / 35 PASS |
| `PYTHONPATH=src python3 -m unittest -v tests.test_report_mobile_browser` | 1 / 1 PASS（真实 Chrome） |
| 六仓 `test_version_pinned_six_repository_capability_recall` | 1 / 1 PASS；19 / 66 / 18 / 59 |
| Waku `test_waku_is_a_separate_evidence_bounded_compatibility_corpus` | 1 / 1 PASS |
| `PYTHONPATH=src .venv/bin/python -m unittest -v tests.test_validation` | 13 / 13 PASS |
| `ruff check` 当前四个产品模块与对应 tests/fixture test | `All checks passed!` |
| `PYTHONPATH=src .venv/bin/python -m compileall -q src tests` | exit 0 |

上述成功输出是回归基线，不能抵消本轮现场反例：反例同样走正式 `build_index()` / `validate_index()` / `render_report()` 链路，且得到 valid 与已渲染 HTML。

## 解除阻断的最低条件

1. Python comprehension 中的 walrus 必须按 Python 语义写入正确包围 scope，并与零次执行路径 join；不能在 comprehension 销毁时丢失外层 kill。
2. JS/TS parameter/pattern parser 必须区分 TypeScript type annotation 和 object destructuring rename；所有参数名必须在 function/method/arrow scope 内 shadow 外层 provenance。
3. `for..of` / `for..in` 无声明 target 必须走 assignment/unknown；`var` 必须属于 function scope；loop join 必须包含零次路径。
4. 为 `do..while` 和 `switch` 建立保守 scope/CFG transfer，或对未支持构造整段 fail closed；不能退化为用外层 binding 扫描内部 call token。
5. JS/TS 分析前必须拒绝未闭合的 parenthesis/bracket/brace，未完整 call 不得生成 boundary。
6. framework 三段 evidence 除了数量、range 和 hash，必须证明三段属于 callsite 当前同一个未被 shadow/kill/join 污染的 provenance identity。
7. coverage 必须复用 `_valid_relationship()`，对缺 source 或 target 的 relationship 与 tutorial/CodeMap 一致降级。
8. 为上述每个反例新增回归，重跑 Teaching 36、六仓 Golden、Waku、validator、Ruff、compileall 与真实 390/1440 Chrome，再交由未参与修复的 Agent 独立复审。

在以上 P0 消失前，Repo Teacher 教学/HTML 交付的最终结论保持 **REQUEST CHANGES / BLOCK**。
