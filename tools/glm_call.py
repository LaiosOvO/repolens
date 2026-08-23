#!/usr/bin/env python3
"""GLM coding plan (glm-5.3) batch caller for repolens.

OpenAI-compatible endpoint per Z.ai docs:
    POST https://api.z.ai/api/coding/paas/v4/chat/completions
    Authorization: Bearer $ZAI_API_KEY
    model: glm-5.3 (or glm-5.3[1m] for 1M context)

Design borrowed from PocketFlow-TCK call_llm.py (proven in the field):
    - JSON-file prompt cache keyed by SHA256(prompt + model) — batch reruns are free;
    - per-day call log for provenance;
    - retries with exponential backoff on 429/5xx;
    - reasoning_effort passthrough (thinking cannot be disabled on glm-5.3;
      use "low"/"high" for batch work, "max" is the default and slow).

Env:
    ZAI_API_KEY   required. No fallbacks — the key lives nowhere on this machine.
    GLM_MODEL     optional, default "glm-5.3"
    GLM_EFFORT    optional, default "high" (low|high|max)
    GLM_LOG_DIR   optional, default "logs" (relative to cwd)

Usage:
    from glm_call import call_glm
    txt = call_glm("...prompt...", effort="low", use_cache=True)

    CLI: python glm_call.py --selftest        # needs ZAI_API_KEY
         python glm_call.py --check-env       # env diagnostics, no key needed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

BASE_URL = "https://api.z.ai/api/coding/paas/v4"
DEFAULT_MODEL = "glm-5.3"
DEFAULT_EFFORT = "high"
MAX_TOKENS = 16384
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_DELAYS = (5, 15, 45, 120)  # seconds


def _log_path() -> str:
    log_dir = os.getenv("GLM_LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"glm_calls_{datetime.now():%Y%m%d}.log")


def _log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} - {msg}\n"
    try:
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass  # logging must never break the pipeline


def _cache_paths() -> tuple[str, str]:
    """Return (cache_file, index_file). Cache sits next to the target repo's
    stage ledger, so reruns after a crash resume for free."""
    root = os.getenv("GLM_CACHE_DIR", os.path.join(".glm_cache"))
    return os.path.join(root, "cache.json"), os.path.join(root, "index.json")


def _load_cache() -> dict:
    cache_file, _ = _cache_paths()
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    cache_file, index_file = _cache_paths()
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    tmp = cache_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, cache_file)  # atomic: a killed batch never corrupts the cache
    # human-readable index: hash -> {model, effort, prompt_head, saved_at, out_len}
    index = {}
    for k, v in cache.items():
        index[k] = {
            "model": v.get("model"),
            "effort": v.get("effort"),
            "prompt_head": v.get("prompt_head"),
            "saved_at": v.get("saved_at"),
            "out_len": len(v.get("text") or ""),
        }
    tmp2 = index_file + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    os.replace(tmp2, index_file)


def _cache_key(prompt: str, model: str, effort: str) -> str:
    raw = json.dumps([prompt, model, effort], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def call_glm(
    prompt: str,
    *,
    model: str | None = None,
    effort: str | None = None,
    use_cache: bool = True,
    max_tokens: int = MAX_TOKENS,
    retries: int = len(RETRY_DELAYS),
) -> str:
    """Call glm-5.3 once. Returns the assistant text. Raises on final failure."""
    model = model or os.getenv("GLM_MODEL", DEFAULT_MODEL)
    effort = effort or os.getenv("GLM_EFFORT", DEFAULT_EFFORT)

    key = _cache_key(prompt, model, effort)
    if use_cache:
        cache = _load_cache()
        hit = cache.get(key)
        if hit:
            _log(f"CACHE HIT {key[:12]} model={hit.get('model')} len={len(hit['text'])}")
            return hit["text"]

    api_key = os.getenv("ZAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ZAI_API_KEY is not set. GLM coding plan credentials are not "
            "configured on this machine — ask the user for the key."
        )

    url = f"{BASE_URL}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        # thinking cannot be disabled on glm-5.3; effort is the only lever.
        # docs: low | high | max (default max). Batch work -> low/high.
        "reasoning_effort": effort,
        "stream": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    delays = list(RETRY_DELAYS[:retries])
    attempt = 0
    while True:
        attempt += 1
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            _log(
                f"OK {key[:12]} model={model} effort={effort} "
                f"attempt={attempt} {time.time()-t0:.1f}s out_len={len(text)}"
            )
            if use_cache:
                cache = _load_cache()
                cache[key] = {
                    "text": text,
                    "model": model,
                    "effort": effort,
                    "prompt_head": prompt[:120].replace("\n", " "),
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                }
                _save_cache(cache)
            return text
        except urllib.error.HTTPError as e:
            status = e.code
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            if status in RETRY_STATUS and delays:
                wait = delays.pop(0)
                _log(f"RETRY {key[:12]} http={status} attempt={attempt} sleep={wait}s {detail}")
                time.sleep(wait)
                continue
            _log(f"FATAL {key[:12]} http={status} attempt={attempt} {detail}")
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            if delays:
                wait = delays.pop(0)
                _log(f"RETRY {key[:12]} err={type(e).__name__} attempt={attempt} sleep={wait}s")
                time.sleep(wait)
                continue
            _log(f"FATAL {key[:12]} err={type(e).__name__}: {e}")
            raise


# ---- batch runner -----------------------------------------------------------

def run_batch(jobs: list[tuple[str, str]], *, effort: str | None = None) -> dict[str, str]:
    """Sequential batch runner. jobs = [(name, prompt), ...] in dependency order.
    Cache hits skip the API, so a killed batch resumes where it stopped.
    Returns {name: response_text}. Raises the first fatal error after logging."""
    out: dict[str, str] = {}
    for i, (name, prompt) in enumerate(jobs, 1):
        _log(f"BATCH {i}/{len(jobs)} start: {name}")
        out[name] = call_glm(prompt, effort=effort)
        _log(f"BATCH {i}/{len(jobs)} done: {name} len={len(out[name])}")
    return out


def _cli() -> None:
    ap = argparse.ArgumentParser(description="GLM coding plan batch caller")
    ap.add_argument("--selftest", action="store_true", help="one tiny live call")
    ap.add_argument("--check-env", action="store_true", help="env diagnostics, no API call")
    args = ap.parse_args()

    if args.check_env:
        print(f"ZAI_API_KEY set: {bool(os.getenv('ZAI_API_KEY'))}")
        print(f"GLM_MODEL: {os.getenv('GLM_MODEL', DEFAULT_MODEL)}")
        print(f"GLM_EFFORT: {os.getenv('GLM_EFFORT', DEFAULT_EFFORT)}")
        print(f"endpoint: {BASE_URL}/chat/completions")
        cache_file, index_file = _cache_paths()
        print(f"cache: {os.path.abspath(cache_file)}")
        print(f"index: {os.path.abspath(index_file)}")
        return

    if args.selftest:
        text = call_glm(
            "Reply with exactly: repolens-glm-bridge-ok",
            effort="low",
            use_cache=False,
            max_tokens=256,
        )
        print("SELFTEST OK:", text[:200])
        return

    ap.print_help()


if __name__ == "__main__":
    _cli()
