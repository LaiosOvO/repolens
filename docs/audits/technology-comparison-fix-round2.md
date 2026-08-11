# 技术选型比较第三轮修复记录

日期：2026-08-10  
对应复审：`docs/audits/technology-comparison-reaudit.md`  
状态：实现与专项验证完成，等待新的独立 Agent 复审；本文不自行宣告 PASS。

## 30 秒结论

本轮关闭了复审提出的四组 P1 实现问题：curated 身份不再相信导入 JSON；源码引用区分“精确 claim 证据”和“只供继续阅读的上下文”；四种场景现在真正改变推荐路线；首屏直接回答每项能力选哪条路线、借哪些模块、为什么以及限制。SourceBridge 与 OpenWiki 的三个事实边界也已经按实际源码修正。

正式 `examples/reference-selection` 已在 Go analyzer 稳定后通过产品 CLI 从六个真实仓库完整重生成。正式 SourceBridge 索引包含分析指纹、10,922 个 Go 符号和 69,231 条 Go 关系；比较报告与六份项目报告均为 schema `2.0` 的当前产物。

## P1 修复对照

| 复审问题 | 本轮实现 | 验证证据 |
|---|---|---|
| 身份仍信任 index remote/commit | `reference_identity_status()` 直接从 `project.path` 执行 Git 只读查询，要求该路径就是 worktree top-level；读取真实 `origin`、`HEAD`、tracked dirty state，并重算必需源码 worktree bundle。普通目录即使复制同一批文件并伪造 JSON 也只能是 `unverified`。 | 新增普通目录冒充、真实 remote 改写、真实 HEAD 改写、bundle/hash 篡改测试。六个本地固定仓以故意伪造的 index remote/commit 重放，仍由真实 Git 得到 6/6 verified。 |
| 源码链接不能支撑 claim | catalog 新增独立 `AUDITED_CLAIMS`；每条精确证据包含 `path + line_start + line_end + snippet + snippet_sha256 + claim_evidence_id`，并汇总到 comparison 顶层 `claim_evidence`，option 用 `claim_evidence_ids` 闭包引用。未做 claim 审计的 index EvidenceRef、symbol 或整文件入口分别标为 `index-evidence-context`、`symbol-definition`、`whole-file-context`，`supports_option_claim=false`，页面明确显示“仅作上下文，不等价于事实证据”。 | DeepWiki grounding 精确落到 `128-148`、`178-222`、`305-309`；SourceBridge federation、workflow story 与 OpenWiki critic policy 也有精确范围。真实六仓探针得到 185 个引用，其中 15 个关键 claim 精确 hash 证据，其余 170 个诚实标注为上下文，不再把首个 symbol/整文件伪装成事实证明。 |
| scenario_scores 没有驱动页面选择 | 新增 `SCENARIO_ROUTE_PRIORITIES`，先按场景选择可比较的技术对象，再在同一 class 内用 `scenario_scores ± uncertainty` 选首选；同时给出备选路线、理由、关键代价与模块借鉴计划。HTML 提供四个场景按钮，切换首屏和每个能力的推荐面板。 | 新增场景改变 Agent workflow 推荐路线的单测；真实六仓探针中八项能力的默认首选数最大为 1，不再因 singleton class 把 5–6 个项目全部标成首选。 |
| 页面首屏没有可执行结论 | 30 秒摘要现在逐能力显示首选项目、技术路线和不确定性；能力面板显示首选/备选、why、trade-off、建议借鉴的具体源码模块。完整 48 方案仍在折叠区用于复核。 | HTML 专项测试检查场景控件、推荐路线、模块计划、源码/项目链接、安全转义与嵌入 JSON。 |

## 事实边界修正

### SourceBridge federation

- 增加 `internal/db/store_federation.go`，明确 SurrealDB store 才实现 repository link 与 cross-repo reference。
- 保留并精确引用 `internal/graph/store.go:2100-2138`，把它描述为 in-memory stub，不能再把该文件当作 federation 实现。
- 新增路径使 SourceBridge 固定 bundle 从 33 个路径扩为 35 个路径，并更新 bundle SHA-256。

### SourceBridge Workflow Story

- `tutorial-generation` 的 source paths 增加 `workers/knowledge/workflow_story.py`。
- 精确引用生成入口 `611-636` 与 evidence threshold/confidence floor `729-753`。

### OpenWiki critic 次数

- catalog 现在明确写为 `prompt-enforced`，不是 runtime 状态机保证。
- 精确引用 `src/agent/prompts/code.ts:133-136`，对应初审后“再调用一次”的提示词规则。

## 证据语义

页面现在区分四种范围：

1. `claim-evidence / claim`：明确支持当前 catalog 的一个原子事实，有精确行范围与 snippet hash。
2. `index-evidence / index-evidence-context`：索引里的真实片段，但没有经过 catalog claim 绑定，只能作为上下文。
3. `symbol-context / symbol-definition`：精确符号范围，只能证明入口/定义存在。
4. `file-context / whole-file-context`：整文件阅读入口，不支持自然语言事实判断。

这个边界是刻意的：宁可承认尚未完成 claim 审计，也不再把“链接能打开”写成“结论已被证明”。

## 验证结果

```text
专项测试：19 tests，全部通过
Ruff：All checks passed
compileall：通过
全量 unittest discover：159 tests，全部通过
```

真实六仓产品 CLI 正式重放（输出到 `examples/reference-selection`）：

```text
projects                         6
Git + required bundle verified  6/6
capabilities                     8
curated options                 48
source references              185
exact claim evidence            15
honest context references      170
default primary max/capability   1
scenario sets complete           true
DeepWiki grounding ranges        128-148 / 178-222 / 305-309
project report links             96
source links                    347（含四场景模块计划的重复入口）
project reports                   6
schema                            2.0
catalog revision                  2026-08-10.3
SourceBridge fingerprint          c946d4799102bdccfe3cccde9a3dbf7fe40bcbc7d1a3a74b6d1d05d545d5830b
SourceBridge Go symbols           10922
SourceBridge Go relationships     69231
local HTML/file links checked     853
scenario route variants           4
```

正式产物还额外验证了以下闭包：所有 option 的 `claim_evidence_ids` 都能解析到顶层 claim；15 条 claim 的行范围均在真实源码边界内，片段重新计算后的 SHA-256 与报告一致；七份 HTML 中解析到的 853 个本地报告/源码链接全部存在；四种场景产生四组不同的推荐结果。

## 待独立复审

启动一个新的独立 Agent，逐项复审本文和原复审报告的四个 P1；只有该 Agent 的结果可以决定是否 PASS。
