from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from src.agents.planner import RequirementItem
from src.parsers.template_parser import TemplateParser, TemplateValidationError


def test_parse_single_valid_block() -> None:
    text = """\
[REQ-01]
Type: Functional
Description: The system must allow doctors to view patient records during consultation.
Actor: Doctor
Priority: High
Notes: Only assigned doctors can open the record.
"""

    items = TemplateParser().parse(text)

    assert len(items) == 1
    assert isinstance(items[0], RequirementItem)
    assert items[0].source == "REQ-01"
    assert "The system must allow doctors to view patient records during consultation." in items[0].text


def test_parse_multiple_blocks() -> None:
    text = """\
[REQ-01]
Description: The system must allow reception staff to register new patients safely.

[REQ-02]
Description: The system must let staff book patient appointments for doctors.

[REQ-03]
Description: The system must allow lab staff to upload patient test results.
"""

    items = TemplateParser().parse(text)

    assert len(items) == 3
    assert [item.source for item in items] == ["REQ-01", "REQ-02", "REQ-03"]


def test_parse_skips_block_with_no_description() -> None:
    text = """\
[REQ-01]
Description: The system must allow admins to manage user accounts securely.

[REQ-02]
Type: Functional
Actor: Admin
Priority: High
"""

    items = TemplateParser().parse(text)

    assert len(items) == 1
    assert items[0].source == "REQ-01"


def test_parse_actor_and_notes_appended() -> None:
    text = """\
[REQ-01]
Description: The system must allow doctors to approve treatment plans safely.
Actor: Doctor
Notes: must validate format
"""

    items = TemplateParser().parse(text)

    assert len(items) == 1
    assert "Doctor" in items[0].text
    assert "must validate format" in items[0].text


def test_validation_rejects_invalid_type() -> None:
    text = """\
[REQ-01]
Type: Maybe
Description: The system must allow patients to book appointments online safely.
"""

    with pytest.raises(TemplateValidationError) as exc_info:
        TemplateParser().parse(text)

    assert "REQ-01" in str(exc_info.value)
    assert "Type" in str(exc_info.value)


def test_validation_rejects_invalid_priority() -> None:
    text = """\
[REQ-01]
Priority: Critical
Description: The system must allow reception staff to schedule clinic appointments properly.
"""

    with pytest.raises(TemplateValidationError) as exc_info:
        TemplateParser().parse(text)

    assert "REQ-01" in str(exc_info.value)
    assert "Priority" in str(exc_info.value)


def test_validation_rejects_short_description() -> None:
    text = """\
[REQ-01]
Description: Login
"""

    with pytest.raises(TemplateValidationError) as exc_info:
        TemplateParser().parse(text)

    assert "REQ-01" in str(exc_info.value)
    assert "short" in str(exc_info.value)


def test_validation_rejects_empty_file() -> None:
    with pytest.raises(TemplateValidationError):
        TemplateParser().parse("")


def test_parse_case_insensitive_keys() -> None:
    text = """\
[REQ-01]
type: Functional
DESCRIPTION: The system must allow doctors to view laboratory results before treatment.
AcToR: Doctor
priority: High
"""

    items = TemplateParser().parse(text)

    assert len(items) == 1
    assert items[0].source == "REQ-01"


def test_pipeline_cli_format_flag() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sample_input = project_root / "data" / "raw" / "docs" / "requirements_template_sample.txt"
    tasks_output = project_root / "data" / "processed" / "tasks.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.pipelines.doc_to_tasks",
            "--input",
            str(sample_input),
            "--format",
            "template",
            "--force-fallback",
            "--allow-fallback",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert tasks_output.exists()

    tasks_payload = json.loads(tasks_output.read_text(encoding="utf-8"))
    assert "tasks" in tasks_payload
    assert len(tasks_payload["tasks"]) >= 1
