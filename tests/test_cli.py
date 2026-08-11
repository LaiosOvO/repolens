from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_teacher.cli import (
    _build_chapter_batch_pack,
    _build_global_business_inventory_pack,
    _build_inventory_shard_pack,
    _canonicalize_inventory_payload,
    _close_chapter_evidence,
    _decode_json_object,
    _inventory_from_manifest,
    _inventory_json_schema,
    _inventory_prompt,
    _inventory_shard_prompt,
    _chapter_batch_prompt,
    _project_overview_prompt,
    _require_inventory_scope,
    _add_project_navigation,
    _model_prompt,
    _normalize_project_overview,
    _group_inventory_for_humans,
    _remaining_model_timeout,
    _rebind_reviewed_narrative,
    main,
)
from repo_teacher.indexer import _integrity_digest


class CliTest(unittest.TestCase):
    def test_project_overview_drops_a_duplicated_all_supporting_axis(self) -> None:
        source_ref = {"path": "src/app.py", "line_start": 1, "line_end": 1, "claim": "evidence"}
        overview = {
            "project_overview": {
                "capability_order": ["core", "support"],
                "core_product_axes": [
                    {"id": "core-axis", "capability_ids": ["core"], "source_refs": [source_ref]},
                    {"id": "support-bucket", "capability_ids": ["support"], "source_refs": [source_ref]},
                ],
                "supporting_capability_ids": ["support"],
                "source_refs": [source_ref, source_ref, source_ref],
                "engineering_structure": {"source_refs": [source_ref]},
                "runtime_components": [
                    {"source_refs": [source_ref]},
                    {"source_refs": [source_ref]},
                ],
                "code_organization": [
                    {"path": "src", "source_refs": [source_ref]},
                    {"path": "src", "source_refs": [source_ref]},
                ],
            }
        }
        packet = {"scope": {"allowed_source_paths": ["src/app.py"]}}
        capabilities = [{"id": "core"}, {"id": "support"}]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "src").mkdir()
            (source / "src" / "app.py").write_text("pass\n", encoding="utf-8")
            result = _normalize_project_overview(payload=overview, packet=packet, capabilities=capabilities, source=source)

        self.assertEqual(
            [axis["id"] for axis in result["core_product_axes"]], ["core-axis"]
        )

    def test_grouping_excludes_supporting_http_surface_from_product_capabilities(
        self,
    ) -> None:
        payload = {
            "capabilities": [
                {
                    "id": "voice-session",
                    "title": "手机语音会话",
                    "plain_summary": "用户从手机发起并完成一轮语音会话。",
                    "mechanism": "voice-session",
                    "source_feature_ids": ["feature_voice"],
                    "evidence_ids": ["evidence_voice"],
                    "source_refs": [
                        {"path": "server/voice.py", "line_start": 1, "line_end": 2}
                    ],
                },
                {
                    "id": "healthz",
                    "title": "健康检查端点",
                    "plain_summary": "返回固定 ok。",
                    "mechanism": "http-route",
                    "source_feature_ids": ["feature_health"],
                    "evidence_ids": ["evidence_health"],
                    "source_refs": [
                        {"path": "server/app.py", "line_start": 10, "line_end": 11}
                    ],
                },
            ]
        }
        grouped = {
            "groups": [
                {
                    "id": "voice-session",
                    "title": "手机语音会话",
                    "user_actor": "手机用户",
                    "user_goal": "与桌面 Agent 完成语音交互",
                    "visible_outcome": "手机上听到 Agent 回复",
                    "product_surface": "实时语音会话",
                    "causal_flow": "手机音频进入 Agent，回复再被合成为语音返回手机",
                    "why_one_capability": "输入和输出共同构成一次语音会话",
                    "member_ids": ["voice-session"],
                }
            ],
            "excluded_supporting_items": [
                {
                    "member_id": "healthz",
                    "reason": "仅用于存活探测，不交付独立用户结果。",
                }
            ],
        }

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("repo_teacher.cli._run_codex_json", return_value=grouped),
            patch("repo_teacher.cli.time.monotonic", return_value=0.0),
        ):
            result = _group_inventory_for_humans(
                payload,
                source=Path(directory),
                workspace=Path(directory) / "workspace",
                deadline=10_000.0,
                provider="codex",
            )

        self.assertEqual(
            [item["id"] for item in result["capabilities"]], ["voice-session"]
        )
        self.assertIn("手机音频进入 Agent", result["capabilities"][0]["plain_summary"])
        self.assertNotIn("server/voice.py", result["capabilities"][0]["title"])

    def test_inventory_prompts_do_not_promote_supporting_surfaces(self) -> None:
        full_prompt = _inventory_prompt(Path("/tmp/pack.json"), Path("/tmp/source"))
        shard_prompt = _inventory_shard_prompt(
            Path("/tmp/shard.json"), Path("/tmp/source"), ["server"]
        )
        for prompt in (full_prompt, shard_prompt):
            self.assertIn("健康/就绪探针", prompt)
            self.assertIn("不得独立输出", prompt)
            self.assertIn("用户目标", prompt)
        schema = _inventory_json_schema()
        self.assertIn("capabilities", schema["properties"])
        capability_schema = schema["properties"]["capabilities"]["items"]
        self.assertIn("implementation_modules", capability_schema["required"])
        self.assertIn("importance", capability_schema["required"])
        self.assertIn("user_goal", capability_schema["required"])
        self.assertIn("module_dispositions", schema["required"])
        self.assertIn("逐个交代", full_prompt)

    def test_inventory_scope_rejects_unreviewed_product_modules(self) -> None:
        packet = {
            "scope": {
                "allowed_source_paths": [
                    "src/pipecat/cli/main.py",
                    "src/pipecat/pipeline/pipeline.py",
                    "src/pipecat/transports/base.py",
                ],
                "feature_ids": ["feature_cli"],
                "evidence_ids": ["evidence_cli"],
                "module_paths": [
                    "src/pipecat/cli",
                    "src/pipecat/pipeline",
                    "src/pipecat/transports",
                ],
                "required_product_module_paths": [
                    "src/pipecat/cli",
                    "src/pipecat/pipeline",
                    "src/pipecat/transports",
                ],
                "require_module_coverage": True,
            }
        }
        payload = {
            "capabilities": [
                {
                    "id": "cli-only",
                    "implementation_modules": [
                        {
                            "path": "src/pipecat/cli",
                            "classification": "core",
                        }
                    ],
                    "source_feature_ids": ["feature_cli"],
                    "evidence_ids": ["evidence_cli"],
                    "source_refs": [
                        {"path": "src/pipecat/cli/main.py"}
                    ],
                }
            ],
            "module_dispositions": [
                {
                    "path": "src/pipecat/cli",
                    "disposition": "supporting",
                    "capability_ids": ["cli-only"],
                    "reason": "命令入口只负责启动。",
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "unreviewed product modules"):
            _require_inventory_scope(payload, packet)

        payload["module_dispositions"].extend(
            [
                {
                    "path": "src/pipecat/pipeline",
                    "disposition": "core-capability",
                    "capability_ids": ["cli-only"],
                    "reason": "执行处理器链。",
                },
                {
                    "path": "src/pipecat/transports",
                    "disposition": "core-capability",
                    "capability_ids": ["cli-only"],
                    "reason": "承接实时媒体输入输出。",
                },
            ]
        )
        _require_inventory_scope(payload, packet)

    def test_inventory_canonicalization_preserves_module_dispositions(self) -> None:
        packet = {
            "scope": {
                "allowed_source_paths": ["src/pipeline.py"],
                "module_paths": ["src"],
            },
            "feature_hints": [
                {
                    "id": "feature_pipeline",
                    "evidence_ids": ["evidence_pipeline"],
                    "steps": [{"path": "src/pipeline.py"}],
                }
            ],
            "evidence": [
                {
                    "id": "evidence_pipeline",
                    "kind": "graph-navigation-slice",
                    "path": "src/pipeline.py",
                    "line_start": 1,
                    "line_end": 8,
                }
            ],
        }
        payload = {
            "capabilities": [
                {
                    "id": "pipeline",
                    "implementation_modules": [
                        {
                            "path": "src",
                            "classification": "core",
                            "responsibility": "运行帧管线",
                            "handoff": "把帧交给下游处理器",
                        }
                    ],
                    "source_refs": [
                        {
                            "path": "src/pipeline.py",
                            "line_start": 1,
                            "line_end": 8,
                        }
                    ],
                }
            ],
            "module_dispositions": [
                {
                    "path": "src",
                    "disposition": "core-capability",
                    "capability_ids": [],
                    "reason": "核心运行时。",
                }
            ],
        }

        result = _canonicalize_inventory_payload(payload, packet)

        self.assertEqual(
            result["module_dispositions"][0]["capability_ids"], ["pipeline"]
        )
        self.assertEqual(result["capabilities"][0]["id"], "pipeline")

    def test_global_business_inventory_keeps_modules_as_topology_not_model_shards(
        self,
    ) -> None:
        pack = {
            "schema_version": "repo-teacher-analysis-pack/v1",
            "project": {"name": "fixture", "path": "/tmp/fixture"},
            "instructions": [],
            "required_chapter_sections": [],
            "modules": [
                {"id": "pipeline", "path": "src/pipeline", "symbol_count": 20},
                {"id": "transport", "path": "src/transport", "symbol_count": 12},
            ],
            "reading_path": [
                {"path": "src/pipeline/run.py", "order": 1},
                {"path": "src/transport/ws.py", "order": 2},
                {"path": "tests/test_health.py", "order": 3},
                {"path": ".claude/skills/review/SKILL.md", "order": 4},
                {"path": "changelog/2026.md", "order": 5},
            ],
            "feature_hints": [
                {
                    "id": "feature_pipeline",
                    "evidence_ids": ["evidence_pipeline"],
                    "steps": [
                        {
                            "path": "src/pipeline/run.py",
                            "evidence_ids": ["evidence_pipeline"],
                        },
                        {
                            "path": "src/transport/ws.py",
                            "evidence_ids": ["evidence_transport"],
                        },
                    ],
                },
                {
                    "id": "feature_health",
                    "evidence_ids": ["evidence_health"],
                    "steps": [
                        {
                            "path": "tests/test_health.py",
                            "evidence_ids": ["evidence_health"],
                        }
                    ],
                },
                {
                    "id": "feature_agent_instruction",
                    "evidence_ids": ["evidence_agent_instruction"],
                    "steps": [
                        {
                            "path": ".claude/skills/review/SKILL.md",
                            "evidence_ids": ["evidence_agent_instruction"],
                        }
                    ],
                },
                {
                    "id": "feature_changelog",
                    "evidence_ids": ["evidence_changelog"],
                    "steps": [
                        {
                            "path": "changelog/2026.md",
                            "evidence_ids": ["evidence_changelog"],
                        }
                    ],
                },
            ],
            "evidence": [
                {"id": "evidence_pipeline", "path": "src/pipeline/run.py"},
                {"id": "evidence_transport", "path": "src/transport/ws.py"},
                {"id": "evidence_health", "path": "tests/test_health.py"},
                {
                    "id": "evidence_agent_instruction",
                    "path": ".claude/skills/review/SKILL.md",
                },
                {"id": "evidence_changelog", "path": "changelog/2026.md"},
            ],
            "capability_graph": {
                "schema_version": "repo-teacher-capability-graph/v1",
                "stats": {},
                "feature_slices": [
                    {
                        "id": "slice_pipeline",
                        "feature_id": "feature_pipeline",
                        "implementation_nodes": [
                            {"path": "src/pipeline/run.py", "line": 10}
                        ],
                        "resolved_edges": [
                            {
                                "id": "edge_pipeline_transport",
                                "source_path": "src/pipeline/run.py",
                                "target_path": "src/transport/ws.py",
                            }
                        ],
                    }
                ],
                "capability_candidates": [],
                "mechanism_clusters": [
                    {
                        "id": "cluster_transport",
                        "central_nodes": [
                            {"path": "src/transport/ws.py", "line": 5}
                        ],
                    }
                ],
                "components": [],
                "module_dependencies": [
                    {"source": "pipeline", "target": "transport", "count": 1}
                ],
                "unresolved_edge_examples": [],
                "interpretation_contract": [],
            },
        }

        result = _build_global_business_inventory_pack(pack)

        self.assertEqual(
            [item["path"] for item in result["modules"]],
            [
                "src/pipeline",
                "src/transport",
                ".claude/skills/review",
                "changelog",
                "tests",
            ],
        )
        self.assertEqual(
            [item["category"] for item in result["modules"][-3:]],
            ["engineering-support", "documentation", "testing"],
        )
        self.assertEqual(
            [item["id"] for item in result["feature_hints"]],
            ["feature_pipeline"],
        )
        self.assertEqual(
            {item["id"] for item in result["evidence"]},
            {"evidence_pipeline", "evidence_transport"},
        )
        self.assertIn("src/pipeline/run.py", result["scope"]["allowed_source_paths"])
        self.assertIn("src/transport/ws.py", result["scope"]["allowed_source_paths"])
        self.assertNotIn("tests/test_health.py", result["scope"]["allowed_source_paths"])
        self.assertEqual(
            result["scope"]["required_product_module_paths"],
            ["src/pipeline", "src/transport"],
        )
        self.assertEqual(
            result["inventory_strategy"]["decision_scope"],
            "whole-repository-business-capabilities",
        )
        self.assertIn(
            "pipeline",
            result["capability_graph"]["module_dependencies"][0]["source"],
        )

    def test_product_navigation_reads_root_readme_without_promoting_it_to_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "README.md").write_text(
                "Realtime voice framework for developers.", encoding="utf-8"
            )
            pack = {
                "project": {"path": str(source)},
                "files": [{"path": "README.md"}],
                "evidence": [],
            }
            enriched = _add_project_navigation(
                {"scope": {"allowed_source_paths": []}}, pack
            )

        self.assertEqual(enriched["product_navigation"][0]["path"], "README.md")
        self.assertIn("Realtime voice framework", enriched["product_navigation"][0]["snippet"])
        self.assertEqual(enriched.get("evidence"), None)

    def test_remaining_model_timeout_honors_explicit_budget_above_600_seconds(
        self,
    ) -> None:
        with patch("repo_teacher.cli.time.monotonic", return_value=100.25):
            self.assertEqual(_remaining_model_timeout(7300.25), 7200)

    def test_remaining_model_timeout_rejects_expired_global_deadline(self) -> None:
        with patch("repo_teacher.cli.time.monotonic", return_value=100.25):
            with self.assertRaisesRegex(TimeoutError, "deadline exceeded"):
                _remaining_model_timeout(100.25)

    def test_reviewed_narrative_rebinds_analyzer_fingerprint_not_commit(self) -> None:
        narrative = {
            "project": {"commit": "abc", "analysis_fingerprint": "old"},
            "chapters": [
                {
                    "id": "memory",
                    "source_feature_ids": ["old-feature"],
                    "evidence_ids": ["old-evidence"],
                    "source_refs": [
                        {"path": "memory.py", "line_start": 3, "line_end": 4}
                    ],
                    "difficulty_map": {
                        "items": [{"evidence_ids": ["old-evidence"]}]
                    },
                }
            ],
        }
        pack = {
            "project": {"commit": "abc", "analysis_fingerprint": "new"},
            "feature_hints": [
                {
                    "id": "current-feature",
                    "evidence_ids": ["current-evidence"],
                    "steps": [
                        {
                            "path": "memory.py",
                            "line_start": 3,
                            "line_end": 4,
                            "evidence_ids": ["current-evidence"],
                        }
                    ],
                }
            ],
            "evidence": [
                {
                    "id": "current-evidence",
                    "path": "memory.py",
                    "line_start": 3,
                    "line_end": 4,
                    "kind": "symbol-definition",
                }
            ],
        }

        rebound = _rebind_reviewed_narrative(narrative, pack)

        self.assertEqual(rebound["project"]["analysis_fingerprint"], "new")
        self.assertEqual(
            rebound["chapters"][0]["source_feature_ids"], ["current-feature"]
        )
        self.assertEqual(
            rebound["chapters"][0]["evidence_ids"], ["current-evidence"]
        )
        self.assertEqual(
            rebound["chapters"][0]["difficulty_map"]["items"][0][
                "evidence_ids"
            ],
            ["current-evidence"],
        )
        self.assertEqual(narrative["project"]["analysis_fingerprint"], "old")
        with self.assertRaisesRegex(ValueError, "commit does not match"):
            _rebind_reviewed_narrative(
                narrative,
                {"project": {"commit": "other", "analysis_fingerprint": "new"}},
            )

    def test_decode_json_object_accepts_plain_and_fenced_json(self) -> None:
        self.assertEqual(_decode_json_object('{"ok":true}'), {"ok": True})
        self.assertEqual(
            _decode_json_object('```json\n{"ok":true}\n```'), {"ok": True}
        )

    def test_decode_json_object_rejects_trailing_explanation(self) -> None:
        with self.assertRaises(ValueError):
            _decode_json_object('{"ok":true}\nextra')

    def test_close_chapter_evidence_promotes_valid_difficulty_evidence(self) -> None:
        payload = {
            "chapters": [
                {
                    "id": "memory",
                    "evidence_ids": ["evidence_write"],
                    "difficulty_map": {
                        "items": [
                            {
                                "evidence_ids": [
                                    "evidence_read",
                                    "hallucinated_evidence",
                                ]
                            }
                        ]
                    },
                }
            ]
        }
        result = _close_chapter_evidence(
            payload,
            {
                "scope": {"allowed_source_paths": []},
                "evidence": [
                    {"id": "evidence_write"},
                    {"id": "evidence_read"},
                ],
            },
            [{"id": "memory", "evidence_ids": ["evidence_write"]}],
        )

        chapter = result["chapters"][0]
        self.assertEqual(
            chapter["evidence_ids"], ["evidence_write", "evidence_read"]
        )
        self.assertEqual(
            chapter["difficulty_map"]["items"][0]["evidence_ids"],
            ["evidence_read"],
        )

    def test_inventory_shard_pack_is_graph_first_and_excludes_unrelated_modules(self) -> None:
        pack = {
            "schema_version": "repo-teacher-analysis-pack/v1",
            "project": {"name": "fixture", "path": "/tmp/fixture"},
            "instructions": ["read graph first"],
            "required_chapter_sections": ["runtime"],
            "modules": [
                {"id": "memory", "path": "src/memory", "symbol_count": 5},
                {"id": "voice", "path": "src/voice", "symbol_count": 7},
            ],
            "reading_path": [
                {"path": "src/memory/store.py", "order": 1},
                {"path": "src/voice/asr.py", "order": 2},
            ],
            "feature_hints": [
                {
                    "id": "feature_memory",
                    "evidence_ids": ["evidence_memory"],
                    "steps": [{"path": "src/memory/store.py", "evidence_ids": ["evidence_memory"]}],
                },
                {
                    "id": "feature_voice",
                    "evidence_ids": ["evidence_voice"],
                    "steps": [{"path": "src/voice/asr.py", "evidence_ids": ["evidence_voice"]}],
                },
            ],
            "evidence": [
                {"id": "evidence_memory", "path": "src/memory/store.py"},
                {"id": "evidence_voice", "path": "src/voice/asr.py"},
            ],
            "capability_graph": {
                "schema_version": "repo-teacher-capability-graph/v1",
                "stats": {},
                "feature_slices": [
                    {
                        "id": "slice_memory",
                        "feature_id": "feature_memory",
                        "implementation_nodes": [
                            {"id": "memory_write", "path": "src/memory/store.py", "line": 10}
                        ],
                        "resolved_edges": [
                            {"id": "edge_memory", "source_path": "src/memory/store.py", "target_path": "src/memory/query.py"}
                        ],
                    },
                    {
                        "id": "slice_voice",
                        "feature_id": "feature_voice",
                        "implementation_nodes": [
                            {"id": "voice_asr", "path": "src/voice/asr.py", "line": 8}
                        ],
                        "resolved_edges": [],
                    },
                ],
                "capability_candidates": [
                    {
                        "id": "candidate_memory",
                        "source_feature_ids": ["feature_memory"],
                        "implementation_nodes": [
                            {"id": "memory_write", "path": "src/memory/store.py", "line": 10}
                        ],
                        "resolved_edges": [
                            {"id": "edge_memory", "source_path": "src/memory/store.py", "target_path": "src/memory/query.py"}
                        ],
                    },
                    {
                        "id": "candidate_voice",
                        "source_feature_ids": ["feature_voice"],
                        "implementation_nodes": [
                            {"id": "voice_asr", "path": "src/voice/asr.py", "line": 8}
                        ],
                        "resolved_edges": [],
                    },
                ],
                "mechanism_clusters": [],
                "components": [],
                "module_dependencies": [
                    {"source": "memory", "target": "voice", "kind": "calls", "count": 1}
                ],
                "unresolved_edge_examples": [],
                "interpretation_contract": ["candidates are seeds"],
            },
        }

        shard = _build_inventory_shard_pack(pack, ["src/memory"])

        self.assertEqual([item["path"] for item in shard["modules"]], ["src/memory"])
        self.assertEqual([item["id"] for item in shard["feature_hints"]], ["feature_memory"])
        self.assertEqual([item["id"] for item in shard["evidence"]], ["evidence_memory"])
        self.assertEqual(
            [item["id"] for item in shard["capability_graph"]["capability_candidates"]],
            ["candidate_memory"],
        )
        self.assertIn("src/memory/store.py", shard["scope"]["allowed_source_paths"])
        self.assertNotIn("src/voice/asr.py", shard["scope"]["allowed_source_paths"])

    def test_inventory_shard_prompt_forbids_whole_repository_rescan(self) -> None:
        prompt = _inventory_shard_prompt(
            Path("/tmp/inventory-shard.json"),
            Path("/tmp/source"),
            ["src/memory"],
        )

        self.assertIn("只读取这个分片证据包", prompt)
        self.assertIn("allowed_source_paths", prompt)
        self.assertIn("禁止重新扫描整个仓库", prompt)
        self.assertNotIn("请完整读取 /tmp/inventory-shard.json，并按需检查仓库", prompt)

    def test_chapter_batch_pack_keeps_only_selected_capability_closure(self) -> None:
        pack = {
            "schema_version": "repo-teacher-analysis-pack/v1",
            "project": {"name": "fixture"},
            "instructions": [],
            "required_chapter_sections": [],
            "modules": [
                {"path": "src/memory", "symbol_count": 2},
                {"path": "src/voice", "symbol_count": 2},
            ],
            "reading_path": [],
            "feature_hints": [
                {"id": "feature_memory", "evidence_ids": ["evidence_memory"], "steps": [{"path": "src/memory/store.py"}]},
                {"id": "feature_voice", "evidence_ids": ["evidence_voice"], "steps": [{"path": "src/voice/asr.py"}]},
            ],
            "evidence": [
                {"id": "evidence_memory", "path": "src/memory/store.py"},
                {"id": "evidence_voice", "path": "src/voice/asr.py"},
            ],
            "capability_graph": {
                "feature_slices": [
                    {"feature_id": "feature_memory", "implementation_nodes": [{"path": "src/memory/store.py"}]},
                    {"feature_id": "feature_voice", "implementation_nodes": [{"path": "src/voice/asr.py"}]},
                ],
                "capability_candidates": [], "mechanism_clusters": [], "components": [],
                "module_dependencies": [], "unresolved_edge_examples": [],
                "interpretation_contract": [],
            },
        }
        capabilities = [{
            "id": "memory", "source_feature_ids": ["feature_memory"],
            "evidence_ids": ["evidence_memory"],
            "source_refs": [{"path": "src/memory/store.py", "line_start": 1, "line_end": 2, "claim": "write"}],
        }]

        batch_pack = _build_chapter_batch_pack(pack, capabilities)

        self.assertEqual([item["id"] for item in batch_pack["feature_hints"]], ["feature_memory"])
        self.assertEqual([item["id"] for item in batch_pack["evidence"]], ["evidence_memory"])
        self.assertEqual(batch_pack["scope"]["capability_ids"], ["memory"])
        self.assertEqual(batch_pack["scope"]["allowed_source_paths"], ["src/memory/store.py"])

    def test_report_prompt_teaches_mechanisms_instead_of_listing_code(self) -> None:
        prompt = _model_prompt(Path("/tmp/pack.json"), Path("/tmp/source"))

        self.assertIn("具体用户动作", prompt)
        self.assertIn("核心抽象", prompt)
        self.assertIn("它本质上是什么", prompt)
        self.assertIn("for、while、事件循环", prompt)
        self.assertIn("continue/return/break/最大轮次", prompt)
        self.assertIn("router 在什么时候读取哪份 state", prompt)
        self.assertIn("串行轮次、半双工还是真全双工", prompt)
        self.assertIn("仅写“Router 决定路由”不合格", prompt)
        self.assertIn("human-report-schema.json", prompt)

    def test_human_report_prompts_require_cross_capability_interactions(self) -> None:
        overview_prompt = _project_overview_prompt(
            Path("/tmp/overview-pack.json"), Path("/tmp/source"), ["voice", "flow"]
        )
        chapter_prompt = _chapter_batch_prompt(
            Path("/tmp/chapter-pack.json"),
            Path("/tmp/inventory.json"),
            Path("/tmp/source"),
            ["voice", "workers"],
        )

        self.assertIn("数据、控制权与状态", overview_prompt)
        self.assertIn("语音帧管线把转写交给 Flow", overview_prompt)
        self.assertIn("客户端怎样持续采集/送帧", overview_prompt)
        self.assertIn("一键部署", overview_prompt)
        self.assertIn("谁收到什么", chapter_prompt)
        self.assertIn("媒体帧怎样变成 Flow 的上下文或事件", chapter_prompt)
        self.assertIn("没有内置固定任务目录", chapter_prompt)
        self.assertIn("任务怎样排队/持久化", chapter_prompt)

    def test_inventory_schema_does_not_cap_capability_count(self) -> None:
        schema = _inventory_json_schema()
        capabilities = schema["properties"]["capabilities"]

        self.assertEqual(capabilities["minItems"], 1)
        self.assertNotIn("maxItems", capabilities)

    def test_report_command_is_the_single_human_first_product_surface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            output = Path(directory) / "report"
            root.mkdir()
            (root / "cli.py").write_text(
                "import argparse\n\ndef main():\n"
                "    parser = argparse.ArgumentParser()\n"
                "    parser.add_subparsers().add_parser('serve')\n",
                encoding="utf-8",
            )

            def narrative(
                _source: Path,
                pack: dict,
                _workspace: Path,
                _timeout: int,
                _inventory: str | None = None,
            ) -> dict:
                feature = pack["feature_hints"][0]
                evidence_id = pack["evidence"][0]["id"]
                return {
                    "schema_version": "repo-teacher-human-report/v1",
                    "project": {
                        "commit": pack["project"]["commit"],
                        "analysis_fingerprint": pack["project"]["analysis_fingerprint"],
                    },
                    "generator": {"name": "Codex", "method": "test synthesis"},
                    "chapters": [{
                        "id": "command-service", "title": "Command Service",
                        "summary": "Expose a user-facing command.", "mechanism": "cli",
                        "question": "How does one command run?", "use_when": "Local automation.",
                        "distinguish": "A command is a product action, not merely main().",
                        "source_feature_ids": [feature["id"]], "evidence_ids": [evidence_id],
                        "source_refs": [{"path": "cli.py", "line_start": 1, "line_end": 5,
                                         "claim": "命令解析器声明并分派 serve。"}],
                        "runtime_story": {"trigger": "User command", "owner": "CLI parser",
                            "output": "Command result", "consumer": "User",
                            "steps": ["Parse", "Dispatch", "Return"]},
                        "construction": {"explanation": "Parser and handler are separated.",
                            "objects": [{"name": "Parser", "role": "Parse input"},
                                        {"name": "Handler", "role": "Execute action"}]},
                        "mechanism_model": {
                            "plain_summary": "This is one bounded parse-dispatch-return pass, not a loop.",
                            "storage": "No independent storage; argv and the in-memory command object are authoritative.",
                            "write_path": "The parser writes validated fields into the command object.",
                            "read_path": "The dispatcher reads the parsed command directly; there is no search index.",
                            "control_loop": "One parse-dispatch-return pass; this capability is not a loop.",
                            "decision_rules": "The registered command name selects exactly one handler.",
                            "termination": "The selected handler returns or validation fails.",
                            "dynamic_behavior": "Commands must be registered before dispatch; runtime code generation is unsupported.",
                            "worked_example": ["Parse serve", "Select handler", "Return result"],
                        },
                        "state_flow": [
                            {"stage": "Input", "reads": "argv", "writes": "command", "why_next": "parse succeeds"},
                            {"stage": "Run", "reads": "command", "writes": "result", "why_next": "handler returns"}],
                        "difficulty_map": {"summary": "Dispatch boundaries must remain explicit.",
                            "unknowns": [], "items": [{"id": "dispatch", "title": "Safe dispatch",
                                "why_hard": "Inputs cross a trust boundary.",
                                "naive_failure": "Execute unchecked input.",
                                "reuse_question": "Which commands are allowed?",
                                "runtime_steps": ["Parse", "Validate", "Dispatch"],
                                "invariants": ["Only registered commands run"],
                                "failure_modes": ["Unknown command"],
                                "tradeoffs": ["Explicit registration costs boilerplate"],
                                "evidence_ids": [evidence_id]}]},
                        "design_choices": [
                            {"choice": "Registered commands", "why": "Auditable", "cost": "Boilerplate"},
                            {"choice": "Separate handler", "why": "Testable", "cost": "Extra layer"}],
                        "boundary": {"supported": ["Registered command"], "unsupported": ["Remote execution"]},
                        "reuse_plan": {"take": ["Dispatch boundary"], "adapt": ["Commands"],
                            "avoid": ["Unchecked eval"], "verify": ["Invalid input"]},
                    }],
                }

            with patch("repo_teacher.cli._synthesize_with_codex", side_effect=narrative):
                exit_code = main(["report", str(root), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "analysis-pack.json").is_file())
            self.assertTrue((output / "human-report.json").is_file())
            self.assertTrue((output / "capability-graph.json").is_file())
            visible = (output / "index.html").read_text(encoding="utf-8").split(
                '<script id="repo-data"', 1
            )[0]
            self.assertIn("Command Service", visible)
            self.assertIn("真正难点与失败方式", visible)
            self.assertNotIn("程序入口：", visible)

    def test_source_audited_manifest_can_be_converted_into_inventory(self) -> None:
        pack = {
            "feature_hints": [
                {
                    "id": "feature_session",
                    "evidence_ids": ["ev_session"],
                    "steps": [{"path": "backend/auth.go", "line_start": 10, "line_end": 20}],
                }
            ],
            "evidence": [
                {
                    "id": "ev_session",
                    "path": "backend/auth.go",
                    "line_start": 10,
                    "line_end": 20,
                }
            ],
        }
        manifest = [
            {
                "id": "local_auth",
                "title": "本地登录",
                "user_action": "用户用邮箱建立本地会话。",
                "mechanism_question": "本地登录态如何创建并返回？",
                "distinguish": "不是远程 OAuth。",
                "coverage_notes": "已覆盖入口与 service。",
                "source_refs": [
                    {
                        "path": "backend/auth.go",
                        "line_start": 10,
                        "line_end": 20,
                        "claim": "创建本地 session。",
                    },
                    {
                        "path": "backend/auth.go",
                        "line_start": 10,
                        "line_end": 20,
                        "claim": "返回 session 给调用方。",
                    },
                    {
                        "path": "backend/auth.go",
                        "line_start": 10,
                        "line_end": 20,
                        "claim": "不会保存真实密码。",
                    },
                ],
            }
        ]

        inventory = _inventory_from_manifest(manifest, pack)

        capability = inventory["capabilities"][0]
        self.assertEqual(capability["id"], "local_auth")
        self.assertEqual(capability["source_feature_ids"], ["feature_session"])
        self.assertEqual(capability["evidence_ids"], ["ev_session"])
        self.assertIn("审计覆盖", capability["distinguish"])

    def test_index_command_writes_json_and_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            output = Path(directory) / "result"
            root.mkdir()
            (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
            (root / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(["index", str(root), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((output / "index.json").is_file())
            self.assertTrue((output / "index.html").is_file())
            payload = json.loads((output / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["stats"]["files"], 2)
            self.assertRegex(payload["generation_id"], r"^[0-9a-f]{32}$")
            self.assertTrue((output / "current").is_symlink())
            self.assertTrue((output / "index.json").is_symlink())
            self.assertEqual(
                {
                    item.name
                    for item in output.iterdir()
                    if item.is_symlink() and item.name != "current"
                },
                {"index.json", "index.html", "capability-graph.json"},
            )
            self.assertIn(
                payload["generation_id"],
                (output / "index.html").read_text(encoding="utf-8"),
            )
            self.assertIn("Generated repository index", stdout.getvalue())

    def test_index_command_rejects_missing_source(self) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = main(["index", "/definitely/missing/repository"])

        self.assertEqual(exit_code, 2)
        self.assertIn("does not exist", stderr.getvalue())

    def test_index_publishes_capability_graph_and_graph_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            output = Path(directory) / "output"
            query_output = Path(directory) / "query.json"
            root.mkdir()
            (root / "main.py").write_text(
                "def helper():\n    return 1\n\ndef main():\n    return helper()\n",
                encoding="utf-8",
            )

            self.assertEqual(main(["index", str(root), "--output", str(output)]), 0)
            graph_path = output / "capability-graph.json"
            self.assertTrue(graph_path.is_file())
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            self.assertEqual(graph["schema_version"], "repo-teacher-capability-graph/v1")
            self.assertGreaterEqual(graph["stats"]["nodes"], 2)

            self.assertEqual(
                main(
                    [
                        "graph",
                        str(output / "index.json"),
                        "main",
                        "--output",
                        str(query_output),
                    ]
                ),
                0,
            )
            query = json.loads(query_output.read_text(encoding="utf-8"))
            self.assertTrue(query["matched_node_ids"])
            self.assertIn("callers", query)
            self.assertIn("callees", query)

    def test_validate_accepts_stable_and_current_paths_for_the_same_generation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            output = Path(directory) / "output"
            root.mkdir()
            (root / "main.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            self.assertEqual(main(["index", str(root), "--output", str(output)]), 0)

            stable_stdout = io.StringIO()
            current_stdout = io.StringIO()
            with contextlib.redirect_stdout(stable_stdout):
                stable = main(["validate", str(output / "index.json")])
            with contextlib.redirect_stdout(current_stdout):
                current = main(
                    ["validate", str(output / "current" / "index.json")]
                )

            self.assertEqual(stable, 0)
            self.assertEqual(current, 0)
            self.assertIn("PASS", stable_stdout.getvalue())
            self.assertIn("PASS", current_stdout.getvalue())

    def test_compare_command_writes_feature_first_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first"
            second = root / "second"
            output = root / "selection"
            first.mkdir()
            second.mkdir()
            (first / "parser.py").write_text("def parse_code():\n    return []\n", encoding="utf-8")
            (second / "call_graph.py").write_text("def build_graph():\n    return {}\n", encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(["compare", str(first), str(second), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((output / "technology-selection.json").is_file())
            self.assertTrue((output / "technology-selection.html").is_file())
            self.assertTrue((output / "projects" / "first" / "index.json").is_file())
            self.assertEqual(
                {
                    item.name
                    for item in output.iterdir()
                    if item.is_symlink() and item.name != "current"
                },
                {"projects", "technology-selection.json", "technology-selection.html"},
            )
            self.assertTrue(
                all(
                    (output / name).exists()
                    for name in (
                        "projects",
                        "technology-selection.json",
                        "technology-selection.html",
                    )
                )
            )
            self.assertIn("Generated technology selection report", stdout.getvalue())

    def test_compare_command_rejects_one_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["compare", str(root), "--output", str(root / "out")])
            self.assertEqual(exit_code, 2)
            self.assertIn("at least two", stderr.getvalue())

    def test_explain_command_locates_exact_module_and_writes_clickable_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            output = Path(directory) / "result"
            module = root / "src" / "acp"
            module.mkdir(parents=True)
            (module / "client.py").write_text(
                "class ACPClient:\n"
                "    def connect(self):\n"
                "        return 'connected'\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(["explain", str(root), "ACP", "--output", str(output)])

            self.assertEqual(exit_code, 0)
            result_path = output / "modules" / "acp.json"
            report_path = output / "modules" / "acp.html"
            self.assertTrue((output / "index.json").is_file())
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue(result_path.is_file())
            self.assertTrue(report_path.is_file())
            self.assertEqual(
                {
                    item.name
                    for item in output.iterdir()
                    if item.is_symlink() and item.name != "current"
                },
                {"index.json", "index.html", "modules"},
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["resolution"]["status"], "exact_name_match")
            self.assertFalse(result["resolution"]["verified_capability_surface"])
            self.assertEqual(result["modules"][0]["path"], "src/acp")
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("src/acp", report)
            self.assertIn("file://", report)
            self.assertIn("Generated module explanation", stdout.getvalue())

    def test_explain_command_rejects_limit_above_safety_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["explain", directory, "ACP", "--limit", "101"])
            self.assertEqual(exit_code, 2)
            self.assertIn("between 1 and 100", stderr.getvalue())

    def test_export_skill_command_uses_generated_feature_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            index_output = root / "index"
            skill_output = root / "skill"
            source.mkdir()
            (source / "cli.py").write_text(
                "import argparse\n\ndef main():\n    parser = argparse.ArgumentParser()\n    parser.add_subparsers().add_parser('serve')\n",
                encoding="utf-8",
            )
            self.assertEqual(main(["index", str(source), "--output", str(index_output)]), 0)
            payload = json.loads((index_output / "index.json").read_text(encoding="utf-8"))
            feature_id = payload["features"][0]["id"]

            exit_code = main(
                [
                    "export-skill",
                    str(index_output / "index.json"),
                    "--feature",
                    feature_id,
                    "--output",
                    str(skill_output),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((skill_output / "SKILL.md").is_file())

    def test_export_skill_force_never_replaces_unowned_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            index_output = root / "index"
            skill_output = root / "skill"
            source.mkdir()
            (source / "cli.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            self.assertEqual(main(["index", str(source), "--output", str(index_output)]), 0)
            skill_output.mkdir()
            protected = skill_output / "keep.txt"
            protected.write_text("user data", encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                refused = main(
                    [
                        "export-skill",
                        str(index_output / "index.json"),
                        "--output",
                        str(skill_output),
                    ]
                )
            self.assertEqual(refused, 1)
            self.assertTrue(protected.is_file())
            self.assertIn("never deletes or replaces", stderr.getvalue())

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                forced = main(
                    [
                        "export-skill",
                        str(index_output / "index.json"),
                        "--output",
                        str(skill_output),
                        "--force",
                    ]
                )
            self.assertEqual(forced, 1)
            self.assertEqual(protected.read_text(encoding="utf-8"), "user data")
            self.assertIn("never deletes or replaces", stderr.getvalue())

    def test_index_staging_failure_keeps_old_json_and_html_generation(self) -> None:
        import repo_teacher.persistence as persistence

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            output = Path(directory) / "output"
            root.mkdir()
            source = root / "main.py"
            source.write_text("def main():\n    return 1\n", encoding="utf-8")
            self.assertEqual(main(["index", str(root), "--output", str(output)]), 0)
            old_json = (output / "index.json").read_text(encoding="utf-8")
            old_html = (output / "index.html").read_text(encoding="utf-8")
            old_target = (output / "current").readlink()
            source.write_text("def main():\n    return 2\n", encoding="utf-8")
            real_write = persistence.atomic_write_text
            writes = 0

            def fail_second_artifact(path: Path, content: str) -> None:
                nonlocal writes
                writes += 1
                if writes == 2:
                    raise OSError("injected CLI generation write failure")
                real_write(path, content)

            stderr = io.StringIO()
            with (
                patch.object(
                    persistence, "atomic_write_text", new=fail_second_artifact
                ),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = main(["index", str(root), "--output", str(output)])

            self.assertEqual(exit_code, 1)
            self.assertEqual((output / "current").readlink(), old_target)
            self.assertEqual((output / "index.json").read_text(encoding="utf-8"), old_json)
            self.assertEqual((output / "index.html").read_text(encoding="utf-8"), old_html)

    def test_partial_index_returns_nonzero_without_switching_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            output = Path(directory) / "output"
            root.mkdir()
            (root / "main.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            self.assertEqual(main(["index", str(root), "--output", str(output)]), 0)
            old_target = (output / "current").readlink()
            partial = json.loads((output / "index.json").read_text(encoding="utf-8"))
            partial["stats"]["scan_complete"] = False
            partial["stats"]["truncated"] = True
            partial["freshness"] = "partial-unvalidated"
            partial["integrity_sha256"] = _integrity_digest(partial)
            stderr = io.StringIO()

            with (
                patch("repo_teacher.cli.build_index", return_value=partial),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = main(["index", str(root), "--output", str(output)])

            self.assertEqual(exit_code, 1)
            self.assertEqual((output / "current").readlink(), old_target)
            self.assertIn("pre-publication validation", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
