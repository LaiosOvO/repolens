# RepoLens 生产 Agent 合同

这里不是 Prompt 草稿目录。每个 `.md` 都是一个可独立执行、可版本化、可审计的 Agent 合同，必须自己写清：

- 中文角色目标；
- 精确输入与允许读取的范围；
- 按顺序执行的动作；
- 唯一输出 Schema；
- Good Case 与 Bad Cases；
- 质量门、失败语义和最小重跑阶段。

Prompt 的具体任务措辞放在 `repo_teacher/prompts/*.md`；JSON 结构放在 `repo_teacher/schemas/`；Agent 文件只引用它们，不复制第二份会漂移的实现。

## Agent 与阶段

| 顺序 | 中文 Agent | 文件 | 只读取 | 只产出 | 失败回到 |
| --- | --- | --- | --- | --- | --- |
| 1 | 项目定位与工程结构分析员 | `project-context-analyzer.md` | 固定快照、CodeGraph、canonical index、README 导航 | `project-overview.json` | evidence-pack |
| 2 | 业务能力目录分析员 | `business-capability-analyst.md` | 有界 analysis pack、源码切片、项目定位 | 模型阶段 inventory 核心字段 | evidence-pack 或 inventory |
| 3 | 能力证据与 Schema 审校员 | `capability-reviewer.md` | inventory、公开 Schema、canonical index、source manifest | `inventory-validation.json` | 精确失败阶段 |
| 4 | 业务功能机制讲解员 | `chapter-writer.md` | approved inventory 中的一项能力及其源码闭包 | `chapters/<id>.json` | 只重跑当前章节 |
| 5 | 人类阅读与技术选型审校员 | `human-report-reviewer.md` | 全部章节、图、HTML、浏览器结果 | `human-readability-review.json` | overview/inventory/chapter/renderer |

## 关键交接规则

1. 项目定位 Agent 不得发明 capability，只能把产品主张写成结构化项目合同。
2. 业务能力 Agent 只能基于已关闭的证据包和源码因果链归组；需要返修时，可以把“已批准主旅程的一段支持性实现”附加到冻结能力，但不得改写其语义。
3. 审校 Agent 不改写失败产物，只返回稳定错误码和最小重跑阶段；若发现某候选只是主旅程的前置步骤，应要求回到 global-grouping 而不是强行提升级别。
4. 章节 Agent 不得新增、删除、合并或改名 capability；它只解释已批准能力的运行机制、难点和复用边界。
5. 人类审校 Agent 不用 CSS 掩盖内容问题；内容缺失必须退回内容阶段，图若没有真实交互和状态语义也必须重写。
6. 任一 Agent 都不得用关键词或正则决定业务功能；CodeGraph 关系、源码因果链、已批准能力闭包和 review issue 才是事实基础。

## 唯一事实源

- 模型目录 Schema：`inventory_json_schema()`
- 最终目录 Schema：`persisted_inventory_json_schema()`
- 项目概览 Schema：`project_overview_json_schema()`
- 章节批次 Schema：`chapter_batch_json_schema()`
- 完整公开 Schema：`repo_teacher/schemas/capability-inventory-v1.schema.json`
- Good/Bad Cases：`tests/fixtures/capability-inventory/capability-inventory-*.json`

任何 Agent 文档示例与这些 Schema 不一致都属于发布阻断，而不是文档小问题。
