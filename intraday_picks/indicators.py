"""Hand-rolled indicators on OHLCV DataFrames (columns Open, High, Low, Close, Volume).

Kept dependency-free on purpose: TA-Lib is painful to build on Windows and these are a few
lines each. Windows that describe "the typical day" exclude the current bar so a screen can
compare today against history without contaminating the baseline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CRORE = 1e7


def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=n).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    ranges = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev_close).abs(), (df["Low"] - prev_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder's ATR (exponential with alpha = 1/n)."""
    return true_range(df).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def atr_pct(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return atr(df, n) / df["Close"] * 100.0


def median_volume(df: pd.DataFrame, n: int = 20, exclude_last: bool = True) -> pd.Series:
    med = df["Volume"].rolling(n, min_periods=max(5, n // 2)).median()
    return med.shift(1) if exclude_last else med


def turnover_cr(df: pd.DataFrame) -> pd.Series:
    return df["Close"] * df["Volume"] / CRORE


def median_turnover_cr(df: pd.DataFrame, n: int = 20, exclude_last: bool = True) -> pd.Series:
    med = turnover_cr(df).rolling(n, min_periods=max(5, n // 2)).median()
    return med.shift(1) if exclude_last else med


def rolling_high(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Highest high of the previous n bars, excluding the current bar."""
    return df["High"].rolling(n, min_periods=n).max().shift(1)


def rolling_low(df: pd.DataFrame, n: int = 20) -> pd.Series:
    return df["Low"].rolling(n, min_periods=n).min().shift(1)


def close_position(row: pd.Series) -> float:
    """Where the close sits in the bar's range: 0 = at the low, 1 = at the high."""
    rng = float(row["High"] - row["Low"])
    if rng <= 0:
        return 0.5
    return float((row["Close"] - row["Low"]) / rng)


def pct_change(series: pd.Series, n: int = 1) -> pd.Series:
    return series.pct_change(n) * 100.0


def last_cross(fast: pd.Series, slow: pd.Series, lookback: int = 20) -> tuple[int | None, str | None]:
    """Most recent fast/slow cross within `lookback` bars: (bars ago, 'up'|'down')."""
    diff = (fast - slow).dropna()
    if len(diff) < 2:
        return None, None
    sign = np.sign(diff.to_numpy())
    changes = np.where(sign[1:] * sign[:-1] < 0)[0]
    if len(changes) == 0:
        return None, None
    idx = int(changes[-1]) + 1
    bars_ago = len(sign) - 1 - idx
    if bars_ago > lookback:
        return None, None
    return bars_ago, "up" if sign[idx] > 0 else "down"


def returns_pct(series: pd.Series, n: int) -> float | None:
    """Percent change over the last n bars, or None when there is not enough data."""
    s = series.dropna()
    if len(s) <= n:
        return None
    prev = float(s.iloc[-1 - n])
    if prev == 0:
        return None
    return (float(s.iloc[-1]) / prev - 1.0) * 100.0
