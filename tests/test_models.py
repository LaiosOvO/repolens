from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from repo_teacher.models import FileRecord, SymbolRecord, stable_id, to_dict
from repo_teacher.snapshot import _sanitize_remote, capture_snapshot


class ModelsTest(unittest.TestCase):
    def test_stable_id_is_repeatable_and_namespaced(self) -> None:
        first = stable_id("symbol", "src/app.py", "main", "12")
        second = stable_id("symbol", "src/app.py", "main", "12")

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("symbol_"))
        self.assertNotEqual(first, stable_id("file", "src/app.py", "main", "12"))

    def test_records_serialize_without_dataclass_objects(self) -> None:
        file = FileRecord(
            id="file_1",
            path="src/app.py",
            language="Python",
            size=42,
            lines=3,
            sha256="abc",
        )
        symbol = SymbolRecord(
            id="symbol_1",
            file_id=file.id,
            path=file.path,
            name="main",
            qualified_name="main",
            kind="function",
            line=1,
            end_line=3,
            analyzer="python-ast",
            confidence="exact",
        )

        payload = to_dict({"file": file, "symbols": [symbol]})

        self.assertEqual(payload["file"]["path"], "src/app.py")
        self.assertEqual(payload["symbols"][0]["analyzer"], "python-ast")

    def test_remote_credentials_and_query_are_never_persisted(self) -> None:
        credential = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        sanitized = _sanitize_remote(
            f"https://alice:{credential}@github.com/acme/private.git?token=secret"
        )
        self.assertEqual(sanitized, "https://github.com/acme/private.git")
        self.assertEqual(_sanitize_remote("git@github.com:acme/private.git"), "git@github.com:acme/private.git")

    def test_git_status_failure_is_unknown_not_clean(self) -> None:
        values = iter(["/tmp/project", "main", None, "abc", None])
        with patch("repo_teacher.snapshot._git", side_effect=lambda *_args: next(values)):
            with patch("repo_teacher.snapshot._detect_license", return_value=None):
                snapshot = capture_snapshot(Path("/tmp/project"))
        self.assertIsNone(snapshot.dirty)


if __name__ == "__main__":
    unittest.main()
