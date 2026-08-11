# Go analyzer 第五次独立复审

> 审计对象：`src/repo_teacher/analyzers/go.py`、`go_semantic.py`、`analyzers/__init__.py`、`indexer.py` 的 Go resolver / warm 路径、`models.py`、`validation.py` 与专项测试  
> 真实基准：SourceBridge `2a128bf0c8461fae91d2b424d9168ddf205bb11b`  
> 审计方式：独立只读复审；除本报告外未修改产品代码、测试或正式 examples  
> 审计时间：2026-08-10（Asia/Shanghai）

## 结论

**Verdict：PASS**  
**Architectural status：CLEAR（限本轮 Go analyzer / resolver / warm baseline 范围）**

第四轮的全部 Go 阻断已经关闭。本轮用合法 Go 反例重新验证了嵌套 block、function literal、method receiver、named result，以及 `if` / `for` / `range` / `switch` / type-switch initializer 的精确作用域；没有再发现错误 method/function target 或局部绑定泄漏。warm 返回值与 baseline 不共享可变对象，磁盘 JSON baseline 可以完整复用 1,575/1,575 个文件，并保持 core/derived artifacts 与 cold 一致。

当前代码对 fresh SourceBridge cold 与磁盘 JSON warm 均得到 **0 errors / 1 个已知 dirty-worktree warning**；8 个机械错误门 cold/warm 全为 0，symbol/relationship ID 唯一，gopls 固定样本为 451/451。专项 67/67、Ruff、compileall 全部通过。

这个 PASS 不把 lexical fallback 夸大为语义级 Go type checker，也不覆盖尚未统一重生成的正式 `examples/reference-selection/projects/sourcebridge/`。正式 examples 是合并后的发布产物门，不是本轮 Go 实现正确性门。

## 第四轮阻断关闭矩阵

| 验收点 | 本轮重放结果 | 结论 |
|---|---|---|
| typed nested block shadow | `store *Store` 外层中，`store := Other{}` 内层不借用外层 `Store` 类型；内层 unresolved，离开 block 后恢复 `Store.Save` | PASS |
| untyped nested block shadow | method receiver `store *Store` 内执行 `store := any(nil)`；内层 unresolved，block 后恢复 receiver 的 `Store.Save` | PASS |
| typed function literal shadow | `func(store *Other)` 内精确连接 `Other.Save`，literal 外恢复 `Store.Save` | PASS |
| untyped/callable function literal shadow | `func(run func())` 内 `run()` 保持 `syntax-shadowed-unresolved`；literal 前后 package `run()` 均可解析 | PASS |
| method receiver shadow | receiver 只在 method body 的有效区间提供类型证据，内层同名变量不继承 receiver 类型且不向外泄漏 | PASS |
| named result：普通函数 | 单名、多名 named result 均 shadow package function；`(func(), error)` 等 unnamed result 不创建伪 binding | PASS |
| named result：function literal | literal 的单名、多名 named result 仅在 literal body 内生效；unnamed result 不 shadow；typed result `store *Other` 覆盖外层 `store *Store` | PASS |
| 普通 short declaration | `run := run()` 与 `run, other := run(), maker()` 的 RHS 仍解析 package `run`，声明后的 `run()` 才是 local/unresolved | PASS |
| `if` initializer | binding 覆盖 condition/body/else 链，并在整个 `if` 后结束；statement 后 package `run()` 恢复 | PASS |
| `for` initializer / post | init RHS `run()` 仍指 package function；condition、post、body 使用 local；普通 `run = maker()` 不创建新 binding；loop 后恢复 package `run()` | PASS |
| `range` declaration | `range values()` 的 RHS 仍指 package function；body 中 local `values()` unresolved；loop 后恢复 package `values()` | PASS |
| expression/type switch | initializer 或 type-switch guard 的 RHS 保持 package target；condition/body 使用 local；switch 后恢复 package target | PASS |
| warm mutable ownership | baseline 与 warm 的所有递归 `dict/list` identity 交集为 0；修改 warm 的 core/derived records 后 baseline digest 和 validator 仍有效 | PASS |
| 磁盘 JSON warm | cold 写盘、独立读取 JSON 后 warm 为 `compatible`，1,575 reused / 0 reanalyzed，derived artifacts reused | PASS |

实现边界与上述结果一致：`go.py` 的 `_statement_scope` 和 `_short_declaration_scope_start` 分别决定 statement 结束位置与声明真正可见的起点；`_local_bindings` 同时处理 receiver、parameters、named results、嵌套 literal parameters/results。普通 `=` 不再被当作声明。resolver 每个 occurrence 只消费其当前最内层的类型证据，没有证据时保持 unresolved。

## SourceBridge fresh cold / 磁盘 warm

本轮在共享工作区最后一次 validator 修复之后重新生成了新的 fingerprint 和两份临时 JSON；旧 fingerprint 产物没有被当作证据复用。

| 指标 | Cold | Disk JSON warm |
|---|---:|---:|
| analysis fingerprint | `0eee3da879690a35f868d6cc1ae3dea47e44a7968bfdd0f1e31cd6f5efd9e761` | 相同 |
| build | 31.537s | 17.619s（另含 JSON load 0.774s） |
| command wall | 34.77s | 23.77s |
| maximum resident set size | 525,959,168 bytes | 548,274,176 bytes |
| validator | 0 errors / 1 warning | 0 errors / 1 warning |
| baseline status | absent | `compatible` |
| files reused / reanalyzed | 0 / 1,575 | 1,575 / 0 |
| derived artifacts reused | false | true |
| Go symbols | 10,922 | 10,922 |
| Go relationships | 73,058 | 73,058 |
| receiver-type edges | 3,827 | 3,827 |
| calls resolved / unresolved | 7,816 / 41,169 | 7,816 / 41,169 |
| imports resolved / unresolved | 1,250 / 3,412 | 1,250 / 3,412 |

时间是在多个共享 Agent 并发运行时测得，只作为本机样本，不作稳定性能承诺。正确性数据不依赖性能数字。唯一 warning 是 SourceBridge clone 已知的 `dirty-worktree`（用户保留的 `D LICENSE`）。

### Cold/warm 内容一致性

两份落盘 JSON 重新读取后，以下集合逐项相等：

```text
files, symbols, relationships, modules, reading_path,
features, evidence, tutorials, codemaps, coverage, analyzers
```

两者 analysis fingerprint 相同。warm 的差异只限于预期的运行元数据，例如 `analyzed_at`、reuse statistics、change classification 和相应 integrity digest；没有 stale target 或 stale derived artifact。

## 八个机械错误门

以下检查同时在最终 cold 和 warm JSON 上运行，结果完全相同：

| 门禁 | Cold | Warm |
|---|---:|---:|
| 无限定名 / package selector 错连 method/interface-method | 0 | 0 |
| resolved cross-language calls | 0 | 0 |
| resolved non-callable targets | 0 | 0 |
| external/stdlib import -> local | 0 | 0 |
| external package selector -> local | 0 | 0 |
| receiver contract errors | 0 | 0 |
| cross-file lexical parent errors | 0 | 0 |
| duplicate relationship IDs | 0 | 0 |

总 symbol IDs 与总 relationship IDs 也分别唯一。receiver contract probe 额外确认每个 Go method 恰有一个有效 `receiver-type` edge，edge source/path 属于 method 文件，method 的 lexical `parent_id` 为空，target 是同 package 的本地 Go type/struct/interface。

## Warm ownership 与 JSON round-trip

自动测试与独立递归 identity probe 共同证明：

- cold 经 `json.dumps` / `json.loads` 后可作为 baseline；warm 为 `compatible`；
- baseline 与 warm 的递归 mutable containers（全部 `dict/list`）共享数量为 **0**；
- `files`、`symbols`、`relationships` 以及所有 primary/derived 集合内容一致但对象所有权独立；
- 逐集合修改 warm 的首个 record 后，baseline 的 `integrity_sha256` 不变，重新计算 digest 相等，`validate_index(baseline)` 仍为 true；
- SourceBridge cold/warm 的 core、derived、analyzer metadata 逐项相等。

对应实现是 warm hydrate 时重新物化 records，并在返回边界对 modules/reading path/features/evidence/tutorials/codemaps/coverage 做独立复制；calls/import/receiver-type 的 target 仍会先清空再由当前 resolver 重证，而不是信任旧 target。

## gopls 与自动化证据

固定 SourceBridge spread sample：

```text
files: 30
gopls declarations: 451
fallback declarations: 451
matched: 451
missing / extra: 0 / 0
```

这只证明 declaration occurrence 目录的一致性，不证明 lexical fallback 等价于 gopls call graph。

最终专项命令覆盖 analyzer、incremental/warm、validator：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_analyzers tests.test_indexer tests.test_validation -v

Ran 67 tests in 73.122s — OK
command wall: 73.49s
maximum resident set size: 265,863,168 bytes
```

其中 Go analyzer 31 项全部通过，包含 gopls 451/451、round4 shadow/named-result/scope 反例与本轮新增的 short-declaration RHS、for/range/switch/type-switch 精确 scope 反例。共享 validator 的 static feature mutation 合同也已在这次最终重跑中通过；此前实现报告记录的 6 个共享失败已不再存在。

```text
ruff check <本轮 Go/indexer/validation 源码与专项测试> — PASS
python3 -m compileall -q <同一范围> — PASS
```

## 与参考项目的关系

### SourceBridge

当前实现参考了 SourceBridge 的语言隔离、package/import 边界、receiver identity、增量重证和“歧义不连边”原则。它没有复制 SourceBridge 的 Tree-sitter AST/query 实现；本项目仍是手写 token/lexical fallback。因此可评价为机制层参考充分，但不是代码等价，也不能声称已具有完整 Go semantics。

### CodeBoarding

`go_semantic.py` 把 gopls 保持为显式、可选的 differential probe，并保留 path/URI/range/kind/qualified-name occurrence identity。451/451 是有效回归门，但当前没有 CodeBoarding 风格的持久 LSP server、definition/reference 正式图边、workspace readiness/backpressure/recycler；metadata 对这一边界保持诚实。

## 非阻断边界与发布交接

- fallback 仍然是 precision-first lexical analyzer；局部赋值 type inference、embedding/implements、interface dispatch、泛型 type checking 等没有类型证明的调用会 unresolved，而不是猜 target。
- 较高 unresolved 数字是当前安全边界，UI 不应展示为 `semantic-exact`。
- 本轮按审计范围没有重生成 `examples/reference-selection/projects/sourcebridge/index.json` 与 HTML。正式 examples 必须在所有共享 lane 合并后用最终 fingerprint 统一重生，再对磁盘正式 JSON 执行 validator 和 warm replay；本报告不为旧正式产物背书。
- 本轮未运行仓库所有非相关产品测试；已运行并通过 Go/indexer/validator 的 67 项专项。最终发布仍应由主 Agent 在全部并发 lane 冻结后执行一次全量测试。

在上述明确边界内，Go analyzer round5 可以结束整改并进入统一产物重生与全量发布验证阶段。
