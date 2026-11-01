/** Formatting helpers. Indian digit grouping for rupees, signed percentages, compact dates. */

export function inr(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function rupees(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return "–";
  return `₹${inr(value, decimals)}`;
}

export function pct(value: number | null | undefined, decimals = 2, sign = true): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const text = `${Math.abs(value).toFixed(decimals)}%`;
  if (!sign) return text;
  return value > 0 ? `+${text}` : value < 0 ? `−${text}` : text;
}

export function signed(value: number | null | undefined, decimals = 2, suffix = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const text = `${Math.abs(value).toFixed(decimals)}${suffix}`;
  return value > 0 ? `+${text}` : value < 0 ? `−${text}` : text;
}

export function fmtDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = {}): string {
  if (!iso) return "–";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00+05:30`);
  return d.toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short", year: "numeric", timeZone: "Asia/Kolkata", ...opts });
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
}

export function title(text: string | null | undefined): string {
  if (!text) return "–";
  return text.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function todayIst(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}
