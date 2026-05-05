from __future__ import annotations

import re
import unittest
from pathlib import Path

from src.agents.planner import PlannerAgent, RequirementItem
from src.core.schemas import Task, TaskList
from src.parsers.brief_parser import BriefParser
from src.services import BriefGenerator, SprintPlanner


class FakeLLMClient:
    def __init__(self, payload: dict):
        self.payload = payload

    def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
        return self.payload


class RecordingLLMClient:
    def __init__(self, payload: dict | None = None, *, error: Exception | None = None):
        self.payload = payload or {}
        self.error = error
        self.prompts: list[str] = []

    def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.payload


class SequencedLLMClient:
    def __init__(self, payloads: list[dict]):
        self.payloads = list(payloads)
        self.prompts: list[str] = []

    def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
        self.prompts.append(prompt)
        if not self.payloads:
            raise AssertionError("No payloads left in SequencedLLMClient")
        return self.payloads.pop(0)


class InvalidShapeLLMClient:
    def __init__(self, payload: dict):
        self.payload = payload

    def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
        return self.payload


class PlannerPromptTests(unittest.TestCase):
    def test_llm_prompt_contains_raw_text(self):
        raw = "we need registration and booking and maybe billing later"
        requirements = PlannerAgent._parse_requirements(
            "1. Users can register.\n2. Patients can book appointments.\n3. The system can support billing later."
        )

        prompt = PlannerAgent._build_prompt(
            raw_text=raw,
            requirements=requirements,
            allow_decomposition=True,
        )

        self.assertIn("Original student input:", prompt)
        self.assertIn(raw, prompt)
        self.assertIn(
            "If any requirement item is unclear or inconsistent with the original input, correct it. Do not invent requirements not implied by the original text.",
            prompt,
        )

    def test_build_prompt_includes_atomic_decomposition_hints(self):
        requirements = [
            RequirementItem(line_no=1, source="REQ-01", text="The system should Register and enroll in available courses."),
            RequirementItem(line_no=2, source="REQ-02", text="The system should Upload grades and course materials."),
        ]

        prompt = PlannerAgent._build_prompt(
            raw_text="brief",
            requirements=requirements,
            allow_decomposition=True,
        )

        self.assertIn("Atomic decomposition hints:", prompt)
        self.assertIn("Atomic line contract:", prompt)
        self.assertIn("Emit EXACTLY 3 task object(s)", prompt)
        self.assertIn('REQ-01: emit at least 2 task(s), all with source "REQ-01"', prompt)
        self.assertIn("The system should Register in available courses", prompt)
        self.assertIn("The system should enroll in available courses", prompt)
        self.assertNotIn('REQ-02: emit at least', prompt)

    def test_compact_prompt_includes_atomic_decomposition_hints(self):
        requirements = [
            RequirementItem(line_no=1, source="REQ-03", text="The system should Generate tuition invoices and process online payments."),
        ]

        prompt = PlannerAgent._build_compact_prompt(
            requirements=requirements,
            allow_decomposition=True,
        )

        self.assertIn("Atomic decomposition hints:", prompt)
        self.assertIn("Atomic line contract:", prompt)
        self.assertIn("Emit EXACTLY 2 task object(s)", prompt)
        self.assertIn('REQ-03: emit at least 2 task(s), all with source "REQ-03"', prompt)

    def test_llm_requirement_text_expands_atomic_fragments_with_repeated_sources(self):
        requirements = [
            RequirementItem(line_no=1, source="REQ-01", text="The system should Register and enroll in available courses."),
            RequirementItem(line_no=2, source="REQ-02", text="The system should Upload grades and course materials."),
        ]

        req_text = PlannerAgent._llm_requirement_text(
            requirements,
            allow_decomposition=True,
        )

        self.assertIn("[REQ-01] The system should Register in available courses", req_text)
        self.assertIn("[REQ-01] The system should enroll in available courses", req_text)
        self.assertIn("[REQ-02] The system should Upload grades and course materials", req_text)


class PlannerLlmPayloadRepairTests(unittest.TestCase):
    def test_normalizes_invalid_llm_task_fields_before_validation(self):
        planner = PlannerAgent(
            InvalidShapeLLMClient(
                {
                    "tasks": [
                        {
                            "id": "bad-id",
                            "title": "Implement registration workflow",
                            "description": "Users can register for an account.",
                            "req_type": "FR",
                            "calculated_complexity": 2,
                            "source": "FR",
                        },
                        {
                            "title": "Implement payment workflow",
                            "description": "Users can pay invoices online.",
                            "req_type": "FR",
                            "complexity": 4,
                            "dependencies": ["T001"],
                            "source": "???",
                        },
                    ]
                }
            )
        )

        result = planner.plan_from_requirements(
            "1. Users can register for an account.\n2. Users can pay invoices online.",
            allow_fallback=False,
            allow_decomposition=False,
        )

        self.assertEqual([task.id for task in result.tasks], ["T001", "T002"])
        self.assertEqual([task.source for task in result.tasks], ["line 1", "line 2"])
        self.assertEqual([task.complexity for task in result.tasks], [2, 2])

    def test_quality_check_rejects_under_decomposed_llm_output(self):
        planner = PlannerAgent(
            InvalidShapeLLMClient(
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Implement post management workflow",
                            "description": "Users can create, edit, and delete their posts.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": "line 1",
                        }
                    ]
                }
            )
        )

        with self.assertRaisesRegex(ValueError, "decomposition under-produced tasks"):
            planner.plan_from_requirements(
                "1. Users can create, edit, and delete their posts.",
                allow_fallback=False,
                allow_decomposition=True,
            )

    def test_near_miss_atomic_decomposition_is_supplemented(self):
        planner = PlannerAgent(
            InvalidShapeLLMClient(
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Implement tuition invoicing workflow",
                            "description": "The system should Generate tuition invoices and process online payments.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": "line 1",
                        }
                    ]
                }
            )
        )

        result = planner.plan_from_requirements(
            "1. The system should Generate tuition invoices and process online payments.",
            allow_fallback=False,
            allow_decomposition=True,
        )

        self.assertEqual(len(result.tasks), 2)
        self.assertEqual([task.source for task in result.tasks], ["line 1", "line 1"])
        self.assertIn("generate tuition invoices", result.tasks[0].description.lower())
        self.assertIn("process online payments", result.tasks[1].description.lower())

    def test_normalizes_duplicate_llm_task_ids_to_sequential_ids(self):
        planner = PlannerAgent(
            InvalidShapeLLMClient(
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Implement registration workflow",
                            "description": "Users can register for an account.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": "line 1",
                        },
                        {
                            "id": "T001",
                            "title": "Implement payment workflow",
                            "description": "Users can pay invoices online.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": ["T001"],
                            "source": "line 2",
                        },
                    ]
                }
            )
        )

        result = planner.plan_from_requirements(
            "1. Users can register for an account.\n2. Users can pay invoices online.",
            allow_fallback=False,
            allow_decomposition=False,
        )

        self.assertEqual([task.id for task in result.tasks], ["T001", "T002"])
        self.assertEqual(result.tasks[1].dependencies, ["T001"])

    def test_wrong_req_type_is_corrected_from_requirement_source(self):
        planner = PlannerAgent(
            InvalidShapeLLMClient(
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Optimize account registration latency",
                            "description": "Users can register for an account.",
                            "req_type": "NFR",
                            "complexity": 4,
                            "dependencies": [],
                            "source": "line 1",
                        }
                    ]
                }
            )
        )

        result = planner.plan_from_requirements(
            "1. Users can register for an account.",
            allow_fallback=False,
            allow_decomposition=False,
        )

        self.assertEqual(result.tasks[0].req_type, "FR")
        self.assertEqual(result.tasks[0].complexity, 2)

    def test_non_dict_llm_items_are_dropped_when_remaining_tasks_cover_layout(self):
        planner = PlannerAgent(
            InvalidShapeLLMClient(
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Implement registration workflow",
                            "description": "Users can register for an account.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": "line 1",
                        },
                        "title",
                        {
                            "id": "T002",
                            "title": "Implement authentication workflow",
                            "description": "Users can log in with email and password.",
                            "req_type": "FR",
                            "complexity": 3,
                            "dependencies": ["T001"],
                            "source": "line 2",
                        },
                    ]
                }
            )
        )

        result = planner.plan_from_requirements(
            "1. Users can register for an account.\n2. Users can log in with email and password.",
            allow_fallback=False,
            allow_decomposition=False,
        )

        self.assertEqual([task.id for task in result.tasks], ["T001", "T002"])
        self.assertEqual(result.tasks[1].dependencies, ["T001"])

    def test_aggressive_completion_only_applies_to_medium_repair_cases(self):
        self.assertFalse(
            PlannerAgent._should_align_llm_tasks_to_expected_layout(
                raw_count=3,
                expected_count=10,
                aggressive_completion=False,
            )
        )
        self.assertTrue(
            PlannerAgent._should_align_llm_tasks_to_expected_layout(
                raw_count=3,
                expected_count=10,
                aggressive_completion=True,
            )
        )
        self.assertFalse(
            PlannerAgent._should_align_llm_tasks_to_expected_layout(
                raw_count=4,
                expected_count=14,
                aggressive_completion=True,
            )
        )

    def test_multi_task_llm_plan_without_dependencies_uses_reference_skeleton(self):
        brief_text = Path("data/raw/docs/project_brief_lms.txt").read_text(encoding="utf-8")
        parsed_requirements = BriefParser().parse(brief_text)
        requirements_text = "\n".join(
            f"[{item.source}] {item.text}"
            for item in parsed_requirements
        )
        planner = PlannerAgent(
            InvalidShapeLLMClient(
                {
                    "tasks": [
                        {
                            "id": f"T{index:03d}",
                            "title": f"Implement placeholder workflow {index}",
                            "description": f"Placeholder task {index}.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": f"REQ-{index:02d}",
                        }
                        for index in range(1, 11)
                    ]
                }
            )
        )

        result = planner.plan_from_requirements(
            requirements_text,
            allow_fallback=False,
            allow_decomposition=True,
        )

        self.assertTrue(any(task.dependencies for task in result.tasks))

    def test_quality_check_flags_missing_dependency_chain_when_reference_plan_has_one(self):
        brief_text = Path("data/raw/docs/project_brief_iot_dashboard.txt").read_text(encoding="utf-8")
        requirements = [
            RequirementItem(
                line_no=item.line_no,
                source=item.source,
                text=item.text,
                sources=item.sources,
            )
            for item in BriefParser().parse(brief_text)
        ]
        planner = PlannerAgent(InvalidShapeLLMClient({"tasks": []}))
        task_list = TaskList(
            tasks=[
                Task(
                    id="T001",
                    title="Implement Sensor Data Ingestion Pipeline",
                    description="The system should ingest data from sensors.",
                    req_type="FR",
                    complexity=2,
                    dependencies=[],
                    source="REQ-01",
                ),
                Task(
                    id="T002",
                    title="Implement Real-Time Dashboard",
                    description="The system should provide a real-time dashboard.",
                    req_type="FR",
                    complexity=2,
                    dependencies=[],
                    source="REQ-02",
                ),
                Task(
                    id="T003",
                    title="Implement Alert Management System",
                    description="The system should trigger alerts based on thresholds.",
                    req_type="FR",
                    complexity=2,
                    dependencies=[],
                    source="REQ-03",
                ),
                Task(
                    id="T004",
                    title="Implement Historical Data Viewer",
                    description="The system should provide a historical data viewer.",
                    req_type="FR",
                    complexity=2,
                    dependencies=[],
                    source="REQ-04",
                ),
                Task(
                    id="T005",
                    title="Enforce Device Management Constraints",
                    description="The system should track firmware versions and device health.",
                    req_type="NFR",
                    complexity=3,
                    dependencies=[],
                    source="REQ-05",
                ),
                Task(
                    id="T006",
                    title="Implement Predictive Maintenance Module",
                    description="The system should support predictive maintenance workflows.",
                    req_type="FR",
                    complexity=2,
                    dependencies=[],
                    source="REQ-06",
                ),
                Task(
                    id="T007",
                    title="Implement Sensor Throughput Workflow",
                    description="The system should process at least 10,000 sensor readings per second.",
                    req_type="FR",
                    complexity=2,
                    dependencies=[],
                    source="REQ-07",
                ),
                Task(
                    id="T008",
                    title="Optimize Refresh Performance",
                    description="The dashboard should refresh in under 2 seconds.",
                    req_type="NFR",
                    complexity=4,
                    dependencies=[],
                    source="REQ-08",
                ),
                Task(
                    id="T009",
                    title="Implement Data Retention Policy",
                    description="The system should retain raw data for 90 days.",
                    req_type="FR",
                    complexity=2,
                    dependencies=[],
                    source="REQ-09",
                ),
                Task(
                    id="T010",
                    title="Enforce End-to-End Encryption",
                    description="Sensitive data should be encrypted in transit and at rest.",
                    req_type="NFR",
                    complexity=3,
                    dependencies=[],
                    source="REQ-10",
                ),
            ]
        )

        issues = planner._quality_issues(
            task_list=task_list,
            requirements=requirements,
            allow_decomposition=True,
        )

        self.assertIn("missing dependency chain: expected at least one dependency based on requirement structure", issues)

    def test_missing_inferred_dependencies_are_repaired(self):
        planner = PlannerAgent(
            InvalidShapeLLMClient(
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Implement account registration workflow",
                            "description": "Users can register for an account.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": "line 1",
                        },
                        {
                            "id": "T002",
                            "title": "Implement authentication workflow",
                            "description": "Users can log in with email and password.",
                            "req_type": "FR",
                            "complexity": 3,
                            "dependencies": [],
                            "source": "line 2",
                        },
                        {
                            "id": "T003",
                            "title": "Implement role management workflow",
                            "description": "Admins can manage user roles and permissions.",
                            "req_type": "FR",
                            "complexity": 4,
                            "dependencies": [],
                            "source": "line 3",
                        },
                    ]
                }
            )
        )

        result = planner.plan_from_requirements(
            "1. Users can register for an account.\n2. Users can log in with email and password.\n3. Admins can manage user roles and permissions.",
            allow_fallback=False,
            allow_decomposition=False,
        )

        self.assertEqual(result.tasks[1].dependencies, ["T001"])
        self.assertTrue(result.tasks[2].dependencies)

    def test_llm_corrects_parse_error(self):
        raw = "1. Patients can book appointments online and doctors can view patient records."
        llm = RecordingLLMClient(error=ValueError("mock llm failure"))
        planner = PlannerAgent(llm)

        planner.plan_from_requirements(
            raw,
            allow_fallback=True,
            allow_decomposition=True,
        )

        self.assertTrue(llm.prompts, "Expected the planning LLM prompt to be generated")
        prompt = llm.prompts[0]
        self.assertIn("Original student input:", prompt)
        self.assertIn(raw, prompt)
        self.assertIn("Requirements:", prompt)
        self.assertRegex(prompt, r"\[(?:line|block) \d+(?: clause \d+)?\]")

    def test_single_task_object_is_repaired_into_tasks_wrapper(self):
        raw = "1. Users can register with email."
        llm = SequencedLLMClient(
            [
                {
                    "id": "T001",
                    "title": "Implement email registration workflow",
                    "description": "Users can register with email.",
                    "req_type": "FR",
                    "complexity": 2,
                    "dependencies": [],
                    "source": "line 1",
                },
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Implement email registration workflow",
                            "description": "Users can register with email.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": "line 1",
                        }
                    ]
                },
            ]
        )
        planner = PlannerAgent(llm)

        result = planner.plan_from_requirements(
            raw,
            allow_fallback=True,
            allow_decomposition=False,
        )

        self.assertEqual(len(result.tasks), 1)
        self.assertEqual(result.tasks[0].id, "T001")
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("Wrap every task inside the top-level tasks array.", llm.prompts[1])

    def test_compact_retry_prompt_is_used_after_reasoning_failure(self):
        raw = "1. Users can register with email.\n2. Admins can view reports."
        llm = SequencedLLMClient(
            [
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Implement email registration workflow",
                            "description": "Users can register with email.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": "line 1",
                        },
                        {
                            "id": "T002",
                            "title": "Implement admin reporting workflow",
                            "description": "Admins can view reports.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": ["T001"],
                            "source": "line 2",
                        },
                    ]
                },
            ]
        )
        planner = PlannerAgent(llm)

        original_generate = llm.generate_json

        def _wrapped_generate(prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
            if len(llm.prompts) == 0:
                llm.prompts.append(prompt)
                raise ValueError(
                    "LLM response did not contain a valid JSON object. Response preview: Thinking Process:"
                )
            return original_generate(prompt, output_schema=output_schema, strict_json_only=strict_json_only)

        llm.prompts = []
        llm.generate_json = _wrapped_generate  # type: ignore[method-assign]

        result = planner.plan_from_requirements(
            raw,
            allow_fallback=True,
            allow_decomposition=False,
        )

        self.assertEqual(len(result.tasks), 2)
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("Compact retry. Return ONLY valid JSON", llm.prompts[1])
        self.assertFalse(planner.last_used_fallback)

    def test_quality_repair_prompt_is_used_after_under_decomposition_failure(self):
        raw = (
            "1. The system should Register and enroll in available courses.\n"
            "2. The system should Upload grades and course materials."
        )
        llm = SequencedLLMClient(
            [
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Implement course registration workflow",
                            "description": "The system should Register and enroll in available courses.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": "line 1",
                        }
                    ]
                },
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "title": "Implement course registration workflow",
                            "description": "The system should Register in available courses.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": [],
                            "source": "line 1",
                        },
                        {
                            "id": "T002",
                            "title": "Implement course enrollment workflow",
                            "description": "The system should enroll in available courses.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": ["T001"],
                            "source": "line 1",
                        },
                        {
                            "id": "T003",
                            "title": "Implement grade and materials upload workflow",
                            "description": "The system should Upload grades and course materials.",
                            "req_type": "FR",
                            "complexity": 2,
                            "dependencies": ["T001"],
                            "source": "line 2",
                        },
                    ]
                },
            ]
        )
        planner = PlannerAgent(llm)

        result = planner.plan_from_requirements(
            raw,
            allow_fallback=True,
            allow_decomposition=True,
        )

        self.assertEqual(len(result.tasks), 3)
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("Quality issues to fix:", llm.prompts[1])
        self.assertFalse(planner.last_used_fallback)


class BriefGeneratorSummaryTests(unittest.TestCase):
    def test_assumption_log_populated(self):
        from src.graph.dependency_graph import DependencyGraph

        requirements_text = """\
1. Admins can manage user accounts.
2. Doctors can view patient records.
3. Patients can book appointments.
4. The system should send SMS reminders if possible.
"""
        planner = PlannerAgent(FakeLLMClient(payload={}))
        task_list = planner.plan_from_requirements(
            requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        requirements = planner.last_prepared_requirements
        graph_stats = DependencyGraph(task_list).summary()
        sprint_plan = SprintPlanner.build_sprint_plan(task_list, graph_stats)

        brief = BriefGenerator.build(task_list, requirements, graph_stats, sprint_plan)
        assumption_log = brief["committee_brief"]["assumption_log"]

        self.assertTrue(assumption_log)


class PlannerDeduplicationTests(unittest.TestCase):
    def test_dedup_removes_identical_intent(self):
        items = [
            RequirementItem(
                line_no=1,
                source="line 1",
                text="The system must support user login functionality.",
            ),
            RequirementItem(
                line_no=2,
                source="line 2",
                text="The system should support user login functionality securely.",
            ),
        ]

        deduplicated = PlannerAgent.deduplicate_requirements(items)

        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0].source, "line 1")
        self.assertEqual(deduplicated[0].all_sources, ("line 1", "line 2"))
        self.assertIn("securely", deduplicated[0].text.lower())

    def test_dedup_preserves_distinct_requirements(self):
        items = [
            RequirementItem(
                line_no=1,
                source="line 1",
                text="Users can log in to the system.",
            ),
            RequirementItem(
                line_no=2,
                source="line 2",
                text="Admins can export audit reports.",
            ),
        ]

        deduplicated = PlannerAgent.deduplicate_requirements(items)

        self.assertEqual(len(deduplicated), 2)
        self.assertEqual(deduplicated[0].all_sources, ("line 1",))
        self.assertEqual(deduplicated[1].all_sources, ("line 2",))


# ---------------------------------------------------------------------------
# Generic requirements — intentionally domain-neutral
# ---------------------------------------------------------------------------
GENERIC_REQUIREMENTS = """\
1. Users can register using email or phone number.
2. After registration, users must verify their account via OTP.
3. The system supports multi-factor authentication for login.
4. Users can create, update, and delete their profile.
5. The system must support role-based access control: Admin and Member.
6. Admins can view, deactivate, and manage any user account.
7. The system must integrate with a third-party payment gateway.
8. All API responses must be under 300ms under 200 concurrent users.
9. The system must be GDPR compliant: users can request data deletion and export.
10. Users can view their activity history and generate reports.
"""

ECOMMERCE_REQUIREMENTS = """\
1. Customers can browse and search the product catalog.
2. Customers can add products to their shopping cart and update quantities.
3. Customers can place an order and choose a shipping method.
4. Customers can pay using credit card or PayPal via Stripe integration.
5. The system must send order confirmation and shipping notifications via email.
6. Admins can manage product listings: create, update, and deactivate products.
7. The system must process payments under 2 seconds under 500 concurrent checkouts.
8. The system must encrypt all payment data at rest using AES-256.
9. Admins can generate weekly sales reports and export them as CSV.
10. The system must support English and Arabic with RTL layout for Arabic.
"""

HEALTHCARE_REQUIREMENTS = """\
1. Users can register using email, phone number, national ID, Google OAuth, or Apple Sign-In.
2. Users must verify their account via a one-time code sent to their email or phone.
3. The system must support multi-factor authentication for login.
4. The system must enforce a secure password policy for all registered user accounts.
5. The system must support role-based access control with roles: Admin, Doctor, Receptionist, Lab Technician, and Patient.
6. Doctors can view patient records and add consultation notes.
7. Admins can manage user accounts: create, update, suspend, reactivate, or delete any account.
8. Patients can book and cancel appointments, and view upcoming appointments.
9. Receptionists can schedule appointments on behalf of patients, view patient profiles, and update booking records.
10. Lab technicians can upload test results and update patient records.
11. The system must integrate with external calendar services to sync appointment availability.
12. If an appointment conflict is detected, the system must notify patients via email and push notifications.
13. All patient data must be encrypted at rest and in transit.
14. The system must be GDPR compliant: users can request data deletion, data export, consent withdrawal, and access to their activity access log.
15. The system must support multiple languages including Arabic with RTL layout.
"""

TECHNICAL_PLANNER_REQUIREMENTS = """\
1. The system must accept project requirements in multiple formats, including plain text, structured documents, and PDF files, and extract meaningful information for further processing.
2. The system must automatically generate a structured list of tasks, where each task includes a unique ID, title, description, priority level, estimated complexity, and dependencies.
3. The system must construct a directed dependency graph between tasks, ensuring no circular dependencies and enabling identification of the critical path.
4. The system must estimate the time required for each task using a machine learning model, and provide confidence intervals for each estimation.
5. The system must classify tasks into categories such as frontend, backend, database, DevOps, and testing based on semantic understanding of the requirements.
6. The system must support iterative refinement of generated tasks by allowing feedback loops between the planner agent and critic agent.
7. The system must monitor a Git repository and analyze commit frequency, code changes, and contribution patterns to assess project progress.
8. The system must detect potential risks such as delays, bottlenecks, or underperformance, and generate alerts with explanations.
9. The system must provide explainability for all decisions, including task generation, time estimation, and risk prediction, using human-readable justifications.
10. The system must store task embeddings in a vector database to enable semantic search and retrieval of similar past tasks.
11. The system must maintain a graph database to represent task dependencies and support advanced queries such as critical path analysis and bottleneck detection.
12. The system must support a multi-agent architecture including Planner, Estimator, Monitor, and Critic agents, coordinated through a central orchestration engine.
13. The system must allow exporting generated tasks and reports in multiple formats, including JSON, CSV, and PDF.
14. The system must provide a user interface dashboard displaying task breakdown, dependency graphs, estimated timelines, and risk indicators.
15. The system must operate fully offline without reliance on external APIs or cloud services, using locally hosted language models.
16. The system must ensure all data processing and storage are performed securely, with local encryption mechanisms applied where applicable.
17. The system must handle incomplete or ambiguous requirements by generating assumptions and prompting for clarification when necessary.
18. The system must support scalability to handle projects with at least 200 tasks without significant performance degradation.
19. The system must maintain an execution log of all agent interactions, including inputs, outputs, and decision traces, for debugging and evaluation.
20. The system must provide evaluation metrics including task generation accuracy, dependency correctness, estimation error, and risk prediction performance.
"""

FOCUSED_PERFORMANCE_DIRECTION_REQUIREMENTS = """\
1. The system must automatically generate a structured list of tasks from project requirements.
2. The system must provide a dashboard showing generated task metrics and dependency summaries.
3. The system must allow exporting generated task reports as CSV.
4. The system must expose an API for project analytics and dependency queries.
5. The system must support scalability to handle projects with at least 200 tasks without significant performance degradation.
"""

ACCESS_DECISION_REQUIREMENTS = """\
1. Users can register using email.
2. Users must verify their account via OTP.
3. The system must support role-based access control with roles: Admin, Doctor, Lab Technician, and Patient.
4. Users can browse the product catalog.
5. Patients can book appointments.
6. Doctors can view patient records.
7. Lab technicians can upload test results.
8. The system must support GDPR data deletion requests.
9. The system must integrate with a third-party payment gateway.
10. Admins can generate weekly sales reports.
"""

ARTIFACT_DEPENDENCY_REQUIREMENTS = """\
1. Users can register using email.
2. The system must support role-based access control with roles: Doctor and Manager.
3. Staff can create patient records.
4. Staff can update patient records.
5. Doctors can view patient records.
6. The system must generate patient record summary reports.
7. The system must provide a dashboard showing patient record summaries.
8. The system must export patient record summaries as CSV.
"""

NFR_CONSTRAINT_REQUIREMENTS = """\
1. Users can sync appointments with external calendar services.
2. The system must store patient records and execution logs.
3. Doctors can view patient records.
4. The system must provide a dashboard showing patient activity analytics.
5. Users can browse the public help center.
6. The system must operate fully offline without reliance on external APIs or cloud services, using locally hosted language models.
7. The system must ensure all patient data and execution logs are processed and stored securely with local encryption mechanisms.
8. All API responses must stay under 300ms under 200 concurrent users.
9. The system must keep an audit trail for changes to patient records and billing entries.
10. Staff can update billing entries.
"""

OPTIONAL_SCOPE_REQUIREMENTS = """\
1. The system must support ambulance tracking, maybe in a later phase.
2. The system must send SMS appointment reminders if possible.
3. The system must support surgery scheduling as a future enhancement.
4. Patients can book appointments online.
"""

MIXED_OPTIONAL_CLAUSE_REQUIREMENTS = """\
1. Nurses can record patient vitals and nursing notes, maybe record administered medication for admitted patients, and maybe track patient follow-up during the shift.
"""

NURSING_MIXED_OPTIONAL_REQUIREMENTS = """\
1. For nurses, I think they need something different from doctors, like entering vitals, notes, maybe medication given to the patient if he is admitted, and maybe follow-up during the shift.
"""

REGISTRATION_MIXED_CERTAINTY_REQUIREMENTS = """\
1. Patients can register using national ID, but in some cases maybe passport, and maybe temporary data first in emergencies.
"""

COMPLEX_REGISTRATION_UNCERTAINTY_REQUIREMENTS = """\
1. First, there should be patient registration, and I think the patient can register using national number or something official, but in some cases maybe passport, and in emergency I don't think we can wait for full information because maybe the patient is unknown or in urgent condition, so maybe temporary data first and then complete later.
"""

REPORTING_MIXED_CERTAINTY_REQUIREMENTS = """\
1. The system must provide management reports for daily patients, admissions, and revenue. We are not sure if these reports are basic or advanced, but at least some dashboard or export would be useful.
"""

HOSPITAL_WORKFLOW_CHAIN_REQUIREMENTS = """\
1. Patients can register online.
2. Receptionists can create appointments for patients.
3. Doctors can record diagnosis and treatment plans.
4. Doctors can request laboratory tests.
5. Lab staff can collect samples and enter laboratory results.
6. Doctors can request radiology studies.
7. Radiology staff can upload radiology reports.
8. The system must return completed test results to the patient file.
9. Doctors can prescribe medications after reviewing completed test results.
10. Pharmacists can dispense prescribed medications.
11. The system must generate billing entries for completed medications and services.
12. The system must discharge admitted patients after billing completion.
13. The system must support Arabic and English.
"""

LAB_MIXED_CERTAINTY_REQUIREMENTS = """\
1. Lab module is needed because doctors request tests and then lab staff do sample collection and result entry. Maybe some tests are normal and some critical, so if the result is dangerous it should be highlighted or notify the doctor somehow. Also maybe a sample can be rejected if it is damaged or not enough, so status tracking may be needed from requested until completed.
"""

RADIOLOGY_MIXED_CERTAINTY_REQUIREMENTS = """\
1. Radiology also is needed like x-ray, CT maybe, ultrasound, things like that. The doctor requests it, then radiology department sees the request, schedules it if needed, then uploads report. We don't know if storing the actual image is needed or only the report, because full image storage may be too much, but maybe just attach a file or link.
"""

ACCESS_CONTROL_MIXED_CERTAINTY_REQUIREMENTS = """\
1. There should be different user roles, definitely admin, receptionist, doctor, nurse, pharmacist, lab staff, radiology staff, billing employee, maybe insurance employee too, and patient maybe as portal user if we have time. But access control is very important. Admin should manage users and permissions, but maybe not see everything medical unless hospital policy allows it.
"""


class PlannerStructuralTests(unittest.TestCase):
    """Tests that do not depend on any specific domain — pure structural validation."""

    def _run(self, requirements_text: str, decompose: bool = False) -> object:
        planner = PlannerAgent(FakeLLMClient(payload={}))
        return planner.plan_from_requirements(
            requirements_text,
            allow_fallback=True,
            allow_decomposition=decompose,
        )

    # --- Basic structural guarantees ---

    def test_sequential_ids(self):
        result = self._run(GENERIC_REQUIREMENTS)
        for idx, task in enumerate(result.tasks, start=1):
            self.assertEqual(task.id, f"T{idx:03d}", f"ID mismatch at position {idx}")

    def test_all_req_types_valid(self):
        result = self._run(GENERIC_REQUIREMENTS)
        for task in result.tasks:
            self.assertIn(task.req_type, {"FR", "NFR"}, f"{task.id} has invalid req_type")

    def test_complexity_in_range(self):
        result = self._run(GENERIC_REQUIREMENTS)
        for task in result.tasks:
            self.assertGreaterEqual(task.complexity, 1)
            self.assertLessEqual(task.complexity, 5)

    def test_all_titles_action_oriented(self):
        result = self._run(GENERIC_REQUIREMENTS)
        action_prefixes = {
            "Implement", "Build", "Design", "Configure", "Integrate",
            "Enforce", "Enable", "Optimize", "Automate", "Establish",
            "Validate", "Monitor",
        }
        for task in result.tasks:
            first_word = task.title.strip().split()[0]
            self.assertIn(first_word, action_prefixes, f"{task.id}: bad title: {task.title!r}")

    def test_no_self_dependencies(self):
        result = self._run(GENERIC_REQUIREMENTS)
        for task in result.tasks:
            self.assertNotIn(task.id, task.dependencies, f"{task.id} depends on itself")

    def test_no_forward_dependencies_except_late_nfr_constraints(self):
        result = self._run(GENERIC_REQUIREMENTS)
        id_to_index = {t.id: i for i, t in enumerate(result.tasks)}
        by_id = {t.id: t for t in result.tasks}
        for task in result.tasks:
            for dep in task.dependencies:
                dep_task = by_id[dep]
                dep_tags = PlannerAgent._extract_semantic_tags(dep_task.description)
                if dep_task.req_type == "NFR" and ({"security", "performance", "offline_operation", "compliance"} & dep_tags):
                    continue
                self.assertLess(
                    id_to_index[dep],
                    id_to_index[task.id],
                    f"{task.id} has forward dependency on {dep}",
                )

    def test_source_format_correct(self):
        result = self._run(GENERIC_REQUIREMENTS)
        import re
        for task in result.tasks:
            self.assertRegex(
                task.source,
                r"^(?:line \d+|block \d+(?: clause \d+)?|REQ-\d+)$",
                f"{task.id} has bad source: {task.source!r}",
            )

    def test_no_duplicate_ids(self):
        result = self._run(GENERIC_REQUIREMENTS)
        ids = [t.id for t in result.tasks]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate task IDs found")

    # --- 1:1 mapping without decomposition ---

    def test_one_to_one_mapping_no_decompose(self):
        result = self._run(GENERIC_REQUIREMENTS, decompose=False)
        lines = [l for l in GENERIC_REQUIREMENTS.strip().splitlines() if l.strip()]
        self.assertEqual(len(result.tasks), len(lines))

    # --- NFR classification ---

    def test_performance_classified_nfr(self):
        result = self._run(GENERIC_REQUIREMENTS)
        perf_tasks = [t for t in result.tasks if "300ms" in t.description or "concurrent" in t.description.lower()]
        for t in perf_tasks:
            self.assertEqual(t.req_type, "NFR", f"{t.id} should be NFR: {t.description!r}")

    def test_available_doctors_requirement_remains_fr(self):
        text = "The system should book and manage patient appointments for available doctors."
        self.assertEqual(PlannerAgent._classify_req_type(text), "FR")
        self.assertNotIn("performance", PlannerAgent._extract_semantic_tags(text))

    def test_available_doctors_title_is_not_reliability_title(self):
        text = "The system should book and manage patient appointments for available doctors."
        title = PlannerAgent._action_title_from_text(text, "FR")
        self.assertNotEqual(title, "Optimize system uptime and reliability constraints")

    def test_highly_available_system_remains_nfr(self):
        text = "The system must be highly available during clinic hours."
        self.assertEqual(PlannerAgent._classify_req_type(text), "NFR")
        self.assertIn("performance", PlannerAgent._extract_semantic_tags(text))

    def test_gdpr_actionable_rights_classified_fr(self):
        result = self._run(GENERIC_REQUIREMENTS)
        gdpr_tasks = [t for t in result.tasks if "gdpr" in t.description.lower() or "data deletion" in t.description.lower()]
        for t in gdpr_tasks:
            self.assertEqual(t.req_type, "FR", f"{t.id} should be FR")

    def test_internal_system_logging_classified_nfr(self):
        text = "The system must maintain an execution log of all agent interactions, including inputs, outputs, and decision traces."
        self.assertEqual(PlannerAgent._classify_req_type(text), "NFR")

    def test_internal_tracing_and_monitoring_classified_nfr(self):
        text = "The system must monitor agent execution traces and telemetry across the orchestration pipeline."
        self.assertEqual(PlannerAgent._classify_req_type(text), "NFR")

    def test_orchestrator_telemetry_classified_nfr(self):
        text = "The orchestrator must record telemetry and execution traces for agent workflows and internal pipeline health."
        self.assertEqual(PlannerAgent._classify_req_type(text), "NFR")

    def test_pipeline_internal_health_monitoring_classified_nfr(self):
        text = "The pipeline must monitor internal workflow health and runtime metrics for debugging and observability."
        self.assertEqual(PlannerAgent._classify_req_type(text), "NFR")

    def test_execution_engine_tracing_classified_nfr(self):
        text = "The execution engine must capture instrumentation traces for internal service workflows."
        self.assertEqual(PlannerAgent._classify_req_type(text), "NFR")

    def test_user_facing_audit_export_remains_fr(self):
        text = "Admins can export audit reports for compliance reviews."
        self.assertEqual(PlannerAgent._classify_req_type(text), "FR")

    def test_repository_monitoring_feature_remains_fr(self):
        text = "The system must monitor a Git repository and analyze commit frequency to assess project progress."
        self.assertEqual(PlannerAgent._classify_req_type(text), "FR")


class PlannerOptionalScopeTests(unittest.TestCase):
    def _run(self, requirements_text: str, decompose: bool = False) -> object:
        planner = PlannerAgent(FakeLLMClient(payload={}))
        return planner.plan_from_requirements(
            requirements_text,
            allow_fallback=True,
            allow_decomposition=decompose,
        )

    @classmethod
    def setUpClass(cls) -> None:
        planner = PlannerAgent(FakeLLMClient(payload={}))
        cls.result = planner.plan_from_requirements(
            OPTIONAL_SCOPE_REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=True,
        )
        cls.by_source = {task.source: task for task in cls.result.tasks}

    def test_requirement_with_maybe_becomes_optional_low_confidence(self):
        task = self.by_source["line 1"]
        self.assertTrue(task.optional)
        self.assertEqual(task.confidence, "low")

    def test_requirement_with_if_possible_becomes_optional_low_confidence(self):
        task = self.by_source["line 2"]
        self.assertTrue(task.optional)
        self.assertEqual(task.confidence, "low")

    def test_requirement_with_future_enhancement_becomes_optional_low_confidence(self):
        task = self.by_source["line 3"]
        self.assertTrue(task.optional)
        self.assertEqual(task.confidence, "low")

    def test_v2_hedge_marked_optional(self):
        result = self._run("1. Add social login in version 2.")
        task = result.tasks[0]
        self.assertTrue(task.optional)
        self.assertEqual(task.confidence, "low")

    def test_nice_to_have_marked_optional(self):
        result = self._run("1. It would be nice to have a dark mode.")
        task = result.tasks[0]
        self.assertTrue(task.optional)
        self.assertEqual(task.confidence, "low")

    def test_confirmed_requirement_remains_non_optional(self):
        task = self.by_source["line 4"]
        self.assertFalse(task.optional)
        self.assertEqual(task.confidence, "high")

    def test_optional_scope_is_surfaced_in_summary_outputs(self):
        from src.graph.dependency_graph import DependencyGraph

        summary = DependencyGraph(self.result).summary()
        optional_ids = {item["id"] for item in summary["low_confidence_tasks"]}
        self.assertEqual(summary["optional_task_count"], 3)
        self.assertEqual(summary["confirmed_task_count"], 1)
        self.assertEqual(optional_ids, {"T001", "T002", "T003"})

    def test_mixed_requirement_produces_confirmed_and_optional_tasks(self):
        result = self._run(NURSING_MIXED_OPTIONAL_REQUIREMENTS, decompose=True)
        confirmed = [
            task for task in result.tasks
            if not task.optional and task.confidence == "high"
        ]
        optional = [
            task for task in result.tasks
            if task.optional and task.confidence == "low"
        ]
        self.assertTrue(
            any("vitals" in task.description.lower() and "nursing notes" in task.description.lower() for task in confirmed),
            [task.description for task in confirmed],
        )
        self.assertTrue(
            any("administered medication" in task.description.lower() for task in optional),
            [task.description for task in optional],
        )
        self.assertTrue(
            any("follow-up" in task.description.lower() for task in optional),
            [task.description for task in optional],
        )

    def test_hedge_markers_do_not_leak_to_core_registration_clause(self):
        result = self._run(REGISTRATION_MIXED_CERTAINTY_REQUIREMENTS, decompose=True)
        self.assertEqual(len(result.tasks), 1)
        self.assertFalse(result.tasks[0].optional)
        self.assertEqual(result.tasks[0].confidence, "high")

    def test_complex_registration_core_task_stays_confirmed_despite_hedged_details(self):
        result = self._run(COMPLEX_REGISTRATION_UNCERTAINTY_REQUIREMENTS, decompose=True)
        registration = next(
            task for task in result.tasks
            if "registration" in task.title.lower()
        )
        self.assertFalse(registration.optional)
        self.assertEqual(registration.confidence, "high")

    def test_dashboard_reporting_clause_remains_confirmed_when_uncertainty_targets_depth(self):
        result = self._run(REPORTING_MIXED_CERTAINTY_REQUIREMENTS, decompose=True)
        self.assertTrue(result.tasks)
        self.assertTrue(all(not task.optional for task in result.tasks))
        self.assertTrue(all(task.confidence == "high" for task in result.tasks))

    def test_uncertainty_does_not_downgrade_core_laboratory_request_clause(self):
        result = self._run(LAB_MIXED_CERTAINTY_REQUIREMENTS, decompose=True)
        lab_request = next(
            task for task in result.tasks
            if "request laboratory tests" in task.description.lower()
        )
        self.assertFalse(lab_request.optional)
        self.assertEqual(lab_request.confidence, "high")

    def test_uncertainty_does_not_downgrade_core_radiology_request_clause(self):
        result = self._run(RADIOLOGY_MIXED_CERTAINTY_REQUIREMENTS, decompose=True)
        radiology_request = next(
            task for task in result.tasks
            if "request radiology studies" in task.description.lower()
        )
        attachment_support = next(
            task for task in result.tasks
            if "attachments or file links" in task.description.lower()
        )
        self.assertFalse(radiology_request.optional)
        self.assertEqual(radiology_request.confidence, "high")
        self.assertTrue(attachment_support.optional)
        self.assertEqual(attachment_support.confidence, "low")

    def test_uncertainty_does_not_leak_to_admin_user_management_clause(self):
        result = self._run(ACCESS_CONTROL_MIXED_CERTAINTY_REQUIREMENTS, decompose=True)
        user_management = next(
            task for task in result.tasks
            if "manage users and permissions" in task.description.lower()
        )
        self.assertFalse(user_management.optional)
        self.assertEqual(user_management.confidence, "high")

    def test_graph_validity_is_preserved_after_uncertainty_narrowing(self):
        from src.graph.dependency_graph import DependencyGraph

        graph = DependencyGraph(self.result)
        self.assertTrue(graph.summary()["is_valid_dag"])

    # --- Dependency layer semantics ---

    def test_auth_depends_on_identity(self):
        result = self._run(GENERIC_REQUIREMENTS)
        identity_task = next((t for t in result.tasks if t.source == "line 1"), None)
        auth_task = next((t for t in result.tasks if t.source == "line 2"), None)
        if identity_task and auth_task:
            self.assertIn(
                identity_task.id, auth_task.dependencies,
                f"{auth_task.id} should depend on identity task {identity_task.id}"
            )

    def test_rbac_depends_on_identity(self):
        result = self._run(GENERIC_REQUIREMENTS)
        rbac_task = next((t for t in result.tasks if t.source == "line 5"), None)
        identity_chain = [t for t in result.tasks if t.source in {"line 1", "line 2", "line 3"}]
        if rbac_task and identity_chain:
            self.assertTrue(
                any(task.id in rbac_task.dependencies for task in identity_chain),
                f"{rbac_task.id} should depend on an identity/auth prerequisite"
            )


class PlannerParsingTests(unittest.TestCase):
    def test_markdown_headings_and_bullets_are_parsed(self):
        text = """\
## Authentication
- Users can sign up with email.
- Users must verify their email via OTP.

## Billing
- The system must integrate with Stripe API.
"""
        parsed = PlannerAgent._parse_requirements(text)
        self.assertEqual(len(parsed), 3)
        self.assertIn("Users can sign up with email", parsed[0].text)
        self.assertIn("Users must verify their email via OTP", parsed[1].text)
        self.assertIn("integrate with Stripe API", parsed[2].text)

    def test_user_story_is_normalized(self):
        text = "As an admin, I want to approve expense claims, so that spending stays controlled."
        parsed = PlannerAgent._parse_requirements(text)
        self.assertEqual(len(parsed), 1)
        self.assertIn("Admin can approve expense claims", parsed[0].text)
        self.assertIn("so that spending stays controlled", parsed[0].text)

    def test_continuation_lines_are_merged(self):
        text = """\
1. The system must support document uploads
   with version history and audit logs.
2. Users can view uploaded documents.
"""
        parsed = PlannerAgent._parse_requirements(text)
        self.assertEqual(len(parsed), 2)
        self.assertIn("with version history and audit logs", parsed[0].text)

    def test_narrative_paragraph_is_segmented_into_semantic_block_clauses(self):
        text = (
            "Doctors should open the patient profile and see old visits. "
            "The doctor should write diagnosis and treatment plan. "
            "Also maybe the doctor can prescribe medicine directly and then pharmacy sees it."
        )
        parsed = PlannerAgent._parse_requirements(text)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0].source, "block 1 clause 1")
        self.assertEqual(parsed[1].source, "block 1 clause 2")
        self.assertEqual(parsed[2].source, "block 1 clause 3")

    def test_blank_lines_and_intro_filler_do_not_become_requirement_sources(self):
        text = """\
We need a hospital system for a graduation project, but not something very small.

Patients can register online.

"""
        parsed = PlannerAgent._parse_requirements(text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].source, "block 1")
        self.assertIn("Patients can register online", parsed[0].text)

    def test_related_sentences_within_block_preserve_semantic_unity(self):
        text = (
            "The system must support radiology requests. "
            "It would also be better if completed reports appear again in the same patient file."
        )
        parsed = PlannerAgent._parse_requirements(text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].source, "block 1")
        self.assertIn("radiology requests", parsed[0].text)
        self.assertIn("completed reports appear again", parsed[0].text)

    def test_downstream_planner_output_accepts_block_sources(self):
        from src.graph.dependency_graph import DependencyGraph

        planner = PlannerAgent(FakeLLMClient(payload={}))
        text = (
            "Doctors should open the patient profile and see old visits. "
            "The doctor should write diagnosis and treatment plan."
        )
        result = planner.plan_from_requirements(
            text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        self.assertTrue(result.tasks)
        self.assertTrue(all(task.source.startswith("block 1") for task in result.tasks))
        self.assertTrue(DependencyGraph(result).summary()["is_valid_dag"])


class PlannerEcommerceTests(unittest.TestCase):
    """Verify the planner produces sensible output for an e-commerce domain."""

    def setUp(self):
        self.planner = PlannerAgent(FakeLLMClient(payload={}))
        self.result = self.planner.plan_from_requirements(
            ECOMMERCE_REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=True,
        )

    def test_produces_tasks(self):
        self.assertGreater(len(self.result.tasks), 0)

    def test_payment_integration_classified_fr(self):
        payment_task = next(
            (t for t in self.result.tasks if "stripe" in t.description.lower() or "payment" in t.description.lower()),
            None,
        )
        self.assertIsNotNone(payment_task, "No payment task found")
        self.assertEqual(payment_task.req_type, "FR")

    def test_performance_task_classified_nfr(self):
        perf_task = next(
            (t for t in self.result.tasks if "2 seconds" in t.description or "concurrent" in t.description.lower()),
            None,
        )
        self.assertIsNotNone(perf_task, "No performance task found")
        self.assertEqual(perf_task.req_type, "NFR")

    def test_encryption_task_classified_nfr(self):
        enc_task = next(
            (t for t in self.result.tasks if "aes" in t.description.lower() or "encrypt" in t.description.lower()),
            None,
        )
        self.assertIsNotNone(enc_task, "No encryption task found")
        self.assertEqual(enc_task.req_type, "NFR")

    def test_integration_task_complexity_4(self):
        integration_task = next(
            (t for t in self.result.tasks if "stripe" in t.description.lower()),
            None,
        )
        if integration_task:
            self.assertEqual(integration_task.complexity, 4)

    def test_valid_dag(self):
        from src.graph.dependency_graph import DependencyGraph
        graph = DependencyGraph(self.result)
        self.assertEqual(graph.validate(), [], "Cycle detected in e-commerce plan DAG")

    def test_no_duplicate_ids(self):
        ids = [t.id for t in self.result.tasks]
        self.assertEqual(len(ids), len(set(ids)))


class PlannerDecompositionTests(unittest.TestCase):
    """Verify generic decomposition logic on arbitrary compound requirements."""

    def setUp(self):
        self.planner = PlannerAgent(FakeLLMClient(payload={}))

    def _decompose(self, text: str) -> list[str]:
        return PlannerAgent._decompose_requirement(text)

    def test_compound_user_actions_split(self):
        req = "Users can create, edit, and delete their posts."
        parts = self._decompose(req)
        self.assertGreater(len(parts), 1, "Compound requirement should be split")

    def test_simple_requirement_not_split(self):
        req = "Users can view their dashboard."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 1, "Simple requirement should not be split")

    def test_protected_compound_noun_not_split(self):
        req = "The system must notify both patient and doctor via email and push notification."
        parts = self._decompose(req)
        # Should split into at most 2-3 parts, not fragment compound noun "patient and doctor"
        for part in parts:
            self.assertNotIn("doctor.", part, "Should not terminate at 'doctor.'")

    def test_admin_compound_split(self):
        req = "Admins can create, update, and deactivate user accounts."
        parts = self._decompose(req)
        self.assertGreater(len(parts), 1)

    def test_colon_action_list_split(self):
        req = "Admins can manage product listings: create, update, and deactivate products."
        parts = self._decompose(req)
        self.assertGreater(len(parts), 1)
        self.assertTrue(any("create products" in part.lower() for part in parts))
        self.assertTrue(any("update products" in part.lower() for part in parts))
        self.assertTrue(any("deactivate products" in part.lower() for part in parts))

    def test_decomposition_preserves_subject(self):
        req = "Customers can place orders and track shipments."
        parts = self._decompose(req)
        for part in parts:
            self.assertRegex(part.lower(), r"^customers? can ", f"Missing subject in: {part!r}")

    def test_registration_channels_split(self):
        req = "Users can register using email, phone number, or Google OAuth."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 3)
        self.assertTrue(any("register using email" in part.lower() for part in parts))
        self.assertTrue(any("register using phone number" in part.lower() for part in parts))
        self.assertTrue(any("register using google oauth" in part.lower() for part in parts))

    def test_gdpr_rights_split(self):
        req = "The system must be GDPR compliant: users can request data deletion, export, or view access logs."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 3)
        self.assertTrue(any("gdpr data deletion" in part.lower() for part in parts))
        self.assertTrue(any("gdpr data export" in part.lower() for part in parts))
        self.assertTrue(any("access log" in part.lower() for part in parts))

    def test_conditional_notifications_split(self):
        req = "In case of appointment conflict, the system must notify both patient and doctor via email and push notification."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 3)
        self.assertTrue(any("detect appointment conflict" in part.lower() for part in parts))
        self.assertTrue(any("email notifications" in part.lower() for part in parts))
        self.assertTrue(any("push notifications" in part.lower() for part in parts))

    def test_receptionist_workflow_split(self):
        req = "Receptionists can create appointments on behalf of patients, mark patient arrival, and update appointment status."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 3)
        self.assertTrue(any("create appointments on behalf of patients" in part.lower() for part in parts))
        self.assertTrue(any("mark patient arrival" in part.lower() for part in parts))
        self.assertTrue(any("update appointment status" in part.lower() for part in parts))

    def test_lab_results_workflow_split(self):
        req = "Lab Technicians can upload lab results and mark results as verified."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 2)
        self.assertTrue(any("upload lab results" in part.lower() for part in parts))
        self.assertTrue(any("mark results as verified" in part.lower() for part in parts))

    def test_dual_encryption_controls_split(self):
        req = "All sensitive data must be encrypted at rest using AES-256 and encrypted in transit using TLS 1.3."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 2)
        self.assertTrue(any("encrypted at rest" in part.lower() for part in parts))
        self.assertTrue(any("encrypted in transit" in part.lower() for part in parts))

    def test_quality_attribute_requirement_decomposition(self):
        req = "The system must be highly available, encrypted, mobile-friendly, and responsive under peak load."
        parts = self._decompose(req)
        self.assertEqual(parts, [
            "The system must maintain high availability",
            "The system must encrypt sensitive data",
            "The system must support mobile-friendly interfaces",
            "The system must maintain responsive performance under peak load",
        ])

    def test_multi_concern_requirement_decomposition(self):
        req = "The system must handle patient registration, appointment scheduling, and billing workflows."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 3)
        self.assertTrue(any("handle patient registration" in part.lower() for part in parts))
        self.assertTrue(any("handle appointment scheduling" in part.lower() for part in parts))
        self.assertTrue(any("handle billing workflows" in part.lower() for part in parts))

    def test_multi_role_requirement_decomposition(self):
        req = "Doctors can approve admissions, and nurses can assign beds."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 2)
        self.assertTrue(any(part.lower().startswith("doctors can approve admissions") for part in parts))
        self.assertTrue(any(part.lower().startswith("nurses can assign beds") for part in parts))

    def test_multi_module_requirement_decomposition(self):
        req = "The system must support radiology, laboratory, and pharmacy modules."
        parts = self._decompose(req)
        self.assertEqual(len(parts), 3)
        self.assertTrue(any("support radiology modules" in part.lower() for part in parts))
        self.assertTrue(any("support laboratory modules" in part.lower() for part in parts))
        self.assertTrue(any("support pharmacy modules" in part.lower() for part in parts))

    def test_atomic_requirement_stays_atomic(self):
        req = "Patients can view their appointment history."
        parts = self._decompose(req)
        self.assertEqual(parts, ["Patients can view their appointment history"])

    def test_admissions_workflow_decomposes_into_task_grade_clauses(self):
        req = (
            "We also need admissions because some patients are not only visiting clinic and leaving, "
            "some stay in rooms or wards. So there should be rooms, beds, maybe ICU also if we can include it, "
            "and I think a bed should not be assigned to more than one patient at the same time obviously. "
            "Also if a patient moves from one room to another or from ward to ICU it should update. "
            "And when the patient leaves there should be discharge, but I think discharge is not only one click "
            "because maybe doctor approval is needed and maybe billing also should finish before final discharge."
        )
        parts = self._decompose(req)
        self.assertGreaterEqual(len(parts), 4)
        self.assertIn("The system must manage patient admissions and ward placement", parts)
        self.assertIn("The system must manage rooms, beds, and ICU capacity", parts)
        self.assertIn("The system must track patient bed transfers and room changes", parts)
        self.assertIn("The system must enforce discharge approval and billing completion", parts)

    def test_lab_workflow_decomposes_into_operational_phases(self):
        req = (
            "Lab module is needed because doctors request tests and then lab staff do sample collection and result entry. "
            "Maybe some tests are normal and some critical, so if the result is dangerous it should be highlighted or notify the doctor somehow. "
            "Also maybe a sample can be rejected if it is damaged or not enough, so status tracking may be needed from requested until completed."
        )
        parts = self._decompose(req)
        self.assertGreaterEqual(len(parts), 4)
        self.assertIn("Doctors can request laboratory tests", parts)
        self.assertIn("Lab staff can collect samples and enter laboratory results", parts)
        self.assertIn("The system must track laboratory sample status from request to completion", parts)
        self.assertIn("The system must notify doctors about critical laboratory results", parts)

    def test_radiology_workflow_decomposes_into_task_grade_clauses(self):
        req = (
            "Radiology also is needed like x-ray, CT maybe, ultrasound. The doctor requests it, then radiology department "
            "sees the request, schedules it if needed, then uploads report. Maybe just attach a file or link. "
            "Also there are urgent cases, so not all requests have same priority."
        )
        parts = self._decompose(req)
        self.assertGreaterEqual(len(parts), 4)
        self.assertIn("Doctors can request radiology studies", parts)
        self.assertIn("Radiology staff can schedule radiology requests", parts)
        self.assertIn("Radiology staff can upload radiology reports", parts)
        self.assertIn("The system must prioritize urgent radiology requests", parts)

    def test_billing_and_insurance_workflow_decomposes_cleanly(self):
        req = (
            "Billing is important because every service in the hospital should probably cost something. "
            "Every department action that is billable should somehow reflect in billing. "
            "Some patients have insurance so not all amount is paid by patient. "
            "Maybe insurance covers some services and not others, and sometimes approval is needed before certain expensive service. "
            "Still, the system should support insurance information, coverage, and maybe claim status or approval status."
        )
        parts = self._decompose(req)
        self.assertEqual(len(parts), 3)
        self.assertIn("The system must generate billing entries for billable hospital services", parts)
        self.assertIn("The system must support insurance coverage and claim approval status", parts)
        self.assertIn("The system must calculate patient balances for insured and non-insured patients", parts)

    def test_prevents_bad_fragment_emission_for_support_and_reporting_mix(self):
        req = (
            "The system should support Arabic and English because hospitals here may need both. "
            "Also it should be secure and keep logs for important changes because if diagnosis or bill or prescription changed "
            "we may need to know who changed it. We also want reports for management like number of daily patients, admissions, "
            "free beds, revenue, unpaid bills, maybe top requested lab tests or most used services. "
            "We are not sure if these reports are basic or advanced, but at least some dashboard or export would be useful."
        )
        parts = self._decompose(req)
        self.assertEqual(parts, [
            "The system must support Arabic and English",
            "The system must secure hospital data",
            "The system must keep audit logs for important changes",
            "The system must provide management reports and dashboard exports",
        ])
        for part in parts:
            self.assertNotRegex(part.lower(), r"^(?:for nurses|also there|another point is|one important thing is)\b")
            self.assertNotIn("advanced", part.lower())

    def test_rejects_narrative_scoping_requirement(self):
        req = (
            "In general we want one integrated hospital management system with registration, appointments, EMR, admissions, lab, "
            "radiology, pharmacy, billing, insurance, reporting, roles, and security, with a realistic workflow and enough detail "
            "to be convincing as a graduation project."
        )
        parts = self._decompose(req)
        self.assertEqual(parts, [])

    def test_rejects_meta_workflow_commentary_requirement(self):
        req = (
            "One important thing is the workflow should make sense, not just separate pages. For example patient registers, then books "
            "or goes to emergency, then doctor sees him, then maybe orders tests, then results return, then prescription goes to pharmacy."
        )
        parts = self._decompose(req)
        self.assertEqual(parts, [])

    def test_role_access_control_decomposes_without_billing_carryover(self):
        req = (
            "There should be different user roles, definitely admin, receptionist, doctor, nurse, pharmacist, lab staff, radiology staff, "
            "billing employee, maybe insurance employee too, and patient maybe as portal user if we have time. But access control is very "
            "important because receptionist should not edit diagnosis, pharmacist should not change lab results, and patient if he logs in later "
            "should not see internal notes maybe only appointments, results, or prescriptions. Admin should manage users and permissions, but "
            "maybe not see everything medical unless hospital policy allows it, so roles may not be simple."
        )
        parts = self._decompose(req)
        self.assertIn("The system must support hospital role-based access control", parts)
        self.assertIn("Admins can manage users and permissions under hospital policy", parts)
        self.assertIn("The system must restrict receptionists from editing diagnoses", parts)
        self.assertIn("The system must restrict pharmacists from changing laboratory results", parts)
        self.assertIn("Patients can view appointments, results, and prescriptions without internal notes", parts)
        self.assertFalse(any("billing entries" in part.lower() for part in parts))
        self.assertFalse(any("claim approval status" in part.lower() for part in parts))

    def test_plan_skips_narrative_lines_without_leaking_wrong_domain_templates(self):
        requirements = """\
1. In general we want one integrated hospital management system with registration, appointments, EMR, admissions, lab, radiology, pharmacy, billing, insurance, reporting, roles, and security, with a realistic workflow and enough detail to be convincing as a graduation project.
2. There should be different user roles, definitely admin, receptionist, doctor, nurse, pharmacist, lab staff, radiology staff, billing employee, maybe insurance employee too, and patient maybe as portal user if we have time. But access control is very important because receptionist should not edit diagnosis, pharmacist should not change lab results, and patient if he logs in later should not see internal notes maybe only appointments, results, or prescriptions. Admin should manage users and permissions, but maybe not see everything medical unless hospital policy allows it, so roles may not be simple.
3. Billing is important because every service in the hospital should probably cost something. Every department action that is billable should somehow reflect in billing. Some patients have insurance so not all amount is paid by patient. Maybe insurance covers some services and not others, and sometimes approval is needed before certain expensive service. Still, the system should support insurance information, coverage, and maybe claim status or approval status.
"""
        result = self.planner.plan_from_requirements(
            requirements,
            allow_fallback=True,
            allow_decomposition=True,
        )
        line_1_tasks = [task for task in result.tasks if task.source == "line 1"]
        line_2_tasks = [task for task in result.tasks if task.source == "line 2"]
        line_3_tasks = [task for task in result.tasks if task.source == "line 3"]

        self.assertEqual(line_1_tasks, [])
        self.assertTrue(any("role-based access control" in task.title.lower() for task in line_2_tasks))
        self.assertFalse(any("billing entries" in task.title.lower() for task in line_2_tasks))
        self.assertTrue(any("billing entries" in task.title.lower() for task in line_3_tasks))
        self.assertTrue(any("claim approval status" in task.title.lower() for task in line_3_tasks))


class PlannerClassificationTests(unittest.TestCase):
    """Unit tests for req_type and complexity classifiers — domain-agnostic."""

    def test_performance_is_nfr(self):
        self.assertEqual(PlannerAgent._classify_req_type("API response must be under 200ms"), "NFR")

    def test_colloquial_performance_classified_as_nfr(self):
        text = "the app should be fast and have no lag"
        self.assertEqual(PlannerAgent._classify_req_type(text), "NFR")
        self.assertIn("performance", PlannerAgent._extract_semantic_tags(text))

    def test_security_is_nfr(self):
        self.assertEqual(PlannerAgent._classify_req_type("All data must be encrypted at rest using AES-256"), "NFR")

    def test_gdpr_is_nfr(self):
        self.assertEqual(PlannerAgent._classify_req_type("The system must be GDPR compliant"), "NFR")

    def test_gdpr_rights_are_fr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("The system must support GDPR data deletion requests"),
            "FR",
        )

    def test_feature_is_fr(self):
        self.assertEqual(PlannerAgent._classify_req_type("Users can upload profile pictures"), "FR")

    def test_user_enable_2fa_is_fr(self):
        self.assertEqual(PlannerAgent._classify_req_type("Users can enable 2FA for their account"), "FR")

    def test_add_to_cart_under_peak_load_remains_fr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type(
                "Customers can add products to their shopping cart under peak load."
            ),
            "FR",
        )

    def test_browse_search_with_mobile_context_remains_fr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type(
                "Customers can browse and search the product catalog from mobile devices."
            ),
            "FR",
        )

    def test_choose_shipping_method_under_peak_load_remains_fr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type(
                "Customers can choose a shipping method under peak load."
            ),
            "FR",
        )

    def test_appointment_availability_is_fr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("The system must support appointment availability across clinics"),
            "FR",
        )

    def test_doctor_availability_is_fr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("The system must show doctor availability before booking"),
            "FR",
        )

    def test_slot_schedule_availability_is_fr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("Doctors can see slot availability before scheduling follow-up visits"),
            "FR",
        )

    def test_room_bed_availability_is_fr_in_hospital_context(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("The system must manage room and bed availability for admissions"),
            "FR",
        )

    def test_system_service_uptime_availability_remains_nfr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("The platform must maintain API availability and service uptime during peak load"),
            "NFR",
        )

    def test_availability_phrase_classified_as_nfr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("the system should always be available"),
            "NFR",
        )

    def test_mobile_desktop_browser_support_is_nfr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("The app must work on mobile and desktop browsers."),
            "NFR",
        )

    def test_idempotent_billing_operations_are_nfr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("Billing operations must be idempotent to prevent double-charges on retries."),
            "NFR",
        )

    def test_adaptive_bitrate_streaming_is_nfr(self):
        self.assertEqual(
            PlannerAgent._classify_req_type("Video streaming must adapt to bandwidth (adaptive bitrate, 360p-1080p)."),
            "NFR",
        )

    def test_integration_complexity_4(self):
        self.assertEqual(PlannerAgent._score_complexity("Integrate with Stripe payment gateway", "FR"), 4)

    def test_read_only_complexity_1(self):
        self.assertEqual(PlannerAgent._score_complexity("Users can view their order history", "FR"), 1)

    def test_simple_crud_complexity_2(self):
        self.assertEqual(PlannerAgent._score_complexity("Users can create a new project", "FR"), 2)

    def test_auth_complexity_3(self):
        self.assertEqual(PlannerAgent._score_complexity("Users must verify their email via OTP", "FR"), 3)

    def test_rbac_complexity_4(self):
        self.assertEqual(PlannerAgent._score_complexity("System must support role-based access control", "FR"), 4)

    def test_performance_complexity_4(self):
        self.assertEqual(PlannerAgent._score_complexity("Latency must be under 500ms for 100 concurrent users", "NFR"), 4)

    def test_password_policy_title(self):
        title = PlannerAgent._action_title_from_text(
            "Passwords must be hashed with bcrypt + salted, and must meet complexity rules.",
            "NFR",
        )
        self.assertEqual(title, "Enforce password hashing and complexity policy")

    def test_generic_encryption_title(self):
        title = PlannerAgent._action_title_from_text(
            "The system must encrypt sensitive data.",
            "NFR",
        )
        self.assertEqual(title, "Enforce sensitive data encryption controls")

    def test_encryption_title(self):
        title = PlannerAgent._action_title_from_text(
            "All sensitive data must be encrypted at rest using AES-256.",
            "NFR",
        )
        self.assertEqual(title, "Enforce encryption at rest for sensitive data")

    def test_mobile_friendly_title(self):
        title = PlannerAgent._action_title_from_text(
            "The system must support mobile-friendly interfaces.",
            "NFR",
        )
        self.assertEqual(title, "Enable mobile-friendly interface support")

    def test_mobile_desktop_browser_compatibility_title(self):
        title = PlannerAgent._action_title_from_text(
            "The app must work on mobile and desktop browsers.",
            "NFR",
        )
        self.assertEqual(title, "Enable mobile and desktop browser compatibility")

    def test_idempotent_billing_title(self):
        title = PlannerAgent._action_title_from_text(
            "Billing operations must be idempotent to prevent double-charges on retries.",
            "NFR",
        )
        self.assertEqual(title, "Enforce idempotent billing operations")

    def test_adaptive_bitrate_title(self):
        title = PlannerAgent._action_title_from_text(
            "Video streaming must adapt to bandwidth (adaptive bitrate, 360p-1080p).",
            "NFR",
        )
        self.assertEqual(title, "Optimize adaptive video streaming quality")

    def test_peak_load_responsiveness_title(self):
        title = PlannerAgent._action_title_from_text(
            "The system must maintain responsive performance under peak load.",
            "NFR",
        )
        self.assertEqual(title, "Optimize peak-load responsiveness and capacity")

    def test_performance_title(self):
        title = PlannerAgent._action_title_from_text(
            "All API responses must be under 500ms latency under 100 concurrent users.",
            "NFR",
        )
        self.assertEqual(title, "Optimize API latency and concurrency performance")

    def test_registration_and_enrollment_title(self):
        title = PlannerAgent._action_title_from_text(
            "The system should Register and enroll in available courses.",
            "FR",
        )
        self.assertEqual(title, "Implement student registration and course enrollment workflow")

    def test_course_registration_title(self):
        title = PlannerAgent._action_title_from_text(
            "The system should Register in available courses.",
            "FR",
        )
        self.assertEqual(title, "Implement course registration workflow")

    def test_course_enrollment_title(self):
        title = PlannerAgent._action_title_from_text(
            "The system should enroll in available courses.",
            "FR",
        )
        self.assertEqual(title, "Implement course enrollment workflow")

    def test_reporting_title(self):
        title = PlannerAgent._action_title_from_text(
            "The system must generate weekly reports for admins showing sales and churn.",
            "FR",
        )
        self.assertEqual(title, "Implement weekly admin reporting workflow")

    def test_notification_title(self):
        title = PlannerAgent._action_title_from_text(
            "In case of appointment conflict, the system must notify both patient and doctor via email and push notification.",
            "FR",
        )
        self.assertEqual(title, "Implement appointment conflict notifications workflow")

    def test_calendar_integration_title(self):
        title = PlannerAgent._action_title_from_text(
            "The system must integrate with Google Calendar and Outlook Calendar to synchronize appointment schedules and updates.",
            "FR",
        )
        self.assertEqual(title, "Integrate Google Calendar and Outlook Calendar")
        self.assertNotIn("workflow", title.lower())

    def test_external_calendar_services_title_is_trimmed(self):
        title = PlannerAgent._action_title_from_text(
            "The system must integrate with external calendar services to sync appointment availability.",
            "FR",
        )
        self.assertEqual(title, "Integrate external calendar services")

    def test_shipping_api_providers_title_is_trimmed(self):
        title = PlannerAgent._action_title_from_text(
            "The system must integrate with shipping API providers for rate calculation.",
            "FR",
        )
        self.assertEqual(title, "Integrate shipping API providers")

    def test_microsoft_teams_and_slack_title_is_preserved(self):
        title = PlannerAgent._action_title_from_text(
            "The system must integrate with Microsoft Teams and Slack.",
            "FR",
        )
        self.assertEqual(title, "Integrate Microsoft Teams and Slack")

    def test_user_account_lifecycle_title(self):
        title = PlannerAgent._action_title_from_text(
            "Admins can create, update, suspend, reactivate, and permanently delete user accounts.",
            "FR",
        )
        self.assertEqual(title, "Implement user account lifecycle management")

    def test_storage_title_uses_pipeline_noun(self):
        title = PlannerAgent._action_title_from_text(
            "The system must store task embeddings in a vector database to enable semantic search and retrieval of similar past tasks.",
            "FR",
        )
        self.assertEqual(title, "Implement task embedding storage and retrieval pipeline")
        self.assertNotIn("workflow", title.lower())

    def test_monitoring_title_uses_monitor_noun(self):
        title = PlannerAgent._action_title_from_text(
            "The system must monitor a Git repository and analyze commit frequency, code changes, and contribution patterns to assess project progress.",
            "FR",
        )
        self.assertEqual(title, "Implement Git repository progress monitor")
        self.assertNotIn("workflow", title.lower())

    def test_orchestration_title_uses_orchestration_layer(self):
        title = PlannerAgent._action_title_from_text(
            "The system must support a multi-agent architecture including Planner, Estimator, Monitor, and Critic agents, coordinated through a central orchestration engine.",
            "FR",
        )
        self.assertEqual(title, "Implement multi-agent orchestration layer")
        self.assertNotIn("workflow", title.lower())

    def test_dashboard_title_uses_dashboard_noun(self):
        title = PlannerAgent._action_title_from_text(
            "The system must provide a user interface dashboard displaying task breakdown, dependency graphs, estimated timelines, and risk indicators.",
            "FR",
        )
        self.assertEqual(title, "Implement project planning dashboard")
        self.assertNotIn("workflow", title.lower())

    def test_export_title_uses_export_service(self):
        title = PlannerAgent._action_title_from_text(
            "The system must allow exporting generated tasks and reports in multiple formats, including JSON, CSV, and PDF.",
            "FR",
        )
        self.assertEqual(title, "Implement task and report export service")
        self.assertNotIn("workflow", title.lower())

    def test_validation_title_uses_validation_service(self):
        title = PlannerAgent._action_title_from_text(
            "The system must handle incomplete or ambiguous requirements by generating assumptions and prompting for clarification when necessary.",
            "FR",
        )
        self.assertEqual(title, "Implement ambiguous requirements validation service")
        self.assertNotIn("workflow", title.lower())

    def test_generic_workflow_titles_remain_available_as_fallback(self):
        title = PlannerAgent._action_title_from_text(
            "Patients can book appointments online.",
            "FR",
        )
        self.assertEqual(title, "Implement appointments online booking workflow")
        self.assertIn("workflow", title.lower())

    def test_vague_object_produces_unclear_title(self):
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            "1. Users can manage their stuff.",
            allow_fallback=True,
            allow_decomposition=False,
        )
        task = result.tasks[0]
        self.assertIn("UNCLEAR", task.title)
        self.assertEqual(task.confidence, "low")

    def test_specific_object_produces_clean_title(self):
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            "1. Users can manage their appointments.",
            allow_fallback=True,
            allow_decomposition=False,
        )
        task = result.tasks[0]
        self.assertNotIn("UNCLEAR", task.title)


class PlannerIntegrationFocusTests(unittest.TestCase):
    def test_external_calendar_services_focus_is_concise(self):
        focus = PlannerAgent._extract_integration_focus(
            "The system must integrate with external calendar services to sync appointment availability."
        )
        self.assertEqual(focus, "external calendar services")

    def test_shipping_api_providers_focus_is_concise(self):
        focus = PlannerAgent._extract_integration_focus(
            "The system must integrate with shipping API providers for rate calculation."
        )
        self.assertEqual(focus, "shipping API providers")

    def test_external_identity_service_beats_bare_sso(self):
        focus = PlannerAgent._extract_integration_focus(
            "The system must integrate with external identity service for SSO."
        )
        self.assertEqual(focus, "external identity service")

    def test_third_party_payment_gateway_stays_concise(self):
        focus = PlannerAgent._extract_integration_focus(
            "The system must integrate with a third-party payment gateway."
        )
        self.assertEqual(focus, "third-party payment gateway")

    def test_google_and_outlook_calendar_are_preserved(self):
        focus = PlannerAgent._extract_integration_focus(
            "The system must integrate with Google Calendar and Outlook Calendar to synchronize appointment schedules and updates."
        )
        self.assertEqual(focus, "Google Calendar and Outlook Calendar")

    def test_stripe_api_is_preserved(self):
        focus = PlannerAgent._extract_integration_focus(
            "The system must integrate with Stripe API."
        )
        self.assertEqual(focus, "Stripe API")

    def test_microsoft_teams_and_slack_are_preserved(self):
        focus = PlannerAgent._extract_integration_focus(
            "The system must integrate with Microsoft Teams and Slack."
        )
        self.assertEqual(focus, "Microsoft Teams and Slack")

    def test_warehouse_management_system_is_not_over_shortened(self):
        focus = PlannerAgent._extract_integration_focus(
            "The system must integrate with third-party warehouse management system."
        )
        self.assertEqual(focus, "third-party warehouse management system")


class PlannerSemanticTagTests(unittest.TestCase):
    """Verify semantic tag extraction across different domains."""

    def test_identity_tag(self):
        tags = PlannerAgent._extract_semantic_tags("Users can register using email.")
        self.assertIn("identity", tags)

    def test_auth_tag(self):
        tags = PlannerAgent._extract_semantic_tags("Users must verify via OTP after login.")
        self.assertIn("auth", tags)

    def test_access_control_tag(self):
        tags = PlannerAgent._extract_semantic_tags("System must support role-based access control.")
        self.assertIn("access_control", tags)

    def test_integration_tag(self):
        tags = PlannerAgent._extract_semantic_tags("Integrate with third-party payment gateway.")
        self.assertIn("integration", tags)

    def test_notification_tag(self):
        tags = PlannerAgent._extract_semantic_tags("System must notify users via email and push.")
        self.assertIn("notification", tags)

    def test_reporting_tag(self):
        tags = PlannerAgent._extract_semantic_tags("Admins can generate weekly sales reports.")
        self.assertIn("reporting", tags)

    def test_compliance_tag(self):
        tags = PlannerAgent._extract_semantic_tags("System must be GDPR compliant.")
        self.assertIn("compliance", tags)

    def test_performance_tag(self):
        tags = PlannerAgent._extract_semantic_tags("API latency must be under 200ms.")
        self.assertIn("performance", tags)

    def test_unknown_falls_back_to_general(self):
        tags = PlannerAgent._extract_semantic_tags("The sky is blue.")
        self.assertIn("general", tags)


class PlannerHealthcareCompatibilityTests(unittest.TestCase):
    """Confirm the original healthcare requirements still produce a valid plan."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.requirements_text = HEALTHCARE_REQUIREMENTS

    def test_healthcare_plan_is_valid_dag(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        from src.graph.dependency_graph import DependencyGraph
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        graph = DependencyGraph(result)
        self.assertEqual(graph.validate(), [], "Cycle detected in healthcare plan")

    def test_healthcare_plan_has_tasks(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        self.assertGreater(len(result.tasks), 0)

    def test_healthcare_rbac_is_bottleneck(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        from src.graph.dependency_graph import DependencyGraph
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        graph = DependencyGraph(result)
        bottleneck = graph.bottleneck_tasks(top_n=1)[0]
        self.assertGreater(bottleneck["blocks"], 5, "RBAC should be a major bottleneck")

    def test_cancellation_depends_on_booking(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        booking = next((t for t in result.tasks if "book appointments" in t.description.lower()), None)
        cancellation = next((t for t in result.tasks if "cancel" in t.description.lower()), None)
        self.assertIsNotNone(booking)
        self.assertIsNotNone(cancellation)
        self.assertIn(booking.id, cancellation.dependencies)

    def test_upcoming_appointments_view_depends_on_booking(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        booking = next((t for t in result.tasks if "book appointments" in t.description.lower()), None)
        upcoming_view = next(
            (t for t in result.tasks if "view upcoming" in t.description.lower()),
            None,
        )
        self.assertIsNotNone(booking)
        self.assertIsNotNone(upcoming_view)
        self.assertIn(booking.id, upcoming_view.dependencies)

    def test_conflict_detection_depends_on_calendar_integration(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        # Calendar integration is line 11 in the current requirements
        integration = next((t for t in result.tasks if t.source == "line 11"), None)
        detection = next(
            (t for t in result.tasks if "detect appointment conflict" in t.description.lower()),
            None,
        )
        self.assertIsNotNone(integration)
        self.assertIsNotNone(detection)
        self.assertIn(integration.id, detection.dependencies)

    def test_conflict_notification_channels_depend_on_detection(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        detection = next(
            (t for t in result.tasks if "detect appointment conflict" in t.description.lower()),
            None,
        )
        email_task = next(
            (t for t in result.tasks if "email notifications" in t.description.lower()),
            None,
        )
        push_task = next(
            (t for t in result.tasks if "push notifications" in t.description.lower()),
            None,
        )
        self.assertIsNotNone(detection)
        self.assertIsNotNone(email_task)
        self.assertIsNotNone(push_task)
        self.assertIn(detection.id, email_task.dependencies)
        self.assertIn(detection.id, push_task.dependencies)

    def test_security_controls_do_not_depend_on_account_verification(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        verification = next((t for t in result.tasks if t.source == "line 2"), None)
        password_policy = next((t for t in result.tasks if t.source == "line 4"), None)
        encryption = next((t for t in result.tasks if t.source == "line 13"), None)
        self.assertIsNotNone(verification)
        self.assertIsNotNone(password_policy)
        self.assertIsNotNone(encryption)
        self.assertNotIn(verification.id, password_policy.dependencies)
        self.assertNotIn(verification.id, encryption.dependencies)

    def test_password_policy_depends_on_registration_tasks(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        password_policy = next((t for t in result.tasks if t.source == "line 4"), None)
        registration_tasks = [t for t in result.tasks if t.source == "line 1"]
        self.assertIsNotNone(password_policy)
        self.assertGreater(len(registration_tasks), 0)
        self.assertTrue(
            any(task.id in password_policy.dependencies for task in registration_tasks),
            "Password policy should depend on registration foundations",
        )

    def test_localization_does_not_depend_on_rbac(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        rbac = next((t for t in result.tasks if t.source == "line 5"), None)
        localization = next((t for t in result.tasks if t.source == "line 15"), None)
        self.assertIsNotNone(rbac)
        self.assertIsNotNone(localization)
        self.assertNotIn(rbac.id, localization.dependencies)

    def test_access_control_depends_on_verification_not_mfa(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        verification = next((t for t in result.tasks if t.source == "line 2"), None)
        mfa = next((t for t in result.tasks if t.source == "line 3"), None)
        rbac = next((t for t in result.tasks if t.source == "line 5"), None)
        self.assertIsNotNone(verification)
        self.assertIsNotNone(mfa)
        self.assertIsNotNone(rbac)
        self.assertIn(verification.id, rbac.dependencies)
        self.assertNotIn(mfa.id, rbac.dependencies)

    def test_healthcare_special_requirements_are_split(self):
        if not self.requirements_text:
            self.skipTest("data/raw/docs/requirements.txt not found")
        planner = PlannerAgent(FakeLLMClient(payload={}))
        result = planner.plan_from_requirements(
            self.requirements_text,
            allow_fallback=True,
            allow_decomposition=True,
        )
        # Line 1: email, phone, national ID, Google OAuth, Apple Sign-In → 5 tasks
        registration_tasks = [t for t in result.tasks if t.source == "line 1"]
        # Line 12: appointment conflict notification → detect + email + push = 3 tasks
        conflict_tasks = [t for t in result.tasks if t.source == "line 12"]
        # Line 14: GDPR → deletion, export, consent withdrawal, access log = 4 tasks
        gdpr_tasks = [t for t in result.tasks if t.source == "line 14"]
        receptionist_tasks = [t for t in result.tasks if t.source == "line 9"]
        lab_tasks = [t for t in result.tasks if t.source == "line 10"]
        encryption_tasks = [t for t in result.tasks if t.source == "line 13"]
        self.assertEqual(len(registration_tasks), 5)
        self.assertEqual(len(conflict_tasks), 3)
        self.assertEqual(len(gdpr_tasks), 4)
        self.assertEqual(len(receptionist_tasks), 3)
        self.assertEqual(len(lab_tasks), 2)
        self.assertEqual(len(encryption_tasks), 2)


class PlannerTechnicalDomainTests(unittest.TestCase):
    """Regression coverage for technical-domain planner requirements."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.graph.dependency_graph import DependencyGraph
        planner = PlannerAgent(FakeLLMClient(payload={}))
        cls.result = planner.plan_from_requirements(
            TECHNICAL_PLANNER_REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=True,
        )
        cls.graph = DependencyGraph(cls.result)
        cls.summary = cls.graph.summary()

    def test_offline_requirement_is_nfr_without_false_positive_tags(self):
        text = (
            "The system must operate fully offline without reliance on external APIs or cloud "
            "services, using locally hosted language models."
        )
        tags = PlannerAgent._extract_semantic_tags(text)
        self.assertIn("offline_operation", tags)
        self.assertNotIn("integration", tags)
        self.assertNotIn("localization", tags)
        self.assertEqual(PlannerAgent._classify_req_type(text), "NFR")

    def test_technical_titles_are_specific(self):
        expected_titles = {
            "line 1": "Implement multi-format requirements ingestion workflow",
            "line 7": "Implement Git repository progress monitor",
            "line 9": "Implement decision explainability workflow",
            "line 12": "Implement multi-agent orchestration layer",
            "line 13": "Implement task and report export service",
            "line 14": "Implement project planning dashboard",
            "line 17": "Implement ambiguous requirements validation service",
            "line 19": "Implement agent interaction logging service",
            "line 20": "Implement planner evaluation metrics service",
        }
        for source, expected in expected_titles.items():
            task = next((t for t in self.result.tasks if t.source == source), None)
            self.assertIsNotNone(task, f"Missing task for {source}")
            self.assertEqual(task.title, expected)

    def test_agent_interaction_logging_is_classified_nfr(self):
        execution_log = next((t for t in self.result.tasks if t.source == "line 19"), None)
        self.assertIsNotNone(execution_log)
        self.assertEqual(execution_log.req_type, "NFR")

    def test_technical_dependency_chain_is_stable(self):
        by_source = {task.source: task for task in self.result.tasks}
        risk_detection = next(
            task for task in self.result.tasks
            if task.source == "line 8" and "risk detection" in task.title.lower()
        )
        self.assertIn(by_source["line 1"].id, by_source["line 2"].dependencies)
        self.assertIn(by_source["line 2"].id, by_source["line 3"].dependencies)
        self.assertIn(by_source["line 2"].id, by_source["line 4"].dependencies)
        self.assertIn(by_source["line 2"].id, by_source["line 5"].dependencies)
        self.assertIn(by_source["line 7"].id, risk_detection.dependencies)
        self.assertIn(by_source["line 3"].id, risk_detection.dependencies)
        self.assertIn(by_source["line 4"].id, risk_detection.dependencies)

    def test_execution_log_depends_on_orchestration_not_dashboard(self):
        by_source = {task.source: task for task in self.result.tasks}
        execution_log = by_source["line 19"]
        orchestration = by_source["line 12"]
        dashboard = by_source["line 14"]
        self.assertIn(orchestration.id, execution_log.dependencies)
        self.assertNotIn(dashboard.id, execution_log.dependencies)

    def test_export_depends_on_generated_planning_artifacts(self):
        by_source = {task.source: task for task in self.result.tasks}
        export_task = by_source["line 13"]
        task_generation = by_source["line 2"]
        self.assertIn(task_generation.id, export_task.dependencies)
        self.assertNotIn(export_task.id, self.summary["root_tasks"])

    def test_planner_critic_feedback_depends_on_generated_tasks(self):
        by_source = {task.source: task for task in self.result.tasks}
        feedback_task = by_source["line 6"]
        task_generation = by_source["line 2"]
        self.assertIn(task_generation.id, feedback_task.dependencies)

    def test_ambiguous_requirements_handling_joins_workflow(self):
        by_source = {task.source: task for task in self.result.tasks}
        ambiguous_handling = by_source["line 17"]
        ingestion = by_source["line 1"]
        task_generation = by_source["line 2"]
        self.assertIn(ingestion.id, ambiguous_handling.dependencies)
        self.assertIn(task_generation.id, ambiguous_handling.dependencies)
        self.assertNotIn(ambiguous_handling.id, self.summary["root_tasks"])

    def test_requirements_ingestion_remains_valid_root(self):
        by_source = {task.source: task for task in self.result.tasks}
        ingestion = by_source["line 1"]
        self.assertIn(ingestion.id, self.summary["root_tasks"])

    def test_technical_plan_has_no_suspicious_isolated_tasks(self):
        self.assertEqual(self.summary["suspicious_isolated_tasks"], [])
        self.assertEqual(self.summary["validation_warnings"], [])

    def test_offline_nfr_constrains_core_planner_tasks(self):
        offline_task = next(task for task in self.result.tasks if task.source == "line 15")
        constrained = [task for task in self.result.tasks if offline_task.id in task.dependencies]
        self.assertTrue(constrained, "Offline NFR should constrain downstream functional tasks")
        self.assertTrue(
            any(task.source in {"line 2", "line 10", "line 12"} for task in constrained),
            f"Offline NFR attached to unexpected tasks: {[task.id for task in constrained]}",
        )

    def test_security_nfr_constrains_storage_and_exposure_tasks(self):
        security_task = next(task for task in self.result.tasks if task.source == "line 16")
        constrained = [task for task in self.result.tasks if security_task.id in task.dependencies]
        self.assertTrue(constrained, "Security NFR should constrain protected tasks")
        self.assertTrue(
            any(task.source in {"line 10", "line 13", "line 14", "line 19", "line 20"} for task in constrained),
            f"Security NFR attached to unexpected tasks: {[task.id for task in constrained]}",
        )

    def test_performance_nfr_constrains_high_load_planner_surfaces(self):
        performance_task = next(task for task in self.result.tasks if task.source == "line 18")
        constrained = [task for task in self.result.tasks if performance_task.id in task.dependencies]
        self.assertTrue(constrained, "Performance NFR should constrain relevant functional tasks")
        self.assertTrue(
            any(task.source in {"line 14", "line 20", "line 3", "line 4"} for task in constrained),
            f"Performance NFR attached to unexpected tasks: {[task.id for task in constrained]}",
        )

    def test_scalability_nfr_does_not_depend_on_dashboard_or_reporting_surfaces(self):
        performance_task = next(task for task in self.result.tasks if task.source == "line 18")
        forbidden_predecessors = [
            task for task in self.result.tasks
            if task.id in performance_task.dependencies
            and (
                "dashboard" in task.title.lower()
                or "report" in task.title.lower()
                or "export" in task.title.lower()
            )
        ]
        self.assertEqual(
            forbidden_predecessors,
            [],
            f"Scalability NFR should not depend on downstream dashboard/report/export tasks: {[task.id for task in forbidden_predecessors]}",
        )


class PlannerArtifactDependencyStrengtheningTests(unittest.TestCase):
    """Ensure artifact consumer tasks attach to meaningful upstream producers."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.graph.dependency_graph import DependencyGraph
        planner = PlannerAgent(FakeLLMClient(payload={}))
        cls.result = planner.plan_from_requirements(
            ARTIFACT_DEPENDENCY_REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=True,
        )
        cls.by_source = {task.source: task for task in cls.result.tasks}
        cls.graph = DependencyGraph(cls.result)
        cls.summary = cls.graph.summary()

    def test_reporting_task_depends_on_upstream_data_producer(self):
        report_task = self.by_source["line 6"]
        create_task = self.by_source["line 3"]
        update_task = self.by_source["line 4"]
        self.assertTrue(
            {create_task.id, update_task.id} & set(report_task.dependencies),
            f"Report task missing upstream producer dependency: {report_task.dependencies}",
        )

    def test_dashboard_depends_on_report_or_data_generation(self):
        dashboard_task = self.by_source["line 7"]
        report_task = self.by_source["line 6"]
        update_task = self.by_source["line 4"]
        self.assertIn(report_task.id, dashboard_task.dependencies)
        self.assertTrue(
            {update_task.id, self.by_source["line 3"].id} & set(dashboard_task.dependencies),
            f"Dashboard missing direct data producer dependency: {dashboard_task.dependencies}",
        )

    def test_view_task_depends_on_creation_or_update_when_semantically_required(self):
        doctor_view = self.by_source["line 5"]
        create_task = self.by_source["line 3"]
        update_task = self.by_source["line 4"]
        self.assertTrue(
            {create_task.id, update_task.id} & set(doctor_view.dependencies),
            f"View task missing upstream record dependency: {doctor_view.dependencies}",
        )

    def test_rbac_remains_gate_but_not_only_dependency(self):
        doctor_view = self.by_source["line 5"]
        rbac = next(
            task for task in self.result.tasks
            if task.source == "line 2" and "role-based access control" in task.title.lower()
        )
        self.assertIn(rbac.id, doctor_view.dependencies)
        self.assertGreaterEqual(len(doctor_view.dependencies), 2)

    def test_export_depends_on_report_or_data_generation(self):
        export_task = self.by_source["line 8"]
        report_task = self.by_source["line 6"]
        self.assertIn(report_task.id, export_task.dependencies)
        self.assertNotIn(export_task.id, self.summary["root_tasks"])

    def test_valid_true_root_still_remains_root(self):
        registration = self.by_source["line 1"]
        self.assertIn(registration.id, self.summary["root_tasks"])

    def test_graph_validity_is_preserved(self):
        self.assertTrue(self.summary["is_valid_dag"])


class PlannerNfrConstraintPropagationTests(unittest.TestCase):
    """Ensure architectural NFRs constrain the functional tasks they govern."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.graph.dependency_graph import DependencyGraph
        planner = PlannerAgent(FakeLLMClient(payload={}))
        cls.result = planner.plan_from_requirements(
            NFR_CONSTRAINT_REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=True,
        )
        cls.by_source = {task.source: task for task in cls.result.tasks}
        cls.graph = DependencyGraph(cls.result)
        cls.summary = cls.graph.summary()

    def test_security_nfr_constrains_protected_functional_tasks(self):
        security_nfr = self.by_source["line 7"]
        storage_task = self.by_source["line 2"]
        view_task = self.by_source["line 3"]
        self.assertIn(security_nfr.id, storage_task.dependencies)
        self.assertIn(security_nfr.id, view_task.dependencies)

    def test_offline_nfr_constrains_integration_tasks(self):
        offline_nfr = self.by_source["line 6"]
        integration_task = self.by_source["line 1"]
        self.assertIn(offline_nfr.id, integration_task.dependencies)

    def test_performance_nfr_constrains_critical_api_and_dashboard_tasks(self):
        performance_nfr = self.by_source["line 8"]
        integration_task = self.by_source["line 1"]
        dashboard_task = self.by_source["line 4"]
        self.assertIn(performance_nfr.id, integration_task.dependencies)
        self.assertIn(performance_nfr.id, dashboard_task.dependencies)

    def test_audit_control_nfr_constrains_sensitive_mutation_tasks(self):
        audit_nfr = next(
            task for task in self.result.tasks
            if task.source == "line 9" and task.req_type == "NFR"
        )
        patient_records_storage = next(
            task for task in self.result.tasks
            if task.source == "line 2" and "patient records" in task.title.lower()
        )
        billing_update = next(
            task for task in self.result.tasks
            if task.source == "line 10" and "billing entries" in task.title.lower()
        )
        self.assertIn(audit_nfr.id, patient_records_storage.dependencies)
        self.assertIn(audit_nfr.id, billing_update.dependencies)
        constrained = [task for task in self.result.tasks if audit_nfr.id in task.dependencies]
        self.assertTrue(constrained)

    def test_audit_control_propagation_stays_selective(self):
        audit_nfr = next(
            task for task in self.result.tasks
            if task.source == "line 9" and task.req_type == "NFR"
        )
        integration_task = self.by_source["line 1"]
        public_help = self.by_source["line 5"]
        self.assertNotIn(audit_nfr.id, integration_task.dependencies)
        self.assertNotIn(audit_nfr.id, public_help.dependencies)

    def test_unrelated_public_help_task_is_not_over_linked(self):
        public_help = self.by_source["line 5"]
        offline_nfr = self.by_source["line 6"]
        security_nfr = self.by_source["line 7"]
        performance_nfr = self.by_source["line 8"]
        audit_nfr = self.by_source["line 9"]
        self.assertNotIn(offline_nfr.id, public_help.dependencies)
        self.assertNotIn(security_nfr.id, public_help.dependencies)
        self.assertNotIn(performance_nfr.id, public_help.dependencies)
        self.assertNotIn(audit_nfr.id, public_help.dependencies)

    def test_valid_leaf_task_can_remain_unconstrained(self):
        public_help = self.by_source["line 5"]
        self.assertIn(public_help.id, self.summary["leaf_tasks"])
        self.assertEqual(public_help.dependencies, [])

    def test_valid_public_read_only_root_is_not_flagged_as_suspicious(self):
        public_help = self.by_source["line 5"]
        suspicious_ids = {item["id"] for item in self.summary["suspicious_isolated_tasks"]}
        warning_text = " ".join(self.summary["validation_warnings"])
        self.assertNotIn(public_help.id, suspicious_ids)
        self.assertNotIn(public_help.title, warning_text)

    def test_graph_validity_is_preserved(self):
        self.assertTrue(self.summary["is_valid_dag"])


class PlannerEducationNfrPropagationTests(unittest.TestCase):
    """Ensure education-facing workflows inherit relevant quality constraints."""

    REQUIREMENTS = """\
1. Students can register in available courses.
2. Students can enroll in available courses.
3. The system should Upload grades and course materials.
4. The system should Generate tuition invoices.
5. The system should process online payments.
6. The system should Send automated email notifications for deadlines.
7. The system must encrypt sensitive data.
8. The system must support mobile-friendly interfaces.
9. The system must maintain responsive performance under peak load.
"""

    @classmethod
    def setUpClass(cls) -> None:
        planner = PlannerAgent(FakeLLMClient(payload={}))
        cls.result = planner.plan_from_requirements(
            cls.REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=True,
            force_fallback=True,
        )
        cls.security_nfr = next(task for task in cls.result.tasks if "encrypt sensitive data" in task.description.lower())
        cls.mobile_nfr = next(task for task in cls.result.tasks if "mobile-friendly interfaces" in task.description.lower())
        cls.performance_nfr = next(task for task in cls.result.tasks if "responsive performance under peak load" in task.description.lower())

    def test_security_nfr_constrains_payment_and_grade_workflows(self):
        grades = next(task for task in self.result.tasks if "upload grades and course materials" in task.description.lower())
        payments = next(task for task in self.result.tasks if "process online payments" in task.description.lower())
        self.assertIn(self.security_nfr.id, grades.dependencies)
        self.assertIn(self.security_nfr.id, payments.dependencies)

    def test_mobile_and_performance_nfrs_constrain_user_facing_workflows(self):
        registration = next(task for task in self.result.tasks if "register in available courses" in task.description.lower())
        payments = next(task for task in self.result.tasks if "process online payments" in task.description.lower())
        for task in (registration, payments):
            self.assertIn(self.mobile_nfr.id, task.dependencies)
            self.assertIn(self.performance_nfr.id, task.dependencies)


class PlannerPerformanceDependencyCorrectionTests(unittest.TestCase):
    def setUp(self) -> None:
        from src.core.schemas import Task

        self.planner = PlannerAgent(FakeLLMClient(payload={}))
        self.foundation = Task(
            id="T001",
            title="Implement structured task generation workflow",
            description="The system must automatically generate a structured list of tasks.",
            req_type="FR",
            complexity=2,
            dependencies=[],
            source="line 1",
        )
        self.dashboard = Task(
            id="T002",
            title="Implement project planning dashboard",
            description="The system must provide a user interface dashboard displaying task breakdown and risk indicators.",
            req_type="FR",
            complexity=3,
            dependencies=[],
            source="line 2",
        )
        self.scalability = Task(
            id="T003",
            title="Optimize planner scalability for 200-task projects",
            description="The system must support scalability to handle projects with at least 200 tasks without significant performance degradation.",
            req_type="NFR",
            complexity=4,
            dependencies=["T001", "T002"],
            source="line 3",
        )

    def test_inverted_dashboard_to_scalability_edge_is_corrected(self):
        tasks = [self.foundation, self.dashboard, self.scalability]
        self.planner._correct_inverted_performance_dependencies(tasks)
        self.assertIn(self.foundation.id, self.scalability.dependencies)
        self.assertNotIn(self.dashboard.id, self.scalability.dependencies)
        self.assertIn(self.scalability.id, self.dashboard.dependencies)
        self.assertTrue(self.planner._dependency_corrections)

    def test_legitimate_foundation_predecessor_remains_valid(self):
        tasks = [self.foundation, self.dashboard, self.scalability]
        self.planner._correct_inverted_performance_dependencies(tasks)
        self.assertEqual(self.scalability.dependencies, [self.foundation.id])

    def test_unrelated_security_nfr_edge_is_not_reversed(self):
        from src.core.schemas import Task

        security_nfr = Task(
            id="T004",
            title="Enforce data security controls",
            description="The system must ensure all data are encrypted at rest.",
            req_type="NFR",
            complexity=3,
            dependencies=[self.foundation.id],
            source="line 4",
        )
        tasks = [self.foundation, self.dashboard, self.scalability, security_nfr]
        self.planner._correct_inverted_performance_dependencies(tasks)
        self.assertEqual(security_nfr.dependencies, [self.foundation.id])

    def test_corrected_graph_stays_valid(self):
        from src.core.schemas import TaskList
        from src.graph.dependency_graph import DependencyGraph

        tasks = [self.foundation, self.dashboard, self.scalability]
        self.planner._correct_inverted_performance_dependencies(tasks)
        summary = DependencyGraph(TaskList(tasks=tasks)).summary()
        self.assertTrue(summary["is_valid_dag"])


class PlannerFocusedPerformanceDirectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from src.graph.dependency_graph import DependencyGraph

        planner = PlannerAgent(FakeLLMClient(payload={}))
        cls.result = planner.plan_from_requirements(
            FOCUSED_PERFORMANCE_DIRECTION_REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=True,
        )
        cls.by_source = {task.source: task for task in cls.result.tasks}
        cls.summary = DependencyGraph(cls.result).summary()

    def test_scalability_nfr_does_not_receive_inverted_surface_dependencies(self):
        scalability = self.by_source["line 5"]
        self.assertEqual(scalability.req_type, "NFR")
        self.assertEqual(scalability.dependencies, [])

    def test_dashboard_export_and_api_are_constrained_by_scalability(self):
        foundation = self.by_source["line 1"]
        scalability = self.by_source["line 5"]
        dashboard = self.by_source["line 2"]
        export_task = self.by_source["line 3"]
        api_task = self.by_source["line 4"]

        for task in (dashboard, export_task, api_task):
            self.assertIn(foundation.id, task.dependencies)
            self.assertIn(scalability.id, task.dependencies)

    def test_graph_has_no_inverted_performance_validation_warning(self):
        self.assertTrue(self.summary["is_valid_dag"])
        self.assertFalse(
            any("Performance/scalability task" in warning for warning in self.summary["validation_warnings"]),
            self.summary["validation_warnings"],
        )


class PlannerAccessDecisionTests(unittest.TestCase):
    """Validate public vs auth-only vs RBAC dependency inference."""

    @classmethod
    def setUpClass(cls) -> None:
        planner = PlannerAgent(FakeLLMClient(payload={}))
        cls.result = planner.plan_from_requirements(
            ACCESS_DECISION_REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=True,
        )
        cls.by_source = {task.source: task for task in cls.result.tasks}
        cls.verification = cls.by_source["line 2"]
        cls.rbac = next(
            task for task in cls.result.tasks
            if task.source == "line 3" and "role-based access control" in task.title.lower()
        )

    def test_public_catalog_browse_requires_neither_auth_nor_rbac(self):
        browse = self.by_source["line 4"]
        self.assertNotIn(self.verification.id, browse.dependencies)
        self.assertNotIn(self.rbac.id, browse.dependencies)

    def test_patient_booking_requires_auth_baseline_only(self):
        booking = self.by_source["line 5"]
        self.assertIn(self.verification.id, booking.dependencies)
        self.assertNotIn(self.rbac.id, booking.dependencies)

    def test_doctor_record_access_requires_rbac(self):
        doctor_view = self.by_source["line 6"]
        self.assertIn(self.rbac.id, doctor_view.dependencies)

    def test_lab_upload_requires_rbac(self):
        lab_upload = self.by_source["line 7"]
        self.assertIn(self.rbac.id, lab_upload.dependencies)

    def test_gdpr_deletion_requires_auth_baseline_only(self):
        gdpr_delete = self.by_source["line 8"]
        self.assertIn(self.verification.id, gdpr_delete.dependencies)
        self.assertNotIn(self.rbac.id, gdpr_delete.dependencies)

    def test_payment_gateway_integration_requires_neither_by_default(self):
        integration = self.by_source["line 9"]
        self.assertNotIn(self.verification.id, integration.dependencies)
        self.assertNotIn(self.rbac.id, integration.dependencies)

    def test_admin_reporting_requires_rbac(self):
        admin_report = self.by_source["line 10"]
        self.assertIn(self.rbac.id, admin_report.dependencies)


class PlannerHealthcareArtifactDependencyTests(unittest.TestCase):
    """Regression coverage for real hospital artifact-consumer dependencies."""

    @classmethod
    def setUpClass(cls) -> None:
        planner = PlannerAgent(FakeLLMClient(payload={}))
        cls.result = planner.plan_from_requirements(
            Path("data/raw/docs/hospital_requirements_fixture.txt").read_text(encoding="utf-8"),
            allow_fallback=True,
            allow_decomposition=True,
        )

    def test_radiology_attachment_reporting_depends_on_uploaded_reports(self):
        attachment_task = next(
            task for task in self.result.tasks
            if "attachments or file links" in task.description.lower()
        )
        upload_task = next(
            task for task in self.result.tasks
            if "upload radiology reports" in task.description.lower()
        )
        self.assertIn(upload_task.id, attachment_task.dependencies)

    def test_management_dashboard_has_operational_data_dependency_not_only_rbac(self):
        dashboard_task = next(task for task in self.result.tasks if "dashboard" in task.description.lower())
        access_control = next(
            task for task in self.result.tasks
            if "role-based access control" in task.title.lower()
        )
        self.assertGreaterEqual(len(dashboard_task.dependencies), 2)
        self.assertTrue(
            any(task_id != access_control.id for task_id in dashboard_task.dependencies),
            f"Dashboard task missing upstream operational data dependency: {dashboard_task.dependencies}",
        )

    def test_audit_control_nfr_is_not_a_decorative_leaf(self):
        from src.graph.dependency_graph import DependencyGraph
        audit_nfr = next(task for task in self.result.tasks if "audit logs" in task.description.lower())
        constrained = [task for task in self.result.tasks if audit_nfr.id in task.dependencies]
        summary = DependencyGraph(self.result).summary()
        self.assertTrue(constrained, "Audit/control NFR should constrain downstream mutation workflows")
        self.assertNotIn(audit_nfr.id, summary["leaf_tasks"])

    def test_security_nfr_gates_multiple_sensitive_hospital_workflows(self):
        security_nfr = next(task for task in self.result.tasks if "secure hospital data" in task.title.lower())
        constrained = [task for task in self.result.tasks if security_nfr.id in task.dependencies]
        self.assertGreaterEqual(len(constrained), 3)


class PlannerHospitalWorkflowChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        planner = PlannerAgent(FakeLLMClient(payload={}))
        cls.result = planner.plan_from_requirements(
            HOSPITAL_WORKFLOW_CHAIN_REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=False,
        )
        cls.by_source = {task.source: task for task in cls.result.tasks}

    def test_registration_precedes_appointment(self):
        self.assertIn(self.by_source["line 1"].id, self.by_source["line 2"].dependencies)

    def test_doctor_encounter_precedes_lab_and_radiology_ordering(self):
        encounter = self.by_source["line 3"]
        self.assertIn(encounter.id, self.by_source["line 4"].dependencies)
        self.assertIn(encounter.id, self.by_source["line 6"].dependencies)

    def test_lab_and_radiology_orders_precede_result_report_tasks(self):
        self.assertIn(self.by_source["line 4"].id, self.by_source["line 5"].dependencies)
        self.assertIn(self.by_source["line 6"].id, self.by_source["line 7"].dependencies)

    def test_result_availability_can_gate_prescription(self):
        result_visibility = self.by_source["line 8"]
        prescription = self.by_source["line 9"]
        self.assertIn(result_visibility.id, prescription.dependencies)

    def test_prescription_precedes_pharmacy_dispensing(self):
        self.assertIn(self.by_source["line 9"].id, self.by_source["line 10"].dependencies)

    def test_billing_completion_precedes_discharge(self):
        self.assertIn(self.by_source["line 11"].id, self.by_source["line 12"].dependencies)

    def test_unrelated_hospital_task_is_not_over_linked(self):
        localization = self.by_source["line 13"]
        medical_chain_ids = {
            self.by_source["line 4"].id,
            self.by_source["line 5"].id,
            self.by_source["line 9"].id,
            self.by_source["line 10"].id,
            self.by_source["line 11"].id,
            self.by_source["line 12"].id,
        }
        self.assertTrue(medical_chain_ids.isdisjoint(localization.dependencies))

    def test_graph_validity_is_preserved(self):
        from src.graph.dependency_graph import DependencyGraph

        self.assertTrue(DependencyGraph(self.result).summary()["is_valid_dag"])


class PlannerS2TitleHygieneTests(unittest.TestCase):
    """S2: Rule-based title generation regressions caught from cross-domain eval."""

    @staticmethod
    def _titles(brief_text: str) -> list[str]:
        from src.parsers.brief_parser import BriefParser
        from src.agents.planner import PlannerAgent

        parser = BriefParser()
        requirements = parser.parse(brief_text)
        planner = PlannerAgent(llm_client=None)
        # Mirror the doc_to_tasks pipeline: feed pre-parsed brief requirements
        # in by overriding _prepare_requirements so plan_from_requirements skips
        # its plain-text parser path.
        effective_text = "\n".join(
            f"[{item.source}] {item.text}" for item in requirements
        )
        planner._prepare_requirements = (  # type: ignore[method-assign]
            lambda _txt, force_fallback=False: (effective_text, list(requirements))  # noqa: ARG005
        )
        task_list = planner.plan_from_requirements(
            effective_text,
            allow_fallback=True,
            force_fallback=True,
        )
        return [t.title for t in task_list.tasks]

    def _assert_no_bugs(self, titles: list[str]) -> None:
        bugs = {
            "duplicate_word": re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE),
            "and_workflow": re.compile(
                r"\b(?:and|or|with|for|to|in|on|at|of|by)\s+workflow\b", re.IGNORECASE
            ),
            "unbalanced_paren": re.compile(r"\([^)]*$"),
            "duplicate_verb_stem": re.compile(
                r"\b(?:Integrate Integration|Implement Implementation|"
                r"Optimize Optimization|Enforce Enforcement)\b",
                re.IGNORECASE,
            ),
            "verb_strip_remnant": re.compile(
                r"^Optimize\s+(?:in|not|the|and|or|of|to|for|with|but|complete|stored|refresh)\s+",
                re.IGNORECASE,
            ),
            "leading_allow_or_ideally": re.compile(
                r"^(?:Implement|Optimize|Enforce|Integrate)\s+(?:Allow|Ideally|Optionally|Preferably)\b",
                re.IGNORECASE,
            ),
            "role_to_pattern": re.compile(
                r"^(?:Implement|Optimize|Enforce|Integrate)\s+"
                r"(?:doctors?|patients?|users?|customers?|members?|sellers?|"
                r"instructors?|advisors?|registrars?|librarians?|students?|employees?)"
                r"\s+to\b",
                re.IGNORECASE,
            ),
        }
        for title in titles:
            for name, regex in bugs.items():
                self.assertIsNone(
                    regex.search(title),
                    f"Bug [{name}] in title: {title!r}",
                )

    def test_clinic_brief_titles_have_no_template_artifacts(self):
        brief = (
            "Project Title:\nClinic\n\nMain Features:\n"
            "- Register new patients using national ID and contact details\n"
            "- Allow doctors to view patient history and record diagnosis\n"
            "- Send appointment reminders to patients via email\n\n"
            "Expected Benefits:\nThe system should be fast and reliable to ensure zero downtime. "
            "Patient data should be secure and accessible only to authorized users.\n\n"
            "Constraints or Special Notes:\n"
            "- System must respond within two seconds for all standard operations\n"
        )
        self._assert_no_bugs(self._titles(brief))

    def test_crm_integration_does_not_double_verb(self):
        brief = (
            "Project Title:\nCRM\n\nFunctional Requirements:\n"
            "- Integration with email clients (Gmail/Outlook) for two-way sync\n"
            "- Task and follow-up reminders tied to contacts and deals\n\n"
            "Non-Functional Requirements:\n"
            "- API response time must not exceed 500ms for all list and detail views\n"
        )
        titles = self._titles(brief)
        self._assert_no_bugs(titles)
        self.assertFalse(
            any(re.search(r"Integrate\s+integration", t, re.IGNORECASE) for t in titles),
            f"Integrate integration bug regressed: {titles}",
        )

    def test_compressed_nfr_sentence_does_not_emit_optimize_meet(self):
        brief = (
            "Project Title:\nHospital\n\nMain Features:\n"
            "- Patient registration\n\n"
            "Non-Functional Requirements:\n"
            "HIPAA-compliant data security, 99.9% uptime, sub-2s response time.\n"
        )
        titles = self._titles(brief)
        self._assert_no_bugs(titles)
        self.assertFalse(
            any(
                re.search(r"^Optimize\s+(?:meet|maintain|establish)\b", t, re.IGNORECASE)
                for t in titles
            ),
            f"Parser-template double-up regressed: {titles}",
        )

    def test_role_to_pattern_with_leading_the_is_stripped(self):
        brief = (
            "Project Title:\nUniversity\n\nMain Features:\n"
            "- Allow the registrar to manage course schedules and assign instructors to courses\n"
        )
        self._assert_no_bugs(self._titles(brief))

    def test_provide_auxiliary_does_not_produce_delivery_workflow(self):
        brief = (
            "Project Title:\nLMS\n\nFunctional Requirements:\n"
            "- Course builder with video lessons, quizzes, and downloadable materials\n"
            "- Discussion forums per course with moderation features\n"
        )
        titles = self._titles(brief)
        self._assert_no_bugs(titles)
        self.assertFalse(
            any(re.search(r"\bdelivery\s+workflow\b", t, re.IGNORECASE) for t in titles),
            f"'delivery workflow' auxiliary suffix regressed: {titles}",
        )

    def test_safe_nfr_template_helper_behavior(self):
        from src.agents.planner import PlannerAgent

        self.assertEqual(
            PlannerAgent._safe_nfr_template(
                "Enforce", "GDPR compliance", "regulatory", "compliance requirements"
            ),
            "Enforce GDPR compliance",
        )
        self.assertEqual(
            PlannerAgent._safe_nfr_template(
                "Optimize", "API throughput", "system", "performance constraints"
            ),
            "Optimize API throughput performance constraints",
        )
        self.assertEqual(
            PlannerAgent._safe_nfr_template(
                "Optimize", "in", "system", "performance constraints"
            ),
            "Optimize system performance constraints",
        )
        self.assertEqual(
            PlannerAgent._safe_nfr_template(
                "Optimize",
                "meet p99 under 500ms response-time SLO",
                "system",
                "performance constraints",
            ),
            "Meet p99 under 500ms response-time SLO",
        )


if __name__ == "__main__":
    unittest.main()
