from __future__ import annotations

from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings
from ..logs import get_logger
from ..models import RawGame, RawReview

log = get_logger(__name__)

STEAMSPY_API = "https://steamspy.com/api.php"
STEAM_APPDETAILS = "https://store.steampowered.com/api/appdetails"
STEAM_APPREVIEWS = "https://store.steampowered.com/appreviews/{appid}"


class SteamCollectorError(Exception):
    pass


class SteamCollector:
    """Steam Web API collector.

    Top-games source: SteamSpy `top100in2weeks` (no API key needed).
    Per-game detail: store.steampowered.com/api/appdetails.
    Reviews:         store.steampowered.com/appreviews/{appid}.
    """

    platform = "steam"

    def __init__(self, timeout: float | None = None):
        self._client = httpx.Client(
            timeout=timeout or settings.http_timeout,
            headers={"User-Agent": "gca-poc/0.1 (+internal)"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def top_game_ids(self, limit: int = 200) -> list[str]:
        """Return top Steam appids by recent player count.

        SteamSpy top100in2weeks returns at most 100. For limit > 100 we
        paginate via `all` with different pages.
        """
        ids: list[str] = []
        if limit <= 100:
            resp = self._client.get(STEAMSPY_API, params={"request": "top100in2weeks"})
            resp.raise_for_status()
            ids = list(resp.json().keys())[:limit]
            return ids

        # For >100, combine top100in2weeks + top100owned (rough fallback).
        for req in ("top100in2weeks", "top100owned", "top100forever"):
            resp = self._client.get(STEAMSPY_API, params={"request": req})
            resp.raise_for_status()
            for k in resp.json():
                if k not in ids:
                    ids.append(k)
                if len(ids) >= limit:
                    return ids
        return ids

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def fetch_game(self, external_id: str) -> RawGame:
        resp = self._client.get(
            STEAM_APPDETAILS,
            params={"appids": external_id, "l": "english", "cc": "us"},
        )
        resp.raise_for_status()
        body = resp.json() or {}
        entry = body.get(str(external_id), {})
        if not entry or not entry.get("success"):
            raise SteamCollectorError(f"appdetails empty/failed for {external_id}")
        data = entry.get("data") or {}
        # Filter to games only (skip DLC/demos/videos)
        if data.get("type") and data["type"] != "game":
            raise SteamCollectorError(f"not a game (type={data['type']}) for {external_id}")
        return RawGame(
            platform=self.platform,
            external_id=str(external_id),
            payload=data,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def fetch_reviews(self, external_id: str, limit: int = 100) -> list[RawReview]:
        resp = self._client.get(
            STEAM_APPREVIEWS.format(appid=external_id),
            params={
                "json": 1,
                "num_per_page": min(limit, 100),
                "language": "all",
                "purchase_type": "all",
                "filter": "recent",
            },
        )
        resp.raise_for_status()
        body = resp.json() or {}
        out: list[RawReview] = []
        for r in body.get("reviews", [])[:limit]:
            ts = r.get("timestamp_created")
            posted_at = (
                datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, int) else None
            )
            out.append(
                RawReview(
                    platform=self.platform,
                    external_id=str(external_id),
                    review_id=str(r.get("recommendationid")),
                    text=r.get("review"),
                    rating=10 if r.get("voted_up") else 1,
                    posted_at=posted_at,
                )
            )
        return out
