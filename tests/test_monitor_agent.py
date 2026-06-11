from __future__ import annotations

import pytest

from src.agents.monitor import MonitorAgent, format_monitor_report
from src.core.schemas import Task, TaskList


def make_task(id, title, req_type="FR", complexity=2, dependencies=None):
    return Task(
        id=id,
        title=title,
        description=f"{title} description.",
        req_type=req_type,
        complexity=complexity,
        dependencies=list(dependencies or []),
        source="line 1",
        estimated_hours=4,
        estimated_days=1,
        recommended_team_size=1,
    )


def make_commit(sha, message, author="dev@test.com", date="2026-01-01T00:00:00+00:00", files=None):
    return {
        "sha": sha,
        "message": message,
        "author": author,
        "date": date,
        "files_changed": list(files or []),
    }


def three_tasks():
    return TaskList(tasks=[
        make_task("T001", "Implement user registration"),
        make_task("T002", "Design application architecture", dependencies=["T001"]),
        make_task("T003", "Add payment workflow", dependencies=["T002"]),
    ])


def test_no_commits_all_not_started() -> None:
    report = MonitorAgent().track_progress(three_tasks(), commits=[])

    assert report.overall_progress == 0.0
    assert report.tasks_not_started == 3
    assert report.tasks_completed == 0
    assert report.commits_analyzed == 0


def test_matching_commit_marks_in_progress() -> None:
    commits = [make_commit("abc1", "add user registration endpoint")]
    report = MonitorAgent().track_progress(three_tasks(), commits=commits)

    t001 = next(tp for tp in report.task_progress if tp.task_id == "T001")
    assert t001.status == "in_progress"
    assert t001.completion_estimate == 0.5


def test_two_commits_marks_completed() -> None:
    commits = [
        make_commit("abc1", "add user registration endpoint"),
        make_commit("abc2", "refactor user registration validation"),
    ]
    report = MonitorAgent().track_progress(three_tasks(), commits=commits)

    t001 = next(tp for tp in report.task_progress if tp.task_id == "T001")
    assert t001.status == "completed"
    assert t001.completion_estimate == 1.0


def test_done_keyword_in_commit_marks_completed() -> None:
    commits = [make_commit("abc1", "implement user registration complete")]
    report = MonitorAgent().track_progress(three_tasks(), commits=commits)

    t001 = next(tp for tp in report.task_progress if tp.task_id == "T001")
    assert t001.status == "completed"
    assert t001.completion_estimate == 1.0


def test_overall_progress_weighted_by_complexity() -> None:
    task_list = TaskList(tasks=[
        make_task("T001", "Simple task", complexity=1),
        make_task("T002", "Complex task", complexity=4),
    ])
    commits = [
        make_commit("a1", "simple task done"),
        make_commit("a2", "simple task merged"),
    ]
    report = MonitorAgent().track_progress(task_list, commits=commits)

    # T001 completed (1.0 * weight 1), T002 not_started (0.0 * weight 4)
    # weighted: (1.0*1 + 0.0*4) / (1+4) = 0.2
    assert abs(report.overall_progress - 0.2) < 0.01


def test_behind_schedule_detection() -> None:
    task_list = TaskList(tasks=[
        make_task("T001", "Implement core module"),
        make_task("T002", "Build API layer", dependencies=["T001"]),
    ])
    # T002 has 2 commits (completed), but T001 has 0 commits (not_started)
    commits = [
        make_commit("b1", "build api layer start"),
        make_commit("b2", "build api endpoints done"),
    ]
    report = MonitorAgent().track_progress(task_list, commits=commits)

    assert "T001" in report.behind_schedule


def test_report_serialisable() -> None:
    report = MonitorAgent().track_progress(three_tasks(), commits=[])
    payload = report.model_dump(mode="json")

    assert isinstance(payload, dict)
    assert "overall_progress" in payload
    assert "task_progress" in payload
    assert isinstance(payload["task_progress"], list)


def test_commits_param_bypasses_repo_path() -> None:
    commits = [make_commit("x1", "user registration done")]
    report = MonitorAgent().track_progress(three_tasks(), commits=commits)

    assert report.commits_analyzed == 1
    assert report is not None


def test_keyword_mode_still_works() -> None:
    """Ensure use_semantic=False falls back correctly to keyword matching."""
    commits = [make_commit("abc1", "add user registration endpoint")]
    report  = MonitorAgent(use_semantic=False).track_progress(
        three_tasks(), commits=commits
    )
    t001 = next(tp for tp in report.task_progress if tp.task_id == "T001")
    assert t001.status in {"in_progress", "completed"}


def test_explicit_task_id_reference_matches_even_when_titles_differ() -> None:
    task_list = TaskList(tasks=[
        make_task("T001", "Implement user registration"),
        make_task("T002", "Build analytics export"),
    ])
    commits = [
        make_commit(
            "id01",
            "T001 scaffold persistence layer",
            files=["src/backend/t001_registration_flow.py"],
        )
    ]

    report = MonitorAgent(use_semantic=False).track_progress(task_list, commits=commits)

    t001 = next(tp for tp in report.task_progress if tp.task_id == "T001")
    t002 = next(tp for tp in report.task_progress if tp.task_id == "T002")
    assert t001.matched_commits == ["id01"]
    assert "task reference" in t001.match_reasons
    assert t001.matched_files == ["src/backend/t001_registration_flow.py"]
    assert t002.matched_commits == []


def test_report_surfaces_unmatched_commits_and_hotspots() -> None:
    commits = [
        make_commit("abc1", "add user registration endpoint", files=["src/auth/register.py"]),
        make_commit("abc2", "misc refactor for shared helpers", files=["src/shared/helpers.py"]),
    ]

    report = MonitorAgent(use_semantic=False).track_progress(three_tasks(), commits=commits)

    assert [commit.sha for commit in report.unmatched_commits] == ["abc2"]
    assert report.repository_hotspots
    assert report.repository_hotspots[0].path in {
        "src/auth/register.py",
        "src/shared/helpers.py",
    }


def test_semantic_mode_initialises() -> None:
    """SemanticMatcher loads without error when sentence-transformers is available."""
    try:
        agent = MonitorAgent(use_semantic=True)
        # matcher may be None if sentence-transformers missing, but no exception
        assert agent._matcher is None or hasattr(agent._matcher, "matches")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"SemanticMatcher raised unexpectedly: {exc}")


def test_semantic_matches_paraphrase() -> None:
    """Semantic matcher: 'JWT token handling' should match 'User Authentication' task."""
    try:
        from src.agents.monitor import SemanticMatcher
        from src.core.schemas import TaskList
        matcher = SemanticMatcher()
        task_list = TaskList(tasks=[
            make_task("T001", "Implement user authentication module",
                      complexity=3),
        ])
        matcher.precompute(task_list)
        # JWT and authentication are semantically related
        sim = matcher.similarity("Add JWT token handling and session management", "T001")
        assert sim > 0.30, f"Expected similarity > 0.30, got {sim:.3f}"
    except ImportError:
        import pytest
        pytest.skip("sentence-transformers not available")
