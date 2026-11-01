import pytest

from intraday_picks import config, plan, scoring
from intraday_picks.sectors import SectorStrength
from intraday_picks.sentiment import MarketMood
from tests.conftest import mk_feature


def _sector(points_long=2, points_short=0, rank=1):
    return SectorStrength(sector="Information Technology", ret_1d=1.0, ret_5d=3.0, rs_1d=0.5, rs_5d=2.0,
                          composite=1.25, rank=rank, points_long=points_long, points_short=points_short,
                          source="^CNXIT", members=6)


def test_breakout_setup_does_not_double_count_volume():
    f = mk_feature(breakout_up=True, breakout_vol_ok=True, vol_confirm_long=True, regime="bull", atr_pct=2.0)
    c = scoring.score(f, "long", _sector())
    assert c.components["setup"] == 3 and c.components["volume"] == 0
    assert c.components["regime"] == 2 and c.components["sector"] == 2 and c.components["atr"] == 1
    assert c.score == 8


def test_pattern_setup_gets_volume_credit():
    f = mk_feature(pattern_long="hammer", pattern_long_strength=2, vol_confirm_long=True)
    c = scoring.score(f, "long", _sector())
    assert c.components["setup"] == 2 and c.components["volume"] == 1


def test_already_moved_penalty_and_flag():
    f = mk_feature(pattern_long="hammer", pattern_long_strength=2, already_moved_long=True, ret_1d=5.0)
    c = scoring.score(f, "long", None)
    assert c.components["penalty"] == -1 and any("already moved" in x for x in c.flags)


def test_gap_in_direction_is_penalised():
    f = mk_feature(pattern_long="hammer", pattern_long_strength=2, preopen_gap_pct=2.5)
    c = scoring.score(f, "long", None)
    assert c.components["penalty"] == -2


def test_mood_quota_and_sides():
    bull = MarketMood(trade_date="2026-11-02", label="bullish", score=3, caution=False)
    assert bull.sides == ["long"] and bull.quota() == {"long": config.PICKS_TRENDING, "short": 0}
    caution = MarketMood(trade_date="2026-11-02", label="bearish", score=-3, caution=True)
    assert caution.quota() == {"long": 0, "short": config.PICKS_TRENDING // 2}
    none = MarketMood(trade_date="2026-11-02", label="no_trade", score=0, caution=False)
    assert none.quota() == {"long": 0, "short": 0}


def test_rank_applies_funnel_stages():
    feats = {
        "A": mk_feature("A", breakout_up=True, breakout_vol_ok=True),                 # strong, good sector
        "B": mk_feature("B", "Realty", pattern_long="hammer", pattern_long_strength=2),  # weak sector -> dropped
        "C": mk_feature("C"),                                                           # no setup
    }
    sectors = {"Information Technology": _sector(), "Realty": _sector(points_long=0, points_short=2, rank=17)}
    mood = MarketMood(trade_date="2026-11-02", label="bullish", score=3, caution=False)
    res = scoring.rank(feats, ["A", "B", "C"], sectors, mood)
    assert [c.symbol for c in res.picks] == ["A"]
    assert res.counts.with_setup == 2 and res.counts.sector_ok == 1 and res.counts.final == 1


def test_plan_geometry_and_sizing():
    f = mk_feature(high=1000.0, low=980.0, atr_pct=2.0, breakout_up=True, breakout_vol_ok=True)
    c = scoring.score(f, "long", _sector())
    p = plan.build(c, 1, capital=100_000, risk_pct=1.0, max_leverage=4)
    assert p.entry == pytest.approx(1000.05)
    assert p.stop_pct == pytest.approx(1.2)                   # 0.6 * 2.0, inside the clamp
    assert p.stop == pytest.approx(988.05)
    assert p.target == pytest.approx(p.entry + 2 * (p.entry - p.stop))
    assert p.qty == 83 and p.risk_amount <= 1000
    assert p.notional <= 400_000


def test_plan_short_side_and_leverage_cap():
    f = mk_feature(high=120.0, low=100.0, atr_pct=0.5, close=101.0)
    c = scoring.score(f, "short", None)
    p = plan.build(c, 1, capital=100_000, risk_pct=1.0, max_leverage=1)
    assert p.entry == pytest.approx(99.95) and p.stop > p.entry > p.target
    assert p.stop_pct == pytest.approx(config.STOP_MIN_PCT)   # clamp floor
    assert p.qty == 1000 and p.notional <= 100_000 and "leverage" in p.note
