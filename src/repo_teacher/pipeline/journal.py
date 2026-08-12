"""Durable state machine for resumable RepoLens command pipelines."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from ..persistence import atomic_write_text, read_json_path
from .serialization import json_artifact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def digest_mapping(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PipelineJournal:
    """Atomic started/passed/failed records for one source/config identity."""

    def __init__(
        self,
        path: Path,
        *,
        pipeline: str,
        run_identity: Mapping[str, object],
    ) -> None:
        self.path = path
        self.identity = copy.deepcopy(dict(run_identity))
        self.identity_sha256 = digest_mapping(self.identity)
        self.payload = self._load_or_create(pipeline)
        self._persist()

    def _load_or_create(self, pipeline: str) -> dict[str, object]:
        if self.path.is_file():
            try:
                existing = read_json_path(self.path)
                if (
                    existing.get("schema_version") == "repolens-pipeline-journal/v1"
                    and existing.get("pipeline") == pipeline
                    and existing.get("run_identity_sha256") == self.identity_sha256
                    and isinstance(existing.get("stages"), list)
                ):
                    return existing
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                pass
        created = _now()
        return {
            "schema_version": "repolens-pipeline-journal/v1",
            "pipeline": pipeline,
            "status": "started",
            "created_at": created,
            "updated_at": created,
            "run_identity": self.identity,
            "run_identity_sha256": self.identity_sha256,
            "current_stage": None,
            "retry_stage": None,
            "stages": [],
        }

    def _persist(self) -> None:
        self.payload["updated_at"] = _now()
        atomic_write_text(self.path, json_artifact(self.payload))

    def _stage(self, stage_id: str) -> dict[str, object] | None:
        stages = self.payload.get("stages")
        assert isinstance(stages, list)
        return next(
            (
                item
                for item in stages
                if isinstance(item, dict) and item.get("id") == stage_id
            ),
            None,
        )

    def start(
        self,
        stage_id: str,
        *,
        inputs: Mapping[str, object],
        contract_identity: Mapping[str, object] | None = None,
    ) -> bool:
        """Start or retry a stage; return False for a verified prior PASS."""

        input_sha256 = digest_mapping(inputs)
        existing = self._stage(stage_id)
        if (
            existing is not None
            and existing.get("status") == "passed"
            and existing.get("input_sha256") == input_sha256
        ):
            self.payload["current_stage"] = stage_id
            self.payload["status"] = "started"
            self._persist()
            return False
        attempt = int(existing.get("attempt", 0)) + 1 if existing else 1
        record = {
            "id": stage_id,
            "status": "started",
            "attempt": attempt,
            "started_at": _now(),
            "completed_at": None,
            "duration_seconds": None,
            "inputs": copy.deepcopy(dict(inputs)),
            "input_sha256": input_sha256,
            "contract_identity": copy.deepcopy(dict(contract_identity or {})),
            "outputs": {},
            "output_sha256": None,
            "metrics": {},
            "issues": [],
            "retry_stage": stage_id,
        }
        stages = self.payload["stages"]
        assert isinstance(stages, list)
        if existing is None:
            stages.append(record)
        else:
            stages[stages.index(existing)] = record
        self.payload["status"] = "started"
        self.payload["current_stage"] = stage_id
        self.payload["retry_stage"] = stage_id
        self._persist()
        return True

    def pass_stage(
        self,
        stage_id: str,
        *,
        outputs: Mapping[str, object],
        metrics: Mapping[str, object] | None = None,
    ) -> None:
        record = self._stage(stage_id)
        if record is None or record.get("status") not in {"started", "passed"}:
            raise ValueError(f"pipeline stage was not started: {stage_id}")
        record["status"] = "passed"
        record["completed_at"] = _now()
        record["duration_seconds"] = _duration_seconds(
            record.get("started_at"), record.get("completed_at")
        )
        record["outputs"] = copy.deepcopy(dict(outputs))
        record["output_sha256"] = digest_mapping(outputs)
        record["metrics"] = copy.deepcopy(dict(metrics or {}))
        record["issues"] = []
        record["retry_stage"] = "none"
        self.payload["status"] = "started"
        self.payload["current_stage"] = None
        self.payload["retry_stage"] = None
        self._persist()

    def fail_stage(
        self,
        stage_id: str,
        *,
        code: str,
        message: str,
        retry_stage: str | None = None,
    ) -> None:
        record = self._stage(stage_id)
        if record is None:
            self.start(stage_id, inputs={"implicit": True})
            record = self._stage(stage_id)
            assert record is not None
        target = retry_stage or stage_id
        record["status"] = "failed"
        record["completed_at"] = _now()
        record["duration_seconds"] = _duration_seconds(
            record.get("started_at"), record.get("completed_at")
        )
        record["issues"] = [{"code": code, "message": message}]
        record["retry_stage"] = target
        self.payload["status"] = "failed"
        self.payload["current_stage"] = stage_id
        self.payload["retry_stage"] = target
        self._persist()

    def complete(self, *, outputs: Mapping[str, object]) -> None:
        stages = self.payload.get("stages")
        if not isinstance(stages, list) or any(
            not isinstance(item, dict) or item.get("status") != "passed"
            for item in stages
        ):
            raise ValueError("cannot complete a pipeline with unfinished stages")
        self.payload["status"] = "passed"
        self.payload["current_stage"] = None
        self.payload["retry_stage"] = "none"
        self.payload["outputs"] = copy.deepcopy(dict(outputs))
        self.payload["artifacts"] = copy.deepcopy(dict(outputs))
        self.payload["output_sha256"] = digest_mapping(outputs)
        self.payload["completed_at"] = _now()
        self._persist()

    def snapshot(self) -> dict[str, object]:
        return copy.deepcopy(self.payload)
