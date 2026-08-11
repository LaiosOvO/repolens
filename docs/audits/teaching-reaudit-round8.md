# Teaching / Feature / Tutorial / CodeMap Round 8 独立复审

**结论：REQUEST CHANGES / BLOCK**  
**Architecture status：BLOCK**

日期：2026-08-10  
复审性质：未参与 Round 7 实现的独立只读复审。除本报告外，未修改产品源码、测试、fixture 或 examples。

## 一句话结论

Round 7 列出的 11 个合并伪入口已经是 **0 feature / 0 framework evidence / HTML 0 命中**，missing-source relationship 也已在 tutorial / CodeMap / coverage 一致降级。但 Python 编译期 local collector 只在 comprehension 作为独立表达式语句时能看到 walrus；一旦把同一 comprehension 放到普通赋值 RHS，collector 会在 `Assign` 处停止遍历。这使函数内的前置调用再次借用模块级 FastAPI provenance，生成 `exact-entry` 和完整三段 evidence，通过 validator 并进入 HTML。因此仍不能发布。

## 阻断问题

### P0 — 被赋值 RHS 包裹的 comprehension walrus 未建立函数级 compile-time local

最小反例：

```python
from fastapi import FastAPI
app = FastAPI()
def register():
    app.get('/py-before-assigned-comp-walrus-false')
    items = [(app := object()) for item in clients]
```

这是合法 Python。现场用标准库 `ast.parse()` 和 `symtable` 重放的结果为：

```text
ast_parse=ok
register_app_is_local=True
register_app_is_free=False
register_app_is_global=False
```

因此 line 4 的 `app` 不能回退读取模块级 FastAPI binding；实际执行到该行会遇到未初始化的函数 local。静态分析至少必须降级为 unknown，不得确认 route。

当前正式 `build_index()` / `validate_index()` / `render_report()` 链路的现场结果：

```text
matching feature       GET /py-before-assigned-comp-walrus-false, exact-entry
framework evidence     3
  app.py:1              from fastapi import FastAPI
  app.py:2              app = FastAPI()
  app.py:4              app.get('/py-before-assigned-comp-walrus-false')
validate_index          valid=True, errors=0, warnings=0
HTML target hit         true
```

根因在 `src/repo_teacher/features.py:240-336`：

- `_PythonLocalCollector.visit_Assign()` 仅收集 assignment target（`:245-247`），没有遍历 `node.value`。
- `visit_AnnAssign()` 和 `visit_AugAssign()` 也有同样的 RHS 遍历缺口（`:249-253`）。
- `visit_ListComp()` 本身会遍历 iterable / filters / result（`:307-323`），但它在赋值 RHS 中时根本不会被调用。
- `_visit_function()` 依赖 `_python_local_names(node.body)` 预建 compile-time locals（`:460-478`）；由于漏收集 `app`，前置 callsite 会错误解析到 lexical parent 的 FastAPI binding。
- 后续 `visit_Assign()` 在正式数据流阶段确实会访问 RHS，但这发生在前置伪 route 已经被发现之后，无法修正 compile-time local 语义。

Round 7 的回归只使用裸表达式：

```python
[(app := object()) for item in clients]
```

这会经由默认 `Expr` 遍历进入 `visit_ListComp()`，因而恰好绕开了真实工程中常见的“保留 comprehension 结果”包装。这是原 P0 的同一 Binding/Scope 问题，不是新功能要求。

## Round 7 指定反例重放

### 合并 11 伪入口

独立新建临时仓，通过正式公开链路合并重放：

- Python module comprehension walrus；
- Python function-local comprehension walrus 前置调用（裸表达式版）；
- TS generic typed function parameter；
- TS typed arrow + return type；
- TS generic method + return type；
- bare `for..of` assignment target；
- typed `for..of` declaration target；
- `var` function-scope loop target 与 loop 后调用；
- `do..while` block shadow；
- `switch` block shadow；
- malformed unclosed call。

现场输出：

```text
matching_feature_count  0
framework_evidence_count 0
html_hits               []
validate_index           valid=True, errors=0, warnings=0
```

这证明 Round 7 指名的 11 个样例已修好，但不能抵消上述赋值 RHS 派生反例。

### missing-source relationship 三件套

对 `{"id":"r","source_id":"","target_id":"target","kind":"calls"}` 现场调用 `enrich_index()`：

```text
tutorial confirmed relationship  0
tutorial relationship status     location-only
tutorial relationship id         ""
CodeMap resolved edge ids         []
CodeMap relationship gaps         1
coverage resolved check           false
coverage resolved metric          0
```

对称的 missing-target 输入也得到完全相同的 0 resolved 结果。本项 PASS。

## Round 6 合同回归

53 项专项包含并通过以下合同：

- Python lambda / comprehension target / with / except / del / try / match / short-circuit walrus 的 scope、kill 和 CFG join；
- JavaScript catch / declared for / class method / object method / destructuring / brace-less if / compound initializer / conditional initializer / default 与 concise arrow；
- 正常 FastAPI / Express / Commander 的 import / factory / callsite 三段 framework evidence，包含 snippet hash；
- ordinary `alpha -> beta` 只使用一条 direct relationship，source/target 两个 step 共用同一 relationship id，不 BFS 扩展；
- CodeMap 对同 endpoint 的 `calls` / `contains` 平行关系保留不同 id 和 kind；
- 六仓 typed relationship 通过精确 source slice / target slice / callsite range / allowed kind / endpoint symbol 闭包。

这些成功是有效回归证据；本轮的 BLOCK 只来自可重现的新 P0。

## 六仓、独立参考贡献与 Waku

### 真实六仓 Golden

对 `/Volumes/T7/workspace/ontology/graph/repo` 下六个完整 clone 重跑 `test_version_pinned_six_repository_capability_recall`：

| 合同 | 实测结果 |
| --- | ---: |
| 固定 Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationship identities | 18 |
| known technology claims | 59 |
| 逐仓 `validate_index()` | 6 / 6 valid |

Golden 在每个仓库内重新执行 cold `build_index()`，校验固定 commit、源码 blob、capability path、slice hash、typed exact callsite、relationship identity、technology evidence 和派生 CodeMap 闭包。

### 每个项目独立贡献与源码

对 SourceBridge、PocketFlow code2tutorial、OpenWiki、Understand Anything、CodeBoarding 和 DeepWiki Open 分别现场渲染 HTML：

- 每份 HTML 都有 6 张 reference card、1 张当前仓卡、1 个“六仓机制对照”标题；
- 6 个 project / mechanism / mapping / path set 均各自唯一，不是用一个项目的贡献替代其他项目；
- 现场拆解全部卡片得到 18 个引用源文件：**18 / 18 存在，18 / 18 引用行号不超过文件实际行数**。

本项 PASS。

### Waku 仅作兼容性项目

真实 Waku cold index 在 53 项专项中重建并通过 validator。memory / graph / loop / gateway 全部保持：

- `kind=entrypoint-candidate`；
- `confidence=candidate`；
- `source=evidence-bounded-static-feature-discovery`；
- 含 `compatibility-corpus:waku-not-curated`；
- 不生成 `capability-cluster`；
- HTML 有“Waku：单独验证，不进入六仓 curated 技术排名”，不含“六仓机制对照”。

本项 PASS。

## 浏览器验证

本机 Google Chrome 和 system Python Playwright 均可用，现场执行 `tests.test_report_mobile_browser`：

```text
Ran 1 test in 3.200s
OK
```

该测试实际启动 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，在 1440×900 和 390×844 两个 viewport 中物理点击 details，并对 source link 执行真实 click-event，断言 document/body 宽度与 viewport 相等、无 overflow offender。页面通过 `report_path.as_uri()` 以真实 `file://` URL 加载；Chrome launch 未添加 `--allow-file-access-from-files`、禁用 web security 或其他跨 scheme 绕过参数。测试会阻止 source link 的默认外部导航，因而本报告不把“浏览器实际打开源文件”额外声称为 PASS。布局、href 边界和 click-event 合同 PASS。

## 测试与静态检查

| 命令 / 门 | 现场结果 |
| --- | --- |
| `PYTHONPATH=src .venv/bin/python -m unittest -v tests.test_features tests.test_artifacts tests.test_report tests.test_reference_ground_truth tests.test_validation` | **53 / 53 PASS**；`Ran 53 tests in 82.007s`；`OK` |
| 独立合并 11 伪入口正式链路 | 0 feature / 0 framework evidence / HTML 0 命中；validator valid |
| 赋值 RHS comprehension walrus 派生反例 | **1 exact-entry / 3 framework evidence / HTML 命中；validator 错误放行** |
| `PYTHONPATH=src python3 -m unittest -v tests.test_report_mobile_browser` | **1 / 1 PASS**；真实 Chrome；1440 / 390 |
| `ruff check src tests` | `All checks passed!` |
| `PYTHONPATH=src .venv/bin/python -m compileall -q src tests` | exit 0 |

注：一次预检命令尝试 `.venv/bin/ruff`，该路径不存在；随后使用工作区实际 `ruff 0.15.7` 重跑完整 `src tests`，退出码 0。这不是 skip 或忽略失败。

## 解除阻断的最低条件

1. `_PythonLocalCollector` 必须收集 `Assign` / `AnnAssign` / `AugAssign` RHS 中的 walrus target，同时继续保持不穿过嵌套 function / class / lambda 边界的现有合同。
2. 新增至少两个公开链路回归：普通 assignment RHS 和 annotated assignment RHS 包裹 comprehension walrus；两者的函数前置 `app.get(...)` 都必须是 0 feature / 0 framework evidence / HTML 0 命中。
3. 修复后重跑本轮全部 53 项、合并伪入口、六仓 Golden、Waku、Ruff、compileall 和真实 1440 / 390 Chrome，再交由未参与修复的 Agent 独立复审。

在上述 P0 消失前，Repo Teacher 教学 / HTML 交付结论保持 **REQUEST CHANGES / BLOCK**。
