from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from src.core.schemas import CriticIssue, CriticReport, Task, TaskList

if TYPE_CHECKING:
    from src.llm.ollama_client import OllamaClient


class CriticAgent:
    """
    Phase 2 — Automated reviewer for PlannerAgent output.

    Two validation layers:
      Layer 1 (logic)  — Business-rule checks (fast, no LLM)
      Layer 2 (llm)    — Holistic reasoning via OllamaClient (optional, slow)

    Usage::

        agent = CriticAgent()                        # logic-only, no LLM
        agent = CriticAgent(llm_client=client)       # with LLM layer

        report = agent.review(task_list)
        # report.status  → "approved" | "needs_revision" | "rejected"
        # report.score   → 0.0 – 1.0
        # report.issues  → list[CriticIssue]
    """

    # Score penalties
    _PENALTY_ERROR = 0.20
    _PENALTY_WARNING = 0.05
    _PENALTY_INFO = 0.01

    # Thresholds
    _REJECT_THRESHOLD = 0.50
    _REVISION_THRESHOLD = 0.80
    _COMPOUND_NFR_CONCERNS = {
        "availability": re.compile(r"\b(availability|uptime|downtime|highly available|reliab\w*|failover)\b", re.IGNORECASE),
        "encryption": re.compile(r"\b(encrypt(?:ed|ion)?|tls|ssl|aes(?:-\d+)?|at rest|in transit)\b", re.IGNORECASE),
        "performance": re.compile(r"\b(latency|response time|throughput|performance|peak load|concurrent|scalab\w*|load test|stress(?: test)?)\b", re.IGNORECASE),
        "mobile": re.compile(r"\b(mobile[\-\s]?friendly|responsive(?:\s+layout|\s+design)?)\b", re.IGNORECASE),
        "accessibility": re.compile(r"\b(accessibility|wcag|screen reader|keyboard navigation)\b", re.IGNORECASE),
        "localization": re.compile(r"\b(localiz|i18n|rtl|multilingual|language support|arabic|english)\b", re.IGNORECASE),
        "compliance": re.compile(r"\b(gdpr|hipaa|pci|compliance|privacy|data protection|audit)\b", re.IGNORECASE),
    }

    def __init__(self, llm_client: "OllamaClient | None" = None) -> None:
        self._llm = llm_client

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def review(self, task_list: TaskList) -> CriticReport:
        """Run all enabled layers and return a CriticReport."""
        issues: list[CriticIssue] = []

        # Layer 1 — business logic
        issues.extend(self._layer_logic(task_list))

        # Layer 2 — LLM (only if client provided and no hard errors yet)
        hard_errors = [i for i in issues if i.severity == "error"]
        if self._llm is not None and not hard_errors:
            issues.extend(self._layer_llm(task_list))

        score = self._compute_score(issues)
        status = self._compute_status(score, issues)
        suggestions = self._build_suggestions(issues)

        return CriticReport(
            status=status,
            score=round(score, 3),
            issues=issues,
            suggestions=suggestions,
        )

    # ------------------------------------------------------------------ #
    # Layer 1: Business Logic                                              #
    # ------------------------------------------------------------------ #

    def _layer_logic(self, task_list: TaskList) -> list[CriticIssue]:
        issues: list[CriticIssue] = []
        tasks = task_list.tasks

        # --- counts ---
        n = len(tasks)
        if n < 3:
            issues.append(CriticIssue(
                layer="logic",
                severity="info",
                message=f"Very few tasks ({n}). Plan may be under-specified.",
            ))
        if n > 30:
            issues.append(CriticIssue(
                layer="logic",
                severity="info",
                message=f"Many tasks ({n}). Consider grouping or simplifying.",
            ))

        # --- build lookup ---
        id_to_task = {t.id: t for t in tasks}
        all_ids = set(id_to_task)

        # --- duplicate IDs (already caught by Pydantic, but belt-and-suspenders) ---
        seen_ids: set[str] = set()
        for task in tasks:
            if task.id in seen_ids:
                issues.append(CriticIssue(
                    layer="logic",
                    severity="error",
                    message=f"Duplicate task ID: {task.id}",
                ))
            seen_ids.add(task.id)

        # --- unknown dependencies ---
        for task in tasks:
            for dep in task.dependencies:
                if dep not in all_ids:
                    issues.append(CriticIssue(
                        layer="logic",
                        severity="error",
                        message=f"Task {task.id} depends on unknown ID: {dep}",
                    ))

        # --- cyclic dependencies ---
        cycle = self._detect_cycle(id_to_task)
        if cycle:
            issues.append(CriticIssue(
                layer="logic",
                severity="error",
                message=f"Cyclic dependency detected: {' -> '.join(cycle)}",
            ))

        # --- FR / NFR ratio ---
        fr_count = sum(1 for t in tasks if t.req_type == "FR")
        nfr_count = sum(1 for t in tasks if t.req_type == "NFR")
        if nfr_count > 0:
            ratio = fr_count / nfr_count
            if ratio < 0.4:
                issues.append(CriticIssue(
                    layer="logic",
                    severity="warning",
                    message=(
                        f"FR/NFR ratio is {ratio:.1f} ({fr_count} FR, {nfr_count} NFR). "
                        "Unusually few functional requirements."
                    ),
                ))
            elif ratio > 10:
                issues.append(CriticIssue(
                    layer="logic",
                    severity="warning",
                    message=(
                        f"FR/NFR ratio is {ratio:.1f} ({fr_count} FR, {nfr_count} NFR). "
                        "Consider adding non-functional requirements."
                    ),
                ))

        # --- complexity-5 tasks with no dependencies ---
        for task in tasks:
            if task.complexity == 5 and not task.dependencies:
                issues.append(CriticIssue(
                    layer="logic",
                    severity="warning",
                    message=(
                        f"Task {task.id} ({task.title!r}) has max complexity (5) "
                        "but no dependencies. Is it truly standalone?"
                    ),
                ))

        # --- tasks missing estimated_hours ---
        missing_hours = [t.id for t in tasks if t.estimated_hours is None]
        if missing_hours:
            issues.append(CriticIssue(
                layer="logic",
                severity="warning",
                message=(
                    f"{len(missing_hours)} task(s) have no estimated_hours: "
                    f"{', '.join(missing_hours)}"
                ),
            ))

        for task in tasks:
            if task.req_type != "NFR":
                continue
            concerns = self._compound_nfr_concerns(task.description)
            if len(concerns) < 2:
                continue
            lowered = task.description.lower()
            if "," not in lowered and " and " not in lowered and ";" not in lowered:
                continue
            issues.append(CriticIssue(
                layer="logic",
                severity="warning",
                message=(
                    f"Task {task.id} bundles multiple NFR concerns "
                    f"({', '.join(sorted(concerns))}). Split them into separate tasks."
                ),
            ))

        # --- NFR tasks: warn only if ALL tasks are NFR (no FR exists at all) ---
        if fr_count == 0:
            issues.append(CriticIssue(
                layer="logic",
                severity="warning",
                message="Plan contains no functional requirements (FR). At least one FR is expected.",
            ))

        return issues

    # ------------------------------------------------------------------ #
    # Layer 2: LLM Reasoning                                              #
    # ------------------------------------------------------------------ #

    def _layer_llm(self, task_list: TaskList) -> list[CriticIssue]:
        issues: list[CriticIssue] = []

        task_summary = "\n".join(
            f"  {t.id}: [{t.req_type}] C{t.complexity} — {t.title}"
            for t in task_list.tasks
        )
        prompt = (
            "You are a senior software architect reviewing a project task plan.\n"
            "Evaluate the following task list and respond with a JSON object.\n\n"
            f"TASKS ({len(task_list.tasks)} total):\n{task_summary}\n\n"
            "Respond ONLY with a JSON object in this exact format:\n"
            '{"issues": [{"severity": "warning|info", "message": "..."}], '
            '"suggestions": ["..."]}\n'
            "Focus on: missing critical tasks, illogical groupings, "
            "scope gaps, or unrealistic complexity ratings. "
            "Do NOT repeat schema or dependency errors. "
            "If the plan looks good, return empty lists."
        )

        try:
            raw = self._llm.generate_json(prompt)
            for item in raw.get("issues", []):
                sev = item.get("severity", "info")
                if sev not in {"warning", "info"}:
                    sev = "info"
                msg = str(item.get("message", "")).strip()
                if msg:
                    issues.append(CriticIssue(layer="llm", severity=sev, message=msg))
            for suggestion in raw.get("suggestions", []):
                text = str(suggestion).strip()
                if text:
                    issues.append(CriticIssue(layer="llm", severity="info", message=f"Suggestion: {text}"))
        except Exception:  # noqa: BLE001
            # LLM layer is best-effort; never fail the pipeline
            issues.append(CriticIssue(
                layer="llm",
                severity="info",
                message="LLM review unavailable (model offline or timeout). Skipped.",
            ))

        return issues

    # ------------------------------------------------------------------ #
    # Scoring & Status                                                     #
    # ------------------------------------------------------------------ #

    def _compute_score(self, issues: list[CriticIssue]) -> float:
        penalty = 0.0
        for issue in issues:
            if issue.severity == "error":
                penalty += self._PENALTY_ERROR
            elif issue.severity == "warning":
                penalty += self._PENALTY_WARNING
            else:
                penalty += self._PENALTY_INFO
        return max(0.0, 1.0 - penalty)

    def _compute_status(
        self, score: float, issues: list[CriticIssue]
    ) -> Literal["approved", "needs_revision", "rejected"]:
        has_errors = any(i.severity == "error" for i in issues)
        if has_errors or score < self._REJECT_THRESHOLD:
            return "rejected"
        if score < self._REVISION_THRESHOLD:
            return "needs_revision"
        return "approved"

    @staticmethod
    def _build_suggestions(issues: list[CriticIssue]) -> list[str]:
        seen: set[str] = set()
        suggestions: list[str] = []
        for issue in issues:
            if issue.severity in {"error", "warning"} and issue.message not in seen:
                suggestions.append(f"Fix: {issue.message}")
                seen.add(issue.message)
        return suggestions

    @classmethod
    def _compound_nfr_concerns(cls, text: str) -> set[str]:
        return {
            label
            for label, pattern in cls._COMPOUND_NFR_CONCERNS.items()
            if pattern.search(text)
        }

    # ------------------------------------------------------------------ #
    # Cycle Detection (DFS)                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _detect_cycle(id_to_task: dict[str, Task]) -> list[str]:
        """Return a cycle path if one exists, otherwise empty list."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in id_to_task}
        parent: dict[str, str | None] = {tid: None for tid in id_to_task}

        def dfs(node: str) -> list[str]:
            color[node] = GRAY
            for dep in id_to_task[node].dependencies:
                if dep not in color:
                    continue
                if color[dep] == GRAY:
                    # Reconstruct cycle
                    cycle = [dep, node]
                    cur = node
                    while parent[cur] is not None and parent[cur] != dep:
                        cur = parent[cur]  # type: ignore[assignment]
                        cycle.append(cur)
                    cycle.append(dep)
                    return list(reversed(cycle))
                if color[dep] == WHITE:
                    parent[dep] = node
                    result = dfs(dep)
                    if result:
                        return result
            color[node] = BLACK
            return []

        for tid in id_to_task:
            if color[tid] == WHITE:
                result = dfs(tid)
                if result:
                    return result
        return []


def format_critic_report(report: CriticReport) -> str:
    """Return a human-readable summary of a CriticReport."""
    SEP = "=" * 62
    DIV = "-" * 62
    lines = [
        SEP,
        "  CRITIC AGENT  --  PHASE 2 VALIDATION REPORT",
        SEP,
        f"  Status  : {report.status.upper()}",
        f"  Score   : {report.score:.0%}",
        f"  Issues  : {len(report.issues)} "
        f"({sum(1 for i in report.issues if i.severity == 'error')} errors, "
        f"{sum(1 for i in report.issues if i.severity == 'warning')} warnings, "
        f"{sum(1 for i in report.issues if i.severity == 'info')} info)",
    ]

    if report.issues:
        lines.append("\n  ISSUES")
        lines.append(f"  {DIV}")
        icons = {"error": "[ERROR]", "warning": "[WARN]", "info": "[INFO]"}
        for issue in report.issues:
            icon = icons.get(issue.severity, "[ ? ]")
            lines.append(f"  [{issue.layer.upper()}] {icon} {issue.message}")

    if report.suggestions:
        lines.append("\n  SUGGESTIONS")
        lines.append(f"  {DIV}")
        for suggestion in report.suggestions:
            lines.append(f"  • {suggestion}")

    lines.append(SEP)
    return "\n".join(lines)
