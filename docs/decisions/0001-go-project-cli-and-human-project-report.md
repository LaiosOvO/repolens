# ADR-0001：独立 Go 项目、CLI 入口、逐项目人类报告

## 状态

Accepted · 2026-08-10

> 接受依据：`docs/project-readings/` 中 13 个参考/验收仓的独立阅读笔记已经齐备，并形成了稳定一致的产品形态证据：独立项目、CLI 首入口、人类主叙述页、结构化附件、二期薄 Skill。

## 需求

Repo Teacher 的第一位读者是准备研究开源实现的人，而不是已经知道代码入口的维护者。对任意一个仓库，首要任务是让读者快速回答：

1. 这个项目是什么；
2. 它提供哪些主要功能；
3. 每个功能由哪些机制、状态和源码模块实现；
4. 哪些部分值得复用，哪些边界仍需验证。

读者会先分别理解多个项目，再自己决定“哪个功能参考哪个项目”。系统不能把自动排名或预先选好的技术组合冒充用户决策。

HTML 是给人阅读的主入口，但产物不限于单个 HTML。同一份报告可同时包含机器可读的 `report.json`、证据清单、模块索引和后续 Skill 导出。文件、符号、调用和入口是结论的证据，不是人类报告的叙事起点。第一期只使用 `waku-agent` 做端到端验收。

## 参考项目给出的产品形态证据

| 参考项目 | 已采用的产品形态 | 对本项目的启示 |
| --- | --- | --- |
| OpenWiki | 可安装 CLI，生成并持续维护本地 Wiki，再用本地 visualizer 阅读 | 分析管线必须是独立项目；CLI 适合本地仓库和 CI；人类页面是持久产物 |
| PocketFlow Code2Tutorial | 脚本/CLI 读取仓库，依次抽象、找关系、排序章节并写入 output | “先整体、再功能、再实现”的教学顺序应由生成管线保证，不能交给一个提示词 |
| DeepWiki Open | 完整 Web 应用，Wiki、CodeMap、CodeViewer 和引用链分层 | 页面需要层级导航和源码下钻，但首期不必复制服务端与账号体系 |
| CodeBoarding | 独立 CLI/服务，先构建静态关系和组件，再生成文档与图 | 代码事实和人类叙事必须分层；功能不能等同于入口数量 |
| SourceBridge | Go 后端、持久索引、field guide/code tour/MCP/Web 多表面 | Go 适合长时本地索引内核；多表面应共享一个证据模型，但不复制其 AGPL 服务实现 |
| Understand Anything | 持久图、Dashboard、guided tour、freshness/Skill | 报告需要版本与新鲜度；Skill 是索引的消费者，不应成为索引内核 |
| Serena | MCP/CLI 暴露 live LSP 的 symbol/reference/edit | Serena 适合用户选定功能后的语义下钻，不负责持久功能报告或教程编排 |
| CodeWiki / GitNexus / CodeGraph | CLI 为主，同时提供 Wiki、MCP、图和可视化 | 生产内核应可复用为多个界面；第一期只保留最小 CLI + 静态 HTML |
| codebase-to-course / learn-codebase | Skill/教学层，消费已有代码上下文 | Skill 很适合教学习惯和交互，但不能替代扫描、增量、证据校验与持久发布 |

## 决定

### 1. 产品是一个独立 Go 项目

- 一个仓库、一个可分发二进制、模块化单体；
- 本地完成扫描、解析、事实图、功能语义、证据验证和 HTML 发布；
- 不把分析内核塞进 Codex/Claude 的 Skill 目录；
- 不以 Web 服务、微服务、远程数据库作为首期运行条件。

现有 Python 实现保留为研究原型与行为 oracle；新产品能力以 Go 纵向切片迁移，不继续把 Python 原型包装成最终架构。

### 2. CLI 是首期唯一正式接口

第一期命令合同：

```text
repo-teacher report --repo <repo> --profile <reviewed-profile.json> --output <new-report-dir>
repo-teacher verify --repo <repo> --profile <reviewed-profile.json> --bundle <report-dir>
```

后续才增加：

```text
repo-teacher catalog <report-dir> --output <index.html>
repo-teacher export-skill <report.json> --feature <id> --output <dir>
```

CLI 适合本地、CI、Codex Desktop 和未来 ACP 调用；这些调用方不需要重新实现分析逻辑。

### 3. 每个仓库生成自己的人类报告包

每个项目的最小产物是：

- `index.html`：给人阅读的主入口；
- `report.json`：给 CLI、Agent、目录页和后续 Skill 复用的语义结果；
- `evidence.json`：结论到文件、符号、行范围、测试和内容哈希的闭包；
- `modules.json`：用户选中功能后，用于下钻的模块与阅读顺序索引。

主 HTML 固定采用以下叙事顺序：

1. **30 秒看懂**：定位、适用场景、最重要的 4–9 个功能；
2. **功能地图**：用产品语言讲功能，不先列入口/类/文件；
3. **逐功能实现**：提供什么；谁触发→谁接管→输出什么→谁消费；关键技术与状态；
4. **源码下钻**：模块、符号、行范围、测试与证据等级；
5. **复用判断材料**：可直接借鉴、需改造、不要照搬、仍未知；
6. **社区信号**：GitHub/X 只作需求和口碑信号，不作源码事实。

入口、符号统计、原始关系和文件树默认折叠到证据区。可以生成多个页面或附件，但必须从 `index.html` 一处理解阅读顺序，不得把未组织的文字和索引平铺给读者。项目页不替用户选出“赢家”。

### 4. 项目目录页只负责导航

目录页只显示：项目一句话定位、主要功能标签、报告的新鲜度和“打开项目”按钮。它不输出跨项目自动排名，不用一个巨大比较表替代项目页。

### 5. Skill 是二期薄适配器

Skill 只在用户读完项目页并选中功能后出现。它负责：

- 调用同一个 Go CLI；
- 传入仓库、commit 和 feature id；
- 导出选中功能的模块索引与阅读顺序；
- 把结果交给 Codex/Claude/OpenCode。

Skill 不负责扫描语言、建图、缓存、证据验证或 HTML 模板，否则同一能力会在不同 Agent 平台重复实现并发生漂移。

### 6. 首期只用 Waku Agent 做端到端验收

Waku 报告必须稳定解释九个功能：Agent Loop、Memory、Graph Workflow、Gateway、Voice、Tools/MCP、Model Providers、Dashboard/Observability、Eval/Release Gate。

每个功能都必须具备：

- 人类可理解的功能说明；
- 触发→接管→产出→消费链；
- 底层技术和关键状态；
- 关键模块或符号的可点击源码；
- 可复用点、不要照搬的边界、尚未验证项。

其他参考仓用于形成实现设计和生成正式项目页，不进入第一期自动化回归矩阵。

## 方案比较

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| 纯 Skill | 拒绝作为内核 | 不能稳定承载多语言解析、增量状态、证据发布与跨 Agent 复用；适合二期调用和导出 |
| Python CLI 原型继续扩展 | 拒绝作为最终产品 | 已验证研究方向，但与 Go 单二进制、本地长时索引的目标不一致 |
| Go 库、无 CLI | 拒绝 | 用户、CI、ACP 和桌面端缺少共同操作面 |
| Go CLI + 人类 HTML + 结构化附件 | 采用 | 本地、可重复、可被任何 Agent 调用；HTML 负责叙事，JSON/模块索引负责机器复用 |
| 首期 Web 应用 | 延后 | 增加服务、状态、权限和部署成本，不能先解决“报告看不懂” |
| 自动跨项目选型页 | 不作为主产品 | 用户要先理解每个项目，再亲自选择参考来源 |

## 非功能要求

- **本地优先**：默认不上传源码；
- **可重复**：同一 commit、分析器版本和配置生成同一机器合同；
- **可追溯**：每个实现结论必须落到文件/符号/行范围/测试之一；
- **保守失败**：证据不足显示未知，不补写看似合理的实现；
- **可读性**：390px 与桌面无页面级横向溢出，首屏不出现原始文件清单；
- **性能**：Waku 冷分析可在本地交互时间内完成；未变更暖启动只重建必要派生产物；
- **安全**：不执行目标仓库代码；链接和源码片段严格转义；输出发布不可跨代混合。

## 后果

### 正面

- 人类阅读目标和 Agent 证据消费共用一个稳定内核；
- CLI 能被 Skill、桌面端、CI、ACP 和未来 Web UI 复用；
- 每项目独立 HTML 让用户按自己的顺序研究，不被系统排名绑架；
- Waku 单仓验收让首期反馈保持快速。

### 负面

- 从 Python 原型迁移到 Go 有一次性成本；
- 首期没有跨项目自动比较和在线协作界面；
- 高质量功能语义仍需要确定性证据与可审计的叙事层共同完成；
- 只测 Waku 不能证明多语言泛化，第二测试仓必须在首期闭环后再引入。

## 实现顺序

1. Go CLI、项目身份、文件扫描和安全输出；
2. Waku 的 Python 语法事实与九功能报告；
3. 通用 `Project → Capability → ImplementationSlice → Evidence` 合同；
4. 每项目 HTML 模板与目录页；
5. 暖启动、验证、移动端与链接闭包；
6. 用户选中功能后再实现 Skill 导出；
7. Serena live LSP、第二语言、第二测试仓和 Web UI 均延后。

## 源码参考边界

- SourceBridge 当前源码带 `AGPL-3.0-or-later` SPDX 标记；只参考公开架构与行为，不复制实现；
- Serena、CodeTour 等 MIT 组件可以在许可证和依赖边界核对后复用；
- 未声明许可证的教学 Skill/模板只能借鉴交互思路，不复制资产；
- 所有实际复用都必须在模块索引中记录来源、许可证、改动与验证。
