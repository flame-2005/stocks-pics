"use client";

import { useState } from "react";
import { signed } from "@/lib/format";
import type { SectorStrength } from "@/lib/types";
import { useWidth } from "./useWidth";

const ROW = 26;
const BAR = 12;
const LABEL_W = 150;
const PAD_R = 70;

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

/** Diverging bars: 5-day sector return relative to the Nifty. Blue above, red below, gray midpoint. */
export function SectorBars({ sectors }: { sectors: SectorStrength[] }) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const rows = [...sectors].sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99));
  if (rows.length === 0) return <p className="muted text-sm">No sector data for this day.</p>;

  const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r.rs_5d ?? 0)));
  const plotW = Math.max(width - LABEL_W - PAD_R, 60);
  const mid = LABEL_W + plotW / 2;
  const scale = (v: number) => (v / maxAbs) * (plotW / 2);
  const height = rows.length * ROW + 6;

  return (
    <div ref={ref} className="relative w-full min-w-0">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="Sector strength vs Nifty, 5 days" style={{ display: "block", width: "100%", height: "auto" }}>
        <line x1={mid} x2={mid} y1={0} y2={height - 6} stroke="var(--axis)" strokeWidth={1} />
        {rows.map((s, i) => {
          const v = s.rs_5d ?? 0;
          const y = i * ROW + (ROW - BAR) / 2;
          const len = Math.abs(scale(v));
          const x0 = v >= 0 ? mid + 1 : mid - 1 - len;
          const fill = v >= 0 ? "var(--diverge-pos)" : "var(--diverge-neg)";
          return (
            <g
              key={s.sector}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              tabIndex={0}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            >
              <rect x={0} y={i * ROW} width={width} height={ROW} fill="transparent" />
              <text x={LABEL_W - 10} y={y + BAR / 2} dy="0.35em" textAnchor="end" fontSize={12} fill="var(--text-secondary)">
                {SHORT[s.sector] ?? s.sector}
              </text>
              <rect x={x0} y={y} width={Math.max(len, 1)} height={BAR} rx={3} fill={fill} opacity={hover === null || hover === i ? 1 : 0.55} />
              {(() => {
                const text = signed(v, 1, "%");
                const labelW = text.length * 6.6 + 4;
                const outsideX = v >= 0 ? mid + len + 8 : mid - len - 8;
                const fitsInside = len >= labelW + 12;
                const fitsOutside = v >= 0 ? outsideX + labelW <= width : outsideX - labelW >= 0;
                if (!fitsInside && !fitsOutside) return null;
                const inside = fitsInside;
                return (
                  <text
                    x={inside ? (v >= 0 ? mid + len - 6 : mid - len + 6) : outsideX}
                    y={y + BAR / 2}
                    dy="0.35em"
                    textAnchor={(v >= 0) !== inside ? "start" : "end"}
                    fontSize={11}
                    fill={inside ? "#ffffff" : "var(--text-primary)"}
                    className="tabular"
                  >
                    {text}
                  </text>
                );
              })()}
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div className="viz-tooltip" style={{ left: LABEL_W, top: hover * ROW + ROW }}>
          <div className="muted">{rows[hover].sector} · rank {rows[hover].rank}</div>
          <div><strong>{signed(rows[hover].rs_5d, 2, "%")}</strong> vs Nifty, 5 days</div>
          <div><strong>{signed(rows[hover].rs_1d, 2, "%")}</strong> vs Nifty, 1 day</div>
          <div><strong>{signed(rows[hover].ret_5d, 2, "%")}</strong> absolute, 5 days</div>
          <div className="muted">source {rows[hover].source} · {rows[hover].members} stocks</div>
        </div>
      )}
      <details className="mt-2">
        <summary>Table view</summary>
        <table className="data mt-2">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Sector</th>
              <th className="num">1d</th>
              <th className="num">5d</th>
              <th className="num">vs Nifty 1d</th>
              <th className="num">vs Nifty 5d</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.sector}>
                <td className="num">{s.rank}</td>
                <td>{s.sector}</td>
                <td className="num">{signed(s.ret_1d, 2, "%")}</td>
                <td className="num">{signed(s.ret_5d, 2, "%")}</td>
                <td className="num">{signed(s.rs_1d, 2, "%")}</td>
                <td className="num">{signed(s.rs_5d, 2, "%")}</td>
                <td className="muted">{s.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
