# Teaching / Feature / Tutorial / CodeMap Round 13 独立最终复审

**唯一结论：PASS / CLEAR**

日期：2026-08-10  
复审性质：未参与 Round 12 实现的全新、独立、只读复审。本轮完整阅读 `teaching-reaudit-round12.md` 与 `teaching-fix-round12.md`；除本报告外，未修改产品源码、测试、examples 或任何参考仓。

## 一句话结论

Round 12 的两个实现阻断已闭合：`.js` / `.mjs` / `.cjs` 的 confirmed framework boundary 现在需要通过真实 `node --check`；framework evidence 排他检查已改用 Python AST / JavaScript token callsite，block comment 不再可以绕过。Round 11 的 scope token、deferred write、evidence site、module fallback 和 ESM export 回归也全部保持通过。

没有发现新的 Teaching / Feature / Tutorial / CodeMap 实现阻断。磁盘上现有六仓与 Waku 正式产物仍是旧分析指纹；这是源码冻结后的发布重建门，不归因为本轮实现缺陷。

## 1. Round 12 指定反例重放

所有产品行为样例都走用户可见公开链路：

```text
build_index() → validate_index() → render_report()
```

| 合同 | 独立结果 |
| --- | --- |
| `const app;` 后赋值并声明 route | `node --check = 1`；feature 0；framework evidence 0；HTML 伪字符串 0；validator valid |
| 裸 `throw;` 后声明 route | `node --check = 1`；feature / evidence / HTML 均为 0；validator valid |
| 上下文非法 `#;` 后声明 route | `node --check = 1`；feature / evidence / HTML 均为 0；validator valid |
| Node 不存在 | `.js` confirmed boundary 为 0；validator valid |
| Node 超过 3 秒 | `.js` confirmed boundary 为 0；validator valid |
| `app. /*gap*/ get('/false')` 与 live route 同行 | 伪 feature 0；伪 evidence 0；HTML 伪字符串 0；validator valid |

真实 Node v22.22.0 独立检查三个非法样例均返回 1。对应实现在 `src/repo_teacher/features.py:1963-2004`：只有当保守 analyzer 先找到 boundary 且 Node 语法门通过时才保留 confirmed 结果。

## 2. 限定变体：Node goal 与 comment 位置

本轮没有做开放式语言 fuzz，只覆盖任务指定的有限变体。

### Node parse goal

| 文件 | 语法 goal | 结果 |
| --- | --- | --- |
| `.cjs` + `require('express')` 普通 function | CommonJS | confirmed route 1；3 段 provenance；validator valid |
| `.mjs` + `import express` + `export function` | module | confirmed route 1；3 段 provenance；validator valid |
| `.mjs` + `export default async function` | module | confirmed route 1；3 段 provenance；validator valid |
| `.js` | CommonJS 或 module 任一合法 | 两种正例均可进入已证明的语法边界 |

### Comment 位置

独立重放了 comment 位于以下位置的合法 JavaScript：

- receiver 与 `.` 之间；
- `.` 与 member 之间；
- member 与 `(` 之间；
- `(` 与首个 string 参数之间；
- `.` 与 member 之间使用换行 `//` comment。

五项都能被 token callsite 视为同一调用，不能污染 live route 的行级证据。另外把 comment-separated 伪调用分别放到 import site 与 factory site 行中；两者均保守放弃受混合的 live feature，伪字符串未进入任何 evidence 或 standalone HTML。

结构化排他逻辑在 `src/repo_teacher/features.py:2014-2098`；Python 使用 AST node 行范围，JavaScript / TypeScript 使用与 boundary analyzer 相同的 tokenizer / delimiter pairs。

## 3. Round 11 合同不回归

| 指定合同 | 结果 |
| --- | --- |
| deferred function 写外层 binding + 后续 function scope identity reuse | 伪 feature / framework evidence / HTML 均为 0；validator valid |
| deferred arrow 写外层 binding | 伪 feature / evidence / HTML 均为 0；validator valid |
| Python 同行 live + deferred lambda | 受行级 evidence 限制，live 也保守放弃；伪字符串 0 |
| Python 多行 `FastAPI(...)` callback | live feature 1；callback 伪字符串 evidence / HTML 0 |
| JS live route 后紧邻 future arrow symbol | live feature 1；伪 feature / evidence / HTML 0 |
| Python terminal module direct | feature 1；3 段 provenance；module callsite fallback；validator valid |
| JS terminal module direct | feature 1；3 段 provenance；module callsite fallback；validator valid |
| CommonJS 普通 function | feature 1；3 段 provenance；validator valid |
| ESM `export function` | feature 1；3 段 provenance；validator valid |
| ESM `export default async function` | feature 1；3 段 provenance；validator valid |

持久 scope identity 是 `src/repo_teacher/features.py:141-158` 的单调 token，deferred write barrier 在 `:1243-1260`；`_symbol_for_line()` 只返回真正 containing symbol（`:2101-2103`）。无 symbol 的 module callsite 由 `:2377-2408` 建立精确 fallback，validator 在 `src/repo_teacher/validation.py:450-474` 逐字段闭合。

## 4. 安全检查

| 安全项 | 证据 |
| --- | --- |
| 不经 shell | `subprocess.run()` 接收 argv list，未启用 `shell`；独立捕获的 Node 专属调用全部 `shell=False` |
| 不执行待分析源码 | 参数为 `node --input-type <goal> --check -`；源码只从 stdin 输入 |
| 动态不执行神谕 | 源文件中放入顶层 `writeFileSync(marker)`，完整 build + validate 后 marker 仍不存在，route 仍正常被语法检查 |
| 超时 | 每次 Node 调用 `timeout=3.0`；`TimeoutExpired` 整文件 fail closed |
| Node 失败 | `which` 不存在、启动 `OSError`、超时、所有适用 goal 非零均返回 false |
| 环境预加载 | 子进程 `env={}`，不继承 `NODE_OPTIONS` |
| 输出 | stdout / stderr 丢弃，不会把不受信任源文本作为子进程诊断注入报告 |

安全结论仅覆盖该语法门：它依赖运行环境 PATH 中的本地 Node 可执行文件，因此部署方应保证 Node 二进制本身可信。仓库源文本无法通过 argv 注入更改命令结构。

## 5. 性能边界

本轮只给出可审计边界，不做无界压测：

- 只有保守 analyzer 先产生潜在 boundary 的 `.js` / `.mjs` / `.cjs` 文件会启动 Node；
- `.mjs` / `.cjs` 每文件最多一个 3 秒 goal；`.js` 最多 CommonJS + module 两个 goal，极端子进程情形理论上限接近 6 秒/候选文件；
- 当前是按文件启动 Node，复杂度为 O(J) 次子进程，J 是含潜在 confirmed boundary 的 JavaScript 文件数；
- 这个门选择精度优先和 fail closed。大型仓库若出现 Node 启动成本，后续可在不放宽语义的前提下做批量 parse 或受控并发，不是本轮阻断。

## 6. 六仓 Golden 与 Waku compatibility

63 项 scoped 测试从六个固定 HEAD 重做 cold build，不读取现有正式 persisted JSON：

| 合同 | 结果 |
| --- | ---: |
| 六仓固定 Git identity + cold validator | 6 / 6 valid |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationships | 18 |
| known technology claims | 59 |

Waku cold corpus 仍为独立 compatibility corpus：memory / graph / loop / gateway 四项全部是 `entrypoint-candidate` + `confidence=candidate` + `compatibility-corpus:waku-not-curated`，没有 `capability-cluster`，validator valid。它们不进入六仓 curated 技术排名。

## 7. 自动化与真实 Chrome 证据

```text
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round13-focused-pyc \
PYTHONPATH=src .venv/bin/python -m unittest -v \
  tests.test_features tests.test_artifacts tests.test_report \
  tests.test_reference_ground_truth tests.test_validation

Ran 63 tests in 83.002s
OK
```

```text
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round13-browser-pyc \
PYTHONPATH=src python3 -m unittest -v tests.test_report_mobile_browser

Ran 1 test in 3.283s
OK
```

第二个门未 skip，实际启动 `/Applications/Google Chrome.app` 151.0.7922.77，分别在 1440×900 和 390×844 视口检查：首屏标题可见、details 可展开、source link 可交互、`documentElement` 与 body 无水平溢出、无越界元素。

```text
uv run --offline ruff check src tests
All checks passed!

PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round13-compile-pyc \
PYTHONPATH=src .venv/bin/python -m compileall -q src tests
exit 0
```

## 8. 正式产物指纹：仅作为发布门记录

当前相同 analysis config 对应的期望分析指纹是 `de199e7044518305…`。磁盘上现有正式产物为：

- 六仓 6 个 `projects/*/index.json`：`c946d4799102bdcc…`；
- Waku index / memory / graph / loop / gateway 5 个 `index.json`：`3684c28ae32c5b9e…`。

11 / 11 与当前实现指纹不同。这符合“源码先冻结，再重建正式证据包”的发布顺序，不改变本轮对实现的结论。但在主交付标记为“最终当前产物”前，必须重建这 11 项，逐项 persisted validation，然后再生成单一 HTML。

## 9. 剩余风险与准确语义

1. `node --check` 只证明标准 JavaScript 语法在某个 parse goal 中有效，不证明 package mode、模块解析、运行时可达性或处理函数一定执行。
2. Node 是 `.js` / `.mjs` / `.cjs` confirmed framework boundary 的生产依赖；缺失时是召回归零，而不是继续猜测。
3. `.ts` / `.tsx` 不使用 Node 语法门，仍是有界的保守 tokenizer / binding analyzer；不得宣称为完整 TypeScript grammar 证明。
4. evidence schema 仍是行范围，不是 column / byte range。一行或一个 evidence site 中混有其他 framework-shaped call 时，合法 live feature 会一起被保守放弃；这是精度优先取舍，不是 false confirmation。
5. 语法门按候选文件启动 Node，超大 JavaScript 仓库的发布性能应根据候选文件数单独评估。

上述风险均已被当前保守表述包含，不构成新的确认面缺陷。Round 13 对 Teaching / Feature / Tutorial / CodeMap 候选的最终结论维持 **PASS / CLEAR**。
