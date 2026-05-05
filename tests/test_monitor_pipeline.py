from __future__ import annotations

import json

from src.pipelines.run_monitor import DEFAULT_REPORT_PATH, main


def test_run_monitor_creates_valid_report_json() -> None:
    main([])

    assert DEFAULT_REPORT_PATH.exists()
    payload = json.loads(DEFAULT_REPORT_PATH.read_text(encoding="utf-8"))

    assert "overall_progress" in payload
    assert "task_statuses" in payload
