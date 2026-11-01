import Link from "next/link";
import { fmtDate } from "@/lib/format";

export function DateNav({ dates, current, basePath = "/" }: { dates: string[]; current: string; basePath?: string }) {
  const idx = dates.indexOf(current);
  const newer = idx > 0 ? dates[idx - 1] : null;
  const older = idx >= 0 && idx < dates.length - 1 ? dates[idx + 1] : null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {older ? <Link className="btn" href={`${basePath}?date=${older}`}>← {fmtDate(older, { weekday: undefined, year: undefined })}</Link> : <span className="btn" aria-disabled>←</span>}
      <form action={basePath} className="flex items-center gap-2">
        <select name="date" defaultValue={current} className="input" style={{ width: "auto" }}>
          {dates.map((d) => (
            <option key={d} value={d}>{fmtDate(d)}</option>
          ))}
        </select>
        <button className="btn" type="submit">Go</button>
      </form>
      {newer ? <Link className="btn" href={`${basePath}?date=${newer}`}>{fmtDate(newer, { weekday: undefined, year: undefined })} →</Link> : <span className="btn" aria-disabled>→</span>}
    </div>
  );
}
