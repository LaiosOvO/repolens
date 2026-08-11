from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .capability_graph import build_capability_graph, explore_capability_graph
from .indexer import _integrity_digest, build_index
from .human_report import build_report_pack, compose_human_report, human_report_json_schema
from .models import redact_persisted_value
from .persistence import (
    GenerationPublisher,
    OutputLock,
    read_json_path,
    read_published_json,
)
from .report import render_report


REPORT_SYNTHESIS_CONTRACT_VERSION = "global-graph-business-capability-v9"


def _bind_generation(payload: dict[str, object], generation_id: str) -> dict[str, object]:
    bound = redact_persisted_value(copy.deepcopy(payload))
    bound["generation_id"] = generation_id
    if "integrity_sha256" in bound:
        bound["integrity_sha256"] = _integrity_digest(bound)
    return bound


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
    from .validation import validate_index

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
                "index.html": _html_artifact(render_report(result), generation_id),
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


def _model_prompt(pack_path: Path, source: Path) -> str:
    return f"""你是一名面向技术决策者的代码库教师。请完整读取 {pack_path}，并按需检查仓库
{source} 中的源码。JSON 写作合同位于 {pack_path.with_name('human-report-schema.json')}。
只返回一个 JSON object，不要 Markdown 围栏、前言或解释；报告语言为简体中文。

## 目标读者与最终目的
读者不是在找 main、类名或调用链，而是在判断“这个项目提供什么能力、每项能力究竟怎样工作、
难点和代价是什么、哪些实现值得复用”。最终 HTML 必须让第一次接触仓库的人先读懂系统，
再把源码入口作为证据下钻。不要把文件、函数、类、路由、CLI 命令直接提升为功能章节。

## 先在内部完成的分析（不要把这些步骤原样输出）
1. 从具体用户动作出发，归纳全部用户可感知的产品能力；不要设固定数量上限。只有行为、状态与实现
   机制相同的多个入口才可合并，最后做一次 coverage pass，确保每个独立用户动作都归属某章或列入缺口。
2. 为每项能力识别参与对象/核心抽象、它们之间的关系，以及一个从触发到可见结果的中心用例。
3. 按依赖关系选择教学顺序：先讲用途和最小心智模型，再讲数据/控制流，最后才讲实现与源码。
4. 沿真实源码追踪状态变化、分支、循环、并发边界、失败路径和停止条件；识别最难保持的不变量。
5. 区分源码已证实、合理推断和未知。只有证据包中的 canonical feature/evidence ID 可以被引用。

## 每个功能章节的强制叙述合同
- `title` 必须是用户能理解的能力名；禁止使用 main、API endpoint、文件名、类名或函数名充当标题。
- `plain_summary` 先直接回答“它本质上是什么、实际做了哪段因果过程、它不是什么”。这必须是完整
  句子，不能只写“负责/管理/处理/编排某事”，也不能只是名词和技术标签。
- 先用一个具体用户动作解释为什么需要它，再列参与对象及角色，然后讲清输入 → 处理 → 输出 → 消费者。
- `runtime_story.steps` 和 `state_flow` 必须是有因果关系的实际运行顺序；每步写清读什么、写什么，
  以及为什么下一步此时才可以开始。不要把文件阅读顺序冒充运行顺序。
- `mechanism_model` 必须说明实际的数据结构或控制结构。源码能证明时，明确写出 for、while、事件循环、
  状态机、队列、DAG、索引、事务或线程池等具体构造；证据不足时写 unknown，禁止猜测。
- `worked_example` 至少三步，必须使用具体对象和值展示前后状态和分支原因，不能重复抽象字段名。
- `difficulty_map` 识别实现真正困难的地方：需要保持的不变量、最朴素实现为何会错、失败如何显现、
  当前方案用什么代价换取什么性质。不要把“代码复杂”“需要测试”当作难点。
- 每章至少给出 3 个 `source_refs`，其中至少 1 个必须来自非 docs/specs/README 的实现或测试源码。
  文档和 Spec 只能用于导航或核对范围，不能单独证明功能已经实现。每个 source ref 必须给仓库相对路径、
  精确起止行和该切片实际证明的 claim；不得引用生成目录、依赖目录或反向解包资产来冒充当前实现。
- 最后才给源码证据、设计取舍、支持/不支持边界和 take/adapt/avoid/verify 复用建议。

## 按机制类型必须回答的问题
- 存储/记忆：事实源在哪里；原始事件、派生事实/episode、索引如何区分；写入何时提交；失败是否回滚；
  查询是否先过 gate；如何过滤、召回、排序、Top-K、合并与去重。不存在独立存储或搜索层也要直说。
- Agent Loop：它是否真的是循环；源码中的具体循环构造是什么；一轮读取什么；模型结果如何决定直接
  返回或调用工具；工具结果怎样写回下一轮；continue/return/break/最大轮次分别在什么条件触发。
- Graph/Workflow：图在何时由哪些节点、边、依赖和 router 构建；节点何时 ready；并行的最小单位、
  wave/barrier 等待和状态合并规则；冲突如何处理；router 在什么时候读取哪份 state、执行什么判定、
  输出 label 还是目标、是否只选路而不执行工作；没有 ready 节点如何结束；运行中能否安全改拓扑。
- Voice/流式管线：录音何时开始/结束；VAD 或其他边界如何切段；ASR、Agent、TTS 谁先谁后；阶段之间
  传递完整缓冲还是增量流；播放期间是否能监听和打断；它是串行轮次、半双工还是真全双工；背压、
  取消和错误在哪一层处理。仅写“连接 ASR/LLM/TTS”不合格。
- Router/Dispatcher：输入是什么、规则或函数是什么、输出是什么、何时调用、谁消费输出；必须区分
  “选择下一步”和“执行下一步”。仅写“Router 决定路由”不合格。
- 并发：说明为什么这些工作彼此独立才可并发；是 gather、线程池、任务队列还是别的构造；等待点、
  共享状态可见性、结果合并顺序、冲突与失败传播必须明确。

## 证据与反空话规则
- 每个重要机制、难点和边界都绑定 evidence ID；没有证据的行为放入 unsupported/unknowns。
- source_refs 必须来自你实际打开过的当前仓库源码；禁止根据 Spec 标题、路由名或文件名猜测实现。
- 禁止把“X manages Y”“循环推理”“Router 决定”“支持动态工作流”“实时语音”等口号当作解释。
- 禁止为了凑章节而枚举内部辅助函数；宁可减少章节，也不要制造假功能。
- 不要求固定数量的源码文件；证据只取足以证明该判断的最小集合。

使用 generator.name=Codex，generator.method=repo-teacher human-first capability synthesis。
"""


def _source_ref_schema() -> dict[str, object]:
    text = {"type": "string", "minLength": 1, "maxLength": 12_000}
    return {
        "type": "object",
        "properties": {
            "path": text,
            "line_start": {"type": "integer", "minimum": 1},
            "line_end": {"type": "integer", "minimum": 1},
            "claim": text,
        },
        "required": ["path", "line_start", "line_end", "claim"],
        "additionalProperties": False,
    }


def _inventory_json_schema() -> dict[str, object]:
    text = {"type": "string", "minLength": 1, "maxLength": 12_000}
    string_list = {"type": "array", "items": text, "minItems": 1}
    implementation_module = {
        "type": "object",
        "properties": {
            "path": text,
            "classification": {
                "type": "string",
                "enum": ["core", "supporting"],
            },
            "responsibility": text,
            "handoff": text,
        },
        "required": ["path", "classification", "responsibility", "handoff"],
        "additionalProperties": False,
    }
    capability = {
        "type": "object",
        "properties": {
            "id": text,
            "title": text,
            "summary": text,
            "mechanism": text,
            "question": text,
            "use_when": text,
            "distinguish": text,
            "plain_summary": text,
            "importance": {
                "type": "string",
                "enum": [
                    "core-journey",
                    "differentiator",
                    "dependent-capability",
                    "supporting",
                ],
            },
            "user_actor": text,
            "user_goal": text,
            "visible_outcome": text,
            "product_surface": text,
            "causal_flow": text,
            "why_one_capability": text,
            "implementation_modules": {
                "type": "array",
                "items": implementation_module,
                "minItems": 1,
            },
            "source_feature_ids": string_list,
            "evidence_ids": string_list,
            "source_refs": {
                "type": "array",
                "items": _source_ref_schema(),
                "minItems": 3,
            },
        },
        "required": [
            "id",
            "title",
            "summary",
            "mechanism",
            "question",
            "use_when",
            "distinguish",
            "plain_summary",
            "importance",
            "user_actor",
            "user_goal",
            "visible_outcome",
            "product_surface",
            "causal_flow",
            "why_one_capability",
            "implementation_modules",
            "source_feature_ids",
            "evidence_ids",
            "source_refs",
        ],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "capabilities": {
                "type": "array",
                "items": capability,
                "minItems": 1,
            },
            "module_dispositions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "path": text,
                        "disposition": {
                            "type": "string",
                            "enum": ["core-capability", "supporting", "excluded"],
                        },
                        "capability_ids": {
                            "type": "array",
                            "items": text,
                        },
                        "reason": text,
                    },
                    "required": [
                        "path",
                        "disposition",
                        "capability_ids",
                        "reason",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["capabilities", "module_dispositions"],
        "additionalProperties": False,
    }


def _inventory_group_json_schema() -> dict[str, object]:
    text = {"type": "string", "minLength": 1, "maxLength": 12_000}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": text,
                        "title": text,
                        "user_actor": text,
                        "user_goal": text,
                        "visible_outcome": text,
                        "product_surface": text,
                        "causal_flow": text,
                        "why_one_capability": text,
                        "member_ids": {
                            "type": "array",
                            "items": text,
                            "minItems": 1,
                        },
                    },
                    "required": [
                        "id", "title", "user_actor", "user_goal",
                        "visible_outcome", "product_surface", "causal_flow",
                        "why_one_capability", "member_ids",
                    ],
                    "additionalProperties": False,
                },
            },
            "excluded_supporting_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "member_id": text,
                        "reason": text,
                    },
                    "required": ["member_id", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["groups", "excluded_supporting_items"],
        "additionalProperties": False,
    }


def _project_overview_json_schema(capability_count: int) -> dict[str, object]:
    text = {"type": "string", "minLength": 1, "maxLength": 12_000}
    string_list = {"type": "array", "items": text, "minItems": 1}
    source_refs = {
        "type": "array",
        "items": _source_ref_schema(),
        "minItems": 1,
    }
    runtime_component = {
        "type": "object",
        "properties": {
            "name": text,
            "responsibility": text,
            "communication": text,
            "state": text,
            "source_refs": source_refs,
        },
        "required": [
            "name",
            "responsibility",
            "communication",
            "state",
            "source_refs",
        ],
        "additionalProperties": False,
    }
    directory = {
        "type": "object",
        "properties": {
            "path": text,
            "responsibility": text,
            "layer": text,
            "boundary": text,
            "source_refs": source_refs,
        },
        "required": ["path", "responsibility", "layer", "boundary", "source_refs"],
        "additionalProperties": False,
    }
    journey_step = {
        "type": "object",
        "properties": {
            "stage": text,
            "actor": text,
            "action": text,
            "state_change": text,
            "next": text,
        },
        "required": ["stage", "actor", "action", "state_change", "next"],
        "additionalProperties": False,
    }
    product_axis = {
        "type": "object",
        "properties": {
            "id": text,
            "title": text,
            "one_liner": text,
            "user_outcome": text,
            "end_to_end_flow": string_list,
            "capability_ids": string_list,
            "source_refs": source_refs,
        },
        "required": [
            "id", "title", "one_liner", "user_outcome",
            "end_to_end_flow", "capability_ids", "source_refs",
        ],
        "additionalProperties": False,
    }
    engineering_structure = {
        "type": "object",
        "properties": {
            "repository_shape": text,
            "architecture_pattern": text,
            "pattern_reasoning": text,
            "frontend_organization": text,
            "backend_organization": text,
            "worker_and_async_organization": text,
            "shared_contracts": text,
            "dependency_rule": text,
            "media_organization": text,
            "source_refs": source_refs,
        },
        "required": [
            "repository_shape",
            "architecture_pattern",
            "pattern_reasoning",
            "frontend_organization",
            "backend_organization",
            "worker_and_async_organization",
            "shared_contracts",
            "dependency_rule",
            "media_organization",
            "source_refs",
        ],
        "additionalProperties": False,
    }
    overview = {
        "type": "object",
        "properties": {
            "one_liner": text,
            "product_type": text,
            "primary_user": text,
            "problem": text,
            "core_journey": {
                "type": "array",
                "items": journey_step,
                "minItems": 3,
            },
            "core_product_axes": {
                "type": "array",
                "items": product_axis,
                "minItems": 1,
                "maxItems": 4,
            },
            "supporting_capability_ids": {
                "type": "array",
                "items": text,
            },
            "architecture_summary": text,
            "architecture_style": text,
            "engineering_structure": engineering_structure,
            "execution_model": text,
            "runtime_components": {
                "type": "array",
                "items": runtime_component,
                "minItems": 2,
            },
            "frontend_backend_boundary": text,
            "data_and_state": text,
            "deployment_shape": text,
            "code_organization": {
                "type": "array",
                "items": directory,
                "minItems": 2,
            },
            "differentiator": text,
            "not_this": string_list,
            "source_refs": {
                "type": "array",
                "items": _source_ref_schema(),
                "minItems": 3,
            },
            "capability_order": {
                "type": "array",
                "items": text,
                "minItems": capability_count,
                "maxItems": capability_count,
            },
        },
        "required": [
            "one_liner",
            "product_type",
            "primary_user",
            "problem",
            "core_journey",
            "core_product_axes",
            "supporting_capability_ids",
            "architecture_summary",
            "architecture_style",
            "engineering_structure",
            "execution_model",
            "runtime_components",
            "frontend_backend_boundary",
            "data_and_state",
            "deployment_shape",
            "code_organization",
            "differentiator",
            "not_this",
            "source_refs",
            "capability_order",
        ],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"project_overview": overview},
        "required": ["project_overview"],
        "additionalProperties": False,
    }


def _chapter_batch_json_schema(max_items: int) -> dict[str, object]:
    chapter_item = copy.deepcopy(
        human_report_json_schema()["properties"]["chapters"]["items"]
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "chapters": {
                "type": "array",
                "items": chapter_item,
                "minItems": 1,
                "maxItems": max_items,
            }
        },
        "required": ["chapters"],
        "additionalProperties": False,
    }


def _inventory_prompt(pack_path: Path, source: Path) -> str:
    return f"""你是一名面向技术决策者的代码库教师。只读取整仓代码图证据包 {pack_path}，
源码切片位于 {source}。你现在只做第一阶段：一次性产出整仓“业务/框架功能目录”，不要写完整教程章节。
只返回一个 JSON object，不要 Markdown 围栏、前言或解释；报告语言为简体中文。

## 目标
- 识别当前仓库里全部独立的用户可感知能力，不设固定数量上限。
- 一个 capability 必须对应一个独立用户动作或结果；只有行为、状态和实现机制都相同的入口才可合并。
- 目录顺序就是建议阅读顺序：先让人理解系统，再下钻源码。
- 先联合阅读 capability_graph 的 capability_candidates、feature_slices、mechanism_clusters、components、
  module_dependencies 与 modules。代码图负责给出整仓关系和模块边界；模块是判断功能的输入与实现视图，
  但模块名本身不是功能名。
- capability_candidates 主要来自已识别入口，通常不完整，也可能偏向 CLI、测试或示例；它们的数量绝不等于
  项目的功能数量。必须用 components 的全局中心、mechanism_clusters、modules、README 产品定位和源码摘录
  主动发现框架核心能力，尤其检查主数据流、会话/传输、状态/轮次、处理管线、服务适配与 Worker 等区域。
- 这是唯一一次全局功能判断。禁止把模块分别当作独立项目，也禁止按目录逐个制造功能。
- source_excerpts 已包含本次判断所需的代表性实现源码。先用 `cat` 读取证据包；需要核对时只可用
  `cat` 或 `sed -n` 读取 scope.allowed_source_paths，禁止 rg、grep、find、tree 和整仓重扫。

## 绝对要求
- capability 是产品向用户提供的结果，不是“代码里存在的一条可调用路径”。每项输出前必须能回答：
  谁为了什么用户目标触发它、系统改变了什么业务状态或交付了什么可见结果、核心因果链是什么。
- 健康/就绪探针、metrics、静态根页、文档页、smoke test、fixture、样本生成、构建发布脚本、
  仅供内部诊断的路由属于工程支撑面，不得独立输出为 capability；它们只能作为某项产品能力的支撑证据。
  只有当仓库本身的主要产品就是监控、静态托管或开发工具时，对应用户工作流才可能成为产品能力。
- 通用 UI primitive、全局 context、API/tRPC 路由骨架、日志/错误页、feature flag、测试页面等横切基础设施
  不是独立产品功能；把它们作为相关用户旅程的实现支撑，或从功能目录排除。
- title 必须是用户能理解的功能名，不能用 main、文件名、路由名、类名、函数名当标题。
- plain_summary 必须直接回答“它本质上是什么、实际做了哪段因果过程、它不是什么”。
- summary、question、use_when、distinguish 要站在技术选型读者视角，帮助判断这个能力是否值得继续看。
- source_feature_ids 和 evidence_ids 只能引用 analysis pack 里已有的 canonical id。
- 每个 capability 至少 3 个 source_refs，且至少 1 个来自非 docs/specs/README 的实现或测试源码。
- Spec、README、docs 只能导航，不能单独证明功能已实现。
- 禁止把入口、helper、内部工具函数、目录名直接冒充功能。
- 先核对 capability_graph.capability_candidates，再用 feature_slices / module_dependencies / source_refs 补证据；不要回到“整仓自由归纳”。
- 最后做一次 coverage pass，确保每个独立用户动作都已归入 capabilities 或被明确排除；这里只输出已实现能力。
- 必须逐个交代 scope.required_product_module_paths 中的产品实现模块：它是某项核心能力、某项能力的支撑，
  还是不应进入功能目录。每个路径在 module_dispositions 中恰好出现一次；不能只读 CLI/route 候选就结束。
  core-capability 必须绑定至少一个 capability id；supporting/excluded 也必须说明它实际支撑什么或为何排除。
- capability.importance 用于阅读排序：core-journey 是用户完成主要目标的主链；differentiator 是项目相对同类
  真正值得借鉴的机制；dependent-capability 是主链依赖的完整能力；supporting 仅在其本身仍有稳定对外结果时使用。
- examples/testing/documentation/engineering-support 不在必须覆盖的产品模块集合里；只能补充真实产品模块的
  worked example 或证据，绝不能因为文件多、路由多就压过核心框架实现。
- 每项能力都要给 implementation_modules：列出共同完成这项能力的核心模块与支撑模块，说明责任和交接。
  一个能力可以跨多个模块；一个模块也可以支撑多个能力。不要把这种多对多关系压扁成“一个模块等于一个功能”。
  implementation_modules.path 必须逐字选自证据包 modules[].path；不要填文件路径。examples/testing/documentation
  类模块只能标 supporting，且不能单独证明核心能力。

## 对每个 capability 需要给出的字段
- id: 稳定短 id，kebab-case。
- title
- summary
- mechanism: 一句话点出最核心机制，如 agent-loop、graph-workflow、memory-search、websocket-session、plugin-runtime。
- question: 这章读者最该搞懂的实现问题。
- use_when: 什么时候你会因为这个能力考虑复用该项目。
- distinguish: 它和看起来相似的另一类实现有什么本质区别。
- plain_summary
- importance
- user_actor、user_goal、visible_outcome、product_surface、causal_flow、why_one_capability
- implementation_modules: path、classification(core/supporting)、responsibility、handoff
- source_feature_ids
- evidence_ids
- source_refs
- module_dispositions: path、disposition、capability_ids、reason；必须完整覆盖
  scope.required_product_module_paths，不能遗漏，也不能加入其它路径。

使用 generator.name=Codex，generator.method=repo-teacher global graph business capability synthesis。
"""


def _inventory_shard_prompt(
    pack_path: Path,
    source: Path,
    module_paths: Sequence[str],
) -> str:
    focused_modules = ", ".join(module_paths)
    return f"""你是一名面向技术决策者的代码库教师。只读取这个分片证据包：
{pack_path}
源码仓库位于 {source}。只返回一个 JSON object，不要 Markdown 围栏、前言或解释；
报告语言为简体中文。

## 本次范围
- 主模块：{focused_modules}
- 先读 capability_graph.capability_candidates、feature_slices 和 resolved_edges，再按需打开源码。
- source_excerpts 已包含本次判断所需的源码切片。先用 `cat` 读取分片包；需要核对时只可用
  `cat` 或 `sed -n` 读取 scope.allowed_source_paths，禁止 rg、grep、find、tree；禁止重新扫描整个仓库。
- 只能使用 scope.allowed_source_paths 中明确列出的源码；不得自由遍历其它目录。
- 跨模块源码只有在图中已证明是调用者、消费者、状态读写点或依赖端点时才会进入允许列表。

## 目标
- 识别这个分片中全部独立的用户可感知能力，不设固定数量上限。
- 一个 capability 必须对应一个独立用户动作或结果；行为、状态和实现机制都相同才可合并。
- 每项输出前必须能明确说明用户目标、产品状态变化或可见结果以及完整因果链。只有 HTTP 可达、
  测试通过或脚本可运行不构成产品能力。
- 健康/就绪探针、metrics、静态根页、文档页、smoke test、fixture、样本生成、构建发布脚本、
  内部诊断路由属于工程支撑面，不得独立输出；只能作为产品能力的支撑证据。若仓库本身就是
  监控、静态托管或开发工具，才按它实际交付的用户工作流判断。
- 通用 UI primitive、全局 context、API/tRPC 路由骨架、日志/错误页、feature flag、测试页面等
  横切基础设施不是独立产品功能；只能并入真实用户旅程或排除。
- 图候选只是阅读起点；必须用源码与测试证据确认，不能把目录、入口、类或 helper 直接冒充功能。
- 最后做 coverage pass：每个 graph candidate 都必须被纳入某项能力，或因不是用户能力而被排除；这里只输出已确认能力。

## 输出质量
- title 是用户能理解的功能名。
- plain_summary 第一段直接说“它本质是什么、实际走哪段因果过程、又不是什么”。
- mechanism、question、use_when、distinguish 帮助技术选型，不写入口调用清单。
- source_feature_ids 与 evidence_ids 只能引用分片包中的 canonical id。
- 每项至少 3 个 source_refs，至少 1 个为非 docs/specs/README 的实现或测试源码。
- source_refs 只能来自 scope.allowed_source_paths；无证据的能力不能输出。

字段严格使用 capability inventory schema：id、title、summary、mechanism、question、use_when、
distinguish、plain_summary、source_feature_ids、evidence_ids、source_refs。
使用 generator.name=Codex，generator.method=repo-teacher graph-bounded inventory synthesis。
"""


def _project_overview_prompt(
    pack_path: Path,
    source: Path,
    capability_ids: Sequence[str],
) -> str:
    identifiers = ", ".join(capability_ids)
    return f"""你是一名面向技术选型读者的首席架构师。只读取有界证据包 {pack_path}，
源码切片位于 {source}。先用 `cat` 读取证据包；需要核对时只可用 `cat` 或 `sed -n` 读取
scope.allowed_source_paths，禁止 rg、grep、find、tree 和整仓重扫。只返回 JSON object。

你要写报告的第 0 章与第 1 章：先说明“这是什么项目”，再说明它的整体运行架构、
前后端/控制面/Worker/数据层边界，以及主要代码目录分别封装什么。不能从入口函数开始讲。

## 必须回答
- one_liner 第一词句就给出项目定义、主要用户与最终结果；不能写“这是一个包含很多模块的系统”。
- 先读 product_navigation 中的根 README/项目元数据，用它确认作者宣称的产品定位；README 只能证明
  “项目自称什么”，具体实现仍必须由非文档 source_refs 证明。
- core_product_axes 只能有 1–4 条产品主轴，是用户认识这个产品时最先讲的高层能力，不是 15 个同级模块。
  例如语音 Agent 平台应优先是“实时语音通话平台”和“可视化 Agent 工作流平台”，电话接入、
  STT/LLM/TTS、MCP、知识库、评测、配额、鉴权等应归属主轴或降为支撑能力。
- 每个 capability id 最多归属一条 core_product_axis。不直接产生核心用户结果的 id 放入
  supporting_capability_ids；两者必须刚好覆盖 capability_order 的全部 id。
- core_journey 必须是一条真实端到端主链，每步写 actor、动作、状态变化和下一跳。
- 如果是平台提交任务再由 Worker 完成，必须具体说明提交、持久化或排队、调度/租约、Worker 执行、
  事件/结果回传分别由谁负责；没有源码证据的环节明确写未知，不能补成常见架构。
- architecture_style 说明更接近 DDD、分层架构、模块化单体、客户端/服务器、事件驱动、插件式、
  控制面/数据面或其它组合，并说明源码事实，不可只贴标签。
- engineering_structure 是“项目工程结构”，必须直接判断 repository 是 monorepo、单包或多服务，
  代码是 DDD、分层、模块化单体、端到端 feature slice 还是混合结构。不能因为出现 domain 目录就写 DDD；
  要根据依赖方向、业务规则放置和端口/适配器边界说明 pattern_reasoning。
- engineering_structure 还要分别说清前端、后端、Worker/异步任务、共享协议/类型的代码组织，
  以及谁可以依赖谁。没有 Worker 或共享层时明确写“未发现”，不得臆造。
- 媒体项目必须在 engineering_structure.media_organization 中说明前端采集、会话/房间、信令、媒体传输、
  VAD/ASR/录制/回放的代码分布；未找到的环节按证据写未知。
- runtime_components 讲运行时组件怎样通信、各自持有什么状态。
- 如果项目核心包含语音或视频，one_liner 与 architecture_summary 必须优先说明媒体实现：采集端、
  会话/房间、信令与媒体传输协议、P2P/SFU/服务端中转、VAD/ASR/录制/回放是否存在、流式还是整段；
  同时说明面试/会议等业务会话如何驱动媒体链。没有证据的环节明确写未知。
- code_organization 覆盖重要产品源码目录；逐项说明职责、所属层和边界。不要枚举 assets、fixture、
  生成物或 vendor，也不要把文件树当架构。
- frontend_backend_boundary、data_and_state、deployment_shape 都必须明确；未知就说明未知。
- not_this 明确至少两种容易误解的定位。
- source_refs 以及 runtime_components/code_organization 内的 source_refs 只能引用 pack 的
  scope.allowed_source_paths，并指向真实实现行。

## 功能排序
capability_order 必须是以下 id 的精确全排列：{identifiers}
排序规则：核心用户旅程和差异化业务能力最先；其直接依赖其次；接入、配置、管理最后。
语音/视频面试平台必须先讲面试会话和实时媒体链，再讲通用 UI、账户、API 或运行支撑。
通用 UI、API/RPC 骨架、健康检查、测试与工程脚本不应出现在这些 id 中；若仍出现，也放最后并在
架构说明中明确它只是支撑面。
"""


def _chapter_batch_prompt(
    pack_path: Path,
    inventory_path: Path,
    source: Path,
    capability_ids: Sequence[str],
) -> str:
    capability_list = ", ".join(capability_ids)
    return f"""你是一名面向技术决策者的代码库教师。只读取批次证据包 {pack_path} 与
功能目录 {inventory_path}。源码仓库位于 {source}。你现在只完成第二阶段中的一个章节批次。
只返回一个 JSON object，不要 Markdown 围栏、前言或解释；报告语言为简体中文。

## 本批次必须完成的 capability
{capability_list}

## 绝对要求
- 只为上面列出的 capability 输出章节；不能新增、删除或改名。
- source_excerpts 已包含本批次所需源码。先用 `cat` 读取批次包与功能目录；需要核对时只可用
  `cat` 或 `sed -n` 读取 scope.allowed_source_paths，禁止 rg、grep、find、tree 和整仓重扫。
- 只能使用批次包 scope.allowed_source_paths 中明确列出的源码。
- 每个 chapter 的 id 和 title 必须与 capability inventory 完全一致。
- example、demo 和 sample 只能作为相关业务能力的 worked_example 或源码证据出现，不能把示例名称重新提升为章节。
- source_feature_ids 必须与 inventory 一致；evidence_ids 不能丢掉 inventory 已确认的证据。
- source_refs 必须来自你实际打开过的当前仓库源码；至少 3 个，且至少 1 个来自非 docs/specs/README 的实现或测试源码。
- 读者是做技术选型的人，不是追入口调用链的人；先讲功能和机制，再给源码证据。
- 先读 capability inventory 的 implementation_modules。construction.objects 必须覆盖这些核心模块，
  并按实际交接顺序说明“哪个模块产生什么，交给哪个模块继续处理”；支撑模块要明确标成支撑，
  不能与用户功能并列。一个功能跨模块时必须把跨模块链讲完整，不能只挑入口所在目录。
- 必须写清 storage/write/read、control loop、decision、termination、dynamic behavior。
- 如果涉及 Memory、Loop、Graph、Voice、Router、并发，必须把对应具体机制讲透：
  存储在哪里、何时写入、如何查询、是否 gate/filter/rank/merge；
  是否真的是循环、具体是 for/while/事件循环哪一种；
  图在何时构建、router 在什么时候读哪份 state、输出什么、谁消费；
  并发为什么安全、等待点在哪里、结果如何合并；
  Voice 是串行、半双工还是真全双工，谁先谁后，缓冲还是增量流。
- docs/spec/README 只能导航，不能单独当作实现证据。
- 没有证据的内容写进 unsupported 或 unknowns，不能补写成事实。

## 输出目标
- 返回 final HumanReport chapter contract 对应的完整 `chapters` 数组，只包含本批次章节。
- 每章必须把“它本质上怎么运行”和“真正难点是什么”讲清楚，不能停留在“负责/管理/处理/编排”。

使用 generator.name=Codex，generator.method=repo-teacher batched capability chapter synthesis。
"""


def _inventory_merge_prompt(inventory_path: Path) -> str:
    return f"""你现在做 inventory 合并阶段。请完整读取 {inventory_path}，只返回一个 JSON object。

目标：
- 把多个模块分片产出的 capability 列表合并成一个最终 capability inventory。
- 合并重复项时，只能在“用户动作、状态变化和核心机制都相同”时合并。
- 保留每个 capability 最能证明它存在的 source_refs 与 evidence_ids，至少 3 个 source_refs，且至少 1 个来自非 docs/specs/README 的实现或测试源码。
- 最终顺序按技术选型读者最容易理解的教学顺序排列。

规则：
- 只基于 inventory 文件里已有的 source_refs、evidence_ids 和摘要做合并与重排；不要发明新能力。
- title 必须继续保持人类可读；不能退化成文件名、路由名、类名或函数名。
- 如果两个 capability 看起来相似但 question、distinguish、plain_summary 或 source_refs 指向不同机制，就不要合并。

输出字段使用与 capability inventory 相同的 schema。
使用 generator.name=Codex，generator.method=repo-teacher capability inventory merge。
"""


def _run_deepseek_json(
    *,
    schema: dict[str, object],
    prompt: str,
    timeout: int,
    progress_label: str,
) -> dict[str, object]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is required for --provider deepseek")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
    schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    started = time.monotonic()
    print(f"[report 4/6] {progress_label}（DeepSeek JSON）…", flush=True)
    result: object | None = None
    last_error: Exception | None = None
    for attempt in range(2):
        retry_instruction = ""
        if attempt:
            retry_instruction = (
                "\n\n上一次响应无法解析。这次必须输出完整、紧凑的单个 JSON object；"
                "不要代码围栏，不要前后文，不要截断。"
            )
            print(
                f"[report 4/6] {progress_label}返回了不完整 JSON；自动重试 1/1…",
                flush=True,
            )
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是代码库技术教师。必须只返回符合所给 JSON Schema 的一个 JSON object；"
                            "不要 Markdown，不要解释。JSON Schema：" + schema_text
                        ),
                    },
                    {"role": "user", "content": prompt + retry_instruction},
                ],
                "response_format": {"type": "json_object"},
                "stream": False,
                "temperature": 0.0 if attempt else 0.1,
                "max_tokens": 8192,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            result = _decode_json_object(content)
            break
        except HTTPError as error:
            detail = error.read(2_000).decode("utf-8", errors="replace")
            raise ValueError(
                f"DeepSeek synthesis failed with HTTP {error.code}: {detail}"
            ) from error
        except (TimeoutError, URLError) as error:
            raise ValueError(
                f"DeepSeek synthesis failed: {type(error).__name__}"
            ) from error
        except (
            KeyError,
            IndexError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            last_error = error
    if not isinstance(result, dict):
        raise ValueError("DeepSeek synthesis returned invalid JSON") from last_error
    print(
        f"[report 4/6] {progress_label}完成，耗时 {time.monotonic() - started:.1f}s",
        flush=True,
    )
    return result


def _find_opencode() -> str | None:
    configured = os.environ.get("REPO_TEACHER_OPENCODE_BIN", "").strip()
    if configured and Path(configured).is_file():
        return configured
    discovered = shutil.which("opencode")
    if discovered:
        return discovered
    candidates = [Path.home() / ".local" / "bin" / "opencode"]
    nvm_dir = os.environ.get("NVM_DIR", "").strip()
    if nvm_dir:
        candidates.extend(
            sorted(
                Path(nvm_dir).glob("versions/node/*/bin/opencode"),
                reverse=True,
            )
        )
    return next((str(path) for path in candidates if path.is_file()), None)


def _run_opencode_json(
    *,
    source: Path,
    workspace: Path,
    schema: dict[str, object],
    prompt: str,
    timeout: int,
    stage_slug: str,
    progress_label: str,
) -> dict[str, object]:
    opencode = _find_opencode()
    if opencode is None:
        raise ValueError("OpenCode CLI was not found; install opencode-ai or choose codex")
    model = os.environ.get(
        "REPO_TEACHER_OPENCODE_MODEL", "openrouter/deepseek/deepseek-v4-flash"
    ).strip()
    if not model:
        raise ValueError("REPO_TEACHER_OPENCODE_MODEL cannot be empty")
    workspace.mkdir(parents=True, exist_ok=True)
    output_path = workspace / f"{stage_slug}.json"
    schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    bounded_prompt = (
        prompt
        + "\n\n## 输出合同\n只输出一个符合下面 JSON Schema 的 JSON object，"
        "不要 Markdown 围栏、前言或解释：\n"
        + schema_text
    )
    command = [
        opencode,
        "run",
        "--model",
        model,
        "--dir",
        str(source),
        bounded_prompt,
    ]
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    while True:
        elapsed = time.monotonic() - started
        remaining = timeout - elapsed
        if remaining <= 0:
            process.kill()
            process.communicate()
            raise subprocess.TimeoutExpired(command[:-1] + ["<prompt>"], timeout)
        try:
            stdout, stderr = process.communicate(timeout=min(30.0, remaining))
            break
        except subprocess.TimeoutExpired:
            print(
                f"[report 4/6] {progress_label}（OpenCode）… {int(time.monotonic() - started)}s",
                flush=True,
            )
    if process.returncode != 0:
        detail = (stderr or stdout or "OpenCode failed without output").strip()
        raise ValueError(f"OpenCode synthesis failed: {detail[-2_000:]}")
    result = _decode_json_object(stdout)
    output_path.write_text(_json_artifact(result), encoding="utf-8")
    return result


def _decode_json_object(content: object) -> dict[str, object]:
    if not isinstance(content, str):
        raise ValueError("model response content is not text")
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline >= 0:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3].rstrip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise
        result, end = json.JSONDecoder().raw_decode(text[start:])
        if text[start + end :].strip():
            raise ValueError("model response contains text after JSON object")
    if not isinstance(result, dict):
        raise ValueError("model response is not a JSON object")
    return result


def _close_chapter_evidence(
    payload: dict[str, object],
    batch_pack: dict[str, object],
    capabilities: Sequence[dict[str, object]],
    source: Path | None = None,
) -> dict[str, object]:
    """Close model-authored difficulty evidence over the canonical batch packet."""

    scope = batch_pack.get("scope")
    allowed_paths = {
        value
        for value in (
            scope.get("allowed_source_paths", []) if isinstance(scope, dict) else []
        )
        if isinstance(value, str)
    }
    allowed_evidence = {
        evidence.get("id")
        for evidence in batch_pack.get("evidence", [])
        if isinstance(evidence, dict) and isinstance(evidence.get("id"), str)
    }
    excerpt_ranges: dict[str, list[tuple[int, int]]] = {}
    for excerpt in batch_pack.get("source_excerpts", []):
        if not isinstance(excerpt, dict):
            continue
        path = excerpt.get("path")
        start = excerpt.get("line_start")
        end = excerpt.get("line_end")
        if isinstance(path, str) and isinstance(start, int) and isinstance(end, int):
            excerpt_ranges.setdefault(path, []).append((start, end))
    inventory_by_id = {
        str(item.get("id")): item
        for item in capabilities
        if isinstance(item.get("id"), str)
    }
    chapters = payload.get("chapters")
    if not isinstance(chapters, list):
        return payload
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        inventory = inventory_by_id.get(str(chapter.get("id") or ""))
        if inventory is None:
            continue
        chapter["title"] = inventory.get("title")
        chapter["source_feature_ids"] = [
            value
            for value in inventory.get("source_feature_ids", [])
            if isinstance(value, str)
        ]
        for source_ref in chapter.get("source_refs", []):
            if not isinstance(source_ref, dict):
                continue
            raw_path = source_ref.get("path")
            if not isinstance(raw_path, str):
                continue
            normalized_path = raw_path.replace("\\", "/")
            marker = "/source-slice/"
            if marker in normalized_path:
                normalized_path = normalized_path.split(marker, 1)[1]
            while normalized_path.startswith("./"):
                normalized_path = normalized_path[2:]
            if normalized_path in allowed_paths:
                source_ref["path"] = normalized_path
                ranges = excerpt_ranges.get(normalized_path, [])
                if ranges:
                    requested_start = source_ref.get("line_start")
                    requested_end = source_ref.get("line_end")
                    overlap = next(
                        (
                            (max(requested_start, start), min(requested_end, end))
                            for start, end in ranges
                            if isinstance(requested_start, int)
                            and isinstance(requested_end, int)
                            and requested_start <= end
                            and requested_end >= start
                        ),
                        None,
                    )
                    resolved_start, resolved_end = overlap or ranges[0]
                    source_ref["line_start"] = resolved_start
                    source_ref["line_end"] = resolved_end
                elif source is not None:
                    parts = _repo_path_parts(normalized_path)
                    if parts:
                        candidate = source.joinpath(*parts)
                        try:
                            line_count = len(
                                candidate.read_text(encoding="utf-8").splitlines()
                            )
                        except (OSError, UnicodeDecodeError):
                            line_count = 0
                        if line_count:
                            requested_start = source_ref.get("line_start")
                            requested_end = source_ref.get("line_end")
                            resolved_start = (
                                min(max(1, requested_start), line_count)
                                if isinstance(requested_start, int)
                                else 1
                            )
                            resolved_end = (
                                min(max(resolved_start, requested_end), line_count)
                                if isinstance(requested_end, int)
                                else resolved_start
                            )
                            source_ref["line_start"] = resolved_start
                            source_ref["line_end"] = resolved_end
        # Inventory evidence has already passed the full-pack closure gate.  A
        # chapter shard may omit unrelated evidence records for prompt size,
        # but it must never erase the inventory's canonical evidence contract.
        inventory_evidence = [
            value
            for value in inventory.get("evidence_ids", [])
            if isinstance(value, str)
        ]
        chapter_evidence = [
            value
            for value in chapter.get("evidence_ids", [])
            if isinstance(value, str) and value in allowed_evidence
        ]
        difficulties = chapter.get("difficulty_map")
        items = difficulties.get("items") if isinstance(difficulties, dict) else []
        for difficulty in items if isinstance(items, list) else []:
            if not isinstance(difficulty, dict):
                continue
            difficulty_evidence = [
                value
                for value in difficulty.get("evidence_ids", [])
                if isinstance(value, str) and value in allowed_evidence
            ]
            if not difficulty_evidence:
                difficulty_evidence = inventory_evidence[:1]
            difficulty["evidence_ids"] = list(dict.fromkeys(difficulty_evidence))
            chapter_evidence.extend(difficulty_evidence)
        chapter["evidence_ids"] = list(
            dict.fromkeys([*inventory_evidence, *chapter_evidence])
        )
    return payload


def _provider_prompt(
    prompt: str,
    provider: str,
    **json_sections: object,
) -> str:
    if provider == "codex":
        return prompt
    sections = [prompt]
    for title, payload in json_sections.items():
        sections.append(
            f"\n## {title}（这是本机证据的只读快照）\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )
    return "\n".join(sections)


def _run_codex_json(
    *,
    source: Path,
    workspace: Path,
    schema: dict[str, object],
    prompt: str,
    timeout: int,
    stage_slug: str,
    progress_label: str,
    provider: str = "codex",
) -> dict[str, object]:
    if provider == "deepseek":
        return _run_deepseek_json(
            schema=schema,
            prompt=prompt,
            timeout=timeout,
            progress_label=progress_label,
        )
    if provider == "opencode":
        return _run_opencode_json(
            source=source,
            workspace=workspace,
            schema=schema,
            prompt=prompt,
            timeout=timeout,
            stage_slug=stage_slug,
            progress_label=progress_label,
        )
    if provider != "codex":
        raise ValueError(f"unsupported narrative provider: {provider}")
    codex = shutil.which("codex")
    if codex is None:
        raise ValueError("Codex CLI was not found; install Codex or pass --narrative")
    codex_model = os.environ.get("REPO_TEACHER_CODEX_MODEL", "gpt-5.4").strip()
    reasoning_effort = os.environ.get(
        "REPO_TEACHER_CODEX_REASONING_EFFORT", "low"
    ).strip()
    workspace.mkdir(parents=True, exist_ok=True)
    schema_path = workspace / f"{stage_slug}-schema.json"
    output_path = workspace / f"{stage_slug}.json"
    schema_path.write_text(_json_artifact(schema), encoding="utf-8")
    command = [
        codex,
        "exec",
        "-",
        "--ignore-user-config",
        "--model",
        codex_model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--cd",
        str(source),
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ignore-rules",
        "--ephemeral",
        "--color",
        "never",
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
    ]
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    pending_input: str | None = prompt
    while True:
        elapsed = time.monotonic() - started
        remaining = timeout - elapsed
        if remaining <= 0:
            process.kill()
            process.communicate()
            raise subprocess.TimeoutExpired(command, timeout)
        try:
            stdout, stderr = process.communicate(
                input=pending_input,
                timeout=min(30.0, remaining),
            )
            break
        except subprocess.TimeoutExpired:
            pending_input = None
            print(
                f"[report 4/6] {progress_label}… {int(time.monotonic() - started)}s",
                flush=True,
            )
    if process.returncode != 0:
        detail = (stderr or stdout or "Codex failed without output").strip()
        raise ValueError(f"Codex synthesis failed: {detail[-2_000:]}")
    if not output_path.is_file():
        raise ValueError(f"Codex synthesis did not produce {output_path.name}")
    return read_json_path(output_path)


def _require_source_ref_quality(chapters: Sequence[dict[str, object]]) -> None:
    for chapter in chapters:
        source_refs = chapter.get("source_refs")
        if not isinstance(source_refs, list) or len(source_refs) < 3:
            raise ValueError("Codex report chapter requires at least three source_refs")
        implementation_refs = []
        for source_ref in source_refs:
            if not isinstance(source_ref, dict):
                continue
            path = str(source_ref.get("path") or "")
            lowered = path.casefold()
            parts = tuple(part.casefold() for part in Path(path).parts)
            if (
                lowered.endswith(".md")
                or "docs" in parts
                or "specs" in parts
                or Path(path).name.casefold().startswith("readme")
            ):
                continue
            implementation_refs.append(source_ref)
        if not implementation_refs:
            raise ValueError(
                "Codex report chapter requires non-document implementation evidence"
            )


def _chunk_capabilities(
    capabilities: Sequence[dict[str, object]], batch_size: int
) -> list[list[dict[str, object]]]:
    return [
        list(capabilities[index : index + batch_size])
        for index in range(0, len(capabilities), batch_size)
    ]


def _ranges_overlap(
    first_start: int, first_end: int, second_start: int, second_end: int
) -> bool:
    return not (first_end < second_start or second_end < first_start)


def _inventory_from_manifest(
    manifest: object, pack: dict[str, object]
) -> dict[str, object]:
    if isinstance(manifest, dict) and isinstance(manifest.get("capabilities"), list):
        return manifest
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("inventory must be a capability list or a manifest capability array")
    evidence_by_path: dict[str, list[dict[str, object]]] = {}
    for evidence in pack.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        path = evidence.get("path")
        if not isinstance(path, str) or not path:
            continue
        evidence_by_path.setdefault(path, []).append(evidence)
    capabilities: list[dict[str, object]] = []
    for raw_item in manifest:
        if not isinstance(raw_item, dict):
            raise ValueError("inventory manifest entries must be objects")
        item_id = raw_item.get("id")
        title = raw_item.get("title")
        user_action = raw_item.get("user_action")
        mechanism_question = raw_item.get("mechanism_question")
        distinguish = raw_item.get("distinguish")
        source_refs = raw_item.get("source_refs")
        coverage_notes = raw_item.get("coverage_notes")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (item_id, title, user_action, mechanism_question, distinguish)
        ):
            raise ValueError("inventory manifest entry is missing required text fields")
        if not isinstance(source_refs, list) or len(source_refs) < 3:
            raise ValueError(
                f"inventory manifest entry requires at least three source_refs: {item_id}"
            )
        normalized_refs: list[dict[str, object]] = []
        matched_evidence_ids: list[str] = []
        for source_ref in source_refs:
            if not isinstance(source_ref, dict):
                raise ValueError(f"inventory manifest source_ref must be an object: {item_id}")
            path = source_ref.get("path")
            line_start = source_ref.get("line_start")
            line_end = source_ref.get("line_end")
            claim = source_ref.get("claim")
            if (
                not isinstance(path, str)
                or not path
                or not isinstance(line_start, int)
                or not isinstance(line_end, int)
                or line_start < 1
                or line_end < line_start
                or not isinstance(claim, str)
                or not claim.strip()
            ):
                raise ValueError(f"inventory manifest source_ref is invalid: {item_id}")
            normalized_ref = {
                "path": path,
                "line_start": line_start,
                "line_end": line_end,
                "claim": claim.strip(),
            }
            normalized_refs.append(normalized_ref)
            for evidence in evidence_by_path.get(path, []):
                evidence_id = evidence.get("id")
                evidence_start = evidence.get("line_start")
                evidence_end = evidence.get("line_end")
                if (
                    isinstance(evidence_id, str)
                    and isinstance(evidence_start, int)
                    and isinstance(evidence_end, int)
                    and _ranges_overlap(line_start, line_end, evidence_start, evidence_end)
                    and evidence_id not in matched_evidence_ids
                ):
                    matched_evidence_ids.append(evidence_id)
        if not matched_evidence_ids:
            raise ValueError(
                f"inventory manifest could not map to canonical evidence: {item_id}"
            )
        matched_feature_ids: list[str] = []
        for feature in pack.get("feature_hints", []):
            if not isinstance(feature, dict):
                continue
            feature_id = feature.get("id")
            if not isinstance(feature_id, str) or not feature_id:
                continue
            feature_evidence = feature.get("evidence_ids")
            if isinstance(feature_evidence, list) and any(
                isinstance(evidence_id, str) and evidence_id in matched_evidence_ids
                for evidence_id in feature_evidence
            ):
                if feature_id not in matched_feature_ids:
                    matched_feature_ids.append(feature_id)
                continue
            for step in feature.get("steps", []):
                if not isinstance(step, dict):
                    continue
                step_path = step.get("path")
                step_start = step.get("line_start")
                step_end = step.get("line_end")
                for source_ref in normalized_refs:
                    if (
                        step_path == source_ref["path"]
                        and isinstance(step_start, int)
                        and isinstance(step_end, int)
                        and _ranges_overlap(
                            int(source_ref["line_start"]),
                            int(source_ref["line_end"]),
                            step_start,
                            step_end,
                        )
                    ):
                        if feature_id not in matched_feature_ids:
                            matched_feature_ids.append(feature_id)
                        break
                if feature_id in matched_feature_ids:
                    break
        if not matched_feature_ids:
            raise ValueError(
                f"inventory manifest could not map to canonical features: {item_id}"
            )
        distinguish_text = distinguish.strip()
        if isinstance(coverage_notes, str) and coverage_notes.strip():
            distinguish_text = f"{distinguish_text} 审计覆盖：{coverage_notes.strip()}"
        summary = user_action.strip()
        capabilities.append(
            {
                "id": item_id.strip(),
                "title": title.strip(),
                "summary": summary,
                "mechanism": "source-audited-capability",
                "question": mechanism_question.strip(),
                "use_when": f"当你要判断“{title.strip()}”这项能力是否值得复用时。",
                "distinguish": distinguish_text,
                "plain_summary": (
                    f"{summary} 这是一项已由源码切片审计过的独立能力，不是入口函数或页面名。"
                ),
                "source_feature_ids": matched_feature_ids,
                "evidence_ids": matched_evidence_ids,
                "source_refs": normalized_refs,
            }
        )
    return {"capabilities": capabilities}


def _repo_path_parts(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    if value.startswith(("/", "\\")):
        return ()
    raw_parts = value.replace("\\", "/").split("/")
    if ".." in raw_parts:
        return ()
    return tuple(
        part
        for part in raw_parts
        if part and part != "."
    )


def _path_is_within_modules(path: object, module_paths: Sequence[str]) -> bool:
    path_parts = _repo_path_parts(path)
    if not path_parts:
        return False
    for module_path in module_paths:
        module_parts = _repo_path_parts(module_path)
        if module_parts and path_parts[: len(module_parts)] == module_parts:
            return True
    return False


def _source_paths(value: object) -> set[str]:
    paths: set[str] = set()
    if isinstance(value, list):
        for item in value:
            paths.update(_source_paths(item))
        return paths
    if not isinstance(value, dict):
        return paths
    for key, item in value.items():
        if key in {"path", "source_path", "target_path"} and isinstance(item, str):
            if _repo_path_parts(item):
                paths.add(item)
            continue
        if isinstance(item, (dict, list)):
            paths.update(_source_paths(item))
    return paths


def _feature_ids(value: object) -> set[str]:
    if not isinstance(value, dict):
        return set()
    result: set[str] = set()
    feature_id = value.get("feature_id")
    if isinstance(feature_id, str) and feature_id:
        result.add(feature_id)
    source_feature_ids = value.get("source_feature_ids")
    if isinstance(source_feature_ids, list):
        result.update(
            item for item in source_feature_ids if isinstance(item, str) and item
        )
    return result


def _graph_item_matches_scope(
    item: object,
    *,
    module_paths: Sequence[str],
    selected_feature_ids: set[str],
) -> bool:
    if not isinstance(item, dict):
        return False
    if _feature_ids(item) & selected_feature_ids:
        return True
    return any(
        _path_is_within_modules(path, module_paths)
        for path in _source_paths(item)
    )


def _compact_graph_item(
    item: dict[str, object],
    *,
    node_limit: int = 12,
    edge_limit: int = 16,
) -> dict[str, object]:
    compact = copy.deepcopy(item)
    compact.pop("edge_ids", None)
    for field, limit in (
        ("seed_nodes", 12),
        ("implementation_nodes", node_limit),
        ("central_nodes", 8),
        ("resolved_edges", edge_limit),
        ("component_ids", 8),
    ):
        value = compact.get(field)
        if isinstance(value, list):
            compact[field] = value[:limit]
    return compact


def _compact_graph_candidate(item: dict[str, object]) -> dict[str, object]:
    compact = _compact_graph_item(item, node_limit=8, edge_limit=8)
    if _feature_ids(item):
        compact.pop("implementation_nodes", None)
        compact.pop("resolved_edges", None)
    return compact


def _source_path_priority(path: object) -> tuple[int, str]:
    """Prefer product implementation while retaining examples as usage evidence."""

    parts = tuple(part.casefold() for part in _repo_path_parts(path))
    if not parts:
        return (5, "")
    if any(part in {"test", "tests", "fixtures"} for part in parts):
        return (4, "/".join(parts))
    if any(part in {"docs", "doc", "spec", "specs"} for part in parts):
        return (3, "/".join(parts))
    if any(part in {"example", "examples", "demo", "demos", "sample", "samples"} for part in parts):
        return (2, "/".join(parts))
    if parts[0] in {"src", "lib", "libs", "packages", "apps", "server", "client"}:
        return (0, "/".join(parts))
    return (1, "/".join(parts))


def _compact_global_graph_context(graph: object) -> dict[str, object]:
    """Keep whole-repository topology without forwarding the full graph payload."""

    if not isinstance(graph, dict):
        return {}

    def compact_item(
        item: dict[str, object], *, node_limit: int, edge_limit: int
    ) -> dict[str, object]:
        compact = copy.deepcopy(item)
        compact.pop("edge_ids", None)
        for field, limit in (
            ("seed_nodes", node_limit),
            ("implementation_nodes", node_limit),
            ("central_nodes", node_limit),
        ):
            nodes = item.get(field)
            if isinstance(nodes, list):
                compact[field] = sorted(
                    (node for node in nodes if isinstance(node, dict)),
                    key=lambda node: (
                        _source_path_priority(node.get("path"))[0],
                        -int(node.get("in_degree") or 0),
                        _source_path_priority(node.get("path"))[1],
                        str(node.get("qualified_name") or node.get("name") or ""),
                    ),
                )[:limit]
        edges = item.get("resolved_edges")
        if isinstance(edges, list):
            compact["resolved_edges"] = sorted(
                (edge for edge in edges if isinstance(edge, dict)),
                key=lambda edge: (
                    min(
                        _source_path_priority(edge.get("source_path")),
                        _source_path_priority(edge.get("target_path")),
                    ),
                    str(edge.get("id") or ""),
                ),
            )[:edge_limit]
        components = item.get("component_ids")
        if isinstance(components, list):
            compact["component_ids"] = components[:8]
        return compact

    feature_slices = [
        compact_item(item, node_limit=10, edge_limit=12)
        for item in graph.get("feature_slices", [])
        if isinstance(item, dict)
    ]
    capability_candidates = [
        compact_item(item, node_limit=10, edge_limit=12)
        for item in graph.get("capability_candidates", [])
        if isinstance(item, dict)
    ]
    mechanism_clusters = [
        compact_item(item, node_limit=4, edge_limit=0)
        for item in graph.get("mechanism_clusters", [])
        if isinstance(item, dict)
    ]
    components = [
        compact_item(item, node_limit=3, edge_limit=0)
        for item in graph.get("components", [])
        if isinstance(item, dict)
    ]
    return {
        "schema_version": graph.get("schema_version"),
        "stats": graph.get("stats", {}),
        "feature_slices": feature_slices,
        "capability_candidates": capability_candidates,
        "mechanism_clusters": mechanism_clusters,
        "components": components,
        "module_dependencies": [
            copy.deepcopy(item)
            for item in graph.get("module_dependencies", [])[:512]
            if isinstance(item, dict)
        ],
        "unresolved_edge_examples": [
            copy.deepcopy(item)
            for item in graph.get("unresolved_edge_examples", [])[:80]
            if isinstance(item, dict)
        ],
        "interpretation_contract": graph.get("interpretation_contract", []),
    }


def _module_view_path(path: object) -> str | None:
    parts = _repo_path_parts(path)
    if len(parts) < 2:
        return None
    directories = parts[:-1]
    if not directories:
        return None
    if directories[0].casefold() in {"packages", "apps", "services"}:
        depth = min(2, len(directories))
    else:
        depth = min(3, len(directories))
    return "/".join(directories[:depth])


def _module_view_category(path: str) -> str:
    path_parts = _repo_path_parts(path)
    parts = {part.casefold() for part in path_parts}
    if any(part.startswith(".") for part in path_parts):
        return "engineering-support"
    if parts & {"test", "tests", "fixtures"}:
        return "testing"
    if parts & {"example", "examples", "demo", "demos", "sample", "samples"}:
        return "examples"
    if parts & {"doc", "docs", "spec", "specs", "changelog", "changes"}:
        return "documentation"
    if parts & {"script", "scripts", ".github", "build", "tools"}:
        return "engineering-support"
    return "product-implementation"


def _build_module_views(
    pack: dict[str, object], graph: dict[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Derive useful folder-level modules without invoking a model per folder."""

    graph_paths = _source_paths(graph)
    all_paths = {
        path
        for hint in pack.get("feature_hints", [])
        if isinstance(hint, dict)
        for path in _source_paths(hint)
    }
    grouped: dict[str, list[str]] = {}
    for path in sorted(all_paths, key=_source_path_priority):
        module_path = _module_view_path(path)
        if module_path is not None:
            grouped.setdefault(module_path, []).append(path)
    module_views: list[dict[str, object]] = []
    for module_path, paths in grouped.items():
        representatives = sorted(
            paths,
            key=lambda path: (
                0 if path in graph_paths else 1,
                _source_path_priority(path),
            ),
        )[:5]
        module_views.append(
            {
                "path": module_path,
                "category": _module_view_category(module_path),
                "file_count": len(paths),
                "representative_paths": representatives,
            }
        )
    module_views.sort(
        key=lambda item: (
            0 if item["category"] == "product-implementation" else 1,
            str(item["path"]),
        )
    )
    module_by_path = {path: _module_view_path(path) for path in all_paths}
    dependency_counts: dict[tuple[str, str, str], int] = {}
    for section in ("feature_slices", "capability_candidates"):
        for item in graph.get(section, []):
            if not isinstance(item, dict):
                continue
            for edge in item.get("resolved_edges", []):
                if not isinstance(edge, dict):
                    continue
                source_module = module_by_path.get(str(edge.get("source_path") or ""))
                target_module = module_by_path.get(str(edge.get("target_path") or ""))
                if not source_module or not target_module or source_module == target_module:
                    continue
                key = (
                    source_module,
                    target_module,
                    str(edge.get("kind") or "relationship"),
                )
                dependency_counts[key] = dependency_counts.get(key, 0) + 1
    dependencies = [
        {"source": source, "target": target, "kind": kind, "count": count}
        for (source, target, kind), count in sorted(
            dependency_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return module_views[:240], dependencies[:512]


def _build_global_business_inventory_pack(
    pack: dict[str, object], *, hint_limit: int = 320
) -> dict[str, object]:
    """Build one graph-first packet for global capability decisions.

    Modules remain first-class topology evidence, but model calls are not split
    by module.  This prevents local shards from mistaking routes, helpers, or
    examples for independent product capabilities.
    """

    graph = _compact_global_graph_context(pack.get("capability_graph"))
    module_views, module_view_dependencies = _build_module_views(pack, graph)
    product_modules = [
        item
        for item in module_views
        if item.get("category") == "product-implementation"
    ]
    representative_product_paths = {
        path
        for module in product_modules
        for path in module.get("representative_paths", [])
        if isinstance(path, str)
    }
    graph_paths = _source_paths(graph)
    graph_feature_ids = {
        identifier
        for section in ("feature_slices", "capability_candidates")
        for item in graph.get(section, [])
        if isinstance(item, dict)
        for identifier in _feature_ids(item)
    }
    ranked_hints: list[tuple[tuple[object, ...], dict[str, object]]] = []
    for position, hint in enumerate(pack.get("feature_hints", [])):
        if not isinstance(hint, dict):
            continue
        hint_id = hint.get("id")
        hint_paths = _source_paths(hint)
        covers_product_module = bool(hint_paths & representative_product_paths)
        if (
            not covers_product_module
            and hint_id not in graph_feature_ids
            and not (hint_paths & graph_paths)
        ):
            continue
        best_path = min(
            (_source_path_priority(path) for path in hint_paths),
            default=(5, ""),
        )
        ranked_hints.append(
            (
                (
                    0
                    if covers_product_module
                    else 1
                    if hint_id in graph_feature_ids
                    else 2,
                    best_path,
                    position,
                ),
                hint,
            )
        )
    if not ranked_hints:
        for position, hint in enumerate(pack.get("feature_hints", [])):
            if not isinstance(hint, dict):
                continue
            hint_paths = _source_paths(hint)
            ranked_hints.append(
                (
                    (
                        2,
                        min(
                            (_source_path_priority(path) for path in hint_paths),
                            default=(5, ""),
                        ),
                        position,
                    ),
                    hint,
                )
            )
    selected_hints = [
        copy.deepcopy(hint)
        for _, hint in sorted(ranked_hints, key=lambda item: item[0])[:hint_limit]
    ]
    evidence_ids = {
        identifier
        for hint in selected_hints
        for identifier in [
            *(
                hint.get("evidence_ids", [])
                if isinstance(hint.get("evidence_ids"), list)
                else []
            ),
            *(
                evidence_id
                for step in hint.get("steps", [])
                if isinstance(step, dict)
                for evidence_id in (
                    step.get("evidence_ids", [])
                    if isinstance(step.get("evidence_ids"), list)
                    else []
                )
            ),
        ]
        if isinstance(identifier, str)
    }
    selected_evidence = [
        copy.deepcopy(item)
        for item in pack.get("evidence", [])
        if isinstance(item, dict) and item.get("id") in evidence_ids
    ]
    allowed_paths = _source_paths(selected_hints) | _source_paths(selected_evidence)
    modules = module_views
    module_paths = [str(item["path"]) for item in modules]
    selected_feature_ids = sorted(
        str(item["id"])
        for item in selected_hints
        if isinstance(item.get("id"), str) and item.get("id")
    )
    return {
        "schema_version": pack.get("schema_version"),
        "project": pack.get("project", {}),
        "instructions": pack.get("instructions", []),
        "required_chapter_sections": pack.get("required_chapter_sections", []),
        "inventory_strategy": {
            "decision_scope": "whole-repository-business-capabilities",
            "graph_first": True,
            "module_role": (
                "Modules are topology and implementation evidence. They do not "
                "independently define user-facing capabilities."
            ),
            "detail_parallelism": (
                "Parallel work starts only after global capability IDs are fixed."
            ),
        },
        "scope": {
            "module_paths": module_paths,
            "required_product_module_paths": [
                str(item["path"]) for item in product_modules
            ],
            "require_module_coverage": True,
            "allowed_source_paths": sorted(allowed_paths),
            "feature_ids": selected_feature_ids,
            "evidence_ids": sorted(
                str(item["id"])
                for item in selected_evidence
                if isinstance(item.get("id"), str) and item.get("id")
            ),
            "capability_candidate_ids": [
                item.get("id")
                for item in graph.get("capability_candidates", [])
                if isinstance(item, dict) and item.get("id")
            ],
            "mechanism_cluster_ids": [
                item.get("id")
                for item in graph.get("mechanism_clusters", [])
                if isinstance(item, dict) and item.get("id")
            ],
            "graph_paths_without_canonical_evidence": len(
                graph_paths - allowed_paths
            ),
            "contract": (
                "Decide capabilities once from the whole graph; use modules to "
                "explain implementation; cite only canonical allowed paths."
            ),
        },
        "capability_graph": graph,
        "modules": modules,
        "module_view_dependencies": module_view_dependencies,
        "repository_modules": [
            copy.deepcopy(item)
            for item in pack.get("modules", [])
            if isinstance(item, dict)
        ][:200],
        "reading_path": [
            copy.deepcopy(item)
            for item in pack.get("reading_path", [])
            if isinstance(item, dict) and item.get("path") in allowed_paths
        ],
        "feature_hints": selected_hints,
        "evidence": selected_evidence,
    }


def _module_labels(module_paths: Sequence[str]) -> set[str]:
    labels: set[str] = set()
    for module_path in module_paths:
        parts = _repo_path_parts(module_path)
        if parts:
            labels.add(parts[-1])
            labels.add(parts[0])
    return labels


def _filter_graph_context(
    graph: object,
    *,
    module_paths: Sequence[str],
    selected_feature_ids: set[str],
) -> dict[str, object]:
    if not isinstance(graph, dict):
        return {}
    feature_slices = [
        _compact_graph_item(item)
        for item in graph.get("feature_slices", [])
        if isinstance(item, dict)
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=selected_feature_ids,
        )
    ]
    graph_feature_ids = set(selected_feature_ids)
    for item in feature_slices:
        graph_feature_ids.update(_feature_ids(item))
    capability_candidates = [
        _compact_graph_candidate(item)
        for item in graph.get("capability_candidates", [])
        if isinstance(item, dict)
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=graph_feature_ids,
        )
    ]
    for item in capability_candidates:
        graph_feature_ids.update(_feature_ids(item))
    if graph_feature_ids != selected_feature_ids:
        feature_slices = [
            _compact_graph_item(item)
            for item in graph.get("feature_slices", [])
            if isinstance(item, dict)
            if _graph_item_matches_scope(
                item,
                module_paths=module_paths,
                selected_feature_ids=graph_feature_ids,
            )
        ]
    mechanism_clusters = [
        _compact_graph_item(item)
        for item in graph.get("mechanism_clusters", [])
        if isinstance(item, dict)
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=graph_feature_ids,
        )
    ]
    components = [
        _compact_graph_item(item)
        for item in graph.get("components", [])
        if isinstance(item, dict)
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=graph_feature_ids,
        )
    ]
    labels = _module_labels(module_paths)
    module_dependencies = [
        item
        for item in graph.get("module_dependencies", [])
        if isinstance(item, dict)
        and (
            str(item.get("source") or "") in labels
            or str(item.get("target") or "") in labels
        )
    ]
    unresolved_edges = [
        item
        for item in graph.get("unresolved_edge_examples", [])
        if _graph_item_matches_scope(
            item,
            module_paths=module_paths,
            selected_feature_ids=graph_feature_ids,
        )
    ]
    return {
        "schema_version": graph.get("schema_version"),
        "stats": graph.get("stats", {}),
        "feature_slices": feature_slices,
        "capability_candidates": capability_candidates,
        "mechanism_clusters": mechanism_clusters,
        "components": components,
        "module_dependencies": module_dependencies,
        "unresolved_edge_examples": unresolved_edges,
        "interpretation_contract": graph.get("interpretation_contract", []),
    }


def _build_inventory_shard_pack(
    pack: dict[str, object], module_paths: Sequence[str]
) -> dict[str, object]:
    selected_modules = [
        item
        for item in pack.get("modules", [])
        if isinstance(item, dict)
        and _path_is_within_modules(item.get("path"), module_paths)
    ]
    selected_hints = [
        item
        for item in pack.get("feature_hints", [])
        if isinstance(item, dict)
        and any(
            _path_is_within_modules(path, module_paths)
            for path in _source_paths(item)
        )
    ]
    selected_feature_ids = {
        str(item["id"])
        for item in selected_hints
        if isinstance(item.get("id"), str) and item.get("id")
    }
    graph = _filter_graph_context(
        pack.get("capability_graph"),
        module_paths=module_paths,
        selected_feature_ids=selected_feature_ids,
    )
    graph_feature_ids = set(selected_feature_ids)
    for section in ("feature_slices", "capability_candidates"):
        for item in graph.get(section, []):
            graph_feature_ids.update(_feature_ids(item))
    graph_paths = _source_paths(graph)
    selected_hints = [
        item
        for item in pack.get("feature_hints", [])
        if isinstance(item, dict)
        and (
            item.get("id") in graph_feature_ids
            or bool(_source_paths(item) & graph_paths)
            or any(
                _path_is_within_modules(path, module_paths)
                for path in _source_paths(item)
            )
        )
    ]
    evidence_ids = {
        identifier
        for hint in selected_hints
        for identifier in [
            *(hint.get("evidence_ids", []) if isinstance(hint.get("evidence_ids"), list) else []),
            *(
                evidence_id
                for step in hint.get("steps", [])
                if isinstance(step, dict)
                for evidence_id in (
                    step.get("evidence_ids", [])
                    if isinstance(step.get("evidence_ids"), list)
                    else []
                )
            ),
        ]
        if isinstance(identifier, str)
    }
    selected_evidence = [
        item
        for item in pack.get("evidence", [])
        if isinstance(item, dict)
        and item.get("id") in evidence_ids
    ]
    allowed_paths = set()
    for value in (selected_hints, selected_evidence, graph):
        allowed_paths.update(_source_paths(value))
    selected_reading_path = [
        item
        for item in pack.get("reading_path", [])
        if isinstance(item, dict) and item.get("path") in allowed_paths
    ]
    return {
        "schema_version": pack.get("schema_version"),
        "project": pack.get("project", {}),
        "instructions": pack.get("instructions", []),
        "required_chapter_sections": pack.get("required_chapter_sections", []),
        "scope": {
            "module_paths": list(module_paths),
            "allowed_source_paths": sorted(allowed_paths),
            "feature_ids": sorted(
                str(item["id"])
                for item in selected_hints
                if isinstance(item.get("id"), str) and item.get("id")
            ),
            "evidence_ids": sorted(
                str(item["id"])
                for item in selected_evidence
                if isinstance(item.get("id"), str) and item.get("id")
            ),
            "capability_candidate_ids": [
                item.get("id")
                for item in graph.get("capability_candidates", [])
                if isinstance(item, dict) and item.get("id")
            ],
            "resolved_edge_ids": sorted(
                {
                    str(edge["id"])
                    for section in ("feature_slices", "capability_candidates")
                    for item in graph.get(section, [])
                    if isinstance(item, dict)
                    for edge in item.get("resolved_edges", [])
                    if isinstance(edge, dict) and edge.get("id")
                }
            ),
            "contract": "Only inspect allowed_source_paths; graph candidates are seeds, not final features.",
        },
        "capability_graph": graph,
        "modules": selected_modules,
        "reading_path": selected_reading_path,
        "feature_hints": selected_hints,
        "evidence": selected_evidence,
    }


def _build_chapter_batch_pack(
    pack: dict[str, object], capabilities: Sequence[dict[str, object]]
) -> dict[str, object]:
    capability_ids = [
        str(item["id"])
        for item in capabilities
        if isinstance(item.get("id"), str) and item.get("id")
    ]
    feature_ids = {
        identifier
        for item in capabilities
        for identifier in (
            item.get("source_feature_ids", [])
            if isinstance(item.get("source_feature_ids"), list)
            else []
        )
        if isinstance(identifier, str)
    }
    evidence_ids = {
        identifier
        for item in capabilities
        for identifier in (
            item.get("evidence_ids", [])
            if isinstance(item.get("evidence_ids"), list)
            else []
        )
        if isinstance(identifier, str)
    }
    allowed_paths = {
        path
        for item in capabilities
        for source_ref in (
            item.get("source_refs", [])
            if isinstance(item.get("source_refs"), list)
            else []
        )
        if isinstance(source_ref, dict)
        for path in [source_ref.get("path")]
        if isinstance(path, str) and _repo_path_parts(path)
    }
    selected_hints = [
        item
        for item in pack.get("feature_hints", [])
        if isinstance(item, dict) and item.get("id") in feature_ids
    ]
    for hint in selected_hints:
        allowed_paths.update(_source_paths(hint))
        evidence_ids.update(
            identifier
            for identifier in hint.get("evidence_ids", [])
            if isinstance(identifier, str)
        )
    selected_evidence = [
        item
        for item in pack.get("evidence", [])
        if isinstance(item, dict) and item.get("id") in evidence_ids
    ]
    allowed_paths.update(_source_paths(selected_evidence))
    module_paths = sorted(
        {
            str(item.get("path"))
            for item in pack.get("modules", [])
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and any(
                _path_is_within_modules(path, [str(item.get("path"))])
                for path in allowed_paths
            )
        }
    )
    graph = _filter_graph_context(
        pack.get("capability_graph"),
        module_paths=module_paths,
        selected_feature_ids=feature_ids,
    )
    allowed_paths.update(_source_paths(graph))
    return {
        "schema_version": pack.get("schema_version"),
        "project": pack.get("project", {}),
        "instructions": pack.get("instructions", []),
        "required_chapter_sections": pack.get("required_chapter_sections", []),
        "scope": {
            "capability_ids": capability_ids,
            "allowed_source_paths": sorted(allowed_paths),
            "contract": "Explain only selected capabilities from this evidence closure.",
        },
        "capabilities": copy.deepcopy(list(capabilities)),
        "capability_graph": graph,
        "modules": [
            item
            for item in pack.get("modules", [])
            if isinstance(item, dict) and item.get("path") in module_paths
        ],
        "reading_path": [
            item
            for item in pack.get("reading_path", [])
            if isinstance(item, dict) and item.get("path") in allowed_paths
        ],
        "feature_hints": selected_hints,
        "evidence": selected_evidence,
    }


def _add_project_navigation(
    overview_pack: dict[str, object], full_pack: dict[str, object]
) -> dict[str, object]:
    """Add root-level product metadata as positioning-only navigation evidence."""

    enriched = copy.deepcopy(overview_pack)
    preferred_names = {
        "readme",
        "readme.md",
        "readme.rst",
        "readme.txt",
        "pyproject.toml",
        "package.json",
        "go.mod",
        "cargo.toml",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    }
    selected: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for evidence in full_pack.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        path = evidence.get("path")
        if not isinstance(path, str) or path in seen_paths:
            continue
        parts = _repo_path_parts(path)
        if len(parts) != 1 or parts[0].casefold() not in preferred_names:
            continue
        selected.append(copy.deepcopy(evidence))
        seen_paths.add(path)
        if len(selected) >= 6:
            break
    project = full_pack.get("project")
    project_path = project.get("path") if isinstance(project, dict) else None
    source_root = (
        Path(project_path).resolve()
        if isinstance(project_path, str) and project_path
        else None
    )
    if source_root is not None and source_root.is_dir() and len(selected) < 6:
        indexed_root_paths = [
            str(file_record.get("path"))
            for file_record in full_pack.get("files", [])
            if isinstance(file_record, dict)
            and isinstance(file_record.get("path"), str)
            and len(_repo_path_parts(str(file_record.get("path")))) == 1
        ]
        try:
            filesystem_root_paths = [
                child.name for child in source_root.iterdir() if child.is_file()
            ]
        except OSError:
            filesystem_root_paths = []
        for path in sorted(set(indexed_root_paths + filesystem_root_paths)):
            if path in seen_paths:
                continue
            parts = _repo_path_parts(path)
            if len(parts) != 1 or parts[0].casefold() not in preferred_names:
                continue
            candidate = source_root.joinpath(*parts)
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(source_root)
                with resolved.open("r", encoding="utf-8") as handle:
                    snippet = handle.read(12_000)
            except (FileNotFoundError, OSError, UnicodeDecodeError, ValueError):
                continue
            if not snippet.strip():
                continue
            line_count = max(1, snippet.count("\n") + 1)
            selected.append(
                {
                    "id": "product-navigation-"
                    + hashlib.sha256(path.encode("utf-8")).hexdigest()[:16],
                    "path": path,
                    "line_start": 1,
                    "line_end": line_count,
                    "kind": "product-positioning-navigation",
                    "confidence": "navigation-only",
                    "snippet": snippet,
                }
            )
            seen_paths.add(path)
            if len(selected) >= 6:
                break
    enriched["product_navigation"] = selected
    scope = enriched.get("scope")
    if isinstance(scope, dict):
        allowed = {
            item
            for item in scope.get("allowed_source_paths", [])
            if isinstance(item, str)
        }
        allowed.update(seen_paths)
        scope["allowed_source_paths"] = sorted(allowed)
        scope["product_navigation_paths"] = sorted(seen_paths)
    return enriched


def _materialize_source_slice(
    source: Path,
    workspace: Path,
    allowed_paths: Sequence[str],
) -> Path:
    slice_root = workspace / "source-slice"
    slice_root.mkdir(parents=True, exist_ok=True)
    source_root = source.resolve()
    for relative_path in sorted(set(allowed_paths)):
        parts = _repo_path_parts(relative_path)
        if not parts:
            raise ValueError(f"invalid source slice path: {relative_path}")
        candidate = source_root.joinpath(*parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(source_root)
        except (FileNotFoundError, OSError, ValueError) as error:
            raise ValueError(f"source slice path escapes or is missing: {relative_path}") from error
        if not resolved.is_file():
            raise ValueError(f"source slice path is not a regular file: {relative_path}")
        destination = slice_root.joinpath(*parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, destination, follow_symlinks=False)
    return slice_root


def _stage_model_json(
    source_slice: Path,
    filename: str,
    payload: dict[str, object],
) -> Path:
    """Place model context inside the read-only source-slice sandbox."""

    context_root = source_slice / ".repo-teacher-context"
    context_root.mkdir(parents=True, exist_ok=True)
    destination = context_root / filename
    destination.write_text(_json_artifact(payload), encoding="utf-8")
    return destination


def _source_locations(value: object) -> dict[str, list[tuple[int, int]]]:
    result: dict[str, list[tuple[int, int]]] = {}

    def add(path: object, start: object, end: object) -> None:
        if not isinstance(path, str) or not _repo_path_parts(path):
            return
        if not isinstance(start, int) or start < 1:
            return
        resolved_end = end if isinstance(end, int) and end >= start else start
        result.setdefault(path, []).append((start, resolved_end))

    def visit(item: object) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        add(
            item.get("path"),
            item.get("line_start", item.get("line")),
            item.get("line_end", item.get("end_line")),
        )
        add(item.get("source_path"), item.get("source_line"), item.get("source_line"))
        add(item.get("target_path"), item.get("target_line"), item.get("target_line"))
        for child in item.values():
            if isinstance(child, (dict, list)):
                visit(child)

    visit(value)
    return result


def _attach_source_excerpts(
    packet: dict[str, object],
    source: Path,
    *,
    character_budget: int = 240_000,
) -> dict[str, object]:
    enriched = copy.deepcopy(packet)
    locations = _source_locations(packet)
    allowed_paths = set(
        packet.get("scope", {}).get("allowed_source_paths", [])
        if isinstance(packet.get("scope"), dict)
        else []
    )
    excerpts: list[dict[str, object]] = []
    used = 0
    source_root = source.resolve()
    for path in sorted(locations):
        if path not in allowed_paths:
            continue
        parts = _repo_path_parts(path)
        if not parts:
            continue
        candidate = source_root.joinpath(*parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(source_root)
            if not resolved.is_file():
                continue
            lines = resolved.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        ranges = sorted(
            {
                (
                    max(1, start - 8),
                    min(len(lines), max(end, start) + 12, start + 159),
                )
                for start, end in locations[path]
                if start <= len(lines)
            }
        )
        merged: list[tuple[int, int]] = []
        for start, end in ranges:
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        for start, end in merged[:6]:
            content = "\n".join(
                f"{line_number:>6}  {lines[line_number - 1]}"
                for line_number in range(start, end + 1)
            )
            if used + len(content) > character_budget:
                break
            excerpts.append(
                {
                    "path": path,
                    "line_start": start,
                    "line_end": end,
                    "content": content,
                }
            )
            used += len(content)
        if used >= character_budget:
            break
    enriched["source_excerpts"] = excerpts
    scope = enriched.get("scope")
    if isinstance(scope, dict):
        scope["source_excerpt_count"] = len(excerpts)
        scope["source_excerpt_characters"] = used
        scope["source_excerpt_truncated"] = used >= character_budget
    return enriched


def _normalize_project_overview(
    payload: dict[str, object],
    packet: dict[str, object],
    capabilities: Sequence[dict[str, object]],
    source: Path,
) -> dict[str, object]:
    overview = payload.get("project_overview")
    if not isinstance(overview, dict):
        raise ValueError("project overview is missing")
    expected_ids = [
        str(item["id"])
        for item in capabilities
        if isinstance(item.get("id"), str) and item.get("id")
    ]
    order = overview.get("capability_order")
    if (
        not isinstance(order, list)
        or any(not isinstance(item, str) for item in order)
        or len(order) != len(expected_ids)
        or len(set(order)) != len(order)
        or set(order) != set(expected_ids)
    ):
        raise ValueError("project overview capability_order must be an exact permutation")
    scope = packet.get("scope")
    allowed_paths = set(
        scope.get("allowed_source_paths", [])
        if isinstance(scope, dict) and isinstance(scope.get("allowed_source_paths"), list)
        else []
    )
    source_root = source.resolve()

    def normalize_refs(owner: dict[str, object], field: str, *, minimum: int) -> None:
        refs = owner.get("source_refs")
        if not isinstance(refs, list) or len(refs) < minimum:
            raise ValueError(f"project overview {field} requires source_refs")
        for ref in refs:
            if not isinstance(ref, dict):
                raise ValueError(f"project overview {field} has invalid source_ref")
            path = ref.get("path")
            line_start = ref.get("line_start")
            line_end = ref.get("line_end")
            claim = ref.get("claim")
            if (
                not isinstance(path, str)
                or path not in allowed_paths
                or not isinstance(line_start, int)
                or not isinstance(line_end, int)
                or line_start < 1
                or line_end < line_start
                or not isinstance(claim, str)
                or not claim.strip()
            ):
                raise ValueError(f"project overview {field} escaped source scope")
            candidate = source_root.joinpath(*_repo_path_parts(path))
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(source_root)
                line_count = len(resolved.read_text(encoding="utf-8").splitlines())
            except (FileNotFoundError, OSError, UnicodeDecodeError, ValueError) as error:
                raise ValueError(
                    f"project overview {field} references unreadable source: {path}"
                ) from error
            if line_count < 1:
                raise ValueError(f"project overview {field} references empty source: {path}")
            ref["line_start"] = min(line_start, line_count)
            ref["line_end"] = min(max(int(ref["line_start"]), line_end), line_count)
            ref["claim"] = claim.strip()

    normalize_refs(overview, "project", minimum=3)
    axes = overview.get("core_product_axes")
    if not isinstance(axes, list) or not 1 <= len(axes) <= 4:
        raise ValueError("project overview requires one to four core product axes")
    assigned_ids: list[str] = []
    axis_ids: set[str] = set()
    for position, axis in enumerate(axes, start=1):
        if not isinstance(axis, dict):
            raise ValueError("project overview product axis is invalid")
        axis_id = axis.get("id")
        member_ids = axis.get("capability_ids")
        if not isinstance(axis_id, str) or not axis_id or axis_id in axis_ids:
            raise ValueError("project overview product axis ids must be unique")
        if not isinstance(member_ids, list) or not member_ids or any(
            not isinstance(item, str) or item not in expected_ids for item in member_ids
        ):
            raise ValueError("project overview product axis has invalid capability ids")
        axis_ids.add(axis_id)
        assigned_ids.extend(member_ids)
        normalize_refs(axis, f"core_product_axes[{position}]", minimum=1)
    supporting = overview.get("supporting_capability_ids")
    if not isinstance(supporting, list) or any(
        not isinstance(item, str) or item not in expected_ids for item in supporting
    ):
        raise ValueError("project overview supporting capability ids are invalid")
    if len(set(assigned_ids)) != len(assigned_ids):
        raise ValueError("project overview assigns a capability to multiple product axes")
    if set(assigned_ids) & set(supporting):
        raise ValueError("project overview core and supporting capabilities overlap")
    if set(assigned_ids) | set(supporting) != set(expected_ids):
        raise ValueError("project overview capability hierarchy must cover every capability")
    engineering_structure = overview.get("engineering_structure")
    if not isinstance(engineering_structure, dict):
        raise ValueError("project overview engineering_structure is missing")
    normalize_refs(engineering_structure, "engineering_structure", minimum=1)
    for field in ("runtime_components", "code_organization"):
        items = overview.get(field)
        if not isinstance(items, list) or len(items) < 2:
            raise ValueError(f"project overview {field} is incomplete")
        for position, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"project overview {field} item is invalid")
            if field == "code_organization":
                directory = item.get("path")
                parts = _repo_path_parts(directory)
                if not parts or not any(
                    _path_is_within_modules(path, [str(directory)])
                    for path in allowed_paths
                ):
                    raise ValueError(
                        f"project overview code directory is outside source scope: {directory}"
                    )
            normalize_refs(item, f"{field}[{position}]", minimum=1)
    return copy.deepcopy(overview)


def _require_inventory_scope(
    payload: dict[str, object],
    packet: dict[str, object],
) -> None:
    scope = packet.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("inventory packet has no scope")
    allowed_paths = set(scope.get("allowed_source_paths", []))
    allowed_features = set(scope.get("feature_ids", []))
    allowed_evidence = set(scope.get("evidence_ids", []))
    allowed_modules = set(scope.get("module_paths", []))
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("Codex inventory did not produce capabilities")
    capability_ids = {
        str(item.get("id"))
        for item in capabilities
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    implementation_memberships: set[tuple[str, str]] = set()
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ValueError("Codex inventory produced a non-object capability")
        capability_id = str(capability.get("id") or "unknown")
        source_feature_ids = capability.get("source_feature_ids", [])
        evidence_ids = capability.get("evidence_ids", [])
        source_refs = capability.get("source_refs", [])
        if not isinstance(source_feature_ids, list) or not set(source_feature_ids) <= allowed_features:
            raise ValueError(f"Codex inventory escaped feature scope: {capability_id}")
        if not isinstance(evidence_ids, list) or not set(evidence_ids) <= allowed_evidence:
            raise ValueError(f"Codex inventory escaped evidence scope: {capability_id}")
        if not isinstance(source_refs, list):
            raise ValueError(f"Codex inventory has invalid source refs: {capability_id}")
        escaped_paths = sorted(
            {
                str(item.get("path") or "<missing>")
                for item in source_refs
                if not isinstance(item, dict) or item.get("path") not in allowed_paths
            }
        )
        if escaped_paths:
            raise ValueError(
                f"Codex inventory escaped source scope: {capability_id}: {escaped_paths[0]}"
            )
        implementation_modules = capability.get("implementation_modules")
        if implementation_modules is not None:
            if not isinstance(implementation_modules, list) or not implementation_modules:
                raise ValueError(
                    f"Codex inventory has no implementation modules: {capability_id}"
                )
            for module in implementation_modules:
                if not isinstance(module, dict):
                    raise ValueError(
                        f"Codex inventory has invalid implementation module: {capability_id}"
                    )
                path = module.get("path")
                if path not in allowed_modules:
                    raise ValueError(
                        f"Codex inventory escaped module scope: {capability_id}: {path}"
                    )
                if module.get("classification") not in {"core", "supporting"}:
                    raise ValueError(
                        f"Codex inventory has invalid module classification: {capability_id}"
                    )
                implementation_memberships.add((str(path), capability_id))

    if not scope.get("require_module_coverage"):
        return
    required_product_modules = {
        path
        for path in scope.get("required_product_module_paths", [])
        if isinstance(path, str)
    }
    dispositions = payload.get("module_dispositions")
    if not isinstance(dispositions, list):
        raise ValueError("Codex inventory omitted module dispositions")
    disposition_by_path: dict[str, dict[str, object]] = {}
    disposition_memberships: set[tuple[str, str]] = set()
    for disposition in dispositions:
        if not isinstance(disposition, dict):
            raise ValueError("Codex inventory has an invalid module disposition")
        path = disposition.get("path")
        status = disposition.get("disposition")
        members = disposition.get("capability_ids")
        reason = disposition.get("reason")
        if (
            not isinstance(path, str)
            or path not in required_product_modules
            or path in disposition_by_path
        ):
            raise ValueError("Codex inventory has an invalid module disposition path")
        if status not in {"core-capability", "supporting", "excluded"}:
            raise ValueError("Codex inventory has an invalid module disposition status")
        if (
            not isinstance(members, list)
            or any(not isinstance(item, str) or item not in capability_ids for item in members)
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise ValueError("Codex inventory has an invalid module disposition closure")
        if status == "core-capability" and not members:
            raise ValueError("Codex inventory left a core module without a capability")
        disposition_by_path[path] = disposition
        disposition_memberships.update((path, member) for member in members)
    missing = sorted(required_product_modules - set(disposition_by_path))
    if missing:
        raise ValueError(
            f"Codex inventory left unreviewed product modules: {missing[0]}"
        )
    if set(disposition_by_path) - required_product_modules:
        raise ValueError("Codex inventory reviewed modules outside the product scope")
    missing_memberships = sorted(
        membership
        for membership in implementation_memberships - disposition_memberships
        if membership[0] in required_product_modules
    )
    if missing_memberships:
        path, capability_id = missing_memberships[0]
        raise ValueError(
            "Codex inventory module disposition does not reference capability: "
            f"{path}: {capability_id}"
        )


def _canonicalize_inventory_payload(
    payload: dict[str, object], packet: dict[str, object]
) -> dict[str, object]:
    normalized = copy.deepcopy(payload)
    evidence_by_path: dict[str, list[dict[str, object]]] = {}
    for evidence in packet.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        path = evidence.get("path")
        if isinstance(path, str):
            evidence_by_path.setdefault(path, []).append(evidence)
    hints = [
        item for item in packet.get("feature_hints", []) if isinstance(item, dict)
    ]
    capabilities = normalized.get("capabilities")
    if not isinstance(capabilities, list):
        return normalized
    scope = packet.get("scope")
    allowed_paths = set(
        scope.get("allowed_source_paths", [])
        if isinstance(scope, dict)
        else _source_paths(packet)
    )
    allowed_module_paths = {
        value
        for value in (
            scope.get("module_paths", []) if isinstance(scope, dict) else []
        )
        if isinstance(value, str)
    }
    if not allowed_module_paths:
        module_views, _ = _build_module_views(
            packet, _compact_global_graph_context(packet.get("capability_graph"))
        )
        allowed_module_paths = {
            str(item["path"])
            for item in module_views
            if isinstance(item.get("path"), str)
        }
    accepted: list[dict[str, object]] = []
    rejected_examples: list[str] = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        refs = [
            item
            for item in capability.get("source_refs", [])
            if isinstance(item, dict)
        ]
        if not refs or any(item.get("path") not in allowed_paths for item in refs):
            rejected_examples.append(
                f"{capability.get('id') or 'unknown'}:"
                f"{next((item.get('path') for item in refs if item.get('path') not in allowed_paths), '<none>')}"
            )
            continue
        matched_evidence: list[str] = []
        for source_ref in refs:
            path = source_ref.get("path")
            start = source_ref.get("line_start")
            end = source_ref.get("line_end")
            if not isinstance(path, str) or not isinstance(start, int) or not isinstance(end, int):
                continue
            for evidence in evidence_by_path.get(path, []):
                evidence_id = evidence.get("id")
                evidence_start = evidence.get("line_start")
                evidence_end = evidence.get("line_end")
                if (
                    isinstance(evidence_id, str)
                    and isinstance(evidence_start, int)
                    and isinstance(evidence_end, int)
                    and (
                        _ranges_overlap(start, end, evidence_start, evidence_end)
                        or evidence.get("kind") == "graph-navigation-slice"
                    )
                    and evidence_id not in matched_evidence
                ):
                    matched_evidence.append(evidence_id)
        matched_features: list[str] = []
        for hint in hints:
            hint_id = hint.get("id")
            if not isinstance(hint_id, str):
                continue
            hint_evidence = {
                identifier
                for identifier in hint.get("evidence_ids", [])
                if isinstance(identifier, str)
            }
            if hint_evidence & set(matched_evidence):
                matched_features.append(hint_id)
                continue
            hint_paths = _source_paths(hint)
            if any(source_ref.get("path") in hint_paths for source_ref in refs):
                matched_features.append(hint_id)
        if not matched_evidence and matched_features:
            matched_feature_set = set(matched_features)
            matched_evidence.extend(
                identifier
                for hint in hints
                if hint.get("id") in matched_feature_set
                for identifier in hint.get("evidence_ids", [])
                if isinstance(identifier, str)
            )
        if not matched_evidence or not matched_features:
            rejected_examples.append(
                f"{capability.get('id') or 'unknown'}:no-canonical-anchor"
            )
            continue
        raw_modules = capability.get("implementation_modules")
        if isinstance(raw_modules, list):
            normalized_modules: dict[str, dict[str, object]] = {}
            for module in raw_modules:
                if not isinstance(module, dict):
                    continue
                raw_path = module.get("path")
                if not isinstance(raw_path, str):
                    continue
                resolved_path = raw_path if raw_path in allowed_module_paths else None
                if resolved_path is None:
                    candidates = [
                        module_path
                        for module_path in allowed_module_paths
                        if _path_is_within_modules(raw_path, [module_path])
                    ]
                    if candidates:
                        resolved_path = max(
                            candidates, key=lambda value: len(_repo_path_parts(value))
                        )
                if resolved_path is None:
                    continue
                normalized_module = copy.deepcopy(module)
                normalized_module["path"] = resolved_path
                existing = normalized_modules.get(resolved_path)
                if existing is None:
                    normalized_modules[resolved_path] = normalized_module
                    continue
                for field in ("responsibility", "handoff"):
                    old = str(existing.get(field) or "").strip()
                    new = str(normalized_module.get(field) or "").strip()
                    if new and new not in old:
                        existing[field] = f"{old}；{new}" if old else new
                if module.get("classification") == "core":
                    existing["classification"] = "core"
            capability["implementation_modules"] = list(normalized_modules.values())
        capability["evidence_ids"] = matched_evidence
        capability["source_feature_ids"] = list(dict.fromkeys(matched_features))
        accepted.append(capability)
    if not accepted:
        detail = rejected_examples[0] if rejected_examples else "no-capabilities"
        raise ValueError(
            f"inventory produced no capability with canonical source closure ({detail})"
        )
    dispositions = normalized.get("module_dispositions")
    if isinstance(dispositions, list):
        disposition_by_path = {
            item.get("path"): item
            for item in dispositions
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        for capability in accepted:
            capability_id = capability.get("id")
            if not isinstance(capability_id, str):
                continue
            for module in capability.get("implementation_modules", []):
                if not isinstance(module, dict):
                    continue
                disposition = disposition_by_path.get(module.get("path"))
                if not isinstance(disposition, dict):
                    continue
                members = disposition.get("capability_ids")
                if (
                    isinstance(members, list)
                    and capability_id not in members
                    and disposition.get("disposition") != "excluded"
                ):
                    members.append(capability_id)
    normalized["capabilities"] = accepted
    return normalized


def _require_inventory_against_pack(
    payload: dict[str, object], pack: dict[str, object]
) -> None:
    module_views, _ = _build_module_views(
        pack, _compact_global_graph_context(pack.get("capability_graph"))
    )
    module_paths = [
        item.get("path")
        for item in module_views
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and item.get("path") != "."
    ]
    require_module_coverage = isinstance(payload.get("module_dispositions"), list)
    packet = {
        "scope": {
            "allowed_source_paths": sorted(_source_paths(pack)),
            "module_paths": module_paths,
            "required_product_module_paths": [
                str(item["path"])
                for item in module_views
                if item.get("category") == "product-implementation"
            ],
            "require_module_coverage": require_module_coverage,
            "feature_ids": [
                item.get("id")
                for item in pack.get("feature_hints", [])
                if isinstance(item, dict) and item.get("id")
            ],
            "evidence_ids": [
                item.get("id")
                for item in pack.get("evidence", [])
                if isinstance(item, dict) and item.get("id")
            ],
        }
    }
    _require_inventory_scope(payload, packet)


def _inventory_module_shards(pack: dict[str, object]) -> list[list[str]]:
    ignored = {"docs", "specs", "artifacts", "test", "tests"}
    modules: list[tuple[str, int]] = []
    for module in pack.get("modules", []):
        if not isinstance(module, dict):
            continue
        path = str(module.get("path") or "").strip()
        if not path or path == ".":
            continue
        parts = tuple(part.casefold() for part in Path(path).parts)
        if any(part in ignored for part in parts):
            continue
        symbol_count = module.get("symbol_count")
        if not isinstance(symbol_count, int) or symbol_count <= 0:
            continue
        if symbol_count <= 30:
            modules.append((path, symbol_count))
            continue
        source_paths = {
            source_path
            for hint in pack.get("feature_hints", [])
            if isinstance(hint, dict)
            for source_path in _source_paths(hint)
            if _path_is_within_modules(source_path, [path])
        }
        pending = [(path, source_paths)]
        split_units: list[tuple[str, int]] = []
        while pending:
            prefix, prefix_paths = pending.pop()
            prefix_parts = _repo_path_parts(prefix)
            child_groups: dict[str, set[str]] = {}
            for source_path in prefix_paths:
                source_parts = _repo_path_parts(source_path)
                if len(source_parts) <= len(prefix_parts):
                    child_prefix = source_path
                else:
                    child_prefix = "/".join(
                        source_parts[: len(prefix_parts) + 1]
                    )
                child_groups.setdefault(child_prefix, set()).add(source_path)
            if len(child_groups) > 1 and (
                prefix == path or len(prefix_paths) > 20
            ):
                pending.extend(sorted(child_groups.items(), reverse=True))
            else:
                split_units.append((prefix, max(1, len(prefix_paths))))
        if split_units:
            modules.extend(sorted(split_units))
        else:
            modules.append((path, symbol_count))
    if not modules:
        return []
    total_symbols = sum(symbol_count for _, symbol_count in modules)
    shard_count = min(32, len(modules), max(2, (total_symbols + 19) // 20))
    shards: list[list[str]] = [[] for _ in range(shard_count)]
    shard_weights = [0 for _ in range(shard_count)]
    for path, symbol_count in sorted(modules, key=lambda item: (-item[1], item[0])):
        shard_index = min(range(shard_count), key=lambda index: shard_weights[index])
        shards[shard_index].append(path)
        shard_weights[shard_index] += symbol_count
    return [sorted(shard) for shard in shards if shard]


def _group_inventory_for_humans(
    payload: dict[str, object],
    *,
    source: Path,
    workspace: Path,
    deadline: float,
    provider: str,
    product_navigation: Sequence[dict[str, object]] = (),
) -> dict[str, object]:
    capabilities = [
        item for item in payload.get("capabilities", []) if isinstance(item, dict)
    ]
    if not capabilities:
        raise ValueError("capability grouping requires at least one candidate")
    cache_path = workspace / "grouped-capability-inventory.json"
    if cache_path.is_file():
        try:
            cached = read_json_path(cache_path)
            cached_capabilities = cached.get("capabilities")
            if isinstance(cached_capabilities, list) and cached_capabilities:
                print(
                    f"[report 4/6] 复用面向人类阅读的功能分组缓存，共 {len(cached_capabilities)} 章",
                    flush=True,
                )
                if len(cached_capabilities) >= len(capabilities):
                    return cached
                return _group_inventory_for_humans(
                    cached,
                    source=source,
                    workspace=workspace / "next-grouping-pass",
                    deadline=deadline,
                    provider=provider,
                    product_navigation=product_navigation,
                )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass
    compact = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "plain_summary": item.get("plain_summary"),
            "mechanism": item.get("mechanism"),
            "paths": [
                ref.get("path")
                for ref in item.get("source_refs", [])
                if isinstance(ref, dict) and isinstance(ref.get("path"), str)
            ][:3],
        }
        for item in capabilities
    ]
    positioning = [
        {
            "path": item.get("path"),
            "snippet": str(item.get("snippet") or "")[:12_000],
        }
        for item in product_navigation
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]
    prompt = """你正在把细粒度代码候选整理成面向人的“业务功能目录”。只返回 JSON object。

规则：
- 这里只做语义归组；输入目录已经包含全部信息。禁止扫描、搜索或读取源码仓库。
- 先读 product_navigation，确认作者把它定义成什么产品、主要用户是谁、承诺什么结果。它只用于产品定位；
  具体能力仍必须由输入候选的源码证据闭合。
- 一级功能必须是产品对外提供的业务能力或框架公开能力，不是代码模块。报告必须先回答“用户能用它完成什么”，
  然后章节内部才回答“哪些模块共同实现”。目录、类、路由、适配器、example 和脚本本身不是一级功能。
- 如果仓库是框架/SDK，“用户”是使用框架的开发者；能力应写成开发者能构建或控制的稳定产品行为，
  例如有证据时可写实时帧管线、轮次/打断、传输会话、模型服务接入、工具调用、多模态输入；
  不能把某个 food-ordering、voicemail、vision 示例直接当作项目的最高层产品能力。
- example、demo 和 sample 不要丢弃：把它们并入其所演示的公开能力，后续作为“仓库已有场景”解释
  这项能力怎样被组合使用；除非仓库本身就是案例产品，否则示例场景不能成为一级功能标题。
- 如果仓库是平台，“用户”是平台操作者或最终业务用户；必须优先写完整业务旅程，例如实时通话、
  可视化工作流、任务提交到 Worker 结果回传，而不是数据库迁移、API 骨架或内部状态类。
- 每个输入 id 必须且只能出现在一个 group.member_ids 或 excluded_supporting_items.member_id 中。
- group 只保留能回答“谁为了什么目标触发、改变什么产品状态或交付什么可见结果”的产品能力。
- 健康/就绪探针、metrics、静态根页、文档页、smoke test、fixture、样本生成、构建发布脚本、
  内部诊断路由若只是承载或运维支撑，放入 excluded_supporting_items 并写明原因，绝不能单独成章。
- 若某个支撑入口属于一条真实产品链，把它并入那条产品能力；不要把路由本身写成另一个功能。
- 通用 UI、全局 context、API/RPC 骨架、日志、错误恢复、feature flag、测试页和平台运行壳如果没有
  独立用户结果，同样放入 excluded_supporting_items 或并入它实际支撑的产品能力。
- 不设章节数量上限，也不以压缩到某个数字为目标。
- 只有共享同一用户目标、主要状态、可见结果和核心运行机制的条目才可成为一组；“都和音频有关”或
  “都在 examples 目录”不构成同一功能。上下文压缩与音质增强、provider 热切换与传输协议等不同结果
  不得为了减少章节而拼成一章。
- 单一路由、页面、helper、构建脚本或测试如果只是某项产品能力的实现证据，应并入对应能力。
- UI、API 与后端执行器若共同完成一个端到端用户能力，应合为一章，不要按代码层拆章。
- Memory、Agent Loop、Graph、Voice、Router 等机制不同的能力不得因为名称相近而合并。
- title 必须是第一次看项目的人能理解的功能名，不能是文件、类、函数或路由名。
- groups 的顺序就是最终报告顺序：先放最能代表项目、最接近主要用户目标且最有技术差异的核心旅程；
  再放核心旅程依赖的业务能力；接入、配置、管理与工程支撑放最后或排除。
- 对“平台提交任务、Worker 执行”的系统，任务提交→持久化/排队→调度/租约→Worker 执行→事件与结果回传
  是必须优先讲清楚的主架构，不得先讲页面组件或 API 骨架。
- 每个 group 必须明确 user_actor、user_goal、visible_outcome、product_surface、causal_flow；
  why_one_capability 要说明为什么这些 member 共同交付一个结果，而不是恰好代码相邻。

product_navigation：
""" + json.dumps(positioning, ensure_ascii=False, separators=(",", ":")) + """

输入目录：
""" + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    grouping_workspace = workspace / "grouping"
    grouping_source = grouping_workspace / "source-slice"
    grouping_source.mkdir(parents=True, exist_ok=True)
    grouped = _run_codex_json(
        source=grouping_source,
        workspace=grouping_workspace,
        schema=_inventory_group_json_schema(),
        prompt=prompt,
        timeout=_remaining_model_timeout(deadline),
        stage_slug="capability-grouping",
        progress_label=f"Codex 正在把 {len(capabilities)} 个细粒度条目组织成人类功能章节",
        provider=provider,
    )
    by_id = {
        str(item.get("id")): item
        for item in capabilities
        if isinstance(item.get("id"), str)
    }
    assigned: set[str] = set()
    excluded: set[str] = set()
    result: list[dict[str, object]] = []
    groups = grouped.get("groups")
    if not isinstance(groups, list):
        groups = []
    exclusions = grouped.get("excluded_supporting_items")
    if not isinstance(exclusions, list):
        exclusions = []
    for exclusion in exclusions:
        if not isinstance(exclusion, dict):
            raise ValueError("capability grouping produced an invalid exclusion")
        member_id = exclusion.get("member_id")
        reason = exclusion.get("reason")
        if (
            not isinstance(member_id, str)
            or member_id not in by_id
            or not isinstance(reason, str)
            or not reason.strip()
            or member_id in excluded
        ):
            raise ValueError("capability grouping produced an invalid exclusion")
        excluded.add(member_id)
    for position, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            continue
        raw_member_ids = group.get("member_ids")
        if not isinstance(raw_member_ids, list):
            raise ValueError("capability grouping produced invalid member_ids")
        member_ids = [identifier for identifier in raw_member_ids if isinstance(identifier, str)]
        if (
            len(member_ids) != len(raw_member_ids)
            or any(identifier not in by_id for identifier in member_ids)
            or any(identifier in assigned or identifier in excluded for identifier in member_ids)
        ):
            raise ValueError("capability grouping did not produce an exact id partition")
        if not member_ids:
            raise ValueError("capability grouping produced an empty group")
        assigned.update(member_ids)
        members = [by_id[identifier] for identifier in member_ids]
        implementation_refs = [
            source_ref
            for member in members
            for source_ref in member.get("source_refs", [])
            if isinstance(source_ref, dict)
            and isinstance(source_ref.get("path"), str)
            and not any(
                part.casefold() in {
                    "docs", "specs", "examples", "example", "demo", "demos",
                    "sample", "samples", "test", "tests", "fixtures",
                }
                for part in _repo_path_parts(str(source_ref.get("path")))
            )
        ]
        if not implementation_refs:
            raise ValueError(
                "capability grouping promoted an example/document/test without product implementation evidence"
            )
        title = str(group.get("title") or "").strip() or f"业务功能 {position}"
        user_actor = str(group.get("user_actor") or "").strip()
        user_goal = str(group.get("user_goal") or "").strip()
        visible_outcome = str(group.get("visible_outcome") or "").strip()
        product_surface = str(group.get("product_surface") or "").strip()
        causal_flow = str(group.get("causal_flow") or "").strip()
        if not all((user_actor, user_goal, visible_outcome, product_surface, causal_flow)):
            raise ValueError("capability grouping omitted business capability semantics")
        source_refs: list[dict[str, object]] = []
        seen_refs: set[tuple[object, ...]] = set()
        for member in members:
            for source_ref in member.get("source_refs", []):
                if not isinstance(source_ref, dict):
                    continue
                key = (
                    source_ref.get("path"),
                    source_ref.get("line_start"),
                    source_ref.get("line_end"),
                )
                if key in seen_refs:
                    continue
                seen_refs.add(key)
                source_refs.append(copy.deepcopy(source_ref))
        mechanisms = list(
            dict.fromkeys(
                str(member.get("mechanism") or "")
                for member in members
                if member.get("mechanism")
            )
        )
        result.append(
            {
                "id": str(group.get("id") or f"capability-group-{position}"),
                "title": title,
                "summary": (
                    f"{user_actor}为了{user_goal}使用{product_surface}，最终得到{visible_outcome}。"
                ),
                "mechanism": " + ".join(mechanisms[:8]) or "multi-stage-capability",
                "question": f"{causal_flow}在源码中怎样跨模块完成，并在哪些状态与失败边界收束？",
                "use_when": f"当你需要复用“{visible_outcome}”这项完整产品结果时。",
                "distinguish": (
                    "这是用户可感知的业务/框架能力；组成它的目录、API、适配器与示例只作为实现证据。"
                ),
                "plain_summary": (
                    f"{title} 本质上是{causal_flow}；它交付的是{visible_outcome}，"
                    "不是某个入口、目录或示例脚本。"
                ),
                "source_feature_ids": list(
                    dict.fromkeys(
                        identifier
                        for member in members
                        for identifier in member.get("source_feature_ids", [])
                        if isinstance(identifier, str)
                    )
                ),
                "evidence_ids": list(
                    dict.fromkeys(
                        identifier
                        for member in members
                        for identifier in member.get("evidence_ids", [])
                        if isinstance(identifier, str)
                    )
                ),
                "source_refs": source_refs[:16],
            }
        )
    if assigned | excluded != set(by_id):
        raise ValueError("capability grouping omitted input ids")
    if excluded:
        print(
            f"[report 4/6] 排除 {len(excluded)} 个仅承载、运维或测试用途的支撑项；不作为产品功能章节",
            flush=True,
        )
    if not result:
        raise ValueError("capability grouping excluded every candidate")
    grouped_payload = {"capabilities": result}
    cache_path.write_text(_json_artifact(grouped_payload), encoding="utf-8")
    print(
        f"[report 4/6] 细粒度目录组织为 {len(result)} 个可读功能章节；没有丢弃输入条目",
        flush=True,
    )
    if len(result) < len(capabilities) and len(result) > 1 and not excluded:
        return _group_inventory_for_humans(
            grouped_payload,
            source=source,
            workspace=workspace / "next-grouping-pass",
            deadline=deadline,
            provider=provider,
            product_navigation=product_navigation,
        )
    return grouped_payload


def _remaining_model_timeout(deadline: float) -> int:
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


def _synthesize_with_codex(
    source: Path,
    pack: dict[str, object],
    workspace: Path,
    timeout: int,
    inventory_arg: str | None = None,
    provider: str = "codex",
) -> dict[str, object]:
    pack_path = workspace / "analysis-pack.json"
    pack_path.write_text(_json_artifact(pack), encoding="utf-8")
    deadline = time.monotonic() + timeout
    print("[report 4/6] 先归纳完整功能目录，再分批补全章节…", flush=True)
    if inventory_arg:
        inventory_input = read_json_path(Path(inventory_arg).expanduser())
        inventory_payload = _inventory_from_manifest(inventory_input, pack)
        inventory_needs_grouping = not isinstance(
            inventory_payload.get("module_dispositions"), list
        )
        print(
            f"[report 4/6] 已加载外部功能目录，共 {len(inventory_payload['capabilities'])} 项；跳过 inventory 模型阶段",
            flush=True,
        )
    else:
        inventory_needs_grouping = False
        inventory_workspace = workspace / "inventory"
        inventory_workspace.mkdir(parents=True, exist_ok=True)
        inventory_pack = _attach_source_excerpts(
            _add_project_navigation(
                _build_global_business_inventory_pack(pack), pack
            ),
            source,
        )
        inventory_pack_path = inventory_workspace / "analysis-pack-global.json"
        inventory_pack_path.write_text(
            _json_artifact(inventory_pack), encoding="utf-8"
        )
        source_slice = _materialize_source_slice(
            source,
            inventory_workspace,
            inventory_pack["scope"]["allowed_source_paths"],
        )
        model_inventory_pack_path = _stage_model_json(
            source_slice, "analysis-pack-global.json", inventory_pack
        )
        graph = inventory_pack.get("capability_graph")
        graph = graph if isinstance(graph, dict) else {}
        print(
            "[report 4/6] 整仓代码图一次归纳业务功能："
            f"{len(inventory_pack.get('modules', []))} 个模块、"
            f"{len(graph.get('mechanism_clusters', []))} 个机制簇、"
            f"{len(inventory_pack.get('feature_hints', []))} 个证据锚点；"
            "模块只用于功能判断与实现映射，不再分别调用模型",
            flush=True,
        )
        cached_inventory_path = inventory_workspace / "capability-inventory.json"
        inventory_payload: dict[str, object] | None = None
        if cached_inventory_path.is_file():
            try:
                candidate_inventory = _canonicalize_inventory_payload(
                    read_json_path(cached_inventory_path), inventory_pack
                )
                _require_inventory_scope(candidate_inventory, inventory_pack)
                inventory_payload = candidate_inventory
                print(
                    "[report 4/6] 复用已通过整仓模块覆盖门禁的功能目录缓存",
                    flush=True,
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                inventory_payload = None
        if inventory_payload is None:
            inventory_payload = _run_codex_json(
                source=source_slice,
                workspace=inventory_workspace,
                schema=_inventory_json_schema(),
                prompt=_provider_prompt(
                    _inventory_prompt(model_inventory_pack_path, source_slice),
                    provider,
                    analysis_pack=inventory_pack,
                ),
                timeout=_remaining_model_timeout(deadline),
                stage_slug="capability-inventory",
                progress_label="Codex 正在基于整仓代码图归纳业务功能",
                provider=provider,
            )
            inventory_payload = _canonicalize_inventory_payload(
                inventory_payload, inventory_pack
            )
            _require_inventory_scope(inventory_payload, inventory_pack)
    inventory_payload = _canonicalize_inventory_payload(inventory_payload, pack)
    _require_inventory_against_pack(inventory_payload, pack)
    if inventory_needs_grouping:
        navigation_pack = _add_project_navigation(
            {"scope": {"allowed_source_paths": []}}, pack
        )
        inventory_payload = _group_inventory_for_humans(
            inventory_payload,
            source=source,
            workspace=workspace,
            deadline=deadline,
            provider=provider,
            product_navigation=[
                item
                for item in navigation_pack.get("product_navigation", [])
                if isinstance(item, dict)
            ],
        )
        _require_inventory_against_pack(inventory_payload, pack)
    raw_capabilities = inventory_payload.get("capabilities")
    if not isinstance(raw_capabilities, list) or not raw_capabilities:
        raise ValueError("Codex inventory did not produce capabilities")
    capabilities = [capability for capability in raw_capabilities if isinstance(capability, dict)]
    capability_ids = [str(capability.get("id") or "") for capability in capabilities]
    if any(not capability_id for capability_id in capability_ids):
        raise ValueError("Codex inventory produced empty capability id")
    if len(set(capability_ids)) != len(capability_ids):
        raise ValueError("Codex inventory capability ids must be unique")
    overview_workspace = workspace / "project-overview"
    overview_workspace.mkdir(parents=True, exist_ok=True)
    overview_pack = _build_chapter_batch_pack(pack, capabilities)
    overview_pack = _add_project_navigation(overview_pack, pack)
    overview_pack = _attach_source_excerpts(overview_pack, source)
    overview_pack_path = overview_workspace / "analysis-pack-overview.json"
    overview_pack_path.write_text(_json_artifact(overview_pack), encoding="utf-8")
    overview_source = _materialize_source_slice(
        source,
        overview_workspace,
        overview_pack["scope"]["allowed_source_paths"],
    )
    model_overview_pack_path = _stage_model_json(
        overview_source, "analysis-pack-overview.json", overview_pack
    )
    overview_result_path = overview_workspace / "project-overview.json"
    project_overview: dict[str, object] | None = None
    if overview_result_path.is_file():
        try:
            project_overview = _normalize_project_overview(
                read_json_path(overview_result_path),
                overview_pack,
                capabilities,
                source,
            )
            print("[report 4/6] 复用已校验的项目定位与架构章节缓存", flush=True)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            project_overview = None
    if project_overview is None:
        overview_payload = _run_codex_json(
            source=overview_source,
            workspace=overview_workspace,
            schema=_project_overview_json_schema(len(capabilities)),
            prompt=_provider_prompt(
                _project_overview_prompt(
                    model_overview_pack_path,
                    overview_source,
                    capability_ids,
                ),
                provider,
                analysis_pack=overview_pack,
                capability_inventory=inventory_payload,
            ),
            timeout=_remaining_model_timeout(deadline),
            stage_slug="project-overview",
            progress_label="Codex 正在说明项目定位、整体架构与代码组织",
            provider=provider,
        )
        project_overview = _normalize_project_overview(
            overview_payload, overview_pack, capabilities, source
        )
        overview_result_path.write_text(
            _json_artifact({"project_overview": project_overview}), encoding="utf-8"
        )
    by_capability_id = {str(item["id"]): item for item in capabilities}
    capability_ids = [str(item) for item in project_overview["capability_order"]]
    capabilities = [by_capability_id[identifier] for identifier in capability_ids]
    inventory_payload["capabilities"] = capabilities
    inventory_payload["project_overview"] = project_overview
    inventory_path = workspace / "capability-inventory.json"
    inventory_path.write_text(_json_artifact(inventory_payload), encoding="utf-8")
    print(
        f"[report 4/6] 功能目录完成，共 {len(capabilities)} 项；开始分批生成章节…",
        flush=True,
    )
    batches = _chunk_capabilities(
        capabilities,
        batch_size=(
            min(2, len(capabilities))
            if provider == "deepseek"
            else (4 if len(capabilities) > 4 else len(capabilities))
        ),
    )
    chapters_by_id: dict[str, dict[str, object]] = {}
    completed_batches = 0

    def synthesize_batch(
        batch_index: int, batch_capabilities: Sequence[dict[str, object]]
    ) -> dict[str, object]:
        batch_workspace = workspace / f"batch-{batch_index:02d}"
        batch_workspace.mkdir(parents=True, exist_ok=True)
        cached_result_path = batch_workspace / "chapter-result.json"
        expected_ids = {
            str(capability["id"])
            for capability in batch_capabilities
            if isinstance(capability.get("id"), str)
        }
        batch_pack = _attach_source_excerpts(
            _build_chapter_batch_pack(pack, batch_capabilities), source
        )
        if cached_result_path.is_file():
            try:
                cached = read_json_path(cached_result_path)
                cached_chapters = cached.get("chapters")
                cached_ids = {
                    str(chapter.get("id"))
                    for chapter in cached_chapters
                    if isinstance(chapter, dict) and isinstance(chapter.get("id"), str)
                } if isinstance(cached_chapters, list) else set()
                if cached_ids == expected_ids:
                    cached = _close_chapter_evidence(
                        cached, batch_pack, batch_capabilities, source
                    )
                    cached_result_path.write_text(
                        _json_artifact(cached), encoding="utf-8"
                    )
                    print(
                        f"[report 4/6] 复用章节批次 {batch_index + 1}/{len(batches)} 的已校验模型缓存",
                        flush=True,
                    )
                    return cached
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                pass
        batch_pack_path = batch_workspace / "analysis-pack-batch.json"
        batch_pack_path.write_text(_json_artifact(batch_pack), encoding="utf-8")
        source_slice = _materialize_source_slice(
            source,
            batch_workspace,
            batch_pack["scope"]["allowed_source_paths"],
        )
        model_batch_pack_path = _stage_model_json(
            source_slice, "analysis-pack-batch.json", batch_pack
        )
        model_inventory_path = _stage_model_json(
            source_slice, "capability-inventory.json", inventory_payload
        )
        capability_batch_ids = [
            str(capability["id"])
            for capability in batch_capabilities
            if isinstance(capability.get("id"), str)
        ]
        payload = _run_codex_json(
            source=source_slice,
            workspace=batch_workspace,
            schema=_chapter_batch_json_schema(len(capability_batch_ids)),
            prompt=_provider_prompt(
                _chapter_batch_prompt(
                    model_batch_pack_path,
                    model_inventory_path,
                    source_slice,
                    capability_batch_ids,
                ),
                provider,
                analysis_pack=batch_pack,
                capability_inventory=inventory_payload,
            ),
            timeout=_remaining_model_timeout(deadline),
            stage_slug=f"chapter-batch-{batch_index:02d}",
            progress_label=(
                f"Codex 正在补全章节批次 {batch_index + 1}/{len(batches)}"
            ),
            provider=provider,
        )
        payload = _close_chapter_evidence(
            payload, batch_pack, batch_capabilities, source
        )
        cached_result_path.write_text(_json_artifact(payload), encoding="utf-8")
        return payload

    max_workers = min(4, len(batches))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(synthesize_batch, batch_index, batch): (batch_index, batch)
            for batch_index, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            batch_index, batch = futures[future]
            payload = future.result()
            batch_chapters = payload.get("chapters")
            if not isinstance(batch_chapters, list) or not batch_chapters:
                raise ValueError(
                    f"Codex chapter batch {batch_index + 1} did not produce chapters"
                )
            expected = {
                str(capability["id"]): capability
                for capability in batch
                if isinstance(capability.get("id"), str)
            }
            for chapter in batch_chapters:
                if not isinstance(chapter, dict):
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} produced non-object chapter"
                    )
                chapter_id = str(chapter.get("id") or "")
                if chapter_id not in expected:
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} returned unexpected chapter: {chapter_id or 'unknown'}"
                    )
                inventory_capability = expected[chapter_id]
                if chapter.get("title") != inventory_capability.get("title"):
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} changed chapter title: {chapter_id}"
                    )
                if chapter.get("source_feature_ids") != inventory_capability.get(
                    "source_feature_ids"
                ):
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} changed source_feature_ids: {chapter_id}"
                    )
                inventory_evidence = set(
                    inventory_capability.get("evidence_ids", [])
                    if isinstance(inventory_capability.get("evidence_ids"), list)
                    else []
                )
                chapter_evidence = set(
                    chapter.get("evidence_ids", [])
                    if isinstance(chapter.get("evidence_ids"), list)
                    else []
                )
                if not inventory_evidence <= chapter_evidence:
                    raise ValueError(
                        f"Codex chapter batch {batch_index + 1} dropped inventory evidence: {chapter_id}"
                    )
                chapters_by_id[chapter_id] = chapter
            completed_batches += 1
            print(
                f"[report 4/6] 章节批次完成 {completed_batches}/{len(batches)}；"
                f"已补全 {len(chapters_by_id)}/{len(capabilities)} 章",
                flush=True,
            )
    if set(chapters_by_id) != set(capability_ids):
        missing = [capability_id for capability_id in capability_ids if capability_id not in chapters_by_id]
        raise ValueError(f"Codex chapter batches missed capabilities: {missing[0]}")
    ordered_chapters = [chapters_by_id[capability_id] for capability_id in capability_ids]
    _require_source_ref_quality(ordered_chapters)
    return {
        "schema_version": "repo-teacher-human-report/v1",
        "project": {
            "commit": pack["project"]["commit"],
            "analysis_fingerprint": pack["project"]["analysis_fingerprint"],
            "overview": project_overview,
        },
        "generator": {
            "name": "Codex",
            "method": "repo-teacher batched capability synthesis",
        },
        "chapters": ordered_chapters,
    }


def _report_index_with_navigation_evidence(
    canonical: dict[str, object], pack: dict[str, object]
) -> dict[str, object]:
    report_index = copy.deepcopy(canonical)
    features = [
        item
        for item in report_index.get("features", [])
        if isinstance(item, dict)
    ]
    known_feature_ids = {
        item.get("id") for item in features if isinstance(item.get("id"), str)
    }
    for hint in pack.get("feature_hints", []):
        if not isinstance(hint, dict):
            continue
        identifier = hint.get("id")
        if not isinstance(identifier, str) or identifier in known_feature_ids:
            continue
        features.append(
            {
                "id": identifier,
                "kind": "graph-mechanism-candidate",
                "source": "report-only-graph-navigation",
            }
        )
        known_feature_ids.add(identifier)
    evidence = [
        item
        for item in report_index.get("evidence", [])
        if isinstance(item, dict)
    ]
    known_evidence_ids = {
        item.get("id") for item in evidence if isinstance(item.get("id"), str)
    }
    for item in pack.get("evidence", []):
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or identifier in known_evidence_ids:
            continue
        evidence.append(copy.deepcopy(item))
        known_evidence_ids.add(identifier)
    report_index["features"] = features
    report_index["evidence"] = evidence
    return report_index


def _report(
    source_arg: str,
    output_arg: str,
    narrative_arg: str | None,
    inventory_arg: str | None,
    model_timeout: int,
    provider: str,
    max_file_size: int,
    should_open: bool,
) -> int:
    source = Path(source_arg).expanduser()
    if not source.is_dir():
        print(f"error: source is not a directory: {source}", file=sys.stderr)
        return 2
    source = source.resolve()
    output = Path(output_arg).expanduser().resolve()
    try:
        print("[report 1/6] 扫描仓库并建立符号、关系和文件索引…", flush=True)
        previous = _load_baseline(output, source)
        canonical = build_index(
            source, output_dir=output, max_file_size=max_file_size, previous_index=previous
        )
        print(
            f"[report 2/6] 校验源码快照与索引… {canonical['stats']['files']} files, "
            f"{canonical['stats']['symbols']} symbols",
            flush=True,
        )
        _require_valid_index(canonical, source)
        print("[report 3/6] 准备模型证据包；文档只作导航，源码切片才可证明功能…", flush=True)
        capability_graph = build_capability_graph(canonical)
        pack = build_report_pack(canonical, capability_graph)
        if narrative_arg:
            print("[report 4/6] 读取已审核的人类叙述 JSON…", flush=True)
            narrative = _rebind_reviewed_narrative(
                read_json_path(Path(narrative_arg).expanduser()), pack
            )
        else:
            print(f"[report 4/6] 启动 {provider} 全功能 coverage pass…", flush=True)
            inventory_digest = None
            if inventory_arg:
                inventory_digest = hashlib.sha256(
                    Path(inventory_arg).expanduser().read_bytes()
                ).hexdigest()
            cache_identity = json.dumps(
                {
                    "source": str(source),
                    "commit": pack.get("project", {}).get("commit")
                    if isinstance(pack.get("project"), dict)
                    else None,
                    "analysis_fingerprint": pack.get("project", {}).get(
                        "analysis_fingerprint"
                    )
                    if isinstance(pack.get("project"), dict)
                    else None,
                    "provider": provider,
                    "inventory_sha256": inventory_digest,
                    "synthesis_contract": REPORT_SYNTHESIS_CONTRACT_VERSION,
                },
                sort_keys=True,
            ).encode("utf-8")
            cache_key = hashlib.sha256(cache_identity).hexdigest()[:24]
            model_workspace = (
                Path(tempfile.gettempdir()) / "repo-teacher-model-cache" / cache_key
            )
            model_workspace.mkdir(parents=True, exist_ok=True)
            cached_inventory = model_workspace / "capability-inventory.json"
            effective_inventory = inventory_arg
            if effective_inventory is None and cached_inventory.is_file():
                effective_inventory = str(cached_inventory)
                print(
                    f"[report 4/6] 复用当前源码快照的功能目录缓存：{cache_key}",
                    flush=True,
                )
            if provider == "codex":
                narrative = _synthesize_with_codex(
                    source,
                    pack,
                    model_workspace,
                    model_timeout,
                    effective_inventory,
                )
            else:
                narrative = _synthesize_with_codex(
                    source,
                    pack,
                    model_workspace,
                    model_timeout,
                    effective_inventory,
                    provider,
                )
        print("[report 5/6] 校验功能、源码路径、行号和证据闭包…", flush=True)
        report_index = _report_index_with_navigation_evidence(canonical, pack)
        composed = compose_human_report(report_index, narrative)
        generation_id = secrets.token_hex(16)
        canonical = _bind_generation(canonical, generation_id)
        pack = _bind_generation(pack, generation_id)
        narrative = _bind_generation(narrative, generation_id)
        composed = _bind_generation(composed, generation_id)
        artifacts = {
            "index.json": _json_artifact(canonical),
            "analysis-pack.json": _json_artifact(pack),
            "human-report.json": _json_artifact(narrative),
            "capability-graph.json": _json_artifact(
                _bind_generation(capability_graph, generation_id)
            ),
            "index.html": _html_artifact(render_report(composed), generation_id),
        }
        with OutputLock(output):
            print("[report 6/6] 原子发布 JSON 与人类可读 HTML…", flush=True)
            GenerationPublisher(output, generation_id).publish(
                artifacts,
                before_switch=lambda: _require_valid_index(canonical, source),
            )
    except subprocess.TimeoutExpired:
        print("error: Codex synthesis timed out", file=sys.stderr)
        return 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(f"error: failed to generate human report: {error}", file=sys.stderr)
        return 1
    report_path = output / "index.html"
    print(f"Generated human-first repository report: {report_path}")
    print(f"Capabilities: {len(composed['features'])}; evidence refs: {len(canonical['evidence'])}")
    if should_open:
        webbrowser.open(report_path.as_uri())
    return 0


def _compare(source_args: Sequence[str], output_arg: str, max_file_size: int, should_open: bool) -> int:
    from .comparison import build_technology_comparison
    from .comparison_report import render_comparison_report

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
                    render_report(index), generation_id
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
    from .module_locator import locate_modules
    from .module_report import render_module_report

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
                "index.html": _html_artifact(render_report(index), generation_id),
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
    from .skill_export import export_skill

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
    from .validation import validate_index

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
        from .persistence import atomic_write_text

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
        from .persistence import atomic_write_text

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
