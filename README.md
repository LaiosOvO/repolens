# Repo Teacher

Repo Teacher 当前阶段的目标很窄：先把“陌生代码仓库讲清楚”这件事做对，再决定后续 Skill、看板、ACP 或更大的协作系统怎么接。

现在已经完成的是：

- 13 个参考/验收仓的逐仓阅读笔记；
- 基于这些阅读结果收敛出的产品形态决策；
- 一个 Waku Agent 的 Go 版人类报告纵向切片；
- 一份更容易扫读的研究总览页。

先看这里：

- [RepoLens 产品需求与换机交接](/Volumes/T7/workspace/ontology/graph/dev/repo/REPOLENS-REQUIREMENTS.md)
- [研究导航 HTML](/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-teacher-reading-guide.html)
- [逐仓阅读索引](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/README.md)
- [阅读顺序与技术决策](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/reading-order-and-decision.md)
- [正式 ADR](/Volumes/T7/workspace/ontology/graph/dev/repo/docs/decisions/0001-go-project-cli-and-human-project-report.md)
- [Waku 人类报告包](/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects/waku-agent/index.html)

## 当前结论

- 产品核心应该是**独立项目**，不是把能力直接塞进某个 Skill。
- 第一正式入口应该是**CLI**，因为 `repo -> artifact` 最适合本地、CI 和可重复执行。
- 给人的主产物是**每仓一个人类报告包**，其中 `index.html` 负责叙事，`report.json`、`evidence.json`、`modules.json` 负责证据与机器消费。
- Skill 适合做**二期薄适配器**，在用户选中功能之后再导出阅读包和任务包。
- 第一阶段只用 **Waku Agent** 做端到端验收，不急着覆盖所有语言和所有参考仓。

## 当前不是完成态的部分

- 还没有把 13 个参考仓全部变成正式的人类项目页 HTML；
- 还没有把自动分析从 Python 研究原型完整迁到 Go；
- 还没有做跨项目自动选型页、ACP 接入、看板派单和本地知识管理闭环。

## Go 纵向切片

当前可运行命令：

```bash
go run ./cmd/repo-teacher report \
  --repo /Volumes/T7/workspace/ontology/graph/repo/waku-agent \
  --profile /Volumes/T7/workspace/ontology/graph/dev/repo/profiles/waku-agent.json \
  --output /Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects/waku-agent

go run ./cmd/repo-teacher verify \
  --repo /Volumes/T7/workspace/ontology/graph/repo/waku-agent \
  --profile /Volumes/T7/workspace/ontology/graph/dev/repo/profiles/waku-agent.json \
  --bundle /Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects/waku-agent
```

它当前做的是：

- 严格读取并绑定已审阅 profile，明确区分人工功能语义与程序证据校验；
- 验证源码路径和行范围；
- 为每条源码证据计算内容哈希；
- 原子生成 `index.html` + `report.json` + `evidence.json` + `modules.json` + `manifest.json`；
- 用 `verify` 重放产物哈希、仓库快照、源码证据和 HTML/JSON/模块闭包。

对应入口代码：

- [main.go](/Volumes/T7/workspace/ontology/graph/dev/repo/cmd/repo-teacher/main.go)
- [load.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/load.go)
- [render.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/render.go)

## 文档分层

- `docs/project-readings/`：逐仓阅读笔记和决策材料。
- `docs/decisions/`：候选/已冻结 ADR。
- `biz/docs/html/`：给人看的导航页和报告页。
- `outputs/waku-agent/`：当前 Go 纵向切片产物。

这份 README 只保留真实状态，不再把研究原型说成完整生产系统。
