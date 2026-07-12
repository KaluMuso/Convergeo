/**
 * Sentry browser init — vendor app (M16-P06).
 *
 * SDK-free at load time (`import type` only): the heavy `@sentry/nextjs` SDK is passed
 * in by the lazy loader (`app/sentry-init.tsx`), which `import()`s it in an async chunk
 * after hydration, keeping it off first-load JS. Errors-only (no Session Replay, no
 * browser tracing). `beforeSend` / `beforeBreadcrumb` mirror the API PII scrubber:
 * phone, address, email and tokens are masked in both the event body and every
 * breadcrumb. No-op unless `NEXT_PUBLIC_SENTRY_DSN` is set. Release = git sha.
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
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    maxBreadcrumbs: 50,
    integrations: (defaults) =>
      defaults.filter((i) => !/(BrowserTracing|Replay|Feedback)/.test(i.name)),
    beforeSend: (event) => scrub(event) as typeof event,
    beforeBreadcrumb: (crumb) => scrub(crumb) as typeof crumb,
  });
}
