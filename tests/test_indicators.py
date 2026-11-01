import numpy as np
import pandas as pd

from intraday_picks import indicators as ind
from tests.conftest import make_daily


def test_ema_matches_pandas_ewm():
    s = pd.Series(np.linspace(100, 120, 300))
    expected = s.ewm(span=200, adjust=False).mean()
    got = ind.ema(s, 200)
    assert np.isclose(got.iloc[-1], expected.iloc[-1])
    assert got.iloc[:199].isna().all()          # min_periods respected


def test_sma_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert ind.sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0]


def test_atr_constant_range():
    df = pd.DataFrame({"Open": 100.0, "High": 102.0, "Low": 98.0, "Close": 100.0, "Volume": 1.0}, index=range(40))
    atr = ind.atr(df, 14)
    assert np.isclose(atr.iloc[-1], 4.0)        # every true range is 4


def test_rolling_high_excludes_current_bar():
    df = make_daily(60)
    df.iloc[-1, df.columns.get_loc("High")] = 1e9
    hh = ind.rolling_high(df, 20).iloc[-1]
    assert hh < 1e8


def test_median_volume_excludes_last():
    df = make_daily(60, volume=1_000_000)
    df.iloc[-1, df.columns.get_loc("Volume")] = 50_000_000
    assert ind.median_volume(df, 20).iloc[-1] == 1_000_000


def test_last_cross_detects_recent_golden_cross():
    fast = pd.Series([1.0] * 50 + [3.0] * 5)
    slow = pd.Series([2.0] * 55)
    bars_ago, direction = ind.last_cross(fast, slow, 20)
    assert direction == "up" and bars_ago == 4


def test_last_cross_ignores_old_cross():
    fast = pd.Series([1.0] * 5 + [3.0] * 50)
    slow = pd.Series([2.0] * 55)
    assert ind.last_cross(fast, slow, 20) == (None, None)


def test_returns_pct():
    s = pd.Series([100.0, 110.0, 121.0])
    assert np.isclose(ind.returns_pct(s, 1), 10.0)
    assert ind.returns_pct(s, 5) is None
