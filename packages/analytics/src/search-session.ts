/**
 * Optional `X-Analytics-Session` header for client-side `/search` calls (OD-8).
 *
 * Lets the API count DISTINCT anonymous sessions per search term for its k-threshold.
 * The header carries the rotating v2 session id (`vg_sess2`) only: no user id, no anon id,
 * no PII. It is sent only when v2 tracking is on, the visitor is not counts-only (consent
 * not denied, no Global Privacy Control) and a v2 session id already exists. Otherwise
 * the header is omitted and the API counts the search as session-less (conservative).
 */

import { isCountsOnly, currentSessionId } from "./v2/ids";

export const ANALYTICS_SESSION_HEADER = "X-Analytics-Session";

function isV2TrackingOn(): boolean {
  return process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING === "1";
}

/** `{ "X-Analytics-Session": id }` when allowed, else `{}`. Safe to spread into fetch headers. */
export function searchSessionHeaders(): Record<string, string> {
  if (!isV2TrackingOn() || typeof window === "undefined" || isCountsOnly()) {
    return {};
  }
  const id = currentSessionId();
  return id ? { [ANALYTICS_SESSION_HEADER]: id } : {};
}
