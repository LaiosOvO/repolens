"""Deterministic engineering-module classification for report evidence."""

from __future__ import annotations

from .paths import repo_path_parts


def module_view_path(path: object) -> str | None:
    parts = repo_path_parts(path)
    if len(parts) < 2:
        return None
    directories = parts[:-1]
    if directories[0].casefold() in {"packages", "apps", "services"}:
        depth = min(2, len(directories))
    else:
        depth = min(3, len(directories))
    return "/".join(directories[:depth])


def module_view_category(path: str) -> str:
    path_parts = repo_path_parts(path)
    parts = {part.casefold() for part in path_parts}
    filename = path_parts[-1].casefold() if path_parts else ""
    if any(part.startswith(".") for part in path_parts):
        return "engineering-support"
    if parts & {
        "artifacts",
        "artifact",
        "generated",
        "generated-source",
        "reverse-source",
        "decompiled",
        "unpacked",
        "dist",
        "coverage",
        "cache",
        "caches",
    }:
        return "generated-or-reference"
    if (
        parts & {"test", "tests", "fixtures"}
        or ".test." in filename
        or filename.endswith("_test.go")
        or filename.endswith("_test.py")
    ):
        return "testing"
    if parts & {
        "example",
        "examples",
        "demo",
        "demos",
        "sample",
        "samples",
        "assets",
        "sandbox-projects",
    } or any(part.endswith(("-assets", "_assets")) for part in parts):
        return "examples"
    if parts & {"doc", "docs", "spec", "specs", "changelog", "changes"}:
        return "documentation"
    if parts & {"script", "scripts", ".github", "build", "tools"}:
        return "engineering-support"
    return "product-implementation"
