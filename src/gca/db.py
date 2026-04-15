from __future__ import annotations

import contextlib
from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import settings


@contextlib.contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Short-lived Postgres connection with dict rows."""
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn
