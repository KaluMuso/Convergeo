import { createBrowserClient as createSupabaseBrowserClient } from "@supabase/ssr";

import { getSupabaseAnonKey, getSupabaseUrl } from "./env";

import type { SupabaseClient } from "@supabase/supabase-js";

let browserClient: SupabaseClient | undefined;

/** These routes exchange their own PKCE code after the client is created. */
function hasExplicitCodeExchange(pathname: string): boolean {
  const segments = pathname.split("/").filter(Boolean);
  return (
    (segments.length === 2 && (segments[1] === "login" || segments[1] === "signup")) ||
    (segments.length === 3 && segments[1] === "reset-password" && segments[2] === "confirm")
  );
}

export function createBrowserClient(): SupabaseClient {
  if (browserClient) {
    return browserClient;
  }

  // Supabase SSR otherwise exchanges ?code= during client initialization.
  // A second exchange in the route then fails because the code and PKCE
  // verifier are single-use. Other callbacks (such as email confirmation at
  // the configured Site URL) retain Supabase's automatic handling.
  const detectSessionInUrl =
    typeof window === "undefined" || !hasExplicitCodeExchange(window.location.pathname);
  browserClient = createSupabaseBrowserClient(getSupabaseUrl(), getSupabaseAnonKey(), {
    auth: { detectSessionInUrl },
  });
  return browserClient;
}

export function resetBrowserClientForTests(): void {
  browserClient = undefined;
}

/**
 * Current Supabase access token for authenticating API calls from the browser.
 *
 * Reads the live persisted session at call time (Supabase refreshes it under the
 * hood), so it is always fresh and there is no token copied into web storage.
 * Returns null on the server or when there is no session. Suitable as the
 * `getToken` for `createApiClient`.
 */
export async function getBrowserAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") {
    return null;
  }
  const { data } = await createBrowserClient().auth.getSession();
  return data.session?.access_token ?? null;
}
