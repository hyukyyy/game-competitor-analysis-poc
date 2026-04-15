from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Iterator

from ..db import connect
from ..logs import get_logger

log = get_logger(__name__)


@contextlib.contextmanager
def track(stage: str, week_of: dt.date) -> Iterator[dict]:
    """Context manager that records a pipeline_runs row.

    Yields a mutable state dict. Caller sets state["rows_in"] / state["rows_out"].
    On exception → status='failed' with error text. On success → status='success'.
    """
    state: dict = {"rows_in": None, "rows_out": None}

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_runs (stage, week_of, status) VALUES (%s, %s, 'running') RETURNING id",
            (stage, week_of),
        )
        row = cur.fetchone()
        run_id = row["id"]
        conn.commit()
    log.info("pipeline run start: stage=%s week_of=%s run_id=%d", stage, week_of, run_id)

    try:
        yield state
    except Exception as e:
        log.exception("pipeline run FAILED: stage=%s run_id=%d", stage, run_id)
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE pipeline_runs SET status='failed', ended_at=NOW(), error=%s WHERE id=%s",
                (str(e)[:2000], run_id),
            )
            conn.commit()
        raise
    else:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE pipeline_runs SET status='success', ended_at=NOW(), rows_in=%s, rows_out=%s WHERE id=%s",
                (state.get("rows_in"), state.get("rows_out"), run_id),
            )
            conn.commit()
        log.info(
            "pipeline run done: stage=%s run_id=%d rows_in=%s rows_out=%s",
            stage,
            run_id,
            state.get("rows_in"),
            state.get("rows_out"),
        )
