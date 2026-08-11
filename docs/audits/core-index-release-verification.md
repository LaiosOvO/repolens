# 核心索引与多文件发布最终独立验收

验收日期：2026-08-10  
验收角色：未参与本轮实现的独立 verifier  
验收范围：`scanner.py`、`snapshot.py`、`indexer.py`、`validation.py`、
`persistence.py`、`cli.py`、`models.py`、`evidence.py`，以及核心/全量测试、
SourceBridge 与 Waku Agent 真实仓库  
验收约束：除本报告外未修改产品、tests、examples 或参考仓库

## 最终结论

**Verdict：REQUEST CHANGES**  
**Production release status：BLOCK**

多文件 generation transaction 本身已经实质关闭旧 P0：`index`、`explain`、
`compare` 任一 staging 写入失败时，旧 `current` 与旧 generation 的全部 artifact
保持不变；并发 writer、`os._exit`、manifest digest、partial/invalid 发布门也通过。

但本轮发现两个此前回归测试没有覆盖的确定性生产问题：

1. **P0：完整重签后的 Go/JavaScript analyzer 伪记录仍可通过 validator，并被
   warm baseline 作为 compatible 原样复用。** Python 的最终 validator 能发现同类
   伪造，但 baseline 接纳阶段仍会先复用，未满足“伪记录不得进入 warm”的验收合同。
2. **P1：正式 Waku 输出同时存在 `current/index.json` 无法被 CLI validate 读取、
   以及四个悬空 compatibility symlink。** 一个成功的 `index` 命令会主动创建本次
   generation 根本没有生成的 `modules`、`projects`、
   `technology-selection.{json,html}`。

因此 231/231 全量绿测和 SourceBridge 1,575/1,575 warm 复用不能签发生产 PASS。

## P0：Go/JavaScript 语义摘要可由 baseline 自己重签

### 最小可复现数据完整性例

源仓只包含：

```go
package main
func main() {}
```

在合法 cold index 中加入源码不存在的关系：

```json
{
  "source_id": "<main.go 的 file_id>",
  "target_id": null,
  "target_name": "pay_admin",
  "kind": "calls",
  "path": "main.go",
  "line": 2,
  "analyzer": "go-lexer-fallback[package=main]",
  "confidence": "heuristic"
}
```

然后按产品当前公开算法同步：

- `stats.relationships`；
- teaching artifacts（`enrich_index`）；
- 该文件的 `analysis_sha256`；
- `derived_sha256`；
- `integrity_sha256`。

独立重放结果：

```text
validate_index(poison, source).valid = True
build_index(previous_index=poison).baseline_status = compatible
warm reused_files = 1
warm reused_derived_artifacts = True
warm contains target_name=pay_admin = True
validate_index(warm, source).valid = True
```

同样的完整重签探针对 `main.js` 得到：

```text
JavaScript poison validate = True
warm baseline_status = compatible
warm reused_files = 1
fake relationship retained = True
```

Python 的最终 validator 会以 `analysis-semantics-mismatch` 拒绝，但
`_baseline_rejection_reason()` 仍先给出 `compatible`，warm 结果仍含伪边；CLI 的
publish-before-switch gate 最终能阻止它成为 current，却没有满足“warm 不复用”。

### 根因

- `indexer.py:365-437` 的 baseline gate 对 records 只做形状/引用/行号检查，再用
  baseline 自己声明的 records 重算 `analysis_sha256`。摘要不是独立的 analyzer
  证明，攻击者可同时重算 payload 与摘要。
- `validation.py:959-981` 只对 Python/JavaScript relationship 检查可计算的稳定 ID；
  这仍不能证明源码存在该边。Go 普通 `contains/import/calls/receiver-type` 甚至没有
  对应的 stable-ID 重证分支。
- `validation.py:1029-1064` 只有 `language == "Python"` 会对当前源码重新运行
  analyzer 并比较 canonical records。JavaScript 与 Go 只比较 payload 自身摘要。
- 当前测试中的 wrong-kind/fake-edge poison 只重算了最外层 checksum，没有同步
  `analysis_sha256`、derived artifacts 和 stats，所以绿测没有覆盖完整重签攻击。

### 必须达到的修复门

1. warm hydration 之前，必须对**每一种允许 reuse 的 analyzer**从当前源码生成
   canonical per-file semantic records，再与 baseline 比较；或使用等价的、不能由
   baseline payload 自己伪造的受控 analyzer provenance。只增加 kind 白名单不够。
2. 覆盖 Go symbols 与 `contains/import/go-import-alias/calls/receiver-type`，以及
   JavaScript symbols/relationships。任意新增、删除、改 kind、改 endpoint、改 line、
   改 analyzer 后，即使重算全部 SHA-256，也必须使 baseline `rejected/incompatible`，
   `reused_files=0`，且伪记录不得进入返回值。
3. `validate_index()` 与 warm baseline gate 必须共享同一 canonical semantic contract，
   防止“validator 拒绝但 build API 已复用”或“build 接纳且 validator 也接纳”的分裂。
4. 增加完整重签回归，不得只重算 `integrity_sha256`。测试必须同步
   `analysis_sha256`、`derived_sha256`、stats 与派生产物后再验证拒绝。

## P1：Waku 正式 generation 有不可用 current 路径和悬空入口

真实仓库：`/Volumes/T7/workspace/ontology/graph/repo/waku-agent`  
fresh 输出：`/tmp/repo-teacher-core-release.MdmXrk/waku-cold`

fresh index 成功：

```text
files=212, symbols=1557, relationships=9879, modules=13
wall=13.75s, max RSS=171,114,496 B
generation_id=989312ab840d4810071a1db242ae74e9
manifest artifacts=[index.html, index.json]
```

### `current/index.json` 读取失败

```text
repo-teacher validate cold/index.json
=> PASS, rc=0

repo-teacher validate cold/current/index.json
=> error: JSON artifact is not part of the current generation:
          current/index.json
=> rc=1
```

`persistence.py:834-844` 找到 managed output root 后，把 lexical relative path
`current/index.json` 原样交给 `read_published_json()`；而 manifest 中的 artifact key
是 `index.json`，所以 `persistence.py:819-821` 必然拒绝。发布布局明确暴露了
`current`，该路径不能成为 validator 的陷阱。

修复门：`read_json_path()` 必须安全识别 `current/<artifact>` 与当前 immutable
generation 内的路径，去除受验证的 managed prefix 后再走整 generation reader；
仍须保持 current-before/current-after、manifest、size、digest、embedded generation ID
校验，不得退化为普通 `Path.read_text()`。

### 成功输出主动创建四个 broken links

fresh `index` 后的根入口：

```text
index.json                   -> current/index.json                         OK
index.html                   -> current/index.html                         OK
modules                      -> current/modules                            BROKEN
projects                     -> current/projects                           BROKEN
technology-selection.json    -> current/technology-selection.json          BROKEN
technology-selection.html    -> current/technology-selection.html          BROKEN
```

原因是 `persistence.py:661-683` 无条件创建固定 `_COMPATIBILITY_ENTRIES`，而 index
generation 只含 `index.json/index.html`。`explain` 仍会留下 `projects` 与两个
technology-selection 悬空项；`compare` 则会留下 index/modules 悬空项。

修复门：成功发布后的 compatibility namespace 不得有任何 broken link。需要对
`index -> explain -> index -> compare` 等同目录命令序列定义清楚的 surface 合同；
每次 current switch 后逐项断言所有公开入口都存在且属于同一 generation。不能只把
当前四个名字从列表删除，因为旧 command surface 在下一次不同命令切换后仍可能悬空。

## generation transaction 重放：PASS

### 三条 CLI 中途失败

在 tiny repositories 先建立旧 generation，修改源码，再分别于 artifact 2/3/4 写入
时注入 `OSError`：

| 命令 | rc | current target | 旧 artifact SHA-256 集合 |
|---|---:|---|---|
| index | 1 | 不变 | 全部不变 |
| explain | 1 | 不变 | 全部不变 |
| compare | 1 | 不变 | 全部不变 |

staging 中途失败不会暴露新旧混合 JSON/HTML。

### 并发与进程终止

```text
writer A 持有 OutputLock
writer B CLI rc=1，current 不变
writer A 退出 rc=0
writer B 重试 rc=0
```

第二个子进程在 generation 已完成、`before_switch` 内执行 `os._exit(23)`：

```text
child rc=23
current target unchanged=True
read_published_json(...).value=old
lock reacquired after abort=True
```

这会留下不可达的完整 generation，但不会切走旧 current。

### generation identity/hash 闭包与 file://

- 每个 JSON 有同一 32-hex `generation_id`，HTML 有同值 meta；
- manifest v2 对 artifact 记录 exact set、size 与 SHA-256；
- tamper、额外/缺失 artifact、embedded ID 不一致由 reader 拒绝；
- `file://.../index.html` 能通过根 compatibility link 打开当前完整 HTML；
- reader 在读取前后再次检查 current target，切换竞态 fail closed。

注意：这项 PASS 不包括上一节的 `current/index.json` 路径解析和 broken symlink。

### legacy 与异常 current

独立重放结果：

```text
missing current      -> FileNotFoundError
plain-file current   -> ValueError: current generation is not a symbolic link
outside current      -> ValueError: target is outside generation store
malformed current ID -> ValueError: target is malformed
legacy index.json    -> publisher refuses replacement; legacy bytes preserved
```

## partial/invalid 发布门：PASS

对 `index`、`explain`、`compare` 分别注入：

- `scan_complete=False, truncated=True, freshness=partial-unvalidated`；
- 语义上无效但重算最外层 checksum 的 tutorial forgery。

六种调用均得到：

```text
rc=1
current target unchanged=True
```

三条 CLI 都在生成 artifacts 前和 current switch 前验证 source index。此项不能覆盖
P0 的 Go/JavaScript“validator 本身错误签发 valid=True”。

## scanner、manifest、tail-window 与证据脱敏：PASS

### 资源与异常边界

- manifest 的 `max_entries`、deadline、cancel 均 fail closed；
- scanner 的 deadline/cancel/max entries/max files/max total bytes 有显式诊断；
- FIFO 使用 `O_NONBLOCK` 且作为 non-regular 跳过；
- `PermissionError` 转成 `stat-error`，不逃逸整个扫描器；
- stat 后 4-byte 文件增长 2,000,000 bytes 的独立探针中，唯一 `read()` 请求为
  101 bytes（`max_file_size + 1`），结果 `file-changed-while-reading`，未发生无界读取；
- non-Git 最后 snapshot 后新增文件的现有故障注入得到
  `changed while it was being indexed`，不会返回 complete generation；
- publish-point 的第二次 `_require_valid_index` 能检测 build 返回后、current switch 前
  的源码漂移。

普通可写文件系统仍不是 MVCC snapshot。对持续恶意 writer 的数学原子性不在当前
保证内；绝对一致任务仍需只读 filesystem snapshot、固定 worktree 或上游写锁。

### secret 与结构字段

Anthropic、AWS、GitLab、Slack、generic TOKEN 五组生产形状均未出现在序列化 index，
并出现 `[REDACTED]`；index validator 仍为 valid。Go 结构字段
`credentials=example/internal/credentials` 保持原值且 validator valid，说明字段感知
脱敏没有再次破坏 import alias。

## warm 复杂度证据

O(path) 回归对 24 个文件观测到 `_file_analysis_digest` 共 48 次调用；每次只收到该
path 的 `(1 symbol, 1 relationship)`，没有每个文件扫描全图。records 在 hydration
前按 path 分组，per-file digest 的累计处理量对总 records 保持线性。

但完整 CLI warm 仍会进行全树 scan、manifest 与发布前验证，所以不能把
`reanalyzed=0` 解释为近零 wall time。真实 SourceBridge warm 仍为 40.08s、约 1.19GB
max RSS，属于后续性能/容量 WATCH。

## SourceBridge fresh cold + disk current warm

仓库：`/Volumes/T7/workspace/ontology/graph/repo/sourcebridge`  
HEAD：`2a128bf0c8461fae91d2b424d9168ddf205bb11b`  
既有工作树状态：`D LICENSE`（本轮未恢复、未修改）  
输出：`/tmp/repo-teacher-sb-release.Tpe6Fr/output`

| 场景 | wall | max RSS | files | reused | reanalyzed | diagnostic errors | validation errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| fresh cold | 42.65s | 1,236,123,648 B | 1,575 | 0 | 1,575 | 0 | 0 |
| disk current warm | 40.08s | 1,189,642,240 B | 1,575 | 1,575 | 0 | 0 | 0 |

两者均有 1 个预期 `dirty-worktree` warning。以下十组 canonical JSON SHA-256 冷暖逐项
相等：

```text
files(1575), symbols(13956), relationships(91119), modules(21),
reading_path(12), features(8), evidence(40), tutorials(8),
codemaps(8), coverage(8)
```

`read_published_json(output)` 返回 warm generation，证明 root current reader 的完整
generation 校验通过。SourceBridge 真实成功不抵消 synthetic Go poison：前者证明正常
路径一致，后者证明恶意/损坏 baseline 的拒绝边界不完整。

## 测试与静态检查

```text
核心专项：
PYTHONPATH=src python3 -m unittest \
  tests.test_scanner tests.test_indexer tests.test_snapshot \
  tests.test_evidence tests.test_validation tests.test_persistence tests.test_cli -v
=> Ran 85 tests in 65.121s — OK

全量：
PYTHONPATH=src python3 -m unittest discover -s tests -v
=> Ran 231 tests in 164.595s — OK

ruff check src tests
=> All checks passed

python3 -m compileall -q src tests
=> exit 0
```

绿测证明已有合同没有回退；P0 与 Waku P1 来自测试集之外的完整重签和真实输出探针，
所以不能被测试数量抵消。

## 长期运维与恢复边界

1. generation store 是 append-only，没有 retention/GC。SourceBridge 连续 cold/warm
   已留下两个完整 generation；长期运行会线性增长磁盘。
2. staging 中止会留下 `.stage-*`；`before_switch` 中止会留下不可达的完整 immutable
   generation。永久 lockfile 可在进程终止后重获，但不会自动清理这些证据。
3. 当前没有 reader lease，也没有“确认非 current 且无人读取”的安全 GC 协议；清理
   必须在 OutputLock 下按明确保留窗口和审计策略完成。
4. SHA-256/manifest 是损坏检测而非认证。能控制 generation 目录并重写 payload、
   manifest、所有摘要的高权限本地攻击者仍在信任边界内；本报告 P0 更严格地要求即使
   baseline 完整重签，analyzer 语义仍要由当前源码重证。
5. no-replace/exchange 依赖 Darwin `renameatx_np` 或 Linux `renameat2`；其他平台应继续
   fail closed，不得静默退化为逐文件覆盖。

## 解除 BLOCK 的最低条件

1. 关闭 Go/JavaScript/Python warm 完整重签 poison：所有 analyzer 的 canonical
   records 在 reuse 前对当前源码重证；伪 symbol/relationship 不得进入 warm 返回值。
2. 新增完整重签测试，覆盖 Go symbols、contains/import/go-import-alias/calls/
   receiver-type，JavaScript symbols/relationships，Python wrong-kind/fake-edge，以及
   tutorial/codemap/coverage/stats；全部必须 validator reject 且 warm incompatible。
3. 修复 `current/index.json` managed path 读取，同时保持 whole-generation verification。
4. 重新定义 compatibility surface，保证 index/explain/compare 及其顺序组合在成功和
   失败后都没有 broken symlink，且所有公开入口属于同一 current generation。
5. 由新的独立 Agent 重放本报告最小 poison、Waku fresh 输出、三命令故障注入、
   SourceBridge fresh cold/disk warm、核心/全量/Ruff/compileall 后再签发 PASS。

