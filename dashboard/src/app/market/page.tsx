import { redirect } from "next/navigation";
import { Badge } from "@/components/Badge";
import { fmtDate, inr, pct, signed } from "@/lib/format";
import { marketHistory } from "@/lib/queries";
import { createClient } from "@/lib/supabase/server";

export default async function MarketPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { contexts, flows } = await marketHistory(supabase);
  const flowByDate = new Map(flows.map((f) => [f.trade_date, f]));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Market mood by day</h1>
      <section className="card overflow-x-auto">
        <table className="data">
          <thead>
            <tr>
              <th>Date</th>
              <th>Mood</th>
              <th className="num">Score</th>
              <th className="num">Nifty close</th>
              <th className="num">Prev day</th>
              <th className="num">Gap</th>
              <th className="num">Actual day</th>
              <th className="num">VIX</th>
              <th className="num">FII net</th>
              <th className="num">DII net</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {contexts.map((c) => (
              <tr key={c.trade_date}>
                <td className="whitespace-nowrap">{fmtDate(c.trade_date)}</td>
                <td><Badge value={c.mood} /></td>
                <td className="num">{signed(c.score ?? 0, 0)}</td>
                <td className="num">{inr(c.nifty_close, 0)}</td>
                <td className="num">{pct(c.nifty_chg_pct)}</td>
                <td className="num">{pct(c.nifty_gap_pct)}</td>
                <td className={`num ${(c.nifty_day_return ?? 0) > 0 ? "delta-up" : (c.nifty_day_return ?? 0) < 0 ? "delta-down" : ""}`}>{pct(c.nifty_day_return)}</td>
                <td className="num">{c.vix === null ? "–" : c.vix.toFixed(1)}</td>
                <td className="num">{signed(c.fii_net ?? flowByDate.get(c.trade_date)?.fii_net ?? null, 0)}</td>
                <td className="num">{signed(c.dii_net ?? flowByDate.get(c.trade_date)?.dii_net ?? null, 0)}</td>
                <td className="text-xs secondary">{(c.reasons_json ?? []).join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {contexts.length === 0 && <p className="muted text-sm">No runs stored yet.</p>}
      </section>
    </div>
  );
}
