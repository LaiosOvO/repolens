"""Content-addressed identity for semantic pipeline caches."""

from __future__ import annotations

import hashlib
import json
import os
from importlib.resources import files
from typing import Iterable, Mapping

from ..human_report import human_report_json_schema
from ..schemas import (
    chapter_batch_json_schema,
    inventory_group_json_schema,
    inventory_json_schema,
    inventory_semantic_review_json_schema,
    human_readability_review_json_schema,
    persisted_inventory_json_schema,
    project_overview_json_schema,
)


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def packaged_contract_digests() -> dict[str, str]:
    """Hash output-affecting implementation, Agent, Prompt and Schema resources."""

    result: dict[str, str] = {}
    for package, suffix in (
        ("repo_teacher.agents", ".md"),
        ("repo_teacher.prompts", ".md"),
        ("repo_teacher.pipeline", ".py"),
        ("repo_teacher.providers", ".py"),
        ("repo_teacher.renderers", ".py"),
        ("repo_teacher.schemas", ".py"),
    ):
        root = files(package)
        for resource in sorted(root.iterdir(), key=lambda item: item.name):
            if resource.name.endswith(suffix):
                result[f"{package}:{resource.name}"] = _digest_bytes(
                    resource.read_bytes()
                )
    package_root = files("repo_teacher")
    for name in ("capability_graph.py", "human_report.py", "report.py"):
        resource = package_root.joinpath(name)
        result[f"repo_teacher:{name}"] = _digest_bytes(resource.read_bytes())
    for name, schema in (
        ("inventory-model", inventory_json_schema()),
        ("inventory-persisted", persisted_inventory_json_schema()),
        ("inventory-group", inventory_group_json_schema()),
        (
            "inventory-semantic-review",
            inventory_semantic_review_json_schema(
                ["capability-contract-sentinel"], ["candidate-contract-sentinel"]
            ),
        ),
        ("project-overview", project_overview_json_schema(1)),
        ("chapter-model", chapter_batch_json_schema(1)),
        ("human-report", human_report_json_schema()),
        (
            "human-readability-review",
            human_readability_review_json_schema(["capability-contract-sentinel"]),
        ),
    ):
        result[f"schema:{name}"] = _digest_bytes(
            json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
    return result


def provider_model_identity(provider: str) -> dict[str, object]:
    """Return output-affecting provider settings without credentials."""

    if provider == "codex":
        return {
            "provider": "codex",
            "model": os.environ.get("REPO_TEACHER_CODEX_MODEL", "gpt-5.4").strip(),
            "reasoning_effort": os.environ.get(
                "REPO_TEACHER_CODEX_REASONING_EFFORT", "low"
            ).strip(),
            "inventory_model": os.environ.get(
                "REPO_TEACHER_CODEX_INVENTORY_MODEL", "gpt-5.4-mini"
            ).strip(),
            "inventory_reasoning_effort": os.environ.get(
                "REPO_TEACHER_CODEX_INVENTORY_REASONING_EFFORT", "low"
            ).strip(),
        }
    if provider == "opencode":
        return {
            "provider": "opencode",
            "model": os.environ.get(
                "REPO_TEACHER_OPENCODE_MODEL",
                "openrouter/deepseek/deepseek-v4-flash",
            ).strip(),
        }
    if provider == "deepseek":
        return {
            "provider": "deepseek",
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip(),
            "base_url": os.environ.get(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).rstrip("/"),
            "temperature": [0.1, 0.0],
            "max_tokens": 8192,
            "max_attempts": 2,
        }
    raise ValueError(f"unsupported narrative provider: {provider}")


def provider_stage_identity(provider: str, *, inventory: bool = False) -> dict[str, object]:
    """Return provider settings for one model stage without unrelated routes."""

    identity = provider_model_identity(provider)
    if provider == "codex":
        if inventory:
            return {
                "provider": "codex",
                "model": identity["inventory_model"],
                "reasoning_effort": identity["inventory_reasoning_effort"],
            }
        return {
            "provider": "codex",
            "model": identity["model"],
            "reasoning_effort": identity["reasoning_effort"],
        }
    return identity


def contract_digest_subset(
    available: Mapping[str, str],
    selected_keys: Iterable[str],
) -> dict[str, str]:
    """Return a stable subset of packaged contract digests for one stage."""

    result: dict[str, str] = {}
    for key in selected_keys:
        if key not in available:
            raise KeyError(f"missing contract digest: {key}")
        result[str(key)] = str(available[key])
    return result


def build_run_identity(
    *,
    source: str,
    commit: object,
    analysis_fingerprint: object,
    source_manifest_sha256: object,
    indexed_content_sha256: str,
    provider: str,
    inventory_sha256: str | None,
    synthesis_contract: str,
    contract_digests: Mapping[str, str] | None = None,
    provider_config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build an auditable identity whose digest is safe for semantic cache reuse.

    ``source_manifest_sha256`` includes filesystem metadata and is retained for
    diagnostics, but it is deliberately excluded from the semantic cache key.
    The indexed path/content digest is the authoritative source input: touching
    an unchanged checkout must not spend another full model run, while any
    indexed content change still invalidates the cache.
    """

    identity = {
        "schema_version": "repolens-run-identity/v1",
        "source": source,
        "commit": commit,
        "analysis_fingerprint": analysis_fingerprint,
        "source_manifest_sha256": source_manifest_sha256,
        "indexed_content_sha256": indexed_content_sha256,
        "inventory_sha256": inventory_sha256,
        "synthesis_contract": synthesis_contract,
        "provider": dict(provider_config or provider_model_identity(provider)),
        "contracts": dict(contract_digests or packaged_contract_digests()),
    }
    cache_identity = dict(identity)
    cache_identity.pop("source_manifest_sha256", None)
    encoded = json.dumps(
        cache_identity, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    identity["identity_sha256"] = _digest_bytes(encoded)
    return identity


def build_workspace_root_identity(
    *,
    source: str,
    indexed_content_sha256: str,
    provider: str,
) -> dict[str, object]:
    """Build a stable per-repository cache root identity."""

    identity = {
        "schema_version": "repolens-workspace-root-identity/v1",
        "source": source,
        "indexed_content_sha256": indexed_content_sha256,
        "provider": provider,
    }
    encoded = json.dumps(
        identity, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    identity["identity_sha256"] = _digest_bytes(encoded)
    return identity


def build_stage_cache_identity(
    *,
    stage: str,
    source: str,
    indexed_content_sha256: str,
    packet_sha256: str | None = None,
    inventory_sha256: str | None = None,
    prompt_sha256: str | None = None,
    schema_sha256: str | None = None,
    provider_config: Mapping[str, object],
    contract_digests: Mapping[str, str],
) -> dict[str, object]:
    """Build an auditable cache identity for one pipeline stage."""

    identity = {
        "schema_version": "repolens-stage-cache-identity/v1",
        "stage": stage,
        "source": source,
        "indexed_content_sha256": indexed_content_sha256,
        "packet_sha256": packet_sha256,
        "inventory_sha256": inventory_sha256,
        "prompt_sha256": prompt_sha256,
        "schema_sha256": schema_sha256,
        "provider": dict(provider_config),
        "contracts": dict(contract_digests),
    }
    encoded = json.dumps(
        identity, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    identity["identity_sha256"] = _digest_bytes(encoded)
    return identity
