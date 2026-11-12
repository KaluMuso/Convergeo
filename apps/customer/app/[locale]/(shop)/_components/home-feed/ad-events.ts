import { absoluteApiUrl } from "../../../../../lib/api-base-url";

/**
 * Fire-and-forget sponsored-placement beacons (impression once per page view,
 * click on activation). Batches within a short delay; failures are swallowed —
 * reporting must never affect shopping.
 */
type AdEventKind = "impression" | "click";

const BATCH_DELAY_MS = 400;
const MAX_BATCH = 20;
const seenImpressions = new Set<string>();
let queue: Array<{ placement_id: string; kind: AdEventKind }> = [];
let timer: ReturnType<typeof setTimeout> | null = null;

function flush(): void {
  timer = null;
  const batch = queue.slice(0, MAX_BATCH);
  queue = queue.slice(MAX_BATCH);
  if (batch.length === 0) return;
  const url = absoluteApiUrl("/home/ads/events");
  if (!url || typeof navigator === "undefined") return;
  const body = JSON.stringify({ events: batch });
  try {
    const sent =
      typeof navigator.sendBeacon === "function" &&
      navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
    if (!sent) {
      void fetch(url, {
        method: "POST",
        body,
        headers: { "Content-Type": "application/json" },
        keepalive: true,
      }).catch(() => undefined);
    }
  } catch {
    // Telemetry is best-effort.
  }
  if (queue.length > 0) schedule();
}

function schedule(): void {
  if (timer === null) timer = setTimeout(flush, BATCH_DELAY_MS);
}

export function recordAdEvent(placementId: string, kind: AdEventKind): void {
  if (kind === "impression") {
    if (seenImpressions.has(placementId)) return;
    seenImpressions.add(placementId);
  }
  queue.push({ placement_id: placementId, kind });
  if (kind === "click") {
    flush();
    return;
  }
  schedule();
}

/** Test seam. */
export function resetAdEventsForTest(): void {
  seenImpressions.clear();
  queue = [];
  if (timer !== null) clearTimeout(timer);
  timer = null;
}
