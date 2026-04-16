from __future__ import annotations

import datetime as dt
import itertools
import json
import math

from ..db import connect
from ..logs import get_logger
from .similarity import compute_pair

log = get_logger(__name__)

_WEIGHT_KEYS = ("semantic", "genre", "tier", "bm")


# ------------------------------------------------------------------
# NDCG helpers
# ------------------------------------------------------------------

def _dcg(relevances: list[float], k: int) -> float:
    return sum(
        rel / math.log2(i + 2)
        for i, rel in enumerate(relevances[:k])
    )


def _ndcg_at_k(ranked_ids: list[int], relevant_ids: set[int], k: int = 10) -> float:
    """NDCG@k using binary relevance (1 if in relevant_ids, 0 otherwise)."""
    if not relevant_ids:
        return 0.0
    gains = [1.0 if gid in relevant_ids else 0.0 for gid in ranked_ids[:k]]
    ideal = sorted(gains, reverse=True)
    dcg   = _dcg(gains, k)
    idcg  = _dcg(ideal, k)
    return dcg / idcg if idcg > 0 else 0.0


# ------------------------------------------------------------------
# Label loading
# ------------------------------------------------------------------

def _load_labels() -> list[dict]:
    """Return all PM feedback rows and weak similarity rows as labels.

    Returns list of {base_game_id, target_game_id, positive (bool)}.
    """
    labels: list[dict] = []
    with connect() as conn:
        # PM feedback: upvote = positive, downvote = negative
        rows = conn.execute(
            """
            SELECT base_game_id, target_game_id, signal
            FROM pm_feedback
            """
        ).fetchall()
        for r in rows:
            labels.append({
                "base_game_id":   r["base_game_id"],
                "target_game_id": r["target_game_id"],
                "positive":       r["signal"] in ("upvote", "added"),
            })

        # Weak labels: all weak similarities are treated as positive
        rows = conn.execute(
            "SELECT base_game_id, target_game_id FROM weak_similarities"
        ).fetchall()
        for r in rows:
            labels.append({
                "base_game_id":   r["base_game_id"],
                "target_game_id": r["target_game_id"],
                "positive":       True,
            })

    return labels


def _load_game_vectors() -> dict[int, dict]:
    """Return pre-loaded feature vectors keyed by game_id."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                g.id, gf.genre, gf.bm_dist,
                ge.description_embedding,
                ge.review_embedding
            FROM games g
            JOIN game_features gf ON g.id = gf.game_id AND gf.valid_to IS NULL
            JOIN game_embeddings ge ON g.id = ge.game_id
            """
        ).fetchall()
    return {r["id"]: dict(r) for r in rows}


def _genre_embed_for(game_id: int, vectors: dict[int, dict]) -> list[float]:
    """Embed genre string on the fly (uses embedding cache)."""
    from ..pipeline.embedder import get_embedding
    genre = (vectors.get(game_id) or {}).get("genre") or "unknown"
    return get_embedding(genre)


# ------------------------------------------------------------------
# Grid search
# ------------------------------------------------------------------

def _weight_grid(n_steps: int = 5) -> list[dict]:
    """Generate weight combinations that sum to 1.0."""
    step = 1.0 / n_steps
    vals = [round(i * step, 2) for i in range(n_steps + 1)]
    combos = []
    for s, g, t in itertools.product(vals, vals, vals):
        b = round(1.0 - s - g - t, 2)
        if b < 0:
            continue
        if abs(s + g + t + b - 1.0) > 0.01:
            continue
        combos.append({"semantic": s, "genre": g, "tier": t, "bm": b})
    return combos


def _tier_score(game_id: int, tier_map: dict[int, float]) -> float:
    return tier_map.get(game_id, 0.5)


def grid_search(n_steps: int = 5, k: int = 10) -> dict:
    """Run grid search over weight combinations.

    Returns best weights dict: {"semantic": f, "genre": f, "tier": f, "bm": f}
    """
    labels = _load_labels()
    if not labels:
        log.warning("No labels found — returning default weights")
        from .similarity import DEFAULT_WEIGHTS
        return DEFAULT_WEIGHTS

    vectors = _load_game_vectors()

    # Pre-compute tier normalization
    import math as _math
    review_counts = {}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT g.id AS game_id, COUNT(rr.id) AS n
            FROM games g
            LEFT JOIN raw_reviews rr
                ON rr.platform = g.platform AND rr.external_id = g.external_id
            GROUP BY g.id
            """
        ).fetchall()
        for r in rows:
            review_counts[r["game_id"]] = r["n"]
    max_log = max((_math.log1p(v) for v in review_counts.values()), default=1.0) or 1.0
    tier_map = {gid: _math.log1p(cnt) / max_log for gid, cnt in review_counts.items()}

    # Pre-cache genre embeddings
    genre_cache: dict[int, list[float]] = {}
    for gid in vectors:
        genre_cache[gid] = _genre_embed_for(gid, vectors)

    # Group positive labels per base game
    positives: dict[int, set[int]] = {}
    for lbl in labels:
        if lbl["positive"]:
            positives.setdefault(lbl["base_game_id"], set()).add(lbl["target_game_id"])

    base_ids = [bid for bid in positives if bid in vectors]
    if not base_ids:
        log.warning("No labeled base games in vectors — returning default weights")
        from .similarity import DEFAULT_WEIGHTS
        return DEFAULT_WEIGHTS

    log.info("Grid search over %d weight combos × %d base games…",
             len(_weight_grid(n_steps)), len(base_ids))

    best_score = -1.0
    best_weights: dict = {}

    for weights in _weight_grid(n_steps):
        ndcg_sum = 0.0
        for bid in base_ids:
            base_vec = vectors[bid]
            bm_a = base_vec.get("bm_dist") or {}
            if isinstance(bm_a, str):
                bm_a = json.loads(bm_a)

            scores: list[tuple[float, int]] = []
            for tid, tvec in vectors.items():
                if tid == bid:
                    continue
                bm_b = tvec.get("bm_dist") or {}
                if isinstance(bm_b, str):
                    bm_b = json.loads(bm_b)
                s, _ = compute_pair(
                    desc_embed_a=base_vec["description_embedding"],
                    desc_embed_b=tvec["description_embedding"],
                    genre_embed_a=genre_cache[bid],
                    genre_embed_b=genre_cache[tid],
                    tier_a=_tier_score(bid, tier_map),
                    tier_b=_tier_score(tid, tier_map),
                    bm_dist_a=bm_a,
                    bm_dist_b=bm_b,
                    weights=weights,
                )
                scores.append((s, tid))
            scores.sort(reverse=True)
            ranked = [tid for _, tid in scores]
            ndcg_sum += _ndcg_at_k(ranked, positives[bid], k=k)

        avg_ndcg = ndcg_sum / len(base_ids)
        if avg_ndcg > best_score:
            best_score = avg_ndcg
            best_weights = weights
            log.debug("New best: NDCG@%d=%.4f weights=%s", k, best_score, weights)

    log.info("Best weights: %s  NDCG@%d=%.4f", best_weights, k, best_score)
    return best_weights


def save_weights(weights: dict, ndcg_score: float, label_count: int, week_of: dt.date) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO weight_history (week_of, weights, ndcg_score, label_count)
            VALUES (%s, %s::jsonb, %s, %s)
            """,
            [week_of, json.dumps(weights), ndcg_score, label_count],
        )


def load_latest_weights() -> dict:
    """Return the most recently saved weights, or DEFAULT_WEIGHTS if none."""
    with connect() as conn:
        row = conn.execute(
            "SELECT weights FROM weight_history ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            w = row["weights"]
            return w if isinstance(w, dict) else json.loads(w)
    from .similarity import DEFAULT_WEIGHTS
    return DEFAULT_WEIGHTS
