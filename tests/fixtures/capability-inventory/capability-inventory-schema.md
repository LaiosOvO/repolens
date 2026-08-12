# RepoLens 产品 CLI 的 `capability-inventory.json` 测试合同

本文件是产品 CLI 的测试 fixture，不属于 `repository-report` 纯 Skill 的执行合同。

## 两个 Schema 层次

1. `inventory_json_schema()` 约束模型阶段输出，只含 `project_summary`、`capabilities` 和 `module_dispositions`。模型不得伪造提交、快照、缓存或验证信息。
2. `persisted_inventory_json_schema()` 约束 CLI 最终落盘文件。在模型输出通过证据审校后，CLI 再绑定 `schema_version`、`generator`、`project`、源码 manifest、cache key 和 validation artifact。

机器可读 Schema 位于 `src/repo_teacher/schemas/capability-inventory-v1.schema.json`。它由同一 Python 定义机械导出，不允许手工维护第二份分叉合同。

## 顶层字段

| 字段 | 谁产生 | 含义 |
| --- | --- | --- |
| `project_summary` | 业务能力 Agent | 产品类型、主要用户、主要结果、主运行时和明确非目标 |
| `capabilities[]` | 业务能力 Agent | 面向用户结果的完整业务能力，不是文件/路由/类列表 |
| `module_dispositions[]` | 业务能力 Agent + 全局归组 | 每个产品模块进入核心能力、支撑或排除，并只引用最终 capability ID |
| `schema_version` | CLI | 固定为 `repo-teacher-capability-inventory/v1` |
| `grouping_complete` | CLI | 只有完成全局语义归组后才为 `true` |
| `generator` | CLI | 实际 Provider 与生产方法 |
| `project` | CLI | 仓库路径、提交、分支和分析指纹 |
| `source_manifest_sha256` | CLI | 一致源码快照 digest |
| `cache_key` | CLI | 绑定源码、Schema、Prompt 和 Provider 的缓存键 |
| `validation_artifact` | CLI | 同次运行的确定性验证报告 |

## 不能只靠 JSON Shape 表达的不变量

- capability ID 唯一且非空；
- 每项能力至少 3 条 canonical source refs；
- 路径必须是仓库相对 POSIX 路径，不能绝对路径、`..` 或反斜杠；
- source range 必须满足 `1 <= line_start <= line_end`；
- `module_dispositions[].capability_ids` 只能引用最终 capability ID；
- 每个 `implementation_modules[].path` 必须有对应 module disposition；
- `core-capability` disposition 必须绑定至少一个最终 capability ID；
- health、静态页、通用路由等是否属于业务功能由完整用户因果链判断，不能使用关键词或正则决定。

## 样例

- [Good Case](capability-inventory-good.json)：任务提交、Worker 执行与结果回传被组织成一项完整业务能力。
- [Bad Case：health 路由](capability-inventory-bad-health-route.json)：把单一路由冒充业务能力，Shape 和业务语义均不完整。
- [Bad Case：旧 ID 变异说明](capability-inventory-bad-unknown-disposition-id.json)：明确说明对 Good Case 施加的单一 JSON Pointer 变异；全局合并后仍引用 shard 临时 ID，必须 fail closed。

## 导出 Schema

```bash
PYTHONPATH=src python3 scripts/export_inventory_schema.py \
  src/repo_teacher/schemas/capability-inventory-v1.schema.json
```
