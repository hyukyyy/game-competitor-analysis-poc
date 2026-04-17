from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from openai import OpenAI
from jinja2 import Environment, FileSystemLoader

from ..config import Settings
from ..db import connect
from ..logs import get_logger

log = get_logger(__name__)
settings = Settings()

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_UPDATES_SYSTEM = """\
You are a game market analyst. Summarize the most notable recent updates
for the listed competitor games in 3-5 bullet points. Be concise and
focus on changes relevant to a PM (monetization, major content, player
count spikes). Return plain text, no JSON.
""".strip()


# ------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------

def _load_base_game(game_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT id, platform, title FROM games WHERE id = %s", [game_id]).fetchone()
        if not row:
            raise ValueError(f"game_id {game_id} not found")
        return dict(row)


def _load_top_n(base_game_id: int, week_of: dt.date, limit: int = 10) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                gsw.target_game_id, gsw.similarity_score, gsw.rank,
                gsw.component_scores,
                g.title, g.platform
            FROM game_similarities_weekly gsw
            JOIN games g ON g.id = gsw.target_game_id
            WHERE gsw.base_game_id = %s AND gsw.week_of = %s
            ORDER BY gsw.rank
            LIMIT %s
            """,
            [base_game_id, week_of, limit],
        ).fetchall()
    result = []
    for r in rows:
        comps = r["component_scores"]
        if isinstance(comps, str):
            comps = json.loads(comps)
        result.append({
            "game_id":         r["target_game_id"],
            "title":           r["title"],
            "platform":        r["platform"],
            "similarity_score": r["similarity_score"],
            "rank":            r["rank"],
            "components":      comps or {},
        })
    return result


def _load_prev_top_n(base_game_id: int, week_of: dt.date, limit: int = 20) -> dict[int, int]:
    """Return {game_id: rank} for the previous week."""
    prev_week = week_of - dt.timedelta(weeks=1)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT target_game_id, rank
            FROM game_similarities_weekly
            WHERE base_game_id = %s AND week_of = %s
            ORDER BY rank LIMIT %s
            """,
            [base_game_id, prev_week, limit],
        ).fetchall()
    return {r["target_game_id"]: r["rank"] for r in rows}


def _new_entrants(current: list[dict], prev_ranks: dict[int, int]) -> list[dict]:
    return [e for e in current if e["game_id"] not in prev_ranks]


def _rank_changes(current: list[dict], prev_ranks: dict[int, int]) -> list[dict]:
    changes = []
    for entry in current:
        gid = entry["game_id"]
        if gid in prev_ranks and prev_ranks[gid] != entry["rank"]:
            changes.append({
                "title":     entry["title"],
                "prev_rank": prev_ranks[gid],
                "curr_rank": entry["rank"],
            })
    return sorted(changes, key=lambda x: abs(x["prev_rank"] - x["curr_rank"]), reverse=True)


def _llm_updates_summary(top_games: list[dict]) -> str:
    if not top_games:
        return "_No competitor data available._"
    titles = "\n".join(f"- {g['title']} ({g['platform']})" for g in top_games[:10])
    prompt = f"Competitor games this week:\n{titles}\n\nSummarize notable recent updates for these titles."
    try:
        client = OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
        msg = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=512,
            messages=[
                {"role": "system", "content": _UPDATES_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        return msg.choices[0].message.content.strip()
    except Exception as e:
        log.warning("LLM updates summary failed: %s", e)
        return "_Summary unavailable._"


def _load_weights() -> dict:
    from ..engine.weight_tuner import load_latest_weights
    return load_latest_weights()


# ------------------------------------------------------------------
# Main API
# ------------------------------------------------------------------

def generate_report(base_game_id: int, week_of: dt.date, top_n: int = 10) -> dict:
    """Build the full report data structure (does NOT persist)."""
    base_game = _load_base_game(base_game_id)
    current   = _load_top_n(base_game_id, week_of, limit=top_n)
    prev_ranks = _load_prev_top_n(base_game_id, week_of)

    return {
        "base_game":      base_game,
        "week_of":        str(week_of),
        "generated_at":   dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "top_n":          current,
        "new_entrants":   _new_entrants(current, prev_ranks),
        "rank_changes":   _rank_changes(current, prev_ranks),
        "updates_summary": _llm_updates_summary(current),
        "weights":        _load_weights(),
    }


def render_markdown(report_data: dict) -> str:
    """Render report_data to Markdown using the Jinja2 template."""
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=False)
    tmpl = env.get_template("weekly.md.j2")
    return tmpl.render(**report_data)


def save_report(base_game_id: int, week_of: dt.date, content: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO weekly_reports (week_of, base_game_id, content)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (week_of, base_game_id) DO UPDATE SET
                content      = EXCLUDED.content,
                generated_at = NOW()
            """,
            [week_of, base_game_id, json.dumps(content)],
        )


def generate_and_save(base_game_id: int, week_of: dt.date, top_n: int = 10) -> str:
    """Generate, save to DB, and return the rendered Markdown report."""
    data = generate_report(base_game_id, week_of, top_n=top_n)
    save_report(base_game_id, week_of, data)
    return render_markdown(data)


def generate_all(week_of: dt.date, top_n: int = 10) -> int:
    """Generate reports for every 'my game' that has similarity data this week."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT gsw.base_game_id
            FROM game_similarities_weekly gsw
            JOIN games g ON g.id = gsw.base_game_id
            WHERE gsw.week_of = %s AND g.is_my_game = TRUE
            """,
            [week_of],
        ).fetchall()
    count = 0
    for row in rows:
        try:
            generate_and_save(row["base_game_id"], week_of, top_n=top_n)
            count += 1
        except Exception as e:
            log.warning("report failed for game_id=%d: %s", row["base_game_id"], e)
    return count
