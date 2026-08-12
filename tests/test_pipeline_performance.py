from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from repo_teacher.pipeline.performance import (
    build_pipeline_performance,
    collect_model_call_performance,
    write_pipeline_performance,
)


class PipelinePerformanceTest(unittest.TestCase):
    def test_build_summary_supports_legacy_journal_records(self) -> None:
        summary = build_pipeline_performance(
            {
                "schema_version": "repolens-pipeline-journal/v1",
                "pipeline": "inventory",
                "status": "failed",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:12+00:00",
                "current_stage": "capability-inventory",
                "retry_stage": "capability-inventory",
                "stages": [
                    {
                        "id": "evidence-pack",
                        "status": "passed",
                        "attempt": 1,
                        "started_at": "2026-01-01T00:00:01+00:00",
                        "completed_at": "2026-01-01T00:00:04+00:00",
                        "inputs": {},
                        "outputs": {},
                        "metrics": {},
                        "issues": [],
                        "retry_stage": "none",
                    },
                    {
                        "id": "capability-inventory",
                        "status": "failed",
                        "attempt": 2,
                        "started_at": "2026-01-01T00:00:04+00:00",
                        "completed_at": "2026-01-01T00:00:10+00:00",
                        "inputs": {"cache_key": "cache-123"},
                        "outputs": {},
                        "metrics": {},
                        "issues": [{"code": "provider-timeout", "message": "timed out"}],
                        "retry_stage": "capability-inventory",
                    },
                ],
            }
        )

        self.assertEqual(summary["wall_duration_seconds"], 12.0)
        self.assertEqual(summary["longest_stage"]["id"], "capability-inventory")
        self.assertEqual(summary["longest_stage"]["duration_seconds"], 6.0)
        self.assertEqual(summary["stages"][0]["duration_seconds"], 3.0)
        self.assertEqual(
            summary["stages"][1]["cache"],
            {"cache_key": "cache-123"},
        )

    def test_write_pipeline_performance_persists_atomic_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "performance.json"
            summary = write_pipeline_performance(
                output,
                {
                    "schema_version": "repolens-pipeline-journal/v1",
                    "pipeline": "report",
                    "status": "passed",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:06+00:00",
                    "completed_at": "2026-01-01T00:00:06+00:00",
                    "stages": [
                        {
                            "id": "01-graph-index",
                            "status": "passed",
                            "attempt": 1,
                            "started_at": "2026-01-01T00:00:01+00:00",
                            "completed_at": "2026-01-01T00:00:06+00:00",
                            "duration_seconds": 5.0,
                            "inputs": {},
                            "outputs": {},
                            "metrics": {},
                            "issues": [],
                            "retry_stage": "none",
                        }
                    ],
                },
            )
            persisted = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(persisted, summary)
        self.assertEqual(persisted["longest_stage"]["id"], "01-graph-index")

    def test_collect_model_calls_and_shard_parallelism_without_prompt_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            call = workspace / "inventory" / "domain-00"
            call.mkdir(parents=True)
            (call / "capability-inventory-model-performance.json").write_text(
                json.dumps(
                    {
                        "schema_version": "repolens-model-call-performance/v1",
                        "stage": "capability-inventory-model",
                        "provider": "codex",
                        "model": "fast-model",
                        "status": "passed",
                        "duration_seconds": 2.5,
                        "prompt_bytes": 900,
                        "schema_bytes": 100,
                        "prompt": "must-not-leak",
                    }
                ),
                encoding="utf-8",
            )
            (workspace / "inventory" / "inventory-shards-performance.json").write_text(
                json.dumps(
                    {
                        "schema_version": "repolens-inventory-shard-performance/v1",
                        "parallel_wall_seconds": 3.0,
                        "model_seconds_sum": 2.5,
                        "shards": [],
                    }
                ),
                encoding="utf-8",
            )

            summary = collect_model_call_performance(workspace)

        self.assertEqual(summary["model_calls"], 1)
        self.assertEqual(summary["model_call_seconds"], 2.5)
        self.assertNotIn("must-not-leak", str(summary))
        self.assertNotIn("prompt", summary["model_calls_detail"][0])
        self.assertEqual(
            summary["shard_parallelism"]["parallel_wall_seconds"], 3.0
        )


if __name__ == "__main__":
    unittest.main()
