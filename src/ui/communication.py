from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MESSAGES_PATH = PROJECT_ROOT / "storage" / "messages.json"
DEDUP_WINDOW = timedelta(seconds=10)

Role = Literal["Student", "Supervisor"]


def _empty_store() -> dict[str, Any]:
    return {"messages": [], "plan_status": "pending", "updated_at": None}


def _load_store() -> dict[str, Any]:
    if not MESSAGES_PATH.exists():
        return _empty_store()
    try:
        data = json.loads(MESSAGES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("messages", [])
    data.setdefault("plan_status", "pending")
    data.setdefault("updated_at", None)
    if isinstance(data["messages"], list):
        data["messages"] = _dedupe_messages(data["messages"])
    return data


def _save_store(data: dict[str, Any]) -> None:
    MESSAGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    MESSAGES_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _normalise_message_text(text: str) -> str:
    return " ".join(text.strip().split()).casefold()


def _message_dt(message: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(message.get("created_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return None


def _same_message(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("role") == right.get("role")
        and left.get("type") == right.get("type")
        and _normalise_message_text(str(left.get("text", "")))
        == _normalise_message_text(str(right.get("text", "")))
    )


def _is_recent_duplicate(existing: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if not _same_message(existing, candidate):
        return False
    existing_dt = _message_dt(existing)
    candidate_dt = _message_dt(candidate)
    if existing_dt is None or candidate_dt is None:
        return True
    return abs(candidate_dt - existing_dt) <= DEDUP_WINDOW


def _dedupe_messages(messages: list[Any]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        if deduped and _is_recent_duplicate(deduped[-1], item):
            continue
        deduped.append(item)
    return deduped


def _append_message(data: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    messages = data.setdefault("messages", [])
    if not isinstance(messages, list):
        messages = []
        data["messages"] = messages
    if messages and _is_recent_duplicate(messages[-1], message):
        return messages[-1]
    messages.append(message)
    return message


def send_message(role: Role, text: str) -> dict[str, Any]:
    message_text = text.strip()
    if not message_text:
        raise ValueError("Message cannot be empty.")
    data = _load_store()
    message = {
        "id": uuid.uuid4().hex,
        "role": role,
        "type": "message",
        "text": message_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    message = _append_message(data, message)
    _save_store(data)
    return message


def get_messages() -> list[dict[str, Any]]:
    messages = _load_store().get("messages", [])
    if not isinstance(messages, list):
        return []
    return messages


def approve_plan(role: Role = "Supervisor", comment: str = "") -> dict[str, Any]:
    data = _load_store()
    data["plan_status"] = "approved"
    message = {
        "id": uuid.uuid4().hex,
        "role": role,
        "type": "approval",
        "text": comment.strip() or "Plan approved.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    message = _append_message(data, message)
    _save_store(data)
    return message


def reject_plan(role: Role = "Supervisor", comment: str = "") -> dict[str, Any]:
    data = _load_store()
    data["plan_status"] = "rejected"
    message = {
        "id": uuid.uuid4().hex,
        "role": role,
        "type": "rejection",
        "text": comment.strip() or "Plan rejected.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    message = _append_message(data, message)
    _save_store(data)
    return message


def get_plan_status() -> str:
    return str(_load_store().get("plan_status", "pending"))
