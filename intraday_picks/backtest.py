"""Replay the evening pipeline over history and score each pick on the next session.

Two evaluation tiers:
  exact  - 5-minute bars exist in the local cache for that day (recent sessions): first-touch replay.
  daily  - only the daily bar is known: triggered if the day's range crosses the entry; if both
           stop and target lie inside the day's range the stop is assumed (ambiguous, conservative).
No look-ahead: features for session S use bars <= S; the trade happens on the next session.
Known bias: today's Nifty 100 list is applied backwards (survivorship), acceptable for ranking
signals against each other, not for absolute return claims.
"""
from __future__ import annotations

import csv
import time
from collections import defaultdict
from datetime import date

import pandas as pd

from . import config, datasource as ds, outcomes as oc, plan as planmod, scoring, screens, sectors as sec, sentiment
from . import universe as uni
from .pipeline import _index_tickers
from .util import log, today_ist

logger = log("backtest")


def _truncate(frames: dict[str, pd.DataFrame], upto: pd.Timestamp) -> dict[str, pd.DataFrame]:
    return {t: df[df.index <= upto] for t, df in frames.items()}


def _daily_eval(pick: planmod.TradePlan, bar: pd.Series) -> tuple[str, float | None, bool]:
    o, h, l, c = float(bar["Open"]), float(bar["High"]), float(bar["Low"]), float(bar["Close"])
    long = pick.side == "long"
    triggered = h >= pick.entry if long else l <= pick.entry
    if not triggered:
        return "no_entry", None, False
    fill = max(pick.entry, o) if long else min(pick.entry, o)
    risk = abs(pick.entry - pick.stop)
    hit_stop = l <= pick.stop if long else h >= pick.stop
    hit_target = h >= pick.target if long else l <= pick.target
    if hit_stop and hit_target:
        return "stop", round(((pick.stop - fill) if long else (fill - pick.stop)) / risk, 3), True
    if hit_stop:
        return "stop", round(((pick.stop - fill) if long else (fill - pick.stop)) / risk, 3), False
    if hit_target:
        return "target", round(((pick.target - fill) if long else (fill - pick.target)) / risk, 3), False
    return "eod_close", round(((c - fill) if long else (fill - c)) / risk, 3), False


def run(months: int = 6, offline: bool = False, out_csv: str | None = None) -> list[dict]:
    t0 = time.time()
    universe_df = uni.load_universe()
    stocks = universe_df["yahoo"].tolist()
    daily = ds.daily(stocks + _index_tickers(), period="2y", offline=offline)
    nifty = daily.get(config.NIFTY)
    if nifty is None or len(nifty) < 260:
        raise RuntimeError("not enough Nifty history for a backtest")
    sessions = [d for d in nifty.index if d >= pd.Timestamp(today_ist()) - pd.DateOffset(months=months)]
    all_dates = list(nifty.index)
    rows: list[dict] = []
    logger.info("backtesting %d sessions over %d stocks", len(sessions), len(stocks))

    for i, session in enumerate(sessions):
        pos = all_dates.index(session)
        if pos + 1 >= len(all_dates):
            break
        trade_day = all_dates[pos + 1]
        upto = _truncate(daily, session)
        feats: dict[str, screens.Features] = {}
        for row in universe_df.itertuples(index=False):
            df = upto.get(row.yahoo)
            if df is None or len(df) < config.MIN_DAILY_BARS:
                continue
            f = screens.compute_features(row.symbol, row.industry, row.yahoo, df, None)
            if f is not None:
                feats[row.symbol] = f
        if not feats:
            continue
        funnel = screens.liquidity_funnel(feats)
        sectors = sec.sector_strength(universe_df, upto, upto.get(config.NIFTY), {t: upto[t] for t in _index_tickers() if t in upto})
        mood = sentiment.assess(trade_day.date(), upto.get(config.NIFTY), upto.get(config.VIX), None, None)
        result = scoring.rank(feats, funnel, sec.as_map(sectors), mood)
        for rank, cand in enumerate(result.picks, start=1):
            p = planmod.build(cand, rank)
            if p is None:
                continue
            day_df = daily.get(cand.features.yahoo)
            if day_df is None or trade_day not in day_df.index:
                continue
            res, r, ambiguous = _daily_eval(p, day_df.loc[trade_day])
            tier = "daily"
            bars5 = ds.intraday([cand.features.yahoo], interval="5m", period="5d", offline=True).get(cand.features.yahoo)
            if bars5 is not None and (bars5.index.date == trade_day.date()).any():
                exact = oc.evaluate({"side": p.side, "entry": p.entry, "stop": p.stop, "target": p.target, "qty": p.qty}, bars5, trade_day.date())
                res, r, ambiguous, tier = exact["result"], exact["r_multiple"], False, "exact"
            rows.append(
                {
                    "trade_date": trade_day.date().isoformat(), "symbol": p.symbol, "side": p.side, "rank": rank,
                    "setup": p.setup_type, "score": p.score, "mood": mood.label, "sector_points": cand.sector_points,
                    "entry": p.entry, "stop": p.stop, "target": p.target, "result": res, "r": r,
                    "ambiguous": ambiguous, "tier": tier,
                }
            )
        if (i + 1) % 20 == 0:
            logger.info("  %d/%d sessions, %d picks so far", i + 1, len(sessions), len(rows))

    _report(rows)
    out_dir = config.DATA_DIR / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_csv or str(out_dir / f"backtest_{today_ist().isoformat()}_{months}m.csv")
    if rows:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nper-pick results: {path}")
    print(f"done in {time.time() - t0:.0f}s")
    return rows


def _stats(rows: list[dict]) -> dict:
    taken = [r for r in rows if r["result"] not in ("no_entry", "skipped")]
    rs = [r["r"] for r in taken if r["r"] is not None]
    targets = sum(1 for r in taken if r["result"] == "target")
    stops = sum(1 for r in taken if r["result"] == "stop")
    return {
        "picks": len(rows),
        "taken": len(taken),
        "targets": targets,
        "stops": stops,
        "hit_rate": (targets / (targets + stops) * 100.0) if (targets + stops) else 0.0,
        "avg_r": (sum(rs) / len(rs)) if rs else 0.0,
        "total_r": sum(rs) if rs else 0.0,
        "ambiguous_pct": (sum(1 for r in taken if r["ambiguous"]) / len(taken) * 100.0) if taken else 0.0,
    }


def _print_table(title: str, groups: dict[str, list[dict]]) -> None:
    print(f"\n{title}")
    print(f"{'group':<22}{'picks':>6}{'taken':>6}{'hit%':>7}{'avgR':>7}{'totR':>8}{'ambig%':>8}")
    for key in sorted(groups, key=lambda k: -_stats(groups[k])["total_r"]):
        s = _stats(groups[key])
        print(f"{str(key):<22}{s['picks']:>6}{s['taken']:>6}{s['hit_rate']:>7.0f}{s['avg_r']:>7.2f}{s['total_r']:>8.1f}{s['ambiguous_pct']:>8.0f}")


def _report(rows: list[dict]) -> None:
    if not rows:
        print("no picks generated in the window")
        return
    s = _stats(rows)
    print(
        f"\nOverall: {s['picks']} picks, {s['taken']} triggered, hit rate {s['hit_rate']:.0f}%, "
        f"avg {s['avg_r']:+.2f}R, total {s['total_r']:+.1f}R, ambiguous {s['ambiguous_pct']:.0f}% (counted as stops)"
    )
    for field_name, title in (("setup", "By setup"), ("side", "By side"), ("mood", "By market mood"), ("sector_points", "By sector points"), ("tier", "By evaluation tier")):
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            groups[str(r[field_name])].append(r)
        _print_table(title, groups)
    print("\nCaveats: survivorship bias (today's Nifty 100 applied backwards); daily tier ignores intraday path; "
          "no FII/global inputs in the mood, so the mood is trend + VIX only.")
