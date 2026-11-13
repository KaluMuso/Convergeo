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
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
  });
}

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
