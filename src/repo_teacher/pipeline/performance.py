"""Generic stage timing summary derived from a pipeline journal."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Mapping

from ..persistence import atomic_write_text
from .serialization import json_artifact


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _duration_seconds(started_at: object, completed_at: object) -> float | None:
    started = _parse_timestamp(started_at)
    completed = _parse_timestamp(completed_at)
    if started is None or completed is None:
        return None
    return round(max((completed - started).total_seconds(), 0.0), 6)


def _mapping(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _cache_fields(*sections: object) -> dict[str, object] | None:
    cache: dict[str, object] = {}
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        for key, value in section.items():
            if "cache" in str(key).lower():
                cache[str(key)] = copy.deepcopy(value)
    return cache or None


def _stage_summary(stage: Mapping[str, object], journal_updated_at: object) -> dict[str, object]:
    duration_seconds = stage.get("duration_seconds")
    if not isinstance(duration_seconds, (int, float)):
        duration_seconds = _duration_seconds(
            stage.get("started_at"),
            stage.get("completed_at") or journal_updated_at,
        )
    summary = {
        "id": str(stage.get("id") or ""),
        "status": stage.get("status"),
        "attempt": int(stage.get("attempt", 0) or 0),
        "started_at": stage.get("started_at"),
        "completed_at": stage.get("completed_at"),
        "duration_seconds": (
            round(float(duration_seconds), 6)
            if isinstance(duration_seconds, (int, float))
            else None
        ),
        "retry_stage": stage.get("retry_stage"),
        "issues": copy.deepcopy(list(stage.get("issues", [])))
        if isinstance(stage.get("issues"), list)
        else [],
        "metrics": _mapping(stage.get("metrics")),
    }
    cache = _cache_fields(
        stage.get("inputs"),
        stage.get("outputs"),
        stage.get("metrics"),
        stage.get("contract_identity"),
    )
    if cache is not None:
        summary["cache"] = cache
    return summary


def collect_model_call_performance(workspace: Path) -> dict[str, object]:
    """Collect bounded, non-secret provider timing records from a run workspace."""

    calls: list[dict[str, object]] = []
    if workspace.is_dir():
        for path in sorted(workspace.rglob("*-performance.json"))[:1_000]:
            if path.name in {"performance.json", "inventory-shards-performance.json"}:
                continue
            try:
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 64_000:
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            if (
                not isinstance(payload, dict)
                or payload.get("schema_version")
                != "repolens-model-call-performance/v1"
            ):
                continue
            calls.append(
                {
                    key: copy.deepcopy(payload.get(key))
                    for key in (
                        "stage",
                        "provider",
                        "model",
                        "reasoning_effort",
                        "status",
                        "duration_seconds",
                        "prompt_bytes",
                        "schema_bytes",
                        "packet_bytes",
                        "estimated_tokens",
                        "queue_seconds",
                        "cache_reused",
                        "repair_used",
                    )
                    if key in payload
                }
            )
    durations = [
        float(item["duration_seconds"])
        for item in calls
        if isinstance(item.get("duration_seconds"), (int, float))
    ]
    result: dict[str, object] = {
        "model_calls": len(calls),
        "model_calls_passed": sum(item.get("status") == "passed" for item in calls),
        "model_calls_failed": sum(item.get("status") == "failed" for item in calls),
        "model_call_seconds": round(sum(durations), 6),
        "model_calls_detail": calls,
    }
    shard_summary_path = workspace / "inventory" / "inventory-shards-performance.json"
    if not shard_summary_path.is_file():
        shard_summary_path = workspace / "inventory-shards-performance.json"
    if shard_summary_path.is_file() and shard_summary_path.stat().st_size <= 1_000_000:
        try:
            shard_summary = json.loads(shard_summary_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            shard_summary = None
        if isinstance(shard_summary, dict):
            result["shard_parallelism"] = copy.deepcopy(shard_summary)
    return result


def build_pipeline_performance(journal: Mapping[str, object]) -> dict[str, object]:
    """Return a backward-compatible machine summary for one pipeline journal."""

    stages_raw = journal.get("stages")
    stages: list[dict[str, object]] = []
    if isinstance(stages_raw, list):
        stages = [
            _stage_summary(item, journal.get("updated_at"))
            for item in stages_raw
            if isinstance(item, Mapping)
        ]

    wall_duration_seconds = _duration_seconds(
        journal.get("created_at"),
        journal.get("completed_at") or journal.get("updated_at"),
    )
    longest_stage = max(
        (
            stage
            for stage in stages
            if isinstance(stage.get("duration_seconds"), (int, float))
        ),
        key=lambda item: float(item["duration_seconds"]),
        default=None,
    )
    return {
        "schema_version": "repolens-pipeline-performance/v1",
        "pipeline": journal.get("pipeline"),
        "status": journal.get("status"),
        "created_at": journal.get("created_at"),
        "updated_at": journal.get("updated_at"),
        "completed_at": journal.get("completed_at"),
        "current_stage": journal.get("current_stage"),
        "retry_stage": journal.get("retry_stage"),
        "wall_duration_seconds": (
            round(float(wall_duration_seconds), 6)
            if isinstance(wall_duration_seconds, (int, float))
            else None
        ),
        "longest_stage": copy.deepcopy(longest_stage),
        "stages": stages,
    }


def write_pipeline_performance(
    path: Path, journal: Mapping[str, object]
) -> dict[str, object]:
    """Persist a pipeline performance summary atomically and return it."""

    summary = build_pipeline_performance(journal)
    atomic_write_text(path, json_artifact(summary))
    return summary
