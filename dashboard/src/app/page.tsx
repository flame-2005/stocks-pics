import Link from "next/link";
import { redirect } from "next/navigation";
import { DateNav } from "@/components/DateNav";
import { MoodCard } from "@/components/MoodCard";
import { PicksTable } from "@/components/PicksTable";
import { SectorBars } from "@/components/SectorBars";
import { Badge } from "@/components/Badge";
import { fmtDate, title, title as title_ } from "@/lib/format";
import type { Candidate } from "@/lib/types";
import { dayData, tradeDates } from "@/lib/queries";
import { createClient } from "@/lib/supabase/server";

export default async function TodayPage({ searchParams }: { searchParams: Promise<{ date?: string; view?: string }> }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const dates = await tradeDates(supabase);
  const params = await searchParams;
  const current = params.date && dates.includes(params.date) ? params.date : dates[0];

  if (!current) {
    return (
      <div className="card">
        <h1 className="text-lg font-semibold">No data yet</h1>
        <p className="secondary mt-2 text-sm">
          Run <code>python -m intraday_picks prep</code> on the laptop with Supabase configured; the first sync fills this page.
        </p>
      </div>
    );
  }

  const day = await dayData(supabase, current);
  const f = day.funnel;
  const finals = day.candidates.filter((c) => c.stage === "final");
  const buyCandidates = finals.filter((c) => c.side === "long");
  const sellCandidates = finals.filter((c) => c.side === "short");
  const defaultView = day.picks.length === 0 && finals.length > 0 ? "candidates" : "picks";
  const view = params.view === "candidates" || params.view === "picks" ? params.view : defaultView;
  const qs = (v: string) => `/?date=${current}&view=${v}`;
  const shortlist = day.candidates.filter((c) => c.stage !== "final").slice(0, 12);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{fmtDate(current)}</h1>
          <p className="secondary text-sm">
            Funnel: {f.universe} → {f.filtersPassed} pass filters → {f.funnel} liquid → {f.withSetup} with setup → {f.sectorOk} in ok sectors → <strong>{f.final} picks</strong>
          </p>
        </div>
        <DateNav dates={dates} current={current} />
      </div>

      <MoodCard context={day.context} />

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs secondary">Show:</span>
        <Link href={qs("picks")} className="nav-link" aria-current={view === "picks" ? "page" : undefined}>
          Picks ({day.picks.length})
        </Link>
        <Link href={qs("candidates")} className="nav-link" aria-current={view === "candidates" ? "page" : undefined}>
          Candidates for 09:34 ({finals.length})
        </Link>
      </div>

      {view === "candidates" ? (
        <section className="card">
          <h2 className="mb-1 text-base font-semibold">Candidates for the 09:34 decision</h2>
          <p className="muted mb-3 text-xs">
            The side is chosen at 09:34 from the Nifty&apos;s opening 15-minute candle. Only the candidates on that side are checked
            against their own opening candle, and the ones that confirm become the picks shown here with entry, stop and target.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <CandidateList title="If the Nifty opens up → BUY" rows={buyCandidates} side="long" />
            <CandidateList title="If the Nifty opens down → SELL" rows={sellCandidates} side="short" />
          </div>
        </section>
      ) : (
        <section className="card">
          <h2 className="mb-1 text-base font-semibold">Picks</h2>
          {day.picks.length === 0 && finals.length > 0 && (
            <p className="muted mb-3 text-xs">No picks yet for this day: the side is decided at 09:34. See the candidates view.</p>
          )}
          <PicksTable picks={day.picks} />
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card min-w-0">
          <h2 className="mb-1 text-base font-semibold">Sector strength vs Nifty</h2>
          <p className="muted mb-3 text-xs">5-day return relative to the Nifty. Top three sectors score 2 for longs, bottom three score 2 for shorts.</p>
          <SectorBars sectors={day.sectors} />
        </section>
        <section className="card min-w-0">
          <h2 className="mb-1 text-base font-semibold">Shortlist</h2>
          <p className="muted mb-3 text-xs">Stocks with a setup that did not make the final cut.</p>
          {shortlist.length === 0 ? (
            <p className="muted text-sm">Nothing beyond the picks.</p>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Side</th>
                  <th>Setup</th>
                  <th className="num">Score</th>
                  <th>Stage</th>
                </tr>
              </thead>
              <tbody>
                {shortlist.map((c) => (
                  <tr key={`${c.symbol}-${c.side}`}>
                    <td>
                      <div className="font-medium">{c.symbol}</div>
                      <div className="text-xs muted">{c.setup_label}</div>
                    </td>
                    <td><Badge value={c.side} label={c.side === "long" ? "Buy" : "Sell"} /></td>
                    <td>{title(c.setup_type)}</td>
                    <td className="num">{c.score}</td>
                    <td className="muted">{c.stage === "sector" ? "sector ok" : "weak sector"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}

function CandidateList({ title, rows, side }: { title: string; rows: Candidate[]; side: "long" | "short" }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      {rows.length === 0 ? (
        <p className="muted text-sm">None with a setup.</p>
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th>Stock</th>
              <th>Setup</th>
              <th className="num">Score</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={`${c.symbol}-${c.side}`}>
                <td>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{c.symbol}</span>
                    <Badge value={side} label={side === "long" ? "Buy" : "Sell"} />
                  </div>
                  <div className="text-xs muted">{c.sector}</div>
                </td>
                <td>
                  <div>{title_(c.setup_type)}</div>
                  <div className="text-xs muted">{c.setup_label}</div>
                </td>
                <td className="num">{c.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
