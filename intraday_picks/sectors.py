"""Sector relative strength versus the Nifty.

Each NSE industry gets 1-day and 5-day returns, either from its Yahoo sector index (preferred,
verified tickers in universe.INDEX_FOR_INDUSTRY) or from the equal-weight average of its
constituents. Ranked by a composite of both horizons relative to the Nifty.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from . import config, indicators as ind, universe as uni
from .util import log

logger = log("sectors")


@dataclass
class SectorStrength:
    sector: str
    ret_1d: float
    ret_5d: float
    rs_1d: float
    rs_5d: float
    composite: float
    rank: int
    points_long: int
    points_short: int
    source: str        # index ticker or "constituents(n)"
    members: int

    def to_dict(self) -> dict:
        return asdict(self)


def _returns(df: pd.DataFrame | None) -> tuple[float | None, float | None]:
    if df is None or len(df) < 7:
        return None, None
    return ind.returns_pct(df["Close"], 1), ind.returns_pct(df["Close"], 5)


def sector_strength(
    universe_df: pd.DataFrame,
    daily: dict[str, pd.DataFrame],
    nifty_df: pd.DataFrame | None,
    index_data: dict[str, pd.DataFrame] | None = None,
) -> list[SectorStrength]:
    nifty_1d, nifty_5d = _returns(nifty_df)
    nifty_1d = nifty_1d or 0.0
    nifty_5d = nifty_5d or 0.0
    index_data = index_data or {}
    rows: list[dict] = []
    for industry, group in universe_df.groupby("industry"):
        members = group["yahoo"].tolist()
        ret_1d = ret_5d = None
        source = ""
        ticker = uni.INDEX_FOR_INDUSTRY.get(industry)
        if ticker and ticker in index_data:
            ret_1d, ret_5d = _returns(index_data[ticker])
            source = ticker
        if ret_1d is None or ret_5d is None:
            r1, r5 = [], []
            for y in members:
                a, b = _returns(daily.get(y))
                if a is not None and b is not None:
                    r1.append(a)
                    r5.append(b)
            if r1:
                ret_1d, ret_5d = sum(r1) / len(r1), sum(r5) / len(r5)
                source = f"constituents({len(r1)})"
        if ret_1d is None or ret_5d is None:
            logger.warning("no return data for sector %s", industry)
            continue
        rows.append(
            {
                "sector": industry, "ret_1d": ret_1d, "ret_5d": ret_5d,
                "rs_1d": ret_1d - nifty_1d, "rs_5d": ret_5d - nifty_5d,
                "source": source, "members": len(members),
            }
        )
    for r in rows:
        r["composite"] = 0.5 * r["rs_1d"] + 0.5 * r["rs_5d"]
    rows.sort(key=lambda r: r["composite"], reverse=True)
    n = len(rows)
    out: list[SectorStrength] = []
    for i, r in enumerate(rows, start=1):
        if i <= config.SECTOR_TOP_N:
            pl, ps = 2, 0
        elif i > n - config.SECTOR_TOP_N:
            pl, ps = 0, 2
        else:
            pl, ps = 1, 1
        out.append(SectorStrength(rank=i, points_long=pl, points_short=ps, **r))
    return out


def as_map(rows: list[SectorStrength]) -> dict[str, SectorStrength]:
    return {r.sector: r for r in rows}
