import { shouldShowSampleListingBadge } from "../demo-listing";

import { ListingCard, type ListingCardLabels } from "./listing-card";

export type CatalogListing = {
  id: string;
  title: string;
  productSlug: string | null;
  vendorName: string;
  priceNgwee: number;
  condition: string;
  inStock: boolean;
  imagePublicId: string | null;
  rating: number;
  reviewCount: number;
  distanceM: number | null;
};

type ListingGridLabels = ListingCardLabels;

type ListingGridProps = {
  locale: string;
  listings: CatalogListing[];
  labels: ListingGridLabels;
  /** How many leading cards get priority image loading (LCP). Default keeps PLP behaviour. */
  priorityCount?: number;
  /** Injectable for tests; defaults to production-safe sample gate. */
  showSampleBadge?: boolean;
  density?: "default" | "compact";
};

/**
 * Catalog product grid — RSC-safe shell over client `ListingCard` (wishlist localStorage).
 */
export function ListingGrid({
  locale,
  listings,
  labels,
  priorityCount = 2,
  showSampleBadge = shouldShowSampleListingBadge(),
  density = "default",
}: ListingGridProps) {
  return (
    <div
      data-testid="listing-grid"
      className="motion-fade grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4"
    >
      {listings.map((listing, index) => (
        <ListingCard
          key={listing.id}
          locale={locale}
          listing={listing}
          labels={labels}
          priority={index < priorityCount}
          showSampleBadge={showSampleBadge}
          density={density}
        />
      ))}
    </div>
  );
}
