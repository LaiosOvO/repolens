"""Production report pipeline contracts and stage orchestration."""

from .contracts import PipelineStage, ProgressEvent, ProgressSink
from .inventory import CapabilityInventoryStage, InventoryStageRequest
from .source_snapshot import RepositorySnapshot, consistent_repository_snapshot
from .stage_artifacts import build_report_stage_artifacts
from .linear_pipeline import LINEAR_REPORT_STAGES, LinearStageArtifacts

__all__ = [
    "CapabilityInventoryStage",
    "InventoryStageRequest",
    "PipelineStage",
    "ProgressEvent",
    "ProgressSink",
    "RepositorySnapshot",
    "consistent_repository_snapshot",
    "build_report_stage_artifacts",
    "LINEAR_REPORT_STAGES",
    "LinearStageArtifacts",
]
