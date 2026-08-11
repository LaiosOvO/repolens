# Serena 阅读笔记

## 固定版本与许可

- 本地完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/serena`
- `origin`：`https://github.com/oraios/serena.git`
- HEAD：`946ad9817875cbf46b308423296c33eb65e3e728`
- 工作树：clean
- 许可证：MIT（根目录 `LICENSE`）

## 一句话定位

Serena 是给 Agent 使用的语义代码工具箱：用语言服务器查 symbol、reference、declaration、implementation 和 diagnostics，并提供符号级编辑；它不是持久代码图、项目教程生成器或执行沙箱。

## 产品形态

- Python 独立项目；
- `serena` CLI 管理项目、context、mode、tool、memory 与服务；
- FastMCP server 把工具暴露给 Codex、Claude Code 等 MCP client；
- SolidLSP 是多语言语义后端；
- 项目 memory 是 Agent 工作记忆，不是代码 reference 索引。

## 主要功能与实现

### 1. 文件概览与符号定位

- **提供什么**：列出文件符号，按名称路径查 symbol，并限制相对目录、深度和是否包含 body。
- **流程**：Agent 发起 tool call → `GetSymbolsOverviewTool` / `FindSymbolTool` 校验项目与参数 → project language server 查询 document symbols → 返回带文件和范围的符号列表 → Agent 继续定点阅读。
- **技术**：LSP document symbols、统一 symbol model、相对路径约束。
- **源码**：
  - `src/serena/tools/symbol_tools.py:36-132` — `GetSymbolsOverviewTool`
  - `src/serena/tools/symbol_tools.py:134-250` — `FindSymbolTool`
- **测试/证据**：工具会被统一 MCP 包装测试覆盖，见 `test/serena/test_mcp.py:287`。

### 2. 引用、声明与实现查询

- **提供什么**：从一个 symbol 下钻到 references、declaration 和 implementations。
- **流程**：符号定位结果 → 相应 symbolic-read tool → SolidLSP 发送 LSP request → 统一路径/范围 → MCP 返回给 Agent。
- **技术**：LSP references/declaration/implementation、位置归一化。
- **源码**：
  - `src/serena/tools/symbol_tools.py:252-340` — `FindReferencingSymbolsTool`
  - `src/serena/tools/symbol_tools.py:342-397` — `FindImplementationsTool`
  - `src/serena/tools/symbol_tools.py:399-480` — `FindDeclarationTool`
- **边界**：结果由当前语言服务器和当前 worktree 决定；不是跨 commit 的持久知识图。

### 3. Diagnostics 与符号级编辑

- **提供什么**：文件/符号诊断，替换 symbol body，在 symbol 前后插入，rename 和 safe delete。
- **流程**：Agent 选择 symbol → 编辑工具读取精确范围 → 应用文本或 workspace edit → 再读取 diagnostics → 返回修改结果和问题。
- **技术**：LSP diagnostics、rename/workspace edit、基于 symbol range 的文本编辑。
- **源码**：
  - `src/serena/tools/symbol_tools.py:482-583` — diagnostics
  - `src/serena/tools/symbol_tools.py:585-696` — replace/insert/rename
  - `src/serena/tools/symbol_tools.py:698+` — safe delete
- **边界**：trusted project 不等于 sandbox；编辑后仍需 Git diff、测试和用户审批。

### 4. 多语言 SolidLSP 后端

- **提供什么**：把不同语言服务器包装成共同的 symbol、location、diagnostic 与 edit 能力。
- **流程**：项目语言识别 → `LanguageServerConfig` 选择/安装依赖 → 启动 stdio/TCP language server → JSON-RPC 请求 → `SolidLanguageServer` 统一返回。
- **技术**：LSP、JSON-RPC、stdio/TCP process、per-language adapters、dependency provider。
- **源码**：
  - `src/solidlsp/ls.py:344+` — `SolidLanguageServer`
  - `src/solidlsp/ls_process.py:111-768` — 进程与连接
  - `src/solidlsp/ls_config.py:90+` — server id/config
  - `src/solidlsp/language_servers/` — 语言适配器
- **边界**：语言能力和准确率不一致，不能用“支持 LSP”推断所有工具都可用。

### 5. MCP 工具暴露

- **提供什么**：把 Serena tool 转成 FastMCP tool，并兼容不同客户端的 schema 限制。
- **流程**：`SerenaMCPFactory` 收集工具 → `SerenaFastMCPTool` 调整 schema/上下文 → FastMCP server 暴露 → client 调用 `apply`。
- **技术**：MCP、FastMCP、Pydantic/schema 清洗、request context。
- **源码**：
  - `src/serena/mcp.py:48-142` — context 与 tool wrapper
  - `src/serena/mcp.py:144+` — `SerenaMCPFactory`
- **测试**：`test/serena/test_mcp.py:53-286` 覆盖基本包装、执行、无参数、docstring 与工具集合。

### 6. Project Memory 与 CLI 管理

- **提供什么**：保存/列出/读取/编辑项目 memory；CLI 管理项目、模式、context、工具和服务。
- **流程**：CLI/MCP 请求 → `MemoryManager` 限制 memory 路径与格式 → 本地持久化 → 后续 Agent session 读取。
- **技术**：Click command groups、本地 Markdown/memory、项目配置。
- **源码**：
  - `src/serena/cli.py:141-1400` — 自动注册的命令组
  - `src/serena/memories/memory_manager.py:25+` — memory 管理
- **边界**：memory 是人为/Agent 写入的叙述，不是自动重证的源码事实。

## 值得借鉴

- 用户选中一个功能后，用 live LSP 做 symbol/reference/diagnostics/rename 下钻；
- Tool marker 区分 symbolic read/edit 和 optional tool；
- 多语言 server adapter 和 dependency provider；
- 编辑后诊断与 MCP schema 兼容层。

## 不要照搬

- 不把 Serena 当持久仓库索引、功能聚类、教程生成或长任务编排；
- 不把 trusted project 当作安全隔离；
- 不把开源 LSP 能力与付费 JetBrains backend 混为一谈；
- 第一阶段不把语言服务器生命周期放进 Waku HTML 生成关键路径。

## 对 Skill / 项目 / CLI 决策的启示

Serena 本身是独立项目，并同时提供 CLI 与 MCP；这证明复杂的语义分析应由独立运行时持有，MCP/Skill 只是接入面。Repo Teacher 应在用户读完项目报告、选定功能后，才把 Serena 作为可选 live semantics adapter 调用。

## 事实、推断与未验证

- **事实**：上述类、工具、CLI、MCP 与测试在固定 HEAD 存在。
- **推断**：Serena 非常适合“选中模块后的精确下钻”，来自其工具合同与 LSP 数据流。
- **未验证**：本次未对所有语言服务器做准确率与性能矩阵，也未把 JetBrains backend 纳入开源复用评估。
