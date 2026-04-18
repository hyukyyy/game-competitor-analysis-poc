from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...db import connect

router = APIRouter()


class AddMyGameIn(BaseModel):
    platform: str = "steam"
    appid: str


@router.post("/games/my", status_code=201)
def add_my_game(body: AddMyGameIn) -> dict:
    """Register a game as 'my game' (PM analysis target).

    Currently only Steam is supported. Fetches the game metadata from Steam,
    normalizes it, and upserts into games with is_my_game=TRUE.
    """
    if body.platform != "steam":
        raise HTTPException(
            status_code=400,
            detail=f"platform '{body.platform}' not yet supported; use 'steam'",
        )

    # Local imports so API startup doesn't pull heavy collector deps until needed.
    from ...collectors.steam import SteamCollector, SteamCollectorError
    from ...pipeline import normalize as normalize_mod

    ext_id = str(body.appid).strip()
    if not ext_id:
        raise HTTPException(status_code=400, detail="appid is required")

    try:
        with SteamCollector() as c:
            game = c.fetch_game(ext_id)
    except SteamCollectorError as e:
        raise HTTPException(status_code=404, detail=f"fetch failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"collector error: {e}")

    ng = normalize_mod.extract_normalized(body.platform, game.payload)
    if not ng.external_id:
        raise HTTPException(status_code=500, detail="could not normalize payload")

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_games (platform, external_id, payload, collected_at)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT DO NOTHING
            """,
            (game.platform, game.external_id, json.dumps(game.payload)),
        )
        cur.execute(
            """
            INSERT INTO games (platform, external_id, title, description, raw_tags,
                               is_my_game, updated_at)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
            ON CONFLICT (platform, external_id) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                raw_tags = EXCLUDED.raw_tags,
                is_my_game = TRUE,
                updated_at = NOW()
            RETURNING id, platform, external_id, title, is_my_game
            """,
            (ng.platform, ng.external_id, ng.title, ng.description, ng.raw_tags),
        )
        row = cur.fetchone()
        conn.commit()

    return dict(row)


@router.get("/games")
def list_games(
    platform: str | None = Query(None),
    mine: bool = Query(False, description="Only return PM-registered 'my games'"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
) -> list[dict]:
    """List normalized games, optionally filtered by platform or 'my game' flag."""
    clauses: list[str] = []
    params: list = []
    if platform:
        clauses.append("platform = %s")
        params.append(platform)
    if mine:
        clauses.append("is_my_game = TRUE")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    sql = (
        f"SELECT id, platform, external_id, title, is_my_game "
        f"FROM games {where} ORDER BY is_my_game DESC, id LIMIT %s OFFSET %s"
    )
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
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
