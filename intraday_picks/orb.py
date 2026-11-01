"""Opening-range confirmation: decide the side at 09:34, not the evening before.

The notebook says "follow the market trend" and "wait for confirmation before trade". This module
reads the trend from the Nifty's first 15-minute candle and the confirmation from each stock's own
first candle, then trades a break of that candle's range with the stop at the other end.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import pandas as pd

from . import config, indicators as ind
from .screens import Features
from .util import round_tick


def ema200_at_open(bars15: pd.DataFrame | None, day: date) -> float | None:
    """15-minute EMA200 as of the close of `day`'s opening candle (no later bars leak in)."""
    if bars15 is None or bars15.empty:
        return None
    dates = bars15.index.date
    upto = bars15[(dates < day) | ((dates == day) & (bars15.index.time == config.MARKET_OPEN))]
    if len(upto) < config.EMA_15M:
        return None
    return float(ind.ema(upto["Close"], config.EMA_15M).iloc[-1])

DEAD_ZONE_PCT = 0.10          # Nifty first-candle move smaller than this = no direction
MAX_RANGE_PCT = 1.5           # skip stocks whose opening candle spans more than this
MIN_STOP_PCT = 0.30           # tighten no further than this
ENTRY_DEADLINE = time(11, 0)  # an opening-range break after this is not an opening-range break


@dataclass
class OpeningRange:
    open: float
    high: float
    low: float
    close: float
    volume: float
    pct: float          # close vs open, %
    gap_pct: float      # open vs previous close, %
    range_pct: float    # (high - low) / open, %


def opening_range(bars15: pd.DataFrame | None, day: date, prev_close: float) -> OpeningRange | None:
    """The 09:15-09:30 candle of `day` from a 15-minute frame (IST index)."""
    if bars15 is None or bars15.empty:
        return None
    rows = bars15[bars15.index.date == day]
    if rows.empty or rows.index[0].time() != config.MARKET_OPEN:
        return None
    r = rows.iloc[0]
    o, h, l, c = float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"])
    if o <= 0 or prev_close <= 0:
        return None
    return OpeningRange(
        open=o, high=h, low=l, close=c, volume=float(r.get("Volume", 0.0) or 0.0),
        pct=(c / o - 1) * 100, gap_pct=(o / prev_close - 1) * 100, range_pct=(h - l) / o * 100,
    )


def market_direction(nifty: OpeningRange | None, dead_zone: float = DEAD_ZONE_PCT) -> str:
    """'up', 'down' or 'flat' from the Nifty's opening candle (close vs open)."""
    if nifty is None:
        return "flat"
    if nifty.pct >= dead_zone:
        return "up"
    if nifty.pct <= -dead_zone:
        return "down"
    return "flat"


def qualifies(f: Features, orng: OpeningRange, ema200_15m: float | None, side: str) -> tuple[bool, list[str]]:
    """Does the stock's own opening candle confirm `side`? Returns (ok, reasons it failed)."""
    fails: list[str] = []
    if orng.range_pct > MAX_RANGE_PCT:
        fails.append(f"opening range {orng.range_pct:.1f}% too wide")
    if side == "long":
        if orng.close <= orng.open:
            fails.append("opening candle red")
        if orng.close <= f.close:
            fails.append("below yesterday's close")
        if ema200_15m is not None and orng.close < ema200_15m:
            fails.append("below 15-min EMA200")
    else:
        if orng.close >= orng.open:
            fails.append("opening candle green")
        if orng.close >= f.close:
            fails.append("above yesterday's close")
        if ema200_15m is not None and orng.close > ema200_15m:
            fails.append("above 15-min EMA200")
    return not fails, fails


def orb_plan(orng: OpeningRange, side: str, target_r: float) -> dict:
    """Entry on the break of the opening range, stop at the other end (never tighter than MIN_STOP_PCT)."""
    if side == "long":
        entry = round_tick(orng.high + config.TICK)
        stop = min(round_tick(orng.low - config.TICK), round_tick(entry * (1 - MIN_STOP_PCT / 100)))
        target = round_tick(entry + target_r * (entry - stop))
    else:
        entry = round_tick(orng.low - config.TICK)
        stop = max(round_tick(orng.high + config.TICK), round_tick(entry * (1 + MIN_STOP_PCT / 100)))
        target = round_tick(entry - target_r * (stop - entry))
    return {"side": side, "entry": entry, "stop": stop, "target": target, "stop_pct": abs(entry - stop) / entry * 100}


def simulate(plan: dict, bars5: pd.DataFrame, day: date, entry_until: time = ENTRY_DEADLINE,
             use_target: bool = True) -> dict:
    """First-touch replay on 5-minute bars after 09:30. Both exits in one bar count as the stop."""
    out = {"result": "no_entry", "r": None, "pct": None, "entry_time": None, "exit_time": None}
    rows = bars5[(bars5.index.date == day)]
    rows = rows[[t.time() >= time(9, 30) for t in rows.index]]
    if rows.empty:
        out["result"] = "skipped"
        return out
    long = plan["side"] == "long"
    entry, stop, target = plan["entry"], plan["stop"], plan["target"]
    risk = abs(entry - stop)
    fill = None
    for ts, bar in rows.iterrows():
        t = ts.time()
        o, h, l = float(bar["Open"]), float(bar["High"]), float(bar["Low"])
        if fill is None:
            if t >= entry_until:
                return out
            triggered = h >= entry if long else l <= entry
            if not triggered:
                continue
            fill = max(entry, o) if long else min(entry, o)
            out["entry_time"] = ts.isoformat()
        hit_stop = l <= stop if long else h >= stop
        hit_target = use_target and (h >= target if long else l <= target)
        if t >= config.SQUAREOFF:
            exit_price, result = o, "eod_close"
        elif hit_stop:
            gap = (o < stop) if long else (o > stop)
            exit_price, result = (o if gap else stop), "stop"
        elif hit_target:
            exit_price, result = target, "target"
        else:
            continue
        r = ((exit_price - fill) if long else (fill - exit_price)) / risk
        out.update(result=result, r=round(r, 3), pct=round(((exit_price - fill) if long else (fill - exit_price)) / fill * 100, 3),
                   exit_time=ts.isoformat())
        return out
    if fill is not None:                           # data ended before square-off
        last = float(rows.iloc[-1]["Close"])
        r = ((last - fill) if long else (fill - last)) / risk
        out.update(result="eod_close", r=round(r, 3), pct=round(((last - fill) if long else (fill - last)) / fill * 100, 3),
                   exit_time=rows.index[-1].isoformat())
    return out
