# Intraday Picks dashboard

Next.js 16 app that shows the picks, confirmations, outcomes and market mood produced by the Python
engine in the parent folder. Data comes from Supabase (mirrored there by `python -m intraday_picks sync`);
access is invite-only through Supabase Auth.

Setup, Supabase configuration and the invite flow are documented in the repository root
[README](../README.md#web-dashboard-nextjs-on-vercel-invite-only).

```bash
npm install
cp .env.example .env.local      # NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
npm run dev                     # http://localhost:3000
npm run build                   # what Vercel runs
npx tsx scripts/render-check.tsx   # renders the chart components with sample data
```

Deploy by importing the repository into Vercel with `dashboard` as the root directory and the two
environment variables above. Pages: `/` (today), `/history`, `/market`; auth at `/login`,
`/set-password`, `/forgot-password`, `/auth/confirm`.
