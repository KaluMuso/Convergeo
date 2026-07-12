/**
 * Analytics consent state (Zambia DPA aligned).
 *
 * GA4 is a convenience mirror and fires ONLY when the visitor has explicitly
 * granted consent. The default (no decision yet) is treated as NOT granted, so
 * refusal — or simply the absence of a choice — disables GA4. The anonymized
 * server beacon is independent of this state (see `track`).
 *
 * Consent is stored in a first-party cookie so the SSR pass and the client agree.
 */

export type ConsentState = "granted" | "denied" | "unset";

export const CONSENT_COOKIE = "vg_analytics_consent";

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const target = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(target)) {
      return decodeURIComponent(trimmed.slice(target.length));
    }
  }
  return null;
}

/** Current consent decision. Absent/invalid cookie → "unset" (GA4 stays off). */
export function getAnalyticsConsent(): ConsentState {
  const raw = readCookie(CONSENT_COOKIE);
  if (raw === "granted" || raw === "denied") {
    return raw;
  }
  return "unset";
}

/** True only when consent is explicitly granted — the sole gate for GA4. */
export function hasAnalyticsConsent(): boolean {
  return getAnalyticsConsent() === "granted";
}

/** Persist a consent decision as a first-party cookie. No-op during SSR. */
export function setAnalyticsConsent(state: Exclude<ConsentState, "unset">): void {
  if (typeof document === "undefined") {
    return;
  }
  document.cookie =
    `${CONSENT_COOKIE}=${state}; path=/; max-age=${ONE_YEAR_SECONDS}; ` + "samesite=lax";
}
