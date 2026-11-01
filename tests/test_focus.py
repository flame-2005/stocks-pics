from datetime import date

import pandas as pd
import pytest

from intraday_picks import focus, orb
from intraday_picks.sentiment import MarketMood
from tests.conftest import mk_feature

DAY = date(2026, 11, 2)
IST = "Asia/Kolkata"


def _bar15(o, h, l, c):
    idx = pd.DatetimeIndex([pd.Timestamp("2026-11-02 09:15", tz=IST)])
    return pd.DataFrame({"Open": [o], "High": [h], "Low": [l], "Close": [c], "Volume": [1000.0]}, index=idx)


def test_load_symbols_always_starts_with_nifty(tmp_path, monkeypatch):
    f = tmp_path / "focus_list.txt"
    f.write_text("# comment\nreliance\nHDFCBANK  # bank\nnifty50\nRELIANCE\n", encoding="utf-8")
    monkeypatch.setattr(focus.config, "FOCUS_LIST_FILE", f)
    assert focus.load_symbols() == ["NIFTY", "RELIANCE", "HDFCBANK"]
    assert focus.instrument_for("NIFTY") == "NIFTYBEES.NS" and focus.instrument_for("RELIANCE") == "RELIANCE.NS"


def test_preview_leans_with_setup_and_mood():
    mood = MarketMood(trade_date="2026-11-02", label="bullish", score=3, caution=False)
    feats = {
        "NIFTY": mk_feature("NIFTY", "Index", regime="bull"),
        "ABC": mk_feature("ABC", breakout_up=True, breakout_vol_ok=True, regime="bull"),
        "XYZ": mk_feature("XYZ"),
    }
    out = {v.symbol: v for v in focus.preview(DAY, ["NIFTY", "ABC", "XYZ", "NODATA"], feats, {}, mood)}
    assert out["NIFTY"].verdict == "lean_buy"
    assert out["ABC"].verdict == "lean_buy" and out["ABC"].strength == "strong"
    assert out["XYZ"].verdict == "no" and "no setup" in out["XYZ"].reasons[0]
    assert out["NODATA"].verdict == "no" and "no price data" in out["NODATA"].note


def test_decide_flat_market_is_no_for_everyone():
    feats = {"ABC": mk_feature("ABC", breakout_up=True, breakout_vol_ok=True)}
    out = focus.decide(DAY, ["NIFTY", "ABC"], feats, {}, {}, None, "flat", "bullish", 15.0, False)
    assert all(v.verdict == "no" for v in out) and "no direction" in out[0].reasons[0]


def test_decide_buy_with_levels_and_no_without_setup():
    n_or = orb.OpeningRange(23000, 23100, 22990, 23080, 0, 0.35, 0.1, 0.5)
    feats = {
        "ABC": mk_feature("ABC", close=1000.0, breakout_up=True, breakout_vol_ok=True, regime="bull"),
        "XYZ": mk_feature("XYZ", close=500.0),
        "NIFTY": mk_feature("NIFTY", "Index", regime="bull"),
    }
    bars = {
        "ABC.NS": _bar15(1002, 1010, 1000, 1008),          # green, above yesterday's close
        "XYZ.NS": _bar15(501, 505, 500, 504),               # green too, but no setup
        "NIFTYBEES.NS": _bar15(260, 261.5, 259.8, 261.2),   # ETF agrees with the index
    }
    daily = {"NIFTYBEES.NS": pd.DataFrame({"Open": [259.0], "High": [260.5], "Low": [258.5], "Close": [259.9], "Volume": [1.0]})}
    out = {v.symbol: v for v in focus.decide(DAY, ["NIFTY", "ABC", "XYZ"], feats, daily, bars, n_or, "up", "bullish", 15.0, False)}
    abc = out["ABC"]
    assert abc.verdict == "buy" and abc.strength == "strong"
    assert abc.entry == pytest.approx(1010.05) and abc.stop == pytest.approx(999.95)
    assert abc.target == pytest.approx(abc.entry + (abc.entry - abc.stop)) and abc.qty >= 1
    assert out["XYZ"].verdict == "no" and "no setup" in out["XYZ"].reasons[0]
    nifty = out["NIFTY"]
    assert nifty.verdict == "buy" and nifty.instrument == "NIFTYBEES.NS" and nifty.entry == 261.55


def test_decide_sell_rejected_when_candle_disagrees():
    n_or = orb.OpeningRange(23000, 23010, 22900, 22920, 0, -0.35, 0, 0.5)
    feats = {"ABC": mk_feature("ABC", close=1000.0, pattern_short="bearish_engulfing", pattern_short_strength=3, regime="bear")}
    bars = {"ABC.NS": _bar15(1001, 1012, 1000, 1011)}       # green candle on a sell day
    out = focus.decide(DAY, ["ABC"], feats, {}, bars, n_or, "down", "bearish", 15.0, False)
    assert out[0].verdict == "no" and "opening candle green" in out[0].reasons
