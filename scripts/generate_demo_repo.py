from __future__ import annotations

import json
import os
import re
import shutil
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dulwich import porcelain


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_PATH = PROJECT_ROOT / "case_study"
TASKS_PATH = PROJECT_ROOT / "data" / "processed" / "tasks.json"

AUTHORS = [
    ("Maya Haddad", "maya@example.com"),
    ("Omar Saleh", "omar@example.com"),
    ("Lina Nasser", "lina@example.com"),
]

STOP_WORDS = {
    "implement",
    "enable",
    "enforce",
    "optimize",
    "workflow",
    "support",
    "controls",
    "system",
    "process",
    "online",
    "creation",
    "available",
    "course",
    "should",
    "maintain",
    "under",
    "friendly",
}

SKILL_FOLDERS = {
    "backend": Path("src/backend"),
    "platform": Path("src/platform"),
    "security": Path("src/security"),
}

COMPLETED_MESSAGES = [
    "scaffold core flow",
    "integrate validation and persistence",
    "completed end to end",
]
IN_PROGRESS_MESSAGE = "draft integration slice"


def safe_reset_repo() -> None:
    resolved = REPO_PATH.resolve()
    root = PROJECT_ROOT.resolve()
    if resolved == root or root not in resolved.parents:
        raise RuntimeError(f"Refusing to reset unsafe path: {resolved}")

    if REPO_PATH.exists():
        def clear_readonly(function, path, _excinfo) -> None:  # noqa: ANN001
            os.chmod(path, stat.S_IWRITE)
            function(path)

        shutil.rmtree(REPO_PATH, onexc=clear_readonly)

    for relative in ("src/backend", "src/platform", "src/security", "tests", "docs"):
        (REPO_PATH / relative).mkdir(parents=True, exist_ok=True)

    porcelain.init(str(REPO_PATH))


def load_tasks() -> list[dict]:
    if not TASKS_PATH.exists():
        raise RuntimeError(f"Tasks file not found: {TASKS_PATH}")
    payload = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    if not tasks:
        raise RuntimeError("tasks.json has no tasks. Run the pipeline first.")
    return tasks


def task_keywords(task: dict) -> list[str]:
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()
    words = re.findall(r"[a-z0-9]+", text)
    filtered: list[str] = []
    for word in words:
        if len(word) <= 2 or word in STOP_WORDS:
            continue
        if word not in filtered:
            filtered.append(word)
    return filtered[:6] or [str(task.get("id", "task")).lower()]


def task_slug(task: dict) -> str:
    return "_".join(task_keywords(task)[:4])


def task_topic(task: dict) -> str:
    return " ".join(task_keywords(task)[:3])


def build_status_plan(tasks: list[dict]) -> dict[str, str]:
    roots = [task for task in tasks if not task.get("dependencies")]
    dependents = [task for task in tasks if task.get("dependencies")]
    plan: dict[str, str] = {}

    if roots:
        root_completed = max(1, len(roots) // 2)
        for index, task in enumerate(roots):
            plan[task["id"]] = "completed" if index < root_completed else "in_progress"

    if dependents:
        dependent_completed = max(1, len(dependents) // 2)
        for index, task in enumerate(dependents):
            if index < dependent_completed:
                plan[task["id"]] = "completed"
            elif index == dependent_completed:
                plan[task["id"]] = "in_progress"
            else:
                plan[task["id"]] = "not_started"

    if not plan:
        for index, task in enumerate(tasks):
            if index == 0:
                plan[task["id"]] = "completed"
            elif index == 1:
                plan[task["id"]] = "in_progress"
            else:
                plan[task["id"]] = "not_started"

    if "not_started" not in plan.values() and len(tasks) > 2:
        plan[tasks[-1]["id"]] = "not_started"

    if "in_progress" not in plan.values() and len(tasks) > 1:
        plan[tasks[1]["id"]] = "in_progress"

    return plan


def repo_file_for_task(task: dict) -> Path:
    skill = str(task.get("skill_required") or "").lower()
    folder = SKILL_FOLDERS.get(skill, Path("src/backend"))
    return REPO_PATH / folder / f"{str(task['id']).lower()}_{task_slug(task)}.py"


def write_task_file(task: dict, step_no: int, message: str) -> Path:
    path = repo_file_for_task(task)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    block = [
        f"# {task['id']} - {task.get('title', '')}",
        f'TASK_ID = "{task["id"]}"',
        f'TASK_TITLE = "{task.get("title", "")}"',
        f'TASK_TYPE = "{task.get("req_type", "")}"',
        f'TASK_STEP = {step_no}',
        "",
        "def progress_marker() -> str:",
        f'    return "{task["id"]}:{step_no}:{message}"',
        "",
    ]
    content = existing + ("\n" if existing else "") + "\n".join(block)
    path.write_text(content, encoding="utf-8")
    return path


def commit_task_step(task: dict, step_no: int, message: str, commit_no: int) -> None:
    author_name, author_email = AUTHORS[commit_no % len(AUTHORS)]
    author = f"{author_name} <{author_email}>".encode("utf-8")
    when = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc) + timedelta(hours=commit_no * 6)
    timestamp = when.timestamp()

    path = write_task_file(task, step_no, message)
    porcelain.add(str(REPO_PATH), paths=[str(path.relative_to(REPO_PATH))])
    porcelain.commit(
        str(REPO_PATH),
        message=message.encode("utf-8"),
        author=author,
        committer=author,
        author_timestamp=timestamp,
        commit_timestamp=timestamp,
        author_timezone=0,
        commit_timezone=0,
    )


def build_commit_plan(tasks: list[dict], statuses: dict[str, str]) -> list[tuple[dict, int, str]]:
    plan: list[tuple[dict, int, str]] = []
    for task in tasks:
        status = statuses[task["id"]]
        topic = task_topic(task)
        if status == "completed":
            for index, suffix in enumerate(COMPLETED_MESSAGES, start=1):
                plan.append((task, index, f"{task['id']} {topic}: {suffix}"))
        elif status == "in_progress":
            plan.append((task, 1, f"{task['id']} {topic}: {IN_PROGRESS_MESSAGE}"))
    return plan


def main() -> int:
    tasks = load_tasks()
    safe_reset_repo()
    statuses = build_status_plan(tasks)
    commit_plan = build_commit_plan(tasks, statuses)

    for commit_no, (task, step_no, message) in enumerate(commit_plan, start=1):
        commit_task_step(task, step_no, message, commit_no)

    status_groups = {"completed": [], "in_progress": [], "not_started": []}
    for task in tasks:
        status_groups[statuses[task["id"]]].append(task["id"])

    print(f"Generated demo repo: {REPO_PATH}")
    print(f"Tasks source       : {TASKS_PATH}")
    print(f"Commits created    : {len(commit_plan)}")
    print(f"Completed tasks    : {', '.join(status_groups['completed']) or 'none'}")
    print(f"In-progress tasks  : {', '.join(status_groups['in_progress']) or 'none'}")
    print(f"Not-started tasks  : {', '.join(status_groups['not_started']) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
