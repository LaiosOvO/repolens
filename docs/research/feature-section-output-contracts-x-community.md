# Feature-Section Output Contracts: GitHub/X 社区反馈汇总（代码仓库讲解 / DeepWiki / walkthrough / architecture report）

## 研究目标
面向“阅读完一个功能后，用户要知道：为什么存在、用户场景、运行链、状态、模块职责、复用路径、失败模式、可修改点”这类输出契约，基于 GitHub 与 X 一手反馈形成可落地建议。

## 一、事实（可验证）

### 1) DeepWiki/OpenDeepWiki 的用户真实需求
- DeepWiki 核心主张是“解析仓库并自动生成可浏览的 wiki / codemap / architecture 视图”，即将“功能结果”落成可阅读形态而非只给一次性文本。
  - 链接：<https://github.com/AsyncFuncAI/deepwiki-open#readme>

- `#123` 讨论聚焦 **MCP + streaming**：
  - 议题讨论 `ask_question` 式交互、`repo_url + messages` 结构、流式响应和身份 token 约束。
  - 链接：<https://github.com/AsyncFuncAI/deepwiki-open/issues/123>

- `#497` 进一步要求从 deepwiki 层到 MCP 的工具化：`list_projects/get_wiki_structure/get_wiki_page/search_repo` 等工具被提及，体现“功能章节”可直接复用为外部调用边界。
  - 链接：<https://github.com/AsyncFuncAI/deepwiki-open/issues/497>

### 2) 配置与基础设施瓶颈（反向约束）
- `#156`/`#334` 体现“embedding 与 LLM 可拆分配置”诉求，说明真实部署会把模型链路拆开。
  - 链接：<https://github.com/AsyncFuncAI/deepwiki-open/issues/156>
  - 链接：<https://github.com/AsyncFuncAI/deepwiki-open/issues/334>

- `#252` 报告“embedding/向量阶段未正常工作”会导致后续文档链路失效，给出失败链明确边界。
  - 链接：<https://github.com/AsyncFuncAI/deepwiki-open/issues/252>

### 3) CodeTour/Walkthrough 类工具的可复用机制
- Microsoft CodeTour 的设计强调导览步骤、文件位置锚定、可复用 tour 文件和 drift 检测，支持“代码讲解功能必须可重放、可回归、可回滚”。
  - 链接：<https://github.com/microsoft/codetour>

- walkthrough 项目强调结果验证机制（grade/negative case）并输出可视化图说明，说明架构报告在功能说明后要有“成功与失败场景证据”。
  - 链接：<https://github.com/alexanderop/walkthrough>

### 4) 代码审查/输出可靠性的现实反馈
- Codex issue 记录中出现“审查链路误报/反馈不一致/面板异常”等问题，说明“展示层稳定性”会直接损害仓库讲解类项目的可信度。
  - 链接：<https://github.com/openai/codex/issues/35043>
  - 链接：<https://github.com/openai/codex/issues/35980>
  - 链接：<https://github.com/openai/codex/issues/35741>
  - 链接：<https://github.com/openai/codex/issues/32224>

## 二、观点（社区叙事与方向偏好）

### 支持观点
1. **功能应以“运行链和可回溯输入”作为主线输出，而非单页叙事。**
   - DeepWiki 的 MCP 化与 CodeTour 的步骤化都把“可回放”放在核心。

2. **embedding/LLM 解耦是高频真实诉求。**
   - 多条 issue 反复指向 provider 与部署配置问题，说明模型迁移性优先级高。

3. **可执行失败路径比纯可读性更影响可维护。**
   - walkthrough 与 Codex 反馈都在强调“边界、负案例、验证器”比“花哨文档”更能抗迭代。

### 反对/谨慎观点
1. **“自动生成 = 可用于起步，不等于可用于生产决策”。**
   - 多条反馈指出自动化链路中断时先天不透明，说明主文档不能替代运行状态可观测。

2. **“UI 再漂亮也不能掩盖 pipeline 失败”。**
   - 复现类 issue 说明输出界面问题会让功能被误判为“没执行/没生效”。

## 三、X（推特）一手动态

### 支持与关注信号
- Silas Alberti 对 DeepWiki 开发者的支持帖，反映社区对该类代码仓库讲解方向的认同。
  - 链接：<https://x.com/silasalberti/status/1920373843363049807>

- CodeRabbit 在 X 上持续强调 IDE 场景内的反馈，说明结构化建议要尽可能贴近开发者操作上下文。
  - 链接：<https://x.com/coderabbitai/status/1922642534750163184>

### 注意
- 当前 X 语料中，对 DeepWiki/architecture report 的长链技术细节较少，适合作为“关注度/传播意愿”证据，不宜直接作为实现正确性证据。

## 四、对“功能章节输出契约”的可复用模板（每功能都应固定输出）

1. **为什么存在（Problem）**：该功能解决哪个真实接管场景。
2. **触发/路径（Runtime path）**：命令/按钮/API -> service -> writer.
3. **数据状态（State）**：输入、缓存、增量/全量、过期/脏（dirty/stale）语义。
4. **边界职责（Ownership）**：该功能的模块边界、外部依赖、复用点。
5. **失败路径（Failure）**：错误码、超时、provider 失败、空数据、漂移。
6. **如何修改（How-to）**：可替换部件（provider/model/provider config/参数）与回归点。
7. **如何复用（Reuse）**：可导出的证据包（command map/evidence json/示例响应）。

## 事实 / 观点 / 推断

- 事实：DeepWiki 的多条 issue/讨论、CodeTour 的教程模型、walkthrough 的评估约束、Codex 的展示链 bug，均指向“功能输出的运行链与验证性是关键。
- 观点：从社区语境看，开发者更看重可回放与可验证性。
- 推断：主 HTML 输出应将每个功能“先声明输入输出契约，再接一组失败重试与状态迁移”，而不是先写主观体验结论。
