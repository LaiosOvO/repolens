# Teaching / Feature 修复记录（Round 9）

日期：2026-08-10  
范围：lambda compile-time locals、lambda default / nested lambda 作用域、完整 expression-container 回归、非法 Python 语义 fail closed。  
状态：实现和实现者验证完成，teaching 产品源码已冻结，等待新的独立 Agent 复审；本文不自行给出 PASS。

## 一句话结果

Round 9 的问题不是 lambda body walrus 的执行顺序，而是 lambda scope 在扫描 body 前没有建立 Python 编译期 local 集合。本轮让每个 lambda 用同一个 `_PythonLocalCollector` 独立预扫描自己的 body expression，再进入正式 provenance 分析。参数与 body local 属于 lambda；defaults 仍先在 lexical parent 中求值；nested lambda body 不泄漏到外层，但 nested lambda defaults 按 Python 语义在外层执行。合并公共链路现在对 **78 个伪入口**得到 0 feature、0 framework evidence、HTML 0 命中。

## 1. Test-first 公共链路

测试继续从用户可见 seam 验证，不直接断言私有 collector：

`build_index()` → `validate_index()` → `render_report()`

扩展回归后，修复前 `test_combined_scope_and_cfg_adversaries_never_become_framework_features` 失败；合法 lambda 只读外层 framework 的正例测试同期通过。修复后两者转绿。

公共回归当前合并：

- Round 8 原 17 个 Python / JS / TS / malformed 反例；
- Round 8 的 32 项 assignment / nested-call / default / decorator / class-base 结构矩阵；
- 26 项合法 lambda-body expression container；
- nested lambda body 1 项；
- 不合法 `await` lambda 的 walrus 与 readonly receiver 2 项。

总计 78 个入口字符串均不出现在 feature、framework evidence 或 HTML。

## 2. 每个 lambda 独立建立 compile-time locals

`src/repo_teacher/features.py:364-367` 增加 expression 入口，复用已有 `_PythonLocalCollector` 遍历单个 lambda body。`visit_Lambda()` 在 `:530-545` 按以下顺序处理：

1. defaults 在当前 lexical parent 中求值；
2. 收集参数名；
3. 单独预扫描当前 lambda body，得到它自己的 walrus / local binding 集合；
4. 以 `parameters ∪ body locals` 建立新的 `_ScopeIR(kind="lambda")`；
5. 在该 scope 中按表达式顺序分析 callsite 与赋值。

因此：

```python
probe = lambda: (app.get('/false'), (app := object()))
```

中的第一个 `app` 会先命中 lambda 的 compile-time local marker，解析为 unknown，而不会回退借用 module FastAPI provenance。

## 3. declaration boundary 没有被穿透

同一个 collector 对 nested declarations 保持 Round 8 边界：

- nested lambda：只遍历其 defaults，不进入 nested body；当正式 visitor 进入 nested lambda 时，再为它单独预建 body locals；
- nested function / class：只遍历在包围 scope 求值的 decorator、defaults、annotations、bases、keywords，不进入 body；
- comprehension：iteration target 留在 comprehension scope，walrus target 写入最近的非-comprehension scope；
- lambda parameters 始终为 lambda local unknown，不会借用同名外层 framework；
- lambda defaults 先在父 scope 分析，不会错误写入尚未建立的 lambda scope。

正例回归锁定：

- 无同名 local 的 readonly lambda 可以确认外层 FastAPI route；
- nested readonly lambda 也可以确认；
- lambda default 在父 scope 绑定别名时，不污染 lambda local 集合；
- lambda / nested function body 的同名 walrus 不污染 module，后续 module route 继续 confirmed。

## 4. 统一 expression-container 矩阵

测试以数据矩阵生成 lambda bodies，而不是为每种 AST 节点增加产品分支。`_PythonLocalCollector` 通过 `ast.NodeVisitor` 的统一结构遍历覆盖：

- `BoolOp`、`BinOp`、`UnaryOp`、`IfExp`；
- `Dict`、`Set`、`List`、`Tuple`；
- `Call` positional args 与 keywords；
- `Attribute`、`Subscript`、`Slice`、`Starred`；
- `ListComp`、`SetComp`、`DictComp`、`GeneratorExp`；
- `Yield`、`YieldFrom`；
- `JoinedStr`、`FormattedValue`；
- direct `NamedExpr`、nested call、nested lambda default 与 conditional expression。

每一项都把 `app.get('/false')` 放在同一 lambda 中的 walrus 前面，验证 compile-time shadow 而非仅验证执行后 kill。

Python 不支持 async lambda；`await` 放在 lambda body 时，`ast.parse()` 可能生成 AST，但 `compile(..., mode="exec")` 会拒绝。`_python_boundaries()` 现在在 provenance discovery 前执行该语义校验（`:710-717`）。不合法或当前解释器不能可靠支持的 Python 文件直接不产生 confirmed boundary；测试同时覆盖含 walrus和不含 walrus的 invalid-await lambda，防止仅靠 local shadow 偶然通过。

## 5. Round 8 的 32 项矩阵重放

同一个公共回归还程序化生成并锁定：

| 结构 | 数量 | 结果 |
| --- | ---: | --- |
| Assign / AnnAssign / AugAssign / NamedExpr × list / set / dict / generator | 16 | 全部 0 feature / evidence / HTML |
| 四种 assignment 外包 nested call | 4 | 全部为 0 |
| nested function defaults × 四种 comprehension | 4 | 全部为 0 |
| decorators × 四种 comprehension | 4 | 全部为 0 |
| class bases × 四种 comprehension | 4 | 全部为 0 |
| **总计** | **32** | **32 / 32 全零** |

`validate_index()` 对最终合并结果 valid；既有 JS / TS typed、for、do、switch 和 malformed 源码仍无泄漏。

## 6. 六仓与 Waku

最终候选树通过真实六仓 Golden 与逐仓 validator：

| 合同 | 结果 |
| --- | ---: |
| 固定 Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationships | 18 |
| known technology claims | 59 |
| 六仓 validate | 6 / 6 valid |

Waku cold index 同时通过；memory / graph / loop / gateway 继续作为独立 compatibility candidate，不进入六仓 curated 排名。

## 7. 验证证据

- 精确红转绿：lambda / Round8 合并公共链路与 Python scope 正例 2 / 2 通过。
- `tests.test_features`：17 / 17 通过，耗时 0.746 秒。
- Teaching + 六仓 + Waku + validator：53 / 53 通过，耗时 78.873 秒。
- 六仓合同保持 6 / 6、19 / 66 / 18 / 59；Waku cold index 通过。
- 真实 Google Chrome：`tests.test_report_mobile_browser` 1 / 1 通过，耗时 4.116 秒；覆盖 1440×900 与 390×844、details / source-link 物理点击及横向溢出合同。
- `ruff check src tests`：`All checks passed!`。
- `PYTHONPATH=src .venv/bin/python -m compileall -q src tests`：exit 0。

## 8. 修改文件

- `src/repo_teacher/features.py`
- `tests/test_features.py`
- `docs/audits/teaching-fix-round9.md`

未修改 core / indexer / validator / CLI / persistence、Skill、capability catalog、Golden fixture、正式 examples、HTML/CSS 或参考 clone。

## 9. 简化与剩余边界

本轮没有新增依赖或第二套 analyzer。lambda body 与 statement body 共享一个 `_PythonLocalCollector`，容器覆盖由通用 AST traversal 获得；产品代码没有针对 26 个表达式形态逐项分支。

仍需独立 reviewer 对抗验证：nested lambda 的 defaults/body 分界、多级 nested lambda、generator lambda、f-string formatted value、compile 接受但运行语义仍不确定的新 Python AST 节点，以及 future Python 版本的语法兼容边界。动态 monkey patch、runtime decorator 改写和不能证明的 binding 继续 fail closed，不应为了召回率绕过 compile-time local 或 framework provenance identity。

