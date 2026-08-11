# 核心索引最终复审：Architect 反方通道

审计日期：2026-08-10（Asia/Shanghai）  
审计角色：独立 Architect，只读反方复验  
审计范围：`scanner.py`、`indexer.py`、`snapshot.py`、`evidence.py`、`validation.py`、`persistence.py`、`cli.py` 与核心专项测试  
**Architectural Status：BLOCK**

## 结论先行

当前实现已经关闭旧审计中的大部分底层缺陷：凭据展示脱敏、Python 结构指纹、扫描器预算计数、输出目录 containment、SourceBridge Go 冷/暖复用、永久 `flock` 与 `os._exit` 恢复均有实际证据。

但是生产发布门仍不能放行。本轮独立复验确认：

1. `validate_index()` 仍可给伪造的 symbol 类型、凭空关系、tutorial 和 codemap 签发 `valid=True`；无变化 warm baseline 还能把伪造的派生产物继续复制并由 CLI 成功发布。这是旧 P0“可信验证/claim gate”没有完整关闭。
2. `index`、`compare`、`explain` 仍逐文件发布。第二个文件写失败会留下“新 JSON + 旧 HTML”，没有 generation ID，也没有单一原子 current switch。
3. CLI 会把 `partial-unvalidated` 结果按成功产物发布并返回 0。
4. `capture_tree_manifest()` 不执行 `max_entries`、deadline 或 cancellation；它在每次受预算扫描前后无界遍历整棵树，使扫描预算不能成为端到端资源上限。
5. 非 Git 一致性仍只是 race detector。最终 manifest 之后新增文件可被漏掉，但结果仍标成 `freshness=complete`。

因此本通道不是“有风险但可上线”的 WATCH，而是 **BLOCK**。

## P0：验证门与 warm baseline 仍接受可重算摘要的伪造语义

### 代码证据

- `src/repo_teacher/indexer.py:124-319` 的 `_baseline_rejection_reason()` 检查 file/symbol/relationship 的形状、闭包、稳定 ID 和有限源码包含关系，但不重新证明 analyzer 语义。
- `src/repo_teacher/indexer.py:224-259` 对 Python symbol 的 grounding 只要求按声明字段重算 ID，且 `name` 出现在所声明行区间。把真实 `function helper` 改成 `class helper` 仍满足该条件。
- `src/repo_teacher/indexer.py:295-318` 对 relationship 只检查 endpoint、path、line 与 dataclass 形状；不检查 relationship ID 合同，也不证明源码中存在该调用/导入/包含边。
- `src/repo_teacher/indexer.py:1055-1085` 只要求派生集合是 list 且源文件无变化，就允许复用 `modules/reading_path/features/evidence/tutorials/codemaps/coverage`。
- `src/repo_teacher/indexer.py:1258-1267` 随后直接深拷贝这些 baseline 派生产物。
- `src/repo_teacher/validation.py:525-544` 虽将 `tutorials`、`codemaps` 纳入集合和重复 ID 检查，但后续没有对两者执行 schema、feature/step/evidence/graph 闭包或确定性内容验证。
- `src/repo_teacher/validation.py:642-727` 对 symbol/relationship 重复了上述有限检查，仍不重证 analyzer 语义或 relationship ID/source slice。
- `src/repo_teacher/cli.py:145-152` 构建后直接写盘，没有在发布前调用 `validate_index()`；即使调用，当前 validator 也不能拦住下面三类伪造。

### 独立探针

同一份非 Git `a.py` 只有：

```python
def helper():
    return 1
```

探针把真实 symbol 的 `kind` 从 `function` 改成 `class`，按现有合同重算 symbol ID、更新 file membership 和关系 endpoint，再重算 `integrity_sha256`：

```text
validator_valid=True
issues=[]
warm baseline_status=compatible
warm kind=class
warm reused_files=1
```

向同一索引加入源码中不存在的自调用关系：

```text
id=rel_fabricated
source=helper, target=helper, kind=calls, line=1
validator_valid=True
warm baseline_status=compatible
fake_in_warm=True
warm_valid=True
```

将一个真实入口索引的 `tutorials`、`codemaps` 整体替换为任意 JSON 对象并重算摘要：

```text
valid=True
issues=[]
```

最后，把合法 feature 的 title/summary 改成伪造运行时主张并重算摘要，然后通过真实 CLI 再执行一次无变化索引：

```text
cli_rc=0
baseline_status=compatible
reused_derived=True
published_title=FORGED BASELINE CLAIM
published_valid=False
published validation code=feature-claim-mismatch
CLI announced success=True
```

这证明 feature 自身的 claim validator 已经有用，但它没有被用于 baseline 接纳或发布门；更底层的 symbol/relationship 与 tutorial/codemap 则连显式 `validate` 都可通过。

### 生产验收门槛

- 为 symbol/relationship 增加 analyzer 级真实性合同；至少校验 relationship 的确定性 ID、kind/analyzer 组合和其源码 slice，不能只做引用闭包。
- 为 tutorials/codemaps 增加严格 schema、稳定 ID、feature/step/evidence/symbol/relationship 双向闭包和可确定重建内容校验。
- baseline 复用前必须验证所有将被 copy-forward 的集合；不能只验证 core 后信任 derived。
- CLI 发布前必须对最终内存产物和 staging 后磁盘产物都执行完整 validator，并拒绝任何 error。
- 如果允许跨信任边界导入 baseline，checksum 不能作为认证；需要受控 generation 来源或 MAC/签名。当前 `integrity_boundary` 对这一点的文字说明是正确的，但执行链仍把可编辑的 `index.json` 当成可复用 generation。

## P1：跨文件 publication 不是 generation transaction

### 代码证据

- `src/repo_teacher/cli.py:134-152` 先原子替换 `index.json`，再替换 `index.html`。
- `src/repo_teacher/cli.py:200-224` 的 compare 依次发布多个项目 JSON/HTML 和总 comparison JSON/HTML，故障窗口更大。
- `src/repo_teacher/cli.py:275-293` 的 explain 依次发布 index、module JSON、module HTML。
- `src/repo_teacher/persistence.py:366-440` 只保证单文件 publication；`OutputLock` 只串行化合规 writer，不能把多个文件变成一个原子 generation。
- 索引和 HTML 都没有共同 `generation_id`，也没有 staging directory + fsync + validated manifest + atomic current pointer。

### 独立故障注入

先生成一版 JSON/HTML，修改源码，再令第二次 index 的 HTML writer 抛错：

```text
initial_rc=0
failure_rc=1
json_changed=True
html_changed=False
old_json_source_sha != new_json_source_sha
retired_json_count=1
generation_id_present=False
```

`atomic_write_json()` 正确保留了旧 JSON inode，但用户默认路径已经指向新 JSON，而 HTML 仍是旧版；当前可见结果是确定性的混合 generation。

### 生产验收门槛

一次命令的全部产物必须写入唯一 staging generation，完整 fsync、验证并写入共同 generation ID/manifest 后，只通过一个原子 current switch 对外可见；失败不得改变上一 current。`compare` 和 `explain` 必须使用相同协议，而不是只修 `index`。

## P1：partial 结果仍按成功产物发布

`src/repo_teacher/indexer.py:1103-1121,1168-1188` 能正确把不完整扫描标成 `partial-unvalidated`；baseline 和 validator 也会拒绝它。但 `src/repo_teacher/cli.py:145-170` 不检查 `scan_complete/freshness`，仍写盘、打印 `Generated repository index` 并返回 0。

故障隔离探针令 `build_index()` 返回明确 partial 结果：

```text
rc=0
published_json=True
published_html=True
announced_generated=True
```

生产门必须默认 fail closed：partial 只可进入隔离诊断 generation，不能切换 current，也不能以成功状态返回。若以后提供显式 `--allow-partial`，其文件名、HTML 顶部状态、CLI exit/status 和 baseline eligibility 都必须与完整产物分离。

## P1：tree manifest 绕过扫描预算

`src/repo_teacher/scanner.py:126-173` 的 `capture_tree_manifest()` 接收 `ScanOptions`，但只使用 excluded paths/dirs；没有调用 cancellation，没有 deadline，也没有 max entries/files/bytes 计数。`src/repo_teacher/indexer.py:936,1252-1254` 在有界 scanner 之前和最终稳定性门中多次调用该无界遍历。

20-entry 探针设置 `max_entries=1`、`cancelled=lambda: True` 和近零 deadline：

```text
lstat_calls=20
returned_digest=True
cancellation_or_budget_honored=False
```

因此 scanner 的预算单测虽然通过，端到端 `build_index()` 仍可能在 manifest 阶段无界耗时。manifest 必须共享同一个 deadline/cancel token 和 visited-entry budget；到界应返回显式不完整状态而不是一个看似正常的 64 位摘要。

## P1：非 Git snapshot 仍是 best-effort，却标成 complete

`src/repo_teacher/indexer.py:499-524` 的注释诚实说明它“不声称 filesystem snapshot isolation”。但最终顺序是 verification scan → snapshot → final manifest → final snapshot → return；在 final manifest 之后、final snapshot 返回前后新增非 Git 文件，`ProjectSnapshot` 没有 commit/tree identity，无法反映变化。

独立探针在第三次 `capture_snapshot()` 读取完 metadata 后新增 `late.py`：

```text
build_succeeded=True
late_exists=True
late_indexed=False
freshness=complete
scan_complete=True
```

这不是再加一次 manifest 就能消除的理论窗口。生产合同应二选一：

- 对要求“可信 complete”的任务使用固定 clean Git commit、只读副本或文件系统 snapshot；或
- 对普通非 Git 可写目录显式输出 `best-effort-race-detected` 一类 freshness/isolation 字段，不把它与不可变 snapshot 的 `complete` 混为一谈。

`validate_index()` 也只是再次抽样当前树，不会把非 Git 目录升级为原子 snapshot。

## 旧 P0/P1 关闭矩阵

| 旧审计项 | 本轮判定 | 证据/说明 |
|---|---|---|
| remote credential | PASS | `snapshot.py:51-84`；URL 与 SCP-like 专项测试通过。 |
| evidence secret display | PASS | `evidence.py:10-49`；secret corpus 与普通代码负向测试通过。 |
| fabricated exact feature | PARTIAL / BLOCK | 直接 feature mutation 可被 validator 拒绝；symbol/relationship/tutorial/codemap 和 baseline copy-forward 仍可绕过。 |
| rehashed baseline 语义注入 | FAIL | 错误 symbol kind、伪造 call edge、伪造 derived artifact 均可接纳；见 P0。 |
| mixed source snapshot | PARTIAL / BLOCK | 多重 manifest 缩小窗口；非 Git 不具原子 snapshot，且仍标 complete。 |
| structure fingerprint | PASS | Python return/base/property/import 合同已纳入；其他 analyzer 保守 structural。 |
| partial publication | FAIL | 标记正确，但 CLI 仍发布并返回 0。 |
| scanner resource budgets | PARTIAL / BLOCK | scanner 本体通过；manifest 路径无界。 |
| output ancestor/self | PASS | `indexer.py:917-924` 拒绝 root/ancestor，descendant/sibling 测试通过。 |
| stale lock / crash recovery | PASS | permanent directory+file `flock`；独立 `os._exit` 后同 inode 重获锁。 |
| cross-file generation transaction | FAIL | 确定复现新 JSON + 旧 HTML。 |

## 已通过的独立证据

### 核心专项

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_scanner tests.test_indexer tests.test_snapshot \
  tests.test_evidence tests.test_validation tests.test_persistence tests.test_cli -v

Ran 70 tests in 59.639s — OK
```

这些测试证明已有合同没有回退，但当前测试集没有覆盖本报告的 generation、derived baseline、伪造关系、tutorial/codemap 和无界 manifest 探针。

### permanent flock / `os._exit`

独立子进程持锁后直接 `os._exit(0)`：

```text
child_rc=0
permanent=True
inode_stable=True
reacquired=True
```

该旧 P1 已关闭。`src/repo_teacher/persistence.py:443-513` 的释放路径只 unlock/close，不删除锁名；目录 fd 与 lockfile fd 双锁也阻止合规 writer 用替换 lock 名绕过。

### SourceBridge 冷/暖一致性

真实源：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`，cold 后经 JSON round-trip 作为 warm baseline：

```text
cold: 1575 files, 13956 symbols, 91119 relationships, 21 modules, 8 features
warm: baseline_status=compatible, reused=1575, reanalyzed=0
cold validate: valid=True, errors=0
warm validate: valid=True, errors=0
```

以下集合的规范 JSON SHA-256 冷暖逐项相等：

```text
files, symbols, relationships, modules, reading_path,
features, evidence, tutorials, codemaps, coverage
```

这确认 Go round5 与 warm ownership/内容一致性没有回退；它不能抵消 validator 和 publication 的系统级阻断。

## 最终判断

**Architectural Status：BLOCK。**

解除本通道 BLOCK 的最低条件是：

1. 关闭 P0 真实性缺口，并对上述四类 rehashed forgery 建正式回归测试；
2. 为 index/compare/explain 实现同一套原子 generation publication，并重放第二文件失败与进程崩溃探针；
3. partial 默认不切换 current、不返回成功；
4. manifest 与 scanner 共用资源预算；
5. 明确区分非 Git best-effort 一致性与不可变 snapshot 的可信 freshness；
6. 再执行 SourceBridge fresh cold、磁盘 warm、最终落盘 validator 和完整核心专项。

在这些条件完成前，核心索引可作为功能候选继续迭代，但不能以“生产级可信索引与报告发布链”签发 PASS。
