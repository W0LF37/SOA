from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_report.json"
ABLATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "ablation_report.json"

router = APIRouter()

_eval_running = False


def _run_evaluation_bg() -> None:
    global _eval_running
    try:
        from src.pipelines.evaluate import run_evaluation  # type: ignore[import]
        run_evaluation()
    finally:
        _eval_running = False


@router.get("/results")
def get_results() -> dict[str, Any]:
    if not REPORT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No evaluation report found. Run /evaluate/run first.",
        )
    data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    ablation: dict | None = None
    if ABLATION_PATH.exists():
        try:
            ablation = json.loads(ABLATION_PATH.read_text(encoding="utf-8"))
        except Exception:
            ablation = None
    return {"report": data, "ablation": ablation, "running": _eval_running}


@router.post("/run")
def run_evaluation_endpoint(background_tasks: BackgroundTasks) -> dict[str, str]:
    global _eval_running
    if _eval_running:
        return {"status": "already_running", "message": "Evaluation is already in progress"}
    _eval_running = True
    background_tasks.add_task(_run_evaluation_bg)
    return {"status": "started", "message": "Evaluation started in background. Poll /evaluate/results to check."}
