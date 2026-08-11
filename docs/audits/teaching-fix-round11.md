# Teaching / Feature 修复记录（Round 11）

日期：2026-08-10  
范围：Round 11 独立复审指出的 JS deferred ownership、非法 token、framework evidence、module callsite fallback 与 ESM export 正例。  
状态：实现者修复与回归已完成；本文不自行给出 PASS，等待未参与本轮实现的 Agent 独立复审。

## 一句话结果

本轮没有扩展为完整 Python / JavaScript 解释器，而是继续收紧确认面：作用域 ownership 改为不可复用的单调 token；未执行 function / arrow 的赋值不能写回外层；未知 JS token 整文件 fail closed；无法用现有行级证据排除同行伪入口时，合法调用也不提升为 confirmed。模块级合法直接调用没有符号时，则使用可由 validator 独立闭合的精确 callsite fallback。

## 1. TDD 公开 seam

新增回归只通过用户可见链路验证：

`build_index()` → `validate_index()` → `render_report()`

红测先稳定复现：

- 未执行 function / arrow 把 `express()` 赋值写回外层，随后跨函数伪造 route；
- `@ app.get(...)` 中的非法 `@` 被 lexer 静默丢弃后生成 confirmed feature；
- module direct route 生成 `symbol_id=None` callsite step，但 validator 无条件要求 symbol；
- 同行 Python lambda、多行 FastAPI factory callback、邻近 JS arrow 的伪 route 字符串进入 evidence / HTML；
- `export function` 内的 same-function definite-before-direct-call 漏报。

修复后的测试名称：

- `test_deferred_javascript_assignments_cannot_escape_or_reuse_scope_identity`
- `test_unsupported_javascript_token_fails_closed_for_the_whole_file`
- `test_framework_evidence_never_includes_deferred_sibling_boundaries`
- `test_exported_esm_function_keeps_same_function_boundary_recall`
- `test_framework_module_callsite_without_symbol_is_a_closed_fallback`

## 2. 不可复用 scope ownership 与 deferred 写屏障

`_ScopeIR` 现在拥有进程内单调递增、不会因对象释放而复用的 `scope_token`。Python 与 JS framework binding 都记录该 token，不再保存 CPython `id(scope)`。

JS function、method 与 arrow scope 同时设置 `write_barrier`。声明期分析仍可读取 lexical parent，用于理解捕获的 import / binding；但赋值命中 parent 时只在当前 deferred scope 内建立局部分析值，绝不提交到 parent。这样既保留 same-function 内“先 factory、后直接调用”的正例，也阻断未执行 callback 对外层 provenance 的污染。

## 3. 未知 JS token 整文件 fail closed

lexer 不再对未知字符执行无条件跳过：数字和常见 JS / TS punctuation 被显式 token 化，其余未知字符直接抛出 `ValueError`。`_js_boundaries()` 与 JS executable marker 都把该错误降为“无已确认边界”。

因此 `@ app.get(...)` 不会被净化为合法调用。该策略也意味着含当前 lexer 未支持语法的文件会损失召回，而不会得到伪确认。

## 4. Framework evidence 的保守精度

- Python factory provenance 从整个 `ast.Call` 范围收窄到 factory callee 自身所在行；多行 `FastAPI(...)` 参数中的 deferred route 不再进入 factory evidence。
- `_symbol_for_line()` 只接受真正包含 callsite 的 symbol，不再吸附最近的未来 symbol；模块级 direct call 因而不会借用后面的 arrow / function 定义。
- 行级 Evidence schema 无法表达同一物理行的列范围。若 import / factory / call 三个证据行中同时出现另一个 framework boundary，当前 feature 整体不确认，而不是把混合行作为“精确证据”。这是有意的 fail-closed 取舍。

上述三类 Round 11 伪字符串在 `features`、全部 evidence snippet 与 standalone HTML 中均为字面 0。

## 5. Module callsite fallback 与 validator 闭合

当 module direct call 没有 containing symbol 时，builder 只生成一个 callsite fallback step。validator 仅在完整 framework import / factory / call 三段合同已经成立且 `entry_symbol_id=None` 时接受，并逐字段锁定：

- 唯一 step、`order=1`；
- path 与 exact entry line 一致；
- evidence 只能引用该 entry evidence；
- `symbol_id=None`、`relationship_id=None`；
- title 与保守 explanation 必须是 canonical 文案。

重算 integrity 后篡改 fallback 行号仍被 `feature-claim-mismatch` 拒绝。普通 symbol-backed feature 继续走原 symbol closure 门。

## 6. ESM export 正例

statement dispatcher 现在显式识别 `export function`、`export default function`、`export async function`，并复用原 ordinary-function 分析；也为 export declaration / class 保持已有保守处理。没有新增动态调用或 callback 执行推断。

## 7. 六仓 Golden 与 Waku

既定真实仓库门在当前源码下通过：

| 合同 | 结果 |
| --- | ---: |
| 固定 Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationships | 18 |
| known technology claims | 59 |
| 六仓 validator | 6 / 6 valid |

Waku cold corpus 的 memory / graph / loop / gateway 四项继续为 `entrypoint-candidate` + `confidence=candidate`，没有 `capability-cluster`，validator valid，仍不进入六仓 curated 技术排名。

## 8. 验证证据

```text
PYTHONPATH=src .venv/bin/python -m unittest -v \
  tests.test_features tests.test_artifacts tests.test_report \
  tests.test_reference_ground_truth tests.test_validation

Ran 60 tests in 75.842s
OK
```

60 项包含原 55 项门与本轮 5 个新回归，也包含六仓真实 cold Golden 和 Waku compatibility cold build。

```text
uv run --offline ruff check \
  src/repo_teacher/features.py src/repo_teacher/validation.py \
  tests/test_features.py tests/test_validation.py tests/test_artifacts.py

All checks passed!
```

```text
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round11-fix-compile-pyc \
PYTHONPATH=src .venv/bin/python -m compileall -q \
  src/repo_teacher/features.py src/repo_teacher/validation.py \
  tests/test_features.py tests/test_validation.py tests/test_artifacts.py

exit 0
```

## 9. 修改文件

- `src/repo_teacher/features.py`
- `src/repo_teacher/validation.py`
- `tests/test_features.py`
- `tests/test_validation.py`
- `docs/audits/teaching-fix-round11.md`

没有修改 `artifacts.py`、`report.py`、Golden fixture、正式 examples、主 HTML 或任何参考仓。

## 10. 简化与剩余风险

本轮的主要简化是删除不可靠确认路径，而不是继续添加名称正则或模拟 callback runtime。剩余边界：

1. JS / TS lexer 仍是保守子集；遇到未知 token 会整文件放弃 framework confirmed recall。
2. Evidence schema 目前只有行范围，没有列范围；同行混合正负调用只能整体不确认。未来若必须保留同行合法调用，应先为 EvidenceRef、source validation 与 HTML renderer 增加统一的 byte / column range 合同，不能只截短显示文本。
3. 静态 framework feature 仍只证明源码中的同作用域直接声明，不证明部署可达性或真实运行顺序。
4. 本文是实现记录，不替代新的独立 adversarial re-audit。
