"""CLI command adapters.

Each adapter translates parsed arguments into one application command.  Report
and inventory stage ordering lives in their dedicated command/pipeline modules.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence

from ..capability_graph import build_capability_graph, explore_capability_graph
from ..human_report import build_report_pack, compose_human_report
from ..indexer import _integrity_digest, build_index
from ..models import redact_persisted_value
from ..persistence import (
    GenerationPublisher,
    OutputLock,
    read_json_path,
    read_published_json,
)
from ..pipeline.codegraph import _prepare_codegraph
from ..pipeline.synthesis import (
    _canonicalize_inventory_payload,
    _model_workspace_for_pack,
    _report_index_with_navigation_evidence,
    _synthesize_with_codex,
    synthesize_direct_human_report,
)
from ..renderers import render_index, render_report

def _bind_generation(payload: dict[str, object], generation_id: str) -> dict[str, object]:
    bound = redact_persisted_value(copy.deepcopy(payload))
    bound["generation_id"] = generation_id
    if "integrity_sha256" in bound:
        bound["integrity_sha256"] = _integrity_digest(bound)
    return bound


def _rebind_snapshot_source(
    payload: dict[str, object],
    *,
    snapshot_path: Path,
    original_source: Path,
    source_manifest_sha256: str | None = None,
) -> dict[str, object]:
    """Replace ephemeral snapshot locations before an artifact is published."""

    rebound = copy.deepcopy(payload)
    project = rebound.get("project")
    if isinstance(project, dict):
        project_path = project.get("path")
        if project_path == str(snapshot_path):
            project["path"] = str(original_source)
        git_root = project.get("git_root")
        if isinstance(git_root, str):
            try:
                relative = Path(git_root).relative_to(snapshot_path)
            except ValueError:
                pass
            else:
                project["git_root"] = str(original_source / relative)
    if source_manifest_sha256 is not None:
        rebound["source_manifest_sha256"] = source_manifest_sha256
    if "integrity_sha256" in rebound:
        rebound["integrity_sha256"] = _integrity_digest(rebound)
    return rebound


def _json_artifact(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _html_artifact(content: str, generation_id: str) -> str:
    marker = (
        '<meta name="repo-teacher-generation" '
        f'content="{generation_id}">'
    )
    result, count = re.subn(
        r"<head(?P<attributes>[^>]*)>",
        lambda match: f"<head{match.group('attributes')}>{marker}",
        content,
        count=1,
        flags=re.IGNORECASE,
    )
    if count != 1:
        raise ValueError("generated HTML has no unique head element")
    return result


def _require_valid_index(index: dict[str, object], source: Path) -> None:
    from ..validation import validate_index

    validation = validate_index(index, source)
    if not validation["valid"]:
        codes = ", ".join(
            sorted(
                {
                    str(item.get("code") or "validation-error")
                    for item in validation["issues"]
                    if item.get("severity") == "error"
                }
            )
        )
        raise ValueError(f"index failed pre-publication validation: {codes}")


def _rebind_reviewed_narrative(
    narrative: dict[str, object], pack: dict[str, object]
) -> dict[str, object]:
    """Bind reviewed prose to a rebuilt index of the same source revision.

    The analyzer fingerprint describes the deterministic index implementation,
    not the human prose.  Source paths, line ranges and evidence are still
    revalidated later by ``compose_human_report``.
    """

    narrative_project = narrative.get("project")
    pack_project = pack.get("project")
    if not isinstance(narrative_project, dict) or not isinstance(pack_project, dict):
        raise ValueError("human report and analysis pack must include project identity")
    narrative_commit = narrative_project.get("commit")
    pack_commit = pack_project.get("commit")
    if narrative_commit and pack_commit and narrative_commit != pack_commit:
        raise ValueError("human report commit does not match the current source revision")
    rebound = copy.deepcopy(narrative)
    rebound_project = rebound["project"]
    assert isinstance(rebound_project, dict)
    rebound_project["commit"] = pack_commit
    rebound_project["analysis_fingerprint"] = pack_project.get(
        "analysis_fingerprint"
    )
    rebound.pop("generation_id", None)
    chapters = rebound.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("reviewed human report must include chapters")
    canonicalized = _canonicalize_inventory_payload(
        {"capabilities": chapters}, pack
    ).get("capabilities")
    if not isinstance(canonicalized, list) or len(canonicalized) != len(chapters):
        raise ValueError(
            "reviewed human report cannot be closed over the current source evidence"
        )
    closure_by_id = {
        str(item.get("id")): item
        for item in canonicalized
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    current_evidence_ids = {
        str(item.get("id"))
        for item in pack.get("evidence", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise ValueError("reviewed human report contains a non-object chapter")
        closure = closure_by_id.get(str(chapter.get("id") or ""))
        if closure is None:
            raise ValueError(
                "reviewed human report chapter has no current source evidence closure"
            )
        chapter["source_feature_ids"] = closure.get("source_feature_ids", [])
        chapter_evidence = [
            identifier
            for identifier in closure.get("evidence_ids", [])
            if isinstance(identifier, str)
        ]
        difficulty_map = chapter.get("difficulty_map")
        difficulty_items = (
            difficulty_map.get("items", [])
            if isinstance(difficulty_map, dict)
            else []
        )
        for item in difficulty_items if isinstance(difficulty_items, list) else []:
            if not isinstance(item, dict):
                continue
            evidence_ids = [
                identifier
                for identifier in item.get("evidence_ids", [])
                if isinstance(identifier, str)
                and identifier in current_evidence_ids
                and identifier in chapter_evidence
            ]
            item["evidence_ids"] = evidence_ids or chapter_evidence[:1]
        chapter["evidence_ids"] = chapter_evidence
    return rebound


def _load_baseline(output: Path, source: Path) -> dict[str, object] | None:
    try:
        candidate = read_published_json(output, "index.json")
    except (FileNotFoundError, OSError, ValueError):
        return None
    project = candidate.get("project")
    if not isinstance(project, dict) or project.get("path") != str(source):
        return None
    return candidate


def _index(source_arg: str, output_arg: str | None, max_file_size: int, should_open: bool) -> int:
    source = Path(source_arg).expanduser()
    if not source.exists():
        print(f"error: source does not exist: {source}", file=sys.stderr)
        return 2
    if not source.is_dir():
        print(f"error: source is not a directory: {source}", file=sys.stderr)
        return 2

    source = source.resolve()
    output = Path(output_arg).expanduser().resolve() if output_arg else source / ".repo-teacher"
    try:
        json_path = output / "index.json"
        html_path = output / "index.html"
        with OutputLock(output):
            previous_index = _load_baseline(output, source)
            result = build_index(
                source,
                output_dir=output,
                max_file_size=max_file_size,
                previous_index=previous_index,
            )
            generation_id = secrets.token_hex(16)
            result = _bind_generation(result, generation_id)
            _require_valid_index(result, source)
            artifacts = {
                "index.json": _json_artifact(result),
                "index.html": _html_artifact(render_index(result), generation_id),
                "capability-graph.json": _json_artifact(
                    _bind_generation(build_capability_graph(result), generation_id)
                ),
            }
            GenerationPublisher(output, generation_id).publish(
                artifacts,
                before_switch=lambda: _require_valid_index(result, source),
            )
    except (OSError, ValueError) as error:
        print(f"error: failed to generate repository index: {error}", file=sys.stderr)
        return 1

    stats = result["stats"]
    print(f"Generated repository index: {html_path}")
    print(
        f"Indexed {stats['files']} files, {stats['symbols']} symbols, "
        f"{stats['relationships']} relationships across {stats['modules']} modules."
    )
    print(
        f"Incremental work: reused {stats.get('reused_files', 0)} files; "
        f"reanalyzed {stats.get('reanalyzed_files', stats['files'])} files."
    )
    print(f"Machine-readable data: {json_path}")
    if should_open:
        webbrowser.open(html_path.as_uri())
    return 0


def _inventory(
    source_arg: str,
    output_arg: str,
    model_timeout: int,
    provider: str,
    max_file_size: int,
) -> int:
    from . import InventoryCommandPorts, run_inventory

    return run_inventory(
        source_arg,
        output_arg,
        model_timeout,
        provider,
        max_file_size,
        ports=InventoryCommandPorts(
            prepare_codegraph=_prepare_codegraph,
            require_valid_index=_require_valid_index,
            model_workspace_for_pack=_model_workspace_for_pack,
            synthesize=_synthesize_with_codex,
            json_artifact=_json_artifact,
        ),
    )


def _report(
    source_arg: str,
    output_arg: str,
    narrative_arg: str | None,
    inventory_arg: str | None,
    model_timeout: int,
    provider: str,
    max_file_size: int,
    should_open: bool,
    auto_inventory: bool = False,
) -> int:
    from . import ReportCommandPorts, run_report

    return run_report(
        source_arg,
        output_arg,
        narrative_arg,
        inventory_arg,
        model_timeout,
        provider,
        max_file_size,
        should_open,
        auto_inventory,
        ports=ReportCommandPorts(
            prepare_codegraph=_prepare_codegraph,
            load_baseline=_load_baseline,
            require_valid_index=_require_valid_index,
            model_workspace_for_pack=_model_workspace_for_pack,
            synthesize=synthesize_direct_human_report,
            rebind_reviewed_narrative=_rebind_reviewed_narrative,
            report_index_with_navigation_evidence=(
                _report_index_with_navigation_evidence
            ),
            rebind_snapshot_source=_rebind_snapshot_source,
            bind_generation=_bind_generation,
            json_artifact=_json_artifact,
            html_artifact=_html_artifact,
        ),
    )


def _compare(source_args: Sequence[str], output_arg: str, max_file_size: int, should_open: bool) -> int:
    from ..comparison import build_technology_comparison
    from ..comparison_report import render_comparison_report

    sources: list[Path] = []
    for source_arg in source_args:
        source = Path(source_arg).expanduser()
        if not source.exists():
            print(f"error: source does not exist: {source}", file=sys.stderr)
            return 2
        if not source.is_dir():
            print(f"error: source is not a directory: {source}", file=sys.stderr)
            return 2
        sources.append(source.resolve())
    if len(sources) < 2:
        print("error: compare requires at least two repository directories", file=sys.stderr)
        return 2

    resolved = [str(source) for source in sources]
    if len(set(resolved)) != len(resolved):
        print("error: compare sources must be unique", file=sys.stderr)
        return 2

    output = Path(output_arg).expanduser().resolve()
    report_path = output / "technology-selection.html"
    comparison_path = output / "technology-selection.json"
    try:
        with OutputLock(output):
            indexes: list[dict[str, object]] = []
            artifacts: dict[str, str] = {}
            used_slugs: set[str] = set()
            generation_id = secrets.token_hex(16)
            for source in sources:
                base_slug = "".join(character if character.isalnum() or character in "-_" else "-" for character in source.name)
                slug = base_slug or "repository"
                counter = 2
                while slug in used_slugs:
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                used_slugs.add(slug)
                project_output = output / "projects" / slug
                index = build_index(source, output_dir=project_output, max_file_size=max_file_size)
                index = _bind_generation(index, generation_id)
                _require_valid_index(index, source)
                indexes.append(index)
                artifacts[f"projects/{slug}/index.json"] = _json_artifact(index)
                artifacts[f"projects/{slug}/index.html"] = _html_artifact(
                    render_index(index), generation_id
                )

            comparison = build_technology_comparison(indexes)
            comparison["report"] = {
                "title": "代码仓库功能技术选型",
                "source_count": len(indexes),
                "generated_from": resolved,
            }
            comparison = _bind_generation(comparison, generation_id)
            artifacts["technology-selection.json"] = _json_artifact(comparison)
            artifacts["technology-selection.html"] = _html_artifact(
                render_comparison_report(comparison), generation_id
            )

            def validate_all_sources() -> None:
                for candidate, source in zip(indexes, sources, strict=True):
                    _require_valid_index(candidate, source)

            GenerationPublisher(output, generation_id).publish(
                artifacts, before_switch=validate_all_sources
            )
    except (OSError, ValueError) as error:
        print(f"error: failed to compare repositories: {error}", file=sys.stderr)
        return 1

    print(f"Generated technology selection report: {report_path}")
    print(f"Compared {len(sources)} repositories across {len(comparison['capabilities'])} capabilities.")
    print(f"Machine-readable data: {comparison_path}")
    if should_open:
        webbrowser.open(report_path.as_uri())
    return 0


def _report_slug(query: str) -> str:
    slug = "".join(
        character.casefold() if character.isalnum() else "-"
        for character in query.strip()
    )
    slug = "-".join(part for part in slug.split("-") if part)
    return slug[:80] or "capability"


def _explain(
    source_arg: str,
    query: str,
    output_arg: str | None,
    limit: int,
    max_file_size: int,
    should_open: bool,
) -> int:
    from ..module_locator import locate_modules
    from ..module_report import render_module_report

    source = Path(source_arg).expanduser()
    if not source.exists():
        print(f"error: source does not exist: {source}", file=sys.stderr)
        return 2
    if not source.is_dir():
        print(f"error: source is not a directory: {source}", file=sys.stderr)
        return 2
    if limit > 100:
        print("error: limit must be between 1 and 100", file=sys.stderr)
        return 2

    source = source.resolve()
    output = Path(output_arg).expanduser().resolve() if output_arg else source / ".repo-teacher"
    slug = _report_slug(query)
    json_path = output / "modules" / f"{slug}.json"
    html_path = output / "modules" / f"{slug}.html"
    try:
        with OutputLock(output):
            previous_index = _load_baseline(output, source)
            index = build_index(
                source,
                output_dir=output,
                max_file_size=max_file_size,
                previous_index=previous_index,
            )
            result = locate_modules(index, query, limit=limit)
            generation_id = secrets.token_hex(16)
            index = _bind_generation(index, generation_id)
            result = _bind_generation(result, generation_id)
            _require_valid_index(index, source)
            artifacts = {
                "index.json": _json_artifact(index),
                "index.html": _html_artifact(render_index(index), generation_id),
                f"modules/{slug}.json": _json_artifact(result),
                f"modules/{slug}.html": _html_artifact(
                    render_module_report(index, result), generation_id
                ),
            }
            GenerationPublisher(output, generation_id).publish(
                artifacts,
                before_switch=lambda: _require_valid_index(index, source),
            )
    except (OSError, ValueError) as error:
        print(f"error: failed to explain repository capability: {error}", file=sys.stderr)
        return 1

    resolution = result["resolution"]
    print(f"Generated module explanation: {html_path}")
    print(f"Resolution: {resolution['status']} — {resolution['summary']}")
    print(f"Machine-readable data: {json_path}")
    if should_open:
        webbrowser.open(html_path.as_uri())
    return 0


def _serve(directory_arg: str, host: str, port: int, should_open: bool) -> int:
    directory = Path(directory_arg).expanduser()
    if not directory.exists():
        print(f"error: report directory does not exist: {directory}", file=sys.stderr)
        return 2
    if not directory.is_dir():
        print(f"error: report path is not a directory: {directory}", file=sys.stderr)
        return 2
    directory = directory.resolve()
    if not (directory / "index.html").is_file():
        print(f"error: index.html was not found in: {directory}", file=sys.stderr)
        return 2

    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as error:
        print(f"error: could not start server: {error}", file=sys.stderr)
        return 1

    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{display_host}:{server.server_port}/"
    print(f"Serving repository index at {url}")
    print("Press Ctrl-C to stop.")
    if should_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
    return 0


def _export_skill(
    index_arg: str,
    output_arg: str,
    feature_ids: Sequence[str],
    name: str | None,
    force: bool,
) -> int:
    from ..skill_export import export_skill

    index_path = Path(index_arg).expanduser()
    if not index_path.is_file():
        print(f"error: index.json does not exist: {index_path}", file=sys.stderr)
        return 2
    try:
        index = read_json_path(index_path)
        result = export_skill(
            index,
            Path(output_arg),
            feature_ids=feature_ids,
            name=name,
            force=force,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(f"error: failed to export Skill: {error}", file=sys.stderr)
        return 1
    print(f"Exported Skill '{result['name']}' to: {result['path']}")
    print(f"Included {len(result['feature_ids'])} features, {result['files']} files and {result['evidence']} evidence refs.")
    return 0


def _validate(index_arg: str, source_arg: str | None) -> int:
    from ..validation import validate_index

    index_path = Path(index_arg).expanduser()
    if not index_path.is_file():
        print(f"error: index.json does not exist: {index_path}", file=sys.stderr)
        return 2
    try:
        index = read_json_path(index_path)
        result = validate_index(index, Path(source_arg) if source_arg else None)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(f"error: failed to validate index: {error}", file=sys.stderr)
        return 1
    stream = sys.stdout if result["valid"] else sys.stderr
    print(
        f"Index validation: {'PASS' if result['valid'] else 'FAIL'} "
        f"({result['errors']} errors, {result['warnings']} warnings)",
        file=stream,
    )
    for issue in result["issues"]:
        print(f"- {issue['severity'].upper()} {issue['code']}: {issue['message']}", file=stream)
    return 0 if result["valid"] else 1


def _graph(
    index_arg: str,
    query: str | None,
    output_arg: str,
    depth: int,
) -> int:
    index_path = Path(index_arg).expanduser()
    if not index_path.is_file():
        print(f"error: index.json does not exist: {index_path}", file=sys.stderr)
        return 2
    try:
        index = read_json_path(index_path)
        project = index.get("project")
        source = Path(str(project.get("path"))) if isinstance(project, dict) else Path(".")
        _require_valid_index(index, source)
        graph = build_capability_graph(index)
        result = (
            explore_capability_graph(graph, query, depth=depth)
            if query
            else graph
        )
        output = Path(output_arg).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        from ..persistence import atomic_write_text

        atomic_write_text(output, _json_artifact(result))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(f"error: failed to build capability graph: {error}", file=sys.stderr)
        return 1
    stats = graph["stats"]
    print(f"Generated capability graph: {output}")
    print(
        f"Graph contains {stats['nodes']} nodes, {stats['resolved_edges']} resolved edges, "
        f"{stats['components']} components and {stats['feature_slices']} feature slices."
    )
    if query:
        print(
            f"Query matched {len(result['matched_node_ids'])} nodes; "
            f"impact context contains {len(result['impact_node_ids'])} additional nodes."
        )
    return 0


def _prepare_report(index_arg: str, output_arg: str) -> int:
    index_path = Path(index_arg).expanduser()
    if not index_path.is_file():
        print(f"error: index.json does not exist: {index_path}", file=sys.stderr)
        return 2
    try:
        index = read_json_path(index_path)
        project = index.get("project")
        source = Path(str(project.get("path"))) if isinstance(project, dict) else Path(".")
        _require_valid_index(index, source)
        pack = build_report_pack(index)
        output = Path(output_arg).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        from ..persistence import atomic_write_text

        atomic_write_text(output, _json_artifact(pack))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(f"error: failed to prepare human report: {error}", file=sys.stderr)
        return 1
    print(f"Prepared model evidence packet: {output}")
    return 0


def _render_human_report(
    index_arg: str, narrative_arg: str, output_arg: str, should_open: bool
) -> int:
    index_path = Path(index_arg).expanduser()
    narrative_path = Path(narrative_arg).expanduser()
    if not index_path.is_file() or not narrative_path.is_file():
        print("error: index.json and narrative JSON must both exist", file=sys.stderr)
        return 2
    output = Path(output_arg).expanduser().resolve()
    try:
        index = read_json_path(index_path)
        narrative = read_json_path(narrative_path)
        project = index.get("project")
        source = Path(str(project.get("path"))) if isinstance(project, dict) else Path(".")
        _require_valid_index(index, source)
        capability_graph = build_capability_graph(index)
        pack = build_report_pack(index, capability_graph)
        composed = compose_human_report(index, narrative)
        generation_id = secrets.token_hex(16)
        canonical = _bind_generation(index, generation_id)
        pack = _bind_generation(pack, generation_id)
        narrative_artifact = _bind_generation(narrative, generation_id)
        composed = _bind_generation(composed, generation_id)
        artifacts = {
            "index.json": _json_artifact(canonical),
            "analysis-pack.json": _json_artifact(pack),
            "human-report.json": _json_artifact(narrative_artifact),
            "capability-graph.json": _json_artifact(
                _bind_generation(capability_graph, generation_id)
            ),
            "index.html": _html_artifact(render_report(composed), generation_id),
        }
        with OutputLock(output):
            GenerationPublisher(output, generation_id).publish(
                artifacts,
                before_switch=lambda: _require_valid_index(canonical, source),
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(f"error: failed to render human report: {error}", file=sys.stderr)
        return 1
    report = output / "index.html"
    print(f"Generated human-first repository report: {report}")
    print(f"Model narrative: {output / 'human-report.json'}")
    if should_open:
        webbrowser.open(report.as_uri())
    return 0
