"""Small shared helpers: logging, IST clock, number parsing, Indian number formatting."""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from logging.handlers import RotatingFileHandler

from . import config

_LOG_READY = False


def setup_logging(name: str = "intraday") -> logging.Logger:
    global _LOG_READY
    logger = logging.getLogger(name)
    if _LOG_READY:
        return logger
    config.ensure_dirs()
    level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    file_handler = RotatingFileHandler(
        config.LOG_DIR / "intraday.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("peewee").setLevel(logging.WARNING)
    _LOG_READY = True
    return logger


def log(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"intraday.{name}")


def now_ist() -> datetime:
    return datetime.now(tz=config.IST)


def today_ist() -> date:
    return now_ist().date()


def to_num(value, default=None):
    """Parse NSE-style numbers: '3,598.54', '-817.5', '', None."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in ("", "-", "NA", "null", "None"):
        return default
    try:
        return float(text)
    except ValueError:
        return default


def fmt_inr(value, decimals: int = 2) -> str:
    """Indian digit grouping: 1,23,456.78."""
    if value is None:
        return "-"
    negative = value < 0
    value = abs(float(value))
    whole, _, frac = f"{value:.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    text = whole if decimals == 0 else f"{whole}.{frac}"
    return f"-{text}" if negative else text


def pct(value, decimals: int = 2, sign: bool = True) -> str:
    if value is None:
        return "-"
    return f"{value:+.{decimals}f}%" if sign else f"{value:.{decimals}f}%"


def round_tick(price: float, tick: float = config.TICK) -> float:
    return round(round(price / tick) * tick, 2)
