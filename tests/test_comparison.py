from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_teacher.comparison import (
    SCENARIO_PROFILES,
    SCENARIO_ROUTE_PRIORITIES,
    _scenario_recommendations,
    build_technology_comparison,
)
from repo_teacher.reference_catalog import AUDITED_CLAIMS, REFERENCE_CATALOG, REFERENCE_IDENTITIES


def fixture_index(name: str, paths: list[str], symbols: list[tuple[str, str]], root: Path) -> dict:
    content = "def fixture(): pass\nsecond line\nthird line\n"
    files = []
    for index, path in enumerate(paths):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        files.append(
            {
                "id": f"file-{index}",
                "path": path,
                "language": "Python",
                "size": len(content.encode()),
                "lines": 3,
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
                "module": path.split("/", 1)[0],
                "symbols": [],
            }
        )
    by_path = {item["path"]: item for item in files}
    symbol_rows = [
        {
            "id": f"symbol-{index}",
            "file_id": by_path[path]["id"],
            "path": path,
            "name": symbol,
            "qualified_name": symbol,
            "kind": "function",
            "line": 1,
            "end_line": 2,
            "analyzer": "python-ast",
            "confidence": "exact",
            "parent_id": None,
            "signature": "",
            "exported": True,
        }
        for index, (path, symbol) in enumerate(symbols)
    ]
    evidence = [
        {
            "id": "evidence-valid",
            "path": paths[0],
            "line_start": 1,
            "line_end": 2,
            "snippet": "def fixture(): pass\nsecond line",
            "snippet_sha256": hashlib.sha256("def fixture(): pass\nsecond line".encode()).hexdigest(),
            "kind": "source",
            "confidence": "exact",
            "analyzer": "source-lines",
            "symbol_id": symbol_rows[0]["id"] if symbol_rows else None,
        },
        {
            "id": "symbol-looking-but-invalid-evidence",
            "path": paths[0],
            "line_start": 1,
            # deliberately missing line_end and snippet_sha256
        },
        {
            "id": "evidence-wrong-digest",
            "path": paths[0],
            "line_start": 1,
            "line_end": 2,
            "snippet": "def fixture(): pass\nsecond line",
            "snippet_sha256": "b" * 64,
        },
    ]
    return {
        "schema_version": "2.0",
        "project": {
            "name": name,
            "path": str(root),
            "commit": "abc",
            "remote": f"https://example.com/{name}.git",
            "license": "MIT",
        },
        "stats": {"files": len(files), "symbols": len(symbol_rows), "languages": {"Python": len(files)}},
        "files": files,
        "symbols": symbol_rows,
        "relationships": [],
        "evidence": evidence,
    }


def curated_fixture(project_key: str, root: Path) -> tuple[dict, str]:
    identity = REFERENCE_IDENTITIES[project_key]
    paths = sorted({path for item in REFERENCE_CATALOG[project_key].values() for path in item["source_paths"]})
    index = fixture_index(project_key, paths, [(paths[0], "entry")], root)
    index["project"].update(
        {
            "remote": f"https://{identity['remote']}.git",
            "commit": identity["commit"],
            "path": str(root),
        }
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Repo Teacher Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "repo-teacher@example.invalid"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", f"https://{identity['remote']}.git"], check=True
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    index["project"]["commit"] = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    material = "\n".join(f"{item['path']}\0{item['sha256']}" for item in index["files"])
    return index, hashlib.sha256(material.encode()).hexdigest()


class TechnologyComparisonTest(unittest.TestCase):
    def test_groups_projects_by_capability_and_keeps_true_evidence_separate_from_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            graph_project = fixture_index(
                "GraphProject",
                ["core/graph_builder.py", "core/fingerprint.py"],
                [("core/graph_builder.py", "build_call_graph")],
                Path(directory),
            )
            result = build_technology_comparison([graph_project])

        self.assertEqual(result["schema_version"], "2.0")
        capability = next(item for item in result["capabilities"] if item["slug"] == "code-graph")
        option = result["options_by_id"][capability["option_ids"][0]]
        self.assertEqual(option["source"], "heuristic-index-match")
        self.assertEqual(option["evidence_ids"], ["evidence-valid"])
        self.assertIn("symbol-0", option["symbol_ids"])
        self.assertNotIn("symbol-looking-but-invalid-evidence", option["evidence_ids"])
        self.assertNotIn("evidence-wrong-digest", option["evidence_ids"])
        self.assertEqual(option["source_references"][0]["reference_scope"], "index-evidence")
        self.assertFalse(option["source_references"][0]["supports_claim"])
        self.assertTrue(option["source_references"][0]["source_uri"].startswith("file:///"))

    def test_does_not_claim_capability_without_matching_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = fixture_index("Plain", ["src/math.py"], [("src/math.py", "add")], Path(directory))
            result = build_technology_comparison([project])

        self.assertEqual(result["capabilities"], [])
        self.assertEqual(result["options_by_id"], {})

    def test_exact_audited_identity_uses_curated_catalog_and_exposes_methodology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sourcebridge, bundle = curated_fixture("sourcebridge", Path(directory))
            identity = {
                **REFERENCE_IDENTITIES["sourcebridge"],
                "commit": sourcebridge["project"]["commit"],
                "source_bundle_sha256": bundle,
            }
            with patch.dict(REFERENCE_IDENTITIES, {"sourcebridge": identity}):
                result = build_technology_comparison([sourcebridge])

        capability = next(item for item in result["capabilities"] if item["slug"] == "code-parsing")
        option = result["options_by_id"][capability["option_ids"][0]]
        self.assertEqual(option["source"], "curated-source-audit")
        self.assertEqual(option["confidence"], "source-audited")
        self.assertEqual(option["project_key"], "sourcebridge")
        self.assertEqual(option["score_basis"], "reviewer-rubric-signal")
        self.assertIn("scenario_scores", option)
        self.assertFalse(result["score_methodology"]["objective_benchmark"])
        self.assertNotIn("recommendation_option_id", capability)
        self.assertTrue(capability["recommendation_groups"])
        self.assertEqual(capability["default_scenario"], "local-first-product")
        self.assertEqual(
            capability["selected_recommendation"]["preferred_class"], "deterministic-syntax-index"
        )
        self.assertEqual(capability["recommendation_option_ids"], [option["id"]])

    def test_same_name_wrong_remote_and_tampered_source_fall_back_to_heuristic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sourcebridge, bundle = curated_fixture("sourcebridge", Path(directory))
            identity = {
                **REFERENCE_IDENTITIES["sourcebridge"],
                "commit": sourcebridge["project"]["commit"],
                "source_bundle_sha256": bundle,
            }
            with patch.dict(REFERENCE_IDENTITIES, {"sourcebridge": identity}):
                sourcebridge["project"]["remote"] = "https://evil.invalid/sourcebridge.git"
                subprocess.run(
                    ["git", "-C", directory, "remote", "set-url", "origin", "https://evil.invalid/sourcebridge.git"],
                    check=True,
                )
                result = build_technology_comparison([sourcebridge])
                self.assertTrue(result["options"])
                self.assertTrue(all(item["source"] == "heuristic-index-match" for item in result["options"]))

    def test_curated_claim_range_is_hash_bound_and_not_confused_with_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sourcebridge, bundle = curated_fixture("sourcebridge", Path(directory))
            identity = {
                **REFERENCE_IDENTITIES["sourcebridge"],
                "commit": sourcebridge["project"]["commit"],
                "source_bundle_sha256": bundle,
            }
            path = REFERENCE_CATALOG["sourcebridge"]["code-parsing"]["source_paths"][0]
            claims = ({"claim": "Fixture parser entry exists.", "path": path, "line_start": 1, "line_end": 2},)
            with (
                patch.dict(REFERENCE_IDENTITIES, {"sourcebridge": identity}),
                patch.dict(AUDITED_CLAIMS, {("sourcebridge", "code-parsing"): claims}),
            ):
                result = build_technology_comparison([sourcebridge])

        capability = next(item for item in result["capabilities"] if item["slug"] == "code-parsing")
        option = result["options_by_id"][capability["option_ids"][0]]
        reference = next(item for item in option["source_references"] if item["path"] == path)
        self.assertEqual(reference["reference_scope"], "claim-evidence")
        self.assertEqual(reference["evidence_scope"], "claim")
        self.assertTrue(reference["supports_option_claim"])
        self.assertRegex(reference["snippet_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(reference["claim_evidence_id"].startswith("catalog-claim_"))
        claim_by_id = {item["id"]: item for item in result["claim_evidence"]}
        self.assertIn(reference["claim_evidence_id"], claim_by_id)
        self.assertEqual(option["claim_evidence_ids"], [reference["claim_evidence_id"]])
        self.assertEqual(claim_by_id[reference["claim_evidence_id"]]["snippet_sha256"], reference["snippet_sha256"])

        with tempfile.TemporaryDirectory() as directory:
            sourcebridge, bundle = curated_fixture("sourcebridge", Path(directory))
            identity = {
                **REFERENCE_IDENTITIES["sourcebridge"],
                "commit": sourcebridge["project"]["commit"],
                "source_bundle_sha256": bundle,
            }
            with patch.dict(REFERENCE_IDENTITIES, {"sourcebridge": identity}):
                sourcebridge["files"][0]["sha256"] = "f" * 64
                result = build_technology_comparison([sourcebridge])
                self.assertTrue(all(item["source"] == "heuristic-index-match" for item in result["options"]))

    def test_evidence_ids_always_resolve_to_unique_evidence_records_in_owning_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = fixture_index(
                "EvidenceProject", ["src/citation.py"], [("src/citation.py", "citation")], Path(directory)
            )
            result = build_technology_comparison([project])
            evidence_by_id = {item["id"]: item for item in project["evidence"] if "snippet_sha256" in item}
            for option in result["options"]:
                for evidence_id in option["evidence_ids"]:
                    self.assertIn(evidence_id, evidence_by_id)
                    self.assertNotIn(evidence_id, option["symbol_ids"])

    def test_scenario_selection_changes_the_recommended_route_instead_of_listing_singletons(self) -> None:
        options = [
            {
                "id": "dynamic",
                "project_name": "OpenWiki",
                "comparison_class": "dynamic-planner-subagent-runtime",
                "scenario_scores": {"local-first-product": 70, "precise-static-analysis": 45},
                "score_uncertainty": 5,
                "source_paths": ["src/agent/index.ts"],
                "limitations": ["动态行为需预算和审批边界"],
            },
            {
                "id": "fixed",
                "project_name": "CodeBoarding",
                "comparison_class": "fixed-analysis-multi-agent-workflow",
                "scenario_scores": {"local-first-product": 88, "precise-static-analysis": 92},
                "score_uncertainty": 5,
                "source_paths": ["codeboarding_workflows/orchestration.py"],
                "limitations": ["拓扑固定"],
            },
        ]

        recommendations = _scenario_recommendations("agent-workflow", options)

        self.assertEqual(recommendations["local-first-product"]["primary_option_ids"], ["dynamic"])
        self.assertEqual(recommendations["precise-static-analysis"]["primary_option_ids"], ["fixed"])
        self.assertEqual(len(recommendations["local-first-product"]["primary_option_ids"]), 1)

    def test_all_scenario_routes_explain_goal_mechanism_signal_limit_and_switch_condition(self) -> None:
        all_recommendations: list[dict] = []
        for capability_slug in next(iter(SCENARIO_ROUTE_PRIORITIES.values())):
            routes = list(
                dict.fromkeys(
                    route
                    for scenario in SCENARIO_PROFILES
                    for route in SCENARIO_ROUTE_PRIORITIES[scenario][capability_slug]
                )
            )
            options = [
                {
                    "id": f"{capability_slug}-{index}",
                    "project_name": f"Project {index}",
                    "comparison_class": route,
                    "scenario_scores": {scenario: 70 + index for scenario in SCENARIO_PROFILES},
                    "dimension_scores": {
                        "semantic_precision": 75,
                        "evidence_traceability": 75,
                        "tutorial_quality": 75,
                        "incremental_efficiency": 75,
                        "visualization": 75,
                        "production_readiness": 75,
                        "reuse_value": 75,
                    },
                    "score_uncertainty": 5,
                    "source_paths": [f"src/{capability_slug}/{index}.py"],
                    "strengths": [f"{route} 的可核验机制"],
                    "limitations": [f"{route} 的生产边界仍需验证"],
                }
                for index, route in enumerate(routes)
            ]

            recommendations = _scenario_recommendations(capability_slug, options)
            self.assertEqual(set(recommendations), set(SCENARIO_PROFILES))
            self.assertEqual(len({item["why"] for item in recommendations.values()}), 4)
            self.assertEqual(
                len({item["decision_reason"]["route_fit"] for item in recommendations.values()}),
                4,
            )
            self.assertEqual(
                len({item["decision_reason"]["alternative_trigger"] for item in recommendations.values()}),
                4,
            )
            all_recommendations.extend(recommendations.values())

        self.assertEqual(len(all_recommendations), 32)
        self.assertEqual(len({item["why"] for item in all_recommendations}), 32)
        for recommendation in all_recommendations:
            reason = recommendation["decision_reason"]
            self.assertEqual(
                set(reason),
                {
                    "scenario_goal",
                    "preferred_mechanism",
                    "route_fit",
                    "primary_strength",
                    "primary_signal",
                    "critical_limit",
                    "alternative_trigger",
                    "alternative_mechanism",
                    "alternative_projects",
                },
            )
            self.assertTrue(all(reason[key] for key in reason if key != "primary_signal"))
            self.assertEqual(
                set(reason["primary_signal"]),
                {"dimension", "label", "value", "source"},
            )
            self.assertIn(reason["scenario_goal"], recommendation["why"])
            self.assertIn(reason["primary_strength"], recommendation["why"])
            self.assertIn(reason["critical_limit"], recommendation["why"])
            self.assertIn(reason["alternative_trigger"], recommendation["why"])
            self.assertNotIn("场景先选择", recommendation["why"])


if __name__ == "__main__":
    unittest.main()
