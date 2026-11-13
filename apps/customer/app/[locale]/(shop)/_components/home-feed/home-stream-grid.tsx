import { ListingGrid } from "../plp/listing-grid";

import { mapFeedListing, type FeedLabels, type FeedListingWire } from "./feed-types";

/**
 * Grid for stream pages appended on the client. Lazily imported by
 * home-stream-client.tsx so it only ships once a second page is requested.
 */
export default function HomeStreamGrid({
  items,
  locale,
  labels,
}: {
  items: FeedListingWire[];
  locale: string;
  labels: FeedLabels["card"];
}) {
  return (
    <ListingGrid
      locale={locale}
      listings={items.map(mapFeedListing)}
      labels={labels}
      priorityCount={0}
      density="compact"
    />
  );
}
