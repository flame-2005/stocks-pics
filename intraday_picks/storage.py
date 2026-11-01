"""SQLite persistence. One file under DATA_DIR; schema is created on first connect.

Tables: runs, market_context, fii_dii, sector_strength, features, candidates, picks, outcomes.
JSON columns hold lists/dicts as text. The Supabase sync reads these same tables.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from typing import Any, Iterable

from . import config
from .util import log, now_ist

logger = log("storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    trade_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    message_id INTEGER,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS runs_date_mode ON runs(trade_date, mode);

CREATE TABLE IF NOT EXISTS market_context (
    trade_date TEXT PRIMARY KEY,
    phase TEXT,
    mood TEXT,
    score INTEGER,
    caution INTEGER,
    nifty_close REAL, nifty_ema20 REAL, nifty_ema50 REAL, nifty_chg_pct REAL, nifty_gap_pct REAL,
    vix REAL, fii_net REAL, dii_net REAL,
    global_json TEXT, components_json TEXT, reasons_json TEXT,
    nifty_day_return REAL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS fii_dii (
    trade_date TEXT PRIMARY KEY,
    fii_buy REAL, fii_sell REAL, fii_net REAL,
    dii_buy REAL, dii_sell REAL, dii_net REAL,
    source TEXT
);

CREATE TABLE IF NOT EXISTS sector_strength (
    trade_date TEXT NOT NULL,
    sector TEXT NOT NULL,
    ret_1d REAL, ret_5d REAL, rs_1d REAL, rs_5d REAL, composite REAL,
    rank INTEGER, points_long INTEGER, points_short INTEGER,
    source TEXT, members INTEGER,
    PRIMARY KEY (trade_date, sector)
);

CREATE TABLE IF NOT EXISTS features (
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    industry TEXT,
    in_funnel INTEGER DEFAULT 0,
    filter_fails TEXT,
    features_json TEXT NOT NULL,
    PRIMARY KEY (trade_date, symbol)
);

CREATE TABLE IF NOT EXISTS candidates (
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    phase TEXT,
    stage TEXT,
    score REAL,
    setup_type TEXT,
    setup_label TEXT,
    sector TEXT,
    sector_points INTEGER,
    components_json TEXT,
    reasons_json TEXT,
    flags_json TEXT,
    PRIMARY KEY (trade_date, symbol, side)
);

CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY,
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    rank INTEGER,
    entry REAL, stop REAL, target REAL, qty INTEGER,
    stop_pct REAL, atr_pct REAL, alt_stop REAL,
    score REAL, setup_type TEXT, setup_label TEXT, sector TEXT,
    reasons_json TEXT, flags_json TEXT, components_json TEXT,
    entry_window TEXT, squareoff_time TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    phase TEXT,
    preopen_gap_pct REAL,
    confirm_note TEXT,
    confirmed_at TEXT,
    note TEXT,
    updated_at TEXT,
    UNIQUE (trade_date, symbol, side)
);

CREATE TABLE IF NOT EXISTS watchlist (
    month TEXT NOT NULL,
    as_of TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT, industry TEXT, rank INTEGER, is_index INTEGER DEFAULT 0,
    close REAL, ret_1w REAL, ret_1m REAL, ret_3m REAL,
    month_high REAL, month_low REAL, range_pos REAL,
    atr_pct REAL, med_turnover_cr REAL, avg_volume REAL,
    sma50 REAL, sma200 REAL, pct_from_sma50 REAL, pct_from_sma200 REAL, regime TEXT,
    picks_last_month INTEGER, r_last_month REAL, vix REAL,
    PRIMARY KEY (month, symbol)
);

CREATE TABLE IF NOT EXISTS outcomes (
    pick_id INTEGER PRIMARY KEY REFERENCES picks(id),
    trade_date TEXT,
    symbol TEXT,
    side TEXT,
    result TEXT,
    entry_time TEXT, exit_time TEXT,
    entry_price REAL, exit_price REAL,
    r_multiple REAL, pnl REAL,
    mfe REAL, mae REAL,
    day_high REAL, day_low REAL, day_close REAL,
    evaluated_at TEXT
);
"""


def _iso(d: date | str) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)


def _dump(value: Any) -> str:
    return json.dumps(value, default=str)


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ----------------------------------------------------------------------------- runs
def run_done(trade_date: date | str, mode: str) -> bool:
    with db() as conn:
        cur = conn.execute(
            "SELECT 1 FROM runs WHERE trade_date=? AND mode=? AND status='ok' LIMIT 1", (_iso(trade_date), mode)
        )
        return cur.fetchone() is not None


def start_run(trade_date: date | str, mode: str) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO runs(trade_date, mode, started_at, status) VALUES (?,?,?,'running')",
            (_iso(trade_date), mode, now_ist().isoformat(timespec="seconds")),
        )
        return int(cur.lastrowid)


def finish_run(run_id: int, status: str, message_id: int | None = None, notes: str | None = None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE runs SET finished_at=?, status=?, message_id=COALESCE(?, message_id), notes=? WHERE id=?",
            (now_ist().isoformat(timespec="seconds"), status, message_id, notes, run_id),
        )


def run_message_id(trade_date: date | str, mode: str) -> int | None:
    with db() as conn:
        cur = conn.execute(
            "SELECT message_id FROM runs WHERE trade_date=? AND mode=? AND message_id IS NOT NULL ORDER BY id DESC LIMIT 1",
            (_iso(trade_date), mode),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None


def clear_day(trade_date: date | str, modes: Iterable[str] = ("prep", "morning", "confirm", "scorecard")) -> None:
    """Forget a day's runs so a mode can be re-run (keeps picks; they are upserted)."""
    with db() as conn:
        for mode in modes:
            conn.execute("DELETE FROM runs WHERE trade_date=? AND mode=?", (_iso(trade_date), mode))


# ----------------------------------------------------------------------------- context
def save_market_context(mood, phase: str) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO market_context(trade_date, phase, mood, score, caution, nifty_close, nifty_ema20, nifty_ema50,
               nifty_chg_pct, nifty_gap_pct, vix, fii_net, dii_net, global_json, components_json, reasons_json, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(trade_date) DO UPDATE SET phase=excluded.phase, mood=excluded.mood, score=excluded.score,
               caution=excluded.caution, nifty_close=excluded.nifty_close, nifty_ema20=excluded.nifty_ema20,
               nifty_ema50=excluded.nifty_ema50, nifty_chg_pct=excluded.nifty_chg_pct, nifty_gap_pct=excluded.nifty_gap_pct,
               vix=excluded.vix, fii_net=excluded.fii_net, dii_net=excluded.dii_net, global_json=excluded.global_json,
               components_json=excluded.components_json, reasons_json=excluded.reasons_json, updated_at=excluded.updated_at""",
            (
                mood.trade_date, phase, mood.label, mood.score, int(mood.caution), mood.nifty_close, mood.nifty_ema20,
                mood.nifty_ema50, mood.nifty_chg_pct, mood.nifty_gap_pct, mood.vix, mood.fii_net, mood.dii_net,
                _dump(mood.global_chg), _dump([c.__dict__ for c in mood.components]), _dump(mood.reasons),
                now_ist().isoformat(timespec="seconds"),
            ),
        )


def save_nifty_day_return(trade_date: date | str, ret_pct: float | None) -> None:
    with db() as conn:
        conn.execute("UPDATE market_context SET nifty_day_return=? WHERE trade_date=?", (ret_pct, _iso(trade_date)))


def load_market_context(trade_date: date | str) -> dict | None:
    with db() as conn:
        cur = conn.execute("SELECT * FROM market_context WHERE trade_date=?", (_iso(trade_date),))
        row = cur.fetchone()
        return dict(row) if row else None


def save_fii_dii(trade_date: date | str, fii: dict) -> None:
    with db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO fii_dii(trade_date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, source)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                _iso(trade_date), fii.get("fii_buy"), fii.get("fii_sell"), fii.get("fii_net"),
                fii.get("dii_buy"), fii.get("dii_sell"), fii.get("dii_net"), fii.get("source", "nse"),
            ),
        )


def load_fii_dii(trade_date: date | str) -> dict | None:
    with db() as conn:
        cur = conn.execute("SELECT * FROM fii_dii WHERE trade_date=?", (_iso(trade_date),))
        row = cur.fetchone()
        return dict(row) if row else None


# ----------------------------------------------------------------------------- sectors / features / candidates
def save_sectors(trade_date: date | str, sectors) -> None:
    with db() as conn:
        conn.execute("DELETE FROM sector_strength WHERE trade_date=?", (_iso(trade_date),))
        conn.executemany(
            """INSERT INTO sector_strength(trade_date, sector, ret_1d, ret_5d, rs_1d, rs_5d, composite, rank,
               points_long, points_short, source, members) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (_iso(trade_date), s.sector, s.ret_1d, s.ret_5d, s.rs_1d, s.rs_5d, s.composite, s.rank,
                 s.points_long, s.points_short, s.source, s.members)
                for s in sectors
            ],
        )


def load_sectors(trade_date: date | str) -> list[dict]:
    with db() as conn:
        return rows(conn.execute("SELECT * FROM sector_strength WHERE trade_date=? ORDER BY rank", (_iso(trade_date),)))


def save_features(trade_date: date | str, feats: dict, funnel: Iterable[str]) -> None:
    funnel_set = set(funnel)
    with db() as conn:
        conn.execute("DELETE FROM features WHERE trade_date=?", (_iso(trade_date),))
        conn.executemany(
            "INSERT INTO features(trade_date, symbol, industry, in_funnel, filter_fails, features_json) VALUES (?,?,?,?,?,?)",
            [
                (_iso(trade_date), f.symbol, f.industry, int(f.symbol in funnel_set), _dump(f.filter_fails), _dump(f.to_dict()))
                for f in feats.values()
            ],
        )


def load_features(trade_date: date | str) -> tuple[list[dict], list[str]]:
    """(features dicts, funnel symbols) stored by the prep run."""
    with db() as conn:
        data = rows(conn.execute("SELECT * FROM features WHERE trade_date=?", (_iso(trade_date),)))
    feats = [json.loads(r["features_json"]) for r in data]
    funnel = [r["symbol"] for r in data if r["in_funnel"]]
    return feats, funnel


def save_candidates(trade_date: date | str, candidates, phase: str, final_symbols: set[tuple[str, str]]) -> None:
    with db() as conn:
        conn.execute("DELETE FROM candidates WHERE trade_date=?", (_iso(trade_date),))
        payload = []
        for c in candidates:
            stage = "final" if (c.symbol, c.side) in final_symbols else "sector" if c.sector_points >= config.MIN_SECTOR_POINTS else "setup"
            payload.append(
                (_iso(trade_date), c.symbol, c.side, phase, stage, c.score, c.setup_type, c.setup_label, c.industry,
                 c.sector_points, _dump(c.components), _dump(c.reasons), _dump(c.flags))
            )
        conn.executemany(
            """INSERT OR REPLACE INTO candidates(trade_date, symbol, side, phase, stage, score, setup_type, setup_label,
               sector, sector_points, components_json, reasons_json, flags_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            payload,
        )


def load_candidates(trade_date: date | str) -> list[dict]:
    with db() as conn:
        return rows(conn.execute("SELECT * FROM candidates WHERE trade_date=? ORDER BY score DESC", (_iso(trade_date),)))


# ----------------------------------------------------------------------------- picks
def save_picks(trade_date: date | str, plans, phase: str, status: str = "planned") -> list[int]:
    """Upsert picks for a day. Picks from an earlier phase that are not in `plans` become 'dropped'."""
    ids: list[int] = []
    keep = {(p.symbol, p.side) for p in plans}
    ts = now_ist().isoformat(timespec="seconds")
    with db() as conn:
        for p in plans:
            conn.execute(
                """INSERT INTO picks(trade_date, symbol, side, rank, entry, stop, target, qty, stop_pct, atr_pct, alt_stop,
                   score, setup_type, setup_label, sector, reasons_json, flags_json, components_json, entry_window,
                   squareoff_time, status, phase, preopen_gap_pct, note, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(trade_date, symbol, side) DO UPDATE SET rank=excluded.rank, entry=excluded.entry,
                   stop=excluded.stop, target=excluded.target, qty=excluded.qty, stop_pct=excluded.stop_pct,
                   atr_pct=excluded.atr_pct, alt_stop=excluded.alt_stop, score=excluded.score, setup_type=excluded.setup_type,
                   setup_label=excluded.setup_label, sector=excluded.sector, reasons_json=excluded.reasons_json,
                   flags_json=excluded.flags_json, components_json=excluded.components_json, entry_window=excluded.entry_window,
                   squareoff_time=excluded.squareoff_time, status=excluded.status, phase=excluded.phase,
                   preopen_gap_pct=excluded.preopen_gap_pct, note=excluded.note, updated_at=excluded.updated_at""",
                (
                    _iso(trade_date), p.symbol, p.side, p.rank, p.entry, p.stop, p.target, p.qty, p.stop_pct, p.atr_pct,
                    p.alt_stop, p.score, p.setup_type, p.setup_label, p.industry, _dump(p.reasons), _dump(p.flags),
                    _dump(p.components), p.entry_window, p.squareoff, status, phase, p.preopen_gap_pct, p.note, ts,
                ),
            )
            cur = conn.execute("SELECT id FROM picks WHERE trade_date=? AND symbol=? AND side=?", (_iso(trade_date), p.symbol, p.side))
            ids.append(int(cur.fetchone()[0]))
        existing = rows(conn.execute("SELECT id, symbol, side, status FROM picks WHERE trade_date=?", (_iso(trade_date),)))
        for r in existing:
            if (r["symbol"], r["side"]) not in keep and r["status"] in ("planned",):
                conn.execute("UPDATE picks SET status='dropped', phase=?, updated_at=? WHERE id=?", (phase, ts, r["id"]))
    return ids


def load_picks(trade_date: date | str, statuses: Iterable[str] | None = None) -> list[dict]:
    with db() as conn:
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            cur = conn.execute(
                f"SELECT * FROM picks WHERE trade_date=? AND status IN ({placeholders}) ORDER BY rank",
                (_iso(trade_date), *statuses),
            )
        else:
            cur = conn.execute("SELECT * FROM picks WHERE trade_date=? ORDER BY rank", (_iso(trade_date),))
        out = rows(cur)
    for r in out:
        for key in ("reasons_json", "flags_json", "components_json"):
            try:
                r[key.replace("_json", "")] = json.loads(r[key]) if r[key] else ([] if key != "components_json" else {})
            except (TypeError, json.JSONDecodeError):
                r[key.replace("_json", "")] = [] if key != "components_json" else {}
    return out


def update_pick(pick_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now_ist().isoformat(timespec="seconds")
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(f"UPDATE picks SET {cols} WHERE id=?", (*fields.values(), pick_id))


# ----------------------------------------------------------------------------- outcomes
def save_outcome(pick: dict, outcome: dict) -> None:
    with db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO outcomes(pick_id, trade_date, symbol, side, result, entry_time, exit_time, entry_price,
               exit_price, r_multiple, pnl, mfe, mae, day_high, day_low, day_close, evaluated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pick["id"], pick["trade_date"], pick["symbol"], pick["side"], outcome.get("result"),
                outcome.get("entry_time"), outcome.get("exit_time"), outcome.get("entry_price"), outcome.get("exit_price"),
                outcome.get("r_multiple"), outcome.get("pnl"), outcome.get("mfe"), outcome.get("mae"),
                outcome.get("day_high"), outcome.get("day_low"), outcome.get("day_close"),
                now_ist().isoformat(timespec="seconds"),
            ),
        )


def load_outcomes(trade_date: date | str | None = None, limit: int = 500) -> list[dict]:
    with db() as conn:
        if trade_date:
            cur = conn.execute(
                """SELECT o.*, p.entry, p.stop, p.target, p.qty, p.setup_type, p.sector, p.status, p.score
                   FROM outcomes o JOIN picks p ON p.id = o.pick_id WHERE o.trade_date=? ORDER BY p.rank""",
                (_iso(trade_date),),
            )
        else:
            cur = conn.execute(
                """SELECT o.*, p.entry, p.stop, p.target, p.qty, p.setup_type, p.sector, p.status, p.score
                   FROM outcomes o JOIN picks p ON p.id = o.pick_id ORDER BY o.trade_date DESC, p.rank LIMIT ?""",
                (limit,),
            )
        return rows(cur)


WATCHLIST_COLS = (
    "month", "as_of", "symbol", "name", "industry", "rank", "is_index", "close", "ret_1w", "ret_1m", "ret_3m",
    "month_high", "month_low", "range_pos", "atr_pct", "med_turnover_cr", "avg_volume", "sma50", "sma200",
    "pct_from_sma50", "pct_from_sma200", "regime", "picks_last_month", "r_last_month", "vix",
)


def save_watchlist(month: str, as_of: date | str, rows_in: list[dict]) -> None:
    with db() as conn:
        conn.execute("DELETE FROM watchlist WHERE month=?", (month,))
        conn.executemany(
            f"INSERT INTO watchlist({', '.join(WATCHLIST_COLS)}) VALUES ({', '.join('?' for _ in WATCHLIST_COLS)})",
            [tuple(r.get(c) if c != "as_of" else _iso(as_of) for c in WATCHLIST_COLS) for r in rows_in],
        )


def watchlist_exists(month: str) -> bool:
    with db() as conn:
        return conn.execute("SELECT 1 FROM watchlist WHERE month=? LIMIT 1", (month,)).fetchone() is not None


def load_watchlist(month: str | None = None) -> list[dict]:
    with db() as conn:
        if month is None:
            row = conn.execute("SELECT max(month) FROM watchlist").fetchone()
            month = row[0] if row else None
        if not month:
            return []
        return rows(conn.execute("SELECT * FROM watchlist WHERE month=? ORDER BY is_index DESC, rank", (month,)))


def table_rows(table: str, since: str | None = None) -> list[dict]:
    """Raw rows for the Supabase sync. `since` filters on trade_date when the table has one."""
    with db() as conn:
        if table == "watchlist":
            if since:
                return rows(conn.execute("SELECT * FROM watchlist WHERE month >= ?", (since[:7],)))
            return rows(conn.execute("SELECT * FROM watchlist"))
        if since and table != "runs":
            return rows(conn.execute(f"SELECT * FROM {table} WHERE trade_date >= ?", (since,)))
        if since:
            return rows(conn.execute("SELECT * FROM runs WHERE trade_date >= ?", (since,)))
        return rows(conn.execute(f"SELECT * FROM {table}"))
