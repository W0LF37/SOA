from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.pipelines.doc_to_tasks import (
    DEFAULT_GRAPH_PATH,
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_SUMMARY_PATH,
    run_doc_to_tasks_pipeline,
)
from src.pipelines.evaluate import (
    DEFAULT_GROUND_TRUTH_PATH,
    DEFAULT_REPORT_PATH,
    run_evaluation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BRIEF_INPUT = PROJECT_ROOT / "data" / "raw" / "docs" / "project_brief_sample.txt"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run planning + evaluation in one command.")
    parser.add_argument("--input", type=Path, default=DEFAULT_BRIEF_INPUT)
    parser.add_argument("--format", type=str, default="brief", choices=["brief", "template"])
    parser.add_argument("--model", type=str, default="ai-project-manager-planner")
    parser.add_argument(
        "--force-fallback",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_GROUND_TRUTH_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--skip-eval", action="store_true")
    args = parser.parse_args()

    print("\n" + "=" * 62)
    print("  STEP 1 / 2  —  PLANNING PIPELINE")
    print("=" * 62)
    run_doc_to_tasks_pipeline(
        input_path=args.input,
        output_path=DEFAULT_OUTPUT_PATH,
        graph_path=DEFAULT_GRAPH_PATH,
        summary_path=DEFAULT_SUMMARY_PATH,
        model_name=args.model,
        provider=os.getenv("LLM_PROVIDER", "ollama"),
        allow_fallback=True,
        allow_decomposition=True,
        force_fallback=args.force_fallback,
        input_format=args.format,
    )
    plan_summary = json.loads(DEFAULT_SUMMARY_PATH.read_text(encoding="utf-8"))
    if plan_summary.get("llm_used") is True:
        print("Planning mode: LLM (Ollama/Qwen)")
    else:
        print("Planning mode: Rule-based fallback")

    if not args.skip_eval:
        print("\n" + "=" * 62)
        print("  STEP 2 / 2  —  PLANNER EVALUATION")
        print("=" * 62)
        report = run_evaluation(
            ground_truth_path=args.dataset,
            report_path=args.report,
            force_fallback=True,
        )

        passed = report["passed_samples"]
        total = report["total_samples"]
        rate = report["pass_rate_pct"]
        print("\n" + "=" * 62)
        if passed == total:
            print(f"  ALL DONE  —  Planner quality: {passed}/{total} samples PASSED ({rate:.0f}%)")
        else:
            print(f"  DONE WITH WARNINGS  —  {passed}/{total} samples passed ({rate:.0f}%)")
        print("=" * 62 + "\n")
    else:
        print("\n" + "=" * 62)
        print("  ALL DONE  —  Evaluation skipped (--skip-eval)")
        print("=" * 62 + "\n")


if __name__ == "__main__":
    main()
