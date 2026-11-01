import Link from "next/link";
import { redirect } from "next/navigation";
import { CumulativeRChart } from "@/components/CumulativeRChart";
import { HitRateBars } from "@/components/HitRateBars";
import { PicksTable } from "@/components/PicksTable";
import { StatTile } from "@/components/StatTile";
import { rupees, shiftDate, signed, todayIst } from "@/lib/format";
import { cumulativeR, groupStats, historyData, summarize } from "@/lib/queries";
import { createClient } from "@/lib/supabase/server";

const RANGES: { key: string; label: string; days: number | null }[] = [
  { key: "30", label: "Last 30 days", days: 30 },
  { key: "90", label: "Last 90 days", days: 90 },
  { key: "180", label: "Last 6 months", days: 180 },
  { key: "all", label: "All time", days: null },
];

export default async function HistoryPage({ searchParams }: { searchParams: Promise<{ range?: string }> }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const params = await searchParams;
  const range = RANGES.find((r) => r.key === params.range) ?? RANGES[1];
  const from = range.days ? shiftDate(todayIst(), -range.days) : null;
  const { picks } = await historyData(supabase, from);
  const stats = summarize(picks);
  const series = cumulativeR(picks);
  const confirmed = picks.filter((p) => p.status === "confirmed");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-4 text-2xl font-semibold">History</h1>
        {RANGES.map((r) => (
          <Link key={r.key} href={`/history?range=${r.key}`} className="nav-link" aria-current={r.key === range.key ? "page" : undefined}>
            {r.label}
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatTile label="Trading days" value={String(stats.days)} hint={`${stats.picks} picks sent`} />
        <StatTile label="Confirmed picks" value={String(stats.confirmed)} hint={`${stats.taken} triggered`} />
        <StatTile
          label="Hit rate"
          value={stats.hitRate === null ? "–" : `${stats.hitRate.toFixed(0)}%`}
          hint={`${stats.targets} targets · ${stats.stops} stops`}
        />
        <StatTile label="Average R" value={signed(stats.avgR, 2, "R")} deltaGood={stats.avgR === null ? null : stats.avgR > 0} delta={stats.avgR === null ? undefined : signed(stats.totalR, 1, "R total")} />
        <StatTile label="Paper P&L" value={rupees(stats.totalPnl, 0)} deltaGood={stats.totalPnl > 0} delta={`at the configured capital`} />
      </div>

      <section className="card">
        <h2 className="mb-1 text-base font-semibold">Cumulative R, confirmed picks</h2>
        <p className="muted mb-3 text-xs">One R is the distance from entry to stop. Only picks confirmed at 09:34 count.</p>
        <CumulativeRChart points={series} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card min-w-0">
          <h2 className="mb-1 text-base font-semibold">Hit rate by setup</h2>
          <p className="muted mb-3 text-xs">Which part of the playbook is paying.</p>
          <HitRateBars caption="Hit rate by setup" groups={groupStats(confirmed, (p) => p.setup_type ?? "–")} />
        </section>
        <section className="card min-w-0">
          <h2 className="mb-1 text-base font-semibold">Hit rate by market mood</h2>
          <p className="muted mb-3 text-xs">Whether the mood gate is helping.</p>
          <HitRateBars caption="Hit rate by market mood" groups={groupStats(confirmed, (p) => p.mood ?? "–")} />
        </section>
        <section className="card min-w-0">
          <h2 className="mb-1 text-base font-semibold">Hit rate by side</h2>
          <HitRateBars caption="Hit rate by side" groups={groupStats(confirmed, (p) => p.side)} />
        </section>
        <section className="card min-w-0">
          <h2 className="mb-1 text-base font-semibold">Hit rate by sector</h2>
          <HitRateBars caption="Hit rate by sector" groups={groupStats(confirmed, (p) => p.sector ?? "–")} />
        </section>
      </div>

      <section className="card">
        <h2 className="mb-3 text-base font-semibold">Every pick</h2>
        <PicksTable picks={[...picks].reverse()} showDate />
      </section>
    </div>
  );
}
