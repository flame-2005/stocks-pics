"""Trade plan per pick: trigger, stop, target, quantity, timing and the discipline rules."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from . import config
from .scoring import Candidate
from .util import log, round_tick

logger = log("plan")


@dataclass
class TradePlan:
    symbol: str
    industry: str
    side: str
    rank: int
    entry: float
    stop: float
    target: float
    qty: int
    stop_pct: float
    risk_per_share: float
    risk_amount: float
    notional: float
    atr_pct: float | None
    score: float
    setup_type: str | None
    setup_label: str
    reasons: list[str]
    flags: list[str]
    entry_window: str
    squareoff: str
    alt_stop: float | None = None
    note: str = ""
    preopen_gap_pct: float | None = None
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def reward(self) -> float:
        return abs(self.target - self.entry) * self.qty


def entry_window_text() -> str:
    parts = [f"{a.strftime('%H:%M')}-{b.strftime('%H:%M')}" for a, b in config.ENTRY_WINDOWS]
    return " or ".join(parts)


def build(
    cand: Candidate,
    rank: int,
    capital: float = config.CAPITAL,
    risk_pct: float = config.RISK_PCT,
    max_leverage: float = config.MAX_LEVERAGE,
) -> TradePlan | None:
    f = cand.features
    atr_pct = f.atr_pct if f.atr_pct is not None else 2.0
    stop_pct = min(max(config.STOP_ATR_MULT * atr_pct, config.STOP_MIN_PCT), config.STOP_MAX_PCT)

    if cand.side == "long":
        entry = round_tick(f.high + config.TICK)
        stop = round_tick(entry * (1 - stop_pct / 100.0))
        target = round_tick(entry + config.TARGET_R * (entry - stop))
        alt_stop = round_tick(f.low)
    else:
        entry = round_tick(f.low - config.TICK)
        stop = round_tick(entry * (1 + stop_pct / 100.0))
        target = round_tick(entry - config.TARGET_R * (stop - entry))
        alt_stop = round_tick(f.high)

    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0:
        return None
    risk_amount = capital * risk_pct / 100.0
    qty = math.floor(risk_amount / risk_per_share)
    max_qty = math.floor(capital * max_leverage / entry) if entry > 0 else 0
    note = ""
    if qty > max_qty:
        qty = max_qty
        note = f"qty capped by {max_leverage:.0f}x leverage"
    if qty < 1:
        logger.info("%s %s skipped: qty < 1 at capital %.0f", cand.symbol, cand.side, capital)
        return None

    return TradePlan(
        symbol=cand.symbol, industry=cand.industry, side=cand.side, rank=rank,
        entry=entry, stop=stop, target=target, qty=int(qty), stop_pct=round(stop_pct, 2),
        risk_per_share=round(risk_per_share, 2), risk_amount=round(qty * risk_per_share, 2),
        notional=round(qty * entry, 2), atr_pct=f.atr_pct, score=cand.score,
        setup_type=cand.setup_type, setup_label=cand.setup_label, reasons=list(cand.reasons),
        flags=list(cand.flags), entry_window=entry_window_text(), squareoff=config.SQUAREOFF.strftime("%H:%M"),
        alt_stop=alt_stop, note=note, preopen_gap_pct=f.preopen_gap_pct, components=dict(cand.components),
    )


def discipline_rules(capital: float = config.CAPITAL) -> list[str]:
    cap = capital * config.DAILY_LOSS_CAP_PCT / 100.0
    return [
        f"Take at most {config.MAX_TRADES_PER_DAY} of these trades today.",
        f"Stop for the day after losing {config.DAILY_LOSS_CAP_PCT:.1f}% ({cap:,.0f}).",
        "No re-entry in a stock that hit its stop.",
        f"Enter only inside {entry_window_text()}; square off by {config.SQUAREOFF.strftime('%H:%M')}.",
        "Wait for the 09:34 confirmation message before entering a breakout.",
    ]
