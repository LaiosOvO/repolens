# Teaching / Feature / Tutorial / CodeMap 修复记录（Round 7）

日期：2026-08-10  
范围：Python comprehension walrus、JavaScript / TypeScript scope 与 CFG、未闭合语法 fail-closed、relationship coverage 闭包。  
状态：实现和实现者验证完成，产品源码已冻结，等待新的独立 Agent 复审；本文不自行给出 PASS。

## 一句话结果

Round 7 的问题不是三段 evidence 数量不足，而是 callsite 的 binding identity 已经被 shadow、assignment 或 CFG join 污染，却仍借用了旧 import / factory provenance。本轮把修复落在共享 Binding / Scope / CFG 语义上：Python comprehension 的 walrus 写入正确的包围作用域并与零次执行路径合并；JS / TS 参数、for、do、switch 和结构完整性都先更新调用点环境，只有仍能解析到同一 proven framework identity 的 receiver 才能生成 feature 和三段 evidence。

合并端到端反例目前包含 11 个伪入口，正式 `build_index()` 输出 0 个对应 feature、0 条 framework technology evidence；`validate_index()` 通过，最终 HTML 也不包含这些入口。

## 1. Test-first 行为合同

本轮先在两个公共 seam 写红测：

- `build_index()`：用户最终看到的 feature、technology evidence、validator 和 HTML。
- `enrich_index()`：同一次派生中的 tutorial、CodeMap、coverage。

红测初始结果：

- 合并 scope / CFG 仓库出现伪 framework feature，测试失败。
- relationship id 存在但 `source_id` 为空时，coverage 仍写 1 resolved，测试失败。

修复后两个红测均转绿，未通过 mock 或私有 helper 断言绕过正式链路。

## 2. Python comprehension walrus

Python 的 assignment expression 在 comprehension 中不属于 comprehension iteration-variable scope，而是写入最近的非 comprehension 包围作用域。修复包含两部分：

1. `visit_NamedExpr()` 从当前 comprehension scope 向外定位最近的 function / lambda / module scope，并在该 scope 写入新的 binding state。
2. `_visit_comprehension()` 保存全部外层 scope 的执行前状态；完成 generator、filter 和 result 分析后，将“零次执行”与“至少一次执行”的状态做保守 join。只要 walrus 可能覆盖原 FastAPI binding，后续 receiver 就是 unknown。

此外，`_PythonLocalCollector` 现在遍历 comprehension 的 iterable、filter 与 result expression，只收集其中的 walrus target，不把 iteration target 错当作外层 local，也不穿过 lambda。这样以下函数级反例不会在 walrus 执行前错误回退读取 module FastAPI：

```python
app = FastAPI()
def register():
    app.get('/py-before-comp-walrus-false')
    [(app := object()) for item in clients]
```

当前同时锁定：

- module comprehension walrus 覆盖后调用为 unknown；
- function 中 walrus 产生的 compile-time local shadow 会阻止执行前错误读取外层 binding；
- comprehension iteration target 仍只在 comprehension 内 shadow，正常 module binding 在普通 comprehension 后保持可用。

## 3. JS / TS 结构完整性先于 boundary discovery

JS / TS lexer 与 delimiter IR 现在会拒绝：

- 未闭合 block comment；
- 未闭合 string / template literal；
- 未闭合或交叉错配的 `()`、`[]`、`{}`；
- 没有匹配 closing parenthesis 的 route / command call。

`_js_boundaries()` 对这些结构错误统一返回空列表。它不会扫描一个语法前缀后把 `app.get('/path'` 升格为 confirmed boundary，也不会生成 import / factory / call evidence。

## 4. TypeScript 参数与 binding pattern

新增的参数 / declaration binding parser区分两种冒号语义：

- `app: Client`：`app` 是参数或声明 binding，`Client` 是类型，不是 local name。
- `{app: local}`：`local` 是 object destructuring binding。

同一解析合同用于 function、generic function、arrow、generic class / object method、typed return、declaration 与 typed `for..of` target。以下构造都在 function / method scope 正确 shadow 外层 Express：

- `function typed<T>(app: Client) {...}`
- `(app: Client): void => ...`
- `method<T>(app: Client): void {...}`
- `for (const app: Client of clients) {...}`

这不是按 `Client` 名称做黑名单；任意类型名都不会代替真正的 binding name。

## 5. for / do / switch 的保守 CFG

### `for..of` / `for..in`

- bare target `for (app of clients)` 作为 assignment 写入当前可见 binding，body 内 receiver 为 unknown。
- `var` target 写入 function / module scope，而不是临时 loop scope。
- `let` / `const` target 保持 loop lexical scope，不污染外层。
- loop 结束状态合并零次执行路径与执行路径；`var app = express()` 后再被 iteration value 覆盖，不会在 loop 后继续保留旧 Express provenance。

### `do..while`

`do` body 使用正常 block / lexical scope 分析，并在 body 后解析 while condition。局部 `const app = {}` 会在 block 内 shadow 外层 Express，因此 block 内伪 route 为 0；对外层变量的真实 assignment 会保留“body 至少执行一次”的语义。

### `switch`

switch body 建立共享 lexical scope；每个 case 从同一 base 环境独立分析并保守 join，同时保留“不匹配任何 case”的路径。嵌套 block 和直接 case declaration 都能 shadow 外层 receiver，case 内普通对象调用不会借用外层 framework provenance。

## 6. 合并伪入口与 framework evidence

端到端回归把 Python、TypeScript 与 JavaScript 反例放在同一临时仓库：

- Python module comprehension walrus
- Python function-local comprehension walrus 前置调用
- TS generic typed function parameter
- TS typed arrow + return type
- TS generic method + return type
- bare `for..of` assignment target
- typed `for..of` declaration target
- `var` function-scope loop target与 loop 后调用
- `do..while` block shadow
- `switch` block shadow
- malformed unclosed call

验收结果：

| 检查 | 结果 |
| --- | ---: |
| 对应 confirmed / candidate feature | 0 |
| `technology-claim:framework` evidence | 0 |
| `validate_index()` | valid |
| HTML 中对应入口 | 0 |

合法 FastAPI、Express、Fastify、Koa Router、Commander 仍由既有回归确认；正常 framework feature 继续持有 import、factory、callsite 三段独立 evidence。

## 7. Dangling relationship 三件套一致

coverage 不再单独以“id 存在且 target 非空”判断 resolved，而是与 tutorial / CodeMap 共同调用 `_valid_relationship()`。只有 source id 和 target id 都存在的 relationship 才能计入 resolved。

对 `source_id="" / target_id="target"` 的输入，现在三者统一为：

- tutorial：0 confirmed relationship，step 为 `location-only`；
- CodeMap：0 resolved edge，1 个 relationship gap；
- coverage：`resolved_relationships=false`，metric 为 0。

缺 id、缺 source、缺 target 因而使用同一个 closure contract。

## 8. 六仓与 Waku 回归

最终候选树重新冷建六个完整参考 clone，并执行 Golden 与逐仓 validator：

| 合同 | 结果 |
| --- | ---: |
| 固定 Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationships | 18 |
| known technology claims | 59 |
| 六仓 validate | 6 / 6 valid |

Waku 真实冷索引也在同一最终运行中通过：memory、graph、loop、gateway 仍为 `entrypoint-candidate` + `confidence=candidate`，独立于六仓 curated 排名。

## 9. 验证证据

- Teaching + 六仓 + Waku + validator：53 tests，全部通过，耗时 86.052 秒。
- 其中六仓 Golden 保持 19 / 66 / 18 / 59；Waku 冷索引通过。
- 真实 Google Chrome：`tests.test_report_mobile_browser` 1 / 1 通过；同时验证 1440×900 与 390×844、零横向溢出、首屏、details 物理点击和仓库内 source-link 物理点击。
- Ruff：`All checks passed!`。
- `python -m compileall -q src tests`：通过。

本轮未修改 report CSS / HTML 结构、capability catalog、Golden fixture、core validator、Skill、正式 examples 或七个参考 clone。

## 10. 修改文件

- `src/repo_teacher/features.py`
- `src/repo_teacher/artifacts.py`
- `tests/test_features.py`
- `tests/test_artifacts.py`
- `docs/audits/teaching-fix-round7.md`

## 11. 简化与剩余边界

本轮没有新增依赖，也没有增加第二套 analyzer。主要简化是：

- Python walrus 复用现有 `_ScopeIR` 与 `_joined_values()`；
- JS / TS 参数、declaration 与 loop target 复用同一 binding-name parser；
- for / do / switch 复用现有 snapshot / restore / join；
- coverage 复用已有 `_valid_relationship()`。

仍需独立复审的边界：动态 computed property、运行时 monkey patch、宏 / transpiler 扩展、无法静态解析的 JSX / decorator 组合仍会保守降级为 unknown 或不生成 feature。这是 fail-closed 设计，不应在未来为了提高召回率绕过 provenance identity、结构完整性或 CFG join。

新的独立 reviewer 应重点重放：nested comprehension walrus、TS typed arrow / generic method、bare 与 `var` for target、do / switch block 和 direct declaration、mismatched delimiter、三段 evidence 零泄漏、missing-source / missing-target 对称关系，以及六仓 / Waku / Chrome 不回归。
