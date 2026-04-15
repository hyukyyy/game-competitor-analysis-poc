from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.competitors import router as competitors_router
from .routes.feedback import router as feedback_router
from .routes.reports import router as reports_router

app = FastAPI(
    title="Game Competitor Analysis API",
    description="Weekly competitor analysis for games — read-only except POST /feedback.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(competitors_router, tags=["Competitors"])
app.include_router(feedback_router,    tags=["Feedback"])
app.include_router(reports_router,     tags=["Reports"])


@app.get("/health", tags=["Meta"])
def health() -> dict:
    return {"status": "ok"}
