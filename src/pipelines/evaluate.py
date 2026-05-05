from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from datetime import datetime, timezone
from pathlib import Path
import re

from src.agents.critic import CriticAgent
from src.agents.planner import PlannerAgent, RequirementItem
from src.core.schemas import TaskList
from src.graph.dependency_graph import DependencyGraph
from src.parsers.brief_parser import BriefParser, BriefValidationError
from src.parsers.template_parser import TemplateParser, TemplateValidationError
from src.services import EffortEstimator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GROUND_TRUTH_PATH = PROJECT_ROOT / "data" / "evaluation" / "ground_truth.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_report.json"
DEFAULT_EVALUATION_MODE = "rules"
DEFAULT_DECISION_THRESHOLDS = {
    "fallback_rate_max_pct": 30.0,
    "direct_generation_rate_min_pct": 70.0,
    "average_critic_score_min": 0.85,
    "average_overall_score_min": 0.78,
}


@dataclass
class EvaluationResult:
    sample_id: str
    description: str
    input_file: str
    passed: bool
    checks: list[dict]
    task_count: int
    fr_count: int
    nfr_count: int
    optional_count: int
    score: float
    used_fallback: bool
    fallback_reason: str | None
    error: str | None
    tasks: list[dict] = field(default_factory=list)
    req_coverage: float = 0.0
    coverage_score: float = 0.0
    classification_score: float = 0.0
    complexity_score: float = 0.0
    dependency_score: float = 0.0
    overall_score: float = 0.0
    mmre: float = -1.0
    pred25: float = -1.0
    f1_fr: float = -1.0
    f1_nfr: float = -1.0
    critic_score: float = -1.0
    critic_status: str | None = None


class FallbackOnlyClient:
    def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
        raise RuntimeError("evaluation mode: LLM disabled")


def _normalize_evaluation_mode(mode: str) -> str:
    normalized = mode.strip().lower().replace("-", "_")
    allowed_modes = {"rules", "rules_kb", "llm", "llm_kb", "zero_shot"}
    if normalized not in allowed_modes:
        raise ValueError(
            f"Unsupported evaluation mode: {mode}. "
            f"Expected one of: {', '.join(sorted(allowed_modes))}"
        )
    return normalized


def _load_knowledge_base():  # noqa: ANN202
    from src.kb.seed_data import seed_kb
    from src.kb.vector_store import KnowledgeBase

    kb = KnowledgeBase()
    if kb.count() == 0:
        seed_kb(kb)
    return kb


def _load_llm_client(model_name: str | None = None):  # noqa: ANN202
    from src.llm.ollama_client import OllamaClient
    import requests as _requests

    client = OllamaClient(model=model_name) if model_name else OllamaClient()
    _requests.get(client.base_url, timeout=3)
    return client


def _sanitize_template_requirement_text(text: str) -> str:
    cleaned = re.sub(
        r"^Actor:\s*.+?\s+(?:\u2014|-)\s*",
        "",
        text,
    ).strip()
    cleaned = re.sub(r"\s+Notes:\s+.+$", "", cleaned).strip()
    return cleaned or text.strip()


def _planner_items_from_template(items: list[RequirementItem]) -> list[RequirementItem]:
    sanitized: list[RequirementItem] = []
    for item in items:
        sanitized.append(
            RequirementItem(
                line_no=item.line_no,
                source=item.source,
                text=_sanitize_template_requirement_text(item.text),
                sources=item.sources,
            )
        )
    return sanitized


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _sample_id(sample: dict) -> str:
    return sample.get("sample_id") or sample.get("id") or "UNKNOWN"


def _sample_input_label(sample: dict) -> str:
    return sample.get("input_file") or "<inline>"


def _error_result(sample: dict, error: str) -> EvaluationResult:
    return EvaluationResult(
        sample_id=_sample_id(sample),
        description=sample["description"],
        input_file=_sample_input_label(sample),
        passed=False,
        checks=[],
        task_count=0,
        fr_count=0,
        nfr_count=0,
        optional_count=0,
        score=0.0,
        used_fallback=False,
        fallback_reason=None,
        error=error,
    )


def _check_requirement_coverage(
    tasks: list, requirements: list, expected: dict
) -> dict:
    min_coverage = expected.get("req_coverage_min", 0.0)
    if min_coverage == 0.0:
        return {
            "name": "requirement_coverage",
            "passed": True,
            "expected": "N/A",
            "actual": "N/A",
        }
    total_reqs = len(requirements)
    if total_reqs == 0:
        return {
            "name": "requirement_coverage",
            "passed": True,
            "expected": f">= {min_coverage:.0%}",
            "actual": "0/0",
        }
    covered = {task.get("source") for task in tasks if task.get("source")}
    all_sources = {req.source for req in requirements}
    coverage = _requirement_coverage_value(tasks, requirements)
    passed = coverage >= min_coverage
    return {
        "name": "requirement_coverage",
        "passed": passed,
        "expected": f">= {min_coverage:.0%}",
        "actual": f"{coverage:.0%} ({len(covered & all_sources)}/{total_reqs})",
        "score": round(coverage, 3),
    }


def _requirement_coverage_value(tasks: list, requirements: list) -> float:
    total_reqs = len(requirements)
    if total_reqs == 0:
        return 0.0
    covered = {task.get("source") for task in tasks if task.get("source")}
    all_sources = {req.source for req in requirements}
    return len(covered & all_sources) / total_reqs


def _load_sample_text(sample: dict) -> tuple[str, str]:
    if "input_text" in sample:
        return str(sample["input_text"]), _sample_input_label(sample)

    input_file = sample.get("input_file")
    if not input_file:
        raise FileNotFoundError("Sample must define input_file or input_text")

    input_path = _resolve_path(Path(input_file))
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    return input_path.read_text(encoding="utf-8"), str(input_file)


def _requirements_from_inline_text(text: str) -> list[RequirementItem]:
    fragments: list[str] = []
    bullet_lines = [
        re.sub(r"^\s*[-*]\s+", "", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]
    if len(bullet_lines) > 1:
        fragments = bullet_lines
    else:
        fragments = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
            if sentence.strip()
        ]

    if not fragments and text.strip():
        fragments = [text.strip()]

    expanded_fragments: list[str] = []
    for fragment in fragments:
        match = re.match(r"^(?P<prefix>.+?\bmust support\b)\s+(?P<body>.+)$", fragment, re.IGNORECASE)
        if match and "," in match.group("body"):
            prefix = match.group("prefix").strip()
            body = match.group("body").strip().rstrip(".")
            parts = [
                part.strip()
                for part in body.replace(", and ", ", ").split(",")
                if part.strip()
            ]
            if len(parts) > 1:
                expanded_fragments.extend(f"{prefix} {part}" for part in parts)
                continue
        expanded_fragments.append(fragment)
    fragments = expanded_fragments

    requirements: list[RequirementItem] = []
    for idx, fragment in enumerate(fragments, start=1):
        source = f"REQ-{idx:02d}"
        req_text = fragment if fragment.endswith((".", "!", "?")) else f"{fragment}."
        requirements.append(
            RequirementItem(
                line_no=idx,
                source=source,
                text=req_text,
                sources=(source,),
            )
        )
    return requirements


def _expected_min(expected: dict, name: str, default: int = 0) -> int:
    value = expected.get(name)
    if isinstance(value, dict):
        return int(value.get("min", default))
    return int(expected.get(f"{name}_min", default))


def _expected_max(expected: dict, name: str, default: int = 10**9) -> int:
    value = expected.get(name)
    if isinstance(value, dict):
        return int(value.get("max", default))
    return int(expected.get(f"{name}_max", default))


def _score_checks(checks: list[dict]) -> float:
    if not checks:
        return 0.0
    return round(sum(1 for check in checks if check["passed"]) / len(checks), 3)


def compute_classification_score(result, expected_classifications) -> float:  # noqa: ANN001
    """How close is the actual FR/NFR ratio to expected? Returns 0.0-1.0"""
    actual_fr_ratio = result.fr_count / result.task_count if result.task_count > 0 else 0
    expected_fr = expected_classifications.get("FR", 0.6)
    deviation = abs(actual_fr_ratio - expected_fr)
    return max(0.0, 1.0 - deviation / 0.3)


def compute_complexity_calibration(result) -> float:  # noqa: ANN001
    """Are complexities well distributed? Penalize if all tasks have same complexity"""
    raw_tasks = getattr(result, "tasks", [])
    complexities = [
        task.get("complexity") if isinstance(task, dict) else task.complexity
        for task in raw_tasks
        if (task.get("complexity") if isinstance(task, dict) else task.complexity)
        is not None
    ]
    if not complexities:
        return 0.5
    unique = len(set(complexities))
    return min(1.0, unique / 3.0)


def compute_dependency_coherence(result) -> float:  # noqa: ANN001
    """No cycles, no suspicious isolates = 1.0. Each warning = -0.1"""
    if isinstance(result, TaskList):
        task_list = result
    else:
        raw_tasks = getattr(result, "tasks", [])
        if not raw_tasks:
            return 0.5
        task_list = TaskList.model_validate({"tasks": raw_tasks})
    summary = DependencyGraph(task_list).summary()
    warnings = len(summary.get("validation_warnings", []))
    if not summary.get("is_valid_dag", True):
        warnings += max(1, len(summary.get("cycle_issues", [])))
    return max(0.0, 1.0 - warnings * 0.1)


def compute_coverage_score(result, sample) -> float:  # noqa: ANN001, ARG001
    """Requirement coverage — already computed, just normalize to 0-1"""
    return getattr(result, "req_coverage", 0.0)


def compute_mmre(predicted_hours: list[int], actual_hours: list[int]) -> tuple[float, float]:
    """
    MMRE = mean(|actual - predicted| / actual).
    PRED(25) = % of tasks where |actual-predicted|/actual <= 0.25.
    Returns (mmre, pred25). Both -1.0 if lists empty/mismatched.
    """
    pairs = [(p, a) for p, a in zip(predicted_hours, actual_hours) if a and a > 0]
    if not pairs:
        return -1.0, -1.0
    mre_vals = [abs(p - a) / a for p, a in pairs]
    mmre = sum(mre_vals) / len(mre_vals)
    pred25 = sum(1 for v in mre_vals if v <= 0.25) / len(mre_vals)
    return round(mmre, 4), round(pred25, 4)


def compute_classification_f1(tasks: list[dict], sample: dict) -> tuple[float, float]:
    """
    Compute per-class F1 for FR/NFR using task_classifications ground truth.
    Returns (f1_fr, f1_nfr). -1.0 if no ground truth available.
    """
    classifications = (sample.get("expected") or {}).get("task_classifications", [])
    if not classifications:
        return -1.0, -1.0

    results: dict[str, dict] = {"FR": {"tp":0,"fp":0,"fn":0}, "NFR": {"tp":0,"fp":0,"fn":0}}
    for gt in classifications:
        fragment = gt["title_fragment"].lower()
        expected_type = gt["expected_type"]
        matched = next(
            (t for t in tasks if fragment in t.get("title","").lower()), None
        )
        if matched is None:
            results[expected_type]["fn"] += 1
            continue
        actual_type = matched.get("req_type", "FR")
        if actual_type == expected_type:
            results[expected_type]["tp"] += 1
        else:
            results[expected_type]["fn"] += 1
            results[actual_type]["fp"] += 1

    def _f1(cls: str) -> float:
        tp = results[cls]["tp"]
        fp = results[cls]["fp"]
        fn = results[cls]["fn"]
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec  = tp / (tp + fn) if (tp + fn) else 0.0
        return round(2 * prec * rec / (prec + rec), 3) if (prec + rec) else 0.0

    return _f1("FR"), _f1("NFR")


def compute_complexity_entropy(tasks: list[dict]) -> float:
    """Shannon entropy of complexity distribution, normalized by log2(5)."""
    import math
    from collections import Counter
    complexities = [t.get("complexity") for t in tasks if t.get("complexity")]
    if not complexities:
        return 0.0
    counts = Counter(complexities)
    n = sum(counts.values())
    entropy = -sum((c/n) * math.log2(c/n) for c in counts.values() if c > 0)
    return round(min(1.0, entropy / math.log2(5)), 3)


def _average_valid_metric(values: list[float]) -> float | None:
    valid = [value for value in values if value >= 0]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 3)


def run_sample(
    sample: dict,
    force_fallback: bool,
    kb=None,  # noqa: ANN001
    llm_client=None,  # noqa: ANN001
) -> EvaluationResult:
    try:
        text, input_label = _load_sample_text(sample)
    except FileNotFoundError as exc:
        return _error_result(sample, str(exc))

    input_format = sample.get("input_format", None)
    if input_format is None:
        first_chunk = text[:200]
        input_format = "template" if "[REQ-" in first_chunk else "raw"

    requirements_text = text
    template_requirements: list[RequirementItem] | None = None

    if input_format == "template":
        try:
            template_requirements = TemplateParser().parse(text)
        except TemplateValidationError as exc:
            return _error_result(sample, str(exc.errors))
        template_requirements = _planner_items_from_template(template_requirements)
        requirements_text = "\n".join(f"[{r.source}] {r.text}" for r in template_requirements)
    elif input_format == "brief":
        try:
            template_requirements = BriefParser().parse(text)
        except BriefValidationError as exc:
            if "[REQ-" in text[:200]:
                try:
                    template_requirements = TemplateParser().parse(text)
                except TemplateValidationError as template_exc:
                    return _error_result(sample, str(template_exc.errors))
                template_requirements = _planner_items_from_template(template_requirements)
                requirements_text = "\n".join(f"[{r.source}] {r.text}" for r in template_requirements)
                exc = None
            if exc is None:
                pass
            elif "input_text" not in sample and len(text.strip().splitlines()) > 3:
                return _error_result(sample, str(exc.errors))
            else:
                template_requirements = _requirements_from_inline_text(text)
        if template_requirements is None:
            if "input_text" not in sample and len(text.strip().splitlines()) > 3:
                return _error_result(sample, "Unable to parse brief sample")
            template_requirements = _requirements_from_inline_text(text)
        if "[REQ-" not in text[:200]:
            template_requirements = _planner_items_from_template(template_requirements)
            requirements_text = "\n".join(f"[{r.source}] {r.text}" for r in template_requirements)

    planner = PlannerAgent(
        llm_client if llm_client is not None else FallbackOnlyClient(),
        kb=kb,
    )
    original_prepare_requirements = None
    if template_requirements:
        planner._last_prepared_requirements = list(template_requirements)
        original_prepare_requirements = planner._prepare_requirements
        planner._prepare_requirements = (
            lambda _requirements_text, force_fallback=False: (  # noqa: ARG005
                requirements_text,
                list(template_requirements),
            )
        )

    try:
        task_list = planner.plan_from_requirements(
            requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
            force_fallback=force_fallback,
        )
        task_list = EffortEstimator.enrich_task_list(task_list, kb=kb)
        critic_report = CriticAgent().review(task_list)
        graph = DependencyGraph(task_list)
        stats = graph.summary()
    except Exception as exc:  # noqa: BLE001
        return EvaluationResult(
            sample_id=_sample_id(sample),
            description=sample["description"],
            input_file=input_label,
            passed=False,
            checks=[],
            task_count=0,
            fr_count=0,
            nfr_count=0,
            optional_count=0,
            score=0.0,
            used_fallback=planner.last_used_fallback,
            fallback_reason=planner.last_fallback_reason,
            error=str(exc),
        )
    finally:
        if original_prepare_requirements is not None:
            planner._prepare_requirements = original_prepare_requirements

    expected = sample["expected"]
    requirements = template_requirements or []
    tasks = [task.model_dump(mode="json") for task in task_list.tasks]
    task_count = len(task_list.tasks)
    fr_count = sum(1 for t in task_list.tasks if t.req_type == "FR")
    nfr_count = sum(1 for t in task_list.tasks if t.req_type == "NFR")
    optional_count = sum(1 for t in task_list.tasks if t.optional or t.confidence == "low")
    has_dependency_chain = any(bool(t.dependencies) for t in task_list.tasks)
    critical_path_length = stats["critical_path"]["length"]
    forbidden_substrings = expected.get("forbidden_title_substrings", [])
    violations = [
        t.title
        for t in task_list.tasks
        if any(sub.lower() in t.title.lower() for sub in forbidden_substrings)
    ]
    task_count_min = _expected_min(expected, "task_count")
    task_count_max = _expected_max(expected, "task_count")
    fr_count_min = _expected_min(expected, "fr_count")
    nfr_count_min = _expected_min(expected, "nfr_count")
    optional_count_min = _expected_min(expected, "optional_count")

    checks = [
        {
            "name": "task_count_in_range",
            "passed": task_count_min <= task_count <= task_count_max,
            "expected": f"{task_count_min}-{task_count_max}",
            "actual": str(task_count),
        },
        {
            "name": "fr_count_min",
            "passed": fr_count >= fr_count_min,
            "expected": f">= {fr_count_min}",
            "actual": str(fr_count),
        },
        {
            "name": "nfr_count_min",
            "passed": nfr_count >= nfr_count_min,
            "expected": f">= {nfr_count_min}",
            "actual": str(nfr_count),
        },
        {
            "name": "optional_count_min",
            "passed": optional_count >= optional_count_min,
            "expected": f">= {optional_count_min}",
            "actual": str(optional_count),
        },
        {
            "name": "forbidden_title_substrings",
            "passed": len(violations) == 0,
            "expected": "no forbidden substrings in titles",
            "actual": f"{len(violations)} violation(s): {violations[:3]}" if violations else "clean",
        },
        _check_requirement_coverage(tasks, requirements, expected),
    ]
    if "has_dependency_chain" in expected:
        checks.insert(
            4,
            {
                "name": "has_dependency_chain",
                "passed": has_dependency_chain == expected["has_dependency_chain"],
                "expected": str(expected["has_dependency_chain"]),
                "actual": str(has_dependency_chain),
            },
        )
    if "critical_path_min_length" in expected:
        insert_at = 5 if "has_dependency_chain" in expected else 4
        checks.insert(
            insert_at,
            {
                "name": "critical_path_min_length",
                "passed": critical_path_length >= expected["critical_path_min_length"],
                "expected": f">= {expected['critical_path_min_length']}",
                "actual": str(critical_path_length),
            },
        )
    score = _score_checks(checks)
    req_coverage = _requirement_coverage_value(tasks, requirements)
    result = EvaluationResult(
        sample_id=_sample_id(sample),
        description=sample["description"],
        input_file=input_label,
        passed=all(check["passed"] for check in checks),
        checks=checks,
        task_count=task_count,
        fr_count=fr_count,
        nfr_count=nfr_count,
        optional_count=optional_count,
        score=score,
        used_fallback=planner.last_used_fallback,
        fallback_reason=planner.last_fallback_reason,
        error=None,
        tasks=tasks,
        req_coverage=round(req_coverage, 3),
        critic_score=critic_report.score,
        critic_status=critic_report.status,
    )
    expected_classifications = (
        sample.get("expected_classifications")
        or expected.get("expected_classifications")
        or {}
    )
    result.coverage_score = round(compute_coverage_score(result, sample), 3)
    result.classification_score = round(
        compute_classification_score(result, expected_classifications),
        3,
    )
    result.complexity_score = round(compute_complexity_calibration(result), 3)
    result.dependency_score = round(compute_dependency_coherence(result), 3)
    result.overall_score = round(
        (
            result.coverage_score
            + result.classification_score
            + result.complexity_score
            + result.dependency_score
        )
        / 4,
        3,
    )

    # MMRE computation
    actual_hours = (sample.get("expected") or {}).get("actual_hours_per_task", [])
    if actual_hours:
        predicted_hours = [t.get("estimated_hours") or 0 for t in tasks]
        result.mmre, result.pred25 = compute_mmre(predicted_hours, actual_hours)

    # F1 classification
    result.f1_fr, result.f1_nfr = compute_classification_f1(tasks, sample)

    # Replace complexity_score with entropy-based score
    result.complexity_score = compute_complexity_entropy(tasks)
    result.overall_score = round(
        (
            result.coverage_score
            + result.classification_score
            + result.complexity_score
            + result.dependency_score
        )
        / 4,
        3,
    )
    return result


def _run_primary_results(
    samples: list[dict],
    mode: str,
    model_name: str | None = None,
) -> tuple[list[EvaluationResult], str, object | None, object | None]:
    normalized_mode = _normalize_evaluation_mode(mode)
    kb = _load_knowledge_base() if normalized_mode in {"rules_kb", "llm_kb"} else None
    llm_client = (
        _load_llm_client(model_name)
        if normalized_mode in {"llm", "llm_kb", "zero_shot"}
        else None
    )

    if normalized_mode == "rules":
        results = [run_sample(sample, force_fallback=True, kb=None) for sample in samples]
        return results, "rule_based_forced", kb, llm_client
    if normalized_mode == "rules_kb":
        results = [run_sample(sample, force_fallback=True, kb=kb) for sample in samples]
        return results, "rule_based_with_kb", kb, llm_client
    if normalized_mode == "llm":
        results = [
            run_sample(sample, force_fallback=False, kb=None, llm_client=llm_client)
            for sample in samples
        ]
        return results, "llm_pipeline", kb, llm_client
    if normalized_mode == "llm_kb":
        results = [
            run_sample(sample, force_fallback=False, kb=kb, llm_client=llm_client)
            for sample in samples
        ]
        return results, "llm_with_kb", kb, llm_client
    results = [_run_zero_shot(sample, llm_client) for sample in samples]
    return results, "zero_shot_llm", kb, llm_client


def _execution_summary(results: list[EvaluationResult]) -> dict:
    total = len(results)
    if total == 0:
        return {
            "successful_run_rate_pct": 0.0,
            "direct_generation_rate_pct": 0.0,
            "fallback_rate_pct": 0.0,
            "average_critic_score": None,
        }
    successful_runs = sum(1 for result in results if result.error is None)
    direct_generations = sum(
        1
        for result in results
        if result.error is None and not result.used_fallback
    )
    fallbacks = sum(1 for result in results if result.used_fallback)
    return {
        "successful_run_rate_pct": round(successful_runs / total * 100.0, 1),
        "direct_generation_rate_pct": round(direct_generations / total * 100.0, 1),
        "fallback_rate_pct": round(fallbacks / total * 100.0, 1),
        "average_critic_score": _average_valid_metric([r.critic_score for r in results]),
    }


def _check_pass_rates(results: list[EvaluationResult]) -> dict[str, float]:
    check_names: list[str] = []
    seen_checks: set[str] = set()
    for result in results:
        for check in result.checks:
            name = check["name"]
            if name not in seen_checks:
                seen_checks.add(name)
                check_names.append(name)

    check_pass_rates: dict[str, float] = {}
    for name in check_names:
        applicable_count = sum(
            1
            for result in results
            if any(check["name"] == name for check in result.checks)
        )
        passed_count = sum(
            1
            for result in results
            for check in result.checks
            if check["name"] == name and check["passed"]
        )
        check_pass_rates[name] = (
            passed_count / applicable_count * 100.0
            if applicable_count
            else 0.0
        )
    return {name: round(pct, 1) for name, pct in check_pass_rates.items()}


def _build_threshold_assessment(
    mode: str,
    execution_summary: dict,
    metric_summary: dict,
) -> dict:
    normalized_mode = _normalize_evaluation_mode(mode)
    applicable = normalized_mode in {"llm", "llm_kb"}
    if not applicable:
        return {
            "applicable": False,
            "reason": "Training decision thresholds are only meaningful for LLM pipeline modes.",
            "thresholds": DEFAULT_DECISION_THRESHOLDS,
            "checks": [],
            "training_recommended": None,
        }

    average_critic_score = execution_summary.get("average_critic_score")
    checks = [
        {
            "name": "fallback_rate_pct",
            "expected": f"<= {DEFAULT_DECISION_THRESHOLDS['fallback_rate_max_pct']:.1f}",
            "actual": execution_summary["fallback_rate_pct"],
            "passed": execution_summary["fallback_rate_pct"] <= DEFAULT_DECISION_THRESHOLDS["fallback_rate_max_pct"],
        },
        {
            "name": "direct_generation_rate_pct",
            "expected": f">= {DEFAULT_DECISION_THRESHOLDS['direct_generation_rate_min_pct']:.1f}",
            "actual": execution_summary["direct_generation_rate_pct"],
            "passed": execution_summary["direct_generation_rate_pct"] >= DEFAULT_DECISION_THRESHOLDS["direct_generation_rate_min_pct"],
        },
        {
            "name": "average_critic_score",
            "expected": f">= {DEFAULT_DECISION_THRESHOLDS['average_critic_score_min']:.2f}",
            "actual": average_critic_score,
            "passed": isinstance(average_critic_score, (int, float))
            and average_critic_score >= DEFAULT_DECISION_THRESHOLDS["average_critic_score_min"],
        },
        {
            "name": "average_overall_score",
            "expected": f">= {DEFAULT_DECISION_THRESHOLDS['average_overall_score_min']:.2f}",
            "actual": metric_summary.get("average_overall_score"),
            "passed": (metric_summary.get("average_overall_score") or 0.0)
            >= DEFAULT_DECISION_THRESHOLDS["average_overall_score_min"],
        },
    ]
    training_recommended = any(not check["passed"] for check in checks)
    return {
        "applicable": True,
        "thresholds": DEFAULT_DECISION_THRESHOLDS,
        "checks": checks,
        "training_recommended": training_recommended,
    }


def run_evaluation(
    ground_truth_path: Path = DEFAULT_GROUND_TRUTH_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    force_fallback: bool | None = None,
    mode: str = DEFAULT_EVALUATION_MODE,
    model_name: str | None = None,
) -> dict:
    dataset_path = _resolve_path(ground_truth_path)
    report_output_path = _resolve_path(report_path)
    samples = json.loads(dataset_path.read_text(encoding="utf-8"))

    normalized_mode = _normalize_evaluation_mode(mode)
    if force_fallback is not None:
        normalized_mode = "rules" if force_fallback else "llm_kb"

    results, evaluation_mode_label, kb, llm_client = _run_primary_results(
        samples,
        normalized_mode,
        model_name=model_name,
    )
    kb_ablation = None
    if normalized_mode == "rules":
        kb_for_ablation = _load_knowledge_base()
        kb_results = [
            run_sample(sample, force_fallback=True, kb=kb_for_ablation)
            for sample in samples
        ]
        kb_ablation = _build_kb_ablation(results, kb_results)

    total_samples = len(results)
    passed_samples = sum(1 for result in results if result.passed)
    pass_rate = (passed_samples / total_samples * 100.0) if total_samples else 0.0
    avg_task_count = (
        sum(result.task_count for result in results) / total_samples if total_samples else 0.0
    )
    execution_summary = _execution_summary(results)
    metric_summary = _metric_summary(results)
    check_pass_rates = _check_pass_rates(results)
    threshold_assessment = _build_threshold_assessment(
        normalized_mode,
        execution_summary,
        metric_summary,
    )

    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_mode": evaluation_mode_label,
        "evaluation_mode_key": normalized_mode,
        "llm_enabled": llm_client is not None,
        "kb_enabled": kb is not None,
        "llm_model": getattr(llm_client, "model", None),
        "total_samples": total_samples,
        "passed_samples": passed_samples,
        "pass_rate_pct": round(pass_rate, 1),
        "avg_task_count": round(avg_task_count, 2),
        "successful_run_rate_pct": execution_summary["successful_run_rate_pct"],
        "direct_generation_rate_pct": execution_summary["direct_generation_rate_pct"],
        "fallback_rate_pct": execution_summary["fallback_rate_pct"],
        "average_critic_score": execution_summary["average_critic_score"],
        "check_pass_rates": check_pass_rates,
        "metric_summary": metric_summary,
        "threshold_assessment": threshold_assessment,
        "results": [asdict(result) for result in results],
    }
    if kb_ablation is not None:
        report["kb_ablation"] = kb_ablation

    report_output_path.parent.mkdir(parents=True, exist_ok=True)
    report_output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md_report_path = report_output_path.with_suffix(".md")
    md_report_path.write_text(
        _render_markdown_report(report, results),
        encoding="utf-8",
    )

    print("=" * 60)
    print("  AI PROJECT MANAGER -- PLANNER EVALUATION")
    print("=" * 60)
    print(f"  Mode    : {evaluation_mode_label}")
    print(f"  Samples : {total_samples}")
    print(f"  Passed  : {passed_samples} / {total_samples}  ({pass_rate:.1f}%)")
    print(f"  Runs OK : {execution_summary['successful_run_rate_pct']:.1f}%")
    print(f"  Direct  : {execution_summary['direct_generation_rate_pct']:.1f}%")
    print(f"  Fallback: {execution_summary['fallback_rate_pct']:.1f}%")
    avg_critic_score = execution_summary.get("average_critic_score")
    if isinstance(avg_critic_score, (int, float)):
        print(f"  Critic  : {avg_critic_score:.3f}")
    print("")
    for name, pct in report["check_pass_rates"].items():
        print(f"  {name:<35} {pct:.0f}%")
    print("")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {result.sample_id} -- {result.description}")
        if not result.passed:
            for check in result.checks:
                if not check["passed"]:
                    print(
                        f"    x {check['name']}: expected {check['expected']}, got {check['actual']}"
                    )
        if result.error:
            print(f"    ERROR: {result.error}")
    print("")
    print("  Sample ID | Coverage | Classification | Complexity | Dependency | Overall | PASS/FAIL")
    print("  ----------|----------|----------------|------------|------------|---------|----------")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"  {result.sample_id:<9} | "
            f"{result.coverage_score:>8.2f} | "
            f"{result.classification_score:>14.2f} | "
            f"{result.complexity_score:>10.2f} | "
            f"{result.dependency_score:>10.2f} | "
            f"{result.overall_score:>7.2f} | "
            f"{status}"
        )
    print("")
    print(f"  Average Coverage:        {metric_summary['average_coverage']:.2f}")
    print(f"  Average Classification:  {metric_summary['average_classification']:.2f}")
    print(f"  Average Complexity Cal:  {metric_summary['average_complexity_calibration']:.2f}")
    print(f"  Average Dependency:      {metric_summary['average_dependency']:.2f}")
    print(f"  Overall System Score:    {metric_summary['overall_system_score']:.2f} / 1.00")
    if threshold_assessment["applicable"]:
        print("")
        decision = "YES" if threshold_assessment["training_recommended"] else "NO"
        print(f"  Training Recommended:    {decision}")
    if kb_ablation is not None:
        print("")
        _print_kb_ablation(kb_ablation)
    print("")
    print(f"  JSON  -> {report_output_path}")
    print(f"  MD    -> {md_report_path}")
    print("=" * 60)

    return report


def _metric_summary(results: list[EvaluationResult]) -> dict:
    total = len(results)
    if total == 0:
        return {
            "average_coverage": 0.0,
            "average_coverage_score": 0.0,
            "average_classification": 0.0,
            "average_classification_score": 0.0,
            "average_complexity_calibration": 0.0,
            "average_complexity_score": 0.0,
            "average_dependency": 0.0,
            "average_dependency_score": 0.0,
            "average_overall_score": 0.0,
            "overall_system_score": 0.0,
            "average_mmre": None,
            "average_pred25": None,
            "average_f1_fr": None,
            "average_f1_nfr": None,
        }

    average_coverage = sum(result.coverage_score for result in results) / total
    average_classification = sum(result.classification_score for result in results) / total
    average_complexity = sum(result.complexity_score for result in results) / total
    average_dependency = sum(result.dependency_score for result in results) / total
    overall = sum(result.overall_score for result in results) / total

    return {
        "average_coverage": round(average_coverage, 3),
        "average_coverage_score": round(average_coverage, 3),
        "average_classification": round(average_classification, 3),
        "average_classification_score": round(average_classification, 3),
        "average_complexity_calibration": round(average_complexity, 3),
        "average_complexity_score": round(average_complexity, 3),
        "average_dependency": round(average_dependency, 3),
        "average_dependency_score": round(average_dependency, 3),
        "average_overall_score": round(overall, 3),
        "overall_system_score": round(overall, 3),
        "average_mmre": _average_valid_metric([r.mmre for r in results]),
        "average_pred25": _average_valid_metric([r.pred25 for r in results]),
        "average_f1_fr": _average_valid_metric([r.f1_fr for r in results]),
        "average_f1_nfr": _average_valid_metric([r.f1_nfr for r in results]),
    }


def _build_kb_ablation(
    results: list[EvaluationResult],
    kb_results: list[EvaluationResult],
) -> dict:
    rows: list[dict] = []
    by_sample = {result.sample_id: result for result in kb_results}
    for result in results:
        kb_result = by_sample.get(result.sample_id)
        if kb_result is None:
            continue
        rows.append(
            {
                "sample_id": result.sample_id,
                "tasks_no_kb": result.task_count,
                "tasks_with_kb": kb_result.task_count,
                "nfr_no_kb": result.nfr_count,
                "nfr_with_kb": kb_result.nfr_count,
                "optional_no_kb": result.optional_count,
                "optional_with_kb": kb_result.optional_count,
                "delta_tasks": kb_result.task_count - result.task_count,
                "delta_nfr": kb_result.nfr_count - result.nfr_count,
                "delta_optional": kb_result.optional_count - result.optional_count,
            }
        )

    sample_count = len(rows)
    avg_delta_tasks = (
        sum(row["delta_tasks"] for row in rows) / sample_count
        if sample_count
        else 0.0
    )
    avg_delta_nfr = (
        sum(row["delta_nfr"] for row in rows) / sample_count
        if sample_count
        else 0.0
    )
    avg_delta_optional = (
        sum(row["delta_optional"] for row in rows) / sample_count
        if sample_count
        else 0.0
    )
    return {
        "rows": rows,
        "avg_delta_tasks": round(avg_delta_tasks, 2),
        "avg_delta_nfr": round(avg_delta_nfr, 2),
        "avg_delta_optional": round(avg_delta_optional, 2),
        "sample_count": sample_count,
    }


def _print_kb_ablation(kb_ablation: dict) -> None:
    print("  Sample | tasks_no_kb | tasks_with_kb | nfr_no_kb | nfr_with_kb | delta_tasks")
    print("  -------|-------------|---------------|-----------|-------------|------------")
    for row in kb_ablation["rows"]:
        print(
            f"  {row['sample_id']:<6} | "
            f"{row['tasks_no_kb']:<11} | "
            f"{row['tasks_with_kb']:<13} | "
            f"{row['nfr_no_kb']:<9} | "
            f"{row['nfr_with_kb']:<11} | "
            f"{row['delta_tasks']:+d}"
        )
    print(
        "  KB Impact: avg "
        f"{kb_ablation['avg_delta_tasks']:+.1f} tasks, "
        f"{kb_ablation['avg_delta_nfr']:+.1f} NFRs across "
        f"{kb_ablation['sample_count']} samples"
    )


def _render_markdown_report(report: dict, results: list[EvaluationResult]) -> str:
    evaluated_at = report["evaluated_at"][:19].replace("T", " ")
    total = report["total_samples"]
    passed = report["passed_samples"]
    rate = report["pass_rate_pct"]
    avg_tasks = report["avg_task_count"]
    fallback_rate = report["fallback_rate_pct"]
    successful_run_rate = report.get("successful_run_rate_pct")
    direct_generation_rate = report.get("direct_generation_rate_pct")
    average_critic_score = report.get("average_critic_score")

    lines: list[str] = []
    failure_rows: list[tuple[str, str, str, str]] = []
    lines.append("# Planner Agent Evaluation Report\n")
    lines.append(f"**Date:** {evaluated_at} UTC  ")
    lines.append(f"**Mode:** {report['evaluation_mode']}  ")
    lines.append(f"**Fallback rate:** {fallback_rate:.0f}%\n")

    # Summary box
    status_icon = "PASS" if passed == total else "FAIL"
    lines.append("## Summary\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Overall result | **{status_icon} {passed}/{total} samples passed** |")
    lines.append(f"| Pass rate | {rate:.1f}% |")
    lines.append(f"| Avg task count | {avg_tasks} |")
    if successful_run_rate is not None:
        lines.append(f"| Successful run rate | {successful_run_rate:.1f}% |")
    if direct_generation_rate is not None:
        lines.append(f"| Direct generation rate | {direct_generation_rate:.1f}% |")
    if average_critic_score is not None:
        lines.append(f"| Avg critic score | {average_critic_score:.3f} |")
    lines.append("")

    threshold_assessment = report.get("threshold_assessment") or {}
    if threshold_assessment.get("applicable"):
        lines.append("## Training Decision Gate\n")
        lines.append("| Check | Expected | Actual | Result |")
        lines.append("|---|---|---|---|")
        for check in threshold_assessment.get("checks", []):
            status = "OK" if check.get("passed") else "FAIL"
            lines.append(
                f"| `{check['name']}` | {check['expected']} | {check['actual']} | **{status}** |"
            )
        decision = "YES" if threshold_assessment.get("training_recommended") else "NO"
        lines.append("")
        lines.append(f"**Training recommended:** {decision}\n")
    lines.append("")

    # Check pass rates
    lines.append("## Check Pass Rates\n")
    lines.append("| Check | Pass Rate |")
    lines.append("|---|---|")
    for name, pct in report["check_pass_rates"].items():
        bar = "#" * int(pct / 10) + "-" * (10 - int(pct / 10))
        lines.append(f"| `{name}` | {bar} {pct:.0f}% |")
    lines.append("")

    # Per-sample results
    lines.append("## Sample Results\n")
    for result in results:
        icon = "PASS" if result.passed else "FAIL"
        lines.append(f"### [{icon}] {result.sample_id} -- {result.description}\n")
        lines.append(f"**Input:** `{result.input_file}`  ")
        lines.append(f"**Tasks:** {result.task_count} (FR: {result.fr_count} | NFR: {result.nfr_count} | Optional: {result.optional_count})  ")
        task_count_check = next(
            (check for check in result.checks if check["name"] == "task_count_in_range"),
            None,
        )
        expected_range = task_count_check["expected"] if task_count_check else "n/a"
        in_range = task_count_check["passed"] if task_count_check else False
        lines.append("**Task Quality**  ")
        lines.append(f"FR:NFR ratio: {result.fr_count}:{result.nfr_count}  ")
        lines.append(
            f"Task count in expected range ({expected_range}): {'Yes' if in_range else 'No'}  "
        )
        if result.critic_status:
            lines.append(
                f"Critic: {result.critic_status} ({result.critic_score:.3f})  "
            )
        if result.used_fallback:
            lines.append(f"**Fallback:** used ({result.fallback_reason or 'n/a'})  ")
        if result.error:
            lines.append(f"**Error:** {result.error}  ")
        lines.append("")

        lines.append("| Check | Result | Expected | Actual |")
        lines.append("|---|---|---|---|")
        for check in result.checks:
            check_icon = "OK" if check["passed"] else "FAIL"
            lines.append(
                f"| `{check['name']}` | **{check_icon}** | {check['expected']} | {check['actual']} |"
            )
            if not check["passed"]:
                failure_rows.append(
                    (result.sample_id, check["name"], str(check["expected"]), str(check["actual"]))
                )
        lines.append("")

    if failure_rows:
        lines.append("## Failure Analysis\n")
        lines.append("| Sample | Check | Expected | Actual |")
        lines.append("|---|---|---|---|")
        for sample_id, check_name, expected, actual in failure_rows:
            lines.append(f"| `{sample_id}` | `{check_name}` | {expected} | {actual} |")
        lines.append("")

    lines.append(
        "Generated by AI Project Manager Planner Evaluation — rule_based_forced mode"
    )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate planner output quality.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_GROUND_TRUTH_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_EVALUATION_MODE,
        choices=["rules", "rules_kb", "llm", "llm_kb", "zero_shot"],
        help="Primary evaluation mode to run.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Optional Ollama model name for LLM evaluation modes.",
    )
    parser.add_argument("--ablation", action="store_true")
    parser.add_argument(
        "--ablation-fast",
        action="store_true",
        help="Run the fast R/K ablation only; skip slow LLM and zero-shot conditions.",
    )
    parser.add_argument("--conditions", type=str, default=None)
    args = parser.parse_args()
    if args.ablation_fast:
        run_ablation(args.dataset, include_llm=False)
        return
    if args.ablation:
        run_ablation(args.dataset)
        return
    run_evaluation(args.dataset, args.report, mode=args.mode, model_name=args.model)


def _legacy_run_ablation(
    ground_truth_path: Path = DEFAULT_GROUND_TRUTH_PATH,
    output_path: Path | None = None,
) -> dict:
    """
    4-condition ablation study for the CritiPlan paper:
      A: rule-only, no KB
      B: rule-only, no KB  (same as A in fallback mode — variant for future LLM)
      C: rule-only + generic KB (old seed — skip if not available)
      D: rule-only + estimation RAG (new seed_data)
    Conditions A and D are the primary comparison.
    """
    from src.kb.seed_data import seed_kb
    from src.kb.vector_store import KnowledgeBase

    if output_path is None:
        output_path = PROJECT_ROOT / "data" / "evaluation" / "ablation_report.json"

    dataset_path = _resolve_path(ground_truth_path)
    samples = json.loads(dataset_path.read_text(encoding="utf-8"))

    print("Running ablation: Condition A (no KB)...")
    results_a = [run_sample(s, force_fallback=True, kb=None) for s in samples]

    print("Running ablation: Condition D (estimation RAG KB)...")
    kb = KnowledgeBase()
    if kb.count() == 0:
        seed_kb(kb)
    results_d = [run_sample(s, force_fallback=True, kb=kb) for s in samples]

    def _summarise(results: list[EvaluationResult], label: str) -> dict:
        m = _metric_summary(results)
        return {"condition": label, **m,
                "pass_rate": round(sum(1 for r in results if r.passed)/len(results)*100, 1)}

    comparison_rows = []
    by_d = {r.sample_id: r for r in results_d}
    for ra in results_a:
        rd = by_d.get(ra.sample_id)
        if rd is None:
            continue
        comparison_rows.append({
            "sample_id": ra.sample_id,
            "mmre_no_kb":   ra.mmre,
            "mmre_with_kb": rd.mmre if rd else -1.0,
            "mmre_delta":   round((rd.mmre - ra.mmre), 4) if rd and rd.mmre >= 0 and ra.mmre >= 0 else None,
            "pred25_no_kb":   ra.pred25,
            "pred25_with_kb": rd.pred25 if rd else -1.0,
            "coverage_no_kb":   ra.coverage_score,
            "coverage_with_kb": rd.coverage_score if rd else -1.0,
            "overall_no_kb":   ra.overall_score,
            "overall_with_kb": rd.overall_score if rd else -1.0,
        })

    mmre_deltas = [r["mmre_delta"] for r in comparison_rows if r["mmre_delta"] is not None]
    avg_mmre_delta = round(sum(mmre_deltas)/len(mmre_deltas), 4) if mmre_deltas else None

    condition_a = _summarise(results_a, "A: rule-only, no KB")
    condition_d = _summarise(results_d, "D: estimation RAG KB")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_samples": len(samples),
        "condition_A": condition_a,
        "condition_D": condition_d,
        "conditions": {
            "A": condition_a,
            "D": condition_d,
        },
        "avg_mmre_delta_A_to_D": avg_mmre_delta,
        "comparison": comparison_rows,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "="*60)
    print("  ABLATION STUDY — CritiPlan")
    print("="*60)
    print(f"  Samples tested  : {len(samples)}")
    print(f"  Condition A (no KB) — MMRE: {report['condition_A'].get('average_mmre','?')}")
    print(f"  Condition D (RAG)   — MMRE: {report['condition_D'].get('average_mmre','?')}")
    if avg_mmre_delta is not None:
        direction = "worse" if avg_mmre_delta > 0 else "better"
        print(f"  MMRE delta A->D : {avg_mmre_delta:+.4f} ({direction})")
    print(f"  Report saved    : {output_path}")
    print("="*60)
    return report
 
 
def _run_zero_shot(sample: dict, llm_client) -> EvaluationResult:  # noqa: ANN001
    """Zero-shot baseline: raw LLM with no pipeline structure."""
    try:
        text, input_label = _load_sample_text(sample)
    except FileNotFoundError as exc:
        return _error_result(sample, str(exc))
    prompt = (
        "You are a software project planner. Given the following project brief, "
        "list the required software tasks as a JSON object.\n\n"
        "Output ONLY valid JSON in this exact format:\n"
        '{"tasks": [{"title": "...", "req_type": "FR or NFR", "complexity": 1}]}\n\n'
        f"Project Brief:\n{text}"
    )
    try:
        raw = llm_client.generate_json(prompt)
        tasks_raw = raw.get("tasks", [])
        if not tasks_raw:
            return _error_result(sample, "zero-shot: no tasks in LLM response")
    except Exception as exc:  # noqa: BLE001
        return _error_result(sample, f"zero-shot LLM error: {exc}")
    if not isinstance(tasks_raw, list):
        return _error_result(sample, "zero-shot: invalid tasks payload in LLM response")

    def _safe_complexity(value: object) -> int:
        try:
            return max(1, min(5, int(value)))
        except (TypeError, ValueError):
            return 2

    normalized_tasks_raw: list[dict] = []
    for item in tasks_raw:
        if isinstance(item, dict):
            normalized_tasks_raw.append(item)
        elif isinstance(item, str) and item.strip():
            normalized_tasks_raw.append({
                "title": item.strip(),
                "req_type": "FR",
                "complexity": 2,
            })

    if not normalized_tasks_raw:
        return _error_result(sample, "zero-shot: no valid task objects in LLM response")

    tasks = [
        {
            "id": f"T{str(i + 1).zfill(3)}",
            "title": t.get("title", "Unnamed Task"),
            "req_type": (
                t.get("req_type", "FR")
                if t.get("req_type") in ("FR", "NFR")
                else "FR"
            ),
            "complexity": _safe_complexity(t.get("complexity", 2)),
            "dependencies": [],
            "estimated_hours": 0,
            "source": "zero-shot",
        }
        for i, t in enumerate(normalized_tasks_raw)
    ]
    task_count = len(tasks)
    fr_count = sum(1 for t in tasks if t["req_type"] == "FR")
    nfr_count = sum(1 for t in tasks if t["req_type"] == "NFR")
    expected = sample.get("expected", {})
    task_count_min = _expected_min(expected, "task_count")
    task_count_max = _expected_max(expected, "task_count")
    checks = [{
        "name": "task_count_in_range",
        "passed": task_count_min <= task_count <= task_count_max,
        "expected": f"{task_count_min}-{task_count_max}",
        "actual": str(task_count),
    }]
    result = EvaluationResult(
        sample_id=_sample_id(sample),
        description=sample.get("description", ""),
        input_file=input_label,
        passed=all(c["passed"] for c in checks),
        checks=checks,
        task_count=task_count,
        fr_count=fr_count,
        nfr_count=nfr_count,
        optional_count=0,
        score=_score_checks(checks),
        used_fallback=False,
        fallback_reason="zero-shot",
        error=None,
        tasks=tasks,
    )
    result.f1_fr, result.f1_nfr = compute_classification_f1(tasks, sample)
    expected_cls = expected.get("expected_classifications", {})
    result.coverage_score = round(compute_coverage_score(result, sample), 3)
    result.classification_score = round(compute_classification_score(result, expected_cls), 3)
    result.complexity_score = round(compute_complexity_entropy(tasks), 3)
    result.dependency_score = 1.0
    result.overall_score = round(
        (
            result.coverage_score
            + result.classification_score
            + result.complexity_score
            + result.dependency_score
        ) / 4,
        3,
    )
    return result


def run_ablation(
    ground_truth_path: Path = DEFAULT_GROUND_TRUTH_PATH,
    output_path: Path | None = None,
    include_llm: bool = True,
) -> dict:
    """5-condition ablation: R (rules), K (rules+KB), L (LLM+KB), Z (zero-shot), + bootstrap CI."""
    import random

    from src.kb.seed_data import seed_kb
    from src.kb.vector_store import KnowledgeBase

    if output_path is None:
        output_path = PROJECT_ROOT / "data" / "evaluation" / "ablation_report.json"

    dataset_path = _resolve_path(ground_truth_path)
    samples = json.loads(dataset_path.read_text(encoding="utf-8"))

    kb = KnowledgeBase()
    if kb.count() == 0:
        seed_kb(kb)

    llm_client = None
    if include_llm:
        try:
            from src.llm.ollama_client import OllamaClient

            client = OllamaClient()
            import requests as _requests

            _requests.get(client.base_url, timeout=3)
            llm_client = client
            print("Ollama detected - running LLM conditions (L, Z)")
        except Exception:  # noqa: BLE001
            print("Ollama not available - skipping LLM conditions (L, Z)")
    else:
        print("Fast ablation selected - skipping LLM conditions (L, Z)")

    def _bootstrap_ci(values: list, n: int = 1000, alpha: float = 0.95):  # noqa: ANN001
        valid = [v for v in values if v >= 0]
        if len(valid) < 2:
            return None, None
        boot = sorted(
            sum(random.choices(valid, k=len(valid))) / len(valid)
            for _ in range(n)
        )
        lo = int((1 - alpha) / 2 * n)
        hi = int((1 + alpha) / 2 * n)
        return round(boot[lo], 4), round(boot[min(hi, n - 1)], 4)

    def _summarise(results: list, label: str) -> dict:
        m = _metric_summary(results)
        passed = sum(1 for r in results if r.passed)
        mmre_vals = [r.mmre for r in results]
        pred_vals = [r.pred25 for r in results]
        mmre_lo, mmre_hi = _bootstrap_ci(mmre_vals)
        pred_lo, pred_hi = _bootstrap_ci(pred_vals)
        return {
            "condition": label,
            **m,
            "pass_rate": round(passed / len(results) * 100, 1),
            "avg_f1_fr": _average_valid_metric([r.f1_fr for r in results]),
            "avg_f1_nfr": _average_valid_metric([r.f1_nfr for r in results]),
            "mmre_ci_95": [mmre_lo, mmre_hi],
            "pred25_ci_95": [pred_lo, pred_hi],
        }

    print("Condition R: rules only, no KB...")
    results_r = [run_sample(s, force_fallback=True, kb=None) for s in samples]

    print("Condition K: rules + KB (full system, no LLM)...")
    results_k = [run_sample(s, force_fallback=True, kb=kb) for s in samples]

    results_l, results_z = None, None
    if llm_client is not None:
        print("Condition L: LLM + KB (full pipeline)...")
        results_l = [run_sample(s, force_fallback=False, kb=kb, llm_client=llm_client) for s in samples]
        print("Condition Z: zero-shot LLM (no pipeline)...")
        results_z = [_run_zero_shot(s, llm_client) for s in samples]

    conditions: dict = {
        "R": _summarise(results_r, "R: Rules only"),
        "K": _summarise(results_k, "K: Rules + KB"),
    }
    if results_l:
        conditions["L"] = _summarise(results_l, "L: LLM + KB (full system)")
    if results_z:
        conditions["Z"] = _summarise(results_z, "Z: Zero-shot LLM baseline")

    delta_r_k = round(
        (conditions["K"].get("average_overall_score", 0) or 0)
        - (conditions["R"].get("average_overall_score", 0) or 0),
        4,
    )

    avg_mmre_r = conditions["R"].get("average_mmre")
    avg_mmre_k = conditions["K"].get("average_mmre")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_samples": len(samples),
        "llm_available": llm_client is not None,
        "llm_conditions_requested": include_llm,
        "llm_conditions_skipped": llm_client is None,
        "conditions": conditions,
        "delta_R_to_K_overall": delta_r_k,
        "delta_R_to_L_overall": round(
            (conditions.get("L", {}).get("average_overall_score", 0) or 0)
            - (conditions["R"].get("average_overall_score", 0) or 0),
            4,
        ) if "L" in conditions else None,
        "condition_A": conditions["R"],
        "condition_D": conditions["K"],
        "avg_mmre_delta_A_to_D": (
            round(avg_mmre_k - avg_mmre_r, 4)
            if isinstance(avg_mmre_r, (int, float)) and isinstance(avg_mmre_k, (int, float))
            else None
        ),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 60)
    print("  ABLATION STUDY - AI Project Manager")
    print("=" * 60)
    for cond_key, cond in conditions.items():
        print(f"  {cond_key}: {cond['condition']}")
        print(
            "     "
            f"Overall={cond.get('average_overall_score', '?')}  "
            f"MMRE={cond.get('average_mmre', '?')}  "
            f"PRED(25)={cond.get('average_pred25', '?')}  "
            f"F1-FR={cond.get('avg_f1_fr', '?')}  "
            f"Pass={cond.get('pass_rate', '?')}%"
        )
    print(f"  Report: {output_path}")
    print("=" * 60)
    return report


if __name__ == "__main__":
    main()
