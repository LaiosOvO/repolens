"""Business-capability inventory application command."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..capability_graph import build_capability_graph
from ..human_report import build_report_pack
from ..indexer import build_index
from ..persistence import atomic_write_text, read_json_path
from ..pipeline import consistent_repository_snapshot
from ..pipeline.cache_identity import packaged_contract_digests, provider_model_identity
from ..pipeline.journal import PipelineJournal
from ..pipeline.performance import collect_model_call_performance, write_pipeline_performance
from ..pipeline.semantic_review import require_inventory_semantic_review
from ..schemas import require_persisted_inventory


@dataclass(frozen=True, slots=True)
class InventoryCommandPorts:
    """Provider and policy ports composed by the outer CLI adapter."""

    prepare_codegraph: Callable[[Path], str]
    require_valid_index: Callable[[dict[str, object], Path], None]
    model_workspace_for_pack: Callable[..., tuple[str, Path]]
    synthesize: Callable[..., dict[str, object]]
    json_artifact: Callable[[dict[str, object]], str]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _copy_file_checkpoint(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str | None = None,
) -> str:
    """Copy one immutable regular-file checkpoint with digest verification."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(source, flags)
    except OSError as error:
        raise ValueError(f"pipeline checkpoint is missing: {source.name}") from error
    temporary_path: str | None = None
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise ValueError(f"pipeline checkpoint is not a regular file: {source.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_fd, temporary_path = tempfile.mkstemp(
            prefix=f".{destination.name}.checkpoint-",
            dir=destination.parent,
        )
        digest = hashlib.sha256()
        try:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(temporary_fd, view)
                    view = view[written:]
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)
        actual_sha256 = digest.hexdigest()
        if expected_sha256 is not None and actual_sha256 != expected_sha256:
            raise ValueError(f"pipeline checkpoint digest changed: {source.name}")
        os.replace(temporary_path, destination)
        temporary_path = None
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return actual_sha256
    finally:
        os.close(source_fd)
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def _write_json_checkpoint(
    path: Path,
    payload: dict[str, object],
    json_artifact: Callable[[dict[str, object]], str],
) -> str:
    text = json_artifact(payload)
    atomic_write_text(path, text)
    return _sha256_text(text)


def _stage_checkpoint_sha(
    journal: PipelineJournal,
    stage_id: str,
    key: str = "checkpoint_sha256",
) -> str | None:
    stages = journal.snapshot().get("stages")
    if not isinstance(stages, list):
        return None
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("id") != stage_id:
            continue
        outputs = stage.get("outputs")
        if isinstance(outputs, dict) and isinstance(outputs.get(key), str):
            return str(outputs[key])
    return None


def _read_json_checkpoint(path: Path, expected_sha256: str | None) -> dict[str, object]:
    if not expected_sha256 or not path.is_file():
        raise ValueError(f"pipeline checkpoint is missing: {path.name}")
    text = path.read_text(encoding="utf-8")
    if _sha256_text(text) != expected_sha256:
        raise ValueError(f"pipeline checkpoint digest changed: {path.name}")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"pipeline checkpoint is not a JSON object: {path.name}")
    return payload


def _restart_stage_after_bad_checkpoint(
    journal: PipelineJournal,
    stage_id: str,
    *,
    inputs: dict[str, object],
    error: ValueError,
) -> None:
    journal.fail_stage(
        stage_id,
        code="checkpoint-invalid",
        message=str(error),
        retry_stage=stage_id,
    )
    journal.start(stage_id, inputs=inputs)


def _load_semantic_validation(
    model_workspace: Path, capability_ids: list[str]
) -> dict[str, object]:
    semantic_validation_path = model_workspace / "inventory-validation.json"
    if not semantic_validation_path.is_file():
        raise ValueError(
            "independent capability semantic review artifact is missing"
        )
    semantic_validation = read_json_path(semantic_validation_path)
    require_inventory_semantic_review(semantic_validation, capability_ids)
    if semantic_validation.get("status") != "passed":
        issues = semantic_validation.get("issues")
        issue_codes = ", ".join(
            sorted(
                {
                    str(item.get("code") or "semantic-review-failed")
                    for item in issues
                    if isinstance(item, dict)
                }
            )
        )
        raise ValueError(
            "independent capability semantic review failed"
            + (f": {issue_codes}" if issue_codes else "")
        )
    return semantic_validation


def _publish_validation(
    semantic_validation: dict[str, object],
    *,
    source_manifest_sha256: str,
    inventory_sha256: str,
    cache_key: str,
    capabilities: list[dict[str, object]],
    dispositions: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "repolens-inventory-validation/v1",
        "status": "passed",
        "reviewer": semantic_validation.get("reviewer", "capability-reviewer"),
        "source_manifest_sha256": source_manifest_sha256,
        "inventory_sha256": inventory_sha256,
        "cache_key": cache_key,
        "checks": semantic_validation["checks"],
        "reviewed_capability_ids": semantic_validation["reviewed_capability_ids"],
        "issues": semantic_validation["issues"],
        "metrics": {
            "capabilities": len(capabilities),
            "module_dispositions": len(dispositions),
            "source_refs": sum(
                len(item.get("source_refs", [])) for item in capabilities
            ),
        },
    }


def run_inventory(
    source_arg: str,
    output_arg: str,
    model_timeout: int,
    provider: str,
    max_file_size: int,
    *,
    ports: InventoryCommandPorts,
) -> int:
    original_source = Path(source_arg).expanduser()
    if not original_source.is_dir():
        print(f"error: source is not a directory: {original_source}", file=sys.stderr)
        return 2
    original_source = original_source.resolve()
    output = Path(output_arg).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    validation_path = output.with_name(f"{output.stem}.validation.json")
    manifest_path = output.with_name(f"{output.stem}.run-manifest.json")
    performance_path = output.with_name(f"{output.stem}.performance.json")
    checkpoint_dir = output.with_name(f".{output.stem}.checkpoints")
    canonical_checkpoint = checkpoint_dir / "canonical-index.json"
    graph_checkpoint = checkpoint_dir / "capability-graph.json"
    codegraph_checkpoint = checkpoint_dir / "codegraph.db"
    pack_checkpoint = checkpoint_dir / "evidence-pack.json"
    journal: PipelineJournal | None = None
    current_stage = "source-snapshot"
    try:
        with consistent_repository_snapshot(
            original_source,
            excluded_paths=(
                output,
                validation_path,
                manifest_path,
                performance_path,
                checkpoint_dir,
            ),
        ) as snapshot:
            source = snapshot.path
            contract_digests = packaged_contract_digests()
            model_identity = provider_model_identity(provider)
            journal = PipelineJournal(
                manifest_path,
                pipeline="inventory",
                run_identity={
                    "source": str(original_source),
                    "source_manifest_sha256": snapshot.source_manifest_sha256,
                    "provider": provider,
                    "provider_model": model_identity,
                    "contracts": contract_digests,
                    "max_file_size": max_file_size,
                },
            )
            source_started = journal.start(
                "source-snapshot",
                inputs={"source": str(original_source)},
            )
            if source_started:
                journal.pass_stage(
                    "source-snapshot",
                    outputs={
                        "source_manifest_sha256": snapshot.source_manifest_sha256
                    },
                )
            current_stage = "codegraph-index"
            graph_started = journal.start(
                current_stage,
                inputs={"source_manifest_sha256": snapshot.source_manifest_sha256},
            )
            if not graph_started:
                try:
                    _copy_file_checkpoint(
                        codegraph_checkpoint,
                        source / ".codegraph" / "codegraph.db",
                        expected_sha256=_stage_checkpoint_sha(
                            journal,
                            current_stage,
                            "codegraph_checkpoint_sha256",
                        ),
                    )
                    graph_action = "restored"
                except ValueError as error:
                    _restart_stage_after_bad_checkpoint(
                        journal,
                        current_stage,
                        inputs={
                            "source_manifest_sha256": snapshot.source_manifest_sha256
                        },
                        error=error,
                    )
                    graph_started = True
            if graph_started:
                print("[inventory 0/4] 已冻结一致源码快照；准备 CodeGraph…", flush=True)
                graph_action = ports.prepare_codegraph(source)
                codegraph_sha256 = _copy_file_checkpoint(
                    source / ".codegraph" / "codegraph.db",
                    codegraph_checkpoint,
                )
                journal.pass_stage(
                    current_stage,
                    outputs={
                        "action": graph_action,
                        "codegraph_checkpoint": str(codegraph_checkpoint),
                        "codegraph_checkpoint_sha256": codegraph_sha256,
                    },
                )
            print(
                f"[inventory 0/4] CodeGraph {graph_action} 完成；"
                "开始按关系图发现业务功能…",
                flush=True,
            )
            excluded_output = output.parent if output.parent != source else output
            current_stage = "canonical-index"
            canonical_inputs = {
                "source_manifest_sha256": snapshot.source_manifest_sha256,
                "max_file_size": max_file_size,
            }
            canonical_started = journal.start(
                current_stage,
                inputs=canonical_inputs,
            )
            if not canonical_started:
                try:
                    canonical = _read_json_checkpoint(
                        canonical_checkpoint,
                        _stage_checkpoint_sha(journal, current_stage),
                    )
                    ports.require_valid_index(canonical, source)
                    capability_graph = _read_json_checkpoint(
                        graph_checkpoint,
                        _stage_checkpoint_sha(
                            journal, current_stage, "graph_checkpoint_sha256"
                        ),
                    )
                except ValueError as error:
                    _restart_stage_after_bad_checkpoint(
                        journal, current_stage, inputs=canonical_inputs, error=error
                    )
                    canonical_started = True
            if canonical_started:
                print("[inventory 1/4] 建立 canonical 源码索引与能力图…", flush=True)
                canonical = build_index(
                    source,
                    output_dir=excluded_output,
                    max_file_size=max_file_size,
                )
                ports.require_valid_index(canonical, source)
                capability_graph = build_capability_graph(canonical)
                canonical_sha256 = _write_json_checkpoint(
                    canonical_checkpoint, canonical, ports.json_artifact
                )
                graph_sha256 = _write_json_checkpoint(
                    graph_checkpoint, capability_graph, ports.json_artifact
                )
                journal.pass_stage(
                    current_stage,
                    outputs={
                        "analysis_fingerprint": canonical.get("analysis_fingerprint"),
                        "files": canonical.get("stats", {}).get("files")
                        if isinstance(canonical.get("stats"), dict)
                        else None,
                        "checkpoint": str(canonical_checkpoint),
                        "checkpoint_sha256": canonical_sha256,
                        "graph_checkpoint": str(graph_checkpoint),
                        "graph_checkpoint_sha256": graph_sha256,
                    },
                )
            current_stage = "evidence-pack"
            pack_inputs = {
                "analysis_fingerprint": canonical.get("analysis_fingerprint")
            }
            pack_started = journal.start(
                current_stage,
                inputs=pack_inputs,
            )
            if not pack_started:
                try:
                    pack = _read_json_checkpoint(
                        pack_checkpoint,
                        _stage_checkpoint_sha(journal, current_stage),
                    )
                except ValueError as error:
                    _restart_stage_after_bad_checkpoint(
                        journal, current_stage, inputs=pack_inputs, error=error
                    )
                    pack_started = True
            if pack_started:
                pack = build_report_pack(canonical, capability_graph)
                print("[inventory 2/4] 构建全局 CodeGraph 证据包…", flush=True)
                pack_sha256 = _write_json_checkpoint(
                    pack_checkpoint, pack, ports.json_artifact
                )
                journal.pass_stage(
                    current_stage,
                    outputs={
                        "checkpoint": str(pack_checkpoint),
                        "checkpoint_sha256": pack_sha256,
                    },
                    metrics={
                        "feature_hints": len(pack.get("feature_hints", [])),
                        "evidence": len(pack.get("evidence", [])),
                    },
                )
            cache_key, model_workspace = ports.model_workspace_for_pack(
                original_source, pack, canonical, provider
            )
            run_identity_path = model_workspace / "run-identity.json"
            contract_identity = (
                read_json_path(run_identity_path) if run_identity_path.is_file() else {}
            )
            current_stage = "capability-inventory"
            inventory_inputs = {"cache_key": cache_key}
            inventory_started = journal.start(
                current_stage,
                inputs=inventory_inputs,
                contract_identity=contract_identity,
            )
            workspace_inventory = model_workspace / "capability-inventory.json"
            if not inventory_started:
                try:
                    inventory_payload = _read_json_checkpoint(
                        workspace_inventory,
                        _stage_checkpoint_sha(journal, current_stage),
                    )
                except ValueError as error:
                    _restart_stage_after_bad_checkpoint(
                        journal, current_stage, inputs=inventory_inputs, error=error
                    )
                    inventory_started = True
            if inventory_started:
                inventory_payload = ports.synthesize(
                    source,
                    pack,
                    model_workspace,
                    model_timeout,
                    None,
                    provider,
                    inventory_only=True,
                )
                inventory_checkpoint_sha256 = _write_json_checkpoint(
                    workspace_inventory, inventory_payload, ports.json_artifact
                )
                journal.pass_stage(
                    current_stage,
                    outputs={
                        "workspace_inventory": str(workspace_inventory),
                        "checkpoint_sha256": inventory_checkpoint_sha256,
                    },
                    metrics=collect_model_call_performance(model_workspace),
                )
            project = dict(pack.get("project", {}))
            project["path"] = str(original_source)
            inventory_payload["project"] = project
            inventory_payload["source_manifest_sha256"] = snapshot.source_manifest_sha256
            inventory_payload["cache_key"] = cache_key
            capabilities = [
                item
                for item in inventory_payload.get("capabilities", [])
                if isinstance(item, dict)
            ]
            dispositions = [
                item
                for item in inventory_payload.get("module_dispositions", [])
                if isinstance(item, dict)
            ]
            if not capabilities or not dispositions:
                raise ValueError(
                    "capability inventory must contain capabilities and module dispositions"
                )
            inventory_payload["validation_artifact"] = validation_path.name
            require_persisted_inventory(inventory_payload)
            inventory_text = ports.json_artifact(inventory_payload)
            inventory_sha256 = hashlib.sha256(inventory_text.encode("utf-8")).hexdigest()
            capability_ids = [str(item.get("id") or "") for item in capabilities]
            current_stage = "independent-semantic-review"
            journal.start(
                current_stage,
                inputs={
                    "inventory_sha256": inventory_sha256,
                    "capability_ids": capability_ids,
                },
                contract_identity=contract_identity,
            )
            semantic_validation = _load_semantic_validation(
                model_workspace, capability_ids
            )
            validation = _publish_validation(
                semantic_validation,
                source_manifest_sha256=snapshot.source_manifest_sha256,
                inventory_sha256=inventory_sha256,
                cache_key=cache_key,
                capabilities=capabilities,
                dispositions=dispositions,
            )
            journal.pass_stage(
                current_stage,
                outputs={"validation_status": validation["status"]},
                metrics=validation["metrics"],
            )
            current_stage = "publication"
            journal.start(
                current_stage,
                inputs={
                    "inventory_sha256": inventory_sha256,
                    "validation_status": validation["status"],
                },
            )
            atomic_write_text(validation_path, ports.json_artifact(validation))
            atomic_write_text(output, inventory_text)
            validation_sha256 = hashlib.sha256(
                ports.json_artifact(validation).encode("utf-8")
            ).hexdigest()
            journal.pass_stage(
                current_stage,
                outputs={
                    output.name: inventory_sha256,
                    validation_path.name: validation_sha256,
                },
            )
            journal.complete(
                outputs={
                    output.name: inventory_sha256,
                    validation_path.name: validation_sha256,
                }
            )
            write_pipeline_performance(performance_path, journal.snapshot())
    except KeyboardInterrupt:
        if journal is not None:
            journal.fail_stage(
                current_stage,
                code="interrupted",
                message="inventory pipeline was interrupted",
            )
            write_pipeline_performance(performance_path, journal.snapshot())
        print("error: capability inventory was interrupted", file=sys.stderr)
        return 130
    except subprocess.TimeoutExpired:
        if journal is not None:
            journal.fail_stage(
                current_stage,
                code="provider-timeout",
                message="capability inventory synthesis timed out",
            )
            write_pipeline_performance(performance_path, journal.snapshot())
        print("error: capability inventory synthesis timed out", file=sys.stderr)
        return 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        if journal is not None:
            journal.fail_stage(
                current_stage,
                code="stage-failed",
                message=str(error),
            )
            write_pipeline_performance(performance_path, journal.snapshot())
        print(f"error: failed to discover capability inventory: {error}", file=sys.stderr)
        return 1
    print(f"[inventory 4/4] 功能清单已写入：{output}")
    print(f"Validation: {validation_path}")
    print(f"Run manifest: {manifest_path}")
    print(f"Performance: {performance_path}")
    print(f"Capabilities: {len(capabilities)}")
    for position, capability in enumerate(capabilities, start=1):
        print(f"{position:02d}. {capability.get('title')}")
    return 0
