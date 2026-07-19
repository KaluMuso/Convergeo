import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { FilterBar } from "../_components/directory/filter-bar";
import { VendorCardGrid } from "../_components/directory/vendor-card-grid";

import type { Metadata } from "next";

export const revalidate = 60;

type DirectoryApiResponse = {
  items: Array<{
    id: string;
    slug: string;
    display_name: string;
    description: string | null;
    logo_url: string | null;
    preferred_badge: boolean;
    verified: boolean;
    landmark: string | null;
    categories: string[];
    rating_avg: number | null;
    rating_count: number;
    listing_count: number;
    created_at?: string | null;
  }>;
  facets: {
    categories: Array<{ value: string; count: number }>;
    locations: Array<{ value: string; count: number }>;
    badges: Array<{ value: string; count: number }>;
  };
  total: number;
};

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

type DirectoryTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

function readParam(params: Record<string, string | string[] | undefined>, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
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

async function fetchDirectory(query: Record<string, string>): Promise<DirectoryApiResponse | null> {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value) {
      searchParams.set(key, value);
    }
  }

  try {
    const response = await fetch(`${getApiBaseUrl()}/directory?${searchParams.toString()}`, {
      next: { revalidate, tags: ["directory"] },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as DirectoryApiResponse;
  } catch {
    return null;
  }
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getDirectoryTranslator(locale);
  return {
    title: t("index.title"),
    description: t("index.subtitle"),
    alternates: buildCanonicalAlternates(locale, "directory"),
    openGraph: {
      title: t("index.title"),
      description: t("index.subtitle"),
      type: "website",
      locale,
      url: buildLocaleCanonical(locale, "directory"),
    },
    robots: { index: true, follow: true },
  };
}

export default async function DirectoryPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const resolvedSearchParams = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const t = await getDirectoryTranslator(locale);

  const q = readParam(resolvedSearchParams, "q");
  const category = readParam(resolvedSearchParams, "category");
  const location = readParam(resolvedSearchParams, "location");
  const badges = readParam(resolvedSearchParams, "badges");

  const directory = await fetchDirectory({ q, category, location, badges });
  const vendors = directory?.items ?? [];
  const facets = directory?.facets ?? { categories: [], locations: [], badges: [] };
  const total = directory?.total ?? 0;

  const categoryLabels = {
    electronics: t("filters.categories.electronics"),
    "fashion-beauty": t("filters.categories.fashion-beauty"),
    "home-living": t("filters.categories.home-living"),
    groceries: t("filters.categories.groceries"),
  };

  const formatFacetLabel = (label: string, count: number) =>
    t("filters.facetCount", { label, count });

  const categoryOptions = facets.categories.map((facet) => ({
    value: facet.value,
    label: formatFacetLabel(
      categoryLabels[facet.value as keyof typeof categoryLabels] ?? facet.value.replace(/-/g, " "),
      facet.count,
    ),
  }));

  const locationOptions = facets.locations.map((facet) => ({
    value: facet.value,
    label: formatFacetLabel(facet.value, facet.count),
  }));

  return (
    <div className="space-y-6 lg:mx-auto lg:w-full lg:max-w-6xl">
      <section className="overflow-hidden rounded-lg bg-panel px-5 py-8 text-panel-text sm:px-8 sm:py-10">
        <div className="max-w-2xl space-y-3">
          <h1 className="font-display text-h1 text-panel-text">{t("index.title")}</h1>
          <p className="text-body text-panel-muted">{t("index.subtitle")}</p>
          <p className="text-sm text-panel-muted">{t("index.results", { count: total })}</p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href={`/${locale}/sell`}
              className="inline-flex min-h-11 items-center rounded bg-panel-text px-5 text-sm font-semibold text-panel transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {t("index.becomeVendor")}
            </Link>
            <span className="text-sm text-panel-muted">{t("index.heroPitch")}</span>
          </div>
        </div>
      </section>

      <Suspense fallback={null}>
        <FilterBar
          locale={locale}
          categoryOptions={categoryOptions}
          locationOptions={locationOptions}
          initialQuery={q}
          initialCategory={category}
          initialLocation={location}
          initialBadges={badges ? badges.split(",") : []}
          labels={{
            heading: t("filters.heading"),
            searchPlaceholder: t("index.searchPlaceholder"),
            category: t("filters.category"),
            location: t("filters.location"),
            badges: t("filters.badges"),
            allCategories: t("filters.allCategories"),
            allLocations: t("filters.allLocations"),
            preferred: t("filters.preferred"),
            verified: t("filters.verified"),
            apply: t("filters.apply"),
            clear: t("filters.clear"),
          }}
        />
      </Suspense>

      {vendors.length === 0 ? (
        <EmptyState
          icon="🏪"
          title={t("empty.title")}
          body={t("empty.body")}
          data-testid="directory-empty"
        />
      ) : (
        <VendorCardGrid
          locale={locale}
          vendors={vendors.map((vendor) => ({
            id: vendor.id,
            slug: vendor.slug,
            displayName: vendor.display_name,
            description: vendor.description,
            logoUrl: vendor.logo_url,
            preferredBadge: vendor.preferred_badge,
            verified: vendor.verified,
            landmark: vendor.landmark,
            categories: vendor.categories,
            ratingAvg: vendor.rating_avg,
            ratingCount: vendor.rating_count,
            listingCount: vendor.listing_count,
            createdAt: vendor.created_at,
          }))}
          labels={{
            listings: t("card.listings"),
            reviews: t("card.reviews"),
            rating: t("card.rating"),
            noReviews: t("card.noReviews"),
            verifiedSince: t("card.verifiedSince"),
            preferredBadge: t("card.preferredBadge"),
            verifiedBadge: t("card.verifiedBadge"),
            viewProfile: t("index.viewProfile"),
            categoryLabels,
            defaultLocation: t("card.defaultLocation"),
          }}
        />
      )}
    </div>
  );
}
