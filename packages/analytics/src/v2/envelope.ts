/**
 * Analytics v2 wire envelope (Convergeo Intelligence, plan 1A-01).
 *
 * A v2 batch is a strict SUPERSET of the v1 beacon body `{session_id?, events:[{event,
 * props, ts}]}`: a v1 server (collect flag off) ignores the extra keys and behaves
 * exactly as before. Pure helpers only — no browser access, no side effects.
 *
 * The registry (`../../registry/events.v2.json`) is the single source of truth for
 * event names, versions and prop allowlists; the server re-validates everything.
 * Money is never sent as a source of truth (authoritative tables only).
 */

export const ENVELOPE_VERSION = 2 as const;

/** Every registered v2 event name (parity with the registry JSON is unit-tested). */
export const V2_EVENT_NAMES = [
  "session_start",
  "page_view",
  "search",
  "product_view",
  "product_share",
  "recommendation_impression",
  "recommendation_click",
] as const;

export type V2EventName = (typeof V2_EVENT_NAMES)[number];

/** Registered schema version per event; bump on a breaking prop change. */
export const V2_EVENT_VERSIONS: Record<V2EventName, number> = {
  session_start: 1,
  page_view: 1,
  search: 1,
  product_view: 1,
  product_share: 1,
  recommendation_impression: 1,
  recommendation_click: 1,
};

export type SourceApp = "customer" | "vendor" | "admin";

export type ReferrerKind = "direct" | "search" | "social" | "internal" | "other";

/** One event on the wire. `event`/`props`/`ts` are the v1 fields. */
export interface WireEventV2 {
  event: string;
  props: Record<string, unknown>;
  ts: number;
  /** Client-generated UUID; the server dedups on it (retries/double flushes are free). */
  id: string;
  /** Registered event version. */
  ev: number;
  /** Monotonic per-session sequence number (journey ordering). */
  seq: number;
  /** Page template key (never a URL or slug). */
  page?: string;
}

/** A batch on the wire. `session_id` keeps its v1 meaning (legacy persistent id). */
export interface WireBatchV2 {
  v: typeof ENVELOPE_VERSION;
  app: SourceApp;
  /** Legacy v1 persistent id — kept so a v1 server stores what it always stored. */
  session_id?: string;
  /** Pseudonymous visitor id; omitted in counts-only (opt-out / GPC) mode. */
  anon?: string;
  /** Rotating session id (30-min inactivity); omitted in counts-only mode. */
  sid?: string;
  /** "denied" when the visitor opted out — the server then stores no identifiers. */
  consent?: "denied";
  events: WireEventV2[];
}

export interface EventContext {
  id: string;
  seq: number;
  ts: number;
  page?: string;
}

/** Build one v2 wire event; unknown event names fall back to version 1. */
export function buildEventV2(
  event: string,
  props: Record<string, unknown>,
  ctx: EventContext,
): WireEventV2 {
  const ev = (V2_EVENT_VERSIONS as Record<string, number | undefined>)[event] ?? 1;
  const wire: WireEventV2 = { event, props, ts: ctx.ts, id: ctx.id, ev, seq: ctx.seq };
  if (ctx.page) {
    wire.page = ctx.page;
  }
  return wire;
}

export interface BatchIdentity {
  app: SourceApp;
  legacySessionId: string | null;
  anonId: string | null;
  sessionId: string | null;
  countsOnly: boolean;
}

/** Assemble a v2 batch. In counts-only mode no identifier of any kind is attached. */
export function buildBatchV2(events: WireEventV2[], identity: BatchIdentity): WireBatchV2 {
  const batch: WireBatchV2 = { v: ENVELOPE_VERSION, app: identity.app, events };
  if (identity.countsOnly) {
    batch.consent = "denied";
    return batch;
  }
  if (identity.legacySessionId) {
    batch.session_id = identity.legacySessionId;
  }
  if (identity.anonId) {
    batch.anon = identity.anonId;
  }
  if (identity.sessionId) {
    batch.sid = identity.sessionId;
  }
  return batch;
}
