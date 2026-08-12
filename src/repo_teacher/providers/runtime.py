"""Production adapters for schema-constrained model execution.

This module owns provider discovery, subprocess/HTTP transport, timeouts and
response decoding.  It intentionally knows nothing about repository analysis,
capability semantics or command routing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..persistence import atomic_write_text, read_json_path
from ..prompts import render_prompt


def decode_json_object(content: object) -> dict[str, object]:
    """Decode exactly one JSON object and reject trailing model prose."""

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


def _json_artifact(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write_model_performance(
    *,
    workspace: Path,
    stage_slug: str,
    provider: str,
    model: str,
    reasoning_effort: str | None,
    started: float,
    status: str,
    prompt: str,
    schema: dict[str, object],
    error: str | None = None,
) -> None:
    """Persist one provider-call timing record without prompts or secrets."""

    workspace.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": "repolens-model-call-performance/v1",
        "stage": stage_slug,
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "status": status,
        "duration_seconds": round(max(time.monotonic() - started, 0.0), 6),
        "prompt_bytes": len(prompt.encode("utf-8")),
        "schema_bytes": len(_json_artifact(schema).encode("utf-8")),
    }
    if error:
        payload["error"] = error[-1_000:]
    atomic_write_text(
        workspace / f"{stage_slug}-performance.json", _json_artifact(payload)
    )


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
    system_prompt = render_prompt("provider-json-system-v1.md", schema=schema_text)
    started = time.monotonic()
    print(f"[report 03/05] {progress_label}（DeepSeek JSON）…", flush=True)
    result: object | None = None
    last_error: Exception | None = None
    body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "stream": False,
                "temperature": 0.0,
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
        result = decode_json_object(payload["choices"][0]["message"]["content"])
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
        f"[report 03/05] {progress_label}完成，耗时 {time.monotonic() - started:.1f}s",
        flush=True,
    )
    return result


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
    bounded_prompt = render_prompt(
        "provider-json-envelope-v1.md",
        prompt=prompt,
        schema=json.dumps(schema, ensure_ascii=False, separators=(",", ":")),
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
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            process.kill()
            process.communicate()
            raise subprocess.TimeoutExpired(command[:-1] + ["<prompt>"], timeout)
        try:
            stdout, stderr = process.communicate(timeout=min(30.0, remaining))
            break
        except subprocess.TimeoutExpired:
            print(
                f"[report 03/05] {progress_label}（OpenCode）… "
                f"{int(time.monotonic() - started)}s",
                flush=True,
            )
    if process.returncode != 0:
        detail = (stderr or stdout or "OpenCode failed without output").strip()
        raise ValueError(f"OpenCode synthesis failed: {detail[-2_000:]}")
    result = decode_json_object(stdout)
    output_path.write_text(_json_artifact(result), encoding="utf-8")
    return result


def run_structured_json(
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
    """Execute one schema-constrained provider request."""

    if provider == "deepseek":
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
        started = time.monotonic()
        try:
            result = _run_deepseek_json(
                schema=schema,
                prompt=prompt,
                timeout=timeout,
                progress_label=progress_label,
            )
        except Exception as error:
            _write_model_performance(
                workspace=workspace,
                stage_slug=stage_slug,
                provider=provider,
                model=model,
                reasoning_effort=None,
                started=started,
                status="failed",
                prompt=prompt,
                schema=schema,
                error=str(error),
            )
            raise
        _write_model_performance(
            workspace=workspace,
            stage_slug=stage_slug,
            provider=provider,
            model=model,
            reasoning_effort=None,
            started=started,
            status="passed",
            prompt=prompt,
            schema=schema,
        )
        return result
    if provider == "opencode":
        model = os.environ.get(
            "REPO_TEACHER_OPENCODE_MODEL", "openrouter/deepseek/deepseek-v4-flash"
        ).strip()
        started = time.monotonic()
        try:
            result = _run_opencode_json(
                source=source,
                workspace=workspace,
                schema=schema,
                prompt=prompt,
                timeout=timeout,
                stage_slug=stage_slug,
                progress_label=progress_label,
            )
        except Exception as error:
            _write_model_performance(
                workspace=workspace,
                stage_slug=stage_slug,
                provider=provider,
                model=model,
                reasoning_effort=None,
                started=started,
                status="failed",
                prompt=prompt,
                schema=schema,
                error=str(error),
            )
            raise
        _write_model_performance(
            workspace=workspace,
            stage_slug=stage_slug,
            provider=provider,
            model=model,
            reasoning_effort=None,
            started=started,
            status="passed",
            prompt=prompt,
            schema=schema,
        )
        return result
    if provider != "codex":
        raise ValueError(f"unsupported narrative provider: {provider}")
    codex = shutil.which("codex")
    if codex is None:
        raise ValueError("Codex CLI was not found; install Codex or pass --narrative")
    inventory_stage = stage_slug in {
        "capability-inventory-model",
        "capability-inventory-closure-repair",
    }
    codex_model = os.environ.get(
        "REPO_TEACHER_CODEX_INVENTORY_MODEL"
        if inventory_stage
        else "REPO_TEACHER_CODEX_MODEL",
        "gpt-5.4-mini" if inventory_stage else "gpt-5.4",
    ).strip()
    reasoning_effort = os.environ.get(
        "REPO_TEACHER_CODEX_INVENTORY_REASONING_EFFORT"
        if inventory_stage
        else "REPO_TEACHER_CODEX_REASONING_EFFORT",
        "low",
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
        remaining = timeout - (time.monotonic() - started)
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
                f"[report 03/05] {progress_label}… "
                f"{int(time.monotonic() - started)}s",
                flush=True,
            )
    if process.returncode != 0:
        detail = (stderr or stdout or "Codex failed without output").strip()
        _write_model_performance(
            workspace=workspace,
            stage_slug=stage_slug,
            provider=provider,
            model=codex_model,
            reasoning_effort=reasoning_effort,
            started=started,
            status="failed",
            prompt=prompt,
            schema=schema,
            error=detail,
        )
        raise ValueError(f"Codex synthesis failed: {detail[-2_000:]}")
    if not output_path.is_file():
        error = f"Codex synthesis did not produce {output_path.name}"
        _write_model_performance(
            workspace=workspace,
            stage_slug=stage_slug,
            provider=provider,
            model=codex_model,
            reasoning_effort=reasoning_effort,
            started=started,
            status="failed",
            prompt=prompt,
            schema=schema,
            error=error,
        )
        raise ValueError(error)
    result = read_json_path(output_path)
    _write_model_performance(
        workspace=workspace,
        stage_slug=stage_slug,
        provider=provider,
        model=codex_model,
        reasoning_effort=reasoning_effort,
        started=started,
        status="passed",
        prompt=prompt,
        schema=schema,
    )
    return result
