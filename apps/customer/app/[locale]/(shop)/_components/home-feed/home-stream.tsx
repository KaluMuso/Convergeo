import { absoluteApiUrl } from "../../../../../lib/api-base-url";
import { fetchJson } from "../../../../../lib/fetch-json";
import { ListingGrid } from "../plp/listing-grid";

import {
  HOME_STREAM_PAGE_SIZE,
  mapFeedListing,
  type FeedLabels,
  type FeedListingWire,
  type FeedSection,
  type HomeStreamPage,
  type StreamLabels,
} from "./feed-types";
import { HomeStreamClient } from "./home-stream-client";

const EMPTY_STREAM: HomeStreamPage = { items: [], next_cursor: null };

/**
 * First stream page, fetched during SSR (anonymous, ISR-cacheable). Any failure
 * yields an empty stream so the home renders exactly as it did before.
 */
export async function loadHomeStreamFirstPage(): Promise<HomeStreamPage> {
  const url = absoluteApiUrl(`/home/stream?limit=${HOME_STREAM_PAGE_SIZE}`);
  if (!url) return EMPTY_STREAM;
  try {
    const page = await fetchJson<HomeStreamPage>(url, { next: { revalidate: 60 } });
    return {
      items: Array.isArray(page.items) ? page.items : [],
      next_cursor: typeof page.next_cursor === "string" ? page.next_cursor : null,
    };
  } catch {
    return EMPTY_STREAM;
  }
}

/** Listing ids already shown by feed sections (so the stream never repeats them). */
export function listingIdsOf(sections: FeedSection[]): string[] {
  return sections.flatMap((section) => section.listings.map((listing) => listing.id));
}

/**
 * "Popular now" stream that follows the admin-configured sections. The first
 * batch is rendered on the server; the client island loads the rest.
 */
export function HomeListingStream({
  page,
  sectionListingIds,
  locale,
  cardLabels,
  labels,
}: {
  page: HomeStreamPage;
  sectionListingIds: string[];
  locale: string;
  cardLabels: FeedLabels["card"];
  labels: StreamLabels;
}) {
  const shown = new Set(sectionListingIds);
  const first: FeedListingWire[] = page.items.filter((item) => !shown.has(item.id));
  if (first.length === 0 && !page.next_cursor) return null;
  const { title, ...controlLabels } = labels;
  const seenIds = [...sectionListingIds, ...first.map((item) => item.id)];
  return (
    <section
      aria-labelledby="home-stream-title"
      className="home-rail flex flex-col gap-3 lg:gap-4"
      data-testid="home-stream"
    >
      <h2 id="home-stream-title" className="font-display text-h2 text-display-ink">
        {title}
      </h2>
      <HomeStreamClient
        initialCursor={page.next_cursor}
        seenIds={seenIds}
        locale={locale}
        cardLabels={cardLabels}
        labels={controlLabels}
      >
        {first.length > 0 ? (
          <ListingGrid
            locale={locale}
            listings={first.map(mapFeedListing)}
            labels={cardLabels}
            priorityCount={0}
            density="compact"
          />
        ) : null}
      </HomeStreamClient>
    </section>
  );
}
