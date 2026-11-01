"""Central configuration: environment, paths, thresholds, weights, schedule.

Everything that should be tuned lives here. Values in .env override the sizing / secrets
section; the trading thresholds are plain constants so a change is a visible diff.
"""
from __future__ import annotations

import os
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

IST = ZoneInfo("Asia/Kolkata")


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


# --------------------------------------------------------------------------- paths
STATIC_DIR = ROOT / "data"
_default_data_dir = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "intraday-picks"
DATA_DIR = Path(_env("DATA_DIR", str(_default_data_dir)))
CACHE_DIR = DATA_DIR / "cache"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "picks.db"
LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()

# --------------------------------------------------------------------------- secrets / sizing
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
CAPITAL = _env_float("CAPITAL", 100_000.0)
RISK_PCT = _env_float("RISK_PCT", 1.0)
MAX_LEVERAGE = _env_float("MAX_LEVERAGE", 4.0)
DAILY_LOSS_CAP_PCT = _env_float("DAILY_LOSS_CAP_PCT", 1.5)
MAX_TRADES_PER_DAY = 2

# Supabase mirror for the Next.js dashboard (optional; sync is skipped when unset)
SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = _env("SUPABASE_SERVICE_ROLE_KEY")
SYNC_DAYS = int(_env_float("SYNC_DAYS", 10))

NO_TRADE_DATES: set[date] = set()
for _raw in _env("NO_TRADE_DATES").split(","):
    _raw = _raw.strip()
    if _raw:
        try:
            NO_TRADE_DATES.add(date.fromisoformat(_raw))
        except ValueError:
            pass

# --------------------------------------------------------------------------- universe
UNIVERSE_URLS = [
    "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "https://niftyindices.com/IndexConstituent/ind_nifty100list.csv",
]
UNIVERSE_FALLBACK = STATIC_DIR / "nifty100_fallback.csv"
UNIVERSE_CACHE_DAYS = 30
FUNNEL_TARGET = 30          # "list of different sectors' top stocks (~30)"
MAX_PER_INDUSTRY = 3
INDUSTRY_CAPS = {"Financial Services": 4}

# --------------------------------------------------------------------------- hard filters
MIN_PRICE = 100.0                 # no penny stocks
MIN_MEDIAN_TURNOVER_CR = 100.0    # 20-day median daily turnover, in crore rupees
ATR_PCT_MIN = 1.2                 # enough volatility to pay for an intraday trade
ATR_PCT_MAX = 5.0                 # too wild for a 1.5% stop
ATR_PCT_IDEAL = (1.5, 3.5)
MIN_DAILY_BARS = 210              # need SMA200 plus a margin

# --------------------------------------------------------------------------- screens
SMA_FAST = 50
SMA_SLOW = 200
RECENT_CROSS_DAYS = 20
EMA_15M = 200
MEDIAN_WINDOW = 20

BREAKOUT_LOOKBACK = 20
BREAKOUT_VOL_MULT = 1.5
BREAKOUT_MAX_EXTENSION = 1.03     # close must be within 3% of the broken level
CLOSE_POS_TOP = 0.67              # close in the top third of the day's range

MOVER_RET_MIN = 1.0               # "bottom of the gainers list": moved, but not exhausted
MOVER_RET_MAX = 3.5
MOVER_VOL_MULT = 1.5
ALREADY_MOVED_RET = 4.0           # beyond this the stock "has already moved"
ALREADY_MOVED_GAP = 2.0           # pre-open gap % in the trade direction

VOL_CONFIRM_MULT = 1.2
VOL_SHRINK_MULT = 0.8

# --------------------------------------------------------------------------- scoring
WEIGHT_REGIME = 2.0
WEIGHT_SETUP = 3.0
WEIGHT_VOLUME = 1.0
WEIGHT_SECTOR = 2.0
WEIGHT_ATR = 1.0
MIN_PICK_SCORE = 4.0              # below this a candidate is not worth a message
SECTOR_TOP_N = 3                  # top 3 sectors score 2, bottom 3 score 0
MIN_SECTOR_POINTS = 1             # funnel step: drop stocks in the weakest sectors

# --------------------------------------------------------------------------- market mood
VIX_NO_TRADE = 25.0
VIX_CAUTION = 20.0
NIFTY_GAP_NO_TRADE = 1.5          # pre-open gap % against the prevailing trend
MOOD_BULL_SCORE = 2
MOOD_BEAR_SCORE = -2
FII_THRESHOLD_CR = 1000.0
DII_THRESHOLD_CR = 1000.0

PICKS_TRENDING = 4
PICKS_NEUTRAL_EACH = 2

# --------------------------------------------------------------------------- decision mode
# "orb": the side (buy/sell) is decided at 09:34 from the Nifty's opening 15-minute candle and each
#        stock is confirmed on its own opening candle; the evening/09:10 runs only publish candidates.
# "evening": the side comes from the market mood the night before (original design).
DECISION_MODE = _env("DECISION_MODE", "orb").lower()
ORB_TARGET_R = 1.0                # backtest: 1R target had the best win rate at the same expectancy
ORB_CANDIDATES_PER_SIDE = 6       # candidates published at 09:10 for each side
ORB_ENTRY_DEADLINE = time(11, 0)  # an opening-range break after this is not taken

# --------------------------------------------------------------------------- trade plan
STOP_ATR_MULT = 0.6
STOP_MIN_PCT = 0.5
STOP_MAX_PCT = 1.5
TARGET_R = 2.0
TICK = 0.05
ENTRY_WINDOWS = ((time(9, 30), time(11, 0)), (time(13, 30), time(14, 45)))
SQUAREOFF = time(15, 10)
GAP_SKIP_PCT = 3.0                # pre-open |gap| above this: skip the stock
GAP_FLAG_PCT = 1.5                # above this: keep but flag

# --------------------------------------------------------------------------- schedule / guards
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
MORNING_CUTOFF = time(9, 25)
CONFIRM_START = time(9, 31)
CONFIRM_CUTOFF = time(10, 0)
SCORECARD_START = time(15, 35)
DAILY_BAR_FINAL = time(15, 35)    # before this, today's daily bar from Yahoo is partial

# --------------------------------------------------------------------------- yahoo tickers
NIFTY = "^NSEI"
BANKNIFTY = "^NSEBANK"
VIX = "^INDIAVIX"
GLOBAL_TICKERS = {
    "ES=F": "S&P 500 futures",
    "NQ=F": "Nasdaq futures",
    "^N225": "Nikkei 225",
    "^HSI": "Hang Seng",
    "BZ=F": "Brent crude",
    "INR=X": "USD/INR",
    "DX-Y.NYB": "Dollar index",
}

MANUAL_CHECK_LINKS = {
    "Moneycontrol gainers": "https://www.moneycontrol.com/stocks/marketstats/nsegainer/index.php",
    "Moneycontrol FII/DII": "https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/index.php",
    "Chartink breakouts": "https://chartink.com/screeners/breakout",
    "TopStockResearch MA": "https://www.topstockresearch.com/",
}


def ensure_dirs() -> None:
    for p in (DATA_DIR, CACHE_DIR, LOG_DIR, CACHE_DIR / "daily", CACHE_DIR / "intraday"):
        p.mkdir(parents=True, exist_ok=True)
