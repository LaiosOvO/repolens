"""Versioned, human-auditable records for each production report stage."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence


def _stage_record(
    journal: Mapping[str, object], stage_id: str
) -> dict[str, object]:
    stages = journal.get("stages")
    if not isinstance(stages, list):
        raise ValueError("report journal has no stage records")
    for item in stages:
        if isinstance(item, dict) and item.get("id") == stage_id:
            return copy.deepcopy(item)
    raise ValueError(f"report journal is missing stage: {stage_id}")


def _stage(
    journal: Mapping[str, object],
    stage_id: str,
    title: str,
    *,
    inputs: Sequence[str],
    outputs: Sequence[str],
    metrics: Mapping[str, object],
    quality_gates: Sequence[str],
) -> dict[str, object]:
    record = _stage_record(journal, stage_id)
    return {
        "schema_version": "repolens-stage-artifact/v1",
        "stage": stage_id,
        "title": title,
        "status": record["status"],
        "attempt": record["attempt"],
        "started_at": record["started_at"],
        "completed_at": record["completed_at"],
        "input_sha256": record["input_sha256"],
        "output_sha256": record["output_sha256"],
        "issues": record["issues"],
        "retry_stage": record["retry_stage"],
        "inputs": list(inputs),
        "outputs": list(outputs),
        "metrics": dict(metrics),
        "quality_gates": list(quality_gates),
    }


def build_report_stage_artifacts(
    *,
    canonical: Mapping[str, object],
    pack: Mapping[str, object],
    inventory: Mapping[str, object] | None,
    narrative: Mapping[str, object],
    provider: str,
    inventory_digest: str | None,
    source_manifest_sha256: str,
    journal: Mapping[str, object],
    authoritative_journal: str,
) -> dict[str, dict[str, object]]:
    """Build the persistent stage ledger published beside one report."""

    stats = canonical.get("stats") if isinstance(canonical.get("stats"), dict) else {}
    chapters = [
        item for item in narrative.get("chapters", []) if isinstance(item, dict)
    ]
    capabilities = (
        [item for item in inventory.get("capabilities", []) if isinstance(item, dict)]
        if inventory is not None
        else chapters
    )
    dispositions = (
        [item for item in inventory.get("module_dispositions", []) if isinstance(item, dict)]
        if inventory is not None
        else []
    )
    evidence_count = len(
        [item for item in canonical.get("evidence", []) if isinstance(item, dict)]
    )
    artifacts = {
        "pipeline/01-graph-index.json": _stage(
            journal,
            "01-graph-index",
            "CodeGraph 与 canonical 源码索引",
            inputs=["固定源码快照"],
            outputs=["index.json", "capability-graph.json"],
            metrics={
                "files": stats.get("files", 0),
                "symbols": stats.get("symbols", 0),
                "relationships": stats.get("relationships", 0),
                "modules": stats.get("modules", 0),
            },
            quality_gates=["源码快照稳定", "索引验证通过", "关系 ID 唯一"],
        ),
        "pipeline/02-evidence-pack.json": _stage(
            journal,
            "02-evidence-pack",
            "有界证据包与项目定位输入",
            inputs=["index.json", "capability-graph.json"],
            outputs=["analysis-pack.json", "项目定位源码切片"],
            metrics={
                "feature_hints": len(pack.get("feature_hints", [])),
                "evidence_refs": len(pack.get("evidence", [])),
                "reading_paths": len(pack.get("reading_path", [])),
            },
            quality_gates=["路径均在固定仓库内", "引用 ID 闭合", "证据包大小受限"],
        ),
        "pipeline/03-capability-inventory.json": _stage(
            journal,
            "03-capability-inventory",
            "业务能力目录与模块处置",
            inputs=["analysis-pack.json", f"provider:{provider}"],
            outputs=["capability-inventory.json"],
            metrics={
                "capabilities": len(capabilities),
                "module_dispositions": len(dispositions),
                "approved_inventory_sha256": inventory_digest or "narrative-only",
            },
            quality_gates=[
                "Schema 通过",
                "功能证据闭包",
                "模块处置闭包" if inventory is not None else "使用已审核 narrative",
            ],
        ),
        "pipeline/04-project-overview.json": {
            **_stage(
                journal,
                "04-project-overview",
                "项目定位与工程结构",
                inputs=["capability-inventory.json", "analysis-pack.json"],
                outputs=["human-report.json#project_overview"],
                metrics={},
                quality_gates=["先说项目本质", "前后端/Worker/媒体职责有证据"],
            ),
            "project_overview": narrative.get("project_overview", {}),
        },
        "pipeline/05-chapter-index.json": {
            **_stage(
                journal,
                "05-chapter-generation",
                "业务功能章节索引",
                inputs=["capability-inventory.json", "analysis-pack.json"],
                outputs=["human-report.json", "index.html"],
                metrics={"chapters": len(chapters)},
                quality_gates=["总—分—总", "交互与状态讲解", "源码证据在最后"],
            ),
            "chapters": [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "evidence_refs": len(item.get("source_refs", [])),
                }
                for item in chapters
            ],
        },
        "pipeline/06-validation-report.json": {
            **_stage(
                journal,
                "06-validation",
                "发布前验证",
                inputs=["human-report.json", "source-manifest.json"],
                outputs=["validation-report.json", "immutable generation"],
                metrics={
                    "chapters": len(chapters),
                    "canonical_evidence": evidence_count,
                    "module_dispositions": len(dispositions),
                },
                quality_gates=[
                    "canonical index valid",
                    "source manifest stable",
                    "semantic inventory validation passed",
                    "chapter schema and evidence closure passed",
                ],
            ),
            "schema_version": "repolens-validation-report/v1",
            "checks": {
                "canonical_index": "passed",
                "source_manifest": "passed",
                "inventory_schema": "passed" if inventory is not None else "narrative-only",
                "evidence_closure": "passed",
                "atomic_publication_ready": "passed",
            },
            "source_manifest_sha256": source_manifest_sha256,
            "outputs": ["run-manifest.json", "immutable generation"],
        },
    }
    artifacts["run-manifest.json"] = {
        **copy.deepcopy(dict(journal)),
        "schema_version": "repolens-pipeline-journal/v1",
        "source_manifest_sha256": source_manifest_sha256,
        "provider": provider,
        "approved_inventory_sha256": inventory_digest,
        "authoritative_journal": authoritative_journal,
        "primary_output": "index.html",
        "publication_note": (
            "This immutable snapshot was captured before the atomic current-pointer "
            "switch. The sibling authoritative journal records publication success "
            "or failure after the switch."
        ),
    }
    return artifacts
