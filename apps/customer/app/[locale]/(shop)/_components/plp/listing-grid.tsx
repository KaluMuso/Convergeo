import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import { Rail } from "@vergeo/ui/src/rail";

import { shouldShowSampleListingBadge } from "../demo-listing";

import { ListingCard, type ListingCardLabels } from "./listing-card";

import type { OfferBadge } from "../offers/offer-badge";
import type { ReactNode } from "react";

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
  saleUnit?: string;
  unitStepMilli?: number;
  minSteps?: number;
  productClass?: string;
  fulfilmentMode?: string;
  leadTimeDays?: number | null;
  /** W8 offers: live offer this listing takes part in (flag `bundles`). */
  offerBadge?: OfferBadge;
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
  /**
   * `grid` (default): dense responsive grid, 2 cols at 360px up to 6 on desktop.
   * `rail`: single horizontally scrolling row (deal / department rails).
   */
  layout?: "grid" | "rail";
  /**
   * `plp` (default): dense responsive grid up to 6 columns on very wide screens.
   * `account`: account saved/following — 2→3→4 columns without extra breakpoints.
   */
  gridDensity?: "plp" | "account";
  /** Optional per-card action rendered under the card (e.g. storefront compare). */
  renderFooter?: (listing: CatalogListing) => ReactNode;
};

const LISTING_MEDIA_SIZES = "(max-width: 360px) 50vw, (max-width: 720px) 33vw, 25vw";

const GRID_CLASS = {
  plp: "motion-fade grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6",
  account: "motion-fade grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4",
} as const;

function GridWrapper({
  children,
  gridDensity = "plp",
}: {
  children: ReactNode;
  gridDensity?: "plp" | "account";
}) {
  return (
    <div data-testid="listing-grid" data-layout="grid" className={GRID_CLASS[gridDensity]}>
      {children}
    </div>
  );
}

function RailWrapper({ children }: { children: ReactNode }) {
  return (
    <Rail
      as="ul"
      snap
      data-testid="listing-grid"
      data-layout="rail"
      className="motion-fade m-0 flex list-none gap-2 p-0 pb-1 pt-1 [&>li]:w-[8.75rem] [&>li]:shrink-0 [&>li]:snap-start sm:[&>li]:w-40 lg:[&>li]:w-44"
    >
      {children}
    </Rail>
  );
}

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
  density = "compact",
  layout = "grid",
  gridDensity = "plp",
  renderFooter,
}: ListingGridProps) {
  const isRail = layout === "rail";

  const cards = listings.map((listing, index) => {
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

    const card = (
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
    if (isRail) return <li key={listing.id}>{card}</li>;
    const footer = renderFooter?.(listing);
    if (!footer) {
      return card;
    }
    return (
      <div key={listing.id} className="flex min-w-0 flex-col gap-1.5">
        {card}
        {footer}
      </div>
    );
  });

  if (isRail) {
    return <RailWrapper>{cards}</RailWrapper>;
  }
  return <GridWrapper gridDensity={gridDensity}>{cards}</GridWrapper>;
}
