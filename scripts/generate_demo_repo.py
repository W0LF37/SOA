from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_PATH = PROJECT_ROOT / "case_study"
TASKS_PATH = PROJECT_ROOT / "data" / "processed" / "tasks.json"

AUTHORS = [
    ("Maya Haddad", "maya@example.com"),
    ("Omar Saleh", "omar@example.com"),
    ("Lina Nasser", "lina@example.com"),
]

COMPLETED_COUNTS = {
    "T001": 5,
    "T003": 4,
    "T004": 4,
    "T005": 4,
    "T009": 5,
    "T010": 5,
    "T012": 5,
    "T013": 5,
}
IN_PROGRESS = {"T002", "T006", "T007", "T011", "T014"}
NOT_STARTED = {"T008", "T015"}

TASK_KEYWORDS = {
    "T001": "registration",
    "T002": "grades",
    "T003": "advisors",
    "T004": "tuition invoices",
    "T005": "payment",
    "T006": "notification",
    "T007": "registrar schedules",
    "T008": "transcript",
    "T009": "learning system",
    "T010": "available SLA",
    "T011": "response time",
    "T012": "multilingual",
    "T013": "compliance",
    "T014": "five hundred",
    "T015": "mobile interface",
}

COMPLETED_STEPS = [
    "completed slice alpha",
    "completed slice beta",
    "completed slice gamma",
    "completed slice delta",
    "completed slice epsilon",
]

WIP_STEP = "draft slice"


def run_git(args: list[str], *, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_PATH,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


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
    (REPO_PATH / "src").mkdir(parents=True)
    (REPO_PATH / "tests").mkdir()
    run_git(["init"])
    run_git(["config", "user.name", AUTHORS[0][0]])
    run_git(["config", "user.email", AUTHORS[0][1]])


def task_title(task_id: str) -> str:
    if not TASKS_PATH.exists():
        return TASK_KEYWORDS[task_id]
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8")).get("tasks", [])
    for task in tasks:
        if task.get("id") == task_id:
            return str(task.get("title") or TASK_KEYWORDS[task_id])
    return TASK_KEYWORDS[task_id]


def commit_file(task_id: str, index: int, message: str, commit_no: int) -> None:
    slug = TASK_KEYWORDS[task_id].replace(" ", "_")
    folder = REPO_PATH / ("tests" if "tests" in message else "src")
    path = folder / f"{task_id.lower()}_{slug}_{index:02d}.py"
    path.write_text(
        "\n".join(
            [
                f'"""Demo implementation artifact for {task_id}."""',
                "",
                f'TASK_ID = "{task_id}"',
                f'TASK_TITLE = "{task_title(task_id)}"',
                f'COMMIT_MESSAGE = "{message}"',
                "",
                "def marker() -> str:",
                f'    return "{task_id}:{index}:{commit_no}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_git(["add", str(path.relative_to(REPO_PATH))])


def commit(task_id: str, message: str, commit_no: int) -> None:
    author_name, author_email = AUTHORS[commit_no % len(AUTHORS)]
    when = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc) + timedelta(hours=commit_no * 5)
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_AUTHOR_DATE": when.isoformat(),
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
            "GIT_COMMITTER_DATE": when.isoformat(),
        }
    )
    commit_file(task_id, commit_no, message, commit_no)
    run_git(["commit", "-m", message], env=env)


def build_commit_plan() -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = []
    for task_id, count in COMPLETED_COUNTS.items():
        keywords = TASK_KEYWORDS[task_id]
        for index in range(count):
            step = COMPLETED_STEPS[index % len(COMPLETED_STEPS)]
            plan.append((task_id, f"{task_id} {keywords}: {step}"))
    for task_id in sorted(IN_PROGRESS):
        plan.append((task_id, f"{task_id} {TASK_KEYWORDS[task_id]}: {WIP_STEP}"))
    return plan


def main() -> int:
    safe_reset_repo()
    plan = build_commit_plan()
    for commit_no, (task_id, message) in enumerate(plan, start=1):
        commit(task_id, message, commit_no)

    run_git(["status", "--short"])
    print(f"Generated demo repo: {REPO_PATH}")
    print(f"Commits created: {len(plan)}")
    print(f"Authors: {', '.join(name for name, _ in AUTHORS)}")
    print(f"Completed tasks: {', '.join(COMPLETED_COUNTS)}")
    print(f"In-progress tasks: {', '.join(sorted(IN_PROGRESS))}")
    print(f"Not-started tasks: {', '.join(sorted(NOT_STARTED))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
