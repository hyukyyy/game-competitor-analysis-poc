from __future__ import annotations

import hashlib
import json

from ..db import connect
from ..logs import get_logger

log = get_logger(__name__)


def _llm_hash(model: str, prompt: str, content: str) -> str:
    return hashlib.sha256((model + prompt + content).encode()).hexdigest()


def _embedding_hash(text: str, model: str) -> str:
    return hashlib.sha256((text + model).encode()).hexdigest()


def llm_cache_get(model: str, prompt: str, content: str) -> dict | None:
    h = _llm_hash(model, prompt, content)
    with connect() as conn:
        row = conn.execute(
            "SELECT output FROM llm_cache WHERE input_hash = %s", [h]
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE llm_cache SET hit_count = hit_count + 1 WHERE input_hash = %s", [h]
            )
            log.debug("llm_cache hit %s", h[:8])
            return row["output"]
    return None


def llm_cache_put(model: str, prompt: str, content: str, output: dict) -> None:
    h = _llm_hash(model, prompt, content)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO llm_cache (input_hash, model, output)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (input_hash) DO NOTHING
            """,
            [h, model, json.dumps(output)],
        )


def embedding_cache_get(text: str, model: str) -> list[float] | None:
    h = _embedding_hash(text, model)
    with connect() as conn:
        row = conn.execute(
            "SELECT embedding FROM embedding_cache WHERE text_hash = %s", [h]
        ).fetchone()
        if row:
            log.debug("embedding_cache hit %s", h[:8])
            return row["embedding"]
    return None


def embedding_cache_put(text: str, model: str, embedding: list[float]) -> None:
    h = _embedding_hash(text, model)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO embedding_cache (text_hash, model, embedding)
            VALUES (%s, %s, %s)
            ON CONFLICT (text_hash) DO NOTHING
            """,
            [h, model, embedding],
        )
