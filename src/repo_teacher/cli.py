"""RepoLens command-line entry point.

This module only defines arguments and routes them to application commands.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .commands.entrypoints import (
    _compare,
    _explain,
    _export_skill,
    _graph,
    _index,
    _inventory,
    _prepare_report,
    _rebind_reviewed_narrative,
    _render_human_report,
    _report,
    _serve,
    _validate,
)

def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-teacher",
        description="Build a local repository index and an explorable standalone HTML report.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    index = commands.add_parser("index", help="Analyze a repository and generate index.json + index.html")
    index.add_argument("source", help="Repository directory to analyze")
    index.add_argument(
        "--output",
        "-o",
        help="Output directory (default: <source>/.repo-teacher)",
    )
    index.add_argument(
        "--max-file-size",
        type=_positive_int,
        default=1_000_000,
        metavar="BYTES",
        help="Skip files larger than this many bytes (default: 1000000)",
    )
    index.add_argument("--open", action="store_true", help="Open the generated report in the default browser")

    report = commands.add_parser(
        "report",
        help="Generate a human-first feature and implementation report for any repository",
    )
    report.add_argument("source", help="Repository directory to analyze")
    report.add_argument("--output", "-o", required=True, help="Output directory containing index.html")
    report.add_argument(
        "--narrative",
        help="Use an existing human-report JSON instead of invoking Codex (for CI or review)",
    )
    report.add_argument(
        "--inventory",
        help=(
            "Use an existing capability inventory JSON or source-audited manifest "
            "to skip the inventory-model phase and only synthesize chapters"
        ),
    )
    report.add_argument(
        "--auto-inventory",
        action="store_true",
        help=(
            "Compatibility flag; automatic capability discovery is already the default"
        ),
    )
    report.add_argument(
        "--model-timeout",
        type=_positive_int,
        default=900,
        metavar="SECONDS",
        help="Maximum Codex synthesis time (default: 900)",
    )
    report.add_argument(
        "--provider",
        choices=("codex", "opencode", "deepseek"),
        default="codex",
        help=(
            "Narrative model provider (default: codex; opencode supports OpenRouter models; "
            "deepseek reads DEEPSEEK_API_KEY)"
        ),
    )
    report.add_argument(
        "--max-file-size",
        type=_positive_int,
        default=1_000_000,
        metavar="BYTES",
        help="Skip files larger than this many bytes (default: 1000000)",
    )
    report.add_argument("--open", action="store_true", help="Open the generated human report")

    inventory = commands.add_parser(
        "inventory",
        help="Discover and validate the business capability list without generating chapters",
    )
    inventory.add_argument("source", help="Repository directory to analyze")
    inventory.add_argument(
        "--output",
        "-o",
        required=True,
        help="Destination capability-inventory.json",
    )
    inventory.add_argument(
        "--model-timeout",
        type=_positive_int,
        default=900,
        metavar="SECONDS",
        help="Maximum capability synthesis time (default: 900)",
    )
    inventory.add_argument(
        "--provider",
        choices=("codex", "opencode", "deepseek"),
        default="codex",
        help="Capability model provider (default: codex)",
    )
    inventory.add_argument(
        "--max-file-size",
        type=_positive_int,
        default=1_000_000,
        metavar="BYTES",
        help="Skip files larger than this many bytes (default: 1000000)",
    )

    ui = commands.add_parser(
        "ui",
        help="Open the local report generator with provider, model and progress controls",
    )
    ui.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    ui.add_argument("--port", type=int, default=8787, help="Bind port (default: 8787; use 0 for any free port)")
    ui.add_argument("--open", action="store_true", help="Open the local UI in the default browser")

    compare = commands.add_parser("compare", help="Compare how repositories implement the same capabilities")
    compare.add_argument("sources", nargs="+", help="Two or more repository directories to compare")
    compare.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output directory for technology-selection.html and project indexes",
    )
    compare.add_argument(
        "--max-file-size",
        type=_positive_int,
        default=1_000_000,
        metavar="BYTES",
        help="Skip files larger than this many bytes (default: 1000000)",
    )
    compare.add_argument("--open", action="store_true", help="Open the technology selection report")

    explain = commands.add_parser(
        "explain",
        help="Locate a named capability in a repository and explain its concrete module",
    )
    explain.add_argument("source", help="Repository directory to analyze")
    explain.add_argument("query", help="Capability or module name, for example ACP")
    explain.add_argument(
        "--output",
        "-o",
        help="Output directory (default: <source>/.repo-teacher)",
    )
    explain.add_argument(
        "--limit",
        type=_positive_int,
        default=8,
        help="Maximum candidate modules when there is no unique match (default: 8)",
    )
    explain.add_argument(
        "--max-file-size",
        type=_positive_int,
        default=1_000_000,
        metavar="BYTES",
        help="Skip files larger than this many bytes (default: 1000000)",
    )
    explain.add_argument("--open", action="store_true", help="Open the module explanation report")

    graph = commands.add_parser(
        "graph",
        help="Explore callers, callees, impact and capability clusters from a generated index",
    )
    graph.add_argument("index", help="Path to a generated index.json")
    graph.add_argument(
        "query",
        nargs="?",
        help="Optional symbol, path or capability query; omit to export the complete graph",
    )
    graph.add_argument("--output", "-o", required=True, help="Destination JSON path")
    graph.add_argument(
        "--depth",
        type=_positive_int,
        default=2,
        help="Caller/callee traversal depth for a query (default: 2)",
    )

    export = commands.add_parser("export-skill", help="Export selected features as a reusable local Skill")
    export.add_argument("index", help="Path to a generated index.json")
    export.add_argument("--output", "-o", required=True, help="Destination Skill directory")
    export.add_argument(
        "--feature",
        action="append",
        default=[],
        metavar="FEATURE_ID",
        help="Feature ID to include; repeat for multiple features (default: all)",
    )
    export.add_argument("--name", help="Optional lowercase Skill name")
    export.add_argument(
        "--force",
        action="store_true",
        help=(
            "Record explicit replacement authorization for an owned Repo Teacher Skill; "
            "never replaces an unowned destination"
        ),
    )

    validate = commands.add_parser("validate", help="Validate an index against its source snapshot")
    validate.add_argument("index", help="Path to a generated index.json")
    validate.add_argument("--source", help="Override source repository path stored in the index")

    prepare = commands.add_parser(
        "prepare-report",
        help="Prepare a bounded evidence packet for a human-first model-authored report",
    )
    prepare.add_argument("index", help="Path to a generated index.json")
    prepare.add_argument("--output", "-o", required=True, help="Destination analysis-pack.json")

    human = commands.add_parser(
        "render-report",
        help="Validate a model narrative and publish the human-first index.html",
    )
    human.add_argument("index", help="Path to the canonical generated index.json")
    human.add_argument("narrative", help="Path to a repo-teacher-human-report/v1 JSON file")
    human.add_argument("--output", "-o", required=True, help="Destination report directory")
    human.add_argument("--open", action="store_true", help="Open the generated human report")

    serve = commands.add_parser("serve", help="Serve a generated report over local HTTP")
    serve.add_argument("directory", nargs="?", default=".repo-teacher", help="Directory containing index.html")
    serve.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    serve.add_argument("--port", type=_positive_int, default=8765, help="Port (default: 8765)")
    serve.add_argument("--open", action="store_true", help="Open the local URL in the default browser")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "index":
        return _index(arguments.source, arguments.output, arguments.max_file_size, arguments.open)
    if arguments.command == "report":
        return _report(
            arguments.source,
            arguments.output,
            arguments.narrative,
            arguments.inventory,
            arguments.model_timeout,
            arguments.provider,
            arguments.max_file_size,
            arguments.open,
            arguments.auto_inventory,
        )
    if arguments.command == "inventory":
        return _inventory(
            arguments.source,
            arguments.output,
            arguments.model_timeout,
            arguments.provider,
            arguments.max_file_size,
        )
    if arguments.command == "ui":
        from .local_ui import run_local_ui

        if not 0 <= arguments.port <= 65_535:
            print("error: port must be between 0 and 65535", file=sys.stderr)
            return 2
        return run_local_ui(arguments.host, arguments.port, arguments.open)
    if arguments.command == "compare":
        return _compare(arguments.sources, arguments.output, arguments.max_file_size, arguments.open)
    if arguments.command == "explain":
        return _explain(
            arguments.source,
            arguments.query,
            arguments.output,
            arguments.limit,
            arguments.max_file_size,
            arguments.open,
        )
    if arguments.command == "export-skill":
        return _export_skill(
            arguments.index,
            arguments.output,
            arguments.feature,
            arguments.name,
            arguments.force,
        )
    if arguments.command == "validate":
        return _validate(arguments.index, arguments.source)
    if arguments.command == "graph":
        return _graph(
            arguments.index,
            arguments.query,
            arguments.output,
            arguments.depth,
        )
    if arguments.command == "prepare-report":
        return _prepare_report(arguments.index, arguments.output)
    if arguments.command == "render-report":
        return _render_human_report(
            arguments.index, arguments.narrative, arguments.output, arguments.open
        )
    if arguments.command == "serve":
        return _serve(arguments.directory, arguments.host, arguments.port, arguments.open)
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
