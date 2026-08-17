import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Lazy accessor for the Supabase browser client.
 *
 * This module has NO static `@supabase/ssr` / `@supabase/supabase-js` import (the
 * `SupabaseClient` above is a type-only import, erased at build). It reaches the
 * real client through a dynamic `import("./browser-client")`, so a component can
 * import `getBrowserClient` without pulling ~Supabase into its first-load JS — the
 * heavy client is fetched as a separate chunk the first time it is actually needed
 * (a form submit, a menu opening, a session read after hydration).
 *
 * `createBrowserClient` memoises the singleton, so repeated `getBrowserClient()`
 * calls reuse the same client and the dynamic import resolves from cache.
 */
export async function getBrowserClient(): Promise<SupabaseClient> {
  const { createBrowserClient } = await import("./browser-client");
  return createBrowserClient();
}
