from __future__ import annotations

import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
TASKS_PATH = PROJECT_ROOT / "data" / "processed" / "tasks.json"


def main() -> int:
    if not TASKS_PATH.exists():
        print(
            "ERROR: data/processed/tasks.json was not found. "
            "Generate that file before starting the dashboard.",
            file=sys.stderr,
        )
        return 1

    if find_spec("streamlit") is None:
        print(
            "ERROR: Streamlit is not installed in this Python environment. "
            "Install it with: python -m pip install streamlit",
            file=sys.stderr,
        )
        return 1

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "src/ui/app.py",
        "--server.headless",
        "true",
    ]
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
