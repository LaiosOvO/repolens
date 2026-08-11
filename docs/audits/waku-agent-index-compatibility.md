# Waku Agent 真实仓库索引兼容性审计

> 审计日期：2026-08-10  
> 参考仓库：`/Volumes/T7/workspace/ontology/graph/repo/waku-agent`  
> Repo Teacher：`/Volumes/T7/workspace/ontology/graph/dev/repo`  
> 测试产物：`/tmp/repo-teacher-waku-compat.ZwhVuM`  
> 持久化范围：仅本报告；没有修改 Waku Agent、Repo Teacher 源码、测试、examples 或 biz。

## 一句话结论

**Waku Agent 可以作为 Repo Teacher 的第七个真实兼容性样本：冷索引、磁盘暖索引、校验和 `memory / graph / loop / gateway` 四个模块解释均成功。**

但这不是“无条件的教学质量 PASS”：索引器对仓库结构的覆盖很好，通用 feature 发现却只产生 2 个入口功能；`loop` 查询受“语音 wake loop”同名词干扰，并把一条 `self.model.transcribe()` 启发式调用边错误解析为 `Ears.transcribe -> Ears.transcribe`。另外发现两个 generation 兼容入口问题：`current/index.json` 无法直接校验，且不存在的 compare/project 产物仍有悬空符号链接。

## 结果看板

| 检查面 | 结果 | 证据 |
|---|---:|---|
| 仓库身份 | PASS | HEAD `75b0a6d27a19009b0482c877def3eb124181f121`，`main`，工作树干净 |
| 完整 clone | PASS | `--is-shallow-repository=false`，274 commits，4 tags，`git fsck --full --no-dangling` exit 0 |
| 许可证 | PASS | 根目录 `LICENSE`，MIT，Copyright 2026 Sean Chen |
| fresh cold index | PASS | 212 files / 1,557 symbols / 9,879 relationships / 13 modules |
| cold validate | PASS | `Index validation: PASS (0 errors, 0 warnings)` |
| 磁盘 warm index | PASS | 212 reused / 0 reanalyzed / `reused_derived_artifacts=true` |
| cold/warm 核心一致 | PASS | modules/files/symbols/relationships/reading_path/analyzers 逐项相等 |
| cold/warm 派生内容一致 | PASS | features/evidence/tutorials/codemaps/coverage 逐项相等 |
| `explain memory` | PASS with gaps | 24 files / 243 symbols，`composite_candidate`，high 0.82 |
| `explain graph` | PASS with gaps | 11 files / 107 symbols，`composite_candidate`，high 0.82 |
| `explain loop` | REQUEST CHANGES | 能找到 `waku/loop`，但受 wake loop 干扰并产生错误自调用边 |
| `explain gateway` | PASS with gaps | 9 files / 140 symbols，但 `entrypoints=[]` |
| HTML 解析 | PASS | 10 个 immutable HTML，0 parse errors |
| HTML 本地链接/锚点 | PASS | 0 broken page links / 0 missing fragments |
| 秘密扫描 | PASS | 26 个 JSON/HTML，0 credential-pattern hits，188 个 `[REDACTED]` |
| 稳定兼容链接 | REQUEST CHANGES | 16 个悬空 symlink，详见缺陷 RT-WAKU-02 |

## 1. 仓库身份与完整性

| 属性 | 实测值 |
|---|---|
| 路径 | `/Volumes/T7/workspace/ontology/graph/repo/waku-agent` |
| origin | `https://github.com/ShenSeanChen/waku-agent.git` |
| HEAD | `75b0a6d27a19009b0482c877def3eb124181f121` |
| branch | `main` |
| shallow | `false` |
| worktree | clean（`git status --short` 无输出） |
| commits | 274 |
| tags | 4 |
| remote branches | `origin/main`、`origin/memory/mem0-adapter`、`origin/ui/connections-memory-group` |
| packed objects | 2,641，1 pack，0 garbage |
| 磁盘大小 | 12 MiB |
| license | MIT |

`git fsck --full --no-dangling` 成功，且 `.git` 中没有 shallow 边界；因此这不是下载的 source archive，也不是 depth-limited clone。

## 2. 仓库实际提供什么

Waku Agent 是一个以 Python 为主的本地个人 Agent harness，它的实现重点不是“庞大框架”，而是把 Agent loop、三类记忆、图工作流、工具、多模型与多入口用直接可读的源码串起来。

### 2.1 功能与真实实现模块

| 功能 | 真实源码 | 实现方式 |
|---|---|---|
| Agent 装配与一轮对话 | `waku/app.py:18-171` | `Waku` 装配 settings、SQLite、model client、memory、tools、session 和 tracer；`respond()` 选 graph 或 plain loop，然后持久化 |
| Reason→Act→Observe loop | `waku/loop/agent.py:41-114` | 最多 `max_iterations`；模型不再请求工具时结束，工具结果追加回 messages |
| 多模型统一 | `waku/loop/models.py:235-465` | Anthropic wire format 为内部约定；`OpenAICompatClient` 转换 OpenAI-compatible messages/tools/stream |
| 本地长期记忆 | `waku/db.py:12-76`、`waku/memory/__init__.py:45-202` | SQLite + FTS5；semantic facts、episodic episodes、procedural SKILL.md 由 `Memory` facade 统一 |
| 记忆检索门 | `waku/memory/retrieval_gate.py:36-55` | 小模型决定是否检索；异常时 fail-open |
| 会话压缩/固化 | `waku/memory/consolidation.py:37-82` | 累积 N 个 exchange 后，小模型把 chat log 提取为 facts + episode |
| 有界工作上下文 | `waku/app.py:114-136`、`waku/runtime/session.py:63-127` | prompt 只携带最近 `history_turns * 2` 条，旧内容通过检索门返回 |
| 本地 Graph engine | `waku/graph/engine.py:49-206` | 节点/边/代码 router，同 wave 用 thread pool 并行，确定性 merge，检测 state-key collision |
| Triage workflow | `waku/graph/workflows/triage.py:89-125` | classify 与 calendar 并行，gather 后路由 quick reply 或 full agent |
| Gather workflow | `waku/graph/workflows/gather.py:97-157` | GitHub/Web/Calendar/Memory 四路并行扫描，合成后用代码 router 决定是否生成 draft |
| 工具注册表 | `waku/tools/registry.py:15-58`、`waku/tools/__init__.py:14-83` | schema + function 的小型 registry；工具异常转成模型可见文本 |
| MCP 连接 | `waku/tools/mcp_client.py:28-100` | 后台 asyncio loop + `run_coroutine_threadsafe`，把每个 MCP tool 映射进本地 registry |
| CLI/Telegram/Discord/WhatsApp | `waku/gateway/*.py` | 各 channel 只负责 I/O，最终都调 `Waku.respond()` |
| 异步 gateway 隔离 | `waku/gateway/runner.py:34-138` | 每个 gateway 一个 single-worker executor，保证 SQLite 的创建/使用/关闭在同一线程 |
| Gateway 生命周期 | `waku/gateway/supervisor.py:23-118` | 按配置指纹 restart，新实例失败时尝试恢复旧环境/旧实例 |
| 本地语音 | `waku/gateway/voice.py:49-328` | faster-whisper ASR + 话筒 RMS 静音切分 + 自定义 wake word + Kokoro/macOS `say` TTS |
| Dashboard/追踪 | `waku/ops/dashboard.py:64-1130`、`waku/ops/tracing.py:57-164` | 本地 HTTP dashboard、SSE 事件、JSONL trace，可选 OpenTelemetry |
| 确定性 evals | `evals/deterministic/` | gateway、graph、memory、model adapter、session、dashboard 等大量单测 |

### 2.2 一条完整实现流

1. CLI/语音/Telegram/Discord/WhatsApp 收到文本，异步 channel 先经过 `GatewayAgentRunner.respond()`。
2. `Waku.respond()` 组合 observer + tracer，并记录 gate/route/latency/tool 元数据。
3. `Session.build_system()` 装入 SOUL、当前时间、模型身份，按 retrieval gate 结果加入 facts/episodes，再加入匹配的 SKILL.md。
4. 若 `graph_workflows` 开启，triage graph 决定 quick path 或 full-agent path；graph 失败则回退到 plain loop。
5. `run_loop()` 重复 LLM call → tool execute → tool result 回填，直到无 tool call 或达到迭代上限。
6. `Session.add_exchange()` 写入当前 history 与 SQLite `chat_log`；`Memory.maybe_consolidate()` 按阈值生成长期 facts/episode，并重建可读 `MEMORY.md`。
7. Dashboard 和 JSONL/OTel tracer 消费同一 observer 事件，展示 loop、tool、gate 和 graph 路由。

### 2.3 对目标产品的参考价值

| 目标需求 | 可参考部分 | 边界 |
|---|---|---|
| 本地 Agent loop | `waku/loop/agent.py` | 非多 Agent 编排器；它是一个清晰的单 loop 内核 |
| 本地 context/memory | `waku/runtime/session.py`、`waku/memory/` | 适合“有界对话窗口 + 按需检索 + 后台固化”；不是完整 context-engineering 平台 |
| Graph engineering | `waku/graph/engine.py`、`waku/graph/workflows/` | 适合小型本地 DAG/并行 wave；没有分布式持久化、租约、任务恢复或多机调度 |
| 远程 channel 分发 | `waku/gateway/runner.py`、`supervisor.py`、各 adapter | 线程归属、序列化转回、失败回复值得复用；没有设备配对/零信任控制面 |
| 本地语音 | `waku/gateway/voice.py` | 是明确的 ASR→LLM→TTS 串联、wake-word 轮次系统；**不是全双工**，没有 barge-in/同时听说/实时音频模型 |
| MCP/外部工具 | `waku/tools/mcp_client.py` | 同步 Agent loop 跨到异步 MCP 的桥接值得参考；目前还是 stdio server 连接层 |
| 多模型 | `waku/loop/models.py` | 用一个内部消息协议降低 loop 复杂度的做法值得复用 |

## 3. Cold index 实测

### 3.1 命令

```bash
app=/Volumes/T7/workspace/ontology/graph/dev/repo
repo=/Volumes/T7/workspace/ontology/graph/repo/waku-agent
tmp=$(mktemp -d /tmp/repo-teacher-waku-compat.XXXXXX)

/usr/bin/time -l env PYTHONPATH="$app/src" \
  python3 -m repo_teacher index "$repo" -o "$tmp/cold"

PYTHONPATH="$app/src" python3 -m repo_teacher validate \
  "$tmp/cold/index.json" --source "$repo"
```

### 3.2 指标

| 指标 | 值 |
|---|---:|
| wall time | 13.00 s |
| user / sys | 3.77 s / 0.45 s |
| maximum resident set size | 169,132,032 bytes（约 161.3 MiB） |
| peak memory footprint | 159,974,848 bytes |
| files | 212 |
| lines | 31,037 |
| indexed bytes | 1,421,869 |
| visited entries / files | 303 / 251 |
| symbols | 1,557 |
| relationships | 9,879 |
| modules | 13 |
| features / evidence | 2 / 8 |
| tutorials / codemaps / coverage | 2 / 2 / 2 |
| diagnostics | 51 info，0 warning，0 error |
| freshness | `complete` |
| truncated | `false` |
| cold generation | `1a066c005f8189541f447fa77c41f4b3` |

冷索引首次正常多一条 `duplicate-relationships-normalized` info：139 条语义相同的重复关系被合并，0 true collisions。暖索引直接复用规范化后的基线，因此 diagnostics 为 50。

### 3.3 语言、符号与关系

| 类别 | 统计 |
|---|---|
| 语言 | Python 150，Markdown 34，JavaScript 10，JSON 4，YAML 3，HTML/Shell/TypeScript 各 2，CSS/License/Makefile/SQL/TOML 各 1 |
| 符号类型 | function 1,193，method 257，class 94，async-function 13 |
| analyzer | `python-ast` 1,343 符号，`javascript-regex` 214 符号 |
| 关系类型 | calls 7,049，contains 1,557，import 1,273 |
| 关系置信度 | exact 2,610，heuristic 7,269 |

50 条稳定 diagnostics 全是 `unsupported-analyzer` info：Markdown/YAML/JSON/HTML/CSS/Shell/SQL/TOML/Makefile/License 只索引文件元数据，不声称语义符号。这不是扫描失败，但会导致 SKILL.md、README 和配置中的业务语义无法进入图谱。

### 3.4 顶层模块召回

通用 index 生成 13 个顶层模块：`.`、`waku`、`evals`、`scripts`、`examples`、`.pi`、`pi-pokedex`、`.agents`、`.claude`、`.github`、`docs`、`skills`、`sql`。

其中 `waku` 一个模块容纳 95 文件/814 符号，`evals` 容纳 65 文件/728 符号。这对“仓库地图”足够，对“功能精确模块”不足；`memory/graph/loop/gateway` 需要通过 `explain` 的 composite surface 才能被拆开。

## 4. Explain 四个真实功能

四次 `explain` 都使用独立 temp output，不写参考仓。四个 output 的 `index.json` 再次执行 `validate` 均为 `PASS (0 errors, 0 warnings)`。

| query | generation | wall | max RSS | 结果 |
|---|---|---:|---:|---|
| memory | `9cf4d4e945a3850f18f4b75bafa67834` | 6.27 s | 177,668,096 B | 24 files / 243 symbols / high 0.82 |
| graph | `0080ae9c040f966a2060e7efd955f4ec` | 5.02 s | 179,388,416 B | 11 files / 107 symbols / high 0.82 |
| loop | `e89c558d489dd08c92d22cdf6c038e4b` | 4.49 s | 174,342,144 B | 6 files / 84 symbols / medium 0.72 |
| gateway | `d3b7eee485a5826a125b0645392a0528` | 5.37 s | 175,374,336 B | 9 files / 140 symbols / medium 0.62 |

四项 resolution 均为 `composite_candidate`、`verified_capability_surface=false`。这个口径是正确的：它声称“找到源码切片”，没有把静态匹配冒充为运行时功能验证。

### 4.1 memory

**正确召回**

- `waku/memory/__init__.py`：Memory facade、backend selection、gated retrieve、chat log、MEMORY.md export、consolidation。
- `waku/memory/semantic/*`：SQLite FTS5 及 Supabase/Mem0/Zep/LangMem adapters。
- `waku/memory/episodic/*`：SQLite/Notion episodic store。
- `waku/memory/procedural/*`：SKILL.md loader/installer。
- `waku/memory/retrieval_gate.py`、`consolidation.py`。
- `waku/tools/memory_admin.py`：记忆更正/删除/技能创建。
- 召回 17 个相关 eval test files。

**过宽/角色误分**

- `evals/memory_arena.json` 被标成 `core`，它更应是 eval fixture。
- `waku/ops/static/js/compare.js` 被标成 `core`，它是对比 UI，不是 memory 核心实现。
- `waku/gateway/cli.py` 被当作 memory entrypoint，实际只因 `_memory_snapshot()` 命中。

### 4.2 graph

**正确召回**

- `waku/graph/engine.py`、`nodes.py`、`workflows/gather.py`、`workflows/triage.py`。
- `waku/app.py:138-171` 对 graph 的真实装配与 fail-open fallback。
- `waku/ops/gather.py` 对 gather graph 的真实依赖绑定。
- `waku/ops/static/js/graph.js` 和 dashboard，作为可视化面。
- 召回 graph engine/nodes/stream/topology/triage/gather 等相关 evals。

**注意**

- `waku/ops/whiteboard/build_loop_vs_graph.py` 是 presentation slice，报告已正确标为 `presentation`，不应与 engine 相同权重。
- 索引找到了真实 `run_graph`、`Graph.add_edge`、`Waku._respond_via_graph`，这一项的功能命中最稳定。

### 4.3 loop

**正确召回**

- `waku/loop/agent.py`：真正的 reason/act/observe `run_loop`。
- `waku/loop/models.py`：provider/client adapter。

**关键误报**

1. 查询结果把 `waku/gateway/voice.py` 的 `wake_loop` 排在 `run_loop` 之前；这是同名词命中，但不是 Agent loop。
2. 报告的第一条 implementation trace 是：

   ```text
   rel_7c8ce5957801d856
   waku/gateway/voice.py:59  Ears.transcribe
     calls ->
   waku/gateway/voice.py:58  Ears.transcribe
   confidence=heuristic
   ```

   真实源码是：

   ```python
   def transcribe(self, audio, language: str | None = None) -> str:
       segments, _ = self.model.transcribe(...)
   ```

   `self.model.transcribe()` 是对 Whisper model 的外部调用，不是 `Ears.transcribe()` 递归自调用。这是可独立复现的 Python attribute-call 启发式解析误报。
3. `waku/ops/static/js/models.js` 和 whiteboard builder 命中的是模型 UI/教学图，不是 loop 内核。

### 4.4 gateway

**正确召回**

- `waku/gateway/cli.py`、`telegram.py`、`discord.py`、`whatsapp.py`、`voice.py`。
- `waku/gateway/runner.py`：async channel 到 sync Waku/SQLite 的专用线程桥。
- `waku/gateway/supervisor.py`：后台 gateway lifecycle 与 restart rollback。
- `waku/integrations.py`：配置、状态、probe 与 provider/gateway registry。
- 召回 gateway runner/supervisor/Discord access/connections CLI 等 evals。

**漏报**

`gateway` report 的 `entrypoints=[]`，但以下真实入口都存在：

- `waku/gateway/cli.py:55 main`
- `waku/gateway/telegram.py:76 main`
- `waku/gateway/discord.py:194 main`
- `waku/gateway/voice.py:310 main`
- `waku/gateway/whatsapp.py:237 main`

这表明 composite surface 的“文件召回”比“入口角色分类”更稳定。

## 5. Warm index 实测

暖索引是第二个独立 CLI 进程，对同一 output 再次执行 `index`。CLI 通过 `read_published_json(output, "index.json")` 从 `current` generation 的 manifest 验证并读取磁盘基线，不存在进程内内存复用。

```bash
/usr/bin/time -l env PYTHONPATH="$app/src" \
  python3 -m repo_teacher index "$repo" -o "$tmp/cold"
```

| 指标 | cold | warm |
|---|---:|---:|
| wall | 13.00 s | 5.13 s |
| max RSS | 169,132,032 B | 178,339,840 B |
| files | 212 | 212 |
| reused | 0 | 212 |
| reanalyzed | 212 | 0 |
| reused derived | false | true |
| generation | `1a066c005f8189541f447fa77c41f4b3` | `5ec56864a019e228942bae5904a9a104` |
| validate | PASS 0/0 | PASS 0/0 |

### 5.1 一致性

**完全相等的核心集合：** `schema_version`、`analysis_fingerprint`、`analysis_config`、`analyzers`、`modules`、`files`、`symbols`、`relationships`、`reading_path`、`source_manifest_sha256`、`freshness`。

**完全相等的派生集合：** `features`、`evidence`、`tutorials`、`codemaps`、`coverage`。

`project` 除 `analyzed_at` 外完全相等。基线 commit、source manifest 和 analysis fingerprint 都没有变化。

### 5.2 `derived_sha256` 的观测语义

虽然派生集合逐项完全相等，冷/暖 `derived_sha256` 不同：

- cold: `5f21a09a01e7039b5c76f74ec2b7e773f2ae0e1c63d0d8d9ca915ef125586b6c`
- warm: `efd6588edee427eaddfaa963f20911596377045ea364d8c59ddaa133a492c513`

原因是该 digest 还包含 `stats`，而 `reused_files/reanalyzed_files/reused_derived_artifacts/diagnostics` 在 cold/warm 本来就不同。因此它是“派生产物 + 运行统计封装”的 digest，不是纯派生内容 digest。这不导致基线复用失败，但名称与可观测语义不够直观。

## 6. HTML、链接、generation 与 secret 验证

### 6.1 HTML

解析了 10 个唯一 immutable HTML：冷/暖 2 个 index，四个 explain 的 4 个 index + 4 个 module report。

| 检查 | 结果 |
|---|---:|
| HTML parser errors | 0 |
| page-internal broken local paths | 0 |
| missing fragments | 0 |

四个 explain index 的 `validate` 也间接验证了整个 current generation manifest：每个 artifact 都是常规文件、集合与 manifest 完全闭合，size/SHA-256 和 embedded generation ID 一致。

### 6.2 Secret scan

对 26 个唯一 JSON/HTML 扫描了 AWS、GitHub、GitLab、Slack、Anthropic、OpenAI/Stripe-style key、JWT、private key、credential URL 和 unredacted Bearer token 模式：

- credential-pattern hits: **0**
- `[REDACTED]` markers: **188**

Waku 源码中 WhatsApp token、Telegram token 等相关签名/片段已在持久化 JSON/HTML 中脱敏。

## 7. 精确产品缺陷

### RT-WAKU-01：`current/index.json` 无法作为 validate 入参

**严重度：P1（发布代语义/可用性）**

复现：

```bash
PYTHONPATH="$app/src" python3 -m repo_teacher validate \
  "$tmp/cold/current/index.json" --source "$repo"
```

实际：

```text
error: failed to validate index: JSON artifact is not part of the current generation: current/index.json
```

对照：

```bash
PYTHONPATH="$app/src" python3 -m repo_teacher validate \
  "$tmp/cold/index.json" --source "$repo"
# Index validation: PASS (0 errors, 0 warnings)
```

两个路径最终指向同一 generation 的同一 `index.json`。`read_json_path()` 在发现 managed output 后使用 lexical relative path；`current/index.json` 被传给 `read_published_json()` 时定义为 `current/index.json`，而 manifest 声明的是 `index.json`，因此被拒绝。

### RT-WAKU-02：不存在的产物仍建立 compatibility symlink

**严重度：P1（输出闭包/用户导航）**

index output 只发布 `index.json/index.html`，但顶层还建立：

```text
technology-selection.json -> current/technology-selection.json
technology-selection.html -> current/technology-selection.html
projects                  -> current/projects
modules                   -> current/modules
```

这四个在 cold index output 都悬空。Explain output 的 `modules` 存在，但 `technology-selection.{json,html}` 和 `projects` 仍悬空。五个 output 合计检出 16 个 dangling compatibility links。

最小验证：

```bash
test -L "$tmp/cold/technology-selection.html"
test ! -e "$tmp/cold/technology-selection.html"
```

### RT-WAKU-03：Python attribute call 错误解析成当前方法自调用

**严重度：P1（教学实现流准确性）**

最小反例是 `waku/gateway/voice.py:58-62`：

```python
def transcribe(self, audio, language: str | None = None) -> str:
    segments, _ = self.model.transcribe(audio, language=...)
```

产物关系 `rel_7c8ce5957801d856` 把 line 59 解析为对 line 58 `Ears.transcribe` 的调用，并把这条边放在 `explain loop` 的第一条 implementation trace。边的 confidence 是 heuristic，但在主实现流中的位置仍会误导用户。

### RT-WAKU-04：功能发现与项目实际能力间的召回差距

**严重度：P2（教学完整性）**

通用 feature discovery 只生成：

1. `waku/__main__.py · main`
2. `waku/gateway/cli.py · main`

它没有生成 memory、graph、agent loop、gateway adapters、MCP、dashboard 等语义功能，相关 technology claims 大部分为 `unknown`。`explain` 能弥补文件级召回，但它们不会出现在首屏 feature/tutorial/codemap 教学结构中。

### RT-WAKU-05：通用 reading path 对真实执行主线排序不理想

**严重度：P2（教学导航）**

reading path 在 README 之后先放入 `Makefile` 和子项目 `pi-pokedex/package.json`，才到 `waku/app.py`；“理解 waku 模块”的代表文件是 `waku/ops/static/js/compare.js`，“理解 evals 模块”是 `test_gateway_runner.py`。对这个仓库，更有教学价值的顺序是：

```text
README -> waku/app.py -> runtime/session.py -> loop/agent.py
       -> tools/registry.py -> memory/__init__.py -> graph/engine.py
       -> gateways -> dashboard/tracing -> evals
```

## 8. 建议的正式回归断言

Waku Agent 应在源码冻结后加入正式 examples/总账，至少锁定以下断言：

1. Git identity 必须是本报告的 commit/remote/clean state。
2. cold index 必须 `freshness=complete`、`truncated=false`、validate 0 errors。
3. warm 必须 212/212 reuse、0 reanalyze，并保持 core + derived collections 相等。
4. `explain memory` 必须包含 `waku/memory/__init__.py`、`semantic/store.py`、`retrieval_gate.py`、`consolidation.py`。
5. `explain graph` 必须包含 `waku/graph/engine.py`、`workflows/triage.py`、`workflows/gather.py`。
6. `explain loop` 必须把 `waku/loop/agent.py:run_loop` 排在 wake loop/UI/presentation 之前，且不得生成 `Ears.transcribe -> Ears.transcribe` 边。
7. `explain gateway` 必须包含 runner/supervisor 和五个真实 `main` 入口。
8. 只为本 generation 实际存在的 artifact 创建 compatibility link；全部稳定入口不得 dangling。
9. `validate output/index.json` 和 `validate output/current/index.json` 必须具有相同结果。
10. 生成 HTML 必须 0 parse errors、0 broken local links、0 missing fragments，secret scan 0 hits。

## 9. 命令证据总账

```bash
# clone / identity
git -C "$repo" rev-parse HEAD
git -C "$repo" rev-parse --is-shallow-repository
git -C "$repo" status --short
git -C "$repo" remote get-url origin
git -C "$repo" rev-list --count HEAD
git -C "$repo" fsck --full --no-dangling

# cold + validate
/usr/bin/time -l env PYTHONPATH="$app/src" \
  python3 -m repo_teacher index "$repo" -o "$tmp/cold"
PYTHONPATH="$app/src" python3 -m repo_teacher validate \
  "$tmp/cold/index.json" --source "$repo"

# four independent explain outputs
for q in memory graph loop gateway; do
  /usr/bin/time -l env PYTHONPATH="$app/src" \
    python3 -m repo_teacher explain "$repo" "$q" -o "$tmp/explain-$q"
  PYTHONPATH="$app/src" python3 -m repo_teacher validate \
    "$tmp/explain-$q/index.json" --source "$repo"
done

# warm, same output, independent process and disk generation baseline
/usr/bin/time -l env PYTHONPATH="$app/src" \
  python3 -m repo_teacher index "$repo" -o "$tmp/cold"
PYTHONPATH="$app/src" python3 -m repo_teacher validate \
  "$tmp/cold/index.json" --source "$repo"
```

HTML/link/fragment/secret 检查使用 Python 标准库 `html.parser`、`pathlib`、`urllib.parse` 和与 Repo Teacher 脱敏边界相同的 credential regex 家族；没有安装新依赖。

## 10. 最终判定

**作为“新语言/架构样本能否被处理”的兼容性测试：PASS。**

**作为“用户可直接相信的功能教学索引”：REQUEST CHANGES。** 必须先修复 `current/index.json` 路径语义、悬空兼容链接和 Python attribute-call 误解析，并用本报告第 8 节的回归断言重跑。
