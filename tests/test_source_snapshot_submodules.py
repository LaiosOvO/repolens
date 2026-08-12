from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from repo_teacher.pipeline.source_snapshot import consistent_repository_snapshot


class SourceSnapshotSubmoduleTest(unittest.TestCase):
    def test_initialized_submodule_contents_are_part_of_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child"
            parent = root / "parent"
            child.mkdir()
            parent.mkdir()
            for repository in (child, parent):
                subprocess.run(["git", "init", "-q", str(repository)], check=True)
                subprocess.run(
                    ["git", "-C", str(repository), "config", "user.email", "test@example.com"],
                    check=True,
                )
                subprocess.run(
                    ["git", "-C", str(repository), "config", "user.name", "Test"],
                    check=True,
                )
            (child / "runtime.py").write_text("def run():\n    return 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(child), "add", "."], check=True)
            subprocess.run(["git", "-C", str(child), "commit", "-qm", "child"], check=True)
            subprocess.run(
                [
                    "git", "-c", "protocol.file.allow=always", "-C", str(parent),
                    "submodule", "add", "-q", str(child), "vendor/runtime",
                ],
                check=True,
            )
            subprocess.run(["git", "-C", str(parent), "commit", "-qam", "parent"], check=True)

            with consistent_repository_snapshot(parent) as snapshot:
                copied = snapshot.path / "vendor" / "runtime" / "runtime.py"
                self.assertEqual(copied.read_text(encoding="utf-8"), "def run():\n    return 1\n")


if __name__ == "__main__":
    unittest.main()
