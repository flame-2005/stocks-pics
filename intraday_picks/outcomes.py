"""What actually happened: replay a pick against the day's 5-minute bars.

Rules: entries only inside the configured windows and never in the first 15 minutes; fills
through a gap happen at the bar open; if a single bar touches both stop and target the stop
wins (conservative); anything still open at square-off time exits at that bar's open.
"""
from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd

from . import config
from .util import log

logger = log("outcomes")


def _in_window(t: time, windows=None) -> bool:
    return any(a <= t < b for a, b in (windows or config.ENTRY_WINDOWS))


def windows_for(pick: dict):
    """Opening-range picks may only be entered until the deadline; evening picks use both windows."""
    if pick.get("phase") == "orb":
        return ((time(9, 30), config.ORB_ENTRY_DEADLINE),)
    return config.ENTRY_WINDOWS


def evaluate(pick: dict, bars: pd.DataFrame, trade_date: date, windows=None) -> dict:
    windows = windows or windows_for(pick)
    side = pick["side"]
    entry, stop, target, qty = float(pick["entry"]), float(pick["stop"]), float(pick["target"]), int(pick.get("qty") or 0)
    risk = abs(entry - stop)
    out: dict = {
        "result": "no_entry", "entry_time": None, "exit_time": None, "entry_price": None, "exit_price": None,
        "r_multiple": None, "pnl": None, "mfe": None, "mae": None, "day_high": None, "day_low": None, "day_close": None,
    }
    if bars is None or bars.empty or risk <= 0:
        out["result"] = "skipped"
        return out
    day = bars[bars.index.date == trade_date].sort_index()
    if day.empty:
        out["result"] = "skipped"
        return out
    out["day_high"], out["day_low"], out["day_close"] = float(day["High"].max()), float(day["Low"].min()), float(day["Close"].iloc[-1])

    long = side == "long"
    fill: float | None = None
    fill_time: datetime | None = None
    mfe = mae = 0.0

    def r_of(price: float) -> float:
        return ((price - fill) if long else (fill - price)) / risk

    for ts, bar in day.iterrows():
        t = ts.time()
        o, h, l, c = float(bar["Open"]), float(bar["High"]), float(bar["Low"]), float(bar["Close"])
        if fill is None:
            if t >= config.SQUAREOFF or not _in_window(t, windows):
                continue
            triggered = h >= entry if long else l <= entry
            if not triggered:
                continue
            fill = max(entry, o) if long else min(entry, o)
            fill_time = ts
            out["entry_time"], out["entry_price"] = ts.isoformat(), round(fill, 2)
            # same-bar resolution, conservative
            hit_stop = l <= stop if long else h >= stop
            hit_target = h >= target if long else l <= target
            if hit_stop:
                exit_price = stop
                out.update(result="stop", exit_time=ts.isoformat(), exit_price=exit_price)
                break
            if hit_target:
                out.update(result="target", exit_time=ts.isoformat(), exit_price=target)
                break
            mfe, mae = max(mfe, r_of(h if long else l)), min(mae, r_of(l if long else h))
            continue

        mfe, mae = max(mfe, r_of(h if long else l)), min(mae, r_of(l if long else h))
        if t >= config.SQUAREOFF:
            out.update(result="eod_close", exit_time=ts.isoformat(), exit_price=o)
            break
        hit_stop = l <= stop if long else h >= stop
        hit_target = h >= target if long else l <= target
        if hit_stop:
            gap_through = (o < stop) if long else (o > stop)
            out.update(result="stop", exit_time=ts.isoformat(), exit_price=o if gap_through else stop)
            break
        if hit_target:
            out.update(result="target", exit_time=ts.isoformat(), exit_price=target)
            break
    else:
        if fill is not None:                      # ran out of bars before square-off time (data ended early)
            last = day.iloc[-1]
            out.update(result="eod_close", exit_time=day.index[-1].isoformat(), exit_price=float(last["Close"]))

    if fill is not None and out["exit_price"] is not None:
        exit_price = float(out["exit_price"])
        r = ((exit_price - fill) if long else (fill - exit_price)) / risk
        out["r_multiple"] = round(r, 3)
        out["pnl"] = round(((exit_price - fill) if long else (fill - exit_price)) * qty, 2)
        out["mfe"], out["mae"] = round(mfe, 3), round(mae, 3)
        out["exit_price"] = round(exit_price, 2)
    return out


def summarize(outcomes: list[dict]) -> dict:
    confirmed = [o for o in outcomes if o.get("status") == "confirmed"]
    rs = [o["r_multiple"] for o in confirmed if o.get("r_multiple") is not None]
    return {
        "n": len(confirmed),
        "targets": sum(1 for o in confirmed if o.get("result") == "target"),
        "stops": sum(1 for o in confirmed if o.get("result") == "stop"),
        "total_r": round(sum(rs), 2) if rs else 0.0,
    }
