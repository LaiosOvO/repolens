from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from repo_teacher.pipeline.synthesis import _materialize_source_slice


class SourceSliceTest(unittest.TestCase):
    def test_materialized_slice_is_bound_to_indexed_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            workspace = root / "workspace"
            path = source / "src" / "worker.py"
            path.parent.mkdir(parents=True)
            path.write_text("def claim():\n    return 'task'\n", encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()

            slice_root = _materialize_source_slice(
                source,
                workspace,
                ["src/worker.py"],
                {"src/worker.py": digest},
            )

            self.assertEqual((slice_root / "src" / "worker.py").read_bytes(), path.read_bytes())

    def test_source_change_before_copy_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            path = source / "app.py"
            source.mkdir()
            path.write_text("before\n", encoding="utf-8")
            indexed = hashlib.sha256(path.read_bytes()).hexdigest()
            path.write_text("after\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "source changed"):
                _materialize_source_slice(
                    source,
                    root / "workspace",
                    ["app.py"],
                    {"app.py": indexed},
                )

    def test_symlink_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            target = root / "outside.py"
            target.write_text("secret\n", encoding="utf-8")
            (source / "linked.py").symlink_to(target)

            with self.assertRaises(ValueError):
                _materialize_source_slice(
                    source,
                    root / "workspace",
                    ["linked.py"],
                )

    def test_reused_workspace_never_exposes_files_from_an_older_packet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            first = source / "first.py"
            second = source / "second.py"
            first.write_text("FIRST = 1\n", encoding="utf-8")
            second.write_text("SECOND = 2\n", encoding="utf-8")
            hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (first, second)
            }

            first_slice = _materialize_source_slice(
                source, root / "workspace", ["first.py"], hashes
            )
            second_slice = _materialize_source_slice(
                source, root / "workspace", ["second.py"], hashes
            )

            self.assertNotEqual(first_slice, second_slice)
            self.assertTrue((first_slice / "first.py").is_file())
            self.assertFalse((first_slice / "second.py").exists())
            self.assertTrue((second_slice / "second.py").is_file())
            self.assertFalse((second_slice / "first.py").exists())


if __name__ == "__main__":
    unittest.main()
