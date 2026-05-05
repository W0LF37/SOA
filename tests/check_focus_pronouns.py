from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.planner import PlannerAgent


CASES = [
    "Export them as CSV",
    "Archive it after 90 days",
    "Show it in the dashboard",
    "Provide these as weekly summaries",
    "Track those in the audit log",
    "Store this securely",
]

DISALLOWED = {"it", "them", "this", "these", "those", "that", "its", "their"}


def extract_without_pronoun_cleanup(text: str) -> str:
    original = PlannerAgent._PRONOUNS
    PlannerAgent._PRONOUNS = frozenset()
    try:
        return PlannerAgent._extract_focus_phrase(text)
    finally:
        PlannerAgent._PRONOUNS = original


def main() -> int:
    failures: list[str] = []

    for text in CASES:
        before = extract_without_pronoun_cleanup(text)
        after = PlannerAgent._extract_focus_phrase(text)
        first_token = after.split()[0].lower() if after.split() else ""
        ok = first_token not in DISALLOWED

        print(f"INPUT : {text}")
        print(f"BEFORE: {before!r}")
        print(f"AFTER : {after!r}")
        print(f"PASS  : {ok}")
        print()

        if not ok:
            failures.append(text)

    if failures:
        print("FAILED CASES:")
        for text in failures:
            print(f"- {text}")
        return 1

    print("All cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
