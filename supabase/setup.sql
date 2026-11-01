-- Intraday Picks: run this whole file once in Supabase -> SQL editor. Safe to re-run.

-- Intraday Picks: mirror of the laptop's SQLite tables, read by the Next.js dashboard.
-- Run once in the Supabase SQL editor (or `supabase db push`). The Python sync upserts with the
-- service-role key, which bypasses RLS; dashboard users only get SELECT after logging in.

create table if not exists public.runs (
  id bigint primary key,
  trade_date date not null,
  mode text not null,
  started_at timestamptz,
  finished_at timestamptz,
  status text,
  message_id bigint,
  notes text
);
create index if not exists runs_trade_date_idx on public.runs (trade_date desc);

create table if not exists public.market_context (
  trade_date date primary key,
  phase text,
  mood text,
  score integer,
  caution integer,
  nifty_close double precision,
  nifty_ema20 double precision,
  nifty_ema50 double precision,
  nifty_chg_pct double precision,
  nifty_gap_pct double precision,
  vix double precision,
  fii_net double precision,
  dii_net double precision,
  global_json jsonb,
  components_json jsonb,
  reasons_json jsonb,
  nifty_day_return double precision,
  updated_at timestamptz
);

create table if not exists public.fii_dii (
  trade_date date primary key,
  fii_buy double precision,
  fii_sell double precision,
  fii_net double precision,
  dii_buy double precision,
  dii_sell double precision,
  dii_net double precision,
  source text
);

create table if not exists public.sector_strength (
  trade_date date not null,
  sector text not null,
  ret_1d double precision,
  ret_5d double precision,
  rs_1d double precision,
  rs_5d double precision,
  composite double precision,
  rank integer,
  points_long integer,
  points_short integer,
  source text,
  members integer,
  primary key (trade_date, sector)
);

create table if not exists public.features (
  trade_date date not null,
  symbol text not null,
  industry text,
  in_funnel integer default 0,
  filter_fails jsonb,
  features_json jsonb not null,
  primary key (trade_date, symbol)
);

create table if not exists public.candidates (
  trade_date date not null,
  symbol text not null,
  side text not null,
  phase text,
  stage text,
  score double precision,
  setup_type text,
  setup_label text,
  sector text,
  sector_points integer,
  components_json jsonb,
  reasons_json jsonb,
  flags_json jsonb,
  primary key (trade_date, symbol, side)
);

create table if not exists public.picks (
  id bigint primary key,
  trade_date date not null,
  symbol text not null,
  side text not null,
  rank integer,
  entry double precision,
  stop double precision,
  target double precision,
  qty integer,
  stop_pct double precision,
  atr_pct double precision,
  alt_stop double precision,
  score double precision,
  setup_type text,
  setup_label text,
  sector text,
  reasons_json jsonb,
  flags_json jsonb,
  components_json jsonb,
  entry_window text,
  squareoff_time text,
  status text not null default 'planned',
  phase text,
  preopen_gap_pct double precision,
  confirm_note text,
  confirmed_at timestamptz,
  note text,
  updated_at timestamptz,
  unique (trade_date, symbol, side)
);
create index if not exists picks_trade_date_idx on public.picks (trade_date desc);

create table if not exists public.outcomes (
  pick_id bigint primary key references public.picks (id) on delete cascade,
  trade_date date,
  symbol text,
  side text,
  result text,
  entry_time timestamptz,
  exit_time timestamptz,
  entry_price double precision,
  exit_price double precision,
  r_multiple double precision,
  pnl double precision,
  mfe double precision,
  mae double precision,
  day_high double precision,
  day_low double precision,
  day_close double precision,
  evaluated_at timestamptz
);
create index if not exists outcomes_trade_date_idx on public.outcomes (trade_date desc);

-- Row-level security: logged-in (invited) users can read everything, nobody can write from the
-- browser. The Python sync uses the service-role key, which bypasses these policies.
do $$
declare t text;
begin
  foreach t in array array['runs','market_context','fii_dii','sector_strength','features','candidates','picks','outcomes']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "authenticated read" on public.%I', t);
    execute format('create policy "authenticated read" on public.%I for select to authenticated using (true)', t);
  end loop;
end $$;

-- A view the dashboard uses for the history page: one row per pick with its outcome.
create or replace view public.pick_results as
select
  p.id, p.trade_date, p.symbol, p.side, p.rank, p.entry, p.stop, p.target, p.qty, p.score,
  p.setup_type, p.sector, p.status, p.flags_json, p.reasons_json, p.confirm_note,
  o.result, o.entry_price, o.exit_price, o.r_multiple, o.pnl, o.mfe, o.mae,
  m.mood, m.nifty_day_return
from public.picks p
left join public.outcomes o on o.pick_id = p.id
left join public.market_context m on m.trade_date = p.trade_date;

grant select on public.pick_results to authenticated;

-- Monthly watch universe (30 liquid stocks across sectors + index rows) with last-month statistics.
create table if not exists public.watchlist (
  month text not null,
  as_of date not null,
  symbol text not null,
  name text,
  industry text,
  rank integer,
  is_index integer default 0,
  close double precision,
  ret_1w double precision,
  ret_1m double precision,
  ret_3m double precision,
  month_high double precision,
  month_low double precision,
  range_pos double precision,
  atr_pct double precision,
  med_turnover_cr double precision,
  avg_volume double precision,
  sma50 double precision,
  sma200 double precision,
  pct_from_sma50 double precision,
  pct_from_sma200 double precision,
  regime text,
  picks_last_month integer,
  r_last_month double precision,
  vix double precision,
  primary key (month, symbol)
);

alter table public.watchlist enable row level security;
drop policy if exists "authenticated read" on public.watchlist;
create policy "authenticated read" on public.watchlist for select to authenticated using (true);
