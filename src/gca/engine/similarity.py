from __future__ import annotations

import datetime as dt
import json
import math

import numpy as np

from ..db import connect
from ..logs import get_logger
from ..pipeline.embedder import get_embedding

log = get_logger(__name__)

DEFAULT_WEIGHTS = {"semantic": 0.40, "genre": 0.25, "tier": 0.20, "bm": 0.15}
_TIER_SIGMA = 0.3          # controls how fast tier similarity decays
_BM_KEYS = ("gacha", "ads", "premium", "sub")


# ------------------------------------------------------------------
# Component-level math
# ------------------------------------------------------------------

def _cosine(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _kl_sym(p: dict, q: dict) -> float:
    """Symmetric KL divergence, clamped to [0, log(4)] and normalized to [0, 1]."""
    eps = 1e-8
    p_arr = np.array([p.get(k, 0.0) + eps for k in _BM_KEYS], dtype=float)
    q_arr = np.array([q.get(k, 0.0) + eps for k in _BM_KEYS], dtype=float)
    p_arr /= p_arr.sum()
    q_arr /= q_arr.sum()
    kl_pq = float(np.sum(p_arr * np.log(p_arr / q_arr)))
    kl_qp = float(np.sum(q_arr * np.log(q_arr / p_arr)))
    sym_kl = (kl_pq + kl_qp) / 2.0
    # max sym KL for 4-class is 2*log(4) ≈ 2.77; normalize to [0,1]
    return min(1.0, sym_kl / (2.0 * math.log(4)))


def _bm_sim(bm_a: dict, bm_b: dict) -> float:
    return 1.0 - _kl_sym(bm_a, bm_b)


def _tier_sim(tier_a: float, tier_b: float) -> float:
    return math.exp(-abs(tier_a - tier_b) / _TIER_SIGMA)


# ------------------------------------------------------------------
# Pair-level API
# ------------------------------------------------------------------

def compute_pair(
    desc_embed_a: list[float],
    desc_embed_b: list[float],
    genre_embed_a: list[float],
    genre_embed_b: list[float],
    tier_a: float,
    tier_b: float,
    bm_dist_a: dict,
    bm_dist_b: dict,
    weights: dict | None = None,
) -> tuple[float, dict]:
    """Return (overall_score, component_scores) for a game pair."""
    w = weights or DEFAULT_WEIGHTS
    semantic = _cosine(desc_embed_a, desc_embed_b)
    genre    = _cosine(genre_embed_a, genre_embed_b)
    tier     = _tier_sim(tier_a, tier_b)
    bm       = _bm_sim(bm_dist_a, bm_dist_b)
    score = (
        w["semantic"] * semantic
        + w["genre"]   * genre
        + w["tier"]    * tier
        + w["bm"]      * bm
    )
    return round(score, 6), {
        "semantic": round(semantic, 4),
        "genre":    round(genre, 4),
        "tier":     round(tier, 4),
        "bm":       round(bm, 4),
    }


# ------------------------------------------------------------------
# Batch computation
# ------------------------------------------------------------------

def _load_game_data() -> list[dict]:
    """Load all games that have both features and embeddings."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                g.id, g.platform, g.external_id, g.title,
                gf.genre, gf.bm_dist,
                ge.description_embedding
            FROM games g
            JOIN game_features gf ON g.id = gf.game_id AND gf.valid_to IS NULL
            JOIN game_embeddings ge ON g.id = ge.game_id
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _compute_tier_scores(games: list[dict]) -> dict[int, float]:
    """Compute normalized log-review-count tier score for each game."""
    counts: dict[int, int] = {}
    for g in games:
        with connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM raw_reviews WHERE platform = %s AND external_id = %s",
                [g["platform"], g["external_id"]],
            ).fetchone()
        counts[g["id"]] = row["n"] if row else 0

    if not counts:
        return {}
    max_log = max(math.log1p(v) for v in counts.values()) or 1.0
    return {gid: math.log1p(cnt) / max_log for gid, cnt in counts.items()}


def compute_all(
    week_of: dt.date,
    weights: dict | None = None,
    top_n: int = 20,
    changed_only: bool = False,
) -> int:
    """Compute pairwise similarity for all games and store top_n per game.

    Returns number of (base_game_id, target_game_id) pairs written.
    """
    games = _load_game_data()
    if not games:
        log.warning("No games with features+embeddings found — skipping similarity computation")
        return 0

    tier_scores = _compute_tier_scores(games)

    # Pre-compute genre embeddings (cached in embedding_cache)
    log.info("Computing genre embeddings for %d games…", len(games))
    genre_embeds: dict[int, list[float]] = {}
    for g in games:
        genre_str = g.get("genre") or "unknown"
        genre_embeds[g["id"]] = get_embedding(genre_str)

    # Which base games need recomputation?
    if changed_only:
        with connect() as conn:
            existing = {
                r["base_game_id"]
                for r in conn.execute(
                    "SELECT DISTINCT base_game_id FROM game_similarities_weekly WHERE week_of = %s",
                    [week_of],
                ).fetchall()
            }
        base_games = [g for g in games if g["id"] not in existing]
    else:
        base_games = games

    total_written = 0
    for base in base_games:
        scores: list[tuple[float, int, dict]] = []
        for target in games:
            if target["id"] == base["id"]:
                continue
            bm_a = base.get("bm_dist") or {}
            bm_b = target.get("bm_dist") or {}
            if isinstance(bm_a, str):
                bm_a = json.loads(bm_a)
            if isinstance(bm_b, str):
                bm_b = json.loads(bm_b)
            score, components = compute_pair(
                desc_embed_a=base["description_embedding"],
                desc_embed_b=target["description_embedding"],
                genre_embed_a=genre_embeds[base["id"]],
                genre_embed_b=genre_embeds[target["id"]],
                tier_a=tier_scores.get(base["id"], 0.5),
                tier_b=tier_scores.get(target["id"], 0.5),
                bm_dist_a=bm_a,
                bm_dist_b=bm_b,
                weights=weights,
            )
            scores.append((score, target["id"], components))

        scores.sort(key=lambda x: x[0], reverse=True)
        top = scores[:top_n]

        with connect() as conn:
            for rank, (sim_score, target_id, comps) in enumerate(top, start=1):
                conn.execute(
                    """
                    INSERT INTO game_similarities_weekly
                        (week_of, base_game_id, target_game_id, similarity_score, rank,
                         component_scores, calculated_at)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (week_of, base_game_id, target_game_id) DO UPDATE SET
                        similarity_score = EXCLUDED.similarity_score,
                        rank             = EXCLUDED.rank,
                        component_scores = EXCLUDED.component_scores,
                        calculated_at    = NOW()
                    """,
                    [week_of, base["id"], target_id, sim_score, rank, json.dumps(comps)],
                )
        total_written += len(top)
        log.debug("base_game_id=%d: wrote %d similarity rows", base["id"], len(top))

    return total_written
