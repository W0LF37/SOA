"""Run the doc_to_tasks pipeline on every example brief and capture metrics
for an input-vs-output quality assessment.

Usage:
    python scripts/eval_all_briefs.py [--llm]

Without --llm uses force_fallback=True (rule-based, fast, deterministic).
With --llm uses the configured Ollama model.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipelines.doc_to_tasks import run_doc_to_tasks_pipeline

BRIEFS_DIR = PROJECT_ROOT / "data" / "raw" / "docs"
OUT_DIR = PROJECT_ROOT / "data" / "eval_runs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BRIEFS = sorted([p for p in BRIEFS_DIR.glob("project_brief_*.txt")])


def _bullet_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if re.match(r"^\s*[-*]\s+|^\s*\d+\.\s+", line))


def _section_features(text: str) -> dict:
    """Heuristic: count input bullets that look like FR vs NFR signals."""
    nfr_keywords = (
        "compli", "secur", "encrypt", "downtime", "availab", "latenc", "second",
        "perform", "scal", "concurrent", "rate limit", "audit", "gdpr", "pci",
        "hipaa", "iso", "language", "arabic", "english", "mobile", "offline"
    )
    fr = nfr = 0
    for line in text.splitlines():
        if not re.match(r"^\s*[-*]\s+|^\s*\d+\.\s+", line):
            continue
        low = line.lower()
        if any(k in low for k in nfr_keywords):
            nfr += 1
        else:
            fr += 1
    return {"fr_signals": fr, "nfr_signals": nfr, "total_bullets": fr + nfr}


def run_one(brief_path: Path, force_fallback: bool) -> dict:
    out_subdir = OUT_DIR / brief_path.stem
    out_subdir.mkdir(parents=True, exist_ok=True)

    tasks_path = out_subdir / "tasks.json"
    summary_path = out_subdir / "plan_summary.json"
    critic_path = out_subdir / "critic_report.json"
    risk_path = out_subdir / "risk_report.json"
    review_queue_path = out_subdir / "admin_review_queue.json"
    review_decisions_path = out_subdir / "admin_review_decisions.json"
    final_tasks_path = out_subdir / "tasks_final.json"
    monitor_path = out_subdir / "monitor_report.json"
    graph_path = out_subdir / "dependency_graph.json"

    brief_text = brief_path.read_text(encoding="utf-8", errors="replace")
    input_stats = _section_features(brief_text)
    input_stats["chars"] = len(brief_text)
    input_stats["lines"] = brief_text.count("\n") + 1

    started = time.time()
    error = None
    try:
        run_doc_to_tasks_pipeline(
            input_path=brief_path,
            output_path=tasks_path,
            graph_path=graph_path,
            summary_path=summary_path,
            review_queue_path=review_queue_path,
            review_decisions_path=review_decisions_path,
            final_tasks_path=final_tasks_path,
            critic_report_path=critic_path,
            risk_report_path=risk_path,
            monitor_report_path=monitor_path,
            input_format="brief",
            allow_fallback=True,
            force_fallback=force_fallback,
            use_kb=False,  # speed up; KB only changes effort estimates
        )
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    elapsed = time.time() - started

    record = {
        "brief": brief_path.name,
        "input": input_stats,
        "elapsed_seconds": round(elapsed, 2),
        "error": error,
    }

    if error:
        return record

    if tasks_path.exists():
        tasks_data = json.loads(tasks_path.read_text(encoding="utf-8"))
        tasks = tasks_data.get("tasks", [])
        record["tasks"] = {
            "total": len(tasks),
            "fr": sum(1 for t in tasks if t.get("req_type") == "FR"),
            "nfr": sum(1 for t in tasks if t.get("req_type") == "NFR"),
            "complexity_avg": round(
                sum(t.get("complexity", 0) for t in tasks) / max(len(tasks), 1), 2
            ),
            "complexity_max": max((t.get("complexity", 0) for t in tasks), default=0),
            "with_dependencies": sum(1 for t in tasks if t.get("dependencies")),
            "low_confidence": sum(1 for t in tasks if t.get("confidence") == "low"),
            "optional": sum(1 for t in tasks if t.get("optional")),
            "has_type_reason": sum(1 for t in tasks if t.get("type_reason")),
            "has_complexity_reason": sum(
                1 for t in tasks if t.get("complexity_reason")
            ),
        }
        ts = tasks_data.get("tech_stack") or {}
        if ts:
            record["tech_stack"] = {
                k: ts.get(k, []) for k in
                ["frontend", "backend", "database", "devops", "external_services"]
            }
            record["tech_stack"]["detected_from"] = ts.get("detected_from", "")
            record["tech_stack_count"] = sum(
                len(v) for k, v in record["tech_stack"].items()
                if isinstance(v, list)
            )
        else:
            record["tech_stack"] = None
            record["tech_stack_count"] = 0

    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        effort = summary.get("effort_summary") or {}
        analytics = summary.get("graph_analytics") or {}
        highlights = summary.get("plan_highlights") or {}
        record["plan"] = {
            "total_hours": effort.get("total_estimated_hours"),
            "fr_hours": effort.get("fr_estimated_hours"),
            "nfr_hours": effort.get("nfr_estimated_hours"),
            "total_days": effort.get("total_estimated_days"),
            "sprint_count": len(summary.get("sprint_plan", []) or []),
            "critical_path_length": len(analytics.get("critical_path", [])),
            "bottlenecks": len(analytics.get("bottleneck_tasks", [])),
            "parallel_groups": analytics.get("parallel_group_count", 0),
            "is_valid_dag": analytics.get("is_valid_dag"),
            "total_dependencies": analytics.get("total_dependencies"),
            "atomic_task_ratio": highlights.get("atomic_task_ratio"),
            "used_fallback": summary.get("used_fallback"),
            "fallback_reason": summary.get("fallback_reason"),
            "generation_mode": summary.get("generation_mode"),
            "domain_inference": (summary.get("committee_brief") or {}).get(
                "domain_inference"
            ),
        }
        # Coverage: how many input requirements got at least one task
        coverage = highlights.get("coverage_by_requirement") or []
        record["coverage"] = {
            "requirements": len(coverage),
            "covered": sum(1 for c in coverage if c.get("task_count", 0) > 0),
            "fr_covered": sum(
                1 for c in coverage if "FR" in (c.get("req_types") or [])
            ),
            "nfr_covered": sum(
                1 for c in coverage if "NFR" in (c.get("req_types") or [])
            ),
        }

    if critic_path.exists():
        critic = json.loads(critic_path.read_text(encoding="utf-8"))
        record["critic"] = {
            "status": critic.get("status"),
            "score": critic.get("score"),
            "issue_count": len(critic.get("issues", [])),
            "errors": sum(
                1 for i in critic.get("issues", []) if i.get("severity") == "error"
            ),
            "warnings": sum(
                1 for i in critic.get("issues", []) if i.get("severity") == "warning"
            ),
        }

    if risk_path.exists():
        risk = json.loads(risk_path.read_text(encoding="utf-8"))
        risks = risk.get("risks", []) or risk.get("risk_indicators", [])
        cat_counts: dict = {}
        for r in risks:
            cat = r.get("category", "?")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        record["risk"] = {
            "level": risk.get("risk_level"),
            "score": risk.get("risk_score"),
            "high": sum(1 for r in risks if r.get("severity") == "high"),
            "medium": sum(1 for r in risks if r.get("severity") == "medium"),
            "low": sum(1 for r in risks if r.get("severity") == "low"),
            "total": len(risks),
            "categories": cat_counts,
        }

    if review_queue_path.exists():
        try:
            queue = json.loads(review_queue_path.read_text(encoding="utf-8"))
            record["review_queue"] = len(queue) if isinstance(queue, list) else 0
        except Exception:
            record["review_queue"] = 0

    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use LLM (slow); default rule-based")
    parser.add_argument("--briefs", nargs="*", help="Subset of brief filenames")
    args = parser.parse_args()

    targets = BRIEFS
    if args.briefs:
        wanted = set(args.briefs)
        targets = [b for b in BRIEFS if b.name in wanted]

    force_fallback = not args.llm
    print(f"Running on {len(targets)} briefs ({'LLM' if args.llm else 'rule-based'})")

    all_records = []
    for i, brief in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {brief.name}")
        rec = run_one(brief, force_fallback)
        all_records.append(rec)
        if rec.get("error"):
            print(f"  ERROR: {rec['error']}")
        else:
            t = rec.get("tasks", {})
            c = rec.get("critic", {})
            r = rec.get("risk", {})
            print(
                f"  {t.get('total', 0)} tasks (FR {t.get('fr', 0)}/NFR {t.get('nfr', 0)})  "
                f"critic={c.get('status', '?')} {c.get('score', '?')}  "
                f"risk={r.get('level', '?')}  "
                f"hours={rec.get('plan', {}).get('total_hours', '?')}  "
                f"({rec['elapsed_seconds']}s)"
            )

    summary_path = OUT_DIR / "summary.json"
    summary_path.write_text(
        json.dumps(all_records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSummary written: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
