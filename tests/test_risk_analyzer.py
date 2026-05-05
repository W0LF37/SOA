from __future__ import annotations

from src.agents.risk_analyzer import RiskAnalyzer, format_risk_report
from src.core.schemas import CriticIssue, CriticReport, Task, TaskList


def make_task(id, title, complexity=2, req_type="FR", dependencies=None, hours=8):
    return Task(
        id=id,
        title=title,
        description=f"{title} description.",
        req_type=req_type,
        complexity=complexity,
        dependencies=list(dependencies or []),
        source="line 1",
        estimated_hours=hours,
        estimated_days=1,
        recommended_team_size=1,
    )


def make_plan_summary(
    bottlenecks=None,
    critical_path_ids=None,
    critical_path_length=2,
    parallel_groups=None,
    total_hours=100,
    fr_hours=60,
    nfr_hours=40,
    avg_complexity=2.0,
    team_alloc=None,
    assumption_log=None,
):
    return {
        "graph_analytics": {
            "bottleneck_tasks": bottlenecks or [],
            "critical_path": {
                "task_ids": critical_path_ids or [],
                "length": critical_path_length,
            },
            "parallel_groups": parallel_groups or [["T001", "T002"]],
            "avg_complexity": avg_complexity,
        },
        "effort_summary": {
            "total_estimated_hours": total_hours,
            "fr_estimated_hours": fr_hours,
            "nfr_estimated_hours": nfr_hours,
        },
        "team_allocation": team_alloc or [
            {"role": "Backend Engineer", "estimated_hours": 60},
            {"role": "Platform Engineer", "estimated_hours": 40},
        ],
        "plan_highlights": {
            "committee_brief": {
                "assumption_log": assumption_log or [],
            }
        },
    }


def make_critic_report(score=0.99, status="approved", issues=None):
    return CriticReport(
        status=status,
        score=score,
        issues=issues or [],
        suggestions=[],
    )


def three_tasks():
    return TaskList(tasks=[
        make_task("T001", "Implement user registration"),
        make_task("T002", "Design architecture", dependencies=["T001"]),
        make_task("T003", "Add payment workflow", dependencies=["T002"]),
    ])


def test_clean_plan_is_low_risk() -> None:
    report = RiskAnalyzer().analyze(
        task_list=three_tasks(),
        plan_summary=make_plan_summary(),
        critic_report=make_critic_report(),
    )

    assert report.risk_level == "low"
    assert report.risk_score < 0.20


def test_heavy_bottleneck_raises_high_risk() -> None:
    bottlenecks = [{"id": "T001", "title": "Core module", "blocks": 4, "complexity": 3}]
    report = RiskAnalyzer().analyze(
        task_list=three_tasks(),
        plan_summary=make_plan_summary(bottlenecks=bottlenecks),
    )

    assert any(
        r.category == "bottleneck" and r.severity == "high"
        for r in report.risks
    )


def test_critical_bottleneck_raises_critical_risk() -> None:
    bottlenecks = [{"id": "T001", "title": "Core module", "blocks": 6, "complexity": 3}]
    report = RiskAnalyzer().analyze(
        task_list=three_tasks(),
        plan_summary=make_plan_summary(bottlenecks=bottlenecks),
    )

    assert any(
        r.category == "bottleneck" and r.severity == "critical"
        for r in report.risks
    )


def test_foundational_nfr_bottlenecks_are_grouped_not_multiplied() -> None:
    task_list = TaskList(tasks=[
        make_task("T001", "Implement student portal"),
        make_task("T002", "Optimize system uptime and reliability constraints", req_type="NFR"),
        make_task("T003", "Enforce sensitive data encryption controls", req_type="NFR"),
    ])
    bottlenecks = [
        {"id": "T002", "title": "Optimize system uptime and reliability constraints", "blocks": 6, "complexity": 4},
        {"id": "T003", "title": "Enforce sensitive data encryption controls", "blocks": 5, "complexity": 3},
    ]
    report = RiskAnalyzer().analyze(
        task_list=task_list,
        plan_summary=make_plan_summary(bottlenecks=bottlenecks),
    )

    grouped = [
        r for r in report.risks
        if r.category == "bottleneck" and "Foundational NFR gates" in r.message
    ]
    assert len(grouped) == 1
    assert grouped[0].severity == "high"
    assert not any(
        r.category == "bottleneck" and r.severity == "critical"
        for r in report.risks
    )


def test_complexity5_on_critical_path_is_critical() -> None:
    task_list = TaskList(tasks=[
        make_task("T001", "Build orchestration core", complexity=5),
        make_task("T002", "Build worker service", dependencies=["T001"]),
        make_task("T003", "Build admin dashboard", dependencies=["T002"]),
    ])
    summary = make_plan_summary(critical_path_ids=["T001", "T002", "T003"])

    report = RiskAnalyzer().analyze(task_list=task_list, plan_summary=summary)

    assert any(
        r.category == "complexity" and r.severity == "critical"
        for r in report.risks
    )


def test_high_total_hours_triggers_schedule_risk() -> None:
    report = RiskAnalyzer().analyze(
        task_list=three_tasks(),
        plan_summary=make_plan_summary(total_hours=250, fr_hours=150, nfr_hours=100),
    )

    assert any(
        r.category == "schedule" and r.severity == "high"
        for r in report.risks
    )


def test_nfr_exceeds_fr_triggers_medium() -> None:
    report = RiskAnalyzer().analyze(
        task_list=three_tasks(),
        plan_summary=make_plan_summary(fr_hours=40, nfr_hours=80, total_hours=120),
    )

    assert any(
        r.category == "schedule" and r.severity == "medium"
        and "NFR" in r.message
        for r in report.risks
    )


def test_poor_critic_score_triggers_quality_risk() -> None:
    critic = make_critic_report(score=0.70, status="needs_revision")
    report = RiskAnalyzer().analyze(
        task_list=three_tasks(),
        plan_summary=make_plan_summary(),
        critic_report=critic,
    )

    assert any(r.category == "quality" for r in report.risks)
    assert any(r.severity in {"high", "critical"} for r in report.risks)


def test_risk_score_increases_with_issues() -> None:
    bottlenecks = [
        {"id": "T001", "title": "Core", "blocks": 4, "complexity": 3},
        {"id": "T002", "title": "Auth", "blocks": 3, "complexity": 3},
    ]
    report = RiskAnalyzer().analyze(
        task_list=three_tasks(),
        plan_summary=make_plan_summary(
            bottlenecks=bottlenecks,
            total_hours=250,
            fr_hours=100,
            nfr_hours=150,
        ),
    )

    assert report.risk_score > 0.20
    assert report.total_risks >= 2


def test_report_serialisable() -> None:
    report = RiskAnalyzer().analyze(
        task_list=three_tasks(),
        plan_summary=make_plan_summary(),
    )
    payload = report.model_dump(mode="json")

    assert isinstance(payload, dict)
    assert "risk_level" in payload
    assert "risks" in payload
    assert isinstance(payload["risks"], list)
