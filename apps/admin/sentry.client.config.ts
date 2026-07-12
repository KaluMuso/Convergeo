/**
 * Sentry browser init — admin app (M16-P06, STRICTEST).
 *
 * No-op unless `NEXT_PUBLIC_SENTRY_DSN` is set (dev/CI never emit; no DSN committed).
 * Same PII scrubber as customer/vendor, but hardened for the admin origin: no
 * performance tracing (`tracesSampleRate: 0`), fewer breadcrumbs, and console/http
 * breadcrumbs are dropped entirely so admin action detail never reaches Sentry.
 * Release = git sha (injected at build).
 */
import * as Sentry from "@sentry/nextjs";

const REDACTED = "[redacted]";
const EMAIL_MASK = "[redacted-email]";
const PHONE_MASK = "[redacted-phone]";
const TOKEN_MASK = "[redacted-token]";

const SENSITIVE_KEY_PARTS = [
  "phone",
  "msisdn",
  "mobile",
  "tel",
  "email",
  "address",
  "street",
  "landmark",
  "gps",
  "latitude",
  "longitude",
  "coordinate",
  "token",
  "authorization",
  "password",
  "secret",
  "api_key",
  "apikey",
  "otp",
  "pin",
];

const TOKEN_RE = /bearer\s+[A-Za-z0-9._-]+|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/gi;
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const PHONE_RE = /\+260\d{9}|(?<!\d)0\d{9}(?!\d)|\+\d{10,15}/g;

function scrubText(text: string): string {
  return text
    .replace(TOKEN_RE, TOKEN_MASK)
    .replace(EMAIL_RE, EMAIL_MASK)
    .replace(PHONE_RE, PHONE_MASK);
}

function keyIsSensitive(key: string): boolean {
  const lowered = key.toLowerCase();
  return SENSITIVE_KEY_PARTS.some((part) => lowered.includes(part));
}

function scrub(value: unknown): unknown {
  if (typeof value === "string") return scrubText(value);
  if (Array.isArray(value)) return value.map(scrub);
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = keyIsSensitive(k) ? REDACTED : scrub(v);
    }
    return out;
  }
  return value;
}

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? process.env.NODE_ENV,
    release: process.env.NEXT_PUBLIC_SENTRY_RELEASE,
    sendDefaultPii: false,
    // Strictest: no tracing, minimal breadcrumbs.
    tracesSampleRate: 0,
    maxBreadcrumbs: 20,
    beforeSend: (event) => scrub(event) as typeof event,
    // Drop console/http breadcrumbs entirely; scrub whatever remains.
    beforeBreadcrumb: (crumb) => {
      if (crumb.category === "console" || crumb.category === "xhr" || crumb.category === "fetch") {
        return null;
      }
      return scrub(crumb) as typeof crumb;
    },
  });
}
