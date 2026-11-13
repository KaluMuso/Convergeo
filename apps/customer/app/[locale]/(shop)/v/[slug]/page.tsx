import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { brandThemeStyle } from "@vergeo/ui/src/brand-theme";
import { CornerRibbon } from "@vergeo/ui/src/corner-ribbon";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import {
  buildCanonicalAlternates,
  buildLocaleCanonical,
  buildLocalBusinessJsonLd,
  JsonLdScript,
} from "@vergeo/ui/src/seo/json-ld";
import { Tabs, type TabItem } from "@vergeo/ui/src/tabs";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";
import { ShareLinkButton } from "../../../_components/share-link-button";
import { buildStorefrontCompare } from "../../_components/directory/business-home/compare-other-shops";
import {
  ClipsRow,
  directionsHref,
  FindUsSection,
  OffersSection,
  ReviewsSection,
  servicePriceLine,
  StorySection,
  type BusinessBranch,
  type ServiceLabels,
} from "../../_components/directory/business-home/sections";
import {
  visibleSections,
  type BusinessSectionKey,
} from "../../_components/directory/business-home/visible-sections";
import { FollowVendorButton } from "../../_components/directory/follow-vendor-button";
import {
  StorefrontProducts,
  type StorefrontListing,
} from "../../_components/directory/storefront-products";
import {
  buildVendorLadderLabels,
  vendorTrustRibbon,
} from "../../_components/directory/vendor-ladder-labels";
import { catalogDeliveryLabels } from "../../_components/plp/delivery-labels";
import { catalogLogisticsLabels } from "../../_components/plp/logistics-pills";

import type { DaySchedule } from "../../_components/directory/business-home/open-status";
import type { Metadata } from "next";

export const revalidate = 3600;

type VendorLocation = {
  landmark: string;
  lat: number;
  lng: number;
  hours: Record<string, unknown>;
  /** Normalised open days (API); absent on older API builds. */
  schedule?: DaySchedule[];
};

type VendorProfileApiResponse = {
  vendor: {
    id: string;
    slug: string;
    display_name: string;
    description: string | null;
    logo_url: string | null;
    cover_url: string | null;
    whatsapp_msisdn: string | null;
    preferred_badge: boolean;
    kyc_tier: number | null;
    commercial_tier: string | null;
    verified: boolean;
    order_count: number;
    location: VendorLocation | null;
    locations: VendorLocation[];
    created_at: string | null;
    brand_theme?: { primary: string | null; accent: string | null } | null;
  };
  listings: Array<{
    id: string;
    title: string;
    product_slug: string | null;
    price_ngwee: number;
    condition: string;
    in_stock: boolean;
    image_public_id: string | null;
    product_class: string;
    sale_unit: string;
    unit_step_milli: number;
    min_steps: number;
    fulfilment_mode: string;
    lead_time_days: number | null;
    category_slug?: string | null;
    category_name?: string | null;
    delivery_available?: boolean;
    pickup_available?: boolean;
    other_offers_count?: number;
    other_min_price_ngwee?: number | null;
  }>;
  services: Array<{
    id: string;
    title: string;
    category: string | null;
    from_price_ngwee: number | null;
    image_public_id: string | null;
    service_area?: string | null;
    bookable?: boolean;
    booking_price_ngwee?: number | null;
  }>;
  events: Array<{
    id: string;
    slug: string;
    title: string;
    image_public_id: string | null;
  }>;
  reviews_summary: {
    rating_avg: number | null;
    rating_count: number;
  };
  clips?: Array<{
    id: string;
    poster_url: string | null;
    caption: string | null;
  }>;
  offers?: Array<{ id: string; title: string; ends_at: string | null }>;
  offers_enabled?: boolean;
  /** Flag ON and ≥1 live item, per section (API). Absent on older API builds. */
  sections?: Partial<Record<BusinessSectionKey, boolean>>;
};

type PageProps = {
  params: Promise<{ locale: string; slug: string }>;
};

type DirectoryTranslator = {
  (key: string, values?: Record<string, string | number>): string;
  raw: (key: string) => unknown;
};

async function getDirectoryTranslator(locale: string): Promise<DirectoryTranslator> {
  const baseMessages = await getMessages();
  const directoryMessages = await loadNamespace(locale as Locale, "directory");
  const messages = {
    ...baseMessages,
    directory: directoryMessages,
  } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "directory",
  }) as unknown as DirectoryTranslator;
}

async function getCatalogTranslator(locale: string): Promise<DirectoryTranslator> {
  const baseMessages = await getMessages();
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const messages = {
    ...baseMessages,
    catalog: catalogMessages,
  } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "catalog",
  }) as unknown as DirectoryTranslator;
}

async function fetchVendorProfile(slug: string): Promise<VendorProfileApiResponse | null> {
  try {
    const url = absoluteApiUrl(`/directory/${encodeURIComponent(slug)}`);
    if (!url) {
      return null;
    }
    const response = await fetch(url, {
      next: {
        revalidate,
        tags: [`vendor:${slug}`, "directory"],
      },
    });
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as VendorProfileApiResponse;
  } catch {
    return null;
  }
}

function buildVendorJsonLd(
  vendor: VendorProfileApiResponse["vendor"],
  reviews: VendorProfileApiResponse["reviews_summary"],
  locale: string,
): Record<string, unknown> {
  return buildLocalBusinessJsonLd({
    name: vendor.display_name,
    slug: vendor.slug,
    locale,
    description: vendor.description,
    logoUrl: vendor.logo_url,
    landmark: vendor.location?.landmark ?? null,
    lat: vendor.location?.lat ?? null,
    lng: vendor.location?.lng ?? null,
    aggregateRating:
      reviews.rating_count > 0 && reviews.rating_avg !== null
        ? { ratingValue: reviews.rating_avg, reviewCount: reviews.rating_count }
        : null,
  });
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  const profile = await fetchVendorProfile(slug);
  if (!profile) {
    return {
      title: "Vendor not found",
      robots: { index: false, follow: false },
    };
  }

  const t = await getDirectoryTranslator(locale);
  const description = t("profile.metaDescription", {
    name: profile.vendor.display_name,
  });
  const canonicalPath = buildLocaleCanonical(locale, "v", profile.vendor.slug);
  const ogParams = new URLSearchParams({ name: profile.vendor.display_name });

  return {
    title: t("profile.shareTitle", { name: profile.vendor.display_name }),
    description,
    alternates: buildCanonicalAlternates(locale, "v", profile.vendor.slug),
    openGraph: {
      title: profile.vendor.display_name,
      description: profile.vendor.description ?? description,
      type: "website",
      locale,
      url: canonicalPath,
      // The business's own sign comes first on a shared link (§8.5).
      images: profile.vendor.logo_url
        ? [profile.vendor.logo_url]
        : profile.vendor.cover_url
          ? [profile.vendor.cover_url]
          : [
              {
                url: `${buildLocaleCanonical(locale)}/opengraph-image?${ogParams.toString()}`,
              },
            ],
    },
    twitter: {
      card: "summary_large_image",
      title: profile.vendor.display_name,
      description,
    },
    robots: { index: true, follow: true },
  };
}

function VendorServicesGrid({
  locale,
  services,
  labels,
}: {
  locale: string;
  services: VendorProfileApiResponse["services"];
  labels: ServiceLabels;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
      {services.map((service) => (
        <Link
          key={service.id}
          href={`/${locale}/s/${service.id}`}
          className="card-lift block overflow-hidden rounded-lg border border-border bg-surface no-underline shadow-1"
        >
          <div className="aspect-[4/3] w-full bg-bg-2">
            {service.image_public_id ? (
              <CloudinaryImageStatic
                publicId={service.image_public_id}
                alt={service.title}
                width={360}
                ratio="4/3"
                className="h-full w-full object-cover"
              />
            ) : null}
          </div>
          <div className="space-y-1 p-3">
            <p className="truncate text-sm font-medium text-text">{service.title}</p>
            <p className="text-sm font-semibold text-text" data-testid="service-price">
              {servicePriceLine(service, labels)}
            </p>
            {service.service_area ? (
              <p className="truncate text-xs text-text-2">{labels.area(service.service_area)}</p>
            ) : null}
          </div>
        </Link>
      ))}
    </div>
  );
}

function VendorEventsGrid({
  locale,
  events,
}: {
  locale: string;
  events: VendorProfileApiResponse["events"];
}) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
      {events.map((event) => (
        <Link
          key={event.id}
          href={`/${locale}/e/${event.slug}`}
          className="card-lift block overflow-hidden rounded-lg border border-border bg-surface no-underline shadow-1"
        >
          <div className="aspect-[4/3] w-full bg-bg-2">
            {event.image_public_id ? (
              <CloudinaryImageStatic
                publicId={event.image_public_id}
                alt={event.title}
                width={360}
                ratio="4/3"
                className="h-full w-full object-cover"
              />
            ) : null}
          </div>
          <div className="p-3">
            <p className="truncate text-sm font-medium text-text">{event.title}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}

export default async function VendorProfilePage({ params }: PageProps) {
  const { locale, slug } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const [t, tCatalog, profile, baseMessages] = await Promise.all([
    getDirectoryTranslator(locale),
    getCatalogTranslator(locale),
    fetchVendorProfile(slug),
    getMessages(),
  ]);
  const shareLabel = createTranslator({
    locale,
    messages: baseMessages as AbstractIntlMessages,
    namespace: "common",
  })("share.label");

  if (!profile) {
    notFound();
  }

  const { vendor, listings, services, events, reviews_summary: reviews } = profile;
  const clips = profile.clips ?? [];
  const offers = profile.offers ?? [];
  const show = visibleSections({
    counts: {
      products: listings.length,
      services: services.length,
      events: events.length,
      offers: offers.length,
      clips: clips.length,
    },
    sections: profile.sections,
    offersEnabled: profile.offers_enabled,
  });
  const ladderLabels = buildVendorLadderLabels(t);
  const trustRibbon = vendorTrustRibbon(
    { preferredBadge: vendor.preferred_badge, kycTier: vendor.kyc_tier },
    ladderLabels,
  );
  const compareLabels = {
    count: (count: number) => t("profile.home.compareOthers", { count }),
    from: (priceNgwee: number) => t("profile.home.compareFrom", { price: formatK(priceNgwee) }),
    aria: (title: string) => t("profile.home.compareAria", { title }),
  };
  // Commercial tier (Bronze…Platinum) is a vendor plan — never shown to buyers.
  const listingsForGrid: StorefrontListing[] = listings.map((listing) => ({
    categorySlug: listing.category_slug ?? null,
    categoryName: listing.category_name ?? null,
    id: listing.id,
    title: listing.title,
    productSlug: listing.product_slug,
    vendorName: vendor.display_name,
    priceNgwee: listing.price_ngwee,
    condition: listing.condition,
    inStock: listing.in_stock,
    imagePublicId: listing.image_public_id,
    rating: reviews.rating_avg ?? 0,
    reviewCount: reviews.rating_count,
    distanceM: null,
    belowMedian: false,
    deliveryAvailable: listing.delivery_available ?? false,
    pickupAvailable: listing.pickup_available ?? false,
    saleUnit: listing.sale_unit,
    unitStepMilli: listing.unit_step_milli,
    minSteps: listing.min_steps,
    productClass: listing.product_class,
    fulfilmentMode: listing.fulfilment_mode,
    leadTimeDays: listing.lead_time_days,
    compare: buildStorefrontCompare({
      locale,
      productSlug: listing.product_slug,
      title: listing.title,
      otherOffersCount: listing.other_offers_count ?? 0,
      otherMinPriceNgwee: listing.other_min_price_ngwee ?? null,
      labels: compareLabels,
    }),
  }));

  const jsonLd = buildVendorJsonLd(vendor, reviews, locale);

  // One home, many kinds of selling (§8.5.6): only the tabs this business uses.
  // Inactive panels stay mounted (hidden) so services and events are in the
  // crawlable HTML, not only the first tab.
  const offeringTabs: TabItem[] = [];
  if (show.products) {
    offeringTabs.push({
      key: "products",
      label: t("profile.tabProducts"),
      panel: (
        <StorefrontProducts
          locale={locale}
          listings={listingsForGrid}
          labels={{
            search: t("profile.searchStore", { name: vendor.display_name }),
            all: t("profile.allCategories"),
            noMatches: t("profile.noMatches"),
          }}
          gridLabels={{
            vendor: String(t.raw("listings.vendor")),
            noReviews: t("listings.noReviews"),
            reviewCount: String(t.raw("listings.reviewCount")),
            quickAdd: t("listings.quickAdd"),
            wishlist: t("listings.wishlist"),
            outOfStock: t("listings.outOfStock"),
            conditionNew: t("listings.conditionNew"),
            conditionRefurbished: t("listings.conditionRefurbished"),
            conditionUsed: tCatalog("plp.card.conditionUsed"),
            logistics: catalogLogisticsLabels(tCatalog),
            delivery: catalogDeliveryLabels((key) => tCatalog.raw(key)),
          }}
        />
      ),
    });
  }
  if (show.services) {
    offeringTabs.push({
      key: "services",
      label: t("profile.tabServices"),
      panel: (
        <VendorServicesGrid
          locale={locale}
          services={services}
          labels={{
            from: (price) => t("profile.serviceFrom", { price }),
            book: (price) => t("profile.home.serviceBook", { price }),
            quote: t("profile.home.serviceQuote"),
            area: (area) => t("profile.home.serviceArea", { area }),
          }}
        />
      ),
    });
  }
  if (show.events) {
    offeringTabs.push({
      key: "events",
      label: t("profile.tabEvents"),
      panel: <VendorEventsGrid locale={locale} events={events} />,
    });
  }

  const hasRating = reviews.rating_avg !== null && reviews.rating_count > 0;
  const hasAnyStat = hasRating || vendor.order_count > 0;
  const joinedLabel = vendor.created_at
    ? new Intl.DateTimeFormat(locale, {
        month: "short",
        year: "numeric",
      }).format(new Date(vendor.created_at))
    : null;

  const branchSource =
    vendor.locations.length > 0 ? vendor.locations : vendor.location ? [vendor.location] : [];
  const branches: BusinessBranch[] = branchSource.map((branch) => ({
    landmark: branch.landmark,
    lat: branch.lat,
    lng: branch.lng,
    schedule: branch.schedule ?? [],
  }));
  const firstBranch = branches[0] ?? null;
  const dayKey = {
    mon: "dayMon",
    tue: "dayTue",
    wed: "dayWed",
    thu: "dayThu",
    fri: "dayFri",
    sat: "daySat",
    sun: "daySun",
  } as const;

  // Vendor colours re-skin this storefront subtree only (AA-clamped again here).
  const brandStyle = brandThemeStyle(vendor.brand_theme ?? null);
  const brandClass = [
    brandStyle?.["--brand-primary"] ? "v-brand-primary" : "",
    brandStyle?.["--brand-accent"] ? "v-brand-accent" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const secondaryButton =
    "inline-flex min-h-11 items-center justify-center gap-2 rounded border border-border bg-surface px-4 text-sm font-semibold text-text no-underline hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing";

  return (
    <div
      className={`space-y-5 lg:mx-auto lg:w-full lg:max-w-6xl ${brandClass}`}
      style={brandStyle as React.CSSProperties | undefined}
      data-brand-theme={brandStyle ? "vendor" : undefined}
      data-testid="business-home"
    >
      <JsonLdScript data={jsonLd} />

      {/* The sign (§8.3): the business's own cover, logo and name come first;
          Convergeo is the street, not the shop sign. */}
      <header className="relative">
        {vendor.cover_url ? (
          <div
            aria-hidden
            className="h-28 rounded-lg bg-panel bg-cover bg-center sm:h-40"
            style={{ backgroundImage: `url(${vendor.cover_url})` }}
          />
        ) : (
          <div className="h-16 rounded-lg bg-panel sm:h-24" aria-hidden />
        )}
        <div className="flex flex-col gap-3 px-1 pt-3 sm:flex-row sm:items-end sm:gap-4 sm:px-4">
          <div className="-mt-12 shrink-0 sm:-mt-14">
            {vendor.logo_url ? (
              <div
                aria-hidden
                className="h-20 w-20 rounded-lg border-4 border-bg bg-surface bg-cover bg-center sm:h-24 sm:w-24"
                style={{ backgroundImage: `url(${vendor.logo_url})` }}
              />
            ) : (
              <div
                aria-hidden
                className="flex h-20 w-20 items-center justify-center rounded-lg border-4 border-bg bg-primary-tint font-display text-h1 font-bold text-primary sm:h-24 sm:w-24"
              >
                {vendor.display_name.charAt(0)}
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="m-0 font-display text-h1 font-bold text-display-ink">
                {vendor.display_name}
              </h1>
              <CornerRibbon trust={trustRibbon.trust} trustLabel={trustRibbon.trustLabel} />
            </div>
            <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-text-2">
              {hasRating ? (
                <span className="font-semibold text-text">
                  ★ {reviews.rating_avg?.toFixed(1)}{" "}
                  <span className="font-normal text-text-2">
                    ({reviews.rating_count} {t("profile.statReviews").toLowerCase()})
                  </span>
                </span>
              ) : null}
              {vendor.order_count > 0 ? (
                <span>
                  {vendor.order_count} {t("profile.statOrders").toLowerCase()}
                </span>
              ) : null}
              {show.products ? (
                <span>
                  {listings.length} {t("profile.statListings").toLowerCase()}
                </span>
              ) : null}
              {firstBranch ? <span>{firstBranch.landmark}</span> : null}
              {!hasAnyStat ? (
                <span
                  className="rounded-pill bg-accent-tint px-2.5 py-0.5 text-sm font-semibold text-accent-deep"
                  data-testid="vendor-new-seller"
                >
                  {joinedLabel
                    ? t("profile.newSellerJoined", { date: joinedLabel })
                    : t("profile.newSeller")}
                </span>
              ) : null}
            </p>
          </div>
          {/* Three buttons (§8.3): Follow, WhatsApp, Directions — plus Share. */}
          <div className="flex shrink-0 flex-wrap gap-2">
            <FollowVendorButton
              vendorId={vendor.id}
              locale={locale}
              labels={{
                follow: t("profile.follow"),
                following: t("profile.following"),
              }}
            />
            {vendor.whatsapp_msisdn ? (
              <a
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] no-underline hover:bg-[var(--primary-btn-hover)] focus-visible:outline-none focus-visible:shadow-focusRing"
                href={`https://wa.me/${vendor.whatsapp_msisdn}`}
                rel="noopener noreferrer"
                target="_blank"
              >
                <svg
                  aria-hidden
                  viewBox="0 0 24 24"
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M4 20l1.3-3.9A8 8 0 1 1 8 18.7L4 20Z" />
                </svg>
                {t("profile.whatsappCta")}
              </a>
            ) : null}
            {firstBranch ? (
              <a
                className={secondaryButton}
                href={directionsHref(firstBranch)}
                rel="noopener noreferrer"
                target="_blank"
                aria-label={t("profile.home.directionsTo", {
                  place: firstBranch.landmark,
                })}
                data-testid="bh-directions"
              >
                {t("profile.home.directions")}
              </a>
            ) : null}
            <ShareLinkButton label={shareLabel} title={vendor.display_name} />
          </div>
        </div>
      </header>

      <StorySection heading={t("profile.home.storyHeading")} story={vendor.description} />

      <ClipsRow
        locale={locale}
        clips={show.clips ? clips : []}
        labels={{
          heading: t("profile.home.clipsHeading"),
          watch: t("profile.home.clipWatch"),
        }}
      />

      <OffersSection
        enabled={show.offers}
        offers={offers.map((offer) => ({
          id: offer.id,
          title: offer.title,
          endsLabel: offer.ends_at
            ? t("profile.home.offersEnds", {
                date: new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(
                  new Date(offer.ends_at),
                ),
              })
            : null,
        }))}
        labels={{ heading: t("profile.home.offersHeading") }}
      />

      {offeringTabs.length > 0 ? (
        <Tabs items={offeringTabs} ariaLabel={t("profile.offeringsAria")} mountInactivePanels />
      ) : null}

      <ReviewsSection
        ratingAvg={reviews.rating_avg}
        ratingCount={reviews.rating_count}
        labels={{
          heading: t("profile.tabReviews"),
          summary: t("profile.reviewsSummary", {
            rating: reviews.rating_avg ?? 0,
            count: reviews.rating_count,
          }),
          none: t("profile.noReviews"),
          verifiedOnly: t("profile.home.verifiedOnly"),
        }}
      />

      <FindUsSection
        branches={branches}
        labels={{
          heading: t("profile.home.findUsHeading"),
          directions: t("profile.home.directions"),
          directionsTo: (place) => t("profile.home.directionsTo", { place }),
          hoursNotShared: t("profile.home.hoursNotShared"),
          hoursRange: (opens, closes) => t("profile.home.hoursRange", { opens, closes }),
          day: (day) => t(`profile.home.${dayKey[day]}`),
          open: t("profile.home.openNow"),
          closed: t("profile.home.closedNow"),
        }}
      />

      {/* Never trap the customer on one shop: the street is one tap away. */}
      <p className="m-0">
        <Link
          href={`/${locale}/vendors`}
          className="inline-flex min-h-11 items-center text-sm font-semibold text-primary"
          data-testid="bh-other-shops"
        >
          {t("profile.home.browseOtherShops")}
        </Link>
      </p>
    </div>
  );
}
