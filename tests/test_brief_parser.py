from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.agents.planner import RequirementItem
from src.parsers.brief_parser import BriefParser, BriefValidationError


FULL_CLINIC_BRIEF = """\
Project Title:
Clinic Management System

Project Overview:
A web-based system to manage clinic operations including patient registration,
appointments, consultations, and billing.

Problem Statement:
Clinic staff currently manage patient records and appointments on paper,
leading to errors, duplicate records, and inefficient scheduling.

Proposed Solution:
Build a unified digital platform where receptionists, doctors, and billing
staff can collaborate on a single patient record.

Target Users:
- Receptionist
- Doctor
- Billing Staff

Main Features:
- Register new patients using national ID and contact details
- Book and manage patient appointments for available doctors
- Allow doctors to view patient history and record diagnosis
- Generate itemized invoices for consultations and lab tests
- Send appointment reminders to patients via email

Expected Benefits:
The system should be fast and reliable to ensure zero downtime during clinic
hours. Patient data should be secure and accessible only to authorized users.

Constraints or Special Notes:
- Must support both Arabic and English languages
- System must respond within two seconds for all standard operations
"""


def test_parse_full_brief_returns_requirement_items() -> None:
    result = BriefParser().parse(FULL_CLINIC_BRIEF)

    assert isinstance(result, list)
    assert len(result) >= 5
    assert isinstance(result[0], RequirementItem)
    assert result[0].line_no == 1
    assert result[1].line_no == 2
    assert result[0].source == result[0].sources[0] == "REQ-01"


def test_parse_minimal_brief_title_and_features_only() -> None:
    text = """\
Project Title:
Clinic System

Main Features:
- Register patients
- View records
"""

    result = BriefParser().parse(text)

    assert len(result) == 2
    assert [item.source for item in result] == ["REQ-01", "REQ-02"]


def test_missing_main_features_raises_validation_error() -> None:
    text = """\
Project Title:
Clinic System

Project Overview:
A web-based clinic workflow system.
"""

    with pytest.raises(BriefValidationError) as exc_info:
        BriefParser().parse(text)

    assert "Main Features" in exc_info.value.errors[0]


def test_actor_matching_prefixes_requirement_text() -> None:
    text = """\
Project Title:
Clinic System

Target Users:
- Doctor

Main Features:
- Allow doctors to view patient history
"""

    result = BriefParser().parse(text)

    assert "Actor: Doctor" in result[0].text
    assert "—" in result[0].text


def test_constraints_produce_nfr_items() -> None:
    text = """\
Project Title:
Clinic System

Main Features:
- Register patients

Constraints or Special Notes:
- System must be secure and reliable
"""

    result = BriefParser().parse(text)

    assert len(result) >= 2
    assert any("system should" in item.text.lower() for item in result[1:])


def test_expected_benefits_split_compound_free_text_nfrs() -> None:
    text = """\
Project Title:
University Portal

Main Features:
- Students can register in available courses

Expected Benefits:
The system must be highly available, encrypted, mobile-friendly, and responsive under peak load.
"""

    result = BriefParser().parse(text)
    nfr_texts = [item.text.casefold() for item in result[1:]]

    assert len(result) == 5
    assert any("high availability" in item for item in nfr_texts)
    assert any("encrypt sensitive data" in item for item in nfr_texts)
    assert any("mobile-friendly" in item for item in nfr_texts)
    assert any("peak load" in item for item in nfr_texts)


def test_non_functional_plain_text_keeps_localization_as_single_requirement() -> None:
    text = """\
Project Title:
Clinic System

Main Features:
- Register patients

Non-Functional Requirements:
The system must support Arabic and English with RTL layout for Arabic.
"""

    result = BriefParser().parse(text)
    nfr_items = result[1:]

    assert len(nfr_items) == 1
    assert "arabic and english" in nfr_items[0].text.casefold()
    assert "rtl layout" in nfr_items[0].text.casefold()


def test_non_functional_plain_text_preserves_thousands_separator_in_scalability_requirement() -> None:
    text = """\
Project Title:
E-Commerce Platform

Main Features:
- Product catalog with search and filters

Non-Functional Requirements:
Scalable to 10,000 concurrent users, PCI-DSS compliant, mobile-first.
"""

    result = BriefParser().parse(text)
    nfr_texts = [item.text.casefold() for item in result[1:]]

    assert len(nfr_texts) == 3
    assert any("10,000 concurrent users" in item for item in nfr_texts)
    assert not any("scalable to 10." in item for item in nfr_texts)
    assert any("pci-dss" in item for item in nfr_texts)
    assert any("mobile-first" in item for item in nfr_texts)


def test_non_functional_plain_text_normalizes_bare_offline_capability_requirement() -> None:
    text = """\
Project Title:
Mobile Banking App

Main Features:
- Users can transfer funds between accounts

Non-Functional Requirements:
Offline capability.
"""

    result = BriefParser().parse(text)

    assert len(result) == 2
    assert "support offline capability" in result[1].text.casefold()


def test_empty_bullet_lines_are_skipped() -> None:
    text = """\
Project Title:
Clinic System

Main Features:
- Feature A
-   
- Feature B
"""

    result = BriefParser().parse(text)

    assert len(result) == 2


def test_cli_brief_format_produces_tasks_json() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sample_input = project_root / "data" / "raw" / "docs" / "project_brief_sample.txt"
    tasks_output = project_root / "data" / "processed" / "tasks.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.pipelines.doc_to_tasks",
            "--format",
            "brief",
            "--input",
            str(sample_input),
            "--force-fallback",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert tasks_output.exists()

    payload = json.loads(tasks_output.read_text(encoding="utf-8"))
    assert payload["tasks"]
