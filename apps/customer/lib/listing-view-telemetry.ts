import { getSessionId } from "@vergeo/analytics";

import { absoluteApiUrl } from "./api-base-url";

export const MAX_LISTING_IMPRESSION_BATCH = 50;

const IMPRESSION_BATCH_DELAY_MS = 75;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type PendingImpression = {
  key: string;
  listingId: string;
  sessionId: string;
};

/**
 * analytics_v2 (plan 1A-06): a slug-free listing surface, sent only when the build sets
 * NEXT_PUBLIC_ANALYTICS_V2_TRACKING=1 (inlined, so v1 builds drop this and keep
 * byte-identical payloads). Values match `record_listing_view` (home|plp|storefront|pdp|unknown).
 */
export function surfaceFromPath(pathname: string | null | undefined): string {
  const segment = pathname?.replace(/^\/(en|bem|nya|fr|zh)(?=\/|$)/, "").split("/")[1];
  if (!segment) {
    return pathname ? "home" : "unknown";
  }
  return /^(c|search|categories|supplies)$/.test(segment)
    ? "plp"
    : segment === "v"
      ? "storefront"
      : /^[pl]$/.test(segment)
        ? "pdp"
        : "unknown";
}

let pendingImpressions = new Map<string, PendingImpression>();
let impressionBatchTimer: ReturnType<typeof setTimeout> | null = null;
let dedupDay = "";
const sentImpressions = new Set<string>();
const sentPdpViews = new Set<string>();

function currentUtcDay(): string {
  const day = new Date().toISOString().slice(0, 10);
  if (day !== dedupDay) {
    dedupDay = day;
    sentImpressions.clear();
    sentPdpViews.clear();
  }
  return day;
}

function dedupKey(sessionId: string, listingId: string): string {
  return `${currentUtcDay()}:${sessionId}:${listingId}`;
}

function isValidUuid(value: string): boolean {
  return UUID_RE.test(value);
}

function canSendTelemetry(): boolean {
  return (
    typeof navigator !== "undefined" &&
    navigator.onLine !== false &&
    absoluteApiUrl("/telemetry/views") !== null
  );
}

/**
 * Send a first-party, anonymous listing-view payload.
 *
 * This follows the existing analytics convention: the anonymous server record
 * is consent-independent; only the optional GA4 mirror is consent-gated. No
 * account id, query, referrer, or other shopper data is included here.
 */
function transmit(payload: Record<string, string | string[]>, viewerToken?: string): boolean {
  if (typeof navigator === "undefined" || navigator.onLine === false) {
    return false;
  }

  const endpoint = absoluteApiUrl("/telemetry/views");
  if (!endpoint) {
    return false;
  }

  const body = JSON.stringify(payload);
  // v2 only: a signed-in PDP view carries the bearer so the API can drop vendor
  // self-views. Beacons cannot set headers, so that case uses keepalive fetch.
  if (!viewerToken && typeof navigator.sendBeacon === "function") {
    try {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(endpoint, blob)) {
        return true;
      }
    } catch {
      // Fall through to a keepalive fetch when Beacon is unavailable/rejected.
    }
  }

  if (typeof fetch !== "function") {
    return false;
  }

  try {
    void fetch(endpoint, {
      method: "POST",
      headers: viewerToken
        ? { "Content-Type": "application/json", Authorization: `Bearer ${viewerToken}` }
        : { "Content-Type": "application/json" },
      body,
      credentials: "omit",
      keepalive: true,
      referrerPolicy: "no-referrer",
    }).catch(() => undefined);
    return true;
  } catch {
    return false;
  }
}

/**
 * Record one PDP view. The server remains the authoritative daily deduper.
 * `viewerToken` (v2 builds) is used by the API for the vendor self-view check only.
 */
export function recordListingPdpView(listingId: string, viewerToken?: string | null): boolean {
  if (!isValidUuid(listingId) || !canSendTelemetry()) {
    return false;
  }

  const sessionId = getSessionId();
  if (!sessionId) {
    return false;
  }

  const key = dedupKey(sessionId, listingId);
  if (sentPdpViews.has(key)) {
    return false;
  }

  const accepted =
    process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING === "1"
      ? transmit(
          { session_id: sessionId, listing_id: listingId, surface: "pdp" },
          viewerToken ?? undefined,
        )
      : transmit({ session_id: sessionId, listing_id: listingId });
  if (accepted) {
    sentPdpViews.add(key);
  }
  return accepted;
}

/**
 * Flush visible listing impressions in API-sized batches. Failed/offline
 * batches are deliberately dropped rather than replayed as stale impressions.
 */
export function flushListingImpressions(): void {
  if (impressionBatchTimer !== null) {
    clearTimeout(impressionBatchTimer);
    impressionBatchTimer = null;
  }

  const batch = [...pendingImpressions.values()];
  pendingImpressions = new Map();
  if (batch.length === 0) {
    return;
  }

  const bySession = new Map<string, PendingImpression[]>();
  for (const item of batch) {
    const sessionBatch = bySession.get(item.sessionId) ?? [];
    sessionBatch.push(item);
    bySession.set(item.sessionId, sessionBatch);
  }

  for (const [sessionId, sessionBatch] of bySession) {
    for (let start = 0; start < sessionBatch.length; start += MAX_LISTING_IMPRESSION_BATCH) {
      const chunk = sessionBatch.slice(start, start + MAX_LISTING_IMPRESSION_BATCH);
      const accepted = transmit(
        process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING === "1"
          ? {
              session_id: sessionId,
              listing_ids: chunk.map((item) => item.listingId),
              surface: surfaceFromPath(window.location.pathname),
            }
          : {
              session_id: sessionId,
              listing_ids: chunk.map((item) => item.listingId),
            },
      );
      if (accepted) {
        for (const item of chunk) {
          sentImpressions.add(item.key);
        }
      }
    }
  }
}

/** Queue an eligible (50% visible for 1s) listing impression for one batch. */
export function queueListingImpression(listingId: string): boolean {
  if (!isValidUuid(listingId) || !canSendTelemetry()) {
    return false;
  }

  const sessionId = getSessionId();
  if (!sessionId) {
    return false;
  }

  const key = dedupKey(sessionId, listingId);
  if (sentImpressions.has(key) || pendingImpressions.has(key)) {
    return false;
  }

  pendingImpressions.set(key, { key, listingId, sessionId });
  if (pendingImpressions.size >= MAX_LISTING_IMPRESSION_BATCH) {
    flushListingImpressions();
  } else if (impressionBatchTimer === null) {
    impressionBatchTimer = setTimeout(flushListingImpressions, IMPRESSION_BATCH_DELAY_MS);
  }
  return true;
}

/** Test-only reset for module-scoped batching/dedup state. */
export function __resetListingViewTelemetry(): void {
  if (impressionBatchTimer !== null) {
    clearTimeout(impressionBatchTimer);
    impressionBatchTimer = null;
  }
  pendingImpressions.clear();
  sentImpressions.clear();
  sentPdpViews.clear();
  dedupDay = "";
}
