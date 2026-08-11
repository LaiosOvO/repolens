"""Source-audited implementation notes for the bundled reference projects.

The catalog deliberately stores descriptions and file pointers, not copied source.
Every consumer must intersect ``source_paths`` with the paths in the generated
repository index before presenting an entry as evidence.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any
from urllib.parse import urlsplit


SCORE_DIMENSIONS = (
    "semantic_precision",
    "evidence_traceability",
    "tutorial_quality",
    "incremental_efficiency",
    "visualization",
    "production_readiness",
    "reuse_value",
)

CATALOG_REVISION = "2026-08-10.3"
SCORE_RUBRIC_LEVELS = (0, 25, 50, 75, 100)
SCORE_RUBRIC = {
    0: "未发现实现，或源码明确显示不具备该能力",
    25: "只有相邻机制/实验实现，不能承担该能力",
    50: "存在可运行的基础链路，但覆盖、可靠性或复用边界明显不足",
    75: "主要链路完整，并有结构化契约或测试支撑；仍需场景 PoC",
    100: "在固定源码快照中形成完整生产链路；仍不代表性能 benchmark",
}


def _scores(*values: int) -> dict[str, int]:
    if len(values) != len(SCORE_DIMENSIONS):
        raise ValueError("one score is required for every comparison dimension")
    # Historical reviews used fine-grained integers without a repeatable
    # measurement method.  Quantising them onto the published rubric prevents
    # a reviewer opinion such as 88 vs 87 being presented as benchmark data.
    def bucket(value: int) -> int:
        if not 0 <= value <= 100:
            raise ValueError("review signal must be between 0 and 100")
        return min(SCORE_RUBRIC_LEVELS, key=lambda level: (abs(level - value), -level))

    return dict(zip(SCORE_DIMENSIONS, (bucket(value) for value in values), strict=True))


def _entry(
    summary: str,
    approach: str,
    data_flow: tuple[str, ...],
    technology_tags: tuple[str, ...],
    source_paths: tuple[str, ...],
    strengths: tuple[str, ...],
    limitations: tuple[str, ...],
    reuse_verdict: str,
    dimension_scores: dict[str, int],
) -> dict[str, Any]:
    return {
        "summary": summary,
        "approach": approach,
        "data_flow": list(data_flow),
        "technology_tags": list(technology_tags),
        "source_paths": list(source_paths),
        "strengths": list(strengths),
        "limitations": list(limitations),
        "reuse_verdict": reuse_verdict,
        "dimension_scores": dimension_scores,
        "source": "curated-source-audit",
    }


# Scores are comparative implementation-readiness signals (0-100), not project
# popularity scores. A low score can therefore be the most useful result: it says
# that the project is not the right source for that capability.
REFERENCE_CATALOG: dict[str, dict[str, dict[str, Any]]] = {
    "sourcebridge": {
        "code-parsing": _entry(
            "用 Go 驱动 Tree-sitter，为多语言源码提取符号、导入、调用点和注释，并把单文件解析错误降级隔离。",
            "语言注册表提供 grammar 与查询；Parser 对每个文件运行 query，Indexer 汇总 FileResult。",
            ("识别语言配置", "Tree-sitter 构建语法树", "查询符号/导入/调用点", "组装带位置的 FileResult", "写入索引"),
            ("Go", "Tree-sitter", "多语言 query", "位置级符号"),
            ("internal/indexer/languages.go", "internal/indexer/parser.go", "internal/indexer/indexer.go", "internal/indexer/types.go"),
            ("静态证据包含文件与行号", "坏文件不会中止整库解析", "解析层和索引层边界清晰"),
            ("Tree-sitter 调用解析不等于类型解析", "cgo grammar 崩溃无法由 Go recover"),
            "解析内核很适合作为 Go 方案基准；复用前应先确认目标语言 query 覆盖率和许可证边界。",
            _scores(91, 89, 50, 72, 50, 86, 78),
        ),
        "code-graph": _entry(
            "把索引器产出的符号、导入和调用关系写入可查询图，并提供执行路径、影响分析和跨仓关联。",
            "解析结果先标准化为图实体/边，再由 graph store 提供过滤、遍历和路径查询。",
            ("FileResult", "符号/调用边归一化", "Graph Store", "过滤或路径遍历", "影响与理解查询"),
            ("Go", "属性图", "调用边", "路径查询"),
            (
                "internal/indexer/types.go",
                "internal/graph/store.go",
                "internal/db/store_federation.go",
                "internal/graph/execution_path.go",
                "internal/graph/impact.go",
                "internal/graph/federation.go",
            ),
            ("从代码位置一直保留到图查询", "同时覆盖执行路径和变更影响", "有较完整的测试面"),
            (
                "跨仓 federation 只在 SurrealDB store 实现；in-memory Store 明确返回 not supported",
                "存储与完整服务域耦合较深",
                "抽离图层需要重建实体契约",
            ),
            "适合作为图数据契约和查询能力的设计基准；不建议直接搬运整套服务层。",
            _scores(88, 88, 48, 74, 61, 85, 73),
        ),
        "component-discovery": _entry(
            "以静态图为事实底座，再用分层/长上下文 comprehension 策略生成子系统与架构理解。",
            "代码语料被分块成树，子摘要逐层汇总，最终产出可绑定图实体的架构理解。",
            ("代码图与语料", "构建层次树", "叶子摘要", "递归聚合", "子系统/理解结果"),
            ("Python", "hierarchical summarization", "长上下文策略", "静态图 grounding"),
            ("workers/comprehension/corpus.py", "workers/comprehension/tree.py", "workers/comprehension/hierarchical.py", "internal/graph/understanding.go"),
            ("适合大仓分层处理", "组件说明可落回静态图事实", "策略可切换"),
            ("组件命名仍依赖模型", "质量依赖分块和提示词"),
            "可参考“静态图先行、LLM 后置”的边界和分层摘要流程；提示词需针对本产品重写。",
            _scores(78, 82, 70, 67, 55, 80, 78),
        ),
        "tutorial-generation": _entry(
            "知识 worker 将同一代码事实组织为 Cliff Notes、学习路线、系统说明和工作流故事等不同教学产品。",
            "检索共享证据快照，按产物类型生成结构化内容，再执行质量阈值与持久化。",
            ("知识任务", "检索代码快照", "按产物模板生成", "证据/质量 gate", "存储与流式返回"),
            ("Python", "结构化 LLM 输出", "多种教学模板", "流式任务"),
            (
                "workers/knowledge/retrieval.py",
                "workers/knowledge/cliff_notes.py",
                "workers/knowledge/learning_path.py",
                "workers/knowledge/explain_system.py",
                "workers/knowledge/workflow_story.py",
            ),
            ("产物类型完整", "复用统一检索与证据层", "有质量阈值和任务状态"),
            ("实现依赖 SourceBridge 的内部数据契约", "生成质量仍受模型影响"),
            "最适合参考教学产物分层与质量门；应复用产品思路而非耦合内部服务代码。",
            _scores(76, 91, 91, 75, 63, 86, 82),
        ),
        "evidence-grounding": _entry(
            "提供独立证据提取与质量 gate，校验文件/行号引用，过滤空泛措辞和无证据的技术声明。",
            "从结构化字段和正文抽取引用，验证路径与行号，按相关性降权并拒绝无支持的 claim。",
            ("生成内容", "提取文件/行号/符号引用", "路径合法性检查", "相关性与 claim gate", "通过或降级"),
            ("Python", "EvidenceRef", "质量 gate", "claim validation"),
            ("workers/knowledge/types.py", "workers/knowledge/evidence.py", "workers/knowledge/thresholds.py", "workers/knowledge/parse_utils.py"),
            ("证据不是提示词约定而是独立模块", "覆盖行号、路径、空泛话术和推测性表述", "便于测试"),
            ("不能证明引用片段与自然语言结论语义完全一致", "规则表需要持续维护"),
            "这是证据层最强基准之一；建议干净实现同等 gate，并加入 snippet hash 和失效检测。",
            _scores(84, 96, 75, 72, 45, 90, 90),
        ),
        "incremental-update": _entry(
            "ChangeWatch 捕捉变化，Living Wiki orchestrator 用 fingerprint、watermark 与 staleness 选择性重建页面。",
            "变更事件被路由到受影响符号/页面，比较指纹和水位后仅执行增量任务，失败可重试恢复。",
            ("代码变更", "ChangeWatch 路由", "影响范围/指纹比较", "页面失效判定", "增量重建与 watermark"),
            ("Go", "fingerprint", "watermark", "staleness", "retry/resume"),
            ("internal/changewatch/watcher.go", "internal/changewatch/router.go", "internal/livingwiki/orchestrator/fingerprint.go", "internal/livingwiki/orchestrator/incremental.go", "internal/livingwiki/orchestrator/staleness.go"),
            ("覆盖检测、计划、执行和恢复闭环", "页面级新鲜度模型明确", "生产运维考虑充分"),
            ("系统边界较大，无法作为轻量库直接抽离", "依赖内部任务和存储契约"),
            "最适合参考生产级增量状态机；MVP 应先复用 fingerprint/watermark 思路，再逐步扩展事件系统。",
            _scores(77, 87, 70, 95, 53, 93, 84),
        ),
        "codemap-visualization": _entry(
            "分别生成代码 Tour 和架构 Mermaid，并在前端提供依赖图和架构视图。",
            "代码/图证据先转为有序 stops 或 diagram AST，验证 Mermaid 后由前端呈现。",
            ("代码图证据", "生成 Tour stops/diagram", "结构与 Mermaid 校验", "持久化 artifact", "前端交互展示"),
            ("Python", "Go", "Mermaid", "React", "Code Tour"),
            ("workers/knowledge/code_tour.py", "workers/knowledge/architecture_diagram.py", "workers/common/mermaid/validator.py", "web/src/components/architecture/ArchitectureDiagram.tsx"),
            ("Tour 和图是两类互补视图", "有 Mermaid 校验器", "引用可回到代码"),
            ("前后端链路复杂", "图布局仍受 Mermaid 与节点规模限制"),
            "可复用“步骤 Tour + 关系图”双视图产品模型；渲染层可独立重写。",
            _scores(75, 91, 82, 69, 90, 84, 84),
        ),
        "agent-workflow": _entry(
            "知识任务通过 gRPC servicer、job state 与流式事件编排，LLM orchestrator 负责 provider、重试和熔断。",
            "请求创建任务，worker 选择能力并推进状态，结构化事件流回客户端，失败由重试/熔断控制。",
            ("知识请求", "能力选择与 job state", "LLM orchestration", "质量 gate", "流式事件/持久化"),
            ("Python", "Go", "gRPC", "job state", "retry/circuit breaker"),
            ("workers/knowledge/servicer.py", "workers/knowledge/job_state.py", "workers/knowledge/streaming.py", "internal/llm/orchestrator/orchestrator.go"),
            ("任务状态和流式协议清晰", "包含超时、重试、熔断等生产机制", "产物类型可扩展"),
            ("不是轻量通用 Agent SDK", "与 SourceBridge 领域模型紧密耦合"),
            "参考其任务生命周期与可靠性机制，不直接把整套 orchestrator 作为动态工作流内核。",
            _scores(74, 85, 76, 81, 59, 94, 80),
        ),
    },
    "pocketflow-code2tutorial": {
        "code-parsing": _entry(
            "没有 AST、Tree-sitter 或 LSP 解析层；只按 include/exclude 规则抓取文本并整体交给 LLM。",
            "本地/GitHub crawler 读取文本文件，文件路径和内容成为后续提示词上下文。",
            ("仓库地址/目录", "glob 过滤", "读取文本", "文件序号+内容", "LLM 上下文"),
            ("Python", "文本抓取", "glob"),
            ("utils/crawl_local_files.py", "utils/crawl_github_files.py", "nodes.py"),
            ("实现简单、语言无关", "适合小仓快速试验"),
            ("没有符号、引用和调用精度", "上下文规模随仓库线性增长"),
            "不要把它作为生产索引器；仅参考输入过滤和快速 fallback。",
            _scores(18, 24, 65, 20, 24, 35, 38),
        ),
        "code-graph": _entry(
            "没有源码级调用图；AnalyzeRelationships 让 LLM 在已识别抽象之间生成带权关系。",
            "抽象列表和相关文件片段进入提示词，模型输出关系三元组与整体摘要。",
            ("抽象+文件片段", "LLM 推断关系", "YAML 校验", "抽象关系图"),
            ("Python", "LLM", "YAML", "概念关系"),
            ("nodes.py", "flow.py"),
            ("能生成适合教学的高层关系", "流程直观"),
            ("关系不是静态分析事实", "没有行号级调用证据"),
            "只可作为高层叙事关系的候选层；不能替代确定性代码图。",
            _scores(25, 28, 72, 18, 38, 31, 42),
        ),
        "component-discovery": _entry(
            "IdentifyAbstractions 用一次 LLM 调用从全仓文本中选出 5-N 个核心抽象，并绑定文件序号。",
            "拼接文件上下文，要求模型输出 YAML 抽象列表，再严格校验字段和文件序号。",
            ("全仓文本", "LLM 识别核心抽象", "YAML 解析", "文件序号校验", "抽象列表"),
            ("Python", "LLM", "YAML schema-by-code", "文件级 grounding"),
            ("nodes.py", "utils/call_llm.py"),
            ("产品意图非常清楚", "输出有结构校验", "抽象直接服务教学章节"),
            ("一次性塞入全仓，难以扩到大仓", "文件绑定由模型给出且无符号证据"),
            "适合参考“核心抽象”输出契约；生产版应改为图候选+分层模型判定。",
            _scores(42, 45, 85, 16, 35, 39, 66),
        ),
        "tutorial-generation": _entry(
            "用六步 PocketFlow 把抓仓、抽象识别、关系分析、章节排序、并行写章和合并串成完整教程流水线。",
            "固定 DAG 将共享状态逐步丰富；WriteChapters 以 BatchNode 并行生成，最后合并 Markdown。",
            ("FetchRepo", "IdentifyAbstractions", "AnalyzeRelationships", "OrderChapters", "WriteChapters", "CombineTutorial"),
            ("Python", "PocketFlow", "BatchNode", "LLM", "Markdown"),
            ("flow.py", "nodes.py", "main.py"),
            ("总分总教学结构清晰", "工作流短小易懂", "支持章节批处理和多语言"),
            ("缺少可靠源码证据和增量更新", "全量提示词不适合大型仓库"),
            "最值得复用的是六阶段教学流程与章节结构；索引、证据和增量必须由本产品补齐。",
            _scores(38, 38, 92, 18, 38, 44, 80),
        ),
        "evidence-grounding": _entry(
            "以文件序号约束抽象和章节引用，但没有行号、snippet hash 或独立事实校验器。",
            "crawler 分配文件序号，模型返回序号，Python 验证序号范围后取回对应全文。",
            ("文件列表", "分配序号", "LLM 返回 file_indices", "范围校验", "取回文件内容"),
            ("Python", "文件索引", "YAML validation"),
            ("nodes.py", "utils/crawl_local_files.py"),
            ("至少防止引用不存在的文件", "校验逻辑容易复用"),
            ("无法定位行和符号", "无法判断文字 claim 是否被片段支持"),
            "仅把文件序号校验当作最低门槛；生产证据层需要独立实现。",
            _scores(22, 34, 68, 15, 25, 35, 42),
        ),
        "incremental-update": _entry(
            "没有仓库指纹、diff 或章节失效模型；每次运行重新抓取并生成。",
            "CLI 输入触发完整固定流程，LLM 调用层可缓存相同提示词，但不是代码增量分析。",
            ("CLI 请求", "全量抓仓", "可选 LLM prompt cache", "全量生成"),
            ("Python", "prompt cache"),
            ("main.py", "utils/call_llm.py", "flow.py"),
            ("缓存可降低完全相同请求成本",),
            ("不识别文件变更", "不能复用未失效章节", "没有状态迁移"),
            "不作为增量实现参考；只保留 prompt cache 作为二级优化。",
            _scores(12, 22, 61, 12, 20, 25, 24),
        ),
        "codemap-visualization": _entry(
            "输出教程中的 Mermaid 概念关系图，但没有可交互的符号级 Codemap 或 Code Tour。",
            "LLM 关系数据被章节写作提示词转成 Mermaid，最终嵌入 Markdown。",
            ("抽象关系", "章节提示词", "Mermaid 文本", "Markdown 教程"),
            ("Mermaid", "Markdown", "LLM"),
            ("nodes.py", "flow.py"),
            ("低成本获得教学概念图", "静态文档易分发"),
            ("无图 schema 和独立验证", "不能跳转源码", "不是交互式代码图"),
            "可参考教程内概念图的呈现，不作为 Codemap 数据与交互实现。",
            _scores(24, 29, 78, 14, 48, 30, 46),
        ),
        "agent-workflow": _entry(
            "以 PocketFlow 的 Node/BatchNode 和共享字典实现固定 DAG，而非按需求动态设计 Agent 团队。",
            "节点 prep/exec/post 读取并更新 shared state，重试参数包裹 LLM 节点，边定义固定顺序。",
            ("共享状态", "Node prep", "Node exec+retry", "Node post", "下一节点/批节点"),
            ("PocketFlow", "Node", "BatchNode", "shared state"),
            ("flow.py", "nodes.py"),
            ("编排语义极简", "节点易测试和替换", "批处理章节天然并行"),
            ("拓扑固定", "没有动态 planner、预算和持久化 checkpoint"),
            "可复用为教学生成子流程，不适合直接承担动态多 Agent 控制面。",
            _scores(30, 35, 83, 20, 25, 43, 61),
        ),
    },
    "openwiki": {
        "code-parsing": _entry(
            "没有通用 AST/LSP 索引器；通过 Deep Agents 的文件搜索/读取工具让 Agent 直接调查仓库。",
            "code-mode 配置仓库后端，Agent 按提示执行搜索与读取，结果进入对话上下文。",
            ("仓库后端", "Agent search/read tools", "按需读取实现与测试", "上下文证据"),
            ("TypeScript", "Deep Agents", "按需检索"),
            ("src/ingestion/code-mode.ts", "src/agent/prompt.ts", "src/agent/index.ts"),
            ("按问题读取，避免预索引全部内容", "Agent 能沿调用链自主深挖"),
            ("缺少稳定符号表和调用边", "同一仓库不同运行可能得到不同覆盖"),
            "适合作为 Agent 调研层，不作为底层代码索引器。",
            _scores(30, 53, 76, 44, 42, 69, 52),
        ),
        "code-graph": _entry(
            "仓库模式不构建源码调用图；visualize 模块把文档/知识条目关系转换成可浏览图。",
            "Wiki/OKF 链接和元数据被读取为节点与边，再送入本地可视化页面。",
            ("Wiki 页面与 OKF 元数据", "解析链接/关系", "构建可视化 graph", "浏览器展示"),
            ("TypeScript", "OKF", "文档图"),
            ("src/okf/frontmatter.ts", "src/visualize/graph.ts", "src/visualize/client.ts"),
            ("知识图和文档格式一体化", "图数据容易解释"),
            ("不是源码调用图", "精度取决于生成文档中的链接"),
            "可参考知识文档图，不应用它替换静态代码图。",
            _scores(24, 46, 71, 42, 68, 61, 48),
        ),
        "component-discovery": _entry(
            "主 Agent 先深度调查仓库并拟定 Wiki skeleton，再由独立 skeleton critic 对照源码和测试查漏；复审次数由 prompt 约束，不是 runtime 状态机保证。",
            "主 Agent 建立架构清单，critic 独立映射仓库后比较 skeleton；prompt 要求初审后最多再调用一次，运行时没有强制计数器。",
            ("Agent 独立调研", "生成 Wiki skeleton", "critic 重新映射仓库", "差距清单", "修订/通过"),
            ("Deep Agents", "critic subagent", "repository skeleton", "evidence-backed review"),
            ("src/agent/prompts/code.ts", "src/agent/skeleton_critic.ts", "src/agent/index.ts"),
            ("用独立批评者降低漏项", "强调跨边界流程和测试证据", "输出天然适合 Wiki 信息架构"),
            ("critic 调用次数是 prompt-enforced 而非 runtime-enforced", "组件识别主要依靠 Agent 推理", "没有稳定聚类或可重复图算法"),
            "非常适合参考“先盘点、后独立审查”的产品工作流；底层候选仍需静态索引支持。",
            _scores(52, 71, 91, 48, 43, 75, 78),
        ),
        "tutorial-generation": _entry(
            "围绕 Wiki skeleton 分页写作，使用 OKF frontmatter、目录索引和链接校验保持知识库可导航。",
            "仓库调研形成 skeleton，Agent 分页写作，middleware 规范元数据并同步目录，最后校验内部链接。",
            ("仓库调查", "Wiki skeleton", "概念页写作", "OKF normalization/index sync", "链接校验"),
            ("TypeScript", "Deep Agents", "Markdown", "OKF"),
            ("src/agent/prompts/code.ts", "src/agent/okf-middleware.ts", "src/okf/index-sync.ts", "src/agent/wiki-link-validator.ts"),
            ("知识库是可维护文件而非一次性报告", "信息架构与写作分离", "索引和链接自动维护"),
            ("不是循序渐进的代码教程", "页面内容质量依赖 Agent 调研"),
            "最适合参考长期 Wiki 的内容生命周期；教学章节还需额外的阅读路线和步骤模型。",
            _scores(45, 70, 88, 64, 67, 79, 83),
        ),
        "evidence-grounding": _entry(
            "通过强约束仓库调研提示、独立 skeleton critic、Wiki 链接校验和 QA subagents 做过程级事实约束。",
            "Agent 必须读取实现和测试，critic 要求 evidence-backed gap，link validator 再检查文档引用目标。",
            ("源码/测试读取", "证据约束写作", "独立 critic", "链接 validator", "QA subagents"),
            ("Deep Agents", "critic", "link validation", "QA subagents"),
            ("src/agent/skeleton_critic.ts", "src/agent/wiki-link-validator.ts", "src/agent/wiki_qa_subagents.ts", "src/agent/prompts/code.ts"),
            ("多阶段防止覆盖缺口", "测试被明确作为证据", "验证器职责独立"),
            ("没有统一行号/snippet evidence schema", "过程合规不保证每个 claim 可机器验证"),
            "可参考多 Agent 审查 gate；需要补上结构化 EvidenceRef 才能用于可点击技术选型证据。",
            _scores(47, 72, 84, 55, 50, 75, 73),
        ),
        "incremental-update": _entry(
            "以 .last-update 元数据、update 命令、OKF normalization 与幂等 index sync 维护已有 Wiki。",
            "读取上次更新状态和当前仓库，Agent 只修改需要变化的页面，middleware 再归一化和重建目录。",
            ("上次更新时间/现有 Wiki", "update Agent", "编辑受影响页面", "OKF normalization", "幂等目录同步"),
            ("TypeScript", "Git workflow", "OKF", "idempotent index sync"),
            ("openwiki/.last-update.json", "src/agent/index.ts", "src/agent/okf-middleware.ts", "src/okf/index-sync.ts"),
            ("直接维护 Markdown 知识库", "索引同步避免无意义写入", "适合 CI 定期更新"),
            ("没有源码级 fingerprint 依赖图", "页面失效范围主要由 Agent 判断"),
            "适合参考 Wiki 文件更新和 CI 交付；受影响分析应换成确定性指纹/依赖模型。",
            _scores(32, 55, 78, 60, 54, 72, 67),
        ),
        "codemap-visualization": _entry(
            "用 Wiki/OKF 知识关系生成本地交互图，并提供 Mermaid 解析与校验技能。",
            "文档关系转换为 graph 数据，visualize server 提供页面；Mermaid fence 独立清洗并校验。",
            ("Wiki/OKF", "关系图构建", "本地 visualize server", "浏览器交互", "Mermaid 校验"),
            ("TypeScript", "browser graph", "Mermaid", "OKF"),
            ("src/visualize/graph.ts", "src/visualize/server.ts", "src/mermaid/wiki.ts", "src/mermaid/validate.ts"),
            ("图和本地知识库天然连接", "Mermaid 有独立验证", "可交互浏览"),
            ("节点是知识条目而非代码符号", "没有调用路径 Tour"),
            "可参考知识图 UI 和 Mermaid 管线；符号级 Codemap 需接入本产品代码图。",
            _scores(28, 53, 77, 52, 79, 70, 65),
        ),
        "agent-workflow": _entry(
            "基于 Deep Agents 构建主 Agent、条件子 Agent、middleware、checkpoint 与 connector skills 的长任务工作流。",
            "命令选择输出模式和技能，创建 Agent 运行时；middleware 处理上下文/文档，critic 与 QA 子 Agent 按阶段介入。",
            ("CLI command", "解析 mode/skills/connectors", "创建主 Agent", "middleware+subagents", "checkpoint/输出"),
            ("TypeScript", "Deep Agents", "skills", "subagents", "middleware"),
            ("src/agent/index.ts", "src/agent/skills.ts", "src/agent/skeleton_critic.ts", "src/connectors/registry.ts"),
            ("Skill 与 connector 扩展面清晰", "支持长上下文治理和子 Agent 审查", "生产 CLI 体验完整"),
            ("核心依赖 Deep Agents", "工作流主要由提示词和命令模式约束"),
            "动态工作流与 Skill 选择的重要参考；底层执行协议应抽象，避免锁死单一 Agent SDK。",
            _scores(43, 64, 85, 66, 58, 84, 84),
        ),
    },
    "understand-anything": {
        "code-parsing": _entry(
            "插件化解析层以 Tree-sitter 为主，为多语言配置注册 extractor，并为配置/文档语言提供专用 parser。",
            "language registry 选择配置和 grammar，Tree-sitter plugin 调 extractor，统一输出文件结构与关系。",
            ("检测语言", "加载 language/plugin", "Tree-sitter parse", "extractor 提取结构", "归一化结果"),
            ("TypeScript", "Tree-sitter", "plugin registry", "多语言 extractors"),
            ("understand-anything-plugin/packages/core/src/languages/language-registry.ts", "understand-anything-plugin/packages/core/src/plugins/tree-sitter-plugin.ts", "understand-anything-plugin/packages/core/src/plugins/extractors/base-extractor.ts", "understand-anything-plugin/packages/core/src/plugins/registry.ts"),
            ("语言与 parser 可扩展", "大量语言 extractor 和测试", "代码与非代码文件都覆盖"),
            ("不同语言的语义深度不完全一致", "依赖 Tree-sitter grammar 可用性"),
            "TypeScript 解析内核的首选基准；可重点复用插件边界和统一 extractor 契约。",
            _scores(87, 81, 55, 75, 53, 81, 87),
        ),
        "code-graph": _entry(
            "GraphBuilder 将扫描/分析结果转成知识图，normalize 阶段稳定节点和边，持久化层保存供搜索与 Dashboard 使用。",
            "结构分析结果进入 graph builder，节点/边归一化后落盘，再由搜索和 UI 消费。",
            ("结构结果", "GraphBuilder", "normalize graph", "persistence", "search/dashboard"),
            ("TypeScript", "knowledge graph", "JSON persistence", "embedding search"),
            ("understand-anything-plugin/packages/core/src/analyzer/graph-builder.ts", "understand-anything-plugin/packages/core/src/analyzer/normalize-graph.ts", "understand-anything-plugin/packages/core/src/persistence/index.ts", "understand-anything-plugin/packages/core/src/search.ts"),
            ("构建、归一化、存储、查询分层清楚", "有大图 benchmark 与测试", "与 Agent skill 集成自然"),
            ("偏知识图而非编译器级调用图", "图精度仍受 extractor/LLM 分析影响"),
            "非常适合作为本地知识图内核基准；调用边精度应与 LSP/SCIP 方案组合。",
            _scores(75, 76, 70, 76, 82, 79, 84),
        ),
        "component-discovery": _entry(
            "确定性 layer detector 与 LLM analyzer 组合识别架构层、领域和组件，最后由 graph reviewer 校验。",
            "扫描结构先做层级/框架检测，再分批交给专用分析 Agent，合并并审查图。",
            ("项目扫描", "layer/framework detection", "批次/领域 Agent 分析", "合并子图", "graph review"),
            ("TypeScript", "layer detector", "specialized agents", "batch graph merge"),
            ("understand-anything-plugin/packages/core/src/analyzer/layer-detector.ts", "understand-anything-plugin/packages/core/src/analyzer/llm-analyzer.ts", "understand-anything-plugin/agents/architecture-analyzer.md", "understand-anything-plugin/agents/graph-reviewer.md"),
            ("确定性候选与模型语义结合", "支持大型仓库分批", "有专门审查阶段"),
            ("组件结论仍有模型非确定性", "Agent prompts 是实现的重要组成"),
            "最适合参考组件发现的混合管线；建议保留确定性候选、模型裁决、独立审查三层。",
            _scores(70, 71, 84, 73, 78, 77, 86),
        ),
        "tutorial-generation": _entry(
            "TourGenerator 从知识图生成有顺序的代码 Tour，多个 explain/onboard/domain skills 针对不同学习任务消费同一图。",
            "知识图与用户目标进入 tour builder，选择关键节点和顺序，再由 Skill 生成解释或上手材料。",
            ("知识图", "选择目标/关键节点", "TourGenerator 排序", "专用 Skill 解释", "Dashboard/Markdown"),
            ("TypeScript", "TourGenerator", "Claude skills", "knowledge graph"),
            ("understand-anything-plugin/packages/core/src/analyzer/tour-generator.ts", "understand-anything-plugin/agents/tour-builder.md", "understand-anything-plugin/skills/understand-onboard/SKILL.md", "understand-anything-plugin/skills/understand-explain/SKILL.md"),
            ("同一图支持多个教学场景", "Tour 顺序有独立实现与测试", "Skill 可直接给编码 Agent 使用"),
            ("不是完整的长篇章节生成器", "部分呈现依赖宿主 Agent"),
            "最适合参考“图→Tour→Skill”的复用链；长篇教程结构可与 PocketFlow 思路组合。",
            _scores(65, 73, 84, 69, 85, 75, 86),
        ),
        "evidence-grounding": _entry(
            "图节点保留文件来源，extractor 结果和 Tour step 可回到文件；但没有统一的行号 snippet claim gate。",
            "解析器产生文件结构，graph builder 把来源带入节点，解释和 Tour 使用节点路径作为引用。",
            ("parser/extractor", "带来源的图节点", "Tour/解释选择节点", "文件路径回链"),
            ("TypeScript", "source-backed graph", "schema validation"),
            ("understand-anything-plugin/packages/core/src/schema.ts", "understand-anything-plugin/packages/core/src/analyzer/graph-builder.ts", "understand-anything-plugin/packages/core/src/analyzer/tour-generator.ts"),
            ("证据从解析层贯穿到图", "schema 和测试覆盖良好"),
            ("缺少逐 claim 行号/snippet 校验", "Markdown Agent 输出仍需额外 guard"),
            "可复用来源随图传播的模型；补充 EvidenceRef 和文本 claim gate 后更适合生产。",
            _scores(67, 69, 75, 68, 72, 73, 75),
        ),
        "incremental-update": _entry(
            "fingerprint、change classifier、staleness 和 post-tool hook 共同判断图是否失效以及更新深度。",
            "文件指纹与旧快照比较，变化被分类，staleness 决定局部/完整刷新，hook 在编辑后触发维护。",
            ("文件状态", "fingerprint diff", "change classification", "staleness decision", "局部/完整更新", "post-tool hook"),
            ("TypeScript", "fingerprint", "change classifier", "staleness", "hooks"),
            ("understand-anything-plugin/packages/core/src/fingerprint.ts", "understand-anything-plugin/packages/core/src/change-classifier.ts", "understand-anything-plugin/packages/core/src/staleness.ts", "understand-anything-plugin/hooks/post-tool-use-auto-update.mjs"),
            ("从检测到自动触发链路完整", "适合本地 Agent 编辑循环", "各策略有测试"),
            ("持久状态以本地插件场景为主", "复杂并发/分布式恢复不是目标"),
            "本地增量索引的最佳基准；可直接参考状态机边界并加强原子写与锁。",
            _scores(72, 72, 76, 91, 78, 82, 91),
        ),
        "codemap-visualization": _entry(
            "知识图 Dashboard 提供分层节点、文件浏览、路径查找和 Tour step 等交互组件。",
            "持久化 graph JSON 被 Dashboard 加载，布局为层/簇节点，用户可搜索路径并进入 step/Tour。",
            ("knowledge-graph.json", "Dashboard load", "层/簇布局", "路径搜索", "文件/Tour drill-down"),
            ("React", "graph dashboard", "layer clusters", "path finder"),
            ("understand-anything-plugin/packages/dashboard/src/components/DomainGraphView.tsx", "understand-anything-plugin/packages/dashboard/src/components/LayerClusterNode.tsx", "understand-anything-plugin/packages/dashboard/src/components/PathFinderModal.tsx", "understand-anything-plugin/packages/dashboard/src/components/StepNode.tsx"),
            ("从宏观层到文件路径的交互层次完整", "适合本地大图", "Tour 与图复用同一数据"),
            ("前端组件与自身 graph schema 绑定", "超大图仍需聚合和虚拟化策略"),
            "Codemap 交互的首选参考；优先复用信息层级和交互，不照搬 schema。",
            _scores(67, 72, 80, 76, 94, 79, 90),
        ),
        "agent-workflow": _entry(
            "将分析职责拆成 project scanner、架构/领域/file analyzer、graph reviewer 与 tour builder，并通过 Skills 暴露任务入口。",
            "主 Skill 扫描和分批，调用专用 Agent 产出子图，合并后 reviewer 检查，再由任务 Skill 消费。",
            ("主 Skill", "project scan/batching", "specialized agents", "merge subgraphs", "graph reviewer", "task skills"),
            ("Claude plugin", "skills", "specialized agents", "hooks", "local graph"),
            ("understand-anything-plugin/skills/understand/SKILL.md", "understand-anything-plugin/agents/project-scanner.md", "understand-anything-plugin/agents/graph-reviewer.md", "understand-anything-plugin/skills/understand/merge-subdomain-graphs.py"),
            ("角色边界和产物契约明确", "Skill 直接贴近用户任务", "支持分批和审查"),
            ("编排依赖 Claude 插件语义", "不是通用持久任务运行时"),
            "Skill/Agent 目录设计的最佳参考之一；应把任务契约导出为宿主无关格式。",
            _scores(56, 69, 82, 78, 78, 80, 91),
        ),
    },
    "codeboarding": {
        "code-parsing": _entry(
            "为 Python、TypeScript、Java、Go、Rust、C#、PHP 等语言启动 LSP adapter，提取精确 symbol/reference/call-site。",
            "scanner 选择语言 adapter，LSP client 管理 server 进程，adapter 查询文档符号和引用并归一化模型。",
            ("检测语言", "选择 LSP adapter", "启动/复用 language server", "查询 symbols/references", "归一化结果"),
            ("Python", "LSP", "多 language-server adapters", "process recycling"),
            ("static_analyzer/engine/language_adapter.py", "static_analyzer/engine/lsp_client.py", "static_analyzer/engine/adapters/python_adapter.py", "static_analyzer/engine/source_inspector.py"),
            ("类型感知引用通常比纯 AST 更精确", "多语言 adapter 边界清晰", "包含进程复用和资源管理"),
            ("部署需要各语言 server/binary", "版本和环境问题显著增加运维成本"),
            "精确代码关系的首选基准；建议作为可选增强 adapter，而不是唯一解析后端。",
            _scores(94, 92, 52, 78, 52, 82, 85),
        ),
        "code-graph": _entry(
            "CallGraphBuilder、EdgeBuilder 和 SymbolTable 把 LSP 结果组装成静态调用图，再由 Graph 提供遍历和聚类输入。",
            "多语言分析结果进入 symbol table，解析调用与层级边，跨文件 resolver 补全目标后形成图。",
            ("LSP symbols/references", "SymbolTable", "EdgeBuilder/HierarchyBuilder", "ReferenceResolver", "Call Graph"),
            ("Python", "LSP", "call graph", "symbol table", "edge resolution"),
            ("static_analyzer/engine/call_graph_builder.py", "static_analyzer/engine/edge_builder.py", "static_analyzer/engine/symbol_table.py", "static_analyzer/graph.py"),
            ("调用边建立在类型感知来源上", "建图职责拆分细致", "测试覆盖调用图和边"),
            ("图构建链复杂", "需要处理语言 server 的不一致行为"),
            "最适合参考精确调用图 builder 与统一 adapter 契约；对失败语言保留 Tree-sitter fallback。",
            _scores(95, 93, 55, 80, 64, 84, 90),
        ),
        "component-discovery": _entry(
            "先对调用图执行 Leiden 聚类，再由 abstraction/meta/details agents 为簇命名、补充关系和细节。",
            "调用图转无向/加权聚类输入，Leiden 得到稳定簇，Agent 读取簇内代码生成架构抽象。",
            ("Call Graph", "Leiden clustering", "cluster paths/relations", "Abstraction Agent", "Meta/Details synthesis"),
            ("Python", "Leiden", "graph clustering", "specialized agents"),
            ("static_analyzer/leiden_utils.py", "static_analyzer/cluster_helpers.py", "agents/abstraction_agent.py", "agents/meta_agent.py"),
            ("图算法先划边界，降低纯 LLM 幻觉", "簇与详情 Agent 分工明确", "能处理跨组件边"),
            ("聚类质量高度依赖调用图", "Leiden resolution 需要按仓库调参"),
            "组件发现的最强基准之一；建议复用“精确图→聚类候选→LLM 命名”的总体方案。",
            _scores(88, 88, 82, 81, 77, 83, 93),
        ),
        "tutorial-generation": _entry(
            "核心输出是组件架构文档和图，而不是面向初学者的渐进教程；workflow rendering 汇总分析结果。",
            "静态分析和 Agent 产出 analysis model，renderer 将组件/关系组织为 Markdown 与图文件。",
            ("静态图/组件", "Agent details", "analysis model", "workflow rendering", "架构文档"),
            ("Python", "structured agent responses", "Markdown", "diagram"),
            ("agents/details_agent.py", "agents/agent_responses.py", "codeboarding_workflows/rendering.py", "codeboarding_workflows/analysis.py"),
            ("技术内容由精确图支撑", "结构化响应便于多种 renderer", "组件文档深度较好"),
            ("缺少学习路线和教学节奏", "输出更像架构说明而非教程"),
            "把其分析模型作为教程事实源，教学结构应另行采用 Tour/章节生成器。",
            _scores(83, 90, 66, 78, 73, 81, 75),
        ),
        "evidence-grounding": _entry(
            "LSP 模型保留定义、引用和调用位置，Agent tools 以受控接口读取源码、CFG 和 invocation，结构化响应绑定代码实体。",
            "静态分析生成位置证据，Agent 按 scope 通过工具读取，response models 和 validator 限制输出引用。",
            ("LSP positions", "file/symbol index", "scoped Agent tools", "structured response", "validation"),
            ("LSP", "SourceCodeReference", "Agent tools", "Pydantic validation"),
            ("static_analyzer/engine/models.py", "agents/tools/read_source.py", "agents/tools/get_method_invocations.py", "agents/validation.py"),
            ("底层位置证据精确", "Agent 不必直接获得无限文件访问", "响应有模型校验"),
            ("需要额外层把所有自然语言 claim 映射到 evidence id", "LSP 缺失会降低覆盖"),
            "适合参考证据采集和受控读取工具；在本产品中统一转成 EvidenceRef。",
            _scores(92, 91, 72, 79, 65, 85, 89),
        ),
        "incremental-update": _entry(
            "fingerprint diff、change detector 和 incremental orchestrator 共同复用未变静态分析并重算受影响簇/文档。",
            "比较文件指纹得到增删改，规划静态分析范围，copy-forward 未变结果，计算 cluster delta 后调用增量 Agent。",
            ("旧/新 fingerprint", "文件 diff", "受影响静态分析", "copy-forward", "cluster delta", "增量 Agent/renderer"),
            ("Python", "fingerprint diff", "incremental orchestrator", "cluster delta", "copy-forward"),
            ("repo_utils/fingerprint_diff.py", "repo_utils/change_detector.py", "static_analyzer/incremental_orchestrator.py", "static_analyzer/analysis_cache.py", "diagram_analysis/cluster_delta.py", "agents/incremental_agent.py"),
            ("复用跨越静态图、簇和文档层", "有专门增量 CLI 与测试", "变更状态模型明确"),
            ("状态格式和完整分析模型耦合", "异常恢复需要理解多个缓存层"),
            "生产级本地增量的首选参考；优先复用 diff/plan/copy-forward 三段式协议。",
            _scores(89, 91, 77, 96, 70, 90, 94),
        ),
        "codemap-visualization": _entry(
            "Diagram generator 将 analysis.json 的组件、关系与簇变化生成架构图，并有 coverage/shape/delta 诊断。",
            "分析模型进入 scope plan，diagram generator 渲染图，file coverage 与 tree-shape 验证输出完整度。",
            ("analysis model", "scope plan", "diagram generation", "coverage/shape validation", "输出图"),
            ("Python", "diagram generator", "coverage metrics", "cluster delta"),
            ("diagram_analysis/scope_plan.py", "diagram_analysis/diagram_generator.py", "diagram_analysis/file_coverage.py", "diagram_analysis/tree_shape.py", "diagram_analysis/cluster_delta.py"),
            ("可视化有覆盖率和结构诊断", "支持增量簇变化", "图与组件模型一致"),
            ("偏架构组件图，不是代码浏览器", "源码跳转交互有限"),
            "适合参考图生成质量检测；交互式 Codemap 前端需结合 DeepWiki/Understand Anything。",
            _scores(82, 88, 70, 88, 83, 85, 86),
        ),
        "agent-workflow": _entry(
            "Planner、Meta、Abstraction、Details、Incremental agents 通过 orchestration 和 toolkit 围绕共享分析模型协作。",
            "workflow 先完成静态分析，再按簇规划 Agent 任务，工具限制读取范围，结果经过验证和 repair 后渲染。",
            ("workflow request", "static analysis", "Planner/scope", "specialized agents+tools", "validation/repair", "rendering"),
            ("Python", "specialized agents", "toolkit", "structured responses", "repair loop"),
            ("codeboarding_workflows/orchestration.py", "agents/planner_agent.py", "agents/tools/toolkit.py", "agents/repair.py"),
            ("Agent 建立在确定性分析之上", "角色和工具权限明确", "包含 retry/repair/validation"),
            ("面向固定代码架构分析流程", "不是任意需求的动态图编排器"),
            "代码仓协作 Agent 的首选参考；动态 planner 可以复用其角色/工具边界而非固定流程。",
            _scores(85, 90, 78, 86, 73, 89, 92),
        ),
    },
    "deepwiki-open": {
        "code-parsing": _entry(
            "没有 AST/LSP 符号解析器；Repository 层读取仓库文本，RAG pipeline 分块并向量化供问答/Wiki 使用。",
            "准备本地仓库，按文件读取和分块，embedder 写入向量索引，后续检索相关 chunk。",
            ("Git/local repository", "文件过滤/读取", "文本切块", "embedding", "RAG retrieval"),
            ("Python", "RAG", "embeddings", "文本 chunk"),
            ("api/repository.py", "api/rag/pipeline.py", "api/rag/rag.py"),
            ("语言无关", "适合语义问答", "支持多种本地/云模型"),
            ("没有符号和调用边", "chunk 边界不等同于代码语义边界"),
            "只作为语义检索补充，不可替代生产代码索引。",
            _scores(20, 42, 75, 38, 50, 63, 49),
        ),
        "code-graph": _entry(
            "没有源码调用图；Codemap 是由 LLM 生成的 sections → steps 引导式代码导览，并给步骤绑定源码 citation。",
            "仓库树与 RAG context 进入两阶段 Codemap prompt，Pydantic 校验 section/step/citation，随后用真实 snippet 校正行号。",
            ("仓库树/RAG context", "Codemap skeleton", "section/step enrichment", "citation grounding", "引导式阅读"),
            ("Python", "LLM", "Pydantic", "guided code tour", "citation"),
            ("api/services/codemap.py", "api/schemas/codemap.py", "api/routers/codemap.py"),
            ("能按用户问题生成阅读步骤", "citation 可回到真实文件和行", "失败时可降级为 skeleton"),
            ("不产出 node/edge 调用图", "步骤与关系由模型规划", "大仓完整性受检索上下文限制"),
            "把它归入 guided tour 而不是代码图；可参考 question-driven 导览，不能用于影响分析。",
            _scores(28, 40, 78, 36, 85, 61, 55),
        ),
        "component-discovery": _entry(
            "Wiki structure service 根据仓库树、README 和检索内容，由 LLM 规划页面层级与主题。",
            "收集仓库概览，structure prompt 生成嵌套 Wiki page schema，任务层持久化生成状态。",
            ("仓库概览", "structure prompt", "LLM 识别主题", "WikiStructure schema", "页面任务"),
            ("Python", "LLM", "Pydantic", "Wiki structure"),
            ("api/services/wiki/structure.py", "api/services/wiki/prompts.py", "api/schemas/wiki.py"),
            ("输出直接对应用户可见 Wiki 导航", "schema 清晰", "实现易理解"),
            ("没有图聚类候选", "组件边界依赖模型和输入裁剪"),
            "可参考 Wiki 页面规划 schema；组件事实应由静态图/聚类提供。",
            _scores(35, 44, 84, 39, 73, 62, 61),
        ),
        "tutorial-generation": _entry(
            "先生成 Wiki 结构，再以异步任务逐页生成内容，支持任务状态和流式前端更新。",
            "structure 规划 pages，tasks 调度 content generator，结果写入项目目录并通过 API/stream 返回。",
            ("Wiki structure", "创建 page tasks", "RAG+LLM content", "保存 Wiki", "状态/流式展示"),
            ("Python", "async tasks", "RAG", "LLM", "Next.js"),
            ("api/services/wiki/structure.py", "api/services/wiki/tasks.py", "api/services/wiki/content.py", "src/utils/wikiTask.ts"),
            ("结构和内容生成分离", "前端任务体验完整", "支持本地模型部署"),
            ("缺少可验证行号引用", "更偏百科页而非教学步骤"),
            "适合参考异步 Wiki 生成和用户反馈；教程质量与证据 gate 要另行实现。",
            _scores(34, 45, 85, 45, 81, 70, 70),
        ),
        "evidence-grounding": _entry(
            "Wiki 正文主要依靠 RAG 上下文；但 Codemap step 另有 file/snippet/line citation，并用真实文件反查 snippet 来覆盖模型猜测行号。",
            "检索 chunk 注入生成提示；Codemap citation 保存文件与 snippet，生成后在本地源码中定位 snippet 并校正起止行。",
            ("RAG chunks", "section/step 生成", "file+snippet citation", "真实文件 snippet 定位", "可点击行号"),
            ("RAG", "Pydantic", "CodeMapCitation", "snippet grounding"),
            ("api/rag/rag.py", "api/services/codemap.py", "api/schemas/codemap.py", "src/components/CodeMap.tsx"),
            ("Codemap citation 对用户可见", "行号由真实源码校正而非直接信任模型", "检索与生成解耦"),
            ("Wiki 正文并非逐 claim 引用", "snippet fallback 只锚定首个非空行，不能证明自然语言结论", "没有统一 snippet hash"),
            "复用 Codemap citation 与行号校正链路；若用于全产品证据层，仍需扩展到每个 claim 并增加 snippet hash。",
            _scores(42, 66, 73, 39, 70, 62, 62),
        ),
        "incremental-update": _entry(
            "保存 processed projects 和 Wiki task 状态，但未实现文件 fingerprint 到页面失效的增量依赖模型。",
            "项目可被重新处理，前端读取已有任务/产物；更新主要是重新触发生成。",
            ("processed project", "读取已有任务", "重新触发 Wiki/Codemap", "覆盖保存", "刷新前端"),
            ("Python", "task persistence", "Next.js state"),
            ("api/services/wiki/tasks.py", "api/services/wiki/io.py", "src/hooks/useProcessedProjects.ts"),
            ("生成任务可恢复和展示", "已有项目可再次打开"),
            ("没有文件级 diff/fingerprint", "无法精确复用未变页面"),
            "不作为增量算法参考；只参考任务状态和 processed-project UX。",
            _scores(16, 30, 70, 24, 67, 53, 35),
        ),
        "codemap-visualization": _entry(
            "后端返回 sections → steps → citation；前端按章节展示 guide、Mermaid 与步骤，点击 citation 在 CodeViewer 高亮源码行。",
            "Codemap API 流式返回阶段和结构化导览，CodeMap 渲染 section/step，CitationChip 把 file/line 交给 CodeViewer。",
            ("Codemap stream", "sections/steps render", "guide/Mermaid", "citation selection", "CodeViewer line highlight"),
            ("Python", "Next.js", "CodeMapSection", "CodeMapStep", "Mermaid", "CodeViewer"),
            ("api/services/codemap.py", "api/schemas/codemap.py", "src/components/CodeMap.tsx", "src/components/CodeViewer.tsx"),
            ("导览—引用—源码查看闭环完整", "citation chip 明确显示文件与行号", "生成阶段有进度反馈"),
            ("不是 node/edge 图浏览器", "Mermaid 和步骤内容由模型生成", "组件与自身 section/step schema 绑定"),
            "guided Codemap UI 的首选参考之一；若需要确定性代码图，应作为另一种视图而不是替换其数据源。",
            _scores(32, 48, 82, 42, 93, 73, 82),
        ),
        "agent-workflow": _entry(
            "以异步 Wiki task、research service 和流式 API 编排固定生成流程，不是通用多 Agent 动态 planner。",
            "API 创建任务，后台依次生成结构/内容或研究结果，状态通过 task endpoint/stream 提供给前端。",
            ("HTTP request", "create task", "structure/content/research service", "task status", "stream/UI"),
            ("FastAPI", "async tasks", "streaming", "Next.js"),
            ("api/services/wiki/tasks.py", "api/services/research.py", "api/routers/wiki.py", "src/utils/wikiTask.ts"),
            ("异步任务到 UI 的链路清楚", "适合长耗时生成", "部署方式完整"),
            ("任务拓扑固定", "缺少多 Agent 角色、预算、审批和动态图"),
            "参考长任务 API/streaming 控制面；动态 Agent 工作流需要独立 planner/runtime。",
            _scores(25, 37, 78, 46, 77, 67, 59),
        ),
    },
}

# Claim-level anchors are deliberately separate from ``source_paths``.  A path
# says where to continue reading; an audited claim says which exact immutable
# lines support one concrete statement.  comparison.py hashes these ranges from
# the verified worktree and exposes the hash with the link.  Paths without an
# entry here remain useful context, but are labelled ``file-context`` or
# ``symbol-context`` and must not be presented as proof of the prose claim.
AUDITED_CLAIMS: dict[tuple[str, str], tuple[dict[str, Any], ...]] = {
    ("sourcebridge", "code-graph"): (
        {
            "claim": "SurrealDB store implements repository linking and persists a canonical pair.",
            "path": "internal/db/store_federation.go",
            "line_start": 99,
            "line_end": 132,
        },
        {
            "claim": "SurrealDB store persists cross-repository symbol references.",
            "path": "internal/db/store_federation.go",
            "line_start": 182,
            "line_end": 218,
        },
        {
            "claim": "The in-memory Store is explicitly a federation stub and returns not-supported errors.",
            "path": "internal/graph/store.go",
            "line_start": 2100,
            "line_end": 2138,
        },
    ),
    ("sourcebridge", "tutorial-generation"): (
        {
            "claim": "Workflow Story is a concrete knowledge artifact with its own structured generator.",
            "path": "workers/knowledge/workflow_story.py",
            "line_start": 611,
            "line_end": 636,
        },
        {
            "claim": "Deep workflow-story sections pass an explicit evidence threshold and confidence floor.",
            "path": "workers/knowledge/workflow_story.py",
            "line_start": 729,
            "line_end": 753,
        },
    ),
    ("openwiki", "component-discovery"): (
        {
            "claim": "The one-repeat critic policy is written in the repository prompt, not enforced by runtime state.",
            "path": "src/agent/prompts/code.ts",
            "line_start": 133,
            "line_end": 136,
        },
    ),
    ("deepwiki-open", "code-graph"): (
        {
            "claim": "Retrieved chunks are grouped by file and annotated with their real line ranges.",
            "path": "api/services/codemap.py",
            "line_start": 128,
            "line_end": 148,
        },
        {
            "claim": "Codemap citations are grounded by locating their snippet in the local source file.",
            "path": "api/services/codemap.py",
            "line_start": 178,
            "line_end": 222,
        },
        {
            "claim": "Generated Codemap citations are grounded before the final event is emitted.",
            "path": "api/services/codemap.py",
            "line_start": 305,
            "line_end": 309,
        },
    ),
    ("deepwiki-open", "evidence-grounding"): (
        {
            "claim": "Retrieved chunks retain actual source line ranges in Codemap context.",
            "path": "api/services/codemap.py",
            "line_start": 128,
            "line_end": 148,
        },
        {
            "claim": "Snippet lookup and citation grounding overwrite model-provided line guesses.",
            "path": "api/services/codemap.py",
            "line_start": 178,
            "line_end": 222,
        },
        {
            "claim": "The grounding pass runs against the cloned repository before output.",
            "path": "api/services/codemap.py",
            "line_start": 305,
            "line_end": 309,
        },
    ),
    ("deepwiki-open", "codemap-visualization"): (
        {
            "claim": "CitationChip displays the file and grounded line range and dispatches selection.",
            "path": "src/components/CodeMap.tsx",
            "line_start": 53,
            "line_end": 64,
        },
        {
            "claim": "Sections render guided steps and forward citation clicks to the code viewer.",
            "path": "src/components/CodeMap.tsx",
            "line_start": 113,
            "line_end": 137,
        },
        {
            "claim": "CodeViewer fetches the selected file and scrolls the highlighted range into view.",
            "path": "src/components/CodeViewer.tsx",
            "line_start": 49,
            "line_end": 80,
        },
    ),
}

REFERENCE_IDENTITIES: dict[str, dict[str, str]] = {
    "sourcebridge": {
        "remote": "github.com/sourcebridge-ai/sourcebridge",
        "commit": "2a128bf0c8461fae91d2b424d9168ddf205bb11b",
        "source_bundle_sha256": "2857f494bda3e8328d075395d0a3e7122bf24d4e66747dd75436084ec9f235c5",
    },
    "pocketflow-code2tutorial": {
        "remote": "github.com/the-pocket/pocketflow-tutorial-codebase-knowledge",
        "commit": "05b24cbbb0fe409c5e23c9791f0342f07524ffdc",
        "source_bundle_sha256": "18047260f528bbc6a439d033f6da6bdf1c1bc3c542f38df8013811c4ed202f61",
    },
    "openwiki": {
        "remote": "github.com/langchain-ai/openwiki",
        "commit": "7531d615216e8cbccf464f66cfbbae3668871c84",
        "source_bundle_sha256": "eb56af93b382495212d0a2f9983b386a528244b8b8c3920ac22bb55bc5c088b7",
    },
    "understand-anything": {
        "remote": "github.com/egonex-ai/understand-anything",
        "commit": "fe8c5bc591716aafd79b4765549328f08ef5a52e",
        "source_bundle_sha256": "e4497988636b60e79b5b336eeb066f44a1ce60cf5b1ba8c019c755b233fdd0ee",
    },
    "codeboarding": {
        "remote": "github.com/codeboarding/codeboarding",
        "commit": "8c3f2218c3ecab1294902db5914f5e526f78524d",
        "source_bundle_sha256": "e31448f3add15bf0500ae31d1cff96e9c46490b1b139cb060ec60451f32d52c5",
    },
    "deepwiki-open": {
        "remote": "github.com/asyncfuncai/deepwiki-open",
        "commit": "4181daa5ebde79a1baf8e92a09dd874f8b74411b",
        "source_bundle_sha256": "34eee77dc8841b13de9cb134a6c710782656db57aae9762af433b224e5d6caf8",
    },
}


# A capability name is not necessarily one decision problem.  In particular,
# deterministic call graphs, document graphs and guided tours must not share a
# single winner.  Every curated option therefore declares the kind of technical
# object it implements; comparison.py ranks within a class only.
COMPARISON_CLASSES: dict[str, dict[str, str]] = {
    "code-parsing": {
        "sourcebridge": "deterministic-syntax-index",
        "pocketflow-code2tutorial": "text-ingestion",
        "openwiki": "agent-on-demand-reading",
        "understand-anything": "deterministic-syntax-index",
        "codeboarding": "type-aware-lsp-index",
        "deepwiki-open": "text-rag-index",
    },
    "code-graph": {
        "sourcebridge": "deterministic-code-fact-graph",
        "pocketflow-code2tutorial": "llm-concept-relations",
        "openwiki": "document-navigation-graph",
        "understand-anything": "semantic-knowledge-graph",
        "codeboarding": "deterministic-code-fact-graph",
        "deepwiki-open": "guided-code-tour-not-graph",
    },
    "component-discovery": {
        "sourcebridge": "static-graph-plus-hierarchical-llm",
        "pocketflow-code2tutorial": "single-pass-llm-abstractions",
        "openwiki": "agent-plus-independent-critic",
        "understand-anything": "static-analysis-plus-llm-review",
        "codeboarding": "graph-clustering-plus-specialist-agents",
        "deepwiki-open": "llm-wiki-structure-planning",
    },
    "tutorial-generation": {
        "sourcebridge": "multi-artifact-knowledge-workers",
        "pocketflow-code2tutorial": "fixed-tutorial-dag",
        "openwiki": "agent-written-linked-wiki",
        "understand-anything": "knowledge-graph-code-tour",
        "codeboarding": "architecture-document-rendering",
        "deepwiki-open": "async-rag-wiki-generation",
    },
    "evidence-grounding": {
        "sourcebridge": "claim-evidence-gates",
        "pocketflow-code2tutorial": "file-level-reference-validation",
        "openwiki": "process-review-and-link-validation",
        "understand-anything": "code-entity-provenance",
        "codeboarding": "source-location-and-scoped-tools",
        "deepwiki-open": "codemap-snippet-citations",
    },
    "incremental-update": {
        "sourcebridge": "dependency-aware-incremental-rebuild",
        "pocketflow-code2tutorial": "full-regeneration-with-prompt-cache",
        "openwiki": "document-metadata-sync",
        "understand-anything": "fingerprint-staleness-trigger",
        "codeboarding": "dependency-aware-incremental-rebuild",
        "deepwiki-open": "task-persistence-full-regeneration",
    },
    "codemap-visualization": {
        "sourcebridge": "code-tour-plus-architecture-diagram",
        "pocketflow-code2tutorial": "static-mermaid-in-tutorial",
        "openwiki": "document-relationship-graph",
        "understand-anything": "knowledge-graph-dashboard",
        "codeboarding": "validated-architecture-diagram",
        "deepwiki-open": "guided-sections-with-citations",
    },
    "agent-workflow": {
        "sourcebridge": "reliable-domain-job-orchestration",
        "pocketflow-code2tutorial": "fixed-generation-dag",
        "openwiki": "dynamic-planner-subagent-runtime",
        "understand-anything": "skill-and-agent-distribution",
        "codeboarding": "fixed-analysis-multi-agent-workflow",
        "deepwiki-open": "long-task-api-control-plane",
    },
}


def _normalize_remote(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("git@") and ":" in text:
        host, path = text[4:].split(":", 1)
        normalized = f"{host}/{path}"
    else:
        parsed = urlsplit(text)
        allowed_ssh_user = parsed.scheme == "ssh" and parsed.username == "git" and parsed.password is None
        if (
            not parsed.hostname
            or parsed.query
            or parsed.fragment
            or (parsed.username is not None and not allowed_ssh_user)
            or (parsed.password is not None)
        ):
            return ""
        normalized = f"{parsed.hostname}{parsed.path}"
    return normalized.lower().rstrip("/").removesuffix(".git")


def _source_bundle_sha256(index: dict[str, Any], project_key: str) -> str | None:
    files = {
        str(item.get("path")): str(item.get("sha256"))
        for item in index.get("files", [])
        if isinstance(item, dict) and item.get("path") and item.get("sha256")
    }
    required_paths = sorted(
        {path for entry in REFERENCE_CATALOG[project_key].values() for path in entry["source_paths"]}
    )
    if any(path not in files or not re.fullmatch(r"[0-9a-f]{64}", files[path]) for path in required_paths):
        return None
    project = index.get("project", {}) if isinstance(index.get("project"), dict) else {}
    root = Path(str(project.get("path") or ""))
    if not root.is_absolute() or not root.is_dir():
        return None
    resolved_root = root.resolve()
    verified_hashes: dict[str, str] = {}
    for source_path in required_paths:
        relative = PurePosixPath(source_path)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        candidate = (resolved_root / Path(*relative.parts)).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if not hmac.compare_digest(actual, files[source_path]):
            return None
        verified_hashes[source_path] = actual
    material = "\n".join(f"{path}\0{verified_hashes[path]}" for path in required_paths)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _git_value(root: Path, *arguments: str) -> str | None:
    """Read one value from the worktree without trusting index metadata."""

    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git_snapshot(root: Path) -> dict[str, Any] | None:
    """Resolve the actual Git root, origin, HEAD and dirty state.

    Merely copying the audited files and spoofing ``project.remote`` or
    ``project.commit`` in JSON can therefore never produce a verified identity.
    """

    resolved_root = root.resolve()
    git_root = _git_value(resolved_root, "rev-parse", "--show-toplevel")
    if not git_root:
        return None
    try:
        resolved_git_root = Path(git_root).resolve(strict=True)
    except OSError:
        return None
    if resolved_git_root != resolved_root:
        return None
    remote = _git_value(resolved_root, "config", "--get", "remote.origin.url")
    head = _git_value(resolved_root, "rev-parse", "--verify", "HEAD")
    status = _git_value(resolved_root, "status", "--porcelain=v1", "--untracked-files=no")
    if remote is None or head is None or status is None:
        return None
    return {
        "git_root": str(resolved_git_root),
        "remote": _normalize_remote(remote),
        "head": head.lower(),
        "dirty": bool(status),
    }


def reference_identity_status(index: dict[str, Any]) -> dict[str, Any]:
    """Return a fail-closed identity decision for a curated Git worktree."""

    project = index.get("project", {}) if isinstance(index.get("project"), dict) else {}
    root = Path(str(project.get("path") or ""))
    if not root.is_absolute() or not root.is_dir():
        return {"status": "unverified", "project_key": None, "reason": "source root is unavailable"}
    git_snapshot = _git_snapshot(root)
    if git_snapshot is None:
        return {
            "status": "unverified",
            "project_key": None,
            "reason": "source root is not the top level of a readable Git worktree",
        }
    remote = str(git_snapshot["remote"])
    candidate = next(
        (key for key, identity in REFERENCE_IDENTITIES.items() if remote == identity["remote"]),
        None,
    )
    if candidate is None:
        return {"status": "unverified", "project_key": None, "reason": "canonical remote does not match"}
    identity = REFERENCE_IDENTITIES[candidate]
    commit = str(git_snapshot["head"])
    if commit != identity["commit"]:
        return {"status": "stale", "project_key": candidate, "reason": "audited commit does not match"}
    actual_bundle = _source_bundle_sha256(index, candidate)
    if actual_bundle != identity["source_bundle_sha256"]:
        return {
            "status": "stale",
            "project_key": candidate,
            "reason": "required source bundle is missing or has changed",
        }
    return {
        "status": "verified",
        "project_key": candidate,
        "reason": None,
        "git_root": git_snapshot["git_root"],
        "remote": remote,
        "head": commit,
        "worktree_bundle_sha256": actual_bundle,
        "dirty": git_snapshot["dirty"],
    }


def identify_reference_project(index: dict[str, Any]) -> str | None:
    """Return a catalog key only for the exact audited remote/commit/source bundle."""

    status = reference_identity_status(index)
    return str(status["project_key"]) if status["status"] == "verified" else None


def curated_implementation(index: dict[str, Any], capability_slug: str) -> dict[str, Any] | None:
    """Return a curated entry only when every audited identity gate passes."""

    project_key = identify_reference_project(index)
    if project_key is None:
        return None
    raw = REFERENCE_CATALOG.get(project_key, {}).get(capability_slug)
    if raw is None:
        return None
    result = {key: value.copy() if isinstance(value, (list, dict)) else value for key, value in raw.items()}
    result["project_key"] = project_key
    result["comparison_class"] = COMPARISON_CLASSES[capability_slug][project_key]
    result["identity"] = dict(REFERENCE_IDENTITIES[project_key])
    result["source_claims"] = [dict(item) for item in AUDITED_CLAIMS.get((project_key, capability_slug), ())]
    result["catalog_revision"] = CATALOG_REVISION
    return result


def validate_reference_catalog() -> list[str]:
    """Return schema errors so tests and maintenance scripts can fail visibly."""

    errors: list[str] = []
    required = {
        "summary",
        "approach",
        "data_flow",
        "technology_tags",
        "source_paths",
        "strengths",
        "limitations",
        "reuse_verdict",
        "dimension_scores",
        "source",
    }
    expected_capabilities = {
        "code-parsing",
        "code-graph",
        "component-discovery",
        "tutorial-generation",
        "evidence-grounding",
        "incremental-update",
        "codemap-visualization",
        "agent-workflow",
    }
    for project, capabilities in REFERENCE_CATALOG.items():
        if project not in REFERENCE_IDENTITIES:
            errors.append(f"{project}: missing audited identity")
        missing_capabilities = expected_capabilities - set(capabilities)
        if missing_capabilities:
            errors.append(f"{project}: missing capabilities {sorted(missing_capabilities)}")
        for slug, entry in capabilities.items():
            missing = required - set(entry)
            if missing:
                errors.append(f"{project}/{slug}: missing fields {sorted(missing)}")
            if set(entry.get("dimension_scores", {})) != set(SCORE_DIMENSIONS):
                errors.append(f"{project}/{slug}: invalid dimension_scores")
            elif any(score not in SCORE_RUBRIC_LEVELS for score in entry["dimension_scores"].values()):
                errors.append(f"{project}/{slug}: scores are outside the published rubric")
            if not entry.get("source_paths"):
                errors.append(f"{project}/{slug}: no source paths")
            if project not in COMPARISON_CLASSES.get(slug, {}):
                errors.append(f"{project}/{slug}: no comparison class")
            for claim in AUDITED_CLAIMS.get((project, slug), ()):
                if claim.get("path") not in entry.get("source_paths", []):
                    errors.append(f"{project}/{slug}: claim path is not in source_paths")
                start = claim.get("line_start")
                end = claim.get("line_end")
                if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
                    errors.append(f"{project}/{slug}: invalid claim line range")
                if not str(claim.get("claim") or "").strip():
                    errors.append(f"{project}/{slug}: empty claim")
    return errors
