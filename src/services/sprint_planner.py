from __future__ import annotations

from collections import Counter
import math

from src.agents.planner import PlannerAgent
from src.core.schemas import TaskList


class SprintPlanner:
    """Build a simple sprint plan from dependency graph generations."""

    WEEKLY_TEAM_CAPACITY_HOURS = 80
    QUALITY_THEMES = {"performance", "security", "compliance"}
    CORE_WORKFLOW_THEMES = {"crud", "view", "user_management"}
    PLANNING_ANALYTICS_THEMES = {
        "requirements_ingestion",
        "task_planning",
        "dependency_analysis",
        "estimation",
        "classification",
        "orchestration",
    }

    @classmethod
    def build_sprint_plan(
        cls,
        task_list: TaskList,
        graph_stats: dict[str, object],
    ) -> list[dict[str, object]]:
        task_lookup = {task.id: task for task in task_list.tasks}
        sprints: list[dict[str, object]] = []

        for sprint_number, group in enumerate(graph_stats.get("parallel_groups", []), start=1):
            stage_tasks = [task_lookup[task_id] for task_id in group if task_id in task_lookup]
            total_hours = sum(task.estimated_hours or 0 for task in stage_tasks)
            theme_counter: Counter[str] = Counter()
            for task in stage_tasks:
                theme_counter.update(
                    tag
                    for tag in PlannerAgent._extract_semantic_tags(task.description)
                    if tag != "general"
                )

            dominant_themes = [theme for theme, _ in theme_counter.most_common(3)]
            sprints.append(
                {
                    "sprint": sprint_number,
                    "name": cls._sprint_name(sprint_number, dominant_themes),
                    "duration_weeks": max(1, math.ceil(total_hours / cls.WEEKLY_TEAM_CAPACITY_HOURS)),
                    "tasks": [task.id for task in stage_tasks],
                    "goal": cls._sprint_goal(dominant_themes),
                    "total_points": sum(task.complexity for task in stage_tasks),
                    "total_estimated_hours": total_hours,
                    "owner_roles": sorted(
                        {
                            task.suggested_owner_role
                            for task in stage_tasks
                            if task.suggested_owner_role
                        }
                    ),
                    "focus_themes": dominant_themes,
                }
            )

        return sprints

    @classmethod
    def _sprint_name(cls, sprint_number: int, themes: list[str]) -> str:
        theme_set = set(themes)
        if {"identity", "auth", "access_control"} & theme_set:
            if "identity" in theme_set and {"auth", "access_control"} & theme_set:
                return "Identity & Access Foundations"
            if sprint_number == 1 and "identity" in theme_set:
                return "Account Foundation"
            if {"auth", "access_control"} & theme_set:
                return "Authentication & Access Control"
        if cls.CORE_WORKFLOW_THEMES & theme_set:
            return "Core Workflow Delivery"
        if {"integration", "notification"} & theme_set:
            return "Integrations & Notifications"
        if cls.QUALITY_THEMES & theme_set:
            if {"security", "compliance"} & theme_set:
                return "Security & Compliance Readiness"
            return "Performance & Reliability Validation"
        if {"reporting", "dashboard", "explainability"} & theme_set:
            return "Reporting & Decision Visibility"
        if {"monitoring", "risk_analysis"} & theme_set:
            return "Monitoring & Risk Controls"
        if {"storage", "offline_operation"} & theme_set:
            return "Data & Runtime Foundations"
        if cls.PLANNING_ANALYTICS_THEMES & theme_set:
            return "Planning & Coordination Intelligence"
        if "localization" in theme_set:
            return "Localization & Experience Readiness"
        if themes:
            return cls._generic_sprint_name(sprint_number, themes)
        return f"Sprint {sprint_number} Delivery"

    @staticmethod
    def _generic_sprint_name(sprint_number: int, themes: list[str]) -> str:
        labels = []
        for theme in themes[:2]:
            label = PlannerAgent._friendly_theme_label(theme).title()
            if label not in labels:
                labels.append(label)
        if labels:
            return " & ".join(labels)
        return f"Sprint {sprint_number} Delivery"

    @classmethod
    def _sprint_goal(cls, themes: list[str]) -> str:
        theme_set = set(themes)
        if {"identity", "auth", "access_control"} & theme_set:
            if "identity" in theme_set:
                return "Account identity, authentication, and permission foundations are ready for downstream workflows"
            return "Authentication and role-based access controls are enforced before protected workflows proceed"
        if cls.CORE_WORKFLOW_THEMES & theme_set:
            return "Core user-facing workflows are implemented and usable end-to-end"
        if {"integration", "notification"} & theme_set:
            return "External services and user communications are connected and ready for workflow use"
        if cls.QUALITY_THEMES & theme_set:
            if {"security", "compliance"} & theme_set:
                return "Security, privacy, and compliance controls are validated for the planned scope"
            return "Performance, reliability, and scalability targets are validated against realistic load"
        if {"reporting", "dashboard", "explainability"} & theme_set:
            return "Stakeholders can inspect operational outputs, reports, and decision evidence"
        if {"monitoring", "risk_analysis"} & theme_set:
            return "Delivery signals and risk indicators are visible early enough to guide intervention"
        if {"storage", "offline_operation"} & theme_set:
            return "Data persistence, retrieval, and runtime foundations are established"
        if cls.PLANNING_ANALYTICS_THEMES & theme_set:
            return "Planning, estimation, dependency, and coordination capabilities are ready for use"
        if "localization" in theme_set:
            return "Localized user experience requirements are implemented and validated"
        if themes:
            labels = ", ".join(
                PlannerAgent._friendly_theme_label(theme)
                for theme in themes[:2]
            )
            return f"Delivery work for {labels} is completed for this stage"
        return "Parallel delivery work is completed for this stage"
