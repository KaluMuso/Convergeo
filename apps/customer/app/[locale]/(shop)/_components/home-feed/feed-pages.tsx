"use client";

/**
 * Lazily imported chunk (see home-feed-loader.tsx): renders subsequent feed
 * pages fetched on scroll. Kept out of the first-load bundle.
 */
import { absoluteApiUrl } from "../../../../../lib/api-base-url";
import { fetchJson } from "../../../../../lib/fetch-json";

import { FeedSectionView } from "./feed-section";
import {
  HOME_FEED_PAGE_SIZE,
  isRenderableSection,
  type FeedLabels,
  type FeedSection,
  type HomeFeedPage,
} from "./feed-types";

export async function fetchFeedPage(
  cursor: string,
  locale: string,
  accessToken?: string | null,
): Promise<HomeFeedPage> {
  const url = absoluteApiUrl(
    `/home/feed?cursor=${encodeURIComponent(cursor)}&page_size=${HOME_FEED_PAGE_SIZE}&locale=${encodeURIComponent(locale)}`,
  );
  if (!url) throw new Error("api_unavailable");
  return fetchJson<HomeFeedPage>(url, {
    // A cursor page assembles several rails server-side and takes ~2.8s in
    // production today; the 2s default aborted every attempt, so load-more
    // always failed ("Couldn't load more right now").
    timeoutMs: HOME_FEED_PAGE_TIMEOUT_MS,
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
  });
}

/** Per-attempt timeout for a home feed cursor page (see fetchFeedPage). */
export const HOME_FEED_PAGE_TIMEOUT_MS = 8_000;

export function FeedPages({
  sections,
  locale,
  labels,
}: {
  sections: FeedSection[];
  locale: string;
  labels: FeedLabels;
}) {
  return (
    <>
      {sections.filter(isRenderableSection).map((section) => (
        <FeedSectionView key={section.id} section={section} locale={locale} labels={labels} />
      ))}
    </>
  );
}
