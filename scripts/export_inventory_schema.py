#!/usr/bin/env python3
"""Export the canonical public capability-inventory JSON Schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repo_teacher.schemas import persisted_inventory_json_schema


def _schema_text() -> str:
    return (
        json.dumps(persisted_inventory_json_schema(), ensure_ascii=False, indent=2)
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail when the committed schema differs",
    )
    args = parser.parse_args(argv)
    expected = _schema_text()
    if args.check:
        if not args.output.is_file():
            print(f"schema file is missing: {args.output}", file=sys.stderr)
            return 1
        if args.output.read_text(encoding="utf-8") != expected:
            print(f"schema file is stale: {args.output}", file=sys.stderr)
            return 1
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
