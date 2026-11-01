import pytest

from intraday_picks import config, screens
from tests.conftest import make_daily, mk_feature, set_bar


def _features(df, symbol="X", industry="Information Technology"):
    return screens.compute_features(symbol, industry, f"{symbol}.NS", df, None)


def test_breakout_with_volume_is_strong_setup():
    df = make_daily(260, start=1000, vol=0.005, volume=2_000_000)
    hh20 = df["High"].iloc[-21:-1].max()
    close = hh20 * 1.01
    set_bar(df, -1, hh20 * 0.995, close * 1.002, hh20 * 0.99, close, v=4_000_000)   # 2x volume, closes near high
    f = _features(df)
    assert f.breakout_up and f.breakout_vol_ok and not f.breakout_extended
    kind, pts, label = screens.setup_for(f, "long")
    assert kind == "breakout" and pts == 3 and "breakout" in label


def test_extended_breakout_scores_low():
    df = make_daily(260, start=1000, vol=0.005)
    hh20 = df["High"].iloc[-21:-1].max()
    close = hh20 * 1.06
    set_bar(df, -1, hh20, close * 1.001, hh20 * 0.99, close, v=4_000_000)
    f = _features(df)
    assert f.breakout_up and f.breakout_extended
    assert screens.setup_for(f, "long")[1] == 1


def test_mover_band_and_already_moved():
    df = make_daily(260, start=1000, vol=0.003)
    df.iloc[-10, df.columns.get_loc("High")] = 1300.0          # keep the 20-day high far away
    prev = df["Close"].iloc[-2]
    set_bar(df, -1, prev, prev * 1.021, prev * 0.999, prev * 1.02, v=4_000_000)   # +2% on 2x volume, near high
    f = _features(df)
    assert f.mover_long and not f.already_moved_long and not f.breakout_up
    set_bar(df, -1, prev, prev * 1.06, prev * 0.999, prev * 1.055, v=4_000_000)   # +5.5%
    f = _features(df)
    assert f.already_moved_long and not f.mover_long


def test_hard_filters_price_and_turnover():
    df = make_daily(260, start=50, volume=100_000)
    f = _features(df)
    assert any(x.startswith("price<") for x in f.filter_fails)
    assert any(x.startswith("turnover<") for x in f.filter_fails)
    assert not f.passes


def test_short_history_fails_filter():
    f = _features(make_daily(120, start=1000))
    assert any(x.startswith("history") for x in f.filter_fails)


def test_regime_classification():
    up = make_daily(260, start=1000, drift=0.002, vol=0.002)
    assert _features(up).regime == "bull"
    down = make_daily(260, start=1000, drift=-0.002, vol=0.002)
    assert _features(down).regime == "bear"


def test_liquidity_funnel_caps_per_industry():
    feats = {}
    for i in range(10):
        s = f"FIN{i}"
        feats[s] = mk_feature(s, "Financial Services", med_turnover_cr=1000 - i)
    for i in range(6):
        s = f"IT{i}"
        feats[s] = mk_feature(s, "Information Technology", med_turnover_cr=500 - i)
    feats["REALTY"] = mk_feature("REALTY", "Realty", med_turnover_cr=120)
    feats["BAD"] = mk_feature("BAD", "Realty", med_turnover_cr=5000, filter_fails=["price<100"])
    chosen = screens.liquidity_funnel(feats)
    assert "BAD" not in chosen
    assert sum(s.startswith("FIN") for s in chosen) == config.INDUSTRY_CAPS["Financial Services"]
    assert sum(s.startswith("IT") for s in chosen) == config.MAX_PER_INDUSTRY
    assert "REALTY" in chosen                                   # every industry keeps its top name


def test_morning_guards_mark_results_ban_and_gap():
    from datetime import date

    f = mk_feature("ABC")
    feats = {"ABC": f}
    screens.apply_morning_guards(
        feats, date(2026, 11, 2),
        preopen=[{"symbol": "ABC", "gap_pct": 3.5, "iep": 1035.0}],
        results={"ABC": date(2026, 11, 2)},
        ban={"ABC"},
    )
    assert f.in_ban and f.results_date == "2026-11-02" and f.preopen_gap_pct == pytest.approx(3.5)
    assert any(x.startswith("gap") for x in f.filter_fails) and "F&O ban" in f.filter_fails


def test_features_roundtrip_json():
    f = mk_feature("RT", breakout_up=True)
    again = screens.Features.from_dict(f.to_dict())
    assert again == f
