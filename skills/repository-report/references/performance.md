# 性能与恢复合同

本合同只优化重复劳动，不减少产品表面、核心功能或实现证据。固定阶段仍按 `context → graph → project/surfaces → capabilities → evidence plan → implementation → engineering → render` 前进；允许并发的只有阶段内部彼此独立的功能章。

## 1. 三条不变量

1. **一次读取，多处消费**：产品声明/路由/对象只读一轮；公共运行时、状态、协议只取证一次；HTML 只消费 Markdown。
2. **局部失效**：某个功能的源码变化只失效它的 evidence、正文及下游汇总；样式变化只失效 render。
3. **有界并发**：最多 3 个功能单元并发；不得按文件、符号或 surface 启动 Agent，不得递归分派。

## 2. `00-run-manifest.md`

每次运行先写或更新：

```markdown
# Run manifest
- source_snapshot: {Git HEAD + tracked dirty diff hash + relevant untracked manifest，非 Git 则为确定性文件 manifest}
- skill_contract: {SKILL.md 与直接 references 的内容指纹}
- codegraph_identity: {实现/版本 + index snapshot/status}
- started_at: {ISO 8601}

| stage/unit | input fingerprint | artifact | status | cache reason | wall time |
|---|---|---|---|---|---:|
```

允许使用现成的 `git`、`date`、CodeGraph CLI/MCP 与普通文件读取；不得新增 Python/JavaScript/Shell helper。未能可靠计算源码身份时宁可标记 miss，不得猜 hit。

## 3. 阶段指纹

| 阶段 | 输入指纹至少包含 | 不应包含 |
|---|---|---|
| context | source snapshot、顶层产品声明/manifest | HTML/CSS |
| graph | source snapshot、CodeGraph 实现/版本/配置 | 写作 Prompt |
| project + surfaces | context、产品声明、路由/命令、持久对象、Worker/集成入口、coverage 合同 | chapter/html 合同 |
| capabilities | surface ledger、核心准入合同 | 源码全文、HTML |
| evidence plan | capabilities、CodeGraph snapshot、共享运行事实 | CSS |
| 单个功能 evidence/正文 | capability/surface IDs、分配的源码/图节点内容、chapter 合同 | 其他无关功能、HTML |
| engineering | context、surface、已确认公共事实 | 功能正文措辞 |
| render | 所有已通过 Markdown 内容、html 合同 | 源码、CodeGraph、外部研究 |

复用前只做四项轻量检查：指纹一致、产物存在、必需标题/ID 闭合、引用源码路径仍存在。不要为了验证缓存而重新做原阶段。

## 4. 一次产品读取

在同一读取批次收集六路 origin，同时写 `01-project.md` 和 `02-product-surfaces.md`。先建立 origin ledger，再归并 surface；禁止为两份文件分别扫描 README、路由、页面、API 和持久对象。`02-capabilities.md` 只消费 surface ledger，不重新读源码。

## 5. 共享证据计划

`02-evidence-plan.md` 必须包含：

- `shared_facts`：公共启动链、身份/权限、provider、状态库、事件总线、Worker/外部协议；每项只有一个证据位置；
- `capability_units`：功能 ID、surface IDs、入口节点、结果节点、要查询的关系、允许源码路径、与 shared facts 的引用；
- `ownership`：每个功能的 `.evidence.md` 与 `.md` 唯一写入者；
- `gaps`：CodeGraph 未解析边和必须定向读源码的原因。

优先一次查询同一关系社区中的多个入口/状态节点，再按功能拆结果。不要对十三项证据各发一次查询；不要让每个功能重新查询同一 provider、store、event bus 或进程入口。

## 6. 功能章并发

- 默认 `min(3, 核心功能数)` 个独立单元；当前环境不支持并发时顺序执行，但仍复用共享事实。
- 每个单元只拿自己的 capability unit 与必要 shared facts，不拿整仓上下文。
- 单元内严格 `evidence → chapter`；不同单元可并行；最终只串行检查术语一致、surface exact-once 和跨章矛盾。
- 某单元失败只保留为 failed/gap，不重启已通过单元，不启动“全局语义返修”。

## 7. 零再推理 render

`05-report.md` 是目录、数量、章节顺序、业务↔核心映射和待核验摘要，不再改写全部章节。`index.html` 直接采用已通过 Markdown 的标题、自然语言主链、规则表、图和证据；允许为 HTML 转义和导航生成做机械调整，禁止重新读源码或让模型再次总结同一功能。

用户明确内容优先时，浏览器验收不进入关键路径；只做 HTML/锚点/Mermaid 结构检查并如实记录。视觉验收可在内容确认后单独执行。

## 8. 计时与慢阶段处理

记录每阶段的 `started_at`、`completed_at`、wall time、cache hit/miss、CodeGraph query 数、读取源码文件数、功能单元数与并发峰值。并发阶段的 wall time 是最早开始到最晚结束，不能把子单元耗时相加冒充总耗时。

若某阶段超过当前总 wall time 的 35%，先按原因处理：

- surfaces 慢：检查是否重复扫描 product inputs，改为 ledger diff；不能静默截断；
- implementation 慢：合并公共查询、缩小单元上下文、启用最多 3 路并发；不能减少证据项；
- render 超过 60 秒：停止源码读取与重新总结，只做 Markdown 到 HTML 的机械组装；
- CodeGraph 慢：区分首次建图与增量 sync，后续不得重复 init；
- 外部对照慢：先交付当前仓库源码解释，把未完成对照标为待核验；不得阻断 HTML。

## 9. 目标与诚实报告

- 同一快照 warm run：目标 3–5 分钟；
- 首次小/中型仓库：目标 5–12 分钟；大型仓库另报首次 CodeGraph 建图时间；
- 任何超时必须在 `performance.md` 说明慢阶段、输入规模、query/文件数、缓存命中和下一次可复用边界。

目标不是完成声明。只有实际计时满足时才能宣称达到；否则报告真实数字。
