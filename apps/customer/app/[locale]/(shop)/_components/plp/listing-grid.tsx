import { Badge } from "@vergeo/ui/src/badge";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { ProductCard } from "@vergeo/ui/src/product-card";
import Link from "next/link";

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

type ListingGridLabels = {
  vendor: string;
  noReviews: string;
  reviewCount: string;
  quickAdd: string;
  wishlist: string;
  outOfStock: string;
  distance: string;
};

type ListingGridProps = {
  locale: string;
  listings: CatalogListing[];
  labels: ListingGridLabels;
  /** How many leading cards get priority image loading (LCP). Default keeps PLP behaviour. */
  priorityCount?: number;
};

function formatDistance(meters: number | null): string | null {
  if (meters === null) {
    return null;
  }
  if (meters < 1000) {
    return `${Math.round(meters)} m`;
  }
  return `${(meters / 1000).toFixed(1)} km`;
}

export function ListingGrid({ locale, listings, labels, priorityCount = 2 }: ListingGridProps) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
      {listings.map((listing, index) => {
        const distance = formatDistance(listing.distanceM);
        const distanceLabel =
          distance !== null ? labels.distance.replace("{distance}", distance) : undefined;

        const card = (
          <ProductCard
            title={listing.title}
            vendorLabel={labels.vendor.replace("{vendor}", listing.vendorName)}
            ngwee={listing.priceNgwee}
            rating={listing.rating}
            reviewCount={listing.reviewCount}
            noReviewsLabel={labels.noReviews}
            reviewCountLabel={labels.reviewCount}
            quickAddLabel={labels.quickAdd}
            wishlistLabel={labels.wishlist}
            badge={
              !listing.inStock ? (
                <Badge variant="sold_out" label={labels.outOfStock} />
              ) : distanceLabel ? (
                <Badge variant="public" label={distanceLabel} />
              ) : undefined
            }
            media={
              listing.imagePublicId ? (
                <CloudinaryImage
                  publicId={listing.imagePublicId}
                  alt={listing.title}
                  width={360}
                  ratio="4/3"
                  priority={index < priorityCount}
                  sizes="(max-width: 360px) 50vw, (max-width: 720px) 33vw, 25vw"
                  className="h-full w-full object-cover"
                />
              ) : undefined
            }
          />
        );

        // Never invent a product URL — a missing slug is not "all products".
        if (!listing.productSlug) {
          return (
            <div
              key={listing.id}
              className="min-w-0"
              data-testid="listing-card-no-slug"
              aria-label={listing.title}
            >
              {card}
            </div>
          );
        }

        return (
          <Link
            key={listing.id}
            href={`/${locale}/p/${listing.productSlug}`}
            className="min-w-0 no-underline"
          >
            {card}
          </Link>
        );
      })}
    </div>
  );
}
