"""09:34 confirmation: does the first 15-minute candle support the plan?

Notebook rules enforced here: "wait for confirmation before trade", "be safe from fake
breakouts", "15 min - 200 EMA". A pick is confirmed only if the first candle keeps the stock on
the right side of the 15-minute EMA200, has not hit the stop, has not already reached the
target, and (for breakouts) has not fallen back through the broken level.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from . import config, datasource as ds, indicators as ind
from .util import log, round_tick

logger = log("confirm")


@dataclass
class ConfirmResult:
    pick_id: int
    symbol: str
    side: str
    status: str                 # confirmed | cancelled | pending
    note: str
    first_open: float | None = None
    first_high: float | None = None
    first_low: float | None = None
    first_close: float | None = None
    ema200_15m: float | None = None
    suggested_entry: float | None = None
    suggested_stop: float | None = None


def _first_bar(bars: pd.DataFrame, trade_date: date) -> pd.Series | None:
    day = bars[bars.index.date == trade_date]
    if day.empty:
        return None
    first = day.iloc[0]
    if first.name.time() > config.MARKET_OPEN.replace(minute=config.MARKET_OPEN.minute + 1):
        return None            # the 09:15 bar is missing; whatever this is, it is not the opening candle
    return first


def check(pick: dict, feature: dict | None, bars15: pd.DataFrame | None, trade_date: date) -> ConfirmResult:
    base = ConfirmResult(pick_id=pick["id"], symbol=pick["symbol"], side=pick["side"], status="pending", note="")
    if bars15 is None or bars15.empty:
        base.note = "no 15-minute data yet"
        return base
    first = _first_bar(bars15, trade_date)
    if first is None:
        base.note = "opening candle not available yet"
        return base
    # a 15m bar is complete only once the next bar has started; before 09:30 Yahoo serves a partial bar
    upto = bars15[bars15.index <= first.name]
    ema = ind.ema(upto["Close"], config.EMA_15M)
    ema_val = float(ema.iloc[-1]) if len(ema.dropna()) else None

    o, h, l, c = (float(first[k]) for k in ("Open", "High", "Low", "Close"))
    base.first_open, base.first_high, base.first_low, base.first_close, base.ema200_15m = o, h, l, c, ema_val
    side = pick["side"]
    entry, stop, target = float(pick["entry"]), float(pick["stop"]), float(pick["target"])
    prev_close = float(feature["close"]) if feature else None
    level = None
    if feature and pick.get("setup_type") in ("breakout", "breakdown"):
        level = feature.get("hh20") if side == "long" else feature.get("ll20")

    reasons_fail: list[str] = []
    notes_ok: list[str] = []
    if side == "long":
        if ema_val is not None and c < ema_val:
            reasons_fail.append(f"closed below 15-min EMA200 ({ema_val:.2f})")
        if l <= stop:
            reasons_fail.append(f"stop {stop:.2f} already hit in the first candle")
        if h >= target:
            reasons_fail.append(f"target {target:.2f} already reached; do not chase")
        if level is not None and l < level * 0.995:
            reasons_fail.append(f"fell back below the breakout level {level:.2f}: possible fake breakout")
        if prev_close is not None and c < prev_close:
            reasons_fail.append(f"closed below yesterday's close {prev_close:.2f}")
        if not reasons_fail:
            if ema_val is not None:
                notes_ok.append(f"above 15-min EMA200 ({ema_val:.2f})")
            if c > entry:
                notes_ok.append("already through the trigger; enter only on a hold above the first-candle high")
                base.suggested_entry = round_tick(h + config.TICK)
            else:
                base.suggested_entry = entry
            cand_stop = max(stop, round_tick(l - config.TICK))
            if (base.suggested_entry - cand_stop) / base.suggested_entry * 100 <= config.STOP_MAX_PCT and cand_stop < base.suggested_entry:
                base.suggested_stop = cand_stop
            else:
                base.suggested_stop = stop
    else:
        if ema_val is not None and c > ema_val:
            reasons_fail.append(f"closed above 15-min EMA200 ({ema_val:.2f})")
        if h >= stop:
            reasons_fail.append(f"stop {stop:.2f} already hit in the first candle")
        if l <= target:
            reasons_fail.append(f"target {target:.2f} already reached; do not chase")
        if level is not None and h > level * 1.005:
            reasons_fail.append(f"bounced back above the breakdown level {level:.2f}: possible fake breakdown")
        if prev_close is not None and c > prev_close:
            reasons_fail.append(f"closed above yesterday's close {prev_close:.2f}")
        if not reasons_fail:
            if ema_val is not None:
                notes_ok.append(f"below 15-min EMA200 ({ema_val:.2f})")
            if c < entry:
                notes_ok.append("already through the trigger; enter only on a hold below the first-candle low")
                base.suggested_entry = round_tick(l - config.TICK)
            else:
                base.suggested_entry = entry
            cand_stop = min(stop, round_tick(h + config.TICK))
            if (cand_stop - base.suggested_entry) / base.suggested_entry * 100 <= config.STOP_MAX_PCT and cand_stop > base.suggested_entry:
                base.suggested_stop = cand_stop
            else:
                base.suggested_stop = stop

    if reasons_fail:
        base.status = "cancelled"
        base.note = "; ".join(reasons_fail)
    else:
        base.status = "confirmed"
        base.note = "; ".join(notes_ok) if notes_ok else "first candle holds"
    return base


def confirm_picks(trade_date: date, picks: list[dict], features: dict[str, dict], yahoo_of: dict[str, str],
                  offline: bool = False) -> list[ConfirmResult]:
    tickers = [yahoo_of.get(p["symbol"], f"{p['symbol']}.NS") for p in picks]
    bars = ds.intraday(tickers, interval="15m", period="60d", offline=offline) if tickers else {}
    out = []
    for p in picks:
        y = yahoo_of.get(p["symbol"], f"{p['symbol']}.NS")
        out.append(check(p, features.get(p["symbol"]), bars.get(y), trade_date))
    return out
