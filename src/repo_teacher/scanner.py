from __future__ import annotations

import hashlib
import os
import stat
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .models import DiagnosticRecord, FileRecord, stable_id


LANGUAGES = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C/C++ Header",
    ".cc": "C++",
    ".cpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".sh": "Shell",
    ".bash": "Shell",
    ".sql": "SQL",
    ".md": "Markdown",
    ".mdx": "Markdown",
    ".rst": "ReStructuredText",
    ".json": "JSON",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
}

SPECIAL_NAMES = {
    "Dockerfile": "Dockerfile",
    "Makefile": "Makefile",
    "LICENSE": "License",
    "COPYING": "License",
}

DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".omx",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "vendor",
        "dist",
        "build",
        "target",
        "coverage",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".codegraph",
        "__pycache__",
        ".repo-teacher",
    }
)


@dataclass(slots=True)
class ScanOptions:
    max_file_size: int = 1_000_000
    max_files: int | None = 100_000
    max_total_bytes: int | None = 1_000_000_000
    max_entries: int | None = 250_000
    deadline_seconds: float | None = 120.0
    excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS
    excluded_paths: tuple[Path, ...] = ()
    cancelled: Callable[[], bool] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if self.max_file_size <= 0:
            raise ValueError("max_file_size must be greater than zero")
        if self.max_files is not None and self.max_files <= 0:
            raise ValueError("max_files must be greater than zero or None")
        if self.max_total_bytes is not None and self.max_total_bytes <= 0:
            raise ValueError("max_total_bytes must be greater than zero or None")
        if self.max_entries is not None and self.max_entries <= 0:
            raise ValueError("max_entries must be greater than zero or None")
        if self.deadline_seconds is not None and self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be greater than zero or None")


@dataclass(slots=True)
class ScanResult:
    files: list[FileRecord]
    contents: dict[str, str]
    language_counts: dict[str, int]
    skipped: dict[str, int]
    diagnostics: list[DiagnosticRecord] = field(default_factory=list)
    truncated: bool = False
    visited_entries: int = 0
    visited_files: int = 0
    declared_bytes: int = 0


def capture_tree_manifest(path: Path, options: ScanOptions | None = None) -> str:
    """Fingerprint the visible tree boundary used by a scan.

    This is a race detector, not a filesystem snapshot.  It includes supported
    and unsupported entries so a late file cannot hide outside the analyzer's
    language set.  Callers compare manifests captured around the final scan.
    """

    root = path.expanduser().resolve()
    config = options or ScanOptions()
    excluded_roots = tuple(
        item.expanduser().resolve() for item in config.excluded_paths
    )
    digest = hashlib.sha256()
    started_at = time.monotonic()
    visited_entries = 0

    def record_error(error: OSError) -> None:
        relative = str(error.filename or ".")
        raise ValueError(
            f"tree manifest could not inspect {relative}: {type(error).__name__}: {error}"
        ) from error

    def consume(relative: str) -> None:
        nonlocal visited_entries
        try:
            if config.cancelled is not None and config.cancelled():
                raise ValueError("tree manifest was cancelled")
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(
                f"tree manifest cancellation hook failed closed: {error}"
            ) from error
        if (
            config.deadline_seconds is not None
            and time.monotonic() - started_at >= config.deadline_seconds
        ):
            raise ValueError(
                f"tree manifest exceeded its {config.deadline_seconds:g} second deadline"
            )
        if config.max_entries is not None and visited_entries >= config.max_entries:
            raise ValueError(
                "tree manifest reached the configured "
                f"{config.max_entries} entry limit at {relative}"
            )
        visited_entries += 1

    for current, dirs, names in os.walk(
        root, topdown=True, followlinks=False, onerror=record_error
    ):
        current_path = Path(current)
        retained: list[str] = []
        for directory in sorted(dirs):
            candidate = current_path / directory
            relative = candidate.relative_to(root).as_posix()
            consume(relative)
            try:
                metadata = candidate.stat(follow_symlinks=False)
            except OSError as error:
                record_error(error)
            if directory in config.excluded_dirs or stat.S_ISLNK(metadata.st_mode):
                continue
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as error:
                record_error(error)
            if any(resolved.is_relative_to(excluded) for excluded in excluded_roots):
                continue
            retained.append(directory)
        dirs[:] = retained
        for name in sorted([*retained, *names]):
            candidate = current_path / name
            relative = candidate.relative_to(root).as_posix()
            if name not in retained:
                consume(relative)
            try:
                metadata = candidate.lstat()
                digest.update(
                    (
                        f"{relative}\0{stat.S_IFMT(metadata.st_mode)}\0"
                        f"{metadata.st_size}\0{metadata.st_mtime_ns}\0"
                        f"{metadata.st_ctime_ns}\0"
                    ).encode("utf-8", errors="surrogateescape")
                )
            except OSError as error:
                record_error(error)
    return digest.hexdigest()


def _language_for(path: Path) -> str | None:
    if path.name in SPECIAL_NAMES:
        return SPECIAL_NAMES[path.name]
    if path.name.lower().startswith("license"):
        return "License"
    if path.name.lower().startswith("readme"):
        return "Markdown"
    return LANGUAGES.get(path.suffix.lower())


def _module_for(relative: Path) -> str:
    return relative.parts[0] if len(relative.parts) > 1 else "root"


def scan_repository(path: Path, options: ScanOptions | None = None) -> ScanResult:
    root = path.expanduser().resolve()
    config = options or ScanOptions()
    excluded_roots = tuple(
        item.expanduser().resolve() for item in config.excluded_paths
    )
    files: list[FileRecord] = []
    contents: dict[str, str] = {}
    skipped: Counter[str] = Counter()
    diagnostics: list[DiagnosticRecord] = []
    visited_entries = 0
    visited_files = 0
    declared_bytes = 0
    truncated = False
    started_at = time.monotonic()

    def stop(path: str, code: str, message: str) -> None:
        nonlocal truncated
        if truncated:
            return
        truncated = True
        skipped[code.replace("-exceeded", "").replace("-", "_")] += 1
        diagnostics.append(DiagnosticRecord(path, "warning", code, message))

    def interrupted(path: str) -> bool:
        try:
            is_cancelled = bool(config.cancelled and config.cancelled())
        except Exception as error:  # cancellation hooks are external boundaries
            stop(path, "scan-cancelled", f"cancellation hook failed closed: {error}")
            return True
        if is_cancelled:
            stop(path, "scan-cancelled", "scan was cancelled by its caller")
            return True
        if (
            config.deadline_seconds is not None
            and time.monotonic() - started_at >= config.deadline_seconds
        ):
            stop(
                path,
                "scan-deadline-exceeded",
                f"scan exceeded its {config.deadline_seconds:g} second deadline",
            )
            return True
        return False

    def consume_entry(path: str) -> bool:
        nonlocal visited_entries
        if interrupted(path):
            return False
        if config.max_entries is not None and visited_entries >= config.max_entries:
            stop(
                path,
                "max-entries-exceeded",
                f"scan stopped after reaching the configured {config.max_entries} directory-entry limit",
            )
            return False
        visited_entries += 1
        return True

    def record_walk_error(error: OSError) -> None:
        skipped["walk_error"] += 1
        error_path = Path(error.filename) if error.filename else root
        try:
            display_path = str(error_path.relative_to(root))
        except ValueError:
            display_path = str(error_path)
        diagnostics.append(
            DiagnosticRecord(display_path, "error", "walk-error", str(error))
        )

    for current, dirs, names in os.walk(
        root, topdown=True, followlinks=False, onerror=record_walk_error
    ):
        current_path = Path(current)
        if interrupted(current_path.relative_to(root).as_posix() or "."):
            dirs.clear()
            break
        retained_dirs: list[str] = []
        for directory in sorted(dirs):
            source_dir = current_path / directory
            relative_dir = source_dir.relative_to(root).as_posix()
            if not consume_entry(relative_dir):
                break
            try:
                directory_metadata = source_dir.stat(follow_symlinks=False)
            except OSError as exc:
                skipped["stat_error"] += 1
                diagnostics.append(
                    DiagnosticRecord(
                        relative_dir, "warning", "stat-error", str(exc)
                    )
                )
                continue
            if stat.S_ISLNK(directory_metadata.st_mode):
                skipped["symlink"] += 1
                continue
            try:
                is_excluded = any(
                    source_dir.resolve(strict=True).is_relative_to(excluded)
                    for excluded in excluded_roots
                )
            except OSError as exc:
                skipped["stat_error"] += 1
                diagnostics.append(
                    DiagnosticRecord(
                        relative_dir, "warning", "stat-error", str(exc)
                    )
                )
                continue
            if directory not in config.excluded_dirs and not is_excluded:
                retained_dirs.append(directory)
        dirs[:] = [] if truncated else retained_dirs
        if truncated:
            break
        for name in sorted(names):
            source = current_path / name
            relative = source.relative_to(root)
            relative_text = relative.as_posix()
            if not consume_entry(relative_text):
                dirs.clear()
                break
            visited_files += 1
            if config.max_files is not None and visited_files > config.max_files:
                stop(
                    relative_text,
                    "max-files-exceeded",
                    f"scan stopped after reaching the configured {config.max_files} visited-file limit",
                )
                dirs.clear()
                break
            try:
                metadata = source.stat(follow_symlinks=False)
            except OSError as exc:
                skipped["stat_error"] += 1
                diagnostics.append(
                    DiagnosticRecord(relative_text, "warning", "stat-error", str(exc))
                )
                continue
            if stat.S_ISLNK(metadata.st_mode):
                skipped["symlink"] += 1
                continue
            if not stat.S_ISREG(metadata.st_mode):
                skipped["non_regular"] += 1
                continue
            size = metadata.st_size
            remaining_total_bytes = (
                config.max_total_bytes - declared_bytes
                if config.max_total_bytes is not None
                else None
            )
            if (
                config.max_total_bytes is not None
                and (remaining_total_bytes is None or size > remaining_total_bytes)
            ):
                stop(
                    relative_text,
                    "max-total-bytes-exceeded",
                    "scan stopped before the declared repository byte budget would be exceeded "
                    f"({declared_bytes} of {config.max_total_bytes} bytes consumed)",
                )
                dirs.clear()
                break
            declared_bytes += size
            language = _language_for(relative)
            if language is None:
                skipped["unsupported"] += 1
                continue
            if size > config.max_file_size:
                skipped["too_large"] += 1
                continue
            try:
                descriptor = os.open(
                    source,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_NONBLOCK", 0),
                )
                with os.fdopen(descriptor, "rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if not stat.S_ISREG(opened.st_mode):
                        skipped["non_regular"] += 1
                        continue
                    # A regular file may grow after the metadata check.  Never
                    # let that race turn one repository entry into an
                    # unbounded allocation; one extra byte is enough to prove
                    # the declared file-size boundary was crossed.
                    read_boundary = config.max_file_size
                    if remaining_total_bytes is not None:
                        read_boundary = min(read_boundary, remaining_total_bytes)
                    raw = handle.read(read_boundary + 1)
                    closed = os.fstat(handle.fileno())
                if (
                    (
                        metadata.st_dev,
                        metadata.st_ino,
                        metadata.st_size,
                        metadata.st_mtime_ns,
                        metadata.st_ctime_ns,
                    )
                    != (
                        opened.st_dev,
                        opened.st_ino,
                        opened.st_size,
                        opened.st_mtime_ns,
                        opened.st_ctime_ns,
                    )
                    or (
                        opened.st_dev,
                        opened.st_ino,
                        opened.st_size,
                        opened.st_mtime_ns,
                        opened.st_ctime_ns,
                    )
                    != (
                        closed.st_dev,
                        closed.st_ino,
                        closed.st_size,
                        closed.st_mtime_ns,
                        closed.st_ctime_ns,
                    )
                    or len(raw) != opened.st_size
                ):
                    skipped["changed_while_reading"] += 1
                    diagnostics.append(
                        DiagnosticRecord(
                            str(relative),
                            "error",
                            "file-changed-while-reading",
                            "file metadata changed while it was being read; retry from a stable source tree",
                        )
                    )
                    continue
            except OSError as exc:
                skipped["read_error"] += 1
                diagnostics.append(
                    DiagnosticRecord(str(relative), "warning", "read-error", str(exc))
                )
                continue
            if b"\x00" in raw[:8192]:
                skipped["binary"] += 1
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                skipped["encoding"] += 1
                continue
            record = FileRecord(
                id=stable_id("file", relative_text),
                path=relative_text,
                language=language,
                size=size,
                lines=len(text.splitlines()),
                sha256=hashlib.sha256(raw).hexdigest(),
                module=_module_for(relative),
            )
            files.append(record)
            contents[relative_text] = text
        if truncated:
            break

    files.sort(key=lambda item: item.path)
    languages = Counter(file.language for file in files)
    return ScanResult(
        files=files,
        contents=contents,
        language_counts=dict(
            sorted(languages.items(), key=lambda item: (-item[1], item[0]))
        ),
        skipped=dict(sorted(skipped.items())),
        diagnostics=diagnostics,
        truncated=truncated,
        visited_entries=visited_entries,
        visited_files=visited_files,
        declared_bytes=declared_bytes,
    )
