# Intraday Picks

A daily NSE intraday stock recommender that runs a hand-written trading playbook automatically:
market mood first, a sector-based funnel, moving-average trend, breakouts confirmed on the opening
candle, lower-ranked gainers handled with care, and volume as the tie-breaker. It sends 3–4 picks to
Telegram before the open, re-checks them after the first 15-minute candle, scores what happened at
the close, and keeps every run in a database so the rules can be judged on evidence.

Not financial advice. Paper-trade the output for a few weeks before risking money.

## What runs when (IST, Mon–Fri)

| Time  | Mode        | What it does                                                                                           | Sends                                  |
|-------|-------------|--------------------------------------------------------------------------------------------------------|----------------------------------------|
| 20:00 | `prep`      | Downloads daily + 15-minute data, runs the funnel (100 → ~30 → setups → sectors), stores candidates    | Tomorrow's watchlist: buy and sell candidates |
| 09:10 | `morning`   | Re-checks with FII/DII, S&P futures, Asia, Brent, USD/INR, India VIX, pre-open gaps, results, F&O ban   | Final candidates per side (up to 6 each) |
| 09:34 | `confirm`   | Reads the Nifty's opening 15-minute candle for the side, confirms each candidate on its own candle, builds the trade (break of the candle, stop at the other end, 1R target) | **The picks**, up to 4, with entry / SL / target / qty |
| 15:45 | `scorecard` | Replays the day's 5-minute bars: entry before 11:00, first touch of stop or target, square-off at 15:10 | Outcomes in R and rupees               |

Each mode runs once per trading day (re-runs are no-ops), skips holidays and weekends, and refuses to
run outside its time window unless `--force`. `--as-of YYYY-MM-DD` replays any past day.

### Two decision modes

`DECISION_MODE` in `.env` (default `orb`):

- **`orb`** (opening range): the evening and 09:10 runs only publish candidates on both sides. At 09:34 the
  Nifty's first 15-minute candle decides buy or sell day (a move under 0.10% means no trade), and a
  candidate is taken only if its own first candle is in the same direction, beyond yesterday's close and
  on the right side of the 15-minute EMA200. Entry is a break of that candle, stop the other end, target 1R.
- **`evening`**: the original design. The market mood the night before picks the side, picks carry
  entry above yesterday's high / below yesterday's low with an ATR stop and a 2R target, and 09:34 only
  confirms or cancels them.

Why `orb` is the default. On the same 42 sessions (1 Sep to 30 Oct 2026) replayed on real 5-minute bars:

| Approach | Trades | Win rate | Avg per trade | Net after ~0.1% costs |
|---|---|---|---|---|
| evening mode | 78 | 49–53% | −0.02 to −0.04R | −8 to −13% |
| orb mode (setups + opening candle) | 36 | 53–64% | +0.16 to +0.20R | +2.7 to +4.0% |

The Nifty's opening candle called the day's open-to-close direction right on 20 of 28 directional
days (71%) against about 50% for the evening mood. 36 trades is a small sample; the system keeps
scoring itself so this comparison can be re-run as data accumulates
(`python -m intraday_picks backtest --strategy orb`).

## How the notebook rules map to code

| Rule in the notes | Where | Implementation |
|---|---|---|
| Market sentiment: Moneycontrol, global market, FII/DII | `sentiment.py` | Nifty vs EMA20/50, VIX, ES=F, Nikkei/HSI, Brent, USD/INR, FII+DII → bullish / bearish / neutral / no-trade gate |
| Follow the market trend | `scoring.rank` | Bullish day → longs only, bearish → shorts only, neutral → 2 each, no-trade → sit out |
| Large cap, liquid, volatile; no penny/small/low-volume | `screens.hard_filter_fails` | Nifty 100; 20-day median turnover ≥ ₹100 cr; price ≥ ₹100; ATR% in 1.2–5% |
| ~30 stocks across sectors → candlestick → 12 → strong sector → 4 | `screens.liquidity_funnel`, `patterns.py`, `sectors.py` | Top 2–3 per industry by turnover; prior-day patterns; sector relative strength vs Nifty; counts printed in every message |
| 50/200 DMA crossover, 15-min 200 EMA | `screens.compute_features`, `confirm.py` | Regime alignment (close > SMA50 > SMA200) with a bonus for a recent cross; 15-min EMA200 is a hard gate at 09:34 |
| Breakouts, wait for confirmation, avoid fakes | `screens.setup_for`, `confirm.py` | 20-day high/low break on ≥1.5× median volume, close in the top third, not extended; first candle must hold the level |
| Top gainers, pick lower ranks, risky | mover screen | +1% to +3.5% on volume = mover; > 4% or a 2% pre-open gap = "already moved" penalty |
| Always use volume | volume screen | Volume ≥ 1.2× median with price confirms; a move on shrinking volume is penalised |
| Timing | schedule + message | Night prep, 09:10 picks, 09:34 confirmation; entry windows 09:30–11:00 and 13:30–14:45, square off 15:10 |
| No excessive trading | every message | Max 2 trades, daily loss cap 1.5%, no re-entry after a stop |

All thresholds and weights live in `intraday_picks/config.py`.

## Setup (Windows, Python 3.12)

```powershell
cd C:\Users\91636\OneDrive\Desktop\shadab\intraday-picks
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env        # then fill in the values below
.venv\Scripts\python -m intraday_picks doctor
```

`.env` values:

- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: create a bot with @BotFather, send it one message, then read your chat id from `https://api.telegram.org/bot<TOKEN>/getUpdates`.
- `CAPITAL`, `RISK_PCT`, `MAX_LEVERAGE`, `DAILY_LOSS_CAP_PCT`: position sizing. Only the printed quantity changes.
- `DATA_DIR`: leave empty to use `%LOCALAPPDATA%\intraday-picks` (SQLite + parquet cache must stay out of OneDrive).
- `NO_TRADE_DATES`: comma-separated dates to force a no-trade message (budget day, RBI policy, election results).
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`: only needed for the web dashboard (below).

Then:

```powershell
.venv\Scripts\python -m intraday_picks fetch                 # warm the data cache, check coverage
.venv\Scripts\python -m intraday_picks prep --dry-run        # see tonight's watchlist in the console
.venv\Scripts\python -m intraday_picks morning --dry-run --force
.venv\Scripts\python -m pytest tests -q
powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1   # schedule the four daily jobs
```

The scheduler runs `scripts\run.cmd <mode>` under your account, wakes the laptop if asleep, and runs
late if the time was missed. The laptop must be on (locked is fine) and logged in. Logs:
`%LOCALAPPDATA%\intraday-picks\logs\task.log` and `intraday.log`.

### Replaying a day

```powershell
.venv\Scripts\python -m intraday_picks prep      --as-of 2026-10-29 --dry-run --force   # evening before
.venv\Scripts\python -m intraday_picks morning   --as-of 2026-10-30 --dry-run --force
.venv\Scripts\python -m intraday_picks confirm   --as-of 2026-10-30 --dry-run --force
.venv\Scripts\python -m intraday_picks scorecard --as-of 2026-10-30 --dry-run --force
```

### Backtest

```powershell
.venv\Scripts\python -m intraday_picks backtest --months 6            # evening mode on daily bars
.venv\Scripts\python -m intraday_picks backtest --strategy orb --days 60   # 09:34 mode on 5-minute bars
```

Replays the evening pipeline over history and scores each pick on the next session: exact first-touch
on 5-minute bars where the cache has them, otherwise a daily approximation that counts "both stop and
target inside the day's range" as a stop. Prints hit rate and average R by setup, side, mood and sector
points, and writes a per-pick CSV under `%LOCALAPPDATA%\intraday-picks\backtests\`. Caveats are
printed with the results (survivorship bias, no FII/global inputs historically).

## Data sources (all free)

| Need | Source |
|---|---|
| Universe + industry | `archives.nseindia.com/content/indices/ind_nifty100list.csv` (static fallback in `data/`) |
| Daily, 15-min and 5-min bars; indices; global futures | Yahoo Finance via `yfinance` (`auto_adjust=False`, parquet cache) |
| FII/DII, holidays, results calendar, pre-open, F&O ban | NSE public JSON endpoints and archives (`nse.py`) |

Moneycontrol's FII/DII table is rendered client-side and cannot be scraped; the NSE endpoint is used
instead and the figures are stored daily to build a local history.

## Web dashboard (Next.js on Vercel, invite-only)

The dashboard lives in `dashboard/` and reads from Supabase, which the Python side mirrors into after
every run (`sync` runs automatically after `prep` and `morning`; `python -m intraday_picks sync --all`
pushes everything).

1. Create a Supabase project. In the SQL editor run `supabase/migrations/0001_init.sql`.
2. Authentication → Sign In / Providers → Email: turn **off** "Allow new users to sign up". Only
   people you invite (Authentication → Users → Invite user) can log in.
3. Authentication → URL configuration: Site URL = your Vercel URL; add
   `https://<your-app>.vercel.app/auth/confirm` to Redirect URLs.
4. Authentication → Email templates: in **Invite user**, **Magic Link** and **Reset Password** replace
   the link with
   `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type={{ .Type }}&next=/set-password`
   (for Magic Link use `next=/`).
5. Put `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (Project Settings → API) in the laptop's `.env`.
6. Deploy `dashboard/` to Vercel with env vars `NEXT_PUBLIC_SUPABASE_URL` and
   `NEXT_PUBLIC_SUPABASE_ANON_KEY` (the anon key, never the service-role key).

Pages: **Today** (mood, funnel, picks with confirmation and outcome, sector strength), **History**
(hit rate, average R, cumulative R, breakdown by setup and mood, every pick), **Market** (mood and
flows by day), **Watchlist** (the month's 30-stock watch universe plus Nifty 50 and Bank Nifty, with
last-month returns, trend, volatility, turnover and how each name fared in the picks).

### Monthly watch universe

```powershell
.venv\Scripts\python -m intraday_picks watchlist            # build/refresh this month's 30 + indices
.venv\Scripts\python -m intraday_picks watchlist --dry-run  # print only
```

The list is the notebook's "30 top stocks across sectors": the most liquid names per industry from
the previous month (same funnel the daily runs use), frozen for the month. The evening run builds it
automatically the first time it sees a new month. Also run `supabase/migrations/0002_watchlist.sql`.

## Layout

```
intraday_picks/
  __main__.py        CLI: doctor | fetch | prep | morning | confirm | scorecard | backtest | sync
  config.py          every threshold, weight, time window and env value
  pipeline.py        the four modes, guards and idempotency
  datasource.py      yfinance + parquet cache, partial-bar guard, as-of truncation
  nse.py             NSE endpoints with cookie warm-up and retries
  universe.py        Nifty 100 + industry → sector index map
  trading_calendar.py  holidays, next/prev session, expiry day
  indicators.py  patterns.py  screens.py  sectors.py  sentiment.py  scoring.py  plan.py
  orb.py             opening-range decision: Nifty candle direction, stock confirmation, entry/stop
  watchlist.py       monthly 30-stock watch universe + index rows with last-month stats
  confirm.py  outcomes.py  report.py  notify.py  storage.py  sync.py  backtest.py  backtest_orb.py
dashboard/           Next.js app (Supabase auth + data)
supabase/migrations/ Postgres schema + RLS for the dashboard
scripts/             run.cmd, register_tasks.ps1
tests/               pytest suite on synthetic candles (no network)
```

## Your list (Nifty + your own companies)

`focus_list.txt` in the project root holds one NSE symbol per line (comments with `#`). The Nifty is
always included and is traded through the NIFTYBEES ETF. Every symbol on the list gets its own daily
verdict, separate from the system's picks:

| Time | Verdict |
|---|---|
| 20:00 and 09:10 | a lean: "lean BUY", "lean SELL" or "NO" from yesterday's candle, the trend and the market mood |
| 09:34 | a firm "BUY", "SELL" or "NO" with entry, stop, target and quantity when it is a trade: the Nifty's opening candle sets the side, the symbol's own opening candle has to confirm it, and a company also needs a setup from the day before |
| 15:45 | the result of that verdict (target / stop / square-off, R and rupees) |

The verdicts appear as a "Your list" section in each Telegram message, on the dashboard's **Your list**
page (with a running record per symbol), and in the `focus_verdicts` table. Run
`python -m intraday_picks focus` any time to print the current lean without sending anything.
Database: run `supabase/migrations/0003_focus.sql` once (or `supabase/setup.sql` again).
