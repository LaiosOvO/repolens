# Go analyzer 第四次独立复审

> 审计对象：`src/repo_teacher/analyzers/go.py`、`go_semantic.py`、`analyzers/__init__.py`、`indexer.py` 的 Go resolver/metadata/warm 路径、`models.py`、`validation.py` 与相关测试  
> 对照仓库：SourceBridge `2a128bf0c8461fae91d2b424d9168ddf205bb11b`、CodeBoarding 当前本地完整 clone  
> 审计方式：只读复审；除本报告外没有修改产品代码、测试或正式产物  
> 时间：2026-08-10（Asia/Shanghai）

## 结论

**Verdict：REQUEST CHANGES**  
**Architectural status：BLOCK**

第三轮的 receiver 图合同修复是真实有效的：method 不再跨文件挂到 receiver type 的 `parent_id`，`file -> method` 的 lexical/file containment 保留，另用 `method -> type` 的 `receiver-type` 边表达语义归属。当前源码对 SourceBridge cold index 可做到 validator **0 errors**，原错误形状、跨语言、非 callable、外部 import/selector 均为 0，451/451 gopls declaration occurrence golden 也继续通过。

但不能 PASS，原因是以下独立复现的生产正确性问题：

1. **typed parameter / receiver 被内层同名绑定遮蔽后，resolver 仍使用外层显式类型，产生确定错误的 method target。** 同样的问题发生在嵌套 function literal 的同名参数上。这直接违反本轮“receiver/parameter shadow”的验收项。
2. **named result parameter 没有进入 binding model**，可被错误解析为同名 package function。
3. **no-change warm 输出与输入 baseline 共享大量可变对象。** 修改 warm 输出会同时篡改 baseline，使 baseline 的既有 `integrity_sha256` 失效；“immutable value”只是注释约定，没有代码合同。
4. **磁盘 JSON baseline 的真实 warm 路径仍未通过发布闭环。** 两次独立重放均为 `compatible`、1,575/1,575 reused，但产物 validator 出现 5 个 `unsupported-feature-confidence` errors。该问题位于 derived artifact 复用边界，说明“内存对象 warm 通过”不能替代 CLI/JSON round-trip 验证。
5. `examples/reference-selection/projects/sourcebridge/` 仍是旧正式产物，当前 validator 为 **827 errors**，没有重生成。

因此当前 Go analyzer 是有明显进展的 precision-first fallback，但仍不能标记为生产完成。

## 已通过的门禁

### 1. Receiver ownership 与 lexical containment 已分离

实现证据：

- `go.py:811-814`：Go method `parent_id=None`，不再把 receiver type 当 lexical parent。
- `go.py:1423-1471`：项目级 resolver 唯一解析同目录、同 package 的 receiver type，发出 `receiver-type` 边。
- `go.py:1456-1464`：关系 source/path/line 来自 method 所在文件和 method 声明行。
- `go.py:1643-1656`：method 仍由其源文件通过 `contains` 包含。
- `validation.py:399-418`：现有 parent 与 relationship source/path 合同与上述模型一致。

真实 SourceBridge cold probe：

| 检查 | 结果 |
|---|---:|
| Go symbols | 10,922 |
| Go relationships | 73,058 |
| `receiver-type` edges | 3,827 |
| invalid receiver source/path/target | 0 |
| cross-file `parent_id` | 0（包含于 receiver contract probe） |
| validator | 0 errors / 1 known dirty warning |

### 2. SourceBridge 安全形状门禁继续为 0

本轮从当前源码 cold build 后机械检查 91,119 条总 relationships：

| 检查 | 结果 |
|---|---:|
| 原“无限定/package selector -> method/interface-method”错误形状 | 0 |
| resolved cross-language calls | 0 |
| resolved non-callable targets | 0 |
| external/stdlib import -> local | 0 |
| external package selector -> local | 0 |
| receiver contract errors | 0 |
| duplicate relationship IDs | 0 |

Go resolution metadata：

```text
calls resolved / unresolved:       8,224 / 40,761
imports resolved / unresolved:     1,250 / 3,412
receiver types linked:             3,827
```

`indexer.py:1211-1243` 仍诚实声明 fallback 为 `precision-first-syntax-fallback`，gopls 为 disabled、explicit opt-in differential，未伪装成 semantic-exact backend。

### 3. gopls occurrence golden 与删除清边继续通过

- `tests.test_analyzers.AnalyzersTest.test_sourcebridge_30_file_gopls_occurrence_golden`：30 files、451 expected、451 observed、451 matched、missing/extra 0/0。
- occurrence identity 包含 path/URI、source range、kind、qualified name；同 leaf-name method 不会被 set 折叠。
- `test_deleted_go_target_is_not_reused_across_incremental_index` 通过，删除 target 后旧 `target_id` 被清空。
- `test_go_relationship_resolution_is_not_overwritten_by_global_name_fallback` 通过。
- `test_cross_file_go_receiver_graph_validates_and_reuses_warm_baseline` 通过小 fixture。

专项测试：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_analyzers tests.test_indexer tests.test_validation -v

Ran 54 tests in 43.000s — OK
maximum resident set size: 290,013,184 bytes
```

`ruff check` 与 `compileall` 对审计范围均通过。

## Findings

### P0-1：内层 shadow 没有覆盖外层 typed binding，生成错误 method target

**位置**

- `go.py:949-975` 正确把当前 call occurrence 标成 `syntax-shadowed-unresolved`。
- 但 `go.py:1552-1561` 无条件先读取 `typed_bindings_by_symbol[source.id]`；`was_shadowed` 只禁用 type-name fallback，没有禁用已经从外层函数 signature 得到的 typed binding。
- `_typed_local_bindings` 是按整个 symbol 生成的单张 name -> type 表（`go.py:1258-1348`），没有 occurrence/scope 维度。

**合法 Go 反例**

```go
type Store struct{}
type Other struct{}
func (Store) Save(){}
func (Other) Save(){}

func f(store *Store) {
    { store := Other{}; store.Save() }
    store.Save()
}
```

实际输出：两个 `store.Save()` 都是 `syntax-scoped -> Store.Save`。第一条实际 receiver 是 `Other`；zero-dependency fallback 若不做赋值类型推断，至少必须保持 unresolved，绝不能连到 `Store.Save`。

嵌套 function literal 同样失败：

```go
func f(store *Store) {
    _ = func(store *Other) { store.Save() }
    store.Save()
}
```

内层 call 被错误解析为 `Store.Save`，而不是 `Other.Save` 或保守 unresolved。

**影响**

这是确定错误边，会把用户带到错误的底层实现文件；它正位于用户要求的“点击模块后看实现链”关键路径，不能以“高 unresolved 是安全取舍”解释。

**必须修复**

typed binding 必须按 call occurrence 的 lexical scope 解析；最低安全修复是在 `was_shadowed` 时禁止复用外层 signature binding。增加 nested block 和 nested func-literal 两个反例，断言 shadow occurrence 无错误 target、离开 scope 后外层 call 仍可解析。

### P1-1：named result parameter 未进入 shadow binding

**位置**

- `_FunctionDecl` 只保存 receiver 和 input parameter ranges（`go.py:102-111`）。
- `_extract_functions` 在 input parameters 后寻找 body，但没有保存 named result group（`go.py:775-827`）。
- `_local_bindings` 只遍历 receiver 与 input parameters（`go.py:1136-1145`）。

**反例**

```go
func run() {}
func f() (run func()) { run() }
```

当前输出：`run()` 为 `syntax-scoped -> package function run`；实际是 named result function value。

**必须修复**

解析并保存 result parameter group，将 named results 纳入整个 function body 的 lexical bindings；增加单名、多名以及 unnamed result type 回归测试。

### P1-2：warm copy-on-change 实际共享可变输入/输出

**位置**

- `_serialize_records_with_warm_reuse` 在相等时直接 `serialized.append(prior)`（`indexer.py:123-160`）。
- no-change artifact 路径直接赋值 baseline 的 modules/features/evidence（`indexer.py:1077-1103`）与 tutorials/codemaps/coverage（`indexer.py:1280-1287`）。
- 注释称这些值 immutable，但 schema 是普通可变 `dict/list`，API 没有 freeze/copy 防线。

最小复现的对象身份：

```text
files[0] shared:         true
symbols[0] shared:       true
relationships[0] shared: true
modules/features/evidence/tutorials/codemaps/coverage collection shared: true
```

随后执行 `warm["files"][0]["module"] = "MUTATED"`：

```text
cold["files"][0]["module"] == "MUTATED"
cold integrity digest still valid: false
validate_index(cold).valid: false
```

**影响**

调用者对新结果做正常后处理即可污染作为下一轮 baseline 的旧对象；完整性摘要因此变成“返回时正确、共享对象被改后失效”。这也让 stale derived artifact 的归属和生命周期不可审计。

**必须修复**

在 API 合同层实现真正不可变值或隔离 copy；至少新增 identity/mutation regression，证明修改 warm 任意 core/derived nested value 不会改变 `previous_index`，两边 checksum 均保持自洽。若为内存选择结构共享，必须使用不可变容器并在 JSON 边界明确 materialize。

### P1-3：磁盘 JSON baseline 的 warm 发布路径仍未闭环

真实生产路径不是“同一 Python 进程把 cold dict 直接传回”，而是 CLI 从 `index.json` 读取 baseline。两次独立 JSON round-trip 重放：

```text
baseline_status: compatible
files reused / reanalyzed: 1,575 / 0
derived artifacts reused: true
warm build: 4.710s / 5.970s
warm max RSS: 650,117,120 / 594,460,672 bytes
validator: 5 errors / 1 known dirty warning
error code: unsupported-feature-confidence (5 exact-entry features)
```

这说明 core baseline gate 和文件复用已工作，但 derived artifact 复用不能只依靠 fingerprint/commit/dirty/remote 相等；必须对将被复用的 features/evidence/tutorial/codemap/coverage 做完整 validator gate，且必须添加“写 JSON -> 新进程读 JSON -> warm build -> validate 0”集成测试。

该发现也使内存 warm 的“0 errors”不足以作为发布证据。

### P2-1：statement scope 被扩大，导致可证明调用在离开作用域后仍 unresolved

`_local_bindings` 仅以已进入的 `{}` stack 决定 `scope_end`（`go.py:1147-1216`）。`if`/`for`/`switch` init 中的 `:=` 发生在 body `{` 之前，因此被绑定到外层 function scope。

反例：

```go
func run(){}
func maker() func(){ return nil }
func f(){ if run := maker(); run != nil { run() }; run() }
```

当前内外两个 `run()` 都是 `syntax-shadowed-unresolved`；最后一个应恢复解析到 package `run`。这不是错误 target，但损失了本可证明的图边，应在完成 P0/P1 后修复 statement scope。

### P1-4：正式 SourceBridge 示例仍是旧产物

当前文件：

```text
examples/reference-selection/projects/sourcebridge/index.json  37 MB
examples/reference-selection/projects/sourcebridge/index.html  29 MB
mtime: 2026-08-10 03:08
```

当前 validator：

```text
827 errors / 1 warning
1 analysis-fingerprint-mismatch
413 dangling-parent-ref
413 relationship-path-mismatch
```

这与修复报告“尚未重生成”的说明一致，但意味着用户现在打开的正式 HTML/JSON 仍无法证明第四轮实现。它必须在代码通过下一轮复审后统一重生，不能把本轮临时内存 cold probe 当作已发布产物。

## 性能与内存

### Cold

独立 SourceBridge cold build：

```text
build: 10.536s
build + validate wall: 12.45s
maximum resident set size: 388,202,496 bytes
validator: 0 errors / 1 warning
```

相对上一轮记录的 637,304,832 bytes，cold RSS 下降约 **39.1%**，这是实质改进。

### Warm

磁盘 JSON baseline 的两个独立进程样本：build 4.710–5.970s，但 RSS 为 594,460,672–650,117,120 bytes。相对旧 637 MB 一次略低、一次略高，**不能声称 warm memory 已稳定改善**。更重要的是两个产物都有 5 个 validation errors，因此性能数字不能替代正确性门禁。

同进程同时保留 cold/warm 两份对象的样本最大 RSS 为 549,273,600 bytes；该数字受结构共享影响，正是 P1-2 要求补齐别名合同的原因。

## 与参考项目的关系和诚实边界

### SourceBridge

SourceBridge 的 `internal/indexer/languages.go` 注册 Go Tree-sitter grammar/query，`internal/indexer/parser.go` 通过真实 AST 抽取，`internal/indexer/indexer.go` 描述 incremental read -> parse 管线。当前实现确实吸收了语言隔离、receiver identity、package/local import 边界、歧义不连边和增量重证的思路。

但当前仍是手写 token/lexical fallback，不等价于 SourceBridge 的 AST/query：没有完整 scope/type checker、embedding/implements、field/const/local type hierarchy。P0-1 正是这个边界在 typed shadow 上的具体表现。参考程度可评为约 **70% 的机制启发、非代码等价**；不能说“完全参考”。

### CodeBoarding

CodeBoarding `static_analyzer/engine/lsp_client.py` 实现持久 LSP 生命周期、`documentSymbol`、`definition`、batch、workspace readiness、diagnostics/progress；`call_graph_builder.py` 还有启动探针和位置去重。当前 `go_semantic.py` 只实现显式、串行命令式 gopls differential。

451/451 只证明固定样本的 declaration occurrence 目录，不证明 call graph 语义正确。没有持久 `gopls serve`、definition/reference 正式边、workspace backpressure/recycler。参考程度约 **30%**，metadata 当前对此表述诚实，应保持。

## 再复审门槛

1. 修复 typed outer binding 被 nested block / nested function literal shadow 后仍错误连 method 的问题；两个反例不得有错误 target，外层恢复后仍应解析。
2. named result parameter 纳入 binding model，`func f()(run func()){run()}` 不得连到 package function。
3. 增加 if/for/switch initializer scope 回归；至少离开 statement 后不继续 shadow。
4. warm 输出不得与 baseline 共享可变 nested objects，mutation regression 后两份 index checksum/validator 均保持有效。
5. 新增真实 JSON round-trip warm 集成门禁：compatible、reused 接近全部且非 0、reanalyzed=0、validator 0 errors、derived artifacts 闭包有效。
6. 保持 SourceBridge receiver contract、原错误形状、跨语言、非 callable、external import/selector、重复 ID 全为 0。
7. 保持 gopls 451/451、deleted target 清空、fallback/gopls metadata 诚实。
8. 最终重新生成 `examples/reference-selection/projects/sourcebridge/index.json` 与 HTML，并对磁盘正式 JSON 再跑 validator 和 warm replay。

## 可复现命令摘要

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_analyzers tests.test_indexer tests.test_validation -v

ruff check \
  src/repo_teacher/analyzers/go.py \
  src/repo_teacher/analyzers/go_semantic.py \
  src/repo_teacher/analyzers/__init__.py \
  src/repo_teacher/indexer.py src/repo_teacher/models.py \
  src/repo_teacher/validation.py \
  tests/test_analyzers.py tests/test_indexer.py tests/test_validation.py

python3 -m compileall -q \
  src/repo_teacher/analyzers src/repo_teacher/indexer.py \
  src/repo_teacher/models.py src/repo_teacher/validation.py \
  tests/test_analyzers.py tests/test_indexer.py tests/test_validation.py

PYTHONPATH=src python3 -m repo_teacher validate \
  examples/reference-selection/projects/sourcebridge/index.json
```

SourceBridge worktree 的已知 `D LICENSE` 属于用户现有状态；本审计没有恢复或修改。

**最终结论：REQUEST CHANGES。**
