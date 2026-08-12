from __future__ import annotations

import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from repo_teacher.pipeline.grouping import (
    _group_inventory_for_humans,
    _grouping_partition_feedback,
)


PROJECT_SUMMARY = {
    "product_type": "面向用户的任务平台",
    "primary_actor": "用户",
    "primary_outcome": "完成任务并得到可见结果",
    "main_runtime": "客户端提交后由本地运行时处理",
    "not_the_product": ["健康检查", "通用目录和配置页面"],
}


class GroupingPartitionTest(unittest.TestCase):
    def test_grouping_cache_is_bound_to_provider_model_contract(self) -> None:
        candidate = {
            "id": "task",
            "title": "任务执行",
            "plain_summary": "提交任务并得到结果。",
            "mechanism": "submit -> execute -> result",
            "importance": "core-journey",
            "user_actor": "用户",
            "user_goal": "执行任务",
            "visible_outcome": "得到结果",
            "product_surface": "任务工作台",
            "causal_flow": "提交 -> 执行 -> 回传",
            "implementation_modules": [
                {
                    "path": "src/tasks",
                    "classification": "core",
                    "responsibility": "执行任务",
                    "handoff": "返回结果",
                }
            ],
            "source_feature_ids": ["feature-task"],
            "evidence_ids": ["evidence-task"],
            "source_refs": [
                {
                    "path": "src/tasks/run.py",
                    "line_start": 1,
                    "line_end": 8,
                    "claim": "执行并返回任务结果",
                }
            ],
        }
        grouped = {
            "project_summary": PROJECT_SUMMARY,
            "groups": [
                {
                    "id": "task",
                    "title": "任务执行",
                    "user_actor": "用户",
                    "user_goal": "执行任务",
                    "visible_outcome": "得到结果",
                    "product_surface": "任务工作台",
                    "causal_flow": "提交 -> 执行 -> 回传",
                    "why_one_capability": "同一任务闭环。",
                    "importance": "core-journey",
                    "merge_into_capability_id": "__new__",
                    "member_ids": ["task"],
                }
            ],
            "excluded_supporting_items": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "repo_teacher.pipeline.grouping.run_structured_json",
                return_value=grouped,
            ) as model:
                for model_name in ("model-a", "model-b"):
                    with patch.dict(
                        os.environ,
                        {"REPO_TEACHER_CODEX_MODEL": model_name},
                    ):
                        _group_inventory_for_humans(
                            {
                                "capabilities": [candidate],
                                "module_dispositions": [],
                            },
                            source=root,
                            workspace=root / "workspace",
                            deadline=10**12,
                            provider="codex",
                        )

        self.assertEqual(model.call_count, 2)
        first_workspace = model.call_args_list[0].kwargs["workspace"]
        second_workspace = model.call_args_list[1].kwargs["workspace"]
        self.assertNotEqual(first_workspace, second_workspace)

    def test_exact_group_or_exclusion_partition_passes(self) -> None:
        self.assertIsNone(
            _grouping_partition_feedback(
                {
                    "groups": [{"member_ids": ["task", "runtime"]}],
                    "excluded_supporting_items": [{"member_id": "health"}],
                },
                {"task", "runtime", "health"},
            )
        )

    def test_missing_id_produces_concrete_repair_feedback(self) -> None:
        feedback = _grouping_partition_feedback(
            {
                "groups": [{"member_ids": ["task"]}],
                "excluded_supporting_items": [],
            },
            {"task", "renderer"},
        )

        self.assertIsNotNone(feedback)
        assert feedback is not None
        self.assertEqual(feedback["code"], "grouping-partition-incomplete")
        self.assertEqual(feedback["missing_ids"], ["renderer"])

    def test_incomplete_partition_fails_without_a_second_model_call(self) -> None:
        candidate = {
            "id": "task",
            "title": "任务执行",
            "plain_summary": "提交任务并得到结果。",
            "mechanism": "submit -> execute -> result",
            "importance": "core-journey",
            "user_actor": "用户",
            "user_goal": "执行任务",
            "visible_outcome": "得到结果",
            "product_surface": "任务工作台",
            "causal_flow": "提交 -> 执行 -> 回传",
            "implementation_modules": [{"path": "src/tasks"}],
            "source_feature_ids": ["feature-task"],
            "evidence_ids": ["evidence-task"],
            "source_refs": [
                {"path": "src/tasks/run.py", "line_start": 1, "line_end": 8}
            ],
        }
        incomplete = {
            "project_summary": PROJECT_SUMMARY,
            "groups": [],
            "excluded_supporting_items": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "repo_teacher.pipeline.grouping.run_structured_json",
                return_value=incomplete,
            ) as model:
                with self.assertRaisesRegex(ValueError, "exactly once"):
                    _group_inventory_for_humans(
                        {"capabilities": [candidate], "module_dispositions": []},
                        source=root,
                        workspace=root / "workspace",
                        deadline=10**12,
                        provider="codex",
                    )

        model.assert_called_once()

    def test_grouping_prompt_keeps_backend_evidence_beyond_first_three_refs(self) -> None:
        refs = [
            {
                "path": f"frontend/shell-{index}.ts",
                "line_start": 1,
                "line_end": 2,
                "claim": f"shell {index}",
            }
            for index in range(3)
        ]
        refs.append(
            {
                "path": "backend/internal/store/agents.go",
                "line_start": 20,
                "line_end": 60,
                "claim": "后端事实源持久化并读取 Agent 目录",
            }
        )
        candidate = {
            "id": "agent-directory",
            "title": "Agent 目录",
            "plain_summary": "用户查看 Agent 列表与详情。",
            "mechanism": "IPC -> HTTP -> Core -> Store",
            "importance": "core-journey",
            "user_actor": "用户",
            "user_goal": "查看可用 Agent",
            "visible_outcome": "得到 Agent 列表与详情",
            "product_surface": "Agent 目录",
            "causal_flow": "打开目录 -> 后端读取 -> 返回详情",
            "implementation_modules": [
                {
                    "path": "backend/internal/store",
                    "classification": "core",
                    "responsibility": "持久化 Agent",
                    "handoff": "返回 Core",
                }
            ],
            "source_feature_ids": ["feature-agent"],
            "evidence_ids": ["evidence-agent"],
            "source_refs": refs,
        }
        grouped = {
            "project_summary": PROJECT_SUMMARY,
            "groups": [
                {
                    "id": "agent-directory",
                    "title": "Agent 目录与详情",
                    "user_actor": "用户",
                    "user_goal": "查看可用 Agent",
                    "visible_outcome": "得到 Agent 列表与详情",
                    "product_surface": "Agent 目录",
                    "causal_flow": "打开目录 -> 后端读取 -> 返回详情",
                    "why_one_capability": "前后端共同交付同一目录结果。",
                    "importance": "dependent-capability",
                    "member_ids": ["agent-directory"],
                }
            ],
            "excluded_supporting_items": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "repo_teacher.pipeline.grouping.run_structured_json",
                return_value=grouped,
            ) as model:
                _group_inventory_for_humans(
                    {
                        "capabilities": [candidate],
                        "module_dispositions": [
                            {
                                "path": "backend/internal/store",
                                "disposition": "core-capability",
                                "capability_ids": ["agent-directory"],
                                "reason": "事实源",
                            }
                        ],
                    },
                    source=root,
                    workspace=root / "workspace",
                    deadline=10**12,
                    provider="codex",
                )

        prompt = model.call_args.kwargs["prompt"]
        self.assertIn("backend/internal/store/agents.go", prompt)
        self.assertIn("后端事实源持久化并读取 Agent 目录", prompt)

    def test_group_importance_is_set_by_global_product_editor(self) -> None:
        candidate = {
            "id": "agent-directory",
            "title": "Agent 目录",
            "plain_summary": "用户查看 Agent 列表与详情。",
            "mechanism": "IPC -> HTTP -> Core -> Store",
            "importance": "core-journey",
            "user_actor": "用户",
            "user_goal": "查看可用 Agent",
            "visible_outcome": "得到 Agent 列表与详情",
            "product_surface": "Agent 目录",
            "causal_flow": "打开目录 -> 后端读取 -> 返回详情",
            "implementation_modules": [
                {
                    "path": "backend/internal/store",
                    "classification": "core",
                    "responsibility": "持久化 Agent",
                    "handoff": "返回 Core",
                }
            ],
            "source_feature_ids": ["feature-agent"],
            "evidence_ids": ["evidence-agent"],
            "source_refs": [
                {
                    "path": "backend/internal/store/agents.go",
                    "line_start": 1,
                    "line_end": 4,
                    "claim": "读取 Agent",
                }
            ],
        }
        grouped = {
            "project_summary": PROJECT_SUMMARY,
            "groups": [
                {
                    "id": "agent-directory",
                    "title": "Agent 目录与详情",
                    "user_actor": "用户",
                    "user_goal": "查看可用 Agent",
                    "visible_outcome": "得到 Agent 列表与详情",
                    "product_surface": "Agent 目录",
                    "causal_flow": "打开目录 -> 后端读取 -> 返回详情",
                    "why_one_capability": "共同交付目录结果。",
                    "importance": "supporting",
                    "member_ids": ["agent-directory"],
                }
            ],
            "excluded_supporting_items": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "repo_teacher.pipeline.grouping.run_structured_json",
                return_value=grouped,
            ):
                result = _group_inventory_for_humans(
                    {
                        "capabilities": [candidate],
                        "module_dispositions": [
                            {
                                "path": "backend/internal/store",
                                "disposition": "core-capability",
                                "capability_ids": ["agent-directory"],
                                "reason": "事实源",
                            }
                        ],
                    },
                    source=root,
                    workspace=root / "workspace",
                    deadline=10**12,
                    provider="codex",
                )

        self.assertEqual(result["capabilities"][0]["importance"], "supporting")

    def test_grouping_drops_module_claims_without_source_ref_coverage(self) -> None:
        candidate = {
            "id": "protocol-bridge",
            "title": "协议桥",
            "plain_summary": "双向转换协议消息。",
            "mechanism": "processor <-> observer",
            "importance": "differentiator",
            "user_actor": "客户端开发者",
            "user_goal": "接入会话",
            "visible_outcome": "收发协议消息",
            "product_surface": "协议桥",
            "causal_flow": "输入 -> 转换 -> 输出",
            "implementation_modules": [
                {
                    "path": "src/protocol",
                    "classification": "core",
                    "responsibility": "转换协议消息",
                    "handoff": "交给 pipeline",
                },
                {
                    "path": "src/pipeline",
                    "classification": "supporting",
                    "responsibility": "自动挂载协议组件",
                    "handoff": "绑定生命周期",
                },
            ],
            "source_feature_ids": ["feature-protocol"],
            "evidence_ids": ["evidence-protocol"],
            "source_refs": [
                {
                    "path": "src/protocol/processor.py",
                    "line_start": 1,
                    "line_end": 20,
                    "claim": "协议消息转换",
                }
            ],
        }
        grouped = {
            "project_summary": PROJECT_SUMMARY,
            "groups": [
                {
                    "id": "protocol-bridge",
                    "title": "协议桥",
                    "user_actor": "客户端开发者",
                    "user_goal": "接入会话",
                    "visible_outcome": "收发协议消息",
                    "product_surface": "协议桥",
                    "causal_flow": "输入 -> 转换 -> 输出",
                    "why_one_capability": "双向协议闭环。",
                    "importance": "differentiator",
                    "merge_into_capability_id": "__new__",
                    "member_ids": ["protocol-bridge"],
                }
            ],
            "excluded_supporting_items": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "repo_teacher.pipeline.grouping.run_structured_json",
                return_value=grouped,
            ):
                result = _group_inventory_for_humans(
                    {
                        "capabilities": [candidate],
                        "module_dispositions": [],
                    },
                    source=root,
                    workspace=root / "workspace",
                    deadline=10**12,
                    provider="codex",
                )

        self.assertEqual(
            result["capabilities"][0]["implementation_modules"],
            [candidate["implementation_modules"][0]],
        )

    def test_grouping_keeps_evidence_from_every_group_member(self) -> None:
        candidates = []
        for index in range(9):
            candidates.append(
                {
                    "id": f"provider-{index}",
                    "title": f"Provider {index}",
                    "plain_summary": "提供同一类服务。",
                    "mechanism": f"provider-{index} call",
                    "importance": "dependent-capability",
                    "user_actor": "开发者",
                    "user_goal": "调用服务",
                    "visible_outcome": "得到统一结果",
                    "product_surface": "服务接入层",
                    "causal_flow": "输入 -> 供应商 -> 输出",
                    "implementation_modules": [
                        {
                            "path": f"src/provider_{index}",
                            "classification": "core",
                            "responsibility": "供应商接入",
                            "handoff": "返回统一结果",
                        }
                    ],
                    "source_feature_ids": [f"feature-{index}"],
                    "evidence_ids": [f"evidence-{index}"],
                    "source_refs": [
                        {
                            "path": f"src/provider_{index}/service.py",
                            "line_start": line,
                            "line_end": line + 1,
                            "claim": f"provider {index} evidence {line}",
                        }
                        for line in (1, 3)
                    ],
                }
            )
        grouped = {
            "project_summary": PROJECT_SUMMARY,
            "groups": [
                {
                    "id": "providers",
                    "title": "多供应商服务接入",
                    "user_actor": "开发者",
                    "user_goal": "调用服务",
                    "visible_outcome": "得到统一结果",
                    "product_surface": "服务接入层",
                    "causal_flow": "输入 -> 供应商 -> 输出",
                    "why_one_capability": "同一服务合同。",
                    "importance": "dependent-capability",
                    "merge_into_capability_id": "__new__",
                    "member_ids": [item["id"] for item in candidates],
                }
            ],
            "excluded_supporting_items": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "repo_teacher.pipeline.grouping.run_structured_json",
                return_value=grouped,
            ):
                result = _group_inventory_for_humans(
                    {"capabilities": candidates, "module_dispositions": []},
                    source=root,
                    workspace=root / "workspace",
                    deadline=10**12,
                    provider="codex",
                )

        paths = {
            item["path"] for item in result["capabilities"][0]["source_refs"]
        }
        self.assertEqual(
            paths,
            {f"src/provider_{index}/service.py" for index in range(9)},
        )

    def test_grouping_rejects_merge_into_existing_capability_without_approval_stage(
        self,
    ) -> None:
        candidate = {
            "id": "template-step",
            "title": "模板选择",
            "mechanism": "form -> task submission",
            "importance": "dependent-capability",
            "user_actor": "用户",
            "user_goal": "用模板填写任务参数",
            "visible_outcome": "参数进入任务提交主链",
            "product_surface": "模板表单",
            "causal_flow": "选择模板 -> 填写参数 -> 交给任务服务",
            "source_feature_ids": ["feature-template"],
            "evidence_ids": ["evidence-template"],
            "source_refs": [
                {
                    "path": "src/templates/submit.py",
                    "line_start": 1,
                    "line_end": 8,
                    "claim": "表单转交既有任务创建主链",
                }
            ],
            "implementation_modules": [
                {
                    "path": "src/templates",
                    "classification": "supporting",
                    "responsibility": "收集任务参数",
                    "handoff": "交给任务服务",
                }
            ],
        }
        grouped = {
            "project_summary": PROJECT_SUMMARY,
            "groups": [
                {
                    "id": "template-step",
                    "title": "模板选择",
                    "user_actor": "用户",
                    "user_goal": "用模板填写任务参数",
                    "visible_outcome": "参数进入任务提交主链",
                    "product_surface": "模板表单",
                    "causal_flow": "选择模板 -> 填写参数 -> 交给任务服务",
                    "why_one_capability": "它只是已批准任务旅程的前置步骤。",
                    "importance": "dependent-capability",
                    "merge_into_capability_id": "task-execution",
                    "member_ids": ["template-step"],
                }
            ],
            "excluded_supporting_items": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "repo_teacher.pipeline.grouping.run_structured_json",
                return_value=grouped,
            ):
                with self.assertRaisesRegex(
                    ValueError, "unknown approved capability"
                ):
                    _group_inventory_for_humans(
                        {
                            "capabilities": [candidate],
                            "module_dispositions": [
                                {
                                    "path": "src/templates",
                                    "disposition": "supporting",
                                    "capability_ids": ["template-step"],
                                    "reason": "任务前置表单",
                                }
                            ],
                        },
                        source=root,
                        workspace=root / "workspace",
                        deadline=10**12,
                        provider="codex",
                    )


if __name__ == "__main__":
    unittest.main()
