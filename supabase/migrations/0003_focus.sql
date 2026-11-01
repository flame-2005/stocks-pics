-- "Your list": daily verdicts for the Nifty (via NIFTYBEES) and the user's own companies.
create table if not exists public.focus_verdicts (
  trade_date date not null,
  symbol text not null,
  instrument text,
  phase text,
  verdict text,
  strength text,
  side text,
  entry double precision,
  stop double precision,
  target double precision,
  qty integer,
  stop_pct double precision,
  score_long double precision,
  score_short double precision,
  regime text,
  setup_type text,
  setup_label text,
  close double precision,
  reasons_json jsonb,
  flags_json jsonb,
  note text,
  result text,
  entry_price double precision,
  exit_price double precision,
  r_multiple double precision,
  pnl double precision,
  updated_at timestamptz,
  primary key (trade_date, symbol)
);

alter table public.focus_verdicts enable row level security;
drop policy if exists "authenticated read" on public.focus_verdicts;
create policy "authenticated read" on public.focus_verdicts for select to authenticated using (true);
