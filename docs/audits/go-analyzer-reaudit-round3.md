# Go analyzer 第三次独立复审

> 审计对象：`src/repo_teacher/analyzers/go.py`、`go_semantic.py`、`analyzers/__init__.py`、`src/repo_teacher/indexer.py` 的 Go 集成、相关测试与 `docs/audits/go-analyzer-fix-round2.md`  
> 正式产物：`examples/reference-selection/projects/sourcebridge/index.json` 与 `index.html`  
> 真实仓库：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge` @ `2a128bf0c8461fae91d2b424d9168ddf205bb11b`  
> 审计时间：2026-08-10；只读复审，除本报告外未修改产品代码或产物

## 结论

**Verdict：REQUEST CHANGES**  
**Architectural status：BLOCK**

第二轮要求的主要精度门禁已有实质进步：SourceBridge 中原有的 23 条“无限定调用/package selector 错连 method”已归零，四类安全门禁仍为 0，30 文件 gopls 声明 occurrence 差分为 **451/451**，正式产物也已重生成并包含 10,922 个 Go symbols 与 69,231 条 Go relationships。

但当前仍不能 PASS，原因是两个可重现的正确性缺口：

1. **正式 SourceBridge index 无法通过产品自己的 validator，且不能作为增量基线复用。** `repo-teacher validate` 返回 826 errors：413 个 cross-file method parent 被判为非法，其对应的 413 条 contains 边又被判为 path/source 不一致。用该正式 index 做 `previous_index` 重放时，基线被整体拒绝，1,575 个文件全部重分析，`reused_files=0`。
2. **shadow 和 receiver 规则只覆盖了简单样例，仍会生成错误的 `syntax-scoped` target。** 多变量 `var` / `:=`、嵌套 function literal 参数不会完整进入 shadow set；局部变量覆盖本地 type 名时，resolver 仍会把 selector 当作 method expression 连到被覆盖的 type。

因此，当前实现可作为“precision-first 词法 fallback”继续修复，但不能把当前正式 index 标记为已验证生产产物，也不能将所有 `syntax-scoped` 边直接当作“底层实现链”的确定事实。

## 已通过项

### SourceBridge 正式产物与零错连门禁

| 检查 | 第三次复审结果 |
|---|---:|
| 正式 index schema / fingerprint | `2.0` / 64 hex，与当前源码及 config 计算值相同 |
| Go symbols | **10,922** |
| Go relationships | **69,231** |
| resolved / unresolved calls | **8,212 / 40,773** |
| unresolved ratio | **83.236%** |
| 原 23 条无限定/package selector → method/interface-method | **0** |
| cross-language resolved call | **0** |
| non-callable resolved call | **0** |
| external/stdlib import → local | **0** |
| external selector → local | **0** |
| 无显式本地类型证据的 resolved method call | **0（对正式产物的现有边机械重算）** |
| 重复 relationship ID | **0**；87,292 个 ID 全部唯一 |
| fallback analyzer metadata | enabled / implicit / 10,922 symbols / 69,231 relationships |
| gopls analyzer metadata | disabled / non-implicit / 0 fabricated records |

`index.html` 与 JSON 在本次复审时均已存在：HTML 约 30 MB，有完整 `doctype` / closing tag，包含 83 个 SourceBridge 本地源码链接；JSON 约 39 MB。这关闭了上轮“正式产物没有 Go 记录”的阻塞项，但不代表产物通过了 validator。

### occurrence-aware gopls

`DeclarationOccurrence` 身份包含 path、URI、起止 line/column、kind 和 normalized qualified name，并用 `Counter` 比较，不再用 leaf-name set 折叠同名 method。本机 `gopls v0.21.1` 真实重放：

```text
sample files: 30
expected declarations: 451
observed fallback declarations: 451
matched occurrences: 451
missing / extra: 0 / 0
sample manifests: 30
```

这项对“固定样本的声明目录”是 PASS；它不是 call graph 精度证明，当前 index metadata 也没有做这种夸大声明。

### 小型增量清边与自动化

- `tests.test_indexer.IndexerTest.test_deleted_go_target_is_not_reused_across_incremental_index` 通过：删除 `helper.go` 后，未变 `main.go` 上的旧 target 被清为 `None`。
- `tests.test_analyzers`：19/19 PASS，含真实 30 文件 gopls golden。
- `tests.test_indexer`：24/24 PASS，含 SourceBridge 真实 golden、零错连门禁、ID 唯一和 deleted-target 清理。
- `ruff check` 与 `compileall` 通过。

需要区分：小型 deleted-target 测试的正确性通过，但 SourceBridge 真实基线因 P0-1 被整体拒绝，所以当前还没有证明“这个真实大仓能增量复用并重证边”。

## Findings

### P0-1：cross-file receiver parent 与 validator/baseline 契约相互矛盾

**证据**

- `go.py:1290-1316` 会把 method 的 `parent_id` 指向同 package/同目录中的 receiver type，即使 type 在另一个文件；并把 contains edge 的 `source_id` 改为该 type。这个功能本身是用户需要的跨文件 receiver 归属。
- `indexer.py:268-270` 的 baseline gate 要求 parent 与 child 同 path；`indexer.py:298-304` 又要求 relationship path 必须等于 source symbol path。
- `validation.py:399-403` 与 `:411-418` 重复了同样的同文件假设。

正式 SourceBridge index 实测：

```text
repo-teacher validate .../sourcebridge/index.json
valid: false
errors: 826
dangling-parent-ref: 413
relationship-path-mismatch: 413
warnings: 1 (known dirty worktree: user-owned D LICENSE)
```

该 index 作为 `previous_index` 的真实重放：

```text
baseline_status: rejected
reason: baseline symbol ... has an invalid parent
reused_files / reanalyzed_files: 0 / 1575
elapsed: 9.681s (11.27s wall)
peak RSS: 637,304,832 bytes
```

**影响**

- 正式可视化产物未通过发布门禁。
- 跨文件 receiver 越完整，增量基线反而越不可用。
- SourceBridge 每次都变成全量重建，所以不能将小 fixture 的 deleted-target 测试扩大解读为真实大仓增量级保证。

**必须修复**

统一 graph schema、baseline gate 与 validator 对 cross-file parent/归属边的契约。修复后必须新增真实 SourceBridge 基线复用测试，断言 validator 0 errors、绝大部分未变文件被复用，且 cross-file method parent/contains 仍保留。

### P1-1：shadow 识别对合法 Go 多绑定和嵌套参数仍会错连

`go.py:1034-1084` 只完整处理外层函数参数与部分单名声明：

- `var other, run func(); run()` 只收集 `var` 后第一个名字，`run()` 被错连到 package function `run`。
- `run, other := maker(); run()` 只会收集 `:=` 前最后一个 identifier，第一个 `run` 被错连。
- `func outer(){ _ = func(run func()){ run() } }` 的嵌套 function literal 参数未进入 shadow set；内层 `run()` 还被归到 `outer` 并错连 package function。

三个最小探针均返回非空 target 且 `confidence="syntax-scoped"`。这不只是 unresolved 率问题，而是把已证明错误的边交给下游。

**必须修复**：要么建立最小词法作用域/多名绑定处理，要么对无法安全建模的嵌套 function literal 调用保持 unresolved。增加上述三个反例测试，不得只保留当前 `tests/test_analyzers.py:336-361` 的单参数/单 `:=` 样例。

### P1-2：被局部变量覆盖的 type 仍被当成 method expression receiver

`go.py:1371-1402` 对两段 selector 发现 root 已 shadow 时只禁用 import alias，但随后仍会用 `parts[0] in local_types` 把 root 当作本地 type。合法 Go 反例：

```go
type Store struct{}
type Other struct{}
func (Store) Save(){}
func (Other) Save(){}
func outer(){ Store := Other{}; Store.Save() }
```

实际 target 应是 `Other.Save`；当前 resolver 返回 `Store.Save` 且 confidence 为 `syntax-scoped`。这与 analyzer metadata 中“receiver selectors require explicit local type evidence”的边界不一致。

**必须修复**：如果 selector root 被局部绑定覆盖，必须禁用同名 type 的 method-expression fallback；在没有局部赋值类型推断时应保持 unresolved。

### P2-1：gopls 差分是声明目录 gate，不是语义边 gate

`go_semantic.py:283-398` 的 occurrence identity 已正确修复上轮折叠问题，但它仅比较 declaration symbols。`definition()` / diagnostics 仍未进入正式 index，正式 metadata 对此是诚实的。

`differential_sample()` 串行启动 30 次 command，每次拥有独立 timeout，无全局 deadline/cancellation/persistent server。本轮 19 个 analyzer tests 共用 33.848s，其中大部分时间为真实 gopls golden。这对显式 CI probe 尚可接受，但不能等价为 CodeBoarding 的持久 LSP 生产路径。

### P2-2：83.236% unresolved 是诚实的安全取舍，仍是产品边界

高 unresolved 没有被全局同名 fallback 掩盖，这一点应保留。但它意味着当前默认产物主要是“声明目录 + 部分可证明语法边 + 大量 unresolved candidates”，不是语义级调用图。UI/报告必须继续显示这一边界，不得把 `syntax-scoped` 改名为 `semantic-exact`。

## 与参考项目的机制对照

### SourceBridge Tree-sitter：约 70%（中等置信）

已参考并实现：语言隔离、package/local import 边界、call occurrence、receiver identity、same-package resolution、callable kind 限定和“歧义不连边”。未等价的部分仍包括 Tree-sitter AST/query、doc comment、field/const/var、test marker、embedding/implements/hierarchy，以及参考实现的增量契约。本轮新发现的 cross-file parent/baseline 矛盾使“增量复用”不能计为完整。

### CodeBoarding gopls/LSP：约 30%（中等置信）

已参考并实现：显式 gopls 可用性/timeout、document symbols、qualified receiver、source range、occurrence-aware 差分和 per-file manifest。未实现：持久 `gopls serve`、definition/reference 持久边、workspace readiness、progress/backpressure、server recycler、语义增量失效/重证。因此当前 gopls 只是差分基准，不是正式 analyzer backend。

## 再复审门槛

1. 统一 cross-file receiver parent/contains 的 schema、baseline 和 validator 契约；正式 SourceBridge JSON 必须 `validate` 0 errors。
2. 用正式 SourceBridge index 作基线重放，基线必须 compatible，未变文件应实际复用，不得再是 0/1,575。
3. 增加 multi-name `var` / `:=`、嵌套 function literal parameter 和局部 type-name shadow 反例；所有未证明边必须 unresolved。
4. 继续保持原 23 条错连、跨语言、非 callable、外部 import、外部 selector 全为 0。
5. 继续保持 30 文件 occurrence-aware gopls 451/451、relationship ID 唯一、deleted-target 清空和诚实 fallback/gopls metadata。
6. 重生成 SourceBridge JSON/HTML，再运行产物 validator 与真实增量基线 gate；仅“文件存在”不等于发布合格。

## 验证记录

```text
PYTHONPATH=src python3 -m unittest tests.test_analyzers -v
# 19 tests in 33.848s — PASS

PYTHONPATH=src python3 -m unittest tests.test_indexer -v
# 24 tests in 12.274s — PASS

ruff check <Go analyzer/indexer/test scope>
python3 -m compileall -q <Go analyzer/indexer/test scope>
# PASS / PASS

PYTHONPATH=src python3 -m repo_teacher validate \
  examples/reference-selection/projects/sourcebridge/index.json
# FAIL: 826 errors, 1 warning

<formal SourceBridge index mechanical safety probe>
# unsafe shape=0; cross-language=0; non-callable=0;
# external import=0; external selector=0; method without explicit type proof=0;
# relationship IDs unique

<formal SourceBridge previous_index replay>
# baseline rejected; reused=0; reanalyzed=1575; elapsed=9.681s
```

SourceBridge worktree 的唯一已知 dirty 项是用户保留的 `D LICENSE`；本审计未恢复或修改它。

**最终结论：REQUEST CHANGES。**
