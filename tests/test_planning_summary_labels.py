from __future__ import annotations

from src.agents.planner import RequirementItem
from src.core.schemas import Task, TaskList
from src.services.brief_generator import BriefGenerator
from src.services.sprint_planner import SprintPlanner


def _task(text: str) -> Task:
    return Task(
        id="T001",
        title="Implement domain workflow",
        description=text,
        req_type="FR",
        complexity=3,
        dependencies=[],
        source="line 1",
    )


def _domain_for(text: str) -> str:
    requirements = [
        RequirementItem(line_no=1, source="line 1", text=text),
    ]
    return BriefGenerator._domain_inference(
        TaskList(tasks=[_task(text)]),
        requirements,
    )


def test_sprint_names_are_generic_for_planning_themes() -> None:
    name = SprintPlanner._sprint_name(1, ["task_planning", "orchestration"])
    goal = SprintPlanner._sprint_goal(["task_planning", "orchestration"])

    assert name == "Planning & Coordination Intelligence"
    assert "Agent Feedback" not in name
    assert "planner-critic" not in goal.lower()


def test_sprint_names_use_product_themes() -> None:
    assert SprintPlanner._sprint_name(1, ["identity", "access_control"]) == "Identity & Access Foundations"
    assert SprintPlanner._sprint_name(2, ["crud", "view"]) == "Core Workflow Delivery"
    assert SprintPlanner._sprint_name(3, ["performance", "security"]) == "Security & Compliance Readiness"


def test_domain_inference_detects_common_project_domains() -> None:
    cases = {
        "Students enroll in courses, take quizzes, track grades, and download certificates.": "education and learning management",
        "CRM users track leads through a sales pipeline and forecast opportunities.": "CRM and sales operations",
        "IoT devices send sensor telemetry over MQTT and trigger real-time alerts.": "IoT monitoring and device operations",
        "Customers complete KYC, fund a wallet, and pay invoices through Stripe.": "fintech, payments, and billing operations",
        "Bank customers review account balances, transfer funds, scan QR codes for bill payments, and enable biometric login.": "fintech, payments, and billing operations",
        "Shoppers browse a product catalog, add items to cart, checkout, and track shipping.": "commerce and transactional order management",
    }

    for text, expected_domain in cases.items():
        assert _domain_for(text) == f"Likely domain: {expected_domain}."
