"""Apply schema.sql to a Supabase project via psycopg.

Invoked by the Terraform null_resource in modules/supabase/main.tf. Idempotent:
safe to re-run when schema_hash changes (schema.sql uses CREATE ... IF NOT EXISTS).

Usage:
    python apply_schema.py <schema_sql_path> <database_url>
"""
from __future__ import annotations

import pathlib
import sys

import psycopg


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <schema_sql_path> <database_url>", file=sys.stderr)
        return 2

    schema_path = pathlib.Path(sys.argv[1])
    database_url = sys.argv[2]

    sql = schema_path.read_text(encoding="utf-8")

    print(f"[apply_schema] connecting...", flush=True)
    conn = psycopg.connect(database_url, connect_timeout=60, autocommit=True)
    print(f"[apply_schema] CREATE EXTENSION vector", flush=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    print(f"[apply_schema] applying {schema_path} ({len(sql)} chars)", flush=True)
    conn.execute(sql)
    row = conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
    ).fetchone()
    print(f"[apply_schema] done - public tables: {row[0]}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
