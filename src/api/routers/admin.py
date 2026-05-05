from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.runtime_paths import prepare_writable_file_path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
QUEUE_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/admin_review_queue.json")
TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks.json")
DECISIONS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/admin_review_decisions.json")
FINAL_TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks_final.json")
SUMMARY_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/plan_summary.json")

router = APIRouter()


class ReviewDecision(BaseModel):
    task_id: str
    action: Literal["approved", "edited", "rejected", "skipped"]
    new_title: str | None = None
    note: str | None = None


class ReviewSubmission(BaseModel):
    decisions: list[ReviewDecision]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/queue")
def get_queue() -> dict[str, Any]:
    if not QUEUE_PATH.exists():
        return {"items": [], "total": 0, "status": "no_pipeline_run"}

    queue = _load(QUEUE_PATH)
    items = queue.get("items", [])
    if not items:
        return {"items": [], "total": 0, "status": "empty"}

    tasks_by_id: dict[str, dict] = {}
    if not TASKS_PATH.exists():
        return {"items": [], "total": 0, "status": "no_pipeline_run"}
    if QUEUE_PATH.stat().st_mtime < TASKS_PATH.stat().st_mtime:
        return {"items": [], "total": 0, "status": "empty"}
    tasks_by_id = {
        t["id"]: t
        for t in _load(TASKS_PATH).get("tasks", [])
        if isinstance(t, dict) and t.get("id")
    }
    snapshot = queue.get("generated_for_task_ids")
    current_ids = sorted(tasks_by_id)
    if snapshot is None or sorted(str(task_id) for task_id in snapshot) != current_ids:
        return {"items": [], "total": 0, "status": "empty"}

    enriched = []
    for item in items:
        tid = item.get("task_id", "")
        task = tasks_by_id.get(tid, {})
        enriched.append({
            "task_id": tid,
            "title": task.get("title", item.get("title", "")),
            "source": task.get("source", item.get("source", "")),
            "confidence": task.get("confidence", item.get("confidence", "")),
            "optional": task.get("optional", item.get("optional", False)),
            "complexity": task.get("complexity", item.get("complexity", 1)),
            "req_type": task.get("req_type", item.get("req_type", "FR")),
            "description": task.get("description", item.get("description", "")),
            "reason": item.get("reason", ""),
            "dependencies": task.get("dependencies", []),
        })

    already_reviewed = DECISIONS_PATH.exists()
    return {
        "items": enriched,
        "total": len(enriched),
        "status": "reviewed" if already_reviewed else "pending",
    }


@router.post("/review")
def submit_review(body: ReviewSubmission) -> dict[str, Any]:
    if not TASKS_PATH.exists():
        raise HTTPException(status_code=404, detail="tasks.json not found — run pipeline first")

    decisions = [d.model_dump() for d in body.decisions]
    decisions_payload = {
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "decisions": decisions,
    }

    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISIONS_PATH.write_text(
        json.dumps(decisions_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    tasks_payload = _load(TASKS_PATH)
    all_tasks = tasks_payload.get("tasks", [])
    valid_task_ids = {
        str(task.get("id"))
        for task in all_tasks
        if isinstance(task, dict) and task.get("id")
    }
    unknown_ids = sorted({d["task_id"] for d in decisions} - valid_task_ids)
    if unknown_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task_id values: {', '.join(unknown_ids)}",
        )

    rejected_ids = {d["task_id"] for d in decisions if d["action"] == "rejected"}
    edited_titles = {
        d["task_id"]: d["new_title"]
        for d in decisions
        if d["action"] == "edited" and d.get("new_title")
    }

    kept: list[dict] = []
    for task in all_tasks:
        tid = task.get("id")
        if tid in rejected_ids:
            continue
        t = dict(task)
        if tid in edited_titles:
            t["title"] = edited_titles[tid]
        deps = t.get("dependencies", [])
        if isinstance(deps, list):
            t["dependencies"] = [dep for dep in deps if dep not in rejected_ids]
        kept.append(t)

    final_payload = dict(tasks_payload)
    final_payload["tasks"] = kept
    FINAL_TASKS_PATH.write_text(
        json.dumps(final_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    counts = {"approved": 0, "edited": 0, "rejected": 0, "skipped": 0}
    for d in decisions:
        if d["action"] in counts:
            counts[d["action"]] += 1

    if SUMMARY_PATH.exists():
        summary = _load(SUMMARY_PATH)
        queue_total = 0
        if QUEUE_PATH.exists():
            queue_total = _load(QUEUE_PATH).get("total", 0)
        summary["admin_review"] = {
            "status": "completed",
            "reviewed_at": decisions_payload["reviewed_at"],
            "total_flagged": queue_total,
            **counts,
            "tasks_final_file": "data/processed/tasks_final.json",
        }
        SUMMARY_PATH.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return {
        "status": "completed",
        "kept_tasks": len(kept),
        "rejected_tasks": len(rejected_ids),
        "counts": counts,
        "tasks_final_file": "data/processed/tasks_final.json",
    }
