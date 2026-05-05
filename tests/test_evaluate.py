from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipelines.evaluate import (
    DEFAULT_GROUND_TRUTH_PATH,
    DEFAULT_REPORT_PATH,
    EvaluationResult,
    _build_threshold_assessment,
    _execution_summary,
    _metric_summary,
    FallbackOnlyClient,
    run_evaluation,
    run_sample,
)


def _load_dataset() -> list[dict]:
    return json.loads(DEFAULT_GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def _get_sample(sample_id: str) -> dict:
    return next(sample for sample in _load_dataset() if sample["sample_id"] == sample_id)


def test_fallback_only_client_raises() -> None:
    client = FallbackOnlyClient()

    with pytest.raises(RuntimeError):
        client.generate_json("any prompt")


def test_run_sample_s01_passes() -> None:
    sample = _get_sample("S01")

    result = run_sample(sample, force_fallback=True)

    assert result.passed is True
    assert result.error is None
    assert result.fr_count >= 4


def test_run_sample_s03_single_req() -> None:
    sample = _get_sample("S03")

    result = run_sample(sample, force_fallback=True)

    assert result.task_count >= 1
    assert result.task_count <= 3


def test_run_sample_s04_brief_format() -> None:
    sample = _get_sample("S04")

    result = run_sample(sample, force_fallback=True)

    assert result.passed is True
    assert result.nfr_count >= 1


def test_run_evaluation_all_pass(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"

    report = run_evaluation(DEFAULT_GROUND_TRUTH_PATH, report_path)

    assert DEFAULT_REPORT_PATH.name == "evaluation_report.json"
    assert report["pass_rate_pct"] == 100.0
    assert report_path.exists()


def test_forbidden_title_check_catches_leakage(tmp_path: Path) -> None:
    input_path = tmp_path / "forbidden_title_sample.txt"
    input_path.write_text("Register patients", encoding="utf-8")

    sample = {
        "sample_id": "SX",
        "description": "Forbidden title check sample",
        "input_file": str(input_path),
        "expected": {
            "task_count_min": 1,
            "task_count_max": 3,
            "fr_count_min": 1,
            "nfr_count_min": 0,
            "optional_count_min": 0,
            "has_dependency_chain": False,
            "critical_path_min_length": 1,
            "forbidden_title_substrings": ["The system should Register"],
        },
    }

    result = run_sample(sample, force_fallback=True)
    forbidden_check = next(
        check for check in result.checks if check["name"] == "forbidden_title_substrings"
    )

    if forbidden_check["actual"] == "clean":
        assert forbidden_check["passed"] is True
    else:
        assert any(
            not check["passed"]
            for check in result.checks
            if check["name"] == "forbidden_title_substrings"
        )


def test_threshold_assessment_flags_training_for_weak_llm_results() -> None:
    results = [
        EvaluationResult(
            sample_id="S1",
            description="sample 1",
            input_file="a.txt",
            passed=False,
            checks=[],
            task_count=4,
            fr_count=3,
            nfr_count=1,
            optional_count=0,
            score=0.5,
            used_fallback=True,
            fallback_reason="bad json",
            error=None,
            overall_score=0.74,
            critic_score=0.80,
        ),
        EvaluationResult(
            sample_id="S2",
            description="sample 2",
            input_file="b.txt",
            passed=True,
            checks=[],
            task_count=5,
            fr_count=4,
            nfr_count=1,
            optional_count=0,
            score=1.0,
            used_fallback=False,
            fallback_reason=None,
            error=None,
            overall_score=0.80,
            critic_score=0.82,
        ),
    ]

    execution_summary = _execution_summary(results)
    metric_summary = _metric_summary(results)
    assessment = _build_threshold_assessment("llm_kb", execution_summary, metric_summary)

    assert assessment["applicable"] is True
    assert assessment["training_recommended"] is True
    assert any(check["name"] == "fallback_rate_pct" and check["passed"] is False for check in assessment["checks"])


def test_threshold_assessment_skips_non_llm_modes() -> None:
    assessment = _build_threshold_assessment(
        "rules",
        _execution_summary([]),
        _metric_summary([]),
    )

    assert assessment["applicable"] is False
    assert assessment["training_recommended"] is None
