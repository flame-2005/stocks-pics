"use client";

import { useMemo, useState } from "react";
import { fmtDate, signed } from "@/lib/format";
import { useWidth } from "./useWidth";

type Point = { date: string; dayR: number; cumR: number };

const PAD = { top: 16, right: 56, bottom: 28, left: 40 };
const HEIGHT = 220;

/** Single-series line (cumulative R by day) with crosshair + tooltip and a table twin. */
export function CumulativeRChart({ points }: { points: Point[] }) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const geom = useMemo(() => {
    const w = Math.max(width - PAD.left - PAD.right, 10);
    const h = HEIGHT - PAD.top - PAD.bottom;
    const ys = points.map((p) => p.cumR);
    const lo = Math.min(0, ...ys);
    const hi = Math.max(0, ...ys);
    const span = hi - lo || 1;
    const niceStep = pickStep(span);
    const yMin = Math.floor(lo / niceStep) * niceStep;
    const yMax = Math.ceil(hi / niceStep) * niceStep || niceStep;
    const x = (i: number) => PAD.left + (points.length > 1 ? (i / (points.length - 1)) * w : w / 2);
    const y = (v: number) => PAD.top + h - ((v - yMin) / (yMax - yMin || 1)) * h;
    const ticks: number[] = [];
    for (let t = yMin; t <= yMax + 1e-9; t += niceStep) ticks.push(Number(t.toFixed(6)));
    return { w, h, x, y, ticks, yMin, yMax };
  }, [points, width]);

  if (points.length === 0) {
    return <p className="muted text-sm">No confirmed picks with outcomes yet.</p>;
  }

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${geom.x(i).toFixed(1)},${geom.y(p.cumR).toFixed(1)}`).join(" ");
  const area = `${path} L${geom.x(points.length - 1).toFixed(1)},${geom.y(0).toFixed(1)} L${geom.x(0).toFixed(1)},${geom.y(0).toFixed(1)} Z`;
  const last = points[points.length - 1];
  const hovered = hover !== null ? points[hover] : null;

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    let best = 0;
    let bestDist = Infinity;
    points.forEach((_, i) => {
      const d = Math.abs(geom.x(i) - px);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    setHover(best);
  };

  return (
    <div ref={ref} className="relative w-full min-w-0">
      <svg viewBox={`0 0 ${width} ${HEIGHT}`} width="100%"
        role="img"
        aria-label="Cumulative R over time"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        style={{ display: "block", width: "100%", height: "auto", touchAction: "none" }}
      >
        {geom.ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={PAD.left + geom.w} y1={geom.y(t)} y2={geom.y(t)} stroke={t === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} />
            <text x={PAD.left - 8} y={geom.y(t)} dy="0.35em" textAnchor="end" fontSize={11} fill="var(--text-muted)" className="tabular">
              {signed(t, 1)}
            </text>
          </g>
        ))}
        <path d={area} fill="var(--series-1-wash)" />
        <path d={path} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {hovered && hover !== null && (
          <>
            <line x1={geom.x(hover)} x2={geom.x(hover)} y1={PAD.top} y2={PAD.top + geom.h} stroke="var(--axis)" strokeWidth={1} />
            <circle cx={geom.x(hover)} cy={geom.y(hovered.cumR)} r={6} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
          </>
        )}
        <circle cx={geom.x(points.length - 1)} cy={geom.y(last.cumR)} r={4} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
        <text x={geom.x(points.length - 1) + 8} y={geom.y(last.cumR)} dy="0.35em" fontSize={12} fontWeight={600} fill="var(--text-primary)" className="tabular">
          {signed(last.cumR, 1, "R")}
        </text>
        <text x={PAD.left} y={HEIGHT - 8} fontSize={11} fill="var(--text-muted)">
          {fmtDate(points[0].date, { weekday: undefined })}
        </text>
        <text x={PAD.left + geom.w} y={HEIGHT - 8} fontSize={11} fill="var(--text-muted)" textAnchor="end">
          {fmtDate(last.date, { weekday: undefined })}
        </text>
      </svg>
      {hovered && hover !== null && (
        <div
          className="viz-tooltip"
          style={{ left: Math.min(geom.x(hover) + 12, width - 160), top: PAD.top }}
        >
          <div className="muted">{fmtDate(hovered.date)}</div>
          <div>
            <strong>{signed(hovered.cumR, 2, "R")}</strong> cumulative
          </div>
          <div>
            <strong>{signed(hovered.dayR, 2, "R")}</strong> that day
          </div>
        </div>
      )}
      <details className="mt-2">
        <summary>Table view</summary>
        <table className="data mt-2">
          <thead>
            <tr>
              <th>Date</th>
              <th className="num">Day R</th>
              <th className="num">Cumulative R</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.date}>
                <td>{fmtDate(p.date)}</td>
                <td className="num">{signed(p.dayR, 2)}</td>
                <td className="num">{signed(p.cumR, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function pickStep(span: number): number {
  const raw = span / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const norm = raw / mag;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return step * mag;
}
