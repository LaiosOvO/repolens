# Go analyzer 第二次独立复审

> 审计对象：`src/repo_teacher/analyzers/go.py`、`go_semantic.py`、`analyzers/__init__.py`、`src/repo_teacher/indexer.py` 的 Go resolver 集成、`tests/test_analyzers.py`  
> 对照材料：`docs/audits/go-analyzer-audit.md`、`docs/audits/go-analyzer-fix-reference.md`  
> 参考实现：SourceBridge Tree-sitter 索引器、CodeBoarding gopls/LSP 语义图  
> 真实仓库：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`  
> 审计时间：2026-08-10；数字以本次重放时的工作区为准  
> 审计性质：独立、只读；除本报告外未修改产品代码或产物

## 结论

**Verdict：REQUEST CHANGES**

本轮修复是实质进步：跨语言 target、非 callable target、外部/标准库 import 连到本地、外部 selector 连到本地均已降为 0；receiver 跨文件 parent、interface method、抗注释行位移的 ID、同行重复调用点、delimiter diagnostic 和单文件故障隔离也都有自动化证据。默认索引不会隐式运行或下载 gopls。

但是还有两个会直接污染用户判断的阻塞项：

1. SourceBridge 全仓仍有 **23 条可机械证明为错误的已解析 call target**；解析器把无限定调用/包 selector 的候选集扩大到 method、interface-method，而这两种调用形状只能安全解析到 package function。
2. 用户实际会打开的 SourceBridge 参考产物仍是旧版：`examples/reference-selection/projects/sourcebridge/index.json` 没有 fingerprint，Go symbol/relationship 都是 0。

因此，当前源码可作为“精度优先的快速 fallback”继续修复，但不能将已发布的参考 HTML/index 或当前全部 `syntax-scoped` 边当作生产级实现事实。

## SourceBridge 全仓重放

### 主结果

| 指标 | 结果 |
|---|---:|
| 扫描到的 Go 文件 | 771 |
| Go symbols | 10,922 |
| function / method / interface-method | 4,847 / 3,827 / 514 |
| Go relationships | 69,231 |
| calls / contains / import / alias | 48,985 / 10,922 / 4,662 / 4,662 |
| resolved / unresolved calls | 6,974 / 42,011 |
| unresolved call ratio | **85.763%** |
| resolved / unresolved imports | 1,250 / 3,412 |
| 无 parent 的 receiver method | **0** |
| 跨语言 Go call target | **0** |
| 指向非 callable symbol 的 Go call | **0** |
| 外部/标准库 import → 本地 | **0** |
| 外部/标准库 selector → 本地 | **0** |
| relationship ID 重复 | **0** |
| 已解析的无限定/包 selector → method | **23（错误）** |

直接执行 scanner → Go analyzer → project resolver 的时间为：扫描 1.286s，分析 2.761s，解析 0.338s，合计 **4.385s**。完整 `build_index` 重放为约 8–11s（还包含两次 tree manifest、其他语言、feature/artifact 构建与完整性检查）。性能足够支撑 fallback，不是本次拒绝上线的原因。

### 30 文件 gopls 差分

采样方法是可复核的：将默认 1MB 限制内的 SourceBridge `.go` 文件按相对路径排序，对 `i=0..29` 选取 `round(i * (N-1) / 29)`。本机 `gopls v0.21.1`。

- 现有 `GoplsAdapter.differential()` 返回：409 expected / 409 observed / 409 matched，recall 100%。
- 用 `(line, leaf-name)` 保留每个声明 occurrence 重算：**451 / 451 matched，recall 100%**。
- 两者差 42 不是声明丢失，而是现有 adapter 用名称 `set` 将同名方法/声明折叠了。所以本次真实样本的声明召回仍然是 100%，但 adapter 当前的 `gopls_count` 不是“声明数”，不能用来设置可信的回归阈值。

## 逐项审计

| 要求 | 证据 | 结论 |
|---|---|---|
| 跨语言 target=0 | 全仓 resolved Go calls 按 target analyzer 重放 | PASS |
| 非 callable target=0 | target kind 限定 function/method/interface-method，全仓统计 0 | PASS，但 callable 不等于“这个调用形状可调”，见 P0-1 |
| 外部/标准库 import→本地=0 | `go.mod` module path 证明后才解析；全仓 0 | PASS |
| 外部 selector→本地=0 | import alias + local module gate；全仓 0 | PASS |
| receiver 跨文件 | package directory + receiver type 的 project pass；3,827 methods 均有 parent | PASS |
| interface methods | 一等 `interface-method` symbol；全仓 514 | PASS |
| stable ID 抗注释行位移 | ID 不含 line；专项测试通过 | PASS |
| 同行重复 call occurrence | relationship ID 包含 column + ordinal；专项测试与全仓 ID 唯一性通过 | PASS |
| diagnostic / per-file isolation | delimiter/comment/literal/package diagnostics + dispatcher 异常边界；专项测试通过 | PASS |
| gopls 可选、非隐式依赖 | 主 indexer 不 import/invoke `go_semantic`；缺少 gopls 时返回 unavailable | PASS |
| 30 文件差分可复核 | 确定性 spread sample 可重放 | PARTIAL；现有指标折叠 occurrence/kind/parent |
| relationship ID 唯一 | 全仓 69,231 Go relationships，重复 ID=0 | PASS |
| 85% unresolved 风险诚实 | fix reference 明确写 85.763%、说明需要 gopls 才能补全 | PASS |
| incremental 跨边界边 | 未变 main.go 复用 + helper.go 删除后，旧 call target 被清空 | PASS（fallback 语法边） |

## Findings

### P0-1：无限定/包 selector 调用被错连到 method

**证据**

- `go.py:1013-1023` 将 function、method、interface-method 全部放入同一 `callable_index`。
- `go.py:1095-1128` 对无限定 `name()` 和已证明的包 selector `pkg.Name()` 使用这个混合索引，最后只检查 `_CALLABLE_KINDS`。
- 但这两种形状的静态 package 目标只能是 function；method 需要 receiver，interface method 需要动态 dispatch，都不能由现有信息证明。

SourceBridge 全仓有 23 条错边，例如：

- `internal/api/graphql/knowledge_job.go:265` 的函数参数 `run(runCtx, rt)` 被连到 `knowledge_stream_driver.go` 的 `streamProgressDriver.run` method。
- `internal/api/graphql/llm_sync.go:50` 的函数参数 `run(noopRuntime{})` 同样被连到上述 method。
- `gen/go/common/v1/version_grpc.pb.go:102` 的 interface assertion 中 `testEmbeddedByValue()` 被连到 `UnimplementedVersionServiceServer.testEmbeddedByValue` method；同类 protobuf 生成文件共多处。
- `internal/db/livingwiki_repo_settings_store.go:271` 的包级 helper `decryptAPIKey(...)` 被连到 `SurrealLLMConfigStore.decryptAPIKey` method。

**影响**

这些边有 `target_id` 且 `confidence="syntax-scoped"`，下游会把它们当作 resolved internal/inbound/outbound 依赖。对“这个功能底层怎么实现”的产品目标而言，这是事实性数据污染，因此定为 P0。

**必须修复**

- 对现有 fallback，无限定和 package selector 候选只允许 `kind == "function"`。
- receiver method call 保持 unresolved，直到 gopls definition 或类型信息证明。
- 补充函数参数/局部变量 shadowing 测试；`run func(...); run()` 不得连到同 package method/function。
- 将上述 23 条机械检查固化为 SourceBridge golden gate。

### P0-2：已交付的 SourceBridge 产物仍然完全没有 Go 结果

`examples/reference-selection/projects/sourcebridge/index.json` 在复审时：

- 文件大小 8,237,109 bytes；
- `analysis_fingerprint` 缺失；
- analyzer 以 `go-` 开头的 symbol = **0**；
- analyzer 以 `go-` 开头的 relationship = **0**。

当前源码实跑是 10,922 Go symbols / 69,231 Go relationships，说明用户会查看的基准产物尚未重生成。SourceBridge 的核心索引/图能力大量在 Go 中，所以这不是文档新旧问题，而是产品输出缺失。

**必须修复**：在 P0-1 修复后重生成 SourceBridge index/HTML，运行 `validate`，并在发布 gate 中检查 fingerprint 存在、已扫描受支持语言的 analyzer 记录非 0。

### P1-1：gopls 差分将声明折叠成 leaf-name set，无法作为 CI 精度/召回 gate

`go_semantic.py:157-178` 只取 `raw.rsplit(".", 1)[-1]`，然后用两个 `set[str]` 做差集。这会同时丢掉：

- 同一文件中多个 receiver/interface 的同名 method occurrence；
- receiver / interface parent；
- declaration kind；
- line/column/range；
- 同名但类型不同的误匹配。

本次 30 文件样本中，adapter 的 409 实际对应 451 个可定位声明。虽然本次用 `(line, name)` 交叉检查后仍是 451/451，但现有 API 可以在漏掉一个同名 method 时仍报 100%。

**必须修复**：使用 declaration occurrence 键（至少 path + line + column + normalized qualified parent + kind），返回可审核的 per-file sample manifest 和 mismatch 位置，再将确定性 30 文件差分固化到测试/发布 gate。

### P1-2：85.763% unresolved 是诚实的，但仍意味着默认产品不具备 CodeBoarding 的语义边能力

这一点不是“应当继续写更多正则”。当前 `GoplsAdapter` 是显式 command probe，它的 definition/diagnostic 方法没有进入 indexer、没有生成 `semantic-exact` 边；主路径只是保守 fallback。这个取舍已在 fix reference 中说明，因此不将“可选 gopls”本身判为 P0；但在宣称能提供可信的“底层实现链”之前，必须有一条用户显式启用的持久 gopls/LSP 语义层，或把 UI 功能边界限定为“声明目录 + 未证明候选”。

### P1-3：关键生产门禁仍只有人工探针，没有进入测试

`tests/test_analyzers.py` 现有 13 个测试，Go 专项已覆盖基本声明、interface method、ID 行位移、同行 occurrence、外部 import/selector、receiver parent、diagnostic、isolation 和 gopls absence。但以下仍没有固化：

- 跨语言 target 端到端为 0；
- 无限定/包 selector 不得解析到 method/interface-method；
- 参数/局部变量 shadowing；
- SourceBridge 真实仓库 golden 数据与错边 gate；
- 30 文件 occurrence-aware gopls 差分；
- changed/deleted Go 文件后的跨边界 target 清理；
- 已交付参考 index 的 fingerprint/analyzer 完整性。

这些是本次“人工重放可通过、下次改动可能回归”的主要原因。

### P2-1：column/ordinal 只进入 ID，没有进入图 schema

`go.py:398-428` 使用 column/ordinal 保证同行调用关系 ID 唯一，这已解决调用点丢失。但 `models.py:77-87` 的 `RelationshipRecord` 仍只有 line，所以 UI/消费者无法显示或复核同行的精确位置。建议在下一次 schema 升级中添加 column/end position/occurrence，而不是要求消费者反推 hash ID。

### P2-2：语法教学元数据仍落后于 SourceBridge

当前已补齐 interface method 和 receiver parent，但仍没有 doc comment、`_test.go`/`Test*` 标记、field/const/var、embedding/implements/hierarchy。这些不阻塞“快速声明目录”，但 doc/test/hierarchy 会直接影响项目教学和技术选型的解释质量，应在扩展更多语法细节之前优先。

### P2-3：显式传入 PATH 命令名 `"gopls"` 会被判定为 unavailable

`go_semantic.py:62-68` 只对默认 `None` 调用 `shutil.which`；如果调用者显式传入 `GoplsAdapter("gopls")`，`Path("gopls").is_file()` 通常为 false。建议对无路径分隔符的显式 executable 同样用 `shutil.which`，且补测试。

## 与两个参考项目的机制完整度

评分表达“机制等价性”，不是复制代码比例。

### SourceBridge Tree-sitter：约 65%（中等置信）

| 机制 | 参考源码 | 当前状态 |
|---|---|---|
| Go 语言注册/路由 | `internal/indexer/languages.go:37-55` | 完整 |
| Tree-sitter AST/query | `languages.go:51-74`、`parser.go:53-70` | 缺失；clean-room lexer fallback |
| function/type/method/interface method 目录 | `parser.go:72-100`、`:115-200` | 大部分完整；30 文件 occurrence 样本 451/451 |
| receiver 捕获与跨文件 parent | `languages.go:63-67` | 完整；本地 project pass 比参考 parser 更明确 |
| import alias/call occurrence | `parser.go:203-305` | 部分；有 alias/column-in-ID，没有 schema column |
| doc comment/test marker | `parser.go:329+`、`languages.go:74` | 缺失 |
| 单文件 panic/error 隔离 | `parser.go:24-51` | 完整；Python dispatcher boundary |
| callable/scoped resolution | `indexer.go` 同文件/同 package 优先与歧义跳过 | 部分；语言/package/import 隔离已有，但 method 候选仍产生 23 错边 |
| 增量复用/边重解析 | SourceBridge delta loop | 部分；SHA 复用 + 全局 fallback 重解析已证明，无 semantic reference |
| 真实仓库 golden/交付产物 gate | SourceBridge indexer tests | 缺失；当前产物仍无 Go records |

### CodeBoarding gopls/LSP：约 25%（中等置信）

| 机制 | 参考源码 | 当前状态 |
|---|---|---|
| gopls 前置检查/可选命令边界 | `go_adapter.py:100-118` | 部分；有 availability/timeout，无 Go toolchain/workspace readiness |
| 持久 `gopls serve` 生命周期 | `go_adapter.py:73-100` | 缺失 |
| document symbols | `call_graph_builder.py:151-190` | 部分；command probe 可用，差分结果折叠 occurrence |
| qualified package/file/receiver identity | `go_adapter.py:120-151` | 部分；fallback 有 package/receiver，gopls 差分丢 parent |
| definition/reference 语义边 | call graph builders / reference warmup | 缺失主路径；只有未接入的 `definition()` command |
| diagnostics | `incremental_orchestrator.py:90-98` | 部分；显式 command API，未接入 index |
| line+column 调用点 | `symbol_table.py` 定位字段 | 部分；仅进 ID |
| hierarchy/package dependencies | `call_graph_builder.py` | 缺失 |
| changed/deleted 语义边重证 | `incremental_orchestrator.py:36-267` | fallback 语法边可重解析；LSP definition/reference 重证缺失 |
| backpressure/filter/memory/recycler | `go_adapter.py:153-248` | 缺失 |

## 修复后的复审门槛

下列条件全部满足后才建议 PASS：

1. SourceBridge 全仓中无限定/包 selector → method/interface-method 为 0；函数参数/局部变量 shadowing 保持 unresolved。
2. 继续保持跨语言、非 callable、外部 import、外部 selector 四项为 0。
3. gopls differential 改为 occurrence-aware、kind/parent/position-aware；固定 30 文件 sample manifest 和 mismatch 证据。
4. 把上述机械检查、incremental deleted-file 重解析和 SourceBridge golden 纳入自动化测试。
5. 重生成 SourceBridge index/HTML；fingerprint 存在、Go analyzer records 非 0、`validate` 通过。
6. 如果产品宣称“语义级调用链”，需显式启用 gopls/LSP definition/reference 层并区分 `semantic-exact` 与 `syntax-scoped`；否则 UI 必须把 85.763% unresolved 与 fallback 边界置于首屏。

## 验证记录

```text
PYTHONPATH=src python3 -m unittest tests.test_analyzers -v
# 13/13 PASS

python3 -m compileall -q src/repo_teacher/analyzers tests/test_analyzers.py
# PASS

ruff check src/repo_teacher/analyzers tests/test_analyzers.py
# PASS

<SourceBridge scanner -> Go analyze_file -> resolve_go_relationships>
# 771 Go files; 10,922 symbols; 69,231 relationships; 4.385s
# cross-language=0; non-callable=0; external import->local=0;
# external selector->local=0; relationship duplicate ID=0;
# unqualified/package selector->method=23 (blocking)

<deterministic 30-file gopls spread differential>
# adapter leaf-name sets: 409/409
# occurrence-aware (line,name): 451/451

<incremental deleted-helper probe>
# unchanged main.go reused; deleted helper.go;
# old resolved call target cleared to None
```

## 残余风险

- 即使 P0-1 修复，零依赖 lexer 仍无法证明 local/parameter shadowing、function value、generic instantiation、embedding 和 interface dispatch；高精度边仍需 gopls。
- unresolved 85.763% 是安全取舍，但会使默认教学链较稀疏；不应用“解析失败”后的全局同名回退来提高数字。
- build tags、`go.work`、`replace`、vendor、multi-module 的完整语义仍没有建模。
- symbol ID 对无关行位移稳定，但 signature 改变、文件改名、package 改名会按契约改变；跨重命名迁移仍需上层 rename detection。
- 本次没有将 SourceBridge 自身 Go tests 作为通过证据；参考仓库之前已记录本机 stdlib/compiler 版本不一致，与被审产品无关。

**最终结论：REQUEST CHANGES。**
