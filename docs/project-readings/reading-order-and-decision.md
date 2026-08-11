# 阅读顺序与技术决策

这份文档只做一件事：帮你快速决定应该先读哪些项目，以及这些阅读最后支持了什么产品形态决策。

## 如果你只有 20 分钟

按这个顺序读：

1. [codebase-to-course.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/codebase-to-course.md)
原因：它最接近“把仓库讲成人类能读懂的页面”，但它是 Skill，不是独立分析内核。
2. [codewiki.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/codewiki.md)
原因：它证明 CLI 很适合把仓库稳定变成文档产物。
3. [pocketflow-code2tutorial.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/pocketflow-code2tutorial.md)
原因：它给了“先总览、再抽象、再关系、再章节”的叙事骨架。
4. [openwiki.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/openwiki.md)
原因：它最值得借的是覆盖检查、critic 和增量更新，不是页面长相。
5. [sourcebridge.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/sourcebridge.md)
原因：它说明重型能力应该在独立项目里持有，再向 CLI/Web/MCP 暴露。
6. [waku-agent.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/waku-agent.md)
原因：它是第一阶段唯一端到端验收仓，不是产品形态基准。

## 如果你是在回答不同问题

### 我想知道“项目应该做成什么形态”

先读：

- [codebase-to-course.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/codebase-to-course.md)
- [codewiki.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/codewiki.md)
- [openwiki.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/openwiki.md)
- [sourcebridge.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/sourcebridge.md)
- [deepwiki-open.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/deepwiki-open.md)

结论：

- 纯 Skill 最适合教学交互，不适合做索引内核。
- CLI 最适合第一正式入口。
- Web/平台形态适合二期以后，不适合当前问题。

### 我想知道“页面叙事怎么组织”

先读：

- [codebase-to-course.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/codebase-to-course.md)
- [pocketflow-code2tutorial.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/pocketflow-code2tutorial.md)
- [learn-codebase.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/learn-codebase.md)

结论：

- 页面必须先讲项目是什么和有什么功能，再讲实现。
- 不能直接从文件树和入口函数开始。
- 章节顺序应该是“30 秒判断 → 功能地图 → 一条真实主线 → 功能卡 → 复用决定”。

### 我想知道“证据和质量门怎么做”

先读：

- [openwiki.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/openwiki.md)
- [codeboarding.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/codeboarding.md)
- [sourcebridge.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/sourcebridge.md)
- [serena.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/serena.md)

结论：

- 证据要落到文件、符号、行范围和测试。
- 覆盖检查与未知项必须显式保留。
- 用户选中功能之后，才进入 live symbol/reference 级下钻。

### 我想知道“图和长期语义索引怎么借”

先读：

- [understand-anything.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/understand-anything.md)
- [gitnexus.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/gitnexus.md)
- [codegraph-ai.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/codegraph-ai.md)
- [serena.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/serena.md)

结论：

- 图层、语义层、教学层应拆开。
- 图本身不是人类报告。
- Serena 更适合“读完项目页后再钻模块”，不适合替代项目页。

## 最终技术决策

### 1. 产品形态

采用：**独立项目**

不采用：纯 Skill、纯 Web 平台、直接延长当前 Python 研究原型

原因：

- `codebase-to-course` 和 `learn-codebase` 证明 Skill 适合教学合同；
- `codewiki`、`openwiki`、`codeboarding` 证明独立 CLI 才适合稳定交付；
- `sourcebridge`、`deepwiki-open` 证明更大的平台能力应该建立在独立内核之上。

### 2. 第一正式入口

采用：**CLI**

原因：

- 最容易做本地、CI、批处理和可重复生成；
- 后续 Skill、桌面端、ACP 都可以调用同一入口；
- 不会把分析内核绑死在某个 Agent 宿主里。

### 3. 给人的主产物

采用：**每仓一个人类报告包**

最小产物结构：

- `index.html`
- `report.json`
- `evidence.json`
- `modules.json`

原因：

- HTML 负责让人先看懂；
- JSON 附件负责让机器和后续 Agent 接着工作；
- 这比只生成一篇长文或者只生成一份 JSON 都更稳。

### 4. Skill 的位置

采用：**二期薄适配器**

原因：

- 用户先读项目页；
- 选中功能后再导出模块索引、Skill 和阅读路线；
- Skill 不负责重新做索引、聚类、证据验证。

### 5. 首期验收仓

采用：**只用 Waku Agent**

原因：

- 它同时覆盖 Loop、Memory、Graph、Gateway、Voice、Tools/MCP、Providers、Dashboard、Eval；
- 足够复杂，能暴露报告是否还在“文件平铺”；
- 范围可控，适合先打通一条纵向闭环。

## 哪些项目各自贡献最大

| 项目 | 最该借的部分 | 明确不要照搬的部分 |
| --- | --- | --- |
| codebase-to-course | 人类教学页面合同 | 把分析内核做成纯 Skill |
| codewiki | CLI 交付与层次化模块拆解 | 直接把仓级文档当成功能页 |
| pocketflow-code2tutorial | 教程章节生成顺序 | 把弱证据直接写成确定结论 |
| openwiki | critic、QA、增量更新、未知项保留 | 把 Wiki 覆盖误认为教学完成 |
| sourcebridge | 多表面共享同一证据模型 | 直接复制其 AGPL 实现 |
| deepwiki-open | 交互式源码下钻形态 | 第一阶段就上完整服务端 |
| codeboarding | 全量/增量/局部分析模式 | 把静态分析结果直接等同于人类叙事 |
| understand-anything | 图层与学习路线 | 图即报告 |
| serena | 选中模块后的 live semantics | 用它替代项目级功能报告 |
| waku-agent | 端到端复杂验收语料 | 当作产品形态基准 |

## 已固化位置

- 正式 ADR：[/Volumes/T7/workspace/ontology/graph/dev/repo/docs/decisions/0001-go-project-cli-and-human-project-report.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/decisions/0001-go-project-cli-and-human-project-report.md)
- 研究导航 HTML：[/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-teacher-reading-guide.html](/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-teacher-reading-guide.html)
- 逐仓笔记索引：[/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/README.md](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/README.md)
