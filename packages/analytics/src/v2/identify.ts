/**
 * analytics_v2 sign-in linking (Convergeo Intelligence 1A-08, plan §R-B, OD-2).
 *
 * After a customer signs in, tell the API which anonymous v2 session they were using so
 * rollups can join "browsing before first purchase" journeys to the account. Loaded on
 * demand (dynamic import from the auth flow), never in a route's first-load JS.
 *
 * Privacy: the body is the anonymous session id and nothing else (no PII); the account is
 * resolved server-side from the bearer token. Nothing is sent when v2 tracking is off, the
 * visitor has opted out (consent `denied` or Global Privacy Control), or no v2 session
 * exists yet. At most one call per v2 session. Failures are swallowed: this is best-effort.
 */

import { currentSessionId, isCountsOnly } from "./ids";

export const LINKED_KEY = "vg_ident2";

function readLinked(): string | null {
  try {
    return window.localStorage.getItem(LINKED_KEY);
  } catch {
    return null;
  }
}

function writeLinked(sessionId: string): void {
  try {
    window.localStorage.setItem(LINKED_KEY, sessionId);
  } catch {
    // storage blocked — worst case the link is re-sent (the API is idempotent)
  }
}

export interface IdentifyArgs {
  apiBaseUrl: string;
  accessToken: string;
}

/** Link the current anonymous v2 session to the signed-in account. Resolves true if sent. */
export async function identifyAnalyticsSession({
  apiBaseUrl,
  accessToken,
}: IdentifyArgs): Promise<boolean> {
  if (typeof window === "undefined" || process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING !== "1") {
    return false;
  }
  if (isCountsOnly()) {
    return false;
  }
  const sessionId = currentSessionId();
  if (!sessionId || readLinked() === sessionId) {
    return false;
  }
  try {
    const response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/analytics/identify`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ session_id: sessionId }),
      keepalive: true,
    });
    if (!response.ok) {
      return false;
    }
    writeLinked(sessionId);
    return true;
  } catch {
    return false;
  }
}
