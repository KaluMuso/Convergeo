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

import type { AnalyticsEventMap, AnalyticsEventName } from "./events";
import type { GtagWindow } from "./gtag";
import type { CapturedEvent } from "./v2/runtime";

interface QueuedEvent {
  event: string;
  props: Record<string, unknown>;
  ts: number;
}

type V2Runtime = typeof import("./v2/runtime");

/** Flush the batch automatically once it reaches this size. */
export const MAX_BATCH = 20;
/** v2: hard cap on pending events (oldest dropped) and the idle flush delay. */
export const MAX_QUEUE_V2 = 50;
export const FLUSH_INTERVAL_MS_V2 = 15_000;

let queue: QueuedEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
// v2 runtime is an async chunk; events captured before it loads wait here.
let v2Runtime: V2Runtime | null = null;
let v2Loading: Promise<void> | null = null;
let v2Pending: CapturedEvent[] = [];

/**
 * Build-time switch. Call sites below spell out `process.env.NEXT_PUBLIC_…` literally so
 * Next.js inlines it as a constant (customer next.config defines it, "" by default) and
 * the minifier can drop every v2 branch; it is read at call time so tests can toggle it.
 */
export function isV2Tracking(): boolean {
  return process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING === "1";
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

function afterEnqueueV2(): void {
  if (queue.length > MAX_QUEUE_V2) {
    queue = queue.slice(queue.length - MAX_QUEUE_V2);
  }
  if (queue.length >= MAX_BATCH) {
    flush();
  } else {
    scheduleFlushV2();
  }
}

function loadV2Runtime(): Promise<void> {
  if (v2Loading === null) {
    v2Loading = import("./v2/runtime").then(
      (mod) => {
        v2Runtime = mod;
        const pending = v2Pending;
        v2Pending = [];
        for (const captured of pending) {
          mod.enqueueEvent(queue, captured);
        }
        afterEnqueueV2();
      },
      () => {
        v2Loading = null; // chunk failed (offline): retry on the next event
      },
    );
  }
  return v2Loading;
}

function enqueueV2(event: string, props: Record<string, unknown>): void {
  const captured: CapturedEvent = {
    event,
    props,
    ts: Date.now(),
    path: typeof location === "undefined" ? "" : location.pathname,
    referrer: typeof document === "undefined" ? "" : document.referrer,
    host: typeof location === "undefined" ? "" : location.hostname,
  };
  if (v2Runtime !== null) {
    v2Runtime.enqueueEvent(queue, captured);
    afterEnqueueV2();
    return;
  }
  v2Pending.push(captured);
  if (v2Pending.length > MAX_QUEUE_V2) {
    v2Pending.shift();
  }
  void loadV2Runtime();
  scheduleFlushV2();
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
  if (process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING === "1" && v2Pending.length > 0) {
    // Runtime not loaded yet (e.g. tab hidden within ms of the first event): degrade to
    // the v1 shape, which every server version accepts, rather than lose the events.
    for (const captured of v2Pending) {
      queue.push({ event: captured.event, props: captured.props, ts: captured.ts });
    }
    v2Pending = [];
  }
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
  const isV2Batch =
    process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING === "1" &&
    v2Runtime !== null &&
    batch.every((item) => "id" in item);
  let body: string;
  if (isV2Batch && v2Runtime !== null) {
    body = v2Runtime.buildBody(batch);
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
  v2Pending = [];
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  v2Runtime?.__resetRuntime();
}

/** Test-only: load the v2 runtime chunk now (it otherwise loads on the first v2 event). */
export async function __loadV2RuntimeForTests(): Promise<void> {
  await loadV2Runtime();
}

/** Test-only: forget the loaded v2 runtime (simulates the chunk not having loaded yet). */
export function __unloadV2RuntimeForTests(): void {
  v2Runtime = null;
  v2Loading = null;
  v2Pending = [];
}
