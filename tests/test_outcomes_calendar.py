from datetime import date

import pytest

from intraday_picks import outcomes, trading_calendar as cal
from tests.conftest import make_5m

DAY = "2026-10-30"
PICK = {"side": "long", "entry": 100.0, "stop": 99.0, "target": 102.0, "qty": 10}


def test_first_15_minutes_never_trigger_then_target():
    bars = make_5m(DAY, [
        ("09:15", 99.5, 100.8, 99.2, 99.6),      # would trigger, but inside the first 15 minutes
        ("09:20", 99.6, 99.9, 99.3, 99.5),
        ("09:25", 99.5, 99.8, 99.4, 99.7),
        ("09:35", 99.8, 100.3, 99.7, 100.2),     # trigger, fill at 100
        ("10:00", 100.2, 102.2, 100.1, 102.0),   # target
        ("15:10", 101.0, 101.2, 100.9, 101.1),
    ])
    out = outcomes.evaluate(PICK, bars, date(2026, 10, 30))
    assert out["result"] == "target" and out["entry_price"] == 100.0
    assert out["r_multiple"] == pytest.approx(2.0) and out["pnl"] == pytest.approx(20.0)


def test_same_bar_stop_and_target_counts_as_stop():
    bars = make_5m(DAY, [
        ("09:35", 99.8, 102.5, 98.5, 101.0),
        ("15:10", 101.0, 101.2, 100.9, 101.1),
    ])
    out = outcomes.evaluate(PICK, bars, date(2026, 10, 30))
    assert out["result"] == "stop" and out["r_multiple"] == pytest.approx(-1.0)


def test_no_entry_outside_windows():
    bars = make_5m(DAY, [
        ("09:35", 99.0, 99.5, 98.9, 99.2),
        ("12:00", 99.5, 100.5, 99.4, 100.2),     # lunch chop window: not allowed
        ("15:10", 100.0, 100.1, 99.9, 100.0),
    ])
    out = outcomes.evaluate(PICK, bars, date(2026, 10, 30))
    assert out["result"] == "no_entry" and out["r_multiple"] is None


def test_gap_fill_and_eod_close():
    bars = make_5m(DAY, [
        ("09:35", 100.6, 100.9, 100.5, 100.7),   # gaps through the trigger: fill at the open 100.6
        ("11:30", 100.7, 101.0, 100.4, 100.8),
        ("15:10", 101.1, 101.3, 101.0, 101.2),   # square-off at this bar's open
        ("15:15", 101.2, 101.4, 101.0, 101.3),
    ])
    out = outcomes.evaluate(PICK, bars, date(2026, 10, 30))
    assert out["result"] == "eod_close" and out["entry_price"] == pytest.approx(100.6)
    assert out["exit_price"] == pytest.approx(101.1)
    assert out["r_multiple"] == pytest.approx(0.5)


def test_short_side_target():
    pick = {"side": "short", "entry": 100.0, "stop": 101.0, "target": 98.0, "qty": 5}
    bars = make_5m(DAY, [
        ("09:40", 100.3, 100.4, 99.8, 99.9),     # trigger at 100
        ("10:30", 99.9, 100.2, 97.9, 98.1),      # target
    ])
    out = outcomes.evaluate(pick, bars, date(2026, 10, 30))
    assert out["result"] == "target" and out["r_multiple"] == pytest.approx(2.0) and out["pnl"] == pytest.approx(10.0)


def test_calendar_uses_static_holidays_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(cal.nse, "holidays", lambda: None)
    monkeypatch.setattr(cal.config, "DATA_DIR", tmp_path)
    cal._cache.clear()
    assert not cal.is_trading_day(date(2026, 1, 26))       # Republic Day
    assert not cal.is_trading_day(date(2026, 11, 1))       # Sunday
    assert cal.is_trading_day(date(2026, 11, 2))
    assert cal.next_trading_day(date(2026, 10, 30)) == date(2026, 11, 2)
    assert cal.prev_trading_day(date(2026, 11, 2)) == date(2026, 10, 30)
    assert cal.is_expiry_day(date(2026, 11, 3))            # Tuesday
    cal._cache.clear()
