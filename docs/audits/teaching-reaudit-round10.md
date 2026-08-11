# Teaching / Feature / Tutorial / CodeMap Round 10 独立复审

**结论：REQUEST CHANGES / BLOCK**  
**Architecture status：BLOCK**

日期：2026-08-10  
复审性质：未参与 Round 9 实现的独立只读复审。除本报告外，未修改产品源码、测试、fixture、examples 或参考仓库。

## 一句话结论

Round 9 指定的 lambda compile-time local 问题已经修复：direct、表达式容器、四种 comprehension / generator、yield、f-string、nested lambda/default，以及 invalid `await` lambda 均按预期 fail closed；合并 **78 个伪入口**现场得到 0 feature、0 framework evidence、HTML 0 命中，readonly outer binding 正例也保留。53 项专项、六仓 Golden、Waku、真实 Chrome、Ruff 和 compileall 全部通过。

但是 Round 6—9 的共享 Scope / Binding 合同仍有两个可稳定复现的 P0：

1. class body 中的 comprehension 错误闭包 class namespace，把运行时必然 `NameError` 的普通 free-name lookup 拼接成 class 内 FastAPI provenance；
2. Python lambda / nested function 和 JavaScript closure 在声明点立即分析 deferred body，父 binding 随后被普通对象重绑时，已经追加的 framework boundary 不会撤回。

两类反例都会生成 feature、完整三段 framework evidence，通过 validator 并进入最终 HTML。因此当前 HTML 仍不能作为完成交付。

## P0 — class comprehension 错误继承 class namespace

最小合法 Python：

```python
from fastapi import FastAPI
clients = [1]

class Holder:
    app = FastAPI()
    routes = [app.get('/class-list-result-false') for item in clients]
```

Python 的 class namespace 不是 comprehension 隐式执行 scope 的 lexical closure。最外层 iterable 在 class scope 求值，但 comprehension body、filter 和后续 iterable 中的 free name 不读取 class local。现场用 stub `FastAPI` 执行：

```text
compile                 ok
runtime                 NameError: name 'app' is not defined
```

正式 `build_index()` → `validate_index()` → `render_report()` 却得到：

```text
feature                 1 × GET /class-list-result-false
feature confidence      exact-entry
framework evidence      3
HTML                    hit
validator               valid=True, issues=0
```

根因：

- `src/repo_teacher/features.py:518-528` 在 class body 中建立 class `_ScopeIR`，并把 `app = FastAPI()` 保存为 proven binding；
- `src/repo_teacher/features.py:547-575` 的 comprehension 只把第一个 iterable 放在当前 scope 求值，随后在 `:562` 直接以当前 class scope 作为 comprehension parent；
- `src/repo_teacher/features.py:678-707` 因而沿 `comprehension → class` 错误解析到 FastAPI provenance 并追加 boundary；
- function / lambda 已分别在 `:499-506`、`:535-542` 对 class lexical parent 做跳过，comprehension 没有采用同一边界。

独立派生矩阵逐 case 建临时仓、编译、stub 执行并走正式公开链路。**10 / 10** 均为 runtime `NameError`，但各自产生 1 feature、3 framework evidence、HTML 命中且 validator valid：

| class comprehension 位置 | 结果 |
| --- | --- |
| list result | 错误确认 |
| set result | 错误确认 |
| dict result | 错误确认 |
| consumed generator result | 错误确认 |
| comprehension filter | 错误确认 |
| 第二层 iterable | 错误确认 |
| nested comprehension | 错误确认 |
| lambda inside list comprehension | 错误确认 |
| lambda default 内 list comprehension | 错误确认 |
| decorator expression 内 list comprehension | 错误确认 |

合法边界也已重放：

```python
class Holder:
    app = FastAPI()
    routes = [item for item in app.get('/class-outermost-iter-live')]
```

该 outermost iterable 在 class scope 求值，stub runtime 成功且当前分析确认 1 feature。修复不能粗暴跳过整个 class comprehension；必须只让 body / filters / 后续 iterables 的 lexical lookup 跳过 class，同时保留第一个 iterable 的 class-scope 求值。

## P0 — deferred closure body 冻结声明时 provenance

### Python

```python
from fastapi import FastAPI

def run():
    app = FastAPI()
    probe = lambda: app.get('/lambda-closure-late-rebind-false')
    app = object()
    probe()

run()
```

lambda 中的 `app` 是 free variable，运行时通过 closure cell 读取调用时的值。stub runtime 得到：

```text
AttributeError: 'object' object has no attribute 'get'
```

正式链路却得到：

```text
feature                 1 × GET /lambda-closure-late-rebind-false
confidence              exact-entry
framework evidence      3
HTML                    hit
validator               valid=True, issues=0
```

根因链：

- `_ScopeIR.resolve_binding()` 在 `src/repo_teacher/features.py:145-150` 直接读取 parent 当前值；
- `visit_Lambda()` 在 `:530-545` 于声明位置立即分析 body；
- 后续普通赋值只在 `:456-460` 更新父 scope binding；
- 已由 `visit_Call()` 在 `:678-707` 追加的 boundary 不会因 late rebind 或真实调用位置撤回。

### JavaScript

```javascript
import express from 'express';
let app = express();
const probe = () => app.get('/js-closure-late-rebind-false', handler);
app = {};
probe();
```

Node stub runtime 为 `TypeError: app.get is not a function`。正式链路仍生成 1 个 `static-entry`、3 条 framework evidence、HTML 命中并通过 validator。对应的声明点 body 分析位于 `src/repo_teacher/features.py:1290-1312`（arrow）与 `:1448-1470`（function）。

这不是“实际可达性未知”可以覆盖的动态风险：framework claim 明确声称 import、factory 与 callsite 属于同一个 proven receiver identity，而 closure 在真实 call 时读取的已经是另一个 binding value。

## P2 — 非空 ghost endpoint 的 dangling 三件套仍不一致

Round 7 的空 `source_id` / `target_id` 已修好，但 `_valid_relationship()` 在 `src/repo_teacher/artifacts.py:64-73` 只要求两个 endpoint 字符串非空，不校验 endpoint 是否属于 symbols / CodeMap nodes。

对称现场输入：

```text
source_id="ghost", target_id="target"
source_id="source", target_id="ghost"
```

两者都得到：

```text
tutorial confirmed       1
step status              resolved-static
relationship id          r
CodeMap resolved edges   0
CodeMap gaps             0
coverage resolved        true / metric 1
```

CodeMap 在 `src/repo_teacher/artifacts.py:412-418` 发现 endpoint 不在 node set 后跳过 edge，但 `relationship_gaps` 在 `:473-489` 又调用同一个弱 `_valid_relationship()`，所以既没有 resolved edge，也没有 gap。完整 core validator 会拒绝这类 membership 错误，因此本项单独定为 P2；但 `enrich_index()` 的 tutorial / CodeMap / coverage fail-closed 合同仍未闭合。

## P2 / WATCH — 邻近被抑制伪入口仍可能作为宽 evidence snippet 进入 HTML

`_build_feature()` 在 `src/repo_teacher/features.py:2090-2097` 为合法入口固定截取 `line .. line+5`。现场混合：

```python
app.get('/nearby-live')
probe = lambda: (app.get('/nearby-suppressed-false'), (app := object()))
```

结果是合法入口存在、伪入口 feature=0、伪入口 framework evidence=0，但 `entry-declaration` 的 3—4 行宽切片使 `/nearby-suppressed-false` 仍字面进入 HTML。合并 78 全负 fixture 不会暴露这种正负例相邻组合。该项不改变前两个 P0 已经决定的 BLOCK，但最终“伪入口 HTML 0”若按字面合同执行，还需要收窄或结构化 entry evidence。

## Round 9 lambda 修复重放

### 78 个合并伪入口

对 `tests.test_features.FeatureDiscoveryTest.test_combined_scope_and_cfg_adversaries_never_become_framework_features` 做额外捕获，确认生成源码中恰好 **78 个不同伪入口**，不是仅凭测试名推断：

| 组成 | 数量 |
| --- | ---: |
| Round 8 前既有 Python / JS / TS / malformed 反例 | 17 |
| Round 8 assignment / nested call / default / decorator / class-base 矩阵 | 32 |
| lambda body expression-container | 26 |
| nested lambda body | 1 |
| invalid await lambda | 2 |
| **总计** | **78** |

现场结果：

```text
counterexamples          78
matching feature         0
framework evidence       0
HTML hit                 0
invalid await compile    SyntaxError: 'await' outside async function
validator                valid
```

26 项 lambda body matrix 覆盖 direct、BoolOp、BinOp、UnaryOp、IfExp、dict/set/list/tuple、Call args/kwargs、Attribute、Subscript、Slice、Starred、list/set/dict comprehension、generator、Yield、YieldFrom、JoinedStr、FormattedValue、nested call、nested lambda default 与 conditional。

### defaults / body / readonly outer binding

额外公共链路矩阵未复用产品私有 helper：

- 6 / 6 合法正例保留：direct readonly outer、nested readonly、default 在父 scope 的合法 route、nested lambda default 父 scope route、default alias、nested body 不污染 outer；
- 4 / 4 反例归零：outer 在 nested default walrus 前读取同名 local、nested body walrus 前读取、nested default walrus 后 body free lookup、同名 parameter default；
- 3 / 3 补充正例保留：comprehension target 不污染 lambda outer 的前后 readonly route、多级 nested readonly；
- 4 / 4 补充反例归零：filter / dict key / nested comprehension walrus、多级 nested default/body；
- 所有反例同时为 0 feature、HTML 0，validator valid。

因此 Round 9 在 `src/repo_teacher/features.py:364-367` 与 `:530-545` 增加的“每个 lambda 独立预建 body locals，defaults 先在父 scope 求值”本身成立。本轮 BLOCK 来自共享 class / deferred closure 边界，而不是原 lambda-body walrus 修复失效。

## Round 8 / 7 / 6 合同、六仓与 Waku

53 项专项现场完整运行，无 skip：

```text
Ran 53 tests in 77.684s
OK
```

其中确认通过：

- Python 既有 function / lambda / comprehension target / with / except / del / try / match / short-circuit scope 与 CFG；
- JS / TS catch、for、var、do、switch、typed function / arrow / method、malformed syntax；
- parallel `calls` / `contains` relationship 按 identity 保留；
- missing id、空 source 与现场补充的空 target 对称降级；
- 六仓固定 identity、slice / typed callsite / relationship / technology closure 与逐仓 validator；
- Waku 独立 compatibility candidate。

六仓 Golden 通过的固定数量合同：

| 合同 | 结果 |
| --- | ---: |
| 固定仓库 / Git identity | 6 / 6 |
| curated capabilities | 19 |
| audited slices | 66 |
| typed resolved relationship identities | 18 |
| known technology claims | 59 |
| 逐仓 validator | 6 / 6 valid |

六个项目仍分别为 SourceBridge、PocketFlow code2tutorial、OpenWiki、Understand Anything、CodeBoarding、DeepWiki Open，各自使用独立 reference mechanism / mapping / source range / non-adopted boundary；没有用单一项目替代六仓参考。

Waku 现场重新 cold build 后：memory、graph、loop、gateway 共 4 项，全部为 `entrypoint-candidate` + `confidence=candidate`，带 `compatibility-corpus:waku-not-curated`；`capability-cluster=0`，不进入六仓 curated 排名。

## 浏览器与静态门

| 命令 / 门 | 结果 |
| --- | --- |
| `PYTHONPATH=src .venv/bin/python -m unittest -v tests.test_features tests.test_artifacts tests.test_report tests.test_reference_ground_truth tests.test_validation` | 53 / 53 PASS；77.684s；无 skip |
| 精确捕获合并 78 伪入口 | 0 feature / 0 framework evidence / HTML 0；invalid await fail closed |
| class-comprehension 派生矩阵 | **10 / 10 错误确认；各 1 feature / 3 evidence / HTML hit / validator valid** |
| Python closure late rebind | **runtime fail；1 exact-entry / 3 evidence / HTML hit / validator valid** |
| JS arrow late rebind | **runtime fail；1 static-entry / 3 evidence / HTML hit / validator valid** |
| ghost source / target dangling | **tutorial / CodeMap / coverage 分裂** |
| `PYTHONPATH=src python3 -m unittest -v tests.test_report_mobile_browser` | 1 / 1 PASS；5.498s；真实 Google Chrome；1440×900 / 390×844 |
| `ruff check src tests` | `All checks passed!` |
| `PYTHONPYCACHEPREFIX=/tmp/repo-teacher-round10-pyc PYTHONPATH=src .venv/bin/python -m compileall -q src tests` | exit 0 |

浏览器测试从真实 `file://` 报告加载，在两个 viewport 中物理点击 details 与 source link，检查首屏、document/body width 与 overflow offender。Chrome launch 只有 `executable_path` 和 `headless=True`；没有 `--allow-file-access-from-files`、`--disable-web-security` 或其他策略绕过。

## 独立审查线说明

按代码复审流程尝试启动专用 `code-reviewer` 与 `architect` 角色，两者均因当前 ChatGPT 账户不支持其固定 `gpt-5-codex` 模型而在执行前 HTTP 400。随后启动两个继承当前可用模型、职责分离的只读 fallback lane：code-review lane 给出 REQUEST CHANGES 并发现 class-comprehension P0；architecture/devil's-advocate lane 给出 BLOCK 并发现 deferred closure 与 ghost endpoint 问题。主复审随后用公开链路独立复现了全部阻断，不把子 lane 的口头结论当作唯一证据。

## 解除阻断的最低条件

1. comprehension 的第一个 iterable 继续在当前 class scope 求值；comprehension body、filters 与后续 iterables 的 free-name lexical parent 必须跳过 class scope。新增至少上述 list/set/dict/generator、filter、第二 iterable、nested、lambda/default/decorator 公开链路回归。
2. deferred Python / JS closure body 不能冻结声明点父 scope provenance。只有在真实 callsite / 所有可达 rebind 路径仍证明同一 identity 时才能确认 framework boundary；否则降级 unknown。至少加入 Python lambda、nested function、JS arrow / function 的“声明后重绑普通对象再调用”回归。
3. `_valid_relationship()` 必须校验 source / target endpoint membership，并让 tutorial、CodeMap、coverage 共用同一 closure 结果；ghost source / target 对称降级为 location-only + 1 gap + coverage 0。
4. 若最终合同要求伪入口字面不进入 HTML，entry evidence 不得用无结构的 `line+5` 吞入已被分析器抑制的相邻伪入口。
5. 修复后重跑 78 合并反例、class / closure 新矩阵、53 项专项、六仓 6/6 与 19/66/18/59、Waku、真实 Chrome 390/1440、Ruff、compileall，再交由未参与修复的 reviewer 复审。

在 class comprehension 与 deferred closure 的 binding identity P0 消失前，Teaching / Feature / Tutorial / CodeMap / HTML 的最终结论保持 **REQUEST CHANGES / BLOCK**。
