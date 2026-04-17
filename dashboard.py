"""
Interactive Dashboard Server
Users can paste bug reports, upload logs, run the pipeline live,
and watch agents execute in real-time via Server-Sent Events.
"""

import asyncio
import json
import os
import sys
import time
import uuid
import webbrowser
from pathlib import Path
from threading import Thread, Timer
from queue import Queue

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="Bug Investigation Dashboard")

STATIC_DIR = PROJECT_ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Global state for active pipeline runs ──
pipeline_jobs = {}


class PipelineJob:
    def __init__(self, job_id: str, bug_text: str, log_text: str, repo_code: str = ""):
        self.job_id = job_id
        self.bug_text = bug_text
        self.log_text = log_text
        self.repo_code = repo_code
        self.events = Queue()
        self.status = "pending"
        self.report = None
        self.error = None


def _load_text(path: str) -> str:
    p = PROJECT_ROOT / path
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def _load_json(path: str) -> dict:
    p = PROJECT_ROOT / path
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


# ── API Endpoints ──

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/sample-bug-report")
def sample_bug_report():
    return JSONResponse({"content": _load_text("inputs/bug_report.md")})


@app.get("/api/sample-logs")
def sample_logs():
    return JSONResponse({"content": _load_text("inputs/logs/app.log")})


@app.get("/api/sample-code")
def sample_code():
    return JSONResponse({"content": _load_text("src/services/payment_service.py")})


@app.get("/api/report")
def api_report():
    return JSONResponse(_load_json("output/investigation_report.json"))


@app.get("/api/repro")
def api_repro():
    return JSONResponse({"content": _load_text("repro/repro_test.py")})


@app.get("/api/trace")
def api_trace():
    lines = _load_text("logs/agent_trace.log").strip().split("\n")
    entries = []
    for line in lines:
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return JSONResponse(entries)


@app.get("/api/llm-status")
def llm_status():
    """Return the current LLM connection status."""
    from utils.llm_client import get_llm_client
    llm = get_llm_client()
    return JSONResponse(llm.status)


@app.post("/api/run")
async def run_pipeline(request: Request):
    """Start a new pipeline run."""
    body = await request.json()
    bug_text = body.get("bug_report", "")
    log_text = body.get("log_content", "")
    repo_code = body.get("repo_code", "")

    if not bug_text.strip():
        return JSONResponse({"error": "Bug report is required"}, status_code=400)
    if not log_text.strip():
        return JSONResponse({"error": "Log content is required"}, status_code=400)

    job_id = str(uuid.uuid4())[:8]
    job = PipelineJob(job_id, bug_text, log_text, repo_code)
    pipeline_jobs[job_id] = job

    thread = Thread(target=_run_pipeline_thread, args=(job,), daemon=True)
    thread.start()

    return JSONResponse({"job_id": job_id})


@app.get("/api/stream/{job_id}")
async def stream_events(job_id: str):
    """SSE endpoint to stream pipeline progress."""
    job = pipeline_jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    async def event_generator():
        while True:
            if not job.events.empty():
                event = job.events.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "complete" or event.get("type") == "error":
                    break
            else:
                await asyncio.sleep(0.1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _run_pipeline_thread(job: PipelineJob):
    """Execute the pipeline in a background thread, emitting events."""
    import logging
    # Suppress pipeline logs going to console during web runs
    logging.getLogger("pipeline").handlers.clear()

    try:
        job.status = "running"
        job.events.put({"type": "started", "message": "Pipeline starting..."})

        # Emit event for each stage
        from models.bug_report import BugReport
        from config import Config
        Config.ensure_directories()

        bug_report = BugReport.from_markdown(job.bug_text)
        job.events.put({
            "type": "parsed",
            "message": f"Parsed: {bug_report.title}",
            "severity": bug_report.severity.value,
        })

        # If user provided repo code, write it to a temp source dir
        if job.repo_code.strip():
            import tempfile, shutil
            user_src = PROJECT_ROOT / "user_src"
            user_src.mkdir(exist_ok=True)
            # Write each code block separated by "--- filename.py ---"
            import re
            blocks = re.split(r'---\s*(\S+\.py)\s*---', job.repo_code)
            if len(blocks) >= 3:
                for i in range(1, len(blocks), 2):
                    fname = blocks[i]
                    content = blocks[i + 1] if i + 1 < len(blocks) else ""
                    fpath = user_src / fname
                    fpath.parent.mkdir(parents=True, exist_ok=True)
                    fpath.write_text(content.strip(), encoding="utf-8")
            else:
                # Single file — write as service.py
                (user_src / "user_code.py").write_text(job.repo_code, encoding="utf-8")
            Config.SRC_DIR = user_src

        agents_info = [
            ("triage_agent", "Triage Agent", "Parsing bug report, generating hypotheses..."),
            ("log_analyst_agent", "Log Analyst Agent", "Extracting stack traces, error patterns, deploy correlations..."),
            ("repo_navigator_agent", "Repo Navigator Agent", "Mapping codebase, tracing dependency chain..."),
            ("reproduction_agent", "Reproduction Agent", "Generating repro test, executing pytest..."),
            ("fix_planner_agent", "Fix Planner Agent", "Synthesizing evidence, planning the fix..."),
            ("reviewer_agent", "Reviewer Agent", "Challenging findings, scoring quality..."),
            ("communication_agent", "Communication Agent", "Notifying team, scheduling post-mortem..."),
        ]

        # Import and run the actual pipeline
        from orchestrator import Pipeline
        pipeline = Pipeline()

        # Monkey-patch _run_stage to emit events
        original_run_stage = pipeline._run_stage

        current_stage_idx = [0]

        def patched_run_stage(stage_num, stage_name, stage_fn):
            idx = current_stage_idx[0]
            agent_id, agent_name, desc = agents_info[idx]
            job.events.put({
                "type": "agent_start",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "stage": stage_num,
                "message": desc,
            })

            start = time.time()
            original_run_stage(stage_num, stage_name, stage_fn)
            duration = int((time.time() - start) * 1000)

            job.events.put({
                "type": "agent_complete",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "stage": stage_num,
                "duration_ms": duration,
                "message": f"{agent_name} completed in {duration}ms",
            })
            current_stage_idx[0] += 1

        pipeline._run_stage = patched_run_stage
        report = pipeline.run(bug_report=bug_report, log_content=job.log_text)

        job.report = report
        job.status = "complete"

        report_dict = _load_json("output/investigation_report.json")
        repro_content = _load_text("repro/repro_test.py")

        job.events.put({
            "type": "complete",
            "message": "Investigation complete!",
            "confidence": report.confidence_score,
            "report": report_dict,
            "repro": repro_content,
        })

    except Exception as e:
        job.status = "error"
        job.error = str(e)
        import traceback
        job.events.put({
            "type": "error",
            "message": f"Pipeline failed: {e}",
            "traceback": traceback.format_exc(),
        })


def open_browser():
    webbrowser.open("http://localhost:8050")


if __name__ == "__main__":
    Timer(1.5, open_browser).start()
    print("\n  Interactive Dashboard at http://localhost:8050\n")
    uvicorn.run(app, host="0.0.0.0", port=8050, log_level="warning")
