# Skill 导出第二轮整改记录

日期：2026-08-10  
整改输入：`docs/audits/skill-export-reaudit.md`  
当前状态：**READY FOR INDEPENDENT RE-AUDIT（不自行判定 PASS）**

## 一句话结果

第二轮已针对复审中的全部 P0/P1 和两个 P2 补齐实现与对抗测试：发布根目录由逐层 `openat/O_NOFOLLOW` 与目录 inode 锁定，导出 payload 对所有内嵌引用做闭包验证，freshness 对 source 缺失、Git 状态未知和非 Git 文件集合变化 fail closed，CLI 提供显式 `--force`，并增加可恢复的目录发布事务。

## 整改对照

| 原复审问题 | 本轮实现 | 回归证据 |
|---|---|---|
| P0 深层祖先 symlink 可跨根写入 | `persistence.SecureDirectory` 逐层 `lstat/openat + O_NOFOLLOW`，持有父目录 fd 与 `(dev, ino)`；所有 rename 使用同一 `src_dir_fd/dst_dir_fd`；rename 后 fsync 并复核身份。只规范化位于不可写系统前缀中的 OS 别名（macOS `/var -> /private/var`），可写祖先下的 symlink 一律拒绝。 | `test_refuses_deep_ancestor_symlink_even_with_force`、`test_detects_parent_swap_to_symlink_before_publish`、`test_atomic_writer_refuses_deep_ancestor_symlink`。测试同时断言外部目录未出现 Skill。 |
| P1 `file.symbols` / `module.entrypoints` 悬空 | `_reference_payload()` 把选中 symbol 的 `parent_id` 递归纳入闭包；`file.symbols` 和 `module.entrypoints` 裁剪为 payload 内实体；模块统计按裁剪后的子图重算。`validate_skill_payload()` 逐项验证 file→symbol、module→entrypoint、symbol→parent/file/path 和双向 file ownership。 | fixture 闭包测试；`test_payload_validator_rejects_every_embedded_dangling_reference`；真实 Understand Anything fresh 全量导出测试。 |
| P1 source 缺失与非 Git 新文件 fail-open | `project.path` 缺失、不存在、symlink 直接失败；Git 仓要求 Git 元数据与 status 均可用且 clean；非 Git 仓重新扫描完整默认可索引集合，对路径集合和 SHA-256 做全量相等比较，新增、删除、修改均阻断。 | `test_export_skill_requires_an_existing_source_path`、`test_git_status_unknown_fails_closed`、`test_non_git_added_and_deleted_files_block_export`、原 stale-file 测试。 |
| P1 CLI 没有 `--force` | `export-skill --force` 明确透传；help 说明会替换目标全部非 Repo Teacher 内容；未指定时错误明确要求重新运行 `--force`。 | `test_export_skill_force_is_explicit_and_replaces_destination` 同时验证拒绝时用户文件保留、显式 force 后才替换。 |
| P2 任意字段/资源膨胀进入 reference | 所有 project/feature/module/file/symbol/relationship/evidence/artifact/step 按公开字段白名单投影；未知 prompt-like 字段默认丢弃；导出增加 250,000 条记录和 64 MiB JSON 总预算。 | fixture 注入未知 `prompt_injection` 与 `unknown_secret`，断言未进入 payload。 |
| P2 进程崩溃窗口 | 在替换前写同父目录事务 marker，记录 target/stage/backup；启动时在锁内恢复。target→backup 后崩溃会恢复旧 target；stage→target 后崩溃会验证新 Skill，再清理 backup；模糊或篡改状态 fail closed。每次目录 rename/unlink 均 fsync 父目录。 | `test_recovers_crash_between_backup_and_publish`；原 Python 异常回滚测试继续通过。 |

## 固定 Skill 契约保持不变

- `SKILL.md` 仍是数据无关固定模板。
- `agents/openai.yaml` 仍由固定模板产生，默认 prompt 使用显式 `$skill-name`。
- required file manifest 与 SHA-256 篡改检测保持启用。
- `references/code-index.md` 继续转义不可信文本。
- `--force` 只扩大“同一已锁定父目录内替换目标”的授权，不允许解析或跨越攻击者可控 symlink。

## 真实仓验证

对 `/Volumes/T7/workspace/ontology/graph/repo/understand-anything` 使用当前源码重新执行 `build_index()`，随后不传 feature filter 全量调用 `export_skill()`：

```text
source files: 457
selected features: 3 / 3
exported modules: 1
exported files: 3
exported symbols: 3
exported relationships: 0
exported evidence: 3
dangling refs: 0
validate_exported_skill: valid=True
official quick_validate.py: Skill is valid!
```

该真实仓断言已落入 `test_real_understand_anything_fresh_full_export_has_zero_dangling_refs`，不是一次性手工 smoke。

## 验证记录

整改后最后一次相关验证：

```text
PYTHONPATH=src python3 -m unittest tests.test_skill_export tests.test_persistence tests.test_cli -v
32 tests, PASS

ruff check src/repo_teacher/skill_export.py src/repo_teacher/skill_validation.py \
  src/repo_teacher/persistence.py src/repo_teacher/cli.py \
  tests/test_skill_export.py tests/test_persistence.py tests/test_cli.py
All checks passed!

python3 -m compileall -q src tests
exit 0

python3 .../skill-creator/scripts/quick_validate.py <fresh-understand-anything-export>
Skill is valid!
```

全仓测试已执行到 103 项；本轮负责的 32 项全部通过，但当时并行开发中的 Go analyzer、artifacts、features、module locator 和 report 仍有 11 项失败。它们不在本轮写权限内，因此本记录不把全仓状态误报为通过；主 Agent 集成其他模块后需要再次运行全仓测试。

## 交给独立复审 Agent 的重点

1. 重放 `root/link -> outside` 与“写完 stage 后把父目录换成 symlink”两个探针，确认 `--force` 也无法在 outside 创建或替换内容。
2. 对真实 fresh index 枚举 payload 中所有 ID/path 字段，确认悬空计数仍为 0，而不只依赖 validator 返回值。
3. 模拟 marker 的 pre-backup、post-backup、post-publish 状态，确认只执行可证明安全的恢复，篡改 marker fail closed。
4. 重新运行官方 validator 和主 Agent 收敛后的全仓测试。

