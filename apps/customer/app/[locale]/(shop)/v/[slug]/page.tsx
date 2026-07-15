import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { CornerRibbon } from "@vergeo/ui/src/corner-ribbon";
import {
  buildCanonicalAlternates,
  buildLocaleCanonical,
  buildLocalBusinessJsonLd,
  JsonLdScript,
} from "@vergeo/ui/src/seo/json-ld";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

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
    preferred_badge: boolean;
    kyc_tier: number | null;
    verified: boolean;
    location: VendorLocation | null;
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

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

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
    const response = await fetch(`${getApiBaseUrl()}/directory/${encodeURIComponent(slug)}`, {
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

  const { vendor, listings, reviews_summary: reviews } = profile;
  const hoursLines = vendor.location
    ? formatHours(vendor.location.hours, (day, hoursValue) =>
        t("profile.hoursLine", { day, hours: hoursValue }),
      )
    : [];
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
  }));

  const jsonLd = buildVendorJsonLd(vendor, reviews, locale);

  return (
    <div className="space-y-6 lg:mx-auto lg:w-full lg:max-w-5xl">
      <JsonLdScript data={jsonLd} />

      <header className="overflow-hidden rounded-lg border border-border bg-surface">
        {/* Cover band — gradient fallback (no cover image in the vendor data model yet). */}
        <div className="h-28 bg-gradient-to-br from-panel to-panel-2 sm:h-40" aria-hidden />
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
          </div>
        </div>
        <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-border px-4 py-3">
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
        </dl>
      </header>

      {vendor.description || vendor.location ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {vendor.description ? (
            <section className="rounded-lg border border-border bg-surface p-4">
              <h2 className="mb-1 text-sm font-semibold text-text">{t("profile.about")}</h2>
              <p className="text-sm text-text-2">{vendor.description}</p>
            </section>
          ) : null}

          {vendor.location ? (
            <section className="space-y-2 rounded-lg border border-border bg-surface p-4">
              <h2 className="text-sm font-semibold text-text">{t("profile.location")}</h2>
              <p className="text-sm text-text-2">
                {t("profile.landmarkValue", { landmark: vendor.location.landmark })}
              </p>
              {hoursLines.length > 0 ? (
                <div>
                  <h3 className="mb-1 text-sm font-semibold text-text">{t("profile.hours")}</h3>
                  <ul className="space-y-1 text-sm text-text-2">
                    {hoursLines.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
      ) : null}

      <section className="space-y-3">
        <h2 className="font-display text-lg font-semibold text-text">
          {t("profile.listingsHeading")}
        </h2>
        {listingsForGrid.length > 0 ? (
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
              distance: t("listings.distance"),
            }}
          />
        ) : null}
      </section>
    </div>
  );
}
