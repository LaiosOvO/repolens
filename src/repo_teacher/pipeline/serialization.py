"""Canonical JSON serialization shared by pipeline stages.

This module has no knowledge of prompts, providers, or business semantics.
"""

from __future__ import annotations

import json


def json_artifact(payload: dict[str, object]) -> str:
    """Return the stable UTF-8 JSON representation used for persisted artifacts."""

    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
