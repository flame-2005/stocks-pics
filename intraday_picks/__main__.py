"""CLI entry point.

  python -m intraday_picks doctor
  python -m intraday_picks fetch
  python -m intraday_picks prep      [--as-of 2026-10-29] [--dry-run] [--force] [--offline]
  python -m intraday_picks morning   [--as-of DATE] [--dry-run] [--force] [--offline]
  python -m intraday_picks confirm   [--as-of DATE] [--dry-run] [--force]
  python -m intraday_picks scorecard [--as-of DATE] [--dry-run] [--force]
  python -m intraday_picks backtest  [--months 6] [--offline]
  python -m intraday_picks sync      [--since 2026-10-01]
  python -m intraday_picks watchlist [--as-of DATE] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _date(text: str) -> date:
    return date.fromisoformat(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="intraday_picks", description="Daily NSE intraday stock recommender")
    sub = parser.add_subparsers(dest="mode", required=True)

    def common(p: argparse.ArgumentParser, as_of: bool = True) -> None:
        if as_of:
            p.add_argument("--as-of", type=_date, help="replay as if run with data up to this date (YYYY-MM-DD)")
        p.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
        p.add_argument("--force", action="store_true", help="ignore the once-per-day and time-window guards")
        p.add_argument("--offline", action="store_true", help="use cached data only, no network")

    sub.add_parser("doctor", help="environment and data-source health check")
    fetch = sub.add_parser("fetch", help="download/refresh all market data and report coverage")
    fetch.add_argument("--no-check", action="store_true")
    for mode, help_text in (
        ("prep", "evening run: compute the watchlist for the next session"),
        ("morning", "09:10 run: final picks with pre-open, global cues and guards"),
        ("confirm", "09:34 run: check the opening 15-minute candle"),
        ("scorecard", "15:45 run: evaluate what happened"),
    ):
        common(sub.add_parser(mode, help=help_text))
    bt = sub.add_parser("backtest", help="replay the evening pipeline over history")
    bt.add_argument("--months", type=int, default=6)
    bt.add_argument("--strategy", choices=["evening", "orb"], default="evening",
                    help="evening = picks decided the night before (daily bars); orb = side decided at 09:34 from opening candles (5-minute bars, last ~60 sessions)")
    bt.add_argument("--days", type=int, default=60, help="orb mode: sessions of 5-minute history to use")
    bt.add_argument("--offline", action="store_true")
    bt.add_argument("--out", help="CSV path for per-pick results")
    wl = sub.add_parser("watchlist", help="build this month's 30-stock watch universe (+ Nifty) from last month's data")
    common(wl)
    sync = sub.add_parser("sync", help="push local SQLite tables to Supabase")
    sync.add_argument("--since", type=_date, help="only rows with trade_date >= this date")
    sync.add_argument("--all", action="store_true", help="push every row (default: last 10 days)")

    args = parser.parse_args(argv)

    from . import pipeline

    if args.mode == "doctor":
        return 0 if pipeline.run_doctor() else 1
    if args.mode == "fetch":
        pipeline.run_fetch(check=not args.no_check)
        return 0
    if args.mode == "backtest":
        if args.strategy == "orb":
            from . import backtest_orb

            backtest_orb.run(days=args.days, offline=args.offline, out_csv=args.out)
            return 0
        from . import backtest

        backtest.run(months=args.months, offline=args.offline, out_csv=args.out)
        return 0
    if args.mode == "sync":
        from . import sync as syncmod

        syncmod.run(since=args.since, push_all=args.all)
        return 0
    if args.mode == "watchlist":
        from . import watchlist

        watchlist.run(as_of=args.as_of, offline=args.offline, dry_run=args.dry_run)
        if not args.dry_run:
            try:
                from . import sync as syncmod

                syncmod.run(quiet=True)
            except Exception as exc:  # noqa: BLE001
                print(f"sync skipped: {exc}")
        return 0

    runner = {
        "prep": pipeline.run_prep,
        "morning": pipeline.run_morning,
        "confirm": pipeline.run_confirm,
        "scorecard": pipeline.run_scorecard,
    }[args.mode]
    runner(as_of=args.as_of, dry_run=args.dry_run, force=args.force, offline=args.offline)
    if args.mode in ("prep", "morning") and not args.dry_run:
        try:
            from . import sync as syncmod

            syncmod.run(quiet=True)
        except Exception as exc:  # noqa: BLE001 - sync must never break a trading run
            print(f"sync skipped: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
