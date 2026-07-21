import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { Breadcrumbs } from "@vergeo/ui/src/breadcrumbs";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import {
  buildBreadcrumbListJsonLd,
  buildCanonicalAlternates,
  buildLocaleCanonical,
  JsonLdScript,
} from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getApiBaseUrl, resolveApiBaseUrl } from "../../../../../lib/api-base-url";
import { fetchJson } from "../../../../../lib/fetch-json";
import { buildCategoryTree } from "../../_components/category-tree";
import { fetchCategoriesResult } from "../../_components/merch-data";
import { AppliedFilterBar } from "../../_components/plp/applied-filter-bar";
import { ChildCategoryNav } from "../../_components/plp/child-category-nav";
import { FacetPanel, type FacetCounts } from "../../_components/plp/facet-panel";
import { type CatalogListing } from "../../_components/plp/listing-grid";
import { PlpBrowseClient } from "../../_components/plp/load-more";
import { MobileFilterDrawer } from "../../_components/plp/mobile-filter-drawer";
import { decodePlpFilters } from "../../_components/plp/plp-filters";
import { type CatalogSort, SortBar } from "../../_components/plp/sort-bar";

import type { Metadata } from "next";

export const revalidate = 60;

type CatalogApiResponse = {
  items: Array<{
    id: string;
    title: string;
    product_slug: string | null;
    vendor_name: string;
    price_ngwee: number;
    condition: string;
    in_stock: boolean;
    image_public_id: string | null;
    rating: number;
    review_count: number;
    distance_m: number | null;
  }>;
  facets: FacetCounts;
  total: number;
  next_cursor: string | null;
};

type PageProps = {
  params: Promise<{ locale: string; slug: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
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

function slugToCategoryPath(slug: string[]): string | undefined {
  if (slug.length === 0) {
    return undefined;
  }
  if (slug.length === 1 && slug[0] === "all") {
    return undefined;
  }
  return slug.join("/");
}

function categoryTitleFromPath(path: string | undefined): string {
  if (!path) {
    return "";
  }
  const leaf = path.split("/").at(-1) ?? path;
  return leaf
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function buildCatalogQuery(
  categoryPath: string | undefined,
  searchParams: Record<string, string | string[] | undefined>,
): string {
  const params = new URLSearchParams();
  if (categoryPath) {
    params.set("category_path", categoryPath);
  }
  for (const [key, value] of Object.entries(searchParams)) {
    if (value === undefined || key === "slug") {
      continue;
    }
    if (Array.isArray(value)) {
      if (value[0]) {
        params.set(key, value[0]);
      }
    } else {
      params.set(key, value);
    }
  }
  return params.toString();
}

async function fetchCatalog(queryString: string): Promise<CatalogApiResponse | null> {
  const baseUrl = resolveApiBaseUrl();
  if (!baseUrl) {
    return null;
  }
  const suffix = queryString ? `?${queryString}` : "";
  try {
    return await fetchJson<CatalogApiResponse>(`${baseUrl}/catalog/listings${suffix}`, {
      next: { revalidate: 60 },
    });
  } catch {
    return null;
  }
}

function mapListing(item: CatalogApiResponse["items"][number]): CatalogListing {
  return {
    id: item.id,
    title: item.title,
    productSlug: item.product_slug,
    vendorName: item.vendor_name,
    priceNgwee: item.price_ngwee,
    condition: item.condition,
    inStock: item.in_stock,
    imagePublicId: item.image_public_id,
    rating: item.rating,
    reviewCount: item.review_count,
    distanceM: item.distance_m,
  };
}

export function generateStaticParams() {
  return LOCALES.flatMap((locale) => [
    { locale, slug: ["all"] },
    { locale, slug: ["electronics"] },
    { locale, slug: ["fashion-beauty"] },
  ]);
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  const resolvedSearch = await searchParams;
  const t = await getCatalogTranslator(locale);
  const categoryPath = slugToCategoryPath(slug);
  const categoryName = categoryTitleFromPath(categoryPath) || t("plp.defaultCategory");

  const canonicalPath = buildLocaleCanonical(locale, "c", ...slug);
  const hasFilters = Object.keys(resolvedSearch).some((key) => !["lat", "lng"].includes(key));

  return {
    title: t("plp.title", { category: categoryName }),
    description: t("plp.results", { count: 0 }).replace("0", categoryName),
    alternates: buildCanonicalAlternates(locale, "c", ...slug),
    openGraph: {
      title: t("plp.title", { category: categoryName }),
      description: t("plp.results", { count: 0 }).replace("0", categoryName),
      type: "website",
      locale,
      url: canonicalPath,
    },
    robots: {
      index: !hasFilters,
      follow: true,
    },
  };
}

export default async function CategoryPlpPage({ params, searchParams }: PageProps) {
  const { locale, slug } = await params;
  const resolvedSearch = await searchParams;
  setRequestLocale(locale);

  const t = await getCatalogTranslator(locale);
  const categoryPath = slugToCategoryPath(slug);
  const categoryName = categoryTitleFromPath(categoryPath) || t("plp.defaultCategory");
  const queryString = buildCatalogQuery(categoryPath, resolvedSearch);
  const catalog = await fetchCatalog(queryString);
  const catalogUnavailable = catalog === null;

  const filterState = decodePlpFilters(new URLSearchParams(queryString));
  const sort = (resolvedSearch.sort as CatalogSort | undefined) ?? "relevance";
  const hasLocation = Boolean(filterState.lat && filterState.lng);

  const listings = (catalog?.items ?? []).map(mapListing);
  const facets: FacetCounts = catalog?.facets ?? {
    condition: [],
    availability: [],
    rating: [],
  };
  const total = catalog?.total ?? 0;
  const apiBaseUrl = getApiBaseUrl();

  const categoriesResult = await fetchCategoriesResult();
  const categoryTree =
    categoriesResult.ok && categoriesResult.categories.length > 0
      ? buildCategoryTree(categoriesResult.categories)
      : [];
  const leafSlug = slug[slug.length - 1] ?? "";
  const activeNav =
    leafSlug && leafSlug !== "all"
      ? categoryTree.find((entry) => entry.slug === leafSlug)
      : undefined;
  const childCategories =
    activeNav?.children.map((child) => ({ slug: child.slug, name: child.name })) ??
    (leafSlug === "all" || !leafSlug
      ? categoryTree.map((entry) => ({ slug: entry.slug, name: entry.name }))
      : []);
  const childParentParts = activeNav ? [activeNav.slug] : [];

  const facetLabels = {
    heading: t("plp.facets.heading"),
    price: t("plp.facets.price"),
    minPrice: t("plp.facets.minPrice"),
    maxPrice: t("plp.facets.maxPrice"),
    condition: t("plp.facets.condition"),
    conditionNew: t("plp.facets.conditionNew"),
    conditionRefurbished: t("plp.facets.conditionRefurbished"),
    availability: t("plp.facets.availability"),
    inStock: t("plp.facets.inStock"),
    outOfStock: t("plp.facets.outOfStock"),
    rating: t("plp.facets.rating"),
    rating4Plus: t("plp.facets.rating4Plus"),
    rating3Plus: t("plp.facets.rating3Plus"),
    location: t("plp.facets.location"),
    radiusKm: t("plp.facets.radiusKm"),
    apply: t("plp.facets.apply"),
    clear: t("plp.facets.clear"),
  };

  const gridLabels = {
    vendor: t("plp.card.vendor"),
    noReviews: t("plp.card.noReviews"),
    reviewCount: t("plp.card.reviewCount"),
    quickAdd: t("plp.card.quickAdd"),
    quickAddError: t("plp.card.quickAddError"),
    wishlist: t("plp.card.wishlist"),
    wishlistRemove: t("plp.card.wishlistRemove"),
    outOfStock: t("plp.card.outOfStock"),
    distance: t("plp.card.distance"),
    sampleListing: t("home.demo.sampleListing"),
    mediaEmpty: t("plp.card.mediaEmpty"),
  };

  const breadcrumbJsonLd = buildBreadcrumbListJsonLd(locale, [
    { name: t("home.nav.home"), path: "" },
    { name: categoryName, path: `c/${slug.join("/")}` },
  ]);

  const plpPathname = `/${locale}/c/${slug.join("/")}`;
  const activeSearchParams = new URLSearchParams(queryString);

  return (
    // Shop layout already provides the page <main> landmark — avoid nesting.
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
      <JsonLdScript data={breadcrumbJsonLd} />
      <Breadcrumbs
        ariaLabel={t("plp.breadcrumbAria")}
        ellipsisLabel="…"
        LinkComponent={Link}
        items={[
          { key: "home", label: t("home.nav.home"), href: `/${locale}` },
          { key: "category", label: categoryName },
        ]}
      />
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-h1 text-display-ink">
          {t("plp.title", { category: categoryName })}
        </h1>
        <p className="text-sm text-text-2" data-testid="plp-results-count" aria-live="polite">
          {catalogUnavailable ? t("plp.resultsUnknown") : t("plp.results", { count: total })}
        </p>
      </header>

      <ChildCategoryNav
        locale={locale}
        heading={t("plp.childCategories")}
        categories={childCategories}
        parentSlugParts={childParentParts}
      />

      <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <div className="hidden lg:block">
          <FacetPanel labels={facetLabels} facets={facets} initialState={filterState} />
        </div>

        <section className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              <SortBar
                labels={{
                  label: t("plp.sort.label"),
                  relevance: t("plp.sort.relevance"),
                  cheapest: t("plp.sort.cheapest"),
                  nearest: t("plp.sort.nearest"),
                  newest: t("plp.sort.newest"),
                }}
                value={sort}
                hasLocation={hasLocation}
              />
            </div>
            <MobileFilterDrawer
              labels={{
                ...facetLabels,
                openFilters: t("plp.facets.openFilters"),
                filtersActive: t("plp.facets.filtersActive"),
              }}
              facets={facets}
              initialState={filterState}
            />
          </div>

          <AppliedFilterBar
            pathname={plpPathname}
            searchParams={activeSearchParams}
            filterState={filterState}
            labels={{
              ariaLabel: t("plp.filters.appliedAria"),
              clearAll: t("plp.filters.clearAll"),
              // Preserve `{token}` placeholders for client-side chip templating.
              removeChip: t("plp.filters.removeChip", { filter: "{filter}" }),
              priceRange: t("plp.filters.priceRange", { min: "{min}", max: "{max}" }),
              minPriceOnly: t("plp.filters.minPriceOnly", { min: "{min}" }),
              maxPriceOnly: t("plp.filters.maxPriceOnly", { max: "{max}" }),
              conditionNew: t("plp.facets.conditionNew"),
              conditionRefurbished: t("plp.facets.conditionRefurbished"),
              inStock: t("plp.facets.inStock"),
              outOfStock: t("plp.facets.outOfStock"),
              rating4Plus: t("plp.facets.rating4Plus"),
              rating3Plus: t("plp.facets.rating3Plus"),
              nearMe: t("plp.facets.location"),
              radiusKm: t("plp.facets.radiusKm", { km: "{km}" }),
            }}
          />

          {catalogUnavailable ? (
            <EmptyState
              title={t("plp.unavailableTitle")}
              body={t("plp.unavailableBody")}
              data-testid="plp-unavailable"
            />
          ) : listings.length === 0 ? (
            <EmptyState
              title={t("plp.emptyTitle")}
              body={t("plp.emptyBody")}
              data-testid="plp-empty"
            />
          ) : (
            <PlpBrowseClient
              key={`${locale}|${queryString}`}
              locale={locale}
              initialListings={listings}
              gridLabels={gridLabels}
              apiBaseUrl={apiBaseUrl}
              queryString={queryString}
              nextCursor={catalog?.next_cursor ?? null}
              labels={{
                loadMore: t("plp.loadMore"),
                loading: t("plp.loading"),
                moreLoaded: t("plp.moreLoaded"),
                endOfResults: t("plp.endOfResults"),
                loadError: t("plp.loadError"),
                retry: t("plp.retry"),
              }}
            />
          )}
        </section>
      </div>
    </div>
  );
}
