"""Your list: the Nifty plus the user's own companies, each given a daily verdict.

Evening / 09:10  -> a lean ("lean buy", "lean sell", "no") from yesterday's candle, trend and mood.
09:34            -> a firm verdict ("buy", "sell", "no") from the Nifty's opening candle and the
                    symbol's own opening candle, with entry, stop, target and quantity when it is a trade.
15:45            -> the result of that verdict on 5-minute bars.

The Nifty is traded through the NIFTYBEES ETF: the index candle gives the direction, the ETF's own
opening candle gives the price levels.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

from . import config, datasource as ds, orb, outcomes as oc, scoring, screens
from .screens import Features
from .sectors import SectorStrength
from .sentiment import MarketMood
from .util import log

logger = log("focus")

NIFTY_ALIASES = {"NIFTY", "NIFTY50", "NIFTY 50", "^NSEI", "NIFTYBEES"}
NIFTY_KEY = "NIFTY"


@dataclass
class FocusVerdict:
    trade_date: str
    symbol: str
    instrument: str
    phase: str                      # prep | orb
    verdict: str                    # lean_buy | lean_sell | buy | sell | no
    strength: str = ""              # strong | ok | ""
    side: str | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    qty: int | None = None
    stop_pct: float | None = None
    score_long: float | None = None
    score_short: float | None = None
    regime: str | None = None
    setup_type: str | None = None
    setup_label: str | None = None
    close: float | None = None
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    note: str = ""

    def to_row(self) -> dict:
        d = asdict(self)
        d["reasons_json"] = json.dumps(d.pop("reasons"))
        d["flags_json"] = json.dumps(d.pop("flags"))
        return d

    @property
    def is_trade(self) -> bool:
        return self.verdict in ("buy", "sell")


# ----------------------------------------------------------------------------- the list
def load_symbols() -> list[str]:
    """NIFTY first, then the user's symbols from focus_list.txt (deduplicated, upper-case)."""
    symbols = [NIFTY_KEY]
    path = config.FOCUS_LIST_FILE
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.split("#", 1)[0].strip().upper()
            if s and s not in NIFTY_ALIASES and s not in symbols:
                symbols.append(s)
    return symbols


def instrument_for(symbol: str) -> str:
    return f"{config.FOCUS_NIFTY_INSTRUMENT}.NS" if symbol == NIFTY_KEY else f"{symbol}.NS"


def tickers(symbols: list[str]) -> list[str]:
    """Every Yahoo ticker the list needs: the index itself, the ETF, and each company."""
    out = [config.NIFTY, instrument_for(NIFTY_KEY)]
    out.extend(instrument_for(s) for s in symbols if s != NIFTY_KEY)
    return list(dict.fromkeys(out))


def load_data(symbols: list[str], session: date, offline: bool) -> tuple[dict, dict]:
    """(daily frames, 15-minute frames) for everything the list needs, data up to `session`."""
    t = tickers(symbols)
    daily = ds.daily(t, period="1y", as_of=session, offline=offline)
    intraday = ds.intraday(t, interval="15m", period="60d", as_of=session, offline=offline)
    return daily, intraday


def build_features(symbols: list[str], daily: dict, intraday: dict, industries: dict[str, str]) -> dict[str, Features]:
    feats: dict[str, Features] = {}
    for s in symbols:
        yahoo = config.NIFTY if s == NIFTY_KEY else instrument_for(s)
        df = daily.get(yahoo)
        if df is None or len(df) < 30:
            continue
        f = screens.compute_features(s, industries.get(s, "Index" if s == NIFTY_KEY else "Other"), yahoo, df, intraday.get(yahoo))
        if f is not None:
            feats[s] = f
    return feats


def _size(entry: float, stop: float) -> tuple[int, str]:
    risk = abs(entry - stop)
    if risk <= 0 or entry <= 0:
        return 0, "no risk distance"
    qty = math.floor(config.CAPITAL * config.RISK_PCT / 100.0 / risk)
    max_qty = math.floor(config.CAPITAL * config.MAX_LEVERAGE / entry)
    if qty > max_qty:
        return max_qty, f"qty capped by {config.MAX_LEVERAGE:.0f}x leverage"
    return qty, ""


# ----------------------------------------------------------------------------- evening lean
def preview(trade_date: date, symbols: list[str], feats: dict[str, Features], sector_map: dict[str, SectorStrength],
            mood: MarketMood) -> list[FocusVerdict]:
    out: list[FocusVerdict] = []
    for s in symbols:
        f = feats.get(s)
        v = FocusVerdict(trade_date=trade_date.isoformat(), symbol=s, instrument=instrument_for(s), phase="prep", verdict="no")
        if f is None:
            v.note = "no price data (check the symbol spelling)"
            out.append(v)
            continue
        v.close, v.regime = f.close, f.regime
        if s == NIFTY_KEY:
            trend = {"bull": "Nifty above 50 and 200 DMA", "bear": "Nifty below 50 and 200 DMA"}.get(f.regime, "Nifty trend mixed")
            if mood.label == "bullish":
                v.verdict, v.side = "lean_buy", "long"
            elif mood.label == "bearish":
                v.verdict, v.side = "lean_sell", "short"
            v.reasons = [f"market mood {mood.label} ({mood.score:+d})", trend]
            v.flags = list(mood.reasons)
            v.note = "decided at 09:34 from the opening candle"
            out.append(v)
            continue
        cl = scoring.score(f, "long", sector_map.get(f.industry))
        cs = scoring.score(f, "short", sector_map.get(f.industry))
        v.score_long, v.score_short = cl.score, cs.score
        best = cl if cl.score >= cs.score else cs
        v.flags = [x for x in f.filter_fails if not x.startswith("history")]
        if best.setup_points >= 1 and best.score >= config.MIN_PICK_SCORE:
            v.verdict = "lean_buy" if best.side == "long" else "lean_sell"
            v.side = best.side
            v.strength = "strong" if best.setup_points >= 2 and best.components.get("regime", 0) >= 2 else "ok"
            v.setup_type, v.setup_label = best.setup_type, best.setup_label
            v.reasons = list(best.reasons[:3])
            v.flags.extend(best.flags)
            if mood.label in ("bullish", "bearish") and mood.sides and best.side not in mood.sides:
                v.flags.append(f"against the market mood ({mood.label})")
        else:
            v.reasons = [f"no setup on yesterday's candle (best score {best.score:g} {best.side})"]
            v.note = "nothing to do unless 09:34 changes the picture"
        out.append(v)
    return out


# ----------------------------------------------------------------------------- 09:34 verdict
def decide(trade_date: date, symbols: list[str], feats: dict[str, Features], daily: dict, bars15: dict,
           n_or: orb.OpeningRange | None, direction: str, mood_label: str | None, vix: float | None,
           caution: bool) -> list[FocusVerdict]:
    out: list[FocusVerdict] = []
    side = "long" if direction == "up" else "short" if direction == "down" else None
    for s in symbols:
        inst = instrument_for(s)
        f = feats.get(s)
        v = FocusVerdict(trade_date=trade_date.isoformat(), symbol=s, instrument=inst, phase="orb", verdict="no")
        if f is not None:
            v.close, v.regime = f.close, f.regime
        if side is None:
            v.reasons = ["Nifty opening candle flat: the market has no direction today"]
            out.append(v)
            continue
        if vix is not None and vix > config.VIX_NO_TRADE:
            v.reasons = [f"India VIX {vix:.1f}: too volatile, sit out"]
            out.append(v)
            continue

        if s == NIFTY_KEY:
            etf = daily.get(inst)
            prev_close = float(etf["Close"].iloc[-1]) if etf is not None and len(etf) else 0.0
            o_r = orb.opening_range(bars15.get(inst), trade_date, prev_close)
            if o_r is None:
                v.reasons = [f"no opening candle for {config.FOCUS_NIFTY_INSTRUMENT} yet"]
                out.append(v)
                continue
            agrees = o_r.pct > 0 if side == "long" else o_r.pct < 0
            if not agrees:
                v.reasons = [f"{config.FOCUS_NIFTY_INSTRUMENT} candle {o_r.pct:+.2f}% disagrees with the index {n_or.pct:+.2f}%"]
                out.append(v)
                continue
            geom = orb.orb_plan(o_r, side, config.ORB_TARGET_R)
            qty, note = _size(geom["entry"], geom["stop"])
            aligned = (side == "long" and f is not None and f.regime == "bull") or (side == "short" and f is not None and f.regime == "bear")
            v.verdict, v.side, v.strength = ("buy" if side == "long" else "sell"), side, ("strong" if aligned else "ok")
            v.entry, v.stop, v.target, v.qty, v.stop_pct, v.note = geom["entry"], geom["stop"], geom["target"], qty, round(geom["stop_pct"], 2), note
            v.reasons = [f"Nifty opened {n_or.pct:+.2f}%, {config.FOCUS_NIFTY_INSTRUMENT} candle {o_r.pct:+.2f}%"]
            v.reasons.append("with the daily trend" if aligned else f"daily trend is {f.regime if f else 'unknown'}")
            if mood_label in ("bullish", "bearish") and ((side == "long") != (mood_label == "bullish")):
                v.flags.append(f"against the evening mood ({mood_label})")
            if caution:
                v.flags.append("caution flag: half size")
            out.append(v)
            continue

        if f is None:
            v.reasons = ["no price data (check the symbol spelling)"]
            out.append(v)
            continue
        o_r = orb.opening_range(bars15.get(inst), trade_date, f.close)
        if o_r is None:
            v.reasons = ["no opening candle yet"]
            out.append(v)
            continue
        ok, fails = orb.qualifies(f, o_r, orb.ema200_at_open(bars15.get(inst), trade_date), side)
        setup_type, pts, label = screens.setup_for(f, side)
        v.setup_type, v.setup_label = setup_type, label
        cand = scoring.score(f, side, None)
        v.score_long = cand.score if side == "long" else None
        v.score_short = cand.score if side == "short" else None
        v.flags = [x for x in f.filter_fails if not x.startswith("history")]
        if not ok:
            v.reasons = fails
            out.append(v)
            continue
        if pts < 1:
            v.reasons = [f"opening candle agrees with the market ({o_r.pct:+.2f}%) but there was no setup on yesterday's candle"]
            v.note = "just following the market; the backtest says that is not worth a trade"
            out.append(v)
            continue
        geom = orb.orb_plan(o_r, side, config.ORB_TARGET_R)
        qty, note = _size(geom["entry"], geom["stop"])
        v.verdict, v.side = ("buy" if side == "long" else "sell"), side
        v.strength = "strong" if pts >= 2 and cand.components.get("regime", 0) >= 2 else "ok"
        v.entry, v.stop, v.target, v.qty, v.stop_pct, v.note = geom["entry"], geom["stop"], geom["target"], qty, round(geom["stop_pct"], 2), note
        v.reasons = [label, f"opening candle {o_r.pct:+.2f}% vs Nifty {n_or.pct:+.2f}%"] + list(cand.reasons[:1])
        v.flags.extend(cand.flags)
        if caution:
            v.flags.append("caution flag: half size")
        out.append(v)
    return out


# ----------------------------------------------------------------------------- outcomes
def evaluate(trade_date: date, verdicts: list[dict], offline: bool = False) -> list[dict]:
    """Attach result / R / P&L to each buy or sell verdict using the day's 5-minute bars."""
    out = []
    for v in verdicts:
        if v.get("verdict") not in ("buy", "sell") or not v.get("entry"):
            out.append({**v, "result": "skipped" if v.get("verdict") != "no" else None})
            continue
        inst = v["instrument"]
        bars = ds.intraday([inst], interval="5m", period="5d", offline=offline).get(inst) if offline else ds.today_bars(inst, "5m", trade_date)
        pick = {"side": v["side"], "entry": v["entry"], "stop": v["stop"], "target": v["target"], "qty": v.get("qty") or 0, "phase": "orb"}
        res = oc.evaluate(pick, bars, trade_date)
        out.append({**v, "result": res["result"], "entry_price": res["entry_price"], "exit_price": res["exit_price"],
                    "r_multiple": res["r_multiple"], "pnl": res["pnl"]})
    return out
