import Link from "next/link";
import { redirect } from "next/navigation";
import { Badge } from "@/components/Badge";
import { DivergingBars } from "@/components/DivergingBars";
import { fmtDate, inr, pct, signed } from "@/lib/format";
import { watchlistData } from "@/lib/queries";
import { createClient } from "@/lib/supabase/server";
import type { WatchlistRow } from "@/lib/types";

const SHORT: Record<string, string> = {
  "Financial Services": "Financials",
  "Information Technology": "IT",
  "Automobile and Auto Components": "Auto",
  "Fast Moving Consumer Goods": "FMCG",
  "Oil Gas & Consumable Fuels": "Oil & Gas",
  "Metals & Mining": "Metals",
  "Construction Materials": "Cement",
  "Consumer Services": "Consumer Svcs",
  "Consumer Durables": "Durables",
  Telecommunication: "Telecom",
};

const TREND: Record<string, { badge: string; label: string }> = {
  bull: { badge: "bullish", label: "Uptrend" },
  bear: { badge: "bearish", label: "Downtrend" },
  mixed: { badge: "neutral", label: "Mixed" },
};

function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: "UTC" });
}

function rangeText(pos: number | null): string {
  if (pos === null) return "–";
  const p = Math.round(pos * 100);
  return p >= 80 ? `near high (${p}%)` : p <= 20 ? `near low (${p}%)` : `${p}% of range`;
}

function IndexCard({ row }: { row: WatchlistRow }) {
  const trend = TREND[row.regime ?? "mixed"] ?? TREND.mixed;
  return (
    <div className="card min-w-0 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs secondary">{row.symbol}</div>
        <Badge value={trend.badge} label={trend.label} />
      </div>
      <div className="text-2xl font-semibold leading-tight">{inr(row.close, 0)}</div>
      <dl className="grid grid-cols-3 gap-x-4 gap-y-1 text-xs">
        <Item label="1 week" value={pct(row.ret_1w)} good={(row.ret_1w ?? 0) > 0} />
        <Item label="1 month" value={pct(row.ret_1m)} good={(row.ret_1m ?? 0) > 0} />
        <Item label="3 months" value={pct(row.ret_3m)} good={(row.ret_3m ?? 0) > 0} />
        <Item label="Month range" value={`${inr(row.month_low, 0)} – ${inr(row.month_high, 0)}`} />
        <Item label="Position" value={rangeText(row.range_pos)} />
        <Item label={row.vix !== null ? "India VIX" : "ATR"} value={row.vix !== null ? row.vix.toFixed(1) : `${(row.atr_pct ?? 0).toFixed(1)}%`} />
      </dl>
    </div>
  );
}

function Item({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div>
      <dt className="muted">{label}</dt>
      <dd className={`font-medium tabular ${good === undefined ? "" : good ? "delta-up" : "delta-down"}`}>{value}</dd>
    </div>
  );
}

export default async function WatchlistPage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const params = await searchParams;
  const { month, months, indices, stocks } = await watchlistData(supabase, params.month);

  if (!month) {
    return (
      <div className="card">
        <h1 className="text-lg font-semibold">No watch universe yet</h1>
        <p className="secondary mt-2 text-sm">
          Run <code>python -m intraday_picks watchlist</code> on the laptop; it also builds itself on the first evening run of each month.
        </p>
      </div>
    );
  }

  const asOf = stocks[0]?.as_of ?? indices[0]?.as_of;
  const bars = [...stocks]
    .sort((a, b) => (b.ret_1m ?? 0) - (a.ret_1m ?? 0))
    .map((s) => ({
      label: s.symbol,
      value: s.ret_1m,
      sub: SHORT[s.industry ?? ""] ?? s.industry ?? "",
      details: [`1 week ${pct(s.ret_1w)}`, `3 months ${pct(s.ret_3m)}`, `vs 50-day average ${pct(s.pct_from_sma50)}`],
    }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Watch universe · {monthLabel(month)}</h1>
          <p className="secondary text-sm">
            The 30 most liquid names across sectors, chosen from the month before (data up to {fmtDate(asOf)}), plus the indices.
            This is the pool the daily funnel draws from.
          </p>
        </div>
        {months.length > 1 && (
          <div className="flex flex-wrap gap-1">
            {months.map((m) => (
              <Link key={m} href={`/watchlist?month=${m}`} className="nav-link" aria-current={m === month ? "page" : undefined}>
                {monthLabel(m)}
              </Link>
            ))}
          </div>
        )}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {indices.map((row) => <IndexCard key={row.symbol} row={row} />)}
      </div>

      <section className="card">
        <h2 className="mb-1 text-base font-semibold">Last month&apos;s move, by stock</h2>
        <p className="muted mb-3 text-xs">Close-to-close return over the last 21 sessions.</p>
        <DivergingBars rows={bars} caption="One-month return by stock" />
      </section>

      <section className="card overflow-x-auto">
        <h2 className="mb-3 text-base font-semibold">The 30</h2>
        <table className="data">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Stock</th>
              <th>Sector</th>
              <th className="num">Close</th>
              <th className="num">1w</th>
              <th className="num">1m</th>
              <th className="num">3m</th>
              <th>Trend</th>
              <th className="num">ATR</th>
              <th className="num">Turnover (₹ cr/day)</th>
              <th className="num">vs 50 DMA</th>
              <th>Month range</th>
              <th className="num">Picks last month</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((s) => {
              const trend = TREND[s.regime ?? "mixed"] ?? TREND.mixed;
              return (
                <tr key={s.symbol}>
                  <td className="num">{s.rank}</td>
                  <td>
                    <div className="font-semibold">{s.symbol}</div>
                    <div className="text-xs muted">{s.name}</div>
                  </td>
                  <td>{SHORT[s.industry ?? ""] ?? s.industry}</td>
                  <td className="num">{inr(s.close)}</td>
                  <td className={`num ${(s.ret_1w ?? 0) > 0 ? "delta-up" : (s.ret_1w ?? 0) < 0 ? "delta-down" : ""}`}>{pct(s.ret_1w, 1)}</td>
                  <td className={`num ${(s.ret_1m ?? 0) > 0 ? "delta-up" : (s.ret_1m ?? 0) < 0 ? "delta-down" : ""}`}>{pct(s.ret_1m, 1)}</td>
                  <td className={`num ${(s.ret_3m ?? 0) > 0 ? "delta-up" : (s.ret_3m ?? 0) < 0 ? "delta-down" : ""}`}>{pct(s.ret_3m, 1)}</td>
                  <td><Badge value={trend.badge} label={trend.label} /></td>
                  <td className="num">{s.atr_pct === null ? "–" : `${s.atr_pct.toFixed(1)}%`}</td>
                  <td className="num">{inr(s.med_turnover_cr, 0)}</td>
                  <td className="num">{pct(s.pct_from_sma50, 1)}</td>
                  <td className="text-xs">{rangeText(s.range_pos)}</td>
                  <td className="num">
                    {s.picks_last_month ? `${s.picks_last_month} · ${signed(s.r_last_month, 1, "R")}` : "–"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
