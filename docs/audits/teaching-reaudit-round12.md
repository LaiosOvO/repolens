# Teaching / Feature / Tutorial / CodeMap Round 12 独立复审

**结论：REQUEST CHANGES / BLOCK**  
**Architecture status：BLOCK**

日期：2026-08-10  
复审性质：未参与 Round 11 修复的只读复审。除本报告外，没有修改产品源码、测试、examples 或参考仓库。

## 一句话结论

Round 11 已正确关闭原报告中的 scope identity 复用、deferred outer-write、`@` / 未闭合结构、Python 同行与多行 factory、最近未来 symbol、module callsite fallback 和 ESM `export function` 样例；60 项专项、六仓 cold Golden、Waku cold corpus、Chrome 双视口、Ruff 与 compileall 也通过。

但“confirmed 必须 fail closed”仍有两条可稳定复现的绕过：

1. lexer 只拒绝未知字符，不验证由已支持 token 组成的 JavaScript 是否符合语法。`node --check` 明确拒绝的 `const app;`、`throw;`、`#;` 文件仍生成 confirmed HTTP feature、三段 framework evidence、valid validator 与 HTML 内容；
2. 同一物理行中的 deferred route 在 `.` 和方法名之间插入合法 block comment 后，会被 JS token analyzer 看见、却绕过 evidence 排他正则。伪 route 不成为 feature，但进入 entry / factory / call evidence 和 HTML。

此外，当前正式六仓和 Waku 的 11 个 persisted `index.json` 全部与当前分析指纹不一致，不能作为最终可验证交付物。因此本轮不能给 PASS。

## P0 — 只做 token 白名单不能证明 JavaScript 语法有效

最小 CommonJS 反例：

```javascript
const express = require('express');
const app;
app = express();
app.get('/round12-malformed-const-false', handler);
```

公开链路结果：

```text
node --check          exit 1 / SyntaxError: Missing initializer in const declaration
feature               1 × GET /round12-malformed-const-false
confidence            static-entry
framework evidence    3（import / factory / call）
validator             valid=True, issues=0
standalone HTML       命中伪入口字符串
```

两个相邻但有界的反方变体同样成立：

```javascript
throw;
const app = express();
app.get('/malformed-throw-false', handler);
```

```javascript
#;
const app = express();
app.get('/malformed-hash-false', handler);
```

二者均为 `node --check = 1`，但均得到 1 confirmed feature、3 条 framework evidence、valid validator 与 HTML 命中。这里没有扩展 fuzz；三个样例分别覆盖非法 declaration、非法 statement 和上下文非法 punctuation。

根因：

- `src/repo_teacher/features.py:844-966` 只保证 token 可词法化；`#` 还在显式 punctuation 白名单中；
- `src/repo_teacher/features.py:1527-1538` 把没有 initializer 的 `const` 当作普通 unknown declaration，随后 `:1515-1524` 接受后续赋值；
- `src/repo_teacher/features.py:1908-1975` 对无法识别的 statement 以分号为界继续分析，`throw;`、`#;` 不会使整文件失效；
- `src/repo_teacher/features.py:2001-2006` 只捕获 lexer / delimiter 的 `ValueError`，没有任何语法有效性证明；
- validator 的 canonical rebuild 使用同一个 analyzer，因此相同错误可以在重建时自洽，不能独立拒绝伪确认。

Round 11 的 `@` 未知 token 与未闭合 delimiter 已正确归零，但这不能支持“malformed JS 整文件 fail closed”的更强合同。最低修复应在进入 confirmed boundary 前使用可审计的 JS/TS parse-validity 门，或把当前 analyzer 可证明的语法子集定义成严格 grammar 并拒绝任何不完整 declaration / statement；不能继续依靠增加字符白名单。

## P1 — block comment 绕过同行 evidence 排他门

合法 JavaScript：

```javascript
import express from 'express';
const app = express(); app.get('/round12-comment-live', handler); const probe = () => app. /*gap*/ get('/round12-comment-false', handler);
```

真实语法门为 `node --check = 0`。公开链路结果：

```text
confirmed feature                  1 × GET /round12-comment-live
GET /round12-comment-false feature 0
validator                          valid=True, issues=0
伪字符串进入 entry evidence        1
伪字符串进入 framework evidence    factory + call
standalone HTML                     命中 /round12-comment-false
```

真实 Chromium 对生成报告的检查：collapsed details 时伪字符串不在 `innerText`，但存在于 DOM `textContent`；展开全部 details 后进入可见 `innerText`。这不是仅存在于嵌入 JSON 的无害字符串，而是用户可打开的证据内容。

根因：

- `src/repo_teacher/features.py:864-869` 的 JS lexer 会正确丢弃 block comment，因此 deferred analyzer 看到等价的 `app.get(...)` token 序列并按设计不把它提升为 feature；
- `src/repo_teacher/features.py:94-98` 的 `_BOUNDARY_CALL` 只接受 `.` 后直接空白再接方法名，无法跨 `/*...*/`；
- `src/repo_teacher/features.py:101-131` 完全依赖该正则判定一行是否只含当前 boundary，于是只观察到 live route；
- `src/repo_teacher/features.py:2285-2293` 和 `:2346-2369` 最终仍把整个物理行保存成 entry、factory 与 call evidence。

最低修复不应继续补正则。排他检查必须复用与边界分析相同的 token / AST callsite 表示，或先引入统一 column / byte range 证据合同；只要证据仍按整行持久化，就必须能结构化识别该行所有 sibling framework calls 后再决定 fail closed。

## P0 — 正式 persisted 交付物全部已过期

当前源码对每个 persisted index 的期望分析指纹为 `a3872f89997d547e…`，但：

- 六仓正式输出仍为 `c946d4799102bdcc…`；
- Waku index / memory / graph / loop / gateway 仍为 `3684c28ae32c5b9e…`。

逐个 `validate_index(persisted, source)`：

| persisted 输出 | valid | 主要错误 |
| --- | ---: | --- |
| SourceBridge | false | analysis-fingerprint-mismatch，另有 tree / semantic / derived drift；工作树 dirty warning 与用户已知 `LICENSE` 删除一致 |
| PocketFlow code2tutorial | false | analysis-fingerprint-mismatch + semantic / derived / canonical mismatch |
| OpenWiki | false | analysis-fingerprint-mismatch + semantic / derived / canonical mismatch |
| Understand Anything | false | analysis-fingerprint-mismatch + semantic / derived / canonical mismatch |
| CodeBoarding | false | analysis-fingerprint-mismatch + semantic / derived / canonical mismatch |
| DeepWiki Open | false | analysis-fingerprint-mismatch + semantic / derived / canonical mismatch |
| Waku index / memory / graph / loop / gateway | 全部 false | 每项均至少 analysis-fingerprint-mismatch |

这与 cold-build 能力是否正确是两件事：当前实现可以重新构建并通过，但磁盘上供最终 HTML 链接的正式证据包仍不是当前实现的产物。必须在本轮源码阻断修复完成并冻结分析指纹后，重新生成六仓与 Waku，逐项持久化验证，再更新最终 HTML。

## 已闭合的 Round 11 指定反例

所有条目都通过独立临时仓的公开 `build_index()` → `validate_index()` → `render_report()` 链路重放。

| 合同 | 结果 |
| --- | --- |
| 未调用 JS function 写外层 + 后续函数 scope identity reuse | 0 feature / 0 framework evidence / HTML 0；validator valid |
| 未调用 JS arrow 写外层 + 后续调用 | 0 / 0 / 0；validator valid |
| 未知 `@` token | `node --check=1`，0 / 0 / 0；validator valid |
| 未闭合 JS function body | `node --check=1`，0 / 0 / 0；validator valid |
| Python 同行 live + deferred lambda | 为避免行级混证，live 也 fail closed；伪字符串 evidence / HTML 0 |
| Python 多行 `FastAPI(...)` callback | live feature 1；callback 伪字符串 evidence / HTML 0；validator valid |
| JS live 后邻近未来 arrow symbol | live feature 1；伪 feature / evidence / HTML 0；validator valid |
| Python terminal module direct | feature 1、3 段 provenance、validator valid |
| JS terminal module direct | feature 1、3 段 provenance、validator valid |
| CommonJS 多行 ordinary function | feature 1、3 段 provenance、validator valid |
| ESM `export function` | feature 1、3 段 provenance、validator valid |
| ESM `export default async function` 有界正例 | feature 1、3 段 provenance、validator valid |

源码层面，`_ScopeIR.scope_token` 的单调 token 在 `src/repo_teacher/features.py:180-199`，deferred write barrier 在 `:1281-1298`，普通 function / arrow 创建 barrier 在 `:1446-1469` 与 `:1609-1638`；这些修复方向和上述重放一致。`_symbol_for_line()` 在 `:2009-2011` 也已只接受 containing symbol；module callsite fallback 与 validator 在 `src/repo_teacher/features.py:2294-2316`、`src/repo_teacher/validation.py:450-474` 闭合。ESM export dispatch 在 `src/repo_teacher/features.py:1934-1949` 保留了明确正例。

## 六仓 cold Golden 与 Waku cold corpus

专项测试重新从六个固定 HEAD 构建，不读取正式 persisted JSON，并逐仓执行 validator：

| 合同 | 结果 |
| --- | ---: |
| 固定 Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationships | 18 |
| known technology claims | 59 |
| cold validator | 6 / 6 valid |

Waku cold build 继续得到 memory / graph / loop / gateway 四项：全部 `entrypoint-candidate` + `confidence=candidate` + `compatibility-corpus:waku-not-curated`，没有 `capability-cluster`，validator valid。该结果证明当前 cold analyzer 的 Golden 主链未因 Round 11 改动回归，但不抵消上面的 confirmed-JS 反例与 persisted 过期问题。

## 验证命令与结果

专项门：

```bash
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round12-focused-pyc \
PYTHONPATH=src .venv/bin/python -m unittest -v \
  tests.test_features tests.test_artifacts tests.test_report \
  tests.test_reference_ground_truth tests.test_validation
```

```text
Ran 60 tests in 80.130s
OK
```

真实 Chrome 报告门：

```bash
PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round12-browser-pyc \
PYTHONPATH=src python3 -m unittest -v tests.test_report_mobile_browser
```

```text
Ran 1 test in 3.083s
OK
```

另外使用真实 `/Applications/Google Chrome.app` 打开本报告反例生成的 standalone HTML：1440 视口 `scrollWidth=clientWidth=1440`，390 视口 `scrollWidth=clientWidth=390`；malformed confirmed route 两个视口均可见，comment-gap 伪字符串在展开 details 后可见。

```bash
uv run --offline ruff check src tests
# All checks passed!

PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round12-compile-pyc \
PYTHONPATH=src .venv/bin/python -m compileall -q src tests
# exit 0
```

## 解除阻断的最低条件

1. confirmed JS/TS boundary 必须拥有语法有效性证明；至少把本文 `const` 无 initializer、`throw;`、上下文非法 `#;` 三个固定反例加入公开链路回归，并确保 feature / framework evidence / HTML 均为 0。
2. evidence 排他门必须与 JS tokenizer / parser 共享结构化 callsite，不得继续用独立正则近似；本文 comment-gap 伪字符串必须在全部 evidence 与 HTML 中字面为 0。
3. 修复后重跑 Round 11 全部指定反例与本文两个最小反例、60 项专项、六仓 6/6 与 19/66/18/59、Waku candidate、真实 Chrome 双视口、Ruff 与 compileall。
4. 分析指纹冻结后重新生成正式六仓与 Waku 全部 JSON / HTML，并逐项 persisted validation；在此之前最终单一 HTML 不得标记生产验收 PASS。

在 malformed supported-token JS 能得到 confirmed feature、同行 comment-gap 伪入口能进入证据，以及正式 persisted 产物尚未重新闭合前，最终结论保持 **REQUEST CHANGES / BLOCK**。
