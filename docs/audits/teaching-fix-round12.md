# Teaching / Feature 修复记录（Round 12）

日期：2026-08-10  
范围：Round 12 独立复审指出的 JavaScript 真实语法门与 framework evidence 排他门。  
状态：实现者修复与回归已完成；本文不自行给出 PASS，等待未参与本轮实现的 Agent 独立复审。

## 一句话结果

本轮只关闭两类已知确认面，没有扩展语言解释范围：`.js`、`.mjs`、`.cjs` 只有同时通过现有保守 analyzer 与本地 `node --check` 才能生成 confirmed framework boundary；证据排他检查改为 Python AST / JavaScript token 结构化 callsite 扫描，不再依赖 boundary 正则。Node 不存在、超时或语法检查失败时，JavaScript 文件的 framework boundary 整体 fail closed。

## 1. TDD 公开 seam

新增回归均通过用户可见链路验证：

`build_index()` → `validate_index()` → `render_report()`

红测先稳定复现：

- `const app; app = express()`、裸 `throw;`、上下文非法 `#;` 都只由现有已支持 token 组成，但不是真实合法 JavaScript；
- Node 不存在或语法检查超时时，不能继续生成 confirmed JavaScript boundary；
- `app. /*gap*/ get('/false')` 会被 tokenizer 识别，却能绕过原正则并污染同行 entry / factory / call evidence 与 HTML。

对应回归：

- `test_node_syntax_gate_rejects_supported_token_but_malformed_javascript`
- `test_node_syntax_gate_fails_closed_when_node_is_unavailable_or_times_out`
- `test_structured_js_evidence_exclusivity_sees_comment_separated_call`

## 2. `.js` / `.mjs` / `.cjs` 真实语法门

`_node_check_javascript()` 使用通过 `shutil.which()` 解析出的本地 Node 绝对路径，受控调用：

```text
node --input-type <commonjs|module> --check -
```

源码只通过标准输入交给语法检查器，`--check` 不执行源码；子进程禁用继承环境以避免 `NODE_OPTIONS` preload，丢弃 stdout / stderr，并设置 3 秒超时。

扩展名策略保持有界：

| 扩展名 | 语法 goal |
| --- | --- |
| `.mjs` | module |
| `.cjs` | commonjs |
| `.js` | commonjs 或 module 至少一个合法 |

若 analyzer 没有发现 boundary，不启动 Node。若发现潜在 boundary，则 Node 缺失、启动失败、超时或所有适用 goal 都返回非零时，整文件不产生 framework boundary。三个 Round 12 非法文件现在在 feature、framework evidence、standalone HTML 中均为字面 0，validator 仍为 valid。

`.ts` / `.tsx` 不发送给 Node：Node 的 `--check` 不是 TypeScript parser。本轮按任务边界保留现有保守 tokenizer / delimiter / binding analyzer；遇到 analyzer 不支持或无法证明的 token / 结构仍整文件不确认。它不等价于完整 TypeScript grammar validation，也不应被报告为该能力。

## 3. 结构化 evidence 排他门

已删除 `_BOUNDARY_CALL` 正则路径。排他检查现在使用与语言相符的结构：

- Python：`ast.parse()` 后遍历 `ast.Call(Attribute(...))`，按节点的 `lineno` / `end_lineno` 与 import、factory、call 三个证据 site 做重叠判断；
- JavaScript / TypeScript：复用 `_js_tokens()` 与 `_js_pairs()`，comments 在 token 层消失，再识别 `receiver . member ( string ... )` 的闭合调用结构并映射为 boundary entrypoint。

因此 `app. /*gap*/ get('/round12-comment-false')` 与普通 `app.get(...)` 得到相同的结构化 callsite。只要行级证据 site 中观察到与当前 boundary 不同的 sibling framework call，当前 feature 整体不提升为 confirmed，伪字符串不会进入 evidence 或 HTML。

Round 11 的 Python 同行 lambda、多行 factory callback、邻近 JS arrow 和 module direct callsite fallback 回归继续通过；没有恢复“绑定最近未来 symbol”的路径。

## 4. 六仓 Golden 与 Waku

完整专项从六个固定 HEAD 做 cold build，不读取正式 persisted JSON，并逐仓执行 validator：

| 合同 | 结果 |
| --- | ---: |
| 固定 Git identity / validator | 6 / 6 valid |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationships | 18 |
| known technology claims | 59 |

Waku cold corpus 的 memory / graph / loop / gateway 四项继续为 `entrypoint-candidate` + `confidence=candidate`，没有 `capability-cluster`，validator valid，仍不进入六仓 curated 技术排名。

## 5. 验证证据

```text
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round12-fix-focused-pyc \
PYTHONPATH=src .venv/bin/python -m unittest -v \
  tests.test_features tests.test_artifacts tests.test_report \
  tests.test_reference_ground_truth tests.test_validation

Ran 63 tests in 79.040s
OK
```

63 项包含 Round 11 全部门、Round 12 三个新回归、六仓真实 cold Golden 与 Waku compatibility cold build。

```text
uv run --offline ruff check \
  src/repo_teacher/features.py src/repo_teacher/validation.py \
  tests/test_features.py tests/test_validation.py tests/test_artifacts.py

All checks passed!
```

```text
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round12-fix-compile-pyc \
PYTHONPATH=src .venv/bin/python -m compileall -q \
  src/repo_teacher/features.py src/repo_teacher/validation.py \
  tests/test_features.py tests/test_validation.py tests/test_artifacts.py

exit 0
```

系统 Python 环境还执行了真实浏览器门：

```text
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round12-fix-browser-pyc \
PYTHONPATH=src python3 -m unittest -v tests.test_report_mobile_browser

Ran 1 test in 6.087s
OK
```

该门使用本地 Chrome 检查桌面与 390px 视口。项目 `.venv` 没有 Playwright，因此同一测试在 `.venv` 中会按测试合同 skip；上述系统 Python 运行实际完成浏览器断言。

## 6. 修改文件

- `src/repo_teacher/features.py`
- `tests/test_features.py`
- `docs/audits/teaching-fix-round12.md`

本轮没有修改 `validation.py`、`artifacts.py`、`report.py`、正式 examples、主 HTML、Golden fixture 或任何参考仓。

## 7. 简化与剩余风险

1. Node 现在是 `.js` / `.mjs` / `.cjs` confirmed framework boundary 的生产语法证明依赖。缺少 Node 时召回归零而不是猜测确认；这符合 fail-closed，但部署清单应显式声明该运行时要求。
2. `.js` 在 commonjs 或 module 任一标准 parse goal 合法即可通过语法门。这证明标准 JavaScript 语法有效，不证明目标仓库的 `package.json` 运行模式、模块解析或运行可达性。
3. `.ts` / `.tsx` 仍是有界的保守词法 / binding 分析，不具备完整 grammar 证明；无法证明时必须维持 candidate / 不确认，不能扩大技术表述。
4. Evidence schema 仍只有行范围，没有 column / byte range。同一证据行混合 live 与不同 sibling boundary 时会整体放弃合法 feature，这是有意的精度优先取舍。
5. 正式 persisted 六仓与 Waku 产物需要等源码与分析指纹冻结后由主交付流程统一重建、逐项验证；本轮按职责没有修改这些产物。
6. 本文是实现记录，不替代全新 Agent 的 Round 13 adversarial re-audit。
