"""Candlestick patterns on the last daily bar(s).

Each detector looks at the final one to three bars of a daily OHLC frame and reports a strength
of 1 (needs confirmation), 2 (solid) or 3 (strong reversal). Context matters: a hammer only
counts after a down move, a shooting star only after an up move.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PRIOR_MOVE_PCT = 1.0      # move over the 5 bars before the pattern bar to call it a trend
SMALL_BODY = 0.35         # body <= 35% of range -> "small body" candles
DOJI_BODY = 0.10
MARUBOZU_BODY = 0.85
SHADOW_MULT = 2.0


@dataclass(frozen=True)
class Pattern:
    name: str
    side: str        # "long" or "short"
    strength: int


def _bar(df: pd.DataFrame, i: int) -> dict[str, float]:
    row = df.iloc[i]
    o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    return {
        "o": o, "h": h, "l": l, "c": c, "rng": rng, "body": body,
        "green": c > o, "red": c < o,
        "upper": h - max(o, c), "lower": min(o, c) - l,
        "mid": (o + c) / 2.0,
    }


def _prior_move(df: pd.DataFrame, end: int = -2, span: int = 5) -> float:
    """% move of the close over `span` bars ending at index `end` (the bar before the pattern)."""
    closes = df["Close"]
    if len(closes) < abs(end) + span + 1:
        return 0.0
    start_val = float(closes.iloc[end - span])
    return (float(closes.iloc[end]) / start_val - 1.0) * 100.0 if start_val else 0.0


def _avg_body(df: pd.DataFrame, n: int = 10) -> float:
    sub = df.iloc[-(n + 1) : -1]
    if sub.empty:
        return 0.0
    return float((sub["Close"] - sub["Open"]).abs().mean())


def detect(df: pd.DataFrame) -> list[Pattern]:
    """All patterns present on the last bar (and 2-3 bar combinations ending there)."""
    if df is None or len(df) < 12:
        return []
    found: list[Pattern] = []
    cur, prev = _bar(df, -1), _bar(df, -2)
    avg_body = _avg_body(df)
    prior = _prior_move(df)
    down_before, up_before = prior <= -PRIOR_MOVE_PCT, prior >= PRIOR_MOVE_PCT

    # --- engulfing
    if prev["red"] and cur["green"] and cur["o"] <= prev["c"] and cur["c"] >= prev["o"] and cur["body"] > prev["body"]:
        found.append(Pattern("bullish_engulfing", "long", 3 if down_before else 2))
    if prev["green"] and cur["red"] and cur["o"] >= prev["c"] and cur["c"] <= prev["o"] and cur["body"] > prev["body"]:
        found.append(Pattern("bearish_engulfing", "short", 3 if up_before else 2))

    # --- single-bar shapes
    small = cur["body"] <= SMALL_BODY * cur["rng"]
    hammer_shape = small and cur["lower"] >= SHADOW_MULT * max(cur["body"], 0.02 * cur["rng"]) and cur["upper"] <= 0.15 * cur["rng"]
    star_shape = small and cur["upper"] >= SHADOW_MULT * max(cur["body"], 0.02 * cur["rng"]) and cur["lower"] <= 0.15 * cur["rng"]
    if hammer_shape and down_before:
        found.append(Pattern("hammer", "long", 2))
    if hammer_shape and up_before:
        found.append(Pattern("hanging_man", "short", 1))
    if star_shape and up_before:
        found.append(Pattern("shooting_star", "short", 2))
    if star_shape and down_before:
        found.append(Pattern("inverted_hammer", "long", 1))

    if cur["body"] <= DOJI_BODY * cur["rng"]:
        if down_before:
            found.append(Pattern("doji_after_drop", "long", 1))
        elif up_before:
            found.append(Pattern("doji_after_rally", "short", 1))

    if cur["body"] >= MARUBOZU_BODY * cur["rng"] and avg_body and cur["body"] >= 1.2 * avg_body:
        found.append(Pattern("bullish_marubozu" if cur["green"] else "bearish_marubozu", "long" if cur["green"] else "short", 2))

    # --- two-bar penetration
    if prev["red"] and cur["green"] and cur["o"] < prev["c"] and prev["mid"] < cur["c"] < prev["o"]:
        found.append(Pattern("piercing_line", "long", 2))
    if prev["green"] and cur["red"] and cur["o"] > prev["c"] and prev["o"] < cur["c"] < prev["mid"]:
        found.append(Pattern("dark_cloud_cover", "short", 2))

    # --- three-bar stars
    if len(df) >= 13:
        first = _bar(df, -3)
        if (
            first["red"] and first["body"] >= max(avg_body, 1e-9)
            and prev["body"] <= 0.4 * first["body"]
            and cur["green"] and cur["c"] > first["mid"]
        ):
            found.append(Pattern("morning_star", "long", 3))
        if (
            first["green"] and first["body"] >= max(avg_body, 1e-9)
            and prev["body"] <= 0.4 * first["body"]
            and cur["red"] and cur["c"] < first["mid"]
        ):
            found.append(Pattern("evening_star", "short", 3))

    return found


def best(df: pd.DataFrame, side: str) -> Pattern | None:
    """Strongest pattern for one side ('long' or 'short'), or None."""
    candidates = [p for p in detect(df) if p.side == side]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.strength)
