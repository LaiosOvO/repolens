---
name: repository-report
description: 为技术选型生成面向人类、源码证据闭合的仓库业务功能报告。用于先确认一个仓库真正提供哪些业务能力，再生成讲清交互、状态、路由、循环、难点、工程结构和复用边界的离线 HTML。
---

# 仓库业务功能报告

调用已经安装的 `repo-teacher` 生产流水线。Skill 只负责编排、展示人工确认点和汇报产物；索引、Prompt、Schema、Provider、缓存、证据校验和 HTML 渲染都由 Python 产品实现。

## 工作流

1. 明确源码仓库和输出目录。
2. 先执行功能目录：

   ```bash
   repo-teacher inventory SOURCE --output capability-inventory.json
   ```

3. 向用户展示：项目一句话定位、按重要性排序的功能标题、每项一句话结果、核心模块和证据数。停在这里等待用户确认；不得提前生成章节。
4. 用户确认后，用同一份不可变目录生成完整报告：

   ```bash
   repo-teacher report SOURCE --output OUTPUT_DIR \
     --inventory capability-inventory.json
   ```

5. 验证稳定入口：

   ```bash
   repo-teacher validate OUTPUT_DIR/index.json --source SOURCE
   repo-teacher validate OUTPUT_DIR/current/index.json --source SOURCE
   ```

6. 最终汇报 `index.html`、功能数、源码证据数、验证结论、运行时间和剩余未知项。

## 产物要求

- 主要交付：`index.html`，先说项目本质，再讲工程结构、产品主轴、业务功能和实现机制，源码证据放最后。
- 审批交付：`capability-inventory.json`，必须带非空 `module_dispositions`。
- 机器交付：`index.json`、`analysis-pack.json`、`capability-graph.json`、`human-report.json`。
- 过程交付：阶段 manifest、项目概览、逐章 JSON、验证报告；允许只重跑失败阶段。

完整阶段表见 [references/pipeline-contract.md](references/pipeline-contract.md)，阶段字段合同见 [references/artifact-contract.md](references/artifact-contract.md)，
`capability-inventory.json` 的公开 Schema、不变量与 Good/Bad Cases 见 [references/capability-inventory-schema.md](references/capability-inventory-schema.md)。
只在调试失败阶段、审查 Schema 或接入新 Provider 时读取这些 references。

## 不可妥协的质量门

- CodeGraph 先于模型归纳。
- 功能判断来自关系图、源码证据、用户动作和可见结果；禁止用正则或关键词决定功能。
- 路由、文件、类、health、静态页、测试和通用 UI 不是独立业务功能。
- 每章第一句必须先说机制本质，再用真实交互图和文字讲状态、循环、路由、并发、结束与失败。
- 每个因果结论必须能回到 canonical source refs；未知就明确写未知。
- 无效、过期、Schema 不完整或证据闭包失败的缓存必须拒绝并只重跑对应阶段。
