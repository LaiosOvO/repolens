# 产品形态证据汇总

## 用户目标

输入一个本地代码仓库，输出该项目自己的人类报告包。`index.html` 是主阅读入口，也可以附带 `report.json`、证据清单和模块索引。页面先让读者理解“项目是什么、有哪些功能”，再解释每个功能的实现、技术、源码和复用边界。读者看完多个项目后，自己决定“哪个功能参考哪个项目”。

## 产品形态证据矩阵

| 项目 | 实际形态 | 稳定产物 | 对目标的主要贡献 |
| --- | --- | --- | --- |
| codebase-to-course | Skill | interactive HTML course / course directory | 最接近“产品先、实现后”的人类教学合同 |
| learn-codebase | Skill | 对话与 learning journal | 苏格拉底式理解、预测/揭示/回忆，不是索引内核 |
| PocketFlow Code2Tutorial | Python script/CLI | Markdown tutorial output | abstraction→relationship→chapter→write 的可读叙事流水线 |
| CodeWiki | CLI + MCP | docs / GitHub Pages viewer | CLI 交付、层次化模块分解、MCP 作为第二入口 |
| OpenWiki | CLI + local visualizer | 自维护 Markdown Wiki | 本地/CI 更新、no-op、critic/validation、可视化 |
| CodeBoarding | CLI + Web explorer | `analysis.json`、Markdown、Mermaid | 静态事实、调用图、组件、增量分析底座 |
| SourceBridge | Go platform + CLI + MCP + Web/IDE | field guides / tours / paths | Go 长时内核、多表面共享证据；范围与许可证不宜整体复制 |
| Understand Anything | Skill/plugin + Dashboard | knowledge graph / onboarding | freshness、持久图、guided tour；Skill 消费索引而非替代索引 |
| DeepWiki Open | Web app | interactive Wiki / CodeMap | 层级页面、引用、源码下钻；首期无需复制服务端 |
| GitNexus | CLI + MCP + Web | `.gitnexus` 图与 Wiki | 预计算图服务 Agent 与 Wiki；形态仍以独立 CLI 为底座 |
| CodeGraph | MCP server + IDE | semantic graph / tools | 分析引擎与工具面，不是人类报告成品 |
| Serena | CLI + MCP toolkit | live symbol/reference/edit | 用户选定功能后的 live semantics adapter |
| Waku Agent | Python CLI + Dashboard/Gateway | Agent 运行时状态 | 第一阶段唯一 E2E 语料，不是教学产品先例 |

## 最终结论

1. **不是纯 Skill**：Skill 擅长进入教学/执行模式，但无法独立承担多语言解析、增量、新鲜度、证据验证和可重复发布。
2. **是独立项目**：核心需要持久状态、版本化模型、测试和多个调用面。
3. **CLI 是第一入口**：`repo -> artifact` 最适合本地、CI、批处理、Codex Desktop 和未来 ACP 调用。
4. **每项目有自己的报告包**：HTML 是给人的主入口，JSON/证据/模块索引是给机器和后续 Agent 的附件；目录页只导航，不替用户排名。
5. **Skill 是二期薄封装**：用户选择功能后，Skill 调 CLI 导出模块索引和阅读包。
6. **Web 延后**：只有出现多仓托管、账号、协作和持续交互需求时才增加。

## 这份结论如何落地

- 正式 ADR：[`../decisions/0001-go-project-cli-and-human-project-report.md`](../decisions/0001-go-project-cli-and-human-project-report.md)
- 阅读导航：[`reading-order-and-decision.md`](reading-order-and-decision.md)
- 第一阶段验收页：[Waku 人类报告包](/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects/waku-agent/index.html)

## 说明

- 这份矩阵回答的是“产品应该长成什么样”，不是“哪个项目整体最好”。
- 用户最终仍然需要看具体项目页，再自己决定某个功能参考哪个项目。
