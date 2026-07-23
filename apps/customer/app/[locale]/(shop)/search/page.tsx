import { createApiClient } from "@vergeo/config";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { getApiBaseUrl, resolveApiBaseUrl } from "../../../../lib/api-base-url";
import { BackToTop } from "../_components/back-to-top";
import { BrowseDiscoveryChips } from "../_components/browse-discovery-chips";
import { fetchCategoriesResult, type CategoryRow } from "../_components/merch-data";
import { RecentSearches } from "../_components/search/recent-searches";
import {
  ResultsTabs,
  type SearchResponse,
  type TabCounts,
} from "../_components/search/results-tabs";
import { SearchAnalytics } from "../_components/search/search-analytics";
import { SearchAppliedFilterBar } from "../_components/search/search-applied-filter-bar";
import { SearchFilterPanel } from "../_components/search/search-filter-panel";
import {
  appendSearchFiltersToApiParams,
  decodeSearchFilters,
  encodeSearchFilters,
  type SearchFilterState,
} from "../_components/search/search-filters";
import { NearMeToggle } from "../_components/search/near-me-toggle";
import { SearchInput } from "../_components/search/search-input";
import { searchTabKinds, type SearchKind } from "../_components/search/search-kinds";
import { SearchMobileFilterDrawer } from "../_components/search/search-mobile-filter-drawer";
import { SearchUnavailablePanel } from "../_components/search/search-unavailable-panel";
import {
  normalizeSearchQuery,
  parseSearchKind,
  parseSearchPage,
  resolveSearchPageView,
} from "../_components/search/search-view";
import { ZeroResults } from "../_components/search/zero-results";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{
    q?: string;
    kind?: string;
    page?: string;
    min_price?: string;
    max_price?: string;
    category_path?: string;
    lat?: string;
    lng?: string;
  }>;
};

/** Parse a URL coordinate, bounded to valid lat/lng; null if absent or out of range. */
function parseCoord(raw: string | undefined, bound: number): number | null {
  if (raw == null || raw.trim() === "") {
    return null;
  }
  const value = Number(raw);
  if (!Number.isFinite(value) || Math.abs(value) > bound) {
    return null;
  }
  return value;
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

async function fetchSearch(params: {
  q: string;
  kind?: SearchKind;
  page?: number;
  pageSize?: number;
  filters?: SearchFilterState;
  lat?: number | null;
  lng?: number | null;
}): Promise<SearchResponse | null> {
  const baseUrl = resolveApiBaseUrl();
  if (!baseUrl) {
    return null;
  }
  const client = createApiClient({ baseUrl });
  const searchParams = new URLSearchParams({
    q: params.q,
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  });
  if (params.kind) {
    searchParams.set("kind", params.kind);
  }
  if (params.filters) {
    appendSearchFiltersToApiParams(searchParams, params.filters);
  }
  if (params.lat != null && params.lng != null) {
    searchParams.set("lat", String(params.lat));
    searchParams.set("lng", String(params.lng));
  }

  try {
    return await client.request<SearchResponse>(`/search?${searchParams.toString()}`);
  } catch {
    return null;
  }
}

function buildSearchCategoryOptions(categories: CategoryRow[]) {
  return categories
    .filter((row) => !row.prohibited)
    .sort((left, right) => left.position - right.position)
    .map((row) => ({
      path: row.path || row.slug,
      label: row.name,
    }));
}

function buildCategoryLabelMap(
  options: Array<{ path: string; label: string }>,
): Record<string, string> {
  return Object.fromEntries(options.map((option) => [option.path, option.label]));
}

async function fetchTabCounts(query: string): Promise<TabCounts | null> {
  // Must use the shared (non-client) SEARCH_KINDS — see CUST-SEARCH-01 / digest 3273208722.
  const kinds = searchTabKinds();
  const responses = await Promise.all(
    kinds.map(async (kind) => {
      const response = await fetchSearch({
        q: query,
        kind: kind === "all" ? undefined : kind,
        page: 1,
        pageSize: 1,
      });
      if (response === null) {
        return null;
      }
      return [kind, response.total] as const;
    }),
  );

  if (responses.some((entry) => entry === null)) {
    return null;
  }

  return Object.fromEntries(responses as Array<readonly [keyof TabCounts, number]>) as TabCounts;
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const { q } = await searchParams;
  const trimmed = q?.trim();
  const searchMessages = await loadNamespace(locale as Locale, "search");
  const t = createTranslator({
    locale,
    messages: { search: searchMessages },
    namespace: "search",
  }) as (key: string, values?: Record<string, string | number>) => string;

  return {
    title: trimmed ? `${t("title")} — ${trimmed}` : t("title"),
    description: t("placeholder"),
    alternates: buildCanonicalAlternates(locale, "search"),
    openGraph: {
      title: trimmed ? `${t("title")} — ${trimmed}` : t("title"),
      description: t("placeholder"),
      type: "website",
      locale,
      url: buildLocaleCanonical(locale, "search"),
    },
    // Parameterised search results must not enter the organic index.
    robots: {
      index: false,
      follow: false,
    },
  };
}

export default async function SearchPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const resolvedSearchParams = await searchParams;
  const { q, kind: kindParam, page: pageParam } = resolvedSearchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const [searchMessages, catalogMessages, navMessages] = await Promise.all([
    loadNamespace(locale as Locale, "search"),
    loadNamespace(locale as Locale, "catalog"),
    loadNamespace(locale as Locale, "nav"),
  ]);
  const messages = {
    ...baseMessages,
    search: searchMessages,
    catalog: catalogMessages,
    nav: navMessages,
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "search" }) as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;
  const tCatalog = createTranslator({ locale, messages, namespace: "catalog" });
  const tNav = createTranslator({ locale, messages, namespace: "nav" });

  const normalized = normalizeSearchQuery(q);
  const activeKind = parseSearchKind(kindParam);
  const page = parseSearchPage(pageParam);
  const query = normalized.status === "ok" ? normalized.query : "";
  const filterParams = new URLSearchParams();
  for (const [key, value] of Object.entries(resolvedSearchParams)) {
    if (typeof value === "string" && value.length > 0) {
      filterParams.set(key, value);
    }
  }
  const filterState = decodeSearchFilters(filterParams);
  const userLat = parseCoord(resolvedSearchParams.lat, 90);
  const userLng = parseCoord(resolvedSearchParams.lng, 180);
  const showCategoryFilters =
    activeKind === "all" ||
    activeKind === "products" ||
    activeKind === "services" ||
    activeKind === "events" ||
    activeKind === "vendors";
  const showPriceFilters = activeKind === "all" || activeKind === "products";

  const categoriesResult = await fetchCategoriesResult();
  const searchCategoryOptions =
    categoriesResult.ok && categoriesResult.categories.length > 0
      ? buildSearchCategoryOptions(categoriesResult.categories)
      : [];
  const categoryLabelMap = buildCategoryLabelMap(searchCategoryOptions);

  const [searchResponse, tabCounts] =
    normalized.status === "ok"
      ? await Promise.all([
          fetchSearch({
            q: query,
            kind: activeKind === "all" ? undefined : activeKind,
            page,
            filters: showCategoryFilters ? filterState : undefined,
            lat: userLat,
            lng: userLng,
          }),
          fetchTabCounts(query),
        ])
      : [null, null];

  const view = resolveSearchPageView({
    normalized,
    kind: activeKind,
    searchResponse,
    tabCounts,
  });

  const categorySuggestions = [
    { key: "electronics", href: `/${locale}/c/electronics`, label: t("categories.electronics") },
    { key: "fashion", href: `/${locale}/c/fashion`, label: t("categories.fashion") },
    { key: "home", href: `/${locale}/c/home-living`, label: t("categories.home") },
    { key: "groceries", href: `/${locale}/c/groceries-staples`, label: t("categories.groceries") },
  ];

  const suggestionTerms = [
    t("suggestionTerms.phones"),
    t("suggestionTerms.chitenge"),
    t("suggestionTerms.kitchenware"),
    t("suggestionTerms.lusakaVendors"),
  ];

  const browseDiscoveryChips = [
    {
      key: "categories",
      href: `/${locale}/categories`,
      label: tNav("shop.allCategories"),
    },
    {
      key: "directory",
      href: `/${locale}/directory`,
      label: tNav("shop.directory"),
    },
    {
      key: "services",
      href: `/${locale}/services`,
      label: tNav("shop.services"),
    },
    {
      key: "events",
      href: `/${locale}/events`,
      label: tNav("shop.events"),
    },
  ];
  const browseDiscoveryAria = tNav("shop.browseChipsAria");

  const retryParams = new URLSearchParams();
  if (query.length > 0) {
    retryParams.set("q", query);
  }
  if (activeKind !== "all") {
    retryParams.set("kind", activeKind);
  }
  if (page > 1) {
    retryParams.set("page", String(page));
  }
  for (const [key, value] of encodeSearchFilters(filterState).entries()) {
    retryParams.set(key, value);
  }
  const retryHref =
    retryParams.toString().length > 0
      ? `/${locale}/search?${retryParams.toString()}`
      : `/${locale}/search`;

  const filterPanelLabels = {
    heading: t("filters.heading"),
    price: t("filters.price"),
    minPrice: t("filters.minPrice"),
    maxPrice: t("filters.maxPrice"),
    category: t("filters.category"),
    categoryAll: t("filters.categoryAll"),
    apply: t("filters.apply"),
    clear: t("filters.clear"),
    openFilters: t("filters.openFilters"),
    filtersActive: t("filters.filtersActive"),
    facetCount: t("filters.facetCount"),
  };

  const appliedFilterLabels = {
    ariaLabel: t("filters.appliedAria"),
    clearAll: t("filters.clearAll"),
    removeChip: t("filters.removeChip"),
    priceRange: t("filters.priceRange"),
    minPriceOnly: t("filters.minPriceOnly"),
    maxPriceOnly: t("filters.maxPriceOnly"),
  };

  const searchPathname = `/${locale}/search`;

  const categoryCounts =
    view.status === "results" && view.response.facets
      ? Object.fromEntries(
          view.response.facets.categories.map((bucket) => [bucket.value, bucket.count]),
        )
      : {};

  const resultsTabsLabels = {
    ariaLabel: t("tabs.ariaLabel"),
    all: t("tabs.all"),
    products: t("tabs.products"),
    services: t("tabs.services"),
    events: t("tabs.events"),
    vendors: t("tabs.vendors"),
    count: t("tabs.count"),
    resultsCount: t("results.count", {
      count: view.status === "results" ? view.response.total : 0,
    }),
    degraded: t("results.degraded"),
    priceFrom: t("result.priceFrom"),
    category: t("result.category"),
    distanceAway: t("result.distanceAway"),
    marketplaceListing: t("result.marketplaceListing"),
    wishlist: tCatalog("plp.card.wishlist"),
    wishlistRemove: tCatalog("plp.card.wishlistRemove"),
    mediaEmpty: tCatalog("plp.card.mediaEmpty"),
    noReviews: tCatalog("plp.card.noReviews"),
    reviewCount: tCatalog("plp.card.reviewCount"),
    loadMore: t("pagination.loadMore"),
    loading: t("pagination.loading"),
    moreLoaded: t("pagination.moreLoaded"),
    endOfResults: t("pagination.endOfResults"),
    loadError: t("pagination.loadError"),
    retry: t("pagination.retry"),
  };

  const nearMeLabels = {
    enable: t("nearMe.enable"),
    active: t("nearMe.active"),
    locating: t("nearMe.locating"),
    denied: t("nearMe.denied"),
    unsupported: t("nearMe.unsupported"),
    clear: t("nearMe.clear"),
    hint: t("nearMe.hint"),
  };

  return (
    // Shop layout already provides the page <main> landmark — avoid nesting.
    <div className="mx-auto w-full max-w-3xl py-3 motion-rise sm:py-5 lg:max-w-6xl xl:max-w-7xl">
      {view.status === "results" ? (
        <SearchAnalytics
          normalizedTerm={view.query}
          zeroResult={false}
          resultCount={view.response.total}
        />
      ) : null}
      {view.status === "zero" ? (
        <SearchAnalytics normalizedTerm={view.query} zeroResult resultCount={0} />
      ) : null}

      <header className="mb-3 space-y-3 lg:mb-4">
        <h1 className="font-display text-h1 text-display-ink">{t("title")}</h1>
        {query ? (
          <p className="text-sm text-text-2" data-testid="search-query-summary">
            {t("results.forQuery", { query })}
          </p>
        ) : null}
        <SearchInput
          locale={locale}
          initialQuery={query || (normalized.status === "invalid" ? (q?.trim() ?? "") : "")}
          autoFocus={!query && normalized.status !== "invalid"}
          labels={{
            placeholder: t("placeholder"),
            submit: t("submit"),
            ariaLabel: t("input.ariaLabel"),
            suggestionsLabel: t("input.suggestionsLabel"),
            noSuggestions: t("input.noSuggestions"),
            recentTitle: t("recent.title"),
          }}
        />
        {!query ? (
          <BrowseDiscoveryChips ariaLabel={browseDiscoveryAria} chips={browseDiscoveryChips} />
        ) : null}
        {query ? (
          <div className="flex flex-wrap items-center gap-2">
            <NearMeToggle locale={locale} labels={nearMeLabels} />
          </div>
        ) : null}
      </header>

      <RecentSearches
        locale={locale}
        query={query || undefined}
        className="mb-6"
        labels={{
          title: t("recent.title"),
          clear: t("recent.clear"),
          remove: t("recent.remove"),
        }}
      />

      {view.status === "unavailable" ? (
        <SearchUnavailablePanel
          retryHref={retryHref}
          labels={{
            title: t("unavailable.title"),
            body: t("unavailable.body"),
            retry: t("unavailable.retry"),
            browseHeading: t("unavailable.browseHeading"),
          }}
          chips={browseDiscoveryChips}
          browseAriaLabel={browseDiscoveryAria}
        />
      ) : null}

      {view.status === "invalid" ? (
        <EmptyState
          title={t("invalid.title")}
          body={t("invalid.body")}
          data-testid="search-invalid-query"
        />
      ) : null}

      {view.status === "zero" ? (
        <ZeroResults
          query={view.query}
          locale={locale}
          labels={{
            title: t("noResults.title", { query: view.query }),
            suggestionsTitle: t("noResults.suggestionsTitle"),
            categoriesTitle: t("noResults.categoriesTitle"),
            suggestionTerms,
            categories: categorySuggestions,
            askVergeoTitle: t("askVergeo.title"),
            askVergeoTeaser: t("askVergeo.teaser"),
            askVergeoSlotLabel: t("askVergeo.slotLabel"),
          }}
        />
      ) : null}

      {view.status === "results" ? (
        <Suspense fallback={null}>
          {showCategoryFilters ? (
            <div className="grid gap-3 lg:grid-cols-[14rem_minmax(0,1fr)] lg:gap-4 xl:grid-cols-[15rem_minmax(0,1fr)]">
              <div className="hidden lg:block">
                <SearchFilterPanel
                  labels={filterPanelLabels}
                  categories={searchCategoryOptions}
                  initialState={filterState}
                  categoryCounts={categoryCounts}
                  showPriceFilters={showPriceFilters}
                />
              </div>
              <div className="flex min-w-0 flex-col gap-3">
                <SearchMobileFilterDrawer
                  labels={filterPanelLabels}
                  categories={searchCategoryOptions}
                  initialState={filterState}
                  categoryCounts={categoryCounts}
                  showPriceFilters={showPriceFilters}
                />
                <SearchAppliedFilterBar
                  pathname={searchPathname}
                  searchParams={filterParams}
                  filterState={filterState}
                  categoryLabels={categoryLabelMap}
                  labels={appliedFilterLabels}
                />
                <ResultsTabs
                  key={`${locale}|${view.query}|${view.kind}|${page}|${JSON.stringify(filterState)}`}
                  locale={locale}
                  query={view.query}
                  activeKind={view.kind}
                  page={page}
                  response={view.response}
                  tabCounts={view.tabCounts}
                  apiBaseUrl={getApiBaseUrl()}
                  filterState={filterState}
                  userLat={userLat}
                  userLng={userLng}
                  labels={resultsTabsLabels}
                />
              </div>
            </div>
          ) : (
            <ResultsTabs
              key={`${locale}|${view.query}|${view.kind}|${page}`}
              locale={locale}
              query={view.query}
              activeKind={view.kind}
              page={page}
              response={view.response}
              tabCounts={view.tabCounts}
              apiBaseUrl={getApiBaseUrl()}
              userLat={userLat}
              userLng={userLng}
              labels={resultsTabsLabels}
            />
          )}
        </Suspense>
      ) : null}

      {view.status === "results" ? <BackToTop label={t("pagination.backToTop")} /> : null}
    </div>
  );
}
