"use client";

import { formatK } from "@vergeo/i18n";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { Tabs } from "@vergeo/ui/src/tabs";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import type { SearchKind } from "./search-input";

export type SearchHit = {
  id: string;
  entity_kind: string;
  entity_id: string;
  title: string;
  body: string | null;
  category_path: string | null;
  price_min_ngwee: number | null;
  price_max_ngwee: number | null;
  lat: number | null;
  lng: number | null;
  locale_terms: string[] | null;
  boost_signals: Record<string, unknown>;
  rrf_score: number;
};

export type SearchResponse = {
  query: string;
  expanded_query: string;
  page: number;
  page_size: number;
  total: number;
  results: SearchHit[];
  degraded: boolean;
};

export type SearchKindFilter = SearchKind | "all";

export const SEARCH_KINDS: SearchKind[] = ["products", "services", "events", "supplies", "vendors"];

export type TabCounts = Record<SearchKindFilter, number>;

export type ResultsTabsLabels = {
  ariaLabel: string;
  all: string;
  products: string;
  services: string;
  events: string;
  supplies: string;
  vendors: string;
  count: string;
  resultsCount: string;
  degraded: string;
  priceFrom: string;
  category: string;
  loadMore: string;
};

export type ResultsTabsProps = {
  locale: string;
  query: string;
  activeKind: SearchKindFilter;
  page: number;
  response: SearchResponse;
  tabCounts: TabCounts;
  labels: ResultsTabsLabels;
};

function tabLabel(labels: ResultsTabsLabels, kind: SearchKindFilter, count: number): string {
  const nameMap: Record<SearchKindFilter, string> = {
    all: labels.all,
    products: labels.products,
    services: labels.services,
    events: labels.events,
    supplies: labels.supplies,
    vendors: labels.vendors,
  };
  return labels.count.replace("{label}", nameMap[kind]).replace("{count}", String(count));
}

function readImagePublicId(hit: SearchHit): string | null {
  const signals = hit.boost_signals;
  const candidates = ["image_public_id", "public_id", "thumbnail_public_id"];
  for (const key of candidates) {
    const value = signals[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return null;
}

function resultHref(locale: string, hit: SearchHit): string {
  const id = encodeURIComponent(hit.entity_id);
  switch (hit.entity_kind) {
    case "product":
      return `/${locale}/p/${id}`;
    case "service":
      return `/${locale}/services/${id}`;
    case "event":
      return `/${locale}/e/${id}`;
    case "listing":
      return `/${locale}/p/${id}`;
    case "vendor":
      return `/${locale}/v/${id}`;
    default:
      return `/${locale}/search?q=${encodeURIComponent(hit.title)}`;
  }
}

function formatCategoryLabel(categoryPath: string | null): string | null {
  if (!categoryPath) {
    return null;
  }
  const leaf = categoryPath.split("/").filter(Boolean).at(-1);
  if (!leaf) {
    return null;
  }
  return leaf.replace(/-/g, " ");
}

function SearchResultCard({
  hit,
  locale,
  labels,
}: {
  hit: SearchHit;
  locale: string;
  labels: ResultsTabsLabels;
}) {
  const imagePublicId = readImagePublicId(hit);
  const href = resultHref(locale, hit);
  const category = formatCategoryLabel(hit.category_path);
  const priceNgwee = hit.price_min_ngwee ?? hit.price_max_ngwee;

  return (
    <article className="flex gap-3 rounded-lg border border-border bg-surface p-3">
      {imagePublicId ? (
        <Link href={href} className="relative block h-20 w-20 shrink-0 overflow-hidden rounded-md">
          <CloudinaryImage
            publicId={imagePublicId}
            alt=""
            width={720}
            sizes="80px"
            className="h-full w-full object-cover"
          />
        </Link>
      ) : null}
      <div className="min-w-0 flex-1">
        <h3 className="truncate font-medium text-text">
          <Link
            href={href}
            className="hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            {hit.title}
          </Link>
        </h3>
        {hit.body ? <p className="mt-1 line-clamp-2 text-sm text-text-2">{hit.body}</p> : null}
        {category ? (
          <p className="mt-1 text-xs text-text-3">
            {labels.category.replace("{category}", category)}
          </p>
        ) : null}
        {priceNgwee != null ? (
          <p className="mt-1 text-sm font-medium text-text">
            {labels.priceFrom.replace("{price}", formatK(priceNgwee))}
          </p>
        ) : null}
      </div>
    </article>
  );
}

function ResultsList({
  hits,
  locale,
  labels,
}: {
  hits: SearchHit[];
  locale: string;
  labels: ResultsTabsLabels;
}) {
  if (hits.length === 0) {
    return null;
  }

  return (
    <ul className="space-y-3" data-testid="search-results-list">
      {hits.map((hit) => (
        <li key={hit.id}>
          <SearchResultCard hit={hit} locale={locale} labels={labels} />
        </li>
      ))}
    </ul>
  );
}

export function ResultsTabs({
  locale,
  query,
  activeKind,
  page,
  response,
  tabCounts,
  labels,
}: ResultsTabsProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const navigateWithKind = useCallback(
    (kind: SearchKindFilter) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("q", query);
      params.delete("page");
      if (kind === "all") {
        params.delete("kind");
      } else {
        params.set("kind", kind);
      }
      router.push(`/${locale}/search?${params.toString()}`);
    },
    [locale, query, router, searchParams],
  );

  const loadMore = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("q", query);
    params.set("page", String(page + 1));
    if (activeKind !== "all") {
      params.set("kind", activeKind);
    }
    router.push(`/${locale}/search?${params.toString()}`);
  }, [activeKind, locale, page, query, router, searchParams]);

  const tabItems = useMemo(() => {
    const kinds: SearchKindFilter[] = ["all", ...SEARCH_KINDS];
    return kinds.map((kind) => ({
      key: kind,
      label: (
        <span data-testid={`search-tab-${kind}`}>
          {tabLabel(labels, kind, tabCounts[kind] ?? 0)}
        </span>
      ),
      panel: (
        <div className="space-y-4">
          <p className="text-sm text-text-2">{labels.resultsCount}</p>
          {response.degraded ? <p className="text-xs text-text-3">{labels.degraded}</p> : null}
          <ResultsList hits={response.results} locale={locale} labels={labels} />
          {response.page * response.page_size < response.total ? (
            <button
              type="button"
              onClick={loadMore}
              className="inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-border bg-surface px-4 text-sm font-medium text-primary hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {labels.loadMore}
            </button>
          ) : null}
        </div>
      ),
    }));
  }, [labels, locale, loadMore, response, tabCounts]);

  return (
    <Tabs
      ariaLabel={labels.ariaLabel}
      value={activeKind}
      onValueChange={(key) => navigateWithKind(key as SearchKindFilter)}
      items={tabItems}
      tabListClassName="scrollbar-none"
    />
  );
}
