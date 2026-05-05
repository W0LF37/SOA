from __future__ import annotations

from collections import Counter, defaultdict
import re

from src.agents.planner import PlannerAgent, RequirementItem
from src.core.schemas import TaskList


class BriefGenerator:
    """Produce committee-ready narrative and allocation summaries."""

    KNOWN_SERVICES = (
        "Google OAuth",
        "Apple Sign-In",
        "Google Calendar",
        "Outlook Calendar",
        "Stripe",
        "PayPal",
        "Twilio",
        "AWS",
        "Azure",
        "GCP",
    )
    DOMAIN_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "hospital operations and clinical workflow management",
            (
                r"\bpatient\b",
                r"\bdoctor\b",
                r"\bnurse\b",
                r"\bclinic\b",
                r"\bhospital\b",
                r"\behr\b",
                r"\bemr\b",
                r"\blab\b",
                r"\bradiology\b",
                r"\bpharmacy\b",
                r"\badmission\b",
                r"\bdischarge\b",
                r"\btriage\b",
            ),
        ),
        (
            "education and learning management",
            (
                r"\bstudents?\b",
                r"\bteachers?\b",
                r"\binstructors?\b",
                r"\bcourses?\b",
                r"\bquizzes?\b",
                r"\blms\b",
                r"\blearning\b",
                r"\bcertificates?\b",
                r"\benroll(?:ment|s|ed)?\b",
                r"\btranscripts?\b",
                r"\bfaculty\b",
                r"\btuition\b",
                r"\bgrades?\b",
            ),
        ),
        (
            "fintech, payments, and billing operations",
            (
                r"\bkyc\b",
                r"\bwallet\b",
                r"\bbank(?:ing)?\b",
                r"\baccount balances?\b",
                r"\btransaction history\b",
                r"\btransfer funds?\b",
                r"\bfund transfers?\b",
                r"\bbill payments?\b",
                r"\bqr codes?\b",
                r"\bbiometric\b",
                r"\b2fa\b",
                r"\bmfa\b",
                r"\bpayment gateway\b",
                r"\bstripe\b",
                r"\bpaypal\b",
                r"\binvoices?\b",
                r"\bbilling\b",
                r"\bsubscription\b",
                r"\bpci\b",
                r"\bsettlement\b",
                r"\bdunning\b",
                r"\bfraud\b",
                r"\b3ds\b",
            ),
        ),
        (
            "CRM and sales operations",
            (
                r"\bcrm\b",
                r"\bleads?\b",
                r"\bsales\b",
                r"\bpipeline\b",
                r"\bcontact\b",
                r"\bcampaign\b",
                r"\bforecasts?\b",
                r"\bopportunit(?:y|ies)\b",
            ),
        ),
        (
            "commerce and transactional order management",
            (
                r"\be-?commerce\b",
                r"\bcarts?\b",
                r"\bcheckout\b",
                r"\bcatalog\b",
                r"\borders?\b",
                r"\bshipping\b",
                r"\binventory\b",
                r"\bproducts?\b",
            ),
        ),
        (
            "IoT monitoring and device operations",
            (
                r"\biot\b",
                r"\bsensors?\b",
                r"\bdevices?\b",
                r"\bmqtt\b",
                r"\btelemetry\b",
                r"\bthreshold\b",
                r"\breal[- ]time alert\b",
            ),
        ),
        (
            "HR and employee operations",
            (
                r"\bhr\b",
                r"\bemployee\b",
                r"\bpayroll\b",
                r"\bleave\b",
                r"\battendance\b",
                r"\brecruitment\b",
                r"\bperformance review\b",
            ),
        ),
        (
            "library and borrowing management",
            (
                r"\blibrary\b",
                r"\bbook\b",
                r"\bborrow\b",
                r"\bloan\b",
                r"\bopac\b",
                r"\bmember\b",
                r"\bdue date\b",
            ),
        ),
        (
            "social platform and content moderation",
            (
                r"\bsocial\b",
                r"\bfeed\b",
                r"\bfollow\b",
                r"\blike\b",
                r"\bcomment\b",
                r"\bmoderation\b",
                r"\bpost\b",
            ),
        ),
        (
            "AI-assisted planning and engineering workflow orchestration",
            (
                r"\bplanner\b",
                r"\bcritic\b",
                r"\bdependency graph\b",
                r"\btask generation\b",
                r"\bestimation\b",
                r"\brisk prediction\b",
                r"\borchestration engine\b",
                r"\bllm\b",
                r"\bknowledge base\b",
            ),
        ),
    )

    @classmethod
    def build(
        cls,
        task_list: TaskList,
        requirements: list[RequirementItem],
        graph_stats: dict[str, object],
        sprint_plan: list[dict[str, object]],
    ) -> dict[str, object]:
        effort_summary = cls._effort_summary(task_list)
        team_allocation = cls._team_allocation(task_list)
        risk_register = cls._risk_register(task_list)
        graph_summary = cls._committee_brief(
            task_list=task_list,
            requirements=requirements,
            graph_stats=graph_stats,
            sprint_plan=sprint_plan,
            effort_summary=effort_summary,
        )
        committee_brief = {
            "domain_inference": cls._domain_inference(task_list, requirements),
            "scope_assessment": cls._scope_assessment(task_list),
            "ambiguity_register": cls.build_ambiguity_register(task_list),
            "assumption_log": cls.build_assumption_log(task_list, requirements),
            "confidence_signal": cls._confidence_signal(task_list),
            "graph_summary": graph_summary,
        }
        return {
            "committee_brief": committee_brief,
            "effort_summary": effort_summary,
            "team_allocation": team_allocation,
            "risk_register": risk_register,
        }

    @staticmethod
    def build_ambiguity_register(task_list: TaskList) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for task in task_list.tasks:
            title = task.title or ""
            if "UNCLEAR" in title:
                reason = "Task title is unclear and requires clarification of the missing object or scope."
            elif task.optional and task.confidence == "low":
                reason = "Task was marked optional and low-confidence because the source wording was hedged or future-scoped."
            elif task.confidence == "low":
                reason = "Task remains low-confidence and should be clarified before committing to delivery."
            else:
                continue
            entries.append(
                {
                    "task_id": task.id,
                    "reason": reason,
                    "original_source": task.source,
                }
            )
        return entries

    @classmethod
    def build_assumption_log(
        cls,
        task_list: TaskList,
        requirements: list[RequirementItem],
    ) -> list[str]:
        assumptions: list[str] = []
        requirement_text = " ".join(req.text.lower() for req in requirements)
        role_mentions = {
            role
            for role in ("admin", "doctor", "patient", "receptionist", "lab", "nurse", "pharmacist")
            if re.search(rf"\b{re.escape(role)}(?:s| staff| technician)?\b", requirement_text)
        }
        access_control_tasks = [
            task for task in task_list.tasks
            if "access_control" in PlannerAgent._extract_semantic_tags(task.description)
            or re.search(r"\b(role|permission|access control)\b", task.title, flags=re.IGNORECASE)
        ]
        if len(role_mentions) >= 2 and access_control_tasks:
            assumptions.append(
                "RBAC and permission boundaries were inferred as a structural control because multiple user roles appear in the source requirements."
            )

        optional_tasks = [
            task for task in task_list.tasks
            if task.optional or task.confidence == "low"
        ]
        if optional_tasks:
            assumptions.append(
                f"{len(optional_tasks)} task(s) were marked optional or low-confidence because the planner detected hedge or future-scope language in the source text."
            )

        dependent_tasks = [task for task in task_list.tasks if task.dependencies]
        if dependent_tasks:
            assumptions.append(
                f"Dependency sequencing was inferred for {len(dependent_tasks)} task(s) to produce an executable implementation order beyond the raw prose order."
            )

        unclear_tasks = [task for task in task_list.tasks if "UNCLEAR" in task.title]
        if unclear_tasks:
            assumptions.append(
                f"{len(unclear_tasks)} task(s) were left explicitly unclear because the source wording did not name a specific object or deliverable."
            )

        return assumptions

    @staticmethod
    def _effort_summary(task_list: TaskList) -> dict[str, int]:
        total_hours = sum(task.estimated_hours or 0 for task in task_list.tasks)
        fr_hours = sum(
            task.estimated_hours or 0 for task in task_list.tasks if task.req_type == "FR"
        )
        nfr_hours = total_hours - fr_hours
        return {
            "total_estimated_hours": total_hours,
            "total_estimated_days": max(1, (total_hours + 7) // 8) if total_hours else 0,
            "fr_estimated_hours": fr_hours,
            "nfr_estimated_hours": nfr_hours,
        }

    @classmethod
    def _team_allocation(cls, task_list: TaskList) -> list[dict[str, object]]:
        grouped: dict[str, list] = defaultdict(list)
        for task in task_list.tasks:
            grouped[task.suggested_owner_role or "Backend Engineer"].append(task)

        allocations: list[dict[str, object]] = []
        for role, tasks in sorted(
            grouped.items(),
            key=lambda item: -sum(task.estimated_hours or 0 for task in item[1]),
        ):
            theme_counter: Counter[str] = Counter()
            for task in tasks:
                theme_counter.update(
                    tag
                    for tag in PlannerAgent._extract_semantic_tags(task.description)
                    if tag != "general"
                )
            dominant_themes = [theme for theme, _ in theme_counter.most_common(3)]
            allocations.append(
                {
                    "role": role,
                    "task_ids": [task.id for task in tasks],
                    "task_count": len(tasks),
                    "estimated_hours": sum(task.estimated_hours or 0 for task in tasks),
                    "focus": ", ".join(
                        PlannerAgent._friendly_theme_label(theme)
                        for theme in dominant_themes
                    ) or "general delivery",
                }
            )
        return allocations

    @staticmethod
    def _risk_register(task_list: TaskList) -> list[dict[str, object]]:
        risk_counter: Counter[str] = Counter()
        risk_tasks: dict[str, list[str]] = defaultdict(list)
        for task in task_list.tasks:
            for risk in task.risks:
                risk_counter[risk] += 1
                risk_tasks[risk].append(task.id)

        return [
            {
                "risk": risk,
                "task_count": count,
                "task_ids": sorted(risk_tasks[risk]),
            }
            for risk, count in risk_counter.most_common(8)
        ]

    @classmethod
    def _domain_inference(
        cls,
        task_list: TaskList,
        requirements: list[RequirementItem],
    ) -> str:
        text = " ".join(
            [req.text for req in requirements] + [f"{task.title} {task.description}" for task in task_list.tasks]
        ).lower()
        domain_scores = cls._domain_scores(text)
        if domain_scores:
            domain, score = domain_scores.most_common(1)[0]
            if score >= 2:
                return f"Likely domain: {domain}."
        return "Likely domain: multi-role business workflow application."

    @classmethod
    def _domain_scores(cls, text: str) -> Counter[str]:
        scores: Counter[str] = Counter()
        for domain, patterns in cls.DOMAIN_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, text):
                    scores[domain] += 1
        return scores

    @staticmethod
    def _scope_assessment(task_list: TaskList) -> str:
        fr_count = sum(1 for task in task_list.tasks if task.req_type == "FR")
        nfr_count = len(task_list.tasks) - fr_count
        optional_count = sum(1 for task in task_list.tasks if task.optional or task.confidence == "low")
        return (
            f"Scope includes {fr_count} functional task(s) and {nfr_count} non-functional task(s); "
            f"{optional_count} task(s) sit outside the confirmed baseline because they are optional or low-confidence."
        )

    @staticmethod
    def _confidence_signal(task_list: TaskList) -> str:
        low_confidence = [task for task in task_list.tasks if task.confidence == "low"]
        unclear = [task for task in task_list.tasks if "UNCLEAR" in task.title]
        if not low_confidence:
            return "Planning confidence is high: no low-confidence tasks were detected in the current plan."
        if unclear:
            return (
                f"Planning confidence is moderate: {len(low_confidence)} low-confidence task(s) exist, "
                f"including {len(unclear)} task(s) that still require clarification."
            )
        return f"Planning confidence is moderate: {len(low_confidence)} task(s) remain low-confidence and should be reviewed before commitment."

    @classmethod
    def _committee_brief(
        cls,
        task_list: TaskList,
        requirements: list[RequirementItem],
        graph_stats: dict[str, object],
        sprint_plan: list[dict[str, object]],
        effort_summary: dict[str, int],
    ) -> str:
        task_lookup = {task.id: task for task in task_list.tasks}
        cp_ids = graph_stats.get("critical_path", {}).get("task_ids", [])
        cp_points = sum(task_lookup[task_id].complexity for task_id in cp_ids if task_id in task_lookup)
        total_weeks = sum(item.get("duration_weeks", 0) for item in sprint_plan)
        top_bottleneck = graph_stats.get("bottleneck_tasks", [{}])[0]
        bottleneck_sprint = cls._task_sprint_map(sprint_plan).get(top_bottleneck.get("id"))
        parallel_start = len(sprint_plan[0]["tasks"]) if sprint_plan else 0
        services = cls._external_services(task_list)
        integration_sprint = cls._first_integration_sprint(task_list, sprint_plan)
        offline_count = sum(
            1
            for task in task_list.tasks
            if "offline_operation" in PlannerAgent._extract_semantic_tags(task.description)
        )

        sentences = [
            f"{len(requirements)} requirements -> {len(task_list.tasks)} atomic tasks across {len(sprint_plan)} delivery sprints.",
            (
                "Critical delivery path: "
                f"{' -> '.join(cp_ids) or 'core workflow'} "
                f"({len(cp_ids)} hops, ~{cp_points} story points, estimated {total_weeks} weeks with a 2-person team)."
            ),
            (
                "Coordination hotspot: "
                f"{top_bottleneck.get('title', top_bottleneck.get('id', 'Top bottleneck'))} "
                f"blocks {top_bottleneck.get('blocks', 0)} downstream tasks"
                + (
                    f" and should be closed by Sprint {bottleneck_sprint}."
                    if bottleneck_sprint
                    else "."
                )
            ),
            f"Parallel execution opportunity: {parallel_start} tasks can start immediately in Sprint 1.",
        ]

        if offline_count:
            sentences.append(
                "Operational constraint: "
                f"{offline_count} offline requirement"
                + ("s" if offline_count != 1 else "")
                + " should be validated for secure caching, synchronization, and recovery behavior before release."
            )

        if services:
            services_text = ", ".join(services[:4])
            if len(services) > 4:
                services_text += ", ..."
            sentences.append(
                "External dependencies: "
                f"{len(services)} third-party services ({services_text})"
                + (
                    f" should be contract-ready before Sprint {integration_sprint}."
                    if integration_sprint
                    else "."
                )
            )

        sentences.append(
            "Effort breakdown: "
            f"{effort_summary['total_estimated_hours']} estimated hours | "
            f"FR: {effort_summary['fr_estimated_hours']}h | "
            f"NFR: {effort_summary['nfr_estimated_hours']}h."
        )
        return " ".join(sentences)

    @staticmethod
    def _task_sprint_map(sprint_plan: list[dict[str, object]]) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for sprint in sprint_plan:
            for task_id in sprint.get("tasks", []):
                mapping[task_id] = int(sprint["sprint"])
        return mapping

    @classmethod
    def _first_integration_sprint(
        cls,
        task_list: TaskList,
        sprint_plan: list[dict[str, object]],
    ) -> int | None:
        task_to_sprint = cls._task_sprint_map(sprint_plan)
        for task in task_list.tasks:
            if "integration" in PlannerAgent._extract_semantic_tags(task.description):
                return task_to_sprint.get(task.id)
        return None

    @classmethod
    def _external_services(cls, task_list: TaskList) -> list[str]:
        found: list[str] = []
        haystacks = [
            f"{task.title} {task.description}".lower()
            for task in task_list.tasks
        ]
        for service in cls.KNOWN_SERVICES:
            if any(service.lower() in haystack for haystack in haystacks):
                found.append(service)
        return found
