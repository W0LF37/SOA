from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

import requests

from src.agents.critic import CriticAgent, format_critic_report
from src.agents.monitor import MonitorAgent, format_monitor_report
from src.agents.risk_analyzer import RiskAnalyzer, format_risk_report
from src.agents.planner import PlannerAgent, RequirementItem
from src.graph.dependency_graph import DependencyGraph
from src.llm import OllamaClient
from src.parsers.brief_parser import BriefParser, BriefValidationError
from src.parsers.template_parser import TemplateParser, TemplateValidationError
from src.services import BriefGenerator, EffortEstimator, SprintPlanner

if TYPE_CHECKING:
    from src.core.schemas import CriticReport

from src.core.schemas import PlanSummary, TechStackReport
from src.core.runtime_paths import prepare_writable_file_path


DEFAULT_MODEL = "ai-project-manager-planner"
DEFAULT_HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen3.5-9B")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "data" / "raw" / "docs" / "requirements.txt"
DEFAULT_OUTPUT_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks.json")
DEFAULT_GRAPH_PATH = prepare_writable_file_path(PROJECT_ROOT, "storage/graph/dependency_graph.json")
DEFAULT_SUMMARY_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/plan_summary.json")
DEFAULT_REVIEW_QUEUE_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/admin_review_queue.json")
DEFAULT_REVIEW_DECISIONS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/admin_review_decisions.json")
DEFAULT_FINAL_TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks_final.json")
DEFAULT_CRITIC_REPORT_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/critic_report.json")
DEFAULT_RISK_REPORT_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/risk_report.json")
DEFAULT_MONITOR_REPORT_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/monitor_report.json")


def _project_path(path: Path) -> str:
    """Return a portable project-relative path for persisted reports."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix() if not path.is_absolute() else path.name


def build_llm_client(model_name: str, provider: str = "ollama") -> OllamaClient:
    normalized_provider = provider.strip().lower()
    if normalized_provider == "ollama":
        return OllamaClient(model=model_name)
    raise ValueError(f"Unsupported LLM provider: {provider}")


def _ollama_model_available(model_name: str) -> bool:
    response = requests.get("http://localhost:11434/api/tags", timeout=3)
    response.raise_for_status()
    payload = response.json()
    model_names: set[str] = set()
    for model in payload.get("models", []):
        if not isinstance(model, dict):
            continue
        for key in ("name", "model"):
            value = model.get(key)
            if value:
                model_names.add(str(value))
    return model_name in model_names or f"{model_name}:latest" in model_names


def _safe_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_message = message.encode(encoding, errors="replace").decode(encoding)
        print(safe_message)


def _load_knowledge_base_for_pipeline(use_kb: bool) -> tuple[object | None, int]:
    if not use_kb:
        return None, 0

    try:
        from src.kb.seed_data import seed_kb
        from src.kb.vector_store import get_kb, reset_kb

        kb = get_kb()
        if kb.count() == 0:
            seed_kb(kb)
        kb_document_count = kb.count()
        _safe_print(f"Knowledge Base ready ({kb_document_count} documents)")
        return kb, kb_document_count
    except Exception as exc:  # noqa: BLE001
        try:
            reset_kb()
        except Exception:  # noqa: BLE001
            pass
        _safe_print(f"[WARN] Knowledge Base unavailable ({exc}) -- continuing without KB")
        return None, 0


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _auxiliary_llm_layers_enabled() -> bool:
    return _env_flag("CRITIPLAN_ENABLE_LLM_AUX")


def build_review_queue(task_list, plan_summary) -> list[dict]:  # noqa: ANN001
    _ = plan_summary
    items: list[dict] = []
    for task in task_list.tasks:
        if not (
            task.confidence == "low"
            or task.optional is True
            or "UNCLEAR" in task.title
        ):
            continue

        if "UNCLEAR" in task.title:
            reason = "Title is unclear and requires clarification."
        elif task.optional and task.confidence == "low":
            reason = "Task is marked optional and low-confidence."
        else:
            reason = "Task is low-confidence and should be confirmed."

        items.append(
            {
                "task_id": task.id,
                "title": task.title,
                "description": task.description,
                "source": task.source,
                "confidence": task.confidence,
                "optional": task.optional,
                "complexity": getattr(task, "complexity", 1),
                "req_type": getattr(task, "req_type", "FR"),
                "dependencies": list(getattr(task, "dependencies", []) or []),
                "reason": reason,
            }
        )

    return sorted(items, key=lambda item: item["task_id"])


def run_doc_to_tasks_pipeline(
    input_path: Path = DEFAULT_INPUT_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    graph_path: Path = DEFAULT_GRAPH_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    review_queue_path: Path = DEFAULT_REVIEW_QUEUE_PATH,
    review_decisions_path: Path = DEFAULT_REVIEW_DECISIONS_PATH,
    final_tasks_path: Path = DEFAULT_FINAL_TASKS_PATH,
    critic_report_path: Path = DEFAULT_CRITIC_REPORT_PATH,
    risk_report_path: Path = DEFAULT_RISK_REPORT_PATH,
    monitor_report_path: Path = DEFAULT_MONITOR_REPORT_PATH,
    model_name: str = DEFAULT_MODEL,
    provider: str = "ollama",
    allow_fallback: bool = False,
    allow_decomposition: bool = False,
    force_fallback: bool = False,
    input_format: str = "brief",
    pre_parsed_requirements: list[RequirementItem] | None = None,
    repo_path: str | None = None,
    use_kb: bool = True,
) -> Path:
    if _env_flag("CRITIPLAN_FORCE_FALLBACK"):
        force_fallback = True
        allow_fallback = True
        _safe_print("[INFO] Fast demo mode enabled: using rule-based planner with KB calibration.")

    if provider.strip().lower() == "ollama" and not force_fallback:
        try:
            if not _ollama_model_available(model_name):
                _safe_print(
                    "⚠ Model not found. Run: ollama create "
                    "ai-project-manager-planner -f models/Modelfile"
                )
                force_fallback = True
        except requests.exceptions.RequestException:
            _safe_print("⚠ Ollama not reachable — switching to rule-based fallback")
            force_fallback = True

    if not input_path.exists():
        raise FileNotFoundError(f"Missing input file: {input_path}")

    requirements_text = input_path.read_text(encoding="utf-8")
    template_requirements = list(pre_parsed_requirements or [])
    if input_format == "template" and not template_requirements:
        try:
            template_requirements = TemplateParser().parse(requirements_text)
        except TemplateValidationError as exc:
            print("[ERROR] Template validation failed:")
            for err in exc.errors:
                print(f"  - {err}")
            raise SystemExit(1)
    elif input_format == "brief" and not template_requirements:
        try:
            template_requirements = BriefParser().parse(requirements_text)
        except BriefValidationError as exc:
            print("[ERROR] Brief validation failed:")
            for err in exc.errors:
                print(f"  - {err}")
            raise SystemExit(1)
    elif not template_requirements:
        raise ValueError(f"Unsupported input format: {input_format}")

    llm_client = build_llm_client(model_name, provider=provider)
    kb, kb_document_count = _load_knowledge_base_for_pipeline(use_kb)

    planner = PlannerAgent(llm_client, kb=kb)
    effective_requirements_text = requirements_text
    original_prepare_requirements = None
    if template_requirements:
        effective_requirements_text = "\n".join(
            f"[{item.source}] {item.text}" for item in template_requirements
        )
        planner._last_prepared_requirements = list(template_requirements)
        original_prepare_requirements = planner._prepare_requirements
        planner._prepare_requirements = (
            lambda _requirements_text, force_fallback=False: (  # noqa: ARG005
                effective_requirements_text,
                list(template_requirements),
            )
        )

    try:
        task_list = planner.plan_from_requirements(
            effective_requirements_text,
            allow_fallback=allow_fallback,
            allow_decomposition=allow_decomposition,
            force_fallback=force_fallback,
        )
    finally:
        if original_prepare_requirements is not None:
            planner._prepare_requirements = original_prepare_requirements

    requirements = planner.last_prepared_requirements or planner._parse_requirements(requirements_text)
    used_fallback = planner.last_used_fallback
    fallback_reason = planner.last_fallback_reason
    llm_attempted = planner.last_llm_attempted
    llm_accepted = planner.last_llm_accepted
    retrieved_kb_context = planner.last_retrieved_kb_context
    aux_llm_client = llm_client if _auxiliary_llm_layers_enabled() and not used_fallback else None
    if aux_llm_client is None:
        _safe_print("[INFO] Auxiliary LLM critic/risk layers disabled for a fast, reliable run.")

    # Attach tech-stack detection (keyword scan of the original brief)
    task_list.tech_stack = TechStackReport(**planner._detect_tech_stack(requirements_text))

    task_list = EffortEstimator.enrich_task_list(task_list, kb=kb)
    for stale_review_path in (review_decisions_path, final_tasks_path):
        stale_review_path.unlink(missing_ok=True)

    # Phase 2 — Critic Agent validation
    critic = CriticAgent(llm_client=aux_llm_client)
    critic_report = critic.review(task_list)
    critic_report_path.parent.mkdir(parents=True, exist_ok=True)
    critic_report_path.write_text(
        json.dumps(critic_report.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(format_critic_report(critic_report))
    if critic_report.status == "rejected":
        raise SystemExit(
            f"[CRITIC] Plan rejected (score={critic_report.score:.0%}). "
            "Fix the issues above and re-run the pipeline."
        )

    # Write tasks.json — clean TaskList only, no metadata mixed in.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(task_list.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Build dependency graph and run analytics.
    graph = DependencyGraph(task_list)
    stats = graph.summary()
    plan_highlights = planner.build_plan_highlights(task_list, requirements, stats)
    sprint_plan = SprintPlanner.build_sprint_plan(task_list, stats)
    brief_package = BriefGenerator.build(task_list, requirements, stats, sprint_plan)
    plan_highlights["committee_brief"] = brief_package["committee_brief"]

    # Write dependency_graph.json — node-link format for D3.js / Cytoscape.js.
    graph.save(graph_path)

    # Write plan_summary.json — full analytics report.
    generation_mode = (
        "rule_based_fallback_forced"
        if force_fallback
        else "rule_based_fallback_after_llm_failure"
        if used_fallback
        else "llm_with_fallback_available"
        if allow_fallback
        else "llm_strict"
    )
    plan_summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "provider": provider,
        "generation_mode": generation_mode,
        "llm_used": not used_fallback,
        "llm_attempted": llm_attempted,
        "llm_accepted": llm_accepted,
        "llm_model": model_name if not used_fallback else "rule-based-fallback",
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason,
        "retrieved_kb_context": retrieved_kb_context,
        "kb_document_count": kb_document_count,
        "llm_planning_trace": {
            "role": "LLM Planning Reasoner",
            "attempted": llm_attempted,
            "accepted": llm_accepted,
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
            "kb_enabled": use_kb,
            "retrieved_kb_context_chars": len(retrieved_kb_context),
            "kb_document_count": kb_document_count,
        },
        "critic": {
            "status": critic_report.status,
            "score": critic_report.score,
            "issues_count": len(critic_report.issues),
            "report_file": _project_path(critic_report_path),
        },
        "input_file": _project_path(input_path),
        "tasks_file": _project_path(output_path),
        "graph_file": _project_path(graph_path),
        "pipeline_config": {
            "allow_fallback": allow_fallback,
            "allow_decomposition": allow_decomposition,
            "force_fallback": force_fallback,
            "use_kb": use_kb,
        },
        "plan_highlights": plan_highlights,
        "committee_brief": brief_package["committee_brief"],
        "sprint_plan": sprint_plan,
        "effort_summary": brief_package["effort_summary"],
        "team_allocation": brief_package["team_allocation"],
        "risk_register": brief_package["risk_register"],
        "graph_analytics": stats,
    }
    review_queue = build_review_queue(task_list, plan_summary)
    admin_review_summary = {
        "status": "pending" if review_queue else "empty",
        "total_flagged": len(review_queue),
        "queue_file": _project_path(review_queue_path),
    }
    if not review_queue:
        admin_review_summary["tasks_final_file"] = _project_path(final_tasks_path)
    plan_summary["admin_review"] = admin_review_summary
    plan_summary = PlanSummary.model_validate(plan_summary).model_dump(mode="json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(plan_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    risk_analyzer = RiskAnalyzer(llm_client=aux_llm_client)
    risk_report = risk_analyzer.analyze(
        task_list=task_list,
        plan_summary=plan_summary,
        critic_report=critic_report,
    )
    risk_report_path.parent.mkdir(parents=True, exist_ok=True)
    risk_report_path.write_text(
        json.dumps(risk_report.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(format_risk_report(risk_report))

    review_queue_path.parent.mkdir(parents=True, exist_ok=True)
    review_queue_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generated_for_task_ids": [task.id for task in task_list.tasks],
                "total": len(review_queue),
                "items": review_queue,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if not review_queue:
        final_tasks_path.write_text(
            json.dumps(task_list.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if repo_path is not None:
        monitor = MonitorAgent()
        progress_report = monitor.track_progress(task_list, repo_path=repo_path)
        monitor_report_path.parent.mkdir(parents=True, exist_ok=True)
        monitor_report_path.write_text(
            json.dumps(progress_report.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(format_monitor_report(progress_report))

    _print_report(
        stats,
        plan_highlights,
        sprint_plan,
        brief_package["effort_summary"],
        generation_mode,
        used_fallback,
        fallback_reason,
        critic_report,
        review_queue,
        output_path,
        graph_path,
        summary_path,
        critic_report_path,
    )
    return output_path


def _print_report(
    stats: dict,
    plan_highlights: dict,
    sprint_plan: list[dict],
    effort_summary: dict,
    generation_mode: str,
    used_fallback: bool,
    fallback_reason: str | None,
    critic_report: CriticReport,
    review_queue: list[dict],
    output_path: Path,
    graph_path: Path,
    summary_path: Path,
    critic_report_path: Path,
) -> None:
    SEP = "=" * 62
    DIV = "-" * 62

    committee_brief = plan_highlights.get("committee_brief")
    if isinstance(committee_brief, dict):
        committee_text = committee_brief.get("graph_summary", "")
    else:
        committee_text = str(committee_brief or "")

    print(SEP)
    print("  AI PROJECT MANAGER  --  PHASE 1 PLANNER AGENT")
    print(SEP)

    dag_status = "VALID (no cycles)" if stats["is_valid_dag"] else "INVALID -- CYCLES DETECTED"
    print(f"\n  Tasks           : {stats['total_tasks']}  "
          f"({stats['fr_count']} FR  |  {stats['nfr_count']} NFR)")
    print(f"  Dependencies    : {stats['total_dependencies']}")
    print(f"  Avg complexity  : {stats['avg_complexity']} / 5")
    print(f"  Estimated effort: {effort_summary['total_estimated_hours']} hours")
    print(f"  Generation mode : {generation_mode}")
    complexity_dist = stats["complexity_distribution"]
    dist_str = "  ".join(f"C{k}={v}" for k, v in complexity_dist.items() if v > 0)
    print(f"  Distribution    : {dist_str}")
    print(f"  DAG             : {dag_status}")
    print(f"  Task ratio      : {plan_highlights['atomic_task_ratio']} atomic tasks per requirement")

    if stats["cycle_issues"]:
        for c in stats["cycle_issues"]:
            print(f"    !! {c}")

    print(f"\n  EXECUTIVE BRIEF")
    print(f"  {DIV}")
    print(f"  {committee_text}")

    if isinstance(committee_brief, dict):
        print(f"  {committee_brief.get('domain_inference', '')}")
        print(f"  {committee_brief.get('scope_assessment', '')}")
        print(f"  {committee_brief.get('confidence_signal', '')}")
        ambiguity_register = committee_brief.get("ambiguity_register", [])
        if ambiguity_register:
            print(f"  Ambiguities: {len(ambiguity_register)} flagged item(s).")
        assumption_log = committee_brief.get("assumption_log", [])
        if assumption_log:
            print(f"  Assumptions: {len(assumption_log)} structural note(s) recorded.")

    top_themes = plan_highlights.get("theme_breakdown", [])
    if top_themes:
        theme_text = "  ".join(f"{item['theme']}={item['count']}" for item in top_themes[:5])
        print(f"\n  DELIVERY THEMES")
        print(f"  {DIV}")
        print(f"  {theme_text}")

    cp = stats["critical_path"]
    print(f"\n  CRITICAL PATH  |  weight={cp['total_weight']}  |  {cp['length']} tasks")
    print(f"  {DIV}")
    for tid, title in zip(cp["task_ids"], cp["titles"]):
        print(f"    {tid}  {title}")

    bottlenecks = stats["bottleneck_tasks"]
    print(f"\n  BOTTLENECK TASKS  (blocks most work)")
    print(f"  {DIV}")
    for b in bottlenecks:
        bar = "#" * b["blocks"]
        print(f"    {b['id']}  blocks={b['blocks']} {bar:<14}  C{b['complexity']}  {b['title']}")

    roots = stats["root_tasks"]
    leaves = stats["leaf_tasks"]
    print(f"\n  ENTRY POINTS  [{len(roots)}]  :  {' | '.join(roots)}")
    print(f"  DELIVERABLES  [{len(leaves)}]  :  {' | '.join(leaves)}")

    groups = stats["parallel_groups"]
    print(f"\n  PARALLEL EXECUTION PLAN  |  {len(groups)} stages")
    print(f"  {DIV}")
    for stage in plan_highlights.get("stage_summaries", []):
        tasks_str = "  ".join(stage["task_ids"])
        print(f"    Stage {stage['stage']:02d}  [{stage['task_count']:2d} tasks]  {tasks_str}")
        print(f"      {stage['headline']}")

    if sprint_plan:
        print(f"\n  SPRINT PLAN")
        print(f"  {DIV}")
        for sprint in sprint_plan:
            print(
                f"    Sprint {sprint['sprint']:02d}  "
                f"[{sprint['duration_weeks']}w | {sprint['total_points']} pts | {sprint['total_estimated_hours']}h]  "
                f"{sprint['name']}"
            )
            print(f"      {sprint['goal']}")
            print(f"      {'  '.join(sprint['tasks'])}")

    risk_signals = plan_highlights.get("risk_signals", [])
    if risk_signals:
        print(f"\n  RISK SIGNALS")
        print(f"  {DIV}")
        for signal in risk_signals:
            print(f"    - {signal}")

    if used_fallback:
        print(f"\n  FALLBACK NOTICE")
        print(f"  {DIV}")
        print(f"    - Rule-based fallback was used for this run.")
        if fallback_reason:
            print(f"    - {fallback_reason}")

    if review_queue:
        print(f"\n  ADMIN REVIEW REQUIRED")
        print(f"  {DIV}")
        print(f"  {len(review_queue)} task(s) flagged for admin review.")
        print(f"  Run: python -m src.pipelines.admin_review")
    else:
        print(f"\n  Admin review: all tasks confirmed — no review required.")

    print(f"\n  Output files:")
    print(f"    tasks    ->  {output_path}")
    print(f"    graph    ->  {graph_path}")
    print(f"    summary  ->  {summary_path}")
    print(f"    critic   ->  {critic_report_path}")
    print(f"\n  CRITIC STATUS")
    print(f"  {DIV}")
    icon = "[OK]" if critic_report.status == "approved" else "[WARN]" if critic_report.status == "needs_revision" else "[FAIL]"
    print(f"    {icon} {critic_report.status.upper()}  (score={critic_report.score:.0%})")
    if critic_report.issues:
        for issue in critic_report.issues:
            print(f"    [{issue.severity.upper()}] {issue.message}")
    print(SEP)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 Planner Agent pipeline")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument(
        "--provider",
        type=str,
        default=os.getenv("LLM_PROVIDER", "ollama"),
        help="LLM provider to use: ollama.",
    )
    parser.add_argument(
        "--allow-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable rule-based fallback when LLM output fails quality checks (default: enabled).",
    )
    parser.add_argument(
        "--allow-decomposition",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Split compound requirements into executable sub-tasks (default: enabled).",
    )
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="Skip LLM entirely and use rule-based planner (requires --allow-fallback).",
    )
    parser.add_argument(
        "--format",
        "--input-format",
        dest="format",
        type=str,
        default="brief",
        choices=["template", "brief"],
        help="Input format: 'template' for structured REQ-NN blocks (default: brief), 'brief' for a Project Brief document.",
    )
    args = parser.parse_args()

    run_doc_to_tasks_pipeline(
        input_path=args.input,
        output_path=args.output,
        graph_path=args.graph,
        summary_path=args.summary,
        model_name=args.model,
        provider=args.provider,
        allow_fallback=args.allow_fallback,
        allow_decomposition=args.allow_decomposition,
        force_fallback=args.force_fallback,
        input_format=args.format,
    )


if __name__ == "__main__":
    main()
