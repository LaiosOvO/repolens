# 核心索引第二轮修复交付

日期：2026-08-10  
范围：核心扫描、索引、校验、generation 发布、Python 关系解析及对应核心测试  
状态：**实现与自测完成，等待不同 Agent 独立复审；本文不自行签发 PASS。**

## 结论先行

本轮针对以下两份独立审计报告逐项修复：

- `docs/audits/core-index-release-verification.md`
- `docs/audits/waku-agent-index-compatibility.md`

原先的三个生产阻断已经有对应实现和回归：

1. 完整重签的 Go、JavaScript、Python 伪 symbol/relationship 不能再靠自算
   `analysis_sha256`、`derived_sha256`、`integrity_sha256` 通过校验或进入 warm；
2. `output/index.json`、`output/current/index.json` 和当前 immutable generation 中的
   `index.json` 经过同一整 generation reader，非当前 generation 被拒绝；
3. compatibility links 只覆盖当前 generation 真实存在的 artifact，Waku `index`
   不再生成 `modules/projects/technology-selection.*` 悬空链接。

真实 SourceBridge 与 Waku 都完成 fresh cold、独立进程 disk warm、root/current 双入口
validate、十组集合一致性和精确关系探针。SourceBridge warm 为
`1575 reused / 0 reanalyzed`；Waku warm 为 `212 reused / 0 reanalyzed`。

验证过程中额外发现并修复了一个真实 warm 回归：Python signature 中的
`token: str` 会在持久化时变成 `token: [REDACTED]`，但 baseline clean reproof
曾拿未脱敏 analyzer 输出比较，导致可信 baseline 被拒绝。新增红测后，canonical
比较统一使用持久化脱敏表示；SourceBridge 随后恢复全量复用。

## 1. 修复映射

| 独审阻断 | 实现结果 | 关键回归/真实门 |
|---|---|---|
| 任意 dict 可伪装 warm baseline | 只有 `read_published_json()` 在验证当前 immutable generation 全部 artifact 后返回的 `VerifiedPublishedJson` 才有 reuse 资格；对象绑定 output、artifact 和 generation ID | `test_unverified_in_memory_baseline_is_never_reused`；完整重签磁盘 poison 回归 |
| Go/JS/Python 完整重签伪语义可通过 | baseline reuse 前对当前源码重新运行所有受支持 analyzer、去重并执行 Go/通用 resolver，再逐 path 比较 canonical symbol/relationship；validator 也 clean rebuild 并比较 canonical claims | `test_fully_resigned_forged_language_claims_are_rejected`；`test_rehashed_symbol_kind_and_relationship_forgery_are_rejected` |
| 重签 tutorial/codemap/stats 可进入 warm | derived teaching artifact 每次 warm 都重算；validator 比较 modules、reading path、features、evidence、tutorials、codemaps、coverage 和稳定 stats | `test_fully_resigned_derived_forgery_is_recomputed_on_disk_warm`；`test_rehashed_tutorial_codemap_and_stats_forgery_are_rejected` |
| current 路径不能 validate | managed reader 识别 root stable path、`current/<artifact>` 和当前 immutable generation path；所有路径走 manifest exact-set、size、digest、embedded generation ID、current-before/after 校验 | persistence/CLI current-path 回归；SourceBridge/Waku root/current 都 0 errors |
| 非当前 generation/混代可被读 | immutable generation ID 必须等于当前指针；整个 current generation 的 artifact 集合全部验证后才返回一个 JSON | `test_all_supported_current_paths_verify_the_same_generation`；旧 generation path 拒绝 |
| index 产生四个 dangling link | 从 manifest 实际 artifact 计算 compatibility surface；`index`、`explain`、`compare` 各自只暴露闭集 | persistence/CLI link closure 回归；Waku/SourceBridge 只有 index 两个有效 link |
| hard-kill 后 root links 可能与 current 不一致 | `current` 是唯一权威；任意下一次 writer 获取 `OutputLock` 时，先从 current manifest 恢复 root convenience view；需要修复时先完整校验 generation，再变更 links | `test_next_writer_repairs_compatibility_links_after_hard_exit` 使用真实子进程 `os._exit(23)` |
| Waku `self.model.transcribe()` 错连本地方法 | Python import edge携带显式 binding provenance；裸函数、同类 `self/cls.method`、显式本地 module binding 才能解析；未知多级 receiver 保持 unresolved | Waku 真仓 `rel_7c8ce5957801d856` 的 `target_id=None`，错误连到 `Ears.transcribe` 为 0 |
| 持久化脱敏使 honest warm 被误拒绝 | baseline canonical analyzer 输出先走和落盘相同的 `redact_persisted_value()`，再做逐 path 语义比较 | `test_redacted_python_signature_still_reuses_verified_baseline` 先红后绿；SourceBridge 1575/1575 |

## 2. 可信 baseline 与 canonical reproof

### 2.1 磁盘 provenance

`src/repo_teacher/persistence.py` 中的 `VerifiedPublishedJson` 只能由受控 reader 创建。
reader 的顺序是：

1. 解析并限制 `current` 只能指向 `.repo-teacher-generations/<32hex>`；
2. 有界读取 v2 manifest；
3. 验证目录实际 regular-file 集合与 manifest exact set 相等；
4. 对每个 artifact 校验 size、SHA-256 和嵌入的 `generation_id`；
5. 读取前后复核 `current` 没有切换；
6. 才返回带 output、relative artifact、generation ID 私有 provenance 的 JSON。

`src/repo_teacher/indexer.py` 的 baseline gate 还会检查 provenance 与本次
`output_dir`、`index.json`、source identity 和 analysis fingerprint 一致。普通内存
dict、从别处拷来的 JSON、旧 generation、manifest 被改写的 generation 都不能获得
reuse 资格；安全行为是 full reindex，而不是“尽力相信”。

### 2.2 所有支持语言的源码重证

baseline hydration 前，当前扫描内容会重新经过 language analyzer、relationship ID
去重、Go package/receiver resolver 和通用 resolver。随后按 path 比较：

- symbol：stable ID、file/path、name、qualified name、kind、range、analyzer、parent、
  signature、exported；
- relationship：source、target name、kind、path、line、analyzer、confidence、receiver
  hint；
- Go 的解析置信度按 project-resolved 归一化，避免图可用性变化冒充源码 claim 变化；
- canonical records 在比较前使用与落盘相同的 secrets 脱敏表示。

这不是 kind 白名单。即使攻击者同步改写记录、per-file digest、derived artifact、stats
和总 integrity digest，只要源码 analyzer 不能重建同一 claim，baseline 就被拒绝。

validator 的 `canonical-source-claims-mismatch` 则对当前源码执行独立 clean
`build_index(previous_index=None)`，比较 files、symbols、relationships、modules、
reading path、features、evidence、tutorials、codemaps、coverage 和稳定 stats 的摘要。
cache 只以 source root、当前 tree manifest、analysis fingerprint 为键并有界保留；
不是持久化信任来源。

### 2.3 derived artifact 策略

本轮明确选择保守策略：即使 primary files 全部复用，feature/evidence/tutorial/
codemap/coverage 仍重新生成，`reused_derived_artifacts=false`。manifest 只能证明旧字节
完整，不能证明被完整重签的旧 teaching claim 真实。SourceBridge/Waku 的冷暖十组
集合仍逐项相等。

## 3. generation 发布与可见边界

### 3.1 权威面

每次写命令创建唯一 immutable staging generation，写完全部 JSON/HTML/项目子报告，
逐个 readback、validate、fsync 后，将 staging 原子提交为 generation，再原子交换
`current`。`current` 是唯一权威提交点；读者不接受不同 generation 混用。

普通异常发生在 compatibility reconciliation 时，会恢复旧 current 和旧闭合 links。
staging failure、并发 writer、manifest tamper、symlink/FIFO、`os._exit` 和 permanent
`flock` 均有专项回归。

### 3.2 root compatibility view 的诚实边界

根目录 `index.json/index.html/modules/projects/technology-selection.*` 是
`current/<same-name>` 的非权威 convenience links。正常命令返回时，它们与当前
generation 的实际 artifact exact closure 一致；`file://.../index.html` 可以直接打开。

如果进程在 **current 已交换、root links 尚未修完** 的极窄窗口被 SIGKILL，current
仍完整且可验证，但 root convenience view 可能暂时陈旧。下一次任意 writer 启动时
会按 current manifest 自动修复，并清除受控的 orphan scratch symlink。这里没有把
整个 output directory 做原子交换，因此不能宣称 root namespace 对 hard-kill 全原子。

immutable generations 当前是 append-only；失败或旧 generation 会保留用于检查，尚未
实现 retention/GC。

## 4. Waku 精确兼容性闭合

真实仓：`/Volumes/T7/workspace/ontology/graph/repo/waku-agent`  
HEAD：`75b0a6d27a19009b0482c877def3eb124181f121`  
状态：clean、non-shallow  
输出：`/tmp/repo-teacher-core-r2-waku.LXioyf/output`

| 场景 | wall | max RSS | files | symbols | relationships | modules | reused/reanalyzed |
|---|---:|---:|---:|---:|---:|---:|---:|
| fresh cold | 7.78s | 196,132,864 B | 212 | 1,557 | 9,879 | 13 | 0 / 212 |
| disk warm | 8.00s | 200,523,776 B | 212 | 1,557 | 9,879 | 13 | 212 / 0 |

两次 generation 的十组集合均相等：

```text
files(212), symbols(1557), relationships(9879), modules(13),
features(6), evidence(30), tutorials(6), codemaps(6),
coverage(6), reading_path(12)
```

root 和 `current/index.json` 在 cold/warm 均为 `PASS (0 errors, 0 warnings)`。
根链接 exact set 是 `{index.json, index.html}`，二者均存在并指向 current；其余四类
入口均不存在，不是 dangling symlink。

Waku false-call 精确探针：

```text
relationship = rel_7c8ce5957801d856
path         = waku/gateway/voice.py
source_id    = symbol_934ee7f1a2b66b96
target_name  = self.model.transcribe
target_id    = None
Ears.transcribe symbols = 1
false edges to Ears.transcribe = 0
```

## 5. SourceBridge 大仓门

真实仓：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`  
HEAD：`2a128bf0c8461fae91d2b424d9168ddf205bb11b`  
既有状态：`D LICENSE`（本轮没有恢复或改动）  
输出：`/tmp/repo-teacher-core-r2-sourcebridge-fixed.9aLCND/output`

| 场景 | wall | max RSS | files | symbols | relationships | modules | reused/reanalyzed |
|---|---:|---:|---:|---:|---:|---:|---:|
| fresh cold | 59.69s | 1,291,321,344 B | 1,575 | 13,956 | 91,119 | 21 | 0 / 1,575 |
| disk warm | 64.44s | 1,427,488,768 B | 1,575 | 13,956 | 91,119 | 21 | 1,575 / 0 |

cold/warm 的 root 和 current validate 都是 `0 errors`，仅有预期的既有
`dirty-worktree` warning。十组集合逐项相等：

```text
files(1575), symbols(13956), relationships(91119), modules(21),
features(8), evidence(40), tutorials(8), codemaps(8),
coverage(8), reading_path(12)
```

根链接 exact set 是 `{index.json, index.html}`，不存在 modules/projects/technology
selection 悬空项。

### 5.1 external selector 探针定义与样本

定义不是“名字里有点号”这么宽泛，而是：同文件存在
`go-import-alias(alias=importPath)`，`calls.target_name` 是 `alias.member`，且
`importPath` 不属于 SourceBridge 自身 module `github.com/sourcebridge/sourcebridge`。

结果：**12,798 条 external selector call claims，resolved target 数为 0**。以下是前
8 条确定性样本；`target_id` 均为 `None`：

| relationship ID | path | source | target | import |
|---|---|---|---|---|
| `rel_aa1cf08200d576ae` | `benchmarks/qa/cmd/runner/main.go` | `symbol_6cea136070c9d8d3` | `flag.StringVar` | `flag` |
| `rel_d588bb2d22dcddcf` | 同上 | `symbol_6cea136070c9d8d3` | `flag.StringVar` | `flag` |
| `rel_6d9b9191e6308b93` | 同上 | `symbol_6cea136070c9d8d3` | `flag.StringVar` | `flag` |
| `rel_f7b3799b8c1c1bf0` | 同上 | `symbol_6cea136070c9d8d3` | `flag.StringVar` | `flag` |
| `rel_46ea4f32576e2143` | 同上 | `symbol_6cea136070c9d8d3` | `flag.StringVar` | `flag` |
| `rel_316d84ea65bdd0e0` | 同上 | `symbol_6cea136070c9d8d3` | `os.Getenv` | `os` |
| `rel_1affd51d748eb0d6` | 同上 | `symbol_6cea136070c9d8d3` | `flag.Parse` | `flag` |
| `rel_227381bc940a4410` | 同上 | `symbol_6cea136070c9d8d3` | `errors.New` | `errors` |

这项证明外部 package selector 被保守保留为源码 claim，没有被仓内同名 symbol 错连。

### 5.2 warm 性能口径

`reanalyzed=0` 只表示 primary analyzer record 从可信 baseline hydration；CLI warm 仍执行
全树扫描、canonical baseline reproof、derived 重算和发布前 clean validation。因此
64.44s/约 1.43GB 是当前诚实成本，不应描述为“近零成本 warm”。

per-path digest 已预先按 path 分组，synthetic 回归中每个 path 只收到自己的 records，
累计复杂度保持 O(total records)，没有退回 O(files × graph records)。

## 6. 扫描、non-Git 与 secrets 边界

- scanner/manifest 统一执行 `max_entries`、files、declared bytes、deadline、cancel；
- symlink/stat 检查在异常边界内，`PermissionError` 转为可观测 diagnostic；
- FIFO/non-regular file 不阻塞，读取按 `max_file_size + 1` 有界；
- partial/truncated index 非零退出，既不发布也不进入 baseline；
- non-Git 在初始、扫描后和 publish-point 复核 tree manifest/snapshot，尾窗变化 fail
  closed；这是竞态检测，不是文件系统 MVCC；
- URL/SCP remote、snippet 和全部持久化文本覆盖 GitHub、AWS、GitLab、Slack、Anthropic、
  Bearer/JWT、generic token/password/private-key 等 fail-closed corpus；
- Go `go-import-alias` 等结构字段不做 assignment-style 误脱敏，避免破坏 resolver。

## 7. 多项目参考采用矩阵

以下“采用”指机制借鉴与本项目独立实现，不代表复制参考仓源码。没有采用的部分明确
列出，避免为了填表虚构复用。

| 项目与固定版本 | 阅读的真实源码 | 本轮 core 采用点 | 明确未采用边界 |
|---|---|---|---|
| SourceBridge `2a128bf0c846…` | `internal/livingwiki/orchestrator/fingerprint.go`、`incremental.go` | 将实现/config/source identity 纳入 fingerprint；以完整 freshness envelope、watermark 和真实 1,575-file Go 仓作为增量/安全 golden | 没有复制其 Go orchestrator、PR/publish、LLM wiki pipeline；Repo Teacher 使用本地 Python generation store |
| Understand Anything `fe8c5bc59171…` | `understand-anything-plugin/packages/core/src/fingerprint.ts`、`change-classifier.ts` | 内容 hash + structural fingerprint；缺少完整结构证明时保守判 structural，而非误判 implementation-only | 没有采用其 plugin、tree-sitter graph、前端或存储格式；当前完整 structural contract 仍主要是 Python AST |
| CodeBoarding `8c3f2218c3ec…` | `repo_utils/fingerprint_diff.py`、`static_analyzer/incremental_orchestrator.py` | 缺 baseline/sidecar 时 full rebuild；按文件 invalidate/merge；dangling/旧记录 fail closed | 没有复制 LSP/static analyzer cache；Repo Teacher 额外要求 verified generation provenance 和源码 canonical reproof |
| OpenWiki `7531d615216e…` | `src/agent/okf-middleware.ts`、`src/agent/utils.ts` | 参考 finalize gate、内容 snapshot、interrupted run 不可当 completed baseline 的设计；映射为 validate-before-publish 和 partial fail closed | 这是设计模式参考，没有复制 OpenWiki middleware/runtime；它不是本项目 generation transaction 的代码来源 |
| DeepWiki-Open `4181daa5ebde…` | `api/services/codemap.py::_ground_citations` | source-grounded citation/evidence 原则：派生 claim 必须回到受 hash/range 约束的源码 | 没有采用 RAG、LLM 生成、provider 或 codemap pipeline；core derived artifact 是确定性本地生成 |
| PocketFlow-Code2Tutorial `05b24cbbb0fe…` | `flow.py`、`nodes.py::CombineTutorial` | 借鉴“先分析关系/结构，再组合 tutorial”的阶段顺序，用于审视 derived artifact closure | 没有采用 PocketFlow runtime、LLM batch/retry 或其教程节点；warm derived 本轮选择全部重算 |
| Waku Agent `75b0a6d27a19…` | `waku/gateway/voice.py` | 第七兼容性项目，不是六仓选型基准；真实暴露并闭合 current validate、dangling links、Python unknown receiver false-call | 没有把 Waku 的 voice/agent/memory 实现并入 Repo Teacher；只作为真实 Python/JS 兼容 corpus |

仓库身份复核：除 SourceBridge 既有 `D LICENSE` 外，Understand Anything、CodeBoarding、
OpenWiki、DeepWiki-Open、PocketFlow-Code2Tutorial、Waku 在本轮探针时均为 clean；参考仓
没有被本轮实现修改。

## 8. 验证证据

核心专项：

```text
PYTHONPATH=src .venv/bin/python -m unittest -v \
  tests.test_persistence tests.test_scanner tests.test_snapshot \
  tests.test_indexer tests.test_validation tests.test_cli tests.test_analyzers

Ran 121 tests in 76.565s — OK
```

全量：

```text
PYTHONPATH=src .venv/bin/python -m unittest discover -v tests
Ran 254 tests in 164.222s — OK (skipped=3)
```

静态门：

```text
ruff check src tests                                      — All checks passed
PYTHONPATH=src .venv/bin/python -m compileall -q src tests — PASS
```

三个 skip 都是本机测试进程未安装 Playwright/Chromium 的可选浏览器断言；不是核心索引、
generation、warm 或 Waku 探针 skip。

## 9. 改动面与剩余风险

本轮核心实现集中在：

- `src/repo_teacher/persistence.py`
- `src/repo_teacher/indexer.py`
- `src/repo_teacher/validation.py`
- `src/repo_teacher/analyzers/python.py`
- 对应 `tests/test_persistence.py`、`test_indexer.py`、`test_validation.py`、
  `test_cli.py`、`test_analyzers.py`

仍需独立复审关注：

1. warm 为安全执行 canonical reproof 和 derived 重算，SourceBridge wall/RSS 仍高；这是
   性能 WATCH，不是被隐藏的 reuse；
2. immutable generation 尚无 retention/GC，长期使用会持续占用磁盘；
3. manifest SHA-256 是完整性 checksum，不是抵抗有权限本地 writer 的签名/MAC；
4. 普通可写文件系统不是 MVCC，non-Git 多次 manifest 只能检测竞态，不能提供数学上的
   原子 source snapshot；高保证任务仍需只读 filesystem snapshot 或固定 worktree；
5. root compatibility view 在 hard-kill 极窄窗口可短暂陈旧，权威读取必须以 current
   generation reader 为准；下一次 writer 会恢复闭集；
6. validator clean rebuild 与 baseline source reproof 共享 analyzer 实现，能防 payload
   自签 poison，但不能替代对 analyzer 本身正确性的持续 golden/独立语义审计。

下一步应由未参与本轮修改的 Agent 重放两份旧审计的 P0/P1 对抗探针，并单独判断是否
达到生产发布标准。

## 10. Round 10 teaching validator 合同集成附录

Round 10 将有完整 framework provenance 的静态入口收窄为 **callsite 单行证据**，并把
summary 统一为“保守同作用域静态框架调用声明；实际可达性未知”。旧 validator 固定
要求 `line..line+5` 且使用“已确认语法/执行边界”，会错误拒绝六仓和 Waku 的当前
确定性输出。

本次只修改 `validation.py` 与 `tests/test_validation.py`，通过公开
`validate_index(index, source)` seam 先建立失败回归，再做最小合同更新：

- framework claim 必须恰好包含三个互异、直接引用的
  `technology-claim:framework` evidence，顺序为 `import / factory / call`；
- 三段 evidence 必须与 entry 的 path、confidence、base analyzer、entry symbol 闭合，
  且各自 stable evidence identity 有效；
- `call` evidence 必须与 entry 是同一单行并具有同一 source snippet hash；
- framework claim 的 source path、confidence、保守 claim scope 和
  `framework:<value>` tag 必须一致；
- 只有满足以上全部条件，entry 才允许 `line_end == line_start`，并接受
  “保守同作用域合同 / 实际可达性未知”的 summary；
- 非 framework 的 legacy 静态入口仍保留 `line..line+5` 范围；候选入口语义不变；
- 缺少 factory/call stage、重复 evidence、错误 analyzer/path/symbol、扩大到生产运行时
  可达性的 summary 均返回 `feature-claim-mismatch`，不会因兼容新合同而放宽。

本附录专项证据：

```text
tests.test_validation: 15/15 — OK
ruff check validation.py + test_validation.py — All checks passed
compileall validation.py + test_validation.py — PASS
```

六仓/Waku 的 53 项 teaching integration gate 由 teaching lane 在本 validator 冻结后
重新执行；本附录不替代该独立集成门，也不自行签发 PASS。
