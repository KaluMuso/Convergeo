"use client";

import { Skeleton } from "@vergeo/ui/src/skeleton";
import { lazy, Suspense, useCallback, useMemo, type ReactNode } from "react";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";
import { fetchJson } from "../../../../../lib/fetch-json";
import { ProgressiveLoadControls } from "../progressive-load/progressive-load-controls";
import { useProgressiveLoad, type ProgressivePage } from "../progressive-load/use-progressive-load";

import {
  HOME_STREAM_PAGE_SIZE,
  type FeedLabels,
  type FeedListingWire,
  type HomeStreamPage,
  type StreamLabels,
} from "./feed-types";

const HomeStreamGrid = lazy(() => import("./home-stream-grid"));

/** Stable reference: the hook resets whenever `initialItems` changes identity. */
const NO_ITEMS: FeedListingWire[] = [];
/** Slow 3G: a request may legitimately take several seconds. */
const STREAM_FETCH_TIMEOUT_MS = 12_000;
/** Pages made entirely of already-shown listings are skipped, at most this many. */
const MAX_SKIPPED_PAGES = 3;

export type StreamFetcher = (cursor: string, signal: AbortSignal) => Promise<HomeStreamPage>;

export const fetchStreamPage: StreamFetcher = async (cursor, signal) => {
  const url = absoluteApiUrl(
    `/home/stream?cursor=${encodeURIComponent(cursor)}&limit=${HOME_STREAM_PAGE_SIZE}`,
  );
  if (!url) throw new Error("api_unavailable");
  return fetchJson<HomeStreamPage>(url, { signal, timeoutMs: STREAM_FETCH_TIMEOUT_MS });
};

/**
 * Pull the next page, dropping listings the shopper already sees above (the
 * home sections). If a whole page is duplicates, keep walking the cursor so the
 * IntersectionObserver never stalls on an "empty" page that appended nothing.
 */
export async function loadStreamPage(
  fetcher: StreamFetcher,
  cursor: string,
  signal: AbortSignal,
  seen: ReadonlySet<string>,
): Promise<ProgressivePage<FeedListingWire>> {
  let next: string | null = cursor;
  for (let hop = 0; next && hop <= MAX_SKIPPED_PAGES; hop += 1) {
    const page: HomeStreamPage = await fetcher(next, signal);
    const items = page.items.filter((item) => !seen.has(item.id));
    next = page.next_cursor;
    if (items.length > 0 || !next) return { items, nextCursor: next };
  }
  return { items: [], nextCursor: next };
}

function StreamSkeleton() {
  return (
    <div
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4"
      data-testid="home-stream-skeleton"
      aria-hidden="true"
    >
      {Array.from({ length: 4 }, (_, index) => (
        <Skeleton key={index} shape="block" className="aspect-[3/4] w-full rounded-lg" />
      ))}
    </div>
  );
}

/**
 * Client island for the home "Popular now" stream. The first page arrives as
 * server-rendered `children` (SEO / LCP); this component only ever fetches the
 * pages after it. IntersectionObserver auto-loading, data-saver gating, abort,
 * id de-duplication, retry and the aria-live count all come from
 * `useProgressiveLoad` + `ProgressiveLoadControls` (the same pair PLP uses).
 */
export function HomeStreamClient({
  children,
  initialCursor,
  seenIds,
  locale,
  cardLabels,
  labels,
  fetcher = fetchStreamPage,
}: {
  children: ReactNode;
  initialCursor: string | null;
  /** Listing ids already rendered server-side (sections + first stream page). */
  seenIds: string[];
  locale: string;
  cardLabels: FeedLabels["card"];
  labels: Omit<StreamLabels, "title">;
  fetcher?: StreamFetcher;
}) {
  const seen = useMemo(() => new Set(seenIds), [seenIds]);
  const fetchPage = useCallback(
    (cursor: string, signal: AbortSignal) => loadStreamPage(fetcher, cursor, signal, seen),
    [fetcher, seen],
  );
  const { items, status, hasMore, lastAppendedCount, loadMore, sentinelRef } =
    useProgressiveLoad<FeedListingWire>({
      initialItems: NO_ITEMS,
      initialCursor,
      resetKey: `${locale}|${initialCursor ?? ""}`,
      fetchPage,
    });

  return (
    <>
      {children}
      {items.length > 0 ? (
        <Suspense fallback={<StreamSkeleton />}>
          <HomeStreamGrid items={items} locale={locale} labels={cardLabels} />
        </Suspense>
      ) : null}
      {status === "loading" ? <StreamSkeleton /> : null}
      <ProgressiveLoadControls
        status={status}
        hasMore={hasMore}
        lastAppendedCount={lastAppendedCount}
        labels={labels}
        onLoadMore={loadMore}
        sentinelRef={sentinelRef}
        testIdPrefix="home-stream"
      />
    </>
  );
}
