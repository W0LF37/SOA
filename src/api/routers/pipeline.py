from __future__ import annotations

import asyncio
import json
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from src.api.routers.data import SUMMARY_PATH, TASKS_PATH, read_json
from src.core.runtime_paths import iter_readable_shared_input_paths, resolve_writable_shared_input_path
from src.pipelines.doc_to_tasks import run_doc_to_tasks_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMP_INPUT = resolve_writable_shared_input_path(PROJECT_ROOT)
DEFAULT_SAMPLE_INPUT = PROJECT_ROOT / "data" / "raw" / "docs" / "project_brief_sample.txt"

router = APIRouter()
_events: queue.Queue[dict[str, Any]] = queue.Queue()
_last_run: dict[str, Any] = {"status": "idle"}
_lock = threading.Lock()


def _clear_pending_events() -> None:
    while True:
        try:
            _events.get_nowait()
        except queue.Empty:
            return


def _load_pipeline_input() -> tuple[str, str]:
    for candidate in iter_readable_shared_input_paths(PROJECT_ROOT):
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8").strip()
            if text:
                return text, "latest_ui_input"

    if SUMMARY_PATH.exists():
        try:
            summary = read_json(SUMMARY_PATH)
            input_file = summary.get("input_file")
            if isinstance(input_file, str) and input_file.strip():
                candidate = Path(input_file)
                if not candidate.is_absolute():
                    candidate = PROJECT_ROOT / candidate
                if candidate.exists():
                    text = candidate.read_text(encoding="utf-8").strip()
                    if text:
                        return text, "last_pipeline_input"
        except Exception:
            pass

    if DEFAULT_SAMPLE_INPUT.exists():
        return DEFAULT_SAMPLE_INPUT.read_text(encoding="utf-8").strip(), "default_sample"

    return "", "empty"


class PipelineRunRequest(BaseModel):
    requirements: str = Field(..., min_length=1)
    input_format: Literal["brief", "template"] = "brief"
    use_kb: bool = True
    allow_fallback: bool = True


class _LogCapture:
    def __init__(self) -> None:
        self._old: object | None = None

    def __enter__(self) -> "_LogCapture":
        self._old = sys.stdout
        sys.stdout = self  # type: ignore[assignment]
        return self

    def write(self, text: str) -> None:
        if text.strip():
            _events.put({"type": "log", "message": text.rstrip()})
        if self._old:
            self._old.write(text)  # type: ignore[attr-defined]

    def flush(self) -> None:
        if self._old:
            self._old.flush()  # type: ignore[attr-defined]

    def isatty(self) -> bool:
        if self._old and hasattr(self._old, "isatty"):
            return bool(self._old.isatty())  # type: ignore[attr-defined]
        return False

    def __getattr__(self, name: str) -> Any:
        if self._old and hasattr(self._old, name):
            return getattr(self._old, name)
        raise AttributeError(name)

    def __exit__(self, *_args: object) -> None:
        sys.stdout = self._old  # type: ignore[assignment]


def _write_with_retry(path: Path, text: str, retries: int = 3) -> None:
    """Write text to path; retry on Windows PermissionError (transient file lock)."""
    for attempt in range(retries):
        try:
            path.write_text(text, encoding="utf-8")
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(0.3)


def _run_pipeline(payload: PipelineRunRequest) -> None:
    global _last_run
    started = time.perf_counter()
    with _lock:
        _last_run = {"status": "running", "started_at": time.time()}
    try:
        TEMP_INPUT.parent.mkdir(parents=True, exist_ok=True)
        _write_with_retry(TEMP_INPUT, payload.requirements.strip())
        _events.put({"type": "status", "message": "Pipeline started"})
        with _LogCapture():
            run_doc_to_tasks_pipeline(
                input_path=TEMP_INPUT,
                input_format=payload.input_format,
                force_fallback=False,
                allow_fallback=payload.allow_fallback,
                use_kb=payload.use_kb,
            )
        elapsed = round(time.perf_counter() - started, 2)
        tasks = read_json(TASKS_PATH)
        summary = read_json(SUMMARY_PATH)
        result = {
            "status": "completed",
            "elapsed_seconds": elapsed,
            "task_count": len(tasks.get("tasks", [])),
            "llm_used": summary.get("llm_used", False),
        }
        with _lock:
            _last_run = result
        _events.put({"type": "complete", "message": "Pipeline completed", "data": result})
    except Exception as exc:  # noqa: BLE001
        result = {"status": "failed", "error": str(exc)}
        with _lock:
            _last_run = result
        _events.put({"type": "error", "message": str(exc)})


@router.post("/run")
def run_pipeline(payload: PipelineRunRequest) -> dict[str, Any]:
    if _last_run.get("status") == "running":
        raise HTTPException(status_code=409, detail="Pipeline already running")
    _clear_pending_events()
    thread = threading.Thread(target=_run_pipeline, args=(payload,), daemon=True)
    thread.start()
    return {"status": "accepted"}


@router.get("/input")
def pipeline_input() -> dict[str, str]:
    text, source = _load_pipeline_input()
    return {"text": text, "source": source}


@router.get("/status")
def pipeline_status() -> dict[str, Any]:
    return dict(_last_run)


@router.get("/events")
async def pipeline_events() -> EventSourceResponse:
    async def generator():
        max_idle = 0
        while True:
            try:
                event = _events.get_nowait()
                yield {
                    "event": event.get("type", "message"),
                    "data": json.dumps(event, ensure_ascii=False),
                }
                max_idle = 0
                if event.get("type") in ("complete", "error"):
                    return
            except queue.Empty:
                status = _last_run.get("status", "idle")
                if status in ("completed", "failed") and max_idle >= 3:
                    return
                if status in ("completed", "failed"):
                    max_idle += 1
                yield {"event": "heartbeat", "data": json.dumps({"status": status})}
            await asyncio.sleep(1)

    return EventSourceResponse(generator())
