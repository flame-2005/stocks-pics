"use client";

import { useState } from "react";
import { signed, title } from "@/lib/format";
import { useWidth } from "./useWidth";

export type GroupStat = {
  label: string;
  picks: number;
  confirmed: number;
  taken: number;
  targets: number;
  stops: number;
  hitRate: number | null;
  avgR: number | null;
  totalR: number;
};

const ROW = 30;
const BAR = 14;
const LABEL_W = 110;
const PAD_R = 120;

/** Horizontal bars of hit rate per group. One series, so one hue; the value sits at the bar tip. */
export function HitRateBars({ groups, caption }: { groups: GroupStat[]; caption: string }) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const rows = groups.filter((g) => g.taken > 0);
  if (rows.length === 0) return <p className="muted text-sm">No confirmed picks with outcomes yet.</p>;

  const plotW = Math.max(width - LABEL_W - PAD_R, 40);
  const height = rows.length * ROW + 8;
  const x = (v: number) => LABEL_W + (v / 100) * plotW;

  return (
    <div ref={ref} className="relative w-full min-w-0">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={caption} style={{ display: "block", width: "100%", height: "auto" }}>
        {[0, 25, 50, 75, 100].map((t) => (
          <line key={t} x1={x(t)} x2={x(t)} y1={0} y2={height - 8} stroke={t === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} />
        ))}
        {rows.map((g, i) => {
          const y = i * ROW + (ROW - BAR) / 2;
          const w = Math.max(x(g.hitRate ?? 0) - x(0), 0);
          return (
            <g
              key={g.label}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              tabIndex={0}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            >
              <rect x={0} y={i * ROW} width={width} height={ROW} fill="transparent" />
              <text x={LABEL_W - 10} y={y + BAR / 2} dy="0.35em" textAnchor="end" fontSize={12} fill="var(--text-secondary)">
                {title(g.label)}
              </text>
              <path
                d={roundedRight(x(0), y, w, BAR, 4)}
                fill="var(--series-1)"
                opacity={hover === null || hover === i ? 1 : 0.55}
              />
              <text x={x(0) + w + 8} y={y + BAR / 2} dy="0.35em" fontSize={12} fill="var(--text-primary)" className="tabular">
                {g.hitRate === null ? "–" : `${g.hitRate.toFixed(0)}%`}
                <tspan fill="var(--text-muted)"> · {g.targets}/{g.targets + g.stops} · {signed(g.avgR, 2, "R")}</tspan>
              </text>
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div className="viz-tooltip" style={{ left: LABEL_W, top: hover * ROW + ROW }}>
          <div className="muted">{title(rows[hover].label)}</div>
          <div><strong>{rows[hover].hitRate === null ? "–" : `${rows[hover].hitRate!.toFixed(0)}%`}</strong> hit rate</div>
          <div><strong>{rows[hover].targets}</strong> targets · <strong>{rows[hover].stops}</strong> stops · {rows[hover].taken} taken</div>
          <div><strong>{signed(rows[hover].avgR, 2, "R")}</strong> average · <strong>{signed(rows[hover].totalR, 1, "R")}</strong> total</div>
        </div>
      )}
      <details className="mt-2">
        <summary>Table view</summary>
        <table className="data mt-2">
          <thead>
            <tr>
              <th>Group</th>
              <th className="num">Picks</th>
              <th className="num">Taken</th>
              <th className="num">Targets</th>
              <th className="num">Stops</th>
              <th className="num">Hit rate</th>
              <th className="num">Avg R</th>
              <th className="num">Total R</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((g) => (
              <tr key={g.label}>
                <td>{title(g.label)}</td>
                <td className="num">{g.picks}</td>
                <td className="num">{g.taken}</td>
                <td className="num">{g.targets}</td>
                <td className="num">{g.stops}</td>
                <td className="num">{g.hitRate === null ? "–" : `${g.hitRate.toFixed(0)}%`}</td>
                <td className="num">{signed(g.avgR, 2)}</td>
                <td className="num">{signed(g.totalR, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function roundedRight(x: number, y: number, w: number, h: number, r: number): string {
  const rr = Math.min(r, w, h / 2);
  if (w <= 0) return "";
  return `M${x},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h - rr} Q${x + w},${y + h} ${x + w - rr},${y + h} H${x} Z`;
}
