# Repo Teacher 生产版设计

## 产品目标

Repo Teacher 是第一个优先产品：输入任意本地代码仓库，输出一个既能帮助人做技术取舍、又能直接交给 Agent 继续实现的代码知识包。用户先看到“仓库做什么、有哪些可观察功能、最值得复用什么”，再选择一个功能沿真实源码、调用关系和测试证据逐步下钻；最后可把所选功能或模块导出为可安装 Skill。

生产版是 local-first 单用户工具，不把源码上传到 Repo Teacher 服务。默认不需要 LLM；配置本地 OpenAI-compatible 模型后，可以改善命名、摘要和教程叙事，但任何模型结论都必须引用确定性 EvidenceRef，验证失败时回退到确定性结果。

## 三种方案与决定

### A. 直接组合六个参考项目

能力表面最全，但会引入 Go、Node、Python、SurrealDB、LSP 和多个 Agent runtime；SourceBridge 的 AGPL 还会污染分发边界。不采用。

### B. 统一内核＋可插拔分析器（采用）

保留现有 Python 本地 CLI，将参考项目验证过的数据合同、增量机制、教程流水线和证据门干净实现为一套内核。Python AST 是第一精确分析器，JS/TS 内建分析器明确标记 heuristic；Tree-sitter/SCIP/LSP 通过后续适配器接入而不改变 schema。该方案最适合本地产品、可测试、可渐进增强。

### C. Fork DeepWiki-Open 或 CodeBoarding

能较快获得大型 Web UI 或 LSP 图，但会继承云仓库假设、部署重量和已有信息架构，难以实现用户要求的“先决策、再教学、最后导出 Skill”。仅作为专项实现参考。

## 核心用户流程

1. `repo-teacher index <repo>` 捕获 commit、扫描边界和旧 baseline。
2. Analyzer Registry 生成文件、符号、关系与结构诊断；未解析语言仍保留文件事实。
3. Graph Builder 解析唯一目标、组件边和有限执行路径。
4. Feature Discovery 从 CLI 命令、HTTP route、入口、公开 API 和测试发现功能候选。
5. Evidence Store 为每个结论生成路径、行范围、snippet、hash、analyzer 与 confidence。
6. Coverage Critic 检查入口、异常、配置、持久化、安全边界和测试是否有教学归属。
7. Tutorial/Codemap Builder 按“用途→入口→执行路径→状态/依赖→测试→复用边界”生成章节。
8. Report Renderer 生成离线 HTML；用户按功能而非文件树浏览。
9. `repo-teacher export` 将选中功能/模块导出为 Skill 目录。
10. 下次运行比较指纹，只重分析变化文件，并明确 stale/changed/deleted 影响。

## 数据合同 2.0

顶层对象：

- `project`：Git 与扫描身份；
- `files/symbols/relationships`：确定性代码事实；
- `components`：面向架构的模块集合；
- `features`：用户可观察功能与入口；
- `evidence`：文件/行/snippet/hash 证据；
- `tutorials`：功能教程与验证路径；
- `codemaps`：节点、边、步骤与 citations；
- `coverage`：完整性得分和未覆盖风险；
- `changes`：相对 baseline 的增量结果；
- `diagnostics`：解析、证据、LLM 和导出错误。

每个派生对象都携带 `source`、`confidence` 和 evidence IDs。文件行号只用于当前快照展示；稳定身份由 commit、相对路径、qualified symbol 和结构签名共同生成。

## 可靠性与安全

- 输出使用临时文件＋原子替换，并用进程锁阻止并发覆盖。
- 跳过 symlink、二进制、超大文件、密钥目录和输出目录；所有相对路径必须约束在 repo root。
- HTML 转义仓库文本并设置严格 CSP；本地服务默认只绑定 `127.0.0.1`、禁止目录列表、提供 `/healthz`。
- 代码、README 和 issue 文本仅是数据，不能覆盖系统提示或证据规则。
- LLM 响应必须通过 schema、citation、文件范围和 snippet hash 校验；失败时保留诊断并回退。
- 不执行目标仓库代码；验证命令只作为建议写入，不自动运行。

## 性能与增量

- 扫描顺序确定、分析可并行、默认总字节和单文件大小有预算。
- 旧 `index.json` schema 兼容且文件 hash 未变时，复用符号和关系；变化文件重新分析。
- 所有派生层每次从当前事实图重建，避免复用已失效语义。
- 记录 `reused_files/reanalyzed_files/duration_ms`，真实仓库基准必须输出数据而非主观判断。

## 生产验收

1. 六个参考仓库均能索引，单仓失败不产生半写文件。
2. 第二次运行能复用未变化分析；修改一个 fixture 只报告一个 changed file。
3. 每个 feature tutorial 至少有一个有效 EvidenceRef；无证据功能不得进入“已验证”。
4. HTML 首屏给出功能、复用价值和风险，不再只显示文件数量。
5. 用户能选择功能或模块，通过 CLI 导出通过 Skill validator 的目录。
6. 自动化测试覆盖 schema、增量、路径安全、citation grounding、LLM fallback、Skill export、CLI、HTTP 和 HTML escaping。

