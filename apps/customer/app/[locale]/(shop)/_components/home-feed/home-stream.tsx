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
import { HomeStreamClient } from "./home-stream-client-lazy";
import { HomeStreamEmpty, type HomeStreamEmptyLabels } from "./home-stream-empty";

export type HomeStreamFirstPageResult =
  { status: "ok"; page: HomeStreamPage } | { status: "error" };

/**
 * First stream page, fetched during SSR (anonymous, ISR-cacheable). Failures are
 * distinct from an empty catalogue so the UI never shows the marketing empty
 * state when the API could not be reached.
 */
export async function loadHomeStreamFirstPage(): Promise<HomeStreamFirstPageResult> {
  const url = absoluteApiUrl(`/home/stream?limit=${HOME_STREAM_PAGE_SIZE}`);
  if (!url) return { status: "error" };
  try {
    const page = await fetchJson<HomeStreamPage>(url, {
      next: { revalidate: 60 },
    });
    return {
      status: "ok",
      page: {
        items: Array.isArray(page.items) ? page.items : [],
        next_cursor: typeof page.next_cursor === "string" ? page.next_cursor : null,
      },
    };
  } catch {
    return { status: "error" };
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
export type HomeStreamSectionLabels = StreamLabels & {
  empty: HomeStreamEmptyLabels;
};

export function HomeListingStream({
  stream,
  sectionListingIds,
  locale,
  cardLabels,
  labels,
}: {
  stream: HomeStreamFirstPageResult;
  sectionListingIds: string[];
  locale: string;
  cardLabels: FeedLabels["card"];
  labels: HomeStreamSectionLabels;
}) {
  if (stream.status === "error") {
    return null;
  }

  const page = stream.page;
  const shown = new Set(sectionListingIds);
  const first: FeedListingWire[] = page.items.filter((item) => !shown.has(item.id));
  const { title, empty, ...controlLabels } = labels;

  if (first.length === 0 && !page.next_cursor) {
    if (page.items.length > 0) {
      return null;
    }
    return (
      <section
        aria-labelledby="home-stream-title"
        className="home-rail flex flex-col gap-3 lg:gap-4"
        data-testid="home-stream"
      >
        <h2 id="home-stream-title" className="font-display text-h2 text-display-ink">
          {title}
        </h2>
        <HomeStreamEmpty locale={locale} labels={empty} />
      </section>
    );
  }

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
