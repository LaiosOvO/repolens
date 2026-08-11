# Teaching / Feature / Tutorial / CodeMap Round 11 最终独立复审

**结论：REQUEST CHANGES / BLOCK**  
**Architecture status：BLOCK**

日期：2026-08-10  
复审性质：未参与 Round 10 实现的最终只读复审。除本报告外，未修改产品源码、测试、examples、fixture 或参考仓库。

## 一句话结论

Round 10 的主要收缩方向成立：class body comprehension 指定 10 类全部在运行时 `NameError`，且公开链路为 0 feature / 0 framework evidence / HTML 0；普通 Python lambda、Python nested function、JS arrow、JS nested function 的 late rebind 也不再 confirmed；14 个 returned / stored / deferred / generator / class / conditional / cross-scope 反例全部归零；ghost source / target、精确三段 validator、六仓 Golden、Waku、Chrome、55 项专项、261 项全量、Ruff 与 compileall 均达到记录中的结果。

但最终确认合同仍存在可稳定复现的阻断：

1. JS 分析器会在**未执行的 deferred function / arrow 声明期**把 factory 赋值提前写回外层；`owner_scope_id` 又保存可回收的 Python `id(scope)`，随后另一个函数 scope 复用同一地址时，跨 scope provenance 被伪装为“当前函数自己创建”。运行时必然 `TypeError` 的入口得到 1 feature、完整 3 段 evidence、validator valid、HTML 命中；
2. JS lexer 会静默丢弃 `@` 等未知字符，将 `node --check` 明确拒绝的源码净化成合法 token 序列并生成 confirmed feature；
3. 合法的 terminal module direct call 与多行 JS ordinary function feature 会被 validator 自己拒绝，`export function` 正例还会直接漏报；
4. 最近未来 symbol、同行多表达式与多行 factory 仍能把受抑制伪入口带入 entry / framework evidence 和 HTML。

因此当前 framework feature、validator 与最终 HTML 不能作为完成交付。

## P0 — deferred JS 外层写回与可复用 `id(scope)` 伪造同作用域 provenance

最小合法 CommonJS：

```javascript
const express = require('express');
let leaked;
function first() { leaked = express(); }
function second() { leaked.get('/audit-js-id-reuse-function-false', handler); }
second();
```

`first()` 从未调用，Node stub 运行得到：

```text
runtime                    TypeError
```

公开链路现场结果：

```text
false confirmation repeat 100 / 100
feature                    1 × GET /audit-js-id-reuse-function-false
confidence                 static-entry
framework evidence         3（import / factory / call）
validator                  valid=True, issues=0
HTML                       hit
```

独立 arrow 变体同样为 20 / 20 误确认：

```javascript
const express = require('express');
let app;
const init = () => { app = express(); };
function register() { app.get('/audit-js-owner-arrow-false', handler); }
register();
```

根因链：

- `src/repo_teacher/features.py:94-102` 的 `_FrameworkBinding.owner_scope_id` 只保存整数 `id(scope)`；
- `src/repo_teacher/features.py:1222-1230` 的 `_assign()` 会把 deferred body 中的赋值写入已存在的外层 binding；
- `src/repo_teacher/features.py:1378-1400` 与 `:1540-1567` 在声明位置立即分析 arrow / ordinary function body，分析结束后临时 `_ScopeIR` 可被释放；
- `src/repo_teacher/features.py:1438-1454` 用 `id(self.scope)` 创建 factory ownership；
- `src/repo_teacher/features.py:1308-1313` 仅以整数相等判断 same-scope，下一函数复用地址后即错误放行。

这不是“实际可达性未知”的保守余量：factory 赋值发生在未执行函数中，真实调用点 receiver 仍是 `undefined`，三段 provenance 明确声称的 receiver identity 不存在。

## P0 — malformed JavaScript 被 lexer 静默净化后 confirmed

最小反例：

```javascript
const express = require('express');
function register() { const app = express(); @ app.get('/audit-js-malformed-one-line-false', handler); }
```

现场：

```text
node --check               SyntaxError / exit 1
feature                    1 × GET /audit-js-malformed-one-line-false
framework evidence         3
validator                  valid=True, issues=0
HTML                       hit
```

`src/repo_teacher/features.py:883-907` 只记录已知 identifier / operator / punctuation；不在集合中的 `@` 经过无条件 `index += 1` 被丢弃。随后 `:1287-1337` 看到的已是完整直接 call token 序列，`_js_boundaries()` 在 `:1912-1917` 也没有语法有效性门。validator 的 canonical rebuild 重放同一错误 analyzer，不能独立识别该伪造。

## P1 — 允许的 module / ordinary-function 正例与 validator 不闭合

以下均为独立临时仓、公开 `build_index()` → `validate_index()` 重放：

| 正例 | feature | validator |
| --- | ---: | --- |
| Python terminal module direct call | 1 exact-entry | **False** |
| JavaScript terminal module direct call | 1 static-entry | **False** |
| Python 多行 ordinary function direct call | 1 exact-entry | True |
| CommonJS 多行 ordinary function direct call | 1 static-entry | **False** |
| ESM `export function` 内 definite-before-direct-call | **0** | True |

前三个失败输出相同或同源：

```text
feature-claim-mismatch:
entry symbol, first step, and entry evidence do not close
```

原因：

- `src/repo_teacher/features.py:2213-2227` 在没有可关联 symbol 时生成 `symbol_id=None` 的精确 callsite fallback step；
- `src/repo_teacher/validation.py:450-469` 只要 first step 存在，就无条件要求有效 symbol closure；
- JS regex symbol 不能覆盖多行函数 body 时，函数内 call 也落入该矛盾；
- `src/repo_teacher/features.py:1837-1886` 只有 statement 首 token 为 `function` 才进入 `_analyze_function()`，`export function` 被当作普通表达式而漏报。

这违反“module scope direct 与 module 直属 ordinary function definite-before-direct-call 正例必须保留”的明确合同。feature 被创建但完整 index 无法验证，不算保留成功。

## P1 — 被抑制伪入口仍可进入 entry / framework evidence 与 HTML

### 最近未来 symbol 泄漏

```javascript
const express = require('express');
const app = express();
app.get('/audit-js-adjacent-live', handler);
const probe = () => app.get('/audit-js-adjacent-false', handler);
```

结果：合法入口 1、伪 feature 0、伪 framework evidence 0，但伪字符串进入 1 条 `symbol-definition` evidence 与 HTML，validator 仍 valid。`src/repo_teacher/features.py:1920-1925` 在没有 containing symbol 时选择最近的**未来** symbol，导致 `probe` 被错误绑定为 live route 的处理 symbol；`:2039-2047` 随后把其定义行写入 evidence。

### 同一物理行泄漏

```python
from fastapi import FastAPI
def register():
    app = FastAPI(); app.get('/audit-py-same-line-live'); probe = lambda: app.get('/audit-py-same-line-false')
```

结果：live feature 1、伪 feature 0，但伪字符串进入 `entry-declaration`、framework `factory`、framework `call` 三条 evidence 与 HTML，validator valid。

### 多行 factory 泄漏

```python
from fastapi import FastAPI
app = FastAPI(
    lifespan=lambda: ghost.get('/audit-py-factory-decorator-false')
)
@app.get('/audit-py-factory-decorator-live')
def live(): return 1
```

结果：live feature 1、伪 feature 0，伪字符串进入 framework `factory` evidence 与 HTML，validator valid。

`src/repo_teacher/features.py:81-90` 与 `:2257-2278` 的 evidence 仍以完整物理行 / AST call range 为单位；`src/repo_teacher/validation.py:368-375` 只验证 range/hash 与 entry call 的闭合，不能证明 snippet 不含被 analyzer 明确抑制的第二个调用。

## 已闭合合同的独立重放

### class body comprehension：10 / 10

每案独立 `compile()`、stub runtime、临时仓 `build_index()`、`validate_index()`、`render_report()`：

| 位置 | runtime | feature | framework evidence | HTML |
| --- | --- | ---: | ---: | ---: |
| list result | NameError | 0 | 0 | 0 |
| set result | NameError | 0 | 0 | 0 |
| dict result | NameError | 0 | 0 | 0 |
| consumed generator result | NameError | 0 | 0 | 0 |
| filter | NameError | 0 | 0 | 0 |
| second iterable | NameError | 0 | 0 | 0 |
| nested comprehension | NameError | 0 | 0 | 0 |
| lambda inside comprehension | NameError | 0 | 0 | 0 |
| lambda default inside comprehension | NameError | 0 | 0 | 0 |
| decorator expression containing comprehension | NameError | 0 | 0 | 0 |

10 / 10 index 均 `valid=True, issues=0`。

### ordinary late rebind 与跨 scope 负例

不含上述外层写回 / id-reuse 绕过的基础矩阵：

- Python lambda late rebind：runtime `AttributeError`，0 feature / 0 framework evidence / HTML 0；
- Python nested function late rebind：runtime `AttributeError`，0 / 0 / 0；
- JS arrow late rebind：runtime `TypeError`，0 / 0 / 0；
- JS nested function late rebind：runtime `TypeError`，0 / 0 / 0；
- returned / stored / deferred / generator / class / conditional / cross-scope 的 Python + JS 共 **14** 个伪入口：0 feature、0 framework evidence、evidence / HTML 0，validator valid。

这说明普通声明后 rebind 的修复本身有效；P0 是 deferred body 写回外层与 ownership token 可复用形成的新绕过。

### ghost source / target

两个对称输入均得到：

```text
tutorial confirmed                 0
slice relationship_status          location-only
slice relationship_id              ""
CodeMap resolved_edge_ids          0
CodeMap relationship_gaps          1
coverage resolved_relationships    false / 0
```

### validator 三段证据

合法 decorator baseline：

```text
stages        [import, factory, call]
line ranges   [(1,1), (2,2), (3,3)]
count         3
validator     valid
```

重新计算 integrity 后的 5 个变形全部被拒绝，并均含 `feature-claim-mismatch`：

| 变形 | 结果 |
| --- | --- |
| 缺 call stage | reject |
| stage 倒序 | reject |
| 伪造 call analyzer 为 factory | reject |
| call evidence 改指 factory 行 | reject |
| summary 夸大为生产流量 / runtime 必然可达 | reject |

### 六仓 Golden 与 Waku cold build

独立 cold build 汇总：

| 项目 | identity | curated | slices | resolved | known tech | valid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SourceBridge | 1 | 3 | 11 | 6 | 8 | 1 |
| PocketFlow code2tutorial | 1 | 2 | 7 | 0 | 6 | 1 |
| OpenWiki | 1 | 3 | 10 | 0 | 9 | 1 |
| Understand Anything | 1 | 3 | 9 | 0 | 11 | 1 |
| CodeBoarding | 1 | 3 | 11 | 7 | 11 | 1 |
| DeepWiki Open | 1 | 5 | 18 | 5 | 14 | 1 |
| **合计** | **6 / 6** | **19** | **66** | **18** | **59** | **6 / 6** |

Waku cold build：memory / graph / loop / gateway 共 4 项，全部 `entrypoint-candidate` + `confidence=candidate`，`capability-cluster=0`，validator valid，不进入 curated。

## 验证命令与数字

公开链路反例均以系统临时目录创建最小仓，核心调用为：

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
# 每案独立写入 tempfile.TemporaryDirectory()；
# build_index(root) -> validate_index(index, root) -> render_report(index)
# runtime 另由 compile/exec stub 或 node stub / node --check 重放。
PY
```

正式门：

```bash
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round11-targeted-pyc \
PYTHONPATH=src .venv/bin/python -m unittest -v \
  tests.test_features tests.test_artifacts tests.test_report \
  tests.test_reference_ground_truth tests.test_validation
```

```text
Ran 55 tests in 101.083s
OK
```

```bash
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round11-full-pyc \
PYTHONPATH=src .venv/bin/python -m unittest discover -v
```

```text
Ran 261 tests in 188.050s
OK (skipped=3)
```

3 个 skip 均因该 venv 未安装 Playwright；要求的报告浏览器门随后使用已安装 Playwright 的系统 Python 独立执行：

```bash
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round11-browser-system-pyc \
PYTHONPATH=src python3 -m unittest -v tests.test_report_mobile_browser
```

```text
Ran 1 test in 4.607s
OK
```

该测试使用真实 `/Applications/Google Chrome.app`，覆盖 1440×900 与 390×844，物理点击 details 与 source link，并检查首屏、document/body width 和 overflow offender。

```bash
ruff check --no-cache src tests
# All checks passed!

PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round11-compile-pyc \
PYTHONPATH=src .venv/bin/python -m compileall -q src tests
# exit 0
```

## 独立审查线

专用 `code-reviewer` 与 `architect` 角色在执行前均因账户不支持其固定 `gpt-5-codex` 模型返回 HTTP 400，没有产生审查意见。随后以两个继承当前可用模型、上下文隔离、职责分离的只读 fallback lane 完整复审：

- code/spec lane：`REQUEST CHANGES`；
- architecture/devil's-advocate lane：`BLOCK`。

主复审对本文所有阻断另行使用公开链路复现，不把 fallback lane 的结论当作唯一证据。

## 解除阻断的最低条件

1. **隔离 deferred side effects。** JS function / arrow / callback 的声明期分析不得把 body assignment 提交到 enclosing scope；若不能证明真实调用与顺序，外层 binding 必须保持原值或 unknown。
2. **替换裸 `id(scope)` ownership。** 使用分析生命周期内不可复用的单调 scope token，或保留稳定对象 identity；禁止任何逃逸 binding 以可回收对象地址作为同作用域证明。
3. **增加 JS 语法 fail-closed 门。** 未知 token 不得静默丢弃；在语法有效性未证明时，不得生成 confirmed framework boundary。至少加入 `@`、未闭合结构与邻近未知字符反例。
4. **统一 builder / validator 的 callsite fallback。** terminal module direct call 没有 symbol 时，精确 callsite step 必须可验证；不得强绑任意未来 symbol。Python module、JS module、CJS / ESM 多行 ordinary function 与 `export function` 正例必须通过完整公开链路。
5. **结构化 evidence。** entry / factory / call evidence 必须指向目标表达式，而不是整行或包含 nested callback 的整段 AST call；最近未来 arrow、同行伪入口、多行 factory 伪入口在 evidence 与 HTML 中都必须字面为 0。
6. 修复后重跑本文 P0/P1 最小反例、class 10 类、4 个 ordinary late-rebind、14 个 fail-closed 负例、ghost 双端、5 个 validator 变形、55 项专项、261 项全量、六仓 6/6 与 19/66/18/59、Waku、真实 Chrome 双视口、Ruff 与 compileall，再交由未参与修复的 reviewer 复审。

在 deferred ownership 伪造、malformed JS 误确认以及正例 / evidence 闭合问题消失前，最终结论保持 **REQUEST CHANGES / BLOCK**。
