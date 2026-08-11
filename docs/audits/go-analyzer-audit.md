# Go 代码分析器独立审计

> 审计对象：`src/repo_teacher/analyzers/go.py`、`src/repo_teacher/analyzers/__init__.py`、`tests/test_analyzers.py`、`src/repo_teacher/indexer.py` 及模块定位消费链路  
> 参考实现：SourceBridge（Tree-sitter Go）与 CodeBoarding（gopls/LSP、语义边、增量更新）  
> 真实样本：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`  
> 审计时间：2026-08-10（报告数字以审计时工作区源码为准）  
> 审计性质：只读；除本报告外没有修改产品代码或产物

## 结论

**Verdict：REQUEST CHANGES**

当前实现是一个速度不错、对顶层 Go 声明有较高召回率的“词法导航器”，但还不是可以给技术选型、模块依赖和实现流程提供可信证据的生产级 Go 语义分析器。

最重要的判断只有三点：

1. **可保留的部分**：无外部依赖、约 6 秒完成 SourceBridge 全仓混合语言索引；在 30 个 Go 文件的 gopls 对照样本中，顶层函数、方法、结构体、接口和具名类型命中 289/298，声明召回率为 **96.98%**。
2. **当前不能用于决策的部分**：通用关系解析器会把 Go 调用和 import 解析到错误语言、错误 package、非可调用类型及同名本地文件。真实全仓中，14,183 条“已解析”Go 调用至少有 1,200 条可以机械证明为错误，错误下界为 **8.46%**；589 条被解析的外部/标准库 import 全部是错误本地目标。
3. **建议的技术定位**：保留 lexer 作为快速降级扫描器；生产默认使用 **gopls 语义解析**，Tree-sitter 可作为不具备 Go toolchain 时的语法级后备。后备结果必须保持 `unresolved`，不能用全局同名匹配冒充已解析事实。

因此，本模块目前可以支撑“文件里大致有哪些顶层对象”，**不能支撑**“这个模块如何实现、调用了谁、谁依赖它、应该复用哪段代码”这类用户核心问题。

## 真实探针结果

### 全仓扫描

| 探针 | 结果 | 解读 |
|---|---:|---|
| 直接运行 Go lexer | 772 个 `.go` 文件，11,106,034 bytes，323,810 行，3.819s | 含被产品扫描器按大小排除的 1 个文件 |
| 最新 `build_index(SourceBridge)` | 1,575 文件，429,020 行，15,936,290 bytes，5.920s | 混合语言全仓；扫描完成 |
| Go analyzer 输入 | 771 个 Go 文件 | 1 个文件因 `too_large` 跳过 |
| Go symbols | 10,408 | 4,847 function；3,827 method；1,381 struct；191 type；162 interface |
| Go relationships | 63,840 | 48,770 calls；10,408 contains；4,662 import |
| 已解析 Go calls | 14,183 / 48,770（29.08%） | “解析率”不等于正确率 |
| 无 parent 的 methods | 413 / 3,827（10.79%） | receiver 类型在其他文件时无法关联 |
| lexer diagnostics | 0 | 对有效仓库正常；但语法错误覆盖不足，见 P1 |
| indexer 关系归一化 | 删除 448 个“语义相同”的重复关系，修复 0 个真实 ID collision | 其中包含同一行多次调用，实际调用点被静默合并 |

直接 lexer 的吞吐约为 **2.77 MiB/s**。性能是当前实现的明确优点，不是此次拒绝上线的原因。

### gopls 声明差分

使用本机 `gopls v0.21.1` 对 30 个确定性抽样的 SourceBridge Go 文件执行 document-symbol 对照：

- gopls 目标声明：298
- lexer 命中：289
- 声明召回率：96.98%
- 抽样内精度代理：100%（只说明这些顶层声明未观察到多报，不代表全仓语义精度）
- 漏掉的 9 个声明全部是 **interface 方法**：
  - `internal/graph/search_types.go`：`SearchSymbolsFTS`、`SearchSymbolsVector`、`UpsertSymbolEmbedding`
  - `internal/trash/types.go`：`Get`、`List`、`MoveToTrash`、`PermanentlyDelete`、`RestoreFromTrash`、`SweepExpired`

这说明 lexer 很适合做声明目录，但接口契约缺失会直接影响“模块提供了哪些能力”的讲解。

### 已解析边的机械错误下界

以下分类有重叠，去重后共有 **1,200 / 14,183（8.46%）** 条已解析 Go call 可确定为错误；这只是下界，并未验证剩余 91.54% 都正确。

| 错误类型 | 数量 | 为什么可以确定错误 |
|---|---:|---|
| 外部/标准库 selector 被连到本地符号 | 831 | 例如 `time.Now`、`os.ReadFile` 的 selector 根来自外部 import，却被连到仓库内同名方法/函数 |
| 跨 Go package 的无限定名调用 | 178 | SourceBridge 不存在 dot import；Go 无限定标识符不能直接调用另一 package 的符号 |
| 调用被连到非可调用 symbol | 211 | 目标是 `type`、`struct` 或 `interface`；常见来源是用户类型转换被词法规则当作调用 |
| Go 调用跨语言解析 | 195 | 193 条连到 TypeScript，2 条连到 Python |

具体例子：

- `cli/mcp_proxy.go` 的 `cancel` / `e.cancel` 被解析到 `web/src/app/(app)/admin/llm/profile-name-pill.tsx` 的 TypeScript `cancel`。
- `cli/password_input.go` 的 `register` 被解析到 `workers/comprehension/capabilities.py` 的 Python `ModelCapabilityRegistry.register`。
- `benchmarks/.../main.go` 的 `time.Now` 被解析到 `internal/qa/lazy_agent_synth_test.go` 的 `mockClock.Now`。
- `os.ReadFile` 被解析到 `internal/git/local.go` 的仓库内 `ReadFile`。

Go import 也存在同一问题：4,662 条 import 中有 589 条被解析为本地文件，但这些 589 条全部是标准库或外部 module。主要错误为 `context` 431 条、`errors` 136 条、`runtime` 17 条。例如 `context` 被连到 `internal/knowledge/context.go`，而不是标准库 package。

## Findings

### P0-1：通用解析器制造了“有 target_id 的错误事实”

**证据**

- `go.py:587-637` 只识别“identifier/selector 后跟 `(`”的形状，无法区分函数调用、方法调用、类型转换和泛型实例化。
- `go.py:623-633` 只对同文件的简单函数做初始解析，其余全部交给全局 resolver。
- `indexer.py:422-454` 把所有语言、所有 symbol kind 按 `name` / `qualified_name` 放进同一个索引；selector 找不到时退化为最后一段名称，全局唯一即写入 `target_id`。
- `indexer.py:455-477` 用点分段和文件 stem 解析所有语言的 import，不理解 Go module path、package、alias、标准库与外部依赖。
- `module_locator.py:408-455` 将有 `target_id` 的关系展示为 `resolved`；`module_locator.py:583-615` 又依据同一 target 将其分为 internal/inbound/outbound，并用于后续符号排名和实现 trace。

**影响**

这是 P0，不是一般精度优化。产品向用户展示的是“确定到模块和文件的实现证据”，错误 target 会污染：

- 模块内部/入站/出站依赖；
- 核心 symbol 排名；
- 实现链路与阅读顺序；
- 技术选型时对“可复用代码”的判断。

`confidence="heuristic"` 不能抵消这个问题，因为下游仍把非空 `target_id` 作为 resolved graph edge 使用。

**必须修改**

1. resolver 至少按 `language + package/module + symbol kind` 隔离；Go call 只允许指向 callable symbol。
2. Go selector 必须根据当前文件 import alias 解析；标准库/外部 module 不得退化到仓库内同名符号。
3. 无法由 gopls/类型信息证明的关系保留 `target_name`，但 `target_id=None`。
4. 禁止跨语言兜底匹配。

### P0-2：交付的 SourceBridge 索引产物没有 Go 分析结果

审计时 `examples/reference-selection/projects/sourcebridge/index.json`：

- `analysis_fingerprint` 缺失；
- 共 3,034 symbols、18,294 relationships；
- `analyzer="go-lexer"` 的 symbol 和 relationship 均为 **0**；
- 同一文件却记录了 771 个 Go 文件。

最新源码实跑会得到 10,408 个 Go symbols 和 63,840 条 Go relationships，说明示例产物是在 Go analyzer 接入前生成的。用户当前要用 SourceBridge 做参考基准，这个产物会把其核心 Go 实现完全漏掉。

**必须修改**：语义修复后重新生成、校验并发布 SourceBridge index/HTML；CI 应拒绝 fingerprint 缺失或“仓库包含受支持语言但对应 analyzer 记录为 0”的参考产物。

### P1-1：receiver 只在同文件关联，跨文件方法失去类型归属

`go.py:645-647` 的 `known_types` 是单文件字典，`go.py:535-550` 只从这个字典设置 `parent_id`。真实仓库中 413 个方法（10.79%）没有 parent。

最小复现：`p/type.go` 定义 `type Store struct{}`，`p/method.go` 定义 `func (s *Store) Save()`，结果 `Store.Save.parent_id=None`，contains 只能退回 file→method 且标为 heuristic。

这会使“ACP 模块里的 Store 有哪些方法”之类的类型级导航不完整。需要 package 级第二阶段关联；CodeBoarding 的 gopls parent chain 和 package/file-qualified identity 是更可靠的参考。

### P1-2：ID 只对完全相同文本稳定，不抗无语义行位移

- symbol ID 包含行号：`go.py:368`、`go.py:539`。在函数前插入一行注释，ID 会改变。
- relationship ID 只有 path+line，没有 column/ordinal：`go.py:261-281`。同一行 `target(); target()` 产生相同 ID。
- `indexer.py:219-253`、`indexer.py:708-722` 将这种同 ID、同字段的调用当重复边删除。SourceBridge 实跑删除了 448 个 occurrence，丢失调用点数量。

当前测试 `tests/test_analyzers.py:134-158` 只验证同一源码重复运行 ID 相同，并没有验证增量场景真正需要的稳定性。

需要把 symbol 的持久身份建立在 Go package import path、receiver、kind、qualified name 等语义键上；调用点至少保存 line、column、ordinal，并把“调用边”与“调用点列表”分开建模。

### P1-3：语法诊断与单文件故障隔离不足

`go.py:107-202` 只为未闭合注释和 literal 产生诊断；括号/花括号不匹配、缺 token 等常见语法错误通常静默返回 heuristic symbol。最小复现 `func Good(){ Target()` 会返回 `Good` symbol 和零 diagnostic。

此外，`analyzers/__init__.py:10-17` 直接调用 analyzer，`indexer.py:684-696` 的逐文件循环没有异常隔离。任一 analyzer 未预期异常会终止全仓索引。

对照 SourceBridge：

- `internal/indexer/parser.go:24-51` 将单文件 panic 降级为文件错误；
- `parser.go:53-70` 使用 context-aware Tree-sitter parse；
- `internal/indexer/indexer.go:145-185` 在 delta 循环内处理 cancellation 和单文件错误。

生产版至少要有文件级 try/diagnostic 隔离、取消点和 parser diagnostics。lexer fallback 可以容错，但必须明确标记 incomplete parse。

### P1-4：声明目录不错，但语义层缺失会形成高漏报和误报

`go.py:558-584` 丢弃 import alias、blank import、dot import 等解析所需元数据；`go.py:587-637` 没有 definition/reference/type information。最终只有 29.08% calls 被赋 target，其中仍至少 8.46% 明确错误。

这意味着不能只继续增加正则或排除词表。Go 的 package、method set、embedding、接口实现、泛型、函数值和类型转换需要语义服务。生产优先基线应采用 CodeBoarding 的 gopls 路线；Tree-sitter 适合语法抽取和降级，不应被误认为类型解析器。

### P2-1：用户需要的代码教学信息仍缺少

与 SourceBridge 的 Tree-sitter 配置相比，当前 Go 结果未提供：

- doc comment；
- `_test.go` / `Test*` 标记；
- 精确 column/range；
- interface 方法；
- package symbol；
- const/var/field；
- embedding / implements / hierarchy。

其中 doc comment、接口方法和测试关联最直接影响“项目有哪些功能、每个功能如何实现”的 HTML 教学结果，应优先于低价值语法细节。

### P2-2：增量索引只复用了文件结果，没有重证跨文件语义边

当前 indexer 会按 SHA 复用未变文件，并在全量集合上重新执行同名 resolver，这是有价值的基础；但它没有证明 changed/deleted file 边界上的语义关系仍成立。

CodeBoarding 的 `static_analyzer/incremental_orchestrator.py:36-108` 会失效 changed/deleted 文件，重新运行 LSP 并合并；`:132-213` 用 live references 验证跨边界旧边；`:216-267` 用 definition request 补回 changed file 的新 outbound edges。当前实现只覆盖了“缓存复用”，没有覆盖“语义边重验证”。

## 与参考项目的机制完整度

这里的“完整度”衡量**机制等价性**，不是复制代码比例。计分规则：完整=1、部分=0.5、缺失=0；仅对 Go analyzer 直接相关机制计分。

### SourceBridge：约 30%（中等置信）

| SourceBridge 机制 | 参考源码 | 当前状态 |
|---|---|---|
| 语言注册与路由 | `internal/indexer/languages.go:20-49` | 完整：Go 已注册到本地 dispatcher |
| Tree-sitter AST/query | `languages.go:51-76`、`parser.go:53-70` | 缺失：使用自写 lexer |
| 函数/类型/方法抽取 | `parser.go:72-88`、`:115-200` | 部分：顶层声明召回高，但漏 interface 方法与精确列 |
| receiver 捕获 | `languages.go:63-67` | 部分：能识别 receiver 名，但仅同文件建立 parent |
| import/call-site 抽取 | `parser.go:203-305` | 部分：能抽名字/行，缺 alias、column 和语义 target |
| doc comment/test 标记 | `parser.go:104-110`、`:328+` | 缺失 |
| 单文件错误隔离与取消 | `parser.go:24-58`、`indexer.go:145-185` | 缺失 |
| callable-only、scoped resolution | `indexer.go:522-583`、`:666-710` | 缺失；当前全语言/全 kind 同名兜底更不保守 |
| 文件 delta merge | `indexer.go:60-195` | 部分：有 SHA 复用，但没有等价的 per-file cancellation/error contract |
| 测试/关系专项契约 | SourceBridge indexer tests | 缺失对应真实 Go golden/differential tests |

SourceBridge 自身仍使用名字匹配做部分全局 fallback，也不等同于 gopls；它比当前 resolver 更保守，因为只索引 callable，并优先 same-file / same-package，歧义则跳过。SourceBridge symbol 使用 UUID，**不适合作为稳定 ID 设计参考**。

### CodeBoarding：约 10%（中等置信）

| CodeBoarding 机制 | 参考源码 | 当前状态 |
|---|---|---|
| gopls 生命周期、workspace ready/backpressure | `go_adapter.py:73-118` | 缺失 |
| LSP document symbols | `call_graph_builder.py:24-70`、`:151-190` | 缺失 |
| package/file/receiver qualified name | `go_adapter.py:120-151` | 部分：当前只有 receiver.name，缺 package/file identity |
| references/definitions 语义边 | `call_graph_builder.py:130-134`、edge builders | 缺失 |
| line+column call sites | `symbol_table.py:84-111`、incremental orchestrator `:187-213` | 缺失 |
| callable/non-call discrimination | edge/source inspection tests | 缺失 |
| hierarchy 与 package dependencies | `call_graph_builder.py:72-84` | 缺失 |
| gopls diagnostics | `incremental_orchestrator.py:95-98` | 缺失 |
| changed-file invalidation 与跨边界重验证 | `incremental_orchestrator.py:36-267` | 部分：有 SHA 复用，无语义重验证 |
| memory/filter/timeout controls | `go_adapter.py:153-248` | 缺失 |

其余四个参考仓库主要提供知识展示、教学、可视化或产品工作流，不是 Go parser/semantic graph 的直接基准，因此不把“未复用”计为此模块缺陷。对 Go 分析器，应明确以 SourceBridge 和 CodeBoarding 为两条实现基线。

## 测试完整度与缺口

现有 `tests/test_analyzers.py` 共 6 个测试全部通过，其中 Go 只有 3 个：基础声明/调用、相同源码的重复 ID、未闭合注释。它们能防止基本回归，但不能证明生产正确性。

上线前必须补齐以下测试：

1. **解析语义**：package-aware 同名函数、import alias、标准库/外部 module、selector、方法表达式、函数值、用户类型转换、泛型调用。
2. **类型归属**：receiver type 与 method 分处不同文件；pointer/value receiver；embedded type；interface 方法。
3. **边的安全性**：跨语言 target 恒为 0；外部/标准库 import 指向本地文件恒为 0；call target 只能是 callable；歧义不解析。
4. **调用点**：同一行两次相同调用保留两个位置；多行 selector；column 与 enclosing symbol 正确。
5. **稳定身份**：声明前插入注释/空行不改变 symbol ID；文件改名、package 改名的迁移行为有明确契约。
6. **错误与隔离**：不平衡 delimiter、截断文件、坏 UTF-8、analyzer 抛异常、取消请求；坏文件不得终止全仓。
7. **真实仓库 golden**：固定 SourceBridge 的 representative files；断言已知 interface methods、receiver parents、关键 call/import targets。
8. **gopls differential**：按固定样本比较 declaration recall、edge precision，记录阈值并在 CI 回归。
9. **性能预算**：冷启动、增量单文件、无 gopls fallback；同时测时间与峰值内存。
10. **消费链路**：错误或 unresolved edge 不得进入 module locator 的 resolved buckets、核心排名与 implementation trace。

## 生产通过门槛

完成以下条件后才建议改为 PASS：

1. Go 关系解析按语言、module/package、import alias 和 callable kind 隔离；真实 SourceBridge 上 **0 条跨语言 Go target、0 条外部/标准库 import→本地 target、0 条 conversion→callable edge**。
2. gopls 作为生产语义层，或提供等价的 definition/reference/type-checking 能力；Tree-sitter/lexer fallback 的未证明关系保持 unresolved。
3. package 内跨文件 receiver parent 完整；30 文件 gopls 声明样本至少覆盖当前 298/298，并纳入 interface methods。
4. symbol ID 不因声明前插入注释/空行而改变；call-site 有 column/ordinal，重复调用点不丢失。
5. 语法 diagnostics、单文件异常隔离和取消机制具备自动测试。
6. 增量更新对 changed/deleted file 的跨边界边做重新验证，不复用无法证明的旧 target。
7. SourceBridge 全仓 golden 与 gopls differential 测试进入 CI，并设定精度/召回/性能阈值。
8. 重新生成 `examples/reference-selection/projects/sourcebridge/index.json` 及对应 HTML；fingerprint 存在、Go analyzer records 非零、产物校验通过。

建议把精度契约分成三层展示：`semantic-exact`（gopls definition/reference 已证明）、`syntax-exact`（Tree-sitter 只证明语法范围）、`heuristic-unresolved`（lexer 只给导航候选）。这样既能保留当前速度优势，也不会把候选关系包装成技术选型证据。

## 验证记录与限制

已执行：

```text
PYTHONPATH=src python3 -m unittest tests.test_analyzers -v
# 6/6 PASS；其中 Go 3/3 PASS

PYTHONPATH=src python3 <SourceBridge 全仓 build_index/关系审计探针>
# 1,575 files；13,442 symbols；81,901 relationships；5.920s

gopls version
# golang.org/x/tools/gopls v0.21.1

<30 文件 gopls symbols 差分探针>
# 289/298，96.98% declaration recall
```

尝试执行 SourceBridge 自身 `go test ./internal/indexer`，但本机安装存在 Go stdlib/compiler 版本不一致：stdlib 为 `go1.22.4`，`go tool` 为 `go1.26.3`，因此参考仓库测试在编译前失败。这是本次参考验证限制，不归因于被审计产品。SourceBridge 源码、测试机制、本地 analyzer 测试、gopls 差分和真实全仓索引探针均已完成。

**最终结论：REQUEST CHANGES。**
