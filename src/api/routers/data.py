from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from src.core.runtime_paths import prepare_writable_file_path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TASKS_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks.json")
SUMMARY_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/plan_summary.json")
RISK_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/risk_report.json")
GRAPH_PATH = prepare_writable_file_path(PROJECT_ROOT, "storage/graph/dependency_graph.json")
MONITOR_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/monitor_report.json")

router = APIRouter()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        try:
            display = path.relative_to(PROJECT_ROOT)
        except ValueError:
            display = path
        raise HTTPException(status_code=404, detail=f"Missing file: {display}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail=f"Expected object JSON in {path.name}")
    return data


@router.get("/tasks")
def tasks() -> dict[str, Any]:
    return read_json(TASKS_PATH)


@router.get("/summary")
def summary() -> dict[str, Any]:
    return read_json(SUMMARY_PATH)


@router.get("/risks")
def risks() -> dict[str, Any]:
    return read_json(RISK_PATH)


@router.get("/graph")
def graph() -> dict[str, Any]:
    return read_json(GRAPH_PATH)


@router.get("/monitor")
def monitor_report() -> dict[str, Any]:
    return read_json(MONITOR_PATH)


@router.get("/brief")
def brief() -> dict[str, Any]:
    summary = read_json(SUMMARY_PATH)
    return {
        "committee_brief": summary.get("committee_brief", {}),
        "team_allocation": summary.get("team_allocation", []),
        "risk_register": summary.get("risk_register", []),
        "effort_summary": summary.get("effort_summary", {}),
        "plan_highlights": summary.get("plan_highlights", {}),
        "admin_review": summary.get("admin_review"),
        "critic": summary.get("critic", {}),
        "generated_at": summary.get("generated_at"),
        "model": summary.get("model"),
        "generation_mode": summary.get("generation_mode"),
    }


@router.get("/tech-stack")
def tech_stack() -> dict[str, Any]:
    data = read_json(TASKS_PATH)
    ts = data.get("tech_stack")
    if not ts:
        return {"frontend": [], "backend": [], "database": [], "devops": [], "external_services": [], "detected_from": "requirements"}
    return ts


@router.get("/all")
def all_data() -> dict[str, Any]:
    def optional(path: Path) -> dict[str, Any] | None:
        try:
            return read_json(path)
        except HTTPException:
            return None

    return {
        "tasks": optional(TASKS_PATH),
        "summary": optional(SUMMARY_PATH),
        "risks": optional(RISK_PATH),
        "graph": optional(GRAPH_PATH),
        "monitor": optional(MONITOR_PATH),
    }
