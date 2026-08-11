# 核心索引生产链最终独立复审

审计日期：2026-08-10  
审计范围：`scanner.py`、`indexer.py`、`snapshot.py`、`evidence.py`、`validation.py`、`persistence.py`、`cli.py` 与核心测试  
审计方式：只读源码复核、旧 P0/P1 逐项重放、临时目录故障注入、专项与全量测试；除本报告外未修改产品代码或正式 examples。

## 最终结论

**Verdict：REQUEST CHANGES**  
**Architectural status：BLOCK**

第二条独立反方通道也给出 **BLOCK**，证据见
`docs/audits/core-index-final-architect-lane.md`。该通道独立重放了同类语义注入、
三条 CLI 混合 generation、partial 成功发布、manifest 预算绕过、非 Git 尾窗，
并单独完成 SourceBridge cold/disk-warm 与永久 lock 探针；因此本结论不是单一 reviewer
的静态推断。

当前候选已经实质关闭了许多旧问题：URL/SCP remote 的既有凭据语料、Python return/base/property/import 结构指纹、output ancestor、扫描计数、partial baseline 拒绝、O(path) warm hydration、永久 `flock` 与 `os._exit` 恢复都通过。

但它仍不能作为生产级核心链发布。最直接的阻断不是抽象风险，而是已经重放成功的确定性故障：

1. `index`、`explain`、`compare` 仍逐文件发布；中间写失败会留下新旧混合的可见产物。
2. 重算 checksum 后，伪造 symbol/relationship/tutorial/codemap 可以通过 validator 或被 warm baseline 原样继承；当前“完整验证门禁”并不完整。
3. evidence 的“fail closed”不覆盖常见带供应商前缀的 secret 环境变量，凭据仍能进入 JSON/HTML snippet。
4. 非 Git/Git dirty tree 仍只是竞态检测，不是一致 snapshot；最后一次 manifest 之后的变化可漏检却得到 `freshness=complete`。
5. manifest 遍历绕开 deadline/cancellation/entry budget，文件在 stat 后增长时也会无界 `read()`，因此资源门禁不是端到端的。

## 阻断问题

### P0-1：跨文件发布没有 generation transaction

**源码证据**

- `cli.py:151-152`：`index.json` 与 `index.html` 依次调用两个单文件 writer。
- `cli.py:214-224`：`compare` 逐项目发布 JSON/HTML，最后再发布总 JSON/HTML。
- `cli.py:291-293`：`explain` 依次发布 index、module JSON、module HTML。
- 全项目不存在用于这些产物的 generation ID、staging generation、validate-before-publish 或原子 `current` 指针切换。

**独立故障注入结果**

```text
index:   rc=1, index.json changed=True,  index.html changed=False
explain: rc=1, index.json changed=True,  module JSON/HTML remained old
compare: rc=1, project a JSON/HTML changed,
               project b JSON changed but HTML remained old,
               total comparison JSON/HTML remained old
```

`atomic_write_text()` 只保证一个文件替换时原子；它不能把多个文件变成一个 generation。命令虽然返回 1，用户下次打开目录仍会看到混合版本。验收必须是：唯一 staging generation 中完成全部写入、fsync、完整验证；每个 JSON/HTML 带同一 generation ID；最后只原子切换一个 `current` entry；失败不得改变当前可见 generation。

### P0-2：baseline/validator 仍接受可重算的语义伪造

`integrity_sha256` 已正确声明为 checksum 而非签名；问题在于受控 generation 边界并未实际建立，CLI 直接从可写的 `index.json` 读取 baseline（`cli.py:137-149,276-289`），也没有在发布前调用 `validate_index()`。

**独立探针一：同名、错误类型 symbol**

在真实源码 `def main()` 的同一行注入 `kind=class, name=main` 的 symbol，按当前 stable-ID 公式生成 ID、补入 file membership 并重算 checksum：

```text
direct validate: valid=True
warm baseline: compatible, reused_files=1
fabricated symbol reused=True
warm validate: valid=True
```

原因是 `indexer.py:224-259` / `validation.py:642-698` 只验证 ID 公式与“name 出现在 source slice”，没有证明 analyzer/kind/signature 与源码 AST 记录一致。

**独立探针二：任意 relationship**

给真实 `main` symbol 注入 `target_name=pay_admin, kind=calls, line=1` 的任意 relationship 并重算 checksum：

```text
direct validate: valid=True
warm baseline: compatible
fabricated relationship reused=True
warm validate: valid=True
```

`indexer.py:273-318` 与 `validation.py:711-727` 没有验证 relationship stable ID，也没有把 call target/line 重新绑定到当前 analyzer 输出或源码语法。

**独立探针三：derived artifacts**

篡改 tutorial/codemap 标题与内容并重算 checksum：

```text
direct validate: valid=True
warm baseline: compatible, reused_derived_artifacts=True
fabricated tutorial reused=True
warm validate: valid=True
```

`validation.py:525-543` 虽把 tutorials/codemaps 加入 collection 形状检查，却不验证它们的字段、引用闭包或内容合同；modules、reading_path、coverage 甚至不在 collection gate。`indexer.py:1055-1086,1258-1277` 在无文件变化时直接复用这些记录。

已有 fabricated feature 测试本身会被 validator 拒绝，这是进步；但 CLI 不做 publish 前验证，所以带伪造 feature 的 warm build 仍可先被写入。必须让 baseline 复用和发布门禁使用同一套完整、源码重算的合同，而不是只验证少量主张。

### P0-3：evidence secret scanner 仍不是 fail closed

旧指定语料（GitHub PAT、Bearer/JWT、数据库 URL、quoted/unquoted `client_secret`/`password`）通过，remote URL 与 token-shaped SCP userinfo 也通过。但 `evidence.py:10-29` 的规则仍让以下常见生产凭据原样保留：

```text
ANTHROPIC_API_KEY=sk-ant-api03-<redacted-example>
AWS_SECRET_ACCESS_KEY=AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD
TOKEN=opaque-production-secret-value
GITLAB_TOKEN=glpat-<redacted-example>
SLACK_BOT_TOKEN=xoxb-<redacted-example>
```

这些值会由 `EvidenceStore.add()` 放进可持久化的 `snippet`（`evidence.py:92-104`），随后进入 JSON/HTML。若产品继续称为 fail closed，应对“疑似 secret assignment”整段隐藏，或接入经过维护的 secret detection 语料/引擎；不能只列举少数 key/token 前缀。

### P1-1：最后一次 snapshot 后仍有可观测竞态窗口

`_source_is_stable()` 的顺序是 manifest → verification scan → snapshot → final manifest → final snapshot（`indexer.py:513-524`）。在第三次、即最后一次 `capture_snapshot()` 返回后立即向非 Git tree 新增文件，`build_index()` 仍成功返回：

```text
returned=True
indexed_paths=['main.py']
late_exists=True
```

结果仍标记 `freshness=complete`（`indexer.py:1169-1170`）。Git dirty tree 也有同类窗口。当前注释已诚实称其为 race detector，但对外 freshness/validator 语义仍像一致 generation。

生产边界应明确二选一：只对固定 clean commit/只读 filesystem snapshot 签发 complete；或把普通可写 tree 标记为 best-effort，并禁止它成为 validated/exact generation。多做一次 manifest 仍不能消除“最后一次检查之后”的窗口。

### P1-2：扫描预算没有覆盖 manifest 和 stat→read 竞态

`capture_tree_manifest()`（`scanner.py:126-173`）完全不消费 `max_entries`、deadline 或 cancellation callback。独立探针传入 `max_entries=1`、已过期 deadline、立即返回 true 的 cancellation，200 个 entry 仍全部遍历并返回 digest，callback 调用次数为 0。

此外 `scan_repository()` 在 pre-open stat 后执行无长度上限的 `handle.read()`（`scanner.py:315-343`）。独立探针令 4-byte 文件在 stat 后增长到 2,000,000 bytes，在 `max_file_size=100`、`max_total_bytes=100` 下仍先完整读取，再以 `file-changed-while-reading` 丢弃；`declared_bytes` 仍为 4。正确性诊断成立，但资源门禁已经被绕过。

需要让 manifest 遍历本身可取消、有 entry/deadline 上限；文件打开必须 `O_NOFOLLOW`，并按剩余预算做 bounded read（至少 `limit+1`），不能依赖读完后的 metadata 比较限制资源。

### P1-3：partial 仍会被 CLI 作为成功 generation 发布

`build_index()` 会把不完整扫描标成 `partial-unvalidated`，baseline 和 validator 也会拒绝，这是已完成的修复。但 `_index/_compare/_explain` 没有检查 `stats.scan_complete` 或调用 validator，仍会写出报告、打印 `Generated...` 并返回 0（`cli.py:145-170,200-234,284-304`）。

默认生产路径应 fail closed：partial 不得切换 current，CLI 返回非零。若提供显式 `--allow-partial`，必须在 UI/JSON/exit status 上持续显示 PARTIAL，并禁止它成为 baseline、comparison recommendation 或 Skill 来源。

## 旧问题逐项重放

| 旧检查项 | 本轮结论 | 说明 |
|---|---|---|
| remote URL / SCP 凭据 | PASS（指定语料） | URL 去 userinfo/query/fragment；token-shaped SCP userinfo 去除。 |
| evidence secret | **FAIL** | 既有 corpus 通过，但常见 vendor-prefixed/generic secret assignment 仍泄漏。 |
| schema/config/runtime fingerprint | PASS | schema、预算、Python runtime、核心/analyzer/capability catalog 均进入 fingerprint。 |
| integrity checksum | PASS（边界说明） | 可检测意外损坏，明确不是认证；但 CLI 未建立受控 generation。 |
| fabricated feature claim gate | 部分 PASS | validator 拒绝旧 fabricated feature；publish/baseline 仍未调用完整 gate。 |
| stable ID / graph closure / baseline poison | **FAIL** | wrong-kind same-name symbol、任意 relationship、derived artifact 可注入。 |
| return/base/property/import structural fingerprint | PASS | Python AST 合同覆盖；JS/TS/Go 不完整时保守 structural。 |
| FIFO / walk error / non-regular | PASS | FIFO 不阻塞，walk/stat/read 错误可观察。 |
| visited entries/files/declared bytes/deadline/cancel | **FAIL（端到端）** | 主 scan 计数通过；manifest 绕过全部预算，stat 后增长会无界读取。 |
| whole-tree race detector | **FAIL（complete 语义）** | 已缩小窗口，但 final snapshot 后变化仍漏检。 |
| partial baseline / validator | PASS | partial 不能被复用或 validate。 |
| partial CLI publish | **FAIL** | 仍可写产物并返回成功。 |
| output root/ancestor | PASS | root 与 ancestor 拒绝，安全 descendant/sibling 允许。 |
| O(path) baseline hydration / reading path | PASS | records 一次分组；reading path 预分组且 12 步后 break。 |
| relationship generation ID uniqueness | PASS | 生成路径去重并修复真碰撞。 |
| relationship ID/source grounding validation | **FAIL** | validator 接受任意唯一 ID 与无源码 call 主张。 |
| unsupported analyzer conservative behavior | PASS | 有 diagnostic；changed file 保守 structural。 |
| permanent lock / `os._exit` | PASS | 双 `flock`、永久 regular lockfile、释放不 unlink，专项重放通过。 |
| 单文件 atomic writer | PASS（其声明范围） | 单 entry exchange/no-replace，旧 entry 保留。 |
| 跨文件 generation | **FAIL** | 三条 CLI 路径均可复现混合 generation。 |
| Skill append-only transaction | PASS（引用独立报告） | `skill-export-reaudit-append-only-final.md` 已独立 PASS；本轮复跑共享 OutputLock/persistence 测试。 |

## SourceBridge cold/warm 与核心参考采用程度

### SourceBridge

本轮读取并核对 `go-analyzer-reaudit-round5.md` 的独立证据；Architect 反方通道又在当前工作树重新执行固定 commit `2a128bf...` 的 cold/disk-warm：两者 validator 均为 0 errors，warm `compatible`，1,575/1,575 文件复用，10 个 core/derived 集合一致。核心专项也重新执行了真实 SourceBridge golden。

采用充分的部分：版本化 analysis fingerprint、语言隔离、package/receiver-aware Go resolver、文件级变化集合、freshness/partial 字段、warm record 重证。仍未采用的生产关键：SourceBridge 的 commit/watermark 边界、fresh/suspect/stale current-generation 切换和完整 publish transaction。**Go analyzer PASS 不能为 CLI generation 或 baseline 信任边界背书。**

### Understand Anything

Python 结构 fingerprint 已采用其 `hasStructuralAnalysis` 思路，并覆盖 return、base、property、import specifier/alias；无完整结构证明时保守 structural。这一子能力达到预期。未达到的是“整个可见产物由同一验证后的 generation 提供”，以及普通可写 tree 的强 snapshot 语义。

### CodeBoarding

文件 added/changed/deleted、按 path cache invalidation/hydration、changed 记录重分析与 target 重连已采用，复杂度也从逐文件扫描全记录收敛。未达到的是缓存记录对当前 analyzer 输出的完整重证、所有 derived artifact 闭包，以及跨文件原子 cache publication；因此“有 checksum + 闭包形状”仍不能等价为可信 baseline。

## 验证证据

核心专项：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_scanner tests.test_indexer tests.test_snapshot \
  tests.test_evidence tests.test_validation tests.test_persistence tests.test_cli -v

Ran 70 tests — OK
```

这些绿测证明已写入的合同成立；本报告的 P0/P1 来自测试之外的独立故障注入，因此不能被 70/70 抵消。

全量与静态检查：

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v
Ran 214 tests in 214.431s — OK

python3 -m compileall -q src tests — PASS
ruff check src tests — All checks passed
```

`python3 -m ruff` 在当前 Homebrew Python 中未安装 module，但 workspace 的独立
`ruff` executable 可用并通过。全量绿测不改变上述确定性阻断的 verdict。

## 解除 BLOCK 的最低门槛

1. 为 `index/explain/compare` 建立统一 generation publisher：staging、generation ID、完整 validate、fsync、原子 current switch、失败不改变 current。
2. baseline 只从受控 current generation 读取，并在复用前对 core + modules/reading path/features/evidence/tutorials/codemaps/coverage 做完整合同验证；symbol/relationship 必须由当前 analyzer 结果或等价 source fingerprint 证明。
3. 扩展 secret gate 到 vendor-prefixed/generic credential assignments，新增负向 corpus，并在不确定时隐藏整段。
4. 对普通可写 tree 降级 freshness；complete 只允许固定 clean commit 或只读 filesystem snapshot。
5. manifest 与 file read 共用真正端到端的 entry/file/byte/deadline/cancel budget；fd no-follow + bounded read。
6. partial 默认不发布、不切 current、CLI 非零；仅在显式 opt-in 下产生清晰隔离的诊断产物。

在以上门槛满足并由新的独立 Agent 重放同一探针前，核心生产链保持 **REQUEST CHANGES / BLOCK**。
