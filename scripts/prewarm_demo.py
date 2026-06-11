from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


API_BASE = os.environ.get("CRITIPLAN_API_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")
UI_BASE = os.environ.get("CRITIPLAN_UI_BASE_URL", "http://127.0.0.1:5173").rstrip("/")


def _request_json(url: str, payload: dict | None = None) -> dict:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return parsed


def _request_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.read(512).decode("utf-8", errors="ignore")


def _wait_for(url: str, label: str, timeout_seconds: int = 90) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            _request_text(url)
            print(f"[warmup] {label} ready")
            return
        except Exception as exc:  # pragma: no cover - best effort runtime helper
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"{label} did not respond in time: {last_error}")


def _print_progress(title: str) -> None:
    print(f"[warmup] {title}")


def main() -> int:
    try:
        _wait_for(f"{API_BASE}/health", "API", timeout_seconds=120)
        _wait_for(f"{UI_BASE}/login", "Frontend", timeout_seconds=120)

        _print_progress("Loading dashboard data")
        data = _request_json(f"{API_BASE}/data/all")
        task_count = len(((data.get("tasks") or {}).get("tasks")) or [])
        print(f"[warmup] Loaded {task_count} task(s)")

        _print_progress("Loading committee brief")
        _request_json(f"{API_BASE}/data/brief")

        _print_progress("Loading communication state")
        _request_json(f"{API_BASE}/chat/messages")

        _print_progress("Precomputing monitor report")
        monitor = _request_json(
            f"{API_BASE}/monitor/analyze",
            {"repo_path": None, "use_semantic": True},
        )
        progress = round(float(monitor.get("overall_progress", 0)) * 100)
        commits = int(monitor.get("commits_analyzed", 0) or 0)
        print(f"[warmup] Monitor cached at {progress}% from {commits} commit(s)")

        _print_progress("Precomputing AI insights")
        explain = _request_json(
            f"{API_BASE}/ai/explain",
            {
                "context_type": "critic",
                "item_id": "plan",
                "question": (
                    "Summarize this project plan in 3 bullet points for an academic supervisor. "
                    "Focus on quality score, key risks, and critical path."
                ),
            },
        )
        explanation = str(explain.get("explanation", "")).strip()
        if explanation:
            first_line = explanation.splitlines()[0].strip()
            print(f"[warmup] AI insights ready: {first_line[:100]}")

        _print_progress("Checking presentation routes")
        for route in ("/dashboard", "/monitor", "/brief", "/plan"):
            _request_text(f"{UI_BASE}{route}")
            print(f"[warmup] Route OK: {route}")

        print("[warmup] Presentation cache is ready")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"[warmup] HTTP error {exc.code}: {exc.reason}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - best effort runtime helper
        print(f"[warmup] Failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
