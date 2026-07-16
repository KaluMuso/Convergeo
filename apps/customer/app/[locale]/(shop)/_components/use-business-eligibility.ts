"use client";

import { useEffect, useState } from "react";

/**
 * Client-side "is the current viewer a verified business buyer?" check, used to
 * gate the wholesale Supplies nav entry.
 *
 * Why client-side: the shop layout is a locale-only server component with no
 * cookie/session read, which keeps the PLP/PDP underneath statically cacheable
 * (ISR). Resolving eligibility server-side here would opt the whole shop segment
 * out of ISR just to show one nav link — a bad trade. So we resolve it after
 * hydration instead.
 *
 * Cost control: the Supabase browser client and the business-status client are
 * imported dynamically (not statically), so none of that code lands in the
 * first-load JS the bundle budget measures — it loads as an async chunk only
 * after mount. The result is memoised at module scope so the desktop header link
 * and the mobile bottom-nav item share a single `/business/status` request per
 * page session, and it stays `false` until confirmed (guests / non-eligible — the
 * common case — never flash a Supplies entry).
 */
let cachedEligible: boolean | null = null;
let inflight: Promise<boolean> | null = null;

async function resolveEligibility(): Promise<boolean> {
  const [{ createBrowserClient }, { createBusinessApiClient }] = await Promise.all([
    import("@vergeo/auth/browser-client"),
    import("../../account/business/_components/business-api"),
  ]);

  const supabase = createBrowserClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token ?? null;
  if (!token) {
    return false;
  }

  try {
    const status = await createBusinessApiClient(() => token).getStatus();
    return status.eligible;
  } catch {
    return false;
  }
}

export function useBusinessEligibility(): boolean {
  const [eligible, setEligible] = useState<boolean>(cachedEligible ?? false);

  useEffect(() => {
    if (cachedEligible !== null) {
      setEligible(cachedEligible);
      return;
    }

    let active = true;
    if (!inflight) {
      inflight = resolveEligibility()
        .then((value) => {
          cachedEligible = value;
          return value;
        })
        .catch(() => {
          cachedEligible = false;
          return false;
        });
    }
    void inflight.then((value) => {
      if (active) {
        setEligible(value);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return eligible;
}

/** Test-only: reset the module-level memo so cases don't leak between tests. */
export function __resetBusinessEligibilityCache(): void {
  cachedEligible = null;
  inflight = null;
}
