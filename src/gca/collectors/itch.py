from __future__ import annotations

import datetime as dt
from typing import Iterable

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings
from ..logs import get_logger
from ..models import RawGame, RawReview

log = get_logger(__name__)

_BASE = "https://itch.io/api/1"
_BROWSE_URL = "https://itch.io/games/top-rated.json"
_HEADERS = {"User-Agent": "gca-poc/0.1 (+internal)"}


class ItchCollectorError(Exception):
    pass


class ItchCollector:
    """Collector for itch.io via public API + browse endpoint.

    API key is optional for public data; required only for user-specific
    endpoints. Set ITCH_API_KEY in .env if available.
    """

    def __init__(self, api_key: str | None = None, timeout: float = 15.0) -> None:
        settings = Settings()
        self._api_key = api_key or getattr(settings, "itch_api_key", None)
        self._client = httpx.Client(headers=_HEADERS, timeout=timeout, follow_redirects=True)

    def __enter__(self) -> "ItchCollector":
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def top_game_ids(self, limit: int = 200) -> Iterable[str]:
        """Return itch.io game IDs from the top-rated browse endpoint."""
        ids: list[str] = []
        page = 1
        while len(ids) < limit:
            try:
                batch = self._browse_page(page)
            except Exception as e:
                log.warning("itch browse page %d failed: %s", page, e)
                break
            if not batch:
                break
            for game in batch:
                gid = str(game.get("id", ""))
                if gid and gid not in ids:
                    ids.append(gid)
                if len(ids) >= limit:
                    break
            page += 1
        return ids[:limit]

    def fetch_game(self, external_id: str) -> RawGame:
        data = self._fetch_game_api(external_id)
        game = data.get("game")
        if not game:
            raise ItchCollectorError(f"no game data for id {external_id}")
        if game.get("classification") not in (None, "game"):
            raise ItchCollectorError(f"id {external_id} is not a game (classification={game.get('classification')})")
        return RawGame(
            platform="itch",
            external_id=str(game["id"]),
            payload=game,
            collected_at=dt.datetime.now(dt.timezone.utc),
        )

    def fetch_reviews(self, external_id: str, limit: int = 50) -> Iterable[RawReview]:
        # itch.io does not have a public reviews API — ratings are aggregated only.
        log.debug("itch.io has no public reviews API; skipping reviews for %s", external_id)
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _browse_page(self, page: int) -> list[dict]:
        resp = self._client.get(_BROWSE_URL, params={"page": page})
        resp.raise_for_status()
        return resp.json().get("games", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _fetch_game_api(self, game_id: str) -> dict:
        if self._api_key:
            url = f"{_BASE}/{self._api_key}/game/{game_id}"
        else:
            # Keyless public endpoint (limited fields)
            url = f"{_BASE}/key/game/{game_id}"
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.json()
