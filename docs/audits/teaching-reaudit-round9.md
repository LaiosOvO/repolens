# Teaching / Feature / Tutorial / CodeMap Round 9 独立复审

**结论：REQUEST CHANGES / BLOCK**  
**Architecture status：BLOCK**

日期：2026-08-10  
复审性质：未参与 Round 8 实现的独立只读复审。除本报告外，未修改产品源码、测试、fixture、examples 或参考仓库。

## 一句话结论

Round 8 已修复 Assign RHS comprehension walrus 的原始 P0：本轮扩展的 **32 项** Assign / AnnAssign / AugAssign / NamedExpr × list / set / dict / generator comprehension、nested call、default、decorator、base 矩阵全部得到 0 feature / 0 framework evidence / HTML 0 命中；Round 8 合并的 17 个伪入口也继续保持全零。合法模块、普通函数、nested function body 和 class body 边界没有回归。

但是 lambda 的执行作用域仍没有预建其 body 内的 compile-time locals。只要 lambda body 在调用模块级 `app.get(...)` 之后出现 `(app := ...)`，当前 visitor 会先把调用错误解析到模块级 FastAPI binding，再处理 walrus。该伪入口生成 `exact-entry`、完整三段 framework evidence，通过 validator 并进入 HTML。这是 Round 6—8 同一 Binding / Scope P0 在 lambda 自身作用域中的残留，因此当前 HTML 仍不能发布。

## 阻断问题

### P0 — lambda body 的 walrus local 未在调用点前建立 compile-time shadow

最小合法 Python：

```python
from fastapi import FastAPI
app = FastAPI()
probe = lambda: (app.get('/lambda-before-walrus-false'), (app := object()))
```

标准库 `ast` / `symtable` 现场结果：

```text
ast_parse=ok
scope_type= function
app_is_local= True
app_is_free= False
app_is_global= False
app_is_assigned= True
```

因此 lambda 内第一个 `app.get(...)` 不能读取模块级 FastAPI binding；实际执行 lambda 时会在该调用点遇到尚未初始化的 lambda local。静态分析至少必须降级为 unknown。

正式 `build_index()` → `validate_index()` → `render_report()` 链路的现场输出：

```text
matching feature       GET /lambda-before-walrus-false, exact-entry
framework evidence     3
  app.py:1             from fastapi import FastAPI
  app.py:2             app = FastAPI()
  app.py:3             probe = lambda: (...)
validate_index         valid=True, issues=0
HTML target hit        true
```

同一问题不是只出现在直接 walrus。将 lambda body 的第二个 tuple element 分别替换为下列结构，六种输入均为 **1 feature / 3 framework evidence / HTML 命中 / validator valid**：

| lambda body 后续写入形态 | feature | framework evidence | HTML | validator |
| --- | ---: | ---: | --- | --- |
| direct `(app := object())` | 1 | 3 | hit | valid |
| list comprehension | 1 | 3 | hit | valid |
| set comprehension | 1 | 3 | hit | valid |
| dict comprehension | 1 | 3 | hit | valid |
| generator expression | 1 | 3 | hit | valid |
| nested `consume(transform(list-comp))` | 1 | 3 | hit | valid |

根因位于 `src/repo_teacher/features.py:524-538`：

- `visit_Lambda()` 只把 `_python_argument_names(node.args)` 放进 lambda 的 `local_names`；
- 它没有像 `_visit_function()` 在 `:485-504` 那样，对当前执行作用域的 body 先运行 local collector；
- 随后 `self.visit(node.body)` 按表达式顺序扫描。前置 `app.get()` 经 `_ScopeIR.resolve_binding()` 在当前 lambda 找不到 local marker，于是错误回退到模块 scope；
- 等 `visit_NamedExpr()` 在 `:470-479` 写入 lambda scope 时，伪 route 已经被确认，三段 evidence 也已经形成。

Round 8 的“不穿透 lambda body”只保护了**外层 collector 不把 lambda body 的写入算成外层 local**；它没有建立**lambda 自身 body 的 compile-time local 集合**。这两个合同必须同时成立。

## Round 8 P0 与扩展结构矩阵重放

### Assign RHS 原始 P0

原反例：

```python
def register():
    app.get('/py-before-assigned-comp-walrus-false')
    items = [(app := object()) for item in clients]
```

本轮通过正式公开链路重放，结果为 0 feature / 0 framework evidence / HTML 0 命中；原始 P0 已修好。

### 32 项结构矩阵

每个 case 都在独立临时仓中经 `ast.parse()` 与正式 `build_index()` / `validate_index()` / `render_report()` 执行，避免一个 case 的正例 evidence 污染另一个 case 的计数。

| 结构组 | case 数 | 结果 |
| --- | ---: | --- |
| Assign / AnnAssign / AugAssign / NamedExpr × list / set / dict / generator comprehension | 16 | 16 / 16 为 0 feature、0 framework evidence、HTML 0，validator valid |
| 四种 assignment 形态外包 nested call | 4 | 4 / 4 同上 |
| nested function defaults × 四种 comprehension | 4 | 4 / 4 同上 |
| decorators × 四种 comprehension | 4 | 4 / 4 同上 |
| class bases × 四种 comprehension | 4 | 4 / 4 同上 |
| **总计** | **32** | **32 / 32 PASS** |

这证明 Round 8 对 `Assign.value`、`AnnAssign.annotation/value`、`AugAssign.value`、`NamedExpr.value`、default、decorator 与 base 的遍历是有效的；本轮 BLOCK 不是原 Assign RHS 修复失效，而是 lambda 自身 scope 初始化仍不完整。

### lexical boundary 与合法正例

独立合并正负例得到：

```text
GET /module-live                    present
GET /function-live                  present
GET /after-nested-body-live         present
GET /after-class-body-live          present
GET /after-lambda-body-live         present
GET /nested-before-walrus-false     absent
GET /lambda-before-walrus-false     present  <-- P0
validate_index                      valid
```

因此：

- nested function body 的 assignment/comprehension walrus 没有污染外层，且 nested function 自身的前置调用正确被 compile-time local 阻断；
- class body 的直接 assignment / NamedExpr 没有污染包围函数；
- lambda body 的写入没有污染 module，lambda 后的模块 route 仍保留；
- 唯一失败是 lambda **内部**没有预建 body local，导致 lambda 内赋值前调用错误穿透到 lexical parent。

## 合并 17 反例与 Round 7 / Round 6 合同

### Round 8 合并 17 伪入口

现场复刻 `test_combined_scope_and_cfg_adversaries_never_become_framework_features` 的四文件临时仓，覆盖 8 个 Python walrus / assignment / default 反例、8 个 JS / TS typed / for / do / switch 反例和 1 个 malformed call：

```text
counterexamples           17
matching feature count     0
framework evidence count   0
HTML hit count             0
validate_index             valid=True, issues=0
```

该项 PASS。

### Scope、JS / TS、dangling、parallel、typed

- Python 既有 function / comprehension target / with / except / del / try / match / short-circuit scope 与 CFG join 回归通过；新增 lambda 反例是现有测试未覆盖的同类缺口。
- JavaScript catch / for / class method / object method / destructuring / var hoist / brace-less branch / compound initializer / arrow 合同通过。
- TS generic typed function、typed arrow return、generic method、typed `for..of` 与 bare / var target 的合并反例均为 0 feature。
- parallel `calls` / `contains` 同 endpoint 关系按 identity 保留 2 条；专项通过。
- dangling relationship id、missing-source 与现场补充的对称 missing-target 输入均统一降级：tutorial confirmed=0、step location-only、relationship id 清空、CodeMap resolved=0 / gap=1、coverage check=false / metric=0。
- 六仓 typed relationship 的 source slice、target slice、callsite range、allowed kind、endpoint closure 与固定 relationship identity 全部由 Golden 通过。

## 六仓、不同参考项目与 Waku

53 项专项中的真实六仓 cold Golden 逐仓执行固定 Git identity、源码 blob、capability slice、typed callsite、technology evidence、CodeMap closure 与 `validate_index()`。现场结果：

| 合同 | 结果 |
| --- | ---: |
| 固定 Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationship identities | 18 |
| known technology claims | 59 |
| 逐仓 validator | 6 / 6 valid |

报告合同仍逐项展示 SourceBridge、PocketFlow code2tutorial、OpenWiki、Understand Anything、CodeBoarding、DeepWiki Open 六个不同项目及各自机制、映射、源码范围和未采用边界；不是以单一项目替代六仓参考。

Waku 真实 cold index 同时通过：memory / graph / loop / gateway 仍全部为 `entrypoint-candidate` + `confidence=candidate`，带 `compatibility-corpus:waku-not-curated`，不生成 curated `capability-cluster`；HTML 保留“Waku：单独验证，不进入六仓 curated 技术排名”，不出现“六仓机制对照”。该项 PASS。

## 浏览器、测试与静态检查

| 命令 / 门 | 现场结果 |
| --- | --- |
| `PYTHONPATH=src .venv/bin/python -m unittest -v tests.test_features tests.test_artifacts tests.test_report tests.test_reference_ground_truth tests.test_validation` | **53 / 53 PASS**；`Ran 53 tests in 87.211s`；无 skip |
| Round 8 合并 17 伪入口正式链路 | **0 feature / 0 framework evidence / HTML 0**；validator valid |
| Round 9 32 项结构矩阵 | **32 / 32 PASS** |
| lambda direct/list/set/dict/generator/nested-call 派生反例 | **6 / 6 错误生成 1 exact-entry / 3 framework evidence / HTML 命中；validator 错误放行** |
| `.venv` 浏览器预检 | Playwright 不在该 venv，明确 skip；不计为通过证据 |
| `PYTHONPATH=src python3 -m unittest -v tests.test_report_mobile_browser` | **1 / 1 PASS**；`Ran 1 test in 2.725s`；真实 Google Chrome；1440×900 / 390×844 |
| `ruff check src tests` | `All checks passed!` |
| `PYTHONPATH=src .venv/bin/python -m compileall -q src tests` | exit 0 |

浏览器测试以 `report_path.as_uri()` 加载真实 `file://` 报告，在两个 viewport 中物理点击 details 与 source link，检查首屏、document/body width 和 overflow offender。Chrome launch 只有 `executable_path` 与 `headless=True`，未添加 `--allow-file-access-from-files`、禁用 web security 或其他跨 scheme / file 策略绕过。source link 的默认导航由测试 click listener 阻止，所以本报告只确认 href 边界与 click-event，不额外声称浏览器实际打开源码文件。

## 独立审查能力说明

按代码复审流程尝试启动专用 code-reviewer 与 architecture/devil's-advocate 两条额外只读 lane；两者均因当前 ChatGPT 账户不支持其固定 `gpt-5-codex` 模型而在执行前返回 HTTP 400，没有产生可采用的审查证据。本报告没有把缺失的 lane 冒充为批准依据。由于主复审已独立、可重复地得到上述 P0，最终 verdict 无论如何都是 REQUEST CHANGES / BLOCK。

## 解除阻断的最低条件

1. lambda scope 在访问 body 前必须预建 body 自己的 compile-time locals；可复用 `_PythonLocalCollector` 对单个 expression 的遍历结果，并与参数名合并。该 collector 必须继续遵守：nested lambda 只遍历 default、不进入 nested body；nested function / class body 不泄漏；comprehension iteration target 不登记为 lambda outer local，而其中 walrus target要登记。
2. 新增公开链路回归，不直接断言私有 helper：至少覆盖 direct walrus、list / set / dict / generator comprehension 与 nested call 六种 lambda body 形态；每个 lambda 内赋值前 FastAPI 调用都必须为 0 feature / 0 framework evidence / HTML 0。
3. 同时保留合法模块/函数 route、lambda 后模块 route、nested function body 与 class body 不污染外层的正例，防止通过全局禁用 lambda 分析来“修复”。
4. 修复后重跑 17 合并反例、32 项 Round 9 结构矩阵、53 项专项、六仓 19 / 66 / 18 / 59、6 / 6 validator、Waku、Ruff、compileall 与真实 Chrome 390 / 1440，再交由未参与修复的 reviewer 独立复审。

在 lambda compile-time local P0 消失前，Repo Teacher 教学 / HTML 的最终结论保持 **REQUEST CHANGES / BLOCK**。
