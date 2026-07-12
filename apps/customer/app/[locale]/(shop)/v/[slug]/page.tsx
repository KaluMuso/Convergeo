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
    <div className="space-y-6 lg:mx-auto lg:w-full lg:max-w-3xl">
      <JsonLdScript data={jsonLd} />

      <header
        className="space-y-3 rounded border border-border bg-surface p-4"
        style={{ borderRadius: "var(--r)" }}
      >
        <div className="flex flex-wrap items-start gap-3">
          {vendor.logo_url ? (
            <div
              aria-hidden
              className="h-16 w-16 rounded-full border border-border bg-cover bg-center"
              style={{ backgroundImage: `url(${vendor.logo_url})` }}
            />
          ) : null}
          <div className="min-w-0 flex-1 space-y-2">
            <h1 className="font-display text-h1 text-display-ink">{vendor.display_name}</h1>
            <div className="flex flex-wrap items-center gap-2">
              {vendor.preferred_badge ? (
                <CornerRibbon trust="preferred" trustLabel={t("profile.preferredBadge")} />
              ) : null}
              {vendor.verified ? (
                <CornerRibbon trust="id_verified" trustLabel={t("profile.verifiedBadge")} />
              ) : null}
            </div>
          </div>
        </div>

        {vendor.description ? (
          <section>
            <h2 className="mb-1 text-sm font-semibold text-text">{t("profile.about")}</h2>
            <p className="text-sm text-text-2">{vendor.description}</p>
          </section>
        ) : null}

        {vendor.location ? (
          <section className="space-y-2">
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

        <section>
          <h2 className="mb-1 text-sm font-semibold text-text">{t("profile.reviewsHeading")}</h2>
          <p className="text-sm text-text-2">
            {reviews.rating_count > 0 && reviews.rating_avg !== null
              ? t("profile.reviewsSummary", {
                  rating: reviews.rating_avg,
                  count: reviews.rating_count,
                })
              : t("profile.noReviews")}
          </p>
        </section>
      </header>

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
