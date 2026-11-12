/**
 * analytics_v2 client runtime — loaded on demand as an ASYNC chunk (never in a route's
 * first-load JS) by `track.ts` when `NEXT_PUBLIC_ANALYTICS_V2_TRACKING=1`. Holds the
 * session/visitor logic, page-key mapping and envelope building (plan 1A-04/1A-04b).
 */

import { getSessionId } from "../session";

import { buildBatchV2, buildEventV2, type WireEventV2 } from "./envelope";
import {
  currentSessionId,
  forgetAnonId,
  getAnonId,
  isCountsOnly,
  newId,
  touchSession,
} from "./ids";
import { pageKeyFromPath, referrerKind } from "./page-key";

/** An event captured before/while the runtime loads (location data is read at capture). */
export interface CapturedEvent {
  event: string;
  props: Record<string, unknown>;
  ts: number;
  path: string;
  referrer: string;
  host: string;
}

let lastKey = "";
let lastAt = 0;

/**
 * Turn a captured event into v2 wire events appended to `queue` (a `session_start` first
 * when the 30-min session rotated). Exact repeats within 1 s are dropped.
 */
export function enqueueEvent(queue: unknown[], captured: CapturedEvent): void {
  const { event, props, ts } = captured;
  const key = event + JSON.stringify(props);
  if (key === lastKey && ts - lastAt < 1000) {
    return;
  }
  lastKey = key;
  lastAt = ts;

  const page = pageKeyFromPath(captured.path);
  const session = touchSession(ts, 2);
  const seq = session?.seq ?? 0;
  if (session?.isNew && event !== "session_start") {
    queue.push(
      buildEventV2(
        "session_start",
        { entry_page_key: page, referrer_kind: referrerKind(captured.referrer, captured.host) },
        { id: newId(), seq, ts, page },
      ),
    );
  }
  queue.push(buildEventV2(event, props, { id: newId(), seq: seq + 1, ts, page }));
}

/** Serialize a v2 batch. Counts-only (opt-out / GPC) forgets the visitor id, sends none. */
export function buildBody(batch: unknown[]): string {
  const countsOnly = isCountsOnly();
  if (countsOnly) {
    forgetAnonId();
  }
  return JSON.stringify(
    buildBatchV2(batch as WireEventV2[], {
      app: "customer",
      legacySessionId: countsOnly ? null : getSessionId(),
      anonId: countsOnly ? null : getAnonId(),
      sessionId: countsOnly ? null : currentSessionId(),
      countsOnly,
    }),
  );
}

/** Test-only. */
export function __resetRuntime(): void {
  lastKey = "";
  lastAt = 0;
}
