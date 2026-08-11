# CodeGraph AI profile

## 固定版本身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai`
- origin：`https://github.com/codegraph-ai/CodeGraph.git`
- HEAD：`489ccf1612555510f8367e3e673181f6a1275fe4`
- 工作树：clean

## 一句话定位
CodeGraph AI 是一个围绕代码图谱展开的多产品工作区：同一套图谱引擎同时服务 MCP、VS Code、JetBrains、GitHub Action 和面向 agent 的规则/技能。

## 产品形态与许可证
- 形态：MCP Server + VS Code 扩展 + JetBrains 插件 + CLI 工具包 + GitHub Action/规则包。
- 版本身份：`0.20.1`。
- 许可证：Apache-2.0，见 [README.md](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/README.md:1)、[mcp-package/package.json](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/mcp-package/package.json:7) 和 [vscode/package.json](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/package.json:8)。

## 主要功能
1. 以 MCP 暴露跨语言代码智能：用户在 MCP 客户端里配置 `codegraph-mcp`，然后直接调用图谱工具；触发→接管→输出→消费：`mcp-package` 的 `postinstall` 会拉取平台引擎，`codegraph-mcp` 再把本地二进制转成 MCP 进程，输出是 42 个工具的结构化结果，消费端是 Claude Code、Cursor、Codex 等 MCP 客户端；底层机制/关键技术：本地引擎二进制、按平台下载、`--graph-only`、`--run-tool`、混合 BM25+semantic 检索、`codegraph_*` 工具命名；关键源码：[codegraph-ai/README.md](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/README.md:7) 的产品总述，[codegraph-ai/mcp-package/package.json](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/mcp-package/package.json:22) 的 bin 和 `postinstall`，[codegraph-ai/mcp-package/bin/codegraph-mcp.js](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/mcp-package/bin/codegraph-mcp.js:19) 的引擎发现/拉取/启动；复用价值：这是标准“重引擎、轻客户端”的 MCP 分发模式；局限：引擎不是随包内置，首次安装和平台兼容是主要变量。
2. 让 VS Code 在激活时自动接入图谱引擎：用户安装扩展后，激活时如果没有引擎会提示下载，存在旧版本时会提示更新；触发→接管→输出→消费：`activate()` 里先定版本、找 `~/.codegraph/bin`，再启动语言客户端与 LSP 服务，输出是 CodeLens、命令、状态栏、AI 工具注册和图谱/LSP 能力，消费端是 VS Code 用户；底层机制/关键技术：同一引擎目录与 MCP/JetBrains 共享、进程 spawn、版本 staleness 检查、engine lifecycle 管理、Telemetry；关键源码：[codegraph-ai/vscode/package.json](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/package.json:32) 的 activation/commands，[codegraph-ai/vscode/src/extension.ts](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/src/extension.ts:179) 的 `activate` / `serverOptions` / `client.start`, [codegraph-ai/vscode/src/engineDownload.ts](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/src/engineDownload.ts:43) 的 `engineVersion` / `offerEngineDownload` / `offerEngineUpdateIfStale`；复用价值：适合借鉴“共享引擎目录 + 多客户端复用”的桌面集成方式；局限：首次激活会遇到下载/版本一致性提示，且本地二进制问题会直接影响体验。
3. 让 JetBrains 系列 IDE 共用同一图谱引擎：README 明确说明 IntelliJ/PyCharm/GoLand/Android Studio 等通过同一引擎、同一 `~/.codegraph/bin` 工作；触发→接管→输出→消费：插件在 IDE 里下载/复用引擎，输出 Code Vision、Symbols、Memories、graph panel 和 MCP 注册，消费端是 JetBrains 用户；底层机制/关键技术：LSP 驱动、共享引擎路径、单次下载跨 IDE 复用；关键源码：[codegraph-ai/README.md](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/README.md:43) 的 JetBrains 段落，[codegraph-ai/vscode/src/server.ts](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/src/server.ts:16) 的引擎路径规则，[codegraph-ai/vscode/src/engineDownload.ts](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/src/engineDownload.ts:28) 的 `managedInstallDir`; 复用价值：同一下载为多 IDE 省带宽和维护成本；局限：JetBrains 端行为主要在 README 里描述，仓库内可见代码偏少。
4. 给 agent 提供先读图再 grep 的规则/技能/CI 面：README 里有 rules for agents，GitHub Action 里有 PR review 流程；触发→接管→输出→消费：规则文件让 Claude/Cursor/Codex 先用 `codegraph_*` 工具，GitHub Action 用 `codegraph-server --graph-only --run-tool codegraph_pr_context` 输出评论，消费端是代码审查者和 CI；底层机制/关键技术：规则文件分发、graph-only 模式、无 API key 的结构化 PR 上下文；关键源码：[codegraph-ai/README.md](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/README.md:54) 的 agent rules 和 PR review，[codegraph-ai/mcp-package/bin/postinstall.js](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/mcp-package/bin/postinstall.js:99) 的静态模型拉取提示，[codegraph-ai/vscode/package.json](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/package.json:47) 的命令贡献；复用价值：适合做“工具优先”的 agent 工作流规范；局限：对 agent 生态依赖重，规则文件需要手动分发到不同宿主。
5. 通过静态 embedding 模型和 graph-only 模式换取速度/内存：用户可选 `--embedding-model static`，也可在内存不足时只跑 graph-only；触发→接管→输出→消费：`postinstall` 可拉取 `jina-code-static-256`，扩展/CLI 都可使用同一模型目录，输出是更快的索引和更轻的运行时，消费端是所有客户端；底层机制/关键技术：model2vec/静态向量、可选 ONNX、内存门控、共享模型目录；关键源码：[codegraph-ai/README.md](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/README.md:103) 的静态模型说明，[codegraph-ai/mcp-package/bin/postinstall.js](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/mcp-package/bin/postinstall.js:99) 的模型下载，[codegraph-ai/vscode/src/engineDownload.ts](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/src/engineDownload.ts:125) 的 stale/update 流程；复用价值：适合在资源受限环境里保留“足够好”的语义搜索；局限：需要本地模型目录，且静态模型是可选项，不是默认强约束。
6. 提供持久 memory 与文档型工具：README 把 memory、docs、design verification 都列进工具面；触发→接管→输出→消费：MCP 工具返回 memory 搜索、文档索引、设计验证、架构生成结果，消费端是 agent 和开发者；底层机制/关键技术：persistent memory layer、index markdown、search docs、verify design；关键源码：[codegraph-ai/README.md](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/README.md:220) 的 memory/doc tools 列表，[codegraph-ai/mcp-package/package.json](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/mcp-package/package.json:49) 的安装脚本，[codegraph-ai/vscode/src/extension.ts](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/src/extension.ts:399) 的初始化参数；复用价值：对“代码知识库 + 代理记忆”类产品很有参考价值；局限：这套能力对索引质量和本地存储依赖较高。

## 事实
- README 把它描述为“cross-language code intelligence for AI agents and developers”，并明确列出 42 个 MCP 工具、38 种语言、VS Code 扩展、JetBrains 插件和 persistent memory layer；见 [README.md](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/README.md:1)。
- `mcp-package/package.json`、`vscode/package.json` 都声明许可证为 Apache-2.0，版本为 `0.20.1`；见 [mcp-package/package.json](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/mcp-package/package.json:2) 与 [vscode/package.json](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/vscode/package.json:2)。
- `postinstall.js` 明确说明引擎是按平台拉取而不是打包进 npm 包；见 [mcp-package/bin/postinstall.js](/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai/mcp-package/bin/postinstall.js:35)。

## 推断
- 这是一个“同一引擎，多宿主”的产品，核心资产不是单个 UI，而是图谱引擎和工具协议。
- VS Code / JetBrains / MCP / GitHub Action 这几条线共享同一引擎目录，说明项目把一致性放在优先级很高的位置。

## 未知
- JetBrains 插件的详细代码不在当前读到的主执行入口里，更多实现细节需要进入 `jetbrains/README.md` 或相关源码继续核实。

## 对 Skill / 项目 / CLI 决策的启示
CodeGraph 的图内核和 MCP/IDE 表面分离，证明核心事实层应独立分发；但它不提供人类教程，因此 Repo Teacher 仍需自己的逐项目 HTML 层。
