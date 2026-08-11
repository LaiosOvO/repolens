# Teaching round 6 最终独立复审

**结论：REQUEST CHANGES / BLOCK**  
**Architecture status：BLOCK**

**复审性质：** 未参与 Round 5 实现的只读复审。除本报告外，没有修改产品源码、测试、正式 `examples` 或六个参考仓库。复审同时使用了独立 code-review 与 architecture/devil's-advocate 两条只读检查线；两条线均得到 BLOCK。

## 一句话结论

Round 5 已修好简单的函数、代码块、顺序赋值和候选卡片问题，六仓固定版本能力也保持 19/66/59；但 framework provenance 仍不是完整的调用点数据流模型。常见的 Python lambda/comprehension/with/except/del/try/match 和 JavaScript catch/for/class method/`var`/destructuring/无花括号分支仍能把普通对象或条件绑定提升成“已确认运行边界”。此外，framework claim 没有引用 import/factory 证据，typed relationship 的 role 没有约束到具体 source slice/callsite，普通教程仍会在同一条真实边的 source 端写 `location-only`。这些错误直接污染“项目提供什么功能、底层技术如何实现”的核心输出，不能发布。

## 阻断问题

### P0 — Python framework provenance 仍会跨越未建模的 scope / kill / join

当前 visitor 只显式建模函数、类、`if`、`while`、`for`；local collector 与 transfer 没有覆盖 lambda、comprehension、`with ... as`、exception target、`del`、`try`/`match` 多路径和短路表达式。最终 `visit_Call()` 会继续读取过期的外层 `_FrameworkBinding`：

- `src/repo_teacher/features.py:145-200`
- `src/repo_teacher/features.py:259-358`
- `src/repo_teacher/features.py:360-389`

最小反例均被错误确认为 FastAPI `exact-entry`：

| 构造 | 最小反例核心 | 应有结果 | 实际结果 |
| --- | --- | --- | --- |
| lambda 参数 shadow | `app=FastAPI(); f=lambda app: app.get('/lambda-false')` | 不确认 | `GET /lambda-false` |
| comprehension target | `app=FastAPI(); [app.get('/comp-false') for app in clients]` | 不确认 | `GET /comp-false` |
| `with ... as` target | `app=FastAPI(); with resource() as app: app.get('/with-false')` | 不确认 | `GET /with-false` |
| exception target | `app=FastAPI(); except Error as app: app.get('/except-false')` | 不确认 | `GET /except-false` |
| delete kill | `app=FastAPI(); del app; app.get('/deleted-false')` | 不确认 | `GET /deleted-false` |
| `try` join | `app=object(); try: app=FastAPI(); except Error: pass; app.get('/try-false')` | 不确认 | `GET /try-false` |
| `match` join | 仅一个 `case` 写入 `app=FastAPI()`，match 后调用 | 不确认 | `GET /match-false` |
| 短路/walrus | 条件表达式内才可能建立 binding，表达式后调用 | 不确认 | confirmed |

这也直接反证 `teaching-fix-round5.md` 中“删除、分支与不能证明的来源会 kill provenance”的完成声明。

### P0 — JavaScript framework provenance 仍会跨越 shadow、hoist、destructuring 与控制流

当前 token 级实现把所有 `{}` 当作同类 block、把 `var` 当 block-local，只识别部分 identifier declaration 和 brace-bodied function/arrow 参数，也没有 CFG join。相关位置：

- `src/repo_teacher/features.py:613-701`
- `src/repo_teacher/features.py:704-777`
- `src/repo_teacher/features.py:780-806`

最小反例：

| 构造 | 最小反例核心 | 应有结果 | 实际结果 |
| --- | --- | --- | --- |
| catch 参数 shadow | 外层 `app=express()`；`catch (app) { app.get('/catch-false') }` | 不确认 | `GET /catch-false` |
| for binding shadow | 外层 `app=express()`；`for (const app of clients) { app.get('/for-false') }` | 不确认 | `GET /for-false` |
| class/object method 参数 | `method(app) { app.get('/method-false') }` | 不确认 | `GET /method-false` |
| destructuring shadow/reassign | block 内 `const {app}=options` 或 `({app}=options)` 后调用 | 不确认 | confirmed |
| `var` function hoist | block 内 `var app={}` 后，block 外 `app.get(...)` | 不确认 | confirmed |
| brace-less conditional | `let app=ordinary; if (enabled) app=express(); app.get('/if-false')` | 不确认 | `GET /if-false` |
| compound value | `const app=express() && {}; app.get('/compound-false')` | 不确认 | confirmed |
| expression-bodied arrow/default param | 参数 shadow 后调用 | 不确认 | confirmed |

端到端临时仓库中，`/lambda-false`、`/with-false`、`/deleted-false`、`/if-false` 四条不存在或仅条件成立的路由都进入正式 feature，并被报告统计为 **4 个“已确认运行边界（可触发入口）”**。

#### 必须采用统一 IR / kill / join 合同，不应继续逐正则补洞

下一轮最低设计合同：

1. **Binding IR**：每个 binding 至少保存 `state = proven | unknown | killed`、framework kind、module、factory、声明 scope、definition/callsite range，以及 import/factory 两类 evidence id；alias 复制同一 provenance identity，而不是只复制字符串。
2. **Scope IR**：显式区分 module、function、class、lambda/comprehension、block、catch、loop；Python class body 不是 method closure，JavaScript `var` 属于 function scope，`let/const` 属于 block scope。
3. **Transfer**：所有 declaration、assignment、destructuring、parameter、`with/except/for` target、pattern capture、`del`、walrus、CommonJS/ESM alias 均统一走 `define/alias/kill/unknown`；不支持的 RHS 必须变成 `unknown`，不能保留旧 provenance。
4. **CFG join**：`if/try/except/else/finally/match/loop/short-circuit` 后，仅当每个可达前驱都持有完全相同、仍有效的 provenance identity 时保留；否则 fail closed 为 `unknown`。循环必须包含零次执行路径。
5. **Boundary gate**：只在当前 callsite 解析到 `proven http-server/cli` 时生成 confirmed boundary；unsupported syntax、未闭合 control flow 或不完整 scope 直接不生成。
6. **测试矩阵**：每个正例都配同名 shadow、前后重绑定、条件写入、alias 保留、client/ordinary object 负例；Python 与 JS/TS 分别覆盖所有上述 scope/flow construct。

### P1 — framework technology claim 不是 evidence-closed

`_FrameworkBinding` 只保存 framework/module/factory 名称，没有 import/factory 的源码位置。`_build_feature()` 在 route/command 调用行创建唯一 `technology-claim:framework` evidence，却声称该 receiver 由特定 module/factory 构造：

- `src/repo_teacher/features.py:73-79`
- `src/repo_teacher/features.py:1102-1113`
- `src/repo_teacher/features.py:1151-1153`

实测：

```python
from fastapi import FastAPI
app = FastAPI()
@app.get('/x')
```

claim 是 `framework=fastapi`、`module fastapi / factory FastAPI`，但它唯一的 evidence snippet 只有 `@app.get('/x')`。该片段和 hash 只能证明调用形状，不能独立证明 import、factory 或 receiver binding；`validate_index()` 仍返回 valid。

修复要求：claim 至少同时引用 **import/factory binding evidence** 与 **route/command call evidence**（可以是两个 evidence，也可以是覆盖完整最小 provenance chain 的多个精确 range）。缺任一环时 framework 必须是 unknown，不能由 receiver 拼写推断。

### P1 — typed relationship 消费了 role 名称，却没有消费 role 对应的 source slice/callsite

`_relationships_for_audit_steps()` 先把 role 映射成 symbol id，再仅按 `source_id/target_id/kind` 选边；当两个 slice 使用同一函数 symbol 时，role 的具体 range 被丢失。endpoint fill 又会把同一边附到任何重复 symbol slice：

- `src/repo_teacher/capability_catalog.py:538-575`
- `src/repo_teacher/capability_catalog.py:577-619`

真实 SourceBridge 反例：

- contract source role “提示词与模型调用”是 `workers/knowledge/code_tour.py:75-109`；
- 被选中的 `generate_code_tour -> TourStop` `calls` 发生在 **line 116**，不在该 role slice；
- 同一 edge 还被附到同 symbol 的“路径与证据门禁” `128-181` slice，尽管 typed contract 写的是“提示词与模型调用 -> 结构化停止点模型”。

因此“source role + target role + allowed kind”仍只是 symbol-level 标签，不是 slice-level typed contract。Golden fixture 当前把这个错配固化为正确答案。

修复要求：relationship contract 必须引用稳定的 `source_slice_id/target_slice_id`（或等价索引），并验证 relationship 的 callsite `path:line` 位于 source slice；target symbol 必须由 target slice 精确覆盖。一个 edge 可以投影到两个真实 endpoint step，但不能投影到只是复用同一 symbol 的无关 role slice。

### P1 — 普通教程的真实 edge source 端仍被写成 location-only

普通仓库的 `_direct_symbol_path()` 只把 relationship id 放到 target step，entry/source step 保持空值。tutorial 和 CodeMap gap 又只看 step 自己是否有 `relationship_id`：

- `src/repo_teacher/features.py:962-1001`
- `src/repo_teacher/artifacts.py:77-121`
- `src/repo_teacher/artifacts.py:379-455`

独立 `alpha -> beta -> gamma` 冷建结果：教程只展示 `alpha + beta`，没有 BFS 延伸到 `gamma`，这部分正确；但同一输出同时出现：

- `alpha`：`location-only`，“没有已解析静态关系”；
- `beta`：`resolved-static`；
- CodeMap：真实 `alpha -> beta` `calls` edge。

这与 Round 5 修复的 curated endpoint 原则相同：已知 edge 的 source 和 target 都不能声称没有静态关系。修复后两个 endpoint step 都应引用同一 relationship，唯一关系计数仍为 1。

### P1 — CodeMap 用 endpoint pair 去重，会丢失不同 typed relationship

`_codemap()` 用 `(source_id, target_id)` 判重，而不是 relationship id/kind：

- `src/repo_teacher/artifacts.py:371-408`

合成输入中，`a -> b` 同时存在 `calls:r1` 和 `contains:r2`。结果 tutorial 与 coverage 都计数 2，CodeMap 却只留下 `r1`，`resolved_edge_ids` 为 1。生产合同必须按 relationship identity 保留不同 kind；只应用 endpoint pair 阻止 synthetic reading-order edge 与已有 resolved edge 重叠。

### P2 — 派生教学对象还有两个 fail-closed / 文案边界

1. step 带不存在的 relationship id 时，tutorial 会计为 resolved，CodeMap 为 0 resolved 且也不生成 gap，coverage 为 0。当前 core validator 会拒绝该输入，因此不是本轮首要发布阻断，但 `enrich_index()` 自身仍会产生互相矛盾的对象。
2. 所有 tutorial 都固定写 `direct entry relationships only`；curated capability 使用的是人工 contract-selected slices/edges，不一定是 entry direct edge。应按 ordinary/curated 生成准确文案。

## 已通过的合同

### 六仓固定版本冷建、Golden 与证据闭包

对六个完整本地 clone 逐一重新冷建，并运行 `validate_index()` 与 Golden：

| 仓库 | 能力 | slices | unique resolved | endpoint steps | location-only | known claims | validate errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sourcebridge | 3 | 11 | 6 | 9 | 2 | 8 | 0 |
| pocketflow-code2tutorial | 2 | 7 | 0 | 0 | 7 | 6 | 0 |
| openwiki | 3 | 10 | 0 | 0 | 10 | 9 | 0 |
| understand-anything | 3 | 9 | 0 | 0 | 9 | 11 | 0 |
| codeboarding | 3 | 11 | 7 | 9 | 2 | 11 | 0 |
| deepwiki-open | 5 | 18 | 5 | 7 | 11 | 14 | 0 |
| **合计** | **19** | **66** | **18** | **25** | **41** | **59** | **0** |

补充结果：

- 六仓 CodeMap 为 18 条 resolved-static edge、40 条 reading-order edge；两类 id 与语义分离。
- 59 条 curated 已知 technology claim 均有当前 fixture 要求的 evidence/range/hash，六仓 Git identity 与固定 commit 通过。
- SourceBridge `graph-store` capability 的全部 step/evidence path 仅为 `internal/graph/store.go`，没有 `testhelper`。
- 上表证明 Round 5 的 **数量合同** 和旧 7 个“incident endpoint 被无条件写成 location-only”表面矛盾已消失；它不能抵消本报告发现的 source-role slice 错配。

### ordinary tutorial 的总—分—总与直接一跳边界

独立临时仓库 `alpha -> beta -> gamma` 中：

- feature/tutorial 只包含入口 `alpha` 与直接解析一跳 `beta`，没有递归加入 `gamma`；
- 章节顺序为 `purpose-and-entry`、`main-implementation-chain`、`data-state-and-dependencies`、`error-and-evidence-gaps`、`reuse-boundary`；
- purpose、entry、main chain、state、dependencies、error/gaps、reuse 均存在；
- resolved-static 与 suggested reading-order 保持不同 id/semantics。

但 source endpoint 的 location-only 矛盾仍须按上文 P1 修复。

### candidate 分组、统计与卡片 verdict

`_is_unconfirmed_feature()` 已被分组、confirmed boundary 计数和 feature card verdict 共同使用。`kind=http-route/cli-command + confidence=candidate` 的 legacy 记录显示为未确认候选，confirmed 数为 0，卡片不会出现“只确认运行边界声明”。该项通过。

### 真实 Chromium 1440 / 390 响应式检查

检查对象：当前源码对 SourceBridge 新生成的 `/private/tmp/repo-teacher-round6.Y83xVx/index.html`，通过本地 HTTP 交给 Codex in-app Chromium 检查。

| 视口 | document/client width | page overflow offender | 首个 feature card | 结果 |
| --- | --- | ---: | --- | --- |
| 1440×900 | 1425 / 1425 | 0 | 1164px，正常 | PASS |
| 390×844 | 375 / 375 | 0 | 347px，正常 | PASS |

- “查看完整路径”默认折叠；真实 click 后 `open=true` 且路径可见，再次 click 后 `open=false` 且 code 不可见。
- HTML 中 116 个 source link（31 个唯一 href）全部是仓库内 `file://...#Lstart-Lend`，31/31 文件存在，范围合法，0 越界、0 逃逸。
- 受 Browser 安全策略约束，允许的本地 HTTP 页面不能真正跳转到 `file://` 源码；真实 click 后 URL 保持在 HTTP 报告。因此本复审确认了响应式、折叠、href 与物理 range，但**没有把源码物理导航记作独立 PASS**。这不影响本轮已由 P0/P1 阻断的总 verdict。

## 测试与静态检查

- Teaching scoped：`29 tests`，全部通过，`44.426s`。
- 全量：`231 tests`，全部通过，`177.794s`。
- 六仓 Golden：PASS；19 能力、66 slices、18 unique resolved、25 endpoint steps、41 location-only、59 known claims。
- Ruff：`All checks passed!`。
- `PYTHONPATH=src python3 -m compileall -q src tests`：exit 0。

测试全绿不能抵消上述最小反例；现有 `tests/test_features.py` 只覆盖简单 function/block/if/reassignment，未覆盖本报告列出的 scope/CFG 组合。现有 framework-claim 测试只检查 evidence id/kind/scope 字符串，没有验证 evidence snippet 真能证明 import/factory binding。

## 解除阻断的最低条件

1. 以统一 binding/scope/CFG IR 实现 Python 与 JS/TS provenance，覆盖上述全部 define/alias/kill/join 反例；不能再用逐个 regex/特殊分支补丁。
2. framework claim 同时绑定 import/factory 与 boundary call 两段独立、可哈希 evidence；缺环即 unknown。
3. typed relationship contract 改为 slice/callsite 级，修正 SourceBridge code-tour fixture；不得因重复 symbol 把 edge 投影到无关 role。
4. ordinary direct edge 同时标注 source/target endpoint；CodeMap 按 relationship identity/kind 保留平行 typed edge；派生统计一致。
5. 新增上述反例回归，重跑六仓、scoped/full/Ruff/compileall 和 Chromium；再由未参与修复的 Agent 独立复审。

在以上条件满足前，Teaching / Feature / Tutorial / CodeMap / Report 的最终结论保持 **REQUEST CHANGES / BLOCK**。
