# Teaching / Feature 修复记录（Round 10）

日期：2026-08-10  
范围：framework boundary 的保守确认合同、deferred scope 抑制、精确 evidence、dangling endpoint 一致降级。  
状态：实现与实现者验证完成；本文不自行给出 PASS，等待未参与实现的 Agent 独立复审。

## 一句话结果

本轮不再尝试模拟完整 Python / JavaScript 动态语义。`confirmed framework boundary` 现在只允许两种可证明形态：

1. module scope 创建的 framework instance，由 module scope 的直接语句调用；
2. 顶层普通函数在自己的 scope 内确定创建 framework instance，随后由同一函数 body 的直接语句调用。

lambda、arrow、nested function、class / method、comprehension、generator、control-flow 内调用以及 returned / stored callback 均不再提升为 confirmed。receiver 的 framework provenance 还必须由当前确认 scope 自己创建；从父 scope 捕获、条件 join 引入或跨 scope alias 的 binding 都 fail closed。

## 1. Test-first：先锁住公开链路反例

测试只使用用户可见 seam：

`build_index()` → `validate_index()` → `render_report()`

修复前，以下新增断言稳定失败：

- Python lambda / stored lambda、nested returned callback、generator body 被错误提升；
- JavaScript arrow / stored arrow、nested returned callback、generator body 被错误提升；
- Python class comprehension 10 项矩阵产生伪 framework feature；
- Python / JavaScript 条件分支内调用和 conditional join 后调用被错误保留；
- 非空 ghost source / target 在 tutorial、CodeMap、coverage 中出现不同结论；
- 合法入口旁边的被抑制伪入口字符串通过宽 evidence 进入 HTML。

修复后，module-level 与 same ordinary function 的 Python / ESM / CommonJS 正例继续 confirmed；所有上述反例均为 0 feature、0 framework evidence、HTML 0 命中。

## 2. 保守 scope ownership 与 direct-statement 合同

`src/repo_teacher/features.py` 的语言共用 IR 增加两项不可伪造的局部事实：

- `_FrameworkBinding.owner_scope_id`：记录 framework factory 真正创建 instance 的 lexical scope；
- `_ScopeIR.boundary_scope`：仅 module 或 module 直接声明的非 generator 普通函数可成为确认 scope。

确认调用同时要求：

- 当前 scope 是允许确认的 scope；
- receiver 的 `owner_scope_id` 与当前 scope identity 相同；
- 调用是当前 body 的直接 statement（Python 直接 expression / 直接函数 decorator；JS/TS 完整直接 call expression）；
- receiver 没有被 kill、rebind 或由 conditional join 新引入。

`_joined_values()` 现在只能保留所有路径都与 branch 前 base identity 相同的既有 proof。即便两个分支看起来都赋值同一种 factory，也不会把两个不同运行时对象合并成一个 proven identity。

## 3. Python 的允许与禁止边界

Python AST 先为每个允许 body 收集“立即执行的直接调用”节点，再进入原有 binding/dataflow visitor：

- module body：允许直接调用与直接函数声明上的 route / command decorator；
- module 直接声明的普通 `def`：允许函数内先创建、后直接调用；
- `async def`、含 `yield` / `yield from` 的 generator、nested function、lambda、class body / method、comprehension own scope：不成为确认 scope；
- `if`、`try`、loop、with、match、default、nested expression 内的调用不属于 direct statement。

class comprehension 本轮采用产品合同层面的保守策略：无论 Python 对最外 iterable 的细分求值规则如何，class / comprehension 都不提升 framework boundary。这比继续扩展 class-namespace 模拟更容易审计，也符合“不可证明即 unknown”。

## 4. JavaScript / TypeScript 的允许与禁止边界

JS/TS lexer/IR 不再在任意表达式中扫描并提升 framework-shaped call。只有 `_analyze_range(..., allow_boundary_statements=True)` 下的完整直接 call expression可以确认：

- module body允许；
- module 直接声明、非 generator 的普通 `function` body允许；
- block、if/for/while/do/switch/try/catch、class/object method、nested function、arrow、generator、initializer、logical / conditional / assignment expression均不允许提升；
- 调用必须覆盖完整 expression，不能把 callback、参数、RHS 或链式子表达式中的内层 call 当作直接边界。

ESM 与 CommonJS 的 Express / Fastify / Koa Router / Commander 解析仍沿用原 import/factory provenance；只是 instance identity 必须属于当前确认 scope。

## 5. Framework evidence 精确到单行调用

对拥有完整 framework provenance 的 feature：

- entry evidence 从旧 `line .. line+5` 收窄为精确调用行；
- import、factory、call 三段 technology evidence 各自保持 source hash；
- symbol / relationship 阅读步骤仍保留，但 symbol definition evidence 只取定义首行，不再吞入后续 deferred callback；
- summary 改为“满足保守同作用域合同的静态框架调用声明；实际可达性未知”。

因此混合正负例中，合法 route / command 继续存在，而 `/python-lambda-late-false`、`/js-arrow-late-false`、returned/stored callback 与 generator 伪字符串均不出现在 feature evidence 或最终 HTML。

对应 core validator 合同由独立 owner 同步：只有 import / factory / call 三段 distinct、同 path / confidence / base analyzer、call hash 与 exact entry line 闭合时，才接受 framework 单行 entry 与保守 summary。普通 static feature 仍走 legacy evidence range；缺 stage、hash 错误或夸大 runtime 的变形继续被拒绝。

## 6. Tutorial / CodeMap / coverage 共用 endpoint closure

`src/repo_teacher/artifacts.py::_valid_relationship()` 不再只检查 endpoint 字符串非空，而是同时要求 source / target 都属于当前 `symbols_by_id`。

空 source、非空 ghost source、非空 ghost target 三种输入现在一致得到：

- tutorial `confirmed_relationship_count = 0`；
- slice `relationship_status = location-only` 且清空 relationship id；
- 明确 gap：关系不存在、端点为空或端点符号未收录；
- CodeMap `resolved_edge_ids = []` 且恰有 1 个 gap；
- coverage `resolved_relationships = false / 0`。

## 7. 六仓与 Waku 回归

最终 55 项门包含真实六仓 cold Golden、逐仓 validator 与 Waku compatibility corpus，全部通过。由固定断言证明：

| 合同 | 结果 |
| --- | ---: |
| 固定 Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationships | 18 |
| known technology claims | 59 |
| 六仓 validate | 6 / 6 valid |

六仓仍分别保留 SourceBridge、PocketFlow code2tutorial、OpenWiki、Understand Anything、CodeBoarding、DeepWiki Open 的独立机制、源码路径、映射能力和未采用边界。Waku 的 memory / graph / loop / gateway 继续是独立 `entrypoint-candidate` compatibility corpus，不进入 curated 技术排名。

## 8. 最终验证证据

- 新增 Round 10 精确反例与原 teaching/artifact scoped：26 / 26 PASS（parent 独立重放）。
- `PYTHONPATH=src .venv/bin/python -m unittest -q tests.test_features tests.test_artifacts tests.test_report tests.test_reference_ground_truth tests.test_validation`：55 / 55 PASS，`Ran 55 tests in 96.885s`。
- 六仓固定合同：6 / 6、19 / 66 / 18 / 59；逐仓 validator 与 Waku cold corpus均在上述 55 项中通过。
- `PYTHONPATH=src python3 -m unittest -v tests.test_report_mobile_browser`：1 / 1 PASS，真实 Google Chrome，`Ran 1 test in 3.221s`；覆盖 1440×900 与 390×844、details / source-link 物理点击及横向溢出合同。
- `ruff check src tests`：`All checks passed!`。
- `PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round10-final-pyc PYTHONPATH=src .venv/bin/python -m compileall -q src tests`：exit 0。

## 9. 本轮 teaching 修改文件

- `src/repo_teacher/features.py`
- `src/repo_teacher/artifacts.py`
- `tests/test_features.py`
- `tests/test_artifacts.py`
- `docs/audits/teaching-fix-round10.md`

未修改 `capability_catalog.py`、`report.py`、Golden fixture、正式 examples、Skill、CLI / persistence / indexer。validator 与其测试由 core owner 在独立写权限内同步，本文仅记录集成结果。

## 10. 简化与剩余边界

本轮主要是删除 confirmation surface：不新增 parser 依赖，不再为每种动态语言容器补一条正则，也不声称模拟完整 CFG / runtime。代价是召回率有意下降：class、closure、callback、generator、nested control flow 中即使某些调用运行时可达，也会保持 unknown。要提高这些场景召回，必须引入独立的行为 trace、可验证 callsite 或更强的语言级 IR；不得仅放宽 receiver 名称或声明时 binding 推断。

仍需独立 reviewer 重点对抗：scope-owner identity 是否可被 alias / join 绕过、direct-expression 判断是否误吞 nested call、framework 三段 evidence 与 entry hash 是否可变形、ghost endpoint 的三件套一致性，以及混合合法 / 被抑制伪入口在 JSON 与 HTML 中是否均为精确切片。
