import { redirect } from "next/navigation";
import { Badge } from "@/components/Badge";
import { DateNav } from "@/components/DateNav";
import { fmtDate, inr, rupees, signed, title } from "@/lib/format";
import { focusData, focusHistory } from "@/lib/queries";
import { createClient } from "@/lib/supabase/server";
import type { FocusVerdict } from "@/lib/types";

const VERDICT_BADGE: Record<string, { badge: string; label: string }> = {
  buy: { badge: "long", label: "BUY" },
  sell: { badge: "short", label: "SELL" },
  lean_buy: { badge: "long", label: "lean BUY" },
  lean_sell: { badge: "short", label: "lean SELL" },
  no: { badge: "dropped", label: "NO" },
};

function VerdictBadge({ v }: { v: FocusVerdict }) {
  const b = VERDICT_BADGE[v.verdict ?? "no"] ?? VERDICT_BADGE.no;
  return <Badge value={b.badge} label={b.label + (v.strength ? ` · ${v.strength}` : "")} />;
}

export default async function FocusPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const params = await searchParams;
  const { dates, current, rows } = await focusData(supabase, params.date);
  const history = await focusHistory(supabase);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Your list</h1>
          <p className="secondary text-sm">
            The Nifty (traded through NIFTYBEES) and the companies in <code>focus_list.txt</code> on the laptop. Each gets a lean
            in the evening and a firm BUY / SELL / NO at 09:34, with entry, stop and target when it is a trade.
          </p>
        </div>
        {current && <DateNav dates={dates} current={current} basePath="/focus" />}
      </div>

      {!current ? (
        <div className="card">
          <p className="muted text-sm">No verdicts stored yet. They appear after the next evening run.</p>
        </div>
      ) : (
        <section className="card">
          <h2 className="mb-1 text-base font-semibold">{fmtDate(current)}</h2>
          <p className="muted mb-3 text-xs">
            {rows.some((r) => r.phase === "orb") ? "Firm 09:34 verdicts." : "Evening lean; the firm verdict comes at 09:34."}
          </p>
          <div className="overflow-x-auto">
            <table className="data">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Verdict</th>
                  <th className="num">Entry</th>
                  <th className="num">Stop</th>
                  <th className="num">Target</th>
                  <th className="num">Qty</th>
                  <th>Why</th>
                  <th>Result</th>
                  <th className="num">R</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((v) => (
                  <tr key={v.symbol}>
                    <td>
                      <div className="font-semibold">{v.symbol}</div>
                      <div className="text-xs muted">
                        {v.symbol === "NIFTY" ? "via NIFTYBEES" : v.setup_label || title(v.regime)}
                        {v.close !== null && ` · close ${inr(v.close)}`}
                      </div>
                    </td>
                    <td><VerdictBadge v={v} /></td>
                    <td className="num">{v.entry === null ? "–" : inr(v.entry)}</td>
                    <td className="num">{v.stop === null ? "–" : inr(v.stop)}</td>
                    <td className="num">{v.target === null ? "–" : inr(v.target)}</td>
                    <td className="num">{v.qty ?? "–"}</td>
                    <td className="text-xs">
                      {(v.reasons_json ?? []).map((r) => <div key={r}>• {r}</div>)}
                      {(v.flags_json ?? []).map((f) => <div key={f} className="secondary">⚠ {f}</div>)}
                      {v.note && <div className="muted">ℹ {v.note}</div>}
                    </td>
                    <td>{v.result ? <Badge value={v.result} /> : <span className="muted">–</span>}</td>
                    <td className={`num ${(v.r_multiple ?? 0) > 0 ? "delta-up" : (v.r_multiple ?? 0) < 0 ? "delta-down" : ""}`}>
                      {signed(v.r_multiple, 2)}
                      {v.pnl !== null && v.pnl !== undefined && <div className="text-xs muted">{rupees(v.pnl, 0)}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card">
        <h2 className="mb-1 text-base font-semibold">Record per symbol</h2>
        <p className="muted mb-3 text-xs">Only firm BUY / SELL verdicts count; a NO is a decision too, but it has no result.</p>
        {history.length === 0 ? (
          <p className="muted text-sm">No results yet.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="num">Days</th>
                <th className="num">Trades</th>
                <th className="num">Targets</th>
                <th className="num">Stops</th>
                <th className="num">Hit rate</th>
                <th className="num">Total R</th>
                <th className="num">Paper P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.symbol}>
                  <td className="font-semibold">{h.symbol}</td>
                  <td className="num">{h.days}</td>
                  <td className="num">{h.trades}</td>
                  <td className="num">{h.targets}</td>
                  <td className="num">{h.stops}</td>
                  <td className="num">{h.hitRate === null ? "–" : `${h.hitRate.toFixed(0)}%`}</td>
                  <td className={`num ${h.totalR > 0 ? "delta-up" : h.totalR < 0 ? "delta-down" : ""}`}>{signed(h.totalR, 2)}</td>
                  <td className="num">{rupees(h.pnl, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
