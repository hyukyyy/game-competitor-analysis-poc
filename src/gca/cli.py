from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from .collectors.appstore import AppStoreCollector, AppStoreCollectorError
from .collectors.itch import ItchCollector, ItchCollectorError
from .collectors.steam import SteamCollector, SteamCollectorError
from .db import connect
from .engine import similarity as similarity_mod
from .engine import weight_tuner
from .engine import weak_labels as weak_labels_mod
from .logs import get_logger
from .pipeline import embedder as embedder_mod
from .pipeline import feature_extractor as fe_mod
from .pipeline import normalize as normalize_mod
from .pipeline import runs
from .report import weekly as report_mod

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
    sql = sql_path.read_text(encoding="utf-8")
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


def cmd_extract_features(args: argparse.Namespace) -> int:
    week = _week_of(args.week_of)
    with runs.track("feature_extractor", week) as state:
        n = fe_mod.extract_all(changed_only=args.changed_only)
        state["rows_out"] = n
    print(f"✓ extracted features for {n} games")
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    week = _week_of(args.week_of)
    with runs.track("embedder", week) as state:
        n = embedder_mod.embed_all(changed_only=args.changed_only)
        state["rows_out"] = n
    print(f"✓ embedded {n} games")
    return 0


def cmd_feature_quality(args: argparse.Namespace) -> int:
    import yaml  # type: ignore

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"✗ fixture not found: {fixture_path}", file=sys.stderr)
        return 1

    with fixture_path.open() as f:
        gold: list[dict] = yaml.safe_load(f)

    fields = ["genre", "subgenre", "bm_dist", "play_style", "session_length_minutes", "core_loop"]
    totals: dict[str, int] = {k: 0 for k in fields}
    matches: dict[str, int] = {k: 0 for k in fields}
    canary_pass = 0

    for entry in gold:
        result = fe_mod.extract_features_for_game(
            game_id=entry.get("game_id", 0),
            title=entry.get("title", ""),
            description=entry.get("description", ""),
            reviews=entry.get("reviews", []),
        )
        if result is None:
            continue
        if result.get("_canary_answer") == "yes":
            canary_pass += 1
        for field in fields:
            if field in entry.get("expected", {}):
                totals[field] += 1
                if str(result.get(field)) == str(entry["expected"][field]):
                    matches[field] += 1

    print(f"Feature quality report ({len(gold)} gold entries):")
    for field in fields:
        if totals[field]:
            pct = 100 * matches[field] / totals[field]
            print(f"  {field:<28} {matches[field]}/{totals[field]} = {pct:.0f}%")
    print(f"  canary pass rate             {canary_pass}/{len(gold)} = {100*canary_pass/len(gold):.0f}%")
    return 0


def cmd_collect_appstore(args: argparse.Namespace) -> int:
    week = _week_of(args.week_of)
    with AppStoreCollector(country=args.country) as c, runs.track("collector.appstore", week) as state:
        ids = list(c.top_game_ids(limit=args.limit))
        state["rows_in"] = len(ids)
        inserted = skipped = 0
        with connect() as conn:
            for ext_id in ids:
                try:
                    game = c.fetch_game(ext_id)
                except AppStoreCollectorError as e:
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
                        log.debug("reviews skip %s: %s", ext_id, e)
                inserted += 1
            conn.commit()
        state["rows_out"] = inserted
        print(f"✓ collected {inserted}/{len(ids)} App Store games (skipped {skipped})")
    return 0


def cmd_collect_itch(args: argparse.Namespace) -> int:
    week = _week_of(args.week_of)
    with ItchCollector() as c, runs.track("collector.itch", week) as state:
        ids = list(c.top_game_ids(limit=args.limit))
        state["rows_in"] = len(ids)
        inserted = skipped = 0
        with connect() as conn:
            for ext_id in ids:
                try:
                    game = c.fetch_game(ext_id)
                except ItchCollectorError as e:
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
            conn.commit()
        state["rows_out"] = inserted
        print(f"✓ collected {inserted}/{len(ids)} itch.io games (skipped {skipped})")
    return 0


def cmd_similarity(args: argparse.Namespace) -> int:
    week = _week_of(args.week_of)
    weights = weight_tuner.load_latest_weights() if not args.default_weights else None
    with runs.track("similarity", week) as state:
        n = similarity_mod.compute_all(
            week_of=week,
            weights=weights,
            top_n=args.top_n,
            changed_only=args.changed_only,
        )
        state["rows_out"] = n
    print(f"✓ wrote {n} similarity rows for week {week}")
    return 0


def cmd_tune_weights(args: argparse.Namespace) -> int:
    week = _week_of(args.week_of)
    best = weight_tuner.grid_search(n_steps=args.n_steps, k=args.k)
    with connect() as conn:
        n_labels = conn.execute(
            "SELECT COUNT(*) AS n FROM pm_feedback"
        ).fetchone()["n"]
        n_weak = conn.execute(
            "SELECT COUNT(*) AS n FROM weak_similarities"
        ).fetchone()["n"]
    weight_tuner.save_weights(best, ndcg_score=0.0, label_count=n_labels + n_weak, week_of=week)
    print(f"✓ best weights: {best}")
    print(f"  labels used: {n_labels} PM + {n_weak} weak")
    return 0


def cmd_weak_labels(args: argparse.Namespace) -> int:
    if args.source == "tag_overlap":
        n = weak_labels_mod.collect_tag_overlap_weak_labels(min_shared=args.min_shared)
        print(f"✓ inserted {n} tag-overlap weak label rows")
    elif args.source == "steam":
        n = weak_labels_mod.collect_steam_weak_labels()
        print(f"✓ inserted {n} Steam morelike weak label rows")
    else:
        print(f"✗ unknown source: {args.source}", file=sys.stderr)
        return 1
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    week = _week_of(args.week_of)
    with runs.track("report", week) as state:
        if args.game_id:
            md = report_mod.generate_and_save(args.game_id, week, top_n=args.top_n)
            out_path = Path(f"report_{args.game_id}_{week}.md")
            out_path.write_text(md, encoding="utf-8")
            print(f"✓ report written to {out_path}")
            state["rows_out"] = 1
        else:
            n = report_mod.generate_all(week, top_n=args.top_n)
            print(f"✓ generated {n} reports for week {week}")
            state["rows_out"] = n
    return 0


def cmd_add_my_game(args: argparse.Namespace) -> int:
    """Register a game as 'my game' (PM's analysis target)."""
    platform = args.platform
    ext_id = str(args.appid)

    if platform != "steam":
        print(f"✗ platform {platform} not yet supported for add-my-game", file=sys.stderr)
        return 1

    with SteamCollector() as c:
        try:
            game = c.fetch_game(ext_id)
        except SteamCollectorError as e:
            print(f"✗ failed to fetch {platform}:{ext_id}: {e}", file=sys.stderr)
            return 1

    ng = normalize_mod.extract_normalized(platform, game.payload)
    if not ng.external_id:
        print(f"✗ could not normalize {platform}:{ext_id}", file=sys.stderr)
        return 1

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw_games (platform, external_id, payload, collected_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT DO NOTHING
                """,
                (game.platform, game.external_id, json.dumps(game.payload)),
            )
            cur.execute(
                """
                INSERT INTO games (platform, external_id, title, description, raw_tags,
                                   is_my_game, updated_at)
                VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
                ON CONFLICT (platform, external_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    raw_tags = EXCLUDED.raw_tags,
                    is_my_game = TRUE,
                    updated_at = NOW()
                RETURNING id, title
                """,
                (ng.platform, ng.external_id, ng.title, ng.description, ng.raw_tags),
            )
            row = cur.fetchone()
        conn.commit()

    print(f"✓ registered my_game id={row['id']} title={row['title']!r} ({platform}:{ext_id})")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn
    from .api.server import app  # noqa: F401
    uvicorn.run("gca.api.server:app", host=args.host, port=args.port, reload=args.reload)
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

    sp = sub.add_parser("extract-features", help="Extract LLM features for all games")
    sp.add_argument("--changed-only", action="store_true", help="Only process games without current features")
    sp.add_argument("--week-of", default=None)
    sp.set_defaults(func=cmd_extract_features)

    sp = sub.add_parser("embed", help="Generate embeddings for all games")
    sp.add_argument("--changed-only", action="store_true", help="Only embed games with stale/missing embeddings")
    sp.add_argument("--week-of", default=None)
    sp.set_defaults(func=cmd_embed)

    sp = sub.add_parser("feature-quality", help="Measure feature accuracy against gold set")
    sp.add_argument("--fixture", default="tests/fixtures/gold_features.yaml")
    sp.set_defaults(func=cmd_feature_quality)

    sp = sub.add_parser("collect:appstore", help="Collect App Store top games")
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument("--country", default="us")
    sp.add_argument("--week-of", default=None)
    sp.add_argument("--fetch-reviews", action="store_true")
    sp.add_argument("--review-limit", type=int, default=50)
    sp.set_defaults(func=cmd_collect_appstore)

    sp = sub.add_parser("collect:itch", help="Collect itch.io top games")
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument("--week-of", default=None)
    sp.set_defaults(func=cmd_collect_itch)

    sp = sub.add_parser("similarity", help="Compute pairwise similarity for all games")
    sp.add_argument("--week-of", default=None)
    sp.add_argument("--top-n", type=int, default=20)
    sp.add_argument("--changed-only", action="store_true")
    sp.add_argument("--default-weights", action="store_true", help="Use hard-coded default weights")
    sp.set_defaults(func=cmd_similarity)

    sp = sub.add_parser("tune-weights", help="Grid search for optimal similarity weights")
    sp.add_argument("--week-of", default=None)
    sp.add_argument("--n-steps", type=int, default=5, help="Grid resolution (higher = slower)")
    sp.add_argument("--k", type=int, default=10, help="NDCG@k")
    sp.set_defaults(func=cmd_tune_weights)

    sp = sub.add_parser("weak-labels", help="Collect weak similarity labels")
    sp.add_argument("--source", choices=["tag_overlap", "steam"], default="tag_overlap")
    sp.add_argument("--min-shared", type=int, default=3, help="Min shared tags (tag_overlap only)")
    sp.set_defaults(func=cmd_weak_labels)

    sp = sub.add_parser("report", help="Generate weekly competitor report(s)")
    sp.add_argument("--week-of", default=None)
    sp.add_argument("--game-id", type=int, default=None, help="Single game ID (omit = all games)")
    sp.add_argument("--top-n", type=int, default=10)
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("add-my-game", help="Register a game as 'my game' (PM analysis target)")
    sp.add_argument("--platform", choices=["steam"], default="steam")
    sp.add_argument("--appid", required=True, help="Platform app/game id (Steam appid)")
    sp.set_defaults(func=cmd_add_my_game)

    sp = sub.add_parser("serve", help="Start FastAPI server")
    sp.add_argument("--host", default="0.0.0.0")
    sp.add_argument("--port", type=int, default=8000)
    sp.add_argument("--reload", action="store_true")
    sp.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
