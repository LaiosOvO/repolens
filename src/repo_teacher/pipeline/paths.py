"""Repository-relative path contracts shared by evidence stages."""

from __future__ import annotations

from typing import Sequence


def repo_path_parts(value: object) -> tuple[str, ...]:
    """Return normalized safe path parts or an empty tuple for unsafe input."""

    if not isinstance(value, str):
        return ()
    if value.startswith(("/", "\\")):
        return ()
    raw_parts = value.replace("\\", "/").split("/")
    if ".." in raw_parts:
        return ()
    return tuple(part for part in raw_parts if part and part != ".")


def path_is_within_modules(path: object, module_paths: Sequence[str]) -> bool:
    """Match by path components; never by substring or regular expression."""

    path_parts = repo_path_parts(path)
    if not path_parts:
        return False
    for module_path in module_paths:
        module_parts = repo_path_parts(module_path)
        if module_parts and path_parts[: len(module_parts)] == module_parts:
            return True
    return False


def canonical_source_slice_path(
    value: object, allowed_paths: Sequence[str] | set[str]
) -> str | None:
    """Resolve an isolated ``source-slice`` path to an exact repository path.

    Model processes run inside a copied source slice, so some providers return
    that physical absolute path.  The boundary is intentionally narrow: only
    the exact path components after a real ``source-slice`` directory may be
    recovered, and the recovered value must already exist in the packet's
    closed allow-list.  Arbitrary absolute-path suffix matching remains
    forbidden.
    """

    allowed = set(allowed_paths)
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/")
    if normalized in allowed:
        return normalized
    parts = tuple(part for part in normalized.split("/") if part and part != ".")
    try:
        marker_index = parts.index("source-slice")
    except ValueError:
        return None
    candidate_parts = parts[marker_index + 1 :]
    if not candidate_parts or ".." in candidate_parts:
        return None
    candidate = "/".join(candidate_parts)
    return candidate if candidate in allowed else None
