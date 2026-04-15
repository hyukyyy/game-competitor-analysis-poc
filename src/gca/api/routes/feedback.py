from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ...db import connect

router = APIRouter()

_VALID_SIGNALS = {"upvote", "downvote", "clicked", "added"}


class FeedbackIn(BaseModel):
    base_game_id:   int
    target_game_id: int
    week_of:        dt.date
    signal:         str
    user_id:        str | None = None

    @field_validator("signal")
    @classmethod
    def signal_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_SIGNALS:
            raise ValueError(f"signal must be one of {_VALID_SIGNALS}")
        return v


@router.post("/feedback", status_code=201)
def post_feedback(body: FeedbackIn) -> dict:
    """Record a PM feedback signal (upvote/downvote/clicked/added)."""
    with connect() as conn:
        # Validate game IDs exist
        for gid in (body.base_game_id, body.target_game_id):
            row = conn.execute("SELECT id FROM games WHERE id = %s", [gid]).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"game_id {gid} not found")

        conn.execute(
            """
            INSERT INTO pm_feedback
                (base_game_id, target_game_id, week_of, signal, user_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [body.base_game_id, body.target_game_id, body.week_of, body.signal, body.user_id],
        )
    return {"status": "ok"}


@router.get("/feedback/summary")
def feedback_summary(
    base_game_id: int,
    week_of: dt.date | None = None,
) -> list[dict]:
    """Return aggregated feedback counts per (target_game, signal) for a base game."""
    with connect() as conn:
        if week_of:
            rows = conn.execute(
                """
                SELECT target_game_id, signal, COUNT(*) AS n
                FROM pm_feedback
                WHERE base_game_id = %s AND week_of = %s
                GROUP BY target_game_id, signal
                ORDER BY n DESC
                """,
                [base_game_id, week_of],
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT target_game_id, signal, COUNT(*) AS n
                FROM pm_feedback
                WHERE base_game_id = %s
                GROUP BY target_game_id, signal
                ORDER BY n DESC
                """,
                [base_game_id],
            ).fetchall()
    return [dict(r) for r in rows]
