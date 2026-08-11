# 六仓技术选型比较第三次独立复审

**结论：REQUEST CHANGES**  
**Architecture status：BLOCK**  
**日期：2026-08-10**  
**范围：** `reference_catalog.py`、`comparison.py`、`comparison_report.py`、`technology-comparison-fix-round2.md`，以及 `examples/reference-selection` 下正式生成的全部 HTML/JSON。  
**约束：** 本轮只读复审产品实现；除本报告外没有修改产品代码或正式产物。

## 一句话结论

上一轮四个 P1 在数据和证据层已经大部分实质关闭：六仓身份从真实 Git worktree 读取，48 个 curated 方案已重新生成；15 条 claim EvidenceRef 的真实行范围与 SHA-256 全部闭合，另外 170 条入口明确标成 context；四种 scenario 的首选、备选与模块组合也确实形成四组不同数据。

但正式 HTML 的场景选择器不可用。页面给非当前场景写入了 `hidden`，同时自己的 `.decision-grid { display:grid }` 和 `.scenario-recommendation { display:grid }` 又覆盖了隐藏行为。真实 Chromium 中 **36/36 个场景 pane 全部可见并占据布局**，点击按钮只改变 `hidden` 属性和按钮颜色，不能隐藏其他场景。因此用户看到的仍是四套推荐同时平铺，上一轮最核心的“场景进入可见决策”没有真正交付。

此外，“为什么”字段仍只是“先选某技术对象，再按权重筛选，所以某项目是首选”的算法复述，没有解释为什么该场景应该选这类技术对象、为何首选优于备选。限制、不确定性和源码模块已经具备，但决策理由仍不足。

## 30 秒验收表

| 验收项 | 独立实测 | 结论 |
|---|---:|---|
| 正式 schema / catalog | schema `2.0`；catalog `2026-08-10.3` | PASS |
| 项目与方案 | 6 个项目、8 个能力、48 个 curated option | PASS |
| Git 身份 | 真实 worktree top-level + origin + HEAD + required-source bundle，6/6 `verified` | PASS |
| 无 `.git` 的复制目录 + 伪 remote/commit | `unverified` | PASS |
| 48 项事实 | 178 个 source-path 引用、139 个项目内唯一源码文件，0 缺失；未发现新的事实矛盾 | PASS（证据等级见残余边界） |
| 三处上轮修正 | SourceBridge federation、Workflow Story、OpenWiki critic prompt 边界均与源码一致 | PASS |
| claim EvidenceRef | 15 条；0 越界、0 hash/snippet 不一致、0 dangling | PASS |
| context 边界 | 170 条均为 `supports_claim=false` / `supports_option_claim=false` | PASS |
| 场景数据 | 4 个 scenario 的 primary/alternative/module-plan fingerprint 全部不同 | PASS |
| 默认首选聚焦 | local-first 的 8 个能力均只有 1 个 primary | PASS |
| 限制与不确定性 | 32 个场景推荐均有 tradeoff、confidence 与 module plan | PASS |
| 决策理由 | 32 个 `why` 都是同一算法模板，只替换技术类与项目名 | FAIL |
| HTML 场景切换 | 36/36 pane 同时可见；点击后仍为 36/36 | FAIL |
| 项目报告 | 6 份 HTML + 6 份 schema 2.0 JSON 均存在 | PASS |
| 本地链接 | 7 份 HTML 共 853 个本地链接；0 缺失、0 root escape、0 外部 scheme | PASS |
| SourceBridge 正式索引 | fingerprint 存在；10,922 个 Go symbols、69,231 条 Go relationships | PASS |
| 视觉与信息结构 | 首屏层级明显改善、移动端无横向溢出；场景 pane 失效导致正文重新膨胀 | BLOCK |
| 专项测试 | 20 tests，全部通过 | PASS，但没有浏览器状态测试 |

## P0

本轮未发现 P0。

## P1

### P1-1：正式 HTML 的 scenario 切换失效，四套推荐全部同时显示

这是用户可直接遇到的正式产物问题，不是理论边界。

实现链如下：

- `comparison_report.py:270-288` 为非默认场景输出 `hidden`。
- `comparison_report.py:429` 给 `.decision-grid` 声明 `display:grid`。
- `comparison_report.py:433` 给 `.scenario-recommendation` 声明 `display:grid`。
- `comparison_report.py:450-459` 的脚本只切换 `pane.hidden`，没有切换 CSS class 或 inline `display`。

真实 Chromium 的独立探针结果：

```text
initial selected scenario: local-first-product
scenario panes in DOM:     36
scenario panes visible:    36

quick brief:
  precise-static-analysis  hidden=true   computed display=grid
  local-first-product      hidden=false  computed display=grid
  teaching-experience      hidden=true   computed display=grid
  dynamic-agent-runtime    hidden=true   computed display=grid

after clicking each scenario:
  target hidden state changes
  computed display remains grid
  visible panes remains 36
```

36 个 pane 来自 4 个 quick-brief grid，加上 8 个能力各 4 个推荐面板。浏览器实测页面高度为：

```text
1440px desktop: 21,834px
390px mobile:    39,387px
horizontal overflow: 0px
```

因此数据虽然有四种场景，用户界面却没有真正选择场景；用户仍会同时看到互相冲突的四套首选。上一轮 P1-3“场景权重必须进入可见决策或交互”不能判为关闭。

最小修复应在所有 grid 声明之后增加可靠隐藏规则，例如：

```css
[hidden] { display: none !important; }
```

或使用显式 active class，而不是依赖可能被 author CSS 覆盖的 `hidden`。修复后必须由真实浏览器断言：初始只显示 1 个 quick grid + 8 个 capability pane；点击任一场景后仍只显示对应的 9 个 pane。

### P1-2：“为什么”仍没有解释场景与路线的因果关系

`comparison.py:740` 对全部 32 个场景推荐使用同一个模板：

```text
场景先选择 {preferred_class} 技术对象，再只在同一路线内使用场景权重筛选；{primary_names} 是当前首选。
```

这句话描述了算法做了什么，却没有回答：

1. 为什么“本地优先产品”的此项能力应选这个 comparison class；
2. 为什么 primary 比 alternative 更适合当前场景；
3. 哪个可观测源码能力或分维度信号导致该选择；
4. 在什么条件下应该改选备选路线。

`SCENARIO_ROUTE_PRIORITIES`（`comparison.py:236-283`）只有 class 顺序，没有每项路线的 `fit rationale`、`not-fit condition` 或证据。当前 `why` 的 22 个不同字符串只是 class/project 变量不同，逻辑模板完全相同。

已通过的部分不能混淆：

- 每条推荐都有具体 `tradeoff`；真实数据中有 21 个不同限制文本。
- 每条推荐都有 `confidence`，能区分路线内首选、单一参考实现和不确定性并列。
- 每条推荐都有首选/备选项目和 2–3 个模块入口。
- 四种场景的数据组合确实不同。

但这仍不等于“解释理由”。建议让 route priority 本身携带场景化的 `why_this_route`、`switch_when`，并把 primary 的关键 strength/score dimension 与 alternative 的差异写进可见摘要。理由应来自已经审计的事实，不能由 renderer 临时编造。

## P2

### P2-1：专项测试只检查 HTML 字符串，没有验证 scenario 的浏览器可见状态

`tests/test_comparison_report.py:111-133` 会检查场景文案、源码链接和安全转义，但没有加载 HTML、读取 computed style 或点击按钮。于是 `hidden` 存在于字符串就足以通过测试，尽管浏览器实际显示全部 pane。

应增加最小 Playwright/Chromium 回归：

- 页面初始只有默认 scenario 的 9 个 pane 可见；
- 点击四个 scenario 后，visible pane 数始终为 9；
- active button 与 pane 的 scenario 一致；
- 390px、768px、1440px 三个 viewport 无横向溢出。

### P2-2：修复记录的专项测试计数已过期

`technology-comparison-fix-round2.md` 写的是 19 tests；当前同一专项命令实际运行 20 tests 并全部通过。它不影响产品运行，但审计记录应更新，避免把不可复现的数字当完成证据。

## 上一轮四个 P1 逐条复核

| 上一轮 P1 | 当前状态 | 本轮证据 |
|---|---|---|
| P1-1 正式产物仍是旧 schema 1.0 | **关闭** | 正式主 JSON/HTML 为 schema 2.0、catalog `2026-08-10.3`；6 份项目 JSON/HTML 已重生成。 |
| P1-2 context 冒充 claim、源码范围不准确 | **关闭** | 15 条 claim 精确绑定行号/snippet/hash；170 条其余引用明确 `supports_claim=false`。DeepWiki 精确范围为 `128-148`、`178-222`、`305-309`。 |
| P1-3 scenario 不参与可见决策 | **数据层关闭，UI 未关闭** | 四组数据签名不同且推荐聚焦；正式 HTML 36/36 pane 同时可见，场景按钮不能切换内容。 |
| P1-4 identity 信任导入 JSON | **关闭** | 真实 Git root/origin/HEAD/bundle 决定身份；修改 index remote/commit 不影响真实判定，无 `.git` 的精确源码复制 + 伪 metadata 为 `unverified`。 |

## 六仓事实与三处修正复核

### 总体

- catalog：6 × 8 = **48** 项。
- `source_paths`：178 次引用、139 个项目内唯一源码文件，全部存在。
- 正式 option：48/48 `curated-source-audit`，48/48 catalog revision 为 `2026-08-10.3`。
- 本轮未发现相较第二次复审新增的事实矛盾。

这里必须保持证据等级诚实：48 项 catalog 经过源码阅读复核，不代表 48 项都具有机器可验证的逐 claim 证据。机器级 claim 范围目前是 15 条；其余入口只负责让人继续阅读，并已正确标为 context。

### SourceBridge federation：PASS

- `internal/db/store_federation.go:99-132` 实现 repository link，并用 canonical ordering 避免重复 pair。
- `internal/db/store_federation.go:182-218` 把 cross-repository reference 写入 SurrealDB。
- `internal/graph/store.go:2100-2138` 明确是 in-memory stubs，返回 federation not supported。
- catalog 的 source path、summary 和 limitation 已不再把 stub 冒充实现。

### SourceBridge Workflow Story：PASS

- `workers/knowledge/workflow_story.py:611-636` 是独立结构化生成入口。
- `workers/knowledge/workflow_story.py:729-753` 对 deep sections 执行 evidence threshold 与 confidence floor。
- `tutorial-generation` 已包含该文件，两个 claim 的行范围/hash 均闭合。

### OpenWiki critic policy：PASS

- `src/agent/prompts/code.ts:133-136` 把第二次 critic 写在 prompt workflow 中，并禁止第三次调用。
- catalog 明确标注 `prompt-enforced`，没有再宣称 runtime 状态机强制。

### DeepWiki 三组精确范围：PASS

- `api/services/codemap.py:128-148`：按文件组织 retrieved chunks 并保留真实行范围。
- `api/services/codemap.py:178-222`：真实文件 snippet 定位与 citation grounding。
- `api/services/codemap.py:305-309`：在输出前对 cloned repository 执行 grounding。
- `CodeMap.tsx:53-64,113-137` 与 `CodeViewer.tsx:49-80`：citation selection、sections/steps 展示和高亮行跳转。

## 身份与正式产物复核

### Git 身份

`reference_catalog.py:935-1006` 的 gate 会：

1. 从 `project.path` 解析真实 Git top-level；
2. 要求源码目录自身就是该 top-level；
3. 读取真实 `remote.origin.url` 和 `HEAD`；
4. 对 catalog 所需源码重新计算 worktree bundle；
5. 只有 remote、commit、bundle 都与固定 identity 一致才返回 `verified`。

独立攻击探针：

```text
real worktree + spoofed JSON remote/commit  -> verified（以真实 Git 为准）
copied audited files + canonical metadata
+ no .git                                  -> unverified
```

当前正式六仓为 6/6 verified。SourceBridge 的 `dirty=true` 也被如实保留；它来自用户已有的 `LICENSE` 删除。本轮没有恢复或修改该文件。

### 证据闭包

```text
source references            185
claim-evidence                15
context                       170
claim line/hash/snippet error  0
dangling claim id               0
context marked as claim         0
```

15 条 claim 全部使用真实源码重新读取并计算 SHA-256。170 条 context 的分布为：

```text
symbol-definition          111
index-evidence-context      44
whole-file-context          15
```

它们全部为 `supports_claim=false` 与 `supports_option_claim=false`，没有再冒充 claim。

### 正式链接与项目报告

```text
HTML files       7
local links    853
file:// links  757
relative links  96
missing target   0
root escape      0
external scheme  0
symlink output   0
```

6 个项目均有 `projects/<slug>/index.html` 与 schema 2.0 `index.json`。

### SourceBridge Go 数据

正式 `projects/sourcebridge/index.json`：

```text
analysis_fingerprint  c946d4799102bdccfe3cccde9a3dbf7fe40bcbc7d1a3a74b6d1d05d545d5830b
Go files              771
Go symbols            10,922
Go relationships      69,231
all symbols           13,956
all relationships     87,292
```

不是空索引，也不是上轮旧产物。

## 四种 scenario 复核

数据层确实生成了四组不同组合，不是同一结果换标题：

```text
precise-static-analysis  587766c3a639f13c
local-first-product      dce763b8186e0197
teaching-experience      138bffd7f0bc671a
dynamic-agent-runtime    3cf0387ccec6ba4b
unique signatures        4/4
```

签名材料包含 8 个能力的 primary IDs、alternative IDs 和 module plan。默认 local-first 的八项首选为：

| 能力 | 首选 | 备选 |
|---|---|---|
| code-parsing | SourceBridge | CodeBoarding |
| code-graph | CodeBoarding | Understand Anything |
| component-discovery | SourceBridge | CodeBoarding |
| tutorial-generation | SourceBridge | PocketFlow Code2Tutorial |
| evidence-grounding | SourceBridge | Understand Anything |
| incremental-update | CodeBoarding | Understand Anything |
| codemap-visualization | DeepWiki Open | SourceBridge |
| agent-workflow | OpenWiki | SourceBridge |

这组结果已经有明确重点；阻断在于正式页面不能只显示用户选择的这一组，而且 `why` 没有解释 route-priority 本身的理由。

## HTML 视觉与信息结构

### 已改善

- 首屏形成“产品目的 → 30 秒摘要 → 方法契约 → 能力下钻”的清晰层级，不再是 48 张卡平铺。
- desktop hero、色彩层级和 8 个决策卡可快速识别。
- 390px、768px、1440px 均无横向滚动。
- 完整 48 方案默认放进 `<details>`，源码、限制与 rubric 不是第一屏噪声。
- claim 与 context 的视觉文案明确。

### 阻断

- 四个 quick-brief grid 全部占布局；用户必须连续看四套 8 卡摘要。
- 每个能力的四个场景推荐也全部占布局；页面恢复成高密度长报告。
- 点击场景只改变按钮 active 样式，内容没有收敛到所选场景。
- “为什么”卡实际只复述选择算法，仍要求用户自己理解 class 与场景的关系。

所以视觉方向是正确的，但交互结果与信息架构目标相反，不能因为静态截图首屏好看而判 PASS。

## 独立验证记录

专项测试：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_reference_catalog \
  tests.test_comparison \
  tests.test_comparison_report \
  tests.test_cli.CliTest.test_compare_command_writes_feature_first_report -v

Ran 20 tests ... OK
```

此外使用真实 Chromium 完成：

- 1440×1000 desktop 渲染；
- 390×844 mobile 渲染；
- 四个 scenario button 点击；
- 每个 pane 的 `hidden` 与 computed `display` 检查；
- 页面 scrollWidth / clientWidth 检查；
- 七份 HTML 的本地链接解析和目标存在性检查。

独立 code-review lane 复算后得到相同结论：其余验收数字通过，scenario visibility 为阻断性 P1，推荐 `REQUEST CHANGES`。

## 再次复审前的验收门槛

1. 修复 `[hidden]` 与 `display:grid` 冲突，四个场景只能显示当前选中的一组。
2. 增加真实浏览器测试，初始和每次点击后都必须只有 9 个场景 pane 可见。
3. 为每个“场景 × 能力”的 route priority 写出具体 fit rationale 与 switch condition。
4. `why` 至少引用一项可观察实现差异或 reviewer rubric 维度，而不是只复述选择算法。
5. 更新正式 HTML，并重新验证 7 份 HTML 的 853 个链接或新的准确计数。
6. 更新 fix 记录的专项测试数，并提供可复现命令。

## 残余边界

- `verified` 表示固定 remote、HEAD 与 catalog-required source bundle 一致，不表示整个仓库所有文件 clean；dirty 状态单独展示。
- 48 项 catalog 是人工源码审计结论；只有 15 条是当前机器可复核的逐 claim 证据，其余 170 条只是诚实 context。
- reviewer rubric 与 scenario route priority 不是性能 benchmark；最终仍需要目标仓规模、语言、延迟、内存和许可证 PoC。
- 静态 HTML 在打开时不会重新执行 Git/源码校验；`generated_at` 与 catalog revision 是快照新鲜度边界。
- `file://` 下钻依赖当前机器仍保留相同绝对路径。

## 最终判断

**REQUEST CHANGES。Architecture status：BLOCK。**

本轮修复不是无效：身份、正式产物、证据语义、三处事实修正、四场景数据和 SourceBridge Go 索引都已达到本轮验收。剩余阻断也很聚焦：正式 HTML 没有真正隐藏非当前场景，决策理由仍是算法模板。修复这两项并补浏览器回归后，才可以再次申请 PASS。
