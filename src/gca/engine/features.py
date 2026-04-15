from __future__ import annotations

import datetime as dt

from ..db import connect
from ..pipeline import feature_extractor


def get_features(game_id: int, as_of: dt.datetime | None = None) -> dict | None:
    """Return the active feature row for game_id at a given point in time."""
    ts = as_of or dt.datetime.now(dt.timezone.utc)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, game_id, genre, subgenre, bm_dist, play_style,
                   session_length_minutes, core_loop, feature_version,
                   valid_from, valid_to
            FROM game_features
            WHERE game_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
            ORDER BY valid_from DESC
            LIMIT 1
            """,
            [game_id, ts, ts],
        ).fetchone()
        return dict(row) if row else None


def upsert_features(game_id: int, features: dict) -> None:
    """Write a new feature version (SCD Type 2) for game_id."""
    feature_extractor.upsert_features(game_id, features)


def get_embedding(game_id: int, kind: str = "description") -> list[float] | None:
    """Return the embedding vector for game_id. kind: 'description' | 'review'."""
    col = "description_embedding" if kind == "description" else "review_embedding"
    with connect() as conn:
        row = conn.execute(
            f"SELECT {col} FROM game_embeddings WHERE game_id = %s",
            [game_id],
        ).fetchone()
        return row[col] if row else None
