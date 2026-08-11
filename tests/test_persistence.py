from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from repo_teacher.persistence import (
    GenerationPublisher,
    OutputLock,
    atomic_write_json,
    atomic_write_text,
    read_json_path,
    read_published_json,
)


class PersistenceTest(unittest.TestCase):
    def test_atomic_writers_replace_complete_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_path = root / "nested" / "report.html"
            json_path = root / "nested" / "index.json"

            atomic_write_text(text_path, "first")
            atomic_write_text(text_path, "second")
            atomic_write_json(json_path, {"value": "中文"})

            self.assertEqual(text_path.read_text(encoding="utf-8"), "second")
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), {"value": "中文"})
            self.assertEqual(list((root / "nested").glob("*.tmp")), [])
            retired = list((root / "nested").glob(".repo-teacher-retired-report.html-*"))
            self.assertEqual(len(retired), 1)
            self.assertEqual(retired[0].read_text(encoding="utf-8"), "first")

    def test_atomic_writer_preserves_concurrent_replacement_during_exchange(self) -> None:
        import repo_teacher.persistence as module

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.html"
            displaced = root / "original-report.html"
            output.write_text("original", encoding="utf-8")
            real_exchange = module._rename_exchange
            injected = False

            def replace_then_exchange(*args: object, **kwargs: object) -> None:
                nonlocal injected
                if not injected:
                    output.rename(displaced)
                    output.write_text("USER-DATA", encoding="utf-8")
                    injected = True
                real_exchange(*args, **kwargs)

            with patch.object(module, "_rename_exchange", new=replace_then_exchange):
                with self.assertRaisesRegex(OSError, "preserved staging/displaced entry"):
                    atomic_write_text(output, "new-report")

            self.assertEqual(output.read_text(encoding="utf-8"), "new-report")
            self.assertEqual(displaced.read_text(encoding="utf-8"), "original")
            preserved = list(root.glob(".repo-teacher-new-report.html-*"))
            self.assertEqual(len(preserved), 1)
            self.assertEqual(preserved[0].read_text(encoding="utf-8"), "USER-DATA")

    def test_atomic_writer_refuses_non_regular_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            output.mkdir()
            (output / "keep.txt").write_text("USER-DATA", encoding="utf-8")

            with self.assertRaisesRegex(OSError, "non-regular output"):
                atomic_write_text(output, "blocked")

            self.assertEqual((output / "keep.txt").read_text(encoding="utf-8"), "USER-DATA")

    def test_output_lock_is_exclusive_and_keeps_permanent_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with OutputLock(root):
                self.assertTrue((root / ".repo-teacher.lock").is_file())
                with self.assertRaisesRegex(OSError, "locked"):
                    with OutputLock(root):
                        pass
            self.assertTrue((root / ".repo-teacher.lock").is_file())
            with OutputLock(root):
                pass

    def test_output_lock_recovers_after_process_exit_without_unlinking_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = (
                "import os, sys\n"
                "from pathlib import Path\n"
                "from repo_teacher.persistence import OutputLock\n"
                "lock = OutputLock(Path(sys.argv[1]))\n"
                "lock.__enter__()\n"
                "os._exit(0)\n"
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            subprocess.run(
                [sys.executable, "-c", script, str(root)],
                check=True,
                env=environment,
            )

            lockfile = root / ".repo-teacher.lock"
            self.assertTrue(lockfile.is_file())
            with OutputLock(root):
                self.assertTrue(lockfile.is_file())

    def test_output_lock_detects_name_replacement_during_acquisition(self) -> None:
        import repo_teacher.persistence as module

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with OutputLock(root):
                pass
            lock_path = root / ".repo-teacher.lock"
            displaced = root / "original-lock"
            real_assert = module.SecureDirectory.assert_child_identity
            swapped = False

            def swap_then_assert(
                secure: module.SecureDirectory,
                name: str,
                expected: tuple[int, int, int] | None,
            ) -> None:
                nonlocal swapped
                if not swapped and name == lock_path.name:
                    lock_path.rename(displaced)
                    lock_path.write_bytes(b"")
                    swapped = True
                real_assert(secure, name, expected)

            with patch.object(
                module.SecureDirectory,
                "assert_child_identity",
                new=swap_then_assert,
            ):
                with self.assertRaisesRegex(OSError, "changed during write"):
                    with OutputLock(root):
                        pass
            self.assertTrue(lock_path.is_file())
            self.assertTrue(displaced.is_file())

    def test_output_directory_lock_prevents_lockfile_replacement_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with OutputLock(root):
                lock_path = root / ".repo-teacher.lock"
                lock_path.rename(root / "displaced-lock")
                lock_path.write_bytes(b"")
                with self.assertRaisesRegex(OSError, "locked"):
                    with OutputLock(root):
                        pass
            with OutputLock(root):
                pass

    def test_atomic_writer_refuses_existing_file_or_directory_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            output = root / "output"
            outside.mkdir()
            output.mkdir()
            victim = outside / "victim.txt"
            victim.write_text("safe", encoding="utf-8")
            (output / "report.html").symlink_to(victim)

            with self.assertRaisesRegex(OSError, "symbolic link"):
                atomic_write_text(output / "report.html", "overwritten")

            linked_directory = root / "linked-output"
            linked_directory.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(OSError, "symbolic link"):
                atomic_write_text(linked_directory / "other.txt", "blocked")
            self.assertEqual(victim.read_text(encoding="utf-8"), "safe")

    def test_atomic_writer_refuses_deep_ancestor_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            linked = root / "link"
            linked.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(OSError, "symbolic link"):
                atomic_write_text(linked / "nested" / "report.html", "blocked")
            self.assertFalse((outside / "nested" / "report.html").exists())

    def test_generation_publish_is_all_or_nothing_across_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            first_id = "1" * 32
            second_id = "2" * 32
            first = {
                "index.json": json.dumps(
                    {"generation_id": first_id, "value": "old"}
                ),
                "index.html": (
                    '<html><head><meta name="repo-teacher-generation" '
                    f'content="{first_id}"></head><body>old</body></html>'
                ),
            }
            second = {
                "index.json": json.dumps(
                    {"generation_id": second_id, "value": "new"}
                ),
                "index.html": (
                    '<html><head><meta name="repo-teacher-generation" '
                    f'content="{second_id}"></head><body>new</body></html>'
                ),
            }

            with OutputLock(output):
                GenerationPublisher(output, first_id).publish(first)
            old_target = os.readlink(output / "current")

            def fail_before_switch() -> None:
                raise OSError("injected publish failure")

            with OutputLock(output):
                with self.assertRaisesRegex(OSError, "injected publish failure"):
                    GenerationPublisher(output, second_id).publish(
                        second, before_switch=fail_before_switch
                    )

            self.assertEqual(os.readlink(output / "current"), old_target)
            self.assertEqual(
                read_published_json(output, "index.json")["value"], "old"
            )
            self.assertIn("old", (output / "index.html").read_text(encoding="utf-8"))

    def test_all_supported_current_paths_verify_the_same_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"

            def artifacts(generation_id: str, value: str) -> dict[str, str]:
                return {
                    "index.json": json.dumps(
                        {"generation_id": generation_id, "value": value}
                    ),
                    "index.html": (
                        '<html><head><meta name="repo-teacher-generation" '
                        f'content="{generation_id}"></head><body>{value}</body></html>'
                    ),
                }

            first_id = "a" * 32
            second_id = "b" * 32
            with OutputLock(output):
                GenerationPublisher(output, first_id).publish(
                    artifacts(first_id, "first")
                )
            first_generation = output / ".repo-teacher-generations" / first_id
            with OutputLock(output):
                GenerationPublisher(output, second_id).publish(
                    artifacts(second_id, "second")
                )

            stable = read_json_path(output / "index.json")
            current = read_json_path(output / "current" / "index.json")
            immutable_current = read_json_path(
                output / ".repo-teacher-generations" / second_id / "index.json"
            )
            self.assertEqual(stable["generation_id"], second_id)
            self.assertEqual(current, stable)
            self.assertEqual(immutable_current, stable)
            with self.assertRaisesRegex(ValueError, "not the current generation"):
                read_json_path(first_generation / "index.json")

    def test_compatibility_links_only_cover_artifacts_in_current_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            first_id = "c" * 32
            second_id = "d" * 32
            first = {
                "index.json": json.dumps({"generation_id": first_id}),
                "index.html": (
                    '<html><head><meta name="repo-teacher-generation" '
                    f'content="{first_id}"></head></html>'
                ),
            }
            second = {
                "technology-selection.json": json.dumps(
                    {"generation_id": second_id}
                ),
                "technology-selection.html": (
                    '<html><head><meta name="repo-teacher-generation" '
                    f'content="{second_id}"></head></html>'
                ),
                "projects/demo/index.json": json.dumps(
                    {"generation_id": second_id}
                ),
            }
            with OutputLock(output):
                GenerationPublisher(output, first_id).publish(first)
            with OutputLock(output):
                GenerationPublisher(output, second_id).publish(second)

            visible = {
                item.name
                for item in output.iterdir()
                if item.name
                not in {"current", ".repo-teacher-generations", ".repo-teacher.lock"}
            }
            self.assertEqual(
                visible,
                {"projects", "technology-selection.json", "technology-selection.html"},
            )
            for name in visible:
                self.assertTrue((output / name).exists(), name)

    def test_generation_reader_rejects_tampered_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            generation_id = "3" * 32
            artifacts = {
                "index.json": json.dumps(
                    {"generation_id": generation_id, "value": "trusted"}
                ),
                "index.html": (
                    '<html><head><meta name="repo-teacher-generation" '
                    f'content="{generation_id}"></head><body>trusted</body></html>'
                ),
            }
            with OutputLock(output):
                GenerationPublisher(output, generation_id).publish(artifacts)

            target = (output / "current").resolve() / "index.json"
            target.chmod(0o644)
            target.write_text(
                json.dumps({"generation_id": generation_id, "value": "tampered"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "digest"):
                read_published_json(output, "index.json")

    def test_generation_refuses_legacy_collision_and_missing_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            output.mkdir()
            legacy = output / "index.json"
            legacy.write_text('{"legacy": true}\n', encoding="utf-8")
            generation_id = "4" * 32
            artifacts = {
                "index.json": json.dumps({"generation_id": generation_id}),
                "index.html": (
                    '<html><head><meta name="repo-teacher-generation" '
                    f'content="{generation_id}"></head></html>'
                ),
            }

            with self.assertRaises(FileNotFoundError):
                read_published_json(output, "index.json")
            with OutputLock(output):
                with self.assertRaisesRegex(OSError, "legacy"):
                    GenerationPublisher(output, generation_id).publish(artifacts)
            self.assertEqual(legacy.read_text(encoding="utf-8"), '{"legacy": true}\n')
            self.assertFalse((output / "current").exists())

    def test_file_uri_follows_one_generation_and_old_generation_is_retained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"

            def artifacts(generation_id: str, value: str) -> dict[str, str]:
                return {
                    "index.json": json.dumps(
                        {"generation_id": generation_id, "value": value}
                    ),
                    "index.html": (
                        '<html><head><meta name="repo-teacher-generation" '
                        f'content="{generation_id}"></head><body>{value}</body></html>'
                    ),
                }

            first_id = "5" * 32
            second_id = "6" * 32
            with OutputLock(output):
                GenerationPublisher(output, first_id).publish(
                    artifacts(first_id, "first")
                )
            with OutputLock(output):
                GenerationPublisher(output, second_id).publish(
                    artifacts(second_id, "second")
                )

            with urllib.request.urlopen((output / "index.html").as_uri()) as response:
                html = response.read().decode("utf-8")
            self.assertIn(second_id, html)
            self.assertIn("second", html)
            generations = output / ".repo-teacher-generations"
            self.assertTrue((generations / first_id / "index.html").is_file())
            self.assertTrue((generations / second_id / "index.html").is_file())

    def test_staging_write_failure_never_switches_current(self) -> None:
        import repo_teacher.persistence as module

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            first_id = "7" * 32
            second_id = "8" * 32

            def artifacts(generation_id: str, value: str) -> dict[str, str]:
                return {
                    "index.json": json.dumps(
                        {"generation_id": generation_id, "value": value}
                    ),
                    "index.html": (
                        '<html><head><meta name="repo-teacher-generation" '
                        f'content="{generation_id}"></head><body>{value}</body></html>'
                    ),
                }

            with OutputLock(output):
                GenerationPublisher(output, first_id).publish(
                    artifacts(first_id, "old")
                )
            previous_target = os.readlink(output / "current")
            real_write = module.atomic_write_text
            writes = 0

            def fail_second_write(path: Path, content: str) -> None:
                nonlocal writes
                writes += 1
                if writes == 2:
                    raise OSError("injected staging crash")
                real_write(path, content)

            with patch.object(module, "atomic_write_text", new=fail_second_write):
                with OutputLock(output):
                    with self.assertRaisesRegex(OSError, "injected staging crash"):
                        GenerationPublisher(output, second_id).publish(
                            artifacts(second_id, "new")
                        )
            self.assertEqual(os.readlink(output / "current"), previous_target)
            self.assertEqual(
                read_published_json(output, "index.json")["value"], "old"
            )

    def test_compatibility_reconciliation_failure_rolls_back_current_and_links(
        self,
    ) -> None:
        import repo_teacher.persistence as module

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            first_id = "e" * 32
            second_id = "f" * 32
            first = {
                "index.json": json.dumps(
                    {"generation_id": first_id, "value": "old"}
                ),
                "index.html": (
                    '<html><head><meta name="repo-teacher-generation" '
                    f'content="{first_id}"></head></html>'
                ),
            }
            second = {
                "technology-selection.json": json.dumps(
                    {"generation_id": second_id, "value": "new"}
                ),
                "technology-selection.html": (
                    '<html><head><meta name="repo-teacher-generation" '
                    f'content="{second_id}"></head></html>'
                ),
            }
            with OutputLock(output):
                GenerationPublisher(output, first_id).publish(first)
            old_target = os.readlink(output / "current")
            real_replace = module._replace_compatibility_links
            injected = False

            def replace_then_fail(
                secure: module.SecureDirectory, desired: set[str]
            ) -> None:
                nonlocal injected
                real_replace(secure, desired)
                if not injected:
                    injected = True
                    raise OSError("injected compatibility failure")

            with OutputLock(output):
                with patch.object(
                    module, "_replace_compatibility_links", new=replace_then_fail
                ):
                    with self.assertRaisesRegex(
                        OSError, "injected compatibility failure"
                    ):
                        GenerationPublisher(output, second_id).publish(second)

            self.assertEqual(os.readlink(output / "current"), old_target)
            self.assertTrue((output / "index.json").exists())
            self.assertTrue((output / "index.html").exists())
            self.assertFalse((output / "technology-selection.json").exists())
            self.assertFalse((output / "technology-selection.html").exists())
            self.assertEqual(read_published_json(output)["value"], "old")

    def test_next_writer_repairs_compatibility_links_after_hard_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            first_id = "1" * 32
            second_id = "2" * 32
            first = {
                "index.json": json.dumps(
                    {"generation_id": first_id, "value": "old"}
                ),
                "index.html": (
                    '<html><head><meta name="repo-teacher-generation" '
                    f'content="{first_id}"></head></html>'
                ),
            }
            with OutputLock(output):
                GenerationPublisher(output, first_id).publish(first)

            script = (
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "from unittest.mock import patch\n"
                "import repo_teacher.persistence as persistence\n"
                "output = Path(sys.argv[1])\n"
                "generation_id = sys.argv[2]\n"
                "artifacts = {\n"
                "  'technology-selection.json': json.dumps({"
                "'generation_id': generation_id, 'value': 'new'}),\n"
                "  'technology-selection.html': '<html><head><meta name=\"repo-teacher-generation\" '"
                "+ f'content=\"{generation_id}\"></head></html>',\n"
                "}\n"
                "with persistence.OutputLock(output):\n"
                "  with patch.object(persistence, '_replace_compatibility_links', "
                "side_effect=lambda *args: os._exit(23)):\n"
                "    persistence.GenerationPublisher(output, generation_id).publish(artifacts)\n"
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(
                Path(__file__).resolve().parents[1] / "src"
            )
            child = subprocess.run(
                [sys.executable, "-c", script, str(output), second_id],
                check=False,
                env=environment,
            )

            self.assertEqual(child.returncode, 23)
            self.assertEqual(
                read_published_json(output, "technology-selection.json")["value"],
                "new",
            )
            self.assertTrue((output / "index.json").is_symlink())
            self.assertFalse((output / "index.json").exists())

            with OutputLock(output):
                pass

            visible = {
                item.name
                for item in output.iterdir()
                if item.name
                not in {"current", ".repo-teacher-generations", ".repo-teacher.lock"}
            }
            self.assertEqual(
                visible,
                {"technology-selection.json", "technology-selection.html"},
            )
            self.assertTrue(
                all((output / name).exists() for name in visible)
            )
            self.assertFalse(
                any(
                    item.name.startswith(
                        (".repo-teacher-current-", ".repo-teacher-link-")
                    )
                    for item in output.iterdir()
                )
            )


if __name__ == "__main__":
    unittest.main()
