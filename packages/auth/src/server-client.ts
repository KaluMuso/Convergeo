import { createServerClient as createSupabaseServerClient } from "@supabase/ssr";
import type { CookieMethodsServer, SetAllCookies } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { cookies } from "next/headers";

import { getSupabaseAnonKey, getSupabaseUrl } from "./env";

type CookieStore = Awaited<ReturnType<typeof cookies>>;

export function createCookieMethods(cookieStore: CookieStore): CookieMethodsServer {
  return {
    getAll() {
      return cookieStore.getAll();
    },
    setAll(cookiesToSet: Parameters<SetAllCookies>[0]) {
      try {
        cookiesToSet.forEach(({ name, value, options }) => {
          cookieStore.set(name, value, options);
        });
      } catch {
        // Server Components may call set on a read-only cookie store.
      }
    },
  };
}

export function createServerClient(cookieStore: CookieStore): SupabaseClient {
  return createSupabaseServerClient(getSupabaseUrl(), getSupabaseAnonKey(), {
    cookies: createCookieMethods(cookieStore),
  });
}
