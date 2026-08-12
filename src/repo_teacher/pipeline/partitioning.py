"""Deterministic byte/token-budget partitioning for model evidence packets."""

from __future__ import annotations

import math
import json
from collections.abc import Callable, Sequence
from pathlib import PurePosixPath


# Model packets retain the graph/evidence closure, while full allowed source
# files live in the isolated source-slice and can be opened on demand.  Keeping
# the inline packet below 500 KiB avoids the multi-minute prompt ingestion seen
# in large monorepos without truncating the underlying evidence scope.
PACKET_BYTE_BUDGET = 500_000
PACKET_TOKEN_BUDGET = 125_000
# Inventory shards use the same hard ceiling as every other evidence packet.
# A graph-derived scope can legitimately collapse to one evidence-heavy source
# file; rejecting a 400-500 KiB indivisible closure makes the whole unattended
# pipeline fail even though it remains inside the provider-independent packet
# limit.  Ordinary scopes are still recursively split before reaching this
# ceiling, and ``require_packet_budget`` verifies the materialized packet again.
INVENTORY_SHARD_BYTE_BUDGET = PACKET_BYTE_BUDGET
INVENTORY_SHARD_TOKEN_BUDGET = PACKET_TOKEN_BUDGET
INVENTORY_SOURCE_EXCERPT_BUDGET = 120_000
MAX_INVENTORY_SHARDS = 20
MAX_INVENTORY_SCOPES = 256


def _scope_contains(scope: str, path: str) -> bool:
    return path == scope or path.startswith(f"{scope}/")


def expand_oversized_module_scopes(
    module_paths: Sequence[str],
    *,
    source_paths: Sequence[str],
    measure: Callable[[Sequence[str]], int],
    byte_budget: int = PACKET_BYTE_BUDGET,
    token_budget: int = PACKET_TOKEN_BUDGET,
    max_scopes: int = MAX_INVENTORY_SCOPES,
) -> tuple[list[str], dict[str, str]]:
    """Split one large module by real child paths while retaining its owner.

    The model sees smaller source scopes, but every returned module disposition
    is later folded back into the original graph-derived module.  No source
    path is dropped, guessed from text, or assigned to more than one child.
    """

    normalized_sources = sorted(
        {
            PurePosixPath(path).as_posix()
            for path in source_paths
            if path and not PurePosixPath(path).is_absolute() and ".." not in PurePosixPath(path).parts
        }
    )
    queue = [(str(PurePosixPath(module)), str(PurePosixPath(module))) for module in module_paths]
    accepted: list[str] = []
    owner_by_scope: dict[str, str] = {}
    while queue:
        scope, owner = queue.pop(0)
        byte_count = measure([scope])
        if byte_count <= byte_budget and estimated_tokens(byte_count) <= token_budget:
            accepted.append(scope)
            owner_by_scope[scope] = owner
            continue
        scope_parts = PurePosixPath(scope).parts
        children: set[str] = set()
        for path in normalized_sources:
            if not _scope_contains(scope, path):
                continue
            path_parts = PurePosixPath(path).parts
            if len(path_parts) <= len(scope_parts):
                children.add(path)
            else:
                children.add(PurePosixPath(*path_parts[: len(scope_parts) + 1]).as_posix())
        children.discard(scope)
        if not children:
            raise ValueError(
                "inventory packet exceeds byte/token budget for one indivisible "
                f"source scope: {scope} ({byte_count} bytes/{estimated_tokens(byte_count)} tokens)"
            )
        if len(accepted) + len(queue) + len(children) > max_scopes:
            raise ValueError(
                "inventory packet budget requires more than the configured source-scope limit"
            )
        queue[0:0] = [(child, owner) for child in sorted(children)]
    if len(accepted) != len(set(accepted)):
        raise ValueError("inventory source-scope expansion produced duplicate scopes")
    return accepted, owner_by_scope


def estimated_tokens(byte_count: int) -> int:
    """Return a conservative provider-independent UTF-8 token estimate."""

    if byte_count < 0:
        raise ValueError("packet byte count cannot be negative")
    return math.ceil(byte_count / 4)


def require_packet_budget(
    payload: object,
    *,
    byte_budget: int = PACKET_BYTE_BUDGET,
    token_budget: int = PACKET_TOKEN_BUDGET,
) -> dict[str, int]:
    """Reject an actual model packet that escaped the partition estimate."""

    byte_count = len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    token_count = estimated_tokens(byte_count)
    if byte_count > byte_budget or token_count > token_budget:
        raise ValueError(
            "model evidence packet exceeds byte/token budget after CodeGraph "
            f"materialization: {byte_count} bytes/{token_count} tokens"
        )
    return {"packet_bytes": byte_count, "estimated_tokens": token_count}


def split_shards_by_budget(
    shards: Sequence[Sequence[str]],
    *,
    measure: Callable[[Sequence[str]], int],
    byte_budget: int = PACKET_BYTE_BUDGET,
    token_budget: int = PACKET_TOKEN_BUDGET,
    max_shards: int = MAX_INVENTORY_SHARDS,
) -> tuple[list[list[str]], list[dict[str, object]]]:
    """Recursively split module shards until every measured packet is bounded.

    The function never drops or duplicates a module.  A single module that
    cannot fit is rejected instead of silently truncating its evidence closure.
    """

    if byte_budget < 1 or token_budget < 1 or max_shards < 1:
        raise ValueError("packet budgets and shard limit must be positive")
    queue = [sorted(dict.fromkeys(shard)) for shard in shards if shard]
    expected = [module for shard in queue for module in shard]
    if len(expected) != len(set(expected)):
        raise ValueError("inventory module shards overlap before budget splitting")
    accepted: list[list[str]] = []
    metrics: list[dict[str, object]] = []
    while queue:
        module_paths = queue.pop(0)
        byte_count = measure(module_paths)
        token_count = estimated_tokens(byte_count)
        if byte_count <= byte_budget and token_count <= token_budget:
            accepted.append(module_paths)
            metrics.append(
                {
                    "module_paths": module_paths,
                    "packet_bytes": byte_count,
                    "estimated_tokens": token_count,
                    "byte_budget": byte_budget,
                    "token_budget": token_budget,
                    "truncated": False,
                }
            )
            continue
        if len(module_paths) == 1:
            raise ValueError(
                "inventory packet exceeds byte/token budget for one indivisible "
                f"module: {module_paths[0]} ({byte_count} bytes/{token_count} tokens)"
            )
        if len(accepted) + len(queue) + 2 > max_shards:
            raise ValueError(
                "inventory packet budget requires more than the configured shard limit"
            )
        midpoint = (len(module_paths) + 1) // 2
        queue[0:0] = [module_paths[:midpoint], module_paths[midpoint:]]
    flattened = [module for shard in accepted for module in shard]
    if sorted(flattened) != sorted(expected) or len(flattened) != len(expected):
        raise ValueError("inventory packet splitting changed module coverage")
    return accepted, metrics
