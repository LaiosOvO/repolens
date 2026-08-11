# Go analyzer 第三轮修复证据

> 对应复审：`docs/audits/go-analyzer-reaudit.md`  
> 修改范围：Go lexer/resolver、显式 gopls differential、正式 index 元数据与生产门禁测试  
> 当前状态：实现和本地验证完成，**等待独立 Agent 复审；本文不自行给出 PASS**

## 先看结论

本轮关闭了第二次复审的两个阻塞项：

1. 无限定调用和 package selector 只允许解析到 package-level `function`，不再把 method/interface method 当成候选。参数或局部 function value shadowing 会显式保留为 `syntax-shadowed-unresolved`。
2. gopls 差分从 leaf-name `set` 改为 declaration occurrence：身份包含 URI、相对 path、精确 name range、kind 和 normalized qualified name。同名 interface/method 不再互相抵消。

同时补上了一条受限的 receiver method 能力：只有方法 receiver、显式本地类型参数或 `Type.Method` method expression 提供本地类型证据时才解析 method；赋值推断、interface dispatch、embedding 和无类型证据 selector 继续 unresolved。

## 复审项逐条对应

| 复审要求 | 本轮实现 | 自动化/真实证据 |
|---|---|---|
| 无限定/package selector 不得指向 method/interface-method | resolver 将 package function 和 method 拆成独立 index；前两种调用形状只查 `function_index` | SourceBridge 全仓 unsafe shape target = **0**；反例测试覆盖 method 和 interface-method |
| receiver selector 必须有类型证据 | `_typed_local_bindings()` 只读取显式 receiver/parameter local type；无证据 selector 不查 method index | `store *Store → store.Save()` 与 `Store.Save(store)` 可解析；`other any → other.Save()` unresolved |
| 参数/局部 function value shadowing | `_shadowed_callable_names()` 识别 named parameter、`var`、`:=`、assignment；resolver 不再用同名 package function/alias 覆盖 | `run func(...); run()` 与 `run := func(){}; run()` 均 unresolved；真正 package `run()` 仍可解析 |
| SourceBridge 原 23 条错边归零 | 正式 `build_index()` 后按 call shape + import alias + target kind 机械检查 | **0** |
| 四类安全门禁继续为零 | 语言、callable、module/import alias、target kind 约束仍保留 | cross-language=0；non-callable=0；external import=0；external selector=0 |
| gopls occurrence-aware identity | `DeclarationOccurrence` 使用 path/URI/range/kind/qualified name；用 `Counter` 比较 occurrence，不做集合折叠 | 固定 30 文件：**451 expected / 451 observed / 451 matched** |
| 可复核 sample manifest | `GoplsSampleManifest` 逐文件返回 path、URI、expected/observed/matched 和 mismatch 位置 | 30 个 manifest；missing=0，extra=0 |
| 显式 `GoplsAdapter("gopls")` | 无路径分隔符的 executable 同样经 `shutil.which` 解析 | 真实 `gopls v0.21.1` golden test 使用该形式 |
| 正式 index 有 fingerprint / analyzer 边界 | `build_index()` 写入 `analysis_fingerprint` 和两条 analyzer metadata | Go fallback record 非零；gopls record 明确 `enabled=false / implicit=false / records=0`，不伪造 semantic edge |
| deleted-file 增量失效 | 全局 Go resolver 每次先清除 hydrated target，再按当前 symbol/file 集合重解析 | 删除 `helper.go` 后，复用的 `main.go → helper()` target 变为 `None` |
| 真实 Git capability 进入 feature discovery | `build_index()` 将已捕获的 `project_snapshot` 传给 `discover_features()` | 真实 Understand Anything Git clone 产生 3 条 source-audited capability；无 Git 文件副本为 0 条 source-audited |

## 与参考项目的实现关系

### SourceBridge Tree-sitter 索引器

参考文件：

- `repo/sourcebridge/internal/indexer/languages.go`
- `repo/sourcebridge/internal/indexer/parser.go`
- `repo/sourcebridge/internal/indexer/indexer.go`

采用了它的语言隔离、package/local import 边界、call occurrence、receiver identity、same-package resolution 和“歧义不连边”。本轮进一步收紧了调用形状：package function、method、interface method 使用不同候选集合；这是对第二轮错边证据的直接修复。

没有复制其 AGPL Tree-sitter 代码，也没有新增 parser 依赖。当前仍是 clean-room lexer fallback，因此 doc comment、field/const/var、embedding/implements 等语法教学信息尚未等价。

### CodeBoarding gopls/LSP

参考文件：

- `repo/codeboarding/static_analyzer/engine/adapters/go_adapter.py`
- `repo/codeboarding/static_analyzer/engine/call_graph_builder.py`
- `repo/codeboarding/static_analyzer/engine/symbol_table.py`
- `repo/codeboarding/static_analyzer/incremental_orchestrator.py`

采用了 gopls 作为显式语义基准、qualified receiver、source range、逐文件 mismatch 和 changed/deleted 后重证的边界。本轮 differential identity 已能够区分 `Reader.Run` 与 `Writer.Run`，也能区分 kind 和位置。

尚未实现 CodeBoarding 的持久 `gopls serve`、definition/reference 持久边、progress/backpressure、server recycler 和 semantic incremental orchestration。因此正式索引诚实记录 `go-semantic-gopls.enabled=false`，没有把 fallback edge 标成 `semantic-exact`。

## SourceBridge 全仓正式重放

固定仓库：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`，commit `2a128bf0c8461fae91d2b424d9168ddf205bb11b`。

| 指标 | 结果 |
|---|---:|
| 正式 `build_index()` 文件数 | 1,575 |
| Go symbols | 10,922 |
| Go relationships | 69,231 |
| Go calls | 48,985 |
| resolved / unresolved calls | 8,212 / 40,773 |
| unresolved ratio | **83.236%** |
| unqualified/package selector → method/interface-method | **0** |
| cross-language target | **0** |
| non-callable target | **0** |
| external/stdlib import → local | **0** |
| external selector → local | **0** |
| duplicate relationship ID | **0** |
| `analysis_fingerprint` | 64 hex，存在 |
| `go-lexer-fallback` record | 10,922 symbols / 69,231 relationships |
| `go-semantic-gopls` record | disabled、non-implicit、0 fabricated records |
| full golden test elapsed | 7.861s |

resolved 数字比上一轮增加，是因为显式 receiver/parameter type evidence 可以安全连接 method；它不是恢复全局同名猜测。83.236% unresolved 仍放在产品边界中，体现 precision-first：没有类型证明就不连边。

## 30 文件 gopls 差分

采样规则：对默认 scanner 纳入的 Go 文件按绝对路径排序，取 `round(i * (N-1) / 29)`，`i=0..29`。本机 `gopls v0.21.1`。

```text
sample files: 30
gopls declarations: 451
fallback declarations: 451
matched occurrences: 451
missing: 0
extra: 0
elapsed: 24.680s（自动化 golden test）
```

identity 示例格式：

```text
internal/changewatch/router.go:34:2-34:13 interface-method ImpactApplier.ApplyImpact
```

这项 100% 只证明固定样本的 declaration catalog，不证明 fallback call graph 具有 gopls 语义精度。

## 性能与 unresolved 边界

resolver 预先构建：

- `(directory, package, name) → package function`
- `(directory, package, receiver type, method name) → method`
- `(directory, package) → local type names`
- `source symbol → explicit typed bindings`

因此不会对每一条 selector call 重新遍历全仓 type index 或重新解析签名。SourceBridge 正式 golden build 在本机为 7.861s；没有为提高 resolved 数字引入全局 name fallback。

仍保持 unresolved 的关键边界：

- local variable assignment type inference；
- function value 的真实来源；
- generic instantiation 和 constraint method set；
- embedding/promoted method；
- interface dynamic dispatch；
- build tags、`go.work` / replace / vendor 的完整语义。

## 仍未关闭的非阻塞项

- `RelationshipRecord` schema 仍没有 column/end position；column + ordinal 已进入稳定 relationship ID，但 UI 不能直接展示精确同行 occurrence。该项需要后续 schema migration，不在本轮文件权限内。
- doc comment、`_test.go`/`Test*` 标记、field/const/var、embedding/implements/hierarchy 仍低于 SourceBridge 的教学元数据完整度。
- 若产品要宣称“语义级调用链”，必须新增用户显式启用的持久 gopls/LSP definition/reference 层，并将 edge 标成 `semantic-exact`；当前没有此宣称。

## 验证命令

```text
PYTHONPATH=src python3 -m unittest tests.test_analyzers -v
PYTHONPATH=src python3 -m unittest tests.test_indexer -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
ruff check src tests
python3 -m compileall -q src tests
```

本轮全量结果：`159 tests in 69.670s — OK`；修改范围的 ruff 与全量 compileall 均通过。

正式六仓 `examples/reference-selection` 产物由技术选型 Agent 在本 resolver 稳定后统一重生成，避免两个 Agent 同时覆盖同一路径。产物必须再运行 `repo-teacher validate`，并检查 SourceBridge `index.json` 的 fingerprint、Go records 和上述零错连门禁。
