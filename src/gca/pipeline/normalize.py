from __future__ import annotations

from typing import Any

from ..db import connect
from ..logs import get_logger
from ..models import NormalizedGame

log = get_logger(__name__)


def extract_normalized(platform: str, payload: dict[str, Any]) -> NormalizedGame:
    """Platform-specific raw payload → NormalizedGame."""
    if platform == "steam":
        appid = payload.get("steam_appid") or payload.get("appid")
        tags = [
            g.get("description")
            for g in payload.get("genres") or []
            if isinstance(g, dict) and g.get("description")
        ]
        categories = [
            c.get("description")
            for c in payload.get("categories") or []
            if isinstance(c, dict) and c.get("description")
        ]
        return NormalizedGame(
            platform=platform,
            external_id=str(appid) if appid is not None else "",
            title=payload.get("name"),
            description=payload.get("short_description") or payload.get("detailed_description"),
            raw_tags=[t for t in tags + categories if t],
        )

    if platform == "playstore":
        return NormalizedGame(
            platform=platform,
            external_id=payload.get("appId") or "",
            title=payload.get("title"),
            description=payload.get("description") or payload.get("summary"),
            raw_tags=[t for t in [payload.get("genre"), payload.get("genreId")] if t],
        )

    if platform == "appstore":
        return NormalizedGame(
            platform=platform,
            external_id=str(payload.get("trackId") or ""),
            title=payload.get("trackName"),
            description=payload.get("description"),
            raw_tags=list(payload.get("genres") or []),
        )

    raise ValueError(f"unknown platform: {platform}")


def normalize_all() -> int:
    """Pull latest raw_games and UPSERT into games. Returns rows upserted."""
    count = 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (platform, external_id)
                    platform, external_id, payload
                FROM raw_games
                ORDER BY platform, external_id, collected_at DESC
                """
            )
            rows = cur.fetchall()

        for row in rows:
            try:
                ng = extract_normalized(row["platform"], row["payload"])
            except Exception as e:
                log.warning(
                    "normalize skip platform=%s ext_id=%s err=%s",
                    row["platform"],
                    row["external_id"],
                    e,
                )
                continue
            if not ng.external_id:
                continue
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO games (platform, external_id, title, description, raw_tags, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (platform, external_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        raw_tags = EXCLUDED.raw_tags,
                        updated_at = NOW()
                    """,
                    (ng.platform, ng.external_id, ng.title, ng.description, ng.raw_tags),
                )
            count += 1
        conn.commit()
    return count
