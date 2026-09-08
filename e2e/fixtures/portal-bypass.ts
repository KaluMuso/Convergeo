/**
 * Pure per-origin Vercel Deployment Protection bypass logic.
 *
 * Deliberately dependency-free (no `@playwright/test` import, not even a type
 * one) so ordinary CI can unit-test it directly with Node type-stripping —
 * same contract as `gating-policy.ts`. `test-base.ts` is the thin Playwright
 * wrapper; everything decidable without a browser lives here.
 *
 * Two invariants this module exists to hold:
 *
 *  1. FAIL CLOSED ON ORIGIN. A bypass secret is issued per Vercel PROJECT and
 *     is a credential. Only the three configured portal origins may ever
 *     receive one; every other origin the suite touches (Supabase, the staging
 *     FastAPI, Cloudinary, fonts, anything a page happens to pull) gets none,
 *     and an unparseable URL gets none either.
 *  2. NEVER DROP A HEADER WHEN REWRITING. `route.fallback({ headers })`
 *     REPLACES the request's whole header map, so the replacement must be
 *     built from `request.allHeaders()` — the async accessor that includes
 *     security-sensitive headers such as `Cookie`. `request.headers()` omits
 *     them, so rewriting from it silently strips the Supabase session cookie
 *     off every intercepted request (staging E2E run #70).
 *
 * Nothing here logs, prints, compares or returns a secret for inspection.
 */

/** Header carrying the Vercel automation bypass secret (never a URL param). */
export const BYPASS_HEADER = "x-vercel-protection-bypass";

/** Asks Vercel to set the bypass cookie so subresources are let through too. */
export const SET_BYPASS_COOKIE_HEADER = "x-vercel-set-bypass-cookie";

/** One portal: the origin it is served from and that project's own secret. */
export type PortalTarget = {
  baseUrl: string;
  secret: string;
};

export type PortalBypassConfig = {
  customer: PortalTarget;
  vendor: PortalTarget;
  admin: PortalTarget;
};

/** Lower-cased origin of a URL, or "" when the input cannot be parsed. */
export function originOf(raw: string): string {
  try {
    return new URL(raw).origin.toLowerCase();
  } catch {
    return "";
  }
}

/**
 * Pick the bypass secret for whichever portal origin a request targets.
 *
 * Returns "" for ANY origin that is not one of the three configured portals —
 * including an unparseable URL. That empty string is the whole safety
 * property: the caller leaves such a request completely untouched instead of
 * attaching a Vercel credential to a third party.
 */
export function resolveBypassSecret(url: string, config: PortalBypassConfig): string {
  const target = originOf(url);
  if (!target) return "";
  // Customer is matched FIRST: VENDOR_BASE_URL/ADMIN_BASE_URL default to the
  // customer base, so on a collision (portal origin not separately configured)
  // the origin is genuinely the customer app and must get the customer secret.
  if (target === originOf(config.customer.baseUrl)) return config.customer.secret;
  if (target === originOf(config.vendor.baseUrl)) return config.vendor.secret;
  if (target === originOf(config.admin.baseUrl)) return config.admin.secret;
  return "";
}

/** The distinct, parseable origins the three portals are served from. */
export function portalOrigins(config: PortalBypassConfig): string[] {
  const origins = [config.customer, config.vendor, config.admin]
    .map((target) => originOf(target.baseUrl))
    .filter((origin) => origin.length > 0);
  return [...new Set(origins)];
}

/**
 * True only for the configured portal origins.
 *
 * Used as the route MATCHER so non-portal requests are never intercepted or
 * rewritten in the first place — defence in depth behind
 * `resolveBypassSecret`'s fail-closed return, and one less request rebuilt on
 * a Fast-3G run.
 */
export function isPortalOrigin(url: string, config: PortalBypassConfig): boolean {
  const origin = originOf(url);
  if (!origin) return false;
  return portalOrigins(config).includes(origin);
}

/**
 * The COMPLETE original header set plus the bypass headers.
 *
 * `existing` must come from `request.allHeaders()`. Injected headers are added
 * last so an origin that already carries a bypass header gets the one matching
 * the origin actually being addressed; every other header is passed through
 * byte-for-byte.
 */
export function withBypassHeaders(
  existing: Record<string, string>,
  secret: string,
): Record<string, string> {
  return {
    ...existing,
    [BYPASS_HEADER]: secret,
    [SET_BYPASS_COOKIE_HEADER]: "true",
  };
}

/**
 * Minimal structural view of a Playwright `Route`.
 *
 * Only `allHeaders()` is exposed on purpose: a rewriting code path must not be
 * able to reach the synchronous, cookie-stripping `headers()` accessor through
 * this type at all.
 */
export type BypassRouteRequest = {
  url(): string;
  allHeaders(): Promise<Record<string, string>>;
};

export type BypassRoute = {
  request(): BypassRouteRequest;
  fallback(options?: { headers?: Record<string, string> }): Promise<void>;
};

/**
 * Rewrite one request's bypass headers, or pass it through untouched.
 *
 * `resolveSecret` is injected so this is provable without any env at all.
 */
export async function applyPortalBypass(
  route: BypassRoute,
  resolveSecret: (url: string) => string,
): Promise<void> {
  const request = route.request();
  const secret = resolveSecret(request.url());

  if (!secret) {
    // No argument: Playwright forwards the ORIGINAL request unmodified.
    await route.fallback();
    return;
  }

  // `allHeaders()`, never `headers()` — see invariant 2 at the top of the file.
  const headers = await request.allHeaders();
  await route.fallback({ headers: withBypassHeaders(headers, secret) });
}
