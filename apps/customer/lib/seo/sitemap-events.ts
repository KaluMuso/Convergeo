/**
 * Events sitemap chunk (M10-P09).
 *
 * Not a Next.js route on its own — imported by `sitemap-build.ts` for the
 * events chunk. Lists published events for indexing and drops stale ones
 * (last instance ended more than 30 days ago). Past-but-recent events stay
 * listed.
 *
 * The public `/events` list returns only currently-listable (upcoming)
 * published events, so stale events are already excluded at the source; the
 * `next_starts_at` guard below is defence-in-depth against the API ever
 * returning an aged instance and keeps the 30-day policy explicit here.
 */

import { getApiBaseUrl } from "../api-base-url";

/** Mirror of the detail page's noindex grace window (see event-jsonld.tsx). */
export const EVENT_SITEMAP_STALE_DAYS = 30;
const STALE_MS = EVENT_SITEMAP_STALE_DAYS * 24 * 60 * 60 * 1000;
const EVENT_DURATION_MS = 2 * 60 * 60 * 1000;

type EventsListItem = {
  slug: string;
  next_starts_at?: string | null;
};

type EventsListResponse = {
  items: EventsListItem[];
};

/**
 * True when an event's latest known instance ended more than the grace window
 * ago and should be excluded from the sitemap. Unknown dates are kept (listed).
 */
export function isEventStaleForSitemap(
  latestInstanceIso: string | null | undefined,
  now: number = Date.now(),
): boolean {
  if (!latestInstanceIso) {
    return false;
  }
  const start = new Date(latestInstanceIso).getTime();
  if (!Number.isFinite(start)) {
    return false;
  }
  return start + EVENT_DURATION_MS < now - STALE_MS;
}

/** Slugs of published, non-stale events for the sitemap events chunk. */
export async function fetchEventSitemapSlugs(now: number = Date.now()): Promise<string[]> {
  const base = getApiBaseUrl();
  if (!base) {
    return [];
  }
  try {
    const response = await fetch(`${base}/events`, {
      next: { revalidate: 3600 },
    });
    if (!response.ok) {
      return [];
    }
    const payload = (await response.json()) as EventsListResponse;
    return payload.items
      .filter((item) => !isEventStaleForSitemap(item.next_starts_at, now))
      .map((item) => item.slug);
  } catch {
    return [];
  }
}
