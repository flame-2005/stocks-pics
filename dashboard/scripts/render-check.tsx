/**
 * Server-renders the chart components with sample data and fails if the SVG contains NaN or
 * is suspiciously small. Run from dashboard/:  npx tsx scripts/render-check.tsx
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CumulativeRChart } from "../src/components/CumulativeRChart";
import { HitRateBars } from "../src/components/HitRateBars";
import { SectorBars } from "../src/components/SectorBars";
import { MoodCard } from "../src/components/MoodCard";
import { PicksTable } from "../src/components/PicksTable";
import type { MarketContext, PickResult, SectorStrength } from "../src/lib/types";

const points = [
  { date: "2026-10-20", dayR: 0.5, cumR: 0.5 },
  { date: "2026-10-21", dayR: -1, cumR: -0.5 },
  { date: "2026-10-22", dayR: 2, cumR: 1.5 },
  { date: "2026-10-23", dayR: 0, cumR: 1.5 },
  { date: "2026-10-27", dayR: -1, cumR: 0.5 },
  { date: "2026-10-30", dayR: 0.49, cumR: 0.99 },
];

const groups = [
  { label: "breakout", picks: 9, confirmed: 6, taken: 5, targets: 2, stops: 2, hitRate: 50, avgR: 0.3, totalR: 1.5 },
  { label: "pattern", picks: 20, confirmed: 12, taken: 10, targets: 3, stops: 6, hitRate: 33.3, avgR: -0.2, totalR: -2 },
  { label: "mover", picks: 3, confirmed: 1, taken: 0, targets: 0, stops: 0, hitRate: null, avgR: null, totalR: 0 },
];

const sectors: SectorStrength[] = [
  { trade_date: "2026-10-30", sector: "Services", ret_1d: 1.2, ret_5d: 4.1, rs_1d: 0.7, rs_5d: 3.2, composite: 1.95, rank: 1, points_long: 2, points_short: 0, source: "constituents(2)", members: 2 },
  { trade_date: "2026-10-30", sector: "Information Technology", ret_1d: -0.4, ret_5d: -0.9, rs_1d: -0.9, rs_5d: -1.8, composite: -1.35, rank: 17, points_long: 0, points_short: 2, source: "^CNXIT", members: 6 },
  { trade_date: "2026-10-30", sector: "Power", ret_1d: 0.3, ret_5d: 2.8, rs_1d: -0.2, rs_5d: 1.9, composite: 0.85, rank: 2, points_long: 2, points_short: 0, source: "constituents(6)", members: 6 },
];

const context: MarketContext = {
  trade_date: "2026-10-30", phase: "morning", mood: "bullish", score: 3, caution: 0,
  nifty_close: 23053, nifty_ema20: 22800, nifty_ema50: 22500, nifty_chg_pct: 1.05, nifty_gap_pct: 0.2,
  vix: 15.3, fii_net: 3599, dii_net: -818, global_json: { "ES=F": -1.39 },
  components_json: [{ name: "nifty_trend", value: 23053, points: 1, note: "Nifty above EMA20, EMAs mixed" }],
  reasons_json: [], nifty_day_return: 0.51, updated_at: null,
};

const picks: PickResult[] = [
  {
    id: 1, trade_date: "2026-10-30", symbol: "KOTAKBANK", side: "long", rank: 1, entry: 460.25, stop: 454.1, target: 472.55, qty: 162,
    score: 6, setup_type: "breakout", sector: "Financial Services", status: "confirmed", flags_json: ["already moved +4.3% yesterday"],
    reasons_json: ["20-day breakout above 453.10 on 1.9x volume"], confirm_note: "above 15-min EMA200", result: "eod_close",
    entry_price: 460.25, exit_price: 461.15, r_multiple: 0.15, pnl: 146, mfe: 0.6, mae: -0.3, mood: "bullish", nifty_day_return: 0.51,
  },
];

const outputs: Record<string, string> = {
  CumulativeRChart: renderToStaticMarkup(<CumulativeRChart points={points} />),
  CumulativeRChartEmpty: renderToStaticMarkup(<CumulativeRChart points={[]} />),
  HitRateBars: renderToStaticMarkup(<HitRateBars groups={groups} caption="test" />),
  SectorBars: renderToStaticMarkup(<SectorBars sectors={sectors} />),
  MoodCard: renderToStaticMarkup(<MoodCard context={context} />),
  PicksTable: renderToStaticMarkup(<PicksTable picks={picks} />),
};

let failed = false;
for (const [name, html] of Object.entries(outputs)) {
  const nan = /NaN|undefined/.test(html);
  const tiny = html.length < 200 && !name.endsWith("Empty");
  const status = nan || tiny ? "FAIL" : "ok";
  if (status === "FAIL") failed = true;
  console.log(`[${status}] ${name}: ${html.length} chars${nan ? " (contains NaN/undefined)" : ""}`);
}
console.log(outputs.SectorBars.slice(0, 400));
process.exit(failed ? 1 : 0);
