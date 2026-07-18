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
 */

import { hasAnalyticsConsent } from "./consent";
import type { AnalyticsEventMap, AnalyticsEventName } from "./events";
import type { GtagWindow } from "./gtag";
import { getSessionId } from "./session";

interface QueuedEvent {
  event: string;
  props: Record<string, unknown>;
  ts: number;
}

/** Flush the batch automatically once it reaches this size. */
export const MAX_BATCH = 20;

let queue: QueuedEvent[] = [];

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
  queue.push({ event, props: flatProps, ts: Date.now() });
  if (queue.length >= MAX_BATCH) {
    flush();
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
  // Attach the opaque anonymous session id (never PII) so the server can stitch a
  // visitor's events — and link them to a user id once they authenticate.
  const sessionId = getSessionId();
  const body = JSON.stringify(
    sessionId ? { session_id: sessionId, events: batch } : { events: batch },
  );
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
}
