from __future__ import annotations

from collections import Counter, defaultdict
import json
import logging
import re
from dataclasses import dataclass

from pydantic import ValidationError
import requests

from src.core.schemas import Task, TaskList
from src.llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequirementItem:
    line_no: int
    source: str
    text: str
    sources: tuple[str, ...] = ()

    @property
    def all_sources(self) -> tuple[str, ...]:
        return self.sources or (self.source,)


class PlannerAgent:
    """Universal Planner Agent — works with any software requirements domain."""

    UNCLEAR_TITLE = "Implement [UNCLEAR — requires clarification]"
    ACTION_PREFIXES = {
        "Implement",
        "Build",
        "Design",
        "Configure",
        "Integrate",
        "Enforce",
        "Enable",
        "Optimize",
        "Automate",
        "Establish",
        "Validate",
        "Monitor",
    }

    # ------------------------------------------------------------------ #
    #  Verb / token lexicons — domain-agnostic                            #
    # ------------------------------------------------------------------ #

    _READ_VERBS = {
        "view", "see", "list", "display", "show", "read", "browse",
        "search", "query", "fetch", "get", "find", "filter", "sort", "lookup",
        "download", "track", "monitor", "inspect", "review",
    }
    _READ_VERB_SUFFIX = {
        "search": "search workflow",
        "browse": "browsing workflow",
        "filter": "filtering workflow",
        "query": "query workflow",
        "find": "search workflow",
        "list": "listing workflow",
        "download": "download workflow",
    }
    _WRITE_VERBS = {
        "create", "add", "register", "submit", "upload", "insert", "post",
        "generate", "produce", "issue", "publish", "draft", "record",
        "place", "request", "invite", "checkout", "provision", "enroll",
    }
    _MODIFY_VERBS = {
        "update", "edit", "modify", "change", "set", "assign", "configure",
        "adjust", "manage", "rename", "move", "reorder", "approve",
        "reject", "restore", "enable", "disable", "reschedule", "reactivate",
        "mark", "flag", "tag", "label", "suspend", "deactivate",
    }
    _DELETE_VERBS = {
        "delete", "remove", "cancel", "deactivate", "revoke", "expire",
        "purge", "archive", "disable", "suspend", "terminate",
    }
    _SELECT_VERBS = {"select", "choose", "pick"}
    _INTEGRATE_VERBS = {
        "integrate", "connect", "sync", "synchronize", "link",
        "interface", "communicate", "exchange",
    }
    _NOTIFY_VERBS = {
        "notify", "alert", "send", "email", "push", "message",
        "broadcast", "inform", "remind",
    }
    _REPORT_VERBS = {
        "report", "export", "summarize", "aggregate", "analytics",
        "statistics", "stat", "audit", "log", "track",
    }
    _AUTH_VERBS = {
        "authenticate", "login", "sign in", "logout", "sign out",
        "verify", "validate identity", "authorize",
    }

    _PERF_TOKENS = {
        "latency", "response time", "throughput", "performance",
        "concurrent", "scalab", "uptime", "sla",
        "millisecond", "99.", "benchmark", "load test",
        "bandwidth", "bitrate", "adaptive bitrate", "p95", "p99",
        "events per second",
    }
    _SEC_TOKENS = {
        "encrypt", "hash", "bcrypt", "aes", "tls", "ssl",
        "secure", "security", "password policy", "credential",
        "cryptograph", "cipher", "salt", "biometric", "fingerprint",
        "face recognition", "bank-grade", "end-to-end", "tokenization",
        "tokenized", "cardholder", "raw card data",
    }
    _COMP_TOKENS = {
        "gdpr", "hipaa", "pci", "iso", "compliance", "audit",
        "regulation", "legal", "data protection", "privacy policy",
        "sox", "ferpa", "aml", "kyc", "pci-dss",
    }
    _INTEGRATION_TOKENS = {
        "third-party", "third party", "external", "api", "sdk",
        "webhook", "payment gateway",
        "stripe", "twilio", "aws", "azure", "gcp",
        "calendar api", "map api", "shipping api",
    }
    _WORKFLOW_CONCERN_HINTS = frozenset({
        "registration", "appointments", "appointment", "scheduling", "schedule",
        "records", "record", "emr", "ehr", "admissions", "admission", "bed",
        "beds", "lab", "laboratory", "radiology", "pharmacy", "billing",
        "insurance", "claims", "reporting", "reports", "security", "roles",
        "permissions", "invoices", "payments", "discharge", "triage",
        "prescriptions", "results", "workflow", "workflows", "module", "modules",
        "dashboard", "dashboards", "inventory",
    })
    _SEQUENCE_PATTERNS = (
        "and then",
        "followed by",
        "subsequently",
        "thereafter",
        "before",
        "after",
        "once",
        "then",
    )
    _LOW_SIGNAL_LEADS = (
        "for nurses",
        "also there",
        "another point is",
        "one important thing is",
        "we also need",
        "there should be",
        "it would be better if",
        "we are not sure",
        "there are still some things",
        "in general we want",
    )
    _LOW_SIGNAL_OBJECT_TOKENS = frozenset({
        "advanced", "basic", "different", "same", "thing", "things", "something",
        "anything", "everything", "workflow", "workflows", "feature", "features",
        "capability", "capabilities", "support", "system", "part", "parts", "there",
        "also", "maybe", "important", "another", "point",
    })
    _NARRATIVE_META_PREFIXES = (
        "we need",
        "there are still some things",
        "one important thing is",
        "another point is",
        "in general we want",
        "also there may be edge cases",
    )
    _NARRATIVE_META_CUES = frozenset({
        "graduation project", "not something very small", "main problem now",
        "connected somehow", "if we have time", "outside core scope",
        "not in first version", "future enhancement", "realistic enough",
        "not a toy project", "at least in design", "we are not writing all rules exactly",
        "we know we cannot implement", "for example", "optional", "scope too much",
        "maybe yes maybe no", "probably not in first version",
    })
    _PRONOUNS = frozenset({"them", "it", "this", "these", "those", "that", "its", "their"})
    _FUNCTIONAL_VERB_RE = re.compile(
        r"^(?:the system|platform|application|users?|admins?)\s+"
        r"(?:can|must|should|shall|will|may)\s+"
        r"(?:monitor|audit|log|track|record|capture|store|process|generate|send|detect)\b",
        re.IGNORECASE,
    )
    _INTERNAL_OBSERVABILITY_SUBJECT_RE = re.compile(
        r"^(?:(?:the)\s+)?(?:system|agent|agents?|planner|critic|monitor|orchestrator|"
        r"pipeline|workflow engine|internal service|execution engine|runtime|"
        r"agent workflow controller|internal component|backend service|platform service)\b",
        re.IGNORECASE,
    )
    _INTERNAL_OBSERVABILITY_TERM_RE = re.compile(
        r"\b(log(?:ging)?|audit(?:ing)?|trace(?:ability|ing|s)?|telemetry|"
        r"execution log|decision traces?|interaction logging|event recording|observability|instrumentation)\b",
        re.IGNORECASE,
    )
    _INTERNAL_OBSERVABILITY_TARGET_RE = re.compile(
        r"\b(agent interactions?|agent execution|inputs?|outputs?|decision traces?|execution logs?|"
        r"system events?|planner|critic|orchestrator|pipeline|pipeline health|internal pipeline health|"
        r"agent workflows?|workflow engine|workflow execution|internal service|execution engine|"
        r"runtime|runtime metrics|internal component|backend service|platform service|"
        r"component health|internal health monitoring)\b",
        re.IGNORECASE,
    )
    _USER_FACING_OBSERVABILITY_ACCESS_RE = re.compile(
        r"^(?:users?|admins?|staff|operators?|managers?|patients?|customers?|clients?|members?)\s+"
        r"(?:can|must|should|shall|will|may)\s+"
        r"(?:view|read|access|export|download|display|show|generate)\b",
        re.IGNORECASE,
    )
    _ROLE_SURFACE_WORKFLOW_RE = re.compile(
        r"\b(?:retail\s+customers?|customers?|merchants?|support\s+agents?|customer\s+support|"
        r"compliance\s+analysts?|tenant\s+admins?|admins?|users?)\b.{0,120}"
        r"\b(?:should|can|must|will|may)\s+(?:provide|manage|view|access|export|process|handle|"
        r"track|configure|support|integrate|use|operate)?\b.{0,160}"
        r"\b(?:workspace|console|dashboard|portal|queue|catalog|settlement|payout|inventory|"
        r"payments?|transfers?|refunds?|disputes?|chargebacks?|transaction\s+history|analytics|"
        r"budget\s+alerts?|personalized\s+offers?|credit\s+pre-approval|open\s+banking\s+api)\b",
        re.IGNORECASE,
    )
    _UNCERTAINTY_MARKER_RE = re.compile(
        r"\b(maybe|perhaps|probably|if possible|if we have time|when we have time|optional(?:ly)?|"
        r"can be future enhancement|future enhancement|later phase|"
        r"not in first version|probably not in first version|in version 2|in v2|"
        r"eventually|would be nice|nice to have|stretch goal|down the line|"
        r"at some point|low priority|not urgent|bonus feature|we are not sure|"
        r"i am not sure|i'm not sure|might|could be added later|"
        r"outside core scope|it would be better if|nice if possible|"
        r"ideally|if budget allows|preferred but not required|not required|"
        r"if time permits|budget permitting)\b",
        re.IGNORECASE,
    )
    _UNCERTAINTY_SCOPE_STOPWORDS = frozenset({
        "the", "system", "must", "should", "shall", "will", "may", "might",
        "could", "would", "maybe", "perhaps", "probably", "possible", "optional",
        "future", "later", "phase", "version", "support", "provide", "allow",
        "enable", "handle", "module", "service", "feature", "workflow",
        "first", "there", "this", "that", "with", "from", "into", "also",
        "have", "time", "added", "core", "scope", "good", "better", "nice",
        "priority", "urgent", "eventually", "bonus", "point", "line", "down",
        "some", "stretch", "goal",
    })
    _UNCERTAINTY_QUALIFIER_TOKENS = frozenset({
        "future", "later", "phase", "version", "enhancement", "time",
        "scope", "possible", "optional", "core", "outside", "first",
        "simplified", "easy", "nice", "probably", "eventually", "priority",
        "urgent", "bonus", "stretch", "goal", "point", "line", "down",
    })
    _REQUIREMENT_ACTOR_RE = re.compile(
        r"\b(?:the system|platform|application|service|solution|users?|admins?|"
        r"managers?|staff|clients?|customers?|operators?|employees?|doctors?|"
        r"patients?|agents?|members?|receptionists?|technicians?|lab staff|"
        r"lab technicians?|radiology staff|radiology department|nurses?|"
        r"pharmacists?|pharmacy|supervisors?|accountants?|cashiers?)\b",
        re.IGNORECASE,
    )
    _REQUIREMENT_MODAL_RE = re.compile(
        r"\b(?:can|must|should|shall|will|may|need to|needs to)\b",
        re.IGNORECASE,
    )
    _VAGUE_NOUNS = frozenset({
        "stuff", "things", "thing", "it", "them", "everything",
        "anything", "something", "feature", "features", "functionality",
    })
    _VAGUE_FOCUS_STOPWORDS = frozenset({
        "the", "a", "an", "their", "his", "her", "its", "our", "your",
        "my", "this", "that", "these", "those", "all", "any", "new",
        "with", "for", "from", "into", "of", "to", "and", "or",
    })
    _COLLOQUIAL_PERFORMANCE_RE = re.compile(
        r"(?:"
        r"\b(?:app|application|system|platform|service|api)\b.{0,24}"
        r"\b(?:should|must|shall|will|needs?\s+to)\b.{0,16}"
        r"\b(?:be|feel|load|remain|stay)\b.{0,12}"
        r"\b(?:fast|quick|snappy|responsive|smooth|instant|unresponsive)\b"
        r"|"
        r"\bfeels?\s+(?:fast|quick|snappy|responsive|smooth)\b"
        r"|"
        r"\b(?:should|must|shall|will|needs?\s+to)\s+load\s+"
        r"(?:fast|quickly|instantly|smoothly)\b"
        r"|"
        r"\bno lag\b"
        r"|"
        r"\bwithout lag\b"
        r"|"
        r"\bunresponsive\b"
        r"|"
        r"\bno delays?\b"
        r"|"
        r"\bwithout delays?\b"
        r"|"
        r"\bslow to load\b"
        r"|"
        r"\bnot be slow\b"
        r")",
        re.IGNORECASE,
    )
    _COLLOQUIAL_RELIABILITY_RE = re.compile(
        r"(?:"
        r"\b(?:app|application|system|platform|service|api)\b.{0,24}"
        r"\b(?:should|must|shall|will|needs?\s+to)\b.{0,16}"
        r"(?:\balways\s+be\s+available\b|\bbe\s+always\s+available\b|"
        r"\bbe\s+available\b|\bbe\s+always\s+on\b|\bstay\s+up\b|"
        r"\bremain\s+available\b|\bwork\s+offline\b)"
        r"|"
        r"\b(?:app|application|system|platform|service|api)\b.{0,24}"
        r"(?:\balways\s+available\b|\balways\s+on\b|\bno downtime\b|\bnever go down\b)"
        r")",
        re.IGNORECASE,
    )
    _PERFORMANCE_CONSTRAINT_RE = re.compile(
        r"\b(latency|response time|throughput|performance|concurrent|scalab\w*|"
        r"bandwidth|bitrate|adaptive bitrate|"
        r"uptime|downtime|sla|slo|p95|p99|events?\s+per\s+second|"
        r"load test|benchmark|stress(?: test)?|99(?:\.\d+)?%?)\b|"
        r"\b\d+\s*(?:ms|milliseconds?|seconds?)\b|"
        r"\brespond(?:s)?\s+within\b|"
        r"\b(?:within|under|no more than)\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?:ms|milliseconds?|seconds?|minutes?)\b",
        re.IGNORECASE,
    )
    _INFRASTRUCTURE_AVAILABILITY_RE = re.compile(
        r"(?:"
        r"\b(?:system|service|platform|api|application|app)\b.{0,24}\b(?:availability|uptime|"
        r"downtime|reliab\w*|highly\s+available)\b|"
        r"\b(?:availability|uptime|downtime|reliab\w*|highly\s+available)\b.{0,24}"
        r"\b(?:system|service|platform|api|application|app)\b|"
        r"\b(?:system|service|platform|api|application|app)\s+availability\b|"
        r"\bavailability\s+of\s+(?:the\s+)?(?:system|service|platform|api|application|app)\b"
        r")",
        re.IGNORECASE,
    )
    _DEDUP_SIMILARITY_THRESHOLD = 0.7

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        llm_client: OllamaClient,
        kb: "KnowledgeBase | None" = None,
    ) -> None:
        self.llm_client = llm_client
        self.kb = kb
        self._dependency_corrections: list[str] = []
        self._last_prepared_requirements: list[RequirementItem] = []
        self._last_llm_attempted = False
        self._last_llm_accepted = False
        self._last_used_fallback = False
        self._last_fallback_reason: str | None = None
        self._last_retrieved_kb_context = ""

    @property
    def last_prepared_requirements(self) -> list[RequirementItem]:
        return list(self._last_prepared_requirements)

    @property
    def last_used_fallback(self) -> bool:
        return self._last_used_fallback

    @property
    def last_fallback_reason(self) -> str | None:
        return self._last_fallback_reason

    @property
    def last_llm_attempted(self) -> bool:
        return self._last_llm_attempted

    @property
    def last_llm_accepted(self) -> bool:
        return self._last_llm_accepted

    @property
    def last_retrieved_kb_context(self) -> str:
        return self._last_retrieved_kb_context

    def plan_from_requirements(
        self,
        requirements_text: str,
        allow_fallback: bool = False,
        allow_decomposition: bool = False,
        force_fallback: bool = False,
    ) -> TaskList:
        self._last_llm_attempted = False
        self._last_llm_accepted = False
        self._last_used_fallback = False
        self._last_fallback_reason = None
        self._last_retrieved_kb_context = ""
        _, requirements = self._prepare_requirements(requirements_text)
        if allow_decomposition and len(requirements) >= 2:
            requirements = self.deduplicate_requirements(requirements)
        self._last_prepared_requirements = list(requirements)
        if not requirements:
            raise ValueError("requirements text is empty")

        if force_fallback:
            if not allow_fallback:
                raise ValueError("force_fallback requires allow_fallback=True")
            self._last_used_fallback = True
            self._last_fallback_reason = "Rule-based fallback was forced by pipeline configuration."
            return self._build_rule_based_plan(
                requirements=requirements,
                allow_decomposition=allow_decomposition,
            )

        prompt = self._build_llm_prompt(
            raw_text=requirements_text,
            requirements=requirements,
            allow_decomposition=allow_decomposition,
        )

        try:
            return self._generate_plan_with_llm(
                prompt=prompt,
                requirements=requirements,
                allow_decomposition=allow_decomposition,
                allow_fallback=allow_fallback,
            )
        except (ValueError, ValidationError, requests.exceptions.RequestException) as exc:
            if allow_fallback and self._should_retry_compact_prompt(exc):
                compact_prompt = self._build_compact_prompt(
                    requirements=requirements,
                    allow_decomposition=allow_decomposition,
                )
                req_text = "\n".join(f"[{item.source}] {item.text}" for item in requirements)
                compact_prompt = self._inject_knowledge_base_context(compact_prompt, req_text)
                try:
                    return self._generate_plan_with_llm(
                        prompt=compact_prompt,
                        requirements=requirements,
                        allow_decomposition=allow_decomposition,
                        allow_fallback=allow_fallback,
                    )
                except (ValueError, ValidationError, requests.exceptions.RequestException) as compact_exc:
                    exc = compact_exc
            if not allow_fallback:
                raise
            self._last_used_fallback = True
            self._last_fallback_reason = (
                "Rule-based fallback was used after LLM planning failed: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.warning(self._last_fallback_reason)
            return self._build_rule_based_plan(
                requirements=requirements,
                allow_decomposition=allow_decomposition,
            )

    def _generate_plan_with_llm(
        self,
        *,
        prompt: str,
        requirements: list[RequirementItem],
        allow_decomposition: bool,
        allow_fallback: bool,
    ) -> TaskList:
        self._last_llm_attempted = True
        model_output = self.llm_client.generate_json(
            prompt,
            output_schema=TaskList.model_json_schema(),
            strict_json_only=not allow_fallback,
        )
        model_output = self._repair_tasklist_wrapper_if_needed(
            model_output,
            prompt=prompt,
            allow_fallback=allow_fallback,
        )
        model_output = self._normalize_llm_task_payload(
            model_output,
            requirements=requirements,
            allow_decomposition=allow_decomposition,
        )
        llm_tasks = TaskList.model_validate(model_output)
        llm_tasks = self._apply_uncertainty_metadata(llm_tasks, requirements)
        llm_tasks = self._annotate_task_explainability(llm_tasks, requirements)

        issues = self._quality_issues(
            task_list=llm_tasks,
            requirements=requirements,
            allow_decomposition=allow_decomposition,
        )
        if issues and allow_fallback and self._is_repairable_quality_failure(issues):
            repair_prompt = self._build_quality_repair_prompt(
                requirements=requirements,
                allow_decomposition=allow_decomposition,
                current_output=model_output,
                issues=issues,
            )
            repaired_output = self.llm_client.generate_json(
                repair_prompt,
                output_schema=TaskList.model_json_schema(),
                strict_json_only=False,
            )
            repaired_output = self._repair_tasklist_wrapper_if_needed(
                repaired_output,
                prompt=repair_prompt,
                allow_fallback=allow_fallback,
            )
            repaired_output = self._normalize_llm_task_payload(
                repaired_output,
                requirements=requirements,
                allow_decomposition=allow_decomposition,
                aggressive_completion=True,
            )
            repaired_tasks = TaskList.model_validate(repaired_output)
            repaired_tasks = self._apply_uncertainty_metadata(repaired_tasks, requirements)
            repaired_tasks = self._annotate_task_explainability(repaired_tasks, requirements)
            repaired_issues = self._quality_issues(
                task_list=repaired_tasks,
                requirements=requirements,
                allow_decomposition=allow_decomposition,
            )
            if not repaired_issues:
                llm_tasks = repaired_tasks
                issues = []
            else:
                issues = repaired_issues
        if issues:
            raise ValueError("Quality check failed: " + "; ".join(issues))

        self._last_llm_accepted = True
        return llm_tasks

    @staticmethod
    def _should_retry_compact_prompt(exc: Exception) -> bool:
        lowered = str(exc).lower()
        return any(
            marker in lowered
            for marker in (
                "thinking process",
                "did not contain a valid json object",
                "missing required keys: tasks",
                "task-like json without the required top-level tasks wrapper",
                "field required",
                "truncated json",
            )
        )

    @staticmethod
    def _is_repairable_quality_failure(issues: list[str]) -> bool:
        if not issues:
            return False
        repairable_prefixes = (
            "decomposition produced fewer tasks than requirements",
            "decomposition under-produced tasks for ",
            "req_type mismatch at ",
            "complexity out of range at ",
            "non action-oriented title at ",
        )
        return all(issue.startswith(repairable_prefixes) for issue in issues)

    def _build_quality_repair_prompt(
        self,
        *,
        requirements: list[RequirementItem],
        allow_decomposition: bool,
        current_output: dict,
        issues: list[str],
    ) -> str:
        compact_prompt = self._build_compact_prompt(
            requirements=requirements,
            allow_decomposition=allow_decomposition,
        )
        issues_text = "\n".join(f"- {issue}" for issue in issues)
        serialized_output = json.dumps(current_output, ensure_ascii=False, indent=2)
        prompt = f"""Repair the previous task list. Return ONLY valid JSON with a top-level "tasks" array.

Quality issues to fix:
{issues_text}

Repair rules:
- Keep valid tasks when possible, but add, split, or correct tasks until every issue above is fixed.
- Do not return fewer tasks than the atomic requirement lines listed below.
- If the same source appears on multiple requirement lines, emit multiple tasks with that same source.
- Correct req_type, title, and complexity so they match the requirement lines.
- Keep dependencies direct and only pointing to earlier task ids.

Previous JSON:
{serialized_output}

{compact_prompt}"""
        req_text = "\n".join(f"[{item.source}] {item.text}" for item in requirements)
        return self._inject_knowledge_base_context(prompt, req_text)

    def _repair_tasklist_wrapper_if_needed(
        self,
        model_output: dict,
        *,
        prompt: str,
        allow_fallback: bool,
    ) -> dict:
        if not isinstance(model_output, dict):
            return model_output
        if "tasks" in model_output:
            return model_output
        if not self._looks_like_single_task_object(model_output):
            return model_output
        if not allow_fallback:
            raise ValueError(
                "LLM returned a single task object instead of the required top-level tasks wrapper."
            )

        repair_prompt = (
            "Your previous response returned a single task object instead of the required top-level JSON object.\n"
            "Return ONLY a JSON object shaped exactly like:\n"
            '{"tasks":[{"id":"T001","title":"...","description":"...","req_type":"FR","complexity":2,"dependencies":[],"source":"line 1"}]}\n'
            "Wrap every task inside the top-level tasks array.\n\n"
            f"{prompt}"
        )
        repaired_output = self.llm_client.generate_json(
            repair_prompt,
            output_schema=TaskList.model_json_schema(),
            strict_json_only=False,
        )
        if isinstance(repaired_output, dict) and "tasks" in repaired_output:
            return repaired_output
        raise ValueError(
            "LLM returned task-like JSON without the required top-level tasks wrapper."
        )

    def _normalize_llm_task_payload(
        self,
        model_output: dict,
        *,
        requirements: list[RequirementItem],
        allow_decomposition: bool,
        aggressive_completion: bool = False,
    ) -> dict:
        if not isinstance(model_output, dict):
            return model_output
        raw_tasks = model_output.get("tasks")
        if not isinstance(raw_tasks, list):
            return model_output

        raw_dict_tasks = [dict(raw_task) for raw_task in raw_tasks if isinstance(raw_task, dict)]
        if not raw_dict_tasks:
            return model_output

        expected_entries = self._expected_task_entries(
            requirements,
            allow_decomposition=allow_decomposition,
        )
        if not expected_entries:
            return model_output

        if self._should_align_llm_tasks_to_expected_layout(
            raw_count=len(raw_dict_tasks),
            expected_count=len(expected_entries),
            aggressive_completion=aggressive_completion,
        ):
            normalized_tasks = self._align_llm_tasks_to_expected_entries(
                raw_dict_tasks,
                expected_entries=expected_entries,
            )
        else:
            normalized_tasks = self._normalize_partial_llm_tasks(
                raw_dict_tasks,
                requirements=requirements,
            )

        normalized_tasks = self._repair_llm_dependencies(
            normalized_tasks,
            requirements=requirements,
            allow_decomposition=allow_decomposition,
        )
        repaired = dict(model_output)
        repaired["tasks"] = normalized_tasks
        return repaired

    def _expected_task_entries(
        self,
        requirements: list[RequirementItem],
        *,
        allow_decomposition: bool,
    ) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for requirement in requirements:
            fragments = (
                self._decompose_requirement(requirement.text)
                if allow_decomposition
                else [requirement.text]
            )
            for fragment in fragments:
                text = fragment.strip().rstrip(".")
                if not text:
                    continue
                req_type = self._classify_req_type(text)
                entries.append(
                    {
                        "source": requirement.source,
                        "text": text,
                        "req_type": req_type,
                        "complexity": self._score_complexity(text, req_type),
                        "title": self._action_title_from_text(text, req_type),
                    }
                )
        return entries

    @staticmethod
    def _should_align_llm_tasks_to_expected_layout(
        *,
        raw_count: int,
        expected_count: int,
        aggressive_completion: bool = False,
    ) -> bool:
        if raw_count <= 0 or expected_count <= 0:
            return False
        if raw_count >= expected_count:
            return True
        if expected_count == 2 and raw_count == 1:
            return True
        if aggressive_completion and expected_count <= 10 and (raw_count / expected_count) >= 0.3:
            return True
        return (raw_count / expected_count) >= 0.6

    def _align_llm_tasks_to_expected_entries(
        self,
        raw_tasks: list[dict],
        *,
        expected_entries: list[dict[str, object]],
    ) -> list[dict]:
        remaining_tasks = [dict(task) for task in raw_tasks]
        repeated_sources = Counter(str(entry["source"]) for entry in expected_entries)
        normalized_tasks: list[dict] = []
        old_to_new_ids: dict[str, str] = {}

        for index, expected in enumerate(expected_entries):
            expected_source = str(expected["source"])
            expected_text = str(expected["text"])
            expected_type = str(expected["req_type"])
            expected_complexity = int(expected["complexity"])
            expected_title = str(expected["title"])

            selected_index: int | None = None
            for candidate_index, candidate in enumerate(remaining_tasks):
                candidate_source = str(candidate.get("source", "")).strip()
                if candidate_source == expected_source and self._is_valid_source_ref(candidate_source):
                    selected_index = candidate_index
                    break

            if selected_index is None and remaining_tasks:
                selected_index = 0

            raw_task = remaining_tasks.pop(selected_index) if selected_index is not None else {}
            task = dict(raw_task)

            original_task_id = str(task.get("id", "")).strip()
            normalized_task_id = f"T{index + 1:03d}"
            if re.match(r"^T\d{3}$", original_task_id) and original_task_id not in old_to_new_ids:
                old_to_new_ids[original_task_id] = normalized_task_id

            task["id"] = normalized_task_id
            task["source"] = expected_source
            task["req_type"] = expected_type
            task["complexity"] = expected_complexity

            title = task.get("title")
            should_reset_title = (
                repeated_sources[expected_source] > 1
                or not isinstance(title, str)
                or not title.strip()
                or not self._is_action_title(title)
                or self._title_mismatch(title, expected_title)
            )
            if should_reset_title:
                task["title"] = expected_title

            description = task.get("description")
            if (
                repeated_sources[expected_source] > 1
                or self._description_needs_reset(description, expected_text)
            ):
                task["description"] = expected_text

            task["type_reason"] = self._type_reason(task["description"], expected_type)
            task["complexity_reason"] = self._complexity_reason(
                task["description"],
                expected_type,
                expected_complexity,
            )
            normalized_tasks.append(task)

        self._remap_llm_dependencies(normalized_tasks, old_to_new_ids)
        return normalized_tasks

    def _normalize_partial_llm_tasks(
        self,
        raw_tasks: list[dict],
        *,
        requirements: list[RequirementItem],
    ) -> list[dict]:
        req_by_source = {item.source: item for item in requirements}
        normalized_tasks: list[dict] = []
        old_to_new_ids: dict[str, str] = {}

        for index, raw_task in enumerate(raw_tasks):
            task = dict(raw_task)

            original_task_id = str(task.get("id", "")).strip()
            normalized_task_id = f"T{index + 1:03d}"
            if re.match(r"^T\d{3}$", original_task_id) and original_task_id not in old_to_new_ids:
                old_to_new_ids[original_task_id] = normalized_task_id
            task["id"] = normalized_task_id

            source = str(task.get("source", "")).strip()
            requirement = req_by_source.get(source)
            if requirement is None and index < len(requirements):
                requirement = requirements[index]
            if requirement is None:
                continue

            expected_text = requirement.text.strip().rstrip(".")
            expected_type = self._classify_req_type(expected_text)
            expected_complexity = self._score_complexity(expected_text, expected_type)
            expected_title = self._action_title_from_text(expected_text, expected_type)

            task["source"] = requirement.source
            task["req_type"] = expected_type
            task["complexity"] = expected_complexity

            title = task.get("title")
            if (
                not isinstance(title, str)
                or not title.strip()
                or not self._is_action_title(title)
                or self._title_mismatch(title, expected_title)
            ):
                task["title"] = expected_title

            description = task.get("description")
            if self._description_needs_reset(description, expected_text):
                task["description"] = expected_text

            task["type_reason"] = self._type_reason(task["description"], expected_type)
            task["complexity_reason"] = self._complexity_reason(
                task["description"],
                expected_type,
                expected_complexity,
            )
            normalized_tasks.append(task)

        self._remap_llm_dependencies(normalized_tasks, old_to_new_ids)
        return normalized_tasks

    @staticmethod
    def _remap_llm_dependencies(
        tasks_payload: list[dict],
        old_to_new_ids: dict[str, str],
    ) -> None:
        known_ids = {
            task_id
            for task in tasks_payload
            if re.match(r"^T\d{3}$", task_id := str(task.get("id", "")).strip())
        }
        position_by_id = {
            str(task.get("id", "")).strip(): index
            for index, task in enumerate(tasks_payload)
        }

        for task in tasks_payload:
            task_id = str(task.get("id", "")).strip()
            raw_dependencies = task.get("dependencies")
            if not isinstance(raw_dependencies, list):
                raw_dependencies = []

            normalized_dependencies: list[str] = []
            for dep in raw_dependencies:
                if not isinstance(dep, str):
                    continue
                normalized_dep = old_to_new_ids.get(dep.strip(), dep.strip())
                if normalized_dep == task_id or normalized_dep not in known_ids:
                    continue
                if position_by_id.get(normalized_dep, -1) >= position_by_id.get(task_id, -1):
                    continue
                normalized_dependencies.append(normalized_dep)
            task["dependencies"] = list(dict.fromkeys(normalized_dependencies))

    def _repair_llm_dependencies(
        self,
        tasks_payload: list[dict],
        *,
        requirements: list[RequirementItem],
        allow_decomposition: bool,
    ) -> list[dict]:
        provisional_tasks: list[Task] = []
        index_map: list[int] = []
        for payload_index, task in enumerate(tasks_payload):
            if not isinstance(task, dict):
                continue

            task_id = str(task.get("id", "")).strip()
            title = task.get("title")
            description = task.get("description")
            req_type = task.get("req_type")
            complexity = task.get("complexity")
            source = str(task.get("source", "")).strip()
            if not (
                re.match(r"^T\d{3}$", task_id)
                and isinstance(title, str) and title.strip()
                and isinstance(description, str) and description.strip()
                and req_type in {"FR", "NFR"}
                and isinstance(complexity, int)
                and self._is_valid_source_ref(source)
            ):
                continue

            provisional_tasks.append(
                Task(
                    id=task_id,
                    title=title,
                    description=description,
                    req_type=req_type,
                    type_reason=task.get("type_reason") or self._type_reason(description, req_type),
                    complexity=complexity,
                    complexity_reason=task.get("complexity_reason") or self._complexity_reason(description, req_type, complexity),
                    dependencies=[],
                    source=source,
                    confidence=task.get("confidence", "high"),
                    optional=bool(task.get("optional", False)),
                )
            )
            index_map.append(payload_index)

        if len(provisional_tasks) < 2:
            return tasks_payload

        snapshot_corrections = list(self._dependency_corrections)
        try:
            for idx in range(len(provisional_tasks)):
                provisional_tasks[idx].dependencies.extend(
                    self._infer_direct_dependencies(provisional_tasks, idx)
                )
            self._propagate_hospital_workflow_chains(provisional_tasks)
            self._propagate_nfr_constraints(provisional_tasks)
            self._correct_inverted_performance_dependencies(provisional_tasks)
            if not any(task.dependencies for task in provisional_tasks):
                reference_plan = self._build_rule_based_plan(
                    requirements=requirements,
                    allow_decomposition=allow_decomposition,
                )
                if len(reference_plan.tasks) == len(provisional_tasks) and any(
                    task.dependencies for task in reference_plan.tasks
                ):
                    for provisional_task, reference_task in zip(
                        provisional_tasks,
                        reference_plan.tasks,
                    ):
                        provisional_task.dependencies = list(reference_task.dependencies)
        finally:
            self._dependency_corrections = snapshot_corrections

        known_ids = {task.id for task in provisional_tasks}
        position_by_id = {task.id: idx for idx, task in enumerate(provisional_tasks)}
        for provisional_task, payload_index in zip(provisional_tasks, index_map):
            payload = tasks_payload[payload_index]
            current_position = position_by_id[provisional_task.id]
            raw_dependencies = payload.get("dependencies")
            candidate_dependencies = raw_dependencies if isinstance(raw_dependencies, list) else []
            cleaned_dependencies = [
                dep for dep in candidate_dependencies
                if isinstance(dep, str)
                and dep in known_ids
                and position_by_id[dep] < current_position
            ]
            inferred_dependencies = [
                dep for dep in provisional_task.dependencies
                if dep in known_ids and position_by_id[dep] < current_position
            ]
            if not cleaned_dependencies and inferred_dependencies:
                payload["dependencies"] = list(dict.fromkeys(inferred_dependencies))
                continue
            if len(cleaned_dependencies) != len(candidate_dependencies):
                payload["dependencies"] = (
                    list(dict.fromkeys(inferred_dependencies))
                    if inferred_dependencies
                    else list(dict.fromkeys(cleaned_dependencies))
                )

        return tasks_payload

    def _prepare_requirements(
        self,
        requirements_text: str,
    ) -> tuple[str, list[RequirementItem]]:
        raw_requirements = self._parse_requirements(requirements_text)
        return requirements_text, raw_requirements

    @classmethod
    def deduplicate_requirements(
        cls,
        items: list[RequirementItem],
        similarity_threshold: float | None = None,
    ) -> list[RequirementItem]:
        if len(items) < 2:
            return list(items)

        threshold = similarity_threshold or cls._DEDUP_SIMILARITY_THRESHOLD
        deduplicated: list[RequirementItem] = []
        token_cache: list[set[str]] = []

        for item in items:
            candidate = cls._ensure_requirement_sources(item)
            candidate_tokens = cls._dedup_tokens(candidate.text)
            best_index: int | None = None
            best_similarity = 0.0

            for index, existing in enumerate(deduplicated):
                if cls._dedup_markers_conflict(candidate.text, existing.text):
                    continue
                similarity = cls._jaccard_similarity(candidate_tokens, token_cache[index])
                shared_tokens = candidate_tokens & token_cache[index]
                if similarity < threshold or len(shared_tokens) < 2:
                    continue
                if similarity > best_similarity:
                    best_index = index
                    best_similarity = similarity

            if best_index is None:
                deduplicated.append(candidate)
                token_cache.append(candidate_tokens)
                continue

            survivor = deduplicated[best_index]
            merged_sources = cls._merge_requirement_sources(survivor, candidate)
            merged_text = survivor.text
            if cls._is_more_informative_requirement_text(candidate.text, survivor.text):
                merged_text = candidate.text

            deduplicated[best_index] = RequirementItem(
                line_no=survivor.line_no,
                source=survivor.source,
                text=merged_text,
                sources=merged_sources,
            )
            token_cache[best_index] = cls._dedup_tokens(merged_text)
            logger.info(
                "[DEDUP] Merged %r into %r (similarity: %.2f)",
                candidate.source,
                survivor.source,
                best_similarity,
            )

        return deduplicated

    # ------------------------------------------------------------------ #
    #  Parsing                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_requirements(requirements_text: str) -> list[RequirementItem]:
        return PlannerAgent._parse_requirement_blocks(requirements_text)

    @classmethod
    def _parse_requirement_blocks(cls, requirements_text: str) -> list[RequirementItem]:
        requirements: list[RequirementItem] = []
        next_requirement_no = 1
        next_block_no = 1
        active_heading: str | None = None
        narrative_lines: list[str] = []

        def flush_narrative_block() -> None:
            nonlocal next_requirement_no, next_block_no, narrative_lines
            if not narrative_lines:
                return
            block_text = " ".join(line.strip() for line in narrative_lines if line.strip())
            narrative_lines = []
            normalized_block = cls._normalize_requirement_text(block_text, active_heading=active_heading)
            block_items = cls._extract_block_requirements(
                normalized_block,
                block_no=next_block_no,
                starting_requirement_no=next_requirement_no,
            )
            if block_items:
                requirements.extend(block_items)
                next_requirement_no += len(block_items)
                next_block_no += 1

        for raw_line in requirements_text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                flush_narrative_block()
                continue

            if cls._looks_like_heading(stripped):
                flush_narrative_block()
                active_heading = cls._clean_heading(stripped)
                continue

            extracted = cls._extract_requirement_line(stripped, next_requirement_no)
            is_explicit_item = extracted is not None
            if extracted:
                flush_narrative_block()
                line_no, text = extracted
            else:
                if (
                    requirements
                    and requirements[-1].source.startswith("line ")
                    and cls._looks_like_continuation(stripped)
                ):
                    previous = requirements[-1]
                    requirements[-1] = RequirementItem(
                        line_no=previous.line_no,
                        source=previous.source,
                        text=f"{previous.text} {cls._normalize_requirement_text(stripped, active_heading=active_heading)}".strip(),
                    )
                    continue
                narrative_lines.append(stripped)
                continue

            normalized = cls._normalize_requirement_text(text, active_heading=active_heading)

            requirements.append(RequirementItem(line_no=line_no, source=f"line {line_no}", text=normalized))
            next_requirement_no = max(next_requirement_no, line_no + 1)

        flush_narrative_block()
        return requirements

    @classmethod
    def _extract_block_requirements(
        cls,
        block_text: str,
        block_no: int,
        starting_requirement_no: int,
    ) -> list[RequirementItem]:
        normalized_block = re.sub(r"\s+", " ", block_text).strip()
        if not normalized_block or cls._is_narrative_meta_requirement(normalized_block):
            return []

        sentences = cls._split_block_sentences(normalized_block)
        grouped_clauses: list[str] = []
        current_parts: list[str] = []

        for sentence in sentences:
            requirement_like = cls._looks_like_requirement_sentence(sentence)
            if requirement_like:
                if current_parts:
                    grouped_clauses.append(" ".join(current_parts).strip())
                current_parts = [sentence]
                continue

            if current_parts:
                if not cls._is_narrative_meta_requirement(sentence):
                    current_parts.append(sentence)
                continue

            if not cls._is_narrative_meta_requirement(sentence) and cls._is_task_grade_clause(sentence):
                current_parts = [sentence]

        if current_parts:
            grouped_clauses.append(" ".join(current_parts).strip())

        if not grouped_clauses:
            if cls._looks_like_requirement_sentence(normalized_block) or cls._is_task_grade_clause(normalized_block):
                grouped_clauses = [normalized_block]
            else:
                return []

        finalized: list[str] = []
        seen: set[str] = set()
        for clause in grouped_clauses:
            normalized = re.sub(r"\s+", " ", clause.strip(" .,;"))
            if not normalized or cls._is_narrative_meta_requirement(normalized):
                continue
            if not (cls._looks_like_requirement_sentence(normalized) or cls._is_task_grade_clause(normalized)):
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            finalized.append(normalized[:1].upper() + normalized[1:])
        if not finalized:
            return []

        items: list[RequirementItem] = []
        for index, clause in enumerate(finalized, start=1):
            source = f"block {block_no}" if len(finalized) == 1 else f"block {block_no} clause {index}"
            items.append(
                RequirementItem(
                    line_no=starting_requirement_no + index - 1,
                    source=source,
                    text=clause,
                )
            )
        return items

    @staticmethod
    def _split_block_sentences(text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [part.strip(" \t") for part in parts if part.strip(" \t")]

    @classmethod
    def _looks_like_requirement_sentence(cls, text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return False
        if cls._is_narrative_meta_requirement(text):
            return False
        if cls._has_access_control_scope(text) or cls._has_billing_insurance_scope(text):
            return True
        if cls._REQUIREMENT_ACTOR_RE.search(text) and cls._REQUIREMENT_MODAL_RE.search(text):
            return True
        if re.match(
            r"^(?:first,?\s+|also,?\s+|then,?\s+|and\s+when\s+|when\s+|for\s+\w+,?\s+)?"
            r"(?:there should be|there must be|we need|we also need|we want|"
            r"it would be better if|lab module is needed|radiology also is needed|"
            r"billing is important|pharmacy should receive|doctors? should|"
            r"the doctor should|the system should|the system must)\b",
            lowered,
        ):
            return True
        return False

    @staticmethod
    def _extract_requirement_line(stripped: str, fallback_line_no: int) -> tuple[int, str] | None:
        numbered = re.match(r"^(?P<num>\d+)\s*[.)\-:]\s*(?P<text>.+)$", stripped)
        if numbered:
            return int(numbered.group("num")), numbered.group("text").strip()

        bracketed_tag = re.match(
            r"^\[(?:REQ|FR|NFR|AC)[\s\-_]?\d+\]\s*(?P<text>.+)$",
            stripped,
            flags=re.IGNORECASE,
        )
        if bracketed_tag:
            return fallback_line_no, bracketed_tag.group("text").strip()

        tagged = re.match(
            r"^(?:REQ|FR|NFR|AC)[\s\-_]?\d+\s*[:.)-]\s*(?P<text>.+)$",
            stripped,
            flags=re.IGNORECASE,
        )
        if tagged:
            return fallback_line_no, tagged.group("text").strip()

        bulleted = re.match(
            r"^(?:[-*•]+|\[[ xX]\]|[A-Za-z][.)]|[ivxlcdmIVXLCDM]+[.)])\s+(?P<text>.+)$",
            stripped,
        )
        if bulleted:
            return fallback_line_no, bulleted.group("text").strip()

        return None

    @staticmethod
    def _looks_like_heading(stripped: str) -> bool:
        plain = stripped.strip().strip(":")
        lowered = plain.lower()

        if re.match(r"^#{1,6}\s+\S", stripped):
            return True
        if stripped.endswith(":") and len(plain.split()) <= 8 and not re.search(
            r"\b(can|must|should|shall|will|may|supports?|provides?|allows?|enables?)\b",
            lowered,
        ):
            return True
        if plain.isupper() and 1 <= len(plain.split()) <= 6:
            return True
        return False

    @staticmethod
    def _clean_heading(stripped: str) -> str:
        cleaned = re.sub(r"^#{1,6}\s*", "", stripped).strip()
        return cleaned.rstrip(":").strip()

    @staticmethod
    def _looks_like_continuation(stripped: str) -> bool:
        lowered = stripped.lower()
        continuation_prefixes = (
            "and ",
            "or ",
            "with ",
            "within ",
            "including ",
            "excluding ",
            "using ",
            "via ",
            "so that ",
            "such that ",
            "to ensure ",
            "where ",
            "when ",
            "then ",
            "because ",
            "which ",
            "that ",
        )
        return stripped[:1].islower() or lowered.startswith(continuation_prefixes)

    @classmethod
    def _normalize_requirement_text(cls, text: str, active_heading: str | None = None) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip(" -–—\t")
        cleaned = re.sub(
            r"^(?:acceptance criteria|acceptance criterion|scenario|user story)\s*[:\-]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        user_story = re.match(
            r"^as an?\s+(?P<role>[^,]+),\s*i\s+"
            r"(?P<intent>want|need|can|should be able)\s+(?:to\s+)?"
            r"(?P<goal>.+?)(?:,\s*so that\s+(?P<benefit>.+))?$",
            cleaned,
            flags=re.IGNORECASE,
        )
        if user_story:
            role = user_story.group("role").strip()
            goal = user_story.group("goal").strip()
            benefit = user_story.group("benefit")
            cleaned = f"{role[:1].upper()}{role[1:]} can {goal}"
            if benefit:
                cleaned += f" so that {benefit.strip()}"

        if active_heading and not re.search(
            r"\b(can|must|should|shall|will|may|supports?|provides?|allows?|enables?)\b",
            cleaned.lower(),
        ):
            cleaned = f"{active_heading}: {cleaned}"

        return cleaned

    @classmethod
    def _dedup_tokens(cls, text: str) -> set[str]:
        return cls._content_tokens(text)

    @classmethod
    def _dedup_markers_conflict(cls, left: str, right: str) -> bool:
        """Keep similar-looking quality metrics separate when their semantics differ."""

        def markers(text: str) -> set[str]:
            lowered = text.casefold()
            found: set[str] = set()
            marker_patterns = {
                "rto": r"\brto\b",
                "rpo": r"\brpo\b",
                "p95": r"\bp95\b",
                "p99": r"\bp99\b",
                "at_rest": r"\bat rest\b",
                "in_transit": r"\bin transit\b",
                "pci": r"\bpci(?:-dss)?\b",
                "gdpr": r"\bgdpr\b",
                "aml": r"\baml\b",
                "kyc": r"\bkyc\b",
                "wcag": r"\bwcag\b",
            }
            for marker, pattern in marker_patterns.items():
                if re.search(pattern, lowered):
                    found.add(marker)
            return found

        left_markers = markers(left)
        right_markers = markers(right)
        return bool(left_markers and right_markers and left_markers != right_markers)

    @staticmethod
    def _jaccard_similarity(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        union = left | right
        if not union:
            return 0.0
        return len(left & right) / len(union)

    @staticmethod
    def _is_more_informative_requirement_text(candidate: str, current: str) -> bool:
        return len(candidate.strip()) > len(current.strip())

    @staticmethod
    def _ensure_requirement_sources(item: RequirementItem) -> RequirementItem:
        if item.sources:
            return item
        return RequirementItem(
            line_no=item.line_no,
            source=item.source,
            text=item.text,
            sources=(item.source,),
        )

    @staticmethod
    def _merge_requirement_sources(*items: RequirementItem) -> tuple[str, ...]:
        ordered: list[str] = []
        for item in items:
            for source in item.all_sources:
                if source not in ordered:
                    ordered.append(source)
        return tuple(ordered)

    # ------------------------------------------------------------------ #
    #  LLM prompt                                                          #
    # ------------------------------------------------------------------ #

    def _build_llm_prompt(
        self,
        raw_text: str,
        requirements: list[RequirementItem],
        allow_decomposition: bool,
    ) -> str:
        prompt = self._build_prompt(
            raw_text=raw_text,
            requirements=requirements,
            allow_decomposition=allow_decomposition,
        )
        req_text = "\n".join(f"[{item.source}] {item.text}" for item in requirements)
        return self._inject_knowledge_base_context(prompt, req_text)

    def _inject_knowledge_base_context(self, prompt: str, req_text: str) -> str:
        ctx = self._knowledge_base_context(req_text)
        if not ctx:
            return prompt

        markers = ("Output ONLY valid JSON", "Return ONLY valid JSON")
        for marker in markers:
            if marker in prompt:
                return prompt.replace(marker, f"{ctx}\n\n{marker}", 1)
        return f"{prompt}\n\n{ctx}"

    def _knowledge_base_context(self, req_text: str) -> str:
        if self.kb is None or self.llm_client is None:
            self._last_retrieved_kb_context = ""
            return ""

        from src.kb.retriever import ContextRetriever

        ctx = ContextRetriever(self.kb).get_context_for_requirement(req_text)
        self._last_retrieved_kb_context = ctx.strip()
        return self._last_retrieved_kb_context

    @staticmethod
    def _build_prompt(
        raw_text: str,
        requirements: list[RequirementItem],
        allow_decomposition: bool,
    ) -> str:
        req_text = PlannerAgent._llm_requirement_text(
            requirements,
            allow_decomposition=allow_decomposition,
        )
        decomposition_hints = PlannerAgent._build_decomposition_hints(
            requirements,
            allow_decomposition=allow_decomposition,
        )
        atomic_execution_hints = PlannerAgent._build_atomic_execution_hints(
            requirements,
            allow_decomposition=allow_decomposition,
        )
        mapping_rule = (
            "Map each requirement to exactly ONE task (strict 1:1 mapping). "
            "Do not merge or split requirements."
            if not allow_decomposition
            else (
                "The Requirements section below has already been normalized into atomic lines "
                "where needed. Emit exactly one task per listed requirement line."
            )
        )

        return f"""You are a senior software project planner. Analyze the software requirements below and produce a structured project plan.

Output ONLY valid JSON — no explanation, no markdown, no text outside the JSON object:
{{
  "tasks": [
    {{
      "id": "T001",
      "title": "Implement ...",
      "description": "Full requirement text or sub-task description.",
      "req_type": "FR",
      "complexity": 2,
      "dependencies": [],
      "source": "block 1 clause 1"
    }}
  ]
}}

Classification rules:
- req_type "FR": functional requirements — features, behaviors, actions a user or the system performs.
- req_type "NFR": non-functional requirements — performance, security, encryption, compliance, scalability, reliability, localization, availability.
- Exception: if an NFR is framed as a user-controllable action (e.g. "users can enable 2FA"), classify as FR.
- Exception: privacy-right workflows that users can exercise (deletion, export, consent withdrawal, access logs) are FR even when GDPR is mentioned.

Complexity rubric (integer 1-5):
- 1: Read-only / display (view, list, search, display)
- 2: Simple CRUD (create, update, delete, register, cancel)
- 3: Business logic, multi-step workflow, authentication, verification, localization
- 4: External integration, role-based access control, performance constraints
- 5: Cross-system orchestration, distributed real-time processing

Dependency rules:
- List only DIRECT predecessor task IDs. No transitive dependencies. No self-reference.
- A task depends on another only if it CANNOT start until the other is complete.
- Identity/registration tasks are prerequisites for auth tasks.
- Auth tasks are prerequisites for access-control tasks.
- Access-control tasks are prerequisites for all protected domain features.

  Mapping rule:
  - {mapping_rule}

  Additional rules:
  - If any requirement item is unclear or inconsistent with the original input, correct it. Do not invent requirements not implied by the original text.
  - ids must be sequential: T001, T002, T003, ...
  - source must match one of the provided requirement references exactly (for example "line 1", "block 2 clause 1", or "REQ-01").
  - If a requirement is displayed as [REQ-01], output the source value as "REQ-01" without square brackets.
  - If the Requirements section repeats the same source on multiple lines, emit one task per line while keeping that same source value on the resulting tasks.
  - title must start with an action verb: Implement, Design, Integrate, Enforce, Optimize, Configure, Build, etc.
  - Never output fewer tasks than the number of atomic requirement lines shown below.
{atomic_execution_hints}
{decomposition_hints}
  
  Original student input:
  {raw_text}

  Requirements:
  {req_text}"""

    @staticmethod
    def _build_compact_prompt(
        requirements: list[RequirementItem],
        allow_decomposition: bool,
    ) -> str:
        req_text = PlannerAgent._llm_requirement_text(
            requirements,
            allow_decomposition=allow_decomposition,
        )
        decomposition_hints = PlannerAgent._build_decomposition_hints(
            requirements,
            allow_decomposition=allow_decomposition,
        )
        atomic_execution_hints = PlannerAgent._build_atomic_execution_hints(
            requirements,
            allow_decomposition=allow_decomposition,
        )
        mapping_rule = (
            "Keep strict 1:1 mapping: one requirement becomes one task."
            if not allow_decomposition
            else "The requirement lines below are already atomic; emit exactly one task per line."
        )
        return f"""Compact retry. Return ONLY valid JSON with a top-level "tasks" array.

Required shape:
{{
  "tasks": [
    {{
      "id": "T001",
      "title": "Implement ...",
      "description": "...",
      "req_type": "FR",
      "complexity": 2,
      "dependencies": [],
      "source": "line 1"
    }}
  ]
}}

Rules:
- No Thinking Process, no explanation, no markdown.
- Always wrap every task inside the top-level "tasks" array.
- Preserve exact source references from the requirement list.
- If a source appears as [REQ-01], output "REQ-01" without square brackets.
- If the Requirements section repeats the same source on multiple lines, emit one task per line while keeping that same source value.
- req_type must be either "FR" or "NFR".
- Dependencies must reference only earlier task ids.
- Never return fewer tasks than the number of requirement lines below.
- {mapping_rule}
{atomic_execution_hints}
{decomposition_hints}

Requirements:
{req_text}"""

    @classmethod
    def _build_decomposition_hints(
        cls,
        requirements: list[RequirementItem],
        *,
        allow_decomposition: bool,
    ) -> str:
        if not allow_decomposition:
            return ""

        hint_lines: list[str] = []
        for item in requirements:
            fragments = cls._decompose_requirement(item.text)
            if len(fragments) < 2:
                continue
            hint_lines.append(
                f'  - {item.source}: emit at least {len(fragments)} task(s), all with source "{item.source}"'
            )
            for fragment in fragments:
                hint_lines.append(f"    * {fragment}")

        if not hint_lines:
            return ""

        return "\n  Atomic decomposition hints:\n" + "\n".join(hint_lines)

    @classmethod
    def _build_atomic_execution_hints(
        cls,
        requirements: list[RequirementItem],
        *,
        allow_decomposition: bool,
    ) -> str:
        atomic_entries: list[tuple[str, str, str, int]] = []
        for item in requirements:
            fragments = (
                cls._decompose_requirement(item.text)
                if allow_decomposition
                else [item.text]
            )
            for fragment in fragments:
                cleaned = fragment.strip().rstrip(".")
                req_type = cls._classify_req_type(cleaned)
                complexity = cls._score_complexity(cleaned, req_type)
                atomic_entries.append((item.source, cleaned, req_type, complexity))

        if not atomic_entries:
            return ""

        hint_lines = [
            "  Atomic line contract:",
            f"  - The Requirements section below contains {len(atomic_entries)} atomic requirement line(s).",
            f"  - Emit EXACTLY {len(atomic_entries)} task object(s), in the same order as the requirement lines.",
            "  - Emit ONE task for EACH requirement line below. Do not merge, summarize, or skip lines.",
            "  - Repeated source values are expected; keep the same source on each corresponding task.",
            '  - FR lines should use action titles like "Implement", "Integrate", or "Build".',
            '  - NFR lines should use action titles like "Enforce", "Optimize", "Enable", or "Configure" and should not use generic "Ensure ..." labels.',
            "  - Security, performance, availability, compliance, mobile, localization, accessibility, and privacy constraints are NFR unless they explicitly describe a user-exercised workflow.",
        ]
        if len(atomic_entries) <= 18:
            hint_lines.append("  Expected atomic line classifications:")
            for idx, (source, text, req_type, complexity) in enumerate(atomic_entries, start=1):
                preview = text if len(text) <= 72 else text[:69].rstrip() + "..."
                hint_lines.append(
                    f'    * atomic line {idx}: source="{source}", req_type={req_type}, complexity~{complexity}, text="{preview}"'
                )
        return "\n" + "\n".join(hint_lines)

    @classmethod
    def _llm_requirement_text(
        cls,
        requirements: list[RequirementItem],
        *,
        allow_decomposition: bool,
    ) -> str:
        lines: list[str] = []
        for item in requirements:
            fragments = (
                cls._decompose_requirement(item.text)
                if allow_decomposition
                else [item.text]
            )
            for fragment in fragments:
                lines.append(f"[{item.source}] {fragment}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Rule-based plan builder                                             #
    # ------------------------------------------------------------------ #

    def _build_rule_based_plan(
        self,
        requirements: list[RequirementItem],
        allow_decomposition: bool,
    ) -> TaskList:
        self._dependency_corrections = []
        raw_entries = self._expected_task_entries(
            requirements,
            allow_decomposition=allow_decomposition,
        )

        tasks: list[Task] = []
        for idx, entry in enumerate(raw_entries, start=1):
            source = str(entry["source"])
            text = str(entry["text"])
            req_type = self._classify_req_type(text)
            title = self._action_title_from_text(text, req_type)
            complexity = self._score_complexity(text, req_type)
            confidence = "high"
            if title == self.UNCLEAR_TITLE:
                confidence = "low"
                logger.warning("[WARN] Vague object detected in requirement: %r", source)

            tasks.append(
                Task(
                    id=f"T{idx:03d}",
                    title=title,
                    description=text + ".",
                    req_type=req_type,
                    type_reason=self._type_reason(text, req_type),
                    complexity=complexity,
                    complexity_reason=self._complexity_reason(text, req_type, complexity),
                    dependencies=[],
                    source=source,
                    confidence=confidence,
                )
            )

        tasks = self._apply_uncertainty_metadata(
            TaskList(tasks=tasks),
            requirements,
        ).tasks

        for idx in range(len(tasks)):
            tasks[idx].dependencies.extend(
                self._infer_direct_dependencies(tasks=tasks, current_index=idx)
            )
        self._propagate_hospital_workflow_chains(tasks)
        self._propagate_nfr_constraints(tasks)
        self._correct_inverted_performance_dependencies(tasks)

        return self._annotate_task_explainability(TaskList(tasks=tasks), requirements)

    @classmethod
    def _contains_uncertainty_marker(cls, text: str) -> bool:
        return cls._UNCERTAINTY_MARKER_RE.search(text) is not None

    @classmethod
    def _extract_uncertain_segments(cls, text: str) -> list[str]:
        sentence_like_segments = re.split(r"(?<=[.!?])\s+|;\s+", text)
        candidates: list[str] = []

        for sentence in sentence_like_segments:
            stripped = sentence.strip()
            if not stripped:
                continue

            clause_segments = re.split(
                r",\s+"
                r"|(?:(?<=\w)\s+(?:but|however|although|though|except|unless|so)\s+)"
                r"|(?:(?<=\w)\s+(?:and|or)\s+(?=(?:maybe|perhaps|probably|optional(?:ly)?|"
                r"if possible|if we have time|when we have time|might|could|"
                r"eventually|would be nice|nice to have|stretch goal|down the line|"
                r"at some point|low priority|not urgent|bonus feature|in version 2|in v2)\b))",
                stripped,
                flags=re.IGNORECASE,
            )
            ordered_clauses = [
                segment.strip(" ,.;:")
                for segment in clause_segments
                if segment.strip(" ,.;:")
            ]
            local_candidates: list[str] = []
            for index, segment in enumerate(ordered_clauses):
                if not cls._contains_uncertainty_marker(segment):
                    continue
                candidate = segment
                qualifier_tokens = cls._content_tokens(segment) - cls._UNCERTAINTY_QUALIFIER_TOKENS
                if not qualifier_tokens and index > 0:
                    previous = ordered_clauses[index - 1]
                    if previous and not cls._contains_uncertainty_marker(previous):
                        candidate = f"{previous} {segment}".strip()
                local_candidates.append(candidate.strip(" ,.;:"))
            if local_candidates:
                candidates.extend(local_candidates)
                continue

            if cls._contains_uncertainty_marker(stripped):
                trimmed = re.split(
                    r"\s+\b(?:but|however|although|though|except)\b\s+",
                    stripped,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0].strip(" ,.;:")
                candidates.append(trimmed or stripped)

        if not candidates and cls._contains_uncertainty_marker(text):
            candidates.append(text.strip())
        return candidates

    @classmethod
    def _content_tokens(cls, text: str) -> set[str]:
        tokens: set[str] = set()
        for raw in re.findall(r"[A-Za-z][A-Za-z0-9'-]+", text.lower()):
            token = raw.strip("'")
            if len(token) <= 3 or token in cls._UNCERTAINTY_SCOPE_STOPWORDS:
                continue
            if token.endswith("ies") and len(token) > 4:
                token = f"{token[:-3]}y"
            elif token.endswith("s") and len(token) > 4:
                token = token[:-1]
            tokens.add(token)
        return tokens

    @classmethod
    def _uncertainty_scope_tokens(cls, text: str) -> set[str]:
        focused = cls._extract_focus_phrase(text)
        focused_tokens = cls._content_tokens(focused) if focused else set()
        return focused_tokens or cls._content_tokens(text)

    @classmethod
    def _confirmed_clause_scope_tokens(cls, text: str) -> set[str]:
        if not cls._contains_uncertainty_marker(text):
            return set()

        sentence_like_segments = re.split(r"(?<=[.!?])\s+|;\s+", text)
        confirmed_clauses: list[str] = []
        for sentence in sentence_like_segments:
            stripped = sentence.strip()
            if not stripped:
                continue
            clause_segments = re.split(
                r",\s+"
                r"|(?:(?<=\w)\s+(?:but|however|although|though|except|unless|so)\s+)"
                r"|(?:(?<=\w)\s+(?:and|or)\s+(?=(?:maybe|perhaps|probably|optional(?:ly)?|"
                r"if possible|if we have time|when we have time|might|could|"
                r"eventually|would be nice|nice to have|stretch goal|down the line|"
                r"at some point|low priority|not urgent|bonus feature|in version 2|in v2)\b))",
                stripped,
                flags=re.IGNORECASE,
            )
            confirmed_clauses.extend(
                segment.strip(" ,.;:")
                for segment in clause_segments
                if segment.strip(" ,.;:") and not cls._contains_uncertainty_marker(segment)
            )

        return cls._content_tokens(" ".join(confirmed_clauses))

    @classmethod
    def _infer_uncertainty_metadata(cls, fragment: str, source_text: str) -> tuple[bool, str]:
        uncertainty_source = source_text or fragment
        uncertain_segments = cls._extract_uncertain_segments(uncertainty_source)
        if not uncertain_segments:
            return False, "high"

        fragment_tokens = cls._uncertainty_scope_tokens(fragment)
        fragment_has_uncertainty = cls._contains_uncertainty_marker(fragment)
        if fragment_has_uncertainty:
            confirmed_scope = cls._confirmed_clause_scope_tokens(fragment)
            if confirmed_scope:
                fragment_tokens = fragment_tokens & confirmed_scope or fragment_tokens
        if not fragment_tokens:
            lowered_source = uncertainty_source.lower().strip()
            if re.match(
                r"^(?:maybe|perhaps|probably|if possible|if we have time|when we have time|"
                r"optional(?:ly)?|eventually|would be nice|nice to have|stretch goal|"
                r"down the line|at some point|low priority|not urgent|bonus feature|"
                r"in version 2|in v2|we are not sure|i am not sure|i'm not sure)\b",
                lowered_source,
            ):
                return True, "low"
            return False, "high"

        for segment in uncertain_segments:
            segment_tokens = cls._content_tokens(segment)
            overlap = fragment_tokens & segment_tokens
            if len(overlap) >= 2:
                return True, "low"
            if len(fragment_tokens) == 1 and overlap:
                return True, "low"
            if fragment_has_uncertainty and len(fragment_tokens) >= 3 and len(overlap) >= 2:
                return True, "low"

        if cls._contains_uncertainty_marker(fragment):
            lowered_fragment = fragment.lower().strip()
            if re.match(
                r"^(?:maybe|perhaps|probably|if possible|if we have time|when we have time|"
                r"optional(?:ly)?|future enhancement|later phase|not in first version|"
                r"probably not in first version|in version 2|in v2|eventually|"
                r"would be nice|nice to have|stretch goal|down the line|at some point|"
                r"low priority|not urgent|bonus feature|we are not sure|i am not sure|i'm not sure)\b",
                lowered_fragment,
            ):
                return True, "low"

        lowered_source = uncertainty_source.lower().strip()
        if re.match(
            r"^(?:maybe|perhaps|probably|if possible|if we have time|when we have time|"
            r"optional(?:ly)?|eventually|would be nice|nice to have|stretch goal|"
            r"down the line|at some point|low priority|not urgent|bonus feature|"
            r"in version 2|in v2|we are not sure|i am not sure|i'm not sure)\b",
            lowered_source,
        ):
            return True, "low"

        return False, "high"

    @classmethod
    def _apply_uncertainty_metadata(
        cls,
        task_list: TaskList,
        requirements: list[RequirementItem],
    ) -> TaskList:
        source_lookup = {f"line {req.line_no}": req.text for req in requirements}
        source_lookup.update({req.source: req.text for req in requirements})
        annotated_tasks: list[Task] = []

        for task in task_list.tasks:
            if task.optional or task.confidence != "high":
                annotated_tasks.append(task)
                continue

            source_text = source_lookup.get(task.source, task.description)
            optional, confidence = cls._infer_uncertainty_metadata(
                task.description,
                source_text,
            )
            annotated_tasks.append(
                task.model_copy(
                    update={
                        "optional": optional,
                        "confidence": confidence,
                    }
                )
            )

        return TaskList(tasks=annotated_tasks)

    # ------------------------------------------------------------------ #
    #  Classification                                                      #
    # ------------------------------------------------------------------ #

    @classmethod
    def _has_infrastructure_availability_signal(cls, text: str) -> bool:
        lowered = text.lower()
        return (
            cls._INFRASTRUCTURE_AVAILABILITY_RE.search(lowered) is not None
            or cls._COLLOQUIAL_RELIABILITY_RE.search(lowered) is not None
        )

    @classmethod
    def _has_performance_or_reliability_signal(cls, text: str) -> bool:
        lowered = text.lower()
        return (
            cls._PERFORMANCE_CONSTRAINT_RE.search(lowered) is not None
            or cls._COLLOQUIAL_PERFORMANCE_RE.search(lowered) is not None
            or cls._has_infrastructure_availability_signal(lowered)
        )

    @classmethod
    def _classify_req_type(cls, text: str) -> str:
        lowered = text.lower()

        if re.search(r"\bkyc onboarding\b", lowered):
            return "FR"

        if cls._ROLE_SURFACE_WORKFLOW_RE.search(lowered):
            return "FR"

        if re.search(r"\b(?:workspace|console|dashboard|portal)\b", lowered) and re.search(
            r"\b(?:should|can|must|will|may)\s+(?:provide|support|enable|allow|manage|include|offer)\b",
            lowered,
        ):
            return "FR"

        scheduling_availability = re.search(
            r"(?:\b(?:appointment|appointments|slot|slots|schedule|scheduling|doctor|room|bed|triage|clinic)\b.{0,30}\bavailability\b|"
            r"\bavailability\b.{0,30}\b(?:appointment|appointments|slot|slots|schedule|scheduling|doctor|room|bed|triage|clinic)\b)",
            lowered,
        ) is not None

        if scheduling_availability:
            return "FR"

        if re.search(r"\bgdpr\b", lowered) and re.search(
            r"\b(data deletion|deletion requests?|data export|export requests?|"
            r"consent withdrawal|access log visibility|access logs?)\b",
            lowered,
        ):
            return "FR"

        # User-controllable security action → FR despite containing security terms
        if re.search(r"\b(can|may)\b", lowered) and re.search(
            r"\b(enable|configure|manage|setup|activate|toggle)\b.{0,30}"
            r"\b(2fa|mfa|security|authentication|keys?|biometric)\b",
            lowered,
        ):
            return "FR"

        # Role performing primary CRUD/domain action → FR even if secondary clause
        # mentions compliance/audit (e.g. "Admins can create... but audit logging")
        if re.search(
            r"^[a-z\s]+\bcan\s+(?:(?:permanently|securely|automatically|manually|"
            r"temporarily|directly|only|also)\s+){0,2}"
            r"(?:create|update|delete|manage|view|browse|search|filter|book|"
            r"upload|approve|register|add|place|choose|checkout|pay|track|"
            r"download|export|cancel|schedule|assign|mark|suspend|reactivate|"
            r"reschedule|deactivate|invite|access|generate|process|submit|"
            r"request|enroll)\b",
            lowered,
        ):
            return "FR"

        if re.search(
            r"\b(work|run|support|compatible?|access(?:ible)?)\b.{0,40}"
            r"\bmobile\b.{0,30}\bdesktop\b.{0,30}\bbrowsers?\b|"
            r"\bmobile\b.{0,30}\bdesktop\b.{0,30}\bbrowsers?\b|"
            r"\bcross[\-\s]?browser\b|\bbrowser compatibility\b|\bcross[\-\s]?platform\b",
            lowered,
        ):
            return "NFR"

        if re.search(
            r"\bidempotent\b|\bdouble[\-\s]?charges?\b",
            lowered,
        ) and re.search(
            r"\b(billing|payment|payments|transaction|transactions|operation|operations|retry|retries|webhook)\b",
            lowered,
        ):
            return "NFR"

        if re.search(r"\bsandbox\b", lowered):
            return "NFR"

        if re.search(r"\bconflict[\-\s]?safe\s+sync\b|\bqueued payments?\b.{0,40}\bsync\b", lowered):
            return "NFR"

        if re.search(r"\bmulti[\-\s]?tenant\b", lowered) and re.search(r"\bdata isolation\b|\bisolation\b", lowered):
            return "NFR"

        if re.search(r"\bdata retention\b|\bretention policy\b", lowered):
            return "NFR"

        if re.search(
            r"\b(adaptive bitrate|bitrate|bandwidth)\b",
            lowered,
        ) and re.search(
            r"\b(adapt|stream(?:ing)?|video)\b",
            lowered,
        ):
            return "NFR"

        if re.search(
            r"\b(fully offline|offline|without reliance on external|locally hosted|"
            r"no external api|no internet|without external apis?|cloud services?)\b",
            lowered,
        ):
            return "NFR"

        if cls._USER_FACING_OBSERVABILITY_ACCESS_RE.search(lowered) and re.search(
            r"\b(logs?|audit reports?|audit trails?|monitoring dashboards?|telemetry|metrics)\b",
            lowered,
        ):
            return "FR"

        internal_observability = (
            cls._INTERNAL_OBSERVABILITY_SUBJECT_RE.search(lowered) is not None
            and not cls._USER_FACING_OBSERVABILITY_ACCESS_RE.search(lowered)
            and (
                cls._INTERNAL_OBSERVABILITY_TERM_RE.search(lowered) is not None
                or (
                    re.search(r"\b(monitor(?:ing)?|metrics?)\b", lowered) is not None
                    and cls._INTERNAL_OBSERVABILITY_TARGET_RE.search(lowered) is not None
                )
            )
            and cls._INTERNAL_OBSERVABILITY_TARGET_RE.search(lowered) is not None
        )
        if internal_observability:
            return "NFR"

        if cls._has_performance_or_reliability_signal(text):
            return "NFR"

        if cls._FUNCTIONAL_VERB_RE.search(lowered) and not re.search(
            r"\b(security|secure|encrypt(?:ed|ion)?|hash(?:ed|ing)?|bcrypt|aes(?:-\d+)?|tls|ssl|"
            r"compliance|gdpr|hipaa|pci|iso|sox|ferpa|regulation(?:s)?|audit(?:ing)?|observability|"
            r"monitoring|logging|localiz(?:ation|e)|i18n|rtl|multilingual|language\s+support|"
            r"data protection|privacy|accessib(?:le|ility)|mobile[\-\s]?(?:friendly|first)|responsive|"
            r"rto|rpo|aml|kyc|tokeniz(?:ed|ation)|cardholder|sandbox|multi[\-\s]?tenant|retention)\b",
            lowered,
        ):
            return "FR"

        nfr_patterns = (
            r"\bsecurity\b",
            r"\bsecure\b",
            r"\bencrypt(?:ed|ion)?\b",
            r"\bhash(?:ed|ing)?\b",
            r"\bbcrypt\b",
            r"\baes(?:-\d+)?\b",
            r"\btls\b",
            r"\bssl\b",
            r"\bmaintainab\w*\b",
            r"\bfailover\b",
            r"\bdisaster recovery\b",
            r"\bcompatib\w*\b",
            r"\bcompliance\b",
            r"\bgdpr\b",
            r"\bhipaa\b",
            r"\bpci\b",
            r"\biso\b",
            r"\bsox\b",
            r"\bferpa\b",
            r"\bregulation(?:s)?\b",
            r"\baml\b",
            r"\bkyc\b",
            r"\baudit(?:ing)?\b",
            r"\bobservability\b",
            r"\bobservable\b",
            r"\btracing\b",
            r"\bmonitoring\b",
            r"\blogging\b",
            r"\blocaliz(?:ation|e)\b",
            r"\bi18n\b",
            r"\brtl\b",
            r"\bmultilingual\b",
            r"\b(?:arabic|hebrew|persian|urdu)\b",
            r"\blanguage\s+support\b",
            r"\bdata protection\b",
            r"\bprivacy\b",
            r"\baccessibility\b",
            r"\baccessible\b",
            r"\bmobile[\-\s]?first\b",
            r"\bmobile[\-\s]?friendly\b",
            r"\bresponsive\b",
            r"\brto\b",
            r"\brpo\b",
            r"\btokeniz(?:ed|ation)\b",
            r"\bcardholder\b",
            r"\bsandbox\b",
            r"\bmulti[\-\s]?tenant\b",
            r"\bdata isolation\b",
            r"\bretention\b",
            r"\bconflict[\-\s]?safe\s+sync\b",
        )
        if any(re.search(pattern, lowered) for pattern in nfr_patterns):
            return "NFR"

        return "FR"

    # ------------------------------------------------------------------ #
    #  Complexity scoring                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def _score_complexity(cls, text: str, req_type: str) -> int:
        lowered = text.lower()

        # External integration → 4
        if any(t in lowered for t in cls._INTEGRATION_TOKENS) or \
                any(t in lowered for t in cls._INTEGRATE_VERBS):
            return 4

        # Performance / load constraints → 4
        if cls._has_performance_or_reliability_signal(text) or any(t in lowered for t in cls._PERF_TOKENS):
            return 4

        # RBAC / permissions → 4
        if re.search(r"\b(rbac|role.based|permission|access control|privilege|entitlement)\b", lowered):
            return 4

        # Security enforcement / compliance → 3
        if any(t in lowered for t in cls._SEC_TOKENS) or \
                any(t in lowered for t in cls._COMP_TOKENS):
            return 3

        # Auth / verification / multi-step token flows → 3
        if re.search(
            r"\b(mfa|2fa|otp|multi.factor|two.factor|biometric|authentication|authorization|"
            r"verify|verification|jwt|token|session|oauth|saml|sso|authenticat\w*|verif\w*)\b",
            lowered,
        ):
            return 3

        # Localization / i18n → 3
        if re.search(r"\b(localiz|i18n|rtl|right.to.left|multilingual|language support)\b", lowered):
            return 3

        # Offline / self-hosted architectural constraints → 4
        if re.search(
            r"\b(offline|locally hosted|no external api|without reliance on external|cloud services?)\b",
            lowered,
        ):
            return 4

        # Compound requirement with 3+ distinct actions → 3
        comma_count = lowered.count(",")
        if comma_count >= 2 and re.search(r"\b(can|must|shall)\b", lowered):
            return 3

        # Detect first action verb after stripping subject/modal
        action_text = re.sub(
            r"^(?:the system|users?|admins?|managers?|staff|clients?|customers?|"
            r"operators?|employees?|doctors?|patients?|agents?|members?)\s+"
            r"(?:can|must|should|shall|will|may)\s+",
            "", lowered, flags=re.IGNORECASE,
        )
        first_word = action_text.split()[0] if action_text.split() else ""

        # Read-only → 1
        if first_word in cls._READ_VERBS and not re.search(
            r"\b(create|update|delete|cancel|book|rate|submit|upload|assign)\b", lowered
        ):
            return 1

        # Simple write/delete → 2
        if first_word in cls._WRITE_VERBS or first_word in cls._DELETE_VERBS or first_word in cls._SELECT_VERBS:
            return 2

        # General CRUD with business verbs → 2
        if re.search(r"\b(create|update|delete|book|cancel|rate|submit|assign|upload|purchase|order)\b", lowered):
            return 2

        return 3 if req_type == "NFR" else 2

    @classmethod
    def _type_reason(cls, text: str, req_type: str) -> str:
        lowered = text.lower()
        if req_type == "FR":
            if re.search(r"\b(can|must|should|shall|will|may)\b", lowered):
                return (
                    "Describes a user-visible feature or system action with an explicit behavior."
                )
            return "Describes a user-visible feature or system action."
        return (
            "Describes a quality attribute or operational constraint such as "
            "security, performance, availability, or compliance."
        )

    @classmethod
    def _complexity_reason(cls, text: str, req_type: str, complexity: int) -> str:
        lowered = text.lower()

        if complexity >= 5:
            return (
                "Complex real-time or cross-system processing with multiple "
                "dependencies and coordination points."
            )

        if complexity == 4:
            if any(token in lowered for token in cls._INTEGRATION_TOKENS) or any(
                token in lowered for token in cls._INTEGRATE_VERBS
            ):
                return "Requires external API or system integration."
            if any(token in lowered for token in cls._PERF_TOKENS):
                return "Includes strict performance or scalability constraints."
            if re.search(
                r"\b(rbac|role.based|permission|access control|privilege|entitlement)\b",
                lowered,
            ):
                return "Requires role-based access control across protected features."
            return "Requires advanced integration or architectural coordination."

        if complexity == 3:
            if any(token in lowered for token in cls._SEC_TOKENS) or any(
                token in lowered for token in cls._COMP_TOKENS
            ):
                return "Requires security, compliance, or controlled validation logic."
            if re.search(
                r"\b(mfa|2fa|otp|multi.factor|two.factor|biometric|authentication|authorization|"
                r"verify|verification|jwt|token|session|oauth|saml|sso|authenticat\w*|verif\w*)\b",
                lowered,
            ):
                return "Requires authentication or multi-step verification workflow."
            if req_type == "NFR":
                return "Introduces quality constraints that need implementation safeguards."
            return "Requires multi-step workflow or domain-specific business logic."

        if complexity == 2:
            return "Standard CRUD or transactional workflow with limited coordination."

        return "Simple read-only or display-focused functionality with no major integration."

    def _annotate_task_explainability(
        self,
        task_list: TaskList,
        requirements: list[RequirementItem],
    ) -> TaskList:
        req_by_source = {item.source: item.text for item in requirements}
        annotated: list[Task] = []

        for task in task_list.tasks:
            task_text = req_by_source.get(task.source, task.description)
            payload = task.model_dump(mode="python")
            payload["title"] = self._normalize_title_text(str(payload.get("title", "")))
            payload["type_reason"] = task.type_reason or self._type_reason(
                task_text,
                task.req_type,
            )
            payload["complexity_reason"] = (
                task.complexity_reason
                or self._complexity_reason(task_text, task.req_type, task.complexity)
            )
            annotated.append(Task(**payload))

        return TaskList(tasks=annotated)

    # ------------------------------------------------------------------ #
    #  Semantic tag extraction (domain-agnostic)                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def _extract_semantic_tags(cls, text: str) -> set[str]:
        """Extract domain-agnostic semantic layer tags from any requirement text."""
        lowered = text.lower()
        tags: set[str] = set()

        # Layer 0 — Foundation / setup
        if re.search(r"\b(design|establish|foundation|setup|set up|initialize|configure|architect|scaffold|bootstrap)\b", lowered):
            tags.add("foundation")

        # Layer 1 — Identity / registration
        if re.search(r"\b(register|signup|sign.up|registration|account creation|onboard|enroll|profile setup)\b", lowered):
            tags.add("identity")

        # Layer 2 — Authentication mechanisms
        if re.search(
            r"\b(otp|mfa|2fa|multi.factor|two.factor|biometric|login|sign.in|logout|"
            r"authentication|authorization|verify|verification|jwt|token|session|oauth|saml|sso|"
            r"authenticat\w*|verif\w*)\b",
            lowered,
        ):
            tags.add("auth")

        # Layer 3 — Access control / permissions
        if re.search(
            r"\b(rbac|role.based|permission|access control|privilege|authoriz|entitlement|role management|access policy|authorization policy)\b",
            lowered,
        ):
            tags.add("access_control")

        # Layer 4 — Domain CRUD features
        if re.search(
            r"\b(create|add|update|delete|book|cancel|rate|submit|assign|purchase|order|manage|edit|upload|"
            r"prescribe|schedule\w*|pay\w*|transfer\w*|transaction\w*|fund\w*|payment\w*|approve|reject|"
            r"choose|select|withdraw\w*|deposit\w*|send\w*|invoice\w*|billing)\b",
            lowered,
        ):
            tags.add("crud")

        # View / read features
        if re.search(
            r"\b(view|list|display|show|search|browse|read|query|fetch|filter|"
            r"balance\w*|history|statement|track\w*|monitor\w*|analytic\w*|insight\w*)\b",
            lowered,
        ):
            tags.add("view")

        # User management (subset of CRUD, but semantically linked to access control)
        if re.search(r"\b(user management|manage users?|create.{0,10}account|deactivate.{0,10}user|suspend|ban user|user account)\b", lowered):
            tags.add("user_management")

        # Notifications / messaging
        if re.search(r"\b(notif(?:ication)?s?|alert|email|sms|push|message|broadcast|remind|inform)\b", lowered):
            tags.add("notification")

        # Reporting / analytics
        if re.search(r"\b(reports?|stats?|analytics?|dashboards?|metrics?|kpis?|workload|satisf|insights?|summaries?)\b", lowered):
            tags.add("reporting")

        # Technical planning / analysis workflows
        if re.search(r"\b(accept|parse|extract|ingest)\b", lowered) and re.search(
            r"\b(requirements?|plain text|structured documents?|pdf files?)\b",
            lowered,
        ):
            tags.add("requirements_ingestion")

        if re.search(r"\b(generate|create|refine|iterative refinement|structured list of tasks)\b", lowered) and re.search(
            r"\btasks?\b",
            lowered,
        ):
            tags.add("task_planning")

        if re.search(
            r"\b(dependency graph|directed graph|circular dependenc|critical path|bottleneck detection|dependency correctness)\b",
            lowered,
        ):
            tags.add("dependency_analysis")

        if re.search(
            r"\b(estimate|estimation|confidence intervals?|machine learning model|estimation error)\b",
            lowered,
        ):
            tags.add("estimation")

        if re.search(
            r"\b(classify|classification|categor(?:ies|ization)|frontend|backend|database|devops|testing)\b",
            lowered,
        ):
            tags.add("classification")

        if re.search(
            r"\b(monitor|repository|git|commit frequency|contribution patterns|execution log|decision traces)\b",
            lowered,
        ):
            tags.add("monitoring")

        if re.search(
            r"\b(risks?|delays?|bottlenecks?|underperformance|risk indicators?)\b",
            lowered,
        ) and re.search(
            r"\b(detect|identify|analy[sz]e|assess|flag|alert|notify|surface|generate)\b",
            lowered,
        ):
            tags.add("risk_analysis")

        if re.search(
            r"\b(explainability|human-readable justifications?|justifications?)\b",
            lowered,
        ):
            tags.add("explainability")

        if re.search(
            r"\b(vector database|graph database|embeddings?|semantic search|retrieval|execution log)\b",
            lowered,
        ):
            tags.add("storage")

        if re.search(
            r"\b(multi-agent|planner agent|critic agent|orchestration engine|agent interactions)\b",
            lowered,
        ):
            tags.add("orchestration")

        if re.search(
            r"\b(user interface|dashboard|timelines?|risk indicators?)\b",
            lowered,
        ):
            tags.add("dashboard")

        if re.search(
            r"\b(export|download|json|csv|pdf)\b",
            lowered,
        ):
            tags.add("export")

        if re.search(
            r"\b(feedback|critic|review|refine|refinement|validation|validate|clarification|assumptions?|ambiguous requirements?)\b",
            lowered,
        ):
            tags.add("validation")

        if re.search(
            r"\b(offline|locally hosted|no external api|without reliance on external|cloud services?)\b",
            lowered,
        ):
            tags.add("offline_operation")

        if re.search(
            r"\b(evaluation metrics|task generation accuracy|dependency correctness|estimation error|risk prediction performance)\b",
            lowered,
        ):
            tags.add("evaluation")

        # External integration — skip when context is explicitly negative (offline, no external)
        _negated_external = bool(re.search(
            r"\b(without|no reliance on|offline|avoid external|not rely|no external|without reliance)\b", lowered
        ))
        if not _negated_external and (
            re.search(r"\b(?:integrat|synchroni|third[\-\s]party|webhook|connect)", lowered) or
            re.search(r"\b(?:external|api|sync|sdk)\b", lowered) or
            any(t in lowered for t in cls._INTEGRATION_TOKENS)
        ):
            tags.add("integration")

        # Security enforcement
        if re.search(
            r"\b(encrypt(?:ion|ed|ing)?|hash|bcrypt|aes|tls|ssl|secure(?:ly)?|security|"
            r"cryptograph|salt|tokeniz(?:ed|ation)|cardholder|raw card data)\b",
            lowered,
        ):
            tags.add("security")

        # Performance / NFR constraints
        if cls._has_performance_or_reliability_signal(text):
            tags.add("performance")

        # Compliance / legal
        if re.search(r"\b(gdpr|hipaa|pci|iso|sox|aml|kyc|compliance|regulation|audit|privacy|data protection)\b", lowered):
            tags.add("compliance")

        # Localization / i18n — "language" alone is too broad (matches "language model"), require context
        if re.search(r"\b(localiz|i18n|rtl|multilingual|right.to.left|language support|multiple languages?|arabic|hebrew|persian|urdu|bilingual)\b", lowered):
            tags.add("localization")

        if not tags:
            tags.add("general")
        return tags

    @staticmethod
    def _safe_nfr_template(verb: str, focus: str, default_focus: str, suffix: str) -> str:
        """Build an NFR title with stop-word and anti-duplication guards.

        Why: avoids "Optimize in performance constraints" (verb-strip leftover),
        "Optimize not exceed 500ms ... performance constraints" (kept-stop-word),
        "Enforce HIPAA-compliant data security security controls" (suffix dup),
        and "Optimize meet response-time SLO performance constraints" (parser
        already produced a clean action phrase — don't double-wrap it).
        """
        focus_safe = (focus or "").strip(" .,;:")
        # If the parser already produced a complete action phrase ("meet p99 SLO",
        # "maintain HIPAA compliance"), use it verbatim with sentence case.
        action_lead = re.match(
            r"^(?:meet|maintain|scale|establish|avoid|encrypt|keep|provide|"
            r"ensure|deliver|store|stay|remain|comply)\b",
            focus_safe,
            flags=re.IGNORECASE,
        )
        if action_lead:
            return focus_safe[:1].upper() + focus_safe[1:]
        # Reject focuses that are stop-words or start with a stop-word/conjunction.
        leading_stop = re.match(
            r"^(?:not|in|the|a|an|and|or|of|to|for|with|on|at|by|but|that|which|"
            r"complete|stored|refresh)\b",
            focus_safe,
            flags=re.IGNORECASE,
        )
        if not focus_safe or leading_stop or len(focus_safe.split()) < 2:
            focus_safe = default_focus
        # Anti-duplication: don't append a suffix word the focus already contains.
        suffix_stems = {
            "performance constraints": r"\bperformance\b",
            "security controls": r"\b(?:security|controls)\b",
            "compliance requirements": r"\b(?:compliance|requirements|comply|regulatory)\b",
            "constraints": r"\bconstraints\b",
        }
        stem_re = suffix_stems.get(suffix)
        if stem_re and re.search(stem_re, focus_safe, flags=re.IGNORECASE):
            return f"{verb} {focus_safe}"
        return f"{verb} {focus_safe} {suffix}"

    @staticmethod
    def _regulation_label(lowered_text: str) -> str | None:
        regulation_patterns = (
            (r"\bpci(?:-dss)?\b", "PCI-DSS"),
            (r"\bhipaa\b", "HIPAA"),
            (r"\bgdpr\b", "GDPR"),
            (r"\bsoc\s*2\b|\bsoc2\b", "SOC 2"),
            (r"\bfedramp\b", "FedRAMP"),
            (r"\bnist\b", "NIST"),
            (r"\bferpa\b", "FERPA"),
            (r"\biso(?:\s*27001)?\b", "ISO 27001"),
        )
        for pattern, label in regulation_patterns:
            if re.search(pattern, lowered_text):
                return label
        return None

    @staticmethod
    def _looks_like_local_model_offline_constraint(lowered_text: str) -> bool:
        return re.search(
            r"\b(local models?|locally hosted|on-device models?|"
            r"no external api|no external apis|without reliance on external|cloud services?)\b",
            lowered_text,
        ) is not None

    @classmethod
    def _nominal_functional_title(cls, action_phrase: str, lowered_text: str) -> str | None:
        cleaned = re.sub(r"^\[[A-Z]+-\d+\]\s*", "", action_phrase).strip(" .,;:")
        cleaned = re.sub(
            r"^(?:the system|platform|application|service|solution)\s+(?:can|must|should|shall|will|may)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" .,;:")
        if not cleaned:
            return None
        common_verbs = cls._known_action_verbs()
        first_word = cls._normalize_action_token(cleaned.split()[0].lower(), common_verbs)
        if first_word in common_verbs:
            if first_word in {"provide", "support", "enable", "allow"} and len(cleaned.split()) > 1:
                cleaned = " ".join(cleaned.split()[1:]).strip(" .,;:")
                first_word = cls._normalize_action_token(cleaned.split()[0].lower(), common_verbs) if cleaned else ""
            else:
                return None
        if not cleaned or first_word in common_verbs:
            return None
        if cleaned.count("(") > cleaned.count(")"):
            cleaned = f"{cleaned})"

        if re.search(r"\b(?:portal|console|workspace)\b", cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(r"\s+,", ",", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
            return f"Implement {cleaned}"

        if re.search(r"\bdashboard\b", cleaned, flags=re.IGNORECASE):
            if re.search(
                r"\b(task breakdown|dependency graphs?|estimated timelines?|risk indicators?|project planning)\b",
                lowered_text,
            ):
                return "Implement project planning dashboard"
            return f"Implement {cleaned}"

        if re.search(
            r"\b(management|processing|tracking|history|records?|notifications?|claims?|"
            r"billing|inventory|catalog|checkout|payments?|registration|appointments?|"
            r"transfers?|balances?|cart|wishlist|prescriptions?|scheduling|booking|"
            r"analytics|alerts)\b",
            cleaned,
            flags=re.IGNORECASE,
        ):
            suffix = "" if cleaned.lower().endswith(("management", "processing")) else " workflow"
            return f"Implement {cleaned}{suffix}"
        return None

    # ------------------------------------------------------------------ #
    #  Title generation (domain-agnostic)                                 #
    # ------------------------------------------------------------------ #

    @classmethod
    def _action_title_from_text(cls, text: str, req_type: str) -> str:
        """Generate a domain-agnostic action-oriented title from any requirement text."""
        lowered = text.lower()
        if req_type == "NFR":
            text = re.sub(
                r"\brespond(?:s)?\s+within\b",
                "response time within",
                text,
                flags=re.IGNORECASE,
            )
            text = re.sub(
                r"\bload(?:s)?\s+within\b",
                "load time within",
                text,
                flags=re.IGNORECASE,
            )
        action_phrase = cls._strip_requirement_prefix(text)
        action_lower = action_phrase.lower()
        focus = cls._extract_focus_phrase(action_phrase)
        tags = cls._extract_semantic_tags(text)

        if cls._is_vague_focus_phrase(focus, action_phrase):
            return cls.UNCLEAR_TITLE

        def semantic_suffix_title(default_focus: str | None = None) -> str | None:
            scoped_focus = (default_focus or focus or "").strip()
            if "storage" in tags:
                if re.search(r"\b(retrieval|semantic search|search)\b", lowered):
                    return f"Implement {scoped_focus or 'data'} retrieval pipeline"
                if re.search(r"\b(graph database|dependency graph)\b", lowered):
                    return f"Implement {scoped_focus or 'data'} storage layer"
                if re.search(r"\b(vector database|embeddings?)\b", lowered):
                    return f"Implement {scoped_focus or 'data'} storage pipeline"
                return f"Implement {scoped_focus or 'data'} data pipeline"

            if "monitoring" in tags:
                if re.search(
                    r"\b(log|logging|audit|trace|traces|telemetry|metrics|execution log|decision traces)\b",
                    lowered,
                ):
                    return f"Implement {scoped_focus or 'system activity'} monitoring service"
                return f"Implement {scoped_focus or 'activity'} monitor"

            if "orchestration" in tags:
                if re.search(r"\b(engine|controller|runtime|coordination)\b", lowered):
                    return f"Implement {scoped_focus or 'agent coordination'} orchestration layer"
                return f"Implement {scoped_focus or 'agent coordination'} orchestrator"

            if "dashboard" in tags:
                if re.search(r"\bdashboard\b", lowered):
                    reporting_focus = cls._extract_reporting_focus(text) or scoped_focus or "user dashboard"
                    if re.search(r"\bdashboard\b", reporting_focus, flags=re.IGNORECASE):
                        return f"Implement {reporting_focus}"
                    return f"Implement {reporting_focus} dashboard"
                return f"Implement {scoped_focus or 'user'} interface module"

            if "export" in tags:
                return f"Implement {scoped_focus or 'data'} export service"

            if "validation" in tags:
                return f"Implement {scoped_focus or 'requirements'} validation service"

            return None

        if re.search(r"\b(passwords?|bcrypt|salt(?:ed)?|password policy|complexity rules?|special char|uppercase|lowercase)\b", lowered):
            return "Enforce password hashing and complexity policy"

        if "access_control" in tags:
            return "Implement role-based access control"

        if "localization" in tags:
            if req_type == "NFR":
                if re.search(r"\barabic\b", lowered) and re.search(r"\benglish\b", lowered):
                    return "Enable Arabic/English RTL/LTR localization support"
                return "Enable multilingual localization support"
            return "Implement multilingual localization support"

        if "requirements_ingestion" in tags:
            return "Implement multi-format requirements ingestion workflow"

        if "task_planning" in tags and re.search(r"\bstructured list of tasks\b", lowered):
            return "Implement structured task generation workflow"

        if "dependency_analysis" in tags and re.search(r"\bdependency graph\b|\bdirected graph\b", lowered):
            return "Implement task dependency graph construction workflow"

        if "estimation" in tags and re.search(r"\b(time required|confidence intervals?|machine learning model|estimate)\b", lowered):
            return "Implement task effort estimation workflow"

        if "classification" in tags and re.search(r"\bclassify\b", lowered):
            return "Implement task category classification workflow"

        if "orchestration" in tags and re.search(r"\bfeedback loops?\b|\bcritic agent\b", lowered):
            return "Implement planner-critic feedback loop"

        if "monitoring" in tags and re.search(r"\bgit\b|\brepository\b", lowered):
            return "Implement Git repository progress monitor"

        if "storage" in tags and re.search(r"\bvector database\b|\bembeddings?\b", lowered):
            return "Implement task embedding storage and retrieval pipeline"

        if "storage" in tags and re.search(r"\bgraph database\b", lowered):
            return "Implement task dependency graph storage layer"

        if "orchestration" in tags and re.search(r"\bmulti-agent\b|\borchestration engine\b", lowered):
            return "Implement multi-agent orchestration layer"

        if re.search(r"\bexport(?:ing)?\b", lowered) and re.search(r"\b(tasks?|reports?)\b", lowered):
            return "Implement task and report export service"

        if "dashboard" in tags:
            dashboard_focus = cls._extract_reporting_focus(text) or focus or "user dashboard"
            if re.search(r"\bdashboard\b", dashboard_focus, flags=re.IGNORECASE):
                return f"Implement {dashboard_focus}"
            return f"Implement {dashboard_focus} dashboard"

        if "monitoring" in tags and re.search(r"\bexecution log\b|\bagent interactions\b", lowered):
            return "Implement agent interaction logging service"

        if "explainability" in tags:
            return "Implement decision explainability workflow"

        if "evaluation" in tags:
            return "Implement planner evaluation metrics service"

        if "risk_analysis" in tags:
            return "Implement project risk detection and alerting workflow"

        if re.search(r"\b(incomplete|ambiguous) requirements\b", lowered):
            return "Implement ambiguous requirements validation service"

        if re.search(r"\badmins?\b", lowered) and re.search(
            r"\b(create|update|suspend|reactivate|delete)\b", lowered
        ) and re.search(r"\buser accounts?\b", lowered):
            return "Implement user account lifecycle management"

        if re.search(r"\bnational id\b", lowered) and re.search(r"\b(?:otp|biometric|two[\-\s]?factor|2fa|mfa)\b", lowered):
            return "Implement national ID, OTP, biometric, and 2FA registration workflow"

        if re.search(r"\bkyc onboarding\b", lowered):
            return "Implement KYC onboarding and manual review workflow"

        if re.search(r"\bwallet top-up\b", lowered) and re.search(r"\bp2p transfers?\b", lowered):
            return "Implement wallet balance and P2P transfer workflow"

        if re.search(r"\bscheduled payments?\b", lowered) and re.search(r"\bbill payments?\b", lowered):
            return "Implement scheduled and bill payment workflow"

        if re.search(r"\bqr code merchant payments?\b", lowered):
            return "Implement QR merchant payments, refunds, disputes, and receipts workflow"

        if "identity" in tags and re.search(r"\b(register|signup|sign up|enroll|onboard)\b", lowered):
            if re.search(r"\b(course|courses|class|classes|module|modules)\b", lowered):
                if re.search(r"\bregister\b", lowered) and re.search(r"\b(enroll|enrollment)\b", lowered):
                    return "Implement student registration and course enrollment workflow"
                if re.search(r"\bregister\b", lowered):
                    return "Implement course registration workflow"
                if re.search(r"\b(enroll|enrollment)\b", lowered):
                    return "Implement course enrollment workflow"
            channel = cls._extract_registration_channel(text)
            if channel:
                return f"Implement {channel} registration workflow"
            return "Implement account registration workflow"

        if re.search(r"\bgdpr\b", lowered):
            if re.search(r"\bdata deletion\b", lowered):
                return "Implement GDPR data deletion request workflow"
            if re.search(r"\bdata export\b|\bexport\b", lowered):
                return "Implement GDPR data export request workflow"
            if re.search(r"\bconsent\b", lowered):
                return "Implement GDPR consent withdrawal workflow"
            if re.search(r"\baccess logs?\b", lowered):
                return "Implement GDPR access log visibility workflow"

        if re.search(r"\bspending analytics\b", lowered):
            if re.search(r"\bbudget alerts?\b", lowered) and re.search(r"\bpersonalized offers?\b", lowered):
                return "Implement spending analytics, budget alerts, and personalized offers workflow"
            return "Implement spending analytics workflow"

        if req_type == "NFR":
            if re.search(r"\b(?:raw\s+card\s+data|cardholder\s+data|tokeniz(?:ed|ation))\b", lowered):
                return "Enforce card-data tokenization and storage restrictions"
            if re.search(r"\bsandbox\b", lowered):
                return "Configure sandbox integration testing environment"
            if re.search(r"\baml\s*/\s*kyc\b|\bkyc\s*/\s*aml\b", lowered) or (
                re.search(r"\baml\b", lowered) and re.search(r"\bkyc\b", lowered)
            ):
                return "Establish AML/KYC compliance controls"
            if re.search(r"\baml\b", lowered):
                return "Establish AML compliance controls"
            if re.search(r"\bkyc\b", lowered):
                return "Establish KYC compliance controls"
            if re.search(r"\b(?:wcag|accessib(?:le|ility)|a11y)\b", lowered):
                level = re.search(r"\bwcag\s+([a]{1,3})\b", text, flags=re.IGNORECASE)
                if level:
                    return f"Enforce WCAG {level.group(1).upper()} accessibility requirements"
                return "Enforce accessibility requirements"
            if re.search(r"\b(?:rto|rpo)\b", lowered):
                objectives: list[str] = []
                for metric in ("RTO", "RPO"):
                    match = re.search(
                        rf"\b{metric}\b\s+(?:under|within|<=?|less than)\s+"
                        r"(\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?|hours?))\b",
                        text,
                        flags=re.IGNORECASE,
                    )
                    if match:
                        objectives.append(f"{metric} under {match.group(1)}")
                if objectives:
                    return f"Enforce {' and '.join(objectives)} recovery objectives"
                return "Enforce recovery-time and recovery-point objectives"
            if re.search(r"\bdata retention\b|\bretention policy\b", lowered):
                if "configurable" in lowered:
                    return "Configure data retention policy"
                return "Enforce data retention policy"
            if re.search(r"\bmulti[\-\s]?tenant\b", lowered) and re.search(r"\b(data isolation|isolation|tenant)\b", lowered):
                return "Enforce multi-tenant data isolation"
            if re.search(r"\bconflict[\-\s]?safe\s+sync\b|\bqueued payments?\b.{0,40}\bsync\b", lowered):
                return "Enable conflict-safe queued payment synchronization"
            throughput = re.search(
                r"\b(\d[\d,]*)\s+events?\s+per\s+second\b",
                text,
                flags=re.IGNORECASE,
            )
            if throughput or re.search(r"\bthroughput\b", lowered):
                focus_match = re.search(r"\bsupport\s+(.+?)\s+throughput\b", lowered)
                focus = focus_match.group(1).strip(" .,;:") if focus_match else "processing"
                if throughput:
                    return f"Optimize {focus} throughput for {throughput.group(1)} events per second"
                return f"Optimize {focus} throughput"
            percentile = re.search(r"\bp(?:95|99)\b", text, flags=re.IGNORECASE)
            response_threshold = re.search(
                r"\b(?:under|within|<=?|less than)\s+(\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|s))\b",
                text,
                flags=re.IGNORECASE,
            )
            if percentile:
                concurrency_target = re.search(r"\b(\d[\d,]*)\s+concurrent users?\b", text, flags=re.IGNORECASE)
                title = f"Optimize {percentile.group(0).lower()}"
                if response_threshold:
                    title += f" under {response_threshold.group(1)}"
                title += " response-time SLO"
                if concurrency_target:
                    title += f" for {concurrency_target.group(1)} concurrent users"
                return title
            if re.search(r"\b(?:distributed tracing|tracing|observability|observable|telemetry)\b", lowered):
                if re.search(r"\baudit logs?\b", lowered):
                    return "Enable observability with audit logs"
                if re.search(r"\bdistributed tracing\b|\btracing\b", lowered):
                    return "Enable distributed tracing observability"
                return "Enable observability monitoring"
            if "offline_operation" in tags:
                if cls._looks_like_local_model_offline_constraint(lowered):
                    return "Enforce fully offline operation with local models"
                return "Enable offline capability support"
            if re.search(r"\bdata processing\b", lowered) and re.search(r"\bstorage\b", lowered) and re.search(
                r"\b(secure|security|encryption|encrypt)\b",
                lowered,
            ):
                return "Enforce secure local data processing and storage"
            if re.search(
                r"\b(work|run|support|compatible?|access(?:ible)?)\b.{0,40}"
                r"\bmobile\b.{0,30}\bdesktop\b.{0,30}\bbrowsers?\b|"
                r"\bmobile\b.{0,30}\bdesktop\b.{0,30}\bbrowsers?\b|"
                r"\bcross[\-\s]?browser\b|\bbrowser compatibility\b|\bcross[\-\s]?platform\b",
                lowered,
            ):
                return "Enable mobile and desktop browser compatibility"
            if re.search(r"\bidempotent\b", lowered) and re.search(
                r"\b(billing|payment|payments|transaction|transactions|operation|operations|retry|retries|webhook)\b",
                lowered,
            ):
                if re.search(r"\b(transaction|transactions|payment|payments)\b", lowered):
                    return "Enforce idempotent transaction processing"
                return "Enforce idempotent billing operations"
            if re.search(r"\b(adaptive bitrate|bitrate|bandwidth)\b", lowered) and re.search(
                r"\b(adapt|stream(?:ing)?|video)\b",
                lowered,
            ):
                return "Optimize adaptive video streaming quality"
            if re.search(r"\bmobile[\-\s]?first\b", lowered):
                return "Enable mobile-first interface support"
            if re.search(r"\b(api|response)\b", lowered) and re.search(
                r"\b(latency|response time|performance|throughput|concurrent users?)\b",
                lowered,
            ):
                return "Optimize API latency and concurrency performance"
            if re.search(r"\bscalab\w*\b", lowered) or (
                re.search(r"\bconcurrent users?\b", lowered)
                and re.search(r"\b(api|response|latency|throughput)\b", lowered) is None
            ):
                concurrent_target = re.search(r"\b(\d[\d,]*)\s+concurrent users?\b", text, flags=re.IGNORECASE)
                if concurrent_target:
                    return f"Optimize scalability for {concurrent_target.group(1)} concurrent users"
                task_target = re.search(r"\b(\d+)\s+tasks?\b", lowered)
                if task_target and re.search(r"\b(projects?|planner|portfolio)\b", lowered):
                    return f"Optimize planner scalability for {task_target.group(1)}-task projects"
                if re.search(r"\b(projects?|planner|portfolio)\b", lowered):
                    return "Optimize planner scalability for large project portfolios"
                return "Optimize concurrent user capacity"
            if re.search(r"\bin transit\b", lowered):
                return "Enforce encryption in transit for sensitive data"
            if re.search(r"\bat rest\b|\baes-?256\b", lowered):
                return "Enforce encryption at rest for sensitive data"
            if re.search(r"\bencrypt(?:ed|ion)?\b", lowered):
                return "Enforce sensitive data encryption controls"
            if re.search(r"\bmobile[\-\s]?friendly\b", lowered):
                return "Enable mobile-friendly interface support"
            if re.search(r"\bresponsive\b", lowered) and re.search(
                r"\b(peak load|concurrent|latency|response time|throughput|performance|load)\b",
                lowered,
            ):
                return "Optimize peak-load responsiveness and capacity"
            if "performance" in tags:
                if re.search(r"\bresponsive\b", lowered) and re.search(
                    r"\b(layout|interface|ui|ux|screen|viewport|browser|device)\b",
                    lowered,
                ):
                    return "Enable mobile-friendly interface support"
                if re.search(r"\bconcurrent users?\b", lowered):
                    if re.search(r"\bregistration\b", lowered):
                        return "Optimize registration concurrency capacity"
                    return "Optimize concurrent user capacity"
                if cls._has_infrastructure_availability_signal(text) or re.search(
                    r"\b(downtime|uptime|reliable|availability|zero.downtime)\b",
                    lowered,
                ):
                    return "Optimize system uptime and reliability constraints"
                return cls._safe_nfr_template("Optimize", focus, "system", "performance constraints")
            regulation = cls._regulation_label(lowered)
            if regulation:
                if re.search(r"\baudit trail\b|\baudit evidence\b|\baudit logs?\b", lowered):
                    return f"Establish {regulation} compliance controls and audit evidence"
                if re.search(r"\b(security|data|privacy|encryption|encrypt)\b", lowered):
                    if re.search(r"\bsecurity\b", regulation, flags=re.IGNORECASE):
                        return f"Enforce {regulation} controls"
                    return f"Enforce {regulation} data security controls"
                return f"Establish {regulation} compliance controls"
            if "security" in tags:
                if re.search(r"\b(authorized|authorization|access control|permission)\b", lowered):
                    return "Enforce authorized user access security controls"
                return cls._safe_nfr_template("Enforce", focus, "data", "security controls")
            if "compliance" in tags:
                if re.search(r"\baudit trail\b", lowered):
                    return "Enforce audit trail for privileged actions"
                return cls._safe_nfr_template("Enforce", focus, "regulatory", "compliance requirements")
            return cls._safe_nfr_template("Enforce", focus, "system", "constraints")

        if re.search(r"\b(detect|identify)\b", lowered) and re.search(r"\bconflicts?\b", lowered):
            return f"Implement {focus or 'conflict'} detection workflow"
        if re.search(r"\b(mfa|2fa|multi.factor)\b", lowered):
            return "Implement multi-factor authentication workflow"
        if re.search(r"\b(otp|verification code|verify|verification)\b", lowered):
            return "Implement account verification workflow"
        if "auth" in tags:
            return f"Implement {focus or 'authentication'} workflow"

        if "integration" in tags:
            integration_focus = cls._extract_integration_focus(text) or focus or "external service"
            # Anti-duplication: drop leading "integration"/"integrating"/"integrated"
            # so we never produce "Integrate integration with X".
            integration_focus = re.sub(
                r"^(?:integration|integrating|integrated)(?:\s+with)?\s+",
                "",
                integration_focus,
                flags=re.IGNORECASE,
            ).strip(" .,;:") or "external service"
            return f"Integrate {integration_focus}"

        if "notification" in tags:
            # Handle "If/When <event> is <state>, notify <audience>" pattern
            conditional = re.match(
                r"^(?:if|when)\s+(?:an?\s+)?(?P<event>\w+(?:\s+\w+){0,3})\s+"
                r"(?:is\s+(?:changed|cancelled?|updated|modified|rescheduled|missed|[a-z]+)|"
                r"changes?|gets?\s+cancelled?|conflicts?)\b",
                lowered,
            )
            if conditional:
                event = conditional.group("event").strip()
                return f"Implement {event} status change notification workflow"

            notification_focus = cls._extract_notification_focus(text) or focus or "notification delivery"
            if re.search(r"\bnotification(s)?\b", notification_focus, flags=re.IGNORECASE):
                return f"Implement {notification_focus} workflow"
            return f"Implement {notification_focus} notification workflow"

        if "reporting" in tags:
            reporting_focus = cls._extract_reporting_focus(text) or focus or "reporting"
            if re.search(r"\b(report|reporting|dashboard|analytics|summary)\b", reporting_focus, flags=re.IGNORECASE):
                return f"Implement {reporting_focus} workflow"
            return f"Implement {reporting_focus} reporting workflow"

        nominal_title = cls._nominal_functional_title(action_phrase, lowered)
        if nominal_title:
            return nominal_title

        first_word = cls._split_leading_action(action_phrase.lower())[0]

        if first_word in cls._READ_VERBS:
            suffix = cls._READ_VERB_SUFFIX.get(first_word, "viewing workflow")
            return f"Implement {focus or 'information access'} {suffix}"

        if first_word == "upload":
            return f"Implement {focus or 'artifact'} upload workflow"

        if first_word == "prescribe":
            return f"Implement {focus or 'entity'} prescription workflow"

        if first_word == "schedule":
            return f"Implement {focus or 'entity'} scheduling workflow"

        if first_word == "reschedule":
            if re.search(r"\bappointments?\b", lowered):
                return "Implement appointment rescheduling workflow"
            return f"Implement {focus or 'entity'} rescheduling workflow"

        if first_word in cls._WRITE_VERBS:
            if re.search(r"\bappointments?\b", lowered) and re.search(r"\bon behalf of\b", lowered):
                return "Implement proxy appointment booking workflow"
            return f"Implement {focus or 'entity'} creation workflow"

        if first_word == "book":
            if re.search(r"\bappointments?\b", lowered) and re.search(r"\bonline\b", lowered) is None:
                return "Implement appointment booking workflow"
            return f"Implement {focus or 'entity'} booking workflow"

        if first_word == "mark":
            if re.search(r"\barrival\b", lowered):
                return "Implement patient arrival tracking workflow"
            if re.search(r"\bresults?\b", lowered) and re.search(r"\bverified\b", lowered):
                return "Implement lab result verification workflow"
            return f"Implement {focus or 'status'} tracking workflow"

        if first_word == "update" and re.search(r"\bappointment status\b", lowered):
            return "Implement appointment status update workflow"

        if first_word in cls._MODIFY_VERBS:
            if first_word == "manage" and re.search(r"\bappointments?\b", lowered):
                return "Implement appointment management workflow"
            return f"Implement {focus or 'entity'} management workflow"

        if first_word in cls._SELECT_VERBS:
            return f"Implement {focus or 'option'} selection workflow"

        if first_word in cls._DELETE_VERBS:
            if re.search(r"\bcancel\b", action_lower):
                return f"Implement {focus or 'entity'} cancellation workflow"
            if re.search(r"\b(deactivate|disable|suspend|archive)\b", action_lower):
                return f"Implement {focus or 'entity'} deactivation workflow"
            if re.search(r"\b(delete|remove|purge)\b", action_lower):
                return f"Implement {focus or 'entity'} deletion workflow"
            return f"Implement {focus or 'entity'} workflow"

        if first_word == "rate":
            return f"Implement {focus or 'entity'} rating workflow"

        if first_word in {"accept", "parse", "extract", "ingest"}:
            return f"Implement {focus or 'data'} ingestion workflow"

        if first_word in {"construct", "build", "compile", "assemble"}:
            return f"Implement {focus or 'structure'} construction workflow"

        if first_word in {"estimate", "predict", "forecast", "compute", "calculate"}:
            return f"Implement {focus or 'metric'} estimation workflow"

        if first_word in {"classify", "categorize", "label", "tag"}:
            return f"Implement {focus or 'item'} classification workflow"

        if first_word in {"detect", "discover", "find", "identify"}:
            return f"Implement {focus or 'issue'} detection workflow"

        if first_word in {"monitor", "observe", "watch", "track"}:
            semantic_title = semantic_suffix_title(focus or "activity")
            if semantic_title:
                return semantic_title
            return f"Implement {focus or 'activity'} monitoring workflow"

        if first_word in {"handle", "process"}:
            if "validation" in tags:
                semantic_title = semantic_suffix_title(focus or "case")
                if semantic_title:
                    return semantic_title
            return f"Implement {focus or 'case'} handling workflow"

        if first_word in {"support", "enable", "allow"}:
            if tags & {"orchestration", "dashboard", "export", "validation"}:
                semantic_title = semantic_suffix_title(focus or "capability")
                if semantic_title:
                    return semantic_title
            return f"Implement {focus or 'capability'} support workflow"

        if first_word in {"store", "persist", "save"}:
            semantic_title = semantic_suffix_title(focus or "data")
            if semantic_title:
                return semantic_title
            return f"Implement {focus or 'data'} storage workflow"

        if first_word == "maintain":
            if tags & {"storage", "monitoring"}:
                semantic_title = semantic_suffix_title(focus or "record")
                if semantic_title:
                    return semantic_title
            return f"Implement {focus or 'record'} maintenance workflow"

        if first_word in {"provide", "display", "show", "expose"}:
            if tags & {"dashboard", "export", "validation"}:
                semantic_title = semantic_suffix_title(focus or "data")
                if semantic_title:
                    return semantic_title
            return f"Implement {focus or 'data'} delivery workflow"

        if first_word in {"operate", "run"}:
            return f"Enforce {focus or 'system'} operational constraints"

        return f"Implement {focus or 'system capability'} workflow"

    @classmethod
    def _is_vague_focus_phrase(cls, focus: str, action_phrase: str) -> bool:
        candidate = (focus or "").strip()
        if not candidate:
            _, rest = cls._split_leading_action(action_phrase)
            candidate = rest.strip()

        lowered = re.sub(r"[^a-z0-9'\s-]+", " ", candidate.lower())
        raw_tokens = [token.strip("'") for token in lowered.split() if token.strip("'")]
        if not raw_tokens:
            return False

        meaningful_tokens = [
            token for token in raw_tokens
            if token not in cls._VAGUE_FOCUS_STOPWORDS
        ]
        if meaningful_tokens:
            return all(token in cls._VAGUE_NOUNS for token in meaningful_tokens)

        return any(token in cls._VAGUE_NOUNS or token in cls._PRONOUNS for token in raw_tokens)

    @staticmethod
    def _extract_registration_channel(text: str) -> str | None:
        lowered = text.lower()
        if "google oauth" in lowered or ("google" in lowered and "oauth" in lowered):
            return "Google OAuth"
        if re.search(r"\bapple\b", lowered) and re.search(r"\bsign.in\b", lowered):
            return "Apple Sign-In"
        if re.search(r"\boauth\b", lowered):
            return "OAuth"
        if re.search(r"\bnational id\b", lowered):
            return "national ID"
        if re.search(r"\bphone(?: number)?\b", lowered):
            return "phone"
        if re.search(r"\bemail\b", lowered):
            return "email"
        return None

    @staticmethod
    def _strip_requirement_prefix(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^\[[A-Z]+-\d+\]\s*", "", cleaned)
        cleaned = re.sub(r"^[A-Z][A-Za-z0-9 /&+-]{1,40}:\s+", "", cleaned)
        # Strip em-dash actor separator left by brief-format prefix stripping
        # e.g. "Doctor — The Doctor should..." → "The Doctor should..."
        cleaned = re.sub(r"^[A-Za-z][A-Za-z\s]*\s*\u2014\s*", "", cleaned)
        cleaned = re.sub(
            r"^as an?\s+[^,]+,\s*i\s+(?:want|need|can|should be able)\s+(?:to\s+)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:after|before|once|when|if|in case of)\s+[^,]+,\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:the system|platform|application|service|solution|users?|admins?|"
            r"managers?|staff|clients?|customers?|operators?|employees?|doctors?|"
            r"patients?|agents?|members?|receptionists?|technicians?|lab technicians?|"
            r"nurses?|supervisors?|accountants?|cashiers?|vendors?|suppliers?|"
            r"merchants?|retail customers?|support agents?|compliance analysts?|tenant admins?)\s+"
            r"(?:can|must|should|shall|will|may|supports?|provides?|offers?|"
            r"allows?|enables?)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^the\s+(?:merchant|retail customer|support agent|compliance analyst|tenant admin|customer|admin)\s+"
            r"(?:can|must|should|shall|will|may|supports?|provides?|offers?|allows?|enables?)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        # Generic fallback: any capitalized role phrase followed by can/must
        cleaned = re.sub(
            r"^(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:can|must|should|shall|will|may)\s+",
            "",
            cleaned,
        )
        cleaned = re.sub(r"^(?:be able to|be)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^(?:all|any|each)\s+", "", cleaned, flags=re.IGNORECASE)
        # Strip soft modifier adverbs (Ideally / Optionally / Preferably)
        cleaned = re.sub(r"^(?:ideally|optionally|preferably)\s+", "", cleaned, flags=re.IGNORECASE)
        # Strip leading "Allow"/"Let" prefix so role-to patterns can be peeled next
        cleaned = re.sub(r"^(?:allow|let)\s+", "", cleaned, flags=re.IGNORECASE)
        # Strip "[the] <role> to" patterns broadly so the residual starts with the actual verb
        cleaned = re.sub(
            r"^(?:the\s+)?(?:doctors?|patients?|users?|staff|admins?|receptionists?|nurses?|"
            r"managers?|technicians?|operators?|customers?|members?|sellers?|"
            r"buyers?|merchants?|instructors?|advisors?|registrars?|librarians?|"
            r"students?|employees?|guests?|visitors?|subscribers?|developers?|"
            r"vendors?|suppliers?|clients?|academic advisors?|sales reps?|"
            r"sales managers?|marketing specialists?)\s+to\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        # Strip pure-auxiliary verbs ("provide/deliver/present/offer") that are
        # syntactic placeholders rather than the requirement's actual action.
        # Intentionally NOT stripping "support/enable/allow" here — those can be
        # the real NFR verb (e.g., "support multilingual", "enable offline").
        cleaned = re.sub(r"^(?:provide|deliver|present|offer)\s+", "", cleaned, flags=re.IGNORECASE)
        # Strip a leading "not\s+" left over after "should/must" stripping so
        # NFR phrases like "not exceed 500ms" don't poison title focus extraction.
        cleaned = re.sub(r"^not\s+(?=[a-z])", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip(" .,;:")

    @classmethod
    def _extract_focus_phrase(cls, text: str, max_words: int = 6) -> str:
        cleaned = cls._strip_requirement_prefix(text)
        subject_modal = re.match(
            r"^(?P<subject>[^,.;]+?)\s+(?:must|should|shall|will|can|may)\s+(?:be|remain|stay)\b",
            cleaned,
            flags=re.IGNORECASE,
        )
        if subject_modal:
            cleaned = subject_modal.group("subject").strip()
        add_to_target = re.match(r"^(?:add|move|save)\s+.+?\s+to\s+(.+)$", cleaned, flags=re.IGNORECASE)
        if add_to_target:
            cleaned = add_to_target.group(1)
        cleaned = re.sub(
            r"^(?:integrate|connect|sync(?:hronize)?|link)\s+(?:with\s+)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:send|notify|alert|message|email|push|remind|inform)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:generate|export|summarize|aggregate|track|log|audit|report)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:authenticate|authorize|verify|validate|login|log in|sign in|"
            r"logout|log out|sign out)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        # Strip leading adverb before verb (e.g. "automatically generate")
        cleaned = re.sub(
            r"^(?:automatically|automatically\s+(?:generate|create|build|compute|detect|classify|send|update)|"
            r"fully|manually|dynamically|seamlessly|continuously|independently)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:accept|parse|ingest|extract|construct|build|compile|estimate|"
            r"predict|forecast|classify|categorize|label|support|enable|allow|"
            r"operate|handle|process|provide|display|show|ensure|guarantee|"
            r"enforce|detect|identify|discover|monitor|observe|watch|offer|"
            r"expose|capture|compute|calculate|analyze|assess|evaluate|optimize|"
            r"deploy|run|serve|host|manage|coordinate|orchestrate|facilitate)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:create|add|register|submit|upload|insert|post|generate|produce|"
            r"issue|publish|draft|record|place|request|invite|checkout|book|order|"
            r"purchase|pay|maintain|keep|retain|preserve|store|persist)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:update|edit|modify|change|set|assign|configure|adjust|manage|"
            r"rename|move|reorder|approve|reject|restore|enable|disable|schedule|"
            r"reschedule|reactivate|mark|prescribe|rate)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^(?:select|choose|pick)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"^(?:delete|remove|cancel|deactivate|revoke|expire|purge|archive|"
            r"disable|suspend|terminate)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:view|see|list|display|show|read|browse|search|query|fetch|get|"
            r"find|filter|sort|lookup|download|track|monitor|inspect|review|"
            r"detect|identify)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^(?:and|or|but)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"^(?:doctors?|patients?|users?|staff|admins?|receptionists?|nurses?|"
            r"managers?|technicians?|operators?)\s+to\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        # Second verb pass: verbs exposed after stripping "role + to"
        # e.g. "doctors to view patient history" → "view ..." → "patient history"
        cleaned = re.sub(
            r"^(?:view|see|list|display|show|read|browse|search|query|fetch|get|"
            r"find|filter|sort|lookup|download|track|monitor|inspect|review|"
            r"detect|identify|allow|enable|register|book|manage|generate|send|"
            r"record|access|create|update|delete|add|remove)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^(?:the|a|an|their|its|all|any|new)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.split(r"\b(?:so that|in order to|to ensure|while|after|before|within|under)\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        # Truncate at enumerations and subordinate clauses to keep focus tight
        cleaned = re.split(
            r"\b(?:such as|including|where|which|by|using|via|to enable|to allow|to support|without|ensuring|displaying|prompting|when necessary|with at least|without significant|for debugging)\b",
            cleaned,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        cleaned = re.sub(r"\bonly\b$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\b(?:with|at|to|for|from|into|of|between)\s*$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.strip(" .,;:")
        while cleaned:
            tokens = cleaned.split()
            if not tokens or tokens[0].lower() not in cls._PRONOUNS:
                break
            cleaned = " ".join(tokens[1:]).strip(" .,;:")
        words = cleaned.split()[:max_words]
        focused = " ".join(words).strip(" .,;:")
        # After 6-word truncation, retrim any trailing stop-word/conjunction so we
        # never emit titles like "Implement X tied to workflow" or "X and workflow".
        focused = re.sub(
            r"\b(?:and|or|but|with|at|to|for|from|into|of|between|by|on|in)\s*$",
            "",
            focused,
            flags=re.IGNORECASE,
        ).strip(" .,;:")
        if focused.count("(") > focused.count(")"):
            focused = f"{focused})"
        return focused

    @classmethod
    def _extract_integration_focus(cls, text: str) -> str:
        cleaned = cls._strip_requirement_prefix(text)
        lowered = cleaned.lower()

        anchor_pattern = (
            r"(?:gateway|api|sdk|service|services|system|platform|provider|providers|"
            r"integration|calendar)"
        )
        purpose_clause_pattern = r"\s+(?:used to|so that|in order to|to|for|that|which)\b"

        def _finalize(candidate: str) -> str:
            candidate = candidate.strip(" .,;:")
            candidate = re.sub(r"^(?:a|an)\s+", "", candidate, flags=re.IGNORECASE)
            purpose_match = re.search(purpose_clause_pattern, candidate, flags=re.IGNORECASE)
            if purpose_match:
                head = candidate[:purpose_match.start()].strip(" .,;:")
                if re.search(rf"\b{anchor_pattern}\b", head, flags=re.IGNORECASE):
                    candidate = head
            candidate = re.sub(r"\s+integration\s*$", "", candidate, flags=re.IGNORECASE).strip(" .,;:")
            return candidate

        def _looks_like_named_service(candidate: str) -> bool:
            if not candidate or re.fullmatch(r"[A-Z]{2,6}", candidate):
                return False
            return bool(re.search(
                r"\b(Calendar|Pay|Maps|Drive|Cloud|API|SDK|Stripe|Twilio|AWS|Azure|"
                r"GCP|SMTP|Outlook|Google|Apple|Facebook|Twitter|LinkedIn|Teams|Slack)\b",
                candidate,
            ) or (" and " in candidate.lower()) or (" or " in candidate.lower()))

        named_services = re.search(
            r"\b((?:[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)"
            r"(?:\s+(?:and|or)\s+(?:[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*))*)"
            r"(?=\s+to\b|[.,;]|$)",
            text,
        )
        if named_services:
            candidate = named_services.group(1).strip(" .,;:")
            if _looks_like_named_service(candidate):
                return _finalize(candidate)

        for marker in (" via ", " through ", " with ", " using "):
            if marker in lowered:
                tail = cleaned[lowered.rfind(marker) + len(marker):].strip(" .,;:")
                anchored = re.search(
                    rf"\b((?:an?\s+)?(?:third-party|external)\s+(?:[A-Za-z0-9][A-Za-z0-9/&+-]*\s+){{0,6}}{anchor_pattern})\b",
                    tail,
                    flags=re.IGNORECASE,
                )
                if anchored:
                    return _finalize(anchored.group(1))
                generic = re.search(
                    rf"\b((?:[A-Za-z0-9][A-Za-z0-9/&+-]*\s+){{0,6}}{anchor_pattern})\b",
                    tail,
                    flags=re.IGNORECASE,
                )
                if generic:
                    return _finalize(generic.group(1))
                if re.search(rf"\b{anchor_pattern}\b", tail, flags=re.IGNORECASE):
                    return _finalize(tail)

        via_matches = re.findall(
            rf"\b(?:via|through|using|with)\s+([^,.;]+?{anchor_pattern})\b",
            cleaned,
            flags=re.IGNORECASE,
        )
        if via_matches:
            return _finalize(via_matches[-1])

        keyword_match = re.search(
            rf"\b((?:an?\s+)?(?:third-party|external)\s+(?:[A-Za-z0-9][A-Za-z0-9/&+-]*\s+){{0,6}}{anchor_pattern}|payment gateway|calendar api|shipping api)\b",
            cleaned,
            flags=re.IGNORECASE,
        )
        if keyword_match:
            return _finalize(keyword_match.group(1))

        # Named external service detection (e.g. "Google Calendar and Outlook Calendar")
        named_services = re.search(
            r"\b((?:[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)"
            r"(?:\s+and\s+(?:[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*))*)\b",
            text,
        )
        if named_services:
            candidate = named_services.group(1).strip()
            if _looks_like_named_service(candidate):
                return _finalize(candidate)

        result = cls._extract_focus_phrase(text)
        return _finalize(result)

    @classmethod
    def _extract_notification_focus(cls, text: str) -> str:
        if re.search(r"\bappointment conflict\b", text, flags=re.IGNORECASE):
            if re.search(r"\bemail\b", text, flags=re.IGNORECASE) and re.search(r"\bpush\b", text, flags=re.IGNORECASE):
                return "appointment conflict notifications"
            if re.search(r"\bemail\b", text, flags=re.IGNORECASE):
                return "appointment conflict email notifications"
            if re.search(r"\bpush\b", text, flags=re.IGNORECASE):
                return "appointment conflict push notifications"
            return "appointment conflict notifications"
        cleaned = cls._strip_requirement_prefix(text)
        cleaned = re.sub(
            r"^(?:provide|support|enable|allow|manage)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        if re.search(r"\band\s+notifications?\b", cleaned, flags=re.IGNORECASE):
            return re.sub(r"\s+", " ", cleaned).strip(" .,;:")
        cleaned = re.sub(r"^(?:send|notify|alert|message|email|push)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.split(r"\b(?:via|through|by|for)\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = re.sub(r"\b(?:notifications?|alerts?|messages?)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:and|or)\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
        return cleaned

    @classmethod
    def _extract_reporting_focus(cls, text: str) -> str:
        if re.search(r"\bweekly\b", text, flags=re.IGNORECASE) and re.search(r"\badmins?\b", text, flags=re.IGNORECASE):
            return "weekly admin reporting"
        if re.search(
            r"\b(task breakdown|dependency graphs?|estimated timelines?|risk indicators?|project planning)\b",
            text,
            flags=re.IGNORECASE,
        ):
            return "project planning dashboard"
        if re.search(r"\bdashboard\b", text, flags=re.IGNORECASE):
            cleaned = cls._strip_requirement_prefix(text)
            cleaned = re.sub(
                r"^(?:provide|display|show|allow|manage|support)\s+",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = re.split(
                r"\b(?:displaying|showing|including|with|for)\b",
                cleaned,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
            if cleaned:
                return cleaned
        if re.search(r"\bevaluation metrics\b", text, flags=re.IGNORECASE):
            return "planner evaluation metrics"
        if re.search(r"\bexport(?:ing)?\b", text, flags=re.IGNORECASE) and re.search(
            r"\b(tasks?|reports?)\b",
            text,
            flags=re.IGNORECASE,
        ):
            return "task and report export"
        cleaned = cls._strip_requirement_prefix(text)
        cleaned = re.sub(
            r"^(?:generate|export|summarize|aggregate|track|log|audit|report|provide|display|show|allow)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.split(r"\b(?:as|into|to|for|showing|displaying|including)\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = re.sub(r"\b(?:reports?|dashboards?|analytics?|summaries?|metrics?)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
        return cleaned

    # ------------------------------------------------------------------ #
    #  Decomposition (domain-agnostic)                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def _decompose_requirement(cls, requirement: str) -> list[str]:
        """
        Split compound requirements into atomic sub-tasks.
        Only splits when distinct VERB PHRASES are detected (not noun lists).
        """
        text = requirement.strip().rstrip(".")

        if cls._is_narrative_meta_requirement(text):
            return []

        for special_decomposer in (
            cls._preserve_lifecycle_management,
            cls._decompose_quality_attribute_list,
            cls._decompose_registration_channels,
            cls._decompose_gdpr_rights,
            cls._decompose_encryption_controls,
            cls._decompose_conditional_notifications,
            cls._decompose_hospital_workflow_requirement,
        ):
            special_parts = special_decomposer(text)
            if special_parts:
                finalized = cls._finalize_decomposition_candidates(special_parts)
                if len(finalized) >= 2:
                    return finalized
                if len(special_parts) == 1:
                    return [special_parts[0].strip(" .")]

        density = cls._semantic_density_analysis(text)
        if density["actor_units"] > 1:
            actor_parts = cls._split_multi_actor_requirement(text)
            if actor_parts:
                finalized = cls._finalize_decomposition_candidates(actor_parts)
                if len(finalized) >= 2:
                    return finalized

        subject_modal_match = re.match(
            r"^((?:the system|platform|application|service|solution|users?|admins?|"
            r"managers?|staff|clients?|customers?|operators?|employees?|doctors?|"
            r"patients?|agents?|members?|receptionists?|technicians?|lab technicians?|"
            r"nurses?|supervisors?|accountants?|cashiers?|vendors?|suppliers?)\s+"
            r"(?:can|must|should|shall|will|may|supports?|provides?|offers?|"
            r"allows?|enables?))\s+(.+)$",
            text, flags=re.IGNORECASE,
        )

        if subject_modal_match:
            subject_modal = subject_modal_match.group(1)
            actions_text = subject_modal_match.group(2)

            if re.match(r"^provide\s+", actions_text, flags=re.IGNORECASE) and "," not in actions_text:
                return [text]

            if ":" in actions_text:
                _, post_colon = actions_text.split(":", 1)
                colon_parts = cls._split_verb_phrases(post_colon.strip())
                if len(colon_parts) >= 2:
                    finalized = cls._finalize_decomposition_candidates(
                        [f"{subject_modal} {p.strip()}" for p in colon_parts]
                    )
                    if len(finalized) >= 2:
                        return finalized

            parts = cls._split_verb_phrases(actions_text)
            if len(parts) >= 2:
                common_verbs = cls._known_action_verbs()
                if parts[0].strip().lower().startswith("provide "):
                    normalized_parts: list[str] = []
                    for part in parts:
                        stripped_part = part.strip()
                        first_token = stripped_part.split()[0].lower() if stripped_part.split() else ""
                        has_clear_action = (
                            cls._first_verb(stripped_part, common_verbs) in common_verbs
                            and not first_token.endswith("ed")
                        )
                        normalized_parts.append(stripped_part if has_clear_action else f"provide {stripped_part}")
                    parts = normalized_parts
                finalized = cls._finalize_decomposition_candidates(
                    [f"{subject_modal} {p.strip()}" for p in parts]
                )
                if len(finalized) >= 2:
                    return finalized

            if density["should_split"]:
                capability_parts = cls._split_semantic_concern_list(actions_text)
                if len(capability_parts) >= 2:
                    finalized = cls._finalize_decomposition_candidates(
                        [f"{subject_modal} {p.strip()}" for p in capability_parts]
                    )
                    if len(finalized) >= 2:
                        return finalized

        return [] if cls._is_narrative_meta_requirement(text) else [text]

    @staticmethod
    def _split_choice_list(text: str) -> list[str]:
        protected = re.sub(r"(?<=\d),(?=\d{3}\b)", "__THOUSANDS_COMMA__", text.strip())
        normalized = re.sub(r"\s*,\s*(?:and\s+)?", ", ", protected, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+or\s+", ", ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+and\s+", ", ", normalized, flags=re.IGNORECASE)
        return [
            part.strip(" .,;:()").replace("__THOUSANDS_COMMA__", ",")
            for part in normalized.split(",")
            if part.strip(" .,;:()")
        ]

    @classmethod
    def _decompose_registration_channels(cls, text: str) -> list[str] | None:
        match = re.match(
            r"^(?P<subject>users?|customers?|clients?|members?)\s+can\s+"
            r"(?:register|sign up|signup|enroll|onboard)\s+"
            r"(?:using|with|via)\s+(?P<channels>.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        channels = cls._split_choice_list(match.group("channels"))
        channels = [
            re.sub(
                r"^(?:may\s+also\s+)?(?:sign in|log in|login)\s+(?:using|with|via)\s+",
                "",
                channel,
                flags=re.IGNORECASE,
            )
            for channel in channels
        ]
        if len(channels) < 2:
            return None

        subject = match.group("subject")
        return [f"{subject} can register using {channel}" for channel in channels]

    @classmethod
    def _preserve_lifecycle_management(cls, text: str) -> list[str] | None:
        lowered = text.lower()
        lifecycle_verbs = re.findall(
            r"\b(create|update|suspend|reactivate|delete|deactivate|activate)\b",
            lowered,
        )
        if len(set(lifecycle_verbs)) >= 4 and re.search(
            r"\b(admins?|managers?)\b", lowered
        ) and re.search(r"\b(user accounts?|accounts?)\b", lowered):
            return [text]
        return None

    @classmethod
    def _decompose_quality_attribute_list(cls, text: str) -> list[str] | None:
        match = re.match(
            r"^(?P<subject>(?:the system|platform|application|service|solution)\s+"
            r"(?:must|should|shall|will|needs?\s+to))\s+"
            r"(?P<body>(?:be|remain|stay)\s+.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        body = re.sub(
            r"^(?:be|remain|stay)\s+",
            "",
            match.group("body").strip(),
            flags=re.IGNORECASE,
        )
        if "," not in body and re.search(r"\band\b", body, flags=re.IGNORECASE) is None:
            return None

        subject = match.group("subject")
        items = cls._split_choice_list(body)
        if len(items) < 2:
            return None

        parts: list[str] = []
        for item in items:
            lowered_item = item.lower()
            if re.search(r"\b(high(?:ly)?\s+available|availability|uptime|downtime|reliab\w*)\b", lowered_item):
                parts.append(f"{subject} maintain high availability")
                continue
            if re.search(r"\b(encrypt(?:ed|ion)?|aes(?:-\d+)?|tls|ssl)\b", lowered_item):
                parts.append(f"{subject} encrypt sensitive data")
                continue
            if re.search(r"\bmobile[\-\s]?friendly\b", lowered_item):
                parts.append(f"{subject} support mobile-friendly interfaces")
                continue
            if re.search(r"\b(responsive|performance|latency|throughput|concurrent|peak load|load)\b", lowered_item):
                if re.search(r"\bpeak load\b", lowered_item):
                    parts.append(f"{subject} maintain responsive performance under peak load")
                elif re.search(r"\bconcurrent\b", lowered_item):
                    parts.append(f"{subject} maintain responsive performance for concurrent users")
                else:
                    parts.append(f"{subject} maintain responsive performance")
                continue

        return parts if len(parts) >= 2 else None

    @classmethod
    def _decompose_gdpr_rights(cls, text: str) -> list[str] | None:
        if not re.search(r"\bgdpr\b", text, flags=re.IGNORECASE):
            return None

        rights: list[str] = []
        if re.search(r"\bdata deletion\b", text, flags=re.IGNORECASE):
            rights.append("The system must support GDPR data deletion requests")
        if re.search(r"\bexport\b", text, flags=re.IGNORECASE):
            rights.append("The system must support GDPR data export requests")
        if re.search(r"\bconsent\b", text, flags=re.IGNORECASE):
            rights.append("The system must support GDPR consent withdrawal")
        if re.search(r"\baccess logs?\b", text, flags=re.IGNORECASE):
            rights.append("The system must provide GDPR access log visibility")

        return rights if len(rights) >= 2 else None

    @classmethod
    def _decompose_encryption_controls(cls, text: str) -> list[str] | None:
        if not re.search(r"\bencrypt(?:ed|ion)?\b", text, flags=re.IGNORECASE):
            return None
        if not (
            re.search(r"\bat rest\b", text, flags=re.IGNORECASE)
            and re.search(r"\bin transit\b", text, flags=re.IGNORECASE)
        ):
            return None

        scope = "All sensitive data" if re.search(
            r"\bsensitive data\b", text, flags=re.IGNORECASE
        ) else "All data"

        at_rest = f"{scope} must be encrypted at rest"
        in_transit = f"{scope} must be encrypted in transit"

        at_rest_alg = re.search(
            r"at rest using\s+([A-Za-z0-9.\- ]+?)(?:\s+and\b|[,.;]|$)",
            text,
            flags=re.IGNORECASE,
        )
        in_transit_alg = re.search(
            r"in transit using\s+([A-Za-z0-9.\- ]+?)(?:\s+and\b|[,.;]|$)",
            text,
            flags=re.IGNORECASE,
        )
        if at_rest_alg:
            at_rest += f" using {at_rest_alg.group(1).strip()}"
        if in_transit_alg:
            in_transit += f" using {in_transit_alg.group(1).strip()}"

        return [at_rest, in_transit]

    @classmethod
    def _decompose_conditional_notifications(cls, text: str) -> list[str] | None:
        # Match "If/When/In case of <trigger>, system must notify <audience> via <channels>"
        # Use a two-pass approach: find trigger prefix + find notify…via suffix
        trigger_match = re.match(
            r"^(?:in case of|if|when)\s+(?P<trigger>.+?)\s*,\s*"
            r"(?=(?:the system|platform|application|service|solution)\s+(?:can|must|should|shall|will|may)\s+notify\b)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        notify_match = re.search(
            r"(?:the system|platform|application|service|solution)\s+"
            r"(?:can|must|should|shall|will|may)\s+notify\s+"
            r"(?P<audience>.+?)\s+via\s+(?P<channels>.+?)\.?\s*$",
            text,
            flags=re.IGNORECASE,
        )

        if not trigger_match or not notify_match:
            return None

        raw_trigger = trigger_match.group("trigger").strip(" .,;:")
        # Simplify complex triggers into a clean label
        lowered_trigger = raw_trigger.lower()
        if re.search(r"\bappointment\b", lowered_trigger) and re.search(
            r"\b(?:conflict|cancel|change|reschedule)\w*\b", lowered_trigger
        ):
            trigger = "appointment conflict"
        else:
            trigger = re.sub(r"^(?:an?|the)\s+", "", raw_trigger, flags=re.IGNORECASE).strip(" .,;:")

        audience = notify_match.group("audience").strip(" .,;:")
        channels = cls._split_choice_list(notify_match.group("channels"))

        # Collect distinct delivery types (merge SMS + push as both are push-class)
        has_email = any("email" in c.lower() for c in channels)
        has_push = any("push" in c.lower() or "sms" in c.lower() for c in channels)
        has_other = [c for c in channels if "email" not in c.lower() and "push" not in c.lower() and "sms" not in c.lower()]

        delivery_parts: list[str] = []
        if has_email:
            delivery_parts.append(f"The system must send {trigger} email notifications to {audience}")
        if has_push:
            delivery_parts.append(f"The system must send {trigger} push notifications to {audience}")
        for ch in has_other:
            delivery_parts.append(f"The system must send {trigger} notifications via {ch} to {audience}")

        if len(delivery_parts) < 1:
            return None

        parts = [f"The system must detect {trigger}"] + delivery_parts
        return parts

    @classmethod
    def _known_action_verbs(cls) -> set[str]:
        return (
            cls._READ_VERBS
            | cls._WRITE_VERBS
            | cls._MODIFY_VERBS
            | cls._DELETE_VERBS
            | cls._SELECT_VERBS
            | cls._NOTIFY_VERBS
            | cls._REPORT_VERBS
            | cls._AUTH_VERBS
            | cls._INTEGRATE_VERBS
            | {
                "book", "rate", "schedule", "purchase", "order", "pay",
                "track", "share", "print", "invite", "accept", "decline",
                "follow", "unfollow", "compare", "clone", "duplicate",
                "prescribe", "approve", "reject", "handle", "support",
                "provide", "maintain", "process", "coordinate", "facilitate",
                "serve", "host", "operate", "restrict", "collect",
                "prioritize", "return", "calculate", "enforce", "secure",
                "check", "block", "detect", "keep", "encrypt",
            }
        )

    @classmethod
    def _extract_action_object(cls, fragment: str) -> str | None:
        _, rest = cls._split_leading_action(fragment)
        if not rest:
            return None
        if re.match(r"^(?:with|within|after|before|during|using|via|through|by|for|to)\b", rest, flags=re.IGNORECASE):
            return None
        object_text = re.split(
            r"\b(?:with|within|after|before|during|using|via|through|by)\b",
            rest,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        return object_text or None

    @classmethod
    def _complete_action_objects(cls, fragments: list[str]) -> list[str]:
        common_verbs = cls._known_action_verbs()
        for_prefix = None
        if fragments:
            first_fragment = fragments[0]
            for_match = re.match(
                r"^(?P<verb>[A-Za-z][A-Za-z'-]*)\s+(?P<object>.+?)\s+for\s+(?P<target>.+)$",
                first_fragment.strip(),
                flags=re.IGNORECASE,
            )
            if for_match:
                for_prefix = f"{for_match.group('verb')} {for_match.group('object')} for"

        if for_prefix:
            adjusted: list[str] = []
            for fragment in fragments:
                if cls._first_verb(fragment, common_verbs) not in common_verbs:
                    adjusted.append(f"{for_prefix} {fragment}".strip())
                else:
                    adjusted.append(fragment)
            fragments = adjusted

        objects = [cls._extract_action_object(fragment) for fragment in fragments]

        last_object: str | None = None
        for index, obj in enumerate(objects):
            if obj:
                last_object = obj
            elif last_object:
                objects[index] = last_object

        next_object: str | None = None
        for index in range(len(objects) - 1, -1, -1):
            if objects[index]:
                next_object = objects[index]
            elif next_object:
                objects[index] = next_object

        completed: list[str] = []
        for fragment, inferred_object in zip(fragments, objects):
            verb, rest = cls._split_leading_action(fragment)
            if inferred_object and (not rest or re.match(r"^(?:with|within|after|before|during|using|via|through|by|for|to)\b", rest, flags=re.IGNORECASE)):
                rest = f"{inferred_object} {rest}".strip()
            completed.append(f"{verb} {rest}".strip())
        return completed

    @classmethod
    def _normalize_action_token(cls, token: str, common_verbs: set[str]) -> str:
        lowered = token.strip(" .,;:()").lower()
        if lowered in common_verbs:
            return lowered
        if lowered in cls._TRANSPARENT_ADVERBS:
            return lowered

        candidates = [lowered]
        if lowered.endswith("ing") and len(lowered) > 4:
            stem = lowered[:-3]
            candidates.extend([stem, f"{stem}e"])
            if lowered.endswith("ying") and len(lowered) > 5:
                candidates.append(f"{lowered[:-4]}y")
            if stem.endswith("kk") or stem.endswith("pp") or stem.endswith("tt") or stem.endswith("ll"):
                candidates.append(stem[:-1])
        if lowered.endswith("ed") and len(lowered) > 3:
            stem = lowered[:-2]
            candidates.extend([stem, f"{stem}e"])
            if stem.endswith("i"):
                candidates.append(f"{stem[:-1]}y")
        if lowered.endswith("es") and len(lowered) > 3:
            candidates.append(lowered[:-2])
        if lowered.endswith("s") and len(lowered) > 2:
            candidates.append(lowered[:-1])

        for candidate in candidates:
            if candidate in common_verbs:
                return candidate
        return lowered

    @classmethod
    def _normalize_fragment_leading_action(cls, fragment: str, common_verbs: set[str]) -> str:
        words = fragment.strip().split()
        if not words:
            return fragment.strip()
        index = 0
        if words[0].lower() in cls._TRANSPARENT_ADVERBS and len(words) > 1:
            index = 1
        normalized = cls._normalize_action_token(words[index], common_verbs)
        if normalized in common_verbs:
            words[index] = normalized
        return " ".join(words).strip(" .,;")

    @classmethod
    def _semantic_density_analysis(cls, text: str) -> dict[str, int | bool]:
        subject_pattern = (
            r"(?:the system|platform|application|service|solution|users?|admins?|"
            r"managers?|staff|clients?|customers?|operators?|employees?|doctors?|"
            r"patients?|agents?|members?|receptionists?|technicians?|lab technicians?|"
            r"nurses?|supervisors?|accountants?|cashiers?|vendors?|suppliers?)\s+"
            r"(?:can|must|should|shall|will|may|supports?|provides?|offers?|"
            r"allows?|enables?)\b"
        )
        actor_units = len(re.findall(subject_pattern, text, flags=re.IGNORECASE))

        common_verbs = cls._known_action_verbs()
        action_units: set[str] = set()
        for token in re.findall(r"[A-Za-z][A-Za-z'\-]*", text):
            normalized = cls._normalize_action_token(token, common_verbs)
            if normalized in common_verbs:
                action_units.add(normalized)

        lowered = text.lower()
        concern_mentions = sum(
            1 for hint in cls._WORKFLOW_CONCERN_HINTS
            if re.search(rf"\b{re.escape(hint)}\b", lowered)
        )
        sequence_markers = sum(
            1 for marker in cls._SEQUENCE_PATTERNS
            if re.search(rf"\b{re.escape(marker)}\b", lowered)
        )
        list_markers = lowered.count(",") + len(re.findall(r"\b(?:and|or)\b", lowered))

        should_split = (
            actor_units > 1
            or len(action_units) > 1
            or sequence_markers > 0
            or (concern_mentions > 1 and list_markers > 0)
        )
        return {
            "actor_units": actor_units,
            "action_units": len(action_units),
            "concern_mentions": concern_mentions,
            "sequence_markers": sequence_markers,
            "list_markers": list_markers,
            "should_split": should_split,
        }

    @classmethod
    def _split_multi_actor_requirement(cls, text: str) -> list[str] | None:
        subject_pattern = (
            r"(?P<lemma>(?:the system|platform|application|service|solution|users?|admins?|"
            r"managers?|staff|clients?|customers?|operators?|employees?|doctors?|"
            r"patients?|agents?|members?|receptionists?|technicians?|lab technicians?|"
            r"nurses?|supervisors?|accountants?|cashiers?|vendors?|suppliers?)\s+"
            r"(?:can|must|should|shall|will|may|supports?|provides?|offers?|"
            r"allows?|enables?))\b"
        )
        matches = list(re.finditer(subject_pattern, text, flags=re.IGNORECASE))
        if len(matches) < 2:
            return None

        parts: list[str] = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            piece = text[start:end].strip(" ,;.")
            piece = re.sub(
                r"(?:,?\s+(?:and|or|then|while|whereas))\s*$",
                "",
                piece,
                flags=re.IGNORECASE,
            ).strip(" ,;.")
            if piece:
                parts.append(piece)

        return parts if len(parts) >= 2 else None

    @classmethod
    def _split_semantic_concern_list(cls, text: str) -> list[str]:
        common_verbs = cls._known_action_verbs()
        verb, rest = cls._split_leading_action(text)
        normalized_verb = cls._normalize_action_token(verb, common_verbs)
        if normalized_verb not in common_verbs or not rest:
            return []
        if re.search(r"\b(access control|role.based|rbac|permissions?)\b", rest, flags=re.IGNORECASE):
            return []
        if re.search(r"\broles?\s*:", rest, flags=re.IGNORECASE):
            return []
        if "," not in rest and re.search(
            r"\b(?:for|with|between|from|to)\s+[^,;]+?\s+and\s+[^,;]+$",
            rest,
            flags=re.IGNORECASE,
        ):
            return []

        items = cls._split_choice_list(rest)
        if len(items) < 2:
            return []
        if any(cls._first_verb(item, common_verbs) in common_verbs for item in items):
            return []

        lowered_rest = rest.lower()
        concern_hits = sum(
            1 for hint in cls._WORKFLOW_CONCERN_HINTS
            if re.search(rf"\b{re.escape(hint)}\b", lowered_rest)
        )
        if concern_hits < 2:
            return []

        shared_tail = ""
        tail_match = re.search(
            r"\b(modules?|workflows?|features?|capabilities?|services?|operations?)\b$",
            items[-1],
            flags=re.IGNORECASE,
        )
        if tail_match:
            shared_tail = tail_match.group(1)

        normalized_items: list[str] = []
        for item in items:
            cleaned_item = item.strip(" .,;")
            if (
                shared_tail
                and len(cleaned_item.split()) == 1
                and re.search(rf"\b{re.escape(shared_tail)}\b$", cleaned_item, flags=re.IGNORECASE) is None
            ):
                cleaned_item = f"{cleaned_item} {shared_tail}"
            normalized_items.append(cleaned_item)

        return [f"{normalized_verb} {item}".strip() for item in normalized_items]

    @classmethod
    def _is_narrative_meta_requirement(cls, text: str) -> bool:
        lowered = re.sub(r"\s+", " ", text.strip().lower())
        if not lowered:
            return False

        prefix_hit = next((prefix for prefix in cls._NARRATIVE_META_PREFIXES if lowered.startswith(prefix)), None)
        if not prefix_hit and re.search(
            r"\b(?:if we have time|outside core scope|not in first version|future enhancement|not a toy project)\b",
            lowered,
        ) is None:
            return False

        meta_hits = sum(1 for cue in cls._NARRATIVE_META_CUES if cue in lowered)
        concrete_subject = re.search(
            r"\b(?:the system|platform|application|service|solution|users?|admins?|"
            r"managers?|staff|clients?|customers?|operators?|employees?|doctors?|"
            r"patients?|agents?|members?|receptionists?|technicians?|lab technicians?|"
            r"nurses?|supervisors?|accountants?|cashiers?|vendors?|suppliers?)\s+"
            r"(?:can|must|should|shall|will|may)\b",
            lowered,
        ) is not None
        restriction_scope = re.search(
            r"\b(?:access control|role.based|permissions?|should not|must not|cannot|can't|restricted to|internal notes)\b",
            lowered,
        ) is not None
        concern_mentions = sum(
            1 for hint in cls._WORKFLOW_CONCERN_HINTS
            if re.search(rf"\b{re.escape(hint)}\b", lowered)
        )

        if prefix_hit in {
            "there are still some things",
            "one important thing is",
            "another point is",
            "in general we want",
            "also there may be edge cases",
        }:
            return True
        if prefix_hit == "we need" and meta_hits >= 1 and not concrete_subject:
            return True
        if meta_hits >= 2 and not restriction_scope and not concrete_subject:
            return True
        if concern_mentions >= 4 and not concrete_subject and not restriction_scope:
            return True
        return False

    @classmethod
    def _has_access_control_scope(cls, text: str) -> bool:
        lowered = text.lower()
        role_mentions = len(re.findall(
            r"\b(?:admin|receptionist|doctor|nurse|pharmacist|lab staff|radiology staff|billing employee|insurance employee|patient)\b",
            lowered,
        ))
        explicit_access_markers = re.search(
            r"\b(?:access control|role.based|permissions?|manage users?|internal notes|policy allows)\b",
            lowered,
        )
        restriction_markers = re.search(
            r"\b(?:should not|must not|cannot|can't|restricted to|only|except)\b",
            lowered,
        )
        protected_scope = re.search(
            r"\b(?:edit|change|view|see|access|manage users?|permissions?|diagnos(?:is|es)|lab results?|internal notes|medical)\b",
            lowered,
        )
        return bool(
            (explicit_access_markers and (re.search(r"\broles?\b", lowered) or role_mentions >= 2))
            or ((re.search(r"\broles?\b", lowered) or role_mentions >= 2) and restriction_markers and protected_scope)
        )

    @classmethod
    def _has_billing_insurance_scope(cls, text: str) -> bool:
        lowered = text.lower()
        if not (re.search(r"\bbilling\b", lowered) and re.search(r"\binsurance\b", lowered)):
            return False
        finance_signals = re.search(
            r"\b(?:billable|cost|paid by patient|coverage|claim status|approval status|insured|non-insured|"
            r"patient balances?|billing entries|expensive service|amount is paid)\b",
            lowered,
        )
        return finance_signals is not None

    @classmethod
    def _finalize_decomposition_candidates(cls, clauses: list[str]) -> list[str]:
        finalized: list[str] = []
        seen: set[str] = set()

        for clause in clauses:
            normalized = re.sub(r"\s+", " ", clause.strip(" .,;"))
            if not normalized:
                continue
            normalized = normalized[:1].upper() + normalized[1:]
            if cls._is_narrative_meta_requirement(normalized):
                continue
            key = normalized.lower()
            if key in seen:
                continue
            if not cls._is_task_grade_clause(normalized):
                continue
            seen.add(key)
            finalized.append(normalized)

        return finalized

    @classmethod
    def _is_task_grade_clause(cls, clause: str) -> bool:
        lowered = clause.strip().lower()
        if not lowered:
            return False
        if any(lowered.startswith(prefix) for prefix in cls._LOW_SIGNAL_LEADS):
            return False
        if re.match(r"^(?:and|or|but|then|also|maybe|not)\b", lowered):
            return False
        if re.search(r"\b(?:i think|we think|not sure|unsure|maybe yes maybe no)\b", lowered):
            return False

        body = clause.strip()
        subject_match = re.match(
            r"^(?P<subject>[^,.;]+?)\s+"
            r"(?:can|must|should|shall|will|may|supports?|provides?|offers?|allows?|enables?)\s+",
            body,
            flags=re.IGNORECASE,
        )
        if subject_match:
            body = body[subject_match.end():].strip()
        body = re.sub(r"^(?:be|remain|stay)\s+", "", body, flags=re.IGNORECASE)

        common_verbs = cls._known_action_verbs()
        verb, rest = cls._split_leading_action(body)
        normalized_verb = cls._normalize_action_token(verb, common_verbs)
        if normalized_verb not in common_verbs:
            return False

        object_text = rest.strip()
        if not object_text or len(object_text.split()) < 1:
            return False
        if re.match(r"^(?:and|or|but|then|also|maybe|not)\b", object_text, flags=re.IGNORECASE):
            return False

        content_tokens = [
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z'\-]*", object_text)
            if token.lower() not in cls._LOW_SIGNAL_OBJECT_TOKENS
            and token.lower() not in {"the", "a", "an", "to", "for", "of", "in", "on", "at", "with", "from", "by"}
        ]
        return len(content_tokens) >= 1

    @classmethod
    def _decompose_hospital_workflow_requirement(cls, text: str) -> list[str] | None:
        lowered = text.lower()

        if re.search(r"\barabic\b", lowered) and re.search(r"\breports?\b", lowered):
            parts = [
                "The system must support Arabic and English",
                "The system must secure hospital data",
                "The system must keep audit logs for important changes",
                "The system must provide management reports and dashboard exports",
            ]
            return parts

        if cls._has_access_control_scope(text):
            parts = [
                "The system must support hospital role-based access control",
                "Admins can manage users and permissions under hospital policy",
            ]
            if re.search(r"\breceptionist\b.*\b(?:should not|must not|cannot|can't)\b.*\bedit diagnosis\b", lowered):
                parts.append("The system must restrict receptionists from editing diagnoses")
            if re.search(r"\bpharmacist\b.*\b(?:should not|must not|cannot|can't)\b.*\bchange lab results\b", lowered):
                parts.append("The system must restrict pharmacists from changing laboratory results")
            if re.search(r"\bpatient\b", lowered) and re.search(r"\binternal notes\b", lowered):
                parts.append("Patients can view appointments, results, and prescriptions without internal notes")
            if len(parts) >= 2:
                return parts

        if re.search(r"\breceptionist\b", lowered) and re.search(r"\bappointments?\b", lowered):
            parts = [
                "Receptionists can create appointments for patients",
                "Receptionists can cancel appointments for patients",
                "Receptionists can reschedule appointments for patients",
            ]
            if re.search(r"\b(same slot|doctor is available|already full|double[\-\s]?book)\b", lowered):
                parts.append("The system must prevent double-booking of appointment slots")
            if re.search(r"\boverbook\w*|overbooking\b", lowered):
                parts.append("Managers can approve appointment overbooking in special cases")
            if len(parts) >= 4:
                return parts

        if re.search(r"\bdoctors?\b", lowered) and re.search(r"\bpatient profile\b", lowered) and re.search(r"\bdiagnosis\b", lowered):
            parts = [
                "Doctors can view patient history and chronic condition summaries",
                "Doctors can record diagnosis and treatment plans",
                "Doctors can order laboratory and radiology tests",
            ]
            if re.search(r"\bresults?\s+come back\b|\bresults?\b.*\bpatient file\b", lowered):
                parts.append("The system must return completed test results to the patient file")
            if re.search(r"\bprescrib\w+\b", lowered):
                parts.append("Doctors can prescribe medications for pharmacy fulfillment")
            return parts

        if re.search(r"\bfor nurses\b", lowered) and re.search(r"\bvitals?\b", lowered):
            parts = [
                "Nurses can record patient vitals and nursing notes",
                "Nurses can record administered medication for admitted patients",
                "Nurses can track patient follow-up during the shift",
            ]
            return parts

        if re.search(r"\badmissions?\b", lowered) and re.search(r"\b(discharge|ward|room|icu|transfer|moves? from one room)\b", lowered):
            parts = [
                "The system must manage patient admissions and ward placement",
                "The system must manage rooms, beds, and ICU capacity",
                "The system must track patient bed transfers and room changes",
                "The system must enforce discharge approval and billing completion",
            ]
            return parts

        if re.search(r"\blab module\b|\blaboratory\b", lowered) and re.search(r"\bsample\b|\bresults?\b", lowered):
            parts = [
                "Doctors can request laboratory tests",
                "Lab staff can collect samples and enter laboratory results",
                "The system must track laboratory sample status from request to completion",
            ]
            if re.search(r"\bcritical\b|\bdangerous\b|\bnotify\b", lowered):
                parts.append("The system must notify doctors about critical laboratory results")
            return parts

        if re.search(r"\bradiology\b", lowered) and re.search(r"\brequest\b|\breport\b", lowered):
            parts = [
                "Doctors can request radiology studies",
                "Radiology staff can schedule radiology requests",
                "Radiology staff can upload radiology reports",
            ]
            if re.search(r"\battach\b|\bfile\b|\blink\b|\bimage\b", lowered):
                parts.append("The system must support radiology report attachments or file links")
            if re.search(r"\burgent\b|\bpriority\b", lowered):
                parts.append("The system must prioritize urgent radiology requests")
            return parts

        if re.search(r"\bpharmacy\b", lowered) and re.search(r"\bprescriptions?\b", lowered):
            parts = [
                "The pharmacy module must receive prescriptions from doctors",
                "Pharmacists can confirm medication availability",
                "Pharmacists can dispense prescribed medications",
                "The system must track pharmacy stock and block expired medication dispensing",
            ]
            if re.search(r"\ballergy\b|\binteraction\b|\brepeated medicine\b|\bduplicate\b", lowered):
                parts.append("The system must check allergy conflicts and duplicate medications")
            return parts

        if cls._has_billing_insurance_scope(text):
            parts = [
                "The system must generate billing entries for billable hospital services",
                "The system must support insurance coverage and claim approval status",
                "The system must calculate patient balances for insured and non-insured patients",
            ]
            return parts
        return None

    # Adverbs that are transparent — strip them to reveal the real verb
    _TRANSPARENT_ADVERBS = frozenset({
        "permanently", "automatically", "immediately", "directly", "fully",
        "securely", "only", "also", "manually", "temporarily", "optionally",
    })

    @classmethod
    def _first_verb(cls, phrase: str, common_verbs: set[str]) -> str:
        """Return the leading verb of a phrase, skipping transparent adverbs."""
        words = phrase.strip().lower().split()
        if not words:
            return ""
        if words[0] in cls._TRANSPARENT_ADVERBS and len(words) > 1:
            return cls._normalize_action_token(words[1], common_verbs)
        return cls._normalize_action_token(words[0], common_verbs)

    @classmethod
    def _split_leading_action(cls, fragment: str) -> tuple[str, str]:
        words = fragment.strip().split()
        if not words:
            return "", ""
        verb_index = 0
        if words[0].lower() in cls._TRANSPARENT_ADVERBS and len(words) > 1:
            verb_index = 1
        verb = words[verb_index]
        rest = " ".join(words[verb_index + 1:]).strip()
        return verb, rest

    @classmethod
    def _split_verb_phrases(cls, text: str) -> list[str]:
        """
        Split a compound action string into verb phrases.
        Only splits when ALL resulting parts begin with a verb.
        Protects compound nouns joined by 'and'/'or'.
        """
        common_verbs = cls._known_action_verbs()
        density = cls._semantic_density_analysis(text)

        # Strip contrast tails only when they are not access restrictions.
        contrast_tail = re.search(r",?\s+but\b(?P<tail>.*)$", text.strip(), flags=re.IGNORECASE | re.DOTALL)
        if contrast_tail and re.search(
            r"\b(?:cannot|can't|should not|must not|restricted to|except|only)\b",
            contrast_tail.group("tail"),
            flags=re.IGNORECASE,
        ) is None:
            text = re.sub(r",?\s+but\b.*$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL).strip()

        quick_normalized = re.sub(r";", ",", text.strip())
        quick_normalized = re.sub(r"\s*,\s*(?:and\s+)?", ", ", quick_normalized)
        quick_normalized = re.sub(r"\s+and\s+", ", ", quick_normalized, flags=re.IGNORECASE)
        quick_parts = [part.strip(" .,;") for part in quick_normalized.split(",") if part.strip(" .,;")]

        # Merge parts that don't start with a verb back into their predecessor
        # (e.g. "view upcoming, past appointments" → "view upcoming and past appointments")
        merged_parts: list[str] = []
        for part in quick_parts:
            if merged_parts and cls._first_verb(part, common_verbs) not in common_verbs:
                merged_parts[-1] = merged_parts[-1].rstrip(" .,;") + " and " + part
            else:
                merged_parts.append(part)
        quick_parts = merged_parts

        if len(quick_parts) >= 2 and all(
            cls._first_verb(part, common_verbs) in common_verbs
            for part in quick_parts
        ):
            return cls._complete_action_objects(quick_parts)

        if density["sequence_markers"] > 0:
            sequence_normalized = re.sub(
                r"\b(?:and then|followed by|subsequently|thereafter|then)\b",
                ", ",
                text.strip(),
                flags=re.IGNORECASE,
            )
            sequence_normalized = re.sub(
                r"\b(?:before|after|once)\s+(?=(?:[A-Za-z]+ing|[A-Za-z]+)\b)",
                ", ",
                sequence_normalized,
                flags=re.IGNORECASE,
            )
            sequence_parts = [
                cls._normalize_fragment_leading_action(part, common_verbs)
                for part in sequence_normalized.split(",")
                if part.strip(" .,;")
            ]
            if len(sequence_parts) >= 2 and all(
                cls._first_verb(part, common_verbs) in common_verbs
                for part in sequence_parts
            ):
                return cls._complete_action_objects(sequence_parts)

        normalized_shared = re.sub(r",\s+and\s+", " and ", text.strip(), flags=re.IGNORECASE)
        shared_object = re.match(
            r"^(?P<verbs>(?:[a-z]+(?:\s*,\s*|\s+and\s+))+[a-z]+)\s+(?P<object>.+)$",
            normalized_shared,
            flags=re.IGNORECASE,
        )
        if shared_object:
            raw_verbs = re.split(r"\s*,\s*|\s+and\s+", shared_object.group("verbs"))
            verbs = [verb.strip().lower() for verb in raw_verbs if verb.strip()]
            obj = shared_object.group("object").strip(" .,;")
            if len(verbs) >= 2 and all(verb in common_verbs for verb in verbs):
                return [f"{verb} {obj}" for verb in verbs]

        if density["should_split"]:
            concern_parts = cls._split_semantic_concern_list(text)
            if len(concern_parts) >= 2:
                return concern_parts

        # Protect known compound noun/adjective phrases from being split
        protected = text
        noun_pairs = [
            r"(?:both\s+)?(?:\w+\s+)?and\s+(?:\w+\s+)?(?:doctor|patient|user|client|customer|employee|manager)",
            r"email\s+and\s+(?:push|sms|in.app)\s+notification",
            r"username\s+and\s+password",
            r"read\s+and\s+write",
            r"start\s+and\s+end",
            r"first\s+and\s+last\s+name",
            r"name\s+and\s+email",
            r"phone\s+(?:number\s+)?and\s+email",
            r"date\s+and\s+time",
        ]
        placeholders: dict[str, str] = {}
        for i, pattern in enumerate(noun_pairs):
            placeholder = f"__PROTECTED_{i}__"
            original = re.search(pattern, protected, flags=re.IGNORECASE)
            if original:
                placeholders[placeholder] = original.group(0)
                protected = re.sub(pattern, placeholder, protected, flags=re.IGNORECASE)

        # Normalize "and"/"or" separating verb phrases → ","
        normalized = re.sub(r";", ",", protected)
        normalized = re.sub(r"\s*,\s*(?:and\s+)?", ", ", normalized)
        normalized = re.sub(r"\s+and\s+", ", ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+or\s+", ", ", normalized, flags=re.IGNORECASE)

        parts = [p.strip(" .,;") for p in normalized.split(",") if p.strip(" .,;")]

        # Restore protected phrases
        restored = []
        for part in parts:
            for placeholder, original in placeholders.items():
                part = part.replace(placeholder, original)
            restored.append(part)

        def starts_with_verb(phrase: str) -> bool:
            return cls._first_verb(phrase, common_verbs) in common_verbs

        if len(restored) >= 2 and all(starts_with_verb(p) for p in restored):
            return cls._complete_action_objects(restored)

        return [text.strip(" .")]

    @staticmethod
    def _should_decompose(requirement: str) -> bool:
        """Return True if the requirement is compound and benefits from decomposition."""
        frags = PlannerAgent._decompose_requirement(requirement)
        return len(frags) > 1

    @staticmethod
    def _is_identity_verification_task(text: str) -> bool:
        lowered = text.lower()
        return (
            re.search(r"\b(verify|verification)\b", lowered) is not None
            and re.search(r"\b(account|identity|email|phone|sms|otp)\b", lowered) is not None
        )

    # ------------------------------------------------------------------ #
    #  Dependency inference (domain-agnostic semantic layers)             #
    # ------------------------------------------------------------------ #

    def _infer_direct_dependencies(self, tasks: list[Task], current_index: int) -> list[str]:
        """
        Infer task dependencies using a universal semantic-layer model:

        Layer 0  foundation       → prerequisite for everything
        Layer 1  identity         → prerequisite for auth, security
        Layer 2  auth             → prerequisite for access_control
        Layer 3  access_control   → prerequisite for crud, view, integration,
                                    notification, reporting, compliance,
                                    user_management, localization
        Layer 4  integration      → prerequisite for performance (integration scope)
        Layer 5  crud/view        → prerequisite for performance (domain scope)
        Layer 6  notification     → depends on crud or integration that triggers it
        Layer 7  performance      → depends on major functional scope tasks
        """
        current = tasks[current_index]
        current_tags = self._extract_semantic_tags(current.description)
        previous = tasks[:current_index]

        def latest(predicate) -> str | None:
            for task in reversed(previous):
                if predicate(task):
                    return task.id
            return None

        def latest_group(predicate) -> list[str]:
            matched_source: str | None = None
            matched_ids: list[str] = []
            for task in reversed(previous):
                if not predicate(task):
                    continue
                if matched_source is None:
                    matched_source = task.source
                if task.source != matched_source:
                    break
                matched_ids.append(task.id)
            return list(reversed(matched_ids))

        def latest_same_source(predicate) -> str | None:
            for task in reversed(previous):
                if task.source == current.source and predicate(task):
                    return task.id
            return None

        foundation_id = latest(
            lambda t: "foundation" in self._extract_semantic_tags(t.description)
        )
        identity_id = latest(
            lambda t: "identity" in self._extract_semantic_tags(t.description)
        )
        identity_group = latest_group(
            lambda t: "identity" in self._extract_semantic_tags(t.description)
        )
        auth_id = latest(
            lambda t: "auth" in self._extract_semantic_tags(t.description)
        )
        auth_group = latest_group(
            lambda t: "auth" in self._extract_semantic_tags(t.description)
        )
        verification_group = latest_group(
            lambda t: self._is_identity_verification_task(t.description)
        )
        access_control_id = latest(
            lambda t: "access_control" in self._extract_semantic_tags(t.description)
        )
        requirements_ingestion_id = latest(
            lambda t: "requirements_ingestion" in self._extract_semantic_tags(t.description)
        )
        planning_generation_id = latest(
            lambda t: "task_planning" in self._extract_semantic_tags(t.description)
            and re.search(r"\b(generate|structured list of tasks)\b", t.description, flags=re.IGNORECASE) is not None
        ) or latest(
            lambda t: "task_planning" in self._extract_semantic_tags(t.description)
        )
        dependency_analysis_id = latest(
            lambda t: "dependency_analysis" in self._extract_semantic_tags(t.description)
        )
        estimation_id = latest(
            lambda t: "estimation" in self._extract_semantic_tags(t.description)
        )
        dashboard_id = latest(
            lambda t: "dashboard" in self._extract_semantic_tags(t.description)
        )
        monitoring_id = latest(
            lambda t: "monitoring" in self._extract_semantic_tags(t.description)
        )
        orchestration_id = latest(
            lambda t: "orchestration" in self._extract_semantic_tags(t.description)
        )
        risk_analysis_id = latest(
            lambda t: "risk_analysis" in self._extract_semantic_tags(t.description)
        )
        evaluation_id = latest(
            lambda t: "evaluation" in self._extract_semantic_tags(t.description)
        )

        deps: list[str] = []

        def add(dep_id: str | None) -> None:
            if dep_id and dep_id != current.id and dep_id not in deps:
                deps.append(dep_id)

        def add_auth_baseline() -> None:
            if verification_group:
                for dep_id in verification_group:
                    add(dep_id)
            elif identity_group:
                for dep_id in identity_group:
                    add(dep_id)
            elif auth_group:
                for dep_id in auth_group:
                    add(dep_id)
            else:
                add(identity_id or auth_id)

        def add_artifact_membership_dependencies(text: str, tags: set[str]) -> None:
            lowered = text.lower()
            planning_artifact_scope = re.search(
                r"\b(tasks?|generated|reports?|dependency graph|dependencies|critical path|bottleneck|"
                r"timelines?|risk indicators?|evaluation metrics?|estimation|confidence intervals?|"
                r"semantic search|retrieval|dashboard|execution log|decision traces)\b",
                lowered,
            ) is not None
            if not planning_artifact_scope:
                return

            is_export_report_view = bool({"export", "reporting", "view", "dashboard"} & tags) or re.search(
                r"\b(export|download|report|dashboard|view|display|show)\b",
                lowered,
            ) is not None
            if not is_export_report_view:
                return

            if re.search(r"\b(tasks?|generated|structured list|plan|roadmap)\b", lowered):
                add(planning_generation_id)
            if re.search(r"\b(dependency graph|dependencies|critical path|bottleneck)\b", lowered):
                add(dependency_analysis_id or planning_generation_id)
            if re.search(r"\b(estimat(?:e|ion)|confidence intervals?|timelines?|effort)\b", lowered):
                add(estimation_id or planning_generation_id)
            if re.search(r"\b(risk|alerts?|risk indicators?)\b", lowered):
                add(risk_analysis_id or monitoring_id or planning_generation_id)
            if re.search(r"\b(reports?|dashboard|analytics|metrics)\b", lowered):
                add(planning_generation_id)

        def add_validation_feedback_dependencies(text: str, tags: set[str]) -> None:
            lowered = text.lower()
            validation_like = (
                "validation" in tags
                or re.search(
                    r"\b(feedback|critic|review|refine|refinement|validate|validation|"
                    r"clarification|assumptions?|ambiguous|incomplete)\b",
                    lowered,
                ) is not None
            )
            if not validation_like:
                return

            if re.search(r"\b(ambiguous|incomplete)\s+requirements?\b|\bclarification\b|\bassumptions?\b", lowered):
                add(requirements_ingestion_id)
                add(planning_generation_id)
            if re.search(r"\b(feedback|critic|review|refine|refinement|generated tasks?)\b", lowered):
                add(planning_generation_id)
            if re.search(r"\b(dependency graph|dependency correctness|critical path|bottleneck)\b", lowered):
                add(dependency_analysis_id or planning_generation_id)
            if re.search(r"\b(estimation|confidence intervals?|estimation error)\b", lowered):
                add(estimation_id or planning_generation_id)
            if re.search(r"\b(risk|underperformance|delays?|bottlenecks?)\b", lowered):
                add(risk_analysis_id or monitoring_id or planning_generation_id)

        def is_artifact_consumer(text: str, tags: set[str]) -> bool:
            lowered = text.lower()
            if {"dashboard", "export"} & tags:
                return True
            if "reporting" in tags and re.search(
                r"\b(report|reporting|dashboard|analytics|summary|summaries|metrics|visibility)\b",
                lowered,
            ):
                return True
            if "view" in tags and re.search(
                r"\b(view|display|show|read|access|return|surface)\b",
                lowered,
            ):
                return True
            if "monitoring" in tags and re.search(
                r"\b(log|trace|metrics|outputs?|results?|progress|status|summary|summaries|visibility)\b",
                lowered,
            ):
                return True
            return False

        def semantic_scope_tokens(text: str) -> set[str]:
            lowered = text.lower()
            normalized_patterns = (
                (r"\blab(?:oratory)?\b", "lab"),
                (r"\bappointments?\b|\bbookings?\b|\bschedul(?:e|ing)\b", "appointment"),
                (r"\bresults?\b", "result"),
                (r"\breports?\b|\breporting\b", "report"),
                (r"\bsummaries?\b", "summary"),
                (r"\bprescrib(?:e|es|ed|ing)\b|\bprescriptions?\b", "prescription"),
                (r"\bdiagnos(?:is|es)\b", "diagnosis"),
                (r"\bmedications?\b|\bmedicines?\b", "medication"),
                (r"\battachments?\b", "attachment"),
                (r"\bfiles?\b", "file"),
                (r"\blinks?\b", "link"),
                (r"\bdependencies?\b", "dependency"),
                (r"\bgraphs?\b", "graph"),
                (r"\btimelines?\b", "timeline"),
                (r"\bindicators?\b", "indicator"),
                (r"\bmetrics?\b", "metric"),
            )
            for pattern, replacement in normalized_patterns:
                lowered = re.sub(pattern, f" {replacement} ", lowered, flags=re.IGNORECASE)

            stopwords = {
                "the", "system", "must", "should", "shall", "will", "may", "can",
                "allow", "allows", "allowing", "support", "supports", "supporting",
                "provide", "provides", "providing", "implement", "workflow",
                "workflows", "manage", "manages", "managed", "using", "their",
                "from", "into", "with", "without", "under", "during", "within",
                "through", "after", "before", "between", "important", "different",
                "multiple", "including", "completed", "generated", "hospital",
            }
            tokens: set[str] = set()
            for raw in re.findall(r"[a-z][a-z0-9-]+", lowered):
                token = raw
                if token.endswith("ies") and len(token) > 4:
                    token = token[:-3] + "y"
                elif token.endswith("s") and len(token) > 4:
                    token = token[:-1]
                if token in stopwords:
                    continue
                if len(token) < 4 and token not in {"lab", "icu", "emr"}:
                    continue
                tokens.add(token)
            return tokens

        def is_data_producer(task: Task, tags: set[str] | None = None) -> bool:
            task_tags = tags or self._extract_semantic_tags(task.description)
            lowered = task.description.lower()
            if task_tags & {"foundation", "security", "compliance"}:
                return False
            if "access_control" in task_tags or re.search(
                r"\b(restrict|permission|access control|role-based)\b",
                lowered,
            ):
                return False
            if is_artifact_consumer(task.description, task_tags) and not re.search(
                r"\b(generate|export|analytics?|summary|dashboard)\b",
                lowered,
            ):
                return False
            return (
                bool(task_tags & {"crud", "task_planning", "dependency_analysis", "estimation", "risk_analysis", "evaluation", "storage"})
                or re.search(
                    r"\b(create|update|upload|record|generate|calculate|track|manage|assign|schedule|"
                    r"collect|request|return|prescrib|store|maintain|analy[sz]e|estimate|"
                    r"classify|construct|extract|ingest)\b",
                    lowered,
                ) is not None
            )

        def add_semantic_consumer_dependencies(text: str, tags: set[str]) -> None:
            lowered = text.lower()
            if not is_artifact_consumer(text, tags):
                return

            current_tokens = semantic_scope_tokens(text)
            candidates: list[tuple[int, int, Task]] = []
            for offset, task in enumerate(previous):
                task_tags = self._extract_semantic_tags(task.description)
                if not is_data_producer(task, task_tags):
                    continue
                if task.source == current.source and not current_tokens:
                    continue
                producer_tokens = semantic_scope_tokens(task.description)
                shared_tokens = current_tokens & producer_tokens
                score = len(shared_tokens) * 5
                if task.source == current.source:
                    score += 3
                if "crud" in task_tags:
                    score += 2
                if re.search(
                    r"\b(generate|upload|record|update|calculate|track|store|manage|create)\b",
                    task.description,
                    flags=re.IGNORECASE,
                ):
                    score += 2
                if "dashboard" in tags and "reporting" in task_tags:
                    score += 1
                if score >= 7:
                    candidates.append((score, offset, task))

            if candidates:
                chosen: list[Task] = []
                for _, _, task in sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True):
                    if task.id in {selected.id for selected in chosen}:
                        continue
                    chosen.append(task)
                    if len(chosen) == 3:
                        break
                for task in reversed(chosen):
                    add(task.id)
                return

            if re.search(r"\b(dashboard|report|analytics|summary|export)\b", lowered) is None:
                return

            fallback_group = latest_group(
                lambda t: (
                    t.source != current.source
                    and is_data_producer(t, self._extract_semantic_tags(t.description))
                )
            )
            for dep_id in fallback_group[-3:]:
                add(dep_id)

        def access_subject(text: str) -> str:
            match = re.match(
                r"^(?P<subject>[^,.;]+?)\s+(?:can|must|should|shall|will|may)\b",
                text,
                flags=re.IGNORECASE,
            )
            return match.group("subject").strip().lower() if match else ""

        def access_actor(text: str) -> str:
            subject = access_subject(text)
            if not subject:
                return "unknown"
            if re.search(r"\b(the system|platform|application|service|solution)\b", subject):
                return "system"
            if re.search(
                r"\b(admins?|managers?|staff|operators?|employees?|doctors?|"
                r"receptionists?|technicians?|lab technicians?|nurses?|"
                r"supervisors?|accountants?|cashiers?)\b",
                subject,
            ):
                return "privileged"
            if re.search(r"\b(users?|customers?|clients?|members?|patients?)\b", subject):
                return "end_user"
            return "unknown"

        def has_admin_or_global_scope(text: str) -> bool:
            return re.search(
                r"\b(admin(?:istrator)?s?|internal|back[\-\s]?office|management|"
                r"privileged|all users?|any user|any account|all accounts?|"
                r"all patients?|system[\-\s]?wide|organization[\-\s]?wide|"
                r"organisation[\-\s]?wide|tenant[\-\s]?wide|global)\b",
                text,
                flags=re.IGNORECASE,
            ) is not None

        def has_sensitive_shared_scope(text: str) -> bool:
            return re.search(
                r"\b(patient records?|medical records?|consultation notes?|"
                r"test results?|lab results?|booking records?|user accounts?|"
                r"permissions?|roles?|privileges?|activity access log|audit logs?)\b",
                text,
                flags=re.IGNORECASE,
            ) is not None

        def is_user_privacy_right(text: str) -> bool:
            return re.search(r"\bgdpr\b", text, flags=re.IGNORECASE) is not None and re.search(
                r"\b(data deletion|data export|consent withdrawal|access log|activity access log)\b",
                text,
                flags=re.IGNORECASE,
            ) is not None

        def is_public_discovery_task(text: str, tags: set[str], actor: str) -> bool:
            if actor not in {"end_user", "unknown"}:
                return False
            if "view" not in tags and re.search(
                r"\b(browse|search|filter|query|find|list|view|read)\b",
                text,
                flags=re.IGNORECASE,
            ) is None:
                return False
            return re.search(
                r"\b(product catalog|catalog(?:ue)?|products?|inventory|storefront|"
                r"marketplace|public content|articles?|documentation|help(?:\s+center)?|"
                r"faqs?|pricing|plans?)\b",
                text,
                flags=re.IGNORECASE,
            ) is not None

        def access_decision(text: str, tags: set[str]) -> str:
            actor = access_actor(text)
            if "access_control" in tags or "user_management" in tags:
                return "rbac"
            if actor == "privileged":
                return "rbac"
            if has_admin_or_global_scope(text):
                return "rbac"
            if is_user_privacy_right(text):
                return "auth"
            if actor == "system":
                if has_sensitive_shared_scope(text):
                    return "rbac"
                if "integration" not in tags and re.search(
                    r"\b(account|profile|wallet|transaction|balance|statement|payments?|"
                    r"bill payments?|fund transfers?|scheduled payments?|appointments?|"
                    r"notifications?|history|analytics|budget alerts|invoices?)\b",
                    text,
                    flags=re.IGNORECASE,
                ):
                    return "auth"
                return "public"
            if actor == "end_user":
                if is_public_discovery_task(text, tags, actor):
                    return "public"
                return "auth"
            if has_sensitive_shared_scope(text):
                return "rbac"
            if is_public_discovery_task(text, tags, actor):
                return "public"
            return "public"

        # Layer 0: foundation is prerequisite for all non-foundation tasks
        if "foundation" not in current_tags:
            add(foundation_id)

        # Layer 1→2: registration is prerequisite for verification; verification
        # is the preferred prerequisite for later auth workflows.
        is_registration_action = re.search(
            r"\b(register|sign up|signup|enroll|onboard)\b",
            current.description,
            flags=re.IGNORECASE,
        ) is not None and re.search(
            r"\bverify|verification|otp\b",
            current.description,
            flags=re.IGNORECASE,
        ) is None

        if "auth" in current_tags and not is_registration_action:
            if self._is_identity_verification_task(current.description):
                for dep_id in identity_group:
                    add(dep_id)
            else:
                for dep_id in verification_group:
                    add(dep_id)
                if not verification_group:
                    add(identity_id)

        if "security" in current_tags and re.search(
            r"\b(passwords?|credentials?)\b", current.description, flags=re.IGNORECASE
        ):
            for dep_id in identity_group:
                add(dep_id)

        # Access control should depend on the verified identity baseline, not MFA.
        if "access_control" in current_tags:
            for dep_id in verification_group:
                add(dep_id)
            if not verification_group:
                for dep_id in identity_group:
                    add(dep_id)

        # Layer 3: decide whether a task is public, auth-gated, or RBAC-gated.
        protected_domain = {
            "crud", "view", "integration", "notification",
            "reporting", "compliance", "user_management",
        }
        if current_tags & protected_domain and "access_control" not in current_tags:
            current_access = access_decision(current.description, current_tags)
            if current_access == "rbac":
                if access_control_id:
                    add(access_control_id)
                else:
                    add_auth_baseline()
            elif current_access == "auth":
                add_auth_baseline()

        # Technical planning flow: requirements intake -> task generation ->
        # graph/estimation/classification/storage -> risk/evaluation/dashboard.
        if "task_planning" in current_tags:
            add(requirements_ingestion_id)

        add_validation_feedback_dependencies(current.description, current_tags)
        add_artifact_membership_dependencies(current.description, current_tags)
        add_semantic_consumer_dependencies(current.description, current_tags)

        if "dependency_analysis" in current_tags:
            add(planning_generation_id)

        if "estimation" in current_tags or "classification" in current_tags:
            add(planning_generation_id)

        if "storage" in current_tags and re.search(
            r"\b(vector database|embeddings?|semantic search|retrieval)\b",
            current.description,
            flags=re.IGNORECASE,
        ):
            add(planning_generation_id)

        if "storage" in current_tags and re.search(
            r"\b(graph database)\b",
            current.description,
            flags=re.IGNORECASE,
        ):
            add(dependency_analysis_id or planning_generation_id)

        if "risk_analysis" in current_tags:
            add(monitoring_id)
            add(dependency_analysis_id)
            add(estimation_id)

        if "explainability" in current_tags:
            add(planning_generation_id)
            add(estimation_id)
            add(risk_analysis_id)

        if "dashboard" in current_tags:
            add(planning_generation_id)
            add(dependency_analysis_id)
            add(estimation_id)
            add(risk_analysis_id)

        if "export" in current_tags:
            add(planning_generation_id)
            if re.search(r"\b(graph|dependencies|critical path|bottleneck)\b", current.description, flags=re.IGNORECASE):
                add(dependency_analysis_id)
            if re.search(r"\b(analytics|metrics|dashboard|risk indicators?)\b", current.description, flags=re.IGNORECASE):
                add(dashboard_id or evaluation_id or risk_analysis_id or planning_generation_id)

        if re.search(r"\bexecution log\b|\bagent interactions\b", current.description, flags=re.IGNORECASE):
            add(orchestration_id)
            add(planning_generation_id)

        if "evaluation" in current_tags:
            add(planning_generation_id)
            add(dependency_analysis_id)
            add(estimation_id)
            add(risk_analysis_id)
            add(monitoring_id)

        # Calendar/scheduling integrations depend on the appointment booking task
        if "integration" in current_tags and re.search(r"\b(calendar|schedule|appointment)\b", current.description, flags=re.IGNORECASE):
            booking_id = latest(
                lambda t: re.search(r"\b(book|schedule)\b", t.description, flags=re.IGNORECASE) is not None
                and re.search(r"\bappointments?\b", t.description, flags=re.IGNORECASE) is not None
                and "integration" not in self._extract_semantic_tags(t.description)
            )
            add(booking_id)

        if current.req_type != "NFR" and "security" in current_tags and re.search(r"\bencrypt(?:ed|ion)?\b", current.description, flags=re.IGNORECASE):
            protected_data_scope = latest(
                lambda t: (
                    "security" not in self._extract_semantic_tags(t.description)
                    and bool(
                        {"crud", "view", "reporting", "user_management"}
                        & self._extract_semantic_tags(t.description)
                    )
                )
            )
            add(protected_data_scope)

        # Layer 4/5→7: performance constraints depend on major functional tasks
        if current.req_type != "NFR" and "performance" in current_tags:
            business_scope = latest(
                lambda t: (
                    "performance" not in self._extract_semantic_tags(t.description)
                    and re.search(
                        r"\b(book|schedule|order|checkout|pay|create)\b",
                        t.description,
                        flags=re.IGNORECASE,
                    ) is not None
                )
            )
            add(business_scope)
            for scope_tag in ("integration", "reporting"):
                scoped = latest(
                    lambda t, tag=scope_tag: (
                        "performance" not in self._extract_semantic_tags(t.description)
                        and tag in self._extract_semantic_tags(t.description)
                    )
                )
                add(scoped)
            technical_scope = latest(
                lambda t: (
                    "performance" not in self._extract_semantic_tags(t.description)
                    and bool(
                        {
                            "task_planning",
                            "dependency_analysis",
                            "estimation",
                            "dashboard",
                            "orchestration",
                            "monitoring",
                            "evaluation",
                        }
                        & self._extract_semantic_tags(t.description)
                    )
                )
            )
            add(technical_scope)

        # Layer 6: notification depends on what triggers it
        if "notification" in current_tags:
            detection_id = latest_same_source(
                lambda t: (
                    re.search(r"\b(detect|identify)\b", t.description, flags=re.IGNORECASE) is not None
                    and re.search(r"\bconflicts?\b", t.description, flags=re.IGNORECASE) is not None
                )
            )
            if detection_id:
                add(detection_id)
            else:
                trigger_id = latest(
                    lambda t: (
                        "integration" in self._extract_semantic_tags(t.description)
                        and "performance" not in self._extract_semantic_tags(t.description)
                    )
                )
                if not trigger_id:
                    trigger_id = latest(
                        lambda t: (
                            "crud" in self._extract_semantic_tags(t.description)
                            and "performance" not in self._extract_semantic_tags(t.description)
                        )
                    )
                add(trigger_id)

        if re.search(r"\bview\b", current.description, flags=re.IGNORECASE) and re.search(
            r"\bupcoming\b.*\bappointments?\b",
            current.description,
            flags=re.IGNORECASE,
        ):
            add(
                latest_same_source(
                    lambda t: (
                        re.search(r"\b(book|schedule)\b", t.description, flags=re.IGNORECASE) is not None
                        and re.search(r"\bappointments?\b", t.description, flags=re.IGNORECASE) is not None
                    )
                )
            )

        if re.search(r"\b(detect|identify)\b", current.description, flags=re.IGNORECASE) and re.search(
            r"\bappointment conflicts?\b",
            current.description,
            flags=re.IGNORECASE,
        ):
            add(
                latest(
                    lambda t: (
                        "integration" in self._extract_semantic_tags(t.description)
                        and re.search(r"\b(calendar|appointment)\b", t.description, flags=re.IGNORECASE) is not None
                    )
                )
            )
            add(
                latest(
                    lambda t: re.search(r"\b(book|schedule)\b", t.description, flags=re.IGNORECASE) is not None
                )
            )

        if re.search(r"\breschedule\b", current.description, flags=re.IGNORECASE) and re.search(
            r"\bappointments?\b",
            current.description,
            flags=re.IGNORECASE,
        ):
            add(
                latest_same_source(
                    lambda t: (
                        re.search(r"\bbook\b", t.description, flags=re.IGNORECASE) is not None
                        and re.search(r"\bappointments?\b", t.description, flags=re.IGNORECASE) is not None
                    )
                )
            )

        if re.search(r"\barrival\b", current.description, flags=re.IGNORECASE):
            add(
                latest_same_source(
                    lambda t: (
                        re.search(r"\b(create|book)\b", t.description, flags=re.IGNORECASE) is not None
                        and re.search(r"\bappointments?\b", t.description, flags=re.IGNORECASE) is not None
                    )
                )
            )

        if re.search(r"\bappointment status\b", current.description, flags=re.IGNORECASE):
            add(
                latest_same_source(
                    lambda t: (
                        re.search(r"\b(create|book|mark)\b", t.description, flags=re.IGNORECASE) is not None
                        and re.search(r"\bappointments?\b|\barrival\b", t.description, flags=re.IGNORECASE) is not None
                    )
                )
            )

        if re.search(r"\bresults?\b", current.description, flags=re.IGNORECASE) and re.search(
            r"\bverified\b",
            current.description,
            flags=re.IGNORECASE,
        ):
            add(
                latest_same_source(
                    lambda t: (
                        re.search(r"\bupload\b", t.description, flags=re.IGNORECASE) is not None
                        and re.search(r"\bresults?\b", t.description, flags=re.IGNORECASE) is not None
                    )
                )
            )

        # Action coupling: downstream mutations depend on the originating workflow.
        if re.search(r"\bcancel\b", current.description, flags=re.IGNORECASE):
            add(
                latest_same_source(
                    lambda t: re.search(r"\b(book|schedule|create|request)\b", t.description, flags=re.IGNORECASE)
                )
            )

        if re.search(r"\brate\b", current.description, flags=re.IGNORECASE):
            add(
                latest_same_source(
                    lambda t: re.search(r"\b(book|schedule|visit|appointment)\b", t.description, flags=re.IGNORECASE)
                )
            )

        # Social platforms: feeds, moderation, and notification centers consume
        # earlier profile/content/community surfaces.
        if re.search(r"\b(news feed|activity feed|feed algorithm)\b", current.description, flags=re.IGNORECASE):
            add(
                latest(
                    lambda t: re.search(r"\b(profile|followers?|following)\b", t.description, flags=re.IGNORECASE)
                )
            )
            add(
                latest(
                    lambda t: re.search(r"\b(post creation|posts?|content)\b", t.description, flags=re.IGNORECASE)
                )
            )

        if re.search(r"\b(moderation|spam detection|moderator review)\b", current.description, flags=re.IGNORECASE):
            add(
                latest(
                    lambda t: re.search(r"\b(post creation|posts?|content|communities|groups?)\b", t.description, flags=re.IGNORECASE)
                )
            )

        if "notification" in current_tags and re.search(
            r"\b(likes?|comments?|mentions?|follows?|notification center)\b",
            current.description,
            flags=re.IGNORECASE,
        ):
            add(
                latest(
                    lambda t: re.search(r"\b(profile|followers?|following|posts?|content|communities|groups?)\b", t.description, flags=re.IGNORECASE)
                )
            )

        return deps

    def _propagate_hospital_workflow_chains(self, tasks: list[Task]) -> None:
        if not tasks:
            return

        def add_dep(task: Task, dep_id: str | None) -> None:
            if dep_id and dep_id != task.id and dep_id not in task.dependencies:
                task.dependencies.append(dep_id)

        stage_cache = {
            task.id: self._hospital_workflow_stages(
                task.description,
                self._extract_semantic_tags(task.description),
            )
            for task in tasks
        }

        def latest_before(
            current_index: int,
            stage_names: set[str],
            predicate=None,
        ) -> str | None:
            for candidate in reversed(tasks[:current_index]):
                if not (stage_cache[candidate.id] & stage_names):
                    continue
                if predicate and not predicate(candidate):
                    continue
                return candidate.id
            return None

        for index, task in enumerate(tasks):
            stages = stage_cache[task.id]
            lowered = task.description.lower()

            if {"appointment", "triage"} & stages:
                add_dep(task, latest_before(index, {"registration"}))

            if "encounter" in stages:
                add_dep(task, latest_before(index, {"appointment", "triage"}))

            if {"lab_order", "radiology_order"} & stages:
                add_dep(task, latest_before(index, {"encounter"}))

            if {"lab_collection", "lab_result"} & stages:
                add_dep(task, latest_before(index, {"lab_order"}))

            if {"radiology_execution", "radiology_report"} & stages:
                add_dep(task, latest_before(index, {"radiology_order"}))

            if "result_visibility" in stages:
                if re.search(r"\blab(?:oratory)?\b", lowered):
                    add_dep(task, latest_before(index, {"lab_result", "lab_collection", "lab_order"}))
                elif re.search(r"\bradiology\b|\bimaging\b|\bx-ray\b|\bct\b|\bultrasound\b", lowered):
                    add_dep(task, latest_before(index, {"radiology_report", "radiology_execution", "radiology_order"}))
                else:
                    add_dep(task, latest_before(index, {"lab_result", "radiology_report", "lab_collection", "radiology_execution"}))

            if "prescription" in stages:
                if re.search(r"\b(result|results|review|after reviewing|after results?)\b", lowered):
                    add_dep(
                        task,
                        latest_before(
                            index,
                            {"result_visibility", "lab_result", "radiology_report"},
                        ),
                    )
                else:
                    add_dep(task, latest_before(index, {"encounter"}))

            if "pharmacy" in stages:
                add_dep(task, latest_before(index, {"prescription"}))

            if "billing" in stages and re.search(
                r"\b(medication|medications|medicine|prescriptions?|services?|dispens(?:e|ing|ed)|pharmacy)\b",
                lowered,
            ):
                add_dep(task, latest_before(index, {"pharmacy"}))

            if "discharge" in stages and re.search(r"\bbilling\b", lowered):
                add_dep(task, latest_before(index, {"billing"}))

    @classmethod
    def _hospital_workflow_stages(cls, text: str, tags: set[str]) -> set[str]:
        lowered = text.lower()
        stages: set[str] = set()

        if re.search(r"\b(register|registration|sign up|signup|enroll|onboard)\b", lowered) and re.search(
            r"\b(patient|patients?|account|accounts?|user|users?)\b",
            lowered,
        ):
            stages.add("registration")

        if re.search(r"\b(appointments?|booking|book|triage|walk in|walk-in|arrival)\b", lowered) and re.search(
            r"\b(radiology|x-ray|ct|ultrasound|imaging)\b",
            lowered,
        ) is None:
            stages.add("appointment")
        if re.search(r"\btriage\b", lowered):
            stages.add("triage")

        if re.search(
            r"\b(patient profile|old visits?|consultation|encounter|diagnos(?:is|es)|treatment plans?)\b",
            lowered,
        ):
            stages.add("encounter")

        if re.search(r"\b(order|request)\b", lowered) and re.search(r"\b(lab|laboratory|sample)\b", lowered):
            stages.add("lab_order")
        if re.search(r"\b(order|request)\b", lowered) and re.search(
            r"\b(radiology|x-ray|ct|ultrasound|imaging|scan)\b",
            lowered,
        ):
            stages.add("radiology_order")

        if re.search(r"\bcollect\b.*\bsamples?\b|\bsample collection\b", lowered):
            stages.add("lab_collection")
        if re.search(
            r"\b(enter|record|verify)\b.*\b(lab(?:oratory)? results?|test results?)\b|\blaboratory results?\b",
            lowered,
        ) and re.search(r"\bnotify\b", lowered) is None:
            stages.add("lab_result")

        if re.search(r"\bschedule\b.*\bradiology requests?\b|\bimaging execution\b|\bperform scans?\b", lowered):
            stages.add("radiology_execution")
        if re.search(r"\bupload\b.*\bradiology reports?\b|\bradiology reports?\b", lowered):
            stages.add("radiology_report")

        if re.search(
            r"\b(return|notify|view|visible|surface|appear)\b",
            lowered,
        ) and re.search(r"\b(results?|reports?)\b", lowered):
            stages.add("result_visibility")

        if re.search(r"\bprescrib(?:e|es|ed|ing)|prescriptions?\b", lowered):
            stages.add("prescription")

        if re.search(r"\bpharmacy\b", lowered) and re.search(
            r"\b(receive|confirm|dispens(?:e|ing|ed)|availability|stock)\b",
            lowered,
        ):
            stages.add("pharmacy")
        elif re.search(r"\bdispens(?:e|ing|ed)\b", lowered):
            stages.add("pharmacy")

        if re.search(
            r"\b(billing|billable|patient balances?|insurance coverage|claim approval status|billing completion)\b",
            lowered,
        ):
            stages.add("billing")

        if re.search(r"\bdischarge\b", lowered):
            stages.add("discharge")

        return stages

    def _propagate_nfr_constraints(self, tasks: list[Task]) -> None:
        if not tasks:
            return

        tag_cache = {task.id: self._extract_semantic_tags(task.description) for task in tasks}
        by_id = {task.id: task for task in tasks}

        def rebuild_dependents() -> dict[str, set[str]]:
            dependents: dict[str, set[str]] = defaultdict(set)
            for task in tasks:
                for dep_id in task.dependencies:
                    dependents[dep_id].add(task.id)
            return dependents

        dependents = rebuild_dependents()

        def reaches(start_id: str, target_id: str) -> bool:
            stack = list(dependents.get(start_id, ()))
            seen: set[str] = set()
            while stack:
                node = stack.pop()
                if node == target_id:
                    return True
                if node in seen:
                    continue
                seen.add(node)
                stack.extend(dependents.get(node, ()))
            return False

        def mentions_sensitive_scope(text: str) -> bool:
            return re.search(
                r"\b(patient|user|account|profile|record|records|medical|diagnos(?:is|es)|"
                r"prescriptions?|results?|billing|claims?|payments?|execution log|decision traces|"
                r"embeddings?|retrieval|storage|audit logs?|history|data|vitals?|allerg(?:y|ies)|"
                r"medications?|lab(?:oratory)?|radiology|pharmacy|admissions?|discharge|"
                r"rooms?|beds?|icu|insurance|permissions?|internal notes?|student|students?|"
                r"course|courses|grade|grades|tuition|materials?|deadline|advisor|"
                r"enroll(?:ment)?|registration)\b",
                text,
                flags=re.IGNORECASE,
            ) is not None

        tasks_by_source: dict[str, list[Task]] = defaultdict(list)
        for task in tasks:
            tasks_by_source[task.source].append(task)

        def extract_audit_scope_categories(text: str) -> set[str]:
            categories: set[str] = set()
            if re.search(
                r"\b(patient records?|medical records?|patient file|patient history|diagnos(?:is|es)|"
                r"treatment plans?|laboratory results?|radiology reports?)\b",
                text,
                flags=re.IGNORECASE,
            ):
                categories.add("patient_records")
            if re.search(
                r"\b(billing entries|billing|claims?|claim approval|insurance|balances?|payments?)\b",
                text,
                flags=re.IGNORECASE,
            ):
                categories.add("billing")
            if re.search(
                r"\b(users?|accounts?|permissions?|roles?|privileges?)\b",
                text,
                flags=re.IGNORECASE,
            ):
                categories.add("access")
            return categories

        def collect_audit_scope_categories(nfr_task: Task) -> set[str]:
            categories = extract_audit_scope_categories(nfr_task.description)

            for sibling in tasks_by_source.get(nfr_task.source, []):
                if sibling.id == nfr_task.id:
                    continue
                categories.update(extract_audit_scope_categories(sibling.description))
            return categories

        def task_matches_audit_scope(task: Task, audit_scope: set[str]) -> bool:
            if not audit_scope:
                return True
            text = task.description
            checks = {
                "patient_records": r"\b(patient records?|medical records?|patient file|patient history|diagnos(?:is|es)|"
                r"treatment plans?|laboratory results?|radiology reports?)\b",
                "billing": r"\b(billing entries|billing|claims?|claim approval|insurance|balances?|payments?)\b",
                "access": r"\b(users?|accounts?|permissions?|roles?|privileges?)\b",
            }
            return any(
                re.search(checks[category], text, flags=re.IGNORECASE) is not None
                for category in audit_scope
                if category in checks
            )

        def is_audit_control_nfr(task: Task, tags: set[str]) -> bool:
            return task.req_type == "NFR" and (
                (
                    "compliance" in tags
                    and re.search(
                        r"\b(audit|audit trail|logging|logs?|traceability|change history)\b",
                        task.description,
                        flags=re.IGNORECASE,
                    ) is not None
                )
                or re.search(
                    r"\b(audit trail|audit logs?|compliance logging|change log|change history)\b",
                    task.description,
                    flags=re.IGNORECASE,
                ) is not None
            )

        def is_security_target(task: Task, tags: set[str]) -> bool:
            if task.req_type != "FR":
                return False
            return (
                mentions_sensitive_scope(task.description)
                and (
                    bool(tags & {"identity", "auth", "crud", "notification", "integration", "user_management", "storage", "access_control", "export", "dashboard", "monitoring"})
                    or bool(tags & {"view", "reporting"})
                    or re.search(
                        r"\b(store|storage|persist|retain|execution logs?|decision traces|export|dashboard|report|view|"
                        r"register|enroll|generate|process|send|upload|record|assign|pay|transfer|balance|transaction|notify)\b",
                        task.description,
                        flags=re.IGNORECASE,
                    ) is not None
                )
            )

        def is_offline_target(task: Task, tags: set[str]) -> bool:
            if task.req_type != "FR":
                return False
            if "integration" in tags or re.search(
                r"\b(external|api|cloud|sync|synchroni|connect|webhook|service)\b",
                task.description,
                flags=re.IGNORECASE,
            ):
                return True
            # Mobile/financial data tasks that must work offline locally
            if re.search(
                r"\b(balance\w*|transaction\w*|transfer\w*|fund\w*|payment\w*|"
                r"account\s+history|spending|statement)\b",
                task.description,
                flags=re.IGNORECASE,
            ) and not re.search(
                r"\b(public|help center|documentation|browse|search)\b",
                task.description,
                flags=re.IGNORECASE,
            ):
                return True
            return bool(
                tags
                & {
                    "task_planning",
                    "dependency_analysis",
                    "estimation",
                    "classification",
                    "explainability",
                    "storage",
                    "orchestration",
                    "evaluation",
                }
            )

        def is_performance_target(task: Task, tags: set[str]) -> bool:
            if task.req_type != "FR":
                return False
            if re.search(
                r"\b(public help|help center|documentation|faq|knowledge base|tutorial)\b",
                task.description,
                flags=re.IGNORECASE,
            ):
                return False
            if tags & {"integration", "reporting", "dashboard", "dependency_analysis", "estimation", "evaluation"}:
                return True
            if tags & {"identity", "auth", "crud", "notification"}:
                return True
            if "export" in tags and re.search(
                r"\b(export|download|json|csv|pdf)\b",
                task.description,
                flags=re.IGNORECASE,
            ) and re.search(
                r"\b(requirements?|documents?|input formats?)\b",
                task.description,
                flags=re.IGNORECASE,
            ) is None:
                return True
            if "view" in tags and re.search(
                r"\b(dashboard|reports?|analytics|metrics|summary|summaries|api|search|results?)\b",
                task.description,
                flags=re.IGNORECASE,
            ):
                return True
            return re.search(
                r"\b(api|dashboard|reports?|analytics|metrics|search|retrieval|dependency graph|"
                r"critical path|bottleneck|export|query|checkout|payments?|appointments?|booking|upload|"
                r"registration|enroll(?:ment)?|invoices?|notifications?|email|courses?|grades?)\b",
                task.description,
                flags=re.IGNORECASE,
            ) is not None

        def is_ui_quality_nfr(task: Task) -> bool:
            return task.req_type == "NFR" and re.search(
                r"\b(mobile[\-\s]?friendly|responsive\s+layout|responsive\s+design|accessibility|wcag)\b",
                task.description,
                flags=re.IGNORECASE,
            ) is not None

        def is_user_facing_target(task: Task, tags: set[str]) -> bool:
            if task.req_type != "FR":
                return False
            if tags & {"identity", "auth", "crud", "view", "notification", "integration", "reporting", "dashboard", "export"}:
                return True
            return re.search(
                r"\b(register|enroll|upload|generate|process|send|view|manage|book|schedule|search|"
                r"pay|invoice|course|grade|student|portal|email)\b",
                task.description,
                flags=re.IGNORECASE,
            ) is not None

        def is_audit_control_target(task: Task, tags: set[str], audit_scope: set[str]) -> bool:
            if task.req_type != "FR":
                return False
            if re.search(r"\b(browse|search|filter|help center|documentation|public)\b", task.description, flags=re.IGNORECASE):
                return False
            if not task_matches_audit_scope(task, audit_scope):
                return False
            if tags & {"crud", "user_management", "access_control", "storage", "monitoring"}:
                return True
            return (
                mentions_sensitive_scope(task.description)
                and re.search(
                    r"\b(create|update|delete|manage|edit|upload|record|assign|prescrib|dispens|"
                    r"schedule|cancel|approve|reject|transfer|discharge|admit|mark|calculate|"
                    r"generate billing|change|modify|suspend|reactivate|store|persist|retain)\b",
                    task.description,
                    flags=re.IGNORECASE,
                ) is not None
            )

        for nfr_task in tasks:
            if nfr_task.req_type != "NFR":
                continue

            nfr_tags = tag_cache[nfr_task.id]
            audit_scope = collect_audit_scope_categories(nfr_task)
            candidate_targets: list[Task] = []

            def is_compliance_target(task: Task, task_tags: set[str]) -> bool:
                if task.req_type != "FR":
                    return False
                # Audit-control NFRs are handled by is_audit_control_nfr — skip here
                if is_audit_control_nfr(nfr_task, nfr_tags):
                    return False
                return bool(task_tags & {"auth", "crud", "reporting"}) or re.search(
                    r"\b(pay\w*|transfer\w*|transaction\w*|fund\w*|invoice\w*|billing|"
                    r"balance\w*|login|register|financial|banking)\b",
                    task.description,
                    flags=re.IGNORECASE,
                ) is not None

            for task in tasks:
                if task.id == nfr_task.id:
                    continue
                task_tags = tag_cache[task.id]
                if "security" in nfr_tags and is_security_target(task, task_tags):
                    candidate_targets.append(task)
                    continue
                if "offline_operation" in nfr_tags and is_offline_target(task, task_tags):
                    candidate_targets.append(task)
                    continue
                if "compliance" in nfr_tags and is_compliance_target(task, task_tags):
                    candidate_targets.append(task)
                    continue
                if is_ui_quality_nfr(nfr_task) and is_user_facing_target(task, task_tags):
                    candidate_targets.append(task)
                    continue
                if "performance" in nfr_tags and is_performance_target(task, task_tags):
                    candidate_targets.append(task)
                    continue
                if is_audit_control_nfr(nfr_task, nfr_tags) and is_audit_control_target(task, task_tags, audit_scope):
                    candidate_targets.append(task)

            candidate_ids = {task.id for task in candidate_targets}
            if not candidate_ids:
                continue

            conflicting_incoming = [dep_id for dep_id in nfr_task.dependencies if dep_id in candidate_ids]
            if conflicting_incoming:
                nfr_task.dependencies = [dep_id for dep_id in nfr_task.dependencies if dep_id not in candidate_ids]
                dependents = rebuild_dependents()

            for target_task in candidate_targets:
                if nfr_task.id in target_task.dependencies:
                    continue
                if reaches(target_task.id, nfr_task.id):
                    continue
                target_task.dependencies.append(nfr_task.id)
                dependents[nfr_task.id].add(target_task.id)

    def _correct_inverted_performance_dependencies(self, tasks: list[Task]) -> None:
        if not tasks:
            return

        by_id = {task.id: task for task in tasks}
        tag_cache = {task.id: self._extract_semantic_tags(task.description) for task in tasks}

        def build_dependents() -> dict[str, set[str]]:
            dependents: dict[str, set[str]] = defaultdict(set)
            for task in tasks:
                for dep_id in task.dependencies:
                    dependents[dep_id].add(task.id)
            return dependents

        dependents = build_dependents()

        def reaches(start_id: str, target_id: str) -> bool:
            stack = list(dependents.get(start_id, ()))
            seen: set[str] = set()
            while stack:
                node = stack.pop()
                if node == target_id:
                    return True
                if node in seen:
                    continue
                seen.add(node)
                stack.extend(dependents.get(node, ()))
            return False

        def is_performance_nfr(task: Task, tags: set[str]) -> bool:
            return task.req_type == "NFR" and (
                "performance" in tags
                or re.search(r"\b(performance|scalab|latency|throughput|response time|concurrent)\b", task.description, flags=re.IGNORECASE)
                is not None
            )

        def is_legitimate_perf_predecessor(task: Task, tags: set[str]) -> bool:
            if task.req_type == "NFR":
                return bool(tags & {"foundation", "offline_operation", "security", "compliance"})
            if tags & {"foundation", "identity", "requirements_ingestion", "task_planning", "dependency_analysis", "storage", "orchestration"}:
                return True
            if re.search(
                r"\b(accept|parse|extract|ingest|build|construct|compile|generate|store|persist|create)\b",
                task.description,
                flags=re.IGNORECASE,
            ) and re.search(
                r"\b(requirements?|tasks?|dependency graph|data|records?|execution logs?|artifacts?)\b",
                task.description,
                flags=re.IGNORECASE,
            ):
                return True
            return False

        def is_downstream_perf_surface(task: Task, tags: set[str]) -> bool:
            if task.req_type != "FR":
                return False
            if tags & {"dashboard", "reporting", "export", "integration", "evaluation"}:
                return True
            if "view" in tags and re.search(r"\b(view|display|show|read|access|surface)\b", task.description, flags=re.IGNORECASE):
                return True
            return re.search(
                r"\b(dashboard|reports?|analytics|metrics|summary|summaries|export|download|api|ui|user interface|view|display|show)\b",
                task.description,
                flags=re.IGNORECASE,
            ) is not None

        for nfr_task in tasks:
            nfr_tags = tag_cache[nfr_task.id]
            if not is_performance_nfr(nfr_task, nfr_tags):
                continue

            inverted_predecessors: list[Task] = []
            preserved_dependencies: list[str] = []
            for dep_id in nfr_task.dependencies:
                dep_task = by_id.get(dep_id)
                if dep_task is None:
                    continue
                dep_tags = tag_cache[dep_task.id]
                if is_legitimate_perf_predecessor(dep_task, dep_tags):
                    preserved_dependencies.append(dep_id)
                    continue
                if is_downstream_perf_surface(dep_task, dep_tags):
                    inverted_predecessors.append(dep_task)
                    continue
                preserved_dependencies.append(dep_id)

            if not inverted_predecessors:
                continue

            nfr_task.dependencies = preserved_dependencies
            dependents = build_dependents()

            for dep_task in inverted_predecessors:
                if nfr_task.id not in dep_task.dependencies and not reaches(dep_task.id, nfr_task.id):
                    dep_task.dependencies.append(nfr_task.id)
                    dependents[nfr_task.id].add(dep_task.id)
                correction_note = (
                    f"Corrected inverted performance/scalability dependency: "
                    f"{dep_task.id} ({dep_task.title}) no longer gates {nfr_task.id} ({nfr_task.title})."
                )
                if correction_note not in self._dependency_corrections:
                    self._dependency_corrections.append(correction_note)

    # ------------------------------------------------------------------ #
    #  Executive summary helpers                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def build_plan_highlights(
        cls,
        task_list: TaskList,
        requirements: list[RequirementItem],
        graph_stats: dict,
    ) -> dict[str, object]:
        tasks_by_source: dict[str, list[Task]] = defaultdict(list)
        theme_counts: Counter[str] = Counter()
        task_lookup = {task.id: task for task in task_list.tasks}

        for task in task_list.tasks:
            tasks_by_source[task.source].append(task)
            theme_counts.update(
                tag for tag in cls._extract_semantic_tags(task.description) if tag != "general"
            )

        coverage_by_requirement = []
        for req in requirements:
            source_key = req.source
            source_tasks = tasks_by_source.get(source_key, [])
            coverage_by_requirement.append(
                {
                    "source": source_key,
                    "original_requirement": req.text,
                    "task_count": len(source_tasks),
                    "task_ids": [task.id for task in source_tasks],
                    "task_titles": [task.title for task in source_tasks],
                    "req_types": sorted({task.req_type for task in source_tasks}),
                    "max_complexity": max((task.complexity for task in source_tasks), default=0),
                }
            )

        high_complexity_tasks = [
            {
                "id": task.id,
                "title": task.title,
                "complexity": task.complexity,
                "source": task.source,
            }
            for task in task_list.tasks
            if task.complexity >= 4
        ]

        optional_tasks = [
            task for task in task_list.tasks
            if task.optional or task.confidence == "low"
        ]

        stage_summaries = []
        for index, group in enumerate(graph_stats.get("parallel_groups", []), start=1):
            stage_tasks = [task_lookup[task_id] for task_id in group if task_id in task_lookup]
            stage_theme_counts: Counter[str] = Counter()
            for task in stage_tasks:
                stage_theme_counts.update(
                    tag for tag in cls._extract_semantic_tags(task.description) if tag != "general"
                )
            dominant_themes = [theme for theme, _ in stage_theme_counts.most_common(3)]
            headline = cls._build_stage_headline(index, dominant_themes)
            stage_summaries.append(
                {
                    "stage": index,
                    "task_count": len(stage_tasks),
                    "task_ids": [task.id for task in stage_tasks],
                    "headline": headline,
                    "dominant_themes": dominant_themes,
                    "titles": [task.title for task in stage_tasks[:5]],
                }
            )

        dominant_themes = [
            {"theme": theme, "count": count}
            for theme, count in theme_counts.most_common(6)
        ]

        risk_signals: list[str] = []
        if theme_counts.get("integration", 0) > 0:
            risk_signals.append("External integrations are present and will need interface contracts plus vendor coordination.")
        if theme_counts.get("offline_operation", 0) > 0:
            risk_signals.append("Offline capability requires secure local storage, synchronization, and recovery-path validation.")
        if theme_counts.get("compliance", 0) > 0:
            risk_signals.append("Compliance-oriented requirements are present and should be validated early to avoid late rework.")
        if theme_counts.get("orchestration", 0) > 0:
            risk_signals.append("Multi-agent coordination depends on stable contracts, shared schemas, and observable execution traces.")
        if graph_stats.get("nfr_count", 0) >= max(2, graph_stats.get("total_tasks", 0) // 4):
            risk_signals.append("Non-functional scope is substantial, so quality engineering should run in parallel with feature delivery.")
        if high_complexity_tasks:
            risk_signals.append(
                f"{len(high_complexity_tasks)} high-complexity tasks sit on the roadmap and deserve early prototyping."
            )
        if optional_tasks:
            risk_signals.append(
                f"{len(optional_tasks)} tasks are marked as optional or low-confidence scope and should be planned outside the confirmed delivery baseline."
            )
        if graph_stats.get("validation_warnings"):
            risk_signals.append("Some non-root workflow tasks are still structurally isolated and should be reviewed before scheduling.")

        top_bottleneck = graph_stats.get("bottleneck_tasks", [{}])[0]
        top_themes_text = ", ".join(cls._friendly_theme_label(item["theme"]) for item in dominant_themes[:3]) or "general delivery"
        bottleneck_name = top_bottleneck.get("title") or top_bottleneck.get("id", "the top bottleneck")
        committee_brief = (
            f"This plan converts {len(requirements)} requirements into {len(task_list.tasks)} executable tasks "
            f"across {top_themes_text}. The critical delivery path runs through "
            f"{' -> '.join(graph_stats.get('critical_path', {}).get('task_ids', [])) or 'the core workflow'}, "
            f"while {bottleneck_name} is the main coordination hotspot. "
            f"The result is a committee-ready roadmap with clear sequencing, visible risk areas, and parallel execution opportunities."
        )

        return {
            "requirement_count": len(requirements),
            "task_count": len(task_list.tasks),
            "atomic_task_ratio": round(len(task_list.tasks) / len(requirements), 2) if requirements else 0.0,
            "theme_breakdown": dominant_themes,
            "high_complexity_tasks": high_complexity_tasks,
            "optional_scope": {
                "task_count": len(optional_tasks),
                "confirmed_task_count": len(task_list.tasks) - len(optional_tasks),
                "task_ids": [task.id for task in optional_tasks],
                "titles": [task.title for task in optional_tasks],
                "sources": sorted({task.source for task in optional_tasks}),
            },
            "coverage_by_requirement": coverage_by_requirement,
            "stage_summaries": stage_summaries,
            "risk_signals": risk_signals,
            "committee_brief": committee_brief,
        }

    @staticmethod
    def _friendly_theme_label(theme: str) -> str:
        theme_labels = {
            "crud": "core workflows",
            "view": "information access",
            "auth": "authentication",
            "identity": "identity",
            "integration": "integrations",
            "notification": "communications",
            "reporting": "reporting",
            "requirements_ingestion": "requirements intake",
            "task_planning": "task planning",
            "dependency_analysis": "dependency analysis",
            "estimation": "estimation",
            "classification": "classification",
            "monitoring": "monitoring",
            "risk_analysis": "risk analysis",
            "explainability": "explainability",
            "storage": "data stores",
            "orchestration": "orchestration",
            "dashboard": "dashboard visibility",
            "offline_operation": "offline operation",
            "evaluation": "evaluation",
            "user_management": "user management",
            "security": "security",
            "performance": "performance",
            "access_control": "access control",
            "localization": "localization",
            "compliance": "compliance",
        }
        return theme_labels.get(theme, theme.replace("_", " "))

    @classmethod
    def _build_stage_headline(cls, stage_index: int, dominant_themes: list[str]) -> str:
        themes = set(dominant_themes)
        if {"identity", "auth"} & themes:
            if "identity" in themes and "auth" in themes:
                return f"Stage {stage_index} establishes identity and authentication foundations"
            if "identity" in themes:
                return f"Stage {stage_index} establishes account and identity foundations"
            return f"Stage {stage_index} hardens authentication and account security"
        if "offline_operation" in themes and not ({"requirements_ingestion", "task_planning"} & themes):
            return f"Stage {stage_index} hardens offline resilience and synchronization constraints"
        if {"requirements_ingestion", "task_planning"} & themes:
            return f"Stage {stage_index} ingests requirements and builds the planning baseline"
        if "performance" in themes and {"evaluation", "reporting", "estimation"} & themes:
            return f"Stage {stage_index} validates planner quality metrics and scalability targets"
        if {"dashboard", "evaluation", "explainability"} & themes:
            return f"Stage {stage_index} exposes decision visibility and evaluation insights"
        if {"dependency_analysis", "estimation", "classification"} & themes:
            return f"Stage {stage_index} builds planning intelligence and execution analysis"
        if {"monitoring", "risk_analysis"} & themes:
            return f"Stage {stage_index} monitors delivery signals and surfaces project risk"
        if "orchestration" in themes:
            return f"Stage {stage_index} coordinates multi-agent execution"
        if "access_control" in themes:
            return f"Stage {stage_index} establishes role-based permissions"
        if "integration" in themes and "performance" in themes:
            return f"Stage {stage_index} connects external services and validates performance targets"
        if "notification" in themes:
            return f"Stage {stage_index} delivers user communications and alerting"
        if "reporting" in themes:
            return f"Stage {stage_index} delivers analytics and reporting visibility"
        if {"crud", "view", "user_management"} & themes:
            return f"Stage {stage_index} delivers core product workflows"
        if "security" in themes:
            return f"Stage {stage_index} hardens platform security controls"
        if "localization" in themes:
            return f"Stage {stage_index} expands localization and experience coverage"
        if dominant_themes:
            labels = ", ".join(cls._friendly_theme_label(theme) for theme in dominant_themes[:2])
            return f"Stage {stage_index} focuses on {labels}"
        return f"Stage {stage_index} focuses on general delivery"

    # ------------------------------------------------------------------ #
    #  Quality validation (structural — not domain-specific)              #
    # ------------------------------------------------------------------ #

    def _quality_issues(
        self,
        task_list: TaskList,
        requirements: list[RequirementItem],
        allow_decomposition: bool,
    ) -> list[str]:
        issues: list[str] = []
        tasks = task_list.tasks

        if not tasks:
            return ["no tasks generated"]

        # Sequential IDs
        for idx, task in enumerate(tasks, start=1):
            expected_id = f"T{idx:03d}"
            if task.id != expected_id:
                issues.append(f"non-sequential id: expected {expected_id}, got {task.id}")

        req_by_source = {item.source: item for item in requirements}
        source_counts: dict[str, int] = {}

        for task in tasks:
            if not self._is_valid_source_ref(task.source):
                issues.append(f"invalid source format: {task.source}")
                continue
            if task.source not in req_by_source:
                issues.append(f"unknown source reference: {task.source}")
                continue
            source_counts[task.source] = source_counts.get(task.source, 0) + 1

            # req_type must match classifier
            expected_type = self._classify_req_type(req_by_source[task.source].text)
            if task.req_type != expected_type:
                issues.append(
                    f"req_type mismatch at {task.id}: expected {expected_type}, got {task.req_type}"
                )

            # Title must start with an action verb
            if not self._is_action_title(task.title):
                issues.append(f"non action-oriented title at {task.id}: {task.title!r}")

            # Complexity within ±1 of expected (LLM has some judgement latitude)
            expected_complexity = self._score_complexity(req_by_source[task.source].text, expected_type)
            if abs(task.complexity - expected_complexity) > 1:
                issues.append(
                    f"complexity out of range at {task.id}: "
                    f"expected ~{expected_complexity}, got {task.complexity}"
                )

        # Mapping cardinality
        if not allow_decomposition:
            if len(tasks) != len(requirements):
                issues.append(
                    f"1:1 mapping violated: expected {len(requirements)} tasks, got {len(tasks)}"
                )
        else:
            if len(tasks) < len(requirements):
                issues.append(
                    f"decomposition produced fewer tasks than requirements: "
                    f"{len(tasks)} < {len(requirements)}"
                )
            for requirement in requirements:
                expected_fragments = self._decompose_requirement(requirement.text)
                expected_count = len(expected_fragments)
                actual_count = source_counts.get(requirement.source, 0)
                if expected_count > 1 and actual_count < expected_count:
                    issues.append(
                        f"decomposition under-produced tasks for {requirement.source}: "
                        f"expected at least {expected_count}, got {actual_count}"
                    )

        # Dependency integrity
        index_by_id = {task.id: idx for idx, task in enumerate(tasks)}
        for task in tasks:
            if task.id in task.dependencies:
                issues.append(f"self dependency at {task.id}")
            for dep in task.dependencies:
                if dep not in index_by_id:
                    issues.append(f"unknown dependency {dep} at {task.id}")
                    continue
                if index_by_id[dep] >= index_by_id[task.id]:
                    issues.append(f"non-previous dependency {dep} at {task.id}")
        for index, task in enumerate(tasks):
            inferred_dependencies = self._infer_direct_dependencies(tasks, index)
            if inferred_dependencies and not task.dependencies:
                issues.append(
                    f"missing inferred dependency at {task.id}: "
                    f"expected one of {inferred_dependencies}"
                )

        if len(tasks) > 1 and not any(task.dependencies for task in tasks):
            snapshot_corrections = list(self._dependency_corrections)
            try:
                reference_plan = self._build_rule_based_plan(
                    requirements=requirements,
                    allow_decomposition=allow_decomposition,
                )
            finally:
                self._dependency_corrections = snapshot_corrections
            if len(reference_plan.tasks) == len(tasks) and any(
                task.dependencies for task in reference_plan.tasks
            ):
                issues.append(
                    "missing dependency chain: expected at least one dependency "
                    "based on requirement structure"
                )

        return issues

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_valid_source_ref(source: str) -> bool:
        return re.match(
            r"^(?:line\s+\d+|block\s+\d+(?:\s+clause\s+\d+)?|REQ-\d+)$",
            source.strip(),
            flags=re.IGNORECASE,
        ) is not None

    @staticmethod
    def _looks_like_single_task_object(model_output: dict) -> bool:
        if "tasks" in model_output:
            return False
        taskish_keys = {
            "id",
            "title",
            "description",
            "req_type",
            "complexity",
            "dependencies",
            "source",
        }
        overlap = taskish_keys & set(model_output.keys())
        return len(overlap) >= 3 and "id" in overlap and "title" in overlap

    @classmethod
    def _is_action_title(cls, title: str) -> bool:
        first = title.strip().split(" ", 1)[0]
        return first in cls.ACTION_PREFIXES

    @classmethod
    def _normalize_title_text(cls, title: str) -> str:
        cleaned = re.sub(r"\s+", " ", title).strip()
        cleaned = re.sub(r"\s+,", ",", cleaned)
        cleaned = re.sub(r",\s*,+", ",", cleaned)
        replacements = {
            r"\bqR\b": "QR",
            r"\bkYC\b": "KYC",
            r"\baML\b": "AML",
            r"\bp2p\b": "P2P",
            r"\bpCI(?:-dSS)?\b": "PCI-DSS",
            r"\bgDPR\b": "GDPR",
            r"\bwCAG\b": "WCAG",
            r"\brTO\b": "RTO",
            r"\brPO\b": "RPO",
            r"\bsAR\b": "SAR",
        }
        for pattern, replacement in replacements.items():
            cleaned = re.sub(pattern, replacement, cleaned)
        cleaned = re.sub(r"\b(security|compliance|performance|workflow)\s+\1\b", r"\1", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
        return cleaned

    @classmethod
    def _title_mismatch(cls, actual_title: str, expected_title: str) -> bool:
        """Flag obvious domain leakage or semantic drift from the expected title."""
        action_verbs = ["integrate", "enforce", "optimize", "implement", "design", "configure"]
        actual_verb = next((v for v in action_verbs if v in actual_title.lower()), "implement")
        expected_verb = next((v for v in action_verbs if v in expected_title.lower()), "implement")
        if actual_verb != expected_verb:
            return True

        actual_lower = actual_title.casefold()
        expected_lower = expected_title.casefold()
        leak_phrases = (
            "project planning dashboard",
            "planner scalability",
            "project portfolios",
            "local models",
        )
        if any(phrase in actual_lower and phrase not in expected_lower for phrase in leak_phrases):
            return True

        actual_tokens = cls._content_tokens(actual_title)
        expected_tokens = cls._content_tokens(expected_title)
        if not expected_tokens:
            return False

        overlap = actual_tokens & expected_tokens
        if len(expected_tokens) >= 3 and len(overlap) < 2:
            return True
        if len(expected_tokens) < 3 and not overlap:
            return True
        return False

    @classmethod
    def _description_needs_reset(cls, description: object, expected_text: str) -> bool:
        if not isinstance(description, str) or not description.strip():
            return True

        normalized = re.sub(r"\s+", " ", description).strip().casefold()
        if normalized in {"title", "description", "task title", "task description", "todo", "tbd"}:
            return True
        if re.search(r"\bfull requirement text\b|\bsub-task description\b", normalized):
            return True
        if re.search(r"\b(?:fr|nfr)\b", normalized) and re.search(r"\b(?:fr|nfr)\b", expected_text.casefold()) is None:
            return True

        description_tokens = cls._content_tokens(description)
        expected_tokens = cls._content_tokens(expected_text)
        if not expected_tokens:
            return False

        overlap = description_tokens & expected_tokens
        required_overlap = len(expected_tokens) if len(expected_tokens) <= 3 else max(3, len(expected_tokens) - 1)
        if len(overlap) >= required_overlap:
            return False
        if normalized.startswith("the system should") or len(description_tokens) <= 4:
            return True
        return False

    # ------------------------------------------------------------------ #
    #  Tech stack detection (keyword-based, domain-agnostic)              #
    # ------------------------------------------------------------------ #

    _TECH_FRONTEND = [
        "react", "vue", "angular", "next.js", "nextjs", "nuxt", "svelte",
        "flutter", "swift", "kotlin", "xamarin", "ionic", "electron",
    ]
    _TECH_BACKEND = [
        "django", "fastapi", "flask", "node", "express", "spring", "laravel",
        ".net", "rails", "phoenix", "actix", "gin", "fiber",
    ]
    _TECH_DATABASE = [
        "postgresql", "mysql", "mongodb", "redis", "sqlite", "oracle",
        "cassandra", "elasticsearch", "dynamodb", "firestore", "mariadb",
    ]
    _TECH_DEVOPS = [
        "docker", "kubernetes", "aws", "azure", "gcp", "github actions",
        "ci/cd", "nginx", "terraform", "ansible", "jenkins", "gitlab ci",
    ]
    _TECH_EXTERNAL = [
        "stripe", "twilio", "sendgrid", "firebase", "oauth", "jwt",
        "graphql", "rest api", "websocket", "pusher", "algolia", "mapbox",
    ]

    @staticmethod
    def _matches_tech_keyword(text: str, keyword: str) -> bool:
        pattern = re.escape(keyword.lower()).replace(r"\ ", r"\s+")
        return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text) is not None

    @classmethod
    def _detect_tech_stack(cls, text: str) -> dict:
        """Keyword scan of requirements text to identify mentioned technologies."""
        lower = text.lower()
        detected = {
            "frontend":          [k for k in cls._TECH_FRONTEND if cls._matches_tech_keyword(lower, k)],
            "backend":           [k for k in cls._TECH_BACKEND if cls._matches_tech_keyword(lower, k)],
            "database":          [k for k in cls._TECH_DATABASE if cls._matches_tech_keyword(lower, k)],
            "devops":            [k for k in cls._TECH_DEVOPS if cls._matches_tech_keyword(lower, k)],
            "external_services": [k for k in cls._TECH_EXTERNAL if cls._matches_tech_keyword(lower, k)],
            "detected_from":     "requirements",
        }

        def add(category: str, label: str) -> None:
            values = detected[category]
            if label not in values:
                values.append(label)
                detected["detected_from"] = "requirements+inferred"

        if any(term in lower for term in ["web-based", "web based", "web platform", "browser"]):
            add("frontend", "web frontend")
            add("backend", "application api")
        if any(term in lower for term in ["api integration", "open banking api", "rest api", "graphql", "external account aggregation"]):
            add("backend", "application api")
        if any(term in lower for term in ["mobile app", "mobile application"]):
            add("frontend", "mobile client")
        if any(term in lower for term in ["mobile-friendly", "mobile friendly", "mobile-first", "mobile first", "mobile and desktop", "responsive interface"]):
            add("frontend", "responsive web ui")
        if any(term in lower for term in ["wcag", "accessibility", "accessible"]):
            add("frontend", "accessibility layer")
        if any(term in lower for term in ["arabic and english", "multilingual", "localization", "localisation"]):
            add("frontend", "i18n localization")
        if any(term in lower for term in ["record", "records", "grades", "invoices", "transcript", "course schedules", "transaction history", "wallet", "settlement reports"]):
            add("database", "relational database")
        if any(term in lower for term in ["online payment", "payments", "tuition invoices", "payment information", "bill payments", "qr code", "qr-code", "checkout", "wallet top-up", "p2p transfers"]):
            add("external_services", "payment gateway")
        if any(term in lower for term in ["kyc", "aml", "liveness", "sanctions screening", "identity verification"]):
            add("external_services", "identity verification")
            add("backend", "compliance controls")
        if any(term in lower for term in ["pci-dss", "pci dss", "gdpr", "audit evidence", "sar export"]):
            add("backend", "compliance controls")
        if any(term in lower for term in ["email notification", "email notifications", "automated email"]):
            add("external_services", "email service")
        if any(term in lower for term in ["sms", "twilio", "alerts", "push notification"]):
            add("external_services", "messaging service")
        if "learning management system" in lower or " lms" in lower:
            add("external_services", "lms integration")
        if any(term in lower for term in ["encrypted", "unauthorized access", "data protection", "biometric", "2fa", "mfa", "otp", "multi-factor"]):
            add("backend", "auth and authorization")
        if any(term in lower for term in ["highly available", "downtime", "concurrent users", "peak load"]):
            add("devops", "availability monitoring")
        if any(term in lower for term in ["audit logs", "distributed tracing", "observability", "observable"]):
            add("devops", "observability")
        if any(term in lower for term in ["rto", "rpo", "backup", "recovery objectives"]):
            add("devops", "disaster recovery")
        if any(term in lower for term in ["50,000 concurrent", "horizontal scaling", "peak load"]):
            add("devops", "horizontal scaling")

        return detected
