# RepoLens 使用说明

RepoLens（CLI 命令保留为 `repo-teacher`）是一个本地代码仓库教学报告生成器。它先建立文件、符号与依赖图，再由模型把源码证据归纳成“项目定位 → 产品主轴 → 业务功能 → 端到端交互 → 底层机制 → 难点与取舍 → 工程结构 → 源码证据”，最终为每个仓库生成一个主要给人阅读的 `index.html`。

## 生产架构

RepoLens 的 `report` 是一个无需人工介入、不会自动回跳的固定五阶段 Pipeline：

`01 固定源码 → 02 CodeGraph/AST 索引 → 03 一次内容生成 → 04 证据校验 → 05 原子发布`

五个阶段各写一个可缓存 JSON。模型只在第 03 阶段调用一次；输出不满足 Schema 或证据闭包时，
任务就明确失败在第 03/04 阶段，下次从已经通过且输入身份相同的产物继续，不启动“语义返修循环”。

- `repo_teacher.pipeline`：阶段顺序、缓存、失败语义和进度合同。
- `repo_teacher.agents`：项目定位、业务功能和章节写作角色合同。
- `repo_teacher.prompts`：版本化 prompt 资源。
- `repo_teacher.schemas`：模型结构化输出合同。
- `repo_teacher.providers`：Codex、OpenCode/DeepSeek 的发现、传输、超时、
  JSON 解码与测试 fake；CLI 不包含模型调用实现。
- `repo_teacher.renderers`：把已验证报告模型渲染为离线 HTML，不参与功能判断。
- `skills/repository-report`：调用同一条 CLI，不复制产品逻辑。

完整技术决策见 [`docs/architecture/five-stage-reference-pipeline.md`](docs/architecture/five-stage-reference-pipeline.md)。

它不会把 `main`、路由、鉴权、健康检查、数据库迁移、example 或 UI primitive 直接当成一级产品功能。example 会保留在对应业务功能的“真实场景”和源码证据中。

每个业务功能必须先说“简单来说，这个功能就是……”，然后用交互图和文字回答：

- 谁触发，谁接管，产生什么，交给谁；
- 每一步读什么、写什么、由谁决定下一步；
- 循环、事件循环、路由、并发、等待和合并怎样工作；
- 如何结束、打断、失败和恢复；
- 一个真实场景从头到尾怎样运行；
- 哪些结论由源码证明，哪些仍然未知。

语音项目还必须讲清采集/送帧、缓冲、VAD、ASR、Flow/LLM/Tool、TTS、音频与文本回传、客户端播放及打断之间的完整交接。平台/Worker 项目必须讲清任务在本地还是远端执行、提交什么、怎样排队、Worker 实际做什么、产物放哪里、怎样部署和回传状态。

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

Repo Teacher 会依次从 `REPO_TEACHER_OPENCODE_BIN`、当前 `PATH`、`~/.local/bin` 和 NVM 版本目录寻找 OpenCode。JS 语法校验所需的 Node 也会先查 `REPO_TEACHER_NODE` / `NVM_BIN` / `PATH`，最后从登录 shell 读取外接硬盘上的 NVM 版本；非交互 CLI 不再要求手工执行 `nvm use`。

## 直接使用 CLI

### 推荐：纯 Skill Markdown-first 流水线

在 Codex、Claude Code 或 OpenCode 中直接调用 `$repository-report`，并提供源码与输出目录：

```text
使用 $repository-report
SOURCE=/absolute/path/to/repository
OUTPUT=/absolute/path/to/report
STAGE=all
```

只先检查功能覆盖时把 `STAGE` 改为 `capabilities`。Skill 由当前 agent 本体顺序生成阶段 Markdown 和 `index.html`，不调用 RepoLens 产品程序、渲染器或辅助脚本；CodeGraph 只用于源码关系取证。完整合同见 [`skills/repository-report/SKILL.md`](skills/repository-report/SKILL.md)。

需要单独检查功能清单时，可只运行 inventory：

```bash
.venv/bin/repo-teacher inventory \
  /absolute/path/to/repository \
  --output /absolute/path/to/capability-inventory.json \
  --provider codex
```

也可以把已审核清单交给完整报告，跳过重复识别：

```bash
.venv/bin/repo-teacher report \
  /absolute/path/to/repository \
  --output /absolute/path/to/reports/project-name \
  --inventory /absolute/path/to/capability-inventory.json \
  --provider codex
```

Codex：

```bash
.venv/bin/repo-teacher report \
  /absolute/path/to/repository \
  --output /absolute/path/to/reports/project-name \
  --provider codex \
  --model-timeout 3600
```

`report` 默认从源码快照一直运行到 `index.html`，不需要人工确认。`--inventory` 只是复用已有
证据闭合功能目录的高级入口，不是正常使用的必经步骤。

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
3. **产品主轴与交互图**：先建立项目的产品心智模型和端到端数据流。
4. **业务功能**：用户能完成什么；框架项目则是开发者能构建或控制什么。
5. **实现机制**：跨哪些模块完成，状态和控制权怎样传递。
6. **真正难点**：不变量、失败方式、当前取舍和生产边界。
7. **源码证据**：最后下钻到文件、行号、符号和静态关系。

运维、治理、通用平台和工程能力默认折叠，不与核心业务功能并列。

## 产物

- `index.html`：主要人类报告，离线可读，交互图无需外部运行时。
- `current/index.json`：当前固定版本的机器索引。
- `current/human-report.json`：模型生成的业务功能与教程结构。
- `current/capability-graph.json`：代码图和功能切片。
- `current/analysis-pack.json`：有界证据包。
- `current/source-manifest.json`：本次读取的源码身份与闭包。
- `current/approval.json`：仅在显式传入 `--inventory` 时记录其身份。
- `current/chapters/*.json`：逐章结构化内容。
- `current/chapter-validation/*.json`：逐章证据和叙述合同检查。
- `.<报告名>.pipeline/stages/01-*.json` 至 `05-*.json`：固定五阶段账本；每阶段记录
  `passed/failed`、输入/输出 digest 与耗时。
- `.<报告名>.pipeline/stages/pipeline.json`：当前阶段和整条 Pipeline 终态。

`inventory` 命令同样会在功能清单旁发布 `.validation.json`、
`.run-manifest.json` 和 `.performance.json`。`report` 会在报告目录旁发布
`<报告名>.performance.json`。性能文件按五阶段记录 wall time、模型调用次数和最长阶段；
本地界面读取同一进度合同。没有隐藏的审校重试次数或分片循环。

根目录入口和 `current/` 由同一 generation 发布；不要手工修改生成文件。

## 验证报告

```bash
.venv/bin/repo-teacher validate \
  /absolute/path/to/reports/project-name/index.json \
  --source /absolute/path/to/repository
```

根入口和 `current/index.json` 都应通过验证。报告中的性能、生产规模、运行可达性等结论只有在实际运行证据存在时才会标为已确认。
