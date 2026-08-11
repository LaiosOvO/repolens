from __future__ import annotations

import subprocess
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from repo_teacher.scanner import ScanOptions, capture_tree_manifest, scan_repository
from repo_teacher.snapshot import capture_snapshot


def run_git(path: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    )


class ScannerTest(unittest.TestCase):
    def test_snapshot_and_scan_are_deterministic_and_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "web").mkdir()
            (root / "node_modules").mkdir()
            (root / ".omx").mkdir()
            (root / "src" / "app.py").write_text(
                "def main():\n    return 1\n", encoding="utf-8"
            )
            (root / "web" / "main.ts").write_text(
                "export function boot() { return 1 }\n", encoding="utf-8"
            )
            (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
            (root / "LICENSE").write_text("MIT License\n", encoding="utf-8")
            (root / "node_modules" / "skip.js").write_text(
                "export const skip = 1\n", encoding="utf-8"
            )
            (root / ".omx" / "state.json").write_text(
                '{"internal": true}\n', encoding="utf-8"
            )
            (root / "too-large.py").write_text("x" * 500, encoding="utf-8")
            (root / "binary.py").write_bytes(b"hello\x00world")

            run_git(root, "init")
            run_git(root, "config", "user.email", "fixture@example.com")
            run_git(root, "config", "user.name", "Fixture")
            run_git(root, "add", "README.md", "LICENSE", "src/app.py", "web/main.ts")
            run_git(root, "commit", "-m", "fixture")

            snapshot = capture_snapshot(root)
            result = scan_repository(root, ScanOptions(max_file_size=128))

            self.assertTrue(snapshot.is_git)
            self.assertEqual(len(snapshot.commit or ""), 40)
            self.assertEqual(snapshot.license, "MIT")
            self.assertEqual(
                [file.path for file in result.files],
                ["LICENSE", "README.md", "src/app.py", "web/main.ts"],
            )
            self.assertEqual(result.language_counts["Python"], 1)
            self.assertEqual(result.language_counts["TypeScript"], 1)
            self.assertNotIn(
                "node_modules/skip.js", [file.path for file in result.files]
            )
            self.assertEqual(result.skipped["too_large"], 1)
            self.assertEqual(result.skipped["binary"], 1)

    def test_non_git_directory_is_reported_without_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("print('ok')\n", encoding="utf-8")

            snapshot = capture_snapshot(root)

            self.assertFalse(snapshot.is_git)
            self.assertIsNone(snapshot.commit)
            self.assertIsNone(snapshot.dirty)

    def test_fifo_is_skipped_without_blocking(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO is not supported on this platform")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.mkfifo(root / "blocked.py")

            result = scan_repository(root)

            self.assertEqual(result.files, [])
            self.assertEqual(result.skipped.get("non_regular"), 1)

    def test_scan_stops_at_file_budget_with_observable_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("a.py", "b.py", "c.py"):
                (root / name).write_text("VALUE = 1\n", encoding="utf-8")

            result = scan_repository(
                root, ScanOptions(max_files=2, max_total_bytes=None)
            )

            self.assertEqual([file.path for file in result.files], ["a.py", "b.py"])
            self.assertTrue(result.truncated)
            self.assertEqual(result.skipped["max_files"], 1)
            self.assertEqual(result.diagnostics[0].code, "max-files-exceeded")
            self.assertEqual(result.diagnostics[0].path, "c.py")

    def test_scan_byte_budget_counts_examined_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_bytes(b"a\x00b")
            (root / "b.py").write_text("pass\n", encoding="utf-8")

            result = scan_repository(
                root, ScanOptions(max_files=None, max_total_bytes=3)
            )

            self.assertEqual(result.files, [])
            self.assertEqual(result.skipped["binary"], 1)
            self.assertEqual(result.skipped["max_total_bytes"], 1)
            self.assertEqual(result.diagnostics[0].code, "max-total-bytes-exceeded")
            self.assertTrue(result.truncated)

    def test_invalid_scan_budgets_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_files"):
            ScanOptions(max_files=0)
        with self.assertRaisesRegex(ValueError, "max_total_bytes"):
            ScanOptions(max_total_bytes=0)
        with self.assertRaisesRegex(ValueError, "max_entries"):
            ScanOptions(max_entries=0)
        with self.assertRaisesRegex(ValueError, "deadline_seconds"):
            ScanOptions(deadline_seconds=0)

    def test_unsupported_and_too_large_files_consume_visited_file_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.bin").write_bytes(b"unsupported")
            (root / "b.py").write_text("x" * 100, encoding="utf-8")
            (root / "c.py").write_text("pass\n", encoding="utf-8")

            result = scan_repository(
                root,
                ScanOptions(
                    max_file_size=10,
                    max_files=2,
                    max_total_bytes=None,
                    deadline_seconds=None,
                ),
            )

            self.assertTrue(result.truncated)
            self.assertEqual(result.visited_files, 3)
            self.assertEqual(result.skipped["unsupported"], 1)
            self.assertEqual(result.skipped["too_large"], 1)
            self.assertIn("max-files-exceeded", {item.code for item in result.diagnostics})

    def test_scan_supports_cancellation_and_entry_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("pass\n", encoding="utf-8")
            (root / "b.py").write_text("pass\n", encoding="utf-8")

            cancelled = scan_repository(
                root, ScanOptions(cancelled=lambda: True, deadline_seconds=None)
            )
            limited = scan_repository(
                root, ScanOptions(max_entries=1, deadline_seconds=None)
            )

            self.assertTrue(cancelled.truncated)
            self.assertIn("scan-cancelled", {item.code for item in cancelled.diagnostics})
            self.assertTrue(limited.truncated)
            self.assertEqual(limited.visited_entries, 1)
            self.assertIn("max-entries-exceeded", {item.code for item in limited.diagnostics})

    def test_scan_deadline_and_stat_errors_are_observable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.py"
            target.write_text("pass\n", encoding="utf-8")
            original_stat = Path.stat

            def failing_stat(path: Path, *args: object, **kwargs: object) -> object:
                if path.name == target.name and path.parent.name == target.parent.name:
                    raise PermissionError("denied")
                return original_stat(path, *args, **kwargs)

            with patch.object(Path, "stat", failing_stat):
                failed = scan_repository(root, ScanOptions(deadline_seconds=None))
            ticks = iter((0.0, 1.0, 1.0, 1.0))
            with patch("repo_teacher.scanner.time.monotonic", side_effect=lambda: next(ticks)):
                expired = scan_repository(root, ScanOptions(deadline_seconds=0.5))

            self.assertEqual(failed.skipped["stat_error"], 1)
            self.assertIn("stat-error", {item.code for item in failed.diagnostics})
            self.assertTrue(expired.truncated)
            self.assertIn("scan-deadline-exceeded", {item.code for item in expired.diagnostics})

    def test_tree_manifest_fails_closed_on_entry_budget_and_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("pass\n", encoding="utf-8")
            (root / "b.py").write_text("pass\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "entry limit"):
                capture_tree_manifest(
                    root,
                    ScanOptions(max_entries=1, deadline_seconds=None),
                )
            calls = 0

            def cancelled() -> bool:
                nonlocal calls
                calls += 1
                return True

            with self.assertRaisesRegex(ValueError, "cancelled"):
                capture_tree_manifest(
                    root,
                    ScanOptions(cancelled=cancelled, deadline_seconds=None),
                )
            self.assertGreater(calls, 0)


if __name__ == "__main__":
    unittest.main()
