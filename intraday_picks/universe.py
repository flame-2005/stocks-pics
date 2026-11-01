"""Nifty 100 universe with the NSE industry classification and Yahoo tickers.

The constituents CSV is fetched from NSE archives, cached for 30 days under DATA_DIR and backed
by a static copy in data/nifty100_fallback.csv so a network failure never blocks a run.
"""
from __future__ import annotations

import io
import time

import pandas as pd
import requests

from . import config
from .util import log

logger = log("universe")

# NSE "Industry" value -> Yahoo sector index used for sector strength (verified tickers).
# Industries without an entry use the equal-weight average of their constituents.
INDEX_FOR_INDUSTRY: dict[str, str] = {
    "Information Technology": "^CNXIT",
    "Automobile and Auto Components": "^CNXAUTO",
    "Healthcare": "^CNXPHARMA",
    "Fast Moving Consumer Goods": "^CNXFMCG",
    "Metals & Mining": "^CNXMETAL",
    "Oil Gas & Consumable Fuels": "^CNXENERGY",
    "Realty": "^CNXREALTY",
    "Financial Services": "NIFTY_FIN_SERVICE.NS",
    "Construction": "^CNXINFRA",
    "Consumer Durables": "^CNXCONSUM",
    "Consumer Services": "^CNXCONSUM",
}

SHORT_NAMES: dict[str, str] = {
    "Financial Services": "Financials",
    "Information Technology": "IT",
    "Automobile and Auto Components": "Auto",
    "Fast Moving Consumer Goods": "FMCG",
    "Oil Gas & Consumable Fuels": "Oil & Gas",
    "Metals & Mining": "Metals",
    "Construction Materials": "Cement",
    "Consumer Services": "Consumer Svcs",
    "Consumer Durables": "Durables",
    "Capital Goods": "Capital Goods",
    "Telecommunication": "Telecom",
}

_universe_cache: pd.DataFrame | None = None


def yahoo_symbol(symbol: str) -> str:
    return f"{symbol.strip().upper()}.NS"


def sector_short(industry: str) -> str:
    return SHORT_NAMES.get(industry, industry)


def _parse(csv_text: str) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as exc:  # noqa: BLE001 - any parse failure means "bad download"
        logger.warning("universe CSV parse failed: %s", exc)
        return None
    cols = {c.strip().lower(): c for c in df.columns}
    name_col = cols.get("company name") or cols.get("name")
    isin_col = cols.get("isin code") or cols.get("isin")
    if "symbol" not in cols or "industry" not in cols or name_col is None:
        logger.warning("universe CSV missing columns: %s", df.columns.tolist())
        return None
    out = pd.DataFrame(
        {
            "symbol": df[cols["symbol"]].astype(str).str.strip().str.upper(),
            "name": df[name_col].astype(str).str.strip(),
            "industry": df[cols["industry"]].astype(str).str.strip(),
            "isin": df[isin_col].astype(str).str.strip() if isin_col else "",
        }
    )
    out = out[out["symbol"].ne("") & out["symbol"].ne("NAN")].drop_duplicates("symbol")
    if len(out) < 50:
        logger.warning("universe CSV has only %d rows; rejecting", len(out))
        return None
    out["yahoo"] = out["symbol"].map(yahoo_symbol)
    return out.reset_index(drop=True)


def _download() -> pd.DataFrame | None:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
    for url in config.UNIVERSE_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200 and r.text.strip():
                df = _parse(r.text)
                if df is not None:
                    logger.info("universe downloaded from %s (%d symbols)", url, len(df))
                    return df
            else:
                logger.warning("universe %s -> HTTP %s", url, r.status_code)
        except requests.RequestException as exc:
            logger.warning("universe %s failed: %s", url, exc)
    return None


def load_universe(force: bool = False) -> pd.DataFrame:
    """DataFrame[symbol, name, industry, isin, yahoo] for the Nifty 100."""
    global _universe_cache
    if _universe_cache is not None and not force:
        return _universe_cache
    config.ensure_dirs()
    cache_file = config.DATA_DIR / "universe_nifty100.csv"
    df: pd.DataFrame | None = None
    fresh = cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < config.UNIVERSE_CACHE_DAYS * 86400
    if fresh and not force:
        df = _parse(cache_file.read_text(encoding="utf-8"))
    if df is None:
        df = _download()
        if df is not None:
            cache_file.write_text(df.to_csv(index=False), encoding="utf-8")
    if df is None and cache_file.exists():
        df = _parse(cache_file.read_text(encoding="utf-8"))
        if df is not None:
            logger.warning("using stale universe cache")
    if df is None:
        df = _parse(config.UNIVERSE_FALLBACK.read_text(encoding="utf-8"))
        logger.warning("using static universe fallback")
    if df is None:
        raise RuntimeError("no universe available (download, cache and fallback all failed)")
    _universe_cache = df
    return df


def industries(df: pd.DataFrame) -> list[str]:
    return sorted(df["industry"].unique().tolist())
