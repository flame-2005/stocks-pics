"""Trading calendar: NSE holidays, trading-day arithmetic, expiry and manual no-trade flags.

Holiday source order: cached NSE holiday-master for the year (refreshed every 30 days) ->
live NSE API (current year only) -> the static file shipped in data/holidays_static.json.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta

from . import config, nse
from .util import log

logger = log("calendar")

_cache: dict[int, set[date]] = {}


def _static_holidays() -> dict[int, set[date]]:
    path = config.STATIC_DIR / "holidays_static.json"
    out: dict[int, set[date]] = {}
    if not path.exists():
        return out
    try:
        for h in json.loads(path.read_text(encoding="utf-8")).get("holidays", []):
            d = date.fromisoformat(h["date"])
            out.setdefault(d.year, set()).add(d)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("static holiday file unreadable: %s", exc)
    return out


def holidays_for(year: int) -> set[date]:
    """Trading holidays (cash market) for a year. Special sessions (Muhurat) count as closed."""
    if year in _cache:
        return _cache[year]
    config.ensure_dirs()
    cache_file = config.DATA_DIR / f"holidays_{year}.json"
    data: list[dict] | None = None
    if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < 30 * 86400:
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError):
            data = None
    if data is None and year == date.today().year:
        fetched = nse.holidays()
        if fetched:
            data = fetched
            cache_file.write_text(json.dumps(data), encoding="utf-8")
    if data is None:
        result = _static_holidays().get(year, set())
        if not result:
            logger.warning("no holiday data for %s; using weekends only", year)
    else:
        result = set()
        for h in data:
            try:
                d = date.fromisoformat(h["date"])
            except (KeyError, ValueError):
                continue
            if d.year == year:
                result.add(d)
    _cache[year] = result
    return result


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_holiday(d: date) -> bool:
    return d in holidays_for(d.year)


def is_trading_day(d: date) -> bool:
    """Market open on this date (ignores the user's manual no-trade list)."""
    return not is_weekend(d) and not is_holiday(d)


def is_manual_no_trade(d: date) -> bool:
    return d in config.NO_TRADE_DATES


def next_trading_day(d: date, inclusive: bool = False) -> date:
    cur = d if inclusive else d + timedelta(days=1)
    for _ in range(30):
        if is_trading_day(cur):
            return cur
        cur += timedelta(days=1)
    raise RuntimeError("no trading day found within 30 days")


def prev_trading_day(d: date, inclusive: bool = False) -> date:
    cur = d if inclusive else d - timedelta(days=1)
    for _ in range(30):
        if is_trading_day(cur):
            return cur
        cur -= timedelta(days=1)
    raise RuntimeError("no trading day found within 30 days")


def is_expiry_day(d: date) -> bool:
    """Nifty weekly options expire on Tuesday; expiry days are choppier."""
    return d.weekday() == 1


def last_completed_session(now: datetime) -> date:
    """Most recent trading day whose daily bar is final at `now` (IST)."""
    today = now.date()
    if is_trading_day(today) and now.time() >= config.DAILY_BAR_FINAL:
        return today
    return prev_trading_day(today)


def trading_days_between(start: date, end: date) -> list[date]:
    out = []
    cur = start
    while cur <= end:
        if is_trading_day(cur):
            out.append(cur)
        cur += timedelta(days=1)
    return out
