"""Orchestration of the four daily modes plus doctor/fetch.

Every mode is idempotent per (trade_date, mode): a second run is a no-op unless --force. Modes
that only make sense inside a time window (morning, confirm, scorecard) refuse to run outside
it unless --force or --as-of is given.
"""
from __future__ import annotations

import json
import math
import sys
import time
import traceback
from datetime import date
from statistics import median

import pandas as pd

from . import (
    config, datasource as ds, nse, notify, orb, outcomes as oc, plan as planmod, report, scoring, screens,
    sectors as sec, sentiment, storage, trading_calendar as cal, universe as uni,
)
from .confirm import confirm_picks
from .screens import Features
from .sectors import SectorStrength
from .util import log, now_ist

logger = log("pipeline")


# ----------------------------------------------------------------------------- shared helpers
def _index_tickers() -> list[str]:
    return sorted({config.NIFTY, config.VIX, config.BANKNIFTY, *uni.INDEX_FOR_INDUSTRY.values()})


def _load_market_data(universe_df: pd.DataFrame, as_of: date | None, offline: bool, with_intraday: bool = True):
    stock_tickers = universe_df["yahoo"].tolist()
    t0 = time.time()
    daily = ds.daily(stock_tickers + _index_tickers(), period="1y", as_of=as_of, offline=offline)
    logger.info("daily data for %d/%d tickers in %.0fs", len(daily), len(stock_tickers) + len(_index_tickers()), time.time() - t0)
    intraday: dict[str, pd.DataFrame] = {}
    if with_intraday:
        t0 = time.time()
        intraday = ds.intraday(stock_tickers, interval="15m", period="60d", as_of=as_of, offline=offline)
        logger.info("15m data for %d tickers in %.0fs", len(intraday), time.time() - t0)
    return daily, intraday


def _compute_features(universe_df: pd.DataFrame, daily: dict, intraday: dict) -> dict[str, Features]:
    feats: dict[str, Features] = {}
    for row in universe_df.itertuples(index=False):
        df = daily.get(row.yahoo)
        if df is None:
            continue
        f = screens.compute_features(row.symbol, row.industry, row.yahoo, df, intraday.get(row.yahoo))
        if f is not None:
            feats[row.symbol] = f
    return feats


def _sector_map_from_rows(rows: list[dict]) -> dict[str, SectorStrength]:
    out = {}
    for r in rows:
        r = {k: v for k, v in r.items() if k != "trade_date"}
        out[r["sector"]] = SectorStrength(**r)
    return out


def _orb() -> bool:
    return config.DECISION_MODE == "orb"


def _rank(feats, funnel, sector_map, mood) -> scoring.RankResult:
    """Evening mode: the mood picks the side. Opening-range mode: candidates on both sides."""
    if not _orb():
        return scoring.rank(feats, funnel, sector_map, mood)
    per_side = 0 if mood.label == "no_trade" else config.ORB_CANDIDATES_PER_SIDE
    return scoring.rank(feats, funnel, sector_map, mood, sides=["long", "short"], quota={"long": per_side, "short": per_side})


def _build_plans(result: scoring.RankResult) -> list[planmod.TradePlan]:
    plans = []
    for i, cand in enumerate(result.picks, start=1):
        p = planmod.build(cand, i)
        if p is not None:
            plans.append(p)
    for i, p in enumerate(plans, start=1):
        p.rank = i
    return plans


def _latest_fii(session: date, offline: bool) -> dict | None:
    stored = storage.load_fii_dii(session)
    if stored and stored.get("fii_net") is not None:
        return stored
    if offline:
        return None
    fii = nse.fii_dii()
    if fii:
        storage.save_fii_dii(fii.get("date") or session, fii)
    return fii


def _nifty_gap_from_preopen(rows: list[dict]) -> float | None:
    """Median pre-open gap of Nifty 50 constituents as a proxy for the index gap."""
    gaps = [r["gap_pct"] for r in rows if r.get("gap_pct") is not None]
    return float(median(gaps)) if len(gaps) >= 20 else None


def _guard(mode: str, trade_date: date, force: bool) -> bool:
    if not cal.is_trading_day(trade_date):
        logger.info("%s: %s is not a trading day; nothing to do", mode, trade_date)
        return False
    if storage.run_done(trade_date, mode) and not force:
        logger.info("%s already completed for %s (use --force to repeat)", mode, trade_date)
        return False
    return True


# ----------------------------------------------------------------------------- prep (evening)
def run_prep(as_of: date | None = None, dry_run: bool = False, force: bool = False, offline: bool = False) -> dict | None:
    now = now_ist()
    session = as_of or cal.last_completed_session(now)
    trade_date = cal.next_trading_day(session)
    if not _guard("prep", trade_date, force):
        return None
    run_id = storage.start_run(trade_date, "prep")
    try:
        universe_df = uni.load_universe()
        daily, intraday = _load_market_data(universe_df, session, offline)
        feats = _compute_features(universe_df, daily, intraday)
        funnel = screens.liquidity_funnel(feats)
        sectors = sec.sector_strength(universe_df, daily, daily.get(config.NIFTY), {t: daily[t] for t in _index_tickers() if t in daily})
        fii = _latest_fii(session, offline)
        global_q = {} if offline else ds.quotes(list(config.GLOBAL_TICKERS))
        mood = sentiment.assess(trade_date, daily.get(config.NIFTY), daily.get(config.VIX), fii, global_q)
        result = _rank(feats, funnel, sec.as_map(sectors), mood)
        plans = [] if _orb() else _build_plans(result)

        storage.save_features(trade_date, feats, funnel)
        storage.save_sectors(trade_date, sectors)
        storage.save_market_context(mood, "prep")
        storage.save_candidates(trade_date, result.shortlist, "prep", {(c.symbol, c.side) for c in result.picks})
        storage.save_picks(trade_date, plans, "prep")

        text = report.prep_message(trade_date, mood, result.counts, result.shortlist, plans, sectors,
                                   candidates=result.picks if _orb() else None)
        message_id = notify.send(text, dry_run=dry_run)
        storage.finish_run(run_id, "ok", message_id, f"{len(plans)} provisional picks, mood {mood.label}")
        from . import watchlist  # local import: watchlist imports pipeline helpers

        watchlist.ensure_current(session)
        return {"trade_date": trade_date, "mood": mood, "plans": plans, "result": result, "sectors": sectors}
    except Exception as exc:  # noqa: BLE001
        storage.finish_run(run_id, "error", None, f"{type(exc).__name__}: {exc}")
        logger.error("prep failed: %s\n%s", exc, traceback.format_exc())
        raise


# ----------------------------------------------------------------------------- morning (09:10)
def run_morning(as_of: date | None = None, dry_run: bool = False, force: bool = False, offline: bool = False) -> dict | None:
    now = now_ist()
    trade_date = as_of or now.date()
    if as_of is None and now.time() > config.MORNING_CUTOFF and not force:
        logger.info("morning: past cutoff %s; not sending stale picks", config.MORNING_CUTOFF)
        return None
    if not _guard("morning", trade_date, force):
        return None
    run_id = storage.start_run(trade_date, "morning")
    try:
        feat_dicts, funnel = storage.load_features(trade_date)
        if not feat_dicts:
            logger.info("no prep data for %s; running prep inline", trade_date)
            run_prep(as_of=cal.prev_trading_day(trade_date), dry_run=True, force=True, offline=offline)
            feat_dicts, funnel = storage.load_features(trade_date)
        feats = {d["symbol"]: Features.from_dict(d) for d in feat_dicts}
        sector_map = _sector_map_from_rows(storage.load_sectors(trade_date))

        preopen_fo = nifty_rows = []
        results = {}
        ban: set[str] = set()
        live_guards = not offline and (as_of is None or as_of >= now.date())
        if live_guards:
            preopen_fo = nse.pre_open("FO")
            nifty_rows = nse.pre_open("NIFTY")
            results = nse.results_calendar()
            ban, _ = nse.fo_ban_list()
        screens.apply_morning_guards(feats, trade_date, preopen_fo, results, ban)
        nifty_gap = _nifty_gap_from_preopen(nifty_rows)

        session = cal.prev_trading_day(trade_date)
        fii = _latest_fii(session, offline)
        global_q = {} if offline else ds.quotes(list(config.GLOBAL_TICKERS) + [config.VIX])
        vix_live = global_q.pop(config.VIX, {}).get("last") if global_q else None
        daily = ds.daily([config.NIFTY, config.VIX], as_of=session, offline=True)
        mood = sentiment.assess(trade_date, daily.get(config.NIFTY), daily.get(config.VIX), fii, global_q, nifty_gap, vix_live)
        result = _rank(feats, funnel, sector_map, mood)
        plans = [] if _orb() else _build_plans(result)

        guards = {
            "results": sorted(s for s, f in feats.items() if f.results_date and s in funnel),
            "ban": sorted(s for s, f in feats.items() if f.in_ban and s in funnel),
            "gap_skipped": sorted(s for s, f in feats.items() if any(x.startswith("gap") for x in f.filter_fails) and s in funnel),
        }
        storage.save_features(trade_date, feats, funnel)
        storage.save_market_context(mood, "morning")
        storage.save_candidates(trade_date, result.shortlist, "morning", {(c.symbol, c.side) for c in result.picks})
        storage.save_picks(trade_date, plans, "morning")

        if mood.label == "no_trade":
            text = report.no_trade_message(trade_date, mood, result.counts)
        elif _orb():
            longs = [c for c in result.picks if c.side == "long"]
            shorts = [c for c in result.picks if c.side == "short"]
            text = report.orb_candidates_message(trade_date, mood, result.counts, longs, shorts, guards)
        else:
            text = report.morning_message(trade_date, mood, result.counts, plans, guards)
        message_id = notify.send(text, dry_run=dry_run)
        storage.finish_run(run_id, "ok", message_id, f"{len(plans)} picks, mood {mood.label}")
        return {"trade_date": trade_date, "mood": mood, "plans": plans, "result": result}
    except Exception as exc:  # noqa: BLE001
        storage.finish_run(run_id, "error", None, f"{type(exc).__name__}: {exc}")
        logger.error("morning failed: %s\n%s", exc, traceback.format_exc())
        raise


# ----------------------------------------------------------------------------- confirm (09:34)
def run_confirm(as_of: date | None = None, dry_run: bool = False, force: bool = False, offline: bool = False) -> list | None:
    now = now_ist()
    trade_date = as_of or now.date()
    if as_of is None and not force:
        if now.time() < config.CONFIRM_START:
            logger.info("confirm: before %s, the opening candle is not complete", config.CONFIRM_START)
            return None
        if now.time() > config.CONFIRM_CUTOFF:
            logger.info("confirm: past cutoff %s", config.CONFIRM_CUTOFF)
            return None
    if not _guard("confirm", trade_date, force):
        return None
    if _orb():
        return _confirm_orb(trade_date, dry_run, offline, replay=as_of is not None)
    picks = storage.load_picks(trade_date, ["planned"])
    if not picks:
        logger.info("confirm: no planned picks for %s", trade_date)
        storage.finish_run(storage.start_run(trade_date, "confirm"), "ok", None, "no picks")
        return []
    run_id = storage.start_run(trade_date, "confirm")
    try:
        feat_dicts, _ = storage.load_features(trade_date)
        features = {d["symbol"]: d for d in feat_dicts}
        yahoo_of = {d["symbol"]: d["yahoo"] for d in feat_dicts}
        results = confirm_picks(trade_date, picks, features, yahoo_of, offline=offline)
        attempts = 0
        while any(r.status == "pending" for r in results) and attempts < 4 and as_of is None and not offline:
            attempts += 1
            logger.info("opening candle not complete yet; retry %d in 60s", attempts)
            time.sleep(60)
            results = confirm_picks(trade_date, picks, features, yahoo_of)
        for r in results:
            if r.status == "pending":
                continue
            storage.update_pick(
                r.pick_id, status=r.status, confirm_note=r.note, confirmed_at=now_ist().isoformat(timespec="seconds")
            )
        text = report.confirm_message(trade_date, results)
        message_id = notify.send(text, reply_to=storage.run_message_id(trade_date, "morning"), dry_run=dry_run)
        storage.finish_run(run_id, "ok", message_id, f"{sum(1 for r in results if r.status == 'confirmed')} confirmed")
        return results
    except Exception as exc:  # noqa: BLE001
        storage.finish_run(run_id, "error", None, f"{type(exc).__name__}: {exc}")
        logger.error("confirm failed: %s\n%s", exc, traceback.format_exc())
        raise


# ----------------------------------------------------------------------------- 09:34 opening-range decision
def _prev_close_from_bars(bars15: pd.DataFrame | None, day: date) -> float | None:
    if bars15 is None or bars15.empty:
        return None
    before = bars15[bars15.index.date < day]
    return float(before["Close"].iloc[-1]) if len(before) else None


def _orb_trade_plan(cand: dict, f: Features, o_r: orb.OpeningRange, n_or: orb.OpeningRange, side: str, rank: int) -> planmod.TradePlan | None:
    geom = orb.orb_plan(o_r, side, config.ORB_TARGET_R)
    entry, stop, target = geom["entry"], geom["stop"], geom["target"]
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0 or entry <= 0:
        return None
    qty = math.floor(config.CAPITAL * config.RISK_PCT / 100.0 / risk_per_share)
    max_qty = math.floor(config.CAPITAL * config.MAX_LEVERAGE / entry)
    note = ""
    if qty > max_qty:
        qty, note = max_qty, f"qty capped by {config.MAX_LEVERAGE:.0f}x leverage"
    if qty < 1:
        return None
    try:
        reasons = list(json.loads(cand.get("reasons_json") or "[]"))[:2]
        flags = list(json.loads(cand.get("flags_json") or "[]"))
    except json.JSONDecodeError:
        reasons, flags = [], []
    reasons.append(f"opening candle {o_r.pct:+.2f}% vs Nifty {n_or.pct:+.2f}%, range {o_r.range_pct:.1f}%")
    return planmod.TradePlan(
        symbol=cand["symbol"], industry=f.industry, side=side, rank=rank, entry=entry, stop=stop, target=target, qty=int(qty),
        stop_pct=round(geom["stop_pct"], 2), risk_per_share=round(risk_per_share, 2), risk_amount=round(qty * risk_per_share, 2),
        notional=round(qty * entry, 2), atr_pct=f.atr_pct, score=float(cand.get("score") or 0.0), setup_type=cand.get("setup_type"),
        setup_label=cand.get("setup_label") or "", reasons=reasons, flags=flags,
        entry_window=f"09:30-{config.ORB_ENTRY_DEADLINE.strftime('%H:%M')}", squareoff=config.SQUAREOFF.strftime("%H:%M"),
        alt_stop=None, note=note, preopen_gap_pct=f.preopen_gap_pct, components={},
    )


def _confirm_orb(trade_date: date, dry_run: bool, offline: bool, replay: bool) -> list | None:
    """Read the Nifty's opening candle, pick the side, confirm candidates on their own candle, send picks."""
    run_id = storage.start_run(trade_date, "confirm")
    try:
        ctx = storage.load_market_context(trade_date) or {}
        if ctx.get("mood") == "no_trade":
            storage.finish_run(run_id, "ok", None, "no-trade day (morning run)")
            return []
        caution = bool(ctx.get("caution"))
        feat_dicts, _ = storage.load_features(trade_date)
        feats = {d["symbol"]: Features.from_dict(d) for d in feat_dicts}
        cands = storage.load_candidates(trade_date)

        n_or = None
        attempts = 0
        while True:
            nifty15 = ds.intraday([config.NIFTY], interval="15m", period="5d", offline=offline).get(config.NIFTY)
            prev_close = _prev_close_from_bars(nifty15, trade_date)
            n_or = orb.opening_range(nifty15, trade_date, prev_close or 1.0)
            if n_or is not None or offline or replay or attempts >= 4:
                break
            attempts += 1
            logger.info("Nifty opening candle not available yet; retry %d in 60s", attempts)
            time.sleep(60)
        if n_or is None:
            text = f"🕤 09:34: the Nifty opening candle is not available yet, no decision for {trade_date:%d %b}. Check the chart manually."
            message_id = notify.send(text, reply_to=storage.run_message_id(trade_date, "morning"), dry_run=dry_run)
            storage.finish_run(run_id, "error", message_id, "no nifty opening candle")
            return None

        direction = orb.market_direction(n_or)
        plans: list[planmod.TradePlan] = []
        rejected: list[tuple[str, list[str]]] = []
        if direction != "flat":
            side = "long" if direction == "up" else "short"
            rows = [c for c in cands if c["side"] == side and c["symbol"] in feats]
            tickers = [feats[c["symbol"]].yahoo for c in rows]
            bars15 = ds.intraday(tickers, interval="15m", period="60d", offline=offline) if tickers else {}
            scored = []
            for c in rows:
                f = feats[c["symbol"]]
                o_r = orb.opening_range(bars15.get(f.yahoo), trade_date, f.close)
                if o_r is None:
                    rejected.append((c["symbol"], ["no opening candle"]))
                    continue
                ok, fails = orb.qualifies(f, o_r, orb.ema200_at_open(bars15.get(f.yahoo), trade_date), side)
                if not ok:
                    rejected.append((c["symbol"], fails))
                    continue
                rel_strength = (o_r.pct - n_or.pct) * (1 if side == "long" else -1)
                scored.append((float(c.get("score") or 0.0) + rel_strength / 10.0, c, f, o_r))
            scored.sort(key=lambda x: -x[0])
            n = config.PICKS_TRENDING // 2 if caution else config.PICKS_TRENDING
            for rank_i, (_, c, f, o_r) in enumerate(scored[:n], start=1):
                p = _orb_trade_plan(c, f, o_r, n_or, side, rank_i)
                if p is not None:
                    plans.append(p)
        storage.save_picks(trade_date, plans, "orb", status="confirmed")
        text = report.orb_decision_message(trade_date, direction, n_or.pct, plans, rejected, caution)
        message_id = notify.send(text, reply_to=storage.run_message_id(trade_date, "morning"), dry_run=dry_run)
        storage.finish_run(run_id, "ok", message_id, f"nifty {direction} {n_or.pct:+.2f}%: {len(plans)} picks, {len(rejected)} rejected")
        return plans
    except Exception as exc:  # noqa: BLE001
        storage.finish_run(run_id, "error", None, f"{type(exc).__name__}: {exc}")
        logger.error("confirm (orb) failed: %s\n%s", exc, traceback.format_exc())
        raise


# ----------------------------------------------------------------------------- scorecard (15:45)
def run_scorecard(as_of: date | None = None, dry_run: bool = False, force: bool = False, offline: bool = False) -> list | None:
    now = now_ist()
    trade_date = as_of or now.date()
    if as_of is None and now.time() < config.SCORECARD_START and not force:
        logger.info("scorecard: market still open")
        return None
    if not _guard("scorecard", trade_date, force):
        return None
    run_id = storage.start_run(trade_date, "scorecard")
    try:
        picks = storage.load_picks(trade_date, ["planned", "confirmed", "cancelled"])
        feat_dicts, _ = storage.load_features(trade_date)
        yahoo_of = {d["symbol"]: d["yahoo"] for d in feat_dicts}
        evaluated: list[dict] = []
        for p in picks:
            y = yahoo_of.get(p["symbol"], f"{p['symbol']}.NS")
            bars = ds.intraday([y], interval="5m", period="5d", offline=offline).get(y) if offline else ds.today_bars(y, "5m", trade_date)
            outcome = oc.evaluate(p, bars, trade_date)
            storage.save_outcome(p, outcome)
            evaluated.append({**p, **outcome})
        nifty_ret = None
        nifty = ds.daily([config.NIFTY], period="1mo", offline=offline).get(config.NIFTY)
        if nifty is not None and len(nifty) >= 2 and nifty.index[-1].date() == trade_date:
            nifty_ret = (float(nifty["Close"].iloc[-1]) / float(nifty["Close"].iloc[-2]) - 1.0) * 100.0
            storage.save_nifty_day_return(trade_date, nifty_ret)
        stats = oc.summarize(evaluated)
        history = storage.load_outcomes(limit=5000)
        confirmed_hist = [h for h in history if h.get("status") == "confirmed" and h.get("r_multiple") is not None]
        stats["cum_r"] = round(sum(h["r_multiple"] for h in confirmed_hist), 2)
        stats["days"] = len({h["trade_date"] for h in history})
        text = report.scorecard_message(trade_date, evaluated, nifty_ret, stats)
        message_id = notify.send(text, reply_to=storage.run_message_id(trade_date, "morning"), dry_run=dry_run)
        storage.finish_run(run_id, "ok", message_id, f"{len(evaluated)} evaluated, {stats['total_r']:+.2f}R")
        return evaluated
    except Exception as exc:  # noqa: BLE001
        storage.finish_run(run_id, "error", None, f"{type(exc).__name__}: {exc}")
        logger.error("scorecard failed: %s\n%s", exc, traceback.format_exc())
        raise


# ----------------------------------------------------------------------------- doctor / fetch
def run_doctor() -> bool:
    ok = True

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(f"  [{'ok' if passed else 'FAIL'}] {name}{': ' + detail if detail else ''}")

    print(f"Python {sys.version.split()[0]} · now {now_ist():%Y-%m-%d %H:%M %Z}")
    check("python >= 3.11", sys.version_info >= (3, 11))
    try:
        config.ensure_dirs()
        test = config.DATA_DIR / ".write_test"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        check("DATA_DIR writable", True, str(config.DATA_DIR))
    except OSError as exc:
        check("DATA_DIR writable", False, str(exc))
    check("DATA_DIR outside OneDrive", "onedrive" not in str(config.DATA_DIR).lower(), str(config.DATA_DIR))
    try:
        with storage.db() as conn:
            n = conn.execute("SELECT count(*) FROM runs").fetchone()[0]
        check("sqlite schema", True, f"{config.DB_PATH} ({n} runs)")
    except Exception as exc:  # noqa: BLE001
        check("sqlite schema", False, str(exc))
    try:
        u = uni.load_universe()
        check("universe", len(u) >= 90, f"{len(u)} symbols, {u['industry'].nunique()} industries")
    except Exception as exc:  # noqa: BLE001
        check("universe", False, str(exc))
    hol = cal.holidays_for(date.today().year)
    check("holiday calendar", len(hol) >= 10, f"{len(hol)} holidays in {date.today().year}")
    q = ds.quotes(["RELIANCE.NS", config.NIFTY])
    check("yahoo finance", "RELIANCE.NS" in q and config.NIFTY in q, ", ".join(f"{k} {v['last']:.0f}" for k, v in q.items()))
    fii = nse.fii_dii()
    check("nse fii/dii", fii is not None, f"FII {fii['fii_net']:+,.0f} cr on {fii['date']}" if fii else "unavailable")
    if notify.configured():
        me = notify.get_me()
        check("telegram bot", me is not None, f"@{me.get('username')}" if me else "getMe failed")
    else:
        check("telegram bot", False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set (messages print to console)")
    check("sizing", config.CAPITAL > 0 and 0 < config.RISK_PCT <= 5, f"capital {config.CAPITAL:,.0f}, risk {config.RISK_PCT}%/trade")
    print("all checks passed" if ok else "some checks failed")
    return ok


def run_fetch(check: bool = True) -> None:
    universe_df = uni.load_universe()
    daily, intraday = _load_market_data(universe_df, None, offline=False)
    stocks = universe_df["yahoo"].tolist()
    have_daily = [t for t in stocks if t in daily]
    short_daily = [t for t in have_daily if len(daily[t]) < 240]
    have_15m = [t for t in stocks if t in intraday]
    short_15m = [t for t in have_15m if len(intraday[t]) < 1400]
    idx_missing = [t for t in _index_tickers() if t not in daily]
    print(f"daily: {len(have_daily)}/{len(stocks)} stocks (short history: {short_daily or 'none'})")
    print(f"15m: {len(have_15m)}/{len(stocks)} stocks (short history: {short_15m or 'none'})")
    print(f"indices: {len(_index_tickers()) - len(idx_missing)}/{len(_index_tickers())} (missing: {idx_missing or 'none'})")
    if check:
        po = nse.pre_open("FO")
        print(f"pre-open rows: {len(po)} · holidays: {len(cal.holidays_for(date.today().year))}")
