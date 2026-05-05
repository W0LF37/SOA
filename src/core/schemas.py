from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Task(BaseModel):
    """Single planned task generated from requirement lines."""

    id: str = Field(..., pattern=r"^T\d{3}$")
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    req_type: Literal["FR", "NFR"]
    type_reason: str | None = None
    complexity: int = Field(..., ge=1, le=5)
    complexity_reason: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    source: str = Field(..., pattern=r"^(?:line \d+|block \d+(?: clause \d+)?|REQ-\d+)$")
    estimated_hours: int | None = Field(default=None, ge=1)
    estimated_days: int | None = Field(default=None, ge=1)
    recommended_team_size: int | None = Field(default=None, ge=1)
    skill_required: str | None = None
    suggested_owner_role: str | None = None
    risks: list[str] = Field(default_factory=list)
    estimation_breakdown: dict[str, object] = Field(default_factory=dict)
    optional: bool = False
    confidence: Literal["high", "medium", "low"] = "high"

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        for dep in value:
            if len(dep) != 4 or not dep.startswith("T") or not dep[1:].isdigit():
                raise ValueError(f"Invalid dependency id: {dep}")
            if dep in seen:
                raise ValueError(f"Duplicate dependency id: {dep}")
            seen.add(dep)
        return value

    @model_validator(mode="after")
    def validate_self_dependency(self) -> "Task":
        if self.id in self.dependencies:
            raise ValueError(f"Task {self.id} cannot depend on itself")
        return self


class TechStackReport(BaseModel):
    """Technology stack detected from the project brief / requirements text."""

    frontend: list[str] = Field(default_factory=list)
    backend: list[str] = Field(default_factory=list)
    database: list[str] = Field(default_factory=list)
    devops: list[str] = Field(default_factory=list)
    external_services: list[str] = Field(default_factory=list)
    detected_from: str = "requirements"


class TaskList(BaseModel):
    """Pipeline output container; serialized to data/processed/tasks.json."""

    tasks: list[Task] = Field(..., min_length=1)
    tech_stack: TechStackReport | None = None

    @model_validator(mode="after")
    def validate_cross_task_references(self) -> "TaskList":
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Task ids must be unique")

        known_ids = set(task_ids)
        for task in self.tasks:
            for dep in task.dependencies:
                if dep not in known_ids:
                    raise ValueError(
                        f"Task {task.id} has unknown dependency: {dep}"
                    )
        return self


class CriticSummary(BaseModel):
    """Compact critic metadata embedded in plan_summary.json."""

    status: Literal["approved", "needs_revision", "rejected"]
    score: float = Field(..., ge=0.0, le=1.0)
    issues_count: int = Field(..., ge=0)
    report_file: str


class LLMPlanningTrace(BaseModel):
    """Trace of the LLM planning attempt and fallback path."""

    role: str
    attempted: bool
    accepted: bool
    used_fallback: bool
    fallback_reason: str | None = None
    kb_enabled: bool
    retrieved_kb_context_chars: int = Field(..., ge=0)
    kb_document_count: int = Field(..., ge=0)


class PipelineConfig(BaseModel):
    """Runtime flags that shaped a pipeline run."""

    allow_fallback: bool
    allow_decomposition: bool
    force_fallback: bool
    use_kb: bool


class EffortSummary(BaseModel):
    """Aggregate effort metrics written to plan_summary.json."""

    total_estimated_hours: int = Field(..., ge=0)
    total_estimated_days: int = Field(..., ge=0)
    fr_estimated_hours: int = Field(..., ge=0)
    nfr_estimated_hours: int = Field(..., ge=0)


class SprintSummary(BaseModel):
    """A sprint-level delivery slice in plan_summary.json."""

    model_config = ConfigDict(extra="allow")

    sprint: int = Field(..., ge=1)
    name: str
    goal: str
    tasks: list[str] = Field(default_factory=list)
    total_estimated_hours: int = Field(..., ge=0)
    total_points: int = Field(..., ge=0)
    duration_weeks: int = Field(..., ge=1)


class TeamAllocationItem(BaseModel):
    """Role allocation summary in plan_summary.json."""

    role: str
    task_ids: list[str] = Field(default_factory=list)
    task_count: int = Field(..., ge=0)
    estimated_hours: int = Field(..., ge=0)
    focus: str


class AdminReviewSummary(BaseModel):
    """Admin review state for the current generated plan."""

    status: Literal["pending", "empty", "completed"]
    total_flagged: int = Field(..., ge=0)
    queue_file: str | None = None
    reviewed_at: str | None = None
    approved: int = Field(default=0, ge=0)
    edited: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    tasks_final_file: str | None = None


class PlanSummary(BaseModel):
    """Full analytics report serialized to data/processed/plan_summary.json."""

    model_config = ConfigDict(extra="allow")

    generated_at: str
    model: str
    provider: str
    generation_mode: str
    llm_used: bool
    llm_attempted: bool
    llm_accepted: bool
    llm_model: str
    used_fallback: bool
    fallback_reason: str | None = None
    retrieved_kb_context: str = ""
    kb_document_count: int = Field(default=0, ge=0)
    llm_planning_trace: LLMPlanningTrace
    critic: CriticSummary
    input_file: str
    tasks_file: str
    graph_file: str
    pipeline_config: PipelineConfig
    plan_highlights: dict[str, Any] = Field(default_factory=dict)
    committee_brief: dict[str, Any] = Field(default_factory=dict)
    sprint_plan: list[SprintSummary] = Field(default_factory=list)
    effort_summary: EffortSummary
    team_allocation: list[TeamAllocationItem] = Field(default_factory=list)
    risk_register: list[dict[str, Any]] = Field(default_factory=list)
    graph_analytics: dict[str, Any] = Field(default_factory=dict)
    admin_review: AdminReviewSummary | None = None


class CriticIssue(BaseModel):
    """A single issue found by the CriticAgent."""

    layer: Literal["schema", "logic", "llm"]
    severity: Literal["error", "warning", "info"]
    message: str


class CriticReport(BaseModel):
    """Output of CriticAgent.review(); serialized to data/processed/critic_report.json."""

    status: Literal["approved", "needs_revision", "rejected"]
    score: float = Field(..., ge=0.0, le=1.0)
    issues: list[CriticIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    reviewed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CommitInfo(BaseModel):
    """A single Git commit parsed from git log."""

    sha: str
    message: str
    author: str
    date: str
    files_changed: list[str] = Field(default_factory=list)


class TaskProgress(BaseModel):
    """Progress status for a single task based on matched commits."""

    task_id: str
    task_title: str
    status: Literal["not_started", "in_progress", "completed"]
    matched_commits: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    completion_estimate: float = Field(..., ge=0.0, le=1.0)


class MonitorReport(BaseModel):
    """Output of MonitorAgent.track_progress(); serialized to data/processed/monitor_report.json."""

    overall_progress: float = Field(..., ge=0.0, le=1.0)
    tasks_tracked: int
    tasks_completed: int
    tasks_in_progress: int
    tasks_not_started: int
    task_progress: list[TaskProgress]
    commits_analyzed: int
    behind_schedule: list[str] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class RiskItem(BaseModel):
    """A single identified risk with its mitigation."""

    category: str
    severity: Literal["critical", "high", "medium", "low"]
    message: str
    affected_tasks: list[str] = Field(default_factory=list)
    mitigation: str = ""
    source: Literal["rule", "llm"] = "rule"


class RiskReport(BaseModel):
    """Output of RiskAnalyzer.analyze(); serialized to data/processed/risk_report.json."""

    risk_level: Literal["low", "medium", "high", "critical"]
    risk_score: float = Field(..., ge=0.0, le=1.0)
    total_risks: int
    risks: list[RiskItem]
    mitigations: list[str] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
