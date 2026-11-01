"""Per-stock features, hard filters, the liquidity funnel and the setup screens.

One `Features` object per symbol carries everything the scorer, planner, message and dashboard
need, and serialises to JSON so the morning run can re-rank what the evening run computed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, timedelta

import pandas as pd

from . import config, indicators as ind, patterns
from .util import log

logger = log("screens")


@dataclass
class Features:
    symbol: str
    industry: str
    yahoo: str
    asof: str
    bars: int
    close: float
    open: float
    high: float
    low: float
    prev_close: float
    ret_1d: float
    ret_5d: float | None
    volume: float
    med_vol20: float | None
    vol_ratio: float | None
    med_turnover_cr: float | None
    atr: float | None
    atr_pct: float | None
    close_pos: float
    sma50: float | None
    sma200: float | None
    regime: str                      # bull | bear | mixed | na
    cross_bars_ago: int | None
    cross_dir: str | None
    hh20: float | None
    ll20: float | None
    breakout_up: bool
    breakout_down: bool
    breakout_vol_ok: bool
    breakout_extended: bool
    pattern_long: str | None
    pattern_long_strength: int
    pattern_short: str | None
    pattern_short_strength: int
    mover_long: bool
    mover_short: bool
    already_moved_long: bool
    already_moved_short: bool
    vol_confirm_long: bool
    vol_confirm_short: bool
    vol_shrink: bool
    ema200_15m: float | None
    last_15m_close: float | None
    ema15_side: str | None           # above | below | None
    filter_fails: list[str] = field(default_factory=list)
    # morning enrichments
    preopen_gap_pct: float | None = None
    preopen_price: float | None = None
    results_date: str | None = None
    in_ban: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Features":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    @property
    def passes(self) -> bool:
        return not self.filter_fails


def _f(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(v) else v


def compute_features(
    symbol: str,
    industry: str,
    yahoo: str,
    daily: pd.DataFrame,
    intraday_15m: pd.DataFrame | None = None,
) -> Features | None:
    """Features from the last completed daily bar. Returns None when history is too short."""
    if daily is None or len(daily) < 30:
        return None
    df = daily
    last, prev = df.iloc[-1], df.iloc[-2]
    close, prev_close = float(last["Close"]), float(prev["Close"])
    if prev_close <= 0 or close <= 0:
        return None

    sma50 = _f(ind.sma(df["Close"], config.SMA_FAST).iloc[-1])
    sma200 = _f(ind.sma(df["Close"], config.SMA_SLOW).iloc[-1])
    atr_series = ind.atr(df, 14)
    atr_val = _f(atr_series.iloc[-1])
    atr_pct = (atr_val / close * 100.0) if atr_val else None
    med_vol = _f(ind.median_volume(df, config.MEDIAN_WINDOW).iloc[-1])
    volume = float(last["Volume"]) if not pd.isna(last["Volume"]) else 0.0
    vol_ratio = (volume / med_vol) if med_vol else None
    med_turnover = _f(ind.median_turnover_cr(df, config.MEDIAN_WINDOW).iloc[-1])
    ret_1d = (close / prev_close - 1.0) * 100.0
    ret_5d = ind.returns_pct(df["Close"], 5)
    close_pos = ind.close_position(last)
    hh20 = _f(ind.rolling_high(df, config.BREAKOUT_LOOKBACK).iloc[-1])
    ll20 = _f(ind.rolling_low(df, config.BREAKOUT_LOOKBACK).iloc[-1])

    if sma50 is None or sma200 is None:
        regime = "na"
    elif close > sma50 > sma200:
        regime = "bull"
    elif close < sma50 < sma200:
        regime = "bear"
    else:
        regime = "mixed"
    cross_bars_ago, cross_dir = (None, None)
    if sma50 is not None and sma200 is not None:
        cross_bars_ago, cross_dir = ind.last_cross(
            ind.sma(df["Close"], config.SMA_FAST), ind.sma(df["Close"], config.SMA_SLOW), config.RECENT_CROSS_DAYS
        )

    vol_ok = vol_ratio is not None and vol_ratio >= config.BREAKOUT_VOL_MULT
    breakout_up = hh20 is not None and close > hh20
    breakout_down = ll20 is not None and close < ll20
    breakout_vol_ok = vol_ok and (
        (breakout_up and close_pos >= config.CLOSE_POS_TOP) or (breakout_down and close_pos <= 1 - config.CLOSE_POS_TOP)
    )
    breakout_extended = (breakout_up and hh20 is not None and close > hh20 * config.BREAKOUT_MAX_EXTENSION) or (
        breakout_down and ll20 is not None and close < ll20 * (2 - config.BREAKOUT_MAX_EXTENSION)
    )

    p_long = patterns.best(df, "long")
    p_short = patterns.best(df, "short")

    mover_vol = vol_ratio is not None and vol_ratio >= config.MOVER_VOL_MULT
    mover_long = config.MOVER_RET_MIN <= ret_1d <= config.MOVER_RET_MAX and mover_vol and close_pos >= config.CLOSE_POS_TOP
    mover_short = -config.MOVER_RET_MAX <= ret_1d <= -config.MOVER_RET_MIN and mover_vol and close_pos <= 1 - config.CLOSE_POS_TOP

    vol_confirm = vol_ratio is not None and vol_ratio >= config.VOL_CONFIRM_MULT
    vol_shrink = vol_ratio is not None and vol_ratio < config.VOL_SHRINK_MULT

    ema200_15m = last_15m_close = None
    ema15_side = None
    if intraday_15m is not None and len(intraday_15m) >= config.EMA_15M:
        ema_series = ind.ema(intraday_15m["Close"], config.EMA_15M)
        ema200_15m = _f(ema_series.iloc[-1])
        last_15m_close = _f(intraday_15m["Close"].iloc[-1])
        if ema200_15m is not None and last_15m_close is not None:
            ema15_side = "above" if last_15m_close > ema200_15m else "below"

    f = Features(
        symbol=symbol, industry=industry, yahoo=yahoo, asof=df.index[-1].date().isoformat(), bars=len(df),
        close=close, open=float(last["Open"]), high=float(last["High"]), low=float(last["Low"]), prev_close=prev_close,
        ret_1d=ret_1d, ret_5d=ret_5d, volume=volume, med_vol20=med_vol, vol_ratio=vol_ratio,
        med_turnover_cr=med_turnover, atr=atr_val, atr_pct=atr_pct, close_pos=close_pos,
        sma50=sma50, sma200=sma200, regime=regime, cross_bars_ago=cross_bars_ago, cross_dir=cross_dir,
        hh20=hh20, ll20=ll20, breakout_up=breakout_up, breakout_down=breakout_down,
        breakout_vol_ok=breakout_vol_ok, breakout_extended=breakout_extended,
        pattern_long=p_long.name if p_long else None, pattern_long_strength=p_long.strength if p_long else 0,
        pattern_short=p_short.name if p_short else None, pattern_short_strength=p_short.strength if p_short else 0,
        mover_long=mover_long, mover_short=mover_short,
        already_moved_long=ret_1d > config.ALREADY_MOVED_RET, already_moved_short=ret_1d < -config.ALREADY_MOVED_RET,
        vol_confirm_long=vol_confirm and ret_1d > 0, vol_confirm_short=vol_confirm and ret_1d < 0, vol_shrink=vol_shrink,
        ema200_15m=ema200_15m, last_15m_close=last_15m_close, ema15_side=ema15_side,
    )
    f.filter_fails = hard_filter_fails(f)
    return f


def hard_filter_fails(f: Features) -> list[str]:
    fails: list[str] = []
    if f.bars < config.MIN_DAILY_BARS:
        fails.append(f"history {f.bars}<{config.MIN_DAILY_BARS} bars")
    if f.close < config.MIN_PRICE:
        fails.append(f"price<{config.MIN_PRICE:.0f}")
    if f.med_turnover_cr is None or f.med_turnover_cr < config.MIN_MEDIAN_TURNOVER_CR:
        fails.append(f"turnover<{config.MIN_MEDIAN_TURNOVER_CR:.0f}cr")
    if f.atr_pct is None:
        fails.append("no ATR")
    elif f.atr_pct < config.ATR_PCT_MIN:
        fails.append(f"ATR {f.atr_pct:.1f}%<{config.ATR_PCT_MIN}%")
    elif f.atr_pct > config.ATR_PCT_MAX:
        fails.append(f"ATR {f.atr_pct:.1f}%>{config.ATR_PCT_MAX}%")
    if f.in_ban:
        fails.append("F&O ban")
    if f.results_date:
        fails.append(f"results {f.results_date}")
    if f.preopen_gap_pct is not None and abs(f.preopen_gap_pct) > config.GAP_SKIP_PCT:
        fails.append(f"gap {f.preopen_gap_pct:+.1f}%")
    return fails


def apply_morning_guards(
    feats: dict[str, Features],
    trade_date: date,
    preopen: list[dict] | None,
    results: dict[str, date] | None,
    ban: set[str] | None,
) -> None:
    """Mutates features with pre-open gap, results-today and F&O-ban information."""
    gap_by_symbol = {row["symbol"]: row for row in (preopen or [])}
    for symbol, f in feats.items():
        row = gap_by_symbol.get(symbol)
        if row:
            f.preopen_gap_pct = row["gap_pct"]
            f.preopen_price = row["iep"]
        if results:
            d = results.get(symbol)
            # results on the trade date, or the previous session (announced after close)
            if d is not None and trade_date - timedelta(days=1) <= d <= trade_date:
                f.results_date = d.isoformat()
        if ban and symbol in ban:
            f.in_ban = True
        f.filter_fails = hard_filter_fails(f)


def liquidity_funnel(feats: dict[str, Features]) -> list[str]:
    """Top stocks per industry by median turnover: the hand-written '~30 stocks across sectors'."""
    passing = [f for f in feats.values() if f.passes and f.med_turnover_cr]
    by_industry: dict[str, list[Features]] = {}
    for f in passing:
        by_industry.setdefault(f.industry, []).append(f)
    for group in by_industry.values():
        group.sort(key=lambda f: f.med_turnover_cr or 0.0, reverse=True)

    chosen: list[Features] = []
    extras: list[Features] = []
    for industry, group in by_industry.items():
        cap = config.INDUSTRY_CAPS.get(industry, config.MAX_PER_INDUSTRY)
        if group:
            chosen.append(group[0])
        extras.extend(group[1:cap])
    extras.sort(key=lambda f: f.med_turnover_cr or 0.0, reverse=True)
    room = max(config.FUNNEL_TARGET - len(chosen), 0)
    chosen.extend(extras[:room])
    chosen.sort(key=lambda f: f.med_turnover_cr or 0.0, reverse=True)
    return [f.symbol for f in chosen]


def setup_for(f: Features, side: str) -> tuple[str | None, float, str]:
    """Best setup for a side: (type, points 0-3, human label). Breakout > pattern > mover on ties."""
    options: list[tuple[float, int, str, str]] = []
    if side == "long":
        if f.breakout_up:
            if f.breakout_vol_ok and not f.breakout_extended:
                options.append((3, 0, "breakout", f"20-day breakout above {f.hh20:.2f} on {f.vol_ratio:.1f}x volume"))
            else:
                why = "extended" if f.breakout_extended else "weak volume"
                options.append((1, 0, "breakout", f"20-day breakout ({why})"))
        if f.pattern_long:
            options.append((f.pattern_long_strength, 1, "pattern", f.pattern_long.replace("_", " ")))
        if f.mover_long:
            options.append((2, 2, "mover", f"gainer {f.ret_1d:+.1f}% on {f.vol_ratio:.1f}x volume, not exhausted"))
    else:
        if f.breakout_down:
            if f.breakout_vol_ok and not f.breakout_extended:
                options.append((3, 0, "breakdown", f"20-day breakdown below {f.ll20:.2f} on {f.vol_ratio:.1f}x volume"))
            else:
                why = "extended" if f.breakout_extended else "weak volume"
                options.append((1, 0, "breakdown", f"20-day breakdown ({why})"))
        if f.pattern_short:
            options.append((f.pattern_short_strength, 1, "pattern", f.pattern_short.replace("_", " ")))
        if f.mover_short:
            options.append((2, 2, "mover", f"loser {f.ret_1d:+.1f}% on {f.vol_ratio:.1f}x volume, not exhausted"))
    if not options:
        return None, 0.0, ""
    options.sort(key=lambda o: (-o[0], o[1]))
    points, _, kind, label = options[0]
    return kind, float(points), label
