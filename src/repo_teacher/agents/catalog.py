"""Minimal reader for packaged Markdown agent specifications."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True, slots=True)
class AgentSpec:
    name: str
    display_name: str
    stage: str
    instructions: str
    contract_version: str
    prompt: str | None = None
    schema: str | None = None


def load_agent_spec(name: str) -> AgentSpec:
    """Load one agent role by exact name; never discover roles by source text."""

    if not name or any(character in name for character in ("/", "\\", "..")):
        raise ValueError("agent name must be a simple packaged identifier")
    text = files("repo_teacher.agents").joinpath(f"{name}.md").read_text(
        encoding="utf-8"
    )
    lines = text.splitlines()
    if len(lines) < 4 or lines[0].strip() != "---":
        raise ValueError(f"agent spec has no front matter: {name}")
    metadata: dict[str, str] = {}
    closing = None
    for position, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing = position
            break
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"invalid agent metadata line: {name}: {line}")
        metadata[key.strip()] = value.strip()
    if closing is None:
        raise ValueError(f"agent spec front matter is not closed: {name}")
    if metadata.get("name") != name or not metadata.get("stage"):
        raise ValueError(f"agent spec identity mismatch: {name}")
    instructions = "\n".join(lines[closing + 1 :]).strip()
    if not instructions:
        raise ValueError(f"agent spec instructions are empty: {name}")
    return AgentSpec(
        name=name,
        display_name=metadata.get("display_name", name),
        stage=metadata["stage"],
        contract_version=metadata.get("contract_version", "repolens-agent/v1"),
        prompt=metadata.get("prompt"),
        schema=metadata.get("schema"),
        instructions=instructions,
    )
