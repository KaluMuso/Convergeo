"use client";

import { formatK } from "@vergeo/i18n";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { ProductCard } from "@vergeo/ui/src/product-card";
import { Tabs } from "@vergeo/ui/src/tabs";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useLocalWishlist } from "../plp/use-local-wishlist";
import {
  ProgressiveLoadControls,
  type ProgressiveLoadControlsLabels,
} from "../progressive-load/progressive-load-controls";
import { useProgressiveLoad } from "../progressive-load/use-progressive-load";

import {
  SEARCH_KINDS,
  searchTabKinds,
  type SearchKind,
  type SearchKindFilter,
} from "./search-kinds";
import { searchResultHref } from "./search-result-href";

export type { SearchKind, SearchKindFilter };
export { SEARCH_KINDS, searchTabKinds };

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
  /** Public route slug (product/vendor/event) when resolved by the search API. */
  slug?: string | null;
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

export type TabCounts = Record<SearchKindFilter, number>;

export type ResultsTabsLabels = ProgressiveLoadControlsLabels & {
  ariaLabel: string;
  all: string;
  products: string;
  services: string;
  events: string;
  vendors: string;
  count: string;
  resultsCount: string;
  degraded: string;
  priceFrom: string;
  category: string;
  /** Honest fallback when search hits omit vendor (never invent a shop name). */
  marketplaceListing: string;
  wishlist: string;
  wishlistRemove: string;
  mediaEmpty: string;
  noReviews: string;
  reviewCount: string;
};

export type ResultsTabsProps = {
  locale: string;
  query: string;
  activeKind: SearchKindFilter;
  page: number;
  response: SearchResponse;
  tabCounts: TabCounts;
  labels: ResultsTabsLabels;
  /** API origin for client page appends (same base as SSR). */
  apiBaseUrl: string;
};

function tabLabel(labels: ResultsTabsLabels, kind: SearchKindFilter, count: number): string {
  const nameMap: Record<SearchKindFilter, string> = {
    all: labels.all,
    products: labels.products,
    services: labels.services,
    events: labels.events,
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

function SearchResultRow({
  hit,
  locale,
  labels,
}: {
  hit: SearchHit;
  locale: string;
  labels: ResultsTabsLabels;
}) {
  const imagePublicId = readImagePublicId(hit);
  const href = searchResultHref(locale, hit);
  const category = formatCategoryLabel(hit.category_path);
  const priceNgwee = hit.price_min_ngwee ?? hit.price_max_ngwee;

  return (
    <article
      className="flex gap-3 rounded-lg border border-border bg-surface p-3"
      data-testid="search-result-row"
    >
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

function SearchProductCard({
  hit,
  locale,
  labels,
}: {
  hit: SearchHit;
  locale: string;
  labels: ResultsTabsLabels;
}) {
  const imagePublicId = readImagePublicId(hit);
  const href = searchResultHref(locale, hit);
  const priceNgwee = hit.price_min_ngwee ?? hit.price_max_ngwee ?? 0;
  const category = formatCategoryLabel(hit.category_path);
  const slug = typeof hit.slug === "string" && hit.slug.trim() ? hit.slug : null;
  const { isWishlisted, toggleWishlist, enabled } = useLocalWishlist(slug);
  const wishlistLabel = isWishlisted ? labels.wishlistRemove : labels.wishlist;
  const [wishlistStatusAnnouncement, setWishlistStatusAnnouncement] = useState("");
  const wishlistMountedRef = useRef(false);

  useEffect(() => {
    if (!wishlistMountedRef.current) {
      wishlistMountedRef.current = true;
      return;
    }
    setWishlistStatusAnnouncement(wishlistLabel);
  }, [isWishlisted, wishlistLabel]);

  const card = (
    <ProductCard
      title={hit.title}
      vendorLabel={category ?? labels.marketplaceListing}
      ngwee={priceNgwee}
      rating={0}
      reviewCount={0}
      noReviewsLabel={labels.noReviews}
      reviewCountLabel={labels.reviewCount.replace("{count}", "0")}
      quickAddLabel=""
      wishlistLabel={wishlistLabel}
      wishlistStatusAnnouncement={wishlistStatusAnnouncement}
      density="compact"
      mediaEmptyLabel={labels.mediaEmpty}
      isWishlisted={isWishlisted}
      onWishlistToggle={enabled ? toggleWishlist : undefined}
      media={
        imagePublicId ? (
          <CloudinaryImage
            publicId={imagePublicId}
            alt={hit.title}
            width={360}
            ratio="1/1"
            sizes="(max-width: 360px) 50vw, 25vw"
            className="h-full w-full object-cover"
          />
        ) : undefined
      }
    />
  );

  return (
    <Link href={href} className="min-w-0 no-underline" data-testid="search-product-card">
      {card}
    </Link>
  );
}

function ResultsList({
  hits,
  locale,
  labels,
  preferProductGrid,
}: {
  hits: SearchHit[];
  locale: string;
  labels: ResultsTabsLabels;
  preferProductGrid: boolean;
}) {
  if (hits.length === 0) {
    return null;
  }

  const productHits = hits.filter((hit) => hit.entity_kind === "product");
  const otherHits = hits.filter((hit) => hit.entity_kind !== "product");
  const showProductGrid = preferProductGrid || productHits.length > 0;

  return (
    <div className="space-y-4" data-testid="search-results-list">
      {showProductGrid && productHits.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3" data-testid="search-product-grid">
          {productHits.map((hit) => (
            <SearchProductCard key={hit.id} hit={hit} locale={locale} labels={labels} />
          ))}
        </div>
      ) : null}

      {otherHits.length > 0 || (!showProductGrid && hits.length > 0) ? (
        <ul className="space-y-3 p-0">
          {(showProductGrid ? otherHits : hits).map((hit) => (
            <li key={hit.id}>
              <SearchResultRow hit={hit} locale={locale} labels={labels} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function nextPageCursor(response: SearchResponse): string | null {
  if (response.page * response.page_size < response.total) {
    return String(response.page + 1);
  }
  return null;
}

export function ResultsTabs({
  locale,
  query,
  activeKind,
  page,
  response,
  tabCounts,
  labels,
  apiBaseUrl,
}: ResultsTabsProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const resetKey = `${locale}|${query}|${activeKind}|${page}|${response.page_size}|${response.total}`;

  const fetchPage = useCallback(
    async (cursor: string, signal: AbortSignal) => {
      const params = new URLSearchParams({
        q: query,
        page: cursor,
        page_size: String(response.page_size),
      });
      if (activeKind !== "all") {
        params.set("kind", activeKind);
      }
      const res = await fetch(`${apiBaseUrl}/search?${params.toString()}`, { signal });
      if (!res.ok) {
        throw new Error(`Search load failed (${res.status})`);
      }
      const body = (await res.json()) as SearchResponse;
      return {
        items: body.results,
        nextCursor: nextPageCursor(body),
      };
    },
    [activeKind, apiBaseUrl, query, response.page_size],
  );

  const { items, status, hasMore, lastAppendedCount, loadMore, sentinelRef } =
    useProgressiveLoad<SearchHit>({
      initialItems: response.results,
      initialCursor: nextPageCursor(response),
      resetKey,
      fetchPage,
    });

  const navigateWithKind = useCallback(
    (kind: SearchKindFilter) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("q", query);
      // Tab change resets pagination / progressive cursor via full navigation.
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

  const controlLabels: ProgressiveLoadControlsLabels = useMemo(
    () => ({
      loadMore: labels.loadMore,
      loading: labels.loading,
      moreLoaded: labels.moreLoaded,
      endOfResults: labels.endOfResults,
      loadError: labels.loadError,
      retry: labels.retry,
    }),
    [labels],
  );

  const tabItems = useMemo(() => {
    const kinds = searchTabKinds();
    return kinds.map((kind) => ({
      key: kind,
      label: (
        <span data-testid={`search-tab-${kind}`}>
          {tabLabel(labels, kind, tabCounts[kind] ?? 0)}
        </span>
      ),
      panel: (
        <div className="space-y-4">
          <p className="text-sm text-text-2" aria-live="polite" data-testid="search-results-count">
            {labels.resultsCount}
          </p>
          {response.degraded ? <p className="text-xs text-text-3">{labels.degraded}</p> : null}
          <ResultsList
            hits={items}
            locale={locale}
            labels={labels}
            preferProductGrid={activeKind === "products" || activeKind === "all"}
          />
          <ProgressiveLoadControls
            status={status}
            hasMore={hasMore}
            lastAppendedCount={lastAppendedCount}
            labels={controlLabels}
            onLoadMore={loadMore}
            sentinelRef={sentinelRef}
            testIdPrefix="search"
          />
        </div>
      ),
    }));
  }, [
    activeKind,
    controlLabels,
    hasMore,
    items,
    labels,
    lastAppendedCount,
    loadMore,
    locale,
    response.degraded,
    sentinelRef,
    status,
    tabCounts,
  ]);

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
