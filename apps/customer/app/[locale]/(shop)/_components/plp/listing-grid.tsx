import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";

import { shouldShowSampleListingBadge } from "../demo-listing";

import { ListingCard, type ListingCardLabels } from "./listing-card";

export type CatalogListing = {
  id: string;
  title: string;
  productSlug: string | null;
  vendorName: string;
  priceNgwee: number;
  /** Optional compare-at price in ngwee; struck through when > priceNgwee. */
  oldNgwee?: number;
  condition: string;
  inStock: boolean;
  imagePublicId: string | null;
  rating: number;
  reviewCount: number;
  distanceM: number | null;
  belowMedian: boolean;
  deliveryAvailable: boolean;
  pickupAvailable: boolean;
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

const LISTING_MEDIA_SIZES = "(max-width: 360px) 50vw, (max-width: 720px) 33vw, 25vw";

/**
 * Catalog product grid — media is rendered here (RSC-safe static Cloudinary) and
 * passed into client `ListingCard` (wishlist / quick-add only).
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
      className="motion-fade grid grid-cols-2 gap-2 sm:gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
    >
      {listings.map((listing, index) => {
        const priority = index < priorityCount;
        const media = listing.imagePublicId ? (
          <CloudinaryImageStatic
            publicId={listing.imagePublicId}
            alt={listing.title}
            width={360}
            ratio="4/3"
            priority={priority}
            sizes={LISTING_MEDIA_SIZES}
            className="h-full w-full object-cover"
          />
        ) : undefined;

        return (
          <ListingCard
            key={listing.id}
            locale={locale}
            listing={listing}
            labels={labels}
            media={media}
            showSampleBadge={showSampleBadge}
            density={density}
          />
        );
      })}
    </div>
  );
}
