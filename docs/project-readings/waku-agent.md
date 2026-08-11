# Waku Agent 阅读笔记

## 固定版本与许可

- 本地完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/waku-agent`
- `origin`：`https://github.com/ShenSeanChen/waku-agent.git`
- HEAD：`75b0a6d27a19009b0482c877def3eb124181f121`
- 工作树：clean
- 许可证：MIT（根目录 `LICENSE`）

## 一句话定位

Waku 是本地优先的个人 Agent 运行时，把显式模型/工具循环、长期记忆、图工作流、多通道 Gateway、本地语音、模型供应商和评测运维放在同一 Python 项目中。

## 产品形态

- Python CLI：`waku` 及其 dashboard/gateway/voice/eval 等子命令；
- 本地 Dashboard：标准库 HTTP server + 静态前端；
- 多通道 Gateway 进程；
- SQLite 本地状态与 JSONL/OTEL 观测；
- 它是 Repo Teacher 的**唯一第一阶段端到端测试仓**，不是代码教学产品形态参考。

## 九个主要功能与实现

| 功能 | 触发 → 接管 → 输出 → 消费 | 底层技术 | 关键源码与测试 |
| --- | --- | --- | --- |
| Agent Loop | `Waku.respond`/Gateway 消息 → `Waku._run_full_turn` + `run_loop` → `LoopResult`/tool events → CLI、Dashboard、Gateway | 显式迭代预算、Anthropic/OpenAI wire adapter、tool schema | `waku/loop/agent.py:35-114`; `waku/app.py:114-137`; `evals/deterministic/test_tool_trigger.py` |
| Memory | turn 前检索/turn 后写入 → `Memory`/consolidation → facts、episodes、history、Markdown → 后续 prompt/Dashboard | SQLite、retrieval gate、fact/episode stores、周期整理 | `waku/memory/__init__.py:45-202`; `waku/memory/consolidation.py:37-82`; `evals/deterministic/test_retrieval_gate.py` |
| Graph Workflow | graph mode/工作流请求 → `Graph` + `run_graph` → 合并 state/事件/路由 → Agent/Dashboard observer | DAG、wave scheduling、ThreadPoolExecutor、reducers、router | `waku/graph/engine.py:54-206`; `waku/graph/nodes.py:18-78`; `evals/deterministic/test_graph_engine.py` |
| Gateway | Telegram/Discord/WhatsApp 消息 → channel adapter + `GatewayAgentRunner`/supervisor → 安全文本/状态 → 外部通道 | asyncio、session isolation、channel adapter、supervisor | `waku/gateway/runner.py:21-138`; `waku/gateway/supervisor.py:1-118`; gateway 系列 deterministic tests |
| Voice | voice CLI/唤醒词 → `Ears`/`wake_loop`/Waku/`Mouth` → 转写、回复、朗读 → 本地用户 | sounddevice、faster-whisper、能量/静音切分、macOS `say` | `waku/gateway/voice.py:32-310`; `evals/deterministic/test_wake_word.py`; `test_speakable.py` |
| Tools / MCP | 模型 tool_use → `ToolRegistry`/`MCPBridge` → tool result/error → 下一模型回合/tracing | JSON Schema、MCP、async bridge | `waku/tools/registry.py:16-58`; `waku/tools/mcp_client.py:28-100`; tool/MCP tests |
| Model Providers | Settings/界面切换 → provider catalog + `get_client`/`apply_provider` → 统一 client/config → loop/judge/arena | adapter、Anthropic SDK、OpenAI-compatible API、health probe | `waku/loop/models.py:29-310`; `waku/integrations.py:711-828`; `test_providers.py` |
| Dashboard / Observability | dashboard 启动/observer event → `Handler`/`Tracer` → 本地 API、event、JSONL、OTEL → 操作者与评测 | `BaseHTTPRequestHandler`、事件流、JSONL、OpenTelemetry | `waku/ops/dashboard.py:883-1157`; `waku/ops/tracing.py:35-167`; dashboard/trace tests |
| Eval / Release Gate | CI/开发者命令 → `release_gate` + scoring/judge suites → exit code/report/score → 发布流程 | pytest、subprocess gate、LLM judge、确定性工具评分 | `waku/ops/release_gate.py:27-92`; `waku/ops/scoring.py:24-59`; eval suites |

## 值得借鉴

- 九类功能覆盖本地 Agent 产品的核心横切面，适合作为一个足够复杂但可读的验收仓；
- 各能力有清晰模块边界和 deterministic tests；
- Loop、Memory、Graph、Gateway 可以在项目页里分别讲清，不需要从入口开始；
- Voice 明确展示了 VAD-like/ASR/Agent/TTS 串联的实际边界。

## 不要照搬

- 内存 Graph 不等于长时间、分布式、可恢复工作流；
- Gateway 线程隔离不等于 sandbox；
- trusted/local HTTP 不等于完整 Web 安全；
- 当前 Voice 是按段录音 + 本地 ASR + 系统 TTS，不是全双工端到端语音；
- LLM judge 不能作为唯一发布证据。

## 对 Skill / 项目 / CLI 决策的启示

Waku 自己证明复杂运行时需要独立项目和 CLI；它的 Skill 只是工具/知识输入的一部分。对 Repo Teacher 来说，Waku 的角色是 E2E 语料：`repo-teacher report <waku>` 必须产出一份人能直接读懂九功能的 HTML，而不是把分析内核实现成 Waku 专用 Skill。

## 事实、推断与未验证

- **事实**：固定 HEAD 的九类模块、数据流和测试路径存在；Go 原型已对所有列出的源码范围做存在/越界/hash 验证。
- **推断**：九功能足以暴露报告是否仍在“入口/文件平铺”，是合适的首期验收仓。
- **未验证**：本轮不运行 Waku 外部 provider、真实聊天通道、麦克风和 LLM judge；这些属于目标项目运行时测试，不是 Repo Teacher 静态报告门。
