# RepoLens 流水线合同

生产实现以 `repo_teacher.commands` 和 `repo_teacher.pipeline` 为准。Skill 只负责编排人工确认点，不能复制或绕过产品逻辑。

| 阶段 | 负责者 | 核心输入 | 必交付产物 | 失败后回到 |
| --- | --- | --- | --- | --- |
| 00 固定源码 | CLI | 仓库路径、输出路径 | `source-manifest.json`、提交身份、排除目录 | 重新固定源码 |
| 01 图索引 | CodeGraph + analyzers | 固定源码快照 | `index.json`、`capability-graph.json`、诊断 | 修分析器或重新索引 |
| 02 证据包 | 项目定位分析员 | 图索引、manifest、README 导航 | `analysis-pack.json`、`project-overview.json`、源码切片清单 | 缩小/补齐证据范围 |
| 03 功能目录 | 业务能力分析员 | 有界证据包、业务域 | `capability-inventory.json`、`module_dispositions` | 重新归纳对应业务域 |
| 04 独立语义反证 | 能力证据审校员 | 原始候选、最终功能目录、Schema、canonical index | `inventory-validation.json`、稳定 issue code；最多一次受控修复 | 回到证据包/功能目录/全局分组 |
| 05 人工确认 | 使用者 | 已审校功能标题、摘要、范围 | `approval.json` 或人工提供的固定 inventory | 修改目录后重审 |
| 06 章节生成 | 业务功能机制讲解员 | approved inventory、按章源码切片 | `chapters/*.json`、`chapter-validation/*.json`、`human-report.json` | 仅重跑失败章节 |
| 07 人类审校 | 人类阅读审校员 | 首页、章节、图、HTML 预览 | `human-readability-review.json`、`validation-report.json` | 回到定位/目录/章节对应阶段 |
| 08 原子发布 | CLI | 全部 PASS 产物 | immutable generation、`current/`、`index.html`、`run-manifest.json` | 保留旧 generation，不切 current |

## 不可变规则

1. CodeGraph 和 canonical index 必须先于模型分析。
2. 功能目录必须在章节写作前确认；章节不能重新发明功能。
3. 每个阶段只读取其声明的输入，只写自己的版本化产物。
4. Provider 可以更换 Codex、OpenCode 或 DeepSeek，但不能改变 Schema、证据闭包、阶段顺序和发布语义。
5. 路由、类、页面、health、静态首页、测试和普通 helper 不能单独升级为业务功能。
6. 缓存必须同时绑定源码 manifest、analysis fingerprint、prompt 版本、Schema 版本和模型配置。
7. 每个模型包必须同时满足 byte/token 上限；超大模块可按真实源码子路径取证，但最终 `module_dispositions` 必须折回原始 CodeGraph 模块。
8. 阶段状态在进入阶段时写 `started`，完成后才写 `passed`；失败必须保留 issue 与 `retry_stage`，禁止成功后批量补写全 PASS。

更详细的文件字段见 [artifact-contract.md](artifact-contract.md)。
