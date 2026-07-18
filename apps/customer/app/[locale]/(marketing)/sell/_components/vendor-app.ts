/**
 * Single source of truth for links from the customer app into the vendor app.
 *
 * The vendor app origin is read from `NEXT_PUBLIC_VENDOR_APP_URL` (inlined at
 * build time by Next). In development the local vendor dev server is used as a
 * convenience fallback, but in a PRODUCTION build an absent/invalid value fails
 * CLOSED: callers receive `null` and must render an unavailable state rather
 * than emit a broken `http://localhost:3001` link that would silently break the
 * vendor-acquisition funnel in production.
 *
 * `process.env.NEXT_PUBLIC_VENDOR_APP_URL` and `process.env.NODE_ENV` are
 * referenced as static member expressions so Next can inline them into the
 * client bundle — do not read them via a computed key.
 */

export const VENDOR_ONBOARDING_PATH = "/onboarding";

/** Dev-only convenience origin; never emitted from a production build. */
const DEV_VENDOR_APP_URL = "http://localhost:3001";

/** Validate + normalise a candidate vendor-app base URL, or `null` if unusable. */
function normaliseVendorAppUrl(raw: string | undefined): string | null {
  if (!raw) {
    return null;
  }

  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return null;
  }

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return null;
  }

  // Only real web origins are usable for a cross-app link.
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return null;
  }

  // Drop any trailing slash so locale/path joins stay clean.
  return trimmed.replace(/\/+$/, "");
}

/**
 * Resolve the vendor app base URL for the current build, or `null` when it is
 * unconfigured/invalid in a production build (fail closed — never localhost).
 */
export function getVendorAppUrl(): string | null {
  const configured = normaliseVendorAppUrl(process.env.NEXT_PUBLIC_VENDOR_APP_URL);
  if (configured) {
    return configured;
  }

  if (process.env.NODE_ENV === "production") {
    return null;
  }

  return DEV_VENDOR_APP_URL;
}

/** True when a usable vendor-app URL exists for this build. */
export function isVendorAppConfigured(): boolean {
  return getVendorAppUrl() !== null;
}

/**
 * Locale-aware vendor onboarding/signup URL, or `null` when the vendor app is
 * unavailable (a production build without `NEXT_PUBLIC_VENDOR_APP_URL`).
 */
export function getVendorSignupUrl(locale: string): string | null {
  const base = getVendorAppUrl();
  if (base === null) {
    return null;
  }

  return `${base}/${locale}${VENDOR_ONBOARDING_PATH}`;
}
