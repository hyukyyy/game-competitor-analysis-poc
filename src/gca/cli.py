from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from .collectors.steam import SteamCollector, SteamCollectorError
from .db import connect
from .logs import get_logger
from .pipeline import normalize as normalize_mod
from .pipeline import runs

log = get_logger("gca.cli")


def _week_of(s: str | None) -> dt.date:
    """Parse ISO date string or return current ISO-week Monday."""
    if s:
        return dt.date.fromisoformat(s)
    today = dt.date.today()
    return today - dt.timedelta(days=today.weekday())


def cmd_migrate(args: argparse.Namespace) -> int:
    sql_path = Path(args.schema)
    if not sql_path.exists():
        print(f"✗ schema file not found: {sql_path}", file=sys.stderr)
        return 1
    sql = sql_path.read_text()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
    print(f"✓ migrations applied from {sql_path}")
    return 0


def cmd_collect_steam(args: argparse.Namespace) -> int:
    week = _week_of(args.week_of)
    with SteamCollector() as c, runs.track("collector.steam", week) as state:
        ids = list(c.top_game_ids(limit=args.limit))
        state["rows_in"] = len(ids)
        inserted = 0
        skipped = 0
        with connect() as conn:
            for ext_id in ids:
                try:
                    game = c.fetch_game(ext_id)
                except SteamCollectorError as e:
                    log.debug("skip %s: %s", ext_id, e)
                    skipped += 1
                    continue
                except Exception as e:
                    log.warning("error fetching %s: %s", ext_id, e)
                    skipped += 1
                    continue
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO raw_games (platform, external_id, payload, collected_at)
                        VALUES (%s, %s, %s::jsonb, NOW())
                        ON CONFLICT DO NOTHING
                        """,
                        (game.platform, game.external_id, json.dumps(game.payload)),
                    )
                inserted += 1
                if args.fetch_reviews:
                    try:
                        revs = c.fetch_reviews(ext_id, limit=args.review_limit)
                        for r in revs:
                            with conn.cursor() as cur:
                                cur.execute(
                                    """
                                    INSERT INTO raw_reviews
                                        (platform, external_id, review_id, text, rating, posted_at)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                    ON CONFLICT (platform, review_id) DO NOTHING
                                    """,
                                    (
                                        r.platform,
                                        r.external_id,
                                        r.review_id,
                                        r.text,
                                        r.rating,
                                        r.posted_at,
                                    ),
                                )
                    except Exception as e:
                        log.warning("review fetch err %s: %s", ext_id, e)
            conn.commit()
        state["rows_out"] = inserted
        print(f"✓ collected {inserted}/{len(ids)} Steam games (skipped {skipped})")
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    week = _week_of(args.week_of)
    with runs.track("normalizer", week) as state:
        n = normalize_mod.normalize_all()
        state["rows_out"] = n
    print(f"✓ normalized {n} games")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT platform, COUNT(*) AS n FROM raw_games GROUP BY platform ORDER BY platform")
        print("raw_games:")
        for row in cur.fetchall():
            print(f"  {row['platform']}: {row['n']}")
        cur.execute("SELECT platform, COUNT(*) AS n FROM games GROUP BY platform ORDER BY platform")
        print("games:")
        for row in cur.fetchall():
            print(f"  {row['platform']}: {row['n']}")
        cur.execute(
            """
            SELECT stage, status, rows_out, started_at, ended_at
            FROM pipeline_runs ORDER BY started_at DESC LIMIT 10
            """
        )
        print("recent runs:")
        for row in cur.fetchall():
            print(
                f"  {row['started_at']:%Y-%m-%d %H:%M} {row['stage']:<20} "
                f"{row['status']:<8} rows_out={row['rows_out']}"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gca", description="Game Competitor Analysis CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("migrate", help="Apply schema.sql")
    sp.add_argument("--schema", default="schema.sql")
    sp.set_defaults(func=cmd_migrate)

    sp = sub.add_parser("collect:steam", help="Collect Steam top games + details")
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument("--week-of", default=None)
    sp.add_argument("--fetch-reviews", action="store_true")
    sp.add_argument("--review-limit", type=int, default=50)
    sp.set_defaults(func=cmd_collect_steam)

    sp = sub.add_parser("normalize", help="Normalize latest raw_games → games")
    sp.add_argument("--week-of", default=None)
    sp.set_defaults(func=cmd_normalize)

    sp = sub.add_parser("status", help="Show pipeline status")
    sp.set_defaults(func=cmd_status)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
