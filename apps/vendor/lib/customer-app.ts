/**
 * Links from the vendor app into the public customer storefront.
 *
 * Uses `NEXT_PUBLIC_SITE_URL` (customer origin) when configured. In development
 * falls back to the local customer dev server. Production builds without a
 * valid URL fail closed — callers must hide or disable storefront links.
 */

/** Dev-only convenience origin; never emitted from a production build. */
const DEV_CUSTOMER_APP_URL = "http://localhost:3000";
/** Public customer origin when NEXT_PUBLIC_SITE_URL is unset in production. */
const PRODUCTION_CUSTOMER_APP_URL = "https://www.vergeo5.com";

function normaliseSiteUrl(raw: string | undefined): string | null {
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

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return null;
  }

  return trimmed.replace(/\/+$/, "");
}

/** Resolve the customer app base URL for the current build, or `null` when unavailable. */
export function getCustomerAppUrl(): string | null {
  const configured = normaliseSiteUrl(process.env.NEXT_PUBLIC_SITE_URL);
  if (configured) {
    return configured;
  }

  if (process.env.NODE_ENV === "production") {
    return PRODUCTION_CUSTOMER_APP_URL;
  }

  return DEV_CUSTOMER_APP_URL;
}

/** Locale-aware public vendor storefront URL, or `null` when the customer app is unavailable. */
export function getVendorStorefrontUrl(locale: string, slug: string): string | null {
  const base = getCustomerAppUrl();
  if (base === null) {
    return null;
  }

  const trimmedSlug = slug.trim();
  if (!trimmedSlug) {
    return null;
  }

  return `${base}/${locale}/v/${encodeURIComponent(trimmedSlug)}`;
}

/**
 * Absolute customer-app URL for a path (`/en/account/event-team/accept`), used in text the
 * vendor shares outside the app. Falls back to the bare path when the origin is unknown.
 */
export function getCustomerAppPathUrl(path: string): string {
  const base = getCustomerAppUrl();
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return base === null ? suffix : `${base}${suffix}`;
}
