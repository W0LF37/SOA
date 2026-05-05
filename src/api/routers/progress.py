from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from src.core.runtime_paths import prepare_writable_file_path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROGRESS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/task_progress.json")
TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks.json")
FINAL_TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks_final.json")

router = APIRouter()


class ProgressUpdateRequest(BaseModel):
    task_id: str
    status: Literal["not_started", "in_progress", "completed"]


def _load_progress_map() -> dict[str, dict[str, str]]:
    if not PROGRESS_PATH.exists():
        return {}
    payload = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("by_task"), dict):
        return payload["by_task"]
    return {}


def _save_progress_map(by_task: dict[str, dict[str, str]]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(
        json.dumps({"by_task": by_task}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_tasks() -> list[dict[str, Any]]:
    tasks_path = FINAL_TASKS_PATH if FINAL_TASKS_PATH.exists() else TASKS_PATH
    if not tasks_path.exists():
        return []
    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    return tasks if isinstance(tasks, list) else []


@router.post("/update")
def update_task_progress(body: ProgressUpdateRequest) -> dict[str, str]:
    by_task = _load_progress_map()
    updated_at = datetime.now().isoformat()
    by_task[body.task_id] = {"status": body.status, "updated_at": updated_at}
    _save_progress_map(by_task)
    return {
        "task_id": body.task_id,
        "status": body.status,
        "updated_at": updated_at,
    }


@router.get("/summary")
def get_progress_summary() -> dict[str, Any]:
    tasks = _load_tasks()
    by_task = _load_progress_map()
    task_ids = [str(task.get("id", "")).strip() for task in tasks if task.get("id")]

    merged_by_task: dict[str, dict[str, str]] = {}
    completed = 0
    in_progress = 0
    not_started = 0

    for task_id in task_ids:
        item = by_task.get(task_id, {"status": "not_started", "updated_at": ""})
        status = item.get("status", "not_started")
        if status == "completed":
            completed += 1
        elif status == "in_progress":
            in_progress += 1
        else:
            not_started += 1
            status = "not_started"
        merged_by_task[task_id] = {
            "status": status,
            "updated_at": item.get("updated_at", ""),
        }

    total = len(task_ids)
    percentage = round((completed / total) * 100, 2) if total else 0.0
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
        "percentage": percentage,
        "by_task": merged_by_task,
    }
