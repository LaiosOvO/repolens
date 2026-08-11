from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _mechanism(feature: Mapping[str, Any]) -> str:
    for tag in _strings(feature.get("technology_tags")):
        if tag.startswith("compatibility-mechanism:"):
            return tag.split(":", 1)[1]
    return ""


def _evidence_ids(feature: Mapping[str, Any]) -> list[str]:
    identifiers = [*_strings(feature.get("evidence_ids")), *_strings(feature.get("test_evidence_ids"))]
    for step in feature.get("steps", []) if isinstance(feature.get("steps"), list) else []:
        if isinstance(step, Mapping):
            identifiers.extend(_strings(step.get("evidence_ids")))
    return list(dict.fromkeys(identifiers))


def _select_evidence(
    identifiers: list[str],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    *markers: str,
) -> list[str]:
    selected = []
    lowered = tuple(marker.lower() for marker in markers)
    for identifier in identifiers:
        evidence = evidence_by_id.get(identifier)
        if not evidence:
            continue
        haystack = "\n".join(
            str(evidence.get(name) or "")
            for name in ("path", "snippet", "kind", "analyzer")
        ).lower()
        if not lowered or any(marker in haystack for marker in lowered):
            selected.append(identifier)
    return selected


def _item(
    *,
    identifier: str,
    category: str,
    title: str,
    why_hard: str,
    runtime_steps: tuple[str, ...],
    invariants: tuple[str, ...],
    naive_failure: str,
    failure_modes: tuple[str, ...],
    tradeoffs: tuple[str, ...],
    reuse_question: str,
    unknowns: tuple[str, ...] = (),
    markers: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": identifier,
        "category": category,
        "title": title,
        "why_hard": why_hard,
        "runtime_steps": list(runtime_steps),
        "invariants": list(invariants),
        "naive_failure": naive_failure,
        "failure_modes": list(failure_modes),
        "tradeoffs": list(tradeoffs),
        "reuse_question": reuse_question,
        "unknowns": list(unknowns),
        "markers": list(markers),
    }


_WAKU_DIFFICULTIES: dict[str, tuple[dict[str, Any], ...]] = {
    "graph": (
        _item(
            identifier="wave-barrier",
            category="concurrency / state",
            title="Wave 是确定性的状态提交屏障，不只是并发批次",
            why_hard="同一波节点要并行提高吞吐，又必须像读取同一版本快照一样观察波前状态；结果还要按稳定顺序提交，才能让 trace 和评测可重复。",
            runtime_steps=("根据依赖与 fired 集合计算本波就绪节点", "为每个节点复制同一份波前 state", "同波节点可并发执行，但先等待整波完成", "按 wave 顺序合并输出，再计算路由和下一波"),
            invariants=("同波节点看不到同波其他节点的写入", "下一波只能读取上一波完整提交后的 state", "合并顺序不能由线程完成顺序决定"),
            naive_failure="为什么不直接用 asyncio.gather：gather 只负责等待，并不提供共享状态快照、确定性提交顺序和冲突检测；若任务直接改同一个 dict，结果会依赖完成时序。",
            failure_modes=("节点偶发读取到另一并发节点的半成品", "相同输入得到不同 trace 或 state", "快节点提前触发下游，破坏 fan-in"),
            tradeoffs=("牺牲跨 wave 的流水线并行", "换取可解释、可重复、可测试的执行边界"),
            reuse_question="你的调度器要的是最大吞吐，还是同一输入可重复的状态提交语义？",
            unknowns=("静态证据不能证明线程调度下的所有时序",),
            markers=("wave", "next_wave", "threadpoolexecutor", "deterministic"),
        ),
        _item(
            identifier="state-collision",
            category="shared state",
            title="并行分支只能写互不相交的 key",
            why_hard="并行节点返回的是待提交补丁；如果两个节点写同一个 key，任何 last-write-wins 都会把业务冲突伪装成线程时序。",
            runtime_steps=("收集整波 results", "记录 key 首个 writer", "发现第二个 writer 写同 key 时立即拒绝", "只有无冲突的 key 才写回共享 state"),
            invariants=("同 wave 的公开写集合必须两两不相交", "顺序执行的下一 wave 可以显式覆盖旧值", "下划线前缀的运行时私有字段不能泄漏到 state"),
            naive_failure="用 dict.update 逐个合并会把业务建模错误降级成静默覆盖；调换线程完成顺序还可能改变最终值。",
            failure_modes=("丢失其中一个分支的写入", "错误只在负载变化时出现", "下游基于被覆盖值做错误路由"),
            tradeoffs=("要求流程设计者提前划分状态所有权", "用显式失败换取结果确定性"),
            reuse_question="你的并行节点是否有明确的状态所有权或 reducer，还是默认 last-write-wins？",
            markers=("graphstatecollision", "collision", "disjoint", "wave_writes"),
        ),
        _item(
            identifier="fan-in-join",
            category="dependency / join",
            title="Gather 不是做计算，而是把多前驱变成一个可见的同步点",
            why_hard="分类和日历查询可以并发，是因为它们读取相同输入、写不同 key；路由却必须同时看到两者的完整结果，所以需要一个依赖汇合点。",
            runtime_steps=("START 同时激活 classify 与 check_calendar", "两个节点在同一 wave 独立写 route/reason 与 calendar", "只有 gather 的全部静态入边都 fired 才进入下一 wave", "gather 完成后 router 才读取已合并 state 并选择 quick/full"),
            invariants=("fan-in 节点必须等待所有声明的前驱", "并行分支不得依赖彼此的同波输出", "router 只能在依赖闭合后的 state 上决策"),
            naive_failure="只在协程层 await 两个任务可以等待结果，但若图里没有显式 join，拓扑、observer 和后续路由都无法表达这个同步边界。",
            failure_modes=("路由在 calendar 尚未写入时提前执行", "新增第三个前驱后忘记更新手写等待逻辑", "可视化图与真实同步行为不一致"),
            tradeoffs=("多一个无业务输出的节点", "换取拓扑可见、可观测、可扩展的 fan-in 合同"),
            reuse_question="你的同步点需要成为图的一等节点，还是只需要函数内部的一次 await？",
            markers=("deps", "fired", "next_wave", "gather", "fan-in"),
        ),
        _item(
            identifier="routing-and-cycles",
            category="control flow / termination",
            title="代码 Router 与双层预算共同约束动态路径",
            why_hard="图允许条件跳转和有意循环，但动态路径不能让模型任意控制，也不能无限运行。",
            runtime_steps=("节点把分类结果写入 state", "纯代码 router 把 label 映射到目标", "跳转目标进入下一 wave", "max_visits 限制单节点循环，max_steps 限制整次运行"),
            invariants=("router label 必须映射到已声明目标", "模型只写数据，代码拥有控制流", "局部与全局预算必须同时生效"),
            naive_failure="把模型输出直接当节点名会让提示词控制拓扑；只设全局 timeout 又无法解释是哪一个循环节点失控。",
            failure_modes=("未知 label 导致路径悬空", "循环耗尽资源", "局部重试吞掉整次任务预算"),
            tradeoffs=("动态性受声明式 targets 约束", "换取可审计路径和确定终止"),
            reuse_question="动态建图是修改下一次运行的 topology，还是允许本次运行中的模型随意新增节点和边？",
            markers=("router", "route", "max_visits", "max_steps", "unknown label"),
        ),
        _item(
            identifier="durability-boundary",
            category="recovery boundary",
            title="它是进程内图执行器，不是可恢复的长期工作流",
            why_hard="state、运行计数、fired 集合和 path 都由当前进程持有；没有 checkpoint 合同就不能从进程崩溃后精确恢复。",
            runtime_steps=("调用方传入内存 state", "一次 run_graph 在当前进程跑到结束", "返回最终 state 与 observer 事件", "未发现把 wave 边界持久化并恢复的证据"),
            invariants=("不能把缺失的持久化能力冒充已经实现", "跨进程恢复需要保存 topology 版本、state、预算和已提交 wave"),
            naive_failure="只把最终 dict 写数据库不能恢复执行中的 wave，也无法判断外部副作用是否已发生。",
            failure_modes=("进程退出后整次运行丢失", "重跑造成工具副作用重复", "代码升级后旧 checkpoint 无法解释"),
            tradeoffs=("实现简单、调试直接", "不承担分布式协调、事务和恢复成本"),
            reuse_question="你的任务是否允许失败后整次重跑？若不允许，checkpoint 应放在哪个提交边界？",
            unknowns=("未发现进程重启恢复测试", "未发现幂等键或外部副作用日志"),
            markers=("run_graph", "state", "graph_end"),
        ),
    ),
    "loop": (
        _item(identifier="tool-protocol-loop", category="protocol state machine", title="模型、工具结果与消息历史必须形成闭合协议", why_hard="每次 tool_use 都要执行并以供应商能理解的 tool_result 形式写回，下一轮才能继续推理。", runtime_steps=("模型生成文本或工具请求", "Registry 执行工具", "结果追加回 messages", "继续迭代直到文本完成"), invariants=("每个工具请求都有对应结果", "工具异常不能破坏消息协议"), naive_failure="只调用工具但不把结果写回，会让模型看不到 observation。", failure_modes=("工具调用悬空", "历史格式被不同供应商拒绝"), tradeoffs=("显式状态机代码较长", "协议边界更容易审计"), reuse_question="你的统一消息模型能否无损表达每家供应商的工具调用？", markers=("tool", "messages", "execute")),
        _item(identifier="loop-budget", category="termination", title="自然结束与硬迭代预算必须同时存在", why_hard="Agent 可以正常给出最终文本，也可能持续请求工具；只有一种停止方式会遗漏另一类情况。", runtime_steps=("每轮增加 iteration", "无工具请求时自然结束", "有工具请求时继续", "达到 max_iterations 时硬停止"), invariants=("任何路径最终都能停止",), naive_failure="只相信模型自己结束可能无限循环。", failure_modes=("工具循环", "成本与延迟失控"), tradeoffs=("预算可能截断可恢复任务", "换取成本上界"), reuse_question="预算耗尽后是失败、部分结果，还是转交人工？", markers=("max_iterations", "iteration", "stop")),
    ),
    "memory": (
        _item(identifier="consolidation-trigger", category="state lifecycle", title="整理触发必须避免每轮重写，也不能永久拖欠", why_hard="长期记忆整理有模型成本，并且会改变后续检索语料。", runtime_steps=("统计未整理聊天", "未达阈值则跳过", "批量提取事实与 episode", "成功后标记已整理"), invariants=("只有成功写入后才能推进 consolidation 水位",), naive_failure="每轮整理成本高，先标记再写入则失败时会丢数据。", failure_modes=("重复整理", "未整理记录被跳过"), tradeoffs=("批处理增加新记忆可见延迟", "换取更低成本"), reuse_question="你的水位线在事务中何时推进？", markers=("consolid", "unconsolidated", "chat_log")),
        _item(identifier="memory-truth-boundary", category="knowledge quality", title="模型提炼结果不是不可变事实", why_hard="摘要会丢上下文，事实还可能互相冲突或过期。", runtime_steps=("读取原始对话", "模型产出结构化候选", "写入事实/episode store", "后续检索消费"), invariants=("保留原始来源与可撤销路径",), naive_failure="直接覆盖旧事实会丢失冲突和来源。", failure_modes=("错误记忆长期放大", "隐私数据无法删除"), tradeoffs=("保留 lineage 增加存储与治理成本",), reuse_question="每条记忆能否回到来源、版本和删除策略？", markers=("fact", "episode", "json")),
    ),
    "gateway": (
        _item(identifier="gateway-reconcile", category="lifecycle", title="配置变化要变成可回滚的生命周期协调", why_hard="启动新通道前通常要停旧实例；新实例失败时不能让服务永久掉线。", runtime_steps=("计算配置指纹", "判断是否需要重建", "停止旧实例并启动新实例", "失败时恢复旧环境/实例并记录健康"), invariants=("同一通道只有一个 owner", "失败后状态与健康信息一致"), naive_failure="保存配置后直接 start 会产生重复连接或僵尸实例。", failure_modes=("重复消费消息", "配置失败导致通道全停"), tradeoffs=("协调器复杂度上升", "换取统一生命周期"), reuse_question="配置更新失败时，你能恢复旧连接吗？", markers=("reconcile", "fingerprint", "restore")),
        _item(identifier="gateway-delivery", category="delivery semantics", title="通道收发与 Agent 执行的背压/幂等边界", why_hard="外部平台可能重投、断线和限流，而 Agent 回合可能很慢。", runtime_steps=("接收外部消息", "映射 session", "串行或排队执行回合", "发送结果并更新健康"), invariants=("同一消息不应重复产生副作用",), naive_failure="直接在线程里调用 Agent 会把背压留给平台连接。", failure_modes=("重复投递", "长任务阻塞后续消息"), tradeoffs=("当前轻量进程内实现", "生产需队列和幂等存储"), reuse_question="消息唯一键、重试和背压由哪一层负责？", markers=("gateway", "status", "stop")),
    ),
    "voice": (
        _item(identifier="speech-segmentation", category="audio state machine", title="何时开始、何时结束一轮语音决定整条体验", why_hard="能量阈值、静音窗口、最大录音时间和唤醒词共同决定切段。", runtime_steps=("监听音频块", "检测语音起点", "累计到静音或上限", "ASR 后进入 Agent"), invariants=("一个 turn 只提交一次完整音频",), naive_failure="固定录音时长会截断或产生长空白。", failure_modes=("误唤醒", "截断尾音", "环境噪声持续占用"), tradeoffs=("简单能量门低延迟但鲁棒性有限",), reuse_question="是否需要独立 VAD、端点检测和噪声自适应？", markers=("silence", "threshold", "record")),
        _item(identifier="voice-duplex-gap", category="real-time boundary", title="ASR→Agent→TTS 串联不等于全双工", why_hard="真正实时对话还需要边说边识别、可打断播放、回声消除和并行会话状态。", runtime_steps=("录完一段", "完整转写", "等待 Agent 回复", "完整朗读"), invariants=("不能把分段串联称为全双工",), naive_failure="只把四个模块连起来无法处理用户在 TTS 播放中插话。", failure_modes=("无法打断", "扬声器回声再次触发 ASR"), tradeoffs=("串联容易本地运行", "交互延迟更高"), reuse_question="你的首版目标是可用语音入口，还是可打断的实时会话？", markers=("transcribe", "speak", "wake")),
    ),
    "tools": (
        _item(identifier="tool-contract", category="schema / dispatch", title="模型看见的 schema 与实际 callable 必须一致", why_hard="名称、参数类型和错误语义任何一个漂移都会在运行时才暴露。", runtime_steps=("注册 Tool", "导出模型 schema", "按 name 查找 callable", "执行并把结果转成文本 observation"), invariants=("schema 与 callable 参数合同一致",), naive_failure="只维护 prompt 中的工具说明会和代码实现漂移。", failure_modes=("参数校验失败", "模型调用不存在工具"), tradeoffs=("最小 registry 清晰", "复杂类型和版本治理需增强"), reuse_question="schema 是否由实现生成并经过版本校验？", markers=("input_schema", "register", "execute")),
        _item(identifier="tool-safety", category="trust boundary", title="错误隔离不等于权限隔离", why_hard="捕获异常只能保护 Agent loop，不能限制文件、网络、CPU 或凭证访问。", runtime_steps=("收到模型调用", "当前进程执行 Python callable", "异常转成模型可见文本", "模型可能决定重试"), invariants=("业务异常不应杀死循环", "安全边界必须在进程/权限层另行实现"), naive_failure="把 try/except 当成沙箱会允许工具继承宿主全部权限。", failure_modes=("越权文件访问", "无限耗时或副作用重复"), tradeoffs=("进程内调用简单快速", "安全与资源隔离不足"), reuse_question="工具的审批、超时、沙箱和幂等分别由谁负责？", markers=("except", "error", "notify")),
    ),
    "providers": (
        _item(identifier="provider-normalization", category="protocol adapter", title="统一消息表面要保留供应商差异", why_hard="文本块、工具调用、流式事件和错误类型在不同 wire protocol 中不完全同构。", runtime_steps=("选择 provider", "规范化输入 messages/tools", "调用原生或兼容客户端", "把响应重新映射为循环可消费形态"), invariants=("工具调用 ID 与结果必须可往返",), naive_failure="只替换 base_url 会把协议差异推迟到运行时。", failure_modes=("tool result 对不上 call id", "流式块丢失"), tradeoffs=("薄适配易维护", "只能覆盖公共子集"), reuse_question="你的统一协议允许哪些有损降级？", markers=("provider", "anthropic", "openai")),
        _item(identifier="provider-configuration", category="configuration ownership", title="全局模型配置不能跨供应商泄漏", why_hard="切换 provider 时继承旧模型 ID、base URL 或 key 会产生隐蔽的 400/鉴权错误。", runtime_steps=("读取目标 provider 配置", "识别继承的跨供应商值", "回退到该 provider 默认模型", "构建带 timeout 的客户端"), invariants=("模型名属于当前 provider", "凭证与 endpoint 不串用"), naive_failure="把 WAKU_MODEL 当作所有 provider 的通用默认值会带入不兼容模型。", failure_modes=("model not found", "凭证发往错误 endpoint"), tradeoffs=("更多归属判断", "换取安全切换"), reuse_question="配置覆盖值有来源/owner 信息吗？", markers=("belongs", "base_url", "api_key")),
    ),
    "dashboard": (
        _item(identifier="observer-stream", category="observability", title="UI 事件必须来自运行时同一事实源", why_hard="聊天、工具、Graph 和 Gateway 都会产事件；手工拼接视图容易和真实路径漂移。", runtime_steps=("observer 接收运行事件", "转换为 SSE/页面事件", "前端按 kind 更新 turn/card", "完成事件封口"), invariants=("终态事件只发一次", "页面不能伪造未发生阶段"), naive_failure="结束后再从日志猜执行过程会遗漏实时顺序和中间失败。", failure_modes=("页面卡在 pending", "事件顺序错乱"), tradeoffs=("事件 schema 成为稳定接口",), reuse_question="运行时、存储和 UI 是否共享同一事件合同？", markers=("observer", "emit", "stream")),
        _item(identifier="dashboard-boundary", category="local service security", title="本地 Dashboard 仍然是权限与并发边界", why_hard="它能读写记忆、触发工具、切换 provider 并暴露本地路径。", runtime_steps=("HTTP handler 接收请求", "校验动作/路径", "调用共享 Agent 或 store", "返回结构化错误"), invariants=("路径不能逃逸工作目录", "写操作需要明确授权"), naive_failure="把 localhost 当成身份认证会忽略恶意网页和多用户机器。", failure_modes=("跨站请求触发本地动作", "多个请求竞争共享 Agent"), tradeoffs=("零部署体验好", "生产需认证和租户隔离"), reuse_question="谁可以访问本地端口，哪些操作需要二次确认？", markers=("handler", "do_post", "lock")),
    ),
    "eval": (
        _item(identifier="gate-composition", category="quality gate", title="确定性检查与模型裁判不能混成一个分数", why_hard="单元/协议失败应硬阻断，主观质量评估则有波动和缺 key 的降级路径。", runtime_steps=("运行 deterministic suites", "全部通过后再运行 judge", "持久化各自结果", "任一硬门失败则拒绝发布"), invariants=("确定性失败不能被平均分掩盖",), naive_failure="加权平均会让严重回归被高主观分抵消。", failure_modes=("回归仍放行", "无 API key 时误报成功"), tradeoffs=("多门输出更复杂", "决策语义清晰"), reuse_question="哪些指标必须 100% 通过，哪些允许统计波动？", markers=("deterministic", "judge", "gate")),
        _item(identifier="eval-reproducibility", category="evaluation lineage", title="发布判定必须能回到版本、输入和裁判配置", why_hard="模型、prompt、测试集和阈值任一变化都会改变结果。", runtime_steps=("记录当前 suite 和 provider", "执行并保存报告", "把结果附到发布决策", "后续对比历史"), invariants=("同一判定有完整 lineage",), naive_failure="只打印 GATE OPEN 无法解释后来为什么放行。", failure_modes=("无法复盘", "阈值漂移"), tradeoffs=("保存更多元数据",), reuse_question="一次 gate 结果能否重放到相同模型、数据和代码版本？", markers=("report", "eval_report", "provider")),
    ),
}


def discover_difficulty_map(
    feature: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Return evidence-bounded implementation difficulties for one feature.

    The rules deliberately do not use LOC or file count.  Repository-specific
    compatibility profiles name semantic mechanisms, while evidence matching
    decides whether each explanation is confirmed or remains an inference.
    """

    mechanism = _mechanism(feature)
    templates = _WAKU_DIFFICULTIES.get(mechanism, ())
    identifiers = _evidence_ids(feature)
    items: list[dict[str, Any]] = []
    for template in templates:
        item = {key: value for key, value in template.items() if key != "markers"}
        matched = _select_evidence(
            identifiers,
            evidence_by_id,
            *[str(marker) for marker in template.get("markers", [])],
        )
        if not matched:
            matched = [identifier for identifier in identifiers if identifier in evidence_by_id][:2]
        item["evidence_ids"] = matched
        item["confidence"] = "confirmed-static" if matched else "inferred-gap"
        if not matched:
            item["unknowns"] = [
                *item.get("unknowns", []),
                "当前索引没有绑定到该难点的独立源码片段；保留为待验证候选。",
            ]
        items.append(item)

    return {
        "method": (
            "execution-flow signals + state/control/failure invariants + evidence gate; "
            "LLM explanation is downstream only"
        ),
        "reference_adoption": [
            "GitNexus / CodeBoarding：结构、执行流、分支与影响候选",
            "Serena：符号、引用和测试的精确定位",
            "PocketFlow / DeepWiki：总分总教学与逐层下钻",
        ],
        "summary": (
            f"{len(items)} 个机制难点按运行过程、不变量、失败方式和复用问题组织；"
            "没有证据的项明确标为推断，不用代码行数冒充难度。"
        ),
        "items": items,
        "unknowns": [
            "静态索引不证明真实线程时序、性能或生产可用性。",
            "没有运行 trace、历史或恢复测试的结论不能升级为高风险已确认事实。",
        ],
    }
