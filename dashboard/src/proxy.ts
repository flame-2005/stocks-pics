import { type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/session";

/** Next.js 16 request proxy: refreshes the Supabase session and sends anonymous visitors to /login. */
export async function proxy(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  // Everything except Next internals and static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
