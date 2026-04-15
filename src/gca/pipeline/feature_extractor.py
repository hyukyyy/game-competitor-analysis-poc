from __future__ import annotations

import json

import anthropic

from ..config import Settings
from ..db import connect
from ..logs import get_logger
from .cache import llm_cache_get, llm_cache_put
from .feature_prompt import SYSTEM, USER_TEMPLATE

log = get_logger(__name__)
settings = Settings()

_REQUIRED_FIELDS = {"genre", "subgenre", "bm_dist", "play_style", "session_length_minutes", "core_loop"}


def extract_features_for_game(
    game_id: int,
    title: str,
    description: str,
    reviews: list[str],
) -> dict | None:
    reviews_text = "\n".join(f"- {r}" for r in reviews[:5]) if reviews else "(no reviews)"
    prompt = USER_TEMPLATE.format(
        title=title or "(untitled)",
        description=(description or "")[:3000],
        reviews=reviews_text,
    )

    cached = llm_cache_get(settings.llm_model, SYSTEM, prompt)
    if cached is not None:
        return cached

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()

    try:
        features = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("game_id=%d LLM returned invalid JSON: %s", game_id, e)
        return None

    if not _REQUIRED_FIELDS.issubset(features):
        log.warning("game_id=%d missing fields: %s", game_id, _REQUIRED_FIELDS - features.keys())
        return None

    if features.get("_canary_answer") != "yes":
        log.warning("game_id=%d canary failed: _canary_answer=%r", game_id, features.get("_canary_answer"))

    llm_cache_put(settings.llm_model, SYSTEM, prompt, features)
    return features


def upsert_features(game_id: int, features: dict) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE game_features SET valid_to = NOW() WHERE game_id = %s AND valid_to IS NULL",
            [game_id],
        )
        row = conn.execute(
            "SELECT COALESCE(MAX(feature_version), 0) + 1 AS v FROM game_features WHERE game_id = %s",
            [game_id],
        ).fetchone()
        version = row["v"]
        conn.execute(
            """
            INSERT INTO game_features
                (game_id, genre, subgenre, bm_dist, play_style,
                 session_length_minutes, core_loop, feature_version, valid_from)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, NOW())
            """,
            [
                game_id,
                features.get("genre"),
                features.get("subgenre"),
                json.dumps(features.get("bm_dist", {})),
                features.get("play_style", []),
                features.get("session_length_minutes"),
                features.get("core_loop"),
                version,
            ],
        )


def extract_all(changed_only: bool = False) -> int:
    with connect() as conn:
        if changed_only:
            rows = conn.execute(
                """
                SELECT g.id, g.platform, g.external_id, g.title, g.description
                FROM games g
                LEFT JOIN game_features gf ON g.id = gf.game_id AND gf.valid_to IS NULL
                WHERE gf.game_id IS NULL OR g.updated_at > gf.valid_from
                """
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, platform, external_id, title, description FROM games"
            ).fetchall()

    count = 0
    for row in rows:
        with connect() as conn:
            review_rows = conn.execute(
                """
                SELECT text FROM raw_reviews
                WHERE platform = %s AND external_id = %s AND text IS NOT NULL
                LIMIT 5
                """,
                [row["platform"], row["external_id"]],
            ).fetchall()
        review_texts = [r["text"] for r in review_rows]

        features = extract_features_for_game(
            row["id"],
            row["title"] or "",
            row["description"] or "",
            review_texts,
        )
        if features:
            upsert_features(row["id"], features)
            count += 1
        else:
            log.warning("skipping game_id=%d (feature extraction failed)", row["id"])

    return count
