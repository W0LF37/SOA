from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FEEDBACK_PATH = PROJECT_ROOT / "data" / "processed" / "task_feedback.json"

router = APIRouter()


class TaskFeedbackRequest(BaseModel):
    task_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


def _load_entries() -> list[dict[str, Any]]:
    if not FEEDBACK_PATH.exists():
        return []
    payload = json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        entries = payload.get("entries", [])
        return entries if isinstance(entries, list) else []
    return payload if isinstance(payload, list) else []


def _save_entries(entries: list[dict[str, Any]]) -> None:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_PATH.write_text(
        json.dumps({"entries": entries}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


@router.post("/task")
def save_task_feedback(body: TaskFeedbackRequest) -> dict[str, str]:
    entries = _load_entries()
    entries.append(
        {
            "task_id": body.task_id,
            "rating": body.rating,
            "comment": body.comment,
            "timestamp": datetime.now().isoformat(),
        }
    )
    _save_entries(entries)
    return {"status": "saved", "task_id": body.task_id}


@router.get("/summary")
def get_feedback_summary() -> dict[str, Any]:
    entries = _load_entries()
    ratings = [int(entry["rating"]) for entry in entries if isinstance(entry.get("rating"), int)]
    by_task: dict[str, dict[str, float | int]] = {}

    for entry in entries:
        task_id = str(entry.get("task_id", "")).strip()
        rating = entry.get("rating")
        if not task_id or not isinstance(rating, int):
            continue
        task_bucket = by_task.setdefault(task_id, {"total": 0, "count": 0})
        task_bucket["total"] = int(task_bucket["total"]) + rating
        task_bucket["count"] = int(task_bucket["count"]) + 1

    normalized_by_task = {
        task_id: {
            "avg": round(int(bucket["total"]) / max(int(bucket["count"]), 1), 2),
            "count": int(bucket["count"]),
        }
        for task_id, bucket in by_task.items()
    }

    average_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    return {
        "average_rating": average_rating,
        "total_ratings": len(ratings),
        "by_task": normalized_by_task,
    }
