import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
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
import { FollowVendorButton } from "../../_components/directory/follow-vendor-button";
import {
  buildVendorLadderLabels,
  vendorTrustRibbon,
} from "../../_components/directory/vendor-ladder-labels";
import { ListingGrid, type CatalogListing } from "../../_components/plp/listing-grid";

import type { Metadata } from "next";

export const revalidate = 3600;

type VendorLocation = {
  landmark: string;
  lat: number;
  lng: number;
  hours: Record<string, string>;
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
  }>;
  services: Array<{
    id: string;
    title: string;
    category: string | null;
    from_price_ngwee: number | null;
    image_public_id: string | null;
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
};

type PageProps = {
  params: Promise<{ locale: string; slug: string }>;
};

type DirectoryTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

async function getDirectoryTranslator(locale: string): Promise<DirectoryTranslator> {
  const baseMessages = await getMessages();
  const directoryMessages = await loadNamespace(locale as Locale, "directory");
  const messages = { ...baseMessages, directory: directoryMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "directory",
  }) as unknown as DirectoryTranslator;
}

async function getCatalogTranslator(locale: string): Promise<DirectoryTranslator> {
  const baseMessages = await getMessages();
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const messages = { ...baseMessages, catalog: catalogMessages } as AbstractIntlMessages;

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

function formatHours(
  hours: Record<string, string>,
  formatLine: (day: string, hoursValue: string) => string,
): string[] {
  return Object.entries(hours).map(([day, value]) => formatLine(day, value));
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
    return { title: "Vendor not found", robots: { index: false, follow: false } };
  }

  const t = await getDirectoryTranslator(locale);
  const description = t("profile.metaDescription", { name: profile.vendor.display_name });
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
      images: profile.vendor.logo_url
        ? [profile.vendor.logo_url]
        : [{ url: `${buildLocaleCanonical(locale)}/opengraph-image?${ogParams.toString()}` }],
    },
    robots: { index: true, follow: true },
  };
}

function VendorServicesGrid({
  locale,
  services,
  fromLabel,
}: {
  locale: string;
  services: VendorProfileApiResponse["services"];
  fromLabel: string;
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
            {service.from_price_ngwee !== null ? (
              <p className="text-sm text-text-2">
                {fromLabel.replace("{price}", formatK(service.from_price_ngwee))}
              </p>
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
  const ladderLabels = buildVendorLadderLabels(t);
  const trustRibbon = vendorTrustRibbon(
    { preferredBadge: vendor.preferred_badge, kycTier: vendor.kyc_tier },
    ladderLabels,
  );
  // Commercial tier (Bronze…Platinum) is a vendor plan — never shown to buyers.
  const listingsForGrid: CatalogListing[] = listings.map((listing) => ({
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
    deliveryAvailable: false,
    pickupAvailable: false,
    saleUnit: listing.sale_unit,
    unitStepMilli: listing.unit_step_milli,
    minSteps: listing.min_steps,
    productClass: listing.product_class,
    fulfilmentMode: listing.fulfilment_mode,
    leadTimeDays: listing.lead_time_days,
  }));

  const jsonLd = buildVendorJsonLd(vendor, reviews, locale);

  // Offerings shown as tabs when the vendor has more than one type; a single type
  // renders as a plain section (no tab bar for one tab).
  const offeringTabs: TabItem[] = [];
  if (listingsForGrid.length > 0) {
    offeringTabs.push({
      key: "products",
      label: t("profile.tabProducts"),
      panel: (
        <ListingGrid
          locale={locale}
          listings={listingsForGrid}
          labels={{
            vendor: t("listings.vendor"),
            noReviews: t("listings.noReviews"),
            reviewCount: t("listings.reviewCount"),
            quickAdd: t("listings.quickAdd"),
            wishlist: t("listings.wishlist"),
            outOfStock: t("listings.outOfStock"),
            conditionNew: t("listings.conditionNew"),
            conditionRefurbished: t("listings.conditionRefurbished"),
            conditionUsed: tCatalog("plp.card.conditionUsed"),
          }}
        />
      ),
    });
  }
  if (services.length > 0) {
    offeringTabs.push({
      key: "services",
      label: t("profile.tabServices"),
      panel: (
        <VendorServicesGrid
          locale={locale}
          services={services}
          fromLabel={t("profile.serviceFrom")}
        />
      ),
    });
  }
  if (events.length > 0) {
    offeringTabs.push({
      key: "events",
      label: t("profile.tabEvents"),
      panel: <VendorEventsGrid locale={locale} events={events} />,
    });
  }

  const hasRating = reviews.rating_avg !== null && reviews.rating_count > 0;
  const hasAnyStat = hasRating || vendor.order_count > 0;
  const joinedLabel = vendor.created_at
    ? new Intl.DateTimeFormat(locale, { month: "short", year: "numeric" }).format(
        new Date(vendor.created_at),
      )
    : null;

  const hoursEntries = vendor.locations.length > 0 ? vendor.locations : vendor.location ? [vendor.location] : [];
  const aboutPanel =
    vendor.description || hoursEntries.length > 0 ? (
      <div className="grid gap-6 md:grid-cols-[3fr_2fr]">
        {vendor.description ? (
          <p className="m-0 max-w-prose whitespace-pre-line text-body text-text-2">
            {vendor.description}
          </p>
        ) : null}
        {hoursEntries.length > 0 ? (
          <dl className="m-0 space-y-3 text-sm">
            {hoursEntries.map((branch, index) => (
              <div key={`${branch.landmark}-${index}`} className="space-y-1">
                <dt className="font-semibold text-text">{branch.landmark}</dt>
                {Object.entries(branch.hours ?? {}).map(([day, hours]) => (
                  <dd key={day} className="m-0 text-text-2">
                    {t("profile.hoursLine", { day, hours })}
                  </dd>
                ))}
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    ) : null;

  const reviewsPanel = (
    <div className="flex flex-wrap items-center gap-3 text-body text-text-2">
      {hasRating ? (
        <>
          <span className="font-display text-h2 font-bold text-display-ink">
            {reviews.rating_avg?.toFixed(1)}
          </span>
          <span>
            {t("profile.reviewsSummary", {
              rating: reviews.rating_avg ?? 0,
              count: reviews.rating_count,
            })}
          </span>
        </>
      ) : (
        <span>{t("profile.noReviews")}</span>
      )}
    </div>
  );

  if (aboutPanel) {
    offeringTabs.push({ key: "about", label: t("profile.tabAbout"), panel: aboutPanel });
  }
  offeringTabs.push({ key: "reviews", label: t("profile.tabReviews"), panel: reviewsPanel });

  return (
    <div className="space-y-5 lg:mx-auto lg:w-full lg:max-w-6xl">
      <JsonLdScript data={jsonLd} />

      {/* Compact store header (eBay/Etsy pattern): slim cover, logo tile, name,
          trust, one meta line, actions. No plan tier, no zero-stat table. */}
      <header className="relative">
        {vendor.cover_url ? (
          <div
            aria-hidden
            className="h-24 rounded-lg bg-panel bg-cover bg-center sm:h-36"
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
              {listings.length > 0 ? (
                <span>
                  {listings.length} {t("profile.statListings").toLowerCase()}
                </span>
              ) : null}
              {vendor.location ? <span>{vendor.location.landmark}</span> : null}
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
          <div className="flex shrink-0 flex-wrap gap-2">
            <FollowVendorButton
              vendorId={vendor.id}
              locale={locale}
              labels={{ follow: t("profile.follow"), following: t("profile.following") }}
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
            <ShareLinkButton label={shareLabel} title={vendor.display_name} />
          </div>
        </div>
      </header>

      <Tabs items={offeringTabs} ariaLabel={t("profile.offeringsAria")} />
    </div>
  );
}
