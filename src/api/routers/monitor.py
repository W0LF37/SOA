from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.agents.monitor import MonitorAgent
from src.core.schemas import TaskList
from src.core.runtime_paths import prepare_writable_file_path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks.json")
MONITOR_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/monitor_report.json")
DEFAULT_DEMO_REPO = PROJECT_ROOT / "case_study"

router = APIRouter()


class MonitorRequest(BaseModel):
    repo_path: str | None = None
    use_semantic: bool = True


@router.post("/analyze")
def analyze(payload: MonitorRequest) -> dict[str, Any]:
    try:
        if not TASKS_PATH.exists():
            raise HTTPException(status_code=404, detail="tasks.json not found — run pipeline first")
        try:
            tasks_data = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"tasks.json is malformed: {exc}") from exc

        repo_path = None
        if payload.repo_path:
            candidate = Path(payload.repo_path)
            if not candidate.exists():
                raise HTTPException(status_code=400, detail=f"Repository path does not exist: {payload.repo_path}")
            repo_path = str(candidate)
        elif (DEFAULT_DEMO_REPO / ".git").exists():
            repo_path = str(DEFAULT_DEMO_REPO)
        task_list = TaskList.model_validate(tasks_data)
        report = MonitorAgent(use_semantic=payload.use_semantic).track_progress(
            task_list,
            repo_path=repo_path,
        )
        MONITOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        MONITOR_PATH.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
