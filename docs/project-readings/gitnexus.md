# GitNexus profile

## 固定版本身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/gitnexus`
- origin：`https://github.com/abhigyanpatwari/GitNexus.git`
- HEAD：`49c5b7d81fd5173771b31e7a136f33fde281bd70`
- 工作树：clean

## 一句话定位
GitNexus 是一个面向 AI agent 的知识图谱式代码库索引平台：它把仓库分析、MCP 工具、Web UI、编辑器集成和技能/提示文件都围绕同一份索引组织起来。

## 产品形态与许可证
- 形态：CLI + MCP + Web UI + Editor integration + Skills/Prompts + Hosted deploy.
- 版本身份：`1.6.9`。
- 许可证：PolyForm Noncommercial 1.0.0，见 [package.json](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/package.json:2) 与 [LICENSE](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/LICENSE:1)。

## 主要功能
1. 通过 `gitnexus analyze` 建立仓库知识图谱并自动回写 AI 上下文文件：触发→接管→输出→消费：用户在仓库根目录运行 `gitnexus analyze`，CLI 解析一长串开关（embeddings、skills、pdg、branch、self-commit 等），再交给 `runFullAnalysis` 生成 `.gitnexus/` 索引、可选 skills、AGENTS.md/CLAUDE.md 和仓库注册信息，消费端是后续的 MCP/Web/agent 工作流；底层机制/关键技术：按仓库分析、V8 heap 自适应、worker 池、LadybugDB、Tree-sitter、增量分支索引、PDG 可选构建；关键源码：[gitnexus/package.json](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/package.json:41) 的脚本和依赖，[gitnexus/src/cli/index.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/src/cli/index.ts:58) 的 `analyze` 命令，[gitnexus/src/cli/analyze.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/src/cli/analyze.ts:1) 的分析包装逻辑；复用价值：很适合当“重索引、重上下文”的统一入口；局限：安装和分析成本高，且对内存/原生依赖敏感。
2. 用 `setup` / `uninstall` 管理编辑器集成和 hooks：触发→接管→输出→消费：`gitnexus setup` 检测 Cursor、Claude Code、Antigravity、Codex 等宿主，写 MCP 配置、hooks 和 skills；`uninstall` 做反向清理，输出是编辑器侧的接入状态，消费端是 AI 编辑器宿主；底层机制/关键技术：命令行参数收集、hook 模板、技能镜像、自动检测；关键源码：[gitnexus/src/cli/index.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/src/cli/index.ts:28) 的 `setup` / `uninstall`，[gitnexus/package.json](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/package.json:41) 的 `prepare/postinstall/version`，[gitnexus/README.md](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/README.md:206) 的 skills/hook 说明；复用价值：适合作为“让 agent 自动接管本地仓库”的安装模板；局限：依赖宿主的配置写权限，且不同编辑器能力不完全对等。
3. 以 MCP 暴露图谱工具和资源/提示词：触发→接管→输出→消费：客户端通过 stdio 或 HTTP 调起 `gitnexus mcp`，`createMCPServer` 注册 list/query/context/impact/trace/rename/resources/prompts 等工具，输出是带 next-step hint 的结构化结果，消费端是 AI agent；底层机制/关键技术：MCP server、repository policy、read-only mode、max-token budget、资源模板、提示词驱动的工作流；关键源码：[gitnexus/src/mcp/server.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/src/mcp/server.ts:99) 的 `createMCPServer`，[gitnexus/src/mcp/server.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/src/mcp/server.ts:55) 的 `getNextStepHint`，[gitnexus/README.md](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/README.md:158) 的工具与资源列表；复用价值：很适合学它的“工具返回下一步操作”设计；局限：repo-scoped 工具在多仓库场景里需要显式 repo，否则会变得更啰嗦。
4. 提供本地 HTTP API 和 Web UI：触发→接管→输出→消费：`gitnexus serve` 启动 Express API 和静态站点服务，`gitnexus-web` 或 hosted site 通过 `/api/*` 与它交互，输出是图谱浏览、查询和 MCP over StreamableHTTP，消费端是浏览器；底层机制/关键技术：CORS 白名单、Origin 保护、静态资源兜底、SSE、上传/克隆/分析管线；关键源码：[gitnexus/src/server/api.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/src/server/api.ts:104) 的 `isAllowedOrigin`，[gitnexus/src/server/api.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/src/server/api.ts:165) 的 `resolveWebDistDir` / `registerWebUI`，[gitnexus-web/src/main.tsx](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus-web/src/main.tsx:1) 的 React 入口；复用价值：很适合做“本地后端 + 浏览器图谱前端”的参考；局限：公开部署需要 token，浏览器端又受内存上限约束。
5. 让 Web UI 既能上传本地仓库，也能连远端 server：触发→接管→输出→消费：`RepoAnalyzer` 负责 GitHub/GitLab/Azure/local folder 四种输入模式，调用 `startAnalyze`、`uploadFolder` 和 SSE 进度流；`App.tsx` 再把 `connectToServer` 的结果转成图和 UI 状态，输出是可浏览的知识图谱和进度/错误态，消费端是前端用户；底层机制/关键技术：SSE、AbortController、repo identity 归一化、chat-only fallback、url query state；关键源码：[gitnexus-web/src/components/RepoAnalyzer.tsx](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus-web/src/components/RepoAnalyzer.tsx:196) 的分析器状态机，[gitnexus-web/src/services/backend-client.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus-web/src/services/backend-client.ts:175) 的 `streamSSE`，[gitnexus-web/src/App.tsx](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus-web/src/App.tsx:69) 的 `handleServerConnect` / auto-connect；复用价值：这是一个很完整的“可取消、可恢复、可书签化”的 web 连接流；局限：大图谱会退化成 chat-only 或受浏览器内存限制。
6. 在图上做探索、重点高亮和视图切换：触发→接管→输出→消费：用户在 `GraphCanvas` 点节点、切换 force/tree/circles 视图、开关 AI 高亮，输出是图的重布局、节点 focus 和 code panel 打开，消费端是探索/分析用户；底层机制/关键技术：Graphology + Sigma、knowledgeGraph 转换、社区成员关系、AI citation/tool/blast-radius 高亮；关键源码：[gitnexus-web/src/components/GraphCanvas.tsx](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus-web/src/components/GraphCanvas.tsx:37) 的 `GraphCanvas`，[gitnexus-web/src/lib/graph-adapter.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus-web/src/lib/graph-adapter.ts:1)，[gitnexus-web/src/App.tsx](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus-web/src/App.tsx:237) 的心跳与视图管理；复用价值：适合借鉴“图可视化 + 高亮 + 面板”的三栏式分析 UI；局限：大图下性能会受限，且交互复杂度高。

## 事实
- README 把它直接定义成“the nervous system for agent context”，并明确强调 CLI + MCP + Web UI 两条主路径；见 [README.md](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/README.md:29) 与 [README.md](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/README.md:105)。
- `package.json` 声明了 `gitnexus` CLI bin、`serve` / `mcp` / `analyze` 等脚本，以及 `gitnexus-web`、`gitnexus-shared` 等工作区依赖；见 [package.json](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/package.json:30)。
- MCP server、HTTP API 和 Web UI 都是围绕同一份图谱索引和 registry 工作，而不是三套独立数据源；见 [mcp/server.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/src/mcp/server.ts:8) 与 [server/api.ts](/Volumes/T7/workspace/ontology/graph/repo/gitnexus/gitnexus/src/server/api.ts:4)。

## 推断
- 这是一个“先离线分析、再多宿主消费”的平台，而不是单纯的库；CLI 产出的 `.gitnexus/` 索引是所有上层功能的基础。
- `setup`/skills/hooks 这套机制显示它把“让 AI 自动使用图谱”当作第一等产品目标，而不只是提供查询接口。

## 未知
- 部分具体实现依赖 `src/core/*`、`src/storage/*` 的深层模块，当前 profile 只抓了用户能直接感知的入口层，没有展开到全部内部算法细节。

## 对 Skill / 项目 / CLI 决策的启示
GitNexus 先由 CLI 预计算图，再同时供 MCP、Web 和 Wiki 消费，说明共享内核应属于独立项目；Agent 接口不应各自重新分析仓库。
