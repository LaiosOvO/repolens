"""Stable pipeline interfaces shared by CLI, UI, tests, and skills."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class PipelineStage(StrEnum):
    GRAPH_INDEX = "graph-index"
    EVIDENCE_PACK = "evidence-pack"
    CAPABILITY_INVENTORY = "capability-inventory"
    HUMAN_APPROVAL = "human-approval"
    CHAPTER_GENERATION = "chapter-generation"
    EVIDENCE_REVIEW = "evidence-review"
    PUBLISH = "publish"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    stage: PipelineStage
    current: int
    total: int
    message: str

    def __post_init__(self) -> None:
        if self.total < 1 or not 0 <= self.current <= self.total:
            raise ValueError("progress must satisfy 0 <= current <= total")


class ProgressSink(Protocol):
    def emit(self, event: ProgressEvent) -> None: ...
