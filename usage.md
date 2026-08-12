# RepoLens 使用说明

RepoLens（CLI 命令为 `repo-teacher`）是一个本地代码仓库教学报告生成器。它先建立文件、符号与依赖图，再由模型把源码证据归纳成“项目定位 → 产品主轴 → 业务功能 → 端到端交互 → 底层机制 → 难点与取舍 → 工程结构 → 源码证据”，最终为每个仓库生成一个主要给人阅读的 `index.html`。

正常使用只需执行一次 `report`。它严格顺序运行五个固定阶段：固定源码、CodeGraph/AST
索引、一次生成完整内容、证据校验、原子发布。每阶段都有缓存和耗时记录；失败不会自动回跳
或反复调用模型，修好原因后再次执行会复用输入身份未变化的通过阶段。

实现中 `cli.py` 只解析参数并装配命令；中文 Agent 合同在
`src/repo_teacher/agents/`，版本化 Prompt 在 `src/repo_teacher/prompts/`，
JSON Schema 在 `src/repo_teacher/schemas/`，Codex/OpenCode/DeepSeek 的传输、
超时与 JSON 解码在 `src/repo_teacher/providers/`。这些边界由架构测试锁定。

它不会把 `main`、路由、健康检查、数据库迁移、example 或 UI primitive 直接当成一级产品功能。example 会保留在对应业务功能的“仓库已有场景”和源码证据中。

每个业务功能必须先说“简单来说，这个功能就是……”，然后用交互图和文字讲清触发者、运行时所有者、数据/状态交接、循环与路由、结束/打断、真实例子和证据边界。语音项目会额外说明采集、VAD、ASR、Flow/LLM/Tool、TTS 与回放链；平台/Worker 项目会说明本地或远端执行、任务类型、队列、产物、部署和状态回传。

## 最快使用：本地界面

```bash
cd /Volumes/T7/workspace/ontology/graph/dev/repo
.venv/bin/repo-teacher ui --open
```

若 8787 端口被占用：

```bash
.venv/bin/repo-teacher ui --port 0 --open
```

界面中填写：

1. 源码仓库绝对路径。
2. HTML 输出根目录。
3. 报告名称；结果写到 `<输出根目录>/<报告名称>/index.html`。
4. 执行后端：Codex 或 OpenCode。
5. OpenCode 模式下选择 DeepSeek Flash 或 Pro，并输入 OpenRouter API Key。
6. 点击“开始生成报告”，右侧实时显示五个固定阶段、耗时、失败原因和日志。

API Key 仅注入本次 OpenCode 子进程的环境变量，不进入命令行参数、任务 JSON、日志、HTML 或本地配置文件。也可以在启动界面前设置 `OPENROUTER_API_KEY`，这样界面无需填写。

## OpenCode 与本机 NVM

本机 NVM 位于外接硬盘：

```bash
export NVM_DIR=/Volumes/T7/programe/env/nvm
source "$NVM_DIR/nvm.sh"
nvm use 22
opencode --version
```

Repo Teacher 会依次从 `REPO_TEACHER_OPENCODE_BIN`、当前 `PATH`、`~/.local/bin` 和 NVM 版本目录寻找 OpenCode。JS 语法校验所需的 Node 会从 `REPO_TEACHER_NODE`、`NVM_BIN`、`PATH` 或登录 shell 自动发现，所以后台和非交互 CLI 也能使用外接硬盘中的 NVM。

## 直接使用 CLI

需要单独查看功能清单时：

```bash
.venv/bin/repo-teacher inventory \
  /absolute/path/to/repository \
  --output /absolute/path/to/capability-inventory.json \
  --provider codex
```

已有审核清单时可以复用：

```bash
.venv/bin/repo-teacher report \
  /absolute/path/to/repository \
  --output /absolute/path/to/reports/project-name \
  --inventory /absolute/path/to/capability-inventory.json \
  --provider codex
```

Codex 全自动生产流程：

```bash
.venv/bin/repo-teacher report \
  /absolute/path/to/repository \
  --output /absolute/path/to/reports/project-name \
  --provider codex \
  --model-timeout 3600
```

OpenCode + DeepSeek Flash：

```bash
export OPENROUTER_API_KEY='在当前终端临时设置，不要写入仓库'
export REPO_TEACHER_OPENCODE_MODEL='openrouter/deepseek/deepseek-v4-flash'
.venv/bin/repo-teacher report \
  /absolute/path/to/repository \
  --output /absolute/path/to/reports/project-name \
  --provider opencode \
  --model-timeout 3600
```

DeepSeek Pro 使用 `openrouter/deepseek/deepseek-v4-pro`。

## 报告阅读顺序

1. **这是什么项目**：产品类型、用户、结果和差异点。
2. **项目工程结构**：前端、后端、Worker、媒体、共享协议和目录边界。
3. **产品主轴与交互图**：最多四条，先建立项目的产品心智模型和端到端数据流。
4. **业务功能**：用户能完成什么；框架项目则是开发者能构建或控制什么。
5. **实现机制**：跨哪些模块完成，状态和控制权怎样传递。
6. **真正难点**：不变量、失败方式、当前取舍和生产边界。
7. **源码证据**：最后下钻到文件、行号、符号和静态关系。

运维、治理、通用平台和工程能力默认折叠，不与核心业务功能并列。

## 产物

- `index.html`：主要人类报告。
- `current/index.json`：当前固定版本的机器索引。
- `current/human-report.json`：模型生成的业务功能与教程结构。
- `current/capability-graph.json`：代码图和功能切片。
- `current/analysis-pack.json`：有界证据包。
- `current/source-manifest.json`：源码身份与闭包。
- `current/approval.json`：仅在显式传入 `--inventory` 时生成。
- `current/chapters/*.json`：逐章结构化内容。
- `current/chapter-validation/*.json`：逐章证据和叙述合同检查。
- `.<报告名>.pipeline/stages/01-*.json` 至 `05-*.json`：固定阶段状态与输入输出 digest。
- `.<报告名>.pipeline/stages/pipeline.json`：Pipeline 当前阶段和最终状态。
- `<报告名>.performance.json`：五阶段 wall time、模型调用次数与最长阶段；界面读取同一合同。

`inventory` 会在功能清单旁发布 `.validation.json`、`.run-manifest.json` 和
`.performance.json`。
第 04 阶段用确定性 Schema、路径、行号和证据闭包验证第 03 阶段的一次输出；失败时不发布，
也不触发隐式语义返修。

根目录入口和 `current/` 由同一 generation 发布；不要手工修改生成文件。
