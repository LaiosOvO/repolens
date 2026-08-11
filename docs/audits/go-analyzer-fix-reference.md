# Go analyzer 修复与参考实现对应关系

> 范围：`src/repo_teacher/analyzers/go.py`、`go_semantic.py`、分析器隔离边界及专项测试  
> 基准：SourceBridge Tree-sitter 索引器、CodeBoarding gopls/LSP 语义图  
> 状态：修复已实现并自测；必须经过独立 Agent 复审后才能标记 PASS

## 先看结论

本轮将 Go 分析器从“全语言同名猜测”收紧为两层能力：

1. 默认的零依赖 lexer 只输出可由语法证明的声明、接口方法、调用位置和 import alias；项目级 resolver 只在同 package 或已由 `go.mod` 证明的本地 import 中解析 callable target。
2. `gopls` 是显式可选的差分/定义/诊断适配器，不自动下载、不隐式运行；没有 gopls 时保持保守 fallback，无法证明的 selector 保持 `target_id=None`。

因此，外部库、标准库、跨语言同名符号和非 callable 类型不再被包装为“已解析调用”。代价是默认 fallback 的 unresolved 比例较高；这是有意的精度优先策略，不是把候选伪装成事实。

## 审计项与实现证据

| 审计要求 | 本地实现 | 结果 |
|---|---|---|
| package/import-aware、语言隔离、callable-only | `resolve_go_relationships()` 仅索引 `analyzer.startswith("go-")` 的 symbol；call target kind 限定 function/method/interface-method；本地 import 必须匹配 `go.mod` module path | 已实现 |
| 标准库/第三方 selector 保持 unresolved | import alias 被语法关系保存；只有 alias 指向当前仓库 Go module 才可继续解析 | 已实现 |
| receiver 跨文件同 package 关联 | 项目级 pass 以 directory + package + receiver type 建立 parent，并修复 contains source | 已实现 |
| interface method | interface body 方法成为 `interface-method` symbol，parent 指向 interface | 已实现 |
| stable symbol ID | ID 使用 path + package + qualified name + kind + normalized signature，不含 line；无效重复声明使用确定性 occurrence disambiguator | 已实现 |
| 同行重复调用 | relationship ID 包含 line + column + ordinal；两个 `target(); target()` 均保留 | 已实现 |
| syntax diagnostic | 未闭合/错配 delimiter、comment、literal、缺 package 均产生 diagnostic | 已实现 |
| 单文件错误隔离 | `analyze_file()` 捕获某一个 analyzer 的异常并返回 `analyzer-file-failure`，不抛到全仓循环 | 已实现 |
| fallback 标识 | analyzer 明确标记 `go-lexer-fallback[package=…]`；未证明关系 confidence 为 `heuristic-unresolved` | 已实现 |
| 可选 gopls | `GoplsAdapter` 提供 availability、document symbols、definition、diagnostics 和 differential；只有显式构造/调用才启动子进程 | 已实现 |

## SourceBridge：采用了什么

参考源码：

- `repo/sourcebridge/internal/indexer/parser.go`：语法声明、method receiver、import、call-site、doc/test 标记，以及单文件 panic 降级。
- `repo/sourcebridge/internal/indexer/languages.go`：Go Tree-sitter query 和语言路由。
- `repo/sourcebridge/internal/indexer/indexer.go`：callable-only name index、same-file/same-package 优先、歧义不连边。

已采用的机制：

- 明确的 Go analyzer 路由和 fallback 身份；
- 顶层 function/method/type/struct/interface 与 interface method 的声明目录；
- import 和 call-site 分开建模；
- receiver/type parent；
- callable-only、package-scoped、ambiguous → unresolved；
- 单文件 failure isolation；
- call occurrence 不做“caller-target”级语义去重。

没有采用的机制：

- 没有复制 SourceBridge 的 AGPL Tree-sitter 代码，也没有新增 Tree-sitter/cgo 依赖；当前 lexer 是 clean-room 零依赖 fallback。
- 暂未抽取 doc comment、field/const/var、embedding、test marker。
- SourceBridge 使用随机 UUID，不适合增量稳定身份；本实现改用语义键 stable ID。
- SourceBridge 最后的 unambiguous-global fallback 未采用，因为它仍可能跨 Go package 错连。

## CodeBoarding：采用了什么

参考源码：

- `repo/codeboarding/static_analyzer/engine/adapters/go_adapter.py`：gopls toolchain 前置条件、workspace readiness/backpressure、qualified receiver、内存/超时控制。
- `repo/codeboarding/static_analyzer/engine/call_graph_builder.py`：document symbols、definition/reference edge、hierarchy 和 package dependencies。
- `repo/codeboarding/static_analyzer/engine/symbol_table.py`：行列位置和符号表。
- `repo/codeboarding/static_analyzer/incremental_orchestrator.py`：changed/deleted file 失效与跨边界边重验证。

已采用的机制：

- gopls 作为语义真值和差分基准，而不是继续扩大全局正则；
- package/file/receiver 参与身份与解析；
- gopls command 有可用性、timeout、失败显式化；
- document-symbol 差分覆盖 interface methods；
- definition 和 diagnostics 的显式调用接口。

尚未采用的机制：

- 当前 `GoplsAdapter` 是有界 command adapter，不是持久 `gopls serve` LSP client；没有 workspace progress、didOpen backpressure、references batching、server recycler。
- gopls definition 尚未自动替换 fallback graph edge；因此 fallback 的 selector 不会冒充 semantic-exact。
- 没有 hierarchy/implements/embedding/package dependency 图。
- 没有把 gopls 的 changed/deleted-file semantic revalidation 接进增量索引。

生产方向应是：保留当前 lexer 作为快速、无 toolchain 的声明目录；需要“谁调用谁”的可信技术选型证据时，显式启用持久 gopls LSP 层，并将其边标为 `semantic-exact`。

## SourceBridge 全仓复测

测试仓库：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`。扫描器按产品默认大小限制输入 771 个 Go 文件。

| 指标 | 结果 |
|---|---:|
| Go bytes / lines | 8,939,953 / 255,478 |
| symbols | 10,922 |
| function / method / interface-method | 4,847 / 3,827 / 514 |
| relationships / calls / imports | 69,231 / 48,985 / 4,662 |
| resolved / unresolved calls | 6,974 / 42,011 |
| unresolved call ratio | 85.763% |
| receiver methods without parent | 0 |
| cross-language Go targets | 0 |
| non-callable Go call targets | 0 |
| external/stdlib import → local target | 0 |
| external/stdlib selector → local target | 0 |
| scan / analyze / resolve / total | 1.240s / 2.684s / 0.310s / 4.235s |

`gopls v0.21.1` 的确定性 30 文件 spread sample 差分：342 个目标声明，fallback 命中 342，声明召回 **100%**；耗时 26.648s。该数字只证明样本的声明目录，不证明 fallback 调用边具有 gopls 语义精度。

## 集成约束与剩余风险

项目级 resolver 必须在全局 resolver 前调用：

```python
resolve_go_relationships(relationships, symbols, scan.files, project_root=root)
```

而后全局 name-only resolver 必须跳过 `analyzer.startswith("go-")` 的 `calls` / `import`。否则旧 resolver 会再次污染已经被保守清空的 unresolved edge。这是正式 index/HTML 能否满足“机械错误为 0”的必要集成条件。

剩余风险：

- fallback 的 85.763% unresolved call 不会形成错误结论，但教学链路较稀；需要 gopls 才能安全补全 receiver、function value、generic、embedding 和 interface dispatch。
- lexer 不建模 build tags、Go workspace replace、vendor 和多 module replace 指令；它只通过每个 `go.mod` 的 module clause 证明仓库内 import。
- stable ID 在 signature 改变时按契约改变；文件重命名也改变。跨重命名迁移需要上层 rename detection。
- `RelationshipRecord` 当前没有独立 column 字段；column/ordinal 已进入 ID，后续 schema 应将列位置作为一等字段供 UI 展示。
- 本轮没有修改 indexer/CLI/report；正式产物重生成与 fingerprint 验证由集成任务完成。

## 验证命令

```text
PYTHONPATH=src python3 -m unittest tests.test_analyzers -v
python3 -m compileall -q src/repo_teacher/analyzers tests/test_analyzers.py
ruff check src/repo_teacher/analyzers tests/test_analyzers.py
```

以上专项测试通过；最终 verdict 仍以独立审计 Agent 的复审为准。
