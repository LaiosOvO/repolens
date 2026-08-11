# Skill 导出整改独立复审

复审日期：2026-08-10  
范围：`skill_export.py`、`skill_validation.py`、`persistence.py` 的相关安全支持、`test_skill_export.py`、`export-skill` CLI  
参考基线：本机 `skill-creator` 规范与 validator；Understand Anything 的消费型 Skill freshness 机制  
最终结论：**REQUEST CHANGES**  
架构状态：**BLOCK**

## 一句话结论

这轮整改已经解决固定 `SKILL.md` 模板、Markdown 注入、目标所有权、异常回滚、自校验、`agents/openai.yaml` 和 Git dirty/untracked 阻断等问题，但仍存在一个可复现的 symlink 越界写入 P0、一个真实仓可复现的不完整闭包 P1，以及 freshness 和 CLI 覆盖语义的 P1。因此目前不能标为生产可用。

## 阻断问题

### P0 — 深层祖先 symlink 可绕过边界检查并在词法目标之外写入或替换目录

证据：

- `src/repo_teacher/skill_export.py:346-351` 只检查 `target` 和 `target.parent`。
- `src/repo_teacher/skill_export.py:432-457` 随后对父目录执行 `mkdir`，并使用 `os.replace` 发布；两级以上的祖先 symlink 没有被检查。
- `src/repo_teacher/persistence.py:12-17` 的通用原子写入保护同样只检查目标及其直接父目录。

对抗场景：令 `root/link -> outside`，导出目标为 `root/link/nested/skill`。复审实际运行结果：

```text
VULNERABLE: exported .../link/nested/skill
outside skill exists True
```

影响：调用方看到的词法目标位于 `root/link/...`，实际写入发生在 `outside/...`。当 API 使用 `force=True` 时，这一缺陷还可替换词法边界之外的既有目录，具备数据破坏风险。

整改要求：对目标从可信边界到终点的每个已有路径组件执行 `lstat`/symlink 拒绝，并在创建父目录和每次 rename 前重新校验；测试必须覆盖“祖父级 symlink”“创建后换链”的竞争场景。仅检查终点和直接父目录不够。

### P1 — 导出的“闭包”仍包含真实的悬空引用

证据：

- `src/repo_teacher/skill_export.py:252-265` 将选中的 `file`、`module` 记录原样写入，但没有收缩或补齐这些记录内部的引用。
- `src/repo_teacher/skill_validation.py:205-226` 验证 symbol→file 与 file→module，却没有验证 `file.symbols[]` 和 `module.entrypoints[]`。
- `tests/test_skill_export.py:105-191` 只验证显式 feature/step/relationship/evidence 端点，没有覆盖 FileRecord 和 ModuleSummary 自带引用。

真实仓 smoke（对 Understand Anything 当前源码重新 build index 后导出全部功能）：

```text
payload 3 files 0 symbols
dangling file.symbols 124
dangling module.entrypoints 12
```

这说明 `validate_exported_skill()` 返回 PASS 不能证明 payload 是闭合子图；消费 Agent 读取 file/module 导航信息时会遇到不存在的实体或文件。

整改要求：二选一并强制验证：

1. 将 `file.symbols`、`module.entrypoints` 裁剪为 payload 内实体；或
2. 把它们引用的实体递归加入导出闭包。

validator 必须遍历所有携带 ID/路径的字段，而不是只验证 feature 主链。至少增加一个由真实 index 生成、能发现悬空 `file.symbols`/`module.entrypoints` 的回归测试。

### P1 — freshness 在 source 缺失和非 Git 新增文件时 fail-open

证据：

- `src/repo_teacher/skill_export.py:326-333` 在 `project.path` 缺失或路径不存在时直接返回，随后继续导出。
- `src/repo_teacher/validation.py:66-84` 只验证 index 已记录的文件；非 Git 目录新增加文件不会被发现。
- `src/repo_teacher/validation.py:136-143` 依赖 Git snapshot 的 dirty 状态发现未跟踪文件；非 Git 目录和 Git status 不可用时 `dirty=None`，没有相应的 fail-closed gate。

复审实际结果：

```text
missing-source EXPORTED
no-source EXPORTED
NON_GIT_NEW_FILE_EXPORTED ['feature_34b8e97bc4878283']
```

Git 仓库的未跟踪文件场景已正确阻断：

```text
UNTRACKED BLOCKED ValueError source repository has a dirty working tree
```

与 Understand Anything 的对照：它的消费型 Skills 明确检查 commit、committed diff、staged、unstaged 和 untracked 文件，并用测试锁定这些指令；Repo Teacher 对正常 Git dirty/untracked 更严格（直接阻断）是合理的，但对无法证明 freshness 的路径不应静默放行。

整改要求：生产 CLI 导出必须要求有效 `project.path`；路径缺失、source 消失、Git 状态未知均应明确失败。非 Git source 至少比较一次完整可索引文件集合/摘要，发现新增、删除、修改均阻断。

### P1 — CLI 提示使用 `force`，但 CLI 没有 `--force`

证据：

- `src/repo_teacher/cli.py:82-92` 的 `export-skill` parser 没有 `--force`。
- `src/repo_teacher/cli.py:334-348` 没有把 force 参数传给 `export_skill()`。
- `src/repo_teacher/skill_export.py:443-446` 的错误却要求用户 “use force to replace it”。

实际结果：`repo-teacher export-skill ... --force` 以 argparse code 2 失败。用户无法通过产品 CLI 执行实现已经支持、错误信息又明确要求的恢复/覆盖流程。

整改要求：增加显式 `--force`，只在用户写出该参数时传 `True`；帮助文案必须说明它会删除非 Repo Teacher 目录内容。增加 CLI 级“不带参数拒绝且保留文件 / 带参数成功覆盖”的测试。

## 非阻断但应在生产版前处理

### P2 — schema 仍允许无关字段原样进入 Skill reference

`_reference_payload()` 将 project、feature、module、file、symbol、relationship、evidence 记录整体复制，validator 只读取已知字段却不拒绝或剔除未知字段。固定 Skill 指令和 Markdown escaping 已防止数据直接进入 `SKILL.md`，这是明显改进；但任意 index JSON 中的额外 prompt-like 字段、秘密或巨型嵌套值仍会进入 `references/code-index.json`，扩大泄露、prompt injection 和资源耗尽面。

建议：按 payload schema 逐字段投影，并设置记录数、字符串长度和总输出字节预算；源代码 snippet 仍作为不可信数据保留，但未知字段默认丢弃或拒绝。

### P2 — 目录事务只覆盖 Python 异常，不具备进程崩溃恢复

`src/repo_teacher/skill_export.py:447-477` 的 staging/backup/rollback 能通过异常注入测试，正常进程内回滚可靠。但进程在“旧 target→backup”和“stage→target”之间被 kill 时，可能留下缺失 target、backup 和 stale lock；当前没有事务清单、启动恢复或目录 fsync。

建议：写入可识别的事务 marker，启动时在锁内恢复 stage/backup，并在 rename 后 fsync 父目录。若暂不实现，至少把 crash-recovery 明确列为已知限制，不能宣称 crash-safe。

## 已确认整改通过

| 历史问题 | 复审结果 | 证据 |
|---|---|---|
| 直接目标/目录内 symlink | 部分通过 | 目标本身和目标树内 symlink 均被拒绝；但深层祖先仍有 P0 |
| frontmatter 非法或可注入 | 通过 | `SKILL.md` 使用固定、数据无关模板；name/description 受本地 validator 约束 |
| Git dirty/untracked | 通过（Git 正常路径） | 实际 Git 未跟踪文件导出被阻断 |
| 显式关系端点闭包 | 通过 | relationship source/target、step、evidence、test evidence、artifact 主链均有 fail-closed 校验 |
| 重复请求 feature ID | 通过 | 请求列表稳定去重 |
| 目录 staging 与 Python 异常回滚 | 通过 | post-publish validation 注入失败后旧 Skill 完整恢复 |
| `agents/openai.yaml` | 通过 | 包含 display name、25–64 字符短描述、显式 `$skill-name` default prompt |
| 触发描述与渐进披露 | 通过 | description 覆盖 implement/review/explain 使用语境；正文 59 行并把数据移入 references |
| 导出后自校验与篡改检测 | 通过 | 固定文件集合 + SHA-256 manifest；修改 reference 后 validator 拒绝 |
| 官方 skill validator | 通过 | 对真实 Understand Anything 新鲜 index 的导出运行 `quick_validate.py`，结果 `Skill is valid!` |

注意：重复“请求参数”已去重，但重复“源 feature 记录”在无 source path 的 index 中仍被静默取第一条；它会随 freshness/source schema 的 fail-closed 整改一并解决，或应直接在 `_selected_features()` 中报错。

## 验证记录

```text
PYTHONPATH=src python3 -m unittest tests.test_skill_export -v
12 tests, PASS

PYTHONPATH=src python3 -m unittest discover -s tests -v
87 tests, PASS

ruff check skill_export.py skill_validation.py persistence.py test_skill_export.py
PASS

python3 -m compileall -q src tests
PASS

真实仓：fresh build_index(understand-anything) -> export_skill -> validate_exported_skill
导出成功；官方 quick_validate.py PASS；但闭包对抗检查发现 124 + 12 个悬空引用
```

现有测试全部通过不等于审计通过：当前测试没有覆盖上述深层 symlink、完整 record 引用闭包、source 缺失、非 Git 新增文件与 CLI `--force`。

## 达到 PASS 的最小条件

1. 修复深层祖先 symlink 越界，并增加竞争/祖先链测试。
2. 让所有导出记录的 ID 与路径引用闭合；真实 Understand Anything smoke 的 dangling 计数必须为 0。
3. freshness 对 source 缺失、Git 状态未知、非 Git 文件集合变化 fail-closed。
4. CLI 暴露安全、显式且有测试的 `--force`。
5. 重跑 87 项全量测试、官方 validator、真实仓闭包检查与本报告的所有对抗场景。

