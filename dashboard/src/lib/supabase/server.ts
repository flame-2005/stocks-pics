import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { MISSING_ENV_MESSAGE, supabaseEnv } from "./env";

/** Supabase client for server components, server actions and route handlers. */
export async function createClient() {
  const env = supabaseEnv();
  if (!env) throw new Error(MISSING_ENV_MESSAGE);
  const { url, anonKey } = env;
  const cookieStore = await cookies();
  return createServerClient(
    url,
    anonKey,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
          } catch {
            // Called from a server component: cookies are read-only there and the proxy refreshes them.
          }
        },
      },
    },
  );
}
