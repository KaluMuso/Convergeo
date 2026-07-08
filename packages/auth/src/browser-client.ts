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
