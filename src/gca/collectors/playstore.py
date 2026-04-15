from __future__ import annotations

from collections.abc import Iterable

from ..logs import get_logger
from ..models import RawGame, RawReview

log = get_logger(__name__)


class PlayStoreCollector:
    """Google Play Store collector.

    Uses `google-play-scraper` (not in core deps — install on demand).
    Top charts are not exposed by the library; we accept a curated seed
    list of package IDs for PoC.
    """

    platform = "playstore"

    def __init__(self, seed_package_ids: list[str] | None = None):
        self.seed_package_ids = seed_package_ids or []

    def top_game_ids(self, limit: int = 200) -> Iterable[str]:
        return self.seed_package_ids[:limit]

    def fetch_game(self, external_id: str) -> RawGame:
        try:
            from google_play_scraper import app  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "install google-play-scraper to use PlayStoreCollector"
            ) from e
        data = app(external_id, lang="en", country="us")
        return RawGame(platform=self.platform, external_id=external_id, payload=dict(data))

    def fetch_reviews(self, external_id: str, limit: int = 100) -> list[RawReview]:
        try:
            from google_play_scraper import reviews as gp_reviews  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "install google-play-scraper to use PlayStoreCollector"
            ) from e
        result, _ = gp_reviews(external_id, lang="en", country="us", count=limit)
        out: list[RawReview] = []
        for r in result:
            out.append(
                RawReview(
                    platform=self.platform,
                    external_id=external_id,
                    review_id=str(r.get("reviewId") or ""),
                    text=r.get("content"),
                    rating=r.get("score"),
                    posted_at=r.get("at"),
                )
            )
        return out
