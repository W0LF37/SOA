from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.runtime_paths import prepare_writable_directory_path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHROMA_DIR = str(
    prepare_writable_directory_path(
        PROJECT_ROOT,
        "storage/chroma",
        anchor_filenames=("chroma.sqlite3",),
    )
)

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    n_results: int = 5


def _get_kb():
    try:
        from src.kb.vector_store import get_kb  # type: ignore[import]
        return get_kb(persist_dir=CHROMA_DIR)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Knowledge Base unavailable: {exc}. Run: python -m src.kb.seed_cli",
        ) from exc


@router.get("/stats")
def kb_stats() -> dict[str, Any]:
    kb = _get_kb()
    try:
        count = kb.count()
        collection_name = kb.collection.name
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "count": count,
        "collection_name": collection_name,
        "persist_dir": CHROMA_DIR,
        "status": "ready" if count > 0 else "empty",
    }


@router.post("/search")
def search_kb(body: SearchRequest) -> dict[str, Any]:
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    kb = _get_kb()
    try:
        results = kb.query(body.query, n_results=min(body.n_results, 20))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"query": body.query, "results": results, "count": len(results)}
