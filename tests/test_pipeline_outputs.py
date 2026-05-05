from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.pipelines.doc_to_tasks import run_doc_to_tasks_pipeline


PIPELINE_REQUIREMENTS = """\
Project Title:
Pipeline Test System

Main Features:
- Register users with email or phone
- Verify accounts using OTP
- Integrate with Stripe payment gateway
- Generate weekly revenue reports for admins
- Ensure API responses stay under 300ms under 100 concurrent users
"""

OPTIONAL_PIPELINE_REQUIREMENTS = """\
Project Title:
Optional Scope System

Main Features:
- Support ambulance tracking, maybe in a later phase
- Send SMS appointment reminders if possible
- Allow patients to book appointments online
"""

AMBIGUOUS_PIPELINE_REQUIREMENTS = """\
Project Title:
Ambiguous Scope System

Main Features:
- Users can manage their stuff
- Users can register with email
"""

TEMPLATE_REQUIREMENTS = """\
[REQ-01]
Type: Functional
Description: The system must allow reception staff to register new patients safely.
Actor: Receptionist
Priority: High
Notes: Prevent duplicate national ID records.

[REQ-02]
Type: Functional
Description: The system must let doctors review patient records before treatment.
Actor: Doctor
Priority: High
"""


def isolated_artifact_paths(root: Path) -> dict[str, Path]:
    processed = root / "processed"
    return {
        "review_queue_path": processed / "admin_review_queue.json",
        "review_decisions_path": processed / "admin_review_decisions.json",
        "final_tasks_path": processed / "tasks_final.json",
        "critic_report_path": processed / "critic_report.json",
        "risk_report_path": processed / "risk_report.json",
        "monitor_report_path": processed / "monitor_report.json",
    }


class PipelineOutputTests(unittest.TestCase):
    def test_plan_summary_contains_committee_ready_highlights(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "requirements.txt"
            output_path = root / "tasks.json"
            graph_path = root / "graph.json"
            summary_path = root / "summary.json"
            input_path.write_text(PIPELINE_REQUIREMENTS, encoding="utf-8")

            run_doc_to_tasks_pipeline(
                input_path=input_path,
                output_path=output_path,
                graph_path=graph_path,
                summary_path=summary_path,
                **isolated_artifact_paths(root),
                input_format="brief",
                allow_fallback=True,
                allow_decomposition=True,
                force_fallback=True,
            )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertIn("plan_highlights", summary)
            highlights = summary["plan_highlights"]
            self.assertTrue((root / "processed" / "critic_report.json").exists())
            self.assertTrue((root / "processed" / "risk_report.json").exists())
            self.assertIn("committee_brief", highlights)
            self.assertIn("coverage_by_requirement", highlights)
            self.assertIn("stage_summaries", highlights)
            self.assertIn("theme_breakdown", highlights)
            self.assertIn("sprint_plan", summary)
            self.assertIn("effort_summary", summary)
            self.assertIn("team_allocation", summary)
            self.assertIn("risk_register", summary)
            self.assertGreaterEqual(len(highlights["coverage_by_requirement"]), 5)
            self.assertIsInstance(highlights["committee_brief"], dict)
            self.assertIn("domain_inference", highlights["committee_brief"])
            self.assertIn("scope_assessment", highlights["committee_brief"])
            self.assertIn("ambiguity_register", highlights["committee_brief"])
            self.assertIn("assumption_log", highlights["committee_brief"])
            self.assertIn("confidence_signal", highlights["committee_brief"])
            self.assertIn("graph_summary", highlights["committee_brief"])
            self.assertTrue(highlights["committee_brief"]["graph_summary"])

            tasks = json.loads(output_path.read_text(encoding="utf-8"))["tasks"]
            self.assertGreater(len(tasks), 0)
            for task in tasks:
                self.assertIn("estimated_hours", task)
                self.assertIn("estimated_days", task)
                self.assertIn("recommended_team_size", task)
                self.assertIn("skill_required", task)
                self.assertIn("suggested_owner_role", task)
                self.assertIn("risks", task)

    def test_plan_summary_surfaces_optional_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "requirements.txt"
            output_path = root / "tasks.json"
            graph_path = root / "graph.json"
            summary_path = root / "summary.json"
            input_path.write_text(OPTIONAL_PIPELINE_REQUIREMENTS, encoding="utf-8")

            run_doc_to_tasks_pipeline(
                input_path=input_path,
                output_path=output_path,
                graph_path=graph_path,
                summary_path=summary_path,
                **isolated_artifact_paths(root),
                input_format="brief",
                allow_fallback=True,
                allow_decomposition=True,
                force_fallback=True,
            )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            graph_analytics = summary["graph_analytics"]
            optional_scope = summary["plan_highlights"]["optional_scope"]

            self.assertEqual(graph_analytics["optional_task_count"], 2)
            self.assertEqual(graph_analytics["confirmed_task_count"], 1)
            self.assertEqual(optional_scope["task_count"], 2)
            self.assertEqual(optional_scope["confirmed_task_count"], 1)

            tasks = json.loads(output_path.read_text(encoding="utf-8"))["tasks"]
            optional_tasks = [task for task in tasks if task["optional"]]
            self.assertEqual(len(optional_tasks), 2)
            self.assertTrue(all(task["confidence"] == "low" for task in optional_tasks))

    def test_ambiguity_register_populated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "requirements.txt"
            output_path = root / "tasks.json"
            graph_path = root / "graph.json"
            summary_path = root / "summary.json"
            input_path.write_text(AMBIGUOUS_PIPELINE_REQUIREMENTS, encoding="utf-8")

            run_doc_to_tasks_pipeline(
                input_path=input_path,
                output_path=output_path,
                graph_path=graph_path,
                summary_path=summary_path,
                **isolated_artifact_paths(root),
                input_format="brief",
                allow_fallback=True,
                allow_decomposition=True,
                force_fallback=True,
            )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            ambiguity_register = summary["plan_highlights"]["committee_brief"]["ambiguity_register"]

            self.assertTrue(ambiguity_register)
            self.assertIn("T001", {entry["task_id"] for entry in ambiguity_register})

    def test_fallback_warning_is_visible(self) -> None:
        class FailingLLMClient:
            def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
                raise ValueError("truncated json from llm")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "requirements.txt"
            output_path = root / "tasks.json"
            graph_path = root / "graph.json"
            summary_path = root / "summary.json"
            input_path.write_text(PIPELINE_REQUIREMENTS, encoding="utf-8")

            with patch("src.pipelines.doc_to_tasks.build_llm_client", return_value=FailingLLMClient()):
                run_doc_to_tasks_pipeline(
                    input_path=input_path,
                    output_path=output_path,
                    graph_path=graph_path,
                    summary_path=summary_path,
                    **isolated_artifact_paths(root),
                    allow_fallback=True,
                    allow_decomposition=True,
                )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertTrue(summary["used_fallback"])
            self.assertEqual(summary["generation_mode"], "rule_based_fallback_after_llm_failure")
            self.assertIn("fallback", summary["fallback_reason"].lower())
            self.assertIn("truncated json", summary["fallback_reason"].lower())

    def test_fast_demo_env_forces_rule_based_planning(self) -> None:
        class FailingLLMClient:
            def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
                raise AssertionError("LLM should not be called in fast demo mode")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "requirements.txt"
            output_path = root / "tasks.json"
            graph_path = root / "graph.json"
            summary_path = root / "summary.json"
            input_path.write_text(PIPELINE_REQUIREMENTS, encoding="utf-8")

            with (
                patch.dict("os.environ", {"CRITIPLAN_FORCE_FALLBACK": "1"}),
                patch("src.pipelines.doc_to_tasks.build_llm_client", return_value=FailingLLMClient()),
            ):
                run_doc_to_tasks_pipeline(
                    input_path=input_path,
                    output_path=output_path,
                    graph_path=graph_path,
                    summary_path=summary_path,
                    **isolated_artifact_paths(root),
                    allow_fallback=True,
                    allow_decomposition=True,
                )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertTrue(summary["used_fallback"])
            self.assertEqual(summary["generation_mode"], "rule_based_fallback_forced")

    def test_template_input_format_preserves_req_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "requirements_template.md"
            output_path = root / "tasks.json"
            graph_path = root / "graph.json"
            summary_path = root / "summary.json"
            input_path.write_text(TEMPLATE_REQUIREMENTS, encoding="utf-8")

            run_doc_to_tasks_pipeline(
                input_path=input_path,
                output_path=output_path,
                graph_path=graph_path,
                summary_path=summary_path,
                **isolated_artifact_paths(root),
                input_format="template",
                allow_fallback=True,
                allow_decomposition=True,
                force_fallback=True,
            )

            tasks = json.loads(output_path.read_text(encoding="utf-8"))["tasks"]
            self.assertGreater(len(tasks), 0)
            self.assertTrue(all(task["source"].startswith("REQ-") for task in tasks))

    def test_template_validation_failure_exits_pipeline(self) -> None:
        invalid_template = """\
[REQ-01]
Type: Maybe
Description: Too short indeed.
Priority: Urgent
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "requirements_template.md"
            input_path.write_text(invalid_template, encoding="utf-8")

            with self.assertRaises(SystemExit) as context:
                run_doc_to_tasks_pipeline(
                    input_path=input_path,
                    **isolated_artifact_paths(root),
                    input_format="template",
                    allow_fallback=True,
                    allow_decomposition=True,
                    force_fallback=True,
                )

            self.assertEqual(context.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
