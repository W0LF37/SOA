from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.ui.communication import (
    MESSAGES_PATH,
    approve_plan,
    get_messages,
    get_plan_status,
    reject_plan,
    send_message,
)


router = APIRouter()


class MessageRequest(BaseModel):
    role: Literal["Student", "Supervisor"]
    text: str


class DecisionRequest(BaseModel):
    role: Literal["Supervisor"] = "Supervisor"
    comment: str = ""


@router.get("/messages")
def messages() -> dict[str, Any]:
    return {"messages": get_messages(), "plan_status": get_plan_status()}


@router.post("/messages")
def create_message(payload: MessageRequest) -> dict[str, Any]:
    try:
        return send_message(payload.role, payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/messages")
def clear_messages() -> dict[str, str]:
    data = {"messages": [], "plan_status": "pending"}
    MESSAGES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "cleared"}


@router.post("/approve")
def approve(payload: DecisionRequest) -> dict[str, Any]:
    return approve_plan(payload.role, payload.comment)


@router.post("/reject")
def reject(payload: DecisionRequest) -> dict[str, Any]:
    return reject_plan(payload.role, payload.comment)


@router.get("/status")
def status() -> dict[str, str]:
    return {"plan_status": get_plan_status()}
