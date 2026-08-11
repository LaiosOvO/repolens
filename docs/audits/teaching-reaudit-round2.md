# 教学 / 功能发现第二轮独立复审

日期：2026-08-10  
范围：`src/repo_teacher/features.py`、`capability_catalog.py`、`artifacts.py`、`report.py` 与真实六仓 Golden  
结论：**REQUEST CHANGES**  
架构状态：**BLOCK**

## 一句话结论

第二轮已经修掉注释/字符串伪路由、普通模块 fallback、无 main guard 的 Python `main` 升级，以及可见 Mermaid 源码等上一轮问题；六仓固定快照也确实能通过生产 `build_index()` 输出 19/19 个清单路径。但是当前 19 项并不是功能聚合算法发现的，而是产品代码内硬编码并由同一份清单充当测试期望值；更严重的是，任意无 Git 目录只要复制几个参考文件就会被标成指定 commit 的 `source-audited`。边界发现仍会把 HTTP 客户端调用和无关 `.command()` 调用当成服务/CLI 功能。它仍不可作为生产级技术选型或可复用模块结论来源。

## 审计方法

1. 不采信 `docs/audits/teaching-fix-round2.md` 的完成声明，逐行检查四个产品模块和对应测试。
2. 独立复跑专项测试、全量测试、Ruff 和 `compileall`。
3. 对六个固定 commit 的完整 clone 重新执行 `build_index()` 和 `render_report()`，并从 feature 的 step/evidence 源路径独立检查非产品目录误报。
4. 生成 SourceBridge、OpenWiki、DeepWiki Open 的真实 HTML，使用 Chrome 在 `1440×1000` 与 `390×844` 两种视口人工查看首屏和功能卡。
5. 增加未写入产品测试的反例探针：HTTP 客户端调用、无关 `.command()`、错误 Go package、JS 同行除法，以及把参考源码复制到无 Git 临时目录。
6. 按代码审计工作流尝试启动额外 `code-reviewer` 与 `architect` 通道；两个角色均因当前账户不支持其绑定模型而返回 400，因此没有把缺失的额外审查当作批准证据。本报告本身是由上级单独派生的独立复审 Agent 完成。

## 整改门逐项结果

| 检查项 | 结果 | 独立证据 |
|---|---|---|
| 注释/字符串不能伪造 HTTP/CLI | **PASS（限定于该反例）** | Python 使用 AST，JS/TS 先丢弃注释并 tokenize；专项反例通过，见 `features.py:52-180`。但真实调用的 receiver 语义仍未校验，见 P0-2。 |
| 删除配置/普通模块 fallback | **PASS** | `discover_features()` 不再生成 `module-capability`；只有 `eslint.config.js` 与普通 `context-builder.ts` 的仓库输出 0 feature。 |
| 无可执行证据的 Python `main.py:main` 降级 | **PASS** | 无 main guard 的 `main` 进入 `entrypoint-candidate`，证据为 `entry-candidate`，见 `features.py:541-602`。Go 仍有错误 exact 边界，见 P0-2。 |
| 六仓 19 项路径进入最终索引 | **PASS（仅路径注入召回）** | 六仓完整 `build_index()` 得到 3+2+3+3+3+5=19 项；扫描均 complete，19 项八维 key 完整。它不是独立的语义召回，见 P1-1。 |
| `docs/tests/examples` 等非产品目录误报为 0 | **PASS** | 独立按 feature 的 step 与 evidence 路径检查六仓，`docs/tests/testing/examples/__tests__/integration_tests/e2e/demos/playground` 命中 0。 |
| 教程不是 BFS 复制，包含职责切片/关系/缺口 | **FAIL** | 教程仍复制 feature 的 `_walk_symbols` 步骤；六仓 19 个审计能力均只有 1 个位置切片、0 个已确认关系，职责与三类缺口是固定模板，见 P1-2。 |
| CodeMap 以可读 HTML 节点/边显示 | **PARTIAL** | 可见 Mermaid 源码已消失，桌面/窄屏节点/边列表可读；但 19 个审计能力总计 19 节点、0 边，尚不能说明能力如何实现，见 P1-2。 |
| 八维技术标签与显式 unknown | **PARTIAL** | 八个维度都存在且 unknown 可见；已知值来自硬编码、没有逐标签证据，并存在错误/过度断言，见 P1-3。 |
| 可重复六仓 Golden：Tier-1 ≥80%、非产品误报 0 | **PARTIAL** | 测试可重复且路径命中为 19/19、非产品源路径为 0；但期望值与实现来自同一产品常量，且不检查合法/非法边界、能力关系、逐标签证据或首屏顺序，见 P1-1/P1-4。 |

## 六仓真实全链路结果

下表是本次复审重新执行生产 `build_index()` 的结果，不是读取整改报告：

| 仓库 | 清单路径召回 | 非产品源路径误报 | 八维 key | 审计能力 CodeMap |
|---|---:|---:|---|---:|
| SourceBridge | 3/3 | 0 | 3/3 完整 | 3 节点 / 0 边 |
| PocketFlow Code2Tutorial | 2/2 | 0 | 2/2 完整 | 2 节点 / 0 边 |
| OpenWiki | 3/3 | 0 | 3/3 完整 | 3 节点 / 0 边 |
| Understand Anything | 3/3 | 0 | 3/3 完整 | 3 节点 / 0 边 |
| CodeBoarding | 3/3 | 0 | 3/3 完整 | 3 节点 / 0 边 |
| DeepWiki Open | 5/5 | 0 | 5/5 完整 | 5 节点 / 0 边 |
| **合计** | **19/19** | **0** | **19/19** | **19 节点 / 0 边** |

因此可以确认“固定文件被注入最终索引”，不能据此确认“功能发现、聚合和实现讲解已达到 100% recall”。

## P0 — 阻塞发布

### P0-1：`source-audited` 没有校验 Git 身份或 commit，可以被无 Git 文件副本伪造

- 位置：`capability_catalog.py:183-200,205-237`
- 原因：manifest 匹配只检查两个 `signature_paths` 是否存在，单项能力只检查目标文件 SHA-256；`discover_features()` 没有收到项目 snapshot，也没有校验 canonical remote、Git HEAD 或完整源码 bundle。
- 独立复现：把 SourceBridge 的 `store.go`、`execution_path.go`、`code_tour.py` 复制到一个全新的无 Git 临时目录后执行 `build_index()`。

```text
commit=None
执行路径查询 source-audited source-audited-reference-manifest:sourcebridge@2a128bf0c846
图数据存储 source-audited source-audited-reference-manifest:sourcebridge@2a128bf0c846
证据化代码导览 source-audited source-audited-reference-manifest:sourcebridge@2a128bf0c846
```

- 用户影响：HTML 显示“固定版本源码已审计”，但被分析对象并不是该固定版本仓库；这会污染后续技术选型和复用判断。
- 现有可复用实现：同仓 `reference_catalog.py:935-1013` 已有 fail-closed 的 canonical remote + commit + source bundle 验证，本轮另造了一个更弱的身份系统。
- 修复门：只有 `reference_identity_status(index).status == verified` 才能输出 `source-audited`；stale、复制文件或非 Git 输入必须降级为 heuristic/unknown，且来源不得携带未验证的 commit。

### P0-2：真实语法调用仍会被错误升级成服务 HTTP/CLI 边界，Go exact 也缺少 package 语义

- 位置：`features.py:52-70,161-180,269-275,520-538`
- 原因：
  - Python 只检查 attribute 名为 `get/post/...`，没有检查 receiver 是路由器/应用，也没有区分 server decorator 与 HTTP client call。
  - JS/TS 对 HTTP receiver 做了有限白名单，但 CLI 的 `.command()` / `.add_parser()` 对任意 receiver 生效。
  - Go 只在 `main.go` 搜 `func main(`，没有要求 `package main`。
- 独立复现：

```text
requests.get("/private")         -> http-route GET /private exact-entry
client.post("/upload")          -> http-route POST /upload exact-entry
database.command("vacuum")      -> cli-command vacuum static-entry
package helper; func main() {}   -> entrypoint main exact-entry
```

- 另一个 recall 反例：`const ratio = left / right; router.get("/real", handler);` 在同一行时被轻量 slash 扫描器吞掉，合法路由输出为 0。见 `features.py:98-125`。
- 用户影响：报告仍会把客户端请求、数据库命令或非可执行 Go 函数放进“已确认运行边界”和 30 秒功能数。这与上一轮注释/字符串误报一样会污染产品功能清单。
- 修复门：Python 至少区分 decorator/call context 与 receiver 来源；JS/TS 使用真正 parser 或状态完整的 lexer，并限制 CLI receiver/构造来源；Go 必须同时确认 `package main + func main`。这些反例需要进入产品测试。

## P1 — 生产级功能缺口

### P1-1：19/19 是硬编码目录注入和循环 Golden，不是 feature-first 能力发现

- 位置：`capability_catalog.py:63-160,175-245`；`tests/test_reference_ground_truth.py:27-28,78-85,113-116`
- 产品行为：只有六个精确文件形状能生成 `capability-cluster`。任意其他仓库仍只有 HTTP/CLI/entrypoint；没有通用的模块/调用图/概念/前后端证据聚合。
- 测试循环：测试从产品函数 `reference_ground_truth()` 读取期望 paths，再把产品用同一 `REFERENCE_MANIFESTS` 生成的 feature 与它比较。`expected_total == 19` 只固定数量，没有提供独立语义 oracle。
- 这解释了为什么全量路径 recall 是 100%，同时每个能力仍只有一个固定文件和零条关系。
- 修复门：
  1. Golden 期望应放在独立只读 fixture，并明确每仓合法入口、禁止入口、能力 ID、核心/辅助文件、预期关系和技术证据；不能从产品 catalog 生成期望值。
  2. `capability-cluster` 应由通用证据聚合产生，参考 catalog 只能作为 verified repo 的审计覆盖/校准层，不能是唯一能力生产器。
  3. 增加至少一个未列入 catalog 的仓库作为盲测，验证能力发现不是只认六个答案。

### P1-2：教程仍是 BFS 步骤的展示包装，19 个能力的 CodeMap 全部没有边

- 位置：`artifacts.py:64-143,146-280`；`capability_catalog.py:168-225`
- `_tutorial()` 直接复制 `_ordered_steps(feature)`；自动边界 feature 的 steps 来自 `_walk_symbols()` 的 BFS，`reading_order_semantics` 甚至仍写着 `static-breadth-first`。
- “职责”只有两条固定句式：是否带 `relationship_id`；data flow/state/error path 对每个功能都是相同的三句模板。
- source-audited 能力只用 `_symbols_for_path()[0]` 作为 primary，并强制生成一个 step。真实结果里：
  - SourceBridge “图数据存储”定位在 `store.go:21-43` 的 `Repository` struct，而真正 `Store`/`NewStore` 在约 `222-281`。
  - OpenWiki “Wiki 引用校验”定位到 `formatWikiLinkIssues()`，不是主要校验流程。
  - DeepWiki “CodeMap 生成服务”定位到 `local_repo_dir()`，不是 `generate_codemap()` 主流程。
- 六仓所有 19 个能力均为 1 个 location-only 切片、0 个 confirmed relationship；其 CodeMap 总计 19 节点、0 边。
- 修复门：每个能力至少应有角色化的核心/协作/状态/错误切片，关系只能来自已解析边或独立源码审计 claim；不能用“文件里的第一个符号”代替核心实现。CodeMap 应展示这些已确认关系，无关系时明确称为“单点源码定位”而不是地图。

### P1-3：八维标签结构完整，但已知值是无逐项证据的硬编码，存在错误断言

- 位置：`capability_catalog.py:69-122,163-165`；`report.py:273-299`
- 正面：八个维度始终存在，未知项显式显示，未使用通用关键词猜测补齐。
- 阻塞缺口：每个已知标签没有自己的 evidence ID、行号、claim 或置信度。唯一 capability evidence 是前述任意 primary symbol 片段，不能证明所有技术标签。
- 已确认错误示例：SourceBridge `store.go` 被标为 `store:surrealdb`（`capability_catalog.py:69`），而目标文件 `internal/graph/store.go:222-258` 明确说明并实现的是 **in-memory Store**，只说 SurrealDB 后端“can be plugged in”。这会直接误导底层存储选型。
- DeepWiki `api/services/codemap.py` 被标为 `store:job-state`，目标文件主要以 NDJSON stream 发 phase event，清单没有给出 job state 持久化证据。
- 修复门：技术维度应成为 `{dimension, value, confidence, evidence_ids, claim}`，逐项绑定经过审计的源码片段；无法绑定就显示 unknown。修正上述错误标签并为六仓 Golden 增加独立 expected technology facts。

### P1-4：当前 Golden 没有覆盖整改门所要求的 precision 与 HTML 语义

- 位置：`tests/test_reference_ground_truth.py:31-116`
- 当前有价值的部分：真实 commit、工作树文件与 HEAD 相同、完整 `build_index()`、scan complete、八维 key、报告含 nodes/edges 容器、无可见 Mermaid `<pre>`。
- 未覆盖：
  - 每仓合法入口和禁止伪入口；
  - HTTP client / database command / Go wrong-package 等边界 precision；
  - capability 的核心/辅助切片与关系；
  - 已知技术值及对应 evidence；
  - 教程是否不是单切片模板；
  - 首屏是否真的先显示 capability；
  - “非产品目录”检查只从 `entrypoint` 文本取路径，CLI/HTTP 本身不带源码路径，不能发现这两类 feature 的来源目录误报。复审使用 evidence/step 路径补查后六仓当前为 0，但测试本身仍应修复。
- 修复门：把上述内容加入独立 Golden contract，并至少加入针对 precision 的变形/负例仓库。

## P2 — 需要收紧

### P2-1：HTML 口头承诺“先看能力”，实际目录按中文组名排序，边界仍排在能力前

- 位置：`report.py:236-242,508-526`
- `_group_features()` 按 group name 字符串排序；实际 SourceBridge 桌面首屏在 headline “先看 3 个源码审计能力”之后，先连续展示 `/health`、`/sql` 等 HTTP/入口分组，“源码审计能力”在后面。
- 用户影响：用户此前明确反感平铺和找不到重点；当前信息层级仍与文案承诺相反。
- 建议：固定分区优先级为 verified capabilities → confirmed boundaries → candidates，并在目录与详情中一致；不要用本地化标题的字典序决定产品信息架构。

### P2-2：CodeMap 的 HTML 形式已修复，但单节点能力应降级命名

- 位置：`report.py:302-332`
- 节点/边列表在桌面和 390px 窄屏均可读，`→`/`⇢` 语义也清楚，这是本轮有效改进。
- 但无边时仍显示“代码地图”，容易让用户误以为已建立模块关系。建议显示“单点源码定位 · 尚无已确认关系”，有边后再称 CodeMap。

### P2-3：源码链接可点击，但不能直接定位行号

- 位置：`report.py:111-122`
- 链接文本含 `path:start-end`，`href` 只有文件 URI，没有行号/编辑器深链。它满足“打开文件”，尚未满足从能力卡精准落到实现行的最佳体验。
- 建议：保留安全 `file://` 方案的同时，为本地服务模式提供受控的 `#Lx`/内置 CodeViewer 定位；不可放宽根目录约束。

## 验证结果

专项测试：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_features tests.test_artifacts tests.test_report \
  tests.test_reference_ground_truth -v

Ran 18 tests in 15.624s
OK
```

静态检查：

```text
ruff check <本轮教学源码与测试>
All checks passed!

python3 -m compileall -q <本轮教学源码与测试>
```

全量回归在本次共享多 Agent 工作树上执行时为：

```text
Ran 136 tests in 18.393s
FAILED (failures=4, errors=12)
```

16 个失败均集中在另一个正在并行整改的 `skill_export` 夹具身份字段，不由本轮四个教学模块直接触发；因此本报告不把它们重复计为教学 P0，但当前共享分支不能声称“全量测试为绿”。合并前仍必须在所有并行修改稳定后重跑完整套件。

## 最终裁决

**REQUEST CHANGES / Architecture BLOCK**。

本轮对展示层和已知反例的修复是实质进步：注释/字符串、普通模块 fallback、Python candidate 分层、可见 Mermaid、unknown 维度以及非质量化 coverage 标签都已改善；六仓完整扫描也能稳定落入 19 个固定路径。但 source-audited 信任边界可被文件复制伪造，HTTP/CLI/Go 边界仍会制造错误功能，Golden 又把产品答案当测试答案。加上 19 个能力全部只有单点定位和零关系，当前产物仍是“六仓人工书签 + 入口探测 + 更好的 HTML”，还不是用户要求的生产级“讲清功能及底层实现”的通用代码仓库教学器。
