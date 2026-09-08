import { sanitizeNextPath } from "@vergeo/auth/safe-next";

export const DEFAULT_COUNTRY_CODE = "+260";
export const RESEND_COOLDOWN_SECONDS = 60;

export type AuthErrorCode =
  | "wrong_code"
  | "expired"
  | "throttled"
  | "invalid_credentials"
  | "email_not_confirmed"
  | "already_registered"
  | "generic";

export type ParsedAuthError = {
  code: AuthErrorCode;
  retryAfterSeconds?: number;
};

export function normalizeNationalNumber(value: string): string {
  return value.replace(/\D/g, "").slice(0, 9);
}

export function formatE164(countryCode: string, nationalNumber: string): string {
  const digits = normalizeNationalNumber(nationalNumber);
  const code = countryCode.startsWith("+") ? countryCode : `+${countryCode}`;
  return `${code}${digits}`;
}

export function isValidZambianMobile(nationalNumber: string): boolean {
  const digits = normalizeNationalNumber(nationalNumber);
  return /^[79]\d{8}$/.test(digits);
}

export function maskPhone(e164: string): string {
  const digits = e164.replace(/\D/g, "");
  if (digits.length < 4) {
    return e164;
  }
  const visible = digits.slice(-3);
  return `+${digits.slice(0, 3)} ••• ••${visible}`;
}

export function parseAuthError(error: unknown): ParsedAuthError {
  if (!error || typeof error !== "object") {
    return { code: "generic" };
  }

  const record = error as {
    status?: number;
    message?: string;
    retryAfter?: number;
  };

  if (record.status === 429 || record.retryAfter !== undefined) {
    const seconds =
      typeof record.retryAfter === "number" && record.retryAfter > 0
        ? Math.ceil(record.retryAfter)
        : 60;
    return { code: "throttled", retryAfterSeconds: seconds };
  }

  const message = (record.message ?? "").toLowerCase();

  // Email/password specifics — checked before the generic "invalid" match so the
  // OTP flow keeps mapping its "invalid code" to wrong_code.
  if (message.includes("already registered") || message.includes("already been registered")) {
    return { code: "already_registered" };
  }

  if (message.includes("not confirmed")) {
    return { code: "email_not_confirmed" };
  }

  if (message.includes("invalid login credentials") || message.includes("invalid credentials")) {
    return { code: "invalid_credentials" };
  }

  if (message.includes("expired")) {
    return { code: "expired" };
  }

  if (message.includes("invalid") || message.includes("incorrect") || message.includes("wrong")) {
    return { code: "wrong_code" };
  }

  return { code: "generic" };
}

export function parseRetryAfterFromResponse(
  response: Response,
  body?: unknown,
): number | undefined {
  const header = response.headers.get("retry-after");
  if (header) {
    const parsed = Number.parseInt(header, 10);
    if (!Number.isNaN(parsed) && parsed > 0) {
      return parsed;
    }
  }

  if (body && typeof body === "object") {
    const record = body as { error?: { details?: { retry_after?: number } }; retry_after?: number };
    const fromDetails = record.error?.details?.retry_after;
    if (typeof fromDetails === "number" && fromDetails > 0) {
      return fromDetails;
    }
    if (typeof record.retry_after === "number" && record.retry_after > 0) {
      return record.retry_after;
    }
  }

  return undefined;
}

export function resolvePostAuthPath(
  locale: string,
  nextParam: string | null | undefined,
  fallbackPath: string,
): string {
  return sanitizeNextPath(locale, nextParam, fallbackPath);
}

/**
 * Sentinel that `sanitizeNextPath` can never legitimately return: every value
 * it accepts starts with "/". Used only to tell "rejected" apart from "a real
 * destination" without inventing a second sanitizer.
 */
const REJECTED_NEXT = "__vergeo_rejected_next__";

/**
 * The `next` value safe to carry FORWARD through an intermediate auth step
 * (login -> /otp), or null when there is nothing safe to carry.
 *
 * This does NOT replace the post-auth guard: `navigateAfterPortalAuth` still
 * sanitizes at redirect time, so an attacker-supplied absolute URL could never
 * become an external redirect either way. It exists so an unsafe value is
 * dropped at the first hop instead of being echoed into the next URL.
 */
export function forwardableNextParam(
  locale: string,
  nextParam: string | null | undefined,
): string | null {
  if (!nextParam) {
    return null;
  }
  const resolved = sanitizeNextPath(locale, nextParam, REJECTED_NEXT);
  return resolved === REJECTED_NEXT ? null : resolved;
}

export const ONBOARDING_INTERESTS = [
  "electronics",
  "fashion",
  "groceries",
  "services",
  "events",
] as const;

export type OnboardingInterest = (typeof ONBOARDING_INTERESTS)[number];

export function isOnboardingComplete(
  onboarding?: { completed_at?: string | null } | null,
): boolean {
  return Boolean(onboarding?.completed_at);
}

export function resolveCustomerPostAuthPath(
  locale: string,
  nextParam: string | null | undefined,
  fallbackPath: string,
  onboardingComplete: boolean,
): string {
  if (onboardingComplete) {
    return resolvePostAuthPath(locale, nextParam, fallbackPath);
  }

  const query = nextParam ? `?next=${encodeURIComponent(nextParam)}` : "";
  return `/${locale}/welcome${query}`;
}
