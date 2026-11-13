/**
 * Wire types for `GET /home/feed` (services/api/app/services/home_feed/models.py)
 * plus pure mappers shared by the server renderer and the lazy client loader.
 * No server-only imports — this module is bundled into the client chunk.
 */
import type { CatalogListing } from "../plp/listing-grid";

export type FeedListingWire = {
  id: string;
  title: string;
  product_slug: string | null;
  vendor_name: string;
  price_ngwee: number;
  compare_at_ngwee?: number | null;
  condition: string;
  in_stock: boolean;
  image_public_id: string | null;
  rating: number;
  review_count: number;
  distance_m: number | null;
  below_median?: boolean;
  delivery_available?: boolean;
  pickup_available?: boolean;
  sale_unit?: string;
  unit_step_milli?: number;
  min_steps?: number;
  product_class?: string;
};

export type FeedServiceWire = {
  id: string;
  slug: string;
  title: string;
  from_price_ngwee: number | null;
  portfolio_images: string[];
  provider: { display_name: string };
};

export type FeedEventWire = {
  id: string;
  slug: string;
  title: string;
  venue: string | null;
  images: string[];
  next_starts_at: string | null;
  min_price_ngwee: number | null;
  is_free: boolean;
  spots_sold: number;
  spots_total: number;
};

export type FeedVendorWire = {
  id: string;
  slug: string;
  display_name: string;
  logo_url: string | null;
  preferred_badge: boolean;
  verified: boolean;
  landmark: string | null;
  rating_avg: number | null;
  rating_count: number;
  listing_count: number;
};

export type AdCreative = {
  placement_id: string;
  advertiser_name: string;
  image_public_id: string;
  headline: string;
  body: string | null;
  cta_label: string | null;
  cta_href: string;
  external: boolean;
  sponsored: boolean;
};

export type FeedSectionType =
  "category" | "collection" | "rule" | "services" | "events" | "vendors" | "for_you" | "ad_slot";

export type FeedSection = {
  id: string;
  key: string;
  section_type: FeedSectionType;
  layout: "rail" | "grid" | "banner" | "ad";
  title: string | null;
  title_key: string | null;
  view_all_href: string | null;
  listings: FeedListingWire[];
  services: FeedServiceWire[];
  events: FeedEventWire[];
  vendors: FeedVendorWire[];
  ad: AdCreative | null;
  explanation: {
    basis: "personal" | "trending" | "popular";
    top_categories: string[];
  } | null;
};

export type HomeFeedPage = {
  sections: FeedSection[];
  carousel: AdCreative[];
  next_cursor: string | null;
};

export const HOME_FEED_PAGE_SIZE = 4;

/** Serializable label bag built on the server from next-intl and passed down. */
export type FeedLabels = {
  viewAll: string;
  sponsored: string;
  sponsoredBy: string;
  adCta: string;
  loadingMore: string;
  end: string;
  retry: string;
  loadError: string;
  forYouPersonal: string;
  forYouTrending: string;
  free: string;
  fromPrice: string;
  provider: string;
  noReviews: string;
  viewService: string;
  viewEvent: string;
  /** Raw ICU-free template with {filled} and {total}. */
  eventCapacity: string;
  visitStore: string;
  vendorListings: string;
  vendorPreferred: string;
  vendorVerified: string;
  /** home.feed.sections.* → resolved text (for title_key lookups client-side). */
  sectionTitles: Record<string, string>;
  card: {
    vendor: string;
    noReviews: string;
    reviewCount: string;
    quickAdd: string;
    quickAddError?: string;
    wishlist: string;
    wishlistRemove?: string;
    outOfStock: string;
    sampleListing?: string;
    mediaEmpty?: string;
    logistics?: {
      nearest: string;
      belowMedian: string;
      delivery: string;
      pickup: string;
    };
  };
};

export function mapFeedListing(item: FeedListingWire): CatalogListing {
  return {
    id: item.id,
    title: item.title,
    productSlug: item.product_slug,
    vendorName: item.vendor_name,
    priceNgwee: item.price_ngwee,
    oldNgwee: item.compare_at_ngwee ?? undefined,
    condition: item.condition,
    inStock: item.in_stock,
    imagePublicId: item.image_public_id,
    rating: item.rating,
    reviewCount: item.review_count,
    distanceM: item.distance_m,
    belowMedian: item.below_median ?? false,
    deliveryAvailable: item.delivery_available ?? false,
    pickupAvailable: item.pickup_available ?? false,
    saleUnit: item.sale_unit,
    unitStepMilli: item.unit_step_milli,
    minSteps: item.min_steps,
    productClass: item.product_class,
  };
}

const SECTION_KEY_PREFIX = "home.feed.sections.";

/** Per-locale admin text wins; otherwise the i18n key; otherwise no heading. */
export function resolveSectionTitle(section: FeedSection, labels: FeedLabels): string | null {
  if (section.title) return section.title;
  if (section.title_key?.startsWith(SECTION_KEY_PREFIX)) {
    const short = section.title_key.slice(SECTION_KEY_PREFIX.length);
    return labels.sectionTitles[short] ?? null;
  }
  return null;
}

/** Internal hrefs are locale-prefixed; external CTAs (already allow-listed) pass through. */
export function localizeHref(href: string, locale: string): string {
  if (!href.startsWith("/") || href.startsWith("//")) return href;
  const localePrefix = `/${locale}`;
  if (href === localePrefix || href.startsWith(`${localePrefix}/`)) return href;
  if (/^\/(en|bem|nya|fr|zh)(\/|$)/.test(href)) return href;
  return `${localePrefix}${href === "/" ? "" : href}`;
}

/** Sections that must render (non-ad sections need content; ad needs a creative). */
export function isRenderableSection(section: FeedSection): boolean {
  if (section.section_type === "ad_slot") return section.ad !== null;
  return (
    section.listings.length > 0 ||
    section.services.length > 0 ||
    section.events.length > 0 ||
    section.vendors.length > 0
  );
}

/** Wire type for `GET /home/stream` (services/api/app/services/home_feed/stream.py). */
export type HomeStreamPage = {
  items: FeedListingWire[];
  next_cursor: string | null;
};

/** Small pages: ~6 cards is ~3 rows at 360px and a modest JSON payload on 3G. */
export const HOME_STREAM_PAGE_SIZE = 6;

export type StreamLabels = {
  title: string;
  loadMore: string;
  loading: string;
  /** Raw template with `{count}`; announced via aria-live after each load. */
  moreLoaded: string;
  endOfResults: string;
  loadError: string;
  retry: string;
};
