/**
 * Sentry browser init — admin app (M16-P06, STRICTEST).
 *
 * SDK-free at load time (`import type` only): the heavy `@sentry/nextjs` SDK is passed
 * in by the lazy loader (`app/sentry-init.tsx`), which `import()`s it in an async chunk
 * after hydration, keeping it off first-load JS. Same PII scrubber as customer/vendor,
 * hardened for the admin origin: errors only (no tracing/replay), fewer breadcrumbs, and
 * console/http breadcrumbs dropped entirely so admin action detail never reaches Sentry.
 * No-op unless `NEXT_PUBLIC_SENTRY_DSN` is set. Release = git sha.
 */
import type * as SentryType from "@sentry/nextjs";

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

export function scrub(value: unknown): unknown {
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

export function initClientSentry(Sentry: typeof SentryType): void {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? process.env.NODE_ENV,
    release: process.env.NEXT_PUBLIC_SENTRY_RELEASE,
    sendDefaultPii: false,
    // Strictest: no tracing, no replay, minimal breadcrumbs.
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    maxBreadcrumbs: 20,
    integrations: (defaults) =>
      defaults.filter((i) => !/(BrowserTracing|Replay|Feedback)/.test(i.name)),
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
