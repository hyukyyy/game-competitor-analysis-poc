from __future__ import annotations

import datetime as dt
from typing import Iterable

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..logs import get_logger
from ..models import RawGame, RawReview

log = get_logger(__name__)

_SEARCH_URL = "https://itunes.apple.com/search"
_LOOKUP_URL = "https://itunes.apple.com/lookup"
_REVIEWS_URL = "https://itunes.apple.com/{country}/rss/customerreviews/id={appid}/sortby=mostrecent/json"

_HEADERS = {"User-Agent": "gca-poc/0.1 (+internal)"}


class AppStoreCollectorError(Exception):
    pass


class AppStoreCollector:
    """Collector for iOS App Store via iTunes Search API (public, no key required)."""

    def __init__(self, country: str = "us", timeout: float = 15.0) -> None:
        self._country = country
        self._client = httpx.Client(headers=_HEADERS, timeout=timeout, follow_redirects=True)

    def __enter__(self) -> "AppStoreCollector":
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def top_game_ids(self, limit: int = 200) -> Iterable[str]:
        """Return App Store app IDs for top games via iTunes Search API."""
        # iTunes Search can return up to 200 at once
        fetched: list[str] = []
        terms = ["action game", "rpg game", "strategy game", "puzzle game", "sports game"]
        seen: set[str] = set()

        for term in terms:
            if len(fetched) >= limit:
                break
            try:
                batch = self._search_games(term, min(200, limit * 2))
            except Exception as e:
                log.warning("appstore search failed for %r: %s", term, e)
                continue
            for appid in batch:
                if appid not in seen:
                    seen.add(appid)
                    fetched.append(appid)
                if len(fetched) >= limit:
                    break

        return fetched[:limit]

    def fetch_game(self, external_id: str) -> RawGame:
        data = self._lookup(external_id)
        results = data.get("results", [])
        if not results:
            raise AppStoreCollectorError(f"no result for appid {external_id}")
        item = results[0]
        if item.get("kind") not in ("software", "mac-software"):
            raise AppStoreCollectorError(f"appid {external_id} is not an app (kind={item.get('kind')})")
        return RawGame(
            platform="appstore",
            external_id=str(item["trackId"]),
            payload=item,
            collected_at=dt.datetime.now(dt.timezone.utc),
        )

    def fetch_reviews(self, external_id: str, limit: int = 50) -> Iterable[RawReview]:
        reviews: list[RawReview] = []
        for page in range(1, 11):
            if len(reviews) >= limit:
                break
            try:
                batch = self._fetch_review_page(external_id, page)
            except Exception as e:
                log.warning("appstore reviews page %d failed for %s: %s", page, external_id, e)
                break
            if not batch:
                break
            for entry in batch:
                if len(reviews) >= limit:
                    break
                reviews.append(RawReview(
                    platform="appstore",
                    external_id=external_id,
                    review_id=entry.get("id", {}).get("label", ""),
                    text=entry.get("content", {}).get("label"),
                    rating=int(entry.get("im:rating", {}).get("label", 0)),
                    posted_at=_parse_date(entry.get("updated", {}).get("label")),
                ))
        return reviews

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _search_games(self, term: str, limit: int) -> list[str]:
        resp = self._client.get(_SEARCH_URL, params={
            "term": term,
            "country": self._country,
            "entity": "software",
            "genreId": "6014",  # Games genre ID
            "limit": min(limit, 200),
        })
        resp.raise_for_status()
        data = resp.json()
        return [str(r["trackId"]) for r in data.get("results", []) if "trackId" in r]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _lookup(self, appid: str) -> dict:
        resp = self._client.get(_LOOKUP_URL, params={"id": appid, "country": self._country})
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _fetch_review_page(self, appid: str, page: int) -> list[dict]:
        url = _REVIEWS_URL.format(country=self._country, appid=appid)
        resp = self._client.get(url, params={"page": page})
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        feed = data.get("feed", {})
        entries = feed.get("entry", [])
        # First entry is the app itself when page=1, skip it
        if page == 1 and entries and "im:name" in entries[0]:
            entries = entries[1:]
        return entries


def _parse_date(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
