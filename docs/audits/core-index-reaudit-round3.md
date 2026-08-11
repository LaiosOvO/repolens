# Repo Teacher Core Index 独立复审 Round 3

日期：2026-08-10  
复审角色：未参与 core round2 实现的独立 Agent  
复审对象：`docs/audits/core-index-release-verification.md` 中的旧 P0/P1，以及
`docs/audits/core-index-fix-round2.md` 的修复声明  
代码冻结点（默认配置 analysis fingerprint）：
`89a382491d82d64db5dbdbd09ac1e3271bd78d2f2a338e22de797d5d6a2a7133`

## 结论

**PASS — 本轮审计范围内，旧 P0/P1 已闭合，可以通过 core index 发布门。**

我逐条重放了完整重签的 Go、JavaScript、Python relationship poison、受控
generation provenance、root/current/immutable 三入口、非 current/mixed path、正常与异常
发布、`os._exit(23)` hard-kill、下一次锁恢复、partial/invalid 发布门、Waku 多级
receiver，以及真实 Waku/SourceBridge 的新 fingerprint cold-rebuild + disk-warm。

没有发现能够让伪造 relationship 通过 canonical validation 或进入 warm reuse 的路径；
没有发现 partial/invalid generation 替换 current；没有发现 current authority 指向不完整
generation；Waku `self.model.transcribe()` 错连本地 `Ears.transcribe` 的数量为 0。

Round8 teaching 修复改变了 analysis fingerprint。最终签发没有沿用旧 fingerprint 证据：
两仓旧 baseline 都以 `baseline_status=rejected` 被拒绝并全量重建，再由新 fingerprint
generation 完成真正 disk-warm。冻结点另外锁定：

```text
features.py           5d1c75dd6c1cdd58aa20113775b0dae97268b5a07044b3f2e3ff9a078c39ff24
capability_catalog.py a7ff739225e369a97644c635e8cbf88581a06e6d1904e095b619dc3c2c54506c
analysis fingerprint  89a382491d82d64db5dbdbd09ac1e3271bd78d2f2a338e22de797d5d6a2a7133
```

## 1. 旧 P0：完整重签 relationship poison

探针不是只改 JSON 后期待 checksum 报错，而是对每种语言各建一个真实仓库，先生成
合法 index，再加入不存在于源码的 `calls` relationship，同时重算：

- `stats.relationships`
- 每文件 `analysis_sha256`
- 每文件 `derived_sha256`
- 顶层 `integrity_sha256`
- manifest v2 的 artifact size、SHA-256、generation ID

最后用产品自己的 `GenerationPublisher` 发布，使 whole-generation reader 返回
`VerifiedPublishedJson`。结果如下：

| 语言 | poison `validate` | disk/current `validate` | warm baseline | reused / reanalyzed | warm 中伪边 | warm validation |
|---|---|---|---|---:|---:|---|
| Go | false，`canonical-source-claims-mismatch` | false，同码 | rejected | 0 / 1 | 0 | valid |
| JavaScript | false，`canonical-source-claims-mismatch` | false，同码 | rejected | 0 / 1 | 0 | valid |
| Python | false，`analysis-semantics-mismatch` + `canonical-source-claims-mismatch` | false，同码 | rejected | 0 / 1 | 0 | valid |

这闭合了旧报告中的关键绕过：攻击者即使能重算所有非密钥摘要，也不能把不存在于当前
源码 canonical analyzer 输出中的边包装成可信 warm baseline。

实现证据与复核重点：

- `src/repo_teacher/indexer.py::_baseline_rejection_reason()` 对受支持语言逐文件重跑
  canonical analyzer，并比较持久化正规化后的文件、符号和关系 claim。
- `src/repo_teacher/indexer.py::_baseline_publication_rejection_reason()` 要求 baseline
  是受控 reader 创建的 `VerifiedPublishedJson`，绑定当前 output、`index.json`、当前
  generation 和 source identity。
- derived artifacts 不复用：两仓 warm 的 `reused_derived_artifacts=False`。
- `src/repo_teacher/validation.py` 会 clean rebuild 并比较 canonical source claims；
  Python 另有逐文件语义重证。

## 2. Verified provenance 与三入口

合法 generation 上，以下入口读取结果逐字典相等，且类型均为
`VerifiedPublishedJson`：

```text
<output>/index.json
<output>/current/index.json
<output>/.repo-teacher-generations/<current-generation>/index.json
```

reader 在返回 payload 前验证 manifest v2 exact artifact set、每个 artifact 的 size 和
SHA-256、内嵌 generation ID，并进行 current-before/current-after 稳定性检查。

负向重放：

| 输入 | 结果 |
|---|---|
| 非 current immutable generation | `ValueError: immutable artifact is not the current generation` |
| `current/../.repo-teacher-generations/<old>/index.json` mixed path | 同上，拒绝 |
| 完整合法但属于另一 source identity 的 verified generation | baseline rejected，0 reused |
| 普通内存中的 structurally valid dict | baseline rejected，0 reused |
| 修改 current `index.json` 但不更新 manifest | `generation artifact digest/size boundary mismatch` |

因此“看起来像已签名 JSON”与“当前 output 下完整、当前、受 reader 验证的 generation”
已经分离；warm reuse 只接受后者。

## 3. root convenience links、故障与锁恢复

| 场景 | current authority | root convenience surface | 锁/恢复 |
|---|---|---|---|
| 正常 index 发布 | 切到完整新 generation | exact set `{index.html,index.json}`，均指向存在的 `current/*` | 下一 writer 可获取锁 |
| 正常 technology-selection 发布 | 切到完整新 generation | exact set `{technology-selection.html,technology-selection.json}`，无旧 index 残留 | 下一 writer 可获取锁 |
| compatibility reconciliation 中注入异常 | 保持旧 current | 回滚为旧 technology-selection 闭集，目标均存在 | 异常传播；锁可重取 |
| current switch 后、link reconciliation 前 `os._exit(23)` | current 已指向完整新 index generation | 进程刚死亡时旧 root 链可短暂 stale/broken；不是 authority | kernel 释放锁；下一 `OutputLock` 修为 exact `{index.html,index.json}`，清理 scratch，current 不回退 |

这里不把 hard-kill 窗口描述成不存在：root convenience links 不是和 current pointer
跨进程原子切换。通过条件是 current authority 始终完整，且下一 writer 在持锁工作前先恢复
root 闭集；重放满足该合同。调用方若要求 hard-kill 后、下一次写入前也绝无 stale link，
应直接使用 `current/<artifact>`，不要把 root convenience symlink 当 authority。

## 4. partial / invalid 不发布

对 `index`、`explain`、`compare` 各重放两种失败：partial result，以及所有摘要完整
重签但 canonical tutorial claim 伪造的 result，共 6 个用例。

```text
6 / 6: CLI rc=1
6 / 6: stderr 命中 pre-publication validation
6 / 6: current generation 未改变
6 / 6: root links 仍为旧的、完整且目标存在的 index 闭集
```

CLI 在 artifact 创建前验证一次，并在 `before_switch` 再验证一次；失败 artifact 没有成为
current，也没有暴露到 root convenience surface。

## 5. 真实 Waku：新 fingerprint rebuild + disk-warm

仓库：`/Volumes/T7/workspace/ontology/graph/repo/waku-agent`  
HEAD：`75b0a6d27a19009b0482c877def3eb124181f121`  
输出：`/tmp/repo-teacher-core-r3-waku-88558/output`

| 场景 | fingerprint baseline | wall | max RSS | reused / reanalyzed | validation |
|---|---|---:|---:|---:|---|
| 旧 generation 后首跑 | rejected | 6.36s | 211,779,584 B | 0 / 212 | 新 generation PASS |
| 新 generation disk-warm | compatible | 6.70s | 224,624,640 B | 212 / 0 | root/current 均 PASS，0 errors/0 warnings |

两代新 fingerprint generation 的十组 canonical JSON SHA-256 完全一致：

| 集合 | 数量 | SHA-256 |
|---|---:|---|
| files | 212 | `99496189deae109482033c0f481a7d7beb59164dc0e6b721b9a8a0e08053cf38` |
| symbols | 1,557 | `a02a04e2e683528f608999c8527203cf3dfda04b5ef6b7e2f05273f411073ac6` |
| relationships | 9,879 | `a7353fa0664b5d73c84e533c29e8385a581ac47e56a0982ca1222853392aeb41` |
| modules | 13 | `28a998af64ae5088734366d5062e365249be0f7cb60ba5e1f5f2faee06601f92` |
| reading_path | 12 | `45664c1e9e7cbe3ba2d5b67b1079bd12e8faadce4852e7ab502d101e14fa530a` |
| features | 6 | `b3bedbd891671d6d21a605adde5e88663bea1580c0cecbf19012c27904ac2a31` |
| evidence | 30 | `f107cabf5ce73ab7a778123a80abc98ff0e871c28cc98374578b41a3c9b14d38` |
| tutorials | 6 | `212244b8f727d73819b8fb5522b56910d68ce161c5aaeae9f67d3475949ec48a` |
| codemaps | 6 | `b1976e83610a02e663667996be08a2572ce8ad892e4640475e5bc2b617ff2dcb` |
| coverage | 6 | `cde8e53c84551c3d6ecf997e7e704f2b4307e3ba9ea1fca31c10b98b08fbb917` |

root links exact set 为 `{index.html,index.json}`，都指向存在的 `current/*`。

多级 receiver 精确探针：

```text
path                         waku/gateway/voice.py
relationship                rel_7c8ce5957801d856
source_id                   symbol_934ee7f1a2b66b96
target_name                 self.model.transcribe
target_id                   None
Ears.transcribe symbol      symbol_934ee7f1a2b66b96
false edges to that symbol  0
```

source 和 local method ID 恰好相同不构成自调用；关键是未知多级 receiver 保持
`target_id=None`，没有被名字回退误接到 `Ears.transcribe`。

## 6. 真实 SourceBridge：新 fingerprint rebuild + disk-warm

仓库：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`  
HEAD：`2a128bf0c8461fae91d2b424d9168ddf205bb11b`  
既有仓库状态：`D LICENSE`；复审没有恢复或改动参考仓  
输出：`/tmp/repo-teacher-core-r3-sourcebridge-90552/output`

| 场景 | fingerprint baseline | wall | max RSS | reused / reanalyzed | validation |
|---|---|---:|---:|---:|---|
| 旧 generation 后首跑 | rejected | 56.16s | 1,283,096,576 B | 0 / 1,575 | 新 generation PASS |
| 新 generation disk-warm | compatible | 67.99s | 1,305,051,136 B | 1,575 / 0 | root/current 均 PASS，0 errors；各有既有 dirty-worktree warning |

两代新 fingerprint generation 的十组 canonical JSON SHA-256 完全一致：

| 集合 | 数量 | SHA-256 |
|---|---:|---|
| files | 1,575 | `b8245ddb471105246fbf16c5a292ab248e128912906ab8d0e6d1f59646b40af3` |
| symbols | 13,956 | `b66eca5b7abfa2332ddd1382a733c5c6a65459a7842137da27ca703401fcbbbb` |
| relationships | 91,119 | `0af9c2d1b881286f1835646206f42e76b3cf22222fa05ea780a4e2d447e7e8c5` |
| modules | 21 | `4e798e6e9e47c5bc45531bc671ad848e9863ca71fbcd60ae2c98ffccadf6a489` |
| reading_path | 12 | `c3a0f2e26e2090ace184f734eb4ccf8d6285bf4b812594421fa2582e4c457d21` |
| features | 8 | `1d7bcb5c6cdb4d75124eb9fa3b82016eb166ac7e4cf5ce337b6dc89283b0ad25` |
| evidence | 40 | `19722167b94bb84b778d9c96b1bfdc124afbaae87b2a9831e15ee6d014d889d3` |
| tutorials | 8 | `b55ddf82fb35d525f51046f6bba5111cc4cffe6ccc579b7ddc9c37145d22a4dc` |
| codemaps | 8 | `689484b5138195428a6ed6348777b06362ca58430875206f0dd1a38fa68b858f` |
| coverage | 8 | `4f27e6860165677c07a1251bed39439a9b19f959df2ee735640b494fd717507a` |

root/current 都由 `VerifiedPublishedJson` reader 读取且相等；root links exact set 为
`{index.html,index.json}`，目标均存在。warm 仍重建 derived artifacts。

## 7. 摘要复杂度与 secret 探针

### 7.1 O(N) digest

构造 24 个 Python 文件，在 warm 时包装 `_file_analysis_digest` 计数：

```text
reused files            24
digest calls            48
unique paths            24
max symbols per call     1
max relationships/call  2
sum symbols             48
sum relationships       96
```

每个 path 在两个有界阶段各计算一次，调用只接收该 path 的局部 records，没有把全图传给
每文件 digest；工作量随总 records 线性增长，不是文件数乘全图大小。

### 7.2 secret

synthetic Python 源码中放入 Anthropic、AWS、GitLab、Slack 和 generic token 风格默认值。
落盘 JSON 对五种原文命中均为 false，`[REDACTED]` 出现 5 次；Python signature 只保留
redacted 值。Go 的普通 import alias `credentials=example/internal/credentials` 不被误删，
validation 通过。

真实 Waku 与 SourceBridge 的 `index.json` 另用 AWS access key、Anthropic、GitLab、
Slack、private-key header 正则扫描，五类命中均为 false。

## 8. 六仓采用矩阵：源码核对与未采用边界

这里的“采用”均指机制启发后由 Repo Teacher 独立实现，不声称复制参考仓源码。Waku 是
第七兼容 corpus，不混入六仓设计基准。

| 参考仓 / HEAD | 本轮核对的具体源码 | Repo Teacher 采用的机制 | 明确未采用 |
|---|---|---|---|
| SourceBridge `2a128bf0c846…` | `internal/livingwiki/orchestrator/fingerprint.go`、`incremental.go` | 将实现/config/source identity 纳入 fingerprint；完整 freshness envelope；用真实 1,575-file Go 仓做安全增量门 | 未复制 Go orchestrator、PR/publish、LLM wiki pipeline；本项目是本地 Python generation store |
| Understand Anything `fe8c5bc59171…` | `understand-anything-plugin/packages/core/src/fingerprint.ts` 的 `contentHash` / structural fingerprint，以及 `change-classifier.ts` | 内容 hash + structural fingerprint；缺 structural proof 时保守分类为 STRUCTURAL | 未采用 plugin、tree-sitter graph、前端或存储格式；完整 structural contract 目前仍以 Python AST 最强 |
| CodeBoarding `8c3f2218c3ec…` | `repo_utils/fingerprint_diff.py::BaselineUnavailable` / sidecar gate；`static_analyzer/incremental_orchestrator.py` 的 invalidate、reanalyze、merge/filter | baseline/sidecar 不完整则 full rebuild；按文件失效与合并；跨边界旧记录 fail closed | 未复制其 LSP/static analyzer cache；Repo Teacher 额外要求 current verified generation 和 canonical source reproof |
| OpenWiki `7531d615216…` | `src/agent/okf-middleware.ts` 的 `afterAgent` finalize/validate/sync；`src/agent/utils.ts` 的 interrupted/complete metadata 与 SHA snapshot | 发布前后完整性门、interrupted 不冒充 complete、内容快照 | 未采用其 agent runtime、OKF 文档协议、远端同步或 Markdown 生命周期 |
| deepwiki-open `4181daa5ebde…` | `api/services/codemap.py::_ground_citations()`，完成前以真实 source snippet 重定位并覆写 line range | teaching/codemap claim 必须落到当前源码证据，不能只信生成文本中的行号 | 未采用其 RAG/LLM pipeline、数据库、Web UI 或 citation 数据模型 |
| PocketFlow-Code2Tutorial `05b24cbbb0fe…` | `flow.py` 的 Fetch→Identify→AnalyzeRelationships→Order→Write→Combine；`nodes.py` 的 relation index/shape validation 与 `CombineTutorial` | 分阶段 teaching 流程、关系结构验证、组合前闭合章节/文件引用 | 未采用 PocketFlow runtime、LLM prompts、远端 fetch 或其 tutorial 输出 schema |
| Waku `75b0a6d27a19…`（兼容 corpus） | `waku/gateway/voice.py` | 暴露并验证 unknown multilevel receiver、current path 与 root link closure | 未采用 Waku voice/agent/memory 实现；不参与六仓选型排名 |

仓库身份在本轮再次用 `git rev-parse HEAD` 核对。除 SourceBridge 既有 `D LICENSE` 外，
其余六个参考/兼容仓未被本复审修改。

## 9. 冻结代码上的测试与静态门

```text
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_persistence tests.test_scanner tests.test_snapshot \
  tests.test_indexer tests.test_validation tests.test_cli tests.test_analyzers
=> Ran 121 tests in 69.051s — OK

PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
=> Ran 256 tests in 189.007s — OK (skipped=3)

ruff check src tests
=> All checks passed!

PYTHONPATH=src .venv/bin/python -m compileall -q src tests
=> exit 0
```

3 个 skip 是需要 Playwright/本地 Chromium 的可选浏览器断言；core、generation、warm、
Waku 与 SourceBridge 探针没有 skip。本轮真实实仓门和 CLI validate 均独立执行。

## 10. 非阻断剩余风险

以下边界真实存在，但不是本轮旧 P0/P1 的未闭合项：

1. warm 为安全执行 canonical reproof，并总是重算 derived artifacts；SourceBridge warm
   仍为 67.99s、约 1.31GB RSS，安全性通过不代表低成本。
2. immutable generation 当前 append-only，没有 retention/GC。
3. manifest SHA-256 是完整性 checksum，不是抵抗同权限恶意本地 writer 的 MAC 或签名。
4. 源码目录不是 MVCC snapshot；前后稳定性扫描可以检测常见并发变化，但不提供数学上的
   文件系统事务快照。
5. root convenience links 在 hard-kill 的窄窗口可短暂 stale；authoritative current
   generation 完整，下一 writer 会在工作前恢复。
6. validator 与 warm reproof 共享 analyzer 实现；它们能挡 payload 自签伪造，但不能证明
   analyzer 本身绝无共同逻辑错误。

这些风险应继续监控，其中性能与 generation GC 可作为后续工程项；它们不改变本轮
**PASS** 结论。
