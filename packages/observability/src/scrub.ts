/**
 * Shared PII / secret scrubber for Vergeo5 Sentry clients.
 * Mirrors services/api/app/core/sentry.py — keep both in lockstep via tests.
 */

export const REDACTED = "[redacted]";
export const EMAIL_MASK = "[redacted-email]";
export const PHONE_MASK = "[redacted-phone]";
export const TOKEN_MASK = "[redacted-token]";

/** Substring match on key names (case-insensitive). */
export const SENSITIVE_KEY_PARTS = [
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
  "passwd",
  "secret",
  "api_key",
  "apikey",
  "otp",
  "pin",
  "cookie",
  "set-cookie",
  "refresh",
  "access_token",
  "refresh_token",
  "service_role",
  "service-role",
  "webhook_signature",
  "x-lenco-signature",
  "signature",
  "card_number",
  "pan",
  "cvv",
  "cvc",
  "payment_payload",
  "encrypted_payload",
  "lenco",
] as const;

const TOKEN_RE = /bearer\s+[A-Za-z0-9._-]+|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/gi;
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const PHONE_RE = /\+260\d{9}|(?<!\d)0\d{9}(?!\d)|\+\d{10,15}/g;

export function scrubText(text: string): string {
  return text
    .replace(TOKEN_RE, TOKEN_MASK)
    .replace(EMAIL_RE, EMAIL_MASK)
    .replace(PHONE_RE, PHONE_MASK);
}

export function keyIsSensitive(key: string): boolean {
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

/** Resolve immutable release SHA for browser/server labels. */
export function resolveReleaseSha(env: NodeJS.ProcessEnv = process.env): string | undefined {
  const release =
    env.NEXT_PUBLIC_SENTRY_RELEASE ||
    env.SENTRY_RELEASE ||
    env.NEXT_PUBLIC_VERGEO_BUILD_ID ||
    env.VERCEL_GIT_COMMIT_SHA ||
    env.GIT_SHA;
  return release && release.trim() ? release.trim() : undefined;
}

export function resolveEnvironment(
  env: NodeJS.ProcessEnv = process.env,
  fallback = "development",
): string {
  return (
    env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ||
    env.SENTRY_ENVIRONMENT ||
    env.NEXT_PUBLIC_VERGEO_ENV ||
    env.VERCEL_ENV ||
    env.NODE_ENV ||
    fallback
  );
}

/** Production must not expose the sentry-test route without an explicit secret. */
export function isSentryTestEndpointEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  const secret = (env.SENTRY_TEST_SECRET || "").trim();
  if (!secret) return false;
  const nodeEnv = (env.NODE_ENV || "").toLowerCase();
  const vergeoEnv = (env.NEXT_PUBLIC_VERGEO_ENV || env.VERCEL_ENV || "").toLowerCase();
  if (nodeEnv === "production" || vergeoEnv === "production") {
    return (env.ENABLE_SENTRY_TEST_ENDPOINT || "").toLowerCase() === "true";
  }
  return true;
}
