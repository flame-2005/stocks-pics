"""Market mood: the gate that decides whether today is a long day, a short day, or no day.

Inputs mirror the notebook's "market sentiment" line: Nifty trend, India VIX, FII/DII flows,
global cues (S&P futures, Nikkei, Hang Seng, Brent, USD/INR) and, in the morning, the Nifty
pre-open gap. Points are summed into a score; the label is a gate, not a stock score.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

from . import config, indicators as ind, trading_calendar as cal
from .util import log

logger = log("sentiment")


@dataclass
class MoodComponent:
    name: str
    value: float | None
    points: int
    note: str


@dataclass
class MarketMood:
    trade_date: str
    label: str                       # bullish | bearish | neutral | no_trade
    score: int
    caution: bool
    components: list[MoodComponent] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    nifty_close: float | None = None
    nifty_ema20: float | None = None
    nifty_ema50: float | None = None
    nifty_chg_pct: float | None = None
    nifty_gap_pct: float | None = None
    vix: float | None = None
    fii_net: float | None = None
    dii_net: float | None = None
    global_chg: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def sides(self) -> list[str]:
        return {"bullish": ["long"], "bearish": ["short"], "neutral": ["long", "short"], "no_trade": []}[self.label]

    def quota(self) -> dict[str, int]:
        if self.label == "no_trade":
            return {"long": 0, "short": 0}
        trending = config.PICKS_TRENDING // 2 if self.caution else config.PICKS_TRENDING
        each = max(config.PICKS_NEUTRAL_EACH // 2, 1) if self.caution else config.PICKS_NEUTRAL_EACH
        if self.label == "bullish":
            return {"long": trending, "short": 0}
        if self.label == "bearish":
            return {"long": 0, "short": trending}
        return {"long": each, "short": each}


def _last(series: pd.Series) -> float | None:
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) else None


def assess(
    trade_date: date,
    nifty_df: pd.DataFrame | None,
    vix_df: pd.DataFrame | None,
    fii: dict | None,
    global_quotes: dict[str, dict] | None,
    nifty_gap_pct: float | None = None,
    vix_live: float | None = None,
) -> MarketMood:
    comps: list[MoodComponent] = []
    reasons: list[str] = []
    no_trade = False
    caution = False

    # ---- Nifty trend and momentum
    nifty_close = ema20 = ema50 = chg = None
    if nifty_df is not None and len(nifty_df) >= 60:
        nifty_close = _last(nifty_df["Close"])
        ema20 = _last(ind.ema(nifty_df["Close"], 20))
        ema50 = _last(ind.ema(nifty_df["Close"], 50))
        chg = ind.returns_pct(nifty_df["Close"], 1)
        if nifty_close and ema20 and ema50:
            if nifty_close > ema20 > ema50:
                pts, note = 2, "Nifty above EMA20 > EMA50 (uptrend)"
            elif nifty_close < ema20 < ema50:
                pts, note = -2, "Nifty below EMA20 < EMA50 (downtrend)"
            elif nifty_close > ema20:
                pts, note = 1, "Nifty above EMA20, EMAs mixed"
            elif nifty_close < ema20:
                pts, note = -1, "Nifty below EMA20, EMAs mixed"
            else:
                pts, note = 0, "Nifty at EMA20"
            comps.append(MoodComponent("nifty_trend", nifty_close, pts, note))
        if chg is not None:
            pts = 1 if chg > 0.5 else -1 if chg < -0.5 else 0
            comps.append(MoodComponent("nifty_momentum", chg, pts, f"Nifty last session {chg:+.2f}%"))
    else:
        comps.append(MoodComponent("nifty_trend", None, 0, "Nifty data unavailable"))

    # ---- FII / DII
    fii_net = dii_net = None
    if fii:
        fii_net, dii_net = fii.get("fii_net"), fii.get("dii_net")
        if fii_net is not None:
            pts = 1 if fii_net > config.FII_THRESHOLD_CR else -1 if fii_net < -config.FII_THRESHOLD_CR else 0
            comps.append(MoodComponent("fii", fii_net, pts, f"FII net {fii_net:+,.0f} cr"))
        if dii_net is not None:
            pts = 1 if dii_net > config.DII_THRESHOLD_CR else -1 if dii_net < -config.DII_THRESHOLD_CR else 0
            comps.append(MoodComponent("dii", dii_net, pts, f"DII net {dii_net:+,.0f} cr"))
    else:
        comps.append(MoodComponent("fii", None, 0, "FII/DII unavailable (neutral)"))

    # ---- global cues
    g = {k: v["chg_pct"] for k, v in (global_quotes or {}).items() if v.get("chg_pct") is not None}
    if "ES=F" in g:
        v = g["ES=F"]
        comps.append(MoodComponent("us_futures", v, 1 if v > 0.3 else -1 if v < -0.3 else 0, f"S&P futures {v:+.2f}%"))
    asia = [g[k] for k in ("^N225", "^HSI") if k in g]
    if asia:
        v = sum(asia) / len(asia)
        comps.append(MoodComponent("asia", v, 1 if v > 0.5 else -1 if v < -0.5 else 0, f"Asia (Nikkei/HSI avg) {v:+.2f}%"))
    if "BZ=F" in g:
        v = g["BZ=F"]
        comps.append(MoodComponent("crude", v, -1 if v > 2 else 1 if v < -2 else 0, f"Brent {v:+.2f}%"))
    if "INR=X" in g:
        v = g["INR=X"]
        comps.append(MoodComponent("usdinr", v, -1 if v > 0.3 else 1 if v < -0.3 else 0, f"USD/INR {v:+.2f}%"))
    if not g:
        comps.append(MoodComponent("global", None, 0, "global cues unavailable"))

    # ---- VIX
    vix = vix_live if vix_live is not None else (_last(vix_df["Close"]) if vix_df is not None and len(vix_df) else None)
    if vix is not None:
        if vix > config.VIX_NO_TRADE:
            no_trade = True
            reasons.append(f"India VIX {vix:.1f} > {config.VIX_NO_TRADE:.0f}: too volatile, sit out")
        elif vix > config.VIX_CAUTION:
            caution = True
            reasons.append(f"India VIX {vix:.1f} elevated: half-size, fewer picks")
        comps.append(MoodComponent("vix", vix, 0, f"India VIX {vix:.1f}"))

    score = sum(c.points for c in comps)

    # ---- pre-open gap (morning only)
    if nifty_gap_pct is not None:
        against = (nifty_gap_pct < 0 and score > 0) or (nifty_gap_pct > 0 and score < 0)
        if abs(nifty_gap_pct) > config.NIFTY_GAP_NO_TRADE and against:
            no_trade = True
            reasons.append(f"Nifty pre-open gap {nifty_gap_pct:+.2f}% against the trend: sit out")
        elif abs(nifty_gap_pct) > 1.0:
            caution = True
            reasons.append(f"Nifty pre-open gap {nifty_gap_pct:+.2f}%: wait for the first candle")
        comps.append(MoodComponent("nifty_gap", nifty_gap_pct, 0, f"Nifty pre-open gap {nifty_gap_pct:+.2f}%"))

    if cal.is_manual_no_trade(trade_date):
        no_trade = True
        reasons.append("manual no-trade date")
    if cal.is_expiry_day(trade_date):
        reasons.append("Tuesday: weekly Nifty expiry, expect chop around strikes")

    if no_trade:
        label = "no_trade"
    elif score >= config.MOOD_BULL_SCORE:
        label = "bullish"
    elif score <= config.MOOD_BEAR_SCORE:
        label = "bearish"
    else:
        label = "neutral"

    return MarketMood(
        trade_date=trade_date.isoformat(), label=label, score=score, caution=caution, components=comps,
        reasons=reasons, nifty_close=nifty_close, nifty_ema20=ema20, nifty_ema50=ema50, nifty_chg_pct=chg,
        nifty_gap_pct=nifty_gap_pct, vix=vix, fii_net=fii_net, dii_net=dii_net, global_chg=g,
    )
