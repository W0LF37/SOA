from __future__ import annotations

from dataclasses import dataclass
import json

import pytest

from src.pipelines import admin_review
from src.pipelines.doc_to_tasks import build_review_queue


@dataclass
class DummyTask:
    id: str
    title: str
    description: str
    source: str
    confidence: str = "high"
    optional: bool = False


@dataclass
class DummyTaskList:
    tasks: list[DummyTask]


@pytest.fixture
def isolated_admin_paths(tmp_path):
    original_summary = admin_review.DEFAULT_SUMMARY_PATH
    original_queue = admin_review.DEFAULT_REVIEW_QUEUE_PATH
    admin_review.DEFAULT_SUMMARY_PATH = tmp_path / "plan_summary.json"
    admin_review.DEFAULT_REVIEW_QUEUE_PATH = tmp_path / "admin_review_queue.json"
    try:
        yield tmp_path
    finally:
        admin_review.DEFAULT_SUMMARY_PATH = original_summary
        admin_review.DEFAULT_REVIEW_QUEUE_PATH = original_queue


def test_build_review_queue_flags_low_confidence() -> None:
    task_list = DummyTaskList(
        tasks=[
            DummyTask(
                id="T001",
                title="Implement patient registration workflow",
                description="Register patients.",
                source="REQ-01",
                confidence="low",
            )
        ]
    )

    result = build_review_queue(task_list, {})

    assert len(result) == 1
    assert result[0]["task_id"] == "T001"
    assert "low-confidence" in result[0]["reason"]


def test_build_review_queue_flags_unclear_title() -> None:
    task_list = DummyTaskList(
        tasks=[
            DummyTask(
                id="T001",
                title="Implement [UNCLEAR — requires clarification]",
                description="Unclear requirement.",
                source="REQ-01",
            )
        ]
    )

    result = build_review_queue(task_list, {})

    assert len(result) == 1
    assert "unclear" in result[0]["reason"].lower()


def test_build_review_queue_flags_optional() -> None:
    task_list = DummyTaskList(
        tasks=[
            DummyTask(
                id="T001",
                title="Implement ambulance tracking workflow",
                description="Optional ambulance tracking.",
                source="REQ-01",
                confidence="low",
                optional=True,
            )
        ]
    )

    result = build_review_queue(task_list, {})

    assert len(result) == 1
    assert "optional" in result[0]["reason"].lower()


def test_build_review_queue_skips_confirmed_tasks() -> None:
    task_list = DummyTaskList(
        tasks=[
            DummyTask(
                id="T001",
                title="Implement patient registration workflow",
                description="Confirmed task.",
                source="REQ-01",
                confidence="high",
                optional=False,
            ),
            DummyTask(
                id="T002",
                title="Implement ambulance tracking workflow",
                description="Needs review.",
                source="REQ-02",
                confidence="low",
                optional=False,
            ),
        ]
    )

    result = build_review_queue(task_list, {})

    assert len(result) == 1
    assert result[0]["task_id"] == "T002"


def test_finalize_tasks_removes_rejected(isolated_admin_paths) -> None:
    tmp_path = isolated_admin_paths
    tasks_path = tmp_path / "tasks.json"
    decisions_path = tmp_path / "decisions.json"
    output_path = tmp_path / "tasks_final.json"

    tasks_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "T001", "title": "Task 1", "dependencies": []},
                    {"id": "T002", "title": "Task 2", "dependencies": []},
                    {"id": "T003", "title": "Task 3", "dependencies": []},
                ]
            }
        ),
        encoding="utf-8",
    )
    decisions_path.write_text(
        json.dumps(
            {
                "reviewed_at": "2026-04-13T00:00:00+00:00",
                "decisions": [
                    {"task_id": "T002", "action": "rejected", "new_title": None}
                ],
            }
        ),
        encoding="utf-8",
    )

    admin_review.finalize_tasks(decisions_path, tasks_path, output_path)

    output = json.loads(output_path.read_text(encoding="utf-8"))
    output_ids = [task["id"] for task in output["tasks"]]
    assert len(output["tasks"]) == 2
    assert "T002" not in output_ids


def test_finalize_tasks_removes_rejected_from_dependencies(isolated_admin_paths) -> None:
    tmp_path = isolated_admin_paths
    tasks_path = tmp_path / "tasks.json"
    decisions_path = tmp_path / "decisions.json"
    output_path = tmp_path / "tasks_final.json"

    tasks_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "T001", "title": "Task 1", "dependencies": []},
                    {"id": "T002", "title": "Task 2", "dependencies": []},
                    {"id": "T003", "title": "Task 3", "dependencies": ["T001", "T002"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    decisions_path.write_text(
        json.dumps(
            {
                "reviewed_at": "2026-04-13T00:00:00+00:00",
                "decisions": [
                    {"task_id": "T002", "action": "rejected", "new_title": None}
                ],
            }
        ),
        encoding="utf-8",
    )

    admin_review.finalize_tasks(decisions_path, tasks_path, output_path)

    output = json.loads(output_path.read_text(encoding="utf-8"))
    task_t003 = next(task for task in output["tasks"] if task["id"] == "T003")
    assert task_t003["dependencies"] == ["T001"]


def test_finalize_tasks_updates_edited_title(isolated_admin_paths) -> None:
    tmp_path = isolated_admin_paths
    tasks_path = tmp_path / "tasks.json"
    decisions_path = tmp_path / "decisions.json"
    output_path = tmp_path / "tasks_final.json"

    tasks_path.write_text(
        json.dumps({"tasks": [{"id": "T001", "title": "Old Title", "dependencies": []}]}),
        encoding="utf-8",
    )
    decisions_path.write_text(
        json.dumps(
            {
                "reviewed_at": "2026-04-13T00:00:00+00:00",
                "decisions": [
                    {"task_id": "T001", "action": "edited", "new_title": "New Title"}
                ],
            }
        ),
        encoding="utf-8",
    )

    admin_review.finalize_tasks(decisions_path, tasks_path, output_path)

    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["tasks"][0]["title"] == "New Title"


def test_empty_queue_produces_no_review_file() -> None:
    task_list = DummyTaskList(
        tasks=[
            DummyTask(
                id="T001",
                title="Implement patient registration workflow",
                description="Confirmed task.",
                source="REQ-01",
                confidence="high",
                optional=False,
            ),
            DummyTask(
                id="T002",
                title="Implement appointments workflow",
                description="Confirmed task.",
                source="REQ-02",
                confidence="high",
                optional=False,
            ),
        ]
    )

    result = build_review_queue(task_list, {})

    assert result == []
