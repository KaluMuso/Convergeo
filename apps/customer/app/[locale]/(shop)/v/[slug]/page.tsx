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
  const t = await getDirectoryTranslator(locale);
  const profile = await fetchVendorProfile(slug);

  if (!profile) {
    notFound();
  }

  const { vendor, listings, services, events, reviews_summary: reviews } = profile;
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

  return (
    <div className="space-y-6 lg:mx-auto lg:w-full lg:max-w-5xl">
      <JsonLdScript data={jsonLd} />

      <header className="overflow-hidden rounded-lg border border-border bg-surface">
        {/* Cover band — the vendor's uploaded banner, or a gradient fallback. */}
        {vendor.cover_url ? (
          <div
            aria-hidden
            className="h-28 bg-cover bg-center sm:h-40"
            style={{ backgroundImage: `url(${vendor.cover_url})` }}
          />
        ) : (
          <div className="h-28 bg-gradient-to-br from-panel to-panel-2 sm:h-40" aria-hidden />
        )}
        <div className="flex flex-col gap-3 px-4 sm:flex-row sm:items-end sm:gap-4">
          <div className="-mt-12 shrink-0 sm:-mt-16">
            {vendor.logo_url ? (
              <div
                aria-hidden
                className="h-20 w-20 rounded-full border-4 border-surface bg-cover bg-center sm:h-24 sm:w-24"
                style={{ backgroundImage: `url(${vendor.logo_url})` }}
              />
            ) : (
              <div
                aria-hidden
                className="flex h-20 w-20 items-center justify-center rounded-full border-4 border-surface bg-bg-2 font-display text-h1 text-display-ink sm:h-24 sm:w-24"
              >
                {vendor.display_name.charAt(0)}
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1 space-y-2 pb-1 sm:pb-3">
            <h1 className="font-display text-h1 text-display-ink">{vendor.display_name}</h1>
            <div className="flex flex-wrap items-center gap-2">
              {vendor.preferred_badge ? (
                <CornerRibbon trust="preferred" trustLabel={t("profile.preferredBadge")} />
              ) : null}
              {vendor.verified ? (
                <CornerRibbon trust="id_verified" trustLabel={t("profile.verifiedBadge")} />
              ) : null}
              {vendor.location ? (
                <span className="text-sm text-text-3">{vendor.location.landmark}</span>
              ) : null}
            </div>
            {vendor.whatsapp_msisdn ? (
              <a
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded bg-success px-4 text-sm font-medium text-surface no-underline"
                href={`https://wa.me/${vendor.whatsapp_msisdn}`}
                rel="noopener noreferrer"
                target="_blank"
              >
                {t("profile.whatsappCta")}
              </a>
            ) : null}
          </div>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-border px-4 py-3 sm:grid-cols-4">
          <div className="text-center">
            <dd className="font-display text-h3 font-bold text-display-ink">
              {reviews.rating_avg !== null && reviews.rating_count > 0
                ? reviews.rating_avg.toFixed(1)
                : "—"}
            </dd>
            <dt className="text-micro text-text-3">{t("profile.statRating")}</dt>
          </div>
          <div className="text-center">
            <dd className="font-display text-h3 font-bold text-display-ink">
              {reviews.rating_count}
            </dd>
            <dt className="text-micro text-text-3">{t("profile.statReviews")}</dt>
          </div>
          <div className="text-center">
            <dd className="font-display text-h3 font-bold text-display-ink">{listings.length}</dd>
            <dt className="text-micro text-text-3">{t("profile.statListings")}</dt>
          </div>
          <div className="text-center">
            <dd className="font-display text-h3 font-bold text-display-ink">
              {vendor.order_count}
            </dd>
            <dt className="text-micro text-text-3">{t("profile.statOrders")}</dt>
          </div>
        </dl>
      </header>

      {vendor.description || vendor.locations.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {vendor.description ? (
            <section className="rounded-lg border border-border bg-surface p-4">
              <h2 className="mb-1 text-sm font-semibold text-text">{t("profile.about")}</h2>
              <p className="text-sm text-text-2">{vendor.description}</p>
            </section>
          ) : null}

          {vendor.locations.length > 0 ? (
            <section className="space-y-3 rounded-lg border border-border bg-surface p-4">
              <h2 className="text-sm font-semibold text-text">{t("profile.location")}</h2>
              {vendor.locations.map((branch, index) => {
                const branchHours = formatHours(branch.hours, (day, hoursValue) =>
                  t("profile.hoursLine", { day, hours: hoursValue }),
                );
                return (
                  <div key={`${branch.landmark}-${index}`} className="space-y-1">
                    <p className="text-sm font-medium text-text-2">
                      {t("profile.landmarkValue", { landmark: branch.landmark })}
                    </p>
                    {branchHours.length > 0 ? (
                      <ul className="space-y-1 text-sm text-text-3">
                        {branchHours.map((line) => (
                          <li key={line}>{line}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                );
              })}
            </section>
          ) : null}
        </div>
      ) : null}

      {offeringTabs.length > 1 ? (
        <Tabs items={offeringTabs} ariaLabel={t("profile.offeringsAria")} />
      ) : offeringTabs.length === 1 ? (
        <section className="space-y-3">
          <h2 className="font-display text-lg font-semibold text-text">{offeringTabs[0]?.label}</h2>
          {offeringTabs[0]?.panel}
        </section>
      ) : null}
    </div>
  );
}
