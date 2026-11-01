import { title } from "@/lib/format";

const STATUS_TONE: Record<string, string> = {
  confirmed: "good",
  planned: "series",
  cancelled: "critical",
  dropped: "",
  target: "good",
  stop: "critical",
  eod_close: "series",
  no_entry: "",
  skipped: "",
  bullish: "good",
  bearish: "critical",
  neutral: "warning",
  no_trade: "serious",
  long: "series",
  short: "critical",
};

const ICON: Record<string, string> = {
  confirmed: "✓",
  planned: "•",
  cancelled: "✕",
  dropped: "–",
  target: "✓",
  stop: "✕",
  eod_close: "◦",
  no_entry: "–",
  skipped: "–",
  bullish: "▲",
  bearish: "▼",
  neutral: "◆",
  no_trade: "■",
  long: "▲",
  short: "▼",
};

/** Status badge: colour never carries meaning alone, the icon and label always ride along. */
export function Badge({ value, label }: { value: string | null | undefined; label?: string }) {
  const key = value ?? "";
  const tone = STATUS_TONE[key] ?? "";
  return (
    <span className={`badge ${tone}`} title={label ?? title(key)}>
      <span className="dot" aria-hidden />
      <span aria-hidden>{ICON[key] ?? "•"}</span>
      {label ?? title(key)}
    </span>
  );
}
