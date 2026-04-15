from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..models import RawGame, RawReview


class Collector(Protocol):
    """Platform collector contract.

    Implementations must be idempotent: calling fetch_* repeatedly for the
    same external_id should return equivalent data.
    """

    platform: str

    def top_game_ids(self, limit: int) -> Iterable[str]: ...

    def fetch_game(self, external_id: str) -> RawGame: ...

    def fetch_reviews(
        self, external_id: str, limit: int = 100
    ) -> Iterable[RawReview]: ...
