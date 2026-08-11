# CodeWiki profile

## 固定版本身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/codewiki`
- origin：`https://github.com/FSoft-AI4Code/CodeWiki.git`
- HEAD：`a61f0f2b608d6972ca967fd60447280ad6100fd3`
- 工作树：clean

## 一句话定位
CodeWiki 是一个面向大中型代码库的 Python 文档生成器，核心目标不是“列目录”，而是把仓库级结构、跨模块关系和 Mermaid 图一起整理成可读文档。

## 产品形态与许可证
- 形态：Python CLI + MCP Server + 静态 HTML 查看器/网页输出。
- 版本身份：`1.0.1`。
- 许可证：MIT，见 [pyproject.toml](/Volumes/T7/workspace/ontology/graph/repo/codewiki/pyproject.toml:5)；仓库根目录未见独立 `LICENSE` 文件。

## 主要功能
1. 配置多供应商 LLM 和文档生成参数：用户通过 `codewiki config set/show/validate` 配置 API key、base URL、主模型、聚类模型、回退模型、token 上限和 Git ignore 行为；触发→接管→输出→消费：CLI 命令进入 `config_group`，再写入 `ConfigManager` 和 `codewiki/src/config.py` 里的配置结构，输出是持久化的本地配置，后续 `generate` 和 `mcp` 都消费它；底层机制/关键技术：Click 命令组、系统 keychain、`AgentInstructions`、provider 分支（openai-compatible/atlas-cloud/anthropic/bedrock/azure-openai/claude-code/codex）；关键源码：[codewiki/codewiki/cli/main.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/main.py:12) 的 `cli`/`mcp_command`，[codewiki/codewiki/cli/commands/config.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/commands/config.py:35) 的 `config_group`/`config_set`, [codewiki/codewiki/src/config.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/src/config.py:58) 的 `Config`；复用价值：把不同模型供应商的复杂参数收口到统一入口，适合作为其他“多 LLM 文档工具”的配置层；局限：强依赖外部模型服务，且不同 provider 的参数语义不完全一致。
2. 生成仓库级文档并支持增量更新：用户运行 `codewiki generate`，可选 `--github-pages`、`--create-branch`、`--update`、`--compare-to`；触发→接管→输出→消费：命令入口校验仓库、比较 `metadata.json` 里的 commit、找出 changed files、失效受影响模块，再交给 `CLIDocumentationGenerator` 生成文档，输出到 `docs/` 或自定义目录，消费端是浏览器、GitHub Pages 或仓库内文档；底层机制/关键技术：Git diff 基线、模块树失效、模板化文档生成、Mermaid 校验、仓库子目录感知；关键源码：[codewiki/codewiki/cli/commands/generate.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/commands/generate.py:43) 的 `_detect_changed_files` / `_invalidate_affected_modules` / `generate_command`，[codewiki/codewiki/cli/html_generator.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/html_generator.py:13) 的 `HTMLGenerator.generate`，[codewiki/codewiki/cli/main.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/main.py:33) 的 `generate_command` 注册；复用价值：适合把“代码 -> 文档 -> 站点”做成一条可增量的流水线；局限：生成质量依赖外部 LLM，Git 历史缺失或非 Git 场景会退化到全量生成。
3. 提供会话式 MCP 工作流给 IDE/Agent：用户通过 `codewiki mcp` 启动 MCP Server；触发→接管→输出→消费：`analyze_repo` 创建 session，把组件索引、leaf 节点和工作区文件写到磁盘，后续 `read_code_components`、`write_doc_file`、`save_module_tree`、`get_processing_order`、`get_prompt`、`close_session` 都通过 `session_id` 复用这份中间态，输出是工作区中的 `.src/.md/json` 文件，消费端是 IDE agent 或外部 MCP 客户端；底层机制/关键技术：`SessionStore` 内存缓存、TTL、工作区文件落盘、Mermaid 先写后校验、零 LLM/有 LLM 两套工具集；关键源码：[codewiki/codewiki/mcp/server.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/mcp/server.py:4) 的工具定义和 `analyze_repo` 说明，[codewiki/codewiki/mcp/session.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/mcp/session.py:30) 的 `SessionState`/`SessionStore`, [codewiki/codewiki/cli/main.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/main.py:42) 的 `mcp_command`；复用价值：很适合借鉴到“长任务、分步写文件”的 agent 工具包里；局限：会话状态是进程内缓存，最大 10 个会话，2 小时过期，重启即失。
4. 生成可离线打开的静态 HTML 站点：当用户选择 `--github-pages` 时，`HTMLGenerator` 会把 `viewer_template.html`、`module_tree.json` 和 `metadata.json` 拼成单个 `index.html`；触发→接管→输出→消费：`generate` 命令准备 docs 目录，`HTMLGenerator.generate` 做模板替换，输出是静态 HTML 文件，消费端是浏览器或 GitHub Pages；底层机制/关键技术：模板占位符替换、`safe_read`/`safe_write`、元数据回填、路径相对化；关键源码：[codewiki/codewiki/cli/html_generator.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/html_generator.py:83) 的 `generate`，[codewiki/codewiki/cli/html_generator.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/html_generator.py:35) 的 `load_module_tree`/`load_metadata`, [codewiki/codewiki/run_web_app.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/run_web_app.py:1) 的 web 入口；复用价值：适合做“离线可分享”的文档产物；局限：本质是静态查看器，不承载复杂交互逻辑。
5. 兼容本地 Web App 与 CLI/Web 上下文：`run_web_app.py` 负责把 `src` 加入 Python path 并启动前端 web app；触发→接管→输出→消费：脚本启动 `fe.web_app.main`，`codewiki/src/config.py` 通过 `_CLI_CONTEXT` 区分 CLI 和 Web 环境，输出是不同环境下的一套同构文档/分析行为，消费端是浏览器里的 Web App 或命令行；底层机制/关键技术：环境变量、上下文切换、统一配置对象；关键源码：[codewiki/codewiki/run_web_app.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/run_web_app.py:1) 的 `main`，[codewiki/codewiki/src/config.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/src/config.py:33) 的 `_CLI_CONTEXT` / `set_cli_context`, [codewiki/codewiki/cli/main.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/main.py:64) 的 `main`；复用价值：同一套配置与分析代码可以同时服务 CLI 与 Web；局限：Web 入口看起来很轻，真正重逻辑仍在 CLI/MCP/生成器里。

## 事实
- README 明确把它定义为“AI-powered repository documentation generation”，并说明支持多语言、架构感知分析和视觉产物；见 [README.md](/Volumes/T7/workspace/ontology/graph/repo/codewiki/README.md:1)。
- `pyproject.toml` 声明了 `codewiki = "codewiki.cli.main:cli"`，所以命令行入口就是 Click CLI；见 [pyproject.toml](/Volumes/T7/workspace/ontology/graph/repo/codewiki/pyproject.toml:81)。
- MCP 工具分成“零配置 IDE-driven 工具”和“需要 LLM 配置的 legacy 工具”；见 [mcp/server.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/mcp/server.py:4)。

## 推断
- 这个项目更适合作为“代码库文档流水线”而不是“实时问答助手”，因为大部分能力都围绕生成、落盘、回填和导出。
- `agent_instructions`、`prompt_caching` 和 provider 分支说明它支持较强的可配置性，适合被二次封装成团队内工具。

## 未知
- 仓库里没有单独的 `LICENSE` 文件，因此这里只能依据 `pyproject.toml` 的 MIT 声明判断许可证。

## 对 Skill / 项目 / CLI 决策的启示
CodeWiki 把重分析、增量和 HTML 生成放在独立 CLI，把 MCP 作为第二入口。这直接支持“独立项目 + CLI 内核 + HTML 产物；Skill/MCP 只做调用适配”的边界。
