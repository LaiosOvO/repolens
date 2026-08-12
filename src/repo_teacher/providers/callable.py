"""Adapter for existing provider functions and deterministic test fakes."""

from __future__ import annotations

from collections.abc import Callable

from .base import StructuredGenerationRequest


class CallableStructuredModelProvider:
    def __init__(
        self,
        name: str,
        generate: Callable[[StructuredGenerationRequest], dict[str, object]],
    ) -> None:
        if not name.strip():
            raise ValueError("provider name must not be empty")
        self._name = name
        self._generate = generate

    @property
    def name(self) -> str:
        return self._name

    def generate(self, request: StructuredGenerationRequest) -> dict[str, object]:
        return self._generate(request)
