# Teaching / Feature 修复记录（Round 8）

日期：2026-08-10  
范围：Python compile-time local 收集器对 assignment RHS、嵌套表达式与 definition-time 表达式的完整遍历。  
状态：实现和实现者验证完成，teaching 产品源码已冻结，等待新的独立 Agent 复审；本文不自行给出 PASS。

## 一句话结果

Round 8 的派生反例来自 `_PythonLocalCollector` 在 `Assign` / `AnnAssign` / `AugAssign` 节点提前停止，导致位于 RHS 深处的 walrus target 没有进入函数 compile-time local 集合。修复后 collector 按 AST 结构继续遍历赋值值、嵌套表达式和在包围作用域求值的默认参数；同时明确不进入 lambda、nested function 和 class body。合并端到端反例目前对应 **0 feature、0 framework evidence、HTML 0 命中**。

## 1. Test-first 复现

先扩展现有公共链路回归 `test_combined_scope_and_cfg_adversaries_never_become_framework_features`，不直接测试私有 helper。测试经由正式：

`build_index()` → `validate_index()` → `render_report()`

新增矩阵覆盖：

| 语句形态 | RHS / 嵌套形态 | 预期 |
| --- | --- | --- |
| `Assign` | list comprehension walrus | 前置 `app.get` 不确认 |
| `AnnAssign` | generator expression walrus | 前置 `app.get` 不确认 |
| `AugAssign` | dict comprehension walrus | 前置 `app.get` 不确认 |
| nested `NamedExpr` | call argument | 前置 `app.get` 不确认 |
| nested function default | set comprehension walrus | 前置 `app.get` 不确认 |
| lambda default | direct walrus | 前置 `app.get` 不确认 |

修复前，扩展后的合并回归失败：至少 assignment RHS 包装的 walrus 仍生成 confirmed route。正例回归同期保持通过，证明失败不是测试夹具或 framework import 本身失效。

## 2. 结构化 collector 修复

`src/repo_teacher/features.py:245-348` 现在遵守两个边界：

1. **当前 lexical scope 求值的表达式必须完整遍历。**
   - `Assign.value`、`AnnAssign.annotation/value`、`AugAssign.value`；
   - `NamedExpr.value`，因此嵌套 walrus 不会在第一层停止；
   - `for.iter`、with context expression、except type、match subject/guard；
   - comprehension 的 iterable、filters、list/set/generator result、dict key/value。
2. **新的执行作用域不可泄漏到包围 scope。**
   - nested function / class 只遍历在包围作用域求值的 decorator、defaults、annotations、bases、keywords，不进入 body；
   - lambda 只遍历 defaults，不进入 body；
   - comprehension iteration target 仍不登记为外层 local，只有其中的 walrus target 按 Python 语义登记。

这不是对 `app`、FastAPI 或测试路径字符串的条件分支，也没有新增第二套 scope analyzer。

## 3. 反例与正例闭包

合并仓库目前包含 Round 7 的 Python / JS / TS 反例及本轮 6 个 Python RHS/definition-time 派生反例。正式链路结果：

| 检查 | 结果 |
| --- | ---: |
| 17 个合并伪入口对应 feature | 0 |
| `technology-claim:framework` evidence | 0 |
| `validate_index()` | valid |
| HTML 中对应伪入口 | 0 |

为防止“遍历更多节点”跨越真正 scope，`test_python_binding_ir_covers_scopes_kills_and_control_flow_joins` 同时锁定：

- lambda body 内 `(app := object())` 不污染 module `app`，后续 FastAPI route 保持 confirmed；
- nested function body 内 assignment/comprehension walrus 不污染 module `app`；
- 普通 comprehension iteration target 不污染 module binding；
- 既有 with / except / del / try / match / short-circuit kill 与 join 语义不回归。

## 4. 六仓与 Waku 回归

最终候选树通过真实六仓 Golden 与逐仓 validator：

| 合同 | 结果 |
| --- | ---: |
| 固定 Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationships | 18 |
| known technology claims | 59 |
| 六仓 validate | 6 / 6 valid |

Waku 真实冷索引也在同一专项运行中通过；memory / graph / loop / gateway 仍是单独 compatibility candidate，不进入六仓 curated 技术排名。

## 5. 验证证据

- 精确红转绿：2 tests，`test_combined_scope_and_cfg_adversaries...` 与 `test_python_binding_ir...` 全部通过。
- `tests.test_features`：17 / 17 通过。
- Teaching + 六仓 + Waku + validator：53 / 53 通过，耗时 80.207 秒。
- 真实 Google Chrome：`tests.test_report_mobile_browser` 1 / 1 通过，耗时 4.523 秒；覆盖 1440×900、390×844、details / source link 物理点击与横向溢出合同。
- `ruff check src tests`：`All checks passed!`。
- `PYTHONPATH=src .venv/bin/python -m compileall -q src tests`：exit 0。

## 6. 修改文件

- `src/repo_teacher/features.py`
- `tests/test_features.py`
- `docs/audits/teaching-fix-round8.md`

未修改 core / indexer / validator / CLI / persistence、Skill、capability catalog、Golden fixture、正式 examples、HTML/CSS 或参考 clone。

## 7. 简化与剩余边界

本轮没有新增依赖或 parser。所有新语义集中在已有 `_PythonLocalCollector`：依赖 `ast.NodeVisitor` 的结构遍历，而不是枚举框架名称、变量名或源码字符串；测试也复用既有公共链路方法，专项总数保持 53。

仍需独立 reviewer 对抗验证：多层 nested walrus、decorator / default / class-base 的 definition-time 求值、lambda / nested function / class body 的不泄漏，以及 future Python AST 节点新增表达式字段时是否仍 fail closed。动态 monkey patch、runtime decorator 改写和无法静态证明的 import alias 继续保守降级，不应为了召回率绕过 compile-time local 或 provenance identity。

