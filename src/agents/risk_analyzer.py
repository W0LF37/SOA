from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Literal

from src.core.schemas import CriticReport, RiskItem, RiskReport, TaskList

if TYPE_CHECKING:
    from src.llm.ollama_client import OllamaClient


logger = logging.getLogger(__name__)


class RiskAnalyzer:
    """
    Phase 6 — Multi-dimensional risk analyzer for project plans.

    Six detection layers:
      1. Bottlenecks  — high-fanout tasks blocking downstream work
      2. Complexity   — complexity-5 tasks on the critical path
      3. Schedule     — coordination overhead, effort overrun
      4. Dependencies — inferred sequencing, long critical chains
      5. Resources    — role concentration, under-staffed complex tasks
      6. Quality      — poor critic score, unresolved plan errors

    Usage::

        analyzer = RiskAnalyzer()
        report = analyzer.analyze(task_list, plan_summary, critic_report)
        # report.risk_level  -> "low" | "medium" | "high" | "critical"
        # report.risk_score  -> 0.0 - 1.0  (higher = more risk)
        # report.risks       -> list[RiskItem]
    """

    _PENALTY_CRITICAL = 0.30
    _PENALTY_HIGH     = 0.15
    _PENALTY_MEDIUM   = 0.05
    _PENALTY_LOW      = 0.01

    _CRITICAL_THRESHOLD = 0.70
    _HIGH_THRESHOLD     = 0.40
    _MEDIUM_THRESHOLD   = 0.20

    def __init__(self, llm_client: "OllamaClient | None" = None) -> None:
        self._llm = llm_client

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def analyze(
        self,
        task_list: TaskList,
        plan_summary: dict,
        critic_report: CriticReport | None = None,
    ) -> RiskReport:
        """Run all detection layers and return a RiskReport."""
        risks: list[RiskItem] = []

        graph = plan_summary.get("graph_analytics", {})
        effort = plan_summary.get("effort_summary", {})
        team = plan_summary.get("team_allocation", [])
        assumption_log = (
            plan_summary.get("plan_highlights", {})
            .get("committee_brief", {})
            .get("assumption_log", [])
        )

        risks.extend(self._check_bottlenecks(task_list, graph))
        risks.extend(self._check_complexity(task_list, graph))
        risks.extend(self._check_schedule(graph, effort))
        risks.extend(self._check_dependencies(graph, assumption_log))
        risks.extend(self._check_resources(task_list, team))
        if critic_report is not None:
            risks.extend(self._check_quality(critic_report))
        if self._llm is not None:
            risks.extend(
                self._layer_llm(
                    task_list=task_list,
                    context={
                        "plan_summary": plan_summary,
                        "rule_risks": risks,
                    },
                )
            )

        score = self._compute_risk_score(risks)
        level = self._compute_risk_level(score)
        mitigations = self._build_mitigations(risks)

        return RiskReport(
            risk_level=level,
            risk_score=round(score, 3),
            total_risks=len(risks),
            risks=risks,
            mitigations=mitigations,
        )

    # ------------------------------------------------------------------ #
    # Layer 1: Bottlenecks                                                 #
    # ------------------------------------------------------------------ #

    def _check_bottlenecks(self, task_list: TaskList, graph: dict) -> list[RiskItem]:
        risks: list[RiskItem] = []
        by_id = {task.id: task for task in task_list.tasks}
        foundational_gates: list[tuple[dict, object]] = []

        for bt in graph.get("bottleneck_tasks", []):
            task_id = bt.get("id", "?")
            title = bt.get("title", "")
            blocks = bt.get("blocks", 0)
            task = by_id.get(task_id)

            if task is not None and self._is_foundational_quality_gate(task):
                foundational_gates.append((bt, task))
                continue

            if blocks >= 5:
                risks.append(RiskItem(
                    category="bottleneck",
                    severity="critical",
                    message=(
                        f"{task_id} '{title}' blocks {blocks} tasks"
                        " -- critical single point of failure"
                    ),
                    affected_tasks=[task_id],
                    mitigation="Split task or add a parallel implementation path",
                ))
            elif blocks >= 3:
                risks.append(RiskItem(
                    category="bottleneck",
                    severity="high",
                    message=f"{task_id} '{title}' blocks {blocks} downstream tasks",
                    affected_tasks=[task_id],
                    mitigation="Prioritize early delivery; unblock dependencies ASAP",
                ))

        if foundational_gates:
            gate_ids = [bt.get("id", "?") for bt, _task in foundational_gates]
            max_blocks = max(bt.get("blocks", 0) for bt, _task in foundational_gates)
            severity: Literal["medium", "high"] = "high" if max_blocks >= 5 else "medium"
            risks.append(RiskItem(
                category="bottleneck",
                severity=severity,
                message=(
                    f"Foundational NFR gates ({', '.join(gate_ids)}) collectively gate "
                    f"{max_blocks} downstream tasks and should be front-loaded early"
                ),
                affected_tasks=gate_ids,
                mitigation=(
                    "Schedule foundational NFR tasks as parallel early work and validate "
                    "them incrementally rather than treating each as an isolated blocker"
                ),
            ))
        return risks

    # ------------------------------------------------------------------ #
    # Layer 2: Complexity                                                  #
    # ------------------------------------------------------------------ #

    def _check_complexity(
        self, task_list: TaskList, graph: dict
    ) -> list[RiskItem]:
        risks: list[RiskItem] = []
        critical_path_ids = set(
            graph.get("critical_path", {}).get("task_ids", [])
        )

        for task in task_list.tasks:
            if task.complexity == 5:
                if task.id in critical_path_ids:
                    risks.append(RiskItem(
                        category="complexity",
                        severity="critical",
                        message=(
                            f"{task.id} '{task.title}' is complexity-5"
                            " AND on the critical path"
                        ),
                        affected_tasks=[task.id],
                        mitigation=(
                            "Assign a senior engineer; break into sub-tasks"
                        ),
                    ))
                else:
                    risks.append(RiskItem(
                        category="complexity",
                        severity="high",
                        message=(
                            f"{task.id} '{task.title}' has maximum complexity (5)"
                        ),
                        affected_tasks=[task.id],
                        mitigation="Decompose or assign a dedicated pair",
                    ))

        avg = graph.get("avg_complexity", 0.0)
        if avg > 3.5:
            risks.append(RiskItem(
                category="complexity",
                severity="medium",
                message=(
                    f"Average task complexity is {avg:.1f}/5"
                    " -- high overall technical risk"
                ),
                mitigation="Review scope or add buffer time to sprint estimates",
            ))
        return risks

    # ------------------------------------------------------------------ #
    # Layer 3: Schedule                                                    #
    # ------------------------------------------------------------------ #

    def _check_schedule(self, graph: dict, effort: dict) -> list[RiskItem]:
        risks: list[RiskItem] = []

        parallel_groups = graph.get("parallel_groups", [])
        if parallel_groups:
            largest = max(len(g) for g in parallel_groups)
            if largest >= 7:
                risks.append(RiskItem(
                    category="schedule",
                    severity="medium",
                    message=(
                        f"{largest} tasks can start simultaneously"
                        " -- high coordination overhead in first sprint"
                    ),
                    mitigation="Assign clear task owners before sprint starts",
                ))

        total_hours = effort.get("total_estimated_hours", 0)
        if total_hours > 300:
            risks.append(RiskItem(
                category="schedule",
                severity="critical",
                message=(
                    f"Total effort {total_hours}h is very high -- delivery risk"
                ),
                mitigation=(
                    "Reduce scope to MVP or extend timeline significantly"
                ),
            ))
        elif total_hours > 200:
            risks.append(RiskItem(
                category="schedule",
                severity="high",
                message=(
                    f"Total effort {total_hours}h may exceed team capacity"
                ),
                mitigation="Review scope or negotiate timeline with stakeholders",
            ))

        nfr_h = effort.get("nfr_estimated_hours", 0)
        fr_h = effort.get("fr_estimated_hours", 0)
        if nfr_h > fr_h > 0:
            risks.append(RiskItem(
                category="schedule",
                severity="medium",
                message=(
                    f"NFR work ({nfr_h}h) exceeds FR work ({fr_h}h)"
                    " -- quality engineering dominates timeline"
                ),
                mitigation=(
                    "Consider deferring lower-priority NFR tasks to a later phase"
                ),
            ))
        return risks

    # ------------------------------------------------------------------ #
    # Layer 4: Dependencies                                                #
    # ------------------------------------------------------------------ #

    def _check_dependencies(
        self, graph: dict, assumption_log: list
    ) -> list[RiskItem]:
        risks: list[RiskItem] = []

        if any("inferred" in str(entry).lower() for entry in assumption_log):
            risks.append(RiskItem(
                category="dependency",
                severity="medium",
                message=(
                    "Dependency sequencing was inferred for some tasks"
                    " -- not explicitly stated in requirements"
                ),
                mitigation=(
                    "Verify inferred dependencies with stakeholders before sprint"
                ),
            ))

        cp = graph.get("critical_path", {})
        cp_length = cp.get("length", 0)
        if cp_length > 5:
            risks.append(RiskItem(
                category="dependency",
                severity="high",
                message=(
                    f"Critical path spans {cp_length} tasks"
                    " -- any delay cascades to project end"
                ),
                affected_tasks=cp.get("task_ids", []),
                mitigation="Add parallel tracks or fast-track critical path tasks",
            ))
        return risks

    # ------------------------------------------------------------------ #
    # Layer 5: Resources                                                   #
    # ------------------------------------------------------------------ #

    def _check_resources(
        self, task_list: TaskList, team: list
    ) -> list[RiskItem]:
        risks: list[RiskItem] = []

        if team:
            total_h = sum(r.get("estimated_hours", 0) for r in team)
            if total_h > 0:
                for role_data in team:
                    role = role_data.get("role", "Unknown")
                    h = role_data.get("estimated_hours", 0)
                    pct = h / total_h
                    if pct > 0.60:
                        risks.append(RiskItem(
                            category="resource",
                            severity="high",
                            message=(
                                f"{role} carries {pct:.0%} of total effort"
                                " -- resource concentration risk"
                            ),
                            mitigation=(
                                "Cross-train team members or redistribute workload"
                            ),
                        ))

        for task in task_list.tasks:
            if task.complexity >= 4 and task.recommended_team_size == 1:
                risks.append(RiskItem(
                    category="resource",
                    severity="medium",
                    message=(
                        f"{task.id} has complexity {task.complexity}"
                        " but is assigned to a single person"
                    ),
                    affected_tasks=[task.id],
                    mitigation="Assign a pair or dedicated reviewer for this task",
                ))
        return risks

    # ------------------------------------------------------------------ #
    # Layer 6: Quality (Critic Report)                                     #
    # ------------------------------------------------------------------ #

    def _check_quality(self, critic_report: CriticReport) -> list[RiskItem]:
        risks: list[RiskItem] = []

        if critic_report.status == "rejected":
            risks.append(RiskItem(
                category="quality",
                severity="critical",
                message=(
                    "Plan was REJECTED by the Critic Agent -- do not proceed"
                ),
                mitigation=(
                    "Resolve all critic errors before starting any implementation"
                ),
            ))
        elif critic_report.status == "needs_revision":
            risks.append(RiskItem(
                category="quality",
                severity="high",
                message="Plan needs revision according to the Critic Agent",
                mitigation="Address all warnings before committing to estimates",
            ))

        if critic_report.score < 0.80:
            risks.append(RiskItem(
                category="quality",
                severity="high",
                message=(
                    f"Plan quality score is {critic_report.score:.0%}"
                    " -- below acceptable threshold (80%)"
                ),
                mitigation="Review and resolve all critic issues",
            ))

        for err in (i for i in critic_report.issues if i.severity == "error"):
            risks.append(RiskItem(
                category="quality",
                severity="critical",
                message=f"Unresolved plan error: {err.message}",
                mitigation="Fix this error before any implementation begins",
            ))
        return risks

    @staticmethod
    def _is_foundational_quality_gate(task) -> bool:  # noqa: ANN001
        if task.req_type != "NFR":
            return False
        text = f"{task.title} {task.description}"
        return re.search(
            r"\b(availability|uptime|reliab\w*|encrypt(?:ed|ion)?|security|mobile[\-\s]?friendly|"
            r"accessibility|peak-load|peak load|responsive performance|latency|throughput)\b",
            text,
            flags=re.IGNORECASE,
        ) is not None

    # ------------------------------------------------------------------ #
    # Layer 7: LLM novelty pass                                            #
    # ------------------------------------------------------------------ #

    def _layer_llm(self, task_list: TaskList, context: dict) -> list[RiskItem]:
        if self._llm is None:
            return []

        rule_risks: list[RiskItem] = list(context.get("rule_risks", []))
        summary = "; ".join(
            f"{risk.category}:{risk.severity}:{risk.message}"
            for risk in rule_risks[:8]
        ) or "No rule-based risks identified."
        task_snapshot = [
            {
                "id": task.id,
                "title": task.title,
                "type": task.req_type,
                "complexity": task.complexity,
                "hours": task.estimated_hours,
                "dependencies": task.dependencies,
            }
            for task in task_list.tasks[:20]
        ]
        prompt = (
            f"Given these {len(task_list.tasks)} tasks with risk summary: {summary}\n"
            "Identify 2-3 novel risks NOT already captured. Reply as strict JSON in this shape:\n"
            '{"risks":[{"category":"string","severity":"high","description":"string","mitigation":"string"}]}\n'
            f"Tasks:\n{task_snapshot}"
        )

        try:
            payload = self._llm.generate_json(prompt, strict_json_only=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RiskAnalyzer LLM layer failed: %s", exc)
            return []

        items = payload.get("risks", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return []

        known_messages = {risk.message.strip().lower() for risk in rule_risks}
        llm_risks: list[RiskItem] = []
        for item in items[:3]:
            if not isinstance(item, dict):
                continue
            description = str(item.get("description", "")).strip()
            if not description or description.lower() in known_messages:
                continue
            severity = str(item.get("severity", "medium")).strip().lower()
            if severity not in {"high", "medium"}:
                severity = "medium"
            category = str(item.get("category", "quality")).strip().lower() or "quality"
            llm_risks.append(
                RiskItem(
                    category=category,
                    severity=severity,
                    message=description,
                    mitigation=str(item.get("mitigation", "")).strip(),
                    source="llm",
                )
            )
            known_messages.add(description.lower())
        return llm_risks

    # ------------------------------------------------------------------ #
    # Scoring & Level                                                      #
    # ------------------------------------------------------------------ #

    def _compute_risk_score(self, risks: list[RiskItem]) -> float:
        penalty_map = {
            "critical": self._PENALTY_CRITICAL,
            "high":     self._PENALTY_HIGH,
            "medium":   self._PENALTY_MEDIUM,
            "low":      self._PENALTY_LOW,
        }
        return min(1.0, sum(penalty_map[r.severity] for r in risks))

    def _compute_risk_level(self, score: float) -> str:
        if score >= self._CRITICAL_THRESHOLD:
            return "critical"
        if score >= self._HIGH_THRESHOLD:
            return "high"
        if score >= self._MEDIUM_THRESHOLD:
            return "medium"
        return "low"

    @staticmethod
    def _build_mitigations(risks: list[RiskItem]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for r in risks:
            if r.severity in {"critical", "high"} and r.mitigation not in seen:
                result.append(f"[{r.severity.upper()}] {r.mitigation}")
                seen.add(r.mitigation)
        return result


def format_risk_report(report: RiskReport) -> str:
    """Return a human-readable summary of a RiskReport."""
    SEP = "=" * 62
    DIV = "-" * 62
    level_icons = {
        "low":      "[LOW]     ",
        "medium":   "[MEDIUM]  ",
        "high":     "[HIGH]    ",
        "critical": "[CRITICAL]",
    }
    sev_icons = {"critical": "[!!!]", "high": "[!] ", "medium": "[~] ", "low": "[ ] "}
    cat_pad = {
        "bottleneck": "BOTTLENECK",
        "complexity": "COMPLEXITY",
        "schedule":   "SCHEDULE  ",
        "dependency": "DEPENDENCY",
        "resource":   "RESOURCE  ",
        "quality":    "QUALITY   ",
    }

    icon = level_icons.get(report.risk_level, "[?]")
    lines = [
        SEP,
        "  RISK ANALYZER  --  PHASE 6 RISK REPORT",
        SEP,
        f"  Risk Level : {icon} {report.risk_level.upper()}",
        f"  Risk Score : {report.risk_score:.0%}",
        f"  Total Risks: {report.total_risks}",
    ]

    by_sev: dict[str, list[RiskItem]] = {
        "critical": [], "high": [], "medium": [], "low": []
    }
    for r in report.risks:
        by_sev[r.severity].append(r)

    for sev in ("critical", "high", "medium", "low"):
        items = by_sev[sev]
        if not items:
            continue
        lines.append(f"\n  {sev.upper()} RISKS ({len(items)})")
        lines.append(f"  {DIV}")
        for r in items:
            s_icon = sev_icons.get(r.severity, "[?]")
            cat = cat_pad.get(r.category, r.category.upper().ljust(10))
            lines.append(f"  {s_icon} [{cat}] {r.message}")

    if report.mitigations:
        lines.append(f"\n  MITIGATIONS")
        lines.append(f"  {DIV}")
        for m in report.mitigations:
            lines.append(f"  > {m}")

    lines.append(SEP)
    return "\n".join(lines)
