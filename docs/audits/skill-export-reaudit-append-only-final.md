# Skill Export append-only 最终独立复审

复审日期：2026-08-10  
复审角色：未参与本模块实现的只读审计者  
复审对象：`skill_export.py`、`persistence.py`、`skill_validation.py` 及相关测试  
最终结论：**PASS**  
生产门禁：**本轮要求范围内解除 BLOCK**

## 一句话结论

当前候选满足本轮 append-only 与 fail-closed 合同：Skill transaction 没有自动删除或覆盖式发布路径；永久 `flock` 在 `os._exit` 后由内核释放；事务只追加不可变的 `PREPARED → BACKED_UP → PUBLISHED → VERIFIED → COMMITTED` 事件；public/private/workspace/stage/backup、控制 JSON、phase/hash/force/chain 的静态篡改及已覆盖竞态均失败关闭，并保留现场。真实 Understand Anything 冷索引、全 feature 导出、内部闭包验证和官方 validator 均通过。

复审期间我先在旧候选上独立复现了一个真实阻断：最后一次 validator 返回后加入 public `USER-DATA`，旧 `_tree_digest()` 因只哈希固定 manifest 而返回成功。最新候选加入 held-dir-fd 的严格 closed-set 双快照、逐文件 inode/内容/inode 夹持后，我重放同一探针，结果改为失败关闭且 `USER-DATA` 保留。该修复是本次 PASS 的必要条件，不是仅凭既有测试推断。

## 复审基线

完整阅读并交叉核对：

- `docs/audits/skill-export-reaudit.md`
- `docs/audits/skill-export-fix-round2.md`
- `docs/audits/skill-export-fix-round3.md`
- `docs/audits/skill-export-fix-round4.md`
- `src/repo_teacher/skill_export.py`
- `src/repo_teacher/persistence.py`
- `src/repo_teacher/skill_validation.py`
- `tests/test_skill_export.py`
- `tests/test_persistence.py`
- `tests/test_cli.py`

最终判断以复审结束时的最新工作树和独立重跑为准；round 4 整改记录里“全量 202 项仍有 4 项失败”的历史说明已经过期，本次最新全量结果是 **213/213 PASS**。

## 核心合同逐项结论

| 合同 | 结论 | 独立证据 |
|---|---|---|
| 不自动删除用户或事务数据 | PASS | 对三个生产文件做 AST/文本扫描：没有 `unlink`、`rmdir`、`rmtree`、`os.replace`/`Path.replace` 调用；唯一 `.replace()` 是字符串去 NUL。失败路径只报告保留的 transaction。 |
| Skill 发布不覆盖已有 entry | PASS | `SecureDirectory.replace_to()` 只接受 `expected_target=None`，最终使用 macOS `RENAME_EXCL` / Linux `RENAME_NOREPLACE`；新控制文件使用 `O_CREAT | O_EXCL | O_NOFOLLOW`。 |
| 普通持久化不丢失被置换文件 | PASS | 已有普通文件走 atomic exchange，但 displaced inode 随后保留为 `.repo-teacher-retired-*`；竞态失败也保留 staging/displaced 路径。它会改变 live 文件名指向，但不是 destructive overwrite。 |
| 永久锁与异常退出恢复 | PASS | 独立子进程持锁后 `os._exit(0)`：返回码 0，lockfile 仍是同一 inode，下一进程重新获得锁；目录 fd 与 lockfile fd 双 `flock` 防止合规 writer 通过替换锁名绕过。 |
| append-only phase 链 | PASS | 独立连续导出两次：保留两个 transaction；每个都有 PREPARED marker/journal 和四个不可变 phase 文件，第二个永久保留前一 generation 的 `backup`，public validator PASS。 |
| phase/hash/force/chain 严格性 | PASS | exact schema、规范 hash、连续 phase、`previous_*`/`force_authorized` 自洽、单根无分支 generation chain 均受验证；伪造 hash、phase、force、物理现场不一致及 chain 篡改的定向测试通过。 |
| state/workspace/stage 同名替换 | PASS | 我在 COMMITTED 后把整个 state 同名替换为含 `USER-DATA` 的目录，调用失败关闭，替换体和原 transaction 均保留；现有创建期 workspace/stage/state race 测试也证明工具不会写入替换体。 |
| control JSON name/content 竞态 | PASS | `_read_json_child()` 执行 entry identity → fd content/size → entry identity；读取期间同名替换会失败且新旧文件都可达。FIFO、symlink、超过 64 KiB 和 schema/hash 篡改均失败关闭。 |
| public/backup/stage 内容与闭集 | PASS | `_tree_digest()` 在 root/agents/references 上做读前、读后 exact closed-set snapshot，逐文件通过 held dir-fd、`O_NOFOLLOW`、inode/size/mtime/ctime 稳定性夹持读取。 |
| COMMITTED 后 public 篡改 | PASS | 重放此前阻断探针：在最终 validator 返回后注入额外 public 文件，当前调用以 `Skill generation content identity changed` 失败；注入文件仍在，官方 validator 也正确拒绝该现场。 |
| COMMITTED 后 private state 篡改 | PASS | marker 原位改写、marker 同名替换、state 目录同名替换、regular/FIFO/extra-entry 注入均失败关闭并保留数据；history 还会完整复读一遍，再复查 private marker、closed set 和 public tail。 |
| 成功返回前完整复验 | PASS | COMMITTED 后先完整 `_inspect_transactions()`，再跑 public validator 与 generation identity，最后再次完整 `_inspect_transactions()` 并确认新 transaction 是唯一 tail。 |
| source freshness | PASS | source 缺失/不完整、Git identity 降级、dirty/status unknown、非 Git 新增/删除/修改均有 fail-closed 测试；真实 UA 冷索引在发布前后重复 freshness gate 通过。 |
| 闭包与预算 | PASS | 内部 payload validator 验证 feature/module/file/symbol/relationship/evidence 双向闭包；独立 250,001 records 和超过 64 MiB JSON 探针分别触发明确 `ValueError`。 |

## 关键实现证据

1. `skill_export.py:733-812` 的 `_closed_set_snapshot()` 与 `_read_identity_file()` 把“目录闭集”和“文件内容”都绑定到 held fd 与具体 inode，而非只依赖早先的 pathname validator。
2. `skill_export.py:815-892` 的 `_tree_digest()` 对 Skill root、`agents`、`references` 做前后双快照；固定文件读取后再次验证 exact entry set，修复了旧候选忽略新增 entry 的缺陷。
3. `skill_export.py:1079-1131` 对 private control file 和目录 closed set 执行 entry-content-entry/entry-set-entry 夹持，特殊文件不会被阻塞读取。
4. `skill_export.py:1213-1385` 验证 workspace 物理现场、不可变 phase、单链 history、private marker、state closed set 和 public tail，并在返回前复读全部 transaction。
5. `skill_export.py:1572-1622` 按顺序只追加五个 phase，COMMITTED 后执行两轮 history/tail 检查，中间再跑 public validator 和 generation identity。
6. `persistence.py:27-76` 是 kernel-enforced no-replace；`persistence.py:443-513` 的永久双 `flock` 仅 unlock/close，不删除 lockfile。
7. `skill_validation.py:391-497` 对正式 Skill 的 marker schema、exact file set、类型/大小、manifest hash、payload digest、固定模板与 payload 闭包执行完整校验。

## 独立对抗结果

### 1. 旧缺陷复现与最新修复确认

旧候选的精确探针结果：

```text
RESULT=SUCCESS validation=True
EXTRA_EXISTS=True
official validator: FAIL unexpected:USER-DATA
```

最新候选重放同一时序：

```text
RESULT=FAIL OSError ... Skill generation content identity changed
EXTRA_EXISTS=True
official validator: FAIL unexpected:USER-DATA
```

这证明产品不再返回 stale success，同时不删除并发写入的用户 entry。

### 2. state/private marker 同名或内容替换

三种独立探针均为失败关闭：

- COMMITTED 后整个 state 目录被移走、同名放入 `USER-DATA` 目录；
- private marker 原 inode 内容改写；
- private marker 被同名 regular file 替换。

所有探针中替换体保持可读；原 transaction 也仍在被移走的目录中，没有自动清理。

### 3. append-only 成功链

连续执行初次导出与显式 force 导出：

```text
transactions: 2
transaction #1: PREPARED + BACKED_UP + PUBLISHED + VERIFIED + COMMITTED
transaction #2: PREPARED + BACKED_UP + PUBLISHED + VERIFIED + COMMITTED + backup
public validation: True
permanent lockfile: True
```

### 4. `os._exit` 锁恢复

```text
child rc: 0
permanent lockfile: True
same inode after reacquire: True
reacquired: True
```

## 真实 Understand Anything 验证

源仓：`/Volumes/T7/workspace/ontology/graph/repo/understand-anything`  
方式：新临时目录、当前代码重新 `build_index()`、选择全部 feature、全新 export；没有复用旧导出。

```text
index: 457 files, 904 symbols, 3731 relationships, 11 modules, 3 features
selected/exported: 3 / 3 features
export payload: 3 files, 1 module, 20 evidence
validate_skill_payload: PASS, 0 dangling reference
validate_exported_skill: valid=True
official skill-creator quick_validate.py: Skill is valid!
```

这里 `0 symbols / 0 relationships` 是本次三个已识别 feature 的真实闭包结果，不是漏导：其 steps/evidence 指向 3 个文件且没有 symbol/relationship ID；内部 validator 对所有实际携带的 ID/path 仍执行闭包校验。

## 验证命令与结果

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_skill_export tests.test_persistence tests.test_cli
63 tests, PASS

PYTHONPATH=src python3 -m unittest discover -s tests
213 tests, PASS (172.040s)

PYTHONPATH=src python3 -m compileall -q src/repo_teacher
PASS

ruff check skill_export.py persistence.py skill_validation.py \
  test_skill_export.py test_persistence.py
PASS
```

另外独立执行：真实 UA cold export、官方 validator、旧 race 重放、state/marker replacement、append-only 双 generation、`os._exit` lock recovery、250,001-record 与 64 MiB byte budget；结果均符合预期。

## 运维代价与必须接受的限制

本轮 PASS 不是“零成本”的结论。当前安全模型有以下明确代价：

1. **磁盘只增不减。** 每次成功 force 导出永久保留 transaction、phase 和上一 generation backup；空间大致随导出次数 × Skill 大小线性增长。
2. **历史扫描越来越慢。** 每次导出会两次遍历完整 committed chain，并反复验证 retained backup/public generation；历史越长，延迟越高。
3. **任何异常都需要人工处理。** PREPARED/BACKED_UP/PUBLISHED/VERIFIED 未完成现场、额外 entry 或任何可疑 state 都阻止以后导出；产品不会猜测回滚或自动清理。
4. **lockfile 永久存在。** 这是设计，不是 stale lock；不可用“文件存在”判断是否有活跃 writer，必须尝试 `flock`。
5. **锁是 advisory。** 它可靠协调所有遵循协议的 Repo Teacher writer；同 UID 的非协作进程仍可直接改文件，产品通过成功返回前多轮完整性检查来 fail closed，但无法让普通可写目录成为内核不可变快照。
6. **平台限制。** no-replace/exchange 依赖 macOS/Linux 原语；其他平台会 fail closed，不能静默降级为覆盖式 rename。
7. **保留数据具有合规成本。** backup 和 retired file 可能长期保留源码派生内容。上线前必须定义容量告警、保留期限和经过单独审计的离线管理流程；不能把普通递归删除直接接回在线导出事务。

## 最终判定

**PASS。** 本轮没有发现仍可让产品自动删除/覆盖用户数据、绕过 append-only history、在已覆盖的 COMMITTED 竞态后返回 stale success，或导出不新鲜/不闭合 Skill 的阻断问题。

建议将本报告作为 Skill export 当前生产候选的审计基线。后续若修改 `_tree_digest()`、`_read_json_child()`、`_inspect_transactions()`、`SecureDirectory.replace_to()`、`OutputLock` 或引入 history GC，必须重新执行本报告的 race 探针与真实 UA 验证；尤其不能删除 closed-set 的读后快照，也不能在在线事务中恢复按名称递归清理。
