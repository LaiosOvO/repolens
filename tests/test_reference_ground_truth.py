from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from repo_teacher.capability_catalog import (
    CAPABILITY_AUDIT_CONTRACTS,
    TECHNOLOGY_DIMENSIONS,
)
from repo_teacher.indexer import build_index
from repo_teacher.report import render_report
from repo_teacher.validation import validate_index


REFERENCE_ROOT = Path(
    os.environ.get(
        "REPO_TEACHER_REFERENCE_ROOT",
        str(Path(__file__).resolve().parents[3] / "repo"),
    )
)
GOLDEN_FIXTURE = Path(__file__).parent / "fixtures" / "reference_capabilities.json"


def _golden_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@unittest.skipUnless(REFERENCE_ROOT.is_dir(), "full reference clones are not available")
class ReferenceGroundTruthTest(unittest.TestCase):
    def test_version_pinned_six_repository_capability_recall(self) -> None:
        truth = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))
        expected_total = 0
        matched_total = 0
        false_product_paths: list[str] = []
        map_nodes = 0
        map_edges = 0
        resolved_edges = 0
        audited_slices = 0
        known_technology_claims = 0
        non_product_parts = {
            "doc",
            "docs",
            "test",
            "tests",
            "example",
            "examples",
            "__tests__",
            "e2e",
        }

        for project, contract in truth.items():
            with self.subTest(project=project):
                repository = REFERENCE_ROOT / project
                commit = subprocess.run(
                    ["git", "-C", str(repository), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                self.assertEqual(commit, contract["commit"])

                capabilities = contract["capabilities"]
                paths = [item["path"] for item in capabilities.values()]
                expected_total += len(paths)
                for relative in paths:
                    self.assertEqual(
                        subprocess.run(
                            ["git", "-C", str(repository), "hash-object", relative],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip(),
                        subprocess.run(
                            ["git", "-C", str(repository), "rev-parse", f"HEAD:{relative}"],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip(),
                    )

                index = build_index(
                    repository,
                    max_files=100_000,
                    max_total_bytes=1_000_000_000,
                    deadline_seconds=120.0,
                )
                self.assertTrue(index["stats"]["scan_complete"])
                validation = validate_index(index, repository)
                self.assertTrue(validation["valid"], validation["issues"])
                features = [
                    feature
                    for feature in index["features"]
                    if feature["kind"] == "capability-cluster"
                ]
                matched_paths = {feature["entrypoint"] for feature in features}
                matched_total += len(matched_paths.intersection(paths))
                audited_slices += sum(len(feature["steps"]) for feature in features)
                self.assertEqual(matched_paths, set(paths))
                self.assertTrue(
                    all(feature["confidence"] == "source-audited" for feature in features)
                )
                self.assertTrue(
                    all(
                        feature["source"].startswith(
                            "source-audited-reference-manifest:"
                        )
                        for feature in features
                    )
                )
                symbols_by_id = {
                    symbol["id"]: symbol for symbol in index["symbols"] if symbol.get("id")
                }
                relationships_by_id = {
                    relationship["id"]: relationship
                    for relationship in index["relationships"]
                    if relationship.get("id")
                }
                evidence_by_id = {
                    item["id"]: item for item in index["evidence"] if item.get("id")
                }
                for feature in features:
                    expected_slug, expected = next(
                        (slug, item) for slug, item in capabilities.items()
                        if item["path"] == feature["entrypoint"]
                    )
                    expected_relationship_contract = expected.get(
                        "relationship_contract", []
                    )
                    audit_contract = CAPABILITY_AUDIT_CONTRACTS[
                        (project, expected_slug)
                    ]
                    actual_relationship_contract = []
                    for item in audit_contract.relationships:
                        source_slice = audit_contract.slices[item.source_slice_index]
                        target_slice = audit_contract.slices[item.target_slice_index]
                        self.assertLessEqual(
                            source_slice.line_start, item.callsite_line_start
                        )
                        self.assertLessEqual(
                            item.callsite_line_start, item.callsite_line_end
                        )
                        self.assertLessEqual(
                            item.callsite_line_end, source_slice.line_end
                        )
                        actual_relationship_contract.append(
                            {
                                "source_slice_index": item.source_slice_index,
                                "source_role": source_slice.role,
                                "target_slice_index": item.target_slice_index,
                                "target_role": target_slice.role,
                                "callsite_line_start": item.callsite_line_start,
                                "callsite_line_end": item.callsite_line_end,
                                "allowed_kinds": list(item.allowed_kinds),
                            }
                        )
                    self.assertEqual(
                        actual_relationship_contract,
                        expected_relationship_contract,
                    )
                    dimensions = {
                        tag.split(":", 1)[0] for tag in feature["technology_tags"]
                    }
                    self.assertEqual(dimensions, set(TECHNOLOGY_DIMENSIONS))
                    self.assertGreaterEqual(len(feature["steps"]), 2)
                    self.assertEqual(
                        [
                            {"symbol": step["source_symbol"], "role": step["source_role"]}
                            for step in feature["steps"]
                        ],
                        expected["roles"],
                    )
                    for step in feature["steps"]:
                        self.assertEqual(step["path"], expected["path"])
                        self.assertTrue(step["relationship_kind"])
                        self.assertTrue(step["claim_scope"])
                        self.assertNotIn("testhelper", step["path"].lower())
                        symbol_id = step.get("symbol_id")
                        relationship_id = step.get("relationship_id")
                        if symbol_id:
                            symbol = symbols_by_id[symbol_id]
                            self.assertEqual(symbol["path"], step["path"])
                            self.assertLessEqual(symbol["line"], step["line_start"])
                            self.assertGreaterEqual(symbol["end_line"], step["line_end"])
                        if relationship_id:
                            relationship = relationships_by_id[relationship_id]
                            audited_symbol_ids = {
                                item["symbol_id"]
                                for item in feature["steps"]
                                if item.get("symbol_id")
                            }
                            self.assertIn(relationship["source_id"], audited_symbol_ids)
                            self.assertIn(relationship["target_id"], audited_symbol_ids)
                            self.assertEqual(step["relationship_kind"], relationship["kind"])
                            self.assertIn("resolved-static:", step["claim_scope"])
                        else:
                            self.assertEqual(step["relationship_kind"], "location-only")
                            self.assertIn("location-only:", step["claim_scope"])
                            self.assertIn("不是已证明实现流", step["explanation"])
                    feature_relationships = {
                        step["relationship_id"]
                        for step in feature["steps"]
                        if step.get("relationship_id")
                    }
                    for relationship_spec in audit_contract.relationships:
                        source_step = feature["steps"][
                            relationship_spec.source_slice_index
                        ]
                        target_step = feature["steps"][
                            relationship_spec.target_slice_index
                        ]
                        matching = [
                            relationship
                            for relationship in relationships_by_id.values()
                            if relationship["id"] in feature_relationships
                            and relationship["source_id"] == source_step.get("symbol_id")
                            and relationship["target_id"] == target_step.get("symbol_id")
                            and relationship["kind"] in relationship_spec.allowed_kinds
                            and relationship["path"] == source_step["path"]
                            and relationship_spec.callsite_line_start
                            <= relationship["line"]
                            <= relationship_spec.callsite_line_end
                        ]
                        self.assertEqual(
                            len(matching),
                            1,
                            f"{project}/{expected_slug} typed callsite did not close",
                        )
                    resolved_relationships = []
                    for relationship_id in sorted(feature_relationships):
                        relationship = relationships_by_id[relationship_id]
                        source = symbols_by_id[relationship["source_id"]]
                        target = symbols_by_id[relationship["target_id"]]
                        resolved_relationships.append(
                            {
                                "id": relationship["id"],
                                "kind": relationship["kind"],
                                "source": {
                                    "id": source["id"],
                                    "qualified_name": source["qualified_name"],
                                },
                                "target": {
                                    "id": target["id"],
                                    "qualified_name": target["qualified_name"],
                                },
                            }
                        )
                    self.assertEqual(
                        resolved_relationships,
                        expected.get("resolved_relationships", []),
                    )
                    typed_endpoint_indexes = {
                        index
                        for relationship_spec in audit_contract.relationships
                        for index in (
                            relationship_spec.source_slice_index,
                            relationship_spec.target_slice_index,
                        )
                    }
                    for step_index in typed_endpoint_indexes:
                        step = feature["steps"][step_index]
                        self.assertTrue(
                            step.get("relationship_id"),
                            f"{project}/{feature['title']}/{step['source_role']} "
                            "is a typed slice endpoint but is marked location-only",
                        )
                    for expected_tag in expected["technology"]:
                        self.assertIn(expected_tag, feature["technology_tags"])
                    closure = []
                    for step in feature["steps"]:
                        symbol = symbols_by_id.get(step.get("symbol_id"))
                        relationship = relationships_by_id.get(step.get("relationship_id"))
                        closure.append(
                            {
                                "source_symbol": step["source_symbol"],
                                "source_role": step["source_role"],
                                "path": step["path"],
                                "line_start": step["line_start"],
                                "line_end": step["line_end"],
                                "snippet_sha256": step["snippet_sha256"],
                                "symbol": None
                                if symbol is None
                                else {
                                    "qualified_name": symbol["qualified_name"],
                                    "path": symbol["path"],
                                    "line": symbol["line"],
                                    "end_line": symbol["end_line"],
                                },
                                "relationship": None
                                if relationship is None
                                else {
                                    "id": relationship["id"],
                                    "kind": relationship["kind"],
                                    "source_id": relationship["source_id"],
                                    "target_id": relationship["target_id"],
                                    "path": relationship["path"],
                                    "line": relationship["line"],
                                },
                                "relationship_kind": step["relationship_kind"],
                                "claim_scope": step["claim_scope"],
                            }
                        )
                    self.assertEqual(_golden_digest(closure), expected["closure_sha256"])
                for feature in features:
                    expected = next(
                        item for item in capabilities.values()
                        if item["path"] == feature["entrypoint"]
                    )
                    source_lines = (repository / expected["path"]).read_text(
                        encoding="utf-8"
                    ).splitlines()
                    for step in feature["steps"]:
                        self.assertEqual(len(step["evidence_ids"]), 1)
                        evidence_item = evidence_by_id[step["evidence_ids"][0]]
                        self.assertIn(
                            evidence_item["kind"],
                            {"capability-source-audited", "capability-role-slice"},
                        )
                        self.assertEqual(evidence_item["path"], step["path"])
                        self.assertEqual(evidence_item["line_start"], step["line_start"])
                        self.assertEqual(evidence_item["line_end"], step["line_end"])
                        snippet = "\n".join(
                            source_lines[step["line_start"] - 1 : step["line_end"]]
                        )
                        digest = hashlib.sha256(snippet.encode("utf-8")).hexdigest()
                        self.assertEqual(step["snippet_sha256"], digest)
                        self.assertEqual(evidence_item["snippet_sha256"], digest)

                    claim_by_dimension = {
                        claim["dimension"]: claim
                        for claim in feature["technology_claims"]
                    }
                    self.assertEqual(set(claim_by_dimension), set(TECHNOLOGY_DIMENSIONS))
                    technology_closure = []
                    for tag in feature["technology_tags"]:
                        dimension, value = tag.split(":", 1)
                        claim = claim_by_dimension[dimension]
                        self.assertEqual(claim["value"], value)
                        self.assertTrue(claim["claim_scope"])
                        if value == "unknown":
                            self.assertEqual(claim["evidence_ids"], [])
                            self.assertIsNone(claim["source_path"])
                            continue
                        known_technology_claims += 1
                        self.assertEqual(len(claim["evidence_ids"]), 1)
                        technology_evidence = evidence_by_id[claim["evidence_ids"][0]]
                        self.assertEqual(
                            technology_evidence["kind"],
                            f"technology-claim:{dimension}",
                        )
                        self.assertEqual(claim["source_path"], expected["path"])
                        self.assertEqual(technology_evidence["path"], expected["path"])
                        self.assertNotIn("testhelper", technology_evidence["path"].lower())
                        technology_closure.append(
                            {
                                "dimension": dimension,
                                "value": value,
                                "claim_scope": claim["claim_scope"],
                                "source_path": claim["source_path"],
                                "evidence": {
                                    "kind": technology_evidence["kind"],
                                    "path": technology_evidence["path"],
                                    "line_start": technology_evidence["line_start"],
                                    "line_end": technology_evidence["line_end"],
                                    "snippet_sha256": technology_evidence["snippet_sha256"],
                                },
                            }
                        )
                    self.assertEqual(
                        _golden_digest(technology_closure),
                        expected["technology_claims_sha256"],
                    )
                for feature in index["features"]:
                    locations = [
                        step.get("path", "") for step in feature.get("steps", [])
                    ]
                    locations.extend(
                        evidence_by_id[evidence_id].get("path", "")
                        for evidence_id in feature.get("evidence_ids", [])
                        if evidence_id in evidence_by_id
                    )
                    for location in locations:
                        self.assertNotIn("testhelper", location.lower())
                        parts = {part.lower() for part in Path(location).parts}
                        if parts.intersection(non_product_parts):
                            false_product_paths.append(location)

                report = render_report(index)
                self.assertIn('class="codemap-nodes"', report)
                self.assertIn('class="codemap-edges"', report)
                self.assertNotIn('<pre class="codemap-source">', report)
                capability_ids = {feature["id"] for feature in features}
                maps = [
                    item
                    for item in index["codemaps"]
                    if item["feature_id"] in capability_ids
                ]
                map_nodes += sum(len(item["nodes"]) for item in maps)
                map_edges += sum(len(item["edges"]) for item in maps)
                resolved_edges += sum(len(item["resolved_edge_ids"]) for item in maps)

        self.assertEqual(expected_total, 19)
        self.assertGreaterEqual(matched_total / expected_total, 0.8)
        self.assertEqual(matched_total, expected_total)
        self.assertEqual(false_product_paths, [])
        self.assertEqual(known_technology_claims, 59)
        self.assertEqual(audited_slices, 66)
        self.assertGreaterEqual(map_nodes, expected_total * 2)
        self.assertGreater(map_edges, 0)
        self.assertEqual(resolved_edges, 18)

    def test_copied_reference_files_without_git_identity_are_not_source_audited(self) -> None:
        source = REFERENCE_ROOT / "sourcebridge"
        paths = [
            "internal/graph/store.go",
            "internal/graph/execution_path.go",
            "workers/knowledge/code_tour.py",
        ]
        with tempfile.TemporaryDirectory() as directory:
            copy_root = Path(directory)
            for relative in paths:
                destination = copy_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, destination)

            index = build_index(copy_root)

            self.assertFalse(index["project"]["is_git"])
            self.assertFalse(
                any(
                    feature["confidence"] == "source-audited"
                    for feature in index["features"]
                )
            )

    def test_waku_is_a_separate_evidence_bounded_compatibility_corpus(self) -> None:
        repository = REFERENCE_ROOT / "waku-agent"
        self.assertTrue(repository.is_dir())

        index = build_index(
            repository,
            max_files=100_000,
            max_total_bytes=1_000_000_000,
            deadline_seconds=120.0,
        )
        validation = validate_index(index, repository)
        self.assertTrue(validation["valid"], validation["issues"])
        compatibility = [
            feature
            for feature in index["features"]
            if "compatibility-corpus:waku-not-curated"
            in feature["technology_tags"]
        ]
        self.assertEqual(
            {
                next(
                    tag.split(":", 1)[1]
                    for tag in feature["technology_tags"]
                    if tag.startswith("compatibility-mechanism:")
                )
                for feature in compatibility
            },
            {
                "memory",
                "graph",
                "loop",
                "gateway",
                "voice",
                "tools",
                "providers",
                "dashboard",
                "eval",
            },
        )
        self.assertFalse(
            any(feature["kind"] == "capability-cluster" for feature in index["features"])
        )
        tutorial_by_feature = {
            tutorial["feature_id"]: tutorial for tutorial in index["tutorials"]
        }
        relationship_ids = {
            relationship["id"] for relationship in index["relationships"]
        }
        for feature in compatibility:
            self.assertEqual(feature["kind"], "entrypoint-candidate")
            self.assertEqual(feature["confidence"], "candidate")
            self.assertEqual(
                feature["source"], "evidence-bounded-static-feature-discovery"
            )
            self.assertIn(
                "compatibility-corpus:waku-not-curated",
                feature["technology_tags"],
            )
            self.assertEqual(
                {claim["dimension"] for claim in feature["technology_claims"]},
                set(TECHNOLOGY_DIMENSIONS),
            )
            self.assertTrue(
                any(
                    claim["value"] == "unknown"
                    for claim in feature["technology_claims"]
                )
            )
            tutorial = tutorial_by_feature[feature["id"]]
            difficulty_map = tutorial.get("difficulty_map", {})
            self.assertGreaterEqual(
                len(difficulty_map.get("items", [])),
                2,
                f"{feature['entrypoint']} must explain its implementation difficulties",
            )
            for source_slice in tutorial["teaching_contract"]["main_chain"]:
                relationship_id = source_slice["relationship_id"]
                if source_slice["relationship_status"] == "resolved-static":
                    self.assertIn(relationship_id, relationship_ids)
                else:
                    self.assertEqual(relationship_id, "")

        graph_feature = next(
            feature
            for feature in compatibility
            if "compatibility-mechanism:graph" in feature["technology_tags"]
        )
        graph_difficulties = {
            item["id"]
            for item in tutorial_by_feature[graph_feature["id"]]["difficulty_map"]["items"]
        }
        self.assertEqual(
            {
                "wave-barrier",
                "state-collision",
                "fan-in-join",
                "routing-and-cycles",
                "durability-boundary",
            },
            graph_difficulties,
        )

        report = render_report(index)
        for title in (
            "Agent Loop：推理、工具调用与终止条件",
            "Memory：长期记忆与周期整理",
            "Graph Workflow：节点、并行波次与显式路由",
            "Multi-channel Gateway：通道生命周期协调",
            "Voice：本地录音、语音识别与朗读输出",
            "Tools / MCP：工具注册、调用与错误隔离",
            "Model Providers：多模型统一适配",
            "Dashboard / Observability：本地交互与运行观测",
            "Eval / Release Gate：评测与发布门",
        ):
            self.assertIn(title, report)
        visible = report.split('<script id="repo-data"', 1)[0]
        self.assertNotIn("已确认程序入口", visible)
        self.assertLess(
            visible.index("这个项目有哪些功能"),
            visible.index("最后再看源码证据"),
        )
        self.assertIn("Waku：单独验证，不进入六仓 curated 技术排名", report)
        self.assertNotIn("六仓机制对照", report)


if __name__ == "__main__":
    unittest.main()
