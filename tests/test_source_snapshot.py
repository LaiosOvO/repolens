from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from repo_teacher.pipeline import consistent_repository_snapshot


class RepositorySnapshotTest(unittest.TestCase):
    def test_git_snapshot_keeps_identity_and_current_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "repo"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            (source / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
            (source / "app.py").write_text("print('before')\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(source), "add", ".gitignore", "app.py"],
                check=True,
            )
            (source / "new.py").write_text("untracked\n", encoding="utf-8")
            ignored = source / "node_modules" / "dependency.js"
            ignored.parent.mkdir()
            ignored.write_text("ignored\n", encoding="utf-8")

            with consistent_repository_snapshot(source) as snapshot:
                (source / "app.py").write_text("print('after')\n", encoding="utf-8")
                self.assertEqual(
                    (snapshot.path / "app.py").read_text(encoding="utf-8"),
                    "print('before')\n",
                )
                self.assertTrue((snapshot.path / ".git").is_dir())
                self.assertTrue((snapshot.path / "new.py").is_file())
                self.assertFalse((snapshot.path / "node_modules").exists())

    def test_snapshot_excludes_a_requested_output_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = source / "generated-report"
            source.mkdir()
            output.mkdir()
            (source / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (output / "index.html").write_text("old report", encoding="utf-8")

            with consistent_repository_snapshot(
                source, excluded_paths=(output,)
            ) as snapshot:
                self.assertTrue((snapshot.path / "app.py").is_file())
                self.assertFalse((snapshot.path / "generated-report").exists())


if __name__ == "__main__":
    unittest.main()
