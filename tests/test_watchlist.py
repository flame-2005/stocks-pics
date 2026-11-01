from intraday_picks import watchlist
from tests.conftest import make_daily


def test_window_stats_keys_and_ranges():
    df = make_daily(260, start=1000, drift=0.001, vol=0.01)
    s = watchlist._window_stats(df)
    for key in ("close", "ret_1w", "ret_1m", "ret_3m", "month_high", "month_low", "range_pos", "atr_pct",
                "avg_volume", "sma50", "sma200", "pct_from_sma50", "pct_from_sma200"):
        assert key in s
    assert s["month_low"] <= s["close"] <= s["month_high"]
    assert 0.0 <= s["range_pos"] <= 1.0
    assert s["ret_1m"] is not None and s["atr_pct"] > 0


def test_window_stats_short_history_has_no_sma200():
    df = make_daily(100, start=500)
    s = watchlist._window_stats(df)
    assert s["sma200"] is None and s["pct_from_sma200"] is None
    assert s["sma50"] is not None
