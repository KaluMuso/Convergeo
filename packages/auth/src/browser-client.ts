import { createBrowserClient as createSupabaseBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { getSupabaseAnonKey, getSupabaseUrl } from "./env";

let browserClient: SupabaseClient | undefined;

export function createBrowserClient(): SupabaseClient {
  if (browserClient) {
    return browserClient;
  }

  browserClient = createSupabaseBrowserClient(getSupabaseUrl(), getSupabaseAnonKey());
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
