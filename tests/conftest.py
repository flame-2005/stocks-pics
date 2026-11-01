"""Shared synthetic-data helpers for the tests. No network access anywhere in the suite."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from intraday_picks.screens import Features

IST = "Asia/Kolkata"


def make_daily(n: int = 260, start: float = 1000.0, drift: float = 0.0, vol: float = 0.01,
               volume: float = 2_000_000, seed: int = 1, end: str = "2026-10-30") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = start * np.cumprod(1 + rets)
    open_ = np.concatenate([[start], close[:-1]]) * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    idx = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": float(volume)}, index=idx
    )


def set_bar(df: pd.DataFrame, i: int, o: float, h: float, l: float, c: float, v: float | None = None) -> None:
    df.iloc[i, df.columns.get_loc("Open")] = o
    df.iloc[i, df.columns.get_loc("High")] = h
    df.iloc[i, df.columns.get_loc("Low")] = l
    df.iloc[i, df.columns.get_loc("Close")] = c
    if v is not None:
        df.iloc[i, df.columns.get_loc("Volume")] = v


def make_5m(day: str, prices: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """prices: (HH:MM, open, high, low, close) per bar."""
    idx = pd.DatetimeIndex([pd.Timestamp(f"{day} {t}", tz=IST) for t, *_ in prices])
    data = {
        "Open": [p[1] for p in prices], "High": [p[2] for p in prices],
        "Low": [p[3] for p in prices], "Close": [p[4] for p in prices], "Volume": [1000.0] * len(prices),
    }
    return pd.DataFrame(data, index=idx)


def mk_feature(symbol: str = "TEST", industry: str = "Information Technology", **over) -> Features:
    base = dict(
        symbol=symbol, industry=industry, yahoo=f"{symbol}.NS", asof="2026-10-30", bars=260,
        close=1000.0, open=990.0, high=1005.0, low=985.0, prev_close=980.0, ret_1d=2.04, ret_5d=3.0,
        volume=2_000_000, med_vol20=1_000_000, vol_ratio=2.0, med_turnover_cr=200.0,
        atr=20.0, atr_pct=2.0, close_pos=0.75, sma50=950.0, sma200=900.0, regime="bull",
        cross_bars_ago=None, cross_dir=None, hh20=990.0, ll20=900.0,
        breakout_up=False, breakout_down=False, breakout_vol_ok=False, breakout_extended=False,
        pattern_long=None, pattern_long_strength=0, pattern_short=None, pattern_short_strength=0,
        mover_long=False, mover_short=False, already_moved_long=False, already_moved_short=False,
        vol_confirm_long=False, vol_confirm_short=False, vol_shrink=False,
        ema200_15m=None, last_15m_close=None, ema15_side=None, filter_fails=[],
    )
    base.update(over)
    return Features(**base)


@pytest.fixture
def daily() -> pd.DataFrame:
    return make_daily()
