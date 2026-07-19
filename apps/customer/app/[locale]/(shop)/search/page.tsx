import { createApiClient } from "@vergeo/config";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { resolveApiBaseUrl } from "../../../../lib/api-base-url";
import { RecentSearches } from "../_components/search/recent-searches";
import {
  ResultsTabs,
  SEARCH_KINDS,
  type SearchKindFilter,
  type SearchResponse,
  type TabCounts,
} from "../_components/search/results-tabs";
import { SearchInput, type SearchKind } from "../_components/search/search-input";
import { ZeroResults } from "../_components/search/zero-results";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{
    q?: string;
    kind?: string;
    page?: string;
  }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

function parseKind(value: string | undefined): SearchKindFilter {
  if (!value) {
    return "all";
  }
  if ((SEARCH_KINDS as readonly string[]).includes(value)) {
    return value as SearchKind;
  }
  return "all";
}

function parsePage(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

async function fetchSearch(params: {
  q: string;
  kind?: SearchKind;
  page?: number;
  pageSize?: number;
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

  try {
    return await client.request<SearchResponse>(`/search?${searchParams.toString()}`);
  } catch {
    return null;
  }
}

async function fetchTabCounts(query: string): Promise<TabCounts> {
  const kinds: SearchKindFilter[] = ["all", ...SEARCH_KINDS];
  const responses = await Promise.all(
    kinds.map(async (kind) => {
      const response = await fetchSearch({
        q: query,
        kind: kind === "all" ? undefined : kind,
        page: 1,
        pageSize: 1,
      });
      return [kind, response?.total ?? 0] as const;
    }),
  );

  return Object.fromEntries(responses) as TabCounts;
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
    robots: {
      index: Boolean(trimmed),
      follow: true,
    },
  };
}

export default async function SearchPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { q, kind: kindParam, page: pageParam } = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const searchMessages = await loadNamespace(locale as Locale, "search");
  const messages = { ...baseMessages, search: searchMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "search" }) as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;

  const query = q?.trim() ?? "";
  const activeKind = parseKind(kindParam);
  const page = parsePage(pageParam);

  const [searchResponse, tabCounts] = query
    ? await Promise.all([
        fetchSearch({
          q: query,
          kind: activeKind === "all" ? undefined : activeKind,
          page,
        }),
        fetchTabCounts(query),
      ])
    : [null, null];

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

  const searchUnavailable = Boolean(query) && searchResponse === null;

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-4 motion-rise sm:py-6">
      <header className="mb-4 space-y-3">
        <h1 className="font-display text-h1 text-display-ink">{t("title")}</h1>
        <SearchInput
          locale={locale}
          initialQuery={query}
          autoFocus={!query}
          labels={{
            placeholder: t("placeholder"),
            submit: t("submit"),
            ariaLabel: t("input.ariaLabel"),
            suggestionsLabel: t("input.suggestionsLabel"),
            noSuggestions: t("input.noSuggestions"),
          }}
        />
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

      {searchUnavailable ? (
        <EmptyState
          title={t("unavailable.title")}
          body={t("unavailable.body")}
          data-testid="search-unavailable"
        />
      ) : query && searchResponse ? (
        searchResponse.total === 0 ? (
          <ZeroResults
            query={query}
            locale={locale}
            labels={{
              title: t("noResults.title", { query }),
              suggestionsTitle: t("noResults.suggestionsTitle"),
              categoriesTitle: t("noResults.categoriesTitle"),
              suggestionTerms,
              categories: categorySuggestions,
              askVergeoTitle: t("askVergeo.title"),
              askVergeoTeaser: t("askVergeo.teaser"),
              askVergeoSlotLabel: t("askVergeo.slotLabel"),
            }}
          />
        ) : tabCounts ? (
          <ResultsTabs
            locale={locale}
            query={query}
            activeKind={activeKind}
            page={page}
            response={searchResponse}
            tabCounts={tabCounts}
            labels={{
              ariaLabel: t("tabs.ariaLabel"),
              all: t("tabs.all"),
              products: t("tabs.products"),
              services: t("tabs.services"),
              events: t("tabs.events"),
              vendors: t("tabs.vendors"),
              count: t("tabs.count"),
              resultsCount: t("results.count", { count: searchResponse.total }),
              degraded: t("results.degraded"),
              priceFrom: t("result.priceFrom"),
              category: t("result.category"),
              loadMore: t("pagination.loadMore"),
            }}
          />
        ) : null
      ) : null}
    </main>
  );
}
