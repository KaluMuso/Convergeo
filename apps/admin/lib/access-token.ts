import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";

/**
 * Access token for admin API calls.
 *
 * Importing `getBrowserAccessToken` from the `@vergeo/auth` barrel statically pulls
 * supabase-js (~55 kB gzip) plus the server/middleware exports into first-load JS. This goes
 * through the lazy accessor instead, so the Supabase client is its own chunk that loads the
 * first time a token is actually needed. Same contract: live session at call time, null on
 * the server or without a session.
 */
export async function getBrowserAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") {
    return null;
  }
  const { data } = await (await getBrowserClient()).auth.getSession();
  return data.session?.access_token ?? null;
}
