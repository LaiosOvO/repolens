# Skill 导出第四轮事务整改记录

状态：**新修复候选已完成专项验证，等待新的独立 Agent 复审；本文不自签 PASS。**

上一版候选被独立复审判定 `REQUEST CHANGES`。第一轮复审实际复现了
`assert_child_identity()` 与按名称 `unlink()` 之间的竞态：同名文件被替换后，
旧实现会删除替换体中的 `USER-DATA`。因此本候选没有继续修补“安全递归删除”，
而是删除自动清理/自动回滚这一整类行为。

append-only 候选的第二轮独立复审又复现了两个 BLOCK：COMMITTED 写入后仍可在
成功返回前篡改 public Skill；新建 state/workspace/stage 后仍有按 pathname 重开并
写入同名替换目录的窗口。本候选已继续整改，但这些整改仍须由新的独立 Agent 验证，
不能因为“不删除”就跳过成功返回前的完整性检查。

最终独立复审随后又复现：最后一次 validator 返回后、固定 manifest digest 期间注入
public `USER-DATA`，旧 digest 会忽略额外 entry 并返回成功。当前 digest 已改为自身执行
root/agents/references 的严格 closed-set 双快照与每项 inode 夹持；该项修复仍等待同一
reviewer 重跑确认。

## 当前安全合同

### 1. append-only transaction workspace

- 私有 state 只允许一个严格 marker 与符合精确命名合同的 transaction 目录。
- 每次发布保留唯一 transaction workspace，不做成功后 GC，也不删除旧 generation。
- `transaction.json` 与 `.repo-teacher-transaction.json` 是不可变 PREPARED 记录；
  后续状态分别写入不可变的 `phase-BACKED_UP.json`、`phase-PUBLISHED.json`、
  `phase-VERIFIED.json`、`phase-COMMITTED.json`。
- phase 文件必须连续、字段严格相同、phase 精确、规范化记录 hash 正确；phase 与
  现场的 `stage`/`backup` 闭集不一致时 fail closed。
- 任一未到 COMMITTED 的事务都阻止新导出，并返回保留现场的人工检查路径。

### 2. 不再自动删除或猜测恢复

- `SecureDirectory.unlink_verified`、`rmdir_verified`、Skill tree 删除器和事务清理器
  已删除；生产代码不再对 transaction、stage、backup 或旧 Skill generation 调用
  `unlink`/`rmdir`/`rmtree`。
- 导出失败时不自动 rollback。已经移动的 generation、当前 stage、backup 和全部
  控制记录都保留，并返回 transaction 路径。
- COMMITTED history 也永久保留。代价是磁盘占用随导出次数增长；在没有可证明的
  fd-relative 条件删除原语前，这是有意的安全取舍。

### 3. closed set 与身份贯穿

- workspace 与 stage 在创建后立即记录 `(device, inode, type)`；旧 public target
  也在移动前记录同一身份。
- state、transaction workspace、stage、`agents` 与 `references` 都先以随机名称创建，
  从创建时持有的目录 fd 写入完整内容，再用 no-replace rename 发布固定名称；创建、
  写入、校验阶段不按 pathname 重新打开可被同名替换的目录。
- `SecureDirectory.from_open_descriptor()` 直接接管创建时的 fd，并核对 pathname 仍指向
  同一 `(device, inode, type)`；若名称已被替换，替换体不被写入，操作 fail closed。
- transaction 嵌套 identity 只允许精确字段：`generation_id`、`marker_sha256`、
  `tree_sha256`；额外字段、错误长度、非小写 hex 均拒绝。
- `previous_owned`、`previous_entry_identity`、`previous_identity`、
  `previous_transaction_id` 与 `force_authorized` 必须严格自洽。
- 已提交事务形成单一 generation chain。子事务的 previous tree/entry 必须分别
  等于父事务的 new tree/stage entry；public target 必须等于 chain tail。
- workspace、state、stage、backup 的额外用户文件/目录、同名 inode 替换、FIFO、
  symlink、超大 control file 均保留并阻止后续操作。
- stage、backup、public target 与已提交 history 的内容读取均采用
  `identity -> content/hash/validator -> identity` 夹持，拒绝“先验 inode 相同、读取时
  已换成 clone”的竞态。

### 4. publication 与普通持久化

- Skill 发布的两个移动都使用内核 no-replace rename：macOS
  `renameatx_np(RENAME_EXCL)`，Linux `renameat2(RENAME_NOREPLACE)`；不支持的平台
  fail closed，不退化为会覆盖目标的 `os.replace`。
- `SecureDirectory.replace_to` 已禁止 existing-target replace，只允许
  expected-absent 的 no-replace publication，并在操作后核对 source/destination
  identity。
- 通用 `atomic_write_text` 对不存在目标使用 no-replace；对已有 regular file 使用
  内核 atomic exchange。被置换文件不会 unlink，而是保留为
  `.repo-teacher-retired-*`。竞态导致 identity 不匹配时，所有 entry 仍保持可达，
  并报告 staging/displaced 路径。
- Skill 控制文件和 staged Skill 文件不走覆盖式 atomic writer，而用
  `O_CREAT | O_EXCL | O_NOFOLLOW` 一次性创建。

### 5. `--force` 与 lock

- 已有 owned Skill 也必须显式 `--force`；记录中的 `force_authorized` 必须为 true。
- 非 owned、被篡改或与 committed tail 不一致的目录，即使 `--force` 也不会移动、
  覆盖或删除。
- `.repo-teacher.lock` 是永久 regular file。锁由 lockfile fd 与输出目录 fd 的
  `fcntl.flock` 持有，释放只 unlock/close，不按名称 unlink；进程退出后由内核
  提供 stale recovery。

### 6. bounded regular-file control plane

- private marker、transaction journal/marker/phase 必须是 regular file，最大 64 KiB，
  使用 `O_NOFOLLOW | O_NONBLOCK` 和 fd size 核对读取。
- exported Skill marker、payload、文本继续受 validator 的严格 schema、类型、大小、
  symlink 与特殊文件限制。
- generation digest 只遍历 validator 证明的固定 Skill 文件闭集，并通过 no-follow fd
  读取，不对未经证明的历史目录递归遍历或删除。digest 自身也对 root、`agents`、
  `references` 执行读前/读后 closed-set 双快照、目录/文件 entry identity 夹持与文件
  fd stat 稳定性检查，不能依赖更早一次 validator 的瞬时结论。

### 7. COMMITTED 后成功返回门槛

- 写入 `phase-COMMITTED.json` 后必须重新执行完整 `_inspect_transactions()`，重新验证
  private state/workspace 的严格闭集、连续 phase 链、generation chain 与 public tail。
- 新事务必须是 public history 的唯一 committed tail；随后再次运行 public Skill
  validator，并再次用创建时的 public entry identity 与 generation identity 夹持内容。
- COMMITTED 后注入 regular/FIFO、篡改 public `SKILL.md`、替换同名 public generation
  都必须使本次导出报错；不得返回旧的 `validation.valid=True`。

## 专项回归证据

2026-08-10 当前候选：

- Skill/persistence/CLI 专项：**63 tests PASS**（最新复跑 23.118s）。
- scoped Ruff：**PASS**。
- scoped compileall：**PASS**。
- 覆盖所有 phase 的现场：PREPARED/BACKED_UP/PUBLISHED/VERIFIED 均保留并阻止恢复；
  COMMITTED 可作为合法 history tail 继续显式 force 导出。
- 覆盖 state/workspace 额外用户目录、workspace/stage/backup 同名替换、嵌套 identity
  额外字段、伪造 phase 与物理现场不一致。
- 覆盖 target 原本不存在时的抢占竞态、ownership-check 后 target 替换、parent
  symlink swap、post-publish failure 双 generation 保留。
- 覆盖 state/workspace/stage 在创建后被同名替换：替换目录只保留测试写入的
  `USER-DATA`，不会收到 marker、journal 或 staged Skill；工具创建体与替换体都保留。
- 覆盖 COMMITTED 后 public Skill 篡改以及 private state regular/FIFO 注入；本次调用
  必须在返回前重新复验并失败，不能返回 stale success。
- 覆盖完整 history 检查刚返回后再注入 private state，以及 control JSON 读取过程中
  同名 regular file 被替换；最终闭集复查与 file identity 夹持必须保留替换体并失败。
- 覆盖 `_tree_digest()` 内部 validator 刚返回后注入 public `USER-DATA`；digest 自身必须
  以 `unexpected closed set` 失败，且用户文件仍保留。
- 覆盖永久 flock、lockfile 名字替换、普通 atomic writer exchange 时并发用户替换；
  断言 `USER-DATA` 仍可从明确路径读取；子进程持锁后直接退出也能由内核安全恢复。
- 覆盖 journal/marker 超大文件与 FIFO，validator 不阻塞。
- fd-relative 重构后的真实 Understand Anything CLI 冷索引：**457 files、904 symbols、
  3731 relationships、11 modules**；导出 **3 features、3 files、20 evidence**。
- 内部真实 UA 回归：**PASS**；官方
  `skill-creator/scripts/quick_validate.py`：**`Skill is valid!`**。最新 CLI 探针现场保留在
  `/tmp/repo-teacher-round4-closed-set.KrwkNf`。

并行 teaching/ground-truth 工作流稳定后，全量仓库最新复跑：**213 tests PASS**
（154.338s）。

## 独立复审门槛

新的 reviewer 必须独立尝试：

1. 在检查与 rename/exchange 之间替换 source、target、stage、backup、lock 名称；
2. 给 state/workspace 和各 phase 现场加入额外目录、特殊文件、超大 JSON；
3. 伪造合法自 hash 但不符合现场的 phase，或篡改 generation chain；
4. 证明不存在任何 Skill transaction 自动 unlink/rmdir/rmtree 路径；
5. 在 COMMITTED 写入后篡改 public target 或 private state，确认当前调用不能成功返回；
6. 在新建 state/workspace/stage 后替换同名目录，确认替换体不被工具写入；
7. 重跑真实 Understand Anything export 与官方 Skill validator。

reviewer 若仍为 `REQUEST CHANGES`，本模块继续保持未完成状态。
