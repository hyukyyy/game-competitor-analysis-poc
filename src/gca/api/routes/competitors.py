from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, HTTPException, Query

from ...db import connect

router = APIRouter()


@router.get("/games")
def list_games(
    platform: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
) -> list[dict]:
    """List normalized games, optionally filtered by platform."""
    with connect() as conn:
        if platform:
            rows = conn.execute(
                "SELECT id, platform, external_id, title FROM games WHERE platform = %s LIMIT %s OFFSET %s",
                [platform, limit, offset],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, platform, external_id, title FROM games LIMIT %s OFFSET %s",
                [limit, offset],
            ).fetchall()
    return [dict(r) for r in rows]


@router.get("/competitors")
def get_competitors(
    base_game_id: int,
    week_of: dt.date | None = Query(None),
    limit: int = Query(20, le=50),
) -> dict:
    """Return top competitors for a given game and week.

    If week_of is omitted, returns the most recent week available.
    """
    with connect() as conn:
        # Resolve week_of
        if week_of is None:
            row = conn.execute(
                "SELECT MAX(week_of) AS w FROM game_similarities_weekly WHERE base_game_id = %s",
                [base_game_id],
            ).fetchone()
            if not row or row["w"] is None:
                raise HTTPException(status_code=404, detail="No similarity data for this game")
            week_of = row["w"]

        # Base game metadata
        base = conn.execute(
            "SELECT id, platform, title FROM games WHERE id = %s", [base_game_id]
        ).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Base game not found")

        # Top competitors
        rows = conn.execute(
            """
            SELECT
                gsw.target_game_id, gsw.similarity_score, gsw.rank,
                gsw.component_scores,
                g.title, g.platform, g.external_id
            FROM game_similarities_weekly gsw
            JOIN games g ON g.id = gsw.target_game_id
            WHERE gsw.base_game_id = %s AND gsw.week_of = %s
            ORDER BY gsw.rank
            LIMIT %s
            """,
            [base_game_id, week_of, limit],
        ).fetchall()

    competitors = []
    for r in rows:
        comps = r["component_scores"]
        if isinstance(comps, str):
            comps = json.loads(comps)
        competitors.append({
            "rank":             r["rank"],
            "game_id":          r["target_game_id"],
            "title":            r["title"],
            "platform":         r["platform"],
            "external_id":      r["external_id"],
            "similarity_score": round(r["similarity_score"], 4),
            "component_scores": comps,
        })

    return {
        "base_game": {"id": base["id"], "platform": base["platform"], "title": base["title"]},
        "week_of":   str(week_of),
        "competitors": competitors,
    }
