"use client";

import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

export const moderationApi = createApiClient({
  baseUrl: API_BASE,
  getToken: () => {
    if (typeof window === "undefined") {
      return null;
    }
    return window.sessionStorage.getItem("vergeo_admin_token");
  },
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
