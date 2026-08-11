from __future__ import annotations

import subprocess
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .models import ProjectSnapshot


def _git(path: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _detect_license(path: Path) -> str | None:
    candidates: list[Path] = []
    for item in path.iterdir():
        if not item.name.lower().startswith(("license", "copying")):
            continue
        try:
            metadata = item.stat(follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISREG(metadata.st_mode):
            candidates.append(item)
    candidates.sort()
    if not candidates:
        return None
    try:
        descriptor = os.open(
            candidates[0],
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                return "Unknown"
            text = stream.read(20_000).decode("utf-8", errors="ignore").lower()
    except OSError:
        return "Unknown"
    markers = (
        ("GNU AFFERO GENERAL PUBLIC LICENSE", "AGPL"),
        ("GNU GENERAL PUBLIC LICENSE", "GPL"),
        ("apache license", "Apache-2.0"),
        ("mit license", "MIT"),
        ("mozilla public license", "MPL"),
        ("redistribution and use in source and binary forms", "BSD"),
    )
    for marker, label in markers:
        if marker.lower() in text:
            return label
    return "Unknown"


def _sanitize_remote(value: str | None) -> str | None:
    """Return a credential-free remote suitable for persistent reports.

    Git accepts both URL remotes and SCP-like ``user@host:path`` remotes.  The
    text before ``@`` is never needed by Repo Teacher, so it is deliberately
    removed even when it only contains the conventional ``git`` user.  Query
    strings and fragments are also transport metadata and may contain tokens.
    """

    if not value:
        return value
    value = value.strip()
    if "://" not in value:
        sanitized = value.split("#", 1)[0].split("?", 1)[0]
        if "@" in sanitized:
            user, host_path = sanitized.rsplit("@", 1)
            # Conventional transport-only SSH users are not credentials and
            # retaining them preserves a usable canonical Git remote.  Any
            # other userinfo is removed fail-closed because it may be a token.
            sanitized = (
                sanitized if user.lower() in {"git", "hg", "ssh"} else host_path
            )
        return sanitized or None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        if not hostname:
            return None
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = f"{hostname}:{parsed.port}" if parsed.port is not None else hostname
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except (TypeError, ValueError):
        return None


def capture_snapshot(path: Path) -> ProjectSnapshot:
    root = path.expanduser().resolve()
    git_root_value = _git(root, "rev-parse", "--show-toplevel")
    is_git = git_root_value is not None
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") if is_git else None
    if branch == "HEAD":
        branch = None
    status = _git(root, "status", "--porcelain", "--untracked-files=normal") if is_git else None
    return ProjectSnapshot(
        name=root.name,
        path=str(root),
        git_root=str(Path(git_root_value).resolve()) if git_root_value else None,
        is_git=is_git,
        commit=_git(root, "rev-parse", "HEAD") if is_git else None,
        branch=branch,
        dirty=(None if status is None else bool(status)) if is_git else None,
        remote=_sanitize_remote(_git(root, "remote", "get-url", "origin")) if is_git else None,
        license=_detect_license(root),
        analyzed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
