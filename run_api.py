from __future__ import annotations

import uvicorn


def main() -> int:
    uvicorn.run(
        "src.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
