from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from textwrap import fill

from src.core.runtime_paths import prepare_writable_file_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW_QUEUE_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/admin_review_queue.json")
DEFAULT_TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks.json")
DEFAULT_DECISIONS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/admin_review_decisions.json")
DEFAULT_FINAL_TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks_final.json")
DEFAULT_SUMMARY_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/plan_summary.json")


def finalize_tasks(decisions_path: Path, tasks_path: Path, output_path: Path) -> None:
    tasks_payload = _load_json(tasks_path)
    decisions_payload = _load_json(decisions_path)

    tasks = list(tasks_payload.get("tasks", []))
    decisions = list(decisions_payload.get("decisions", []))

    rejected_ids = {
        decision.get("task_id")
        for decision in decisions
        if decision.get("action") == "rejected" and decision.get("task_id")
    }
    edited_titles = {
        decision.get("task_id"): decision.get("new_title")
        for decision in decisions
        if decision.get("action") == "edited"
        and decision.get("task_id")
        and decision.get("new_title")
    }

    kept_tasks: list[dict] = []
    for task in tasks:
        task_id = task.get("id")
        if task_id in rejected_ids:
            continue
        updated_task = dict(task)
        if task_id in edited_titles:
            updated_task["title"] = edited_titles[task_id]
        dependencies = updated_task.get("dependencies", [])
        if isinstance(dependencies, list):
            updated_task["dependencies"] = [
                dep for dep in dependencies if dep not in rejected_ids
            ]
        kept_tasks.append(updated_task)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_payload = dict(tasks_payload)
    final_payload["tasks"] = kept_tasks
    output_path.write_text(
        json.dumps(final_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"tasks_final.json written: {len(kept_tasks)} tasks kept, {len(rejected_ids)} rejected."
    )

    if DEFAULT_SUMMARY_PATH.exists():
        summary_payload = _load_json(DEFAULT_SUMMARY_PATH)
        queue_payload = (
            _load_json(DEFAULT_REVIEW_QUEUE_PATH)
            if DEFAULT_REVIEW_QUEUE_PATH.exists()
            else {"total": 0}
        )
        decision_counts = {
            "approved": 0,
            "edited": 0,
            "rejected": 0,
            "skipped": 0,
        }
        for decision in decisions:
            action = decision.get("action")
            if action in decision_counts:
                decision_counts[action] += 1

        summary_payload["admin_review"] = {
            "status": "completed",
            "reviewed_at": decisions_payload.get("reviewed_at"),
            "total_flagged": queue_payload.get("total", 0),
            "approved": decision_counts["approved"],
            "edited": decision_counts["edited"],
            "rejected": decision_counts["rejected"],
            "skipped": decision_counts["skipped"],
            "tasks_final_file": "data/processed/tasks_final.json",
        }
        DEFAULT_SUMMARY_PATH.write_text(
            json.dumps(summary_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _format_description(text: str) -> str:
    wrapped = fill(text.strip(), width=70) if text.strip() else ""
    if not wrapped:
        return "Description:"
    lines = wrapped.splitlines()
    rendered = [f"Description: {lines[0]}"]
    rendered.extend(f"             {line}" for line in lines[1:])
    return "\n".join(rendered)


def _prompt_action() -> str:
    print("[A] Approve   [E] Edit title   [R] Reject   [S] Skip")
    first = input("Action: ").strip().lower()
    if first in {"a", "e", "r", "s"}:
        return first
    second = input("Action: ").strip().lower()
    if second in {"a", "e", "r", "s"}:
        return second
    return "s"


def _prompt_new_title() -> str | None:
    first = input("New title: ").strip()
    if first:
        return first
    second = input("New title: ").strip()
    if second:
        return second
    return None


def main() -> None:
    if not DEFAULT_REVIEW_QUEUE_PATH.exists():
        print("No review queue found. Run the pipeline first.")
        return

    queue_payload = _load_json(DEFAULT_REVIEW_QUEUE_PATH)
    tasks_payload = _load_json(DEFAULT_TASKS_PATH) if DEFAULT_TASKS_PATH.exists() else {"tasks": []}
    queue_items = queue_payload.get("items", [])

    if not queue_items:
        print("No tasks require review. All tasks are confirmed.")
        return

    tasks_by_id = {
        task.get("id"): task
        for task in tasks_payload.get("tasks", [])
        if isinstance(task, dict) and task.get("id")
    }
    decisions: list[dict] = []
    approved = edited = rejected = skipped = 0

    for item in queue_items:
        task_id = item.get("task_id", "")
        task_data = tasks_by_id.get(task_id, {})
        title = task_data.get("title", item.get("title", ""))
        description = task_data.get("description", item.get("description", ""))
        source = task_data.get("source", item.get("source", ""))
        confidence = task_data.get("confidence", item.get("confidence", ""))
        optional = task_data.get("optional", item.get("optional", False))
        reason = item.get("reason", "")

        print("=" * 60)
        print(f"Task ID: {task_id}")
        print(f"Title: {title}")
        print(f"Source: {source}")
        print(f"Confidence: {confidence} | Optional: {optional}")
        print(f"Reason: {reason}")
        print(_format_description(description))

        action = _prompt_action()
        decision = {
            "task_id": task_id,
            "action": "skipped",
            "new_title": None,
        }

        if action == "a":
            decision["action"] = "approved"
            approved += 1
        elif action == "e":
            new_title = _prompt_new_title()
            if new_title:
                decision["action"] = "edited"
                decision["new_title"] = new_title
                edited += 1
            else:
                skipped += 1
        elif action == "r":
            decision["action"] = "rejected"
            rejected += 1
        else:
            skipped += 1

        decisions.append(decision)

    print("=" * 60)
    print(
        f"Review complete: {approved} approved | {edited} edited | "
        f"{rejected} rejected | {skipped} skipped"
    )

    DEFAULT_DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_DECISIONS_PATH.write_text(
        json.dumps(
            {
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "decisions": decisions,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    finalize_tasks(
        decisions_path=DEFAULT_DECISIONS_PATH,
        tasks_path=DEFAULT_TASKS_PATH,
        output_path=DEFAULT_FINAL_TASKS_PATH,
    )


if __name__ == "__main__":
    main()
