import { Badge } from "./Badge";
import { inr, rupees, signed, title } from "@/lib/format";
import type { PickResult } from "@/lib/types";

export function PicksTable({ picks, showDate = false }: { picks: PickResult[]; showDate?: boolean }) {
  if (picks.length === 0) return <p className="muted text-sm">No picks.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="data">
        <thead>
          <tr>
            {showDate && <th>Date</th>}
            <th>#</th>
            <th>Stock</th>
            <th>Side</th>
            <th>Setup</th>
            <th className="num">Entry</th>
            <th className="num">Stop</th>
            <th className="num">Target</th>
            <th className="num">Qty</th>
            <th className="num">Score</th>
            <th>Status</th>
            <th>Outcome</th>
            <th className="num">R</th>
            <th className="num">P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {picks.map((p) => (
            <tr key={p.id}>
              {showDate && <td className="whitespace-nowrap">{p.trade_date}</td>}
              <td className="num">{p.rank}</td>
              <td>
                <div className="font-semibold">{p.symbol}</div>
                <div className="text-xs muted">{p.sector}</div>
                {(p.reasons_json?.length || p.flags_json?.length || p.confirm_note) && (
                  <details>
                    <summary>why</summary>
                    <ul className="mt-1 text-xs secondary">
                      {(p.reasons_json ?? []).map((r) => <li key={r}>• {r}</li>)}
                      {(p.flags_json ?? []).map((f) => <li key={f}>⚠ {f}</li>)}
                      {p.confirm_note && <li>09:34: {p.confirm_note}</li>}
                    </ul>
                  </details>
                )}
              </td>
              <td><Badge value={p.side} label={p.side === "long" ? "Buy" : "Sell"} /></td>
              <td>{title(p.setup_type)}</td>
              <td className="num">{inr(p.entry)}</td>
              <td className="num">{inr(p.stop)}</td>
              <td className="num">{inr(p.target)}</td>
              <td className="num">{p.qty}</td>
              <td className="num">{p.score}</td>
              <td><Badge value={p.status} /></td>
              <td>{p.result ? <Badge value={p.result} /> : <span className="muted">–</span>}</td>
              <td className={`num ${(p.r_multiple ?? 0) > 0 ? "delta-up" : (p.r_multiple ?? 0) < 0 ? "delta-down" : ""}`}>{signed(p.r_multiple, 2)}</td>
              <td className="num">{p.pnl === null ? "–" : rupees(p.pnl, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
