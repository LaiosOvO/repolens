from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_teacher.reference_catalog import (
    AUDITED_CLAIMS,
    CATALOG_REVISION,
    COMPARISON_CLASSES,
    REFERENCE_CATALOG,
    REFERENCE_IDENTITIES,
    SCORE_DIMENSIONS,
    SCORE_RUBRIC_LEVELS,
    curated_implementation,
    identify_reference_project,
    reference_identity_status,
    validate_reference_catalog,
)


CAPABILITIES = {
    "code-parsing",
    "code-graph",
    "component-discovery",
    "tutorial-generation",
    "evidence-grounding",
    "incremental-update",
    "codemap-visualization",
    "agent-workflow",
}


def audited_fixture(project_key: str, root: Path) -> tuple[dict, str]:
    identity = REFERENCE_IDENTITIES[project_key]
    paths = sorted({path for entry in REFERENCE_CATALOG[project_key].values() for path in entry["source_paths"]})
    files = []
    for position, path in enumerate(paths):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = f"fixture:{path}".encode()
        target.write_bytes(payload)
        files.append(
            {"id": f"file-{position}", "path": path, "sha256": hashlib.sha256(payload).hexdigest(), "lines": 1}
        )
    material = "\n".join(f"{item['path']}\0{item['sha256']}" for item in files)
    bundle = hashlib.sha256(material.encode()).hexdigest()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Repo Teacher Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "repo-teacher@example.invalid"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", f"https://{identity['remote']}.git"], check=True
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return {
        "project": {
            "name": "any display name",
            "path": str(root),
            "remote": f"https://{identity['remote']}.git",
            "commit": head,
        },
        "files": files,
    }, bundle


class ReferenceCatalogTest(unittest.TestCase):
    def test_catalog_covers_six_projects_and_all_48_reviewed_capabilities(self) -> None:
        self.assertEqual(len(REFERENCE_CATALOG), 6)
        self.assertEqual(sum(len(items) for items in REFERENCE_CATALOG.values()), 48)
        self.assertEqual(validate_reference_catalog(), [])
        self.assertRegex(CATALOG_REVISION, r"^\d{4}-\d{2}-\d{2}\.")
        for project, capabilities in REFERENCE_CATALOG.items():
            self.assertEqual(set(capabilities), CAPABILITIES)
            self.assertEqual(set(COMPARISON_CLASSES), CAPABILITIES)
            for slug, entry in capabilities.items():
                self.assertEqual(set(entry["dimension_scores"]), set(SCORE_DIMENSIONS))
                self.assertTrue(set(entry["dimension_scores"].values()) <= set(SCORE_RUBRIC_LEVELS))
                self.assertEqual(entry["source"], "curated-source-audit")
                self.assertIn(project, COMPARISON_CLASSES[slug])

    def test_identity_requires_canonical_remote_commit_and_complete_source_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            index, bundle = audited_fixture("sourcebridge", Path(directory))
            identity = {
                **REFERENCE_IDENTITIES["sourcebridge"],
                "commit": index["project"]["commit"],
                "source_bundle_sha256": bundle,
            }
            with patch.dict(REFERENCE_IDENTITIES, {"sourcebridge": identity}):
                index["project"]["remote"] = "https://spoofed.invalid/not-sourcebridge.git"
                index["project"]["commit"] = "0" * 40
                self.assertEqual(identify_reference_project(index), "sourcebridge")
                entry = curated_implementation(index, "code-parsing")
                self.assertIsNotNone(entry)
                assert entry is not None
                self.assertEqual(entry["source_paths"], REFERENCE_CATALOG["sourcebridge"]["code-parsing"]["source_paths"])
                self.assertEqual(entry["comparison_class"], "deterministic-syntax-index")

    def test_same_name_or_path_cannot_impersonate_a_curated_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            index, _ = audited_fixture("sourcebridge", Path(directory))
            index["project"].update({"name": "SourceBridge", "remote": "https://example.com/fake/sourcebridge.git"})
            subprocess.run(
                ["git", "-C", directory, "remote", "set-url", "origin", "https://example.com/fake/sourcebridge.git"],
                check=True,
            )

            self.assertIsNone(identify_reference_project(index))
            self.assertIsNone(curated_implementation(index, "code-parsing"))
            self.assertEqual(reference_identity_status(index)["status"], "unverified")

            subprocess.run(
                [
                    "git",
                    "-C",
                    directory,
                    "remote",
                    "set-url",
                    "origin",
                    "https://attacker@github.com/sourcebridge-ai/sourcebridge.git?mirror=1",
                ],
                check=True,
            )
            self.assertIsNone(identify_reference_project(index))

    def test_plain_directory_cannot_impersonate_git_even_with_matching_metadata_and_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index, bundle = audited_fixture("sourcebridge", root)
            identity = {
                **REFERENCE_IDENTITIES["sourcebridge"],
                "commit": index["project"]["commit"],
                "source_bundle_sha256": bundle,
            }
            (root / ".git").rename(root / "copied-git-metadata")
            with patch.dict(REFERENCE_IDENTITIES, {"sourcebridge": identity}):
                status = reference_identity_status(index)
            self.assertEqual(status["status"], "unverified")
            self.assertIn("Git worktree", str(status["reason"]))
            self.assertIsNone(curated_implementation(index, "code-parsing"))
            self.assertEqual(reference_identity_status(index)["status"], "unverified")

    def test_wrong_commit_missing_path_and_tampered_hash_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            index, bundle = audited_fixture("sourcebridge", Path(directory))
            identity = {
                **REFERENCE_IDENTITIES["sourcebridge"],
                "commit": index["project"]["commit"],
                "source_bundle_sha256": bundle,
            }
            with patch.dict(REFERENCE_IDENTITIES, {"sourcebridge": identity}):
                subprocess.run(["git", "-C", directory, "commit", "--allow-empty", "-qm", "new head"], check=True)
                self.assertEqual(reference_identity_status(index)["status"], "stale")
                subprocess.run(["git", "-C", directory, "reset", "--hard", "HEAD^", "-q"], check=True)
                index["files"].pop()
                self.assertIsNone(identify_reference_project(index))

        with tempfile.TemporaryDirectory() as directory:
            index, bundle = audited_fixture("sourcebridge", Path(directory))
            identity = {
                **REFERENCE_IDENTITIES["sourcebridge"],
                "commit": index["project"]["commit"],
                "source_bundle_sha256": bundle,
            }
            with patch.dict(REFERENCE_IDENTITIES, {"sourcebridge": identity}):
                index["files"][0]["sha256"] = "f" * 64
                self.assertIsNone(curated_implementation(index, "code-parsing"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index, bundle = audited_fixture("sourcebridge", root)
            identity = {
                **REFERENCE_IDENTITIES["sourcebridge"],
                "commit": index["project"]["commit"],
                "source_bundle_sha256": bundle,
            }
            first_path = Path(index["files"][0]["path"])
            (root / first_path).write_text("modified after indexing", encoding="utf-8")
            with patch.dict(REFERENCE_IDENTITIES, {"sourcebridge": identity}):
                self.assertIsNone(identify_reference_project(index))

    def test_deepwiki_facts_describe_sections_steps_and_real_line_citations(self) -> None:
        graph = REFERENCE_CATALOG["deepwiki-open"]["code-graph"]
        evidence = REFERENCE_CATALOG["deepwiki-open"]["evidence-grounding"]
        codemap = REFERENCE_CATALOG["deepwiki-open"]["codemap-visualization"]

        self.assertIn("sections", graph["summary"])
        self.assertIn("没有源码调用图", graph["summary"])
        self.assertIn("本地源码", evidence["approach"])
        self.assertIn("citation", evidence["summary"].lower())
        self.assertIn("sections", codemap["summary"])
        self.assertIn("CodeViewer", codemap["data_flow"][-1])
        self.assertNotIn("node selection", " ".join(codemap["data_flow"]).lower())
        ranges = {
            (claim["line_start"], claim["line_end"])
            for claim in AUDITED_CLAIMS[("deepwiki-open", "evidence-grounding")]
            if claim["path"] == "api/services/codemap.py"
        }
        self.assertEqual(ranges, {(128, 148), (178, 222), (305, 309)})

    def test_known_sourcebridge_and_openwiki_boundaries_are_explicit(self) -> None:
        sourcebridge_graph = REFERENCE_CATALOG["sourcebridge"]["code-graph"]
        sourcebridge_tutorial = REFERENCE_CATALOG["sourcebridge"]["tutorial-generation"]
        openwiki_components = REFERENCE_CATALOG["openwiki"]["component-discovery"]

        self.assertIn("internal/db/store_federation.go", sourcebridge_graph["source_paths"])
        self.assertTrue(any("in-memory" in item for item in sourcebridge_graph["limitations"]))
        self.assertIn("workers/knowledge/workflow_story.py", sourcebridge_tutorial["source_paths"])
        self.assertIn("prompt", openwiki_components["approach"])
        self.assertTrue(any("prompt-enforced" in item for item in openwiki_components["limitations"]))

    def test_all_48_entries_point_to_files_in_the_fixed_local_snapshots_when_available(self) -> None:
        root = Path("/Volumes/T7/workspace/ontology/graph/repo")
        if not all((root / project).is_dir() for project in REFERENCE_CATALOG):
            self.skipTest("the six audited reference clones are not installed")
        missing = [
            f"{project}:{slug}:{path}"
            for project, capabilities in REFERENCE_CATALOG.items()
            for slug, entry in capabilities.items()
            for path in entry["source_paths"]
            if not (root / project / path).is_file()
        ]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
