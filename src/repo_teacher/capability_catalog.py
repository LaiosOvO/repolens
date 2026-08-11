from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .evidence import EvidenceStore
from .models import (
    FeatureRecord,
    FeatureStep,
    FileRecord,
    ModuleSummary,
    ProjectSnapshot,
    RelationshipRecord,
    SymbolRecord,
    TechnologyClaim,
    stable_id,
)


TECHNOLOGY_DIMENSIONS = (
    "parser",
    "framework",
    "store",
    "retrieval",
    "llm",
    "incremental",
    "evidence",
    "ui",
)

@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    slug: str
    title: str
    summary: str
    path: str
    role: str
    technology: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    project: str
    commit: str
    canonical_remote: str
    signature_paths: tuple[str, ...]
    capabilities: tuple[CapabilitySpec, ...]


@dataclass(frozen=True, slots=True)
class AuditSliceSpec:
    path: str
    line_start: int
    line_end: int
    symbol: str
    role: str
    reading_hypothesis: str


@dataclass(frozen=True, slots=True)
class AuditRelationshipSpec:
    source_slice_index: int
    target_slice_index: int
    callsite_line_start: int
    callsite_line_end: int
    allowed_kinds: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TechnologyEvidenceSpec:
    tag: str
    slice_index: int
    claim_scope: str


@dataclass(frozen=True, slots=True)
class CapabilityAuditContract:
    slices: tuple[AuditSliceSpec, ...]
    technology: tuple[TechnologyEvidenceSpec, ...]
    relationships: tuple[AuditRelationshipSpec, ...] = ()


def _cap(
    slug: str,
    title: str,
    summary: str,
    path: str,
    role: str,
    *technology: str,
) -> CapabilitySpec:
    return CapabilitySpec(slug, title, summary, path, role, technology)


# This is deliberately a small, version-pinned, source-audited manifest rather
# than a keyword classifier.  A repository is matched only when all of its
# signature paths are present; every capability is then grounded to an exact
# file.  Unknown technology dimensions remain explicit in the output.
REFERENCE_MANIFESTS: tuple[ProjectManifest, ...] = (
    ProjectManifest(
        "sourcebridge",
        "2a128bf0c8461fae91d2b424d9168ddf205bb11b",
        "github.com/sourcebridge-ai/sourcebridge",
        ("internal/graph/store.go", "workers/knowledge/code_tour.py"),
        (
            _cap("graph-store", "内存图数据存储", "在进程内维护代码实体、关系与图查询所需的数据；持久化后端仍是扩展点。", "internal/graph/store.go", "内存图存储边界", "store:in-memory", "retrieval:graph-query"),
            _cap("execution-path", "执行路径查询", "从代码图中构造可追溯的调用/执行路径。", "internal/graph/execution_path.go", "路径解析", "store:graph", "retrieval:execution-path", "evidence:source-location"),
            _cap("code-tour", "证据化代码导览", "围绕选定源码节点生成带定位证据的代码导览。", "workers/knowledge/code_tour.py", "导览生成", "llm:provider-adapter", "retrieval:graph-context", "evidence:source-citation"),
        ),
    ),
    ProjectManifest(
        "pocketflow-code2tutorial",
        "05b24cbbb0fe409c5e23c9791f0342f07524ffdc",
        "github.com/the-pocket/pocketflow-tutorial-codebase-knowledge",
        ("flow.py", "nodes.py"),
        (
            _cap("tutorial-flow", "教程工作流编排", "把分析、关系整理和章节写作组织成可执行流程。", "flow.py", "流程编排", "framework:pocketflow", "llm:workflow-nodes"),
            _cap("tutorial-nodes", "教程生成节点", "实现抽象提取、关系分析、章节排序与内容生成节点。", "nodes.py", "教学节点", "parser:repository-context", "framework:pocketflow", "llm:prompted-generation", "evidence:file-reference"),
        ),
    ),
    ProjectManifest(
        "openwiki",
        "7531d615216e8cbccf464f66cfbbae3668871c84",
        "github.com/langchain-ai/openwiki",
        ("src/agent/skeleton_critic.ts", "src/ingestion/ingestion.ts"),
        (
            _cap("skeleton-critic", "知识骨架审查", "在撰写正文前审查知识骨架的覆盖度与具体性。", "src/agent/skeleton_critic.ts", "覆盖审查", "llm:subagent", "evidence:coverage-critique"),
            _cap("wiki-link-validator", "Wiki 引用校验", "解析并校验内部链接、锚点和目标文件。", "src/agent/wiki-link-validator.ts", "链接验证", "parser:markdown", "retrieval:repository-files", "evidence:link-validation"),
            _cap("ingestion", "多来源知识摄取", "从连接器读取来源并驱动知识生成与持久化流程。", "src/ingestion/ingestion.ts", "摄取编排", "framework:connector-registry", "store:backend-adapter", "incremental:ingestion-window", "llm:agent-run"),
        ),
    ),
    ProjectManifest(
        "understand-anything",
        "fe8c5bc591716aafd79b4765549328f08ef5a52e",
        "github.com/egonex-ai/understand-anything",
        ("understand-anything-plugin/src/context-builder.ts", "understand-anything-plugin/src/onboard-builder.ts"),
        (
            _cap("context-builder", "面向问题的上下文构造", "检索相关节点并沿知识图扩展可控上下文。", "understand-anything-plugin/src/context-builder.ts", "上下文检索", "store:knowledge-graph", "retrieval:search-and-neighbor-expansion", "llm:prompt-context"),
            _cap("onboard-builder", "代码库入门导览", "从知识图层级、概念与 tour 生成渐进式入门文档。", "understand-anything-plugin/src/onboard-builder.ts", "入门视图", "store:knowledge-graph", "retrieval:layered-tour", "evidence:file-node"),
            _cap("explain-builder", "定点代码解释上下文", "围绕文件或函数目标收集子节点、连接节点和图层。", "understand-anything-plugin/src/explain-builder.ts", "解释上下文", "parser:path-and-symbol-target", "store:knowledge-graph", "retrieval:connected-subgraph", "llm:explain-prompt", "evidence:target-node"),
        ),
    ),
    ProjectManifest(
        "codeboarding",
        "8c3f2218c3ecab1294902db5914f5e526f78524d",
        "github.com/codeboarding/codeboarding",
        ("codeboarding_cli/commands/full_analysis.py", "static_analyzer/engine/call_graph_builder.py"),
        (
            _cap("full-analysis", "全量仓库分析", "从 CLI 驱动完整静态分析与产物生成。", "codeboarding_cli/commands/full_analysis.py", "全量入口", "framework:cli-workflow", "incremental:full-baseline", "evidence:analysis-artifacts"),
            _cap("call-graph", "跨文件调用图构建", "把语义分析结果转换为可定位的调用图节点与边。", "static_analyzer/engine/call_graph_builder.py", "调用图构建", "parser:language-adapter", "store:call-graph", "retrieval:definition-resolution", "evidence:call-sites"),
            _cap("component-clustering", "架构组件聚类", "基于调用图聚类并把叶簇组合成顶层组件。", "static_analyzer/cluster_helpers.py", "组件聚类", "store:call-graph", "retrieval:leiden-clustering", "incremental:cluster-cache", "evidence:cluster-file-map"),
        ),
    ),
    ProjectManifest(
        "deepwiki-open",
        "4181daa5ebde79a1baf8e92a09dd874f8b74411b",
        "github.com/asyncfuncai/deepwiki-open",
        ("api/services/codemap.py", "src/components/CodeMap.tsx"),
        (
            _cap("codemap-router", "CodeMap API 边界", "暴露代码地图生成、状态和结果查询接口。", "api/routers/codemap.py", "HTTP 边界", "framework:fastapi", "evidence:request-schema"),
            _cap("codemap-service", "CodeMap 生成服务", "编排仓库分析、阶段事件与代码地图产物。", "api/services/codemap.py", "服务编排", "framework:service-layer", "llm:codemap-generation", "evidence:citations"),
            _cap("wiki-structure", "Wiki 结构解析", "解析并规范化 Wiki 页面与章节层级。", "api/services/wiki/structure.py", "结构解析", "parser:xml-and-regex-fallback", "evidence:page-source"),
            _cap("codemap-ui", "交互式代码地图", "展示生成阶段、图内容和可点击源码引用。", "src/components/CodeMap.tsx", "地图 UI", "framework:react", "evidence:citation-chip", "ui:codemap"),
            _cap("code-viewer", "源码定位查看器", "加载文件内容并高亮引用的源码行区间。", "src/components/CodeViewer.tsx", "源码 UI", "framework:react", "retrieval:file-content-api", "evidence:line-highlight", "ui:code-viewer"),
        ),
    ),
)


def _slice(
    path: str,
    line_start: int,
    line_end: int,
    symbol: str,
    role: str,
    reading_hypothesis: str,
) -> AuditSliceSpec:
    return AuditSliceSpec(path, line_start, line_end, symbol, role, reading_hypothesis)


def _edge(
    source_slice_index: int,
    target_slice_index: int,
    callsite_line_start: int,
    callsite_line_end: int,
    *allowed_kinds: str,
) -> AuditRelationshipSpec:
    if not allowed_kinds:
        raise ValueError("an audited relationship must declare at least one allowed kind")
    if min(source_slice_index, target_slice_index) < 0:
        raise ValueError("audited relationship slice indexes must be non-negative")
    if not (1 <= callsite_line_start <= callsite_line_end):
        raise ValueError("audited relationship callsite range is invalid")
    return AuditRelationshipSpec(
        source_slice_index,
        target_slice_index,
        callsite_line_start,
        callsite_line_end,
        tuple(allowed_kinds),
    )


def _tech(tag: str, slice_index: int, claim_scope: str) -> TechnologyEvidenceSpec:
    return TechnologyEvidenceSpec(tag, slice_index, claim_scope)


# Every item below is a version-pinned teaching contract, not a graph-walk seed.
# The two-or-more role slices are independently line/hash bound and the technology
# claims point to the exact slice that supports their deliberately narrow scope.
CAPABILITY_AUDIT_CONTRACTS: dict[tuple[str, str], CapabilityAuditContract] = {
    ("sourcebridge", "graph-store"): CapabilityAuditContract(
        slices=(
            _slice("internal/graph/store.go", 225, 256, "Store", "状态所有权", "constructed-by:NewStore"),
            _slice("internal/graph/store.go", 259, 285, "NewStore", "内存索引初始化", "constructs:Store"),
            _slice("internal/graph/store.go", 305, 380, "StoreIndexResult", "索引结果写入", "populates:Store"),
            _slice("internal/graph/store.go", 1137, 1200, "SearchContent/GetCallers/GetCallees", "图与内容查询", "reads:Store"),
        ),
        technology=(
            _tech("store:in-memory", 0, "Store 以进程内 map 和切片持有仓库、符号与调用图状态；不声称持久化后端。"),
            _tech("retrieval:graph-query", 3, "查询面读取符号、文件与正反向调用图；不声称向量或语义检索。"),
        ),
        relationships=(
            _edge(2, 0, 305, 305, "receiver-type"),
        ),
    ),
    ("sourcebridge", "execution-path"): CapabilityAuditContract(
        slices=(
            _slice("internal/graph/execution_path.go", 22, 65, "TraceLikelyExecutionPath", "路径编排", "calls:traceCallerChain/selectPrimaryNeighbor"),
            _slice("internal/graph/execution_path.go", 68, 85, "traceCallerChain", "上游调用者回溯", "feeds:TraceLikelyExecutionPath"),
            _slice("internal/graph/execution_path.go", 88, 129, "selectPrimaryNeighbor", "候选邻居评分", "selects:ExecutionNode"),
            _slice("internal/graph/execution_path.go", 131, 140, "executionNodeFromSymbol", "源码定位投影", "maps:StoredSymbol-to-ExecutionNode"),
        ),
        technology=(
            _tech("store:graph", 0, "路径函数通过 GraphStore 读取符号和调用边；不声明具体存储介质。"),
            _tech("retrieval:execution-path", 0, "组合 caller/current/callee 形成保守路径；不声明运行时 trace。"),
            _tech("evidence:source-location", 3, "ExecutionNode 携带文件与起止行；不声明内容哈希。"),
        ),
        relationships=(
            _edge(0, 1, 43, 43, "calls"),
            _edge(1, 2, 73, 73, "calls"),
            _edge(0, 2, 52, 52, "calls"),
            _edge(0, 3, 47, 47, "calls"),
        ),
    ),
    ("sourcebridge", "code-tour"): CapabilityAuditContract(
        slices=(
            _slice("workers/knowledge/code_tour.py", 75, 122, "generate_code_tour", "提示词、模型调用与停止点构造", "produces:raw_stops"),
            _slice("workers/knowledge/code_tour.py", 38, 50, "TourStop", "结构化停止点模型", "instantiated-by:generate_code_tour"),
            _slice("workers/knowledge/code_tour.py", 128, 181, "generate_code_tour", "路径与证据门禁", "calls:evaluate_evidence_gate"),
        ),
        technology=(
            _tech("llm:provider-adapter", 0, "通过 LLMProvider 适配器完成确定温度的模型调用；不声明供应商。"),
            _tech("retrieval:graph-context", 0, "snapshot_json 被组装进导览提示上下文；不声明检索算法。"),
            _tech("evidence:source-citation", 2, "停止点以真实路径和行范围通过证据门；不声明行为正确性。"),
        ),
        relationships=(
            _edge(0, 1, 116, 116, "calls"),
        ),
    ),
    ("pocketflow-code2tutorial", "tutorial-flow"): CapabilityAuditContract(
        slices=(
            _slice("flow.py", 12, 21, "create_tutorial_flow", "工作流节点实例化", "constructs:workflow-nodes"),
            _slice("flow.py", 23, 33, "create_tutorial_flow", "节点顺序与 Flow 起点", "connects:workflow-nodes"),
        ),
        technology=(
            _tech("framework:pocketflow", 1, "使用 >> 连接 Node 并以 Flow(start=...) 建立工作流；不声明调度语义之外的行为。"),
            _tech("llm:workflow-nodes", 0, "流程实例化多个生成型 Node；模型调用细节位于节点实现而非此切片。"),
        ),
    ),
    ("pocketflow-code2tutorial", "tutorial-nodes"): CapabilityAuditContract(
        slices=(
            _slice("nodes.py", 85, 116, "IdentifyAbstractions.prep", "仓库上下文组装", "feeds:IdentifyAbstractions.exec"),
            _slice("nodes.py", 241, 287, "AnalyzeRelationships.prep", "抽象关系上下文", "feeds:AnalyzeRelationships.exec"),
            _slice("nodes.py", 410, 470, "OrderChapters", "章节排序输入", "orders:abstractions"),
            _slice("nodes.py", 538, 620, "WriteChapters.prep", "章节写作批次", "produces:chapters"),
            _slice("nodes.py", 754, 830, "CombineTutorial.prep", "教程与图合并", "combines:chapters-and-relationships"),
        ),
        technology=(
            _tech("parser:repository-context", 0, "把文件路径与内容组装为模型上下文；不声明语法 AST 解析。"),
            _tech("framework:pocketflow", 1, "能力由 PocketFlow Node 生命周期方法承载；不声明其他工作流引擎。"),
            _tech("llm:prompted-generation", 2, "章节顺序由提示上下文驱动的生成节点处理；不声明输出正确性。"),
            _tech("evidence:file-reference", 3, "章节批次保留相关文件索引和内容映射；不声明行级引用。"),
        ),
    ),
    ("openwiki", "skeleton-critic"): CapabilityAuditContract(
        slices=(
            _slice("src/agent/skeleton_critic.ts", 7, 24, "SKELETON_CRITIC_SYSTEM_PROMPT", "独立源码审查流程", "instructs:SKELETON_CRITIC_SUBAGENT"),
            _slice("src/agent/skeleton_critic.ts", 25, 54, "SKELETON_CRITIC_SYSTEM_PROMPT", "结构化裁决与通过门", "constrains:review-output"),
            _slice("src/agent/skeleton_critic.ts", 56, 68, "resolveSkeletonCriticSubagents", "子 Agent 注册条件", "registers:SKELETON_CRITIC_SUBAGENT"),
        ),
        technology=(
            _tech("llm:subagent", 2, "以 SubAgent 配置注册独立 critic；不声明具体模型或运行时。"),
            _tech("evidence:coverage-critique", 0, "审查要求先映射源码、实现符号与测试再判断骨架；不声明自动验证。"),
        ),
    ),
    ("openwiki", "wiki-link-validator"): CapabilityAuditContract(
        slices=(
            _slice("src/agent/wiki-link-validator.ts", 92, 140, "validateWikiInternalLinks", "扫描、校验与回写编排", "calls:validateLink/stampBrokenLinks"),
            _slice("src/agent/wiki-link-validator.ts", 332, 385, "extractMarkdownLinks/buildHeadingAnchors", "Markdown 链接与锚点提取", "feeds:validateWikiInternalLinks"),
            _slice("src/agent/wiki-link-validator.ts", 402, 457, "slugifyHeading/resolveRepoLinkPath", "锚点规范化与路径解析", "validates:link-target"),
        ),
        technology=(
            _tech("parser:markdown", 1, "用 Markdown 链接与标题规则提取 href 和 GitHub 风格锚点；不声明完整 Markdown AST。"),
            _tech("retrieval:repository-files", 0, "通过 BackendProtocolV2 枚举并读取 wiki/仓库文件；不声明远程搜索。"),
            _tech("evidence:link-validation", 0, "报告文件、链接和问题计数并把失败定位到源行；不声明内容正确性。"),
        ),
    ),
    ("openwiki", "ingestion"): CapabilityAuditContract(
        slices=(
            _slice("src/ingestion/ingestion.ts", 63, 103, "runOpenWikiIngestion", "连接器注册与逐源编排", "calls:runSourceIngestion"),
            _slice("src/ingestion/ingestion.ts", 122, 206, "runSourceIngestion", "拉取、Agent 更新与错误收敛", "produces:SourceIngestionResult"),
            _slice("src/ingestion/ingestion.ts", 220, 247, "resolveIngestionSourceInstances", "摄取源筛选", "filters:sourceInstances"),
            _slice("src/ingestion/ingestion.ts", 347, 359, "createSourceSynthesisPolicy", "跨源写入策略", "guides:agent-output"),
        ),
        technology=(
            _tech("framework:connector-registry", 0, "从注册表解析 ConnectorRuntime 并逐源执行；不声明插件隔离。"),
            _tech("store:backend-adapter", 1, "以 local-wiki 输出模式把结果交给 Agent 写入后端；不声明具体数据库。"),
            _tech("incremental:ingestion-window", 1, "连接器拉取显式使用 INGESTION_WINDOW_HOURS；不声明文件级 diff。"),
            _tech("llm:agent-run", 1, "拉取后调用 runOpenWikiAgent 更新知识；不声明模型供应商。"),
        ),
    ),
    ("understand-anything", "context-builder"): CapabilityAuditContract(
        slices=(
            _slice("understand-anything-plugin/src/context-builder.ts", 25, 49, "buildChatContext", "搜索与一跳扩展", "expands:matchedIds"),
            _slice("understand-anything-plugin/src/context-builder.ts", 50, 79, "buildChatContext", "节点、边与层聚合", "returns:ChatContext"),
            _slice("understand-anything-plugin/src/context-builder.ts", 85, 140, "formatContextForPrompt", "提示上下文格式化", "formats:ChatContext"),
        ),
        technology=(
            _tech("store:knowledge-graph", 1, "从 KnowledgeGraph 的 nodes/edges/layers 读取上下文；不声明持久化介质。"),
            _tech("retrieval:search-and-neighbor-expansion", 0, "SearchEngine 检索后沿边扩展一跳；不声明向量检索。"),
            _tech("llm:prompt-context", 2, "把图上下文格式化为供 LLM 消费的 Markdown；不声明模型调用。"),
        ),
    ),
    ("understand-anything", "onboard-builder"): CapabilityAuditContract(
        slices=(
            _slice("understand-anything-plugin/src/onboard-builder.ts", 7, 44, "buildOnboardingGuide", "项目与架构层导览", "reads:KnowledgeGraph.layers"),
            _slice("understand-anything-plugin/src/onboard-builder.ts", 46, 89, "buildOnboardingGuide", "概念与 tour 渐进阅读", "reads:KnowledgeGraph.tour"),
            _slice("understand-anything-plugin/src/onboard-builder.ts", 91, 123, "buildOnboardingGuide", "文件地图与复杂度提示", "renders:standalone-markdown"),
        ),
        technology=(
            _tech("store:knowledge-graph", 0, "直接消费 KnowledgeGraph 的 project/nodes/edges/layers/tour；不声明后端。"),
            _tech("retrieval:layered-tour", 1, "按 layer、concept 与 tour 顺序组织内容；不声明自动执行路径。"),
            _tech("evidence:file-node", 2, "文件地图输出 node.filePath 和摘要；不声明行级证据。"),
        ),
    ),
    ("understand-anything", "explain-builder"): CapabilityAuditContract(
        slices=(
            _slice("understand-anything-plugin/src/explain-builder.ts", 22, 56, "buildExplainContext", "路径或符号目标解析", "selects:targetNode"),
            _slice("understand-anything-plugin/src/explain-builder.ts", 58, 102, "buildExplainContext", "子节点与一跳邻居聚合", "returns:ExplainContext"),
            _slice("understand-anything-plugin/src/explain-builder.ts", 108, 159, "formatExplainPrompt", "定点解释提示格式化", "formats:ExplainContext"),
        ),
        technology=(
            _tech("parser:path-and-symbol-target", 0, "解析 path 或 path:function 并精确匹配图节点；不声明语言语法解析。"),
            _tech("store:knowledge-graph", 1, "从 KnowledgeGraph 节点、边和层读取解释上下文；不声明持久化。"),
            _tech("retrieval:connected-subgraph", 1, "收集 contains 子节点和一跳连接节点；不声明任意深度遍历。"),
            _tech("llm:explain-prompt", 2, "生成结构化解释提示文本；不声明模型响应。"),
            _tech("evidence:target-node", 0, "解释锚定目标节点的 filePath/name；不声明行为级证明。"),
        ),
    ),
    ("codeboarding", "full-analysis"): CapabilityAuditContract(
        slices=(
            _slice("codeboarding_cli/commands/full_analysis.py", 25, 55, "add_arguments", "全量分析 CLI 参数", "configures:full-command"),
            _slice("codeboarding_cli/commands/full_analysis.py", 74, 80, "run_from_args", "本地与远程分发", "dispatches:_run_local/_run_remote"),
            _slice("codeboarding_cli/commands/full_analysis.py", 83, 117, "_run_local", "本地分析与文档渲染", "calls:run_full/render_docs"),
        ),
        technology=(
            _tech("framework:cli-workflow", 0, "以 argparse 子命令承载 full 分析入口；不声明服务端 API。"),
            _tech("incremental:full-baseline", 0, "full 命令暴露 force 跳过缓存语义；不声明增量合并。"),
            _tech("evidence:analysis-artifacts", 2, "本地流程运行分析并渲染文档产物；不声明源码行级引用。"),
        ),
        relationships=(
            _edge(1, 2, 80, 80, "calls"),
        ),
    ),
    ("codeboarding", "call-graph"): CapabilityAuditContract(
        slices=(
            _slice("static_analyzer/engine/call_graph_builder.py", 24, 151, "CallGraphBuilder", "类级分析边界与成员容器", "owns:analysis-state"),
            _slice("static_analyzer/engine/call_graph_builder.py", 45, 122, "CallGraphBuilder.build", "符号、边、层级与包依赖流水线", "produces:LanguageAnalysisResult"),
            _slice("static_analyzer/engine/call_graph_builder.py", 151, 190, "CallGraphBuilder._discover_symbols", "LSP documentSymbol 采集", "populates:SymbolTable"),
            _slice("static_analyzer/engine/call_graph_builder.py", 239, 313, "CallGraphBuilder._postprocess_edges", "调用边去重与构造器扩展", "normalizes:EdgeMap"),
        ),
        technology=(
            _tech("parser:language-adapter", 0, "LanguageAdapter 与 LSPClient 构成按语言分析边界；不声明单一解析器。"),
            _tech("store:call-graph", 1, "把 EdgeMap 转为 CallFlowGraph 并置入分析结果；不声明持久化数据库。"),
            _tech("retrieval:definition-resolution", 1, "适配器选择 definitions 或 references 策略解析边；不声明完备调用图。"),
            _tech("evidence:call-sites", 3, "去重边保留调用位置集合并移除别名自边；不声明运行时调用。"),
        ),
        relationships=(
            _edge(0, 1, 45, 45, "contains"),
            _edge(1, 2, 56, 56, "calls"),
            _edge(0, 2, 151, 151, "contains"),
            _edge(1, 3, 68, 68, "calls"),
        ),
    ),
    ("codeboarding", "component-clustering"): CapabilityAuditContract(
        slices=(
            _slice("static_analyzer/cluster_helpers.py", 48, 65, "build_all_cluster_results", "逐语言聚类与统一 ID", "produces:ClusterResult-map"),
            _slice("static_analyzer/cluster_helpers.py", 133, 160, "_build_meta_graph", "跨簇加权调用图", "builds:meta-graph"),
            _slice("static_analyzer/cluster_helpers.py", 402, 427, "supercluster_by_modularity_peak", "Leiden 分辨率与模块度分组", "partitions:leaf-clusters"),
            _slice("static_analyzer/cluster_helpers.py", 504, 533, "anchored_grouping", "增量身份延续与漂移门", "repairs:previous-grouping"),
        ),
        technology=(
            _tech("store:call-graph", 1, "以 CFG 调用边构建簇级 meta graph；不声明外部图数据库。"),
            _tech("retrieval:leiden-clustering", 2, "按模块度峰值选择 Leiden 分区并吸收剩余簇；不声明唯一最优。"),
            _tech("incremental:cluster-cache", 3, "沿用 previous_owner 并用漂移预算决定重分组；不声明文件索引缓存。"),
            _tech("evidence:cluster-file-map", 0, "ClusterResult 保留 cluster_to_files/file_to_clusters 映射；不声明行级证据。"),
        ),
        relationships=(
            _edge(2, 1, 421, 421, "calls"),
            _edge(3, 1, 530, 530, "calls"),
        ),
    ),
    ("deepwiki-open", "codemap-router"): CapabilityAuditContract(
        slices=(
            _slice("api/routers/codemap.py", 15, 36, "handle_websocket_codemap", "WebSocket NDJSON 边界", "streams:generate_codemap"),
            _slice("api/routers/codemap.py", 40, 49, "codemap_stream", "HTTP 流式回退", "streams:generate_codemap"),
            _slice("api/routers/codemap.py", 53, 68, "codemap_file", "源码文件读取 API", "calls:read_repo_file"),
        ),
        technology=(
            _tech("framework:fastapi", 0, "APIRouter 装饰器绑定 WebSocket 路由；不声明部署服务器。"),
            _tech("evidence:request-schema", 0, "WebSocket JSON 被解析为 CodeMapRequest 后再生成；不声明响应正确性。"),
        ),
    ),
    ("deepwiki-open", "codemap-service"): CapabilityAuditContract(
        slices=(
            _slice("api/services/codemap.py", 46, 65, "_generate_json", "流式模型响应与重试", "calls:_collect_stream"),
            _slice("api/services/codemap.py", 128, 148, "_format_context", "检索片段与真实行范围格式化", "feeds:codemap-prompt"),
            _slice("api/services/codemap.py", 201, 222, "_ground_citations", "引用源码定位", "calls:_locate_snippet"),
            _slice("api/services/codemap.py", 225, 312, "generate_codemap", "检索与阶段事件编排", "calls:RAG/ChatStreamer"),
        ),
        technology=(
            _tech("framework:service-layer", 3, "服务函数编排 RAG、事件与生成步骤；不声明 Web 框架。"),
            _tech("llm:codemap-generation", 0, "ChatStreamer 生成 JSON 并在格式失败时重试；不声明模型供应商。"),
            _tech("evidence:citations", 2, "用真实文件内容重新定位模型引用片段行号；不声明引用语义正确。"),
        ),
        relationships=(
            _edge(3, 0, 274, 274, "calls"),
            _edge(3, 1, 253, 253, "calls"),
            _edge(3, 2, 309, 309, "calls"),
        ),
    ),
    ("deepwiki-open", "wiki-structure"): CapabilityAuditContract(
        slices=(
            _slice("api/services/wiki/structure.py", 70, 82, "_page_from_element", "XML 页面模型映射", "maps:Element-to-WikiPage"),
            _slice("api/services/wiki/structure.py", 85, 114, "_pages_via_regex", "页面正则降级解析", "fallback-for:XML-parse"),
            _slice("api/services/wiki/structure.py", 142, 180, "parse_wiki_structure", "清理、严格解析与降级编排", "produces:WikiStructureModel"),
        ),
        technology=(
            _tech("parser:xml-and-regex-fallback", 2, "优先 ElementTree，失败或空页面时退到受限 regex；不声明通用 XML 修复。"),
            _tech("evidence:page-source", 0, "WikiPage 保留 filePaths 与 relatedPages 字段；不声明行级源码证据。"),
        ),
        relationships=(
            _edge(2, 0, 174, 174, "calls"),
            _edge(2, 1, 180, 180, "calls"),
        ),
    ),
    ("deepwiki-open", "codemap-ui"): CapabilityAuditContract(
        slices=(
            _slice("src/components/CodeMap.tsx", 19, 51, "PHASE_DETAIL/activePhase", "生成阶段状态模型", "drives:progress-view"),
            _slice("src/components/CodeMap.tsx", 53, 65, "CitationChip", "可点击引用芯片", "calls:onCitationClick"),
            _slice("src/components/CodeMap.tsx", 68, 98, "CodeMap", "无数据时的阶段反馈", "renders:progress-view"),
            _slice("src/components/CodeMap.tsx", 100, 154, "CodeMap", "章节、图和源码步骤展示", "renders:CodemapData"),
        ),
        technology=(
            _tech("framework:react", 3, "以 React FC 按 CodemapData 渲染章节组件；不声明状态管理库。"),
            _tech("evidence:citation-chip", 1, "CitationChip 展示文件名与行范围并触发点击；不声明引用有效性。"),
            _tech("ui:codemap", 3, "页面显示章节、Mermaid 图与源码步骤；不声明图布局算法。"),
        ),
    ),
    ("deepwiki-open", "code-viewer"): CapabilityAuditContract(
        slices=(
            _slice("src/components/CodeViewer.tsx", 27, 39, "EXT_LANG/langOf", "文件扩展名语言映射", "configures:SyntaxHighlighter"),
            _slice("src/components/CodeViewer.tsx", 41, 74, "CodeViewer", "按文件缓存源码请求", "fetches:/codemap/file"),
            _slice("src/components/CodeViewer.tsx", 76, 81, "CodeViewer", "高亮区间自动滚动", "locates:data-highlight-anchor"),
            _slice("src/components/CodeViewer.tsx", 89, 140, "CodeViewer", "标签页、行号与区间高亮", "renders:source-content"),
        ),
        technology=(
            _tech("framework:react", 1, "React hooks 管理请求缓存、加载与错误状态；不声明全局状态。"),
            _tech("retrieval:file-content-api", 1, "调用 /codemap/file 获取活动文件并按路径缓存；不声明搜索能力。"),
            _tech("evidence:line-highlight", 3, "按 start/end 行为 SyntaxHighlighter 设置背景与锚点；不声明引用正确性。"),
            _tech("ui:code-viewer", 3, "提供文件标签、路径和可滚动代码视图；不声明编辑能力。"),
        ),
    ),
}


REFERENCE_FILE_SHA256: dict[str, dict[str, str]] = {
    "sourcebridge": {
        "internal/graph/store.go": "bfb4fc09a5681671a480db8757b20cff1f1e3d8e6476a87e967adec21967e6fe",
        "internal/graph/execution_path.go": "5e745168698f904dd54083a16376b3a3bb743ae9cd454ca95ae6cfbac8f1ae13",
        "workers/knowledge/code_tour.py": "a06679ad8011534491d0ca23f4631b3526d390a47a296419d44a1ca31c7a366b",
    },
    "pocketflow-code2tutorial": {
        "flow.py": "67af50f8b00126fb2e9e81237335897fcdf390318a4c96908af1110e236f89cf",
        "nodes.py": "7adf30dd82c3b4bfab9108433983601a81535cdebaf74c696a5d2f0554d50a26",
    },
    "openwiki": {
        "src/agent/skeleton_critic.ts": "097805672960a48b2b2bdc4a4c1e5db3223d60dcc617c0095305f4413567de85",
        "src/agent/wiki-link-validator.ts": "09acf6c15604ac78d6a08fa41caa58839ffb28da552abd9753aa7d211d422bbe",
        "src/ingestion/ingestion.ts": "6dfbdc9a71995f3966fd3d5bf017d6bf846cdfeed55891688aaaafe47dd93882",
    },
    "understand-anything": {
        "understand-anything-plugin/src/context-builder.ts": "1acad5d4617b83dd203345edfb62a0d5239e7b9e7baff23181ee9746de739575",
        "understand-anything-plugin/src/onboard-builder.ts": "f11d220545d5138b79f1686f2b19f9a221027d685d6bcf7fcd298ea009af364f",
        "understand-anything-plugin/src/explain-builder.ts": "d523dcfcb14c127b5630254d813051293416bae96022366eac8bfe6705c3723b",
    },
    "codeboarding": {
        "codeboarding_cli/commands/full_analysis.py": "759dcafa01fef1c644cddd5dc2d5d6015ef4986b809b537f572ea5a3cf648532",
        "static_analyzer/engine/call_graph_builder.py": "5481ffd863d60830e0caaaac4b56dbcfa81f06ecec194f777a7ff49e599c632f",
        "static_analyzer/cluster_helpers.py": "9cbc87dfbb7284ba761deee8e7ca311036a356bb655468eea2cf5a9611a924c2",
    },
    "deepwiki-open": {
        "api/routers/codemap.py": "d0e946efb2f7692aabf8a99b825a87455c917f1e9b1b989801636921b8facafe",
        "api/services/codemap.py": "0a9745aff962aca488cec3a512d3a9da79f1d683f0d46adcfa700749de08ce40",
        "api/services/wiki/structure.py": "4e84f720c0e42f0bf60207be19915a3d4647927b2206a1d09833b7fcbcecac71",
        "src/components/CodeMap.tsx": "f70e5cd58ca50fa9c01051572e687799ab28b26511e9d9c4e1741be751355861",
        "src/components/CodeViewer.tsx": "5894699bb9d6ff16f6eddaa11f2fb9b7370363e3e0860eee9025b2f10a5ff3ee",
    },
}


def _symbol_for_audit_slice(
    symbols: list[SymbolRecord], audit_slice: AuditSliceSpec
) -> SymbolRecord | None:
    # A composite label is useful prose, but it is not an addressable symbol.
    # Keep such a slice location-only instead of borrowing whichever declaration
    # happens to overlap the range.
    if "/" in audit_slice.symbol:
        return None
    name = audit_slice.symbol.strip()
    candidates = [
        symbol
        for symbol in symbols
        if symbol.path == audit_slice.path
        and symbol.line <= audit_slice.line_start
        and symbol.end_line >= audit_slice.line_end
        and (
            symbol.name == name
            or symbol.qualified_name == name
            or symbol.qualified_name.endswith(f".{name}")
        )
    ]
    return min(
        candidates,
        key=lambda item: (
            item.end_line - item.line,
            item.qualified_name,
        ),
    ) if candidates else None


def _relationships_for_audit_steps(
    contract: CapabilityAuditContract,
    step_symbols: list[SymbolRecord | None],
    relationships: list[RelationshipRecord],
) -> dict[int, tuple[RelationshipRecord, AuditRelationshipSpec]]:
    """Resolve typed capability edges and project them onto endpoint steps."""

    matched: list[tuple[AuditRelationshipSpec, RelationshipRecord]] = []
    used_ids: set[str] = set()
    for relationship_spec in contract.relationships:
        try:
            source_slice = contract.slices[relationship_spec.source_slice_index]
            target_slice = contract.slices[relationship_spec.target_slice_index]
            source_symbol = step_symbols[relationship_spec.source_slice_index]
            target_symbol = step_symbols[relationship_spec.target_slice_index]
        except IndexError as error:
            raise ValueError("audited relationship references a missing slice") from error
        if not (
            source_slice.line_start
            <= relationship_spec.callsite_line_start
            <= relationship_spec.callsite_line_end
            <= source_slice.line_end
        ):
            raise ValueError(
                "audited relationship callsite is outside its typed source slice: "
                f"slice={relationship_spec.source_slice_index} "
                f"callsite={relationship_spec.callsite_line_start}-"
                f"{relationship_spec.callsite_line_end}"
            )
        if source_symbol is None or target_symbol is None:
            raise ValueError(
                "audited relationship endpoint does not resolve to an exact symbol: "
                f"{source_slice.role} -> {target_slice.role}"
            )
        candidates = sorted(
            (
                relationship
                for relationship in relationships
                if relationship.id not in used_ids
                and relationship.target_id
                and relationship.source_id == source_symbol.id
                and relationship.target_id == target_symbol.id
                and relationship.kind in relationship_spec.allowed_kinds
                and relationship.path == source_slice.path
                and relationship_spec.callsite_line_start
                <= relationship.line
                <= relationship_spec.callsite_line_end
            ),
            key=lambda item: (item.path, item.line, item.kind, item.id),
        )
        if not candidates:
            raise ValueError(
                "audited relationship contract did not resolve: "
                f"slice {relationship_spec.source_slice_index} ({source_slice.role}) -> "
                f"slice {relationship_spec.target_slice_index} ({target_slice.role}) "
                f"at {relationship_spec.callsite_line_start}-"
                f"{relationship_spec.callsite_line_end} {relationship_spec.allowed_kinds}"
            )
        selected = candidates[0]
        matched.append((relationship_spec, selected))
        used_ids.add(selected.id)

    assigned: dict[int, tuple[RelationshipRecord, AuditRelationshipSpec]] = {}
    # Preserve every capability edge despite the legacy one-edge-per-step shape.
    for relationship_spec, relationship in matched:
        preferred = [
            index
            for index in (
                relationship_spec.target_slice_index,
                relationship_spec.source_slice_index,
            )
            if index not in assigned
        ]
        if not preferred:
            raise ValueError(
                "audited relationship cannot be represented by a distinct step: "
                f"{relationship.id}"
            )
        assigned[preferred[0]] = (relationship, relationship_spec)

    # Fill only the two explicitly typed slice endpoints.  A repeated slice for
    # the same symbol is not automatically part of this capability edge.
    for relationship_spec, relationship in matched:
        for index in (
            relationship_spec.source_slice_index,
            relationship_spec.target_slice_index,
        ):
            if index not in assigned:
                assigned[index] = (relationship, relationship_spec)
    return assigned


def _capability_steps(
    manifest: ProjectManifest,
    spec: CapabilitySpec,
    contents: dict[str, str],
    symbols: list[SymbolRecord],
    relationships: list[RelationshipRecord],
    evidence: EvidenceStore,
) -> list[FeatureStep]:
    contract = CAPABILITY_AUDIT_CONTRACTS[(manifest.project, spec.slug)]
    step_symbols = [
        _symbol_for_audit_slice(symbols, audit_slice)
        for audit_slice in contract.slices
    ]
    step_relationships = _relationships_for_audit_steps(
        contract, step_symbols, relationships
    )
    steps: list[FeatureStep] = []
    for order, audit_slice in enumerate(contract.slices, start=1):
        source = contents[audit_slice.path]
        line_count = len(source.splitlines())
        if not (1 <= audit_slice.line_start <= audit_slice.line_end <= line_count):
            raise ValueError(
                f"invalid audited slice {manifest.project}/{spec.slug}: "
                f"{audit_slice.path}:{audit_slice.line_start}-{audit_slice.line_end}"
            )
        symbol = step_symbols[order - 1]
        matched_relationship = step_relationships.get(order - 1)
        relationship = matched_relationship[0] if matched_relationship else None
        relationship_spec = matched_relationship[1] if matched_relationship else None
        if relationship is not None and relationship_spec is not None:
            source_role = contract.slices[relationship_spec.source_slice_index].role
            target_role = contract.slices[relationship_spec.target_slice_index].role
            relationship_scope = (
                f"resolved-static: `{relationship.kind}` at "
                f"{relationship.path}:{relationship.line}; typed contract "
                f"slice {relationship_spec.source_slice_index} `{source_role}` -> "
                f"slice {relationship_spec.target_slice_index} `{target_role}` "
                f"at {relationship_spec.callsite_line_start}-"
                f"{relationship_spec.callsite_line_end} allows "
                f"{relationship_spec.allowed_kinds}; both endpoints are audited symbols"
            )
            explanation = (
                f"固定版本源码中 `{audit_slice.symbol}` 承担“{audit_slice.role}”。"
                f"索引还解析出一条 `{relationship.kind}` 静态关系（"
                f"{relationship.path}:{relationship.line}）；方向以 relationship 记录为准，"
                "它不证明运行时一定执行。"
            )
            relationship_kind = relationship.kind
        else:
            reason = (
                "复合源码声明无法绑定到单一精确符号"
                if "/" in audit_slice.symbol
                else (
                    "当前分析器未产出覆盖该审计范围的精确符号"
                    if symbol is None
                    else "精确符号与本能力其他审计符号之间没有已解析静态边"
                )
            )
            relationship_scope = f"location-only: {reason}"
            explanation = (
                f"固定版本源码位置 `{audit_slice.path}:{audit_slice.line_start}-{audit_slice.line_end}` "
                f"承担“{audit_slice.role}”。该步骤仅作位置证据：{reason}；"
                f"contract 中的 `{audit_slice.reading_hypothesis}` 是待验证阅读假设，"
                "不是已证明实现流。"
            )
            relationship_kind = "location-only"
        reference = evidence.add(
            audit_slice.path,
            audit_slice.line_start,
            audit_slice.line_end,
            kind="capability-source-audited" if order == 1 else "capability-role-slice",
            confidence="exact",
            analyzer=(
                f"reference-manifest@{manifest.project}@{manifest.commit[:12]}:role:{order}"
            ),
            symbol_id=symbol.id if symbol else None,
        )
        steps.append(
            FeatureStep(
                order=order,
                title=(
                    f"核心职责：{audit_slice.role}"
                    if order == 1
                    else f"协作职责：{audit_slice.role}"
                ),
                explanation=(
                    explanation
                ),
                path=audit_slice.path,
                line_start=audit_slice.line_start,
                line_end=audit_slice.line_end,
                evidence_ids=[reference.id],
                symbol_id=symbol.id if symbol else None,
                relationship_id=relationship.id if relationship else None,
                source_symbol=audit_slice.symbol,
                source_role=audit_slice.role,
                claim_scope=(
                    f"{manifest.project}/{spec.slug}:{audit_slice.role}; "
                    f"{relationship_scope}"
                ),
                snippet_sha256=reference.snippet_sha256,
                relationship_kind=relationship_kind,
            )
        )
    return steps


def _technology_claims(
    manifest: ProjectManifest,
    spec: CapabilitySpec,
    contract: CapabilityAuditContract,
    evidence: EvidenceStore,
) -> tuple[list[str], list[TechnologyClaim], list[str]]:
    configured = {item.tag: item for item in contract.technology}
    if set(configured) != set(spec.technology):
        raise ValueError(
            f"technology audit contract drift for {manifest.project}/{spec.slug}: "
            f"manifest={sorted(spec.technology)!r} contract={sorted(configured)!r}"
        )
    supplied = {item.split(":", 1)[0]: item for item in spec.technology}
    tags: list[str] = []
    claims: list[TechnologyClaim] = []
    evidence_ids: list[str] = []
    for dimension in TECHNOLOGY_DIMENSIONS:
        tag = supplied.get(dimension, f"{dimension}:unknown")
        tags.append(tag)
        value = tag.split(":", 1)[1]
        if value == "unknown":
            claims.append(
                TechnologyClaim(
                    dimension=dimension,
                    value=value,
                    claim_scope="该固定版本能力没有足够源码切片证明此技术维度。",
                    confidence="unknown",
                )
            )
            continue
        technology = configured[tag]
        audit_slice = contract.slices[technology.slice_index]
        reference = evidence.add(
            audit_slice.path,
            audit_slice.line_start,
            audit_slice.line_end,
            kind=f"technology-claim:{dimension}",
            confidence="source-audited",
            analyzer=(
                f"reference-manifest@{manifest.project}@{manifest.commit[:12]}:technology:{tag}"
            ),
        )
        evidence_ids.append(reference.id)
        claims.append(
            TechnologyClaim(
                dimension=dimension,
                value=value,
                claim_scope=technology.claim_scope,
                confidence="source-audited",
                evidence_ids=[reference.id],
                source_path=audit_slice.path,
            )
        )
    return tags, claims, evidence_ids


def _normalize_remote(value: str | None) -> str:
    remote = str(value or "").strip()
    if not remote:
        return ""
    if remote.startswith("git@") and ":" in remote:
        host, repository = remote[4:].split(":", 1)
        normalized = f"{host}/{repository}"
    else:
        parsed = urlsplit(remote)
        if not parsed.hostname or parsed.query or parsed.fragment:
            return ""
        normalized = f"{parsed.hostname}{parsed.path}"
    return normalized.lower().rstrip("/").removesuffix(".git")


def _verified_manifest(
    project_snapshot: ProjectSnapshot | None,
    paths: set[str],
) -> ProjectManifest | None:
    """Match a curated snapshot only after Git identity is independently known.

    File hashes still gate every capability below.  This identity gate prevents
    copied reference files in an unrelated or non-Git directory from inheriting
    a fixed-commit ``source-audited`` label.
    """

    if (
        project_snapshot is None
        or not project_snapshot.is_git
        or not project_snapshot.git_root
        or not project_snapshot.commit
        or not project_snapshot.remote
    ):
        return None
    try:
        if Path(project_snapshot.git_root).resolve() != Path(project_snapshot.path).resolve():
            return None
    except (OSError, ValueError):
        return None
    remote = _normalize_remote(project_snapshot.remote)
    commit = project_snapshot.commit.lower()
    return next(
        (
            item
            for item in REFERENCE_MANIFESTS
            if remote == item.canonical_remote
            and commit == item.commit
            and set(item.signature_paths).issubset(paths)
        ),
        None,
    )


def discover_source_audited_capabilities(
    files: list[FileRecord],
    symbols: list[SymbolRecord],
    relationships: list[RelationshipRecord],
    modules: list[ModuleSummary],
    contents: dict[str, str],
    evidence: EvidenceStore,
    *,
    project_snapshot: ProjectSnapshot | None = None,
) -> list[FeatureRecord]:
    paths = {file.path for file in files}
    files_by_path = {file.path: file for file in files}
    manifest = _verified_manifest(project_snapshot, paths)
    if manifest is None:
        return []

    modules_by_name = {module.name: module for module in modules}
    results: list[FeatureRecord] = []
    for spec in manifest.capabilities:
        contract = CAPABILITY_AUDIT_CONTRACTS[(manifest.project, spec.slug)]
        source = contents.get(spec.path)
        if spec.path not in paths or source is None:
            continue
        audited_paths = {audit_slice.path for audit_slice in contract.slices}
        if any(
            path not in paths
            or path not in contents
            or path not in REFERENCE_FILE_SHA256[manifest.project]
            or files_by_path[path].sha256 != REFERENCE_FILE_SHA256[manifest.project][path]
            for path in audited_paths
        ):
            continue
        steps = _capability_steps(
            manifest,
            spec,
            contents,
            symbols,
            relationships,
            evidence,
        )
        technology_tags, technology_claims, technology_evidence_ids = _technology_claims(
            manifest, spec, contract, evidence
        )
        module_name = PurePosixPath(spec.path).parts[0] if "/" in spec.path else "root"
        module = modules_by_name.get(module_name)
        step_evidence_ids = [
            evidence_id for step in steps for evidence_id in step.evidence_ids
        ]
        results.append(
            FeatureRecord(
                id=stable_id("capability", manifest.project, spec.slug, spec.path),
                title=spec.title,
                kind="capability-cluster",
                summary=spec.summary,
                entrypoint=spec.path,
                confidence="source-audited",
                source=f"source-audited-reference-manifest:{manifest.project}@{manifest.commit[:12]}",
                steps=steps,
                component_ids=[module.id] if module else [],
                evidence_ids=list(
                    dict.fromkeys(
                        [*step_evidence_ids, *technology_evidence_ids]
                    )
                ),
                technology_tags=technology_tags,
                technology_claims=technology_claims,
                entry_symbol_id=steps[0].symbol_id if steps else None,
            )
        )
    return results


def reference_ground_truth() -> dict[str, dict[str, object]]:
    """Return the version-pinned probe contract used by regression tests/tools."""

    return {
        manifest.project: {
            "commit": manifest.commit,
            "signature_paths": list(manifest.signature_paths),
            "capability_paths": [spec.path for spec in manifest.capabilities],
            "capability_slugs": [spec.slug for spec in manifest.capabilities],
            "file_sha256": dict(REFERENCE_FILE_SHA256[manifest.project]),
        }
        for manifest in REFERENCE_MANIFESTS
    }
