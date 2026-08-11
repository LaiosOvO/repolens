# 核心索引生产链最终阻断修复记录

修复日期：2026-08-10  
修复范围：`scanner.py`、`snapshot.py`、`indexer.py`、`validation.py`、
`persistence.py`、`cli.py`、`models.py` 及对应核心回归测试  
上游问题：`core-index-final-reaudit.md`、
`core-index-final-architect-lane.md`

## 状态先行

本轮实现与验证已经完成，当前状态是 **Ready for independent re-audit**。

本文不签发 PASS，也不替代独立复审。它只记录修了什么、用什么反例验证、
真实 SourceBridge 的结果，以及仍然存在的信任边界。

## 一、用户可见结果

1. `index`、`explain`、`compare` 不再依次覆盖 JSON/HTML。一次命令的全部产物
   先进入唯一、不可变 generation；全部写完、解析、校验和 `fsync` 后，只交换
   一个 `current` 指针。
2. `output/index.json` 与 `output/index.html` 都通过 `current` 指向同一个 generation。
   `file://.../index.html` 仍可直接打开，不需要本地 HTTP 服务。
3. 任一点写入、readback、validate 或发布前源码复验失败，命令返回非 0，旧
   `current` 不变；不会再出现“新 JSON + 旧 HTML”。
4. partial、truncated、来源已变化或语义闭包失败的索引不会发布，也不会进入
   warm baseline。
5. warm baseline 的语义校验按 path 预分组，复杂度保持为 O(总记录数)，不再对
   每个文件反复扫描全图。

## 二、跨文件 generation transaction

### 磁盘布局

```text
output/
  current -> .repo-teacher-generations/<generation_id>
  index.json -> current/index.json
  index.html -> current/index.html
  modules -> current/modules
  projects -> current/projects
  technology-selection.json -> current/technology-selection.json
  technology-selection.html -> current/technology-selection.html
  .repo-teacher-generations/
    <generation_id>/
      generation-manifest.json
      ...本次命令的全部 JSON / HTML / 项目子报告
```

每个 JSON 带同一个 `generation_id`；每个 HTML 带
`repo-teacher-generation` meta。manifest v2 对每个 artifact 同时记录字节长度和
SHA-256。reader 会验证：

- `current` 只能指向固定 generation namespace；
- generation 目录和 artifact 不得是 symlink/FIFO/非 regular file；
- manifest artifact 集合必须与磁盘集合完全相等；
- 每个 artifact 有界读取，size、digest、内嵌 generation ID 全部一致；
- 读取前后 `current` 必须仍指向同一个 generation。

发布路径通过永久 `flock` 串行化 writer。staging crash、第二个 artifact 写失败、
legacy flat-file 冲突、缺失 `current`、artifact tamper、`os._exit` 后重新获锁均有
专项回归。旧 generation 不会自动删除，故故障证据和旧报告仍可追溯。

`explain` generation 现在也包含完整 `index.html`，不会因切换到 module 报告而让
稳定入口 `output/index.html` 变成断链。

### 保留策略边界

generation 当前是 append-only，产品代码没有自动 GC。这样避免清理器误删仍被
reader 或审计引用的 generation，但长时间运行会增长磁盘占用。后续如增加保留
策略，必须在独立 lock 下按“非 current、无 reader lease、保留审计窗口”删除，
不能在本事务中顺手清理。

## 三、validator 与 baseline 语义闭包

### analyzer 主记录

- symbol ID 必须位于 `symbol_<16hex>` namespace，并满足 Python/JS 或 Go 的稳定
  identity 合同；symbol kind 和 analyzer 使用显式白名单。
- relationship ID 必须位于 `rel_<16hex>` namespace；kind、analyzer、endpoint
  类型、path、line 与稳定 ID 合同闭合。
- Go 的真实 `go-import-alias` 被加入**显式**合同，而不是放宽为任意字符串：它
  必须来自 Go analyzer、以 file 为 source、`target_id=None`、confidence 为
  `syntax-exact`，且是 `alias=module` 形状。邻近伪 kind 仍被拒绝。
- 每个文件保存 `analysis_sha256`，覆盖该 path 的完整 symbol/relationship 语义。
  Python 还会对当前源码重新运行 analyzer，并按生产链相同的去重和字段感知脱敏
  规则比较本地语义。

### 派生产物

`derived_sha256` 覆盖 modules、reading path、features、evidence、tutorials、
codemaps、coverage 与 stats。validator 会重新生成 teaching artifacts、modules、
reading path，并核对所有计数。只重算最外层 checksum 的 tutorial/codemap/stats
伪造不能通过。

### warm baseline

baseline 在 hydration 前验证完整 checksum、stable ID、端点、每文件 analyzer
digest 和 derived digest。records 预先按 path 分组；synthetic 24-file 回归观察到
每次 digest 只收到该文件的 `(1 symbol, 1 relationship)`，总 48 次，而不是
24 次扫描全图。`_file_analysis_digest` 内每条 dataclass 也只 materialize 一次。

旧反例（错误 symbol kind、凭空 call edge、伪 tutorial）即使重算外层 checksum，
也会得到 `baseline_status=rejected`、`reused_files=0`，不会污染 disk warm。

## 四、secret 与结构数据不互相破坏

持久化脱敏覆盖 Anthropic、AWS、GitLab、Slack、GitHub、JWT、Bearer、private key、
credential URL 与 generic token assignment。source snippet、signature、message、
remote 等人类文本字段执行 fail-closed assignment 脱敏；所有字符串仍执行 opaque
token family 脱敏。

关键修复是：assignment 规则不再无差别改写 graph identity 字段。旧实现会把合法
Go import alias：

```text
credentials=github.com/sourcebridge/sourcebridge/internal/livingwiki/credentials
```

错误改成 `credentials=[REDACTED]`，造成 cold/warm 图不一致。本轮字段感知策略既
不落盘真实 secret，也保持 alias、path、target_name 等结构语义稳定。专项 secret
corpus 和真实 SourceBridge cold/warm 都验证了这两条性质。

## 五、scanner、manifest 与非 Git 发布门

- `capture_tree_manifest()` 与主 scanner 使用同一 `max_entries`、deadline、cancel
  预算；walk/lstat/resolve 错误 fail closed。
- symlink 检查、stat 和 open 均在异常边界内；`Path.stat`/`is_symlink` 的
  `PermissionError` 不再逃逸整个扫描器。
- regular file 使用 `O_NOFOLLOW | O_NONBLOCK`，读取上限同时受单文件与总字节预算
  控制；stat 后增长也最多读取 budget + 1 字节。FIFO 不阻塞。
- final full-tree manifest 移到最后一次 snapshot 之后；CLI 在 `current` 切换前再做
  一次完整 `validate_index`，注入“最后 snapshot 后新增文件”会返回非 0且不发布。
- validation 自身若扫描/manifest 失败，会返回 `validation-scan-partial`，而不是抛出
  未结构化异常或继续签发 valid。

## 六、真实 SourceBridge 证据

固定仓库：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`  
HEAD：`2a128bf0c8461fae91d2b424d9168ddf205bb11b`  
工作树状态：`D LICENSE`（用户既有删除，本轮未恢复、未修改）  
最终全新输出：`/tmp/repo-teacher-sourcebridge-final.xE4KOZ`

| 场景 | wall | max RSS | files | reused | reanalyzed | error diagnostics |
|---|---:|---:|---:|---:|---:|---:|
| fresh cold CLI | 36.11s | 922,435,584 B | 1,575 | 0 | 1,575 | 0 |
| disk warm CLI | 33.48s | 845,938,688 B | 1,575 | 1,575 | 0 | 0 |

cold 与 disk warm 的十组核心/派生集合逐项相等：

```text
files 1575, symbols 13956, relationships 91119, modules 21,
features 8, evidence 40, tutorials 8, codemaps 8, coverage 8,
reading_path 12
```

### external selector 探针

探针定义：对 resolved Go `calls`，若 `target_name` 是 `alias.member`，alias 来自
同文件 `go-import-alias`，且 imported module 不等于
`github.com/sourcebridge/sourcebridge` 或其子包，则记为 unsafe external selector
target。

修复前 cold generation 曾稳定出现 16 条，前五条为：

1. `rel_c2ae52771ffe53df`，`cli/serve.go:738`，
   `credentials.NewResolverBroker` -> `symbol_3ed82239bc900ca9`。
2. `rel_2fbeb19734806356`，`internal/api/graphql/resolver.go:208`，同 target。
3. `rel_c4b9606bd47b7d30`，`internal/livingwiki/coldstart/runner.go:1017`，
   `credentials.Take` -> `symbol_25815391d3f8bc32`。
4. `rel_ef95b4f04432d097`，同文件 `:1177`，同 target。
5. `rel_ba9b4553da0d8679`，同文件 `:1924`，同 target。

最终全新 cold：0；最终 disk warm：0。对应 SourceBridge golden 也在核心与全量测试
中通过。

## 七、验证证据

```text
核心 CLI + validation + indexer：54/54 PASS（39.393s）
scanner/persistence/CLI/validation + 关键 baseline：50/50 PASS（8.056s）
全量 unittest 第二轮：231/231 PASS（167.313s）
Ruff：ruff check src tests -> All checks passed
compileall：python -m compileall -q src tests -> exit 0
SourceBridge fresh cold + disk warm：命令均 exit 0
```

全量首轮唯一失败是一个 Skill export 测试 fixture 在人为加入 feature 字段后只重算
外层 checksum、没有按新协议重算 derived digest。fixture 已改为构造合法闭合索引；
该单项通过后，再跑完整 231 项得到上述全绿结果。Skill append-only transaction、
tamper、crash、`os._exit`/flock 回归均包含在这 231 项中。

## 八、参考项目采用关系

| 参考项目 | 本轮采用程度 | 采用点 | 没有照搬的部分 |
|---|---|---|---|
| SourceBridge | 高，真实生产基准 | 大型 Go 图、package/receiver resolution、cold/warm 一致性与真实性能门 | 不复制其产品业务或 Go analyzer 实现；本轮只修 core 持久化、验证和 resolver 边界 |
| Understand Anything | 中高，真实 curated/baseline 基准 | 增量 hydration、派生教学产物、source-audited claim 闭包 | 不复用其插件 UI/运行时；用 Repo Teacher 自有 schema 与 validator |
| CodeBoarding | 中，展示与教学参照 | 模块/reading path/源码定位报告的可追溯发布需求 | 没有移植其服务栈；HTML 仍是本地 standalone artifact |

这三者的关系是“采用经过源码复核的机制与验收基准”，不是按仓库名称宣称复用。
具体实现均能回到上述 owned modules 与回归测试。

## 九、仍需独立复审的边界

1. SHA-256 manifest 与 index checksum 只防偶发损坏，不是签名。能控制 generation
   目录并同时重写 payload、manifest、digest 的本地高权限攻击者仍在信任边界内。
2. 非 Git 普通目录没有原生 MVCC/filesystem snapshot。多轮 scan + final manifest +
   publish-point validate 能检测已注入的尾窗变化，但不能声称对持续恶意并发 writer
   提供数学意义上的原子源码快照。需要绝对保证时，应在只读 filesystem snapshot、
   worktree clone 或上游写锁中运行。
3. generation append-only 会增长磁盘，当前没有自动 retention/GC，见上文保留策略。
4. atomic no-replace/exchange 依赖 Darwin `renameatx_np` 或 Linux `renameat2`；其他平台
   会 fail closed，而不是退化为非原子覆盖。
5. 真实 SourceBridge 工作树已有 `D LICENSE`，因此 snapshot 会如实显示 dirty；这不是
   本轮代码产生的修改。

以上边界不在本文中降格为 PASS。下一步应由未参与实现的 Agent 重放 generation
故障注入、semantic poison、secret corpus、non-Git tail、O(N) 与 SourceBridge
cold/warm 探针后给出最终判定。
