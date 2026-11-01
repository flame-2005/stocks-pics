"""Thin client for NSE India public JSON endpoints and archive files.

NSE blocks plain clients, so every call goes through a warmed-up session that carries the
cookies the home page sets, a browser User-Agent and a referer. Every public function returns
None (or an empty container) on failure and logs a warning; callers treat the data as
"unavailable" instead of crashing.
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import date, datetime
from typing import Any

import requests

from .util import log, to_num

logger = log("nse")

BASE = "https://www.nseindia.com"
ARCHIVES = "https://nsearchives.nseindia.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}
TIMEOUT = 15
RETRIES = 3

_session: requests.Session | None = None
_warmed_at: float = 0.0


def _get_session(force: bool = False) -> requests.Session:
    """Session carrying NSE cookies; re-warmed every 10 minutes or on demand."""
    global _session, _warmed_at
    if _session is None or force or (time.time() - _warmed_at) > 600:
        s = requests.Session()
        s.headers.update(HEADERS)
        try:
            s.get(BASE + "/", timeout=TIMEOUT)
        except requests.RequestException as exc:
            logger.warning("NSE warm-up failed: %s", exc)
        _session = s
        _warmed_at = time.time()
    return _session


def get_json(path: str, params: dict | None = None) -> Any | None:
    url = path if path.startswith("http") else BASE + path
    delay = 1.0
    for attempt in range(1, RETRIES + 1):
        s = _get_session(force=attempt > 1)
        try:
            r = s.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
            logger.warning("NSE %s -> HTTP %s (attempt %d)", path, r.status_code, attempt)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("NSE %s failed: %s (attempt %d)", path, exc, attempt)
        time.sleep(delay)
        delay *= 2
    return None


def get_text(url: str) -> str | None:
    delay = 1.0
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.text
            logger.warning("GET %s -> HTTP %s (attempt %d)", url, r.status_code, attempt)
        except requests.RequestException as exc:
            logger.warning("GET %s failed: %s (attempt %d)", url, exc, attempt)
        time.sleep(delay)
        delay *= 2
    return None


def parse_nse_date(text: str) -> date | None:
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text).strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


# ----------------------------------------------------------------------------- FII / DII
def fii_dii() -> dict | None:
    """Latest provisional FII/FPI and DII cash-market figures in crore rupees."""
    data = get_json("/api/fiidiiTradeReact")
    if not isinstance(data, list) or not data:
        return None
    out: dict[str, Any] = {"date": None, "source": "nse"}
    for row in data:
        cat = str(row.get("category", "")).upper()
        key = "fii" if ("FII" in cat or "FPI" in cat) else "dii" if "DII" in cat else None
        if key is None:
            continue
        out[f"{key}_buy"] = to_num(row.get("buyValue"))
        out[f"{key}_sell"] = to_num(row.get("sellValue"))
        out[f"{key}_net"] = to_num(row.get("netValue"))
        out["date"] = out["date"] or parse_nse_date(str(row.get("date", "")))
    if "fii_net" not in out and "dii_net" not in out:
        return None
    return out


# ----------------------------------------------------------------------------- pre-open
def pre_open(key: str = "FO") -> list[dict]:
    """Pre-open session snapshot. key: FO (F&O stocks), NIFTY, BANKNIFTY, ALL."""
    data = get_json("/api/market-data-pre-open", params={"key": key})
    rows: list[dict] = []
    if not isinstance(data, dict):
        return rows
    for item in data.get("data", []):
        meta = item.get("metadata", {}) if isinstance(item, dict) else {}
        symbol = meta.get("symbol")
        iep = to_num(meta.get("iep"))
        prev = to_num(meta.get("previousClose"))
        if not symbol or iep is None or not prev:
            continue
        rows.append(
            {
                "symbol": str(symbol).upper(),
                "iep": iep,
                "prev_close": prev,
                "gap_pct": (iep / prev - 1.0) * 100.0,
                "quantity": to_num(meta.get("finalQuantity"), 0.0),
                "turnover": to_num(meta.get("totalTurnover"), 0.0),
            }
        )
    return rows


# ----------------------------------------------------------------------------- events
def results_calendar() -> dict[str, date]:
    """Symbols with an upcoming board meeting about results -> earliest meeting date."""
    data = get_json("/api/event-calendar")
    out: dict[str, date] = {}
    if not isinstance(data, list):
        return out
    for row in data:
        purpose = f"{row.get('purpose', '')} {row.get('bm_desc', '')}".lower()
        if "result" not in purpose:
            continue
        d = parse_nse_date(str(row.get("date", "")))
        symbol = row.get("symbol")
        if symbol and d:
            symbol = str(symbol).upper()
            if symbol not in out or d < out[symbol]:
                out[symbol] = d
    return out


# ----------------------------------------------------------------------------- F&O ban
def fo_ban_list() -> tuple[set[str], date | None]:
    """Securities in the F&O ban period: (symbols, trade date the list applies to)."""
    text = get_text(ARCHIVES + "/content/fo/fo_secban.csv")
    if not text:
        return set(), None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    applies_to = None
    if lines and "ban" in lines[0].lower():
        match = re.search(r"\d{1,2}-[A-Za-z]{3}-\d{4}", lines[0])
        applies_to = parse_nse_date(match.group(0)) if match else None
        lines = lines[1:]
    symbols: set[str] = set()
    for row in csv.reader(io.StringIO("\n".join(lines))):
        cells = [c.strip() for c in row if c.strip()]
        if not cells:
            continue
        candidate = cells[1] if len(cells) >= 2 else cells[0]
        if candidate and not candidate.isdigit():
            symbols.add(candidate.upper())
    return symbols, applies_to


# ----------------------------------------------------------------------------- holidays
def holidays() -> list[dict] | None:
    """Capital-market trading holidays for the current year from holiday-master."""
    data = get_json("/api/holiday-master", params={"type": "trading"})
    if not isinstance(data, dict) or "CM" not in data:
        return None
    out = []
    for h in data["CM"]:
        d = parse_nse_date(str(h.get("tradingDate", "")))
        if not d:
            continue
        special = any((h.get(k) or "-") != "-" for k in ("morning_session", "evening_session"))
        out.append(
            {
                "date": d.isoformat(),
                "description": str(h.get("description", "")).strip(),
                "special_session": special,
            }
        )
    return out
