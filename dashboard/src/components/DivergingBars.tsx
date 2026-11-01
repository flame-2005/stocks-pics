"use client";

import { useState } from "react";
import { signed } from "@/lib/format";
import { useWidth } from "./useWidth";

export type DivergingRow = {
  label: string;
  value: number | null;
  sub?: string;
  details?: string[];
};

const ROW = 24;
const BAR = 12;
const LABEL_W = 120;
const PAD_R = 70;

/** Generic diverging bars around zero: blue above, red below, gray midpoint, value at the tip. */
export function DivergingBars({ rows, caption, unit = "%" }: { rows: DivergingRow[]; caption: string; unit?: string }) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const data = rows.filter((r) => r.value !== null);
  if (data.length === 0) return <p className="muted text-sm">Nothing to show.</p>;

  const maxAbs = Math.max(1e-6, ...data.map((r) => Math.abs(r.value as number)));
  const plotW = Math.max(width - LABEL_W - PAD_R, 60);
  const mid = LABEL_W + plotW / 2;
  const scale = (v: number) => (v / maxAbs) * (plotW / 2);
  const height = data.length * ROW + 6;

  return (
    <div ref={ref} className="relative w-full min-w-0">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={caption} style={{ display: "block", width: "100%", height: "auto" }}>
        <line x1={mid} x2={mid} y1={0} y2={height - 6} stroke="var(--axis)" strokeWidth={1} />
        {data.map((r, i) => {
          const v = r.value as number;
          const y = i * ROW + (ROW - BAR) / 2;
          const len = Math.abs(scale(v));
          const x0 = v >= 0 ? mid + 1 : mid - 1 - len;
          return (
            <g
              key={r.label}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              tabIndex={0}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            >
              <rect x={0} y={i * ROW} width={width} height={ROW} fill="transparent" />
              <text x={LABEL_W - 10} y={y + BAR / 2} dy="0.35em" textAnchor="end" fontSize={12} fill="var(--text-secondary)">
                {r.label}
              </text>
              <rect
                x={x0}
                y={y}
                width={Math.max(len, 1)}
                height={BAR}
                rx={3}
                fill={v >= 0 ? "var(--diverge-pos)" : "var(--diverge-neg)"}
                opacity={hover === null || hover === i ? 1 : 0.55}
              />
              {(() => {
                const text = signed(v, 1, unit);
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
          <div className="muted">{data[hover].label}{data[hover].sub ? ` · ${data[hover].sub}` : ""}</div>
          <div><strong>{signed(data[hover].value, 2, unit)}</strong></div>
          {(data[hover].details ?? []).map((d) => <div key={d}>{d}</div>)}
        </div>
      )}
      <details className="mt-2">
        <summary>Table view</summary>
        <table className="data mt-2">
          <thead>
            <tr>
              <th>Item</th>
              <th className="num">Value</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.label}>
                <td>{r.label}{r.sub ? <span className="muted"> · {r.sub}</span> : null}</td>
                <td className="num">{signed(r.value, 2, unit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
