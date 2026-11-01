from intraday_picks import patterns
from tests.conftest import make_daily, set_bar


def _declining(df, start_i=-8, start=100.0, step=1.2):
    price = start
    for i in range(start_i, -2):
        set_bar(df, i, price, price + 0.3, price - step - 0.2, price - step)
        price -= step
    return price


def _rising(df, start_i=-8, start=100.0, step=1.2):
    price = start
    for i in range(start_i, -2):
        set_bar(df, i, price, price + step + 0.2, price - 0.3, price + step)
        price += step
    return price


def test_bullish_engulfing_after_drop():
    df = make_daily(40, start=100, vol=0.002)
    p = _declining(df)
    set_bar(df, -2, p, p + 0.2, p - 1.7, p - 1.5)                  # red
    set_bar(df, -1, p - 1.6, p + 0.6, p - 1.8, p + 0.4)            # green, engulfs
    names = {x.name: x for x in patterns.detect(df)}
    assert "bullish_engulfing" in names and names["bullish_engulfing"].strength == 3
    assert patterns.best(df, "long").name == "bullish_engulfing"


def test_hammer_after_drop():
    df = make_daily(40, start=100, vol=0.002)
    p = _declining(df)
    set_bar(df, -2, p, p + 0.3, p - 1.4, p - 1.2)
    set_bar(df, -1, p - 1.0, p - 0.9, p - 3.6, p - 0.8)            # tiny body, long lower shadow
    assert any(x.name == "hammer" for x in patterns.detect(df))


def test_shooting_star_after_rally():
    df = make_daily(40, start=100, vol=0.002)
    p = _rising(df)
    set_bar(df, -2, p, p + 1.4, p - 0.3, p + 1.2)
    set_bar(df, -1, p + 1.3, p + 4.0, p + 1.2, p + 1.1)           # tiny body, long upper shadow
    found = {x.name for x in patterns.detect(df)}
    assert "shooting_star" in found


def test_morning_star():
    df = make_daily(40, start=100, vol=0.002)
    p = _declining(df, start_i=-9)
    set_bar(df, -3, p, p + 0.2, p - 4.2, p - 4.0)                  # big red
    set_bar(df, -2, p - 4.5, p - 4.2, p - 4.8, p - 4.3)            # small body
    set_bar(df, -1, p - 4.0, p - 0.9, p - 4.1, p - 1.0)            # green, closes above midpoint
    names = {x.name for x in patterns.detect(df)}
    assert "morning_star" in names


def test_no_pattern_on_short_history():
    df = make_daily(8)
    assert patterns.detect(df) == []


def test_bearish_engulfing_is_short_side():
    df = make_daily(40, start=100, vol=0.002)
    p = _rising(df)
    set_bar(df, -2, p, p + 1.4, p - 0.2, p + 1.2)                  # green
    set_bar(df, -1, p + 1.3, p + 1.5, p - 0.8, p - 0.6)            # red, engulfs
    best = patterns.best(df, "short")
    assert best is not None and best.name == "bearish_engulfing"
    assert patterns.best(df, "long") is None
