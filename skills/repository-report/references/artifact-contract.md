# 阶段产物字段合同

所有 JSON 产物必须是 UTF-8 object，包含 `schema_version`；进入 generation 的 JSON 还必须包含相同 `generation_id`。

## `capability-inventory.json`

- `project_summary`：产品类型、主要用户、主要结果、主运行时、明确非目标。
- `capabilities[]`：稳定 ID、标题、第一句总述、用户/目标/结果、因果流、重要性、实现模块、feature/evidence IDs、至少三条源码引用。
- `module_dispositions[]`：模块路径、`core-capability|supporting|excluded`、最终 capability IDs、原因。
- `source_manifest_sha256`、`cache_key`、`schema_version`。

任何空 `module_dispositions`、未知 ID、越界路径或少于三条源码引用都必须拒绝。

## `project-overview.json`

- “这是什么项目”的一句话结论；
- 产品类型、用户、核心结果、差异点与非目标；
- 前端/后端/Worker/媒体/共享协议/部署模块表；
- 工程组织判断及证据；
- 产品主轴顺序和每条主轴包含的 capability IDs；
- 所有判断的 source refs 与未知项。

## `chapters/<capability-id>.json`

- `plain_summary`：第一句先说本质；
- `interaction`：触发者、接管者、输入、步骤、分支、输出、消费者和结束条件；
- `state_flow`：每步读取、写入、下一步决策者；
- `mechanism`：存储/查询、循环、并发、等待、路由、失败与恢复；
- `execution_narrative`：入口输入、字段/状态决策、核心转换、状态提交、下游唤醒、终止返回的自然语言因果链；
- `rule_matrix`：候选生成、合法性校验、选择/路由、调度/并发、停止、失败/恢复；逐项区分 Prompt/模型规则与宿主代码硬规则；
- `alternatives`：至少两种同类框架/范式的控制权、动态时机、路由、持久化、恢复与适用边界，并附官方来源；
- `difficulties`：不变量、天真实现、失败表现、当前取舍；
- `reuse`：可直接借鉴、必须改造、不要照搬、仍需验证；
- `source_refs`：canonical paths/lines/evidence IDs/relationship IDs。

## `validation-report.json`

- 各阶段 PASS/FAIL；
- Schema、源码身份、路径/行号、ID、模块覆盖、引用闭包、缓存新鲜度；
- HTML 本地链接、fragment、交互图闭包、移动端与离线结果；
- 阻断问题和必须重跑的最小阶段。

## `run-manifest.json`

- generation、源码快照、provider/model、prompt/schema 版本；
- 每阶段开始/结束/状态、输入 digest、输出文件与 digest；
- inventory approval digest；
- 最终发布文件清单和剩余未知项。

报告输出目录同级的 `<output>.run-manifest.json` 是权威运行日志；它在原子发布前写 `atomic-publication: started`，切换 `current` 成功后才改成 `passed`。generation 内的同名文件是不可变的发布前快照，并通过 `authoritative_journal` 指向权威日志，避免自我发布产生循环证明。

Skill 最终只向用户突出 `index.html`、功能目录、验证结论和剩余风险；其余 JSON 用于增量重跑、审计和其他 Agent 消费。
