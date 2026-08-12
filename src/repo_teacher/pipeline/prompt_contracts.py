"""Versioned prompt adapters for repository report model stages."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..agents import load_agent_spec
from ..prompts import render_prompt
from ..providers import decode_json_object
from ..schemas import inventory_json_schema
from .serialization import json_artifact as _json_artifact

def _model_prompt(pack_path: Path, source: Path) -> str:
    """Compatibility wrapper around the packaged full-report prompt."""

    return render_prompt(
        "human-report-full-v1.md",
        pack_path=pack_path,
        source=source,
        schema_path=pack_path.with_name("human-report-schema.json"),
    )

def _inventory_json_schema() -> dict[str, object]:
    """Compatibility wrapper for callers that imported the former CLI helper."""

    return inventory_json_schema()

def _inventory_prompt(pack_path: Path, source: Path) -> str:
    agent = load_agent_spec("business-capability-analyst")
    if not agent.prompt:
        raise ValueError("business capability agent has no prompt contract")
    return render_prompt(
        agent.prompt,
        pack_path=pack_path,
        source=source,
    )

def _inventory_shard_prompt(
    pack_path: Path,
    source: Path,
    module_paths: Sequence[str],
) -> str:
    return render_prompt(
        "inventory-shard-v1.md",
        pack_path=pack_path,
        source=source,
        module_paths=", ".join(module_paths),
    )

def _project_overview_prompt(
    pack_path: Path,
    source: Path,
    capability_ids: Sequence[str],
) -> str:
    agent = load_agent_spec("project-context-analyzer")
    if not agent.prompt:
        raise ValueError("project context agent has no prompt contract")
    return render_prompt(
        agent.prompt,
        pack_path=pack_path,
        source=source,
        capability_ids=", ".join(capability_ids),
    )

def _chapter_batch_prompt(
    pack_path: Path,
    inventory_path: Path,
    source: Path,
    capability_ids: Sequence[str],
) -> str:
    agent = load_agent_spec("chapter-writer")
    if not agent.prompt:
        raise ValueError("chapter writer agent has no prompt contract")
    uml_skill_path = Path(__file__).resolve().parents[2] / ".agents/skills/uml/SKILL.md"
    return render_prompt(
        agent.prompt,
        pack_path=pack_path,
        inventory_path=inventory_path,
        source=source,
        capability_ids=", ".join(capability_ids),
        uml_skill_path=uml_skill_path,
    )

def _inventory_merge_prompt(inventory_path: Path) -> str:
    return render_prompt(
        "inventory-merge-v1.md",
        inventory_path=inventory_path,
    )


def inventory_review_prompt(
    pack_path: Path,
    inventory_path: Path,
    source: Path,
    capability_ids: Sequence[str],
) -> str:
    agent = load_agent_spec("capability-reviewer")
    if not agent.prompt:
        raise ValueError("capability reviewer has no prompt contract")
    return render_prompt(
        agent.prompt,
        pack_path=pack_path,
        inventory_path=inventory_path,
        source=source,
        capability_ids=", ".join(capability_ids),
    )


def human_readability_review_prompt(
    pack_path: Path,
    inventory_path: Path,
    report_path: Path,
    source: Path,
    capability_ids: Sequence[str],
) -> str:
    agent = load_agent_spec("human-report-reviewer")
    if not agent.prompt:
        raise ValueError("human report reviewer has no prompt contract")
    return render_prompt(
        agent.prompt,
        pack_path=pack_path,
        inventory_path=inventory_path,
        report_path=report_path,
        source=source,
        capability_ids=", ".join(capability_ids),
    )

def _decode_json_object(content: object) -> dict[str, object]:
    """Compatibility wrapper for callers of the former CLI helper."""

    return decode_json_object(content)
