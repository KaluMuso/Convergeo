"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

const API_BASE = getApiBaseUrl();

export const moderationApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type ProductSummary = {
  id: string;
  name: string;
  slug: string;
  brand: string | null;
  category_id: string;
  status: string;
  aliases: string[];
};

export type DuplicatePair = {
  product_a: ProductSummary;
  product_b: ProductSummary;
  similarity: number;
};

export type MergeProductsResponse = {
  survivor_id: string;
  loser_id: string;
  listings_repointed: number;
  merged_aliases: string[];
  slug_redirect_from: string;
  slug_redirect_to: string;
  idempotent: boolean;
};

export type ProductRelationItem = {
  related_product_id: string;
  name: string;
  slug: string;
  position: number;
};

export type ProductRelationsResponse = {
  product_id: string;
  related: ProductRelationItem[];
};

export function searchProducts(query: string, limit = 20): Promise<ProductSummary[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return moderationApi.request<ProductSummary[]>(`/admin/products/search?${params.toString()}`);
}

export function getProductRelations(productId: string): Promise<ProductRelationsResponse> {
  return moderationApi.request<ProductRelationsResponse>(`/admin/products/${productId}/relations`);
}

export function setProductRelations(
  productId: string,
  relatedProductIds: string[],
): Promise<ProductRelationsResponse> {
  return moderationApi.request<ProductRelationsResponse>(`/admin/products/${productId}/relations`, {
    method: "PUT",
    body: JSON.stringify({ related_product_ids: relatedProductIds }),
  });
}

export type CanonicalQueueItem = {
  id: string;
  name: string;
  slug: string;
  brand: string | null;
  category_id: string;
  status: string;
  vendor_id: string | null;
  vendor_display_name: string | null;
  listing_id: string | null;
  image_urls: string[];
  updated_at: string;
};

export type CanonicalStatusResponse = {
  product_id: string;
  status: string;
  listings_updated: number;
  idempotent: boolean;
};

export function listPendingCanonicalProducts(): Promise<CanonicalQueueItem[]> {
  return moderationApi.request<CanonicalQueueItem[]>(
    "/admin/products/canonical?status=pending_moderation",
  );
}

export function patchCanonicalProductStatus(
  productId: string,
  body: { status: "active" | "rejected"; reason?: string | null },
): Promise<CanonicalStatusResponse> {
  return moderationApi.request<CanonicalStatusResponse>(
    `/admin/products/canonical/${productId}/status`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  );
}
