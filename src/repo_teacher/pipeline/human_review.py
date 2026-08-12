"""Independent human-readability review stage for approved reports."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from ..persistence import read_json_path
from ..schemas import human_readability_review_json_schema
from .evidence_packets import (
    _build_chapter_batch_pack,
    _indexed_file_hashes,
    _materialize_source_slice,
    _stage_model_json,
)
from .prompt_contracts import human_readability_review_prompt
from .partitioning import INVENTORY_SOURCE_EXCERPT_BUDGET, require_packet_budget
from .report_contracts import _attach_source_excerpts
from .serialization import json_artifact


_RETRY_STAGES = {"none", "project-overview", "chapter-generation", "renderer"}
_ISSUE_CODES = {
    "project-essence-missing",
    "chapter-summary-not-one-liner",
    "thirty-second-restatement-failed",
    "interaction-diagram-not-concrete",
    "implementation-mechanism-missing",
    "technology-selection-missing",
    "evidence-location-missing",
}
_TOP_LEVEL_CHECKS = {
    "project_positioning",
    "chapter_coverage",
    "interaction_explainer",
    "implementation_depth",
    "selection_value",
}
_CHAPTER_CHECKS = {
    "summary_clarity",
    "interaction_diagram",
    "implementation_mechanism",
    "selection_signal",
}


def _report_source_paths(report_payload: dict[str, object]) -> set[str]:
    paths: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        if (
            isinstance(value.get("path"), str)
            and isinstance(value.get("line_start"), int)
            and isinstance(value.get("line_end"), int)
        ):
            paths.add(str(value["path"]))
        for item in value.values():
            if isinstance(item, (dict, list)):
                visit(item)

    visit(report_payload)
    return paths


def require_human_readability_review(
    payload: dict[str, object], capability_ids: Sequence[str]
) -> None:
    """Validate exact chapter coverage and PASS/FAIL consistency."""

    expected = list(capability_ids)
    checks = payload.get("checks")
    status = payload.get("status")
    overview = payload.get("project_overview_verdict")
    chapters = payload.get("chapter_verdicts")
    issues = payload.get("blocking_issues")
    retry_stage = payload.get("retry_stage")
    if not isinstance(checks, dict) or not isinstance(chapters, list) or not isinstance(
        issues, list
    ):
        raise ValueError("human readability review omitted checks, chapters, or issues")
    if retry_stage not in _RETRY_STAGES:
        raise ValueError("human readability review returned invalid retry_stage")
    if set(checks) != _TOP_LEVEL_CHECKS or any(
        checks.get(name) not in {"passed", "failed"} for name in _TOP_LEVEL_CHECKS
    ):
        raise ValueError("human readability review returned invalid top-level checks")
    if not isinstance(overview, dict):
        raise ValueError("human readability review omitted project overview verdict")
    if overview.get("status") not in {"pass", "fail"}:
        raise ValueError("human readability review returned invalid project overview status")
    if not isinstance(overview.get("summary"), str) or not overview["summary"].strip():
        raise ValueError("human readability review omitted project overview summary")
    if not isinstance(overview.get("missing_answers"), list) or any(
        not isinstance(item, str) or not item.strip()
        for item in overview["missing_answers"]
    ):
        raise ValueError("human readability review has invalid overview missing answers")
    if not isinstance(overview.get("evidence_locations"), list) or any(
        not isinstance(item, str) or not item.strip()
        for item in overview["evidence_locations"]
    ):
        raise ValueError("human readability review has invalid overview evidence locations")

    reviewed_ids: list[str] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise ValueError("human readability review returned a non-object chapter verdict")
        capability_id = chapter.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            raise ValueError("human readability review chapter verdict has no capability id")
        reviewed_ids.append(capability_id)
        if chapter.get("status") not in {"pass", "fail"}:
            raise ValueError("human readability review chapter verdict has invalid status")
        for field in ("one_liner", "thirty_second_restatement"):
            if not isinstance(chapter.get(field), str) or not str(chapter[field]).strip():
                raise ValueError(
                    f"human readability review chapter verdict omitted {field}"
                )
        chapter_checks = chapter.get("checks")
        missing_answers = chapter.get("missing_answers")
        evidence_locations = chapter.get("evidence_locations")
        if set(chapter_checks or {}) != _CHAPTER_CHECKS or any(
            chapter_checks.get(name) not in {"passed", "failed"}
            for name in _CHAPTER_CHECKS
        ):
            raise ValueError("human readability review chapter verdict has invalid checks")
        if not isinstance(missing_answers, list) or any(
            not isinstance(item, str) or not item.strip() for item in missing_answers
        ):
            raise ValueError("human readability review chapter missing_answers is invalid")
        if not isinstance(evidence_locations, list) or any(
            not isinstance(item, str) or not item.strip() for item in evidence_locations
        ):
            raise ValueError(
                "human readability review chapter evidence_locations is invalid"
            )
        chapter_all_passed = all(value == "passed" for value in chapter_checks.values())
        if chapter["status"] == "pass" and (missing_answers or not chapter_all_passed):
            raise ValueError("human readability review chapter claimed PASS with gaps")
        if chapter["status"] == "fail" and (not missing_answers or chapter_all_passed):
            raise ValueError("human readability review chapter claimed FAIL without gaps")
    if sorted(reviewed_ids) != sorted(expected) or len(reviewed_ids) != len(set(reviewed_ids)):
        raise ValueError("human readability review did not cover the exact capability set")

    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("human readability review returned a non-object blocking issue")
        if issue.get("code") not in _ISSUE_CODES:
            raise ValueError("human readability review returned an unknown issue code")
        capability_id = issue.get("capability_id")
        if capability_id not in set(expected) and capability_id != "":
            raise ValueError(
                "human readability review issue references an unknown capability"
            )
        if not isinstance(issue.get("location"), str) or not issue["location"].strip():
            raise ValueError("human readability review issue has no location")
        if not isinstance(issue.get("message"), str) or not issue["message"].strip():
            raise ValueError("human readability review issue has no message")
        if issue.get("retry_stage") not in _RETRY_STAGES - {"none"}:
            raise ValueError("human readability review issue has no valid retry stage")

    all_top_level_passed = all(value == "passed" for value in checks.values())
    overview_passed = overview["status"] == "pass" and not overview["missing_answers"]
    all_chapters_passed = all(
        isinstance(chapter, dict) and chapter.get("status") == "pass"
        for chapter in chapters
    )
    if status == "passed":
        if (
            issues
            or retry_stage != "none"
            or not all_top_level_passed
            or not overview_passed
            or not all_chapters_passed
        ):
            raise ValueError(
                "human readability review claimed PASS with failed checks or issues"
            )
    elif status == "failed":
        if issues:
            pass
        elif all_top_level_passed and overview_passed and all_chapters_passed:
            raise ValueError(
                "human readability review claimed FAIL without an actionable issue"
            )
        if retry_stage == "none":
            raise ValueError(
                "human readability review claimed FAIL without retry stage"
            )
    else:
        raise ValueError("human readability review returned an invalid status")


def run_human_readability_review(
    *,
    source: Path,
    pack: dict[str, object],
    inventory_payload: dict[str, object],
    report_payload: dict[str, object],
    workspace: Path,
    provider: str,
    timeout: int,
    runner: Callable[..., dict[str, object]],
    stage_slug: str = "human-readability-review",
) -> dict[str, object]:
    """Run an independent human-readable content review over the final report."""

    capabilities = [
        item
        for item in inventory_payload.get("capabilities", [])
        if isinstance(item, dict)
    ]
    capability_ids = [str(item.get("id") or "") for item in capabilities]
    if any(not identifier for identifier in capability_ids):
        raise ValueError("human readability review received an empty capability id")
    review_workspace = workspace / stage_slug
    review_workspace.mkdir(parents=True, exist_ok=True)
    review_path = review_workspace / "human-readability-review.json"
    if review_path.is_file():
        try:
            cached = read_json_path(review_path)
            require_human_readability_review(cached, capability_ids)
            return cached
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass

    review_pack = _build_chapter_batch_pack(pack, copy.deepcopy(capabilities))
    review_pack["approved_inventory"] = copy.deepcopy(inventory_payload)
    review_pack["final_human_report"] = copy.deepcopy(report_payload)
    extra_paths = _report_source_paths(report_payload)
    scope = review_pack.get("scope")
    if isinstance(scope, dict):
        allowed_paths = {
            str(path)
            for path in scope.get("allowed_source_paths", [])
            if isinstance(path, str)
        }
        scope["allowed_source_paths"] = sorted(allowed_paths | extra_paths)
    review_pack = _attach_source_excerpts(
        review_pack,
        source,
        character_budget=INVENTORY_SOURCE_EXCERPT_BUDGET,
    )
    # Inventory and report are passed as separate immutable model artifacts.
    # Keep them only long enough to derive exact source excerpts; duplicating
    # them plus the full capability graph in the review packet is unnecessary.
    review_pack.pop("approved_inventory", None)
    review_pack.pop("final_human_report", None)
    review_pack.pop("capability_graph", None)
    review_pack.pop("feature_hints", None)
    review_pack.pop("evidence", None)
    review_pack.pop("capabilities", None)
    review_pack["review_evidence_contract"] = (
        "Read the separate approved inventory and final report artifacts, then "
        "challenge their claims against these excerpts and allowed source files."
    )
    require_packet_budget(review_pack)
    packet_path = review_workspace / "analysis-pack-review.json"
    packet_path.write_text(json_artifact(review_pack), encoding="utf-8")
    report_path = review_workspace / "human-report.json"
    report_path.write_text(json_artifact(report_payload), encoding="utf-8")
    source_slice = _materialize_source_slice(
        source,
        review_workspace,
        review_pack["scope"]["allowed_source_paths"],
        _indexed_file_hashes(pack),
    )
    model_packet_path = _stage_model_json(
        source_slice, "analysis-pack-review.json", review_pack
    )
    model_inventory_path = _stage_model_json(
        source_slice, "capability-inventory.json", inventory_payload
    )
    model_report_path = _stage_model_json(source_slice, "human-report.json", report_payload)
    review = runner(
        source=source_slice,
        workspace=review_workspace,
        schema=human_readability_review_json_schema(capability_ids),
        prompt=human_readability_review_prompt(
            model_packet_path,
            model_inventory_path,
            model_report_path,
            source_slice,
            capability_ids,
        ),
        timeout=timeout,
        stage_slug=stage_slug,
        progress_label=f"{provider} 正在人类视角审校 {len(capability_ids)} 个章节",
        provider=provider,
    )
    require_human_readability_review(review, capability_ids)
    review["schema_version"] = "repolens-human-readability-review/v1"
    review["reviewer"] = "human-report-reviewer"
    review_path.write_text(json_artifact(review), encoding="utf-8")
    return review
