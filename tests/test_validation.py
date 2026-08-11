from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from repo_teacher.indexer import _integrity_digest, build_index
from repo_teacher.models import ProjectSnapshot, stable_id
from repo_teacher.validation import validate_index


class IndexValidationTest(unittest.TestCase):
    def test_current_index_is_valid_and_changed_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            source.write_text("def main():\n    return 1\n", encoding="utf-8")
            index = build_index(root)

            valid = validate_index(index, root)
            self.assertTrue(valid["valid"], valid["issues"])

            source.write_text("def main():\n    return 2\n", encoding="utf-8")
            stale = validate_index(index, root)
            self.assertFalse(stale["valid"])
            self.assertIn("stale-file", {item["code"] for item in stale["issues"]})
            self.assertIn("stale-evidence", {item["code"] for item in stale["issues"]})

    def test_dangling_feature_reference_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            index = build_index(root)
            index["features"][0]["evidence_ids"].append("missing")

            result = validate_index(index, root)

            self.assertFalse(result["valid"])
            self.assertIn("dangling-evidence-ref", {item["code"] for item in result["issues"]})

    def test_schema_fingerprint_integrity_and_completeness_are_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            index = build_index(root)

            wrong_schema = deepcopy(index)
            wrong_schema["schema_version"] = "0"
            wrong_fingerprint = deepcopy(index)
            wrong_fingerprint["analysis_fingerprint"] = "0" * 64
            corrupt = deepcopy(index)
            corrupt["integrity_sha256"] = "0" * 64
            partial = deepcopy(index)
            partial["stats"]["scan_complete"] = False
            partial["freshness"] = "partial-unvalidated"
            partial["integrity_sha256"] = _integrity_digest(partial)

            cases = {
                "schema-mismatch": wrong_schema,
                "analysis-fingerprint-mismatch": wrong_fingerprint,
                "integrity-mismatch": corrupt,
                "partial-index": partial,
            }
            for expected, candidate in cases.items():
                with self.subTest(expected=expected):
                    result = validate_index(candidate, root)
                    self.assertFalse(result["valid"])
                    self.assertIn(expected, {item["code"] for item in result["issues"]})

    def test_fabricated_exact_feature_is_rejected_even_with_rehashed_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            index = build_index(root)
            index["features"] = [
                {
                    "id": "feature_fabricated",
                    "title": "Transfers all funds",
                    "kind": "runtime-behavior",
                    "summary": "verified production behavior",
                    "entrypoint": "pay_admin",
                    "confidence": "exact",
                    "source": "fabricated",
                    "steps": [],
                    "component_ids": [],
                    "evidence_ids": [],
                    "test_evidence_ids": [],
                    "technology_tags": [],
                    "entry_symbol_id": None,
                }
            ]
            index["integrity_sha256"] = _integrity_digest(index)

            result = validate_index(index, root)

            self.assertFalse(result["valid"])
            codes = {item["code"] for item in result["issues"]}
            self.assertIn("feature-without-evidence", codes)
            self.assertIn("unsupported-feature-confidence", codes)

    def test_exact_entry_rejects_unknown_boundary_analyzer_after_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.py"
            source.write_text(
                'def main():\n    return 1\n\nif __name__ == "__main__":\n    main()\n',
                encoding="utf-8",
            )
            index = build_index(root)
            self.assertTrue(index["features"])
            self.assertTrue(validate_index(index, root)["valid"])

            feature = index["features"][0]
            supporting = next(
                item
                for item in index["evidence"]
                if item["id"] in feature["evidence_ids"]
                and item["kind"] == "entry-declaration"
            )
            supporting["analyzer"] = "untrusted-executable-file-marker-wrapper"
            index["integrity_sha256"] = _integrity_digest(index)
            rejected = validate_index(index, root)
            self.assertFalse(rejected["valid"])
            self.assertIn(
                "unsupported-feature-confidence",
                {item["code"] for item in rejected["issues"]},
            )

    def test_framework_entry_accepts_exact_call_line_and_conservative_summary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "@app.get('/health')\n"
                "def health(): return {}\n",
                encoding="utf-8",
            )
            index = build_index(root)
            feature = next(
                item
                for item in index["features"]
                if item["entrypoint"] == "GET /health"
            )
            evidence = {item["id"]: item for item in index["evidence"]}
            entry = evidence[feature["evidence_ids"][0]]
            framework = next(
                item
                for item in feature["technology_claims"]
                if item["dimension"] == "framework"
            )

            self.assertEqual(entry["line_start"], entry["line_end"])
            self.assertEqual(
                [evidence[item]["analyzer"].rsplit(":", 1)[-1]
                 for item in framework["evidence_ids"]],
                ["import", "factory", "call"],
            )
            self.assertIn("保守同作用域合同", feature["summary"])
            self.assertIn("实际可达性未知", feature["summary"])

            result = validate_index(index, root)

            self.assertTrue(result["valid"], result["issues"])

    def test_framework_entry_rejects_incomplete_provenance_and_runtime_claim(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "@app.get('/health')\n"
                "def health(): return {}\n",
                encoding="utf-8",
            )
            baseline = build_index(root)
            feature = next(
                item
                for item in baseline["features"]
                if item["entrypoint"] == "GET /health"
            )
            feature_index = baseline["features"].index(feature)
            framework_index = next(
                index
                for index, item in enumerate(feature["technology_claims"])
                if item["dimension"] == "framework"
            )

            incomplete = deepcopy(baseline)
            incomplete_claim = incomplete["features"][feature_index][
                "technology_claims"
            ][framework_index]
            incomplete_claim["evidence_ids"] = incomplete_claim["evidence_ids"][:2]
            incomplete["integrity_sha256"] = _integrity_digest(incomplete)

            runtime_claim = deepcopy(baseline)
            runtime_claim["features"][feature_index]["summary"] = (
                "该 HTTP 接口已经确认可从生产流量到达并会在运行时执行。"
            )
            runtime_claim["integrity_sha256"] = _integrity_digest(runtime_claim)

            for candidate in (incomplete, runtime_claim):
                result = validate_index(candidate, root)
                self.assertFalse(result["valid"], result["issues"])
                self.assertIn(
                    "feature-claim-mismatch",
                    {item["code"] for item in result["issues"]},
                )

    def test_framework_module_callsite_without_symbol_is_a_closed_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.js").write_text(
                "import express from 'express';\n"
                "const app = express();\n"
                "app.get('/module-direct', handler);\n",
                encoding="utf-8",
            )

            index = build_index(root)
            feature = next(
                item for item in index["features"]
                if item["entrypoint"] == "GET /module-direct"
            )

            self.assertIsNone(feature["entry_symbol_id"])
            self.assertEqual(len(feature["steps"]), 1)
            self.assertIsNone(feature["steps"][0]["symbol_id"])
            result = validate_index(index, root)
            self.assertTrue(result["valid"], result["issues"])

            forged = deepcopy(index)
            forged_feature = next(
                item for item in forged["features"]
                if item["entrypoint"] == "GET /module-direct"
            )
            forged_feature["steps"][0]["line_start"] = 2
            forged["integrity_sha256"] = _integrity_digest(forged)
            rejected = validate_index(forged, root)
            self.assertFalse(rejected["valid"])
            self.assertIn(
                "feature-claim-mismatch",
                {item["code"] for item in rejected["issues"]},
            )

    def test_static_feature_claim_mutations_fail_even_after_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                'def main():\n    return 1\n\nif __name__ == "__main__":\n    main()\n',
                encoding="utf-8",
            )
            baseline = build_index(root)
            self.assertTrue(validate_index(baseline, root)["valid"])
            feature = baseline["features"][0]
            self.assertEqual(feature["confidence"], "exact-entry")

            mutations = {
                "id": "feature_rehashed_forgery",
                "title": "Transfers all funds",
                "entrypoint": "pay_admin",
                "source": "fabricated",
                "summary": "Verified production behavior.",
                "entry_symbol_id": None,
            }
            for field, value in mutations.items():
                with self.subTest(field=field):
                    candidate = deepcopy(baseline)
                    candidate["features"][0][field] = value
                    candidate["integrity_sha256"] = _integrity_digest(candidate)

                    result = validate_index(candidate, root)

                    self.assertFalse(result["valid"], result["issues"])
                    self.assertIn(
                        "feature-claim-mismatch",
                        {item["code"] for item in result["issues"]},
                    )

    def test_curated_feature_claim_mutations_fail_even_after_rehash(self) -> None:
        reference = Path(
            "/Volumes/T7/workspace/ontology/graph/repo/understand-anything"
        )
        if not (reference / ".git").is_dir():
            self.skipTest("reference Git clone is not available")
        baseline = build_index(reference)
        self.assertTrue(validate_index(baseline, reference)["valid"])
        feature_index = next(
            index
            for index, feature in enumerate(baseline["features"])
            if feature["confidence"] == "source-audited"
        )
        feature = baseline["features"][feature_index]
        replacement_symbol = next(
            (
                symbol["id"]
                for symbol in baseline["symbols"]
                if symbol["id"] != feature.get("entry_symbol_id")
            ),
            None,
        )
        mutations = {
            "id": "capability_rehashed_forgery",
            "title": "Unaudited capability",
            "entrypoint": "src/unrelated.ts",
            "source": "fabricated",
            "summary": "A broader claim than the audited source supports.",
            "entry_symbol_id": replacement_symbol,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                candidate = deepcopy(baseline)
                candidate["features"][feature_index][field] = value
                candidate["integrity_sha256"] = _integrity_digest(candidate)

                result = validate_index(candidate, reference)

                self.assertFalse(result["valid"], result["issues"])
                self.assertIn(
                    "feature-claim-mismatch",
                    {item["code"] for item in result["issues"]},
                )

    def test_validation_detects_new_and_deleted_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "main.py"
            original.write_text("def main(): pass\n", encoding="utf-8")
            index = build_index(root)

            (root / "late.py").write_text("VALUE = 1\n", encoding="utf-8")
            added = validate_index(index, root)
            self.assertIn("unindexed-source-file", {item["code"] for item in added["issues"]})

            (root / "late.py").unlink()
            original.unlink()
            deleted = validate_index(index, root)
            self.assertIn("indexed-source-deleted", {item["code"] for item in deleted["issues"]})

    def test_validation_checks_symbol_membership_and_relationship_path_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def target(): return 1\ndef main(): return target()\n",
                encoding="utf-8",
            )
            index = build_index(root)
            index["files"][0]["symbols"] = []
            index["relationships"][0]["path"] = "missing.py"
            index["integrity_sha256"] = _integrity_digest(index)

            result = validate_index(index, root)

            codes = {item["code"] for item in result["issues"]}
            self.assertIn("symbol-membership-mismatch", codes)
            self.assertTrue(
                {"relationship-path-mismatch", "invalid-relationship-range"}.issubset(codes)
            )

    def test_unknown_git_dirty_state_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main(): pass\n", encoding="utf-8")
            index = build_index(root)
            index["project"]["is_git"] = True
            index["integrity_sha256"] = _integrity_digest(index)
            unknown = ProjectSnapshot(
                name=root.name,
                path=str(root),
                git_root=str(root),
                is_git=True,
                commit=None,
                branch=None,
                dirty=None,
                remote=None,
                license=None,
                analyzed_at="2026-01-01T00:00:00+00:00",
            )

            with patch("repo_teacher.validation.capture_snapshot", return_value=unknown):
                result = validate_index(index, root)

            self.assertTrue(result["valid"], result["issues"])
            self.assertIn("dirty-state-unknown", {item["code"] for item in result["issues"]})

    def test_rehashed_symbol_kind_and_relationship_forgery_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            baseline = build_index(root)

            wrong_kind = deepcopy(baseline)
            symbol = wrong_kind["symbols"][0]
            old_id = symbol["id"]
            symbol["kind"] = "class"
            symbol["id"] = stable_id(
                "symbol",
                symbol["path"],
                symbol["kind"],
                symbol["qualified_name"],
                symbol["line"],
            )
            wrong_kind["files"][0]["symbols"] = [symbol["id"]]
            for relationship in wrong_kind["relationships"]:
                if relationship["source_id"] == old_id:
                    relationship["source_id"] = symbol["id"]
                if relationship.get("target_id") == old_id:
                    relationship["target_id"] = symbol["id"]
            wrong_kind["integrity_sha256"] = _integrity_digest(wrong_kind)

            forged_edge = deepcopy(baseline)
            file = forged_edge["files"][0]
            forged_edge["relationships"].append(
                {
                    "id": stable_id(
                        "rel", "calls", file["id"], "pay_admin", "main.py", 1
                    ),
                    "source_id": file["id"],
                    "target_id": None,
                    "target_name": "pay_admin",
                    "kind": "calls",
                    "path": "main.py",
                    "line": 1,
                    "analyzer": "python-ast",
                    "confidence": "heuristic",
                    "receiver_type_hint": None,
                }
            )
            forged_edge["integrity_sha256"] = _integrity_digest(forged_edge)

            for candidate in (wrong_kind, forged_edge):
                with self.subTest(candidate=len(candidate["relationships"])):
                    result = validate_index(candidate, root)
                    self.assertFalse(result["valid"], result["issues"])
                    self.assertIn(
                        "analysis-semantics-mismatch",
                        {item["code"] for item in result["issues"]},
                    )

    def test_go_import_alias_is_explicitly_supported_but_nearby_kinds_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.go").write_text(
                'package main\nimport alias "fmt"\nfunc main() { alias.Println("ok") }\n',
                encoding="utf-8",
            )
            baseline = build_index(root)
            aliases = [
                item
                for item in baseline["relationships"]
                if item["kind"] == "go-import-alias"
            ]
            self.assertEqual(len(aliases), 1)
            self.assertTrue(validate_index(baseline, root)["valid"])

            forged = deepcopy(baseline)
            alias = next(
                item
                for item in forged["relationships"]
                if item["kind"] == "go-import-alias"
            )
            alias["kind"] = "go-import-alias-shadow"
            forged["integrity_sha256"] = _integrity_digest(forged)
            result = validate_index(forged, root)
            self.assertFalse(result["valid"])
            self.assertIn(
                "unsupported-relationship-kind",
                {item["code"] for item in result["issues"]},
            )

    def test_rehashed_tutorial_codemap_and_stats_forgery_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def main():\n    return 1\nif __name__ == '__main__':\n    main()\n",
                encoding="utf-8",
            )
            baseline = build_index(root)
            mutations = (
                ("tutorials", lambda value: value.append({"id": "tutorial_fake"})),
                ("codemaps", lambda value: value.append({"id": "codemap_fake"})),
                ("stats", lambda value: value.__setitem__("files", 999)),
            )
            for field, mutate in mutations:
                with self.subTest(field=field):
                    candidate = deepcopy(baseline)
                    mutate(candidate[field])
                    candidate["integrity_sha256"] = _integrity_digest(candidate)
                    result = validate_index(candidate, root)
                    self.assertFalse(result["valid"], result["issues"])
                    self.assertIn(
                        "derived-artifacts-mismatch",
                        {item["code"] for item in result["issues"]},
                    )


if __name__ == "__main__":
    unittest.main()
