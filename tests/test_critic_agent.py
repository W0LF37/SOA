from __future__ import annotations

from src.agents.critic import CriticAgent, format_critic_report
from src.core.schemas import Task, TaskList


class FakeLLMClient:
    def __init__(self, payload: dict):
        self.payload = payload

    def generate_json(self, prompt: str):  # noqa: ANN001
        return self.payload


def make_task(
    id,
    title,
    req_type="FR",
    complexity=2,
    dependencies=None,
):
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


def test_approve_valid_plan() -> None:
    task_list = TaskList(
        tasks=[
            make_task("T001", "Capture project requirements"),
            make_task("T002", "Design application architecture", dependencies=["T001"]),
            make_task("T003", "Implement user registration", dependencies=["T002"]),
            make_task("T004", "Implement payment workflow", dependencies=["T002"]),
            make_task("T005", "Generate admin reports", dependencies=["T002"]),
            make_task(
                "T006",
                "Enforce API latency targets",
                req_type="NFR",
                dependencies=["T003"],
            ),
        ]
    )

    report = CriticAgent().review(task_list)

    assert report.status in {"approved", "needs_revision"}
    assert report.status != "rejected"


def test_detect_cyclic_dependency() -> None:
    task_list = TaskList(
        tasks=[
            make_task("T001", "Implement authentication", dependencies=["T002"]),
            make_task("T002", "Implement user onboarding", dependencies=["T001"]),
        ]
    )

    report = CriticAgent().review(task_list)

    assert any(
        issue.severity == "error" and "Cyclic" in issue.message
        for issue in report.issues
    )


def test_cycle_report_is_cp1252_safe() -> None:
    task_list = TaskList(
        tasks=[
            make_task("T001", "Implement authentication", dependencies=["T002"]),
            make_task("T002", "Implement user onboarding", dependencies=["T001"]),
        ]
    )

    report = CriticAgent().review(task_list)
    rendered = format_critic_report(report)

    assert " -> " in rendered
    rendered.encode("cp1252")


def test_llm_suggestions_are_included_in_report() -> None:
    task_list = TaskList(
        tasks=[
            make_task("T001", "Capture project requirements"),
            make_task("T002", "Design application architecture", dependencies=["T001"]),
            make_task("T003", "Implement deployment workflow", dependencies=["T002"]),
        ]
    )

    report = CriticAgent(
        llm_client=FakeLLMClient(
            {
                "issues": [
                    {
                        "severity": "warning",
                        "message": "Rollback planning is missing from the deployment flow.",
                    }
                ],
                "suggestions": [
                    "Add a rollback task before production release.",
                    "Document the deployment owner and approval gate.",
                ],
            }
        )
    ).review(task_list)

    assert any(issue.layer == "llm" for issue in report.issues)
    assert "Fix: Rollback planning is missing from the deployment flow." in report.suggestions
    assert any(
        issue.message == "Suggestion: Add a rollback task before production release."
        for issue in report.issues
    )
    assert any(
        issue.message == "Suggestion: Document the deployment owner and approval gate."
        for issue in report.issues
    )


def test_detect_low_fr_nfr_ratio() -> None:
    task_list = TaskList(
        tasks=[
            make_task("T001", "Implement patient registration"),
            make_task("T002", "Add audit logging", req_type="NFR", dependencies=["T001"]),
            make_task("T003", "Add monitoring", req_type="NFR", dependencies=["T001"]),
            make_task("T004", "Add rate limiting", req_type="NFR", dependencies=["T001"]),
            make_task("T005", "Add backup policy", req_type="NFR", dependencies=["T001"]),
            make_task("T006", "Add encryption at rest", req_type="NFR", dependencies=["T001"]),
        ]
    )

    report = CriticAgent().review(task_list)

    assert any(
        issue.severity == "warning" and "FR/NFR" in issue.message
        for issue in report.issues
    )


def test_near_balanced_nfr_heavy_plan_does_not_warn_ratio() -> None:
    tasks = [
        make_task(f"T{idx:03d}", f"Implement feature {idx}")
        for idx in range(1, 12)
    ] + [
        make_task(f"T{idx:03d}", f"Enforce quality gate {idx}", req_type="NFR")
        for idx in range(12, 35)
    ]

    report = CriticAgent().review(TaskList(tasks=tasks))

    assert not any("FR/NFR ratio" in issue.message for issue in report.issues)


def test_warn_complex_isolated_task() -> None:
    task_list = TaskList(
        tasks=[
            make_task("T001", "Build orchestration core", complexity=5),
            make_task("T002", "Build worker service", dependencies=["T001"]),
            make_task("T003", "Build admin dashboard", dependencies=["T001"]),
        ]
    )

    report = CriticAgent().review(task_list)

    assert any(issue.severity == "warning" for issue in report.issues)


def test_warn_missing_hours() -> None:
    task = make_task("T001", "Implement notifications")
    task.estimated_hours = None

    task_list = TaskList(
        tasks=[
            task,
            make_task("T002", "Implement delivery pipeline", dependencies=["T001"]),
            make_task("T003", "Implement retry handling", dependencies=["T002"]),
        ]
    )

    report = CriticAgent().review(task_list)

    assert any(
        issue.severity == "warning" and "estimated_hours" in issue.message
        for issue in report.issues
    )


def test_warn_compound_nfr_task_needing_decomposition() -> None:
    task = make_task("T001", "Enforce platform constraints", req_type="NFR")
    task.description = (
        "The system must be highly available, encrypted, mobile-friendly, "
        "and responsive under peak load."
    )

    task_list = TaskList(
        tasks=[
            make_task("T000", "Implement student portal"),
            task,
            make_task("T002", "Implement notifications", dependencies=["T000"]),
        ]
    )

    report = CriticAgent().review(task_list)

    assert any(
        issue.severity == "warning" and "bundles multiple NFR concerns" in issue.message
        for issue in report.issues
    )


def test_small_plan_info() -> None:
    task_list = TaskList(tasks=[make_task("T001", "Implement login flow")])

    report = CriticAgent().review(task_list)

    assert any(
        issue.severity == "info" and "few tasks" in issue.message
        for issue in report.issues
    )


def test_score_decreases_with_issues() -> None:
    task_list = TaskList(
        tasks=[
            make_task("T001", "Build system core", complexity=5),
            make_task("T002", "Add audit logging", req_type="NFR", dependencies=["T001"]),
            make_task("T003", "Add metrics", req_type="NFR", dependencies=["T001"]),
            make_task("T004", "Add backups", req_type="NFR", dependencies=["T001"]),
            make_task("T005", "Add rate limiting", req_type="NFR", dependencies=["T001"]),
            make_task("T006", "Add encryption", req_type="NFR", dependencies=["T001"]),
        ]
    )

    report = CriticAgent().review(task_list)
    warning_count = sum(1 for issue in report.issues if issue.severity == "warning")

    assert warning_count >= 2
    assert report.score < 1.0


def test_report_serialisable() -> None:
    task_list = TaskList(
        tasks=[
            make_task("T001", "Capture requirements"),
            make_task("T002", "Design architecture", dependencies=["T001"]),
            make_task("T003", "Implement core workflow", dependencies=["T002"]),
        ]
    )

    report = CriticAgent().review(task_list)
    payload = report.model_dump(mode="json")

    assert isinstance(payload, dict)
    assert payload["status"] == report.status
    assert "issues" in payload
