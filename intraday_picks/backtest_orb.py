"""Backtest of the 09:34 opening-range decision on real 5-minute bars (last ~60 sessions).

Variants:
  evening   the evening pick list traded as planned (baseline, same days)
  A         evening shortlist (stocks with a setup) filtered to the Nifty's opening direction
            and the stock's own opening-candle confirmation, top 4 by evening score
  B         all ~30 liquid funnel stocks, side from the Nifty's opening candle, confirmed on the
            stock's candle, top 4 by opening-candle strength relative to the Nifty
  A-all/B-all  the same without the top-4 cut (the raw edge of the rule)
Exits: opening-range stop with a 1R / 1.5R / 2R target, or stop-only until 15:10.
"""
from __future__ import annotations

import csv
import time
from collections import defaultdict
from datetime import date

import pandas as pd

from . import config, datasource as ds, indicators as ind, orb, plan as planmod, scoring, screens, sectors as sec, sentiment
from . import universe as uni
from .pipeline import _index_tickers
from .util import log, today_ist

logger = log("backtest_orb")

TARGETS = [1.0, 1.5, 2.0, None]       # None = stop only, hold to 15:10
COST_PCT = 0.10                        # round-trip brokerage, STT, charges (approx.)


_ema200_at_open = orb.ema200_at_open


def run(days: int = 60, offline: bool = False, out_csv: str | None = None) -> list[dict]:
    t0 = time.time()
    universe_df = uni.load_universe()
    stocks = universe_df["yahoo"].tolist()
    daily = ds.daily(stocks + _index_tickers(), period="2y", offline=True)
    bars15 = ds.intraday(stocks + [config.NIFTY], interval="15m", period="60d", offline=offline)
    bars5 = ds.intraday(stocks + [config.NIFTY], interval="5m", period="60d", offline=offline)
    nifty_daily = daily[config.NIFTY]
    nifty15 = bars15.get(config.NIFTY)
    nifty5 = bars5.get(config.NIFTY)
    if nifty15 is None:
        raise RuntimeError("no 15-minute Nifty data; cannot read the opening candle")
    have_5m_days = sorted({ts.date() for ts in next(iter(bars5.values())).index})
    sessions = [d for d in have_5m_days if d >= today_ist() - pd.Timedelta(days=days)]
    logger.info("%d sessions with 5-minute data, %d stocks", len(sessions), len(stocks))

    rows: list[dict] = []
    day_stats: list[dict] = []
    for day in sessions:
        ts_day = pd.Timestamp(day)
        prev_idx = nifty_daily.index[nifty_daily.index < ts_day]
        if len(prev_idx) < 260:
            continue
        prev_session = prev_idx[-1]
        upto = {t: df[df.index <= prev_session] for t, df in daily.items()}
        feats: dict[str, screens.Features] = {}
        for r in universe_df.itertuples(index=False):
            df = upto.get(r.yahoo)
            if df is None or len(df) < config.MIN_DAILY_BARS:
                continue
            f = screens.compute_features(r.symbol, r.industry, r.yahoo, df, None)
            if f is not None:
                feats[r.symbol] = f
        funnel = screens.liquidity_funnel(feats)
        sectors = sec.sector_strength(universe_df, upto, upto.get(config.NIFTY), {t: upto[t] for t in _index_tickers() if t in upto})
        smap = sec.as_map(sectors)
        mood = sentiment.assess(day, upto.get(config.NIFTY), upto.get(config.VIX), None, None)
        evening = scoring.rank(feats, funnel, smap, mood)

        nifty_prev_close = float(upto[config.NIFTY]["Close"].iloc[-1])
        n_or = orb.opening_range(nifty15, day, nifty_prev_close)
        direction = orb.market_direction(n_or)
        nifty_oc = None
        if nifty5 is not None:
            nd = nifty5[nifty5.index.date == day]
            if len(nd) > 3:
                nifty_oc = (float(nd["Close"].iloc[-1]) / float(nd["Open"].iloc[0]) - 1) * 100
        day_stats.append({"day": day.isoformat(), "direction": direction, "nifty_first_pct": n_or.pct if n_or else None,
                          "nifty_open_to_close": nifty_oc, "evening_mood": mood.label})

        # ---- baseline: evening picks traded as planned
        for rank, cand in enumerate(evening.picks, start=1):
            p = planmod.build(cand, rank)
            b5 = bars5.get(cand.features.yahoo)
            if p is None or b5 is None:
                continue
            for tgt in TARGETS:
                plan = {"side": p.side, "entry": p.entry, "stop": p.stop, "target": p.target if tgt is None else round(p.entry + (tgt if p.side == "long" else -tgt) * abs(p.entry - p.stop), 2)}
                res = orb.simulate(plan, b5, day, entry_until=config.ENTRY_WINDOWS[1][1], use_target=tgt is not None)
                rows.append({"variant": "evening", "target": tgt or "stop-only", "day": day.isoformat(), "symbol": p.symbol, "side": p.side,
                             "rank": rank, "setup": p.setup_type, "stop_pct": p.stop_pct, **res})

        if direction == "flat":
            continue
        side = "long" if direction == "up" else "short"

        # ---- candidates for A (setup on the Nifty's side) and B (all liquid funnel stocks)
        cand_a: list[tuple[float, screens.Features]] = []
        cand_b: list[tuple[float, screens.Features]] = []
        for symbol in funnel:
            f = feats.get(symbol)
            if f is None or not f.passes:
                continue
            o_r = orb.opening_range(bars15.get(f.yahoo), day, f.close)
            if o_r is None:
                continue
            ok, _ = orb.qualifies(f, o_r, _ema200_at_open(bars15.get(f.yahoo), day), side)
            if not ok:
                continue
            rel_strength = (o_r.pct - (n_or.pct if n_or else 0.0)) * (1 if side == "long" else -1)
            setup_type, setup_pts, _ = screens.setup_for(f, side)
            if setup_pts >= 1:
                c = scoring.score(f, side, smap.get(f.industry))
                cand_a.append((c.score + rel_strength / 10, f))
            cand_b.append((rel_strength, f))
        cand_a.sort(key=lambda x: -x[0])
        cand_b.sort(key=lambda x: -x[0])

        for variant, cands, top in (("A", cand_a, 4), ("A-all", cand_a, None), ("B", cand_b, 4), ("B-all", cand_b, None)):
            chosen = cands if top is None else cands[:top]
            for rank, (_, f) in enumerate(chosen, start=1):
                o_r = orb.opening_range(bars15.get(f.yahoo), day, f.close)
                b5 = bars5.get(f.yahoo)
                if o_r is None or b5 is None:
                    continue
                for tgt in TARGETS:
                    plan = orb.orb_plan(o_r, side, tgt or 2.0)
                    res = orb.simulate(plan, b5, day, use_target=tgt is not None)
                    rows.append({"variant": variant, "target": tgt or "stop-only", "day": day.isoformat(), "symbol": f.symbol, "side": side,
                                 "rank": rank, "setup": screens.setup_for(f, side)[0], "stop_pct": round(plan["stop_pct"], 2), **res})

    _report(rows, day_stats)
    out_dir = config.DATA_DIR / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_csv or str(out_dir / f"orb_backtest_{today_ist().isoformat()}.csv")
    if rows:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nper-trade results: {path}")
    print(f"done in {time.time() - t0:.0f}s")
    return rows


def _stats(rows: list[dict]) -> dict:
    taken = [r for r in rows if r["result"] in ("target", "stop", "eod_close")]
    rs = [r["r"] for r in taken if r["r"] is not None]
    pcts = [r["pct"] for r in taken if r["pct"] is not None]
    targets = sum(1 for r in taken if r["result"] == "target")
    stops = sum(1 for r in taken if r["result"] == "stop")
    wins = sum(1 for r in taken if (r["pct"] or 0) > 0)
    return {
        "signals": len(rows), "taken": len(taken), "targets": targets, "stops": stops,
        "win_pct": wins / len(taken) * 100 if taken else 0.0,
        "avg_r": sum(rs) / len(rs) if rs else 0.0, "total_r": sum(rs) if rs else 0.0,
        "avg_pct": sum(pcts) / len(pcts) if pcts else 0.0,
        "net_pct": (sum(pcts) - COST_PCT * len(pcts)) if pcts else 0.0,
    }


def _report(rows: list[dict], day_stats: list[dict]) -> None:
    ds_df = pd.DataFrame(day_stats)
    n_days = len(ds_df)
    traded = ds_df[ds_df.direction != "flat"]
    agree = traded[(traded.direction == "up") == (traded.nifty_open_to_close > 0)]
    print(f"\nSessions: {n_days} · Nifty opening candle gave a direction on {len(traded)} ({len(traded) / n_days * 100:.0f}%), flat on {n_days - len(traded)}")
    if len(traded):
        print(f"Opening-candle direction matched the Nifty's full-day open-to-close direction on {len(agree)}/{len(traded)} days ({len(agree) / len(traded) * 100:.0f}%)")
    print(f"\nTrades per variant and exit rule (taken = entry triggered; win% = closed in profit before costs; net% = total % after {COST_PCT}% per trade)")
    print(f"{'variant':<9}{'exit':>10}{'signals':>8}{'taken':>6}{'win%':>6}{'tgt':>5}{'stop':>5}{'avgR':>7}{'totR':>7}{'avg%':>7}{'net%':>8}{'/day':>6}")
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["variant"], str(r["target"]))].append(r)
    order = {"evening": 0, "A": 1, "A-all": 2, "B": 3, "B-all": 4}
    for (variant, tgt), rs in sorted(groups.items(), key=lambda kv: (order.get(kv[0][0], 9), kv[0][1])):
        s = _stats(rs)
        label = tgt if tgt == "stop-only" else f"{float(tgt):.1f}R"
        print(f"{variant:<9}{label:>10}{s['signals']:>8}{s['taken']:>6}{s['win_pct']:>6.0f}{s['targets']:>5}{s['stops']:>5}{s['avg_r']:>7.2f}{s['total_r']:>7.1f}{s['avg_pct']:>7.2f}{s['net_pct']:>8.1f}{s['taken'] / max(n_days, 1):>6.1f}")
    print("\nVariant B, 1.5R, by side:")
    by_side: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["variant"] == "B" and str(r["target"]) == "1.5":
            by_side[r["side"]].append(r)
    for side, rs in by_side.items():
        s = _stats(rs)
        print(f"  {side:<6} taken {s['taken']:>3} win {s['win_pct']:.0f}% avg {s['avg_r']:+.2f}R total {s['total_r']:+.1f}R net {s['net_pct']:+.1f}%")
    print("\nCaveats: ~2 months of 5-minute data only; survivorship bias in the universe; costs approximated; "
          "no slippage on the entry break.")
