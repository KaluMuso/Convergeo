import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { resolveApiBaseUrl } from "../../../../lib/api-base-url";
import {
  shouldShowComparison,
  type ComparisonLabels,
  type ComparisonListing,
} from "../_components/pdp/comparison";

import { BackToTop } from "../_components/back-to-top";

import { CompareResults } from "./_components/compare-results";

import type { ListingCondition } from "../_components/pdp/condition-badge";
import type { Metadata } from "next";

export const revalidate = 60;

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ product?: string; slug?: string }>;
};

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type ComparisonApiListing = {
  id: string;
  price_ngwee: number;
  condition: ListingCondition;
  vendor: {
    id: string;
    slug: string;
    display_name: string;
    preferred_badge: boolean;
    rating_avg: number | null;
    rating_count: number;
    lat: number | null;
    lng: number | null;
    landmark: string | null;
  };
  delivery_available: boolean;
  pickup_available: boolean;
};

type ComparisonApiResponse = {
  product_id: string;
  product_slug: string;
  listing_count: number;
  listings: ComparisonApiListing[];
};

async function getCatalogTranslator(locale: string): Promise<CatalogTranslator> {
  const baseMessages = await getMessages();
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const messages = { ...baseMessages, catalog: catalogMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "catalog",
  }) as unknown as CatalogTranslator;
}

function resolveProductSlug(query: { product?: string; slug?: string }): string | null {
  const raw = query.product?.trim() || query.slug?.trim();
  if (!raw) {
    return null;
  }
  // Slugs are path-safe identifiers; reject anything that looks like an injection.
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/i.test(raw)) {
    return null;
  }
  return raw;
}

async function fetchComparison(slug: string): Promise<ComparisonApiResponse | null> {
  const apiBase = resolveApiBaseUrl();
  if (!apiBase) {
    return null;
  }
  try {
    const response = await fetch(`${apiBase}/products/${encodeURIComponent(slug)}/comparison`, {
      next: { revalidate, tags: ["products", "comparison", `product:${slug}`] },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as ComparisonApiResponse;
  } catch {
    return null;
  }
}

function toComparisonListings(response: ComparisonApiResponse): ComparisonListing[] {
  return response.listings.map((listing) => ({
    id: listing.id,
    priceNgwee: listing.price_ngwee,
    condition: listing.condition,
    vendor: {
      id: listing.vendor.id,
      slug: listing.vendor.slug,
      displayName: listing.vendor.display_name,
      preferredBadge: listing.vendor.preferred_badge,
      ratingAvg: listing.vendor.rating_avg,
      ratingCount: listing.vendor.rating_count,
      lat: listing.vendor.lat,
      lng: listing.vendor.lng,
      landmark: listing.vendor.landmark,
    },
    deliveryAvailable: listing.delivery_available,
    pickupAvailable: listing.pickup_available,
  }));
}

function comparisonLabels(t: CatalogTranslator): ComparisonLabels {
  return {
    heading: t("comparison.heading"),
    vendorCount: t("comparison.vendorCount"),
    sortLabel: t("comparison.sortLabel"),
    sortPrice: t("comparison.sortPrice"),
    sortDistance: t("comparison.sortDistance"),
    price: t("comparison.price"),
    condition: t("comparison.condition"),
    distance: t("comparison.distance"),
    vendor: t("comparison.vendor"),
    fulfillment: t("comparison.fulfillment"),
    delivery: t("comparison.delivery"),
    pickup: t("comparison.pickup"),
    selectListing: t("comparison.selectListing"),
    selectedListing: t("comparison.selectedListing"),
    preferredBadge: t("comparison.preferredBadge"),
    noReviews: t("comparison.noReviews"),
    rating: t("comparison.rating"),
    conditionNew: t("comparison.conditionNew"),
    conditionRefurbished: t("comparison.conditionRefurbished"),
    usingFallbackLocation: t("comparison.usingFallbackLocation"),
    lowestPriceBadge: t("comparison.lowestPriceBadge"),
  };
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getCatalogTranslator(locale);

  return {
    title: t("comparePage.title"),
    description: t("comparePage.subtitle"),
    alternates: buildCanonicalAlternates(locale, "compare"),
    openGraph: {
      title: t("comparePage.title"),
      description: t("comparePage.subtitle"),
      type: "website",
      locale,
      url: buildLocaleCanonical(locale, "compare"),
    },
    // Compare is driven by query params — keep it out of the organic index.
    robots: { index: false, follow: false },
  };
}

export default async function ComparePage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const query = await searchParams;
  setRequestLocale(locale);

  const t = await getCatalogTranslator(locale);
  const slug = resolveProductSlug(query);

  if (!slug) {
    return (
      <div className="flex flex-col gap-6 lg:mx-auto lg:w-full lg:max-w-3xl">
        <header className="space-y-2">
          <h1 className="font-display text-h1 text-display-ink">{t("comparePage.title")}</h1>
          <p className="text-body text-text-2">{t("comparePage.subtitle")}</p>
        </header>
        <EmptyState title={t("comparePage.noProductTitle")} body={t("comparePage.noProductBody")} />
        <Link
          href={`/${locale}/search`}
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-5 text-sm font-medium text-surface"
        >
          {t("comparePage.browseCta")}
        </Link>
      </div>
    );
  }

  const comparison = await fetchComparison(slug);
  if (!comparison) {
    return (
      <div className="flex flex-col gap-6 lg:mx-auto lg:w-full lg:max-w-3xl">
        <header className="space-y-2">
          <h1 className="font-display text-h1 text-display-ink">{t("comparePage.title")}</h1>
        </header>
        <EmptyState
          title={t("comparePage.unavailableTitle")}
          body={t("comparePage.unavailableBody")}
        />
        <Link
          href={`/${locale}/p/${slug}`}
          className="inline-flex min-h-11 items-center justify-center rounded border border-border bg-surface px-5 text-sm font-medium text-text"
        >
          {t("comparePage.backToProduct")}
        </Link>
      </div>
    );
  }

  const listings = toComparisonListings(comparison);
  const canCompare = shouldShowComparison(listings.length);

  return (
    <div className="flex flex-col gap-6 lg:mx-auto lg:w-full lg:max-w-5xl">
      <header className="space-y-2">
        <p className="text-sm text-text-2">
          <Link
            href={`/${locale}/p/${comparison.product_slug}`}
            className="text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            {t("comparePage.backToProduct")}
          </Link>
        </p>
        <h1 className="font-display text-h1 text-display-ink">{t("comparePage.title")}</h1>
        <p className="text-body text-text-2">{t("comparePage.subtitle")}</p>
      </header>

      {!canCompare ? (
        <EmptyState
          title={t("comparePage.singleSellerTitle")}
          body={t("comparePage.singleSellerBody")}
        />
      ) : (
        <>
          <CompareResults listings={listings} labels={comparisonLabels(t)} />
          <BackToTop label={t("plp.backToTop")} />
        </>
      )}

      <Link
        href={`/${locale}/p/${comparison.product_slug}`}
        className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-5 text-sm font-medium text-surface"
      >
        {t("comparePage.chooseOnProduct")}
      </Link>
    </div>
  );
}
