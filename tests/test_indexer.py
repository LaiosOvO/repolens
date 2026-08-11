from __future__ import annotations

import json
import secrets
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from repo_teacher.indexer import (
    _analysis_fingerprint,
    _derived_artifacts_digest,
    _file_analysis_digest,
    _integrity_digest,
    build_index,
)
from repo_teacher.module_locator import locate_modules
from repo_teacher.models import stable_id
from repo_teacher.persistence import (
    GenerationPublisher,
    OutputLock,
    read_published_json,
)
from repo_teacher.scanner import scan_repository as real_scan_repository
from repo_teacher.validation import validate_index


def publish_baseline(index: dict[str, object], output: Path) -> dict[str, object]:
    """Round-trip a test baseline through the production publication trust path."""

    generation_id = secrets.token_hex(16)
    payload = deepcopy(index)
    payload["generation_id"] = generation_id
    payload["integrity_sha256"] = _integrity_digest(payload)
    artifacts = {
        "index.json": json.dumps(payload),
        "index.html": (
            '<html><head><meta name="repo-teacher-generation" '
            f'content="{generation_id}"></head></html>'
        ),
    }
    with OutputLock(output):
        GenerationPublisher(output, generation_id).publish(artifacts)
    return read_published_json(output, "index.json")


class IndexerTest(unittest.TestCase):
    def test_unverified_in_memory_baseline_is_never_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            baseline = build_index(root)

            rebuilt = build_index(root, previous_index=baseline)

            self.assertEqual(
                rebuilt["change_classification"]["baseline_status"], "rejected"
            )
            self.assertEqual(rebuilt["stats"]["reused_files"], 0)

    def test_python_unknown_multilevel_receiver_is_not_leaf_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "audio.py").write_text(
                "class Ears:\n"
                "    def transcribe(self, audio, language: str | None = None) -> str:\n"
                "        segments, _ = self.model.transcribe(\n"
                "            audio, language=language\n"
                "        )\n"
                "        return ' '.join(seg.text.strip() for seg in segments).strip()\n"
                "\n"
                "    def helper(self):\n"
                "        return 1\n"
                "\n"
                "    def run(self):\n"
                "        return self.helper()\n",
                encoding="utf-8",
            )

            index = build_index(root)
            model_call = next(
                item
                for item in index["relationships"]
                if item["target_name"] == "self.model.transcribe"
            )
            self_call = next(
                item
                for item in index["relationships"]
                if item["target_name"] == "self.helper"
            )
            helper = next(
                item for item in index["symbols"] if item["qualified_name"] == "Ears.helper"
            )

            self.assertIsNone(model_call["target_id"])
            self.assertEqual(self_call["target_id"], helper["id"])

    def test_fully_resigned_forged_language_claims_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.go").write_text(
                "package main\nfunc main() {}\n", encoding="utf-8"
            )
            (root / "web.js").write_text(
                "export function boot() { return 1; }\n", encoding="utf-8"
            )
            (root / "main.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            output = root / ".published"
            with patch("repo_teacher.indexer.discover_features", return_value=[]):
                baseline = build_index(root, output_dir=output)

            def resign(candidate: dict[str, object]) -> None:
                for file in candidate["files"]:  # type: ignore[index]
                    path = file["path"]
                    file["analysis_sha256"] = _file_analysis_digest(
                        path,
                        [item for item in candidate["symbols"] if item["path"] == path],  # type: ignore[index]
                        [item for item in candidate["relationships"] if item["path"] == path],  # type: ignore[index]
                    )
                candidate["stats"]["relationships"] = len(candidate["relationships"])  # type: ignore[index]
                candidate["derived_sha256"] = _derived_artifacts_digest(candidate)  # type: ignore[arg-type]
                candidate["integrity_sha256"] = _integrity_digest(candidate)  # type: ignore[arg-type]

            language_claims = (
                ("main.go", "go-lexer-fallback[package=main]", "payAdmin"),
                ("web.js", "javascript-regex", "payAdmin"),
                ("main.py", "python-ast", "pay_admin"),
            )
            for path, analyzer, target in language_claims:
                for claim_kind in ("relationship", "symbol"):
                    with self.subTest(path=path, claim_kind=claim_kind):
                        candidate = deepcopy(baseline)
                        file = next(
                            item for item in candidate["files"] if item["path"] == path
                        )
                        if claim_kind == "relationship":
                            candidate["relationships"].append(
                                {
                                    "id": stable_id(
                                        "rel", "calls", file["id"], target, path, 1
                                    ),
                                    "source_id": file["id"],
                                    "target_id": None,
                                    "target_name": target,
                                    "kind": "calls",
                                    "path": path,
                                    "line": 1,
                                    "analyzer": analyzer,
                                    "confidence": "heuristic",
                                    "receiver_type_hint": None,
                                }
                            )
                        else:
                            fake_id = stable_id(
                                "symbol", path, "function", target, 1
                            )
                            candidate["symbols"].append(
                                {
                                    "id": fake_id,
                                    "file_id": file["id"],
                                    "path": path,
                                    "name": target,
                                    "qualified_name": target,
                                    "kind": "function",
                                    "line": 1,
                                    "end_line": 1,
                                    "analyzer": analyzer,
                                    "confidence": "exact",
                                    "parent_id": None,
                                    "signature": None,
                                    "exported": True,
                                }
                            )
                            file["symbols"].append(fake_id)
                            candidate["stats"]["symbols"] = len(
                                candidate["symbols"]
                            )
                        resign(candidate)

                        with patch(
                            "repo_teacher.indexer.discover_features", return_value=[]
                        ):
                            validation = validate_index(candidate, root)

                        self.assertFalse(validation["valid"], validation["issues"])
                        self.assertIn(
                            "canonical-source-claims-mismatch",
                            {item["code"] for item in validation["issues"]},
                        )
                        verified = publish_baseline(candidate, output)
                        with patch(
                            "repo_teacher.indexer.discover_features", return_value=[]
                        ):
                            warm = build_index(
                                root,
                                output_dir=output,
                                previous_index=verified,
                            )
                        self.assertEqual(
                            warm["change_classification"]["baseline_status"],
                            "rejected",
                        )
                        if claim_kind == "relationship":
                            self.assertNotIn(
                                target,
                                {
                                    item["target_name"]
                                    for item in warm["relationships"]
                                    if item["kind"] == "calls"
                                },
                            )
                        else:
                            self.assertNotIn(
                                target,
                                {item["qualified_name"] for item in warm["symbols"]},
                            )

    def test_fully_resigned_derived_forgery_is_recomputed_on_disk_warm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def main():\n    return 1\n"
                "if __name__ == '__main__':\n    main()\n",
                encoding="utf-8",
            )
            output = root / ".published"
            baseline = build_index(root, output_dir=output)
            forged = deepcopy(baseline)
            forged["tutorials"][0]["title"] = "Forged privileged workflow"
            forged["derived_sha256"] = _derived_artifacts_digest(forged)
            forged["integrity_sha256"] = _integrity_digest(forged)

            validation = validate_index(forged, root)
            self.assertFalse(validation["valid"], validation["issues"])
            self.assertIn(
                "canonical-source-claims-mismatch",
                {item["code"] for item in validation["issues"]},
            )

            verified = publish_baseline(forged, output)
            warm = build_index(root, output_dir=output, previous_index=verified)

            self.assertNotIn(
                "Forged privileged workflow",
                {item["title"] for item in warm["tutorials"]},
            )
            self.assertFalse(warm["stats"]["reused_derived_artifacts"])
            self.assertTrue(validate_index(warm, root)["valid"])

    def test_build_index_connects_files_symbols_modules_and_reading_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "web").mkdir()
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            (root / "pyproject.toml").write_text(
                "[project]\nname='demo'\n", encoding="utf-8"
            )
            (root / "src" / "app.py").write_text(
                "from service import run\n\ndef main():\n    return run()\n",
                encoding="utf-8",
            )
            (root / "src" / "service.py").write_text(
                "def run():\n    return 1\n", encoding="utf-8"
            )
            (root / "web" / "main.ts").write_text(
                "export function boot() { return 1 }\n", encoding="utf-8"
            )

            index = build_index(root)

            self.assertEqual(index["schema_version"], "2.0")
            self.assertEqual(index["stats"]["files"], 5)
            self.assertEqual(index["stats"]["symbols"], 3)
            self.assertEqual(
                [file["path"] for file in index["files"]],
                sorted(file["path"] for file in index["files"]),
            )
            self.assertEqual(
                {module["name"] for module in index["modules"]}, {"root", "src", "web"}
            )
            self.assertEqual(index["reading_path"][0]["path"], "README.md")
            self.assertEqual(index["reading_path"][1]["path"], "pyproject.toml")
            self.assertEqual(index["stats"]["tutorials"], len(index["features"]))
            self.assertEqual(index["stats"]["codemaps"], len(index["features"]))
            self.assertEqual(len(index["coverage"]), len(index["features"]))

            run_symbol = next(
                symbol for symbol in index["symbols"] if symbol["name"] == "run"
            )
            call = next(
                relationship
                for relationship in index["relationships"]
                if relationship["kind"] == "calls"
            )
            self.assertEqual(call["target_id"], run_symbol["id"])
            self.assertEqual(call["confidence"], "heuristic")

    def test_go_index_records_fingerprint_fallback_and_disabled_semantic_boundary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "go.mod").write_text("module example.test/project\n", encoding="utf-8")
            (root / "main.go").write_text(
                "package main\nfunc helper(){}\nfunc main(){ helper() }\n",
                encoding="utf-8",
            )

            index = build_index(root)

            self.assertEqual(len(index["analysis_fingerprint"]), 64)
            analyzers = {item["id"]: item for item in index["analyzers"]}
            fallback = analyzers["go-lexer-fallback"]
            semantic = analyzers["go-semantic-gopls"]
            self.assertTrue(fallback["enabled"])
            self.assertGreater(fallback["symbols"], 0)
            self.assertGreater(fallback["relationships"], 0)
            self.assertGreater(fallback["resolution"]["calls_resolved"], 0)
            self.assertFalse(semantic["enabled"])
            self.assertFalse(semantic["implicit"])
            self.assertEqual(semantic["relationships"], 0)

    def test_deleted_go_target_is_not_reused_across_incremental_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "go.mod").write_text("module example.test/project\n", encoding="utf-8")
            (root / "main.go").write_text(
                "package p\nfunc main(){ helper() }\n", encoding="utf-8"
            )
            helper = root / "helper.go"
            helper.write_text("package p\nfunc helper(){}\n", encoding="utf-8")
            output = root / ".published"
            baseline = build_index(root, output_dir=output)
            verified = publish_baseline(baseline, output)
            initial_call = next(
                item for item in baseline["relationships"] if item["kind"] == "calls"
            )
            self.assertIsNotNone(initial_call["target_id"])

            helper.unlink()
            rebuilt = build_index(
                root, output_dir=output, previous_index=verified
            )
            rebuilt_call = next(
                item for item in rebuilt["relationships"] if item["kind"] == "calls"
            )
            self.assertIsNone(rebuilt_call["target_id"])
            self.assertIn("helper.go", rebuilt["changes"]["deleted"])

    def test_cross_file_go_receiver_graph_validates_and_reuses_warm_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "go.mod").write_text(
                "module example.test/project\n", encoding="utf-8"
            )
            (root / "type.go").write_text(
                "package p\ntype Store struct{}\n", encoding="utf-8"
            )
            (root / "method.go").write_text(
                "package p\nfunc (store *Store) Save() {}\n", encoding="utf-8"
            )

            output = root / ".published"
            cold = build_index(root, output_dir=output)
            cold_validation = validate_index(cold, root)
            self.assertTrue(cold_validation["valid"], cold_validation["issues"])
            method = next(item for item in cold["symbols"] if item["name"] == "Save")
            receiver = next(
                item
                for item in cold["relationships"]
                if item["kind"] == "receiver-type"
            )
            self.assertIsNone(method["parent_id"])
            self.assertEqual(receiver["source_id"], method["id"])
            self.assertEqual(receiver["path"], method["path"])

            verified = publish_baseline(cold, output)
            warm = build_index(root, output_dir=output, previous_index=verified)
            warm_validation = validate_index(warm, root)
            self.assertTrue(warm_validation["valid"], warm_validation["issues"])
            self.assertEqual(warm["change_classification"]["baseline_status"], "compatible")
            self.assertEqual(warm["stats"]["reused_files"], warm["stats"]["files"])
            warm_receiver = next(
                item
                for item in warm["relationships"]
                if item["kind"] == "receiver-type"
            )
            self.assertIsNotNone(warm_receiver["target_id"])

    def test_redacted_python_signature_still_reuses_verified_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "client.py").write_text(
                "def request(token: str | None = None) -> None:\n"
                "    return None\n",
                encoding="utf-8",
            )
            output = root / ".published"
            cold = build_index(root, output_dir=output)
            signature = next(
                item["signature"]
                for item in cold["symbols"]
                if item["name"] == "request"
            )
            self.assertIn("[REDACTED]", signature)

            verified = publish_baseline(cold, output)
            warm = build_index(root, output_dir=output, previous_index=verified)

            self.assertEqual(
                warm["change_classification"]["baseline_status"], "compatible"
            )
            self.assertEqual(warm["stats"]["reused_files"], warm["stats"]["files"])

    def test_warm_snapshot_does_not_alias_json_roundtrip_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "go.mod").write_text("module example.test/project\n", encoding="utf-8")
            (root / "main.go").write_text(
                "package main\nfunc helper(){}\nfunc main(){ helper() }\n",
                encoding="utf-8",
            )

            output = root / ".published"
            cold = build_index(root, output_dir=output)
            baseline = json.loads(json.dumps(cold))
            cold_digest = cold["integrity_sha256"]
            baseline_digest = baseline["integrity_sha256"]
            verified = publish_baseline(baseline, output)
            warm = build_index(root, output_dir=output, previous_index=verified)

            self.assertTrue(validate_index(cold, root)["valid"])
            self.assertTrue(validate_index(baseline, root)["valid"])
            self.assertTrue(validate_index(warm, root)["valid"])
            self.assertEqual(warm["change_classification"]["baseline_status"], "compatible")
            self.assertEqual(warm["stats"]["reused_files"], warm["stats"]["files"])
            for key in (
                "files",
                "symbols",
                "relationships",
                "modules",
                "reading_path",
                "features",
                "evidence",
                "tutorials",
                "codemaps",
                "coverage",
            ):
                self.assertIsNot(warm[key], baseline[key], key)
                if warm[key] and isinstance(warm[key][0], dict):
                    self.assertIsNot(warm[key][0], baseline[key][0], key)

            warm["files"][0]["path"] = "mutated.go"
            if warm["features"]:
                warm["features"][0]["title"] = "mutated"
            self.assertEqual(cold["integrity_sha256"], cold_digest)
            self.assertEqual(_integrity_digest(cold), cold_digest)
            self.assertEqual(baseline["integrity_sha256"], baseline_digest)
            self.assertEqual(_integrity_digest(baseline), baseline_digest)

    def test_non_git_copy_never_inherits_source_audited_capabilities(self) -> None:
        reference = Path(
            "/Volumes/T7/workspace/ontology/graph/repo/understand-anything"
        )
        if not reference.is_dir():
            self.skipTest("reference clone is not available")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = (
                "understand-anything-plugin/src/context-builder.ts",
                "understand-anything-plugin/src/onboard-builder.ts",
                "understand-anything-plugin/src/explain-builder.ts",
            )
            for relative in paths:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(reference / relative, destination)

            copied = build_index(root)

            self.assertFalse(copied["project"]["is_git"])
            self.assertNotIn(
                "source-audited",
                {item["confidence"] for item in copied["features"]},
            )

    def test_real_reference_git_snapshot_emits_source_audited_capabilities(self) -> None:
        reference = Path(
            "/Volumes/T7/workspace/ontology/graph/repo/understand-anything"
        )
        if not (reference / ".git").exists():
            self.skipTest("reference Git clone is not available")

        index = build_index(reference)

        audited = [
            item
            for item in index["features"]
            if item["confidence"] == "source-audited"
        ]
        self.assertGreaterEqual(len(audited), 3)
        self.assertTrue(
            all(
                item["source"].startswith("source-audited-reference-manifest:")
                for item in audited
            )
        )

    def test_sourcebridge_go_resolution_golden_has_no_unsafe_targets(self) -> None:
        root = Path("/Volumes/T7/workspace/ontology/graph/repo/sourcebridge")
        if not (root / ".git").exists():
            self.skipTest("SourceBridge reference Git clone is not available")

        index = build_index(root)
        symbols = {item["id"]: item for item in index["symbols"]}
        go_symbols = [
            item
            for item in index["symbols"]
            if item["analyzer"].startswith("go-")
        ]
        go_relationships = [
            item
            for item in index["relationships"]
            if item["analyzer"].startswith("go-")
        ]
        resolved_calls = [
            item
            for item in go_relationships
            if item["kind"] == "calls" and item["target_id"]
        ]
        aliases: dict[str, dict[str, str]] = {}
        for relationship in go_relationships:
            if relationship["kind"] != "go-import-alias" or "=" not in relationship["target_name"]:
                continue
            alias, module = relationship["target_name"].split("=", 1)
            aliases.setdefault(relationship["path"], {})[alias] = module

        unsafe_shape_targets = []
        external_selector_targets = []
        module = "github.com/sourcebridge/sourcebridge"
        for relationship in resolved_calls:
            target = symbols[relationship["target_id"]]
            parts = relationship["target_name"].split(".")
            package_selector = (
                len(parts) == 2
                and parts[0] in aliases.get(relationship["path"], {})
            )
            if target["kind"] in {"method", "interface-method"} and (
                len(parts) == 1 or package_selector
            ):
                unsafe_shape_targets.append(relationship)
            if package_selector:
                imported = aliases[relationship["path"]][parts[0]]
                if imported != module and not imported.startswith(f"{module}/"):
                    external_selector_targets.append(relationship)

        resolved_imports = [
            item
            for item in go_relationships
            if item["kind"] == "import" and item["target_id"]
        ]
        external_import_targets = [
            item
            for item in resolved_imports
            if item["target_name"] != module
            and not item["target_name"].startswith(f"{module}/")
        ]

        self.assertEqual(index["project"]["commit"], "2a128bf0c8461fae91d2b424d9168ddf205bb11b")
        self.assertEqual(len(go_symbols), 10_922)
        self.assertGreaterEqual(len(go_relationships), 69_231)
        self.assertEqual(unsafe_shape_targets, [])
        self.assertEqual(external_selector_targets, [])
        self.assertEqual(external_import_targets, [])
        self.assertTrue(
            all(
                symbols[item["target_id"]]["analyzer"].startswith("go-")
                for item in resolved_calls
            )
        )
        self.assertTrue(
            all(
                symbols[item["target_id"]]["kind"] in {"function", "method"}
                for item in resolved_calls
            )
        )
        relationship_ids = [item["id"] for item in index["relationships"]]
        self.assertEqual(len(relationship_ids), len(set(relationship_ids)))
        self.assertEqual(len(index["analysis_fingerprint"]), 64)

    def test_build_index_excludes_its_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / ".repo-teacher-output"
            output.mkdir()
            (root / "main.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            (output / "old.py").write_text(
                "def stale():\n    return 0\n", encoding="utf-8"
            )

            index = build_index(root, output_dir=output)

            self.assertEqual([file["path"] for file in index["files"]], ["main.py"])

    def test_build_index_reuses_unchanged_files_and_reports_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "stable.py").write_text(
                "def stable():\n    return 1\n", encoding="utf-8"
            )
            (root / "changed.py").write_text(
                "def before():\n    return 1\n", encoding="utf-8"
            )
            output = root / ".published"
            first = build_index(root, output_dir=output)
            verified = publish_baseline(first, output)

            (root / "changed.py").write_text(
                "def after():\n    return 2\n", encoding="utf-8"
            )
            (root / "added.py").write_text("VALUE = 3\n", encoding="utf-8")
            second = build_index(root, output_dir=output, previous_index=verified)

            self.assertEqual(second["changes"]["unchanged"], ["stable.py"])
            self.assertEqual(second["changes"]["changed"], ["changed.py"])
            self.assertEqual(second["changes"]["added"], ["added.py"])
            self.assertEqual(second["stats"]["reused_files"], 1)
            self.assertEqual(second["stats"]["reanalyzed_files"], 2)
            self.assertIn("after", {item["name"] for item in second["symbols"]})

    def test_tampered_or_incompatible_baseline_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            first = build_index(root)
            first["symbols"][0]["name"] = "STALE"

            second = build_index(root, previous_index=first)

            self.assertNotIn("STALE", {item["name"] for item in second["symbols"]})
            self.assertEqual(second["stats"]["reused_files"], 0)
            self.assertEqual(
                second["change_classification"]["baseline_status"], "rejected"
            )
            self.assertIn(
                "baseline-rejected", {item["code"] for item in second["diagnostics"]}
            )

    def test_malformed_but_rehashed_baseline_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            output = root / ".published"
            first = build_index(root, output_dir=output)
            del first["symbols"][0]["qualified_name"]
            first["integrity_sha256"] = _integrity_digest(first)
            verified = publish_baseline(first, output)

            second = build_index(root, output_dir=output, previous_index=verified)

            self.assertEqual(second["stats"]["reused_files"], 0)
            rejection = next(
                item
                for item in second["diagnostics"]
                if item["code"] == "baseline-rejected"
            )
            self.assertIn("incompatible symbols record", rejection["message"])

    def test_project_schema_and_scan_configuration_mismatches_reject_reuse(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as first_directory,
            tempfile.TemporaryDirectory() as second_directory,
        ):
            first_root = Path(first_directory)
            second_root = Path(second_directory)
            (first_root / "main.py").write_text("def main(): pass\n", encoding="utf-8")
            (second_root / "main.py").write_text("def main(): pass\n", encoding="utf-8")
            baseline = build_index(first_root, max_files=10)

            wrong_project = build_index(
                second_root, previous_index=baseline, max_files=10
            )
            wrong_config = build_index(
                first_root, previous_index=baseline, max_files=11
            )
            baseline["schema_version"] = "0"
            baseline["integrity_sha256"] = _integrity_digest(baseline)
            wrong_schema = build_index(
                first_root, previous_index=baseline, max_files=10
            )

            for result in (wrong_project, wrong_config, wrong_schema):
                self.assertEqual(result["stats"]["reused_files"], 0)
                self.assertEqual(
                    result["change_classification"]["baseline_status"], "rejected"
                )

    def test_unsupported_semantic_analyzer_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")

            index = build_index(root)

            diagnostic = next(
                item
                for item in index["diagnostics"]
                if item["code"] == "unsupported-analyzer"
            )
            self.assertEqual(diagnostic["path"], "README.md")
            self.assertIn("Markdown", diagnostic["message"])

    def test_relationship_ids_are_unique_and_identical_occurrences_are_deduplicated(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def target():\n    return 1\n\ndef main():\n    return target() + target()\n",
                encoding="utf-8",
            )

            index = build_index(root)

            relationship_ids = [item["id"] for item in index["relationships"]]
            self.assertEqual(len(relationship_ids), len(set(relationship_ids)))
            calls = [item for item in index["relationships"] if item["kind"] == "calls"]
            self.assertEqual(len(calls), 1)
            self.assertIn(
                "duplicate-relationships-normalized",
                {item["code"] for item in index["diagnostics"]},
            )

    def test_python_import_aliases_on_one_line_have_stable_distinct_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "stt.py").write_text(
                "class WizperSTT:\n    pass\n",
                encoding="utf-8",
            )
            (root / "__init__.py").write_text(
                "from .stt import WizperSTT, WizperSTT as STT\n",
                encoding="utf-8",
            )

            index = build_index(root)

            imports = [
                item
                for item in index["relationships"]
                if item["kind"] == "import" and item["path"] == "__init__.py"
            ]
            self.assertEqual(len(imports), 2)
            self.assertEqual(len({item["id"] for item in imports}), 2)
            self.assertEqual(
                {item["receiver_type_hint"] for item in imports},
                {"binding:WizperSTT", "binding:STT"},
            )
            self.assertTrue(validate_index(index, root)["valid"])

    def test_change_classification_is_conservative_and_signature_aware(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.py"
            source.write_text("def main():\n    return 1\n", encoding="utf-8")
            output = root / ".published"
            baseline = build_index(root, output_dir=output)
            verified = publish_baseline(baseline, output)

            source.write_text("def main():\n    return 2\n", encoding="utf-8")
            internal = build_index(
                root, output_dir=output, previous_index=verified
            )
            self.assertEqual(
                internal["change_classification"]["action"], "SKIP_GRAPH_UPDATE"
            )
            self.assertEqual(
                internal["change_classification"]["implementation_only"], ["main.py"]
            )

            source.write_text("def main(value):\n    return value\n", encoding="utf-8")
            verified = publish_baseline(internal, output)
            structural = build_index(
                root, output_dir=output, previous_index=verified
            )
            self.assertEqual(
                structural["change_classification"]["action"], "FULL_REINDEX"
            )
            self.assertEqual(
                structural["change_classification"]["structural"], ["main.py"]
            )

            (root / "docs.md").write_text("initial\n", encoding="utf-8")
            verified = publish_baseline(structural, output)
            with_docs = build_index(
                root, output_dir=output, previous_index=verified
            )
            (root / "docs.md").write_text("changed\n", encoding="utf-8")
            verified = publish_baseline(with_docs, output)
            unsupported_change = build_index(
                root, output_dir=output, previous_index=verified
            )
            self.assertIn(
                "docs.md", unsupported_change["change_classification"]["structural"]
            )

    def test_non_git_source_change_between_scans_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main(): pass\n", encoding="utf-8")
            calls = 0

            def scan_with_late_file(path: Path, options: object) -> object:
                nonlocal calls
                calls += 1
                if calls == 2:
                    (root / "late.py").write_text("VALUE = 1\n", encoding="utf-8")
                return real_scan_repository(path, options)

            with patch(
                "repo_teacher.indexer.scan_repository", side_effect=scan_with_late_file
            ):
                with self.assertRaisesRegex(
                    ValueError, "changed while it was being indexed"
                ):
                    build_index(root)

    def test_output_cannot_be_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main(): pass\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "repository root"):
                build_index(root, output_dir=root)

    def test_output_ancestor_is_rejected_but_descendant_and_sibling_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "source"
            root.mkdir()
            (root / "main.py").write_text("def main(): pass\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "ancestors"):
                build_index(root, output_dir=parent)
            descendant = build_index(root, output_dir=root / ".generated")
            sibling = build_index(root, output_dir=parent / "report")

            self.assertEqual(descendant["stats"]["files"], 1)
            self.assertEqual(sibling["stats"]["files"], 1)

    def test_rehashed_semantic_poison_is_rejected_by_source_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            output = root / ".published"
            baseline = build_index(root, output_dir=output)
            file = baseline["files"][0]
            fake_id = stable_id("symbol", "main.py", "function", "pay_admin", 1)
            baseline["symbols"].append(
                {
                    "id": fake_id,
                    "file_id": file["id"],
                    "path": "main.py",
                    "name": "pay_admin",
                    "qualified_name": "pay_admin",
                    "kind": "function",
                    "line": 1,
                    "end_line": 2,
                    "analyzer": "python-ast",
                    "confidence": "exact",
                    "parent_id": None,
                    "signature": "",
                    "exported": True,
                }
            )
            file["symbols"].append(fake_id)
            baseline["integrity_sha256"] = _integrity_digest(baseline)
            verified = publish_baseline(baseline, output)

            rebuilt = build_index(root, output_dir=output, previous_index=verified)

            self.assertEqual(rebuilt["stats"]["reused_files"], 0)
            self.assertNotIn(fake_id, {item["id"] for item in rebuilt["symbols"]})
            rejection = next(
                item for item in rebuilt["diagnostics"] if item["code"] == "baseline-rejected"
            )
            self.assertIn("not grounded", rejection["message"])

    def test_rehashed_kind_edge_and_derived_poison_never_enter_warm_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def main():\n    return 1\nif __name__ == '__main__':\n    main()\n",
                encoding="utf-8",
            )
            baseline = build_index(root)

            wrong_kind = deepcopy(baseline)
            symbol = wrong_kind["symbols"][0]
            old_id = symbol["id"]
            symbol["kind"] = "class"
            symbol["id"] = stable_id(
                "symbol", "main.py", "class", symbol["qualified_name"], symbol["line"]
            )
            wrong_kind["files"][0]["symbols"] = [
                symbol["id"]
                if value == old_id
                else value
                for value in wrong_kind["files"][0]["symbols"]
            ]
            for relationship in wrong_kind["relationships"]:
                if relationship["source_id"] == old_id:
                    relationship["source_id"] = symbol["id"]
                if relationship.get("target_id") == old_id:
                    relationship["target_id"] = symbol["id"]
            wrong_kind["integrity_sha256"] = _integrity_digest(wrong_kind)

            fake_edge = deepcopy(baseline)
            file = fake_edge["files"][0]
            fake_edge["relationships"].append(
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
            fake_edge["integrity_sha256"] = _integrity_digest(fake_edge)

            fake_tutorial = deepcopy(baseline)
            fake_tutorial["tutorials"].append({"id": "tutorial_fake"})
            fake_tutorial["integrity_sha256"] = _integrity_digest(fake_tutorial)

            for poisoned in (wrong_kind, fake_edge, fake_tutorial):
                with self.subTest(records=len(poisoned["relationships"])):
                    rebuilt = build_index(root, previous_index=poisoned)
                    self.assertEqual(
                        rebuilt["change_classification"]["baseline_status"],
                        "rejected",
                    )
                    self.assertEqual(rebuilt["stats"]["reused_files"], 0)
                    self.assertFalse(rebuilt["stats"]["reused_derived_artifacts"])

    def test_index_and_derived_artifacts_never_persist_common_secret_families(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secrets = (
                "sk-ant-api03-" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN1234",
                "glpat-" + "abcdefghijklmnopqrst",
                "xoxb-" + "123456789012-abcdefghijklmnop",
                "generic-super-secret-token-value",
            )
            (root / "main.py").write_text(
                "def main():\n    return 1\n"
                "if __name__ == '__main__':\n"
                "    ANTHROPIC_API_KEY='" + secrets[0] + "'\n"
                "    AWS_SECRET_ACCESS_KEY='" + secrets[1] + "'\n"
                "    GITLAB_TOKEN='" + secrets[2] + "'\n"
                "    SLACK_BOT_TOKEN='" + secrets[3] + "'\n"
                "    TOKEN='" + secrets[4] + "'\n"
                "    main()\n",
                encoding="utf-8",
            )

            index = build_index(root)
            serialized = json.dumps(index, ensure_ascii=False)

            for secret in secrets:
                self.assertNotIn(secret, serialized)
            self.assertIn("[REDACTED]", serialized)
            self.assertTrue(validate_index(index, root)["valid"])

    def test_warm_baseline_semantic_closure_groups_records_by_path(self) -> None:
        import repo_teacher.indexer as indexer_module

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in range(24):
                (root / f"file_{number}.py").write_text(
                    f"def function_{number}():\n    return {number}\n",
                    encoding="utf-8",
                )
            output = root / ".published"
            baseline = build_index(root, output_dir=output)
            verified = publish_baseline(baseline, output)
            real_digest = indexer_module._file_analysis_digest
            observed_sizes: list[tuple[int, int]] = []

            def observed_digest(
                path: str, symbols: list[object], relationships: list[object]
            ) -> str:
                observed_sizes.append((len(symbols), len(relationships)))
                return real_digest(path, symbols, relationships)

            with patch.object(
                indexer_module, "_file_analysis_digest", new=observed_digest
            ):
                warm = build_index(
                    root, output_dir=output, previous_index=verified
                )

            self.assertEqual(warm["stats"]["reused_files"], 24)
            self.assertEqual(len(observed_sizes), 48)
            self.assertTrue(all(size == (1, 1) for size in observed_sizes))

    def test_python_structural_fingerprint_covers_public_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.py"
            source.write_text(
                "from pkg import value as first\n"
                "class Base: pass\n"
                "class Service(Base):\n"
                "    item: int = 1\n"
                "def load() -> int:\n"
                "    return 1\n",
                encoding="utf-8",
            )
            output = root / ".published"
            baseline = build_index(root, output_dir=output)
            verified = publish_baseline(baseline, output)
            source.write_text(
                "from pkg import other as first\n"
                "class Base: pass\n"
                "class Other: pass\n"
                "class Service(Other):\n"
                "    item: str = '1'\n"
                "def load() -> str:\n"
                "    return '1'\n",
                encoding="utf-8",
            )

            changed = build_index(
                root, output_dir=output, previous_index=verified
            )

            self.assertTrue(changed["files"][0]["has_structural_analysis"])
            self.assertIn("main.py", changed["change_classification"]["structural"])
            self.assertNotIn(
                "main.py", changed["change_classification"]["implementation_only"]
            )

    def test_late_change_after_verification_scan_is_detected_by_tree_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main(): pass\n", encoding="utf-8")
            calls = 0
            from repo_teacher.snapshot import capture_snapshot as real_snapshot

            def snapshot_with_late_file(path: Path) -> object:
                nonlocal calls
                calls += 1
                if calls == 2:
                    (root / "late.txt").write_text("late\n", encoding="utf-8")
                return real_snapshot(path)

            with patch("repo_teacher.indexer.capture_snapshot", side_effect=snapshot_with_late_file):
                with self.assertRaisesRegex(ValueError, "changed while it was being indexed"):
                    build_index(root)

    def test_non_git_change_after_final_snapshot_is_detected_before_return(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main(): pass\n", encoding="utf-8")
            calls = 0
            from repo_teacher.snapshot import capture_snapshot as real_snapshot

            def snapshot_then_late_file(path: Path) -> object:
                nonlocal calls
                calls += 1
                snapshot = real_snapshot(path)
                if calls == 3:
                    (root / "late.py").write_text("VALUE = 1\n", encoding="utf-8")
                return snapshot

            with patch(
                "repo_teacher.indexer.capture_snapshot",
                side_effect=snapshot_then_late_file,
            ):
                with self.assertRaisesRegex(
                    ValueError, "changed while it was being indexed"
                ):
                    build_index(root)

    def test_partial_scan_is_marked_unvalidated_and_cannot_be_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def main(): pass\nif __name__ == '__main__':\n    main()\n",
                encoding="utf-8",
            )
            (root / "other.py").write_text("VALUE = 1\n", encoding="utf-8")
            partial = build_index(root, max_files=1)

            self.assertFalse(partial["stats"]["scan_complete"])
            self.assertEqual(partial["freshness"], "partial-unvalidated")
            self.assertTrue(
                all(item["confidence"] == "partial-unvalidated" for item in partial["features"])
            )
            rebuilt = build_index(root, previous_index=partial)
            self.assertEqual(rebuilt["change_classification"]["baseline_status"], "rejected")

    def test_capability_catalog_participates_in_analysis_fingerprint(self) -> None:
        baseline = _analysis_fingerprint(100, 10, 1_000)
        original_read = Path.read_bytes

        def changed_catalog(path: Path) -> bytes:
            data = original_read(path)
            return data + b"\nchanged" if path.name == "capability_catalog.py" else data

        with patch.object(Path, "read_bytes", changed_catalog):
            changed = _analysis_fingerprint(100, 10, 1_000)

        self.assertNotEqual(baseline, changed)

    def test_go_relationship_resolution_is_not_overwritten_by_global_name_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a").mkdir()
            (root / "b").mkdir()
            (root / "go.mod").write_text("module example\n", encoding="utf-8")
            (root / "a" / "a.go").write_text("package a\nfunc Run() {}\n", encoding="utf-8")
            (root / "b" / "b.go").write_text("package b\nfunc Run() {}\n", encoding="utf-8")
            (root / "main.go").write_text(
                'package main\nimport "example/a"\nfunc main() { a.Run() }\n',
                encoding="utf-8",
            )

            index = build_index(root)

            call = next(
                item
                for item in index["relationships"]
                if item["kind"] == "calls" and item["path"] == "main.go"
            )
            target = next(item for item in index["symbols"] if item["id"] == call["target_id"])
            self.assertEqual(target["path"], "a/a.go")

    def test_typescript_js_import_specifier_resolves_to_repository_ts_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "cli").mkdir(parents=True)
            (root / "src" / "visualize").mkdir(parents=True)
            (root / "src" / "cli" / "runners.ts").write_text(
                'import { start } from "../visualize/server.js";\nexport function run() { start(); }\n',
                encoding="utf-8",
            )
            (root / "src" / "visualize" / "server.ts").write_text(
                "export function start() {}\n", encoding="utf-8"
            )

            index = build_index(root)

            edge = next(
                item
                for item in index["relationships"]
                if item["kind"] == "import" and item["path"] == "src/cli/runners.ts"
            )
            target = next(item for item in index["files"] if item["id"] == edge["target_id"])
            self.assertEqual(target["path"], "src/visualize/server.ts")

    def test_typescript_asset_import_does_not_resolve_to_same_stem_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "acp").mkdir(parents=True)
            (root / "src" / "acp" / "main.ts").write_text(
                'import "./theme.css";\nexport function run() {}\n',
                encoding="utf-8",
            )
            (root / "src" / "acp" / "theme.css").write_text(
                ":root { color: red; }\n", encoding="utf-8"
            )
            (root / "src" / "acp" / "theme.ts").write_text(
                "export const unrelated = true;\n", encoding="utf-8"
            )

            index = build_index(root)

            edge = next(
                item
                for item in index["relationships"]
                if item["kind"] == "import" and item["path"] == "src/acp/main.ts"
            )
            self.assertEqual(edge["target_name"], "./theme.css")
            self.assertIsNone(edge["target_id"])
            module = locate_modules(index, "acp")["modules"][0]
            self.assertEqual(module["implementation_trace"], [])
            self.assertFalse(
                any(
                    {"src/acp/main.ts", "src/acp/theme.ts"}.issubset(
                        component["file_paths"]
                    )
                    for component in module["component_boundaries"]
                )
            )


if __name__ == "__main__":
    unittest.main()
