from __future__ import annotations

import unittest

from repo_teacher.artifacts import enrich_index
from repo_teacher.report import _render_human_decision_guide, render_report


class ReportTest(unittest.TestCase):
    def test_human_capabilities_are_grouped_by_product_axis_and_support_is_collapsed(self) -> None:
        features = [
            {
                "id": "feature_call",
                "title": "实时语音通话",
                "summary": "用户拨入后与 Agent 实时交互。",
                "kind": "capability-cluster",
                "steps": [{"path": "src/call.py", "line_start": 1, "line_end": 5}],
            },
            {
                "id": "feature_migration",
                "title": "数据库迁移",
                "summary": "升级数据库结构。",
                "kind": "capability-cluster",
                "steps": [{"path": "src/migrate.py", "line_start": 1, "line_end": 5}],
            },
        ]
        tutorials = [
            {"feature_id": "feature_call", "human_chapter": {"id": "voice-call"}},
            {"feature_id": "feature_migration", "human_chapter": {"id": "migration"}},
        ]
        overview = {
            "core_product_axes": [
                {
                    "title": "实时语音通话平台",
                    "one_liner": "接入、理解并响应一通实时电话。",
                    "user_outcome": "完成一轮低延迟语音对话",
                    "capability_ids": ["voice-call"],
                }
            ],
            "supporting_capability_ids": ["migration"],
        }

        result = _render_human_decision_guide(
            features, tutorials, "dograh", "/tmp/dograh", overview
        )

        self.assertIn("产品主轴 01", result)
        self.assertIn("实时语音通话平台", result)
        self.assertIn("核心子功能 01", result)
        self.assertIn('<details class="supporting-capabilities">', result)
        self.assertIn("支撑能力 02", result)
        self.assertLess(result.index("实时语音通话平台"), result.index("数据库迁移"))

    def test_waku_report_is_a_human_tutorial_not_an_entrypoint_catalog(self) -> None:
        report = render_report(
            enrich_index(
                {
                    "project": {"name": "Waku", "path": "/tmp/waku-agent"},
                    "stats": {},
                    "features": [
                        {
                            "id": "raw-main",
                            "title": "程序入口：waku/gateway/cli.py · main",
                            "kind": "entrypoint",
                            "entrypoint": "main",
                            "confidence": "exact-entry",
                        },
                        {
                            "id": "graph",
                            "title": "入口候选：waku/graph/engine.py · run_graph",
                            "kind": "entrypoint-candidate",
                            "entrypoint": "run_graph",
                            "confidence": "candidate",
                            "summary": "图工作流候选。",
                            "technology_tags": [
                                "compatibility-corpus:waku-not-curated",
                                "compatibility-mechanism:graph",
                            ],
                            "steps": [
                                {
                                    "order": 1,
                                    "title": "run_graph",
                                    "path": "waku/graph/engine.py",
                                    "line_start": 104,
                                    "line_end": 196,
                                    "evidence_ids": ["graph-source"],
                                }
                            ],
                            "evidence_ids": ["graph-source"],
                        },
                    ],
                    "evidence": [
                        {
                            "id": "graph-source",
                            "path": "waku/graph/engine.py",
                            "line_start": 104,
                            "line_end": 196,
                            "kind": "symbol-definition",
                            "snippet": "def run_graph(...): ...",
                        }
                    ],
                    "symbols": [],
                    "relationships": [],
                }
            )
        )

        visible = report.split('<script id="repo-data"', 1)[0]
        self.assertNotIn("程序入口：waku/gateway/cli.py · main", visible)
        self.assertNotIn("02 · 从哪里进入", visible)
        self.assertNotIn("功能 01 · entrypoint-candidate", visible)
        self.assertIn("这个功能为什么存在", visible)
        self.assertIn("一次任务完整怎么运行", visible)
        self.assertIn("核心机制怎么构建", visible)
        self.assertIn("状态是怎样一步步变化的", visible)
        self.assertIn("真正难点与失败方式", visible)
        self.assertIn("为什么这样设计", visible)
        self.assertIn("它能做什么、不能做什么", visible)
        self.assertIn("如果你要复用", visible)
        self.assertIn("最后再看源码证据", visible)
        self.assertIn('class="human-glance"', visible)
        self.assertIn('class="human-deep-dive mechanism-details"', visible)
        self.assertIn('class="human-deep-dive difficulty-details"', visible)
        self.assertIn('class="human-deep-dive reuse-details"', visible)
        self.assertNotIn('class="difficulty-card" open', visible)
        self.assertIn('class="difficulty-sequence"', visible)
        self.assertIn("运行前按配置动态建图", visible)
        self.assertIn("运行中让 LLM 新增节点", visible)
        self.assertIn("同 wave 节点读取同一个波前", visible)
        self.assertIn("gather node", visible)
        chapter = visible.split('id="feature-001"', 1)[1]
        self.assertLess(chapter.index("一次任务完整怎么运行"), chapter.index("waku/graph/engine.py:104-196"))

    def test_report_is_standalone_searchable_and_embeds_json_safely(self) -> None:
        index = {
            "schema_version": "1.0",
            "project": {
                "name": "<Demo>",
                "path": "/tmp/demo",
                "commit": "1234567890abcdef",
                "branch": "main",
                "dirty": False,
                "license": "MIT",
                "analyzed_at": "2026-08-10T00:00:00+00:00",
            },
            "stats": {
                "files": 1,
                "symbols": 1,
                "relationships": 1,
                "modules": 1,
                "lines": 3,
                "bytes": 42,
                "languages": {"Python": 1},
                "confidence": {"exact": 2},
                "skipped": {},
                "diagnostics": 1,
            },
            "modules": [{"id": "m1", "name": "root", "path": ".", "file_count": 1, "symbol_count": 1, "languages": {"Python": 1}, "entrypoints": ["app.py"]}],
            "files": [{"id": "f1", "path": "app.py", "language": "Python", "size": 42, "lines": 3, "sha256": "abc", "module": "root", "symbols": ["s1"]}],
            "symbols": [{"id": "s1", "file_id": "f1", "path": "app.py", "name": "main", "qualified_name": "main", "kind": "function", "line": 1, "end_line": 3, "analyzer": "python-ast", "confidence": "exact", "parent_id": None, "signature": "", "exported": True}],
            "relationships": [{"id": "r1", "source_id": "f1", "target_id": "s1", "target_name": "main", "kind": "contains", "path": "app.py", "line": 1, "analyzer": "python-ast", "confidence": "exact"}],
            "reading_path": [{"order": 1, "title": "Start", "path": "app.py", "reason": "Entry", "symbol_id": "s1", "confidence": "heuristic"}],
            "diagnostics": [{"path": "app.py", "severity": "warning", "code": "fixture", "message": "</script><script>alert(1)</script>", "line": 1}],
        }

        report = render_report(index)

        self.assertIn("&lt;Demo&gt;", report)
        self.assertIn('id="repo-data"', report)
        self.assertIn('data-view="symbols"', report)
        self.assertIn('id="search"', report)
        self.assertIn("30 秒重点", report)
        self.assertIn("尚未识别出可独立讲解的功能", report)
        self.assertIn("阅读路线", report)
        self.assertIn("继续下钻", report)
        self.assertNotIn("</script><script>alert(1)</script>", report)
        self.assertNotIn('src="http', report)
        self.assertNotIn('<link rel="stylesheet"', report)

    def test_report_leads_with_features_and_connects_steps_to_evidence(self) -> None:
        index = {
            "schema_version": "2.0",
            "project": {"name": "Feature Demo", "path": "/tmp/demo"},
            "stats": {"files": 2, "languages": {"Python": 2}, "skipped": {}},
            "features": [
                {
                    "id": "feature_1",
                    "title": "CLI 命令：index <unsafe>",
                    "kind": "cli-command",
                    "summary": "扫描仓库并产生 </section><script>alert(1)</script> 索引。",
                    "entrypoint": "repo-teacher index",
                    "confidence": "exact",
                    "source": "deterministic-feature-discovery",
                    "technology_tags": [
                        "parser:python-ast", "framework:unknown", "store:unknown",
                        "retrieval:unknown", "llm:unknown", "incremental:unknown",
                        "evidence:source-lines", "ui:unknown",
                    ],
                    "technology_claims": [
                        {
                            "dimension": "parser",
                            "value": "python-ast",
                            "claim_scope": "仅证明 CLI 入口的 AST 解析。",
                            "confidence": "source-audited",
                            "evidence_ids": ["ev_parser"],
                            "source_path": "src/repo_teacher/cli.py",
                        },
                        {
                            "dimension": "evidence",
                            "value": "source-lines",
                            "claim_scope": "仅证明行范围定位。",
                            "confidence": "source-audited",
                            "evidence_ids": ["ev_evidence"],
                            "source_path": "src/repo_teacher/indexer.py",
                        },
                    ],
                    "entry_symbol_id": "symbol_1",
                    "steps": [
                        {
                            "order": 1,
                            "title": "解析 CLI 参数",
                            "explanation": "入口函数把参数传给索引器。",
                            "path": "src/repo_teacher/cli.py",
                            "line_start": 12,
                            "line_end": 24,
                            "evidence_ids": ["ev_source"],
                        },
                        {
                            "order": 2,
                            "title": "构建索引",
                            "explanation": "索引器调用语言分析器。",
                            "path": "src/repo_teacher/indexer.py",
                            "line_start": 30,
                            "line_end": 44,
                            "evidence_ids": ["ev_indexer"],
                        },
                    ],
                    "evidence_ids": ["ev_source", "ev_indexer"],
                    "test_evidence_ids": ["ev_test"],
                }
            ],
            "evidence": [
                {
                    "id": "ev_parser",
                    "path": "src/repo_teacher/cli.py",
                    "line_start": 12,
                    "line_end": 24,
                    "snippet": "def main():\n    return index()",
                    "kind": "technology-claim:parser",
                    "confidence": "source-audited",
                },
                {
                    "id": "ev_evidence",
                    "path": "src/repo_teacher/indexer.py",
                    "line_start": 30,
                    "line_end": 44,
                    "snippet": "def index_repository(): ...",
                    "kind": "technology-claim:evidence",
                    "confidence": "source-audited",
                },
                {
                    "id": "ev_source",
                    "path": "src/repo_teacher/cli.py",
                    "line_start": 12,
                    "line_end": 24,
                    "snippet": "def main():\n    return index()",
                    "kind": "entry-declaration",
                    "confidence": "exact",
                },
                {
                    "id": "ev_indexer",
                    "path": "src/repo_teacher/indexer.py",
                    "line_start": 30,
                    "line_end": 44,
                    "snippet": "def index_repository(): ...",
                    "kind": "symbol-definition",
                    "confidence": "exact",
                },
                {
                    "id": "ev_test",
                    "path": "tests/test_cli.py",
                    "line_start": 8,
                    "line_end": 16,
                    "snippet": "def test_index_command(): ...",
                    "kind": "test-reference",
                    "confidence": "exact",
                },
            ],
            "tutorials": [
                {
                    "feature_id": "feature_1",
                    "opening": "从入口开始阅读。",
                    "closing": "静态结构不证明运行时分支。",
                    "chapters": [
                        {
                            "kind": "purpose-and-entry",
                            "title": "先看结论：用途与入口",
                            "purpose": "理解索引能力。",
                            "entry": {"boundary": "repo-teacher index", "confidence": "exact"},
                        },
                        {
                            "kind": "main-implementation-chain",
                            "title": "再拆解：主实现链与职责",
                            "purpose": "核对角色。",
                            "slices": [{"title": "CLI 入口", "role": "参数解析", "symbol": "main", "path": "src/repo_teacher/cli.py", "line_start": 12, "claim_scope": "只确认 CLI 边界。"}],
                        },
                        {"kind": "error-and-evidence-gaps", "title": "证据缺口与错误边界", "purpose": "继续核对。", "gaps": {"state": "未知"}},
                    ],
                }
            ],
            "codemaps": [
                {
                    "feature_id": "feature_1",
                    "mermaid": "flowchart LR\n  n1 -->|calls| n2",
                    "resolved_edge_ids": ["rel_1"],
                    "reading_order_edge_ids": [],
                    "nodes": [{"id": "n1", "label": "cli.main", "order": 1}, {"id": "n2", "label": "indexer.build", "order": 2}],
                    "edges": [{"source": "cli.main", "target": "indexer.build", "kind": "calls", "semantics": "resolved-static-relationship"}],
                }
            ],
            "coverage": [
                {
                    "feature_id": "feature_1",
                    "score": 80,
                    "status": "signals-present",
                    "checks": {"entrypoint": True, "steps": True, "evidence": True},
                    "scope": "artifact-evidence-completeness",
                    "behavioral_coverage": "unknown",
                    "gaps": ["未发现测试源码到该入口的静态引用"],
                }
            ],
        }

        report = render_report(index)

        self.assertIn("先看 0 个源码审计能力，再按需下钻边界与候选", report)
        self.assertIn('href="#feature-001"', report)
        self.assertIn('id="feature-001"', report)
        self.assertIn("边界 / 候选分组", report)
        self.assertIn("提供什么功能", report)
        self.assertIn("静态实现阅读路径", report)
        self.assertIn("以下顺序用于阅读，不声明真实运行时先后", report)
        self.assertIn("技术证据与未知项", report)
        self.assertIn("八类底层实现信号", report)
        self.assertIn("框架", report)
        self.assertIn("源码位置", report)
        self.assertIn("测试到入口的静态引用（非行为覆盖） <b>1</b>", report)
        self.assertIn("证据完整度与缺口", report)
        self.assertIn("这不是测试覆盖率", report)
        self.assertIn("cli.main", report)
        self.assertIn("indexer.build", report)
        self.assertIn("主实现链与职责", report)
        self.assertIn("只确认 CLI 边界", report)
        self.assertIn("每个已知标签必须有自己的 evidence ID", report)
        self.assertIn("ev_parser", report)
        self.assertIn("仅证明 CLI 入口的 AST 解析", report)
        self.assertNotIn('<pre class="codemap-source">', report)
        self.assertIn('class="source-link" href="file://', report)
        self.assertIn("#L12-L24", report)
        self.assertIn("/tmp/demo/src/repo_teacher/cli.py", report)
        self.assertIn("src/repo_teacher/cli.py:12-24", report)
        self.assertIn("确定性事实", report)
        self.assertLess(report.index("提供什么功能"), report.index("仓库规模"))
        self.assertNotIn("</section><script>alert(1)</script>", report)
        self.assertIn("&lt;unsafe&gt;", report)

    def test_report_css_guards_the_390px_mobile_viewport(self) -> None:
        report = render_report({"project": {"name": "Mobile"}, "stats": {}})

        self.assertIn("overflow-x:hidden", report)
        self.assertIn("grid-template-columns:minmax(0,1.2fr) minmax(0,.8fr)", report)
        self.assertIn("white-space:pre-wrap", report)
        self.assertIn("table{display:block;max-width:100%;overflow-x:auto}", report)
        self.assertIn("@media(max-width:560px)", report)
        self.assertIn(".source-contract,.tutorial-contract{grid-template-columns:1fr}", report)

    def test_report_tolerates_missing_optional_collections_and_fields(self) -> None:
        report = render_report(
            {
                "schema_version": "2.0",
                "project": {},
                "stats": {"languages": {"Unknown": None}, "skipped": None},
                "features": [{"title": "最小功能"}],
            }
        )

        self.assertIn("Unnamed repository", report)
        self.assertIn("最小功能", report)
        self.assertIn("未标注入口", report)
        self.assertIn("当前只能确定功能入口", report)
        self.assertIn('id="repo-data"', report)

    def test_report_groups_routes_by_product_capability_prefix(self) -> None:
        def route(identifier: str, entrypoint: str) -> dict[str, object]:
            return {
                "id": identifier,
                "title": entrypoint,
                "kind": "http-route",
                "entrypoint": entrypoint,
                "confidence": "static-entry",
                "steps": [],
                "evidence_ids": [],
                "test_evidence_ids": [],
            }

        report = render_report(
            {
                "project": {"name": "Grouped API"},
                "stats": {},
                "features": [
                    route("wiki-list", "GET /api/wiki"),
                    route("wiki-build", "POST /api/v1/wiki/build"),
                    route("chat", "POST /chat"),
                ],
            }
        )

        self.assertIn("0 个源码审计能力", report)
        self.assertEqual(report.count("静态确认 HTTP 入口声明 · /wiki"), 2)
        self.assertEqual(report.count("静态确认 HTTP 入口声明 · /chat"), 2)
        self.assertIn("3 个静态确认入口声明", report)

    def test_candidate_route_and_cli_shapes_never_enter_confirmed_boundary_counts(self) -> None:
        report = render_report(
            {
                "project": {"name": "Unbound shapes"},
                "stats": {},
                "features": [
                    {
                        "id": "route-candidate",
                        "title": "HTTP 接口：GET /maybe",
                        "kind": "http-route",
                        "entrypoint": "GET /maybe",
                        "confidence": "candidate",
                        "steps": [],
                    },
                    {
                        "id": "cli-candidate",
                        "title": "CLI 命令：maybe",
                        "kind": "cli-command",
                        "entrypoint": "maybe",
                        "confidence": "candidate",
                        "steps": [],
                    },
                ],
            }
        )

        self.assertIn("<b>0</b><span>静态确认入口声明", report)
        self.assertIn("<b>2</b><span>未确认入口候选", report)
        self.assertNotIn("已确认 HTTP 边界", report)
        self.assertNotIn("已确认 CLI 边界", report)
        self.assertEqual(
            report.count("只确认同名符号存在，尚无可执行标记证明它是运行入口。"),
            2,
        )
        self.assertNotIn("只确认运行边界声明", report)

    def test_static_entry_declarations_do_not_claim_runtime_reachability(self) -> None:
        report = render_report(
            {
                "project": {"name": "Static only"},
                "stats": {},
                "features": [
                    {
                        "id": "route",
                        "title": "GET /health",
                        "kind": "http-route",
                        "entrypoint": "GET /health",
                        "confidence": "exact-entry",
                        "steps": [],
                    }
                ],
            }
        )

        self.assertIn("静态确认入口声明", report)
        self.assertIn("可运行性与实际可达性未知", report)
        self.assertNotIn("可触发入口", report)
        self.assertNotIn("可直接触发", report)
        self.assertNotIn("运行边界已确认", report)

    def test_source_audited_capabilities_precede_boundaries_and_single_nodes_are_not_maps(self) -> None:
        report = render_report(
            {
                "project": {"name": "Priority Demo"},
                "stats": {},
                "features": [
                    {
                        "id": "route",
                        "title": "GET /health",
                        "kind": "http-route",
                        "entrypoint": "GET /health",
                        "confidence": "exact-entry",
                        "steps": [],
                    },
                    {
                        "id": "capability",
                        "title": "图索引",
                        "kind": "capability-cluster",
                        "entrypoint": "graph/store.py",
                        "confidence": "source-audited",
                        "steps": [
                            {
                                "order": 1,
                                "title": "Store",
                                "path": "graph/store.py",
                                "line_start": 1,
                            }
                        ],
                    },
                ],
                "codemaps": [
                    {
                        "feature_id": "capability",
                        "nodes": [{"id": "store", "label": "Store", "order": 1}],
                        "edges": [],
                    }
                ],
            }
        )

        self.assertLess(
            report.index("<h3>源码审计能力</h3>"),
            report.index("<h3>静态确认 HTTP 入口声明 · /health</h3>"),
        )
        self.assertIn("<strong>单点源码定位</strong>", report)

    def test_source_audited_report_leads_with_human_capability_and_selection_guide(self) -> None:
        report = render_report(
            {
                "project": {
                    "name": "PocketFlow Tutorial",
                    "path": "/tmp/pocketflow-code2tutorial",
                },
                "stats": {},
                "features": [
                    {
                        "id": "tutorial-flow",
                        "title": "教程工作流编排",
                        "kind": "capability-cluster",
                        "summary": "把分析、关系整理和章节写作组织成可执行流程。",
                        "entrypoint": "flow.py",
                        "confidence": "source-audited",
                        "technology_tags": [
                            "framework:pocketflow",
                            "llm:workflow-nodes",
                        ],
                        "technology_claims": [
                            {
                                "dimension": "framework",
                                "value": "pocketflow",
                                "claim_scope": "用固定 DAG 编排教程阶段。",
                                "evidence_ids": ["ev-flow"],
                                "source_path": "flow.py",
                            }
                        ],
                        "steps": [
                            {
                                "order": 1,
                                "title": "create_tutorial_flow",
                                "source_role": "教程阶段编排",
                                "explanation": "连接抓仓、抽象识别、关系整理、分章和合并。",
                                "path": "flow.py",
                                "line_start": 12,
                                "line_end": 33,
                                "evidence_ids": ["ev-flow"],
                            }
                        ],
                        "evidence_ids": ["ev-flow"],
                    }
                ],
                "evidence": [
                    {
                        "id": "ev-flow",
                        "path": "flow.py",
                        "line_start": 12,
                        "line_end": 33,
                        "snippet": "fetch >> identify >> analyze >> order >> write >> combine",
                    }
                ],
                "tutorials": [
                    {
                        "feature_id": "tutorial-flow",
                        "teaching_contract": {
                            "reuse_boundary": {
                                "reusable": ["复用六阶段总—分—总教学编排。"],
                                "must_reverify": ["不要复用全仓文本一次塞入模型的输入策略。"],
                            }
                        },
                        "chapters": [],
                    }
                ],
            }
        )

        self.assertIn("这个项目有哪些功能", report)
        self.assertIn("技术选型怎么用", report)
        self.assertIn("教程工作流编排", report)
        self.assertIn("固定 DAG 编排教程阶段", report)
        self.assertIn("复用六阶段总—分—总教学编排", report)
        self.assertIn("不要复用全仓文本一次塞入模型", report)
        self.assertIn("flow.py:12-33", report)
        self.assertLess(report.index("这个项目有哪些功能"), report.index("30 秒重点"))

    def test_report_does_not_promote_entrypoints_when_semantic_capabilities_are_absent(self) -> None:
        report = render_report(
            {
                "project": {"name": "Unknown App", "path": "/tmp/unknown-app"},
                "stats": {},
                "features": [
                    {
                        "id": "main",
                        "title": "程序入口：main.py · main",
                        "kind": "entrypoint",
                        "summary": "静态入口声明。",
                        "entrypoint": "main",
                        "confidence": "exact-entry",
                        "steps": [],
                    }
                ],
            }
        )

        self.assertIn("尚未形成可用于技术选型的功能语义层", report)
        self.assertIn("入口、类和函数只能作为证据", report)
        self.assertNotIn("<h2>这个项目有哪些功能？</h2>", report)

    def test_report_groups_executable_files_by_meaningful_launcher_directory(self) -> None:
        report = render_report(
            {
                "project": {"name": "Launcher Groups"},
                "stats": {},
                "features": [
                    {"id": "cli", "kind": "entrypoint", "entrypoint": "src/cli/cli.tsx", "steps": []},
                    {"id": "visual", "kind": "entrypoint", "entrypoint": "src/visualize/server.ts", "steps": []},
                ],
            }
        )

        self.assertIn("已确认程序入口 · src/cli", report)
        self.assertIn("已确认程序入口 · src/visualize", report)

    def test_curated_report_compares_all_six_reference_mechanisms_and_boundaries(self) -> None:
        report = render_report(
            {
                "project": {
                    "name": "SourceBridge",
                    "path": "/Volumes/T7/workspace/ontology/graph/repo/sourcebridge",
                },
                "stats": {},
                "features": [],
            }
        )

        for project in (
            "sourcebridge",
            "pocketflow-code2tutorial",
            "openwiki",
            "understand-anything",
            "codeboarding",
            "deepwiki-open",
        ):
            self.assertIn(project, report)
        self.assertIn("internal/graph/execution_path.go:22-140", report)
        self.assertIn("nodes.py:85-116,241-287", report)
        self.assertIn("src/agent/wiki-link-validator.ts:92-457", report)
        self.assertIn("understand-anything-plugin/src/context-builder.ts:25-140", report)
        self.assertIn("static_analyzer/engine/call_graph_builder.py:24-313", report)
        self.assertIn("src/components/CodeViewer.tsx:27-140", report)
        self.assertEqual(report.count("当前仓库 · sourcebridge"), 1)
        self.assertGreaterEqual(report.count("差异 / 未采用："), 6)

    def test_waku_is_reported_as_compatibility_corpus_not_curated_ranking(self) -> None:
        report = render_report(
            {
                "project": {
                    "name": "Waku",
                    "path": "/Volumes/T7/workspace/ontology/graph/repo/waku-agent",
                },
                "stats": {},
                "features": [
                    {
                        "id": "memory",
                        "title": "Memory：长期记忆与周期整理",
                        "summary": "把对话中的稳定事实整理到长期记忆。",
                        "kind": "entrypoint-candidate",
                        "entrypoint": "consolidate_if_due",
                        "technology_tags": [
                            "compatibility-corpus:waku-not-curated",
                            "compatibility-mechanism:memory",
                        ],
                        "technology_claims": [
                            {"dimension": "store", "value": "unknown"}
                        ],
                        "steps": [
                            {
                                "path": "waku/memory/consolidation.py",
                                "relationship_id": "rel-memory",
                            }
                        ],
                    },
                    {
                        "id": "loop",
                        "title": "Agent Loop：推理、工具调用与终止条件",
                        "summary": "在一次任务内反复执行 reason → act → observe。",
                        "kind": "entrypoint-candidate",
                        "entrypoint": "run_loop",
                        "technology_tags": [
                            "compatibility-corpus:waku-not-curated",
                            "compatibility-mechanism:loop",
                        ],
                        "technology_claims": [],
                        "steps": [{"path": "waku/loop/agent.py"}],
                    },
                ],
            }
        )

        self.assertIn("这个项目有哪些功能", report)
        self.assertIn("技术选型怎么用", report)
        self.assertIn("底层机制", report)
        self.assertIn("复用建议", report)
        self.assertIn("先理解功能，再核对实现入口与源码证据", report)
        self.assertLess(
            report.index("这个项目有哪些功能"),
            report.index("先理解功能，再核对实现入口与源码证据"),
        )
        self.assertIn("Memory：长期记忆与周期整理", report)
        self.assertIn("Agent Loop：推理、工具调用与终止条件", report)
        self.assertIn("2 组功能候选", report)
        self.assertNotIn("先看 0 个源码审计能力", report)
        self.assertIn("Waku：单独验证，不进入六仓 curated 技术排名", report)
        self.assertIn("1 条已解析静态关系", report)
        self.assertIn("1 个未知技术维度", report)
        self.assertIn("waku/memory/consolidation.py", report)
        self.assertIn('href="#feature-001"', report)
        self.assertIn('href="#feature-002"', report)
        self.assertIn('id="feature-001"', report)
        self.assertIn('id="feature-002"', report)
        self.assertLess(report.index('href="#feature-001"'), report.index('id="feature-001"'))

    def test_feature_report_teaches_difficulties_as_runtime_contracts(self) -> None:
        index = {
            "project": {"name": "Waku", "path": "/tmp/waku-agent"},
            "stats": {},
            "features": [
                {
                    "id": "graph",
                    "title": "入口候选：waku/graph/engine.py · run_graph",
                    "kind": "entrypoint-candidate",
                    "entrypoint": "run_graph",
                    "confidence": "candidate",
                    "summary": "图工作流候选。",
                    "technology_tags": [
                        "compatibility-corpus:waku-not-curated",
                        "compatibility-mechanism:graph",
                    ],
                    "steps": [],
                }
            ],
            "tutorials": [
                {
                    "feature_id": "graph",
                    "chapters": [],
                    "difficulty_map": {
                        "summary": "难点不在创建节点，而在并发后仍保持确定性。",
                        "items": [
                            {
                                "id": "wave-barrier",
                                "category": "concurrency",
                                "title": "Wave 是状态提交屏障，不只是并发批次",
                                "why_hard": "同一波节点必须读到同一个波前状态。",
                                "runtime_steps": [
                                    "计算本波就绪节点",
                                    "复制同一份波前状态",
                                    "并发执行并等待全部结果",
                                    "按稳定顺序合并后再计算下一波",
                                ],
                                "invariants": ["同波节点看不到同波写入"],
                                "naive_failure": "为什么不直接用 asyncio.gather：任务若直接修改共享 dict，会产生时序依赖。",
                                "failure_modes": ["结果随线程完成顺序变化"],
                                "tradeoffs": ["牺牲流水线并行，换取可重复 trace"],
                                "evidence_ids": [],
                                "confidence": "confirmed",
                                "unknowns": ["没有进程崩溃恢复证据"],
                                "reuse_question": "你的节点是否允许观察同批任务的中间写入？",
                            }
                        ],
                        "unknowns": ["持久 checkpoint 未证明"],
                    },
                }
            ],
        }

        report = render_report(index)

        self.assertIn("真正需要先理解的实现难点", report)
        self.assertIn("Wave 是状态提交屏障，不只是并发批次", report)
        self.assertIn("运行时到底怎么走", report)
        self.assertIn("必须一直成立的不变量", report)
        self.assertIn("如果天真实现会怎样", report)
        self.assertIn("为什么不直接用 asyncio.gather", report)
        self.assertIn("你的节点是否允许观察同批任务的中间写入", report)


if __name__ == "__main__":
    unittest.main()
