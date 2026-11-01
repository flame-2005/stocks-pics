import type { SupabaseClient } from "@supabase/supabase-js";
import type { Candidate, FiiDii, FocusVerdict, FunnelCounts, MarketContext, PickResult, SectorStrength, WatchlistRow } from "./types";

type Client = SupabaseClient;

export async function tradeDates(supabase: Client, limit = 120): Promise<string[]> {
  const { data } = await supabase
    .from("market_context")
    .select("trade_date")
    .order("trade_date", { ascending: false })
    .limit(limit);
  return (data ?? []).map((r) => r.trade_date as string);
}

export async function dayData(supabase: Client, date: string) {
  const [context, picks, sectors, candidates, features] = await Promise.all([
    supabase.from("market_context").select("*").eq("trade_date", date).maybeSingle(),
    supabase.from("pick_results").select("*").eq("trade_date", date).order("rank", { ascending: true }),
    supabase.from("sector_strength").select("*").eq("trade_date", date).order("rank", { ascending: true }),
    supabase.from("candidates").select("*").eq("trade_date", date).order("score", { ascending: false }),
    supabase.from("features").select("symbol,in_funnel,filter_fails").eq("trade_date", date),
  ]);

  const featureRows = (features.data ?? []) as { symbol: string; in_funnel: number; filter_fails: string[] | null }[];
  const candRows = (candidates.data ?? []) as Candidate[];
  const pickRows = ((picks.data ?? []) as PickResult[]).filter((p) => p.status !== "dropped");
  const funnel: FunnelCounts = {
    universe: featureRows.length,
    filtersPassed: featureRows.filter((f) => !f.filter_fails || f.filter_fails.length === 0).length,
    funnel: featureRows.filter((f) => f.in_funnel).length,
    withSetup: new Set(candRows.map((c) => c.symbol)).size,
    sectorOk: new Set(candRows.filter((c) => c.stage === "sector" || c.stage === "final").map((c) => c.symbol)).size,
    final: pickRows.length,
  };

  return {
    context: (context.data ?? null) as MarketContext | null,
    picks: pickRows,
    sectors: (sectors.data ?? []) as SectorStrength[],
    candidates: candRows,
    funnel,
  };
}

export async function historyData(supabase: Client, from: string | null) {
  let picksQuery = supabase.from("pick_results").select("*").order("trade_date", { ascending: true }).order("rank", { ascending: true });
  let ctxQuery = supabase.from("market_context").select("*").order("trade_date", { ascending: true });
  if (from) {
    picksQuery = picksQuery.gte("trade_date", from);
    ctxQuery = ctxQuery.gte("trade_date", from);
  }
  const [picks, contexts] = await Promise.all([picksQuery, ctxQuery]);
  return {
    picks: ((picks.data ?? []) as PickResult[]).filter((p) => p.status !== "dropped"),
    contexts: (contexts.data ?? []) as MarketContext[],
  };
}

export async function marketHistory(supabase: Client, limit = 90) {
  const [contexts, flows] = await Promise.all([
    supabase.from("market_context").select("*").order("trade_date", { ascending: false }).limit(limit),
    supabase.from("fii_dii").select("*").order("trade_date", { ascending: false }).limit(limit),
  ]);
  return {
    contexts: (contexts.data ?? []) as MarketContext[],
    flows: (flows.data ?? []) as FiiDii[],
  };
}

/** Aggregate confirmed-pick outcomes into hit rate and R statistics. */
export function summarize(picks: PickResult[]) {
  const confirmed = picks.filter((p) => p.status === "confirmed");
  const withR = confirmed.filter((p) => p.r_multiple !== null);
  const targets = confirmed.filter((p) => p.result === "target").length;
  const stops = confirmed.filter((p) => p.result === "stop").length;
  const totalR = withR.reduce((s, p) => s + (p.r_multiple ?? 0), 0);
  const totalPnl = withR.reduce((s, p) => s + (p.pnl ?? 0), 0);
  return {
    picks: picks.length,
    confirmed: confirmed.length,
    taken: withR.length,
    targets,
    stops,
    hitRate: targets + stops ? (targets / (targets + stops)) * 100 : null,
    avgR: withR.length ? totalR / withR.length : null,
    totalR,
    totalPnl,
    days: new Set(picks.map((p) => p.trade_date)).size,
  };
}

export function groupStats(picks: PickResult[], key: (p: PickResult) => string) {
  const groups = new Map<string, PickResult[]>();
  for (const p of picks) {
    const k = key(p) || "–";
    groups.set(k, [...(groups.get(k) ?? []), p]);
  }
  return [...groups.entries()]
    .map(([label, rows]) => ({ label, ...summarize(rows) }))
    .sort((a, b) => b.totalR - a.totalR);
}

export function cumulativeR(picks: PickResult[]) {
  const byDay = new Map<string, number>();
  for (const p of picks) {
    if (p.status !== "confirmed" || p.r_multiple === null) continue;
    byDay.set(p.trade_date, (byDay.get(p.trade_date) ?? 0) + p.r_multiple);
  }
  let running = 0;
  return [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, r]) => {
      running += r;
      return { date, dayR: r, cumR: running };
    });
}

export async function watchlistData(supabase: Client, month?: string | null) {
  const { data: monthRows } = await supabase.from("watchlist").select("month").order("month", { ascending: false });
  const months = [...new Set(((monthRows ?? []) as { month: string }[]).map((r) => r.month))];
  const target = month && months.includes(month) ? month : months[0];
  if (!target) return { month: null as string | null, months, indices: [] as WatchlistRow[], stocks: [] as WatchlistRow[] };
  const { data } = await supabase
    .from("watchlist")
    .select("*")
    .eq("month", target)
    .order("is_index", { ascending: false })
    .order("rank", { ascending: true });
  const rows = (data ?? []) as WatchlistRow[];
  return {
    month: target,
    months,
    indices: rows.filter((r) => r.is_index),
    stocks: rows.filter((r) => !r.is_index),
  };
}

export async function focusData(supabase: Client, date?: string | null) {
  const { data: dateRows } = await supabase.from("focus_verdicts").select("trade_date").order("trade_date", { ascending: false });
  const dates = [...new Set(((dateRows ?? []) as { trade_date: string }[]).map((r) => r.trade_date))];
  const current = date && dates.includes(date) ? date : dates[0] ?? null;
  if (!current) return { dates, current, rows: [] as FocusVerdict[] };
  const { data } = await supabase.from("focus_verdicts").select("*").eq("trade_date", current);
  const rows = ((data ?? []) as FocusVerdict[]).sort((a, b) => (a.symbol === "NIFTY" ? -1 : b.symbol === "NIFTY" ? 1 : a.symbol.localeCompare(b.symbol)));
  return { dates, current, rows };
}

export async function focusHistory(supabase: Client) {
  const { data } = await supabase.from("focus_verdicts").select("symbol,trade_date,verdict,result,r_multiple,pnl");
  const rows = (data ?? []) as Pick<FocusVerdict, "symbol" | "trade_date" | "verdict" | "result" | "r_multiple" | "pnl">[];
  const by = new Map<string, typeof rows>();
  for (const r of rows) by.set(r.symbol, [...(by.get(r.symbol) ?? []), r]);
  return [...by.entries()]
    .map(([symbol, list]) => {
      const trades = list.filter((r) => (r.verdict === "buy" || r.verdict === "sell") && r.result);
      const targets = trades.filter((r) => r.result === "target").length;
      const stops = trades.filter((r) => r.result === "stop").length;
      return {
        symbol,
        days: new Set(list.map((r) => r.trade_date)).size,
        trades: trades.length,
        targets,
        stops,
        hitRate: targets + stops ? (targets / (targets + stops)) * 100 : null,
        totalR: trades.reduce((s, r) => s + (r.r_multiple ?? 0), 0),
        pnl: trades.reduce((s, r) => s + (r.pnl ?? 0), 0),
      };
    })
    .sort((a, b) => (a.symbol === "NIFTY" ? -1 : b.symbol === "NIFTY" ? 1 : a.symbol.localeCompare(b.symbol)));
}
