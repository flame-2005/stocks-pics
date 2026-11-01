from datetime import date

import pandas as pd
import pytest

from intraday_picks import orb
from tests.conftest import make_5m, mk_feature

DAY = date(2026, 10, 30)
IST = "Asia/Kolkata"


def _bar15(o, h, l, c, day="2026-10-30", t="09:15"):
    idx = pd.DatetimeIndex([pd.Timestamp(f"{day} {t}", tz=IST)])
    return pd.DataFrame({"Open": [o], "High": [h], "Low": [l], "Close": [c], "Volume": [1000.0]}, index=idx)


def test_opening_range_requires_the_0915_bar():
    assert orb.opening_range(_bar15(100, 101, 99, 100.5, t="09:30"), DAY, 99.0) is None
    r = orb.opening_range(_bar15(100, 101, 99, 100.5), DAY, 99.0)
    assert r.pct == pytest.approx(0.5) and r.gap_pct == pytest.approx(100 / 99 * 100 - 100) and r.range_pct == pytest.approx(2.0)


def test_market_direction_dead_zone():
    up = orb.OpeningRange(100, 101, 99.9, 100.2, 0, 0.2, 0, 1.1)
    flat = orb.OpeningRange(100, 101, 99.9, 100.05, 0, 0.05, 0, 1.1)
    down = orb.OpeningRange(100, 100.1, 99, 99.7, 0, -0.3, 0, 1.1)
    assert orb.market_direction(up) == "up"
    assert orb.market_direction(flat) == "flat"
    assert orb.market_direction(down) == "down"
    assert orb.market_direction(None) == "flat"


def test_qualifies_long_and_short():
    f = mk_feature(close=1000.0)                      # yesterday's close 1000
    green = orb.OpeningRange(1002, 1008, 1000, 1006, 0, 0.4, 0.2, 0.8)
    ok, fails = orb.qualifies(f, green, 990.0, "long")
    assert ok and fails == []
    ok, fails = orb.qualifies(f, green, 1010.0, "long")   # below the 15-min EMA200
    assert not ok and any("EMA200" in x for x in fails)
    ok, fails = orb.qualifies(f, green, 990.0, "short")
    assert not ok and "opening candle green" in fails
    wide = orb.OpeningRange(1000, 1020, 998, 1015, 0, 1.5, 0, 2.2)
    ok, fails = orb.qualifies(f, wide, None, "long")
    assert not ok and any("too wide" in x for x in fails)


def test_orb_plan_geometry():
    r = orb.OpeningRange(1000, 1010, 1000, 1008, 0, 0.8, 0, 1.0)
    p = orb.orb_plan(r, "long", 1.0)
    assert p["entry"] == pytest.approx(1010.05) and p["stop"] == pytest.approx(999.95)
    assert p["target"] == pytest.approx(p["entry"] + (p["entry"] - p["stop"]))
    tight = orb.OpeningRange(1000, 1001, 999.8, 1000.9, 0, 0.09, 0, 0.12)
    p = orb.orb_plan(tight, "long", 1.0)
    assert p["stop_pct"] == pytest.approx(orb.MIN_STOP_PCT, abs=0.02)   # never tighter than the floor
    s = orb.orb_plan(r, "short", 2.0)
    assert s["entry"] == pytest.approx(999.95) and s["stop"] == pytest.approx(1010.05) and s["target"] < s["entry"]


def test_simulate_respects_deadline_and_first_touch():
    plan = {"side": "long", "entry": 101.0, "stop": 99.5, "target": 102.5}
    bars = make_5m("2026-10-30", [
        ("09:30", 100.5, 100.9, 100.2, 100.8),
        ("09:45", 100.8, 101.2, 100.6, 101.1),    # trigger at 101
        ("10:30", 101.1, 102.6, 101.0, 102.4),    # target
        ("15:10", 102.0, 102.1, 101.9, 102.0),
    ])
    out = orb.simulate(plan, bars, DAY)
    assert out["result"] == "target" and out["r"] == pytest.approx(1.0)
    late = make_5m("2026-10-30", [
        ("09:30", 100.5, 100.9, 100.2, 100.8),
        ("11:05", 100.9, 101.5, 100.8, 101.3),    # after the deadline: no entry
        ("15:10", 102.0, 102.1, 101.9, 102.0),
    ])
    assert orb.simulate(plan, late, DAY)["result"] == "no_entry"
    both = make_5m("2026-10-30", [("09:35", 100.9, 102.8, 99.2, 101.0), ("15:10", 101, 101, 101, 101)])
    assert orb.simulate(plan, both, DAY)["result"] == "stop"
