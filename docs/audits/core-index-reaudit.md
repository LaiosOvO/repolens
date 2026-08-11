# 核心索引独立复审

**复审结论：REQUEST CHANGES（生产门禁不通过）**

复审日期：2026-08-10  
复审范围：`scanner.py`、`indexer.py`、`snapshot.py`、`persistence.py`、`evidence.py`、`validation.py` 及其专项测试。  
复审方式：源码检查、25 项核心专项测试、临时目录上的对抗探针，以及与 SourceBridge、Understand Anything、CodeBoarding 的逐机制对照。本报告只记录审计结果，不修改产品代码。

## 结论先行

本轮整改不是“没有效果”：FIFO 阻塞、目录遍历错误静默、配置/实现指纹缺失、直接篡改缓存复用、逐文件扫描全部 baseline 记录、重复 relationship ID、unsupported analyzer 静默、输出目录等于仓库根目录等历史问题已经得到实质修复。

但当前仍有三个 P0 和多个 P1，不能称为生产级：

1. **凭据仍会进入 JSON/HTML**：URL 形式 remote 已脱敏，但 SCP-like remote、GitHub fine-grained token、Bearer token、数据库 URL 和未加引号 secret 均可原样落盘。
2. **`validate` 不是可信门禁**：篡改 `integrity_sha256` 并注入一个完全无证据的 `confidence=exact` 虚构功能后，`validate_index` 仍返回 `valid=True`。
3. **结构变更存在确定性漏判**：只改变 Python 公开函数的返回类型注解，会被判为 `SKIP_GRAPH_UPDATE`。

历史审计特别点名的 stale lock、跨文件 generation transaction、evidence claim gate，当前分别是 **P1 阻断、P1 阻断、P0 阻断**；三者都必须在生产发布前修复。

## 历史问题逐项复核

| 检查项 | 结论 | 证据 | 生产判断 |
|---|---|---|---|
| remote credential | **FAIL / 部分修复** | `snapshot.py:51-64` 只处理包含 `://` 的 URL。探针中 `https://user:secret-token@...?...` 被正确清洗为 `https://example.com/...`；`github_pat_SECRET_VALUE@example.com:org/repo.git` 原样返回。 | P0，安全阻断 |
| analyzer/schema/config fingerprint | **PASS（有 P2 缺口）** | `indexer.py:60-92` 将 schema、三项扫描预算、核心实现文件和全部 analyzer 源码纳入 SHA-256；`indexer.py:130-148` 不匹配即拒绝 baseline；配置不匹配测试通过。未纳入 Python runtime 版本。 | 核心整改通过；runtime 漂移为 P2 |
| 扫描期间混合 snapshot | **FAIL / 部分修复** | `indexer.py:275-289` 的双扫描能捕获第二次扫描开始前的新增文件，现有测试通过；但探针让文件在第二次扫描返回后、`capture_snapshot` 前新增，非 Git 目录仍正常返回，且新文件未入索引。 | P1，正确性阻断 |
| FIFO / 非 regular | **PASS** | `scanner.py:176-179,214-218` 在 open 前后都要求 regular file；FIFO 专项测试不会阻塞。 | 通过 |
| 目录遍历错误 | **PASS（发布语义仍有 P1）** | `scanner.py:140-153` 使用 `os.walk(onerror=...)`；注入 `PermissionError` 得到 `walk-error` diagnostic。`indexer.py` 会令 `scan_complete=false`。但 CLI 仍可将部分索引按成功报告发布。 | 检测通过；部分结果发布见 P1-4 |
| `max_files` / `max_total_bytes` | **FAIL / 部分修复** | 已纳入 `ScanOptions` 并对实际读取的可识别文件生效，已有预算测试通过；但 `scanner.py:170-183` 在预算计数前跳过 unsupported 和 too-large。20 个 unsupported + 20 个 too-large 文件在 `max_files=1,max_total_bytes=5` 下得到 `truncated=False`、零诊断。也没有 wall-clock/cancellation budget。 | P1，资源边界不完整 |
| baseline fail-closed | **FAIL / 部分修复** | schema/config/path/`scan_complete`/digest/字段形状/重复 ID 会拒绝，直接篡改测试通过；但 digest 是可重算的无密钥校验。探针向未变化文件注入合法形状的 `symbol_attacker`、重算 digest 后，baseline 被判 `compatible` 且虚构符号被复用。`indexer.py:150-190` 未验证 symbol path↔file、file_id↔path、行范围、stable ID 或源码对应关系。 | P1，可信缓存阻断 |
| unknown fields | **PASS** | `indexer.py:117-119` 只取 dataclass 已知字段。带 `future_field` 的兼容 baseline 不崩溃，未知字段被忽略。 | 通过（应补正式回归测试） |
| output=self | **FAIL / 部分修复** | `indexer.py:613-623` 拒绝 `output == root`，测试通过；但 output 是 source 的祖先目录时未拒绝。探针以父目录作为 output 后，`src/hidden.py` 被静默排除，结果仍 `scan_complete=True`。 | P1，完整性阻断 |
| O(files × records) baseline hydration | **PASS（另有扩展性问题）** | `indexer.py:193-203,674-690` 先按 path 一次分组，再按文件 O(1) 获取；历史 O(files × records) 已消除。 | 该项通过；`_build_reading_path` 的 O(modules × files) 见 P2-2 |
| duplicate relationship IDs | **PASS** | `indexer.py:219-253` 对语义重复去重、真实冲突稳定改号；现有重复调用测试通过，独立 true-collision 探针输出 2 个唯一 ID、`collisions=1`。 | 通过 |
| unsupported analyzer diagnostic | **PASS（分类语义有缺口）** | `indexer.py:691-705` 对无 analyzer 的文件产生明确 diagnostic，专项测试通过。 | 诊断通过；parse failure/空结构的分类问题见 P1-3 |
| structure classification | **FAIL** | `indexer.py:292-323` 仅比较 `qualified_name/kind/signature/exported` 与 calls/import/contains；Python analyzer 的 signature 不含返回注解。`-> int` 改成 `-> str`、函数体不变时得到 `SKIP_GRAPH_UPDATE`。 | P1，核心语义阻断 |
| 非 Git 并发新增 | **FAIL / 部分修复** | 现有测试覆盖“第二次扫描开始时新增”，会拒绝；对抗探针覆盖“第二次扫描完成后新增”，索引正常返回且遗漏文件。 | P1，与 mixed snapshot 相同 |

## 阻断问题

### P0-1：输出仍可能泄露凭据

- `snapshot.py:51-53` 对不含 `://` 的 remote 直接返回，SCP-like remote 的 userinfo 不会清洗。
- `evidence.py:10-18` 的规则未覆盖 `github_pat_...`、`Authorization: Bearer ...`、数据库连接 URL、未加引号的 `client_secret = ...`。
- `EvidenceStore.add` 会把脱敏结果放入 JSON/HTML；因此这是实际输出面的安全问题，不是纯检测精度问题。

**复现结果：**

```text
github_pat_SECRET_VALUE@example.com:org/repo.git
  => github_pat_SECRET_VALUE@example.com:org/repo.git
GITHUB_TOKEN=github_pat_...
  => 原样保留
Authorization: Bearer eyJ...
  => 原样保留
DATABASE_URL=postgresql://alice:secret@db.local/prod
  => 原样保留
```

**验收门槛：** remote 应统一解析/移除任何 userinfo；snippet 输出应采用可扩展 secret scanner 或至少覆盖主流 token、Bearer/JWT、URI credentials、quoted/unquoted assignments，并为每类增加负向测试。对不能确定安全的片段，应 fail closed 为整段隐藏，而不是尝试原样输出。

### P0-2：`validate_index` 可给虚构“精确功能”签发 PASS

`validation.py:37-153` 不检查：

- `schema_version` 与 `analysis_fingerprint`；
- `integrity_sha256`；
- `stats.scan_complete`；
- feature 是否至少有一条有效 evidence；
- `confidence=exact` 是否满足对应证据策略；
- evidence 的 kind/confidence/analyzer 是否足以支持功能主张；
- 新增但未进入旧索引的源文件。

对抗探针将 `integrity_sha256` 改为 64 个零，并把 features 替换成无任何证据的 `Transfers all funds / confidence=exact / verified production behavior`，结果仍为：

```text
valid=True errors=0 issue_codes=[]
```

这说明当前 `validate` 只能检查部分引用完整性，不能作为报告、Skill 导出或技术选型的真实性门禁。必须将命令和 UI 上的“PASS”撤下或补齐完整校验。

### P0-3：公开实现细节会被原样作为 evidence 输出

此项与 P0-1 同属一个安全根因，但影响面不同：remote 泄露来自 project metadata，snippet 泄露来自任意被功能发现选中的源码行。当前“原文 hash + 脱敏 snippet”的设计本身可保留；生产门槛是先让脱敏层具备明确的覆盖合同、整段 fail-closed 模式和安全测试语料。

### P1-1：rehashed baseline 可注入语义记录

`integrity_sha256` 是 checksum，不是签名。当前 baseline 格式检查能防损坏或旧版本，不能防本地文件被改写并重算摘要。更严重的是 `_baseline_rejection_reason` 没有做跨记录语义校验。

**实测：**在 `main.py` 的 baseline 中加入一个不存在于源码的 `pay_admin` symbol 并重算 digest，下一次构建显示：

```text
baseline_status=compatible reused_files=1 fake_reused=True
```

最低修复应验证 file ID、path、symbol ID、parent、line range、relationship source/target/path 的闭包一致性，并把“摘要只防意外损坏”的信任边界写明。如果 baseline 要跨信任边界复用，需要签名/MAC 或只从受控 generation 目录读取。

### P1-2：双扫描仍不是一致 snapshot

双扫描显著缩小了窗口，但它不是 SourceBridge 的 commit/watermark 语义，也不是文件系统 snapshot。`_source_is_stable` 在第二次扫描返回后还有一次未受保护的窗口；对非 Git 项目，`capture_snapshot` 不包含树 fingerprint。

可接受方案至少选一项：

- 将最终 snapshot 变成第三个、不可分割的 whole-tree manifest 校验并在发布前复核；
- Git 项目只允许固定 clean commit 模式；
- APFS/ZFS snapshot 或临时只读 tree；
- 输出显式标记为 best-effort，并禁止为其签发 exact/validated。

### P1-3：结构指纹低于参考项目语义，发生漏判

Understand Anything 的 `fingerprint.ts:9-38,79-121` 明确包含函数参数、返回类型、export、行数、class methods/properties、imports specifiers，并以 `hasStructuralAnalysis` 表达是否真的能比较；`compareFingerprints` 在缺少结构分析时保守判为 STRUCTURAL（`:142-149`）。

本地实现只以“语言属于支持集合”作为可比较条件；没有返回类型、class property、base class、完整 import specifier、显式 analysis-success 标志。公开返回类型变化被漏判为 `implementation_only`。在补齐语义前，任何 analyzer 缺少完整结构信号或产生 parse diagnostic 的 changed file 都应保守判 structural。

### P1-4：部分扫描被作为成功产物发布

walk/read/changed-while-reading 会令 `scan_complete=false`，达到预算也会 `truncated=true`；但 `build_index` 仍返回完整形状，`cli.py:143-162` 仍写出 JSON/HTML、打印 `Generated repository index` 并返回 0。SourceBridge `changewatch/router.go:430-445,522-538` 会将预算或 merge 失败显式标成 stale/suspect/partial refresh，而不是把它当 fresh。

生产策略应二选一：默认 fail closed、非零退出且不切换 current generation；或显式 `--allow-partial`，并让 HTML 顶部、JSON freshness、CLI exit/status 都显示 PARTIAL，且禁止该结果成为 baseline 或“validated”报告。

### P1-5：扫描预算可以被跳过

`max_files` 和 `max_total_bytes` 只累计已经 stat、未超过单文件大小、实际读取的可识别文件。大量 unsupported 文件、too-large 文件、stat/read errors 均不消耗该预算；目录项遍历也没有上限或 wall-clock/cancel token。

参考 SourceBridge `changewatch/router.go:420-445` 的 `context.WithTimeout`：生产资源门禁应至少包括 visited directory entries、visited files、stat bytes/declared bytes、actual bytes、wall-clock deadline 和 cancellation；达到任何门限都应进入 PARTIAL/失败状态。

### P1-6：父目录 output 会静默产生“完整”的残缺索引

当前只拒绝 `output == source`。当 output 是 source 的祖先目录时，所有 source 子目录都满足 “is_relative_to(excluded)” 而被排除，根文件仍被扫描，因此最终 `scan_complete=True`，但模块大面积丢失。必须拒绝 `source.is_relative_to(output)`，并为 ancestor、descendant、sibling 三种位置写回归测试。

### P1-7：stale lock 是无人值守生产阻断

`persistence.py` 的 OutputLock 使用排他创建能防两个活跃 writer；但崩溃会永久留下 `.repo-teacher.lock`。探针创建 `{"pid":999999}` 后，后续任务始终得到 `output is locked by another writer`。

这对用户计划中的长时间本地 Agent 和远程任务分配是可用性阻断。需要 lock owner token、pid/start-time/host、进程存活与 PID reuse 检查、受控 stale recovery，并保证只删除自己持有且 inode/token 匹配的锁。

### P1-8：index.json + index.html 没有 generation transaction

`atomic_write_text/json` 保证单文件原子，但 `cli.py:143-144` 依次替换 JSON 和 HTML。模拟 JSON 写成功、HTML 写失败后，命令返回 1，但目录内已经是“新 JSON + 旧 HTML”。`compare` 和 `explain` 的跨文件产物窗口更大。

需要写入唯一 staging generation，完成全部文件、fsync、validate 后，再原子切换 `current` 指针/目录；HTML/JSON 都应带同一个 generation ID。失败 generation 不得改变当前可见版本。

## P2 与非阻断改进

1. **runtime 未进分析指纹**：Python AST 行为随 runtime 版本变化，建议加入实现版本、Python major/minor 与 analyzer contract version，而不仅是源码字节。
2. **仍有 O(modules × files)**：`indexer.py:583-590` 为每个模块重新遍历所有文件；而且达到 12 个 reading step 后仍继续循环。大型多顶层目录仓库可退化为平方复杂度。应预分组并在达到上限后 break。
3. **true collision ID 的局部稳定性**：碰撞改号依赖前序全局 collision 计数；罕见但可通过按原 ID 分组、对语义 tuple 排序后局部编号获得更强稳定性。
4. **unknown fields 缺正式测试**：实现具备向前兼容行为，但当前专项测试没有单独锁定该合同。
5. **dirty unknown 不可见**：`snapshot.py` 已用 `dirty=None` 区分 git status 失败，但 `validation.py:142-143` 对 `None` 不产生 warning，用户会看到无异常的 PASS。

## 独立对抗验证结果

### 自动测试

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_scanner tests.test_indexer tests.test_persistence \
  tests.test_evidence tests.test_validation -v

Ran 25 tests in 0.743s — OK
```

这些测试证明已实现的回归合同成立，但没有覆盖本报告的 P0/P1 对抗路径。

### 探针摘要

| 探针 | 实际结果 |
|---|---|
| HTTPS remote user/password/query | 清洗成功 |
| SCP-like remote userinfo | token 原样保留 |
| rehashed semantic baseline poison | baseline `compatible`，虚构 symbol 被复用 |
| 第二次扫描返回后新增非 Git 文件 | 构建成功，新增文件遗漏 |
| output 为 source 父目录 | `scan_complete=True`，子目录文件遗漏 |
| Python return annotation only change | `SKIP_GRAPH_UPDATE` |
| fabricated exact feature + corrupt integrity | `validate_index.valid=True` |
| 40 个预算前跳过的文件 | `truncated=False`，零预算 diagnostic |
| true relationship ID collision | 输出 ID 唯一，修复计数为 1 |
| stale lock | 永久 fail-fast，不能自动安全恢复 |
| JSON 后、HTML 前故障 | 新 JSON + 旧 HTML 混合 generation |

## 与三套参考实现的具体映射

这里的覆盖率是**机制检查表覆盖率估算**，不是代码行覆盖率，也不表示许可证兼容性。

### SourceBridge：约 30%

| 参考机制 | 参考源码 | 本地对应 | 结论 |
|---|---|---|---|
| 版本化、确定性输入 fingerprint | `internal/livingwiki/orchestrator/fingerprint.go:13-43,72-92,114-141` | `indexer.py:60-92` | 部分采用；有 schema/config/实现 hash，但没有 source revision + 下游模型/模板等产物输入身份 |
| diff/page guard、debounce、two watermarks、force-push | `internal/livingwiki/orchestrator/incremental.go:36-57,228-345` | file hashes、`max_files/max_total_bytes` | 只采用内容 diff 与部分预算；watermarks、debounce、queue、force-push 未采用 |
| delta-only + deadline + containment | `internal/changewatch/router.go:420-463` | 全树双扫描 + unchanged analysis reuse | 未达到：没有 wall-clock context、每次仍扫描全树、无 changed-set containment contract |
| old/new merge、impact、freshness envelope | `internal/changewatch/router.go:465-538` | record merge、`scan_complete` | 低程度采用；无 impact invalidation 和 fresh/suspect/stale/partial 状态机 |
| event hash dedup | `internal/changewatch/router.go:636-666` | relationship dedup | 不是同一能力；change event dedup 未采用 |

本地已有“fingerprint + 变化集合 + 记录复用”的骨架，但没有 SourceBridge 生产路径里最关键的 bounded delta、freshness、watermark 与恢复语义，因此不能宣称完整参考。

### Understand Anything：约 45%

| 参考机制 | 参考源码 | 本地对应 | 结论 |
|---|---|---|---|
| content SHA-256 | `understand-anything-plugin/packages/core/src/fingerprint.ts:67-72` | `scanner.py:279-286` | 采用 |
| 显式 `hasStructuralAnalysis`、无分析时保守 | `understand-anything-plugin/packages/core/src/fingerprint.ts:30-39,142-149,248-281` | 仅 `SUPPORTED_ANALYZER_LANGUAGES` | 未完整采用；parse failure/空结构仍可能按可比较处理 |
| function return/export/line count | `understand-anything-plugin/packages/core/src/fingerprint.ts:9-15,87-93,152-187` | symbol signature/export | 参数与 export 部分采用；return/line count 缺失并已实测漏判 |
| class methods/properties/export | `understand-anything-plugin/packages/core/src/fingerprint.ts:17-23,95-101,190-217` | class/method symbols | methods 部分采用；properties/base/完整 class signature 缺失 |
| import source + specifiers / exports | `understand-anything-plugin/packages/core/src/fingerprint.ts:25-28,103-108,220-234` | import target + symbol exported | 部分采用；specifier 与别名语义不完整 |
| 10/30/50% 与目录变化分类 | `understand-anything-plugin/packages/core/src/change-classifier.ts:13-20,45-86` | `indexer.py:383-401` | 基本采用 |

阈值移植较完整，但真正决定阈值输入质量的 structural fingerprint 只实现了一部分；当前约 45% 的机制覆盖不能支撑“结构分类等价”。

### CodeBoarding：约 40%

| 参考机制 | 参考源码 | 本地对应 | 结论 |
|---|---|---|---|
| 全树 fingerprint 缺失时 fail loud | `repo_utils/fingerprint_diff.py:21-31,53-70` | baseline absent 全量重建；invalid baseline diagnostic | 安全回退部分采用；不 fail command，但不会空 diff |
| added/modified/deleted 集合 | `fingerprint_diff.py:34-50` | `indexer.py:663-739` | 采用 |
| invalidate changed nodes/edges/references 并校验 dangling | `static_analyzer/analysis_cache.py:338-392` | 按 path 不复用 changed records | 部分采用；闭包校验不完整，baseline poison 可通过 |
| merge cached + fresh、重建继承边 | `analysis_cache.py:395-440` | 复用 unchanged + fresh changed + resolve | 基础 merge 采用；inheritance/cross-boundary 语义未采用 |
| LSP 重新验证跨边界边和 call site | `static_analyzer/incremental_orchestrator.py:36-108,111-184` | 名称唯一时重连 | 未采用 |
| 原子 cache copy + lock | `analysis_cache.py:303-335` | 单文件 atomic write + OutputLock | 部分采用；没有跨文件 generation transaction 和 stale recovery |

文件级复用和变化集合与 CodeBoarding 同方向，但语义闭包、跨边界验证和发布事务仍明显不足。

### 综合参考覆盖

- 机制骨架覆盖：约 **35%–40%**。
- 与参考项目的生产语义等价度：约 **25%–30%**。
- 已充分参考：内容 hash、schema/config invalidation、文件变化集合、未变化记录一次分组复用、基本阈值分类、单文件 atomic replace。
- 尚未充分参考：可信 freshness、bounded/cancellable delta、watermarks、stale recovery、跨文件 generation、结构指纹完整性、跨边界图验证、证据主张门禁。

## 必须修复后才能复审 PASS 的最小清单

1. 修复 remote 与 snippet credential 泄露，并增加真实 token 语料测试。
2. 让 `validate_index` 校验 schema/fingerprint/integrity/scan completeness/全树新增删除、feature evidence 最低要求和 confidence policy；上述 fabricated-claim 探针必须失败。
3. 结构指纹加入 return type、class/base/property、import specifier 与 `hasStructuralAnalysis`；无法证明时保守 structural。
4. 修复 output ancestor 排除漏洞。
5. 将预算扩展到 visited entries + wall-clock/cancellation；部分扫描不可默认为成功/current。
6. 明确 baseline 信任边界并补齐跨记录闭包；重算摘要的语义 poison 不得直接复用。
7. 实现可恢复、可验证 owner 的 stale lock。
8. 用 staging generation + 原子 current switch 发布 JSON/HTML/比较报告/模块报告。
9. 为第二扫描后的竞态提供固定 commit/只读 snapshot 模式，或禁止为 best-effort 结果签发 exact/validated。

完成以上项目后，应重新运行本报告所有探针，而不只是现有 happy-path 单元测试。当前结论保持 **REQUEST CHANGES**。
