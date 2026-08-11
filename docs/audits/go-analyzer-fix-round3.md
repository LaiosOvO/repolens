# Go analyzer 第三次复审修复记录

> 对应审计：`docs/audits/go-analyzer-reaudit-round3.md`、`docs/audits/go-analyzer-reaudit-round4.md`  
> 修复范围：Go lexical fallback、项目级 Go resolver、warm baseline 序列化/复用、相关测试  
> 真实基准：SourceBridge `2a128bf0c8461fae91d2b424d9168ddf205bb11b`  
> 结论：第四轮反例整改与专项验证已完成，等待新的独立 Agent 复审；本记录不自行给出 PASS。

## 修复结果摘要

第三轮先关闭了两个正确性阻断：

1. Go receiver 不再伪装成 lexical parent。method 始终是 package/file 级声明，`parent_id` 不再跨文件指向 receiver type，`contains` 也保持真实的 `file -> method`。receiver 归属由独立的 `method -> type`、`kind=receiver-type` 关系表达。
2. call root 的 shadow 判断从“少量单名模式”提升为有作用域区间的保守绑定模型，覆盖多名 `var`、多名 `:=`/赋值、method receiver、普通参数和嵌套 function literal 参数。局部变量覆盖 type 名时，resolver 不再退回同名 type 的 method-expression 规则。

第四轮独立复审又发现并复现了四项生产问题：内层同名绑定错误继承外层 receiver 类型、named result 未进入 binding model、`if` initializer scope 过宽，以及 warm 输出与 baseline 共享可变对象。第五轮整改已逐项关闭并加入合法 Go 反例。

最终稳定树上，真实 SourceBridge cold 与磁盘 JSON round-trip warm 均通过 validator；两次 fingerprint 相同，warm baseline 为 compatible，1,575 个文件全部复用，0 个文件重分析。

## 1. Receiver 图合同

### 旧模型为何错误

旧模型会把跨文件 method 的 `parent_id` 改成 receiver type，并将 method 原本的 `file -> method` contains 边改成 `type -> method`。这同时违反两个既有合同：

- `parent_id` 表示同文件 lexical nesting；
- relationship 的 `path` 和 source symbol/file 的 path 必须一致。

因此 SourceBridge 正式 index 出现 413 个非法 cross-file parent 和 413 个 path/source mismatch，共 826 errors，baseline 也被拒绝。

### 新模型

```text
type.go:    file(type.go)   --contains------> Store
method.go:  file(method.go) --contains------> Store.Save
method.go:  Store.Save      --receiver-type-> Store
```

`receiver-type` 关系的 source 是 method，`path` 与 `line` 也来自 method 声明文件，因此保持 relationship source/path/range 合同。target 可以跨文件，但每次 cold/warm 都由同目录、同 package、唯一 receiver type 重新证明。

SourceBridge 结果：

| 门禁 | 结果 |
|---|---:|
| Go methods linked by `receiver-type` | 3,827 |
| cross-file `parent_id` | 0 |
| invalid receiver source/path/target | 0 |
| validator errors | 0 |
| validator warnings | 1（已知用户保留的 `D LICENSE`） |

## 2. Warm baseline 合同

warm hydration 只清除必须重新证明的 target：`calls`、`import`、`receiver-type`。同文件、同 source 的 `contains` target 不再被无条件抹掉。

无源文件变化且 project commit/dirty/remote 与 baseline 相同时：

- 复用 modules、reading path、features、evidence 及 tutorial/codemap/coverage 的分析结果；
- 避免 `enrich_index` 对整个大 index 再做一次 deepcopy；
- files/symbols/relationships 重新物化为独立字典，所有复用的 primary/derived 容器也在返回前独立复制；调用者修改 warm 任意 nested dict/list 不会污染 `previous_index` 或破坏其 integrity；
- 在最终稳定性复扫前释放第一轮 scan 的源码正文，稳定性复扫仍比较完整 file identity 和 tree/snapshot manifest。

真实 SourceBridge warm 结果：

| 指标 | 结果 |
|---|---:|
| baseline status | `compatible` |
| files | 1,575 |
| reused files | 1,575 |
| reanalyzed files | 0 |
| warm build | 5.686s（磁盘 JSON baseline，最终稳定树） |
| warm validator | 0 errors / 1 known dirty warning |
| derived artifacts reused | true |

最终 cold→JSON 写出/读回→warm→双 validator→warm JSON 写出在同一测量进程中的 max RSS 为 **550,977,536 bytes**，低于历史 637 MB；该值包含同时持有 baseline、独立 warm snapshot 与 JSON 字符串。

## 3. Lexical shadow 与 selector 安全

`_LocalBinding(name, start, end, type_name)` 只在绑定实际可见的 token 区间提供 shadow/type evidence。call relationship 持久化该 occurrence 的可选 `receiver_type_hint`，resolver 不再读取 whole-function 的 name→type 表。已加入并通过以下合法 Go 反例：

```go
var other, run func()
run() // unresolved local value

run, other := maker()
run() // unresolved local value

_ = func(run func()) {
    run() // unresolved nested parameter
}

type Store struct{}
type Other struct{}
func outer() {
    Store := Other{}
    Store.Save() // never resolves to type Store's method
}
```

另有 scope boundary 回归：function literal 内的 `run` 参数只影响 literal body，literal 前后的 package-level `run()` 仍可解析。该测试避免用 whole-function shadow set 换取虚假的“安全”。

对于 `Store := Other{}; Store.Save()`，当前 zero-dependency fallback 选择 unresolved。它没有凭名字推断为 `Store.Save`，也没有声称已经实现局部赋值 type inference。若未来由显式 type evidence 或 gopls 证明为 `Other`，才可连接 `Other.Save`。

第四轮反例还覆盖：

```go
func block(store *Store) {
    { store := Other{}; store.Save() } // unresolved，绝不连 Store.Save
    store.Save()                       // Store.Save
}

func literal(store *Store) {
    _ = func(store *Other) { store.Save() } // Other.Save
    store.Save()                              // Store.Save
}

func one() (run func()) { run(); return nil } // named result，unresolved
func unnamed() (func(), error) { run(); return nil, nil } // package run

func scoped() {
    if run := maker(); run != nil { run() } // local，unresolved
    run()                                    // package run
}
```

method receiver 的同名 nested block shadow 也有独立回归：内层 unresolved，离开 block 后恢复 receiver method。单名、多名 named result 与 unnamed result type 均被区分。

第五轮独立审计继续发现了两个合法 Go 边界，现已补齐：

```go
func loop() {
    for run := maker(); run(); run = maker() {
        run() // for-init local
    }
    run() // package function
}

func outer() {
    _ = func() (run func()) {
        run() // literal named result，unresolved local value
        return nil
    }
    run() // package function
}
```

- 普通 `=` 赋值不会创建 binding。`for` post clause 的 `run = maker()` 只更新 init 已声明的变量，不再产生延伸到函数末尾的伪 binding。
- `if`/`for`/`switch` header 的 `:=` 可以跨 header 分号回溯到 statement owner，binding 精确覆盖 condition、post、type-switch guard 和 body，并在整个 statement 结束后终止。binding start 也被移到声明完成之后：`run := run()`、多名 `run, other := run(), maker()`、`for run := run()`、range 与 type-switch guard 的 RHS 同名 call 仍指向 package function，新局部名只影响声明后的 occurrence。
- function literal 除 input parameters 外，也解析 parenthesized result group。单名、多名 named results 在 literal body 内 shadow package function；unnamed result type不产生名字。显式 typed result 产生自身 receiver type evidence，不会继承外层同名 parameter/receiver。

## 4. SourceBridge 真实门禁

最终 cold probe：

```text
cold build: 18.900s（与独立审计并发运行时记录）
combined cold + disk warm max RSS: 550,977,536 bytes
validator: 0 errors / 1 known dirty warning
Go symbols: 10,922
Go relationships: 73,058
receiver-type: 3,827
calls resolved / unresolved: 7,816 / 41,169
imports resolved / unresolved: 1,250 / 3,412
```

精度与图闭包：

| 检查 | 结果 |
|---|---:|
| 原无限定/package selector -> method/interface-method | 0 |
| external selector -> local | 0 |
| external/stdlib import -> local | 0 |
| resolved non-callable | 0 |
| cross-language resolved call | 0 |
| cross-file parent | 0 |
| receiver edge contract errors | 0 |
| relationship ID duplicates | 0 |

gopls declaration occurrence golden 保持：30 files、451 expected、451 observed、451 matched、missing/extra 0/0。

## 5. 自动化验证

```text
PYTHONPATH=src python3 -m unittest tests.test_analyzers -q
# 31 tests in 42.703s — PASS（含 gopls 451/451）

PYTHONPATH=src python3 -m unittest tests.test_indexer tests.test_validation -q
# 36 tests in 30.072s — PASS

ruff check src tests
python3 -m compileall -q src tests
# PASS / PASS

PYTHONPATH=src python3 -m unittest discover -s tests -q
# 第五轮最终重放待共享 Skill-export lane 稳定后补录
```

第三轮全量曾在共享 Teaching lane 稳定后达到 179/179 PASS。第五轮期间共享 Skill-export lane 的 `PosixPath` 参数错误曾中断一次全量；随后 6 个新 static-feature ground-truth mutation validator 测试短暂失败。对应 validator lane 闭合后已重跑，Go/indexer/validation 专项最终 **67/67 PASS**。全仓总数仍在其他并发 lane 增加测试，最终全量由父 Agent 在所有 lane 冻结后统一重放。

## 6. 与参考项目的关系

### SourceBridge

继续参考其 Tree-sitter analyzer 的语言隔离、package/local import 边界和 receiver identity，但没有复制 AST/query 或伪装成语义分析。新 `receiver-type` 边把 receiver ownership 与 lexical containment 分离，这一合同也适合未来接入 SourceBridge 风格的 type hierarchy/embedding。

### CodeBoarding

继续把 gopls 当显式差分基准，不在默认 index 中静默启动 LSP。451/451 只证明声明 occurrence 目录，不夸大为 call graph 精度。持久 gopls server、definition/reference 边、workspace readiness/backpressure 仍属于后续独立模块。

## 7. 剩余边界与交接

- fallback 仍是 precision-first lexical analyzer；高 unresolved 是明确边界，不应在 UI 中改称 semantic-exact。
- 局部 composite literal/type inference、interface dispatch、embedding/implements 和泛型 type checking 仍未实现。
- 本轮没有重生成 `examples/reference-selection/projects/sourcebridge/index.json`/HTML；主 Agent 已要求在所有并发修复合并后统一重生技术选型正式产物。重生后必须再次运行正式文件 validator 和 warm replay。
- final direct-type/scope-start guard 后已在稳定树重新生成 cold JSON 并读回 warm：fingerprint 相同、compatible、1,575/1,575 reused、0 reanalyzed、cold/warm 均 0 errors / 1 dirty warning。
- 需要新的独立审计 Agent 对 round4 全部反例、mutable-alias、磁盘 warm、SourceBridge 门禁与正式产物重新复审；本修复 Agent 不自行判定 PASS。
