"""Consistent copy-on-write repository snapshots for long report pipelines."""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
from typing import Iterator

from ..scanner import DEFAULT_EXCLUDED_DIRS, ScanOptions, capture_tree_manifest


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    original: Path
    path: Path
    source_manifest_sha256: str


def _excluded_roots(paths: Iterable[Path]) -> tuple[Path, ...]:
    return tuple(path.expanduser().resolve() for path in paths)


def _is_excluded(path: Path, roots: tuple[Path, ...]) -> bool:
    absolute = Path(os.path.abspath(path))
    return any(absolute == root or absolute.is_relative_to(root) for root in roots)


def _relative_paths(
    source: Path,
    *,
    excluded_paths: tuple[Path, ...] = (),
) -> list[str]:
    excluded_roots = _excluded_roots(excluded_paths)
    tracked = subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if tracked.returncode == 0:
        paths = sorted(
            path.decode("utf-8", errors="surrogateescape")
            for path in tracked.stdout.split(b"\0")
            if path
        )
        excluded = DEFAULT_EXCLUDED_DIRS | frozenset({".codegraph"})
        paths = [
            path
            for path in paths
            if not any(part in excluded for part in Path(path).parts)
            and not _is_excluded(source.joinpath(*Path(path).parts), excluded_roots)
        ]
        # ``git ls-files`` records a populated submodule as one gitlink path.
        # A report must analyze the checked-out source tree, not an empty
        # directory placeholder, so expand each initialized submodule using
        # its own tracked/untracked manifest.
        submodules = subprocess.run(
            ["git", "-C", str(source), "submodule", "status", "--recursive"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if submodules.returncode == 0:
            expanded: list[str] = []
            submodule_roots: list[str] = []
            for line in submodules.stdout.splitlines():
                fields = line.lstrip(" -+").split()
                if len(fields) < 2:
                    continue
                submodule_path = fields[1].replace("\\", "/").strip("/")
                submodule_root = source.joinpath(*Path(submodule_path).parts)
                if not (submodule_root / ".git").exists():
                    continue
                submodule_roots.append(submodule_path)
                expanded.extend(
                    f"{submodule_path}/{child}"
                    for child in _relative_paths(submodule_root)
                )
            if submodule_roots:
                paths = [path for path in paths if path not in submodule_roots]
                paths.extend(expanded)
        return sorted(set(paths))
    paths: list[str] = []
    for current, dirs, names in os.walk(source, topdown=True, followlinks=False):
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in DEFAULT_EXCLUDED_DIRS
            and not _is_excluded(Path(current) / name, excluded_roots)
        )
        current_path = Path(current)
        for name in sorted(names):
            candidate = current_path / name
            if not _is_excluded(candidate, excluded_roots):
                paths.append(candidate.relative_to(source).as_posix())
    return paths


def _clone_entry(source: Path, destination: Path) -> None:
    metadata = source.lstat()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if stat.S_ISLNK(metadata.st_mode):
        destination.symlink_to(os.readlink(source))
        return
    if not stat.S_ISREG(metadata.st_mode):
        return
    if platform.system() == "Darwin":
        command = ["cp", "-c", "-p", str(source), str(destination)]
    else:
        command = ["cp", "--reflink=auto", "-p", str(source), str(destination)]
    copied = subprocess.run(command, capture_output=True, check=False, timeout=60)
    if copied.returncode == 0:
        return
    shutil.copy2(source, destination, follow_symlinks=False)


def _clone_git_identity(source: Path, destination: Path) -> None:
    git_entry = source / ".git"
    if not git_entry.exists() and not git_entry.is_symlink():
        return
    if git_entry.is_file():
        _clone_entry(git_entry, destination / ".git")
        return
    if platform.system() == "Darwin":
        command = ["cp", "-cR", str(git_entry), str(destination / ".git")]
    else:
        command = [
            "cp",
            "-a",
            "--reflink=auto",
            str(git_entry),
            str(destination / ".git"),
        ]
    copied = subprocess.run(command, capture_output=True, check=False, timeout=120)
    if copied.returncode != 0:
        shutil.copytree(
            git_entry,
            destination / ".git",
            symlinks=True,
            copy_function=shutil.copy2,
        )


def _copy_repository(
    source: Path,
    destination: Path,
    *,
    excluded_paths: tuple[Path, ...] = (),
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for relative in _relative_paths(source, excluded_paths=excluded_paths):
        parts = Path(relative).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"repository snapshot path is invalid: {relative}")
        entry = source.joinpath(*parts)
        if not entry.exists() and not entry.is_symlink():
            continue
        _clone_entry(entry, destination.joinpath(*parts))
    _clone_git_identity(source, destination)


@contextmanager
def consistent_repository_snapshot(
    source: Path,
    *,
    attempts: int = 3,
    excluded_paths: Iterable[Path] = (),
) -> Iterator[RepositorySnapshot]:
    """Yield one stable point-in-time repository tree.

    Git-tracked and untracked, non-ignored files are copied.  The Git metadata
    is retained for commit/remote/dirty identity, while ignored dependency
    trees and CodeGraph caches are not part of feature evidence.
    """

    if attempts < 1:
        raise ValueError("snapshot attempts must be positive")
    original = source.expanduser().resolve()
    excluded = _excluded_roots(excluded_paths)
    options = ScanOptions(
        excluded_dirs=DEFAULT_EXCLUDED_DIRS | frozenset({".codegraph"}),
        excluded_paths=excluded,
    )
    snapshot_parent = original.parent / ".repo-teacher-snapshots"
    snapshot_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"{original.name}-", dir=snapshot_parent
    ) as temporary:
        root = Path(temporary)
        last_before = ""
        for attempt in range(1, attempts + 1):
            before = capture_tree_manifest(original, options)
            last_before = before
            destination = root / f"attempt-{attempt}" / original.name
            _copy_repository(
                original,
                destination,
                excluded_paths=excluded,
            )
            after = capture_tree_manifest(original, options)
            if before == after:
                yield RepositorySnapshot(original, destination, before)
                return
        raise ValueError(
            "source repository changed during every snapshot attempt: "
            f"{last_before[:12]}"
        )
