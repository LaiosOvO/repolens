from __future__ import annotations

import json
import os
import secrets
import stat
import tempfile
import ctypes
import errno
import fcntl
import hashlib
import hmac
import re
import sys
from contextlib import AbstractContextManager
from collections.abc import Callable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any


_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_GENERATIONS_DIRECTORY = ".repo-teacher-generations"
_GENERATION_MANIFEST = "generation-manifest.json"
_GENERATION_ID = re.compile(r"^[0-9a-f]{32}$")
_MAX_GENERATION_MANIFEST_BYTES = 16 * 1024 * 1024
_HTML_GENERATION = re.compile(
    r'<meta\s+name=["\']repo-teacher-generation["\']\s+'
    r'content=["\'](?P<generation>[0-9a-f]{32})["\']\s*/?>',
    re.IGNORECASE,
)
_COMPATIBILITY_ENTRIES = (
    "index.json",
    "index.html",
    "capability-graph.json",
    "analysis-pack.json",
    "human-report.json",
    "modules",
    "projects",
    "technology-selection.json",
    "technology-selection.html",
)
_VERIFIED_PUBLICATION = object()


class VerifiedPublishedJson(dict[str, Any]):
    """A JSON object read through a verified immutable current generation.

    The marker is intentionally created only by :func:`read_published_json`.
    Incremental indexing uses it to distinguish a disk publication whose
    manifest and every artifact were verified from an arbitrary in-memory
    dictionary carrying self-computed checksums.
    """

    def __init__(
        self,
        payload: dict[str, Any],
        *,
        token: object,
        output: Path,
        relative: str,
        generation_id: str,
    ) -> None:
        if token is not _VERIFIED_PUBLICATION:
            raise TypeError("verified publication values can only be created by the reader")
        super().__init__(payload)
        self.publication_output = output
        self.publication_relative = relative
        self.publication_generation_id = generation_id


def _compatibility_entries_for(artifacts: set[str]) -> set[str]:
    """Return the convenience entries backed by this exact generation."""

    return {
        name
        for name in _COMPATIBILITY_ENTRIES
        if name in artifacts
        or any(relative.startswith(f"{name}/") for relative in artifacts)
    }


def _entry_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    """Return the stable fields needed to guard a directory-entry rename."""

    return (metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode))


def _rename_noreplace(
    source_name: str,
    target_name: str,
    *,
    source_fd: int,
    target_fd: int,
) -> None:
    """Atomically rename a directory entry without replacing a destination.

    ``os.rename`` is not sufficient here: POSIX permits it to replace an entry
    created after the caller's last check.  Skill publication needs the kernel
    to enforce the absent-destination precondition in the same operation.
    """

    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    target = os.fsencode(target_name)
    if sys.platform == "darwin":
        function = getattr(libc, "renameatx_np", None)
        if function is None:
            raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        # RENAME_EXCL from <stdio.h> / renameatx_np(2).
        result = function(source_fd, source, target_fd, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(libc, "renameat2", None)
        if function is None:
            raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        # RENAME_NOREPLACE from <linux/fs.h>.
        result = function(source_fd, source, target_fd, target, 0x00000001)
    else:
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), target_name)


def _rename_exchange(
    first_name: str,
    second_name: str,
    *,
    first_fd: int,
    second_fd: int,
) -> None:
    """Atomically exchange two entries without destroying either one.

    Conditional replacement ("replace only if this inode is still present")
    is not exposed by POSIX.  An exchange is the conservative primitive: the
    displaced entry remains reachable and can be retained for inspection.
    """

    libc = ctypes.CDLL(None, use_errno=True)
    first = os.fsencode(first_name)
    second = os.fsencode(second_name)
    if sys.platform == "darwin":
        function = getattr(libc, "renameatx_np", None)
        if function is None:
            raise OSError(errno.ENOTSUP, "atomic exchange rename is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        # RENAME_SWAP from <stdio.h> / renameatx_np(2).
        result = function(first_fd, first, second_fd, second, 0x00000002)
    elif sys.platform.startswith("linux"):
        function = getattr(libc, "renameat2", None)
        if function is None:
            raise OSError(errno.ENOTSUP, "atomic exchange rename is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        # RENAME_EXCHANGE from <linux/fs.h>.
        result = function(first_fd, first, second_fd, second, 0x00000002)
    else:
        raise OSError(errno.ENOTSUP, "atomic exchange rename is unavailable")
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), second_name)


def _trusted_prefix_normalized(path: Path) -> Path:
    """Normalize OS-owned aliases while rejecting caller-controlled symlinks.

    macOS exposes temporary paths below ``/var`` although ``/var`` is an
    immutable root-owned alias to ``/private/var``.  That system prefix is safe
    to normalize.  A symlink below any directory writable by this process is
    attacker-controlled and must be rejected instead of resolved.
    """

    lexical = Path(os.path.abspath(path.expanduser()))
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        candidate = current / part
        try:
            metadata = os.lstat(candidate)
        except FileNotFoundError:
            current = candidate
            continue
        if stat.S_ISLNK(metadata.st_mode):
            if os.access(current, os.W_OK):
                raise OSError(f"refusing to write through symbolic link: {candidate}")
            current = Path(os.path.realpath(candidate))
        else:
            current = candidate
    return current


def _open_directory_chain(path: Path, *, create: bool) -> int:
    """Open every directory with openat/O_NOFOLLOW, optionally mkdirat-ing it."""

    normalized = _trusted_prefix_normalized(path)
    descriptor = os.open(normalized.anchor, _DIRECTORY_FLAGS)
    try:
        for part in normalized.parts[1:]:
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except OSError as error:
                raise OSError(
                    f"refusing unsafe or non-directory path component: {normalized}"
                ) from error
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


class SecureDirectory(AbstractContextManager["SecureDirectory"]):
    """Hold a verified directory fd so rename operations cannot cross its root."""

    def __init__(self, directory: Path, *, create: bool = False) -> None:
        self.path = _trusted_prefix_normalized(directory)
        self._create = create
        self._descriptor: int | None = None
        self._identity: tuple[int, int] | None = None

    @property
    def descriptor(self) -> int:
        if self._descriptor is None:
            raise RuntimeError("secure directory is not open")
        return self._descriptor

    def __enter__(self) -> "SecureDirectory":
        self._descriptor = _open_directory_chain(self.path, create=self._create)
        opened = os.fstat(self._descriptor)
        self._identity = (opened.st_dev, opened.st_ino)
        self.assert_unchanged()
        return self

    @classmethod
    def from_open_descriptor(
        cls,
        directory: Path,
        descriptor: int,
        expected: tuple[int, int, int],
    ) -> "SecureDirectory":
        """Adopt a freshly opened directory fd without reopening its pathname."""

        opened = os.fstat(descriptor)
        identity = _entry_identity(opened)
        if identity != expected or identity[2] != stat.S_IFDIR:
            os.close(descriptor)
            raise OSError(f"open directory identity does not match creation: {directory}")
        instance = cls(directory)
        instance._descriptor = descriptor
        instance._identity = (opened.st_dev, opened.st_ino)
        try:
            instance.assert_unchanged()
        except BaseException:
            instance.__exit__(None, None, None)
            raise
        return instance

    def assert_unchanged(self) -> None:
        """Re-walk ancestors and prove the pathname still names the held fd."""

        if self._identity is None:
            raise RuntimeError("secure directory is not open")
        probe = _open_directory_chain(self.path, create=False)
        try:
            current = os.fstat(probe)
            if (current.st_dev, current.st_ino) != self._identity:
                raise OSError(f"output directory changed during write: {self.path}")
        finally:
            os.close(probe)

    def child_path(self, name: str) -> Path:
        if not name or name in {".", ".."} or "/" in name or os.sep in name:
            raise OSError(f"unsafe output child name: {name}")
        return self.path / name

    def mkdir_unique(self, prefix: str) -> tuple[str, Path]:
        for _ in range(128):
            name = f"{prefix}{secrets.token_hex(8)}"
            try:
                os.mkdir(name, mode=0o700, dir_fd=self.descriptor)
            except FileExistsError:
                continue
            return name, self.child_path(name)
        raise FileExistsError(f"could not allocate a staging directory below {self.path}")

    def child_identity(self, name: str) -> tuple[int, int, int] | None:
        """Return a no-follow identity for a direct child.

        Callers use this immediately before a rename to detect replacement of a
        previously inspected entry.  The held parent fd keeps the lookup below
        the verified directory even when its pathname is concurrently changed.
        """

        self.child_path(name)
        self.assert_unchanged()
        try:
            metadata = os.stat(name, dir_fd=self.descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(metadata.st_mode):
            raise OSError(f"refusing symbolic-link directory entry: {self.child_path(name)}")
        return _entry_identity(metadata)

    def assert_child_identity(
        self,
        name: str,
        expected: tuple[int, int, int] | None,
    ) -> None:
        actual = self.child_identity(name)
        if actual != expected:
            raise OSError(f"directory entry changed during write: {self.child_path(name)}")

    def replace_to(
        self,
        source_name: str,
        target_parent: "SecureDirectory",
        target_name: str,
        *,
        expected_source: tuple[int, int, int],
        expected_target: tuple[int, int, int] | None,
    ) -> None:
        """Rename a verified child to another held directory, fail-closed.

        This is used by the Skill publisher to move backups into its private
        transaction directory.  Both source and destination identities are
        rechecked directly before ``renameat`` and both parent fds are verified
        again after it.
        """

        self.child_path(source_name)
        target_parent.child_path(target_name)
        self.assert_child_identity(source_name, expected_source)
        target_parent.assert_child_identity(target_name, expected_target)
        self.assert_unchanged()
        target_parent.assert_unchanged()
        if expected_target is not None:
            raise OSError(
                "refusing destructive rename over an existing directory entry: "
                f"{target_parent.child_path(target_name)}"
            )
        _rename_noreplace(
            source_name,
            target_name,
            source_fd=self.descriptor,
            target_fd=target_parent.descriptor,
        )
        os.fsync(self.descriptor)
        if target_parent.descriptor != self.descriptor:
            os.fsync(target_parent.descriptor)
        self.assert_unchanged()
        target_parent.assert_unchanged()
        if self.child_identity(source_name) is not None:
            raise OSError(f"source entry remained after rename: {self.child_path(source_name)}")
        target_parent.assert_child_identity(target_name, expected_source)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None
        self._identity = None


def _absolute_without_terminal_symlinks(path: Path) -> Path:
    destination = _trusted_prefix_normalized(path)
    with SecureDirectory(destination.parent, create=True) as parent:
        parent.assert_unchanged()
        try:
            metadata = os.stat(destination.name, dir_fd=parent.descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return destination
        if stat.S_ISLNK(metadata.st_mode):
            raise OSError(f"refusing to write through symbolic link: {destination}")
    return destination


def ensure_no_symlinks_below(root: Path, relative: Path) -> Path:
    """Resolve a lexical child while rejecting every attacker-controlled symlink."""
    base = _trusted_prefix_normalized(root)
    if relative.is_absolute() or ".." in relative.parts:
        raise OSError(f"path must stay below output directory: {relative}")
    current = base
    for part in ("", *relative.parts):
        current = current if not part else current / part
        if current.is_symlink():
            raise OSError(f"refusing to write through symbolic link: {current}")
    return current


def atomic_write_text(path: Path, content: str) -> None:
    """Publish a complete file without ever unlinking a displaced entry.

    A new destination uses a kernel-enforced no-replace rename.  An existing
    destination is exchanged atomically; the old entry is intentionally kept
    under a hidden retired name.  Retention costs disk space, but it means a
    check/rename race can never make caller data unreachable through an
    automatic cleanup path.
    """
    destination = _absolute_without_terminal_symlinks(path)
    with SecureDirectory(destination.parent, create=True) as parent:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".repo-teacher-new-{destination.name}-", dir=parent.path
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            parent.assert_unchanged()
            source_identity = parent.child_identity(temporary.name)
            if source_identity is None:
                raise OSError(f"atomic-write staging entry disappeared: {temporary}")
            target_identity = parent.child_identity(destination.name)
            if target_identity is None:
                _rename_noreplace(
                    temporary.name,
                    destination.name,
                    source_fd=parent.descriptor,
                    target_fd=parent.descriptor,
                )
                os.fsync(parent.descriptor)
                parent.assert_child_identity(destination.name, source_identity)
                return
            if target_identity[2] != stat.S_IFREG:
                raise OSError(f"refusing to replace a non-regular output: {destination}")

            _rename_exchange(
                temporary.name,
                destination.name,
                first_fd=parent.descriptor,
                second_fd=parent.descriptor,
            )
            os.fsync(parent.descriptor)
            published_identity = parent.child_identity(destination.name)
            displaced_identity = parent.child_identity(temporary.name)
            if published_identity != source_identity or displaced_identity != target_identity:
                raise OSError(
                    "atomic-write entries changed during exchange; all entries were preserved "
                    f"at {destination} and {temporary}"
                )
            retired_name = f".repo-teacher-retired-{destination.name}-{secrets.token_hex(8)}"
            _rename_noreplace(
                temporary.name,
                retired_name,
                source_fd=parent.descriptor,
                target_fd=parent.descriptor,
            )
            os.fsync(parent.descriptor)
            parent.assert_child_identity(retired_name, target_identity)
        except BaseException as error:
            # Never unlink by name here.  A concurrent actor may have replaced
            # the temporary entry after the last identity check.  Leaving the
            # object reachable is the only proof-preserving failure behavior.
            if temporary.exists():
                raise OSError(
                    "atomic write failed; preserved staging/displaced entry at "
                    f"{temporary}: {error}"
                ) from error
            raise


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _artifact_relative_path(value: str) -> Path:
    candidate = Path(value)
    if (
        not value
        or candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.parts[0].startswith(".")
        or any(not part or part in {".", ".."} for part in candidate.parts)
    ):
        raise ValueError(f"unsafe generation artifact path: {value!r}")
    return candidate


def _artifact_generation_id(relative: str, content: str) -> str | None:
    if relative.endswith(".json"):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError(f"generation JSON is malformed: {relative}: {error}") from error
        if not isinstance(payload, dict):
            raise ValueError(f"generation JSON must be an object: {relative}")
        value = payload.get("generation_id")
        return value if isinstance(value, str) else None
    if relative.endswith(".html"):
        match = _HTML_GENERATION.search(content)
        return match.group("generation") if match else None
    return None


def _fsync_tree(root: Path) -> None:
    directories: list[Path] = []
    for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories.append(current_path)
        for name in [*dirs, *names]:
            candidate = current_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise OSError(f"generation contains a symbolic link: {candidate}")
            if name in names and not stat.S_ISREG(metadata.st_mode):
                raise OSError(f"generation contains a non-regular artifact: {candidate}")
    for directory in reversed(directories):
        descriptor = os.open(directory, _DIRECTORY_FLAGS)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _make_tree_read_only(root: Path) -> None:
    directories: list[Path] = []
    for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories.append(current_path)
        for name in names:
            candidate = current_path / name
            if candidate.is_symlink():
                raise OSError(f"generation contains a symbolic link: {candidate}")
            candidate.chmod(0o444)
        for name in dirs:
            candidate = current_path / name
            if candidate.is_symlink():
                raise OSError(f"generation contains a symbolic link: {candidate}")
    for directory in reversed(directories):
        directory.chmod(0o555)


def _direct_lstat(parent: SecureDirectory, name: str) -> os.stat_result | None:
    parent.child_path(name)
    parent.assert_unchanged()
    try:
        return os.stat(name, dir_fd=parent.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _read_regular_bounded(path: Path, limit: int) -> bytes:
    """Read one no-follow regular file and reject growth/replacement races."""

    if limit < 0:
        raise ValueError("negative generation artifact size")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError(
                f"generation artifact digest/size boundary mismatch: {path}"
            )
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        material = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(material) > limit
            or _entry_identity(before) != _entry_identity(after)
            or before.st_size != after.st_size
            or len(material) != after.st_size
        ):
            raise ValueError(f"generation artifact changed while being read: {path}")
        return material
    finally:
        os.close(descriptor)


class GenerationPublisher:
    """Publish a complete immutable report generation with one pointer switch.

    Artifacts never replace files from an earlier generation.  Compatibility
    entries such as ``index.html`` are stable symlinks through ``current``;
    therefore readers observe either the complete old generation or the
    complete new one, never a JSON/HTML mixture.
    """

    def __init__(self, output: Path, generation_id: str) -> None:
        if _GENERATION_ID.fullmatch(generation_id) is None:
            raise ValueError("generation_id must be 32 lowercase hexadecimal characters")
        self.output = _trusted_prefix_normalized(output)
        self.generation_id = generation_id

    def publish(
        self,
        artifacts: Mapping[str, str],
        *,
        before_switch: Callable[[], None] | None = None,
    ) -> Path:
        if not artifacts:
            raise ValueError("a generation must contain at least one artifact")
        normalized: dict[str, str] = {}
        for name, content in artifacts.items():
            relative = _artifact_relative_path(str(name)).as_posix()
            if relative == _GENERATION_MANIFEST or relative in normalized:
                raise ValueError(f"reserved or duplicate generation artifact: {relative}")
            if not isinstance(content, str):
                raise TypeError(f"generation artifact must be text: {relative}")
            embedded = _artifact_generation_id(relative, content)
            if embedded != self.generation_id:
                raise ValueError(
                    f"generation artifact has missing or mismatched generation_id: {relative}"
                )
            normalized[relative] = content

        desired_compatibility = _compatibility_entries_for(set(normalized))

        with SecureDirectory(self.output, create=True) as output:
            with SecureDirectory(
                self.output / _GENERATIONS_DIRECTORY, create=True
            ) as generations:
                if generations.child_identity(self.generation_id) is not None:
                    raise FileExistsError(
                        f"immutable generation already exists: {self.generation_id}"
                    )
                stage_name, stage_path = generations.mkdir_unique(".stage-")
                stage_identity = generations.child_identity(stage_name)
                if stage_identity is None or stage_identity[2] != stat.S_IFDIR:
                    raise OSError("generation staging directory disappeared")
                artifact_records: dict[str, dict[str, object]] = {}
                for relative, content in sorted(normalized.items()):
                    destination = stage_path / _artifact_relative_path(relative)
                    atomic_write_text(destination, content)
                    encoded = content.encode("utf-8")
                    material = _read_regular_bounded(destination, len(encoded))
                    if material.decode("utf-8") != content:
                        raise OSError(f"generation artifact readback failed: {relative}")
                    embedded = _artifact_generation_id(relative, content)
                    if embedded != self.generation_id:
                        raise ValueError(
                            f"generation artifact readback ID mismatch: {relative}"
                        )
                    artifact_records[relative] = {
                        "sha256": hashlib.sha256(material).hexdigest(),
                        "size": len(material),
                    }
                manifest = {
                    "schema": "repo-teacher-generation/v2",
                    "generation_id": self.generation_id,
                    "artifacts": artifact_records,
                }
                atomic_write_json(stage_path / _GENERATION_MANIFEST, manifest)
                _fsync_tree(stage_path)
                generations.assert_child_identity(stage_name, stage_identity)
                _rename_noreplace(
                    stage_name,
                    self.generation_id,
                    source_fd=generations.descriptor,
                    target_fd=generations.descriptor,
                )
                generation_path = generations.child_path(self.generation_id)
                _make_tree_read_only(generation_path)
                os.fsync(generations.descriptor)

            # Validate the existing compatibility namespace before switching
            # current.  It is derived from the previous generation and must
            # contain only owned links through that one pointer.
            previous_compatibility: set[str] = set()
            for name in _COMPATIBILITY_ENTRIES:
                expected = f"current/{name}"
                metadata = _direct_lstat(output, name)
                if metadata is None:
                    continue
                if not stat.S_ISLNK(metadata.st_mode):
                    raise OSError(
                        f"refusing to replace legacy or non-symlink output entry: {self.output / name}"
                    )
                if os.readlink(name, dir_fd=output.descriptor) != expected:
                    raise OSError(f"compatibility output link has an unexpected target: {name}")
                previous_compatibility.add(name)

            if before_switch is not None:
                before_switch()

            target = f"{_GENERATIONS_DIRECTORY}/{self.generation_id}"
            temporary = f".repo-teacher-current-{secrets.token_hex(8)}"
            os.symlink(target, temporary, dir_fd=output.descriptor)
            current = _direct_lstat(output, "current")
            had_previous_current = current is not None
            if current is None:
                _rename_noreplace(
                    temporary,
                    "current",
                    source_fd=output.descriptor,
                    target_fd=output.descriptor,
                )
                os.fsync(output.descriptor)
            else:
                if not stat.S_ISLNK(current.st_mode):
                    raise OSError("refusing to replace a non-symlink current generation")
                _rename_exchange(
                    temporary,
                    "current",
                    first_fd=output.descriptor,
                    second_fd=output.descriptor,
                )
                try:
                    os.fsync(output.descriptor)
                except BaseException:
                    _rename_exchange(
                        temporary,
                        "current",
                        first_fd=output.descriptor,
                        second_fd=output.descriptor,
                    )
                    os.fsync(output.descriptor)
                    raise
            try:
                _replace_compatibility_links(output, desired_compatibility)
                # An exchanged entry contains the previous current symlink.
                # Once compatibility links are closed over the new generation,
                # it is no longer part of the publication surface.
                if had_previous_current:
                    os.unlink(temporary, dir_fd=output.descriptor)
                os.fsync(output.descriptor)
            except BaseException:
                # A compatibility-link failure must not leave the new current
                # generation visible.  Restore both the pointer and the exact
                # previous compatibility set before propagating the error.
                try:
                    if had_previous_current:
                        _rename_exchange(
                            temporary,
                            "current",
                            first_fd=output.descriptor,
                            second_fd=output.descriptor,
                        )
                        os.unlink(temporary, dir_fd=output.descriptor)
                    else:
                        os.unlink("current", dir_fd=output.descriptor)
                    _replace_compatibility_links(output, previous_compatibility)
                    os.fsync(output.descriptor)
                except BaseException as rollback_error:
                    raise OSError(
                        "publication compatibility rollback failed"
                    ) from rollback_error
                raise
            return self.output / _GENERATIONS_DIRECTORY / self.generation_id


def _replace_compatibility_links(
    output: SecureDirectory, desired: set[str]
) -> None:
    """Reconcile the owned root links with one current generation."""

    for name in _COMPATIBILITY_ENTRIES:
        expected = f"current/{name}"
        metadata = _direct_lstat(output, name)
        if name not in desired:
            if metadata is not None:
                if not stat.S_ISLNK(metadata.st_mode) or os.readlink(
                    name, dir_fd=output.descriptor
                ) != expected:
                    raise OSError(
                        f"refusing to remove unowned compatibility entry: {name}"
                    )
                os.unlink(name, dir_fd=output.descriptor)
            continue
        if metadata is not None:
            if not stat.S_ISLNK(metadata.st_mode) or os.readlink(
                name, dir_fd=output.descriptor
            ) != expected:
                raise OSError(
                    f"compatibility output link has an unexpected target: {name}"
                )
            continue
        temporary = (
            f".repo-teacher-link-{name.replace('/', '-')}-{secrets.token_hex(8)}"
        )
        os.symlink(expected, temporary, dir_fd=output.descriptor)
        try:
            _rename_noreplace(
                temporary,
                name,
                source_fd=output.descriptor,
                target_fd=output.descriptor,
            )
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=output.descriptor)
            except FileNotFoundError:
                pass
            raise


def _repair_current_compatibility_links(
    output: SecureDirectory, output_path: Path
) -> None:
    """Repair the non-authoritative root view from the verified current manifest.

    A process killed after the authoritative ``current`` exchange cannot run
    the normal exception rollback.  The next writer heals the convenience
    links before doing any work, using only a fully verified current generation
    as the source of truth.
    """

    current = _direct_lstat(output, "current")
    generations = _direct_lstat(output, _GENERATIONS_DIRECTORY)
    if current is None and generations is None:
        return
    if generations is None or not stat.S_ISDIR(generations.st_mode):
        raise OSError("managed publication metadata is incomplete or unsafe")
    if current is None:
        # A first publication may have committed an unreachable immutable
        # generation and then died before installing current.  With no
        # authority to select that generation, leave it append-only and clear
        # only owned convenience links before allowing a fresh publication.
        _replace_compatibility_links(output, set())
    else:
        if not stat.S_ISLNK(current.st_mode):
            raise OSError("managed publication metadata is incomplete or unsafe")
        declared = _declared_current_artifacts(output_path)
        desired = _compatibility_entries_for(declared)
        observed = _observed_compatibility_entries(output)
        has_orphans = any(
            name.startswith((".repo-teacher-current-", ".repo-teacher-link-"))
            for name in os.listdir(output.descriptor)
        )
        if desired == observed and not has_orphans:
            return
        # The cheap manifest comparison above only detects whether repair is
        # necessary.  Never mutate from it: a repair requires full artifact
        # size/digest/generation validation through the authoritative reader.
        _, artifacts, _ = _read_verified_generation(output_path)
        _replace_compatibility_links(output, _compatibility_entries_for(artifacts))
    _remove_orphan_publication_entries(output)
    os.fsync(output.descriptor)


def _declared_current_artifacts(output: Path) -> set[str]:
    """Read the current manifest artifact names for a no-mutation fast path."""

    target_before, generation = _current_generation_target(output)
    try:
        material = _read_regular_bounded(
            generation / _GENERATION_MANIFEST, _MAX_GENERATION_MANIFEST_BYTES
        )
        manifest = json.loads(material.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"generation manifest is unreadable: {error}") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "repo-teacher-generation/v2"
        or manifest.get("generation_id") != generation.name
        or not isinstance(manifest.get("artifacts"), dict)
    ):
        raise ValueError("generation manifest is malformed")
    artifacts: set[str] = set()
    for name in manifest["artifacts"]:
        if not isinstance(name, str):
            raise ValueError("generation manifest artifact name is malformed")
        normalized = _artifact_relative_path(name).as_posix()
        if normalized != name or normalized == _GENERATION_MANIFEST:
            raise ValueError("generation manifest artifact name is malformed")
        artifacts.add(name)
    target_after, _ = _current_generation_target(output)
    if target_before != target_after:
        raise ValueError("current generation changed while it was being read")
    return artifacts


def _observed_compatibility_entries(output: SecureDirectory) -> set[str]:
    """Validate and return the currently installed convenience link names."""

    observed: set[str] = set()
    for name in _COMPATIBILITY_ENTRIES:
        metadata = _direct_lstat(output, name)
        if metadata is None:
            continue
        expected = f"current/{name}"
        if not stat.S_ISLNK(metadata.st_mode) or os.readlink(
            name, dir_fd=output.descriptor
        ) != expected:
            raise OSError(f"compatibility output link has an unexpected target: {name}")
        observed.add(name)
    return observed


def _remove_orphan_publication_entries(output: SecureDirectory) -> None:
    """Remove only well-formed private symlinks left by a killed publisher."""

    for name in os.listdir(output.descriptor):
        if not name.startswith((".repo-teacher-current-", ".repo-teacher-link-")):
            continue
        metadata = _direct_lstat(output, name)
        if metadata is None:
            continue
        if not stat.S_ISLNK(metadata.st_mode):
            raise OSError(f"publication scratch entry is unsafe: {name}")
        target = os.readlink(name, dir_fd=output.descriptor)
        current_target = target.startswith(f"{_GENERATIONS_DIRECTORY}/") and (
            _GENERATION_ID.fullmatch(
                target.removeprefix(f"{_GENERATIONS_DIRECTORY}/")
            )
            is not None
        )
        link_target = target.startswith("current/") and (
            target.removeprefix("current/") in _COMPATIBILITY_ENTRIES
        )
        if not current_target and not link_target:
            raise OSError(f"publication scratch target is unsafe: {name}")
        os.unlink(name, dir_fd=output.descriptor)


def _current_generation_target(output: Path) -> tuple[str, Path]:
    root = _trusted_prefix_normalized(output)
    current = root / "current"
    metadata = current.lstat()
    if not stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"current generation is not a symbolic link: {current}")
    target = os.readlink(current)
    expected_prefix = f"{_GENERATIONS_DIRECTORY}/"
    if not target.startswith(expected_prefix):
        raise ValueError("current generation target is outside the generation store")
    generation_id = target.removeprefix(expected_prefix)
    if _GENERATION_ID.fullmatch(generation_id) is None or "/" in generation_id:
        raise ValueError("current generation target is malformed")
    generation = root / _GENERATIONS_DIRECTORY / generation_id
    if generation.is_symlink() or not generation.is_dir():
        raise ValueError("current generation directory is unavailable or unsafe")
    return target, generation


def _read_verified_generation(
    output: Path,
) -> tuple[str, set[str], dict[str, bytes]]:
    """Read and authenticate the complete current generation against its manifest."""

    target_before, generation = _current_generation_target(output)
    manifest_path = generation / _GENERATION_MANIFEST
    try:
        manifest_material = _read_regular_bounded(
            manifest_path, _MAX_GENERATION_MANIFEST_BYTES
        )
        manifest = json.loads(manifest_material.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"generation manifest is unreadable: {error}") from error
    generation_id = generation.name
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "repo-teacher-generation/v2"
        or manifest.get("generation_id") != generation_id
        or not isinstance(manifest.get("artifacts"), dict)
    ):
        raise ValueError("generation manifest is malformed")
    declared = manifest["artifacts"]
    observed: set[str] = set()
    materials: dict[str, bytes] = {}
    for current, dirs, names in os.walk(generation, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in [*dirs, *names]:
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError(f"generation contains a symbolic link: {candidate}")
        for name in names:
            candidate = current_path / name
            relative_name = candidate.relative_to(generation).as_posix()
            if relative_name == _GENERATION_MANIFEST:
                continue
            if not candidate.is_file():
                raise ValueError(f"generation artifact is not regular: {relative_name}")
            observed.add(relative_name)
            expected = declared.get(relative_name)
            if not isinstance(expected, dict):
                raise ValueError(
                    f"generation artifact declaration is malformed: {relative_name}"
                )
            expected_digest = expected.get("sha256")
            expected_size = expected.get("size")
            if (
                not isinstance(expected_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
                or not isinstance(expected_size, int)
                or isinstance(expected_size, bool)
                or expected_size < 0
            ):
                raise ValueError(
                    f"generation artifact declaration is malformed: {relative_name}"
                )
            material = _read_regular_bounded(candidate, expected_size)
            digest = hashlib.sha256(material).hexdigest()
            if len(material) != expected_size or not hmac.compare_digest(
                digest, expected_digest
            ):
                raise ValueError(f"generation artifact digest mismatch: {relative_name}")
            materials[relative_name] = material
            if relative_name.endswith((".json", ".html")):
                try:
                    embedded = _artifact_generation_id(
                        relative_name, material.decode("utf-8")
                    )
                except (UnicodeDecodeError, ValueError) as error:
                    raise ValueError(
                        f"generation artifact metadata is unreadable: {relative_name}: {error}"
                    ) from error
                if embedded != generation_id:
                    raise ValueError(
                        f"generation artifact ID mismatch: {relative_name}"
                    )
    if observed != set(declared):
        raise ValueError("generation manifest artifact set does not match the directory")
    target_after, _ = _current_generation_target(output)
    if target_before != target_after:
        raise ValueError("current generation changed while it was being read")
    return generation_id, observed, materials


def read_published_json(
    output: Path, relative: str = "index.json"
) -> VerifiedPublishedJson:
    """Read one JSON artifact only after validating its whole generation."""

    relative_name = _artifact_relative_path(relative).as_posix()
    generation_id, observed, materials = _read_verified_generation(output)
    if relative_name not in observed or not relative_name.endswith(".json"):
        raise ValueError(f"JSON artifact is not part of the current generation: {relative_name}")
    try:
        payload = json.loads(materials[relative_name].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"published JSON is unreadable: {relative_name}: {error}") from error
    if not isinstance(payload, dict) or payload.get("generation_id") != generation_id:
        raise ValueError(f"published JSON generation ID mismatch: {relative_name}")
    return VerifiedPublishedJson(
        payload,
        token=_VERIFIED_PUBLICATION,
        output=_trusted_prefix_normalized(output),
        relative=relative_name,
        generation_id=generation_id,
    )


def read_json_path(path: Path) -> dict[str, Any]:
    """Read a standalone JSON file or verify it through a managed generation."""

    lexical = Path(os.path.abspath(path.expanduser()))
    for candidate in (lexical.parent, *lexical.parents):
        if (candidate / _GENERATIONS_DIRECTORY).is_dir() and (candidate / "current").is_symlink():
            try:
                relative_path = lexical.relative_to(candidate)
            except ValueError:
                continue
            parts = relative_path.parts
            if parts and parts[0] == "current":
                relative_path = Path(*parts[1:])
            elif len(parts) >= 3 and parts[0] == _GENERATIONS_DIRECTORY:
                current_target, _ = _current_generation_target(candidate)
                current_generation_id = current_target.removeprefix(
                    f"{_GENERATIONS_DIRECTORY}/"
                )
                if parts[1] != current_generation_id:
                    raise ValueError(
                        "immutable artifact is not the current generation"
                    )
                relative_path = Path(*parts[2:])
            relative = relative_path.as_posix()
            return read_published_json(candidate, relative)
    value = json.loads(lexical.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


class OutputLock(AbstractContextManager["OutputLock"]):
    """A fail-fast advisory lock backed by a permanent regular lockfile.

    The name is never unlinked.  Kernel ``flock`` ownership is tied to the open
    descriptor, so a crashed process releases the lock without a stale-file
    recovery guess or PID liveness heuristic.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = _absolute_without_terminal_symlinks(directory)
        self.path = self.directory / ".repo-teacher.lock"
        self._descriptor: int | None = None
        self._parent: SecureDirectory | None = None
        self._directory_locked = False

    def __enter__(self) -> "OutputLock":
        self._parent = SecureDirectory(self.directory, create=True)
        self._parent.__enter__()
        try:
            fcntl.flock(
                self._parent.descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
            self._directory_locked = True
            self._descriptor = os.open(
                self.path.name,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=self._parent.descriptor,
            )
        except BlockingIOError as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise OSError(f"output is locked by another writer: {self.path}") from error
        except BaseException as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise
        opened = os.fstat(self._descriptor)
        if not stat.S_ISREG(opened.st_mode):
            self.__exit__(None, None, None)
            raise OSError(f"output lock is not a regular file: {self.path}")
        expected = _entry_identity(opened)
        try:
            self._parent.assert_child_identity(self.path.name, expected)
            fcntl.flock(self._descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._parent.assert_child_identity(self.path.name, expected)
        except BlockingIOError as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise OSError(f"output is locked by another writer: {self.path}") from error
        except BaseException as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise
        try:
            _repair_current_compatibility_links(self._parent, self.directory)
        except BaseException as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._descriptor is not None:
            try:
                fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            finally:
                os.close(self._descriptor)
            self._descriptor = None
        if self._parent is not None:
            if self._directory_locked:
                fcntl.flock(self._parent.descriptor, fcntl.LOCK_UN)
                self._directory_locked = False
            self._parent.__exit__(exc_type, exc, traceback)
            self._parent = None
