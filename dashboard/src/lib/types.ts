export type MoodComponent = { name: string; value: number | null; points: number; note: string };

export type MarketContext = {
  trade_date: string;
  phase: string | null;
  mood: "bullish" | "bearish" | "neutral" | "no_trade" | null;
  score: number | null;
  caution: number | null;
  nifty_close: number | null;
  nifty_ema20: number | null;
  nifty_ema50: number | null;
  nifty_chg_pct: number | null;
  nifty_gap_pct: number | null;
  vix: number | null;
  fii_net: number | null;
  dii_net: number | null;
  global_json: Record<string, number> | null;
  components_json: MoodComponent[] | null;
  reasons_json: string[] | null;
  nifty_day_return: number | null;
  updated_at: string | null;
};

export type PickResult = {
  id: number;
  trade_date: string;
  symbol: string;
  side: "long" | "short";
  rank: number | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
  qty: number | null;
  score: number | null;
  setup_type: string | null;
  sector: string | null;
  status: "planned" | "confirmed" | "cancelled" | "dropped" | string;
  flags_json: string[] | null;
  reasons_json: string[] | null;
  confirm_note: string | null;
  result: "target" | "stop" | "eod_close" | "no_entry" | "skipped" | null;
  entry_price: number | null;
  exit_price: number | null;
  r_multiple: number | null;
  pnl: number | null;
  mfe: number | null;
  mae: number | null;
  mood: string | null;
  nifty_day_return: number | null;
};

export type SectorStrength = {
  trade_date: string;
  sector: string;
  ret_1d: number | null;
  ret_5d: number | null;
  rs_1d: number | null;
  rs_5d: number | null;
  composite: number | null;
  rank: number | null;
  points_long: number | null;
  points_short: number | null;
  source: string | null;
  members: number | null;
};

export type Candidate = {
  trade_date: string;
  symbol: string;
  side: "long" | "short";
  phase: string | null;
  stage: "setup" | "sector" | "final" | string | null;
  score: number | null;
  setup_type: string | null;
  setup_label: string | null;
  sector: string | null;
  sector_points: number | null;
  components_json: Record<string, number> | null;
  reasons_json: string[] | null;
  flags_json: string[] | null;
};

export type FunnelCounts = {
  universe: number;
  filtersPassed: number;
  funnel: number;
  withSetup: number;
  sectorOk: number;
  final: number;
};

export type FiiDii = {
  trade_date: string;
  fii_buy: number | null;
  fii_sell: number | null;
  fii_net: number | null;
  dii_buy: number | null;
  dii_sell: number | null;
  dii_net: number | null;
  source: string | null;
};

export type WatchlistRow = {
  month: string;
  as_of: string;
  symbol: string;
  name: string | null;
  industry: string | null;
  rank: number | null;
  is_index: number | null;
  close: number | null;
  ret_1w: number | null;
  ret_1m: number | null;
  ret_3m: number | null;
  month_high: number | null;
  month_low: number | null;
  range_pos: number | null;
  atr_pct: number | null;
  med_turnover_cr: number | null;
  avg_volume: number | null;
  sma50: number | null;
  sma200: number | null;
  pct_from_sma50: number | null;
  pct_from_sma200: number | null;
  regime: string | null;
  picks_last_month: number | null;
  r_last_month: number | null;
  vix: number | null;
};

export type FocusVerdict = {
  trade_date: string;
  symbol: string;
  instrument: string | null;
  phase: string | null;
  verdict: "lean_buy" | "lean_sell" | "buy" | "sell" | "no" | string | null;
  strength: string | null;
  side: "long" | "short" | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
  qty: number | null;
  stop_pct: number | null;
  score_long: number | null;
  score_short: number | null;
  regime: string | null;
  setup_type: string | null;
  setup_label: string | null;
  close: number | null;
  reasons_json: string[] | null;
  flags_json: string[] | null;
  note: string | null;
  result: string | null;
  entry_price: number | null;
  exit_price: number | null;
  r_multiple: number | null;
  pnl: number | null;
  updated_at: string | null;
};
