"""Fixed, append-observable artifacts for the linear report pipeline."""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from ..persistence import atomic_write_text, read_json_path
from .serialization import json_artifact


LINEAR_REPORT_STAGES = (
    "01-source-snapshot",
    "02-code-index",
    "03-content-generation",
    "04-evidence-validation",
    "05-publication",
)

# Compatibility-only stage vocabulary for the standalone ``inventory``
# command.  The human report command never executes these stages; its public
# contract is the fixed five-stage sequence above.
LEGACY_INVENTORY_STAGES = (
    "01-source-snapshot",
    "02-code-index",
    "03-evidence-plan",
    "04-capability-candidates",
    "05-business-grouping",
    "06-semantic-validation",
    "07-project-overview",
    "08-capability-chapters",
)


def _sha256(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(json_artifact(dict(payload)).encode("utf-8")).hexdigest()


class LinearStageArtifacts:
    """Persist exactly one current record for every sequential pipeline stage."""

    def __init__(
        self,
        workspace: Path,
        *,
        stages: tuple[str, ...] = LINEAR_REPORT_STAGES,
    ) -> None:
        self.workspace = workspace
        self.stages = stages
        self.root = workspace / "stages"
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "pipeline.json"
        self.performance_path = workspace / "performance.json"

    def published_artifacts(self) -> dict[str, dict[str, object]]:
        """Return the complete fixed stage ledger for an immutable generation."""

        manifest = read_json_path(self.manifest_path)
        if manifest.get("status") != "passed":
            raise ValueError("linear pipeline is not complete")
        artifacts = {
            f"pipeline/{stage}.json": read_json_path(self.root / f"{stage}.json")
            for stage in self.stages
        }
        artifacts["pipeline/pipeline.json"] = manifest
        artifacts["pipeline/performance.json"] = read_json_path(
            self.performance_path
        )
        return artifacts

    def has_failed_stage(self) -> bool:
        if not self.manifest_path.is_file():
            return False
        return read_json_path(self.manifest_path).get("status") == "failed"

    def stage_passed(
        self, stage: str, *, inputs: Mapping[str, object]
    ) -> bool:
        """Return true only for a passed record with the same deterministic input."""

        path = self.root / f"{stage}.json"
        if stage not in self.stages or not path.is_file():
            return False
        record = read_json_path(path)
        return (
            record.get("schema_version") == "repolens-linear-stage/v1"
            and record.get("stage") == stage
            and record.get("status") == "passed"
            and record.get("attempt") == 1
            and record.get("input_sha256") == _sha256(inputs)
        )

    def pass_stage(
        self,
        stage: str,
        *,
        inputs: Mapping[str, object],
        output: Mapping[str, object],
        metrics: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return self._record(
            stage,
            status="passed",
            inputs=inputs,
            output=output,
            metrics=metrics or {},
            error=None,
        )

    def fail_stage(
        self,
        stage: str,
        *,
        inputs: Mapping[str, object],
        error: str,
        metrics: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return self._record(
            stage,
            status="failed",
            inputs=inputs,
            output={},
            metrics=metrics or {},
            error=error,
        )

    def adopt_from(self, other_workspace: Path) -> None:
        """Copy validated fixed-stage records from a nested model workspace."""

        source_root = other_workspace / "stages"
        for stage in self.stages:
            source = source_root / f"{stage}.json"
            if not source.is_file():
                continue
            record = read_json_path(source)
            if (
                record.get("schema_version") != "repolens-linear-stage/v1"
                or record.get("stage") != stage
                or record.get("attempt") != 1
                or record.get("status") not in {"passed", "failed"}
            ):
                raise ValueError(f"invalid linear stage checkpoint: {stage}")
            atomic_write_text(self.root / source.name, json_artifact(record))
        self._write_manifest()

    def _record(
        self,
        stage: str,
        *,
        status: str,
        inputs: Mapping[str, object],
        output: Mapping[str, object],
        metrics: Mapping[str, object],
        error: str | None,
    ) -> dict[str, object]:
        if stage not in self.stages:
            raise ValueError(f"unknown linear pipeline stage: {stage}")
        record: dict[str, object] = {
            "schema_version": "repolens-linear-stage/v1",
            "stage": stage,
            "position": self.stages.index(stage) + 1,
            "status": status,
            "attempt": 1,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "input_sha256": _sha256(inputs),
            "output_sha256": _sha256(output) if status == "passed" else None,
            "inputs": copy.deepcopy(dict(inputs)),
            "output": copy.deepcopy(dict(output)),
            "metrics": copy.deepcopy(dict(metrics)),
            "error": error,
        }
        atomic_write_text(self.root / f"{stage}.json", json_artifact(record))
        self._write_manifest()
        return record

    def _write_manifest(self) -> None:
        records: list[dict[str, object]] = []
        for stage in self.stages:
            path = self.root / f"{stage}.json"
            if path.is_file():
                records.append(read_json_path(path))
        failed = next(
            (item for item in records if item.get("status") == "failed"), None
        )
        completed = {str(item.get("stage")) for item in records if item.get("status") == "passed"}
        next_stage = next(
            (stage for stage in self.stages if stage not in completed), None
        )
        all_passed = len(completed) == len(self.stages)
        status = (
            "failed"
            if failed is not None
            else ("passed" if all_passed else "in-progress")
        )
        manifest = {
            "schema_version": "repolens-linear-pipeline/v1",
            "execution_model": "strictly-sequential",
            "stage_order": list(self.stages),
            "status": status,
            "current_stage": failed.get("stage") if failed is not None else next_stage,
            "stages": records,
        }
        atomic_write_text(self.manifest_path, json_artifact(manifest))
        timed = [
            item
            for item in records
            if isinstance(item.get("metrics"), dict)
            and isinstance(item["metrics"].get("wall_duration_seconds"), (int, float))
        ]
        durations = {
            str(item["stage"]): float(item["metrics"]["wall_duration_seconds"])
            for item in timed
        }
        longest = max(durations, key=durations.get) if durations else None
        performance = {
            "schema_version": "repolens-linear-performance/v1",
            "execution_model": "strictly-sequential",
            "status": status,
            "current_stage": manifest["current_stage"],
            "stages": [
                {
                    "stage": item.get("stage"),
                    "status": item.get("status"),
                    "wall_duration_seconds": (
                        item.get("metrics", {}).get("wall_duration_seconds")
                        if isinstance(item.get("metrics"), dict)
                        else None
                    ),
                    "model_calls": (
                        item.get("metrics", {}).get("model_calls", 0)
                        if isinstance(item.get("metrics"), dict)
                        else 0
                    ),
                }
                for item in records
            ],
            "total_recorded_wall_seconds": round(sum(durations.values()), 6),
            "longest_stage": longest,
            "longest_stage_seconds": durations.get(longest) if longest else None,
            "model_calls": sum(
                int(item.get("metrics", {}).get("model_calls", 0))
                for item in records
                if isinstance(item.get("metrics"), dict)
            ),
        }
        atomic_write_text(self.performance_path, json_artifact(performance))
