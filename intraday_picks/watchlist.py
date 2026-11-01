"""Monthly watch universe: the notebook's "30 top stocks across sectors", built from the last month.

Selection = the same liquidity funnel the daily runs use (top names per industry by 20-day median
turnover, hard filters applied), frozen once a month. Each row carries last-month statistics so the
dashboard can show what the stock has been doing; the Nifty 50 and Bank Nifty ride along as index rows.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import config, datasource as ds, indicators as ind, screens, storage, trading_calendar as cal
from . import universe as uni
from .pipeline import _index_tickers
from .screens import Features
from .util import log, now_ist

logger = log("watchlist")

WEEK, MONTH, QUARTER = 5, 21, 63
INDEX_ROWS = ((config.NIFTY, "NIFTY 50"), (config.BANKNIFTY, "BANK NIFTY"))


def _f(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(v) else v


def _window_stats(df: pd.DataFrame) -> dict:
    close = df["Close"]
    last = float(close.iloc[-1])
    month = df.iloc[-MONTH:]
    hi, lo = float(month["High"].max()), float(month["Low"].min())
    sma50, sma200 = _f(ind.sma(close, 50).iloc[-1]), _f(ind.sma(close, 200).iloc[-1])
    return {
        "close": last,
        "ret_1w": ind.returns_pct(close, WEEK),
        "ret_1m": ind.returns_pct(close, MONTH),
        "ret_3m": ind.returns_pct(close, QUARTER),
        "month_high": hi,
        "month_low": lo,
        "range_pos": ((last - lo) / (hi - lo)) if hi > lo else None,
        "atr_pct": _f(ind.atr_pct(df, 14).iloc[-1]),
        "avg_volume": _f(month["Volume"].mean()),
        "sma50": sma50,
        "sma200": sma200,
        "pct_from_sma50": ((last / sma50 - 1) * 100) if sma50 else None,
        "pct_from_sma200": ((last / sma200 - 1) * 100) if sma200 else None,
    }


def _picks_last_month(month: str) -> dict[str, tuple[int, float]]:
    """Per symbol: (number of picks, summed R) in the month before `month`."""
    year, mon = int(month[:4]), int(month[5:7])
    prev = f"{year - 1}-12" if mon == 1 else f"{year}-{mon - 1:02d}"
    out: dict[str, tuple[int, float]] = {}
    with storage.db() as conn:
        rows = storage.rows(
            conn.execute(
                """SELECT p.symbol, count(*) AS n, coalesce(sum(o.r_multiple), 0) AS r
                   FROM picks p LEFT JOIN outcomes o ON o.pick_id = p.id
                   WHERE substr(p.trade_date, 1, 7) = ? AND p.status != 'dropped' GROUP BY p.symbol""",
                (prev,),
            )
        )
    for r in rows:
        out[r["symbol"]] = (int(r["n"]), float(r["r"] or 0.0))
    return out


def build(as_of: date | None = None, offline: bool = False) -> tuple[str, date, list[dict]]:
    """(month being monitored, last session used, rows)."""
    session = as_of or cal.last_completed_session(now_ist())
    month = cal.next_trading_day(session).strftime("%Y-%m")
    universe_df = uni.load_universe()
    daily = ds.daily(universe_df["yahoo"].tolist() + _index_tickers(), period="1y", as_of=session, offline=offline)

    feats: dict[str, Features] = {}
    for r in universe_df.itertuples(index=False):
        df = daily.get(r.yahoo)
        if df is None:
            continue
        f = screens.compute_features(r.symbol, r.industry, r.yahoo, df, None)
        if f is not None:
            feats[r.symbol] = f
    chosen = screens.liquidity_funnel(feats)
    names = dict(zip(universe_df["symbol"], universe_df["name"]))
    history = _picks_last_month(month)

    rows: list[dict] = []
    vix_df = daily.get(config.VIX)
    vix = float(vix_df["Close"].iloc[-1]) if vix_df is not None and len(vix_df) else None
    for rank, (ticker, label) in enumerate(INDEX_ROWS, start=1):
        df = daily.get(ticker)
        if df is None or len(df) < QUARTER + 1:
            continue
        stats = _window_stats(df)
        ema20, ema50 = _f(ind.ema(df["Close"], 20).iloc[-1]), _f(ind.ema(df["Close"], 50).iloc[-1])
        close = stats["close"]
        regime = "bull" if ema20 and ema50 and close > ema20 > ema50 else "bear" if ema20 and ema50 and close < ema20 < ema50 else "mixed"
        rows.append({
            "month": month, "as_of": session.isoformat(), "symbol": label, "name": label, "industry": "Index", "rank": rank,
            "is_index": 1, "regime": regime, "med_turnover_cr": None, "picks_last_month": 0, "r_last_month": 0.0,
            "vix": vix if ticker == config.NIFTY else None, **stats,
        })
    for rank, symbol in enumerate(chosen, start=1):
        f = feats[symbol]
        df = daily[f.yahoo]
        n, r = history.get(symbol, (0, 0.0))
        rows.append({
            "month": month, "as_of": session.isoformat(), "symbol": symbol, "name": names.get(symbol, symbol),
            "industry": f.industry, "rank": rank, "is_index": 0, "regime": f.regime, "med_turnover_cr": f.med_turnover_cr,
            "picks_last_month": n, "r_last_month": round(r, 2), "vix": None, **_window_stats(df),
        })
    return month, session, rows


def print_table(month: str, session: date, rows: list[dict]) -> None:
    print(f"\nWatch universe for {month} (built from data up to {session})")
    print(f"{'#':>3} {'symbol':<12}{'sector':<16}{'close':>10}{'1w%':>7}{'1m%':>7}{'3m%':>7}{'trend':>7}{'ATR%':>6}{'turn cr':>9}{'vs50d':>7}{'range':>6}")
    for r in rows:
        sector = uni.sector_short(r["industry"]) if r["industry"] != "Index" else "Index"
        turn = f"{r['med_turnover_cr']:.0f}" if r.get("med_turnover_cr") else "-"
        rng = f"{r['range_pos'] * 100:.0f}%" if r.get("range_pos") is not None else "-"
        print(
            f"{r['rank']:>3} {r['symbol']:<12}{sector[:15]:<16}{r['close']:>10.2f}{(r['ret_1w'] or 0):>+7.1f}{(r['ret_1m'] or 0):>+7.1f}"
            f"{(r['ret_3m'] or 0):>+7.1f}{r['regime']:>7}{(r['atr_pct'] or 0):>6.1f}{turn:>9}{(r['pct_from_sma50'] or 0):>+7.1f}{rng:>6}"
        )


def run(as_of: date | None = None, offline: bool = False, dry_run: bool = False, quiet: bool = False) -> list[dict]:
    month, session, rows = build(as_of, offline)
    if not dry_run:
        storage.save_watchlist(month, session, rows)
    if not quiet:
        print_table(month, session, rows)
    logger.info("watchlist for %s: %d rows (as of %s)%s", month, len(rows), session, " (dry-run)" if dry_run else "")
    return rows


def ensure_current(session: date) -> None:
    """Called by the evening run: build the month's list the first time a month is seen."""
    month = cal.next_trading_day(session).strftime("%Y-%m")
    if storage.watchlist_exists(month):
        return
    try:
        run(as_of=session, offline=True, quiet=True)
    except Exception as exc:  # noqa: BLE001 - the watchlist must never break the trading run
        logger.warning("watchlist build failed: %s", exc)
