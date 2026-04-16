from __future__ import annotations

from sentence_transformers import SentenceTransformer

from ..config import Settings
from ..db import connect
from ..logs import get_logger
from .cache import embedding_cache_get, embedding_cache_put

log = get_logger(__name__)
settings = Settings()

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info("loading embedding model %s", settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def get_embedding(text: str) -> list[float]:
    cached = embedding_cache_get(text, settings.embedding_model)
    if cached is not None:
        return cached

    vec = _get_model().encode(text).tolist()
    embedding_cache_put(text, settings.embedding_model, vec)
    return vec


def embed_all(changed_only: bool = False) -> int:
    with connect() as conn:
        if changed_only:
            rows = conn.execute(
                """
                SELECT g.id, g.platform, g.external_id, g.description
                FROM games g
                LEFT JOIN game_embeddings ge ON g.id = ge.game_id
                WHERE ge.game_id IS NULL OR g.updated_at > ge.updated_at
                """
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, platform, external_id, description FROM games"
            ).fetchall()

    count = 0
    for row in rows:
        with connect() as conn:
            review_rows = conn.execute(
                """
                SELECT text FROM raw_reviews
                WHERE platform = %s AND external_id = %s AND text IS NOT NULL
                LIMIT 10
                """,
                [row["platform"], row["external_id"]],
            ).fetchall()
        review_concat = " ".join(r["text"] for r in review_rows)[:8000]

        desc = row["description"] or ""
        desc_vec = get_embedding(desc) if desc else get_embedding("no description")
        review_vec = get_embedding(review_concat) if review_concat else desc_vec

        with connect() as conn:
            conn.execute(
                """
                INSERT INTO game_embeddings
                    (game_id, description_embedding, review_embedding, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (game_id) DO UPDATE SET
                    description_embedding = EXCLUDED.description_embedding,
                    review_embedding = EXCLUDED.review_embedding,
                    updated_at = NOW()
                """,
                [row["id"], desc_vec, review_vec],
            )
        count += 1
        log.debug("embedded game_id=%d", row["id"])

    return count
