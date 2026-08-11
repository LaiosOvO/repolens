# CodeBoarding 阅读笔记

## 固定身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/codeboarding`
- origin：`https://github.com/CodeBoarding/CodeBoarding.git`
- HEAD：`8c3f2218c3ecab1294902db5914f5e526f78524d`
- 工作树：clean
- 许可证：MIT

## 一句话定位
CodeBoarding 的核心不是“生成一篇教程”，而是“先用静态分析和 LLM 把项目压缩成 `analysis.json`，再用 Markdown / Mermaid / HTML / Web 平台去消费这份中间产物”。

## 产品形态判断
- 形态：独立项目，CLI 是主入口，Web/IDE/CI 是消费面。
- 它不是单一 skill。
- 对我们的价值：它很像你要做的一期 `repo-teacher` 的“骨架参考”，尤其是“先产结构化中间件，再做人类页面”的路线。

## 先看什么
如果你的目标是“快速看懂一个仓库有哪些功能、哪些模块实现这些功能”，CodeBoarding 最值得看的不是首页，而是下面 5 层：

1. 静态解析与组件/关系抽取
2. full / incremental / partial 三种执行模式
3. `analysis.json` 作为统一中间产物
4. Markdown / Mermaid / HTML 等输出层
5. Web 平台如何直接消费分析文件

## 人类可感知功能

### 1. 静态解析与组件/调用关系图
- 提供什么：把仓库变成组件树、关系边、层级结构，供后续文档和图消费。
- 触发 -> 接管 -> 输出 -> 消费：
  full 或 incremental 运行 -> `DiagramGenerator` 和 static analyzer 接管 -> 产出组件、关系、call graph、metadata -> `analysis.json` 与输出生成器消费。
- 底层机制/技术：
  README 明确写了 static analysis + LLM reasoning；增量 orchestrator 会基于 LSP 结果和 `CallGraphBuilder` 重建调用边。
- 关键证据：
  - 产品定位：[README.md](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md:5)
  - “How it works” 图里的 Static Code Analyzer / Incremental Analysis Engine：[README.md](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md:37)
  - 语言服务器准备与本地 binaries：[README.md](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md:98)
  - 关系/静态证据如何进入 JSON：[diagram_analysis/analysis_json.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/diagram_analysis/analysis_json.py:31)
  - 增量路径中的 `CallGraphBuilder`：[static_analyzer/incremental_orchestrator.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/static_analyzer/incremental_orchestrator.py:22)
- 真实相关测试：
  - 渲染/关系投影端到端验证：[tests/codeboarding_workflows/test_rendering.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/tests/codeboarding_workflows/test_rendering.py:124)
- 可复用：很适合拿来做“代码仓库结构索引”底座。
- 改造使用：我们可以借“统一分析对象”思路，但把输出语义换成“功能 -> 模块 -> 证据 -> 阅读顺序”。
- 不照搬：不要一期就复制它完整的 LSP/静态分析引擎。
- 未知：多语言大仓库下的分析时延与成本。

### 2. Full Analysis
- 提供什么：第一次把整个仓库分析完整，生成完整基线。
- 触发 -> 接管 -> 输出 -> 消费：
  `codeboarding full --local /repo` -> `full_analysis.run_from_args` 接管 -> 调 `run_full` + `run_analysis_pipeline` -> 生成 `.codeboarding/analysis.json` 等产物 -> 本地文件、Web 平台、文档系统消费。
- 底层机制/技术：
  full 路径负责 bootstrap 环境、初始化 `.codeboarding/`、构造 `RunPaths`、调用统一 workflow。
- 关键证据：
  - Quick start 和 full 命令：[README.md](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md:65)
  - full 命令入口：[main.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/main.py:26)
  - full 本地执行：[codeboarding_cli/commands/full_analysis.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_cli/commands/full_analysis.py:25)
  - workflow 的 `run_full`：[codeboarding_workflows/analysis.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_workflows/analysis.py:49)
- 真实相关测试：
  - 渲染结果与结构投影测试：[tests/codeboarding_workflows/test_rendering.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/tests/codeboarding_workflows/test_rendering.py:129)
- 可复用：这条链很适合做我们的一期主命令。
- 改造使用：把 full 的输出目标从 `.codeboarding/` 文档改成 `repo-teacher` 的主叙述页 + evidence 附件。
- 不照搬：它面向“文档/图/平台”多端产出；我们一期先把重点收敛到“给人快速看懂”。
- 未知：full 模式的 token 花销上限。

### 3. Incremental Analysis
- 提供什么：只更新变化部分，而不是每次全量重跑。
- 触发 -> 接管 -> 输出 -> 消费：
  `codeboarding incremental --local /repo` -> incremental 命令接管 -> 读取旧 `analysis.json` + `fingerprint.json` -> 差异检测 -> 重跑变更范围 -> 更新新的 `analysis.json`。
- 底层机制/技术：
  不依赖 git diff 才能工作；核心是 baseline + fingerprint；没有 baseline 会 fail fast。
- 关键证据：
  - README 对 incremental baseline 的说明：[README.md](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md:147)
  - incremental 命令入口：[codeboarding_cli/commands/incremental_analysis.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_cli/commands/incremental_analysis.py:18)
  - workflow 的 `run_incremental` 契约：[codeboarding_workflows/analysis.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_workflows/analysis.py:7)
  - 增量 orchestrator 说明与 changed files 合并：[static_analyzer/incremental_orchestrator.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/static_analyzer/incremental_orchestrator.py:44)
- 真实相关测试：
  - git-free 增量工作流测试：[tests/codeboarding_workflows/test_analysis.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/tests/codeboarding_workflows/test_analysis.py:12)
  - CLI incremental 调用契约：[tests/codeboarding_cli/test_incremental_analysis.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/tests/codeboarding_cli/test_incremental_analysis.py:10)
- 可复用：这和你后面要做的“持续研究 + 持续补充项目笔记”非常契合。
- 改造使用：一期就应该给 report/evidence 建 baseline，为后续增量更新做准备。
- 不照搬：不要先做复杂的 warm-LSP；先做“变更后只重算受影响模块/页面”即可。
- 未知：大规模仓库上的 fingerprint 失效策略。

### 4. Partial Analysis
- 提供什么：只更新一个组件，而不是整个项目。
- 触发 -> 接管 -> 输出 -> 消费：
  `codeboarding partial --component-id 1.2` -> partial 命令接管 -> `run_partial` 更新局部组件 -> 重新写回分析产物 -> 输出层刷新局部页面。
- 底层机制/技术：
  partial 明确依赖已有 baseline，不是无中生有。
- 关键证据：
  - partial 命令用法：[README.md](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md:140)
  - partial CLI 实现：[codeboarding_cli/commands/partial_analysis.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_cli/commands/partial_analysis.py:17)
  - workflow `run_partial`：[codeboarding_workflows/analysis.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_workflows/analysis.py:77)
- 真实相关测试：
  - 我本轮阅读中没有单独展开 partial 的专门测试文件；当前最直接证据是 CLI 和 workflow 代码。
- 可复用：对我们很有价值，因为你明确要求“选了哪些模块后，要能导出功能和代码模块索引”。
- 改造使用：我们后面可以把 partial 变成“只重生一个功能卡片/一个项目附件页”。
- 不照搬：不必沿用它的 component id 命名法。
- 未知：组件边界稳定性是否足够强。

### 5. `analysis.json` 作为统一中间产物
- 提供什么：把一次分析结果压缩成一个统一 JSON，成为 Markdown / Mermaid / HTML / Web 平台的共同输入。
- 触发 -> 接管 -> 输出 -> 消费：
  分析完成 -> `analysis.json` 落盘 -> render_docs / output_generators / Web 平台加载 -> 生成不同人类界面。
- 底层机制/技术：
  README 明确写 Web 平台支持直接拖入 `analysis.json`；workflow 渲染阶段会解析 unified analysis 并按层级投影。
- 关键证据：
  - `analysis.json` 输出和 Web 拖拽消费：[README.md](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md:94)
  - unified analysis 解析与关系投影：[codeboarding_workflows/rendering.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_workflows/rendering.py:78)
  - JSON 模型：[diagram_analysis/analysis_json.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/diagram_analysis/analysis_json.py:67)
- 真实相关测试：
  - 渲染管线 end-to-end 测试：[tests/codeboarding_workflows/test_rendering.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/tests/codeboarding_workflows/test_rendering.py:124)
- 可复用：这是它最值得借的地方。
- 改造使用：我们的核心中间件也应有 `report.json` / `module-index.json` / `evidence.json`，而不是只吐 HTML。
- 不照搬：不必强行兼容它的完整 schema。
- 未知：它的 schema 演进成本。

### 6. Markdown / Mermaid / HTML / Web 消费
- 提供什么：同一份分析结果可以转成 Markdown 文档、Mermaid 图、HTML 页面，并被 Web 平台浏览。
- 触发 -> 接管 -> 输出 -> 消费：
  render_docs / output_generators 接管 -> `.md`、Mermaid、HTML、Web 可加载视图 -> 人类在 docs、PR、浏览器里消费。
- 底层机制/技术：
  输出生成器把组件关系转换为 Mermaid/Cytoscape/HTML；测试覆盖了 markdown/html/cytoscape 生成。
- 关键证据：
  - README 对 Markdown / Mermaid / Web 消费的描述：[README.md](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md:29)
  - 远程处理完成后渲染 markdown：[codeboarding_cli/commands/full_analysis.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_cli/commands/full_analysis.py:187)
  - Markdown 生成测试：[tests/output_generators/test_output_generators.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/tests/output_generators/test_output_generators.py:50)
  - HTML/Cytoscape 生成测试：[tests/output_generators/test_output_generators.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/tests/output_generators/test_output_generators.py:168)
- 真实相关测试：
  - Mermaid/Markdown 链接与源码引用：[tests/output_generators/test_output_generators.py](/Volumes/T7/workspace/ontology/graph/repo/codeboarding/tests/output_generators/test_output_generators.py:71)
- 可复用：非常贴近你“最终先看人类页面，但也要保留结构化附件”的需求。
- 改造使用：我们不必只输出一个 HTML，应该同时输出主页、项目页、模块页和 JSON 附件。
- 不照搬：不要继续使用它那种偏“文档站”式讲法；我们要更像“先结论，再证据，再代码入口”。
- 未知：现有 HTML 模板的人类可读性上限。

## 对我们产品形态的直接启示

### 该借什么
- 借“CLI 先跑分析，生成中间产物，再给多个渲染层消费”的主线。
- 借 full / incremental / partial 三个执行模式。
- 借统一 `analysis.json` 思想，但替换成更贴近技术选型的 schema。

### 该改成什么
- 我们的主页面要先回答：
  - 这个项目是什么
  - 先看哪 3-6 个功能
  - 每个功能由哪些模块负责
  - 我为什么该参考它
- 附件页再展开：
  - 功能卡片页
  - 模块索引页
  - evidence 页
  - 原始 JSON

### 明确不照搬
- 不抄它现成的输出模板和文案组织。
- 不把“架构图为中心”误当成“人类快速理解为中心”。
- 不在一期复制整套静态分析/LSP 资产下载体系。

## 事实 / 推断 / 未知

### 事实
- CodeBoarding 明确是 CLI 主导、Web/IDE/CI 复用的独立项目。
- full / incremental / partial 都有真实命令实现。
- `analysis.json` 是真实中间产物，Markdown/Mermaid/HTML/Web 都围绕它消费。

### 推断
- 这套形态最接近你当前要做的一期 repo teaching 产品。
- 它比 SourceBridge 更适合作为一期实现骨架参考。

### 未知
- 静态分析质量在复杂多语言仓库上的稳定性。
- 现有组件切分是否足够适合“功能导向”的教学页。

## 对“独立项目 + CLI + 主叙述页 + 附件页 + 二期薄 Skill”的结论
- CodeBoarding 强烈支持我们把一期做成独立项目，CLI 只是执行入口。
- 真正有价值的产物不是命令本身，而是统一中间产物和多层消费面。
- 你的“主叙述页 + 附件页 + JSON 附件”路线，比“只出一个长 HTML”更贴近这个项目给出的最佳参考。
