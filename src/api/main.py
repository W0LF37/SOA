from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import (
    admin,
    ai_explain,
    chat,
    data,
    evaluate,
    export,
    feedback,
    kb,
    monitor,
    pipeline,
    progress,
)


VERSION = "1.0.0"


def create_app() -> FastAPI:
    app = FastAPI(
        title="CritiPlan API",
        description="Multi-agent AI project planning system — Graduation Project",
        version=VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8501",
            "http://127.0.0.1:8501",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION}

    app.include_router(data.router, prefix="/api/data", tags=["Data"])
    app.include_router(pipeline.router, prefix="/api/pipeline", tags=["Pipeline"])
    app.include_router(monitor.router, prefix="/api/monitor", tags=["Monitor"])
    app.include_router(chat.router, prefix="/api/chat", tags=["Communication"])
    app.include_router(admin.router, prefix="/api/admin", tags=["Admin Review"])
    app.include_router(evaluate.router, prefix="/api/evaluate", tags=["Evaluation"])
    app.include_router(kb.router, prefix="/api/kb", tags=["Knowledge Base"])
    app.include_router(ai_explain.router, prefix="/api/ai", tags=["AI Explain"])
    app.include_router(feedback.router, prefix="/api/feedback", tags=["Feedback"])
    app.include_router(progress.router, prefix="/api/progress", tags=["Progress"])
    app.include_router(export.router, prefix="/api/export", tags=["Export"])
    return app


app = create_app()
