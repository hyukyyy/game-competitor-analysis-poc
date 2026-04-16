from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..db import connect
from ..logs import get_logger

log = get_logger(__name__)

_HEADERS = {"User-Agent": "gca-poc/0.1 (+internal)"}


# ------------------------------------------------------------------
# Source 1: Steam "More Like This" (store recommendations endpoint)
# ------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def fetch_steam_similar(appid: str, timeout: float = 10.0) -> list[str]:
    """Return Steam appids that Steam considers similar to appid.

    Uses the store recommendations page JSON embedded in the HTML.
    Falls back to an empty list if the page structure changes.
    """
    url = f"https://store.steampowered.com/recommended/morelike/{appid}/"
    try:
        with httpx.Client(headers=_HEADERS, timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError:
        return []

    # Steam embeds game IDs as data-ds-appid attributes in the HTML
    import re
    ids = re.findall(r'data-ds-appid="(\d+)"', resp.text)
    # Deduplicate, exclude self
    seen: set[str] = set()
    result: list[str] = []
    for gid in ids:
        if gid != appid and gid not in seen:
            seen.add(gid)
            result.append(gid)
    return result[:20]


# ------------------------------------------------------------------
# Source 2: Play Store "Similar apps" (google-play-scraper optional)
# ------------------------------------------------------------------

def fetch_playstore_similar(package_id: str) -> list[str]:
    """Return Play Store package IDs similar to package_id."""
    try:
        from google_play_scraper import similar  # type: ignore
    except ImportError:
        log.debug("google-play-scraper not installed; skipping Play Store similar")
        return []
    try:
        results = similar(package_id, lang="en", country="us")
        return [r["appId"] for r in results if "appId" in r][:20]
    except Exception as e:
        log.warning("playstore similar failed for %s: %s", package_id, e)
        return []


# ------------------------------------------------------------------
# Source 3: Tag overlap (no external API — works offline)
# ------------------------------------------------------------------

def from_tag_overlap(min_shared: int = 3) -> list[tuple[int, int]]:
    """Return (base_game_id, target_game_id) pairs with ≥ min_shared raw_tags.

    This is a fully local weak label source — no network required.
    """
    with connect() as conn:
        rows = conn.execute("SELECT id, raw_tags FROM games WHERE raw_tags IS NOT NULL").fetchall()

    game_tags: dict[int, set[str]] = {
        r["id"]: set(r["raw_tags"] or []) for r in rows
    }
    pairs: list[tuple[int, int]] = []
    ids = list(game_tags.keys())
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            shared = game_tags[a] & game_tags[b]
            if len(shared) >= min_shared:
                pairs.append((a, b))
    return pairs


# ------------------------------------------------------------------
# Persistence helpers
# ------------------------------------------------------------------

def save_weak_labels(pairs: list[tuple[int, int]], source: str) -> int:
    """Upsert (base_game_id, target_game_id) pairs into weak_similarities.

    Saves both directions (a→b and b→a) for symmetric coverage.
    Returns number of rows inserted.
    """
    inserted = 0
    with connect() as conn:
        for a, b in pairs:
            for base, target in ((a, b), (b, a)):
                result = conn.execute(
                    """
                    INSERT INTO weak_similarities (base_game_id, target_game_id, source)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (base_game_id, target_game_id, source) DO NOTHING
                    """,
                    [base, target, source],
                )
                inserted += result.rowcount
    return inserted


def collect_steam_weak_labels() -> int:
    """Collect Steam "More Like This" for all steam games in DB."""
    with connect() as conn:
        steam_games = conn.execute(
            "SELECT id, external_id FROM games WHERE platform = 'steam'"
        ).fetchall()

    total = 0
    for game in steam_games:
        similar_appids = fetch_steam_similar(game["external_id"])
        if not similar_appids:
            continue

        # Resolve appids to game_ids
        with connect() as conn:
            target_rows = conn.execute(
                f"SELECT id FROM games WHERE platform = 'steam' AND external_id = ANY(%s)",
                [similar_appids],
            ).fetchall()
        target_ids = [r["id"] for r in target_rows]
        pairs = [(game["id"], tid) for tid in target_ids]
        total += save_weak_labels(pairs, "steam_morelike")
        log.debug("steam_morelike: %s → %d pairs", game["external_id"], len(pairs))

    return total


def collect_tag_overlap_weak_labels(min_shared: int = 3) -> int:
    """Compute tag-overlap weak labels from existing games table."""
    pairs = from_tag_overlap(min_shared=min_shared)
    return save_weak_labels(pairs, "tag_overlap")
