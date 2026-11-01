"""Market data via yfinance with a local parquet cache.

Rules enforced here so no screen has to think about them:
- auto_adjust=False: prices are what traded, not dividend-adjusted.
- Daily frames never contain today's bar before 15:35 IST (Yahoo serves a partial bar).
- `as_of` truncates every frame so replays and backtests cannot look ahead.
- Every download merges into the cache, so the cache grows into a backtest history.
"""
from __future__ import annotations

import time
import warnings
from datetime import date

import pandas as pd

warnings.filterwarnings("ignore", module=r"yfinance(\..*)?")   # pandas-3 deprecation noise inside yfinance
import yfinance as yf  # noqa: E402

from . import config  # noqa: E402
from .util import log, now_ist  # noqa: E402

logger = log("datasource")

FIELDS = ["Open", "High", "Low", "Close", "Volume"]
CHUNK = 40


def _safe_name(ticker: str) -> str:
    return ticker.replace("^", "IDX_").replace("=", "_EQ").replace("/", "_").replace(".", "_")


def _cache_path(kind: str, ticker: str):
    folder = config.CACHE_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{_safe_name(ticker)}.parquet"


def _read_cache(kind: str, ticker: str) -> pd.DataFrame | None:
    path = _cache_path(kind, ticker)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 - corrupt cache is not fatal
        logger.warning("cache read failed for %s: %s", ticker, exc)
        return None


def _write_cache(kind: str, ticker: str, df: pd.DataFrame) -> None:
    try:
        df.to_parquet(_cache_path(kind, ticker))
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache write failed for %s: %s", ticker, exc)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in FIELDS if c in df.columns]
    df = df[cols].copy()
    df = df.dropna(subset=["Close"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _split(raw: pd.DataFrame | None, tickers: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        level1 = set(raw.columns.get_level_values(1))
        for t in tickers:
            try:
                if t in level0:
                    df = raw[t]
                elif t in level1:
                    df = raw.xs(t, axis=1, level=1)
                else:
                    continue
            except KeyError:
                continue
            df = _clean(df)
            if not df.empty:
                out[t] = df
    elif len(tickers) == 1:
        df = _clean(raw)
        if not df.empty:
            out[tickers[0]] = df
    return out


def _download(tickers: list[str], period: str, interval: str, tries: int = 3) -> dict[str, pd.DataFrame]:
    delay = 3.0
    for attempt in range(1, tries + 1):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")        # yfinance 1.x on pandas 3 warns on every call
                raw = yf.download(
                    tickers,
                    period=period,
                    interval=interval,
                    group_by="ticker",
                    auto_adjust=False,
                    prepost=False,
                    threads=True,
                    progress=False,
                )
            parts = _split(raw, tickers)
            missing = [t for t in tickers if t not in parts]
            if missing and attempt < tries and len(missing) == len(tickers):
                logger.warning("download returned nothing for %d tickers (attempt %d)", len(tickers), attempt)
            else:
                if missing:
                    logger.warning("no data for %s", ", ".join(missing[:10]))
                return parts
        except Exception as exc:  # noqa: BLE001 - yfinance raises many exception types
            logger.warning("download failed (%s %s, attempt %d): %s", period, interval, attempt, exc)
        time.sleep(delay)
        delay *= 2
    return {}


def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _daily_index(df: pd.DataFrame) -> pd.DataFrame:
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert(config.IST).tz_localize(None)
    df.index = idx.normalize()
    return df[~df.index.duplicated(keep="last")].sort_index()


def _intraday_index(df: pd.DataFrame) -> pd.DataFrame:
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize(config.IST) if idx.tz is None else idx.tz_convert(config.IST)
    df.index = idx
    return df[~df.index.duplicated(keep="last")].sort_index()


def _merge(base: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    if base is None or base.empty:
        return new
    merged = pd.concat([base, new])
    return merged[~merged.index.duplicated(keep="last")].sort_index()


# ----------------------------------------------------------------------------- public API
def daily(
    tickers: list[str],
    period: str = "1y",
    as_of: date | None = None,
    offline: bool = False,
) -> dict[str, pd.DataFrame]:
    """Daily OHLCV per ticker with the partial-bar guard and as_of truncation applied."""
    tickers = list(dict.fromkeys(tickers))
    result: dict[str, pd.DataFrame] = {}
    for t in tickers:
        cached = _read_cache("daily", t)
        if cached is not None:
            result[t] = cached
    if not offline:
        fetched: set[str] = set()
        for chunk in _chunks(tickers, CHUNK):
            for t, df in _download(chunk, period, "1d").items():
                merged = _merge(result.get(t), _daily_index(df))
                result[t] = merged
                _write_cache("daily", t, merged)
                fetched.add(t)
        for t in [t for t in tickers if t not in fetched]:       # Yahoo drops tickers from batches at random
            for t2, df in _download([t], period, "1d", tries=2).items():
                merged = _merge(result.get(t2), _daily_index(df))
                result[t2] = merged
                _write_cache("daily", t2, merged)
    now = now_ist()
    out: dict[str, pd.DataFrame] = {}
    for t, df in result.items():
        if as_of is not None:
            df = df[df.index <= pd.Timestamp(as_of)]
        elif now.time() < config.DAILY_BAR_FINAL:
            df = df[df.index < pd.Timestamp(now.date())]
        if not df.empty:
            out[t] = df
    return out


def intraday(
    tickers: list[str],
    interval: str = "15m",
    period: str = "60d",
    as_of: date | None = None,
    offline: bool = False,
    keep_days: int = 120,
) -> dict[str, pd.DataFrame]:
    """Intraday bars (IST index) per ticker. Bars dated after as_of are dropped."""
    tickers = list(dict.fromkeys(tickers))
    kind = f"intraday_{interval}"
    result: dict[str, pd.DataFrame] = {}
    for t in tickers:
        cached = _read_cache(kind, t)
        if cached is not None:
            result[t] = cached
    if not offline:
        for chunk in _chunks(tickers, CHUNK):
            for t, df in _download(chunk, period, interval).items():
                merged = _merge(result.get(t), _intraday_index(df))
                cutoff = pd.Timestamp(now_ist()) - pd.Timedelta(days=keep_days)
                merged = merged[merged.index >= cutoff]
                result[t] = merged
                _write_cache(kind, t, merged)
    out: dict[str, pd.DataFrame] = {}
    for t, df in result.items():
        if as_of is not None:
            df = df[df.index.tz_convert(config.IST).date <= as_of] if len(df) else df
        if not df.empty:
            out[t] = df
    return out


def quotes(tickers: list[str]) -> dict[str, dict]:
    """Last price vs previous close for indices/futures: {ticker: {last, prev, chg_pct, asof}}."""
    out: dict[str, dict] = {}
    parts = _download(list(dict.fromkeys(tickers)), "5d", "1d")
    for t, df in parts.items():
        df = _daily_index(df)
        closes = df["Close"].dropna()
        if len(closes) < 2:
            continue
        last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
        if prev == 0:
            continue
        out[t] = {"last": last, "prev": prev, "chg_pct": (last / prev - 1.0) * 100.0, "asof": closes.index[-1].date()}
    return out


def today_bars(ticker: str, interval: str, trade_date: date) -> pd.DataFrame:
    """Bars of one ticker for a single session (fresh download, no as_of truncation)."""
    parts = _download([ticker], "5d", interval)
    df = parts.get(ticker)
    if df is None or df.empty:
        return pd.DataFrame(columns=FIELDS)
    df = _intraday_index(df)
    kind = f"intraday_{interval}"
    _write_cache(kind, ticker, _merge(_read_cache(kind, ticker), df))
    mask = df.index.date == trade_date
    return df[mask]
