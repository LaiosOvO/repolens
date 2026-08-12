"""Business-capability and human-report synthesis pipeline.

This module owns model-stage ordering, bounded concurrency, cache reuse,
evidence closure and cross-stage validation.  It contains no CLI parsing.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

from ..human_report import human_report_json_schema
from ..pipeline.inventory import CapabilityInventoryStage, InventoryStageRequest
from ..prompts import compose_provider_prompt
from ..prompts import render_prompt
from ..providers import (
    CallableStructuredModelProvider,
    run_structured_json,
)
from ..schemas import (
    chapter_batch_json_schema,
    inventory_group_json_schema,
    project_overview_json_schema,
)
from ..persistence import atomic_write_text, read_json_path
from .codegraph import (
    _augment_pack_with_codegraph_context,
    _codegraph_domain_context,
    _codegraph_explore_domain,
)
from .cache_identity import build_run_identity
from .cache_identity import (
    build_stage_cache_identity,
    build_workspace_root_identity,
    contract_digest_subset,
    packaged_contract_digests,
    provider_stage_identity,
)
from .evidence_packets import (
    _add_project_navigation,
    _build_chapter_batch_pack,
    _build_global_business_inventory_pack,
    _build_inventory_shard_pack,
    _indexed_file_hashes,
    _materialize_source_slice,
    _source_paths,
    _stage_model_json,
)
from .inventory_contracts import (
    _canonicalize_inventory_payload,
    _inventory_module_shards,
    _merge_inventory_shards,
    _require_inventory_against_pack,
    _require_inventory_scope,
)
from .grouping import _group_inventory_for_humans
from .linear_pipeline import LEGACY_INVENTORY_STAGES, LinearStageArtifacts
from .partitioning import (
    INVENTORY_SHARD_BYTE_BUDGET,
    INVENTORY_SHARD_TOKEN_BUDGET,
    INVENTORY_SOURCE_EXCERPT_BUDGET,
    expand_oversized_module_scopes,
    require_packet_budget,
    split_shards_by_budget,
)
from .prompt_contracts import (
    _chapter_batch_prompt,
    _decode_json_object,
    _inventory_json_schema,
    _inventory_prompt,
    _inventory_shard_prompt,
    _json_artifact,
    _model_prompt,
    _project_overview_prompt,
)
from .report_contracts import (
    _attach_source_excerpts,
    _chunk_capabilities,
    _close_chapter_evidence,
    _inventory_from_manifest,
    _normalize_project_overview,
    _require_source_ref_quality,
)
from .semantic_review import run_inventory_semantic_review
from .timeouts import remaining_model_timeout as _remaining_model_timeout

REPORT_SYNTHESIS_CONTRACT_VERSION = "direct-human-report-v5"
# The production pipeline is linear. Semantic review is one terminal quality
# gate; it never invokes an earlier model stage or starts a review/repair loop.
SEMANTIC_REVIEW_CALLS_PER_RUN = 1

_INVENTORY_STAGE_CONTRACT_KEYS = (
    "repo_teacher.agents:business-capability-analyst.md",
    "repo_teacher.prompts:inventory-global-v1.md",
    "repo_teacher.prompts:inventory-shard-v1.md",
    "repo_teacher.prompts:inventory-shard-closure-repair-v1.md",
    "repo_teacher.prompts:provider-evidence-section-v1.md",
    "schema:inventory-model",
)
_GROUPING_STAGE_CONTRACT_KEYS = (
    "repo_teacher.prompts:inventory-grouping-v1.md",
    "repo_teacher.prompts:provider-evidence-section-v1.md",
    "schema:inventory-group",
)
_OVERVIEW_STAGE_CONTRACT_KEYS = (
    "repo_teacher.agents:project-context-analyzer.md",
    "repo_teacher.prompts:project-overview-v1.md",
    "repo_teacher.prompts:provider-evidence-section-v1.md",
    "schema:project-overview",
)
_CHAPTER_STAGE_CONTRACT_KEYS = (
    "repo_teacher.agents:chapter-writer.md",
    "repo_teacher.prompts:chapter-batch-v1.md",
    "repo_teacher.prompts:provider-evidence-section-v1.md",
    "schema:chapter-model",
)


def _public_inventory_payload(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result.pop("grouping_membership", None)
    result.pop("excluded_candidate_ids", None)
    result.pop("grouping_attachments", None)
    return result




















def _provider_prompt(
    prompt: str,
    provider: str,
    **json_sections: object,
) -> str:
    """Compatibility wrapper around provider-specific prompt packaging."""

    return compose_provider_prompt(prompt, provider, json_sections)


def _run_codex_json(
    *,
    source: Path,
    workspace: Path,
    schema: dict[str, object],
    prompt: str,
    timeout: int,
    stage_slug: str,
    progress_label: str,
    provider: str = "codex",
) -> dict[str, object]:
    """Compatibility wrapper around the provider runtime adapter."""

    return run_structured_json(
        source=source,
        workspace=workspace,
        schema=schema,
        prompt=prompt,
        timeout=timeout,
        stage_slug=stage_slug,
        progress_label=progress_label,
        provider=provider,
    )


def synthesize_direct_human_report(
    source: Path,
    pack: dict[str, object],
    workspace: Path,
    timeout: int,
    _inventory_arg: str | None = None,
    provider: str = "codex",
) -> dict[str, object]:
    """Generate the complete human report in one schema-constrained call.

    The report command deliberately has no inventory/grouping/review repair
    sub-pipeline.  CodeGraph and the canonical index are evidence inputs; the
    single output already contains project identity, ordered business
    capabilities, implementation mechanisms and engineering organization.
    """

    workspace.mkdir(parents=True, exist_ok=True)
    # Repomix-style bounded context: keep the whole-repository topology, but
    # send only the highest-value canonical hints/evidence and bounded source
    # excerpts.  CodeGraph remains the structural truth; it is not an
    # orchestration graph and the model is never handed an unbounded repo dump.
    direct_pack: dict[str, object] | None = None
    packet_bytes = 0
    for hint_limit, excerpt_budget in (
        (160, 100_000),
        (120, 80_000),
        (80, 50_000),
        (50, 35_000),
        (30, 20_000),
    ):
        candidate = _build_global_business_inventory_pack(
            pack,
            hint_limit=hint_limit,
        )
        candidate = _add_project_navigation(candidate, pack)
        graph = candidate.get("capability_graph")
        if isinstance(graph, dict):
            selected_feature_ids = {
                str(item["id"])
                for item in candidate.get("feature_hints", [])
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
            }
            candidate["capability_graph"] = _bounded_direct_report_graph(
                graph,
                selected_feature_ids=selected_feature_ids,
                hint_limit=hint_limit,
            )
            graph = candidate["capability_graph"]
            graph_paths = _source_paths(graph)
            evidence = [
                item
                for item in candidate.get("evidence", [])
                if isinstance(item, dict)
            ]
            evidence_paths = {
                str(item.get("path"))
                for item in evidence
                if isinstance(item.get("path"), str)
            }
            # Every path the bounded graph exposes gets one canonical anchor.
            # This lets the model cite a central call-chain path that was not
            # among the top static feature hints without inventing IDs.
            anchor_budget = max(24, hint_limit * 2)
            for item in pack.get("evidence", []):
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if (
                    not isinstance(path, str)
                    or path not in graph_paths
                    or path in evidence_paths
                ):
                    continue
                evidence.append(copy.deepcopy(item))
                evidence_paths.add(path)
                if len(evidence_paths) >= anchor_budget:
                    break
            candidate["evidence"] = evidence
            scope = candidate.get("scope")
            if isinstance(scope, dict):
                scope["allowed_source_paths"] = sorted(
                    {
                        path
                        for path in scope.get("allowed_source_paths", [])
                        if isinstance(path, str)
                    }
                    | graph_paths
                )
                scope["evidence_ids"] = sorted(
                    str(item["id"])
                    for item in evidence
                    if isinstance(item.get("id"), str)
                )
                mechanism_ids = scope.get("mechanism_cluster_ids")
                if isinstance(mechanism_ids, list):
                    scope["mechanism_cluster_ids"] = mechanism_ids[:24]
                feature_ids = scope.get("feature_ids")
                if isinstance(feature_ids, list):
                    scope["feature_ids"] = feature_ids[:hint_limit]
                candidate_ids = scope.get("capability_candidate_ids")
                if isinstance(candidate_ids, list):
                    scope["capability_candidate_ids"] = candidate_ids[:24]
        product_navigation = candidate.get("product_navigation")
        if isinstance(product_navigation, list):
            trimmed_navigation: list[dict[str, object]] = []
            for item in product_navigation[:2]:
                if not isinstance(item, dict):
                    continue
                entry = copy.deepcopy(item)
                snippet = entry.get("snippet")
                if isinstance(snippet, str) and len(snippet) > 4_000:
                    entry["snippet"] = snippet[:4_000]
                line_end = entry.get("line_end")
                if isinstance(line_end, int):
                    entry["line_end"] = min(line_end, 200)
                trimmed_navigation.append(entry)
            candidate["product_navigation"] = trimmed_navigation
        modules = candidate.get("modules")
        if isinstance(modules, list):
            candidate["modules"] = modules[:48]
        repository_modules = candidate.get("repository_modules")
        if isinstance(repository_modules, list):
            candidate["repository_modules"] = repository_modules[:24]
        module_dependencies = candidate.get("module_view_dependencies")
        if isinstance(module_dependencies, list):
            candidate["module_view_dependencies"] = module_dependencies[:48]
        reading_path = candidate.get("reading_path")
        if isinstance(reading_path, list):
            candidate["reading_path"] = reading_path[:4]
        candidate = _attach_source_excerpts(
            candidate,
            source,
            character_budget=excerpt_budget,
        )
        packet_bytes = len(_json_artifact(candidate).encode("utf-8"))
        if packet_bytes <= 640_000:
            direct_pack = candidate
            break
    if direct_pack is None:
        raise ValueError(
            f"bounded human-report evidence packet exceeds 640000 bytes: {packet_bytes}"
        )
    direct_pack["packet_budget"] = {
        "strategy": "graph-first-bounded-context",
        "max_bytes": 640_000,
        "actual_bytes_before_metadata": packet_bytes,
        "whole_repository_source_dump": False,
    }
    scope = direct_pack.get("scope")
    allowed_source_paths = [
        item
        for item in (
            scope.get("allowed_source_paths", [])
            if isinstance(scope, dict)
            else []
        )
        if isinstance(item, str) and item
    ]
    if not allowed_source_paths:
        raise ValueError("bounded human-report packet has no allowed source paths")
    # Prompt instructions alone are not a security or performance boundary.
    # Give the model a physical copy containing only the packet's allowed
    # source files, so it cannot silently rescan the whole repository.
    model_source = _materialize_source_slice(
        source,
        workspace / "direct-source",
        allowed_source_paths,
        _indexed_file_hashes(pack),
    )
    pack_path = workspace / "analysis-pack-direct.json"
    schema_path = workspace / "human-report-schema.json"
    result_path = workspace / "human-report-direct.json"
    identity_path = workspace / "human-report-direct.identity.json"
    schema = human_report_json_schema()
    atomic_write_text(pack_path, _json_artifact(direct_pack))
    atomic_write_text(schema_path, _json_artifact(schema))
    stable_prompt = _model_prompt(Path("/PACK.json"), Path("/SOURCE"))
    content_identity = {
        "schema_version": "repolens-direct-report-cache/v1",
        "contract": REPORT_SYNTHESIS_CONTRACT_VERSION,
        "packet_sha256": _packet_sha256(direct_pack),
        "prompt_sha256": hashlib.sha256(stable_prompt.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(
            _json_artifact(schema).encode("utf-8")
        ).hexdigest(),
        "provider": provider,
    }
    content_identity["identity_sha256"] = hashlib.sha256(
        _json_artifact(content_identity).encode("utf-8")
    ).hexdigest()
    if result_path.is_file() and identity_path.is_file():
        cached = read_json_path(result_path)
        cached_identity = read_json_path(identity_path)
        if (
            cached.get("schema_version") == "repo-teacher-human-report/v1"
            and cached_identity == content_identity
        ):
            print("[report 03/05] 复用已完成的完整内容产物", flush=True)
            return cached
    prompt = _provider_prompt(
        _model_prompt(pack_path, model_source),
        provider,
        analysis_pack=direct_pack,
    )
    result = _run_codex_json(
        source=model_source,
        workspace=workspace / "direct-report",
        schema=schema,
        prompt=prompt,
        timeout=timeout,
        stage_slug="direct-human-report",
        progress_label="正在一次生成项目定位、核心功能、底层实现和工程结构",
        provider=provider,
    )
    chapters = result.get("chapters")
    if not isinstance(chapters, list):
        raise ValueError("direct human report has no chapters")
    closed = _canonicalize_inventory_payload(
        {"capabilities": chapters}, direct_pack
    ).get("capabilities")
    if not isinstance(closed, list) or len(closed) != len(chapters):
        raise ValueError(
            "direct human report chapters do not close over the bounded evidence packet"
        )
    result["chapters"] = _bind_report_chapter_ids(
        result,
        _close_chapter_evidence(
            {"chapters": closed},
            direct_pack,
            closed,
            source=model_source,
        ).get("chapters", closed),
    )
    atomic_write_text(result_path, _json_artifact(result))
    atomic_write_text(identity_path, _json_artifact(content_identity))
    return result


def _bounded_direct_report_graph(
    graph: dict[str, object],
    *,
    selected_feature_ids: set[str],
    hint_limit: int,
) -> dict[str, object]:
    """Rebuild one compact graph payload for the single human report call."""

    def graph_priority(item: object) -> tuple[int, str]:
        if not isinstance(item, dict):
            return (2, "")
        item_features = {
            str(value)
            for value in [
                item.get("feature_id"),
                *(
                    item.get("source_feature_ids", [])
                    if isinstance(item.get("source_feature_ids"), list)
                    else []
                ),
            ]
            if isinstance(value, str)
        }
        return (
            0 if item_features & selected_feature_ids else 1,
            str(item.get("id") or ""),
        )

    bounded: dict[str, object] = {
        "schema_version": graph.get("schema_version"),
        "stats": copy.deepcopy(graph.get("stats", {})),
        "interpretation_contract": copy.deepcopy(
            graph.get("interpretation_contract", [])
        ),
    }
    for key, limit in (
        ("feature_slices", min(hint_limit, 24)),
        ("capability_candidates", min(hint_limit, 24)),
    ):
        values = graph.get(key)
        bounded[key] = (
            sorted(
                [copy.deepcopy(item) for item in values if isinstance(item, dict)],
                key=graph_priority,
            )[:limit]
            if isinstance(values, list)
            else []
        )
    for key, limit in (
        ("mechanism_clusters", min(16, max(8, hint_limit // 4))),
        ("components", min(16, max(8, hint_limit // 4))),
        ("module_dependencies", min(48, max(16, hint_limit))),
        ("unresolved_edge_examples", 8),
    ):
        values = graph.get(key)
        bounded[key] = (
            [copy.deepcopy(item) for item in values if isinstance(item, dict)][:limit]
            if isinstance(values, list)
            else []
        )
    return bounded


def _bind_report_chapter_ids(
    report: dict[str, object], chapters: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Bind model chapter labels to stable canonical feature IDs.

    The model decides business grouping and reading order, but it does not get
    to mint authoritative identifiers.  Each chapter is deterministically
    bound to one of its canonical feature anchors; overview references are
    rewritten from the model-local label to the same stable ID.  This mirrors
    RepoAgent's code-object identity discipline while preserving a human
    product taxonomy.
    """

    identifiers: dict[str, str] = {}
    for chapter in chapters:
        old_identifier = str(chapter.get("id") or "")
        anchors = [
            item
            for item in chapter.get("source_feature_ids", [])
            if isinstance(item, str) and item
        ]
        if not anchors:
            raise ValueError(
                "human report chapter has no canonical feature anchor"
            )
        # A business capability may merge several structural seeds, and two
        # capabilities may share one low-level seed.  The ID therefore binds
        # the complete canonical anchor set plus the human product title,
        # rather than trusting an arbitrary model label or forcing a false
        # one-feature-to-one-capability mapping.
        stable_input = "\0".join(
            [*sorted(set(anchors)), str(chapter.get("title") or "").strip()]
        )
        identifier = "capability_" + hashlib.sha256(
            stable_input.encode("utf-8")
        ).hexdigest()[:16]
        chapter["id"] = identifier
        identifiers[old_identifier] = identifier

    project = report.get("project")
    overview = project.get("overview") if isinstance(project, dict) else None
    if not isinstance(overview, dict):
        raise ValueError("direct human report has no project overview")

    def mapped_ids(value: object) -> list[str]:
        return [
            identifiers.get(item, item)
            for item in value
            if isinstance(item, str) and item
        ] if isinstance(value, list) else []

    overview["capability_order"] = [str(item["id"]) for item in chapters]
    overview["supporting_capability_ids"] = mapped_ids(
        overview.get("supporting_capability_ids")
    )
    for axis in overview.get("core_product_axes", []):
        if isinstance(axis, dict):
            axis["capability_ids"] = mapped_ids(axis.get("capability_ids"))
    _close_direct_report_difficulty_evidence(chapters)
    return chapters


def _close_direct_report_difficulty_evidence(
    chapters: Sequence[dict[str, object]],
) -> None:
    """Keep difficulty citations inside their owning chapter evidence set."""

    for chapter in chapters:
        chapter_evidence = [
            item
            for item in chapter.get("evidence_ids", [])
            if isinstance(item, str) and item
        ]
        if not chapter_evidence:
            continue
        difficulty_map = chapter.get("difficulty_map")
        items = difficulty_map.get("items") if isinstance(difficulty_map, dict) else []
        for difficulty in items if isinstance(items, list) else []:
            if not isinstance(difficulty, dict):
                continue
            closed = [
                item
                for item in difficulty.get("evidence_ids", [])
                if isinstance(item, str) and item in chapter_evidence
            ]
            difficulty["evidence_ids"] = closed or chapter_evidence[:1]


def _packet_sha256(payload: dict[str, object]) -> str:
    stable = copy.deepcopy(payload)
    project = stable.get("project")
    if isinstance(project, dict):
        # Snapshot directories are intentionally random per run.  They are an
        # execution location, not semantic input, so stage identities bind the
        # fixed commit/content instead of the temporary absolute path.
        project.pop("path", None)
        project.pop("git_root", None)
        # The analyzer fingerprint is a provenance/publication concern.  The
        # packet below already contains every model-visible graph, feature and
        # evidence record, so binding the expensive model cache to an
        # implementation-only fingerprint would invalidate prose even when the
        # bounded semantic input is byte-for-byte unchanged.  Publication
        # rebinds the cached prose to the current fingerprint and validates the
        # complete index before switching generations.
        project.pop("analysis_fingerprint", None)
    return hashlib.sha256(_json_artifact(stable).encode("utf-8")).hexdigest()


def _inventory_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(_json_artifact(payload).encode("utf-8")).hexdigest()


def _prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _schema_sha256(schema: dict[str, object]) -> str:
    return hashlib.sha256(_json_artifact(schema).encode("utf-8")).hexdigest()


def _indexed_content_sha256(canonical: dict[str, object]) -> str:
    return hashlib.sha256(
        "\n".join(
            f"{item.get('path')}\0{item.get('sha256')}"
            for item in canonical.get("files", [])
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and isinstance(item.get("sha256"), str)
        ).encode("utf-8")
    ).hexdigest()


def _indexed_hashes_sha256(indexed_hashes: dict[str, str]) -> str:
    return hashlib.sha256(
        "\n".join(
            f"{path}\0{indexed_hashes[path]}"
            for path in sorted(indexed_hashes)
        ).encode("utf-8")
    ).hexdigest()


def _stage_contract_digests(*selected_keys: str) -> dict[str, str]:
    return contract_digest_subset(packaged_contract_digests(), selected_keys)


def _stage_cache_workspace(
    *,
    root_workspace: Path,
    stage: str,
    source: Path,
    indexed_content_sha256: str,
    provider: str,
    provider_config: dict[str, object],
    contract_digests: dict[str, str],
    packet: dict[str, object] | None = None,
    inventory_payload: dict[str, object] | None = None,
    prompt: str | None = None,
    schema: dict[str, object] | None = None,
) -> tuple[dict[str, object], Path]:
    identity = build_stage_cache_identity(
        stage=stage,
        source="repository-content-bound",
        indexed_content_sha256=indexed_content_sha256,
        packet_sha256=_packet_sha256(packet) if packet is not None else None,
        inventory_sha256=(
            _inventory_sha256(inventory_payload)
            if inventory_payload is not None
            else None
        ),
        prompt_sha256=_prompt_sha256(prompt) if prompt is not None else None,
        schema_sha256=_schema_sha256(schema) if schema is not None else None,
        provider_config=provider_config,
        contract_digests=contract_digests,
    )
    stage_workspace = root_workspace / stage / str(identity["identity_sha256"])[:24]
    stage_workspace.mkdir(parents=True, exist_ok=True)
    (stage_workspace / "cache-identity.json").write_text(
        _json_artifact(identity), encoding="utf-8"
    )
    return identity, stage_workspace


def _adopt_valid_inventory_cache(
    *,
    stage_root: Path,
    target_workspace: Path,
    packet: dict[str, object],
) -> bool:
    """Revalidate and adopt a cache produced by an older identity layout."""

    target = target_workspace / "capability-inventory.json"
    if target.is_file() or not stage_root.is_dir():
        return target.is_file()
    candidates = sorted(
        (
            path
            for path in stage_root.glob("*/capability-inventory.json")
            if path.parent != target_workspace
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        try:
            payload = _canonicalize_inventory_payload(
                read_json_path(candidate), packet
            )
            _require_inventory_scope(payload, packet)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            continue
        atomic_write_text(target, _json_artifact(payload))
        return True
    return False
































































def _synthesize_inventory_shards(
    *,
    source: Path,
    pack: dict[str, object],
    workspace: Path,
    shards: Sequence[Sequence[str]],
    codegraph_context: dict[str, object],
    deadline: float,
    provider: str,
    progress_prefix: str,
    scope_owner_map: dict[str, str] | None = None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    """Run a bounded number of independent business-domain inventory passes."""

    indexed_content_sha256 = _indexed_hashes_sha256(_indexed_file_hashes(pack))
    inventory_provider = provider_stage_identity(provider, inventory=True)
    inventory_contracts = _stage_contract_digests(*_INVENTORY_STAGE_CONTRACT_KEYS)

    def synthesize_one(
        shard_index: int,
        source_scope_paths: Sequence[str],
        queued_at: float,
    ) -> tuple[str, dict[str, object], dict[str, object]]:
        shard_started = time.monotonic()
        label = f"domain-{shard_index:02d}"
        owner_paths = list(
            dict.fromkeys(
                (scope_owner_map or {}).get(path, path)
                for path in source_scope_paths
            )
        )
        shard_workspace = workspace / label
        shard_workspace.mkdir(parents=True, exist_ok=True)
        shard_pack = _attach_source_excerpts(
            _add_project_navigation(
                _build_inventory_shard_pack(
                    pack,
                    owner_paths,
                    codegraph_context=codegraph_context,
                    selection_scope_paths=source_scope_paths,
                ),
                pack,
            ),
            source,
            character_budget=INVENTORY_SOURCE_EXCERPT_BUDGET,
        )
        if not shard_pack["scope"]["allowed_source_paths"]:
            raise ValueError(
                f"CodeGraph business domain has no canonical evidence closure: {label}"
            )
        shard_pack["codegraph_exploration"] = _codegraph_explore_domain(
            source, source_scope_paths
        )
        shard_pack["packet_budget"] = require_packet_budget(
            shard_pack,
            byte_budget=INVENTORY_SHARD_BYTE_BUDGET,
            token_budget=INVENTORY_SHARD_TOKEN_BUDGET,
        )
        require_packet_budget(
            shard_pack,
            byte_budget=INVENTORY_SHARD_BYTE_BUDGET,
            token_budget=INVENTORY_SHARD_TOKEN_BUDGET,
        )
        shard_identity, shard_cache_workspace = _stage_cache_workspace(
            root_workspace=workspace,
            stage=label,
            source=source,
            indexed_content_sha256=indexed_content_sha256,
            provider=provider,
            provider_config=inventory_provider,
            contract_digests=inventory_contracts,
            packet=shard_pack,
            schema=_inventory_json_schema(),
        )
        packet_path = shard_cache_workspace / "analysis-pack-shard.json"
        packet_path.write_text(_json_artifact(shard_pack), encoding="utf-8")
        shard_source = _materialize_source_slice(
            source,
            shard_cache_workspace,
            shard_pack["scope"]["allowed_source_paths"],
            _indexed_file_hashes(pack),
        )
        model_packet_path = _stage_model_json(
            shard_source,
            "analysis-pack-shard.json",
            shard_pack,
        )
        _adopt_valid_inventory_cache(
            stage_root=workspace / label,
            target_workspace=shard_cache_workspace,
            packet=shard_pack,
        )
        model_provider = CallableStructuredModelProvider(
            provider,
            lambda request: _run_codex_json(
                source=request.source,
                workspace=request.workspace,
                schema=request.schema,
                prompt=request.prompt,
                timeout=request.timeout_seconds,
                stage_slug=f"{request.stage}-model",
                progress_label=(
                    f"{provider} 正在归纳业务域 {shard_index + 1}/{len(shards)}"
                ),
                provider=provider,
            ),
        )
        stage = CapabilityInventoryStage(model_provider)
        payload, reused = stage.run(
            InventoryStageRequest(
                source=shard_source,
                workspace=shard_cache_workspace,
                packet=shard_pack,
                packet_path=model_packet_path,
                prompt=_provider_prompt(
                    _inventory_shard_prompt(
                        model_packet_path,
                        shard_source,
                        owner_paths,
                    ),
                    provider,
                    analysis_pack=shard_pack,
                ),
                schema=_inventory_json_schema(),
                timeout_seconds=_remaining_model_timeout(deadline),
            ),
            normalize=_canonicalize_inventory_payload,
            validate=_require_inventory_scope,
        )
        if reused:
            print(
                f"[{progress_prefix}] 复用业务域 {shard_index + 1}/{len(shards)} 缓存",
                flush=True,
            )
        if scope_owner_map:
            dispositions = payload.get("module_dispositions")
            if not isinstance(dispositions, list):
                raise ValueError("inventory shard omitted module dispositions")
            allowed_owners = set(owner_paths)
            for disposition in dispositions:
                if not isinstance(disposition, dict):
                    raise ValueError("inventory shard produced an invalid disposition")
                path = disposition.get("path")
                if not isinstance(path, str) or path not in allowed_owners:
                    raise ValueError(
                        "inventory shard disposition escaped its source-scope owner"
                    )
        performance_path = (
            shard_cache_workspace / "capability-inventory-model-performance.json"
        )
        model_performance = (
            read_json_path(performance_path) if performance_path.is_file() else {}
        )
        packet_budget = shard_pack.get("packet_budget")
        shard_metrics = {
            "label": label,
            "cache_identity_sha256": shard_identity["identity_sha256"],
            "queue_seconds": round(max(shard_started - queued_at, 0.0), 6),
            "wall_duration_seconds": round(
                max(time.monotonic() - shard_started, 0.0), 6
            ),
            "cache_reused": reused,
            "repair_used": False,
            "packet_bytes": packet_budget.get("packet_bytes")
            if isinstance(packet_budget, dict)
            else None,
            "estimated_tokens": packet_budget.get("estimated_tokens")
            if isinstance(packet_budget, dict)
            else None,
            "model_duration_seconds": model_performance.get("duration_seconds")
            if isinstance(model_performance, dict)
            else None,
        }
        return label, payload, shard_metrics

    completed: list[tuple[str, dict[str, object], dict[str, object]]] = []
    max_workers = min(8, len(shards))
    parallel_started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for index, source_scope_paths in enumerate(shards):
            queued_at = time.monotonic()
            futures[
                pool.submit(synthesize_one, index, source_scope_paths, queued_at)
            ] = index
        for future in as_completed(futures):
            completed.append(future.result())
            print(
                f"[{progress_prefix}] 业务域功能目录完成 {len(completed)}/{len(shards)}",
                flush=True,
            )
    completed.sort(key=lambda item: item[0])
    shard_metrics = [item[2] for item in completed]
    model_seconds = sum(
        float(item["model_duration_seconds"])
        for item in shard_metrics
        if isinstance(item.get("model_duration_seconds"), (int, float))
    )
    parallel_wall_seconds = max(time.monotonic() - parallel_started, 0.0)
    atomic_write_text(
        workspace / "inventory-shards-performance.json",
        _json_artifact(
            {
                "schema_version": "repolens-inventory-shard-performance/v1",
                "shards": shard_metrics,
                "max_workers": max_workers,
                "parallel_wall_seconds": round(parallel_wall_seconds, 6),
                "model_seconds_sum": round(model_seconds, 6),
                "parallel_speedup_ratio": round(
                    model_seconds / parallel_wall_seconds, 6
                )
                if parallel_wall_seconds
                else None,
                "cache_hits": sum(bool(item.get("cache_reused")) for item in shard_metrics),
                "repairs": sum(bool(item.get("repair_used")) for item in shard_metrics),
            }
        ),
    )
    project_summary = next(
        (
            payload.get("project_summary")
            for _label, payload, _metrics in completed
            if isinstance(payload.get("project_summary"), dict)
        ),
        None,
    )
    return _merge_inventory_shards(
        [(label, payload) for label, payload, _metrics in completed]
    ), project_summary


def _review_and_repair_inventory(
    *,
    source: Path,
    pack: dict[str, object],
    candidate_payload: dict[str, object],
    inventory_payload: dict[str, object],
    workspace: Path,
    deadline: float,
    provider: str,
    product_navigation: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Run one terminal semantic review without invoking an earlier stage."""

    del product_navigation
    started = time.monotonic()
    review = run_inventory_semantic_review(
        source=source,
        pack=pack,
        candidate_payload=candidate_payload,
        inventory_payload=inventory_payload,
        workspace=workspace,
        provider=provider,
        timeout=_remaining_model_timeout(deadline),
        runner=_run_codex_json,
        stage_slug="inventory-semantic-review",
    )
    atomic_write_text(
        workspace / "inventory-validation.json", _json_artifact(review)
    )
    stages = LinearStageArtifacts(workspace, stages=LEGACY_INVENTORY_STAGES)
    if review.get("status") == "passed":
        stages.pass_stage(
            "06-semantic-validation",
            inputs={
                "candidate_sha256": _packet_sha256(candidate_payload),
                "inventory_sha256": _packet_sha256(inventory_payload),
            },
            output=review,
            metrics={
                "wall_duration_seconds": round(time.monotonic() - started, 6),
                "model_calls": 1,
            },
        )
        return _public_inventory_payload(inventory_payload)
    issues = review.get("issues")
    first_issue = issues[0] if isinstance(issues, list) and issues else {}
    message = (
        first_issue.get("message")
        if isinstance(first_issue, dict)
        else "semantic review failed"
    )
    error = "capability inventory failed independent semantic review: " + str(message)
    stages.fail_stage(
        "06-semantic-validation",
        inputs={
            "candidate_sha256": _packet_sha256(candidate_payload),
            "inventory_sha256": _packet_sha256(inventory_payload),
        },
        error=error,
        metrics={
            "wall_duration_seconds": round(time.monotonic() - started, 6),
            "model_calls": 1,
        },
    )
    raise ValueError(error)


def _synthesize_with_codex(
    source: Path,
    pack: dict[str, object],
    workspace: Path,
    timeout: int,
    inventory_arg: str | None = None,
    provider: str = "codex",
    *,
    inventory_only: bool = False,
) -> dict[str, object]:
    stage_artifacts = LinearStageArtifacts(
        workspace, stages=LEGACY_INVENTORY_STAGES
    )
    pack_path = workspace / "analysis-pack.json"
    pack_path.write_text(_json_artifact(pack), encoding="utf-8")
    indexed_content_sha256 = _indexed_hashes_sha256(_indexed_file_hashes(pack))
    deadline = time.monotonic() + timeout
    progress_prefix = "inventory 3/4" if inventory_only else "report 4/6"
    print(
        f"[{progress_prefix}] 先归纳完整功能目录，再分批补全章节…",
        flush=True,
    )
    generated_candidate_payload: dict[str, object] | None = None
    if inventory_arg:
        inventory_input = read_json_path(Path(inventory_arg).expanduser())
        inventory_payload = _inventory_from_manifest(inventory_input, pack)
        inventory_needs_grouping = not (
            inventory_payload.get("grouping_complete") is True
            or isinstance(inventory_payload.get("module_dispositions"), list)
        )
        print(
            f"[report 4/6] 已加载外部功能目录，共 {len(inventory_payload['capabilities'])} 项；跳过 inventory 模型阶段",
            flush=True,
        )
    else:
        inventory_needs_grouping = False
        inventory_workspace = workspace / "inventory"
        inventory_workspace.mkdir(parents=True, exist_ok=True)
        inventory_provider = provider_stage_identity(provider, inventory=True)
        inventory_contracts = _stage_contract_digests(*_INVENTORY_STAGE_CONTRACT_KEYS)
        module_shards = _inventory_module_shards(pack)
        product_module_paths = list(
            dict.fromkeys(
                path
                for shard in module_shards
                for path in shard
                if isinstance(path, str)
            )
        )
        if not product_module_paths:
            raise ValueError("code graph produced no product implementation domain")
        codegraph_context = _codegraph_domain_context(
            source,
            product_module_paths,
            max_paths=128,
            max_nodes=320,
            max_edges=640,
        )
        pack = _augment_pack_with_codegraph_context(pack, codegraph_context)
        pack_path.write_text(_json_artifact(pack), encoding="utf-8")

        def owner_for_scope(scope: str) -> str:
            owners = [
                module
                for module in product_module_paths
                if scope == module or scope.startswith(f"{module}/")
            ]
            if not owners:
                raise ValueError(
                    f"inventory source scope has no graph-derived module owner: {scope}"
                )
            return max(owners, key=len)

        def measure_inventory_packet(source_scope_paths: Sequence[str]) -> int:
            owner_paths = list(
                dict.fromkeys(owner_for_scope(scope) for scope in source_scope_paths)
            )
            packet = _attach_source_excerpts(
                _build_inventory_shard_pack(
                    pack,
                    owner_paths,
                    codegraph_context=codegraph_context,
                    selection_scope_paths=source_scope_paths,
                ),
                source,
                character_budget=INVENTORY_SOURCE_EXCERPT_BUDGET,
            )
            # The bounded 80 KiB CodeGraph prose is added after partitioning;
            # reserve another 20 KiB for JSON escaping and prompt framing.
            return len(_json_artifact(packet).encode("utf-8")) + 100_000

        source_paths = sorted(_source_paths(pack))
        expanded_domain_shards: list[list[str]] = []
        scope_owner_map: dict[str, str] = {}
        for domain_shard in module_shards:
            expanded: list[str] = []
            for module_path in domain_shard:
                scopes, owners = expand_oversized_module_scopes(
                    [module_path],
                    source_paths=source_paths,
                    measure=measure_inventory_packet,
                    byte_budget=INVENTORY_SHARD_BYTE_BUDGET,
                    token_budget=INVENTORY_SHARD_TOKEN_BUDGET,
                )
                expanded.extend(scopes)
                scope_owner_map.update(owners)
            expanded_domain_shards.append(sorted(dict.fromkeys(expanded)))
        module_shards, partition_metrics = split_shards_by_budget(
            expanded_domain_shards,
            measure=measure_inventory_packet,
            byte_budget=INVENTORY_SHARD_BYTE_BUDGET,
            token_budget=INVENTORY_SHARD_TOKEN_BUDGET,
        )
        (workspace / "inventory-partition-plan.json").write_text(
            _json_artifact(
                {
                    "schema_version": "repolens-inventory-partition/v1",
                    "status": "passed",
                    "shards": partition_metrics,
                    "source_scope_owners": scope_owner_map,
                }
            ),
            encoding="utf-8",
        )
        use_sharded_inventory = len(module_shards) > 1 or any(
            scope != owner for scope, owner in scope_owner_map.items()
        )
        if use_sharded_inventory:
            print(
                f"[{progress_prefix}] CodeGraph 已收敛为 {len(module_shards)} 个业务域；"
                f"最多 {min(8, len(module_shards))} 路并发归纳，再做一次全局语义合并",
                flush=True,
            )
            merged, project_summary = _synthesize_inventory_shards(
                source=source,
                pack=pack,
                workspace=inventory_workspace,
                shards=module_shards,
                codegraph_context=codegraph_context,
                deadline=deadline,
                provider=provider,
                progress_prefix=progress_prefix,
                scope_owner_map=scope_owner_map,
            )
            atomic_write_text(
                workspace / "capability-candidates.json", _json_artifact(merged)
            )
            stage_artifacts.pass_stage(
                "04-capability-candidates",
                inputs={
                    "indexed_content_sha256": indexed_content_sha256,
                    "shards": len(module_shards),
                },
                output={
                    "artifact": "capability-candidates.json",
                    "sha256": _packet_sha256(merged),
                },
                metrics={
                    "candidates": len(merged.get("capabilities", [])),
                    "model_calls": len(module_shards),
                },
            )
            grouping_started = time.monotonic()
            navigation_pack = _add_project_navigation(
                {"scope": {"allowed_source_paths": []}}, pack
            )
            inventory_payload = _group_inventory_for_humans(
                merged,
                source=source,
                workspace=workspace,
                deadline=deadline,
                provider=provider,
                product_navigation=[
                    item
                    for item in navigation_pack.get("product_navigation", [])
                    if isinstance(item, dict)
                ],
            )
            if project_summary is not None and not isinstance(
                inventory_payload.get("project_summary"), dict
            ):
                inventory_payload["project_summary"] = project_summary
            inventory_payload["generator"] = {
                "name": provider,
                "method": "repo-teacher parallel business-domain inventory",
            }
            inventory_payload = _canonicalize_inventory_payload(
                inventory_payload, pack
            )
            _require_inventory_against_pack(inventory_payload, pack)
            atomic_write_text(
                workspace / "capability-inventory.grouped.json",
                _json_artifact(inventory_payload),
            )
            stage_artifacts.pass_stage(
                "05-business-grouping",
                inputs={"candidate_sha256": _packet_sha256(merged)},
                output={
                    "artifact": "capability-inventory.grouped.json",
                    "sha256": _packet_sha256(inventory_payload),
                },
                metrics={
                    "capabilities": len(inventory_payload.get("capabilities", [])),
                    "wall_duration_seconds": round(
                        time.monotonic() - grouping_started, 6
                    ),
                    "model_calls": 1,
                },
            )
            inventory_payload = _review_and_repair_inventory(
                source=source,
                pack=pack,
                candidate_payload=merged,
                inventory_payload=inventory_payload,
                workspace=workspace,
                deadline=deadline,
                provider=provider,
                product_navigation=[
                    item
                    for item in navigation_pack.get("product_navigation", [])
                    if isinstance(item, dict)
                ],
            )
            if project_summary is not None and not isinstance(
                inventory_payload.get("project_summary"), dict
            ):
                inventory_payload["project_summary"] = project_summary
            inventory_payload["generator"] = {
                "name": provider,
                "method": "repo-teacher parallel business-domain inventory",
            }
            inventory_payload["schema_version"] = (
                "repo-teacher-capability-inventory/v1"
            )
            inventory_payload["grouping_complete"] = True
            inventory_path = workspace / "capability-inventory.json"
            inventory_path.write_text(
                _json_artifact(inventory_payload), encoding="utf-8"
            )
            capabilities = [
                item
                for item in inventory_payload.get("capabilities", [])
                if isinstance(item, dict)
            ]
            if not capabilities:
                raise ValueError("parallel business-domain inventory produced no capabilities")
            if inventory_only:
                print(
                    f"[inventory 4/4] 功能目录完成，共 {len(capabilities)} 项；未生成教程章节",
                    flush=True,
                )
                return inventory_payload
            return _synthesize_with_codex(
                source,
                pack,
                workspace,
                _remaining_model_timeout(deadline),
                str(inventory_path),
                provider,
                inventory_only=False,
            )
        print(
            f"[{progress_prefix}] CodeGraph 已收敛产品源码范围；"
            "单次全局模型调用直接生成业务功能目录",
            flush=True,
        )
        codegraph_context = _codegraph_domain_context(
            source,
            product_module_paths,
            max_paths=96,
            max_nodes=256,
            max_edges=512,
        )
        pack = _augment_pack_with_codegraph_context(pack, codegraph_context)
        pack_path.write_text(_json_artifact(pack), encoding="utf-8")
        inventory_pack = _attach_source_excerpts(
            _add_project_navigation(
                _build_global_business_inventory_pack(
                    pack,
                    hint_limit=240,
                    codegraph_context=codegraph_context,
                ),
                pack,
            ),
            source,
        )
        inventory_pack["codegraph_exploration"] = _codegraph_explore_domain(
            source, product_module_paths
        )
        inventory_pack["packet_budget"] = require_packet_budget(inventory_pack)
        require_packet_budget(inventory_pack)
        _, inventory_stage_workspace = _stage_cache_workspace(
            root_workspace=workspace,
            stage="inventory-global",
            source=source,
            indexed_content_sha256=indexed_content_sha256,
            provider=provider,
            provider_config=inventory_provider,
            contract_digests=inventory_contracts,
            packet=inventory_pack,
            schema=_inventory_json_schema(),
        )
        inventory_pack_path = inventory_stage_workspace / "analysis-pack-inventory.json"
        inventory_pack_path.write_text(
            _json_artifact(inventory_pack), encoding="utf-8"
        )
        inventory_source = _materialize_source_slice(
            source,
            inventory_stage_workspace,
            inventory_pack["scope"]["allowed_source_paths"],
            _indexed_file_hashes(pack),
        )
        model_pack_path = _stage_model_json(
            inventory_source,
            "analysis-pack-inventory.json",
            inventory_pack,
        )
        model_provider = CallableStructuredModelProvider(
            provider,
            lambda request: _run_codex_json(
                source=request.source,
                workspace=request.workspace,
                schema=request.schema,
                prompt=request.prompt,
                timeout=request.timeout_seconds,
                stage_slug=f"{request.stage}-model",
                progress_label=f"{provider} 正在一次性归纳全局业务功能",
                provider=provider,
            ),
        )
        inventory_stage = CapabilityInventoryStage(model_provider)
        inventory_payload, reused_inventory = inventory_stage.run(
            InventoryStageRequest(
                source=inventory_source,
                workspace=inventory_stage_workspace,
                packet=inventory_pack,
                packet_path=model_pack_path,
                prompt=_provider_prompt(
                    _inventory_prompt(model_pack_path, inventory_source),
                    provider,
                    analysis_pack=inventory_pack,
                ),
                schema=_inventory_json_schema(),
                timeout_seconds=_remaining_model_timeout(deadline),
            ),
            normalize=_canonicalize_inventory_payload,
            validate=_require_inventory_scope,
        )
        if reused_inventory:
            print(
                f"[{progress_prefix}] 复用已重新校验的业务功能目录缓存",
                flush=True,
            )
        generated_candidate_payload = copy.deepcopy(inventory_payload)
        atomic_write_text(
            workspace / "capability-candidates.json",
            _json_artifact(generated_candidate_payload),
        )
        stage_artifacts.pass_stage(
            "04-capability-candidates",
            inputs={"indexed_content_sha256": indexed_content_sha256, "shards": 1},
            output={
                "artifact": "capability-candidates.json",
                "sha256": _packet_sha256(generated_candidate_payload),
            },
            metrics={
                "candidates": len(generated_candidate_payload.get("capabilities", [])),
                "model_calls": 0 if reused_inventory else 1,
                "cache_reused": reused_inventory,
            },
        )
    inventory_payload = _canonicalize_inventory_payload(inventory_payload, pack)
    _require_inventory_against_pack(inventory_payload, pack)
    if inventory_needs_grouping:
        grouping_started = time.monotonic()
        grouping_input = copy.deepcopy(inventory_payload)
        navigation_pack = _add_project_navigation(
            {"scope": {"allowed_source_paths": []}}, pack
        )
        product_navigation = [
            item
            for item in navigation_pack.get("product_navigation", [])
            if isinstance(item, dict)
        ]
        _, grouping_workspace = _stage_cache_workspace(
            root_workspace=workspace,
            stage="inventory-grouping",
            source=source,
            indexed_content_sha256=indexed_content_sha256,
            provider=provider,
            provider_config=provider_stage_identity(provider, inventory=False),
            contract_digests=_stage_contract_digests(*_GROUPING_STAGE_CONTRACT_KEYS),
            packet={
                "inventory_payload": inventory_payload,
                "product_navigation": product_navigation,
            },
            schema=inventory_group_json_schema(),
        )
        inventory_payload = _group_inventory_for_humans(
            inventory_payload,
            source=source,
            workspace=grouping_workspace,
            deadline=deadline,
            provider=provider,
            product_navigation=product_navigation,
        )
        _require_inventory_against_pack(inventory_payload, pack)
        atomic_write_text(
            workspace / "capability-inventory.grouped.json",
            _json_artifact(inventory_payload),
        )
        stage_artifacts.pass_stage(
            "05-business-grouping",
            inputs={"candidate_sha256": _packet_sha256(grouping_input)},
            output={
                "artifact": "capability-inventory.grouped.json",
                "sha256": _packet_sha256(inventory_payload),
            },
            metrics={
                "capabilities": len(inventory_payload.get("capabilities", [])),
                "wall_duration_seconds": round(
                    time.monotonic() - grouping_started, 6
                ),
                "model_calls": 1,
            },
        )
    if inventory_arg is None:
        candidate_payload = generated_candidate_payload or copy.deepcopy(
            inventory_payload
        )
        navigation_pack = _add_project_navigation(
            {"scope": {"allowed_source_paths": []}}, pack
        )
        inventory_payload = _review_and_repair_inventory(
            source=source,
            pack=pack,
            candidate_payload=candidate_payload,
            inventory_payload=inventory_payload,
            workspace=workspace,
            deadline=deadline,
            provider=provider,
            product_navigation=[
                item
                for item in navigation_pack.get("product_navigation", [])
                if isinstance(item, dict)
            ],
        )
    raw_capabilities = inventory_payload.get("capabilities")
    if not isinstance(raw_capabilities, list) or not raw_capabilities:
        raise ValueError("Codex inventory did not produce capabilities")
    capabilities = [capability for capability in raw_capabilities if isinstance(capability, dict)]
    capability_ids = [str(capability.get("id") or "") for capability in capabilities]
    if any(not capability_id for capability_id in capability_ids):
        raise ValueError("Codex inventory produced empty capability id")
    if len(set(capability_ids)) != len(capability_ids):
        raise ValueError("Codex inventory capability ids must be unique")
    inventory_payload["schema_version"] = "repo-teacher-capability-inventory/v1"
    inventory_payload["grouping_complete"] = True
    inventory_payload["capabilities"] = capabilities
    inventory_path = workspace / "capability-inventory.json"
    inventory_path.write_text(_json_artifact(inventory_payload), encoding="utf-8")
    if inventory_only:
        print(
            f"[inventory 4/4] 功能目录完成，共 {len(capabilities)} 项；"
            "未生成教程章节",
            flush=True,
        )
        return inventory_payload
    overview_started = time.monotonic()
    overview_workspace = workspace / "project-overview"
    overview_workspace.mkdir(parents=True, exist_ok=True)
    overview_pack = _build_chapter_batch_pack(pack, capabilities)
    overview_pack = _add_project_navigation(overview_pack, pack)
    overview_pack = _attach_source_excerpts(overview_pack, source)
    overview_schema = project_overview_json_schema(len(capabilities))
    _, overview_stage_workspace = _stage_cache_workspace(
        root_workspace=workspace,
        stage="project-overview",
        source=source,
        indexed_content_sha256=indexed_content_sha256,
        provider=provider,
        provider_config=provider_stage_identity(provider, inventory=False),
        contract_digests=_stage_contract_digests(*_OVERVIEW_STAGE_CONTRACT_KEYS),
        packet=overview_pack,
        inventory_payload=inventory_payload,
        schema=overview_schema,
    )
    overview_pack_path = overview_stage_workspace / "analysis-pack-overview.json"
    overview_pack_path.write_text(_json_artifact(overview_pack), encoding="utf-8")
    overview_source = _materialize_source_slice(
        source,
        overview_stage_workspace,
        overview_pack["scope"]["allowed_source_paths"],
        _indexed_file_hashes(pack),
    )
    model_overview_pack_path = _stage_model_json(
        overview_source, "analysis-pack-overview.json", overview_pack
    )
    overview_result_path = overview_stage_workspace / "project-overview.json"
    project_overview: dict[str, object] | None = None
    if overview_result_path.is_file():
        try:
            project_overview = _normalize_project_overview(
                read_json_path(overview_result_path),
                overview_pack,
                capabilities,
                source,
            )
            print("[report 4/6] 复用已校验的项目定位与架构章节缓存", flush=True)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            project_overview = None
    if project_overview is None:
        overview_payload = _run_codex_json(
            source=overview_source,
            workspace=overview_stage_workspace,
            schema=overview_schema,
            prompt=_provider_prompt(
                _project_overview_prompt(
                    model_overview_pack_path,
                    overview_source,
                    capability_ids,
                ),
                provider,
                analysis_pack=overview_pack,
                capability_inventory=inventory_payload,
            ),
            timeout=_remaining_model_timeout(deadline),
            stage_slug="project-overview",
            progress_label="Codex 正在说明项目定位、整体架构与代码组织",
            provider=provider,
        )
        project_overview = _normalize_project_overview(
            overview_payload, overview_pack, capabilities, source
        )
        overview_result_path.write_text(
            _json_artifact({"project_overview": project_overview}), encoding="utf-8"
        )
    by_capability_id = {str(item["id"]): item for item in capabilities}
    capability_ids = [str(item) for item in project_overview["capability_order"]]
    capabilities = [by_capability_id[identifier] for identifier in capability_ids]
    inventory_payload["capabilities"] = capabilities
    inventory_payload["project_overview"] = project_overview
    inventory_path.write_text(_json_artifact(inventory_payload), encoding="utf-8")
    stage_artifacts.pass_stage(
        "07-project-overview",
        inputs={"inventory_sha256": _packet_sha256(inventory_payload)},
        output={"artifact": "project-overview.json", "project_overview": project_overview},
        metrics={
            "wall_duration_seconds": round(time.monotonic() - overview_started, 6),
            "model_calls": 1,
        },
    )
    print(
        f"[report 4/6] 功能目录完成，共 {len(capabilities)} 项；开始分批生成章节…",
        flush=True,
    )
    chapters_started = time.monotonic()
    batches = _chunk_capabilities(
        capabilities,
        batch_size=(
            min(2, len(capabilities))
            if provider == "deepseek"
            else (4 if len(capabilities) > 4 else len(capabilities))
        ),
    )
    chapters_by_id: dict[str, dict[str, object]] = {}
    completed_batches = 0

    def synthesize_batch(
        batch_index: int, batch_capabilities: Sequence[dict[str, object]]
    ) -> dict[str, object]:
        expected_ids = {
            str(capability["id"])
            for capability in batch_capabilities
            if isinstance(capability.get("id"), str)
        }
        batch_pack = _attach_source_excerpts(
            _build_chapter_batch_pack(pack, batch_capabilities), source
        )
        batch_schema = chapter_batch_json_schema(len(expected_ids))
        _, batch_workspace = _stage_cache_workspace(
            root_workspace=workspace,
            stage=f"chapter-batch-{batch_index:02d}",
            source=source,
            indexed_content_sha256=indexed_content_sha256,
            provider=provider,
            provider_config=provider_stage_identity(provider, inventory=False),
            contract_digests=_stage_contract_digests(*_CHAPTER_STAGE_CONTRACT_KEYS),
            packet=batch_pack,
            inventory_payload=inventory_payload,
            schema=batch_schema,
        )
        cached_result_path = batch_workspace / "chapter-result.json"
        if cached_result_path.is_file():
            try:
                cached = read_json_path(cached_result_path)
                cached_chapters = cached.get("chapters")
                cached_ids = {
                    str(chapter.get("id"))
                    for chapter in cached_chapters
                    if isinstance(chapter, dict) and isinstance(chapter.get("id"), str)
                } if isinstance(cached_chapters, list) else set()
                if cached_ids == expected_ids:
                    cached = _close_chapter_evidence(
                        cached, batch_pack, batch_capabilities, source
                    )
                    cached_result_path.write_text(
                        _json_artifact(cached), encoding="utf-8"
                    )
                    print(
                        f"[report 4/6] 复用章节批次 {batch_index + 1}/{len(batches)} 的已校验模型缓存",
                        flush=True,
                    )
                    return cached
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                pass
        batch_pack_path = batch_workspace / "analysis-pack-batch.json"
        batch_pack_path.write_text(_json_artifact(batch_pack), encoding="utf-8")
        source_slice = _materialize_source_slice(
            source,
            batch_workspace,
            batch_pack["scope"]["allowed_source_paths"],
            _indexed_file_hashes(pack),
        )
        model_batch_pack_path = _stage_model_json(
            source_slice, "analysis-pack-batch.json", batch_pack
        )
        model_inventory_path = _stage_model_json(
            source_slice, "capability-inventory.json", inventory_payload
        )
        capability_batch_ids = [
            str(capability["id"])
            for capability in batch_capabilities
            if isinstance(capability.get("id"), str)
        ]
        payload = _run_codex_json(
            source=source_slice,
            workspace=batch_workspace,
            schema=batch_schema,
            prompt=_provider_prompt(
                _chapter_batch_prompt(
                    model_batch_pack_path,
                    model_inventory_path,
                    source_slice,
                    capability_batch_ids,
                ),
                provider,
                analysis_pack=batch_pack,
                capability_inventory=inventory_payload,
            ),
            timeout=_remaining_model_timeout(deadline),
            stage_slug=f"chapter-batch-{batch_index:02d}",
            progress_label=(
                f"Codex 正在补全章节批次 {batch_index + 1}/{len(batches)}"
            ),
            provider=provider,
        )
        payload = _close_chapter_evidence(
            payload, batch_pack, batch_capabilities, source
        )
        cached_result_path.write_text(_json_artifact(payload), encoding="utf-8")
        return payload

    max_workers = min(4, len(batches))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(synthesize_batch, batch_index, batch): (batch_index, batch)
            for batch_index, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            batch_index, batch = futures[future]
            payload = future.result()
            batch_chapters = payload.get("chapters")
            if not isinstance(batch_chapters, list) or not batch_chapters:
                raise ValueError(
                    f"Codex chapter batch {batch_index + 1} did not produce chapters"
                )
            expected = {
                str(capability["id"]): capability
                for capability in batch
                if isinstance(capability.get("id"), str)
            }
            for chapter in batch_chapters:
                if not isinstance(chapter, dict):
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} produced non-object chapter"
                    )
                chapter_id = str(chapter.get("id") or "")
                if chapter_id not in expected:
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} returned unexpected chapter: {chapter_id or 'unknown'}"
                    )
                inventory_capability = expected[chapter_id]
                if chapter.get("title") != inventory_capability.get("title"):
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} changed chapter title: {chapter_id}"
                    )
                if chapter.get("source_feature_ids") != inventory_capability.get(
                    "source_feature_ids"
                ):
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} changed source_feature_ids: {chapter_id}"
                    )
                inventory_evidence = set(
                    inventory_capability.get("evidence_ids", [])
                    if isinstance(inventory_capability.get("evidence_ids"), list)
                    else []
                )
                chapter_evidence = set(
                    chapter.get("evidence_ids", [])
                    if isinstance(chapter.get("evidence_ids"), list)
                    else []
                )
                if not inventory_evidence <= chapter_evidence:
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} dropped inventory evidence: {chapter_id}"
                    )
                chapters_by_id[chapter_id] = chapter
            completed_batches += 1
            print(
                f"[report 4/6] 章节批次完成 {completed_batches}/{len(batches)}；"
                f"已补全 {len(chapters_by_id)}/{len(capabilities)} 章",
                flush=True,
            )
    if set(chapters_by_id) != set(capability_ids):
        missing = [capability_id for capability_id in capability_ids if capability_id not in chapters_by_id]
        raise ValueError(f"Codex chapter batches missed capabilities: {missing[0]}")
    ordered_chapters = [chapters_by_id[capability_id] for capability_id in capability_ids]
    _require_source_ref_quality(ordered_chapters)
    report_payload = {
        "schema_version": "repo-teacher-human-report/v1",
        "project": {
            "commit": pack["project"]["commit"],
            "analysis_fingerprint": pack["project"]["analysis_fingerprint"],
            "overview": project_overview,
        },
        "generator": {
            "name": "Codex",
            "method": "repo-teacher batched capability synthesis",
        },
        "chapters": ordered_chapters,
    }
    atomic_write_text(workspace / "human-report.json", _json_artifact(report_payload))
    stage_artifacts.pass_stage(
        "08-capability-chapters",
        inputs={"inventory_sha256": _packet_sha256(inventory_payload)},
        output={
            "artifact": "human-report.json",
            "sha256": _packet_sha256(report_payload),
        },
        metrics={
            "chapters": len(ordered_chapters),
            "batches": len(batches),
            "model_calls": len(batches),
            "wall_duration_seconds": round(time.monotonic() - chapters_started, 6),
        },
    )
    return report_payload


def _report_index_with_navigation_evidence(
    canonical: dict[str, object], pack: dict[str, object]
) -> dict[str, object]:
    report_index = copy.deepcopy(canonical)
    features = [
        item
        for item in report_index.get("features", [])
        if isinstance(item, dict)
    ]
    known_feature_ids = {
        item.get("id") for item in features if isinstance(item.get("id"), str)
    }
    for hint in pack.get("feature_hints", []):
        if not isinstance(hint, dict):
            continue
        identifier = hint.get("id")
        if not isinstance(identifier, str) or identifier in known_feature_ids:
            continue
        features.append(
            {
                "id": identifier,
                "kind": "graph-mechanism-candidate",
                "source": "report-only-graph-navigation",
            }
        )
        known_feature_ids.add(identifier)
    evidence = [
        item
        for item in report_index.get("evidence", [])
        if isinstance(item, dict)
    ]
    known_evidence_ids = {
        item.get("id") for item in evidence if isinstance(item.get("id"), str)
    }
    for item in pack.get("evidence", []):
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or identifier in known_evidence_ids:
            continue
        evidence.append(copy.deepcopy(item))
        known_evidence_ids.add(identifier)
    report_index["features"] = features
    report_index["evidence"] = evidence
    return report_index


def _model_workspace_for_pack(
    source: Path,
    pack: dict[str, object],
    canonical: dict[str, object],
    provider: str,
    inventory_digest: str | None = None,
) -> tuple[str, Path]:
    indexed_content_sha256 = _indexed_content_sha256(canonical)
    # The outer report-stage cache must change whenever the one-shot report
    # prompt, its strict JSON Schema, or the provider/model contract changes.
    # A hand-maintained version string alone is too easy to forget and could
    # otherwise reuse prose generated under a stale content contract.
    stable_prompt = _model_prompt(Path("/PACK.json"), Path("/SOURCE"))
    direct_contract = {
        "version": REPORT_SYNTHESIS_CONTRACT_VERSION,
        "prompt_sha256": _prompt_sha256(stable_prompt),
        "schema_sha256": _schema_sha256(human_report_json_schema()),
        "provider": provider_stage_identity(provider),
    }
    direct_contract_sha256 = hashlib.sha256(
        _json_artifact(direct_contract).encode("utf-8")
    ).hexdigest()
    run_identity = build_run_identity(
        source=str(source),
        commit=(pack.get("project") or {}).get("commit")
        if isinstance(pack.get("project"), dict)
        else None,
        analysis_fingerprint=(pack.get("project") or {}).get("analysis_fingerprint")
        if isinstance(pack.get("project"), dict)
        else None,
        source_manifest_sha256=canonical.get("source_manifest_sha256"),
        indexed_content_sha256=indexed_content_sha256,
        provider=provider,
        inventory_sha256=inventory_digest,
        synthesis_contract=(
            f"{REPORT_SYNTHESIS_CONTRACT_VERSION}:{direct_contract_sha256}"
        ),
        contract_digests={
            "repo_teacher.prompts:human-report-full-v1.md": packaged_contract_digests()[
                "repo_teacher.prompts:human-report-full-v1.md"
            ],
            "schema:human-report": packaged_contract_digests()[
                "schema:human-report"
            ],
        },
        provider_config=provider_stage_identity(provider),
    )
    root_identity = build_workspace_root_identity(
        source=str(source),
        indexed_content_sha256=indexed_content_sha256,
        provider=provider,
    )
    cache_key = str(root_identity["identity_sha256"])[:24]
    workspace = Path(tempfile.gettempdir()) / "repo-teacher-model-cache" / cache_key
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "run-identity.json").write_text(
        _json_artifact(run_identity), encoding="utf-8"
    )
    (workspace / "workspace-root-identity.json").write_text(
        _json_artifact(root_identity), encoding="utf-8"
    )
    return cache_key, workspace
