from __future__ import annotations

import unittest

from repo_teacher.human_report import (
    build_report_pack,
    compose_human_report,
    human_report_json_schema,
)
from repo_teacher.report import render_report


class HumanReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = {
            "schema_version": "2.0",
            "analysis_fingerprint": "fingerprint-1",
            "project": {
                "name": "Any Repo",
                "path": "/tmp/any-repo",
                "commit": "abc123",
                "branch": "main",
            },
            "stats": {"files": 1},
            "files": [
                {"id": "file_graph", "path": "src/graph.py", "lines": 120, "language": "Python"}
            ],
            "symbols": [],
            "relationships": [],
            "modules": [{"id": "module_graph", "name": "graph", "path": "src"}],
            "reading_path": [],
            "features": [
                {
                    "id": "raw_entry",
                    "title": "程序入口：src/graph.py · main",
                    "summary": "静态入口。",
                    "entrypoint": "main",
                    "kind": "entrypoint",
                    "evidence_ids": ["ev_graph"],
                    "steps": [],
                }
            ],
            "evidence": [
                {
                    "id": "ev_graph",
                    "path": "src/graph.py",
                    "line_start": 10,
                    "line_end": 35,
                    "snippet": "def run_graph(state): ...",
                    "kind": "symbol-definition",
                    "confidence": "exact",
                }
            ],
            "tutorials": [],
            "codemaps": [],
            "coverage": [],
            "diagnostics": [],
        }
        self.narrative = {
            "schema_version": "repo-teacher-human-report/v1",
            "project": {
                "commit": "abc123",
                "analysis_fingerprint": "fingerprint-1",
                "overview": {
                    "one_liner": "Any Repo 是一个把已知任务按依赖图并发执行的本地工作流引擎。",
                    "product_type": "本地工作流引擎",
                    "primary_user": "需要编排确定任务的开发者",
                    "problem": "在保持状态确定性的前提下并发执行节点。",
                    "core_product_axes": [
                        {
                            "id": "workflow-engine",
                            "title": "确定性图工作流",
                            "one_liner": "把任务建成依赖图，再按就绪波次推进。",
                            "user_outcome": "应用得到按依赖完成并合并后的最终状态。",
                            "end_to_end_flow": ["提交状态", "执行就绪节点", "合并并路由"],
                            "capability_ids": ["graph-workflow"],
                            "source_refs": [
                                {"path": "src/graph.py", "line_start": 10, "line_end": 35, "claim": "图执行主链。"}
                            ],
                        }
                    ],
                    "supporting_capability_ids": [],
                    "core_journey": [
                        {"stage": "提交", "actor": "应用", "action": "提交初始状态", "state_change": "生成就绪集", "next": "调度"},
                        {"stage": "调度", "actor": "执行器", "action": "并发执行就绪节点", "state_change": "产生节点更新", "next": "提交"},
                        {"stage": "路由", "actor": "Router", "action": "根据合并状态选下一节点", "state_change": "更新就绪集", "next": "结束或下一波"},
                    ],
                    "architecture_summary": "单进程内的图调度器管理节点、依赖和共享状态。",
                    "architecture_style": "分层模块化单体，不是 DDD。",
                    "engineering_structure": {
                        "repository_shape": "单包仓库",
                        "architecture_pattern": "分层模块化单体，不是 DDD",
                        "pattern_reasoning": "业务规则、调度与状态实现共存在 src，没有独立领域层和端口/适配器边界。",
                        "frontend_organization": "未发现前端代码。",
                        "backend_organization": "src 封装图定义、调度和状态合并。",
                        "worker_and_async_organization": "未发现独立 Worker；并发在单进程执行器内。",
                        "shared_contracts": "节点和状态协议与执行器同包。",
                        "dependency_rule": "上层应用依赖图 API，调度器不依赖业务节点实现。",
                        "media_organization": "未发现语音或视频媒体链。",
                        "source_refs": [{"path": "src/graph.py", "line_start": 10, "line_end": 35, "claim": "图定义与调度在同一实现模块。"}],
                    },
                    "execution_model": "执行器以 wave 为单位执行，无就绪节点时结束。",
                    "runtime_components": [
                        {"name": "Graph", "responsibility": "保存节点和边", "communication": "直接函数调用", "state": "拓扑和路由", "source_refs": [{"path": "src/graph.py", "line_start": 10, "line_end": 20, "claim": "Graph 定义拓扑。"}]},
                        {"name": "Executor", "responsibility": "执行就绪节点", "communication": "调用节点函数", "state": "共享状态快照", "source_refs": [{"path": "src/graph.py", "line_start": 21, "line_end": 35, "claim": "Executor 提交每波更新。"}]},
                    ],
                    "frontend_backend_boundary": "未发现网络前后端边界。",
                    "data_and_state": "图和共享状态位于进程内存。",
                    "deployment_shape": "作为 Python 包嵌入应用。",
                    "code_organization": [
                        {"path": "src", "responsibility": "图调度", "layer": "核心执行层", "boundary": "不包含业务节点", "source_refs": [{"path": "src/graph.py", "line_start": 10, "line_end": 35, "claim": "src 是核心实现。"}]},
                        {"path": "src/graph.py", "responsibility": "图定义与执行", "layer": "核心模块", "boundary": "对外暴露 run_graph", "source_refs": [{"path": "src/graph.py", "line_start": 10, "line_end": 35, "claim": "run_graph 是核心边界。"}]},
                    ],
                    "differentiator": "以 wave 隔离并发读写。",
                    "not_this": ["不是分布式工作流平台", "不是动态 Agent Loop"],
                    "source_refs": [
                        {"path": "src/graph.py", "line_start": 10, "line_end": 15, "claim": "图对象定义节点。"},
                        {"path": "src/graph.py", "line_start": 16, "line_end": 25, "claim": "执行器计算就绪集。"},
                        {"path": "src/graph.py", "line_start": 26, "line_end": 35, "claim": "路由选择下一节点。"},
                    ],
                    "capability_order": ["graph-workflow"],
                },
            },
            "generator": {"kind": "codex", "model": "current-session"},
            "chapters": [
                {
                    "id": "graph-workflow",
                    "title": "Graph Workflow",
                    "summary": "把已知任务组织成显式依赖图。",
                    "mechanism": "graph",
                    "question": "怎样并发执行节点而不破坏状态确定性？",
                    "use_when": "任务形状可预先画出。",
                    "distinguish": "Graph 固定流程；Loop 动态发现步骤。",
                    "source_feature_ids": ["raw_entry"],
                    "evidence_ids": ["ev_graph"],
                    "source_refs": [
                        {"path": "src/graph.py", "line_start": 10, "line_end": 35,
                         "claim": "run_graph 计算就绪节点并执行路由。"}
                    ],
                    "mechanism_model": {
                        "plain_summary": "Router 不是执行节点；它读取已提交状态并选择下一条分支。",
                        "storage": "Graph 保存节点、边、路由和共享状态。",
                        "write_path": "节点返回更新，执行器在整波结束后统一提交。",
                        "read_path": "调度器选择依赖已经触发的节点。",
                        "control_loop": "只要还有 wave，就执行、合并并计算下一波。",
                        "decision_rules": "代码路由器把 label 映射到预注册目标。",
                        "termination": "没有就绪节点或命中步骤上限时停止。",
                        "dynamic_behavior": "运行前构图；运行中不能安全修改拓扑。",
                        "worked_example": ["START 释放 A 和 B", "join 等待二者", "router 选择 C"],
                    },
                    "runtime_story": {
                        "trigger": "应用提交初始状态。",
                        "owner": "图执行器。",
                        "output": "合并状态。",
                        "consumer": "上层应用。",
                        "steps": ["建图", "计算就绪节点", "执行", "合并", "路由"],
                    },
                    "construction": {
                        "explanation": "节点、边和路由组成图。",
                        "objects": [
                            {"name": "Node", "role": "执行单元"},
                            {"name": "Edge", "role": "依赖"},
                            {"name": "Router", "role": "分支"},
                            {"name": "State", "role": "数据"},
                        ],
                    },
                    "state_flow": [
                        {"stage": "开始", "reads": "输入", "writes": "ready", "why_next": "依赖满足"},
                        {"stage": "执行", "reads": "snapshot", "writes": "updates", "why_next": "节点完成"},
                        {"stage": "提交", "reads": "updates", "writes": "state", "why_next": "重新计算"},
                    ],
                    "design_choices": [
                        {"choice": "显式边", "why": "依赖可见", "cost": "拓扑更啰嗦"},
                        {"choice": "统一提交", "why": "结果确定", "cost": "减少流水并行"},
                        {"choice": "代码路由", "why": "控制流可审计", "cost": "目标需预注册"},
                    ],
                    "boundary": {"supported": ["条件路由"], "unsupported": ["崩溃恢复"]},
                    "reuse_plan": {
                        "take": ["显式依赖"],
                        "adapt": ["增加 checkpoint"],
                        "avoid": ["冒充分布式工作流"],
                        "verify": ["写冲突"],
                    },
                    "difficulty_map": {
                        "summary": "难点在状态提交。",
                        "items": [
                            {
                                "id": "commit-barrier",
                                "category": "state",
                                "title": "提交屏障",
                                "why_hard": "并发完成顺序不稳定。",
                                "runtime_steps": ["等待", "校验", "提交"],
                                "invariants": ["同批读取同一快照"],
                                "naive_failure": "直接修改共享字典。",
                                "failure_modes": ["结果漂移"],
                                "tradeoffs": ["确定性换吞吐"],
                                "reuse_question": "是否允许中间写可见？",
                                "unknowns": [],
                                "evidence_ids": ["ev_graph"],
                            }
                        ],
                        "unknowns": ["运行性能未证明"],
                    },
                }
            ],
        }

    def test_prepare_pack_is_generic_and_tells_model_not_to_promote_entrypoints(self) -> None:
        pack = build_report_pack(self.index)

        self.assertEqual(pack["schema_version"], "repo-teacher-analysis-pack/v1")
        self.assertEqual(pack["project"]["commit"], "abc123")
        self.assertEqual(pack["feature_hints"][0]["id"], "raw_entry")
        self.assertEqual(pack["evidence"][0]["id"], "ev_graph")
        self.assertIn("不能自动当作产品功能", " ".join(pack["instructions"]))
        instructions = " ".join(pack["instructions"])
        self.assertIn("具体用户动作", instructions)
        self.assertIn("本质上是什么", instructions)
        self.assertIn("总—分—总", instructions)
        self.assertIn("标题后的第一句", instructions)
        self.assertIn("PCM 采集 → ASR → LLM → TTS", instructions)
        self.assertIn("for/while/事件循环", instructions)
        self.assertIn("Router 输入/规则/输出", instructions)
        self.assertIn("串行、半双工或全双工", instructions)
        self.assertIn("不变量", instructions)
        self.assertIn("至少 3 个精确 source_refs", instructions)
        self.assertIn("一次任务完整怎么运行", pack["required_chapter_sections"])

    def test_large_pack_truncation_preserves_hint_evidence_closure(self) -> None:
        index = dict(self.index)
        index["features"] = []
        index["evidence"] = []
        index["files"] = [
            {
                "id": f"file_{position}",
                "path": f"src/file_{position}.py",
                "lines": 1,
                "language": "Python",
            }
            for position in range(2_005)
        ]

        pack = build_report_pack(index)

        evidence_ids = {item["id"] for item in pack["evidence"]}
        referenced_ids = {
            identifier
            for hint in pack["feature_hints"]
            for identifier in [
                *hint.get("evidence_ids", []),
                *(
                    evidence_id
                    for step in hint.get("steps", [])
                    for evidence_id in step.get("evidence_ids", [])
                ),
            ]
        }
        self.assertLessEqual(len(pack["feature_hints"]), 2_000)
        self.assertLessEqual(len(pack["evidence"]), 2_000)
        self.assertEqual(referenced_ids - evidence_ids, set())

    def test_model_narrative_composes_a_human_report_for_any_repository(self) -> None:
        composed = compose_human_report(self.index, self.narrative)
        report = render_report(composed)
        visible = report.split('<script id="repo-data"', 1)[0]

        self.assertEqual([item["title"] for item in composed["features"]], ["Graph Workflow"])
        self.assertEqual(composed["features"][0]["source"], "llm-evidence-synthesis")
        self.assertIn("一次任务完整怎么运行", visible)
        self.assertIn("先讲这是什么项目", visible)
        self.assertIn("项目工程结构", visible)
        self.assertIn("前端代码", visible)
        self.assertIn("后端代码", visible)
        self.assertIn("分层模块化单体，不是 DDD", visible)
        self.assertIn("语音 / 视频代码组织", visible)
        self.assertIn("产品主轴 01", visible)
        self.assertIn("确定性图工作流", visible)
        self.assertIn("核心子功能 01", visible)
        self.assertIn("先看 <b>1 条产品主轴</b>", visible)
        self.assertLess(visible.index("确定性图工作流"), visible.index("Graph Workflow"))
        self.assertLess(visible.index("先讲这是什么项目"), visible.index("这个项目有哪些功能？"))
        self.assertIn("底层机制到底怎么工作", visible)
        self.assertIn("先说结论", visible)
        self.assertIn("Router 不是执行节点", visible)
        self.assertIn('class="feature-thesis"', visible)
        self.assertIn('class="human-recap"', visible)
        self.assertLess(
            visible.index("Router 不是执行节点"),
            visible.index("怎样并发执行节点而不破坏状态确定性"),
        )
        self.assertIn("调度器选择依赖已经触发的节点", visible)
        self.assertIn("运行前构图", visible)
        self.assertIn("怎样并发执行节点而不破坏状态确定性", visible)
        self.assertIn("最后再看源码证据", visible)
        self.assertNotIn("程序入口：src/graph.py · main", visible)

    def test_model_narrative_fails_closed_on_unknown_evidence_or_stale_commit(self) -> None:
        bad_evidence = {**self.narrative, "chapters": [{**self.narrative["chapters"][0], "evidence_ids": ["missing"]}]}
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            compose_human_report(self.index, bad_evidence)

        stale = {**self.narrative, "project": {"commit": "stale", "analysis_fingerprint": "fingerprint-1"}}
        with self.assertRaisesRegex(ValueError, "project commit"):
            compose_human_report(self.index, stale)

        missing_mechanism = {
            **self.narrative,
            "chapters": [{
                key: value
                for key, value in self.narrative["chapters"][0].items()
                if key != "mechanism_model"
            }],
        }
        with self.assertRaisesRegex(ValueError, "mechanism_model"):
            compose_human_report(self.index, missing_mechanism)

    def test_human_report_schema_raises_safe_cap_but_not_40(self) -> None:
        schema = human_report_json_schema()
        chapters = schema["properties"]["chapters"]

        self.assertEqual(chapters["maxItems"], 200)


if __name__ == "__main__":
    unittest.main()
