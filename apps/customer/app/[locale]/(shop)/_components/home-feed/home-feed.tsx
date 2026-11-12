import { absoluteApiUrl } from "../../../../../lib/api-base-url";
import { fetchJson } from "../../../../../lib/fetch-json";

import { FeedSectionView } from "./feed-section";
import {
  HOME_FEED_PAGE_SIZE,
  isRenderableSection,
  type FeedLabels,
  type HomeFeedPage,
} from "./feed-types";
import { ForYouSlot } from "./for-you-slot";
import { HomeFeedLoader } from "./home-feed-loader";

const EMPTY_PAGE: HomeFeedPage = {
  sections: [],
  carousel: [],
  next_cursor: null,
};

/**
 * First feed page, server-rendered (anonymous + ISR-cacheable) for fast LCP.
 * Any failure yields an empty page so the home falls back to its default rails.
 */
export async function loadHomeFeedFirstPage(locale: string): Promise<HomeFeedPage> {
  const url = absoluteApiUrl(
    `/home/feed?page_size=${HOME_FEED_PAGE_SIZE}&locale=${encodeURIComponent(locale)}`,
  );
  if (!url) return EMPTY_PAGE;
  try {
    const page = await fetchJson<HomeFeedPage>(url, {
      next: { revalidate: 60 },
    });
    return {
      sections: Array.isArray(page.sections) ? page.sections : [],
      carousel: Array.isArray(page.carousel) ? page.carousel : [],
      next_cursor: typeof page.next_cursor === "string" ? page.next_cursor : null,
    };
  } catch {
    return EMPTY_PAGE;
  }
}

type RawTranslator = {
  (key: string, values?: Record<string, string | number>): string;
  raw: (key: string) => unknown;
};

/** Build the serializable label bag (raw templates for `{…}` placeholders). */
export function buildFeedLabels(t: RawTranslator, card: FeedLabels["card"]): FeedLabels {
  const raw = (key: string) => String(t.raw(key));
  const titlesRaw = t.raw("home.feed.sections");
  const sectionTitles: Record<string, string> = {};
  if (titlesRaw && typeof titlesRaw === "object") {
    for (const [key, value] of Object.entries(titlesRaw as Record<string, unknown>)) {
      if (typeof value === "string") sectionTitles[key] = value;
    }
  }
  return {
    viewAll: t("home.rails.viewAll"),
    sponsored: t("home.feed.sponsored"),
    sponsoredBy: raw("home.feed.sponsoredBy"),
    adCta: t("home.feed.adCta"),
    loadingMore: t("home.feed.loadingMore"),
    end: t("home.feed.end"),
    retry: t("home.feed.retry"),
    loadError: t("home.feed.loadError"),
    forYouPersonal: t("home.feed.forYouPersonal"),
    forYouTrending: t("home.feed.forYouTrending"),
    free: t("home.events.free"),
    fromPrice: t("home.rails.services.fromPrice"),
    provider: raw("home.rails.services.provider"),
    noReviews: t("home.rails.services.noReviews"),
    viewService: t("home.rails.services.view"),
    viewEvent: t("home.events.cta"),
    eventCapacity: raw("home.feed.eventCapacity"),
    visitStore: t("home.rails.vendors.view"),
    vendorListings: t("home.rails.vendors.listings"),
    vendorPreferred: t("home.rails.vendors.preferred"),
    vendorVerified: t("home.rails.vendors.verified"),
    sectionTitles,
    card,
  };
}

export function HomeFeed({
  page,
  locale,
  labels,
}: {
  page: HomeFeedPage;
  locale: string;
  labels: FeedLabels;
}) {
  const sections = page.sections.filter(isRenderableSection);
  let listingSectionsSeen = 0;
  return (
    <div className="flex flex-col gap-6 lg:gap-10" data-testid="home-feed">
      {sections.map((section) => {
        const priorityCount = section.listings.length > 0 && listingSectionsSeen++ === 0 ? 2 : 0;
        const view = (
          <FeedSectionView
            key={section.id}
            section={section}
            locale={locale}
            labels={labels}
            priorityCount={priorityCount}
          />
        );
        return section.section_type === "for_you" ? (
          <ForYouSlot key={section.id} locale={locale} labels={labels}>
            {view}
          </ForYouSlot>
        ) : (
          view
        );
      })}
      <HomeFeedLoader initialCursor={page.next_cursor} locale={locale} labels={labels} />
    </div>
  );
}
