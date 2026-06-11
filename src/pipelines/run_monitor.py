from __future__ import annotations

import argparse
import json
from itertools import zip_longest
from pathlib import Path
from typing import Sequence

from src.agents.monitor import MonitorAgent
from src.core.runtime_paths import prepare_writable_file_path
from src.core.schemas import MonitorReport, TaskList


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks.json")
DEFAULT_REPO_PATH = PROJECT_ROOT
DEFAULT_REPORT_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/monitor_report.json")


def load_task_list(tasks_path: Path = DEFAULT_TASKS_PATH) -> TaskList:
    return TaskList.model_validate_json(tasks_path.read_text(encoding="utf-8"))


def _task_statuses(report: MonitorReport) -> list[dict]:
    statuses: list[dict] = []
    for task in report.task_progress:
        evidence_commits = []
        for sha, message in zip_longest(task.matched_commits, task.evidence, fillvalue=""):
            evidence_commits.append({"sha": sha, "message": message})

        statuses.append(
            {
                "task_id": task.task_id,
                "task_title": task.task_title,
                "status": task.status,
                "completion_estimate": task.completion_estimate,
                "matched_files": task.matched_files,
                "match_reasons": task.match_reasons,
                "evidence_confidence": task.evidence_confidence,
                "alignment_score": task.alignment_score,
                "evidence_note": task.evidence_note,
                "evidence_commits": evidence_commits,
            }
        )
    return statuses


def save_monitor_report(
    report: MonitorReport,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> Path:
    payload = report.model_dump(mode="json")
    payload["task_statuses"] = _task_statuses(report)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report_path


def format_terminal_report(report: MonitorReport) -> str:
    lines = [
        "=" * 62,
        "  MONITOR PIPELINE REPORT",
        "=" * 62,
        f"  Overall progress: {report.overall_progress:.1%}",
        f"  Commits analyzed: {report.commits_analyzed}",
        "",
        "  Task statuses",
        "  " + "-" * 58,
    ]

    for task in report.task_progress:
        lines.append(f"  {task.task_id}  {task.status:<11}  {task.task_title}")
        if task.matched_commits:
            for sha, message in zip_longest(task.matched_commits, task.evidence, fillvalue=""):
                commit = sha[:12] if sha else "unknown"
                detail = f"{commit}"
                if message:
                    detail = f"{detail}  {message}"
                lines.append(f"      evidence: {detail}")
        else:
            lines.append("      evidence: none")

    lines.append("=" * 62)
    return "\n".join(lines)


def run_monitor_pipeline(
    tasks_path: Path = DEFAULT_TASKS_PATH,
    repo_path: Path = DEFAULT_REPO_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> MonitorReport:
    task_list = load_task_list(tasks_path)
    monitor = MonitorAgent()
    report = monitor.track_progress(task_list, repo_path=str(repo_path))
    save_monitor_report(report, report_path)
    return report


def main(argv: Sequence[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="Run git-based task progress monitoring.")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS_PATH)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args(argv)

    report = run_monitor_pipeline(
        tasks_path=args.tasks,
        repo_path=args.repo,
        report_path=args.report,
    )
    print(format_terminal_report(report))
    print(f"\nSaved monitor report: {args.report}")
    return args.report


if __name__ == "__main__":
    main()
