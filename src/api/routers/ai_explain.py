from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import requests as http_requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.runtime_paths import prepare_writable_file_path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TASKS_PATH   = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks.json")
RISK_PATH    = prepare_writable_file_path(PROJECT_ROOT, "data/processed/risk_report.json")
SUMMARY_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/plan_summary.json")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "ai-project-manager-planner"

router = APIRouter()


class ExplainRequest(BaseModel):
    context_type: Literal["task", "risk", "critic"]
    item_id: str
    question: str = "Why did the AI create this?"


class ExplainResponse(BaseModel):
    explanation: str
    item_id: str
    context_type: str


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def _call_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_ctx": 2048,
            "num_predict": 512,
        },
    }
    try:
        resp = http_requests.post(OLLAMA_URL, json=payload, timeout=90)
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        return _strip_think(raw)
    except http_requests.exceptions.ConnectionError as exc:
        raise HTTPException(status_code=503, detail="Ollama is not running. Start it with: ollama serve") from exc
    except http_requests.exceptions.Timeout as exc:
        raise HTTPException(status_code=504, detail="Ollama timed out generating explanation.") from exc


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path.name}. Run the pipeline first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _build_prompt(req: ExplainRequest) -> str:
    if req.context_type == "task":
        data = _load_json(TASKS_PATH)
        tasks = data.get("tasks", [])
        task = next((t for t in tasks if t.get("id") == req.item_id), None)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {req.item_id} not found.")
        deps = ", ".join(task.get("dependencies", [])) or "none"
        return (
            "You are CritiPlan, an AI project planning system. "
            "A student is asking why a task was created.\n\n"
            f"TASK: {task.get('id')} — {task.get('title')}\n"
            f"Type: {task.get('req_type')} | Complexity: C{task.get('complexity')} "
            f"| Estimated: {task.get('estimated_hours')}h\n"
            f"Description: {task.get('description', '')}\n"
            f"Dependencies: {deps}\n"
            f"Skill Required: {task.get('skill_required', 'N/A')}\n\n"
            f"STUDENT'S QUESTION: {req.question}\n\n"
            "Answer in 2-3 sentences. Be specific about why this task exists, "
            "how complexity was determined, and what it delivers. Plain English only."
        )

    if req.context_type == "risk":
        data = _load_json(RISK_PATH)
        risks = data.get("risks", [])
        try:
            idx = int(req.item_id)
            risk = risks[idx]
        except (ValueError, IndexError) as exc:
            raise HTTPException(status_code=404, detail=f"Risk index {req.item_id} not found.") from exc
        affected = ", ".join(risk.get("affected_tasks", [])) or "none"
        return (
            "You are CritiPlan. A user is asking about a risk indicator.\n\n"
            f"RISK: {risk.get('message')}\n"
            f"Category: {risk.get('category')} | Severity: {risk.get('severity')}\n"
            f"Affected Tasks: {affected}\n"
            f"Suggested Mitigation: {risk.get('mitigation', '')}\n\n"
            f"USER'S QUESTION: {req.question}\n\n"
            "Answer in 2-3 sentences explaining why this risk exists and what "
            "concrete action should be taken. Plain English only."
        )

    # critic
    data = _load_json(SUMMARY_PATH)
    critic = data.get("critic", {})
    highlights = data.get("plan_highlights", {})
    task_count = highlights.get("task_count", "unknown")
    return (
        "You are CritiPlan. A supervisor is asking about the critic agent's validation result.\n\n"
        f"CRITIC RESULT: {critic.get('status', 'unknown')} (score: {critic.get('score', 'N/A')})\n"
        f"Total tasks validated: {task_count}\n"
        f"Issues count: {critic.get('issues_count', 0)}\n\n"
        f"QUESTION: {req.question}\n\n"
        "Answer in 2-3 bullet points summarizing the key findings about this plan "
        "for an academic supervisor. Focus on quality, notable risks, and AI confidence. "
        "Plain English only."
    )


@router.post("/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest) -> ExplainResponse:
    prompt = _build_prompt(req)
    explanation = _call_ollama(prompt)
    return ExplainResponse(explanation=explanation, item_id=req.item_id, context_type=req.context_type)
