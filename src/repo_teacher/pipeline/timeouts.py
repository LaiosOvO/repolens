"""Shared absolute-deadline handling for model stages."""

from __future__ import annotations

import math
import time

def remaining_model_timeout(deadline: float) -> int:
    """Return the remaining global synthesis budget for one provider call.

    Provider calls may run concurrently, so every call receives the same
    absolute deadline instead of a fixed per-stage cap.  This keeps
    ``--model-timeout`` authoritative for the full synthesis while allowing a
    difficult shard to take longer than the previous hidden 600-second limit.
    """

    remaining = math.ceil(deadline - time.monotonic())
    if remaining <= 0:
        raise TimeoutError("Codex synthesis deadline exceeded")
    return remaining
