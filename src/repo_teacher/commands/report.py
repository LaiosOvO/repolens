"""Human-first repository report application command."""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..capability_graph import build_capability_graph
from ..human_report import build_report_pack, compose_human_report
from ..indexer import build_index
from ..persistence import (
    GenerationPublisher,
    OutputLock,
    atomic_write_text,
    read_json_path,
)
from ..pipeline import (
    LinearStageArtifacts,
    consistent_repository_snapshot,
)
from ..scanner import capture_tree_manifest
from ..pipeline.journal import PipelineJournal
from ..pipeline.performance import collect_model_call_performance, write_pipeline_performance
from ..pipeline.report_outputs import build_report_output_sidecars
from ..pipeline.semantic_review import require_inventory_semantic_review
from ..renderers import render_report
from ..schemas import require_persisted_inventory


def _load_approved_inventory(
    inventory_path: Path, source_manifest_sha256: str
) -> tuple[dict[str, object], str, str]:
    """Load an inventory only when its independent review matches this snapshot."""

    approved = read_json_path(inventory_path)
    require_persisted_inventory(approved)
    if approved.get("source_manifest_sha256") != source_manifest_sha256:
        raise ValueError("approved capability inventory belongs to another source snapshot")
    validation_name = approved.get("validation_artifact")
    if (
        not isinstance(validation_name, str)
        or Path(validation_name).name != validation_name
    ):
        raise ValueError("approved capability inventory has no safe validation artifact")
    validation_path = inventory_path.with_name(validation_name)
    validation = read_json_path(validation_path)
    digest = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    if validation.get("inventory_sha256") != digest:
        raise ValueError("approved capability inventory digest does not match validation")
    if validation.get("source_manifest_sha256") != source_manifest_sha256:
        raise ValueError("approved capability validation belongs to another source snapshot")
    capabilities = [
        item for item in approved.get("capabilities", []) if isinstance(item, dict)
    ]
    capability_ids = [str(item.get("id") or "") for item in capabilities]
    require_inventory_semantic_review(validation, capability_ids)
    if validation.get("status") != "passed":
        raise ValueError("approved capability inventory did not pass semantic review")
    return approved, digest, validation_path.name


def _build_inventory_approval(
    *,
    inventory_path: Path,
    inventory_digest: str,
    validation_artifact: str,
    source_manifest_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": "repolens-inventory-approval/v1",
        "status": "approved",
        "approval_source": "--inventory",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "inventory_path": str(inventory_path.resolve()),
        "inventory_sha256": inventory_digest,
        "validation_artifact": validation_artifact,
        "source_manifest_sha256": source_manifest_sha256,
    }


@dataclass(frozen=True, slots=True)
class ReportCommandPorts:
    """Synthesis and validation policies supplied by the outer adapter."""

    prepare_codegraph: Callable[[Path], str]
    load_baseline: Callable[[Path, Path], dict[str, object] | None]
    require_valid_index: Callable[[dict[str, object], Path], None]
    model_workspace_for_pack: Callable[..., tuple[str, Path]]
    synthesize: Callable[..., dict[str, object]]
    rebind_reviewed_narrative: Callable[..., dict[str, object]]
    report_index_with_navigation_evidence: Callable[..., dict[str, object]]
    rebind_snapshot_source: Callable[..., dict[str, object]]
    bind_generation: Callable[[dict[str, object], str], dict[str, object]]
    json_artifact: Callable[[dict[str, object]], str]
    html_artifact: Callable[[str, str], str]


def run_report(
    source_arg: str,
    output_arg: str,
    narrative_arg: str | None,
    inventory_arg: str | None,
    model_timeout: int,
    provider: str,
    max_file_size: int,
    should_open: bool,
    auto_inventory: bool = False,
    *,
    ports: ReportCommandPorts,
) -> int:
    original_source = Path(source_arg).expanduser()
    if not original_source.is_dir():
        print(f"error: source is not a directory: {original_source}", file=sys.stderr)
        return 2
    original_source = original_source.resolve()
    output = Path(output_arg).expanduser().resolve()
    # A report is a complete unattended pipeline by default.  ``--inventory``
    # remains an optimization for callers that already have an approved,
    # snapshot-bound catalog; it is never a required manual checkpoint.
    auto_inventory = auto_inventory or (not narrative_arg and not inventory_arg)
    approved_inventory: dict[str, object] | None = None
    inventory_digest: str | None = None
    approved_validation_artifact: str | None = None
    approved_inventory_path: Path | None = None
    model_workspace: Path | None = None
    manifest_path = output.with_name(f"{output.name}.run-manifest.json")
    performance_path = output.with_name(f"{output.name}.performance.json")
    linear_workspace = output.with_name(f".{output.name}.pipeline")
    linear_stages = LinearStageArtifacts(linear_workspace)
    journal: PipelineJournal | None = None
    current_stage = "01-graph-index"
    linear_current_stage = "01-source-snapshot"
    pipeline_started = time.monotonic()
    try:
        with consistent_repository_snapshot(
            original_source,
            excluded_paths=(output, manifest_path, performance_path, linear_workspace),
        ) as snapshot:
            source_stage_inputs = {
                "source": str(original_source),
                "source_manifest_sha256": snapshot.source_manifest_sha256,
            }
            linear_stages.pass_stage(
                linear_current_stage,
                inputs=source_stage_inputs,
                output={
                    "source_manifest_sha256": snapshot.source_manifest_sha256,
                    "snapshot": "immutable-local-copy",
                },
                metrics={
                    "wall_duration_seconds": round(
                        time.monotonic() - pipeline_started, 6
                    )
                },
            )
            linear_current_stage = "02-code-index"
            linear_started = time.monotonic()
            source = snapshot.path
            requested_inventory_digest = (
                hashlib.sha256(Path(inventory_arg).expanduser().read_bytes()).hexdigest()
                if inventory_arg
                else None
            )
            journal = PipelineJournal(
                manifest_path,
                pipeline="report",
                run_identity={
                    "source": str(original_source),
                    "source_manifest_sha256": snapshot.source_manifest_sha256,
                    "provider": provider,
                    "inventory_sha256": requested_inventory_digest,
                    "narrative": str(Path(narrative_arg).expanduser())
                    if narrative_arg
                    else None,
                    "max_file_size": max_file_size,
                },
            )
            journal.start(
                current_stage,
                inputs={
                    "source_manifest_sha256": snapshot.source_manifest_sha256,
                    "provider": provider,
                },
            )
            print("[report 01/05] 已冻结一致源码快照；准备 CodeGraph…", flush=True)
            graph_action = ports.prepare_codegraph(source)
            print(
                f"[report 01/05] CodeGraph {graph_action} 完成；关系数据仅供索引阶段使用…",
                flush=True,
            )
            print("[report 02/05] 扫描仓库并建立符号、关系和文件索引…", flush=True)
            previous = ports.load_baseline(output, original_source)
            code_index_inputs = {
                "source_manifest_sha256": snapshot.source_manifest_sha256,
                "max_file_size": max_file_size,
            }
            if (
                previous is not None
                and capture_tree_manifest(original_source)
                == capture_tree_manifest(source)
                and linear_stages.stage_passed(
                    linear_current_stage, inputs=code_index_inputs
                )
            ):
                print("[report 02/05] 复用已校验的 CodeGraph/AST 索引…", flush=True)
                canonical = previous
            else:
                canonical = build_index(
                    source,
                    output_dir=output,
                    max_file_size=max_file_size,
                    previous_index=previous,
                    baseline_project_root=original_source,
                )
                print(
                    f"[report 02/05] 校验源码快照与索引… {canonical['stats']['files']} files, "
                    f"{canonical['stats']['symbols']} symbols",
                    flush=True,
                )
                ports.require_valid_index(canonical, source)
            journal.pass_stage(
                current_stage,
                outputs={
                    "codegraph": graph_action,
                    "analysis_fingerprint": canonical.get("analysis_fingerprint"),
                },
                metrics=canonical.get("stats")
                if isinstance(canonical.get("stats"), dict)
                else {},
            )
            current_stage = "02-evidence-pack"
            journal.start(
                current_stage,
                inputs={
                    "analysis_fingerprint": canonical.get("analysis_fingerprint")
                },
            )
            print("[report 02/05] 建立功能候选、调用关系与源码证据包…", flush=True)
            capability_graph = build_capability_graph(canonical)
            pack = build_report_pack(canonical, capability_graph)
            linear_stages.pass_stage(
                linear_current_stage,
                inputs=code_index_inputs,
                output={
                    "analysis_fingerprint": canonical.get("analysis_fingerprint"),
                    "stats": canonical.get("stats", {}),
                    "feature_hints": len(pack.get("feature_hints", [])),
                    "evidence": len(pack.get("evidence", [])),
                },
                metrics={
                    "wall_duration_seconds": round(
                        time.monotonic() - linear_started, 6
                    )
                },
            )
            linear_current_stage = "03-content-generation"
            linear_started = time.monotonic()
            journal.pass_stage(
                current_stage,
                outputs={"source_manifest_sha256": snapshot.source_manifest_sha256},
                metrics={
                    "feature_hints": len(pack.get("feature_hints", [])),
                    "evidence": len(pack.get("evidence", [])),
                    "modules": len(pack.get("modules", [])),
                },
            )
            current_stage = "03-capability-inventory"
            journal.start(
                current_stage,
                inputs={
                    "inventory_sha256": requested_inventory_digest,
                    "auto_inventory": auto_inventory,
                    "narrative_only": narrative_arg is not None,
                },
            )
            if narrative_arg:
                print("[report 03/05] 读取已生成的完整报告 JSON…", flush=True)
                narrative = ports.rebind_reviewed_narrative(
                    read_json_path(Path(narrative_arg).expanduser()), pack
                )
            else:
                content_reused = False
                print(
                    f"[report 03/05] 启动 {provider} 一次生成项目定位、核心业务功能、"
                    "底层实现和工程组织…",
                    flush=True,
                )
                if inventory_arg:
                    inventory_path = Path(inventory_arg).expanduser()
                    (
                        approved_inventory,
                        inventory_digest,
                        approved_validation_artifact,
                    ) = _load_approved_inventory(
                        inventory_path, snapshot.source_manifest_sha256
                    )
                    approved_inventory_path = inventory_path
                cache_key, model_workspace = ports.model_workspace_for_pack(
                    original_source, pack, canonical, provider, inventory_digest
                )
                effective_inventory = inventory_arg
                identity_path = model_workspace / "run-identity.json"
                run_identity = (
                    read_json_path(identity_path) if identity_path.is_file() else {}
                )
                content_inputs = {
                    "analysis_fingerprint": canonical.get("analysis_fingerprint"),
                    "source_manifest_sha256": snapshot.source_manifest_sha256,
                    "provider": provider,
                    "contract_identity": run_identity.get("identity_sha256"),
                    "approved_inventory_sha256": inventory_digest,
                }
                content_cache = linear_workspace / "content" / "human-report.json"
                if (
                    content_cache.is_file()
                    and linear_stages.stage_passed(
                        linear_current_stage, inputs=content_inputs
                    )
                ):
                    content_reused = True
                    print(
                        f"[report 03/05] 复用通过校验的完整内容产物：{cache_key}",
                        flush=True,
                    )
                    narrative = read_json_path(content_cache)
                else:
                    synthesis_args = (
                        source,
                        pack,
                        model_workspace,
                        model_timeout,
                        effective_inventory,
                    )
                    narrative = (
                        ports.synthesize(*synthesis_args)
                        if provider == "codex"
                        else ports.synthesize(*synthesis_args, provider)
                    )
                    content_cache.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_text(
                        content_cache, ports.json_artifact(narrative)
                    )
                # Content cache stores the model result; rebinding is a
                # deterministic stage-04 operation. This makes validation
                # fixes reusable without spending another model call.
                narrative = ports.rebind_reviewed_narrative(narrative, pack)
                if approved_inventory is None:
                    generated_inventory = model_workspace / "capability-inventory.json"
                    if generated_inventory.is_file():
                        approved_inventory = read_json_path(generated_inventory)
                        inventory_digest = hashlib.sha256(
                            generated_inventory.read_bytes()
                        ).hexdigest()

            linear_stages.pass_stage(
                linear_current_stage,
                inputs=(
                    content_inputs
                    if not narrative_arg
                    else {
                        "analysis_fingerprint": canonical.get("analysis_fingerprint"),
                        "narrative": str(Path(narrative_arg).expanduser()),
                    }
                ),
                output={
                    "artifact": "human-report.json",
                    "chapters": len(narrative.get("chapters", [])),
                    "has_project_overview": isinstance(
                        (narrative.get("project") or {}).get("overview"), dict
                    )
                    if isinstance(narrative.get("project"), dict)
                    else False,
                },
                metrics={
                    "wall_duration_seconds": round(
                        time.monotonic() - linear_started, 6
                    ),
                    "model_calls": (
                        0
                        if narrative_arg or content_reused
                        else 1
                    ),
                    "cache_reused": (
                        False if narrative_arg else content_reused
                    ),
                },
            )
            linear_current_stage = "04-evidence-validation"

            journal.pass_stage(
                current_stage,
                outputs={
                    "inventory_sha256": inventory_digest or "narrative-only",
                    "inventory_source": "approved"
                    if approved_inventory_path is not None
                    else "generated-or-narrative",
                },
                metrics={
                    "capabilities": len(approved_inventory.get("capabilities", []))
                    if isinstance(approved_inventory, dict)
                    else len(narrative.get("chapters", [])),
                    **(
                        collect_model_call_performance(model_workspace)
                        if model_workspace is not None
                        else {}
                    ),
                },
            )
            contract_identity = {}
            if model_workspace is not None:
                identity_path = model_workspace / "run-identity.json"
                if identity_path.is_file():
                    contract_identity = read_json_path(identity_path)
            current_stage = "04-project-overview"
            journal.start(
                current_stage,
                inputs={"inventory_sha256": inventory_digest or "narrative-only"},
                contract_identity=contract_identity,
            )
            narrative_project = narrative.get("project")
            overview = (
                narrative_project.get("overview")
                if isinstance(narrative_project, dict)
                else None
            )
            if not isinstance(overview, dict) or not overview:
                raise ValueError("human report has no project overview")
            journal.pass_stage(
                current_stage,
                outputs={"project_overview": "human-report.json#project_overview"},
            )
            current_stage = "05-chapter-generation"
            journal.start(
                current_stage,
                inputs={"inventory_sha256": inventory_digest or "narrative-only"},
                contract_identity=contract_identity,
            )
            chapters = [
                item
                for item in narrative.get("chapters", [])
                if isinstance(item, dict)
            ]
            if not chapters:
                raise ValueError("human report has no business capability chapters")
            journal.pass_stage(
                current_stage,
                outputs={"chapters": [str(item.get("id") or "") for item in chapters]},
                metrics={"chapters": len(chapters)},
            )

            canonical = ports.rebind_snapshot_source(
                canonical,
                snapshot_path=source,
                original_source=original_source,
                source_manifest_sha256=snapshot.source_manifest_sha256,
            )
            pack = ports.rebind_snapshot_source(
                pack,
                snapshot_path=source,
                original_source=original_source,
            )
            print("[report 04/05] 校验内容 Schema、源码路径、行号和证据闭包…", flush=True)
            linear_started = time.monotonic()
            current_stage = "06-validation"
            journal.start(
                current_stage,
                inputs={
                    "chapters": len(chapters),
                    "source_manifest_sha256": snapshot.source_manifest_sha256,
                },
                contract_identity=contract_identity,
            )
            report_index = ports.report_index_with_navigation_evidence(canonical, pack)
            composed = compose_human_report(report_index, narrative)
            output_sidecars = build_report_output_sidecars(
                narrative=narrative,
                source_manifest_sha256=snapshot.source_manifest_sha256,
                inventory_digest=inventory_digest,
            )
            linear_stages.pass_stage(
                linear_current_stage,
                inputs={
                    "chapters": len(chapters),
                    "source_manifest_sha256": snapshot.source_manifest_sha256,
                },
                output={
                    "validation_report": output_sidecars.get(
                        "validation-report.json", {}
                    )
                },
                metrics={
                    "wall_duration_seconds": round(
                        time.monotonic() - linear_started, 6
                    )
                },
            )
            journal.pass_stage(
                current_stage,
                outputs={
                    "validation_report": "validation-report.json",
                },
                metrics={
                    "chapters": len(chapters),
                    "sidecars": len(output_sidecars),
                },
            )
            generation_id = secrets.token_hex(16)
            canonical = ports.bind_generation(canonical, generation_id)
            pack = ports.bind_generation(pack, generation_id)
            narrative = ports.bind_generation(narrative, generation_id)
            composed = ports.bind_generation(composed, generation_id)
            artifacts = {
                "index.json": ports.json_artifact(canonical),
                "analysis-pack.json": ports.json_artifact(pack),
                "human-report.json": ports.json_artifact(narrative),
                "capability-graph.json": ports.json_artifact(
                    ports.bind_generation(capability_graph, generation_id)
                ),
                "index.html": ports.html_artifact(
                    render_report(composed), generation_id
                ),
            }
            if approved_inventory is not None:
                artifacts["capability-inventory.json"] = ports.json_artifact(
                    ports.bind_generation(approved_inventory, generation_id)
                )
            if (
                approved_inventory_path is not None
                and inventory_digest is not None
                and approved_validation_artifact is not None
            ):
                artifacts["approval.json"] = ports.json_artifact(
                    ports.bind_generation(
                        _build_inventory_approval(
                            inventory_path=approved_inventory_path,
                            inventory_digest=inventory_digest,
                            validation_artifact=approved_validation_artifact,
                            source_manifest_sha256=snapshot.source_manifest_sha256,
                        ),
                        generation_id,
                    )
                )
            current_stage = "atomic-publication"
            linear_current_stage = "05-publication"
            publication_started = time.monotonic()
            journal.start(
                current_stage,
                inputs={
                    "generation_id": generation_id,
                    "artifacts": sorted(artifacts),
                },
            )
            artifacts.update(
                {
                    path: ports.json_artifact(
                        ports.bind_generation(payload, generation_id)
                    )
                    for path, payload in output_sidecars.items()
                }
            )
            with OutputLock(output):
                print("[report 05/05] 原子发布 JSON 与人类可读 HTML…", flush=True)
                GenerationPublisher(output, generation_id).publish(artifacts)
            journal.pass_stage(
                current_stage,
                outputs={"generation_id": generation_id, "current": generation_id},
            )
            linear_stages.pass_stage(
                linear_current_stage,
                inputs={"generation_id": generation_id},
                output={
                    "generation_id": generation_id,
                    "index.html": str(output / "index.html"),
                },
                metrics={
                    "wall_duration_seconds": round(
                        time.monotonic() - publication_started, 6
                    )
                },
            )
            # The immutable generation is the product artifact; the fixed
            # stage ledger is the observable execution artifact.  Publishing
            # it after the atomic switch avoids a circular dependency between
            # the publication record and the generation manifest itself.
            journal.complete(
                outputs={
                    "generation_id": generation_id,
                    "index.html": str(output / "index.html"),
                }
            )
            write_pipeline_performance(performance_path, journal.snapshot())
            atomic_write_text(
                performance_path,
                linear_stages.performance_path.read_text(encoding="utf-8"),
            )
    except KeyboardInterrupt:
        linear_stages.fail_stage(
            linear_current_stage,
            inputs={"source": str(original_source)},
            error="report pipeline was interrupted",
        )
        if journal is not None:
            journal.fail_stage(
                current_stage,
                code="interrupted",
                message="report pipeline was interrupted",
            )
            write_pipeline_performance(performance_path, journal.snapshot())
        print("error: report generation was interrupted", file=sys.stderr)
        return 130
    except subprocess.TimeoutExpired:
        linear_stages.fail_stage(
            linear_current_stage,
            inputs={"source": str(original_source)},
            error="report synthesis timed out",
        )
        if journal is not None:
            journal.fail_stage(
                current_stage,
                code="provider-timeout",
                message="report synthesis timed out",
            )
            write_pipeline_performance(performance_path, journal.snapshot())
        print("error: Codex synthesis timed out", file=sys.stderr)
        return 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        linear_stages.fail_stage(
            linear_current_stage,
            inputs={"source": str(original_source)},
            error=str(error),
        )
        if journal is not None:
            journal.fail_stage(
                current_stage,
                code="stage-failed",
                message=str(error),
            )
            write_pipeline_performance(performance_path, journal.snapshot())
        atomic_write_text(
            performance_path,
            linear_stages.performance_path.read_text(encoding="utf-8"),
        )
        print(f"error: failed to generate human report: {error}", file=sys.stderr)
        return 1
    report_path = output / "index.html"
    print(f"Generated human-first repository report: {report_path}")
    print(f"Performance analysis: {performance_path}")
    print(f"Capabilities: {len(composed['features'])}; evidence refs: {len(canonical['evidence'])}")
    if should_open:
        webbrowser.open(report_path.as_uri())
    return 0
