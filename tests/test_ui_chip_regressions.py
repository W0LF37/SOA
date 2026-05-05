from __future__ import annotations

from pathlib import Path

from src.agents.planner import PlannerAgent, RequirementItem
from src.core.schemas import TaskList
from src.parsers.brief_parser import BriefParser
from src.services.brief_generator import BriefGenerator


class EmptyLLMClient:
    def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
        return {}


class StaticPayloadLLMClient:
    def __init__(self, payload: dict):
        self.payload = payload

    def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
        return self.payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_CHIPS_DIR = PROJECT_ROOT / "data" / "eval_runs" / "ui_chips"


def _fallback_plan_for(brief_name: str) -> tuple[str, list[RequirementItem], TaskList]:
    raw_text = (UI_CHIPS_DIR / f"{brief_name}.txt").read_text(encoding="utf-8")
    requirements = BriefParser().parse(raw_text)
    planner = PlannerAgent(EmptyLLMClient())
    result = planner._build_rule_based_plan(
        requirements=requirements,
        allow_decomposition=True,
    )
    return raw_text, requirements, result


def _find_task(task_list: TaskList, phrase: str):
    lowered_phrase = phrase.casefold()
    return next(
        task
        for task in task_list.tasks
        if lowered_phrase in task.title.casefold() or lowered_phrase in task.description.casefold()
    )


def test_university_portal_fallback_plan_keeps_all_compound_nfrs() -> None:
    _, _, result = _fallback_plan_for("university_portal")
    nfr_descriptions = [task.description.casefold() for task in result.tasks if task.req_type == "NFR"]

    assert any("high availability" in description for description in nfr_descriptions)
    assert any("encrypt sensitive data" in description for description in nfr_descriptions)
    assert any("mobile-friendly" in description for description in nfr_descriptions)
    assert any("peak load" in description for description in nfr_descriptions)


def test_ecommerce_fallback_plan_keeps_domain_specific_titles_and_types() -> None:
    _, _, result = _fallback_plan_for("ecommerce")

    titles = [task.title.casefold() for task in result.tasks]
    descriptions = [task.description.casefold() for task in result.tasks]

    assert any("seller dashboard" in title for title in titles)
    assert not any("project planning dashboard" in title for title in titles)
    assert not any("planner scalability" in title for title in titles)
    assert not any("large project portfolios" in title for title in titles)
    assert any("10,000 concurrent users" in description for description in descriptions)
    assert not any("scalable to 10." in description for description in descriptions)

    mobile_task = _find_task(result, "mobile-first")
    pci_task = _find_task(result, "pci-dss")

    assert mobile_task.req_type == "NFR"
    assert "pci-dss" in pci_task.title.casefold()
    assert "compliance compliance" not in pci_task.title.casefold()


def test_hospital_fallback_plan_keeps_titles_clean_and_intact() -> None:
    _, _, result = _fallback_plan_for("hospital_system")

    billing_task = _find_task(result, "insurance claim processing")
    emr_task = _find_task(result, "electronic medical records")
    security_task = _find_task(result, "hipaa")

    assert billing_task.description.casefold() != "title"
    assert "insurance claim processing" in billing_task.title.casefold()
    assert emr_task.title.count("(") == emr_task.title.count(")")
    assert "security security" not in security_task.title.casefold()


def test_mobile_banking_fallback_plan_stays_in_banking_domain() -> None:
    raw_text, requirements, result = _fallback_plan_for("mobile_banking")

    titles = [task.title.casefold() for task in result.tasks]

    assert not any("local models" in title for title in titles)

    offline_task = _find_task(result, "offline")
    qr_task = _find_task(result, "qr code")
    domain = BriefGenerator._domain_inference(result, requirements)
    tech_stack = PlannerAgent._detect_tech_stack(raw_text)

    assert offline_task.req_type == "NFR"
    assert "bill payments and nfr" not in qr_task.description.casefold()
    assert domain == "Likely domain: fintech, payments, and billing operations."
    assert "gin" not in tech_stack["backend"]
    assert "electron" not in tech_stack["frontend"]
    assert "mobile client" in tech_stack["frontend"]
    assert "auth and authorization" in tech_stack["backend"]


def test_clinic_fallback_plan_does_not_invent_lab_test_creation() -> None:
    _, _, result = _fallback_plan_for("clinic_system")

    titles_and_descriptions = [
        f"{task.title.casefold()} || {task.description.casefold()}"
        for task in result.tasks
    ]

    assert not any("lab tests creation" in entry for entry in titles_and_descriptions)
    assert any(
        "itemized invoices for consultations and lab tests" in task.description.casefold()
        for task in result.tasks
    )


def test_llm_placeholder_description_is_replaced_during_layout_repair() -> None:
    planner = PlannerAgent(
        StaticPayloadLLMClient(
            {
                "tasks": [
                    {
                        "id": "T001",
                        "title": "Implement billing and insurance claim processing workflow",
                        "description": "title",
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
        "1. The system should process billing and insurance claims.",
        allow_fallback=False,
        allow_decomposition=False,
    )

    assert "billing and insurance claims" in result.tasks[0].description.casefold()
    assert result.tasks[0].description.casefold() != "title"


def test_llm_placeholder_nfr_description_is_replaced_during_layout_repair() -> None:
    planner = PlannerAgent(
        StaticPayloadLLMClient(
            {
                "tasks": [
                    {
                        "id": "T001",
                        "title": "Implement QR code bill payment workflow",
                        "description": "The system should Bill payments and NFR",
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
        "1. Users can make bill payments using QR code scanning.",
        allow_fallback=False,
        allow_decomposition=False,
    )

    assert "qr code" in result.tasks[0].description.casefold()
    assert "nfr" not in result.tasks[0].description.casefold()


def test_tech_stack_detection_avoids_false_positives_and_infers_mobile_banking_capabilities() -> None:
    detected = PlannerAgent._detect_tech_stack(
        "A mobile banking app must support biometric login, 2FA, QR code bill payments, "
        "a mobile-first responsive interface, encrypted transaction data, and SMS alerts."
    )

    assert "gin" not in detected["backend"]
    assert "electron" not in detected["frontend"]
    assert "responsive web ui" in detected["frontend"]
    assert "auth and authorization" in detected["backend"]
    assert "payment gateway" in detected["external_services"]


def test_fintech_stress_brief_keeps_hard_requirements_clean() -> None:
    brief = """\
Project Title:
Fintech Super-App

Target Users:
- Retail Customer
- Merchant
- Support Agent
- Compliance Analyst
- Tenant Admin

Main Features:
- Customers register with national ID, phone OTP, biometric login, and two-factor authentication
- KYC onboarding with document capture, liveness checks, sanctions screening, and manual review queue
- QR code merchant payments, refunds, disputes, chargebacks, and real-time receipt notifications
- Customer support console for account lock/unlock, device reset, complaint tracking, and secure notes

Expected Benefits:
Launch a mobile-first, compliant, observable, accessible platform.

Non-Functional Requirements:
The platform must be PCI-DSS level 1, AML/KYC compliant, GDPR-ready, encrypted at rest and in transit, accessible to WCAG AA, and responsive at p95 under 700ms for 50,000 concurrent users.
It must support queued payments with conflict-safe sync, idempotent transaction processing, multi-tenant data isolation, configurable data retention, and fraud scoring throughput of 2,000 events per second.

Constraints or Special Notes:
- Do not store raw card data unless tokenized by a certified provider
- Sandbox mode for partner banks is required for integration testing
- Crypto trading is out of scope for v1
"""

    requirements = BriefParser().parse(brief)
    result = PlannerAgent(EmptyLLMClient())._build_rule_based_plan(
        requirements=requirements,
        allow_decomposition=True,
    )
    titles = [task.title for task in result.tasks]
    joined = " || ".join(f"{task.title} :: {task.description}" for task in result.tasks).casefold()

    assert "crypto trading" not in joined
    assert any("KYC onboarding" in title for title in titles)
    assert _find_task(result, "KYC onboarding").req_type == "FR"
    assert _find_task(result, "customer support console").req_type == "FR"
    assert _find_task(result, "card-data tokenization").req_type == "NFR"
    assert _find_task(result, "encryption in transit").req_type == "NFR"
    assert _find_task(result, "conflict-safe queued payment").req_type == "NFR"
    assert _find_task(result, "multi-tenant data isolation").req_type == "NFR"
    assert _find_task(result, "data retention").req_type == "NFR"
    assert _find_task(result, "p95 under 700ms").req_type == "NFR"
    assert not any("qR code" in title or "kYC" in title for title in titles)
    assert "support support" not in joined
    assert "project planning dashboard" not in joined
    assert "planner scalability" not in joined


def test_deduplication_keeps_rto_and_rpo_as_distinct_nfrs() -> None:
    requirements = [
        RequirementItem(line_no=1, source="REQ-01", text="The system should meet RTO under 30 minutes."),
        RequirementItem(line_no=2, source="REQ-02", text="The system should meet RPO under 5 minutes."),
    ]

    deduplicated = PlannerAgent.deduplicate_requirements(requirements)
    result = PlannerAgent(EmptyLLMClient())._build_rule_based_plan(
        requirements=deduplicated,
        allow_decomposition=True,
    )
    titles = [task.title.casefold() for task in result.tasks]

    assert len(deduplicated) == 2
    assert any("rto under 30 minutes" in title for title in titles)
    assert any("rpo under 5 minutes" in title for title in titles)
