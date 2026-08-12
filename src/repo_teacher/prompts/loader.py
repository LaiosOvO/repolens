"""Load packaged prompts without coupling them to command handlers."""

from __future__ import annotations

from importlib.resources import files
import json
from string import Template
from collections.abc import Mapping


def render_prompt(name: str, **values: object) -> str:
    """Render a versioned packaged prompt with strict named placeholders."""

    resource = files("repo_teacher.prompts").joinpath(name)
    template = Template(resource.read_text(encoding="utf-8"))
    return template.substitute({key: str(value) for key, value in values.items()})


def compose_provider_prompt(
    prompt: str,
    provider: str,
    sections: Mapping[str, object],
) -> str:
    """Attach bounded local evidence for providers without filesystem access."""

    if provider == "codex":
        return prompt
    rendered = [prompt]
    for title, payload in sections.items():
        rendered.append(
            render_prompt(
                "provider-evidence-section-v1.md",
                title=title,
                payload=json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        )
    return "\n\n".join(rendered)
