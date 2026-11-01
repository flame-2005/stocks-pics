import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { MISSING_ENV_MESSAGE, supabaseEnv } from "./env";

const PUBLIC_PREFIXES = ["/login", "/forgot-password", "/auth"];

/**
 * Refreshes the Supabase session cookie on every request and gates the app:
 * anonymous visitors only ever see /login, /forgot-password and the /auth routes.
 */
export async function updateSession(request: NextRequest) {
  const env = supabaseEnv();
  if (!env) {
    return new NextResponse(MISSING_ENV_MESSAGE, { status: 500, headers: { "content-type": "text/plain; charset=utf-8" } });
  }
  const { url, anonKey } = env;
  let response = NextResponse.next({ request });

  const supabase = createServerClient(url, anonKey, {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    },
  );

  // getUser() validates the JWT against Supabase; never trust getSession() here.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC_PREFIXES.some((p) => path.startsWith(p));

  if (!user && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  if (user && path.startsWith("/login")) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return response;
}
