/**
 * Consent-aware, data-frugal analytics dispatch.
 *
 * Every `track` call does two things:
 *  1. Enqueues an anonymized event for the server beacon — ALWAYS, regardless of
 *     consent. Beacons are batched and sent with `navigator.sendBeacon` (no
 *     per-event XHR) to stay cheap on 3G. The server log is the source of truth.
 *  2. Mirrors the event to GA4 — ONLY when consent is granted. Refusal (or no
 *     decision yet) disables the GA4 mirror and nothing else.
 *
 * The GA4 measurement id comes from `NEXT_PUBLIC_GA4_MEASUREMENT_ID` only; it is
 * never hardcoded. All browser access is call-time and guarded, so importing this
 * module on the server is safe.
 *
 * analytics_v2 (Convergeo Intelligence 1A-04): when the build sets
 * `NEXT_PUBLIC_ANALYTICS_V2_TRACKING=1`, events additionally carry a v2 envelope
 * (event id, sequence, page key, rotating session, visitor id) and a pending queue is
 * also flushed on a 15 s timer. With the variable unset (default) every code path
 * below is byte-for-byte the v1 behaviour.
 */

import { hasAnalyticsConsent } from "./consent";
import { getSessionId } from "./session";
import { buildBatchV2, buildEventV2, type WireEventV2 } from "./v2/envelope";
import {
  currentSessionId,
  forgetAnonId,
  getAnonId,
  isCountsOnly,
  newId,
  touchSession,
} from "./v2/ids";
import { pageKeyFromPath, referrerKind } from "./v2/page-key";

import type { AnalyticsEventMap, AnalyticsEventName } from "./events";
import type { GtagWindow } from "./gtag";

interface QueuedEvent {
  event: string;
  props: Record<string, unknown>;
  ts: number;
}

/** Flush the batch automatically once it reaches this size. */
export const MAX_BATCH = 20;
/** v2: hard cap on pending events (oldest dropped) and the idle flush delay. */
export const MAX_QUEUE_V2 = 50;
export const FLUSH_INTERVAL_MS_V2 = 15_000;

let queue: QueuedEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let lastV2Key = "";
let lastV2At = 0;

/**
 * Build-time switch. Call sites below spell out `process.env.NEXT_PUBLIC_…` literally so
 * Next.js inlines it as a constant (customer next.config defines it, "" by default) and
 * the minifier can drop every v2 branch; it is read at call time so tests can toggle it.
 */
export function isV2Tracking(): boolean {
  return process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING === "1";
}

function currentPageKey(): string {
  return typeof location === "undefined" ? "other" : pageKeyFromPath(location.pathname);
}

function scheduleFlushV2(): void {
  if (flushTimer !== null || typeof setTimeout === "undefined") {
    return;
  }
  flushTimer = setTimeout(() => {
    flushTimer = null;
    flush();
  }, FLUSH_INTERVAL_MS_V2);
}

function enqueueV2(event: string, props: Record<string, unknown>): void {
  const now = Date.now();
  // Drop exact repeats within 1 s (e.g. React StrictMode double effects).
  const key = event + JSON.stringify(props);
  if (key === lastV2Key && now - lastV2At < 1000) {
    return;
  }
  lastV2Key = key;
  lastV2At = now;

  const page = currentPageKey();
  const session = touchSession(now, 2);
  const seq = session?.seq ?? 0;
  if (session?.isNew && event !== "session_start") {
    const own = typeof location === "undefined" ? "" : location.hostname;
    const ref = typeof document === "undefined" ? "" : document.referrer;
    queue.push(
      buildEventV2(
        "session_start",
        { entry_page_key: page, referrer_kind: referrerKind(ref, own) },
        { id: newId(), seq, ts: now, page },
      ),
    );
  }
  queue.push(buildEventV2(event, props, { id: newId(), seq: seq + 1, ts: now, page }));
  if (queue.length > MAX_QUEUE_V2) {
    queue = queue.slice(queue.length - MAX_QUEUE_V2);
  }
  if (queue.length >= MAX_BATCH) {
    flush();
  } else {
    scheduleFlushV2();
  }
}

/** v2: record a page view for the current location (no-op unless v2 tracking is on). */
export function trackPageView(): void {
  if (process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING !== "1" || typeof window === "undefined") {
    return;
  }
  enqueueV2("page_view", {});
}

function beaconEndpoint(): string {
  return process.env.NEXT_PUBLIC_ANALYTICS_ENDPOINT ?? "/api/analytics/collect";
}

function ga4MeasurementId(): string | undefined {
  return process.env.NEXT_PUBLIC_GA4_MEASUREMENT_ID || undefined;
}

function mirrorToGa4(event: string, props: Record<string, unknown>): void {
  if (typeof window === "undefined") {
    return;
  }
  if (!ga4MeasurementId()) {
    return;
  }
  const w = window as GtagWindow;
  if (typeof w.gtag !== "function") {
    return;
  }
  w.gtag("event", event, props);
}

/**
 * Record an analytics event. Enqueues an anonymized server beacon unconditionally
 * and mirrors to GA4 only when consent is granted.
 */
export function track<E extends AnalyticsEventName>(event: E, props: AnalyticsEventMap[E]): void {
  const flatProps: Record<string, unknown> = { ...props };

  // 1. Server beacon — always, anonymized, consent-independent.
  if (process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING === "1") {
    enqueueV2(event, flatProps);
  } else {
    queue.push({ event, props: flatProps, ts: Date.now() });
    if (queue.length >= MAX_BATCH) {
      flush();
    }
  }

  // 2. GA4 mirror — consent-gated.
  if (hasAnalyticsConsent()) {
    mirrorToGa4(event, flatProps);
  }
}

/**
 * Send the batched beacon queue via `navigator.sendBeacon`. Returns true when the
 * browser accepted the beacon. Safe to call when the queue is empty or during SSR.
 */
export function flush(): boolean {
  if (queue.length === 0) {
    return false;
  }
  if (typeof navigator === "undefined" || typeof navigator.sendBeacon !== "function") {
    // No transport available (SSR / unsupported) — drop rather than leak memory.
    queue = [];
    return false;
  }
  const batch = queue;
  queue = [];
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  let body: string;
  if (process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING === "1") {
    const countsOnly = isCountsOnly();
    if (countsOnly) {
      forgetAnonId(); // opt-out rotates the visitor id; opting back in starts fresh
    }
    body = JSON.stringify(
      buildBatchV2(batch as WireEventV2[], {
        app: "customer",
        legacySessionId: countsOnly ? null : getSessionId(),
        anonId: countsOnly ? null : getAnonId(),
        sessionId: countsOnly ? null : currentSessionId(),
        countsOnly,
      }),
    );
  } else {
    // Attach the opaque anonymous session id (never PII) so the server can stitch a
    // visitor's events — and link them to a user id once they authenticate.
    const sessionId = getSessionId();
    body = JSON.stringify(sessionId ? { session_id: sessionId, events: batch } : { events: batch });
  }
  try {
    const blob = new Blob([body], { type: "application/json" });
    return navigator.sendBeacon(beaconEndpoint(), blob);
  } catch {
    return false;
  }
}

/** Test-only: pending beacon count. */
export function __queueLength(): number {
  return queue.length;
}

/** Test-only: reset the beacon queue. */
export function __resetQueue(): void {
  queue = [];
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  lastV2Key = "";
  lastV2At = 0;
}
