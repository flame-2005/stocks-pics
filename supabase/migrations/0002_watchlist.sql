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
