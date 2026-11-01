/**
 * Supabase connection settings for the server side of the dashboard.
 * Accepts the NEXT_PUBLIC_* names used in .env.local and the plain names used by the Python
 * engine, so one set of values can be reused in Vercel. The service-role key is never read here.
 */
export function supabaseEnv(): { url: string; anonKey: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const anonKey =
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.SUPABASE_ANON_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
    process.env.SUPABASE_PUBLISHABLE_KEY;
  if (!url || !anonKey) return null;
  return { url: url.replace(/\/+$/, ""), anonKey };
}

export const MISSING_ENV_MESSAGE =
  "Dashboard is not configured: set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY " +
  "(or SUPABASE_URL and SUPABASE_ANON_KEY) in the hosting environment and redeploy.";
