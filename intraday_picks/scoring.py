"""Scoring and ranking: turn features + sector strength + market mood into ranked candidates.

Components are independent so one candle is never counted three times:
  regime (0-2) + setup (0-3) + volume (-1..1) + sector (0-2) + ATR fit (0-1) + penalties (<= 0)
The market mood decides which sides are allowed and how many picks each side gets.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import config
from .screens import Features, setup_for
from .sectors import SectorStrength
from .sentiment import MarketMood
from .universe import sector_short
from .util import log

logger = log("scoring")


@dataclass
class Candidate:
    symbol: str
    industry: str
    side: str
    score: float
    setup_type: str | None
    setup_points: float
    setup_label: str
    sector_points: int
    sector_rank: int | None
    components: dict[str, float]
    reasons: list[str]
    flags: list[str]
    features: Features = field(repr=False)

    def to_row(self) -> dict:
        d = asdict(self)
        d.pop("features", None)
        return d


@dataclass
class FunnelCounts:
    universe: int
    filters_passed: int
    funnel: int
    with_setup: int
    sector_ok: int
    final: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RankResult:
    picks: list[Candidate]
    shortlist: list[Candidate]          # everyone with a setup, best first (the "~12")
    counts: FunnelCounts
    quota: dict[str, int]


def _regime_points(f: Features, side: str) -> tuple[float, str | None]:
    if f.regime == "na":
        return 0.0, None
    if side == "long":
        if f.regime == "bull":
            pts, note = 2.0, "above 50 & 200 DMA, 50 > 200"
        elif f.sma200 is not None and f.close > f.sma200:
            pts, note = 1.0, "above 200 DMA, 50 DMA mixed"
        else:
            return 0.0, None
        if f.cross_dir == "up" and f.cross_bars_ago is not None:
            pts = min(pts + 0.5, config.WEIGHT_REGIME)
            note = f"golden cross {f.cross_bars_ago} sessions ago, " + note
        return pts, note
    if f.regime == "bear":
        pts, note = 2.0, "below 50 & 200 DMA, 50 < 200"
    elif f.sma200 is not None and f.close < f.sma200:
        pts, note = 1.0, "below 200 DMA, 50 DMA mixed"
    else:
        return 0.0, None
    if f.cross_dir == "down" and f.cross_bars_ago is not None:
        pts = min(pts + 0.5, config.WEIGHT_REGIME)
        note = f"death cross {f.cross_bars_ago} sessions ago, " + note
    return pts, note


def _already_moved_penalty(ret: float) -> float:
    mag = abs(ret)
    if mag <= config.ALREADY_MOVED_RET:
        return 0.0
    if mag <= config.ALREADY_MOVED_RET + 1.5:
        return -1.0
    if mag <= config.ALREADY_MOVED_RET + 3.0:
        return -2.0
    return -3.0


def score(f: Features, side: str, sector: SectorStrength | None) -> Candidate:
    comps: dict[str, float] = {}
    reasons: list[str] = []
    flags: list[str] = []

    regime_pts, regime_note = _regime_points(f, side)
    comps["regime"] = regime_pts
    if regime_note:
        reasons.append(regime_note)

    setup_type, setup_pts, setup_label = setup_for(f, side)
    comps["setup"] = setup_pts
    if setup_label:
        reasons.insert(0, setup_label)
    else:
        flags.append("no setup")

    vol_pts = 0.0
    uses_volume = setup_type in ("breakout", "breakdown", "mover")
    confirms = f.vol_confirm_long if side == "long" else f.vol_confirm_short
    moved_with_side = f.ret_1d > 0 if side == "long" else f.ret_1d < 0
    if confirms and not uses_volume:
        vol_pts = config.WEIGHT_VOLUME
        reasons.append(f"volume {f.vol_ratio:.1f}x median confirms the move")
    elif f.vol_shrink and moved_with_side:
        vol_pts = -1.0
        flags.append(f"moved on shrinking volume ({f.vol_ratio:.1f}x)")
    comps["volume"] = vol_pts

    if sector is not None:
        sector_pts = sector.points_long if side == "long" else sector.points_short
        sector_rank = sector.rank
        label = sector_short(f.industry)
        if sector_pts == 2:
            reasons.append(f"{label} sector rank {sector.rank} ({sector.rs_5d:+.1f}% vs Nifty, 5d)")
        elif sector_pts == 0:
            flags.append(f"weak sector for this side ({label} rank {sector.rank})")
    else:
        sector_pts, sector_rank = 1, None
    comps["sector"] = float(sector_pts)

    lo, hi = config.ATR_PCT_IDEAL
    comps["atr"] = float(config.WEIGHT_ATR) if f.atr_pct is not None and lo <= f.atr_pct <= hi else 0.0

    penalty = 0.0
    if (side == "long" and f.already_moved_long) or (side == "short" and f.already_moved_short):
        penalty += _already_moved_penalty(f.ret_1d)
        flags.append(f"already moved {f.ret_1d:+.1f}% yesterday")
    if f.preopen_gap_pct is not None:
        gap_with_side = f.preopen_gap_pct if side == "long" else -f.preopen_gap_pct
        if gap_with_side > config.ALREADY_MOVED_GAP:
            penalty -= 2.0
            flags.append(f"pre-open gap {f.preopen_gap_pct:+.1f}% in trade direction: do not chase")
        elif gap_with_side < -1.0:
            penalty -= 1.0
            flags.append(f"pre-open gap {f.preopen_gap_pct:+.1f}% against the trade")
        elif abs(f.preopen_gap_pct) > config.GAP_FLAG_PCT:
            flags.append(f"pre-open gap {f.preopen_gap_pct:+.1f}%")
    comps["penalty"] = penalty

    if f.ema15_side is not None:
        wrong = (side == "long" and f.ema15_side == "below") or (side == "short" and f.ema15_side == "above")
        if wrong:
            flags.append(f"15-min price {f.ema15_side} EMA200: needs confirmation")
        else:
            reasons.append(f"15-min chart {f.ema15_side} EMA200")

    total = sum(comps.values())
    return Candidate(
        symbol=f.symbol, industry=f.industry, side=side, score=round(total, 2),
        setup_type=setup_type, setup_points=setup_pts, setup_label=setup_label,
        sector_points=int(sector_pts), sector_rank=sector_rank, components=comps,
        reasons=reasons[:4], flags=flags, features=f,
    )


def rank(
    feats: dict[str, Features],
    funnel_symbols: list[str],
    sector_map: dict[str, SectorStrength],
    mood: MarketMood,
    sides: list[str] | None = None,
    quota: dict[str, int] | None = None,
) -> RankResult:
    """Rank candidates. By default the mood picks the sides and counts; callers may override both
    (the opening-range mode publishes candidates on both sides and decides the side at 09:34)."""
    quota = quota if quota is not None else mood.quota()
    sides = sides if sides is not None else (mood.sides or ["long", "short"])
    scored: list[Candidate] = []
    for symbol in funnel_symbols:
        f = feats.get(symbol)
        if f is None or not f.passes:
            continue
        for side in sides:
            scored.append(score(f, side, sector_map.get(f.industry)))

    with_setup = [c for c in scored if c.setup_points >= 1]
    sector_ok = [c for c in with_setup if c.sector_points >= config.MIN_SECTOR_POINTS]
    picks: list[Candidate] = []
    for side in sides:
        n = quota.get(side, 0)
        pool = sorted(
            (c for c in sector_ok if c.side == side and c.score >= config.MIN_PICK_SCORE),
            key=lambda c: (-c.score, -c.setup_points, -(c.features.med_turnover_cr or 0)),
        )
        picks.extend(pool[:n])
    picks.sort(key=lambda c: -c.score)

    shortlist = sorted(with_setup, key=lambda c: -c.score)
    counts = FunnelCounts(
        universe=len(feats),
        filters_passed=sum(1 for f in feats.values() if f.passes),
        funnel=len(funnel_symbols),
        with_setup=len({c.symbol for c in with_setup}),
        sector_ok=len({c.symbol for c in sector_ok}),
        final=len(picks),
    )
    logger.info(
        "funnel %d -> %d pass filters -> %d liquid -> %d with setup -> %d sector ok -> %d picks (%s)",
        counts.universe, counts.filters_passed, counts.funnel, counts.with_setup, counts.sector_ok, counts.final, mood.label,
    )
    return RankResult(picks=picks, shortlist=shortlist, counts=counts, quota=quota)
