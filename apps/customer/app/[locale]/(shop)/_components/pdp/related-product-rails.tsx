"use client";

import { useEffect, useState } from "react";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";

import {
  RelatedProducts,
  type RelatedProductItem,
  type RelatedProductsLabels,
} from "./related-products";

export type RelatedRailsLabels = Omit<RelatedProductsLabels, "heading"> & {
  vendorHeading: string;
  categoryHeading: string;
  /** "More from this store" (recommendations scope=store). */
  storeHeading?: string;
  /** "Similar in this category" (recommendations scope=category). */
  similarHeading?: string;
  loading: string;
  unavailable: string;
};
type Rails = {
  product_slug: string;
  listing_id: string | null;
  vendor_name: string | null;
  same_vendor: RelatedProductItem[];
  same_category: RelatedProductItem[];
  source?: "recommendations" | "related-rails";
};

/** /products/{slug}/recommendations item (CatalogListingItem subset). */
type RecommendationItem = {
  id: string;
  title: string;
  product_slug: string | null;
  vendor_name: string;
  price_ngwee: number;
  image_public_id: string | null;
};

function toRelatedItem(item: RecommendationItem): RelatedProductItem {
  return {
    listing_id: item.id,
    vendor_name: item.vendor_name,
    slug: item.product_slug ?? "",
    name: item.title,
    image_public_id: item.image_public_id,
    from_price_ngwee: item.price_ngwee,
  };
}

export function RelatedProductRails({
  locale,
  slug,
  listingId,
  labels,
  cloudName,
}: {
  locale: string;
  slug: string;
  listingId: string | null;
  labels: RelatedRailsLabels;
  cloudName?: string;
}) {
  const key = `${slug}:${listingId ?? ""}`;
  const [state, setState] = useState<{
    key: string;
    data?: Rails;
    error?: boolean;
  }>({ key: "" });
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const query = listingId
      ? `?listing_id=${encodeURIComponent(listingId)}`
      : "";
    const url = absoluteApiUrl(
      `/products/${encodeURIComponent(slug)}/related-rails${query}`,
    );
    const recUrl = (scope: "store" | "category") =>
      absoluteApiUrl(
        `/products/${encodeURIComponent(slug)}/recommendations?scope=${scope}&limit=8`,
      );
    /** Primary source: /recommendations (scope=store|category). */
    async function loadRecommendations(): Promise<Rails> {
      const store = recUrl("store");
      const category = recUrl("category");
      if (!store || !category) throw new Error("API unavailable");
      const [storeRes, categoryRes] = await Promise.all([
        fetch(store, { signal: controller.signal, cache: "no-store" }),
        fetch(category, { signal: controller.signal, cache: "no-store" }),
      ]);
      if (!storeRes.ok || !categoryRes.ok)
        throw new Error("Recommendations unavailable");
      const [storeData, categoryData] = (await Promise.all([
        storeRes.json(),
        categoryRes.json(),
      ])) as [
        { items?: RecommendationItem[] },
        { items?: RecommendationItem[] },
      ];
      if (!Array.isArray(storeData.items) || !Array.isArray(categoryData.items))
        throw new Error("Invalid recommendations");
      return {
        product_slug: slug,
        listing_id: listingId,
        vendor_name: storeData.items[0]?.vendor_name ?? null,
        same_vendor: storeData.items.map(toRelatedItem),
        same_category: categoryData.items.map(toRelatedItem),
        source: "recommendations",
      };
    }
    /** Fallback: legacy /related-rails. */
    async function loadRelatedRails(): Promise<Rails> {
      if (!url) throw new Error("API unavailable");
      const response = await fetch(url, {
        signal: controller.signal,
        cache: "no-store",
      });
      if (!response.ok) throw new Error("Recommendations unavailable");
      const data = (await response.json()) as Rails;
      if (
        data.product_slug !== slug ||
        !Array.isArray(data.same_vendor) ||
        !Array.isArray(data.same_category)
      )
        throw new Error("Invalid recommendations");
      if (data.listing_id !== null && data.listing_id !== listingId)
        throw new Error("Wrong seller");
      return data;
    }
    async function load() {
      try {
        let data: Rails;
        try {
          data = await loadRecommendations();
        } catch (error) {
          if (controller.signal.aborted) throw error;
          data = await loadRelatedRails();
        }
        if (active) setState({ key, data });
      } catch {
        if (active) setState({ key, error: true });
      }
    }
    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [key, slug, listingId]);

  if (state.key !== key)
    return (
      <p role="status" className="text-sm text-text-2">
        {labels.loading}
      </p>
    );
  if (state.error)
    return (
      <p role="status" className="text-sm text-text-2">
        {labels.unavailable}
      </p>
    );
  if (!state.data) return null;
  const data = state.data;
  const seen = new Set([slug]);
  const unique = (items: RelatedProductItem[]) =>
    items.filter((item) => {
      if (
        !item.slug ||
        seen.has(item.slug) ||
        !item.listing_id ||
        !item.from_price_ngwee ||
        item.from_price_ngwee <= 0
      )
        return false;
      seen.add(item.slug);
      return true;
    });
  const vendor = unique(
    data.source === "recommendations" ||
      (data.listing_id === listingId && data.vendor_name)
      ? data.same_vendor
      : [],
  );
  const category = unique(data.same_category);
  return (
    <div
      className="flex min-w-0 flex-col gap-8"
      data-testid="pdp-related-rails"
    >
      <RelatedProducts
        locale={locale}
        items={vendor}
        labels={{
          ...labels,
          heading:
            data.source === "recommendations" && labels.storeHeading
              ? labels.storeHeading
              : labels.vendorHeading.replace(
                  "{vendor}",
                  data.vendor_name ?? "",
                ),
        }}
        cloudName={cloudName}
        headingId="pdp-related-vendor-heading"
      />
      <RelatedProducts
        locale={locale}
        items={category}
        labels={{
          ...labels,
          heading:
            data.source === "recommendations" && labels.similarHeading
              ? labels.similarHeading
              : labels.categoryHeading,
        }}
        cloudName={cloudName}
        headingId="pdp-related-category-heading"
      />
    </div>
  );
}
