"""Mirror the local SQLite tables to Supabase (Postgres) through PostgREST upserts.

The Next.js dashboard on Vercel reads from Supabase; this laptop is the only writer, so the
service-role key is used here and row-level security only has to allow authenticated reads.
Nothing in here may raise into a trading run: callers wrap run() and log failures.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import requests

from . import config, storage
from .util import log, today_ist

logger = log("sync")

# table -> (conflict target, json columns)
TABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "runs": ("id", ()),
    "market_context": ("trade_date", ("global_json", "components_json", "reasons_json")),
    "fii_dii": ("trade_date", ()),
    "sector_strength": ("trade_date,sector", ()),
    "features": ("trade_date,symbol", ("filter_fails", "features_json")),
    "candidates": ("trade_date,symbol,side", ("components_json", "reasons_json", "flags_json")),
    "picks": ("id", ("reasons_json", "flags_json", "components_json")),
    "outcomes": ("pick_id", ()),
    "watchlist": ("month,symbol", ()),
    "focus_verdicts": ("trade_date,symbol", ("reasons_json", "flags_json")),
}
BATCH = 500


def configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_ROLE_KEY)


def _headers() -> dict[str, str]:
    return {
        "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def _prepare(row: dict, json_cols: tuple[str, ...]) -> dict:
    out = dict(row)
    for col in json_cols:
        value = out.get(col)
        if isinstance(value, str):
            try:
                out[col] = json.loads(value)
            except json.JSONDecodeError:
                out[col] = None
    return out


def push_table(table: str, rows: list[dict]) -> int:
    conflict, json_cols = TABLES[table]
    url = f"{config.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
    sent = 0
    for i in range(0, len(rows), BATCH):
        batch = [_prepare(r, json_cols) for r in rows[i : i + BATCH]]
        r = requests.post(url, params={"on_conflict": conflict}, headers=_headers(), json=batch, timeout=60)
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f"supabase {table}: HTTP {r.status_code} {r.text[:300]}")
        sent += len(batch)
    return sent


def run(since: date | None = None, push_all: bool = False, quiet: bool = False) -> dict[str, int]:
    if not configured():
        if not quiet:
            print("sync: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set; skipping")
        return {}
    if not push_all and since is None:
        since = today_ist() - timedelta(days=config.SYNC_DAYS)
    since_iso = since.isoformat() if since else None
    counts: dict[str, int] = {}
    for table in TABLES:                        # order matters: picks before outcomes (FK)
        rows = storage.table_rows(table, since_iso)
        if not rows:
            counts[table] = 0
            continue
        counts[table] = push_table(table, rows)
    summary = ", ".join(f"{t} {n}" for t, n in counts.items() if n)
    logger.info("synced to supabase: %s", summary or "nothing new")
    if not quiet:
        print(f"synced: {summary or 'nothing new'}")
    return counts
