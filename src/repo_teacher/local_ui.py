from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .persistence import read_json_path
from .pipeline.performance import build_pipeline_performance


MODEL_OPTIONS = {
    "deepseek-flash": "openrouter/deepseek/deepseek-v4-flash",
    "deepseek-pro": "openrouter/deepseek/deepseek-v4-pro",
}


def _safe_report_name(value: object) -> str:
    name = str(value or "").strip()
    if not name or len(name) > 100:
        raise ValueError("报告名称必须为 1–100 个字符")
    if name in {".", ".."} or any(character in name for character in ("/", "\\", "\0")):
        raise ValueError("报告名称不能包含路径分隔符")
    if not all(character.isalnum() or character in {"-", "_", "."} for character in name):
        raise ValueError("报告名称只能使用中英文、数字、点、下划线或连字符")
    return name


def validate_job_request(payload: dict[str, Any]) -> dict[str, Any]:
    source = Path(str(payload.get("source") or "")).expanduser().resolve()
    if not source.is_dir():
        raise ValueError("源码仓库目录不存在")
    output_root = Path(str(payload.get("output_root") or "")).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if not output_root.is_dir():
        raise ValueError("输出根目录不可用")
    name = _safe_report_name(payload.get("name"))
    backend = str(payload.get("backend") or "codex")
    if backend not in {"codex", "opencode"}:
        raise ValueError("执行后端只能是 codex 或 opencode")
    model_key = str(payload.get("model") or "deepseek-flash")
    if model_key not in MODEL_OPTIONS:
        raise ValueError("OpenCode 模型只能选择 DeepSeek Flash 或 Pro")
    timeout = payload.get("model_timeout", 3600)
    if not isinstance(timeout, int) or timeout < 60 or timeout > 86_400:
        raise ValueError("模型超时必须在 60–86400 秒之间")
    output = (output_root / name).resolve()
    try:
        output.relative_to(output_root)
    except ValueError as error:
        raise ValueError("输出目录越过了输出根目录") from error
    return {
        "source": source,
        "output": output,
        "output_root": output_root,
        "name": name,
        "backend": backend,
        "model": model_key,
        "model_timeout": timeout,
    }


def build_report_command(config: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "repo_teacher",
        "report",
        str(config["source"]),
        "--output",
        str(config["output"]),
        "--provider",
        str(config["backend"]),
        "--model-timeout",
        str(config["model_timeout"]),
    ]


def progress_from_line(line: str, current: int) -> int:
    phases = {
        "[report 01/05]": 8,
        "[report 02/05]": 28,
        "[report 03/05]": 58,
        "[report 04/05]": 84,
        "[report 05/05]": 96,
    }
    progress = current
    for prefix, value in phases.items():
        if line.startswith(prefix):
            progress = max(progress, value)
            break
    for marker in ("业务域功能目录完成", "模块分片目录完成"):
        if marker not in line:
            continue
        tail = line.split(marker, 1)[1].strip().split("/", 1)
        if len(tail) == 2 and tail[0].isdigit() and tail[1].isdigit() and int(tail[1]):
            progress = max(progress, 42 + int(30 * int(tail[0]) / int(tail[1])))
        break
    return min(progress, 99)


@dataclass
class ReportJob:
    identifier: str
    config: dict[str, Any]
    status: str = "queued"
    progress: int = 0
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    report_uri: str | None = None
    return_code: int | None = None

    def public(self) -> dict[str, Any]:
        performance: dict[str, object] | None = None
        output = self.config.get("output")
        if isinstance(output, Path):
            performance_path = output.with_name(f"{output.name}.performance.json")
            if performance_path.is_file():
                try:
                    performance = read_json_path(performance_path)
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    performance = None
            linear_performance_path = output.with_name(
                f".{output.name}.pipeline"
            ) / "performance.json"
            if linear_performance_path.is_file():
                try:
                    linear = read_json_path(linear_performance_path)
                    performance = {
                        **linear,
                        "wall_duration_seconds": linear.get(
                            "total_recorded_wall_seconds", 0
                        ),
                        "longest_stage": (
                            {
                                "id": linear.get("longest_stage"),
                                "duration_seconds": linear.get(
                                    "longest_stage_seconds", 0
                                ),
                            }
                            if linear.get("longest_stage")
                            else None
                        ),
                    }
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    performance = None
            if performance is None:
                journal_path = output.with_name(f"{output.name}.run-manifest.json")
                if journal_path.is_file():
                    try:
                        performance = build_pipeline_performance(
                            read_json_path(journal_path)
                        )
                    except (
                        OSError,
                        UnicodeDecodeError,
                        json.JSONDecodeError,
                        ValueError,
                    ):
                        performance = None
        return {
            "id": self.identifier,
            "status": self.status,
            "progress": self.progress,
            "logs": self.logs[-300:],
            "error": self.error,
            "report_uri": self.report_uri,
            "output": str(self.config["output"]),
            "backend": self.config["backend"],
            "model": self.config["model"] if self.config["backend"] == "opencode" else None,
            "return_code": self.return_code,
            "performance": performance,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, ReportJob] = {}
        self._lock = threading.Lock()

    def start(self, payload: dict[str, Any], api_key: str) -> ReportJob:
        config = validate_job_request(payload)
        identifier = secrets.token_hex(8)
        job = ReportJob(identifier=identifier, config=config)
        with self._lock:
            if any(item.status in {"queued", "running"} for item in self._jobs.values()):
                raise ValueError("当前已有报告正在生成；完成后再启动下一项")
            self._jobs[identifier] = job
        thread = threading.Thread(
            target=self._run,
            args=(job, api_key),
            name=f"repo-teacher-{identifier}",
            daemon=True,
        )
        thread.start()
        return job

    def get(self, identifier: str) -> ReportJob | None:
        with self._lock:
            return self._jobs.get(identifier)

    def _run(self, job: ReportJob, api_key: str) -> None:
        job.status = "running"
        job.progress = 2
        environment = os.environ.copy()
        if job.config["backend"] == "opencode":
            environment["REPO_TEACHER_OPENCODE_MODEL"] = MODEL_OPTIONS[job.config["model"]]
            if api_key:
                environment["OPENROUTER_API_KEY"] = api_key
            elif not environment.get("OPENROUTER_API_KEY"):
                job.status = "failed"
                job.error = "OpenCode 需要在界面输入 OpenRouter Key，或预先设置 OPENROUTER_API_KEY"
                job.return_code = 2
                return
        command = build_report_command(job.config)
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=environment,
            )
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.rstrip()
                if api_key:
                    line = line.replace(api_key, "[REDACTED]")
                job.logs.append(line)
                job.progress = progress_from_line(line, job.progress)
            job.return_code = process.wait()
        except OSError as error:
            job.status = "failed"
            job.error = str(error)
            job.return_code = 1
            return
        if job.return_code != 0:
            job.status = "failed"
            job.error = job.logs[-1] if job.logs else "报告生成失败"
            return
        report = Path(job.config["output"]) / "index.html"
        if not report.is_file():
            job.status = "failed"
            job.error = "命令完成但没有生成 index.html"
            return
        job.status = "completed"
        job.progress = 100
        job.report_uri = report.as_uri()


_UI_HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repo Teacher · 本地报告生成器</title><style>
:root{--paper:#fffef9;--bg:#efede5;--ink:#172019;--muted:#68716a;--line:#d7dcd5;--green:#0b6b4c;--soft:#e6f3ed;--orange:#dd5d29}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}.shell{width:min(1040px,100%);min-height:100vh;margin:auto;padding:46px;background:var(--paper)}header span{color:var(--orange);font:800 12px/1 ui-monospace,monospace;letter-spacing:.1em}h1{max-width:760px;margin:14px 0 10px;font-size:clamp(2.3rem,6vw,4.6rem);line-height:1.04;letter-spacing:-.05em}header p{max-width:760px;color:var(--muted);font-size:1.08rem}.layout{display:grid;grid-template-columns:1.05fr .95fr;gap:18px;margin-top:34px}.panel{padding:24px;border:1px solid var(--line);border-radius:20px;background:#fff}.panel h2{margin:0 0 18px;font-size:1.2rem}.field{display:grid;gap:7px;margin:14px 0}.field label{font-weight:750}.field small{color:var(--muted)}input,select,button{width:100%;min-height:46px;border:1px solid var(--line);border-radius:11px;background:#fff;color:var(--ink);font:inherit}input,select{padding:0 12px}button{margin-top:12px;border-color:var(--green);background:var(--green);color:#fff;font-weight:850;cursor:pointer}button:disabled{opacity:.5;cursor:wait}.provider-note{padding:13px;border-radius:10px;background:var(--soft);color:var(--green)}.status{display:flex;justify-content:space-between;gap:12px}.bar{height:12px;margin:14px 0 20px;border-radius:99px;background:#e8ebe7;overflow:hidden}.bar i{display:block;width:0;height:100%;background:var(--green);transition:width .25s}.logs{height:430px;overflow:auto;margin:0;padding:15px;border-radius:12px;background:#172019;color:#d9e4dd;white-space:pre-wrap;font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}.result{display:none;margin-top:15px;padding:14px;border-radius:12px;background:var(--soft)}.result a{color:var(--green);font-weight:850}.error{color:#a33020}@media(max-width:760px){.shell{padding:24px 15px}.layout{grid-template-columns:1fr}.logs{height:280px}}
</style></head><body><main class="shell"><header><span>REPO / TEACHER · LOCAL</span><h1>把陌生仓库变成人能读懂的项目报告。</h1><p>先识别业务功能，再解释跨模块实现、工程结构、技术难点和源码证据。API Key 只进入本次子进程环境，不写入命令、日志或配置文件。</p></header><section class="layout"><form class="panel" id="form"><h2>生成参数</h2>
<div class="field"><label for="source">源码仓库</label><input id="source" required placeholder="/Volumes/T7/.../repository"><small>必须是本机已存在的仓库目录。</small></div>
<div class="field"><label for="output">HTML 输出根目录</label><input id="output" required value="/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects"></div>
<div class="field"><label for="name">报告名称</label><input id="name" required placeholder="pipecat"><small>最终生成到 输出根目录/报告名称/index.html。</small></div>
<div class="field"><label for="backend">执行后端</label><select id="backend"><option value="codex">Codex（使用本机 Codex 会话）</option><option value="opencode">OpenCode + OpenRouter</option></select></div>
<div id="opencode" hidden><div class="field"><label for="model">模型</label><select id="model"><option value="deepseek-flash">DeepSeek Flash（更快）</option><option value="deepseek-pro">DeepSeek Pro（更深）</option></select></div>
<div class="field"><label for="key">OpenRouter API Key</label><input id="key" type="password" autocomplete="off" placeholder="未填写时读取 OPENROUTER_API_KEY"><small>不会保存在浏览器 localStorage 或服务端文件。</small></div></div>
<div class="field"><label for="timeout">模型总超时（秒）</label><input id="timeout" type="number" min="60" max="86400" value="3600"></div>
<p class="provider-note">报告顺序固定为：项目定位 → 产品主轴 → 业务功能 → 实现机制 → 难点与取舍 → 工程结构 → 源码证据。</p><button id="start">开始生成报告</button></form>
<section class="panel"><div class="status"><h2>实时进度</h2><strong id="percent">0%</strong></div><div class="bar"><i id="bar"></i></div><p class="provider-note" id="timing">阶段耗时：等待任务…</p><pre class="logs" id="logs">等待任务…</pre><div class="result" id="result"></div></section></section></main>
<script>
const form=document.querySelector('#form'),backend=document.querySelector('#backend'),opencode=document.querySelector('#opencode'),start=document.querySelector('#start'),logs=document.querySelector('#logs'),bar=document.querySelector('#bar'),percent=document.querySelector('#percent'),timing=document.querySelector('#timing'),result=document.querySelector('#result');backend.addEventListener('change',()=>opencode.hidden=backend.value!=='opencode');document.querySelector('#source').addEventListener('input',event=>{const value=event.target.value.replace(/[\\/]+$/,'').split(/[\\/]/).pop();if(value&&!document.querySelector('#name').value)document.querySelector('#name').value=value});let timer=null;function timingText(performance){if(!performance)return '阶段耗时：正在建立运行账本…';const seconds=Number(performance.wall_duration_seconds||0).toFixed(1),current=performance.current_stage||'已完成',longest=performance.longest_stage;return `阶段耗时：${current} · 总墙钟 ${seconds}s${longest?` · 最慢 ${longest.id} ${Number(longest.duration_seconds||0).toFixed(1)}s`:''}`}async function poll(id){const response=await fetch(`/api/jobs/${id}`),job=await response.json();bar.style.width=`${job.progress}%`;percent.textContent=`${job.progress}%`;timing.textContent=timingText(job.performance);logs.textContent=(job.logs||[]).join('\n')||'任务已启动…';logs.scrollTop=logs.scrollHeight;if(job.status==='completed'){clearInterval(timer);start.disabled=false;result.style.display='block';result.innerHTML=`完成：<a href="${job.report_uri}">打开 index.html</a><br><small>${job.output}</small>`}else if(job.status==='failed'){clearInterval(timer);start.disabled=false;result.style.display='block';result.className='result error';result.textContent=job.error||'生成失败'}}form.addEventListener('submit',async event=>{event.preventDefault();start.disabled=true;result.style.display='none';logs.textContent='提交任务…';const payload={source:document.querySelector('#source').value,output_root:document.querySelector('#output').value,name:document.querySelector('#name').value,backend:backend.value,model:document.querySelector('#model').value,api_key:document.querySelector('#key').value,model_timeout:Number(document.querySelector('#timeout').value)};const response=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)}),data=await response.json();document.querySelector('#key').value='';if(!response.ok){start.disabled=false;result.style.display='block';result.className='result error';result.textContent=data.error||'无法启动任务';return}timer=setInterval(()=>poll(data.id),1000);poll(data.id)});
</script></body></html>"""


def run_local_ui(host: str, port: int, should_open: bool) -> int:
    manager = JobManager()

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                body = _UI_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.send_header("cache-control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if path.startswith("/api/jobs/"):
                job = manager.get(path.rsplit("/", 1)[-1])
                if job is None:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "任务不存在"})
                else:
                    self._json(HTTPStatus.OK, job.public())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "页面不存在"})

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/jobs":
                self._json(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                return
            try:
                length = int(self.headers.get("content-length", "0"))
                if length < 2 or length > 64_000:
                    raise ValueError("请求体大小不合法")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("请求必须是 JSON object")
                api_key = str(payload.pop("api_key", ""))
                job = manager.start(payload, api_key)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._json(HTTPStatus.ACCEPTED, {"id": job.identifier})

        def log_message(self, format: str, *args: object) -> None:
            return

    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as error:
        print(f"error: could not start local UI: {error}", file=sys.stderr)
        return 1
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{display_host}:{server.server_port}/"
    print(f"Repo Teacher local UI: {url}")
    print("API keys are kept in memory for the child process only. Press Ctrl-C to stop.")
    if should_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLocal UI stopped.")
    finally:
        server.server_close()
    return 0
