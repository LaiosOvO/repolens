"""One-call business capability inventory stage.

The stage owns cache validation and atomic persistence.  It deliberately does
not know how CodeGraph evidence is collected or how a specific model is
invoked; those vary at the provider/evidence seams.  Its public interface stays
small: one request in, one validated inventory out.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..providers import StructuredGenerationRequest, StructuredModelProvider


InventoryTransform = Callable[
    [dict[str, object], dict[str, object]], dict[str, object]
]
InventoryValidator = Callable[[dict[str, object], dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class InventoryStageRequest:
    source: Path
    workspace: Path
    packet: dict[str, object]
    packet_path: Path
    prompt: str
    schema: dict[str, object]
    timeout_seconds: int


class CapabilityInventoryStage:
    """Generate or reuse a schema-valid, evidence-bound capability inventory."""

    def __init__(self, provider: StructuredModelProvider) -> None:
        self._provider = provider

    def run(
        self,
        request: InventoryStageRequest,
        *,
        normalize: InventoryTransform,
        validate: InventoryValidator,
    ) -> tuple[dict[str, object], bool]:
        cache_path = request.workspace / "capability-inventory.json"
        cached = self._read_valid_cache(cache_path, request.packet, normalize, validate)
        if cached is not None:
            return cached, True

        payload = self._provider.generate(
            StructuredGenerationRequest(
                stage="capability-inventory",
                source=request.source,
                workspace=request.workspace,
                prompt=request.prompt,
                schema=request.schema,
                timeout_seconds=request.timeout_seconds,
            )
        )
        normalized = normalize(payload, request.packet)
        validate(normalized, request.packet)
        self._write_atomic(cache_path, normalized)
        return normalized, False

    @staticmethod
    def _read_valid_cache(
        path: Path,
        packet: dict[str, object],
        normalize: InventoryTransform,
        validate: InventoryValidator,
    ) -> dict[str, object] | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            normalized = normalize(payload, packet)
            validate(normalized, packet)
            return normalized
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            return None

    @staticmethod
    def _write_atomic(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
