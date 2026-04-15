from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, HTTPException, Query

from ...db import connect
from ...report import weekly as weekly_mod

router = APIRouter()


@router.get("/reports")
def get_report(
    base_game_id: int,
    week_of: dt.date | None = Query(None),
    format: str = Query("json", pattern="^(json|markdown)$"),
) -> dict | str:
    """Return the weekly competitor report for a game.

    - format=json   → returns the raw report JSON
    - format=markdown → returns rendered Markdown
    """
    with connect() as conn:
        if week_of is None:
            row = conn.execute(
                "SELECT MAX(week_of) AS w FROM weekly_reports WHERE base_game_id = %s",
                [base_game_id],
            ).fetchone()
            if not row or row["w"] is None:
                raise HTTPException(status_code=404, detail="No report found for this game")
            week_of = row["w"]

        row = conn.execute(
            "SELECT content FROM weekly_reports WHERE base_game_id = %s AND week_of = %s",
            [base_game_id, week_of],
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    content = row["content"]
    if isinstance(content, str):
        content = json.loads(content)

    if format == "markdown":
        return {"markdown": weekly_mod.render_markdown(content)}

    return content


@router.post("/reports/generate", status_code=201)
def trigger_report(
    base_game_id: int,
    week_of: dt.date | None = Query(None),
    top_n: int = Query(10, le=20),
) -> dict:
    """On-demand report generation for a single game."""
    if week_of is None:
        today = dt.date.today()
        week_of = today - dt.timedelta(days=today.weekday())

    try:
        md = weekly_mod.generate_and_save(base_game_id, week_of, top_n=top_n)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")

    return {"status": "ok", "week_of": str(week_of), "chars": len(md)}
