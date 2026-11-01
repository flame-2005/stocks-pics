import { Badge } from "./Badge";
import { inr, pct, signed, title } from "@/lib/format";
import type { MarketContext } from "@/lib/types";

export function MoodCard({ context }: { context: MarketContext | null }) {
  if (!context) {
    return (
      <div className="card">
        <p className="muted text-sm">No run stored for this day.</p>
      </div>
    );
  }
  const comps = context.components_json ?? [];
  const reasons = context.reasons_json ?? [];
  return (
    <div className="card flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Badge value={context.mood} label={`${title(context.mood)} · score ${signed(context.score ?? 0, 0)}`} />
        {context.caution ? <Badge value="neutral" label="Caution: half size" /> : null}
        <span className="text-xs muted">
          {context.phase === "morning" ? "Final (09:10 run)" : "Provisional (evening run)"}
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
        <Item label="Nifty close" value={inr(context.nifty_close, 0)} sub={pct(context.nifty_chg_pct)} />
        <Item label="India VIX" value={context.vix === null ? "–" : context.vix.toFixed(1)} />
        <Item label="FII net" value={context.fii_net === null ? "–" : `${signed(context.fii_net, 0)} cr`} />
        <Item label="DII net" value={context.dii_net === null ? "–" : `${signed(context.dii_net, 0)} cr`} />
      </dl>
      {comps.length > 0 && (
        <ul className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          {comps.map((c) => (
            <li key={c.name} className="flex justify-between gap-3">
              <span className="secondary">{c.note}</span>
              <span className={`tabular ${c.points > 0 ? "delta-up" : c.points < 0 ? "delta-down" : "muted"}`}>
                {c.points ? signed(c.points, 0) : "0"}
              </span>
            </li>
          ))}
        </ul>
      )}
      {reasons.length > 0 && (
        <ul className="text-sm">
          {reasons.map((r) => (
            <li key={r} className="secondary">⚠ {r}</li>
          ))}
        </ul>
      )}
      {context.nifty_day_return !== null && (
        <p className="text-xs muted">Nifty actually closed {pct(context.nifty_day_return)} that day.</p>
      )}
    </div>
  );
}

function Item({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <dt className="text-xs muted">{label}</dt>
      <dd className="font-medium tabular">
        {value} {sub && <span className="text-xs secondary">{sub}</span>}
      </dd>
    </div>
  );
}
