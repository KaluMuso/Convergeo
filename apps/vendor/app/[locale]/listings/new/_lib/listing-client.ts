import { createApiClient } from "@vergeo/config";

import type {
  CanonicalPreview,
  CategoryOption,
  ListingCreatePayload,
  ListingCreateResponse,
  SuggestItem,
} from "./types";

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

type SuggestResponse = {
  query: string;
  suggestions: SuggestItem[];
};

export function createListingClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    suggestProducts(query: string): Promise<SuggestItem[]> {
      const params = new URLSearchParams({ q: query, kind: "product", limit: "8" });
      return client
        .request<SuggestResponse>(`/search/suggest?${params.toString()}`)
        .then((response) => response.suggestions.filter((item) => item.entity_kind === "product"));
    },

    getCanonicalPreview(productId: string): Promise<CanonicalPreview> {
      return client.request<CanonicalPreview>(`/vendor/listings/canonical/${productId}`);
    },

    listCategories(): Promise<CategoryOption[]> {
      return client.request<CategoryOption[]>("/vendor/listings/categories");
    },

    createListing(payload: ListingCreatePayload): Promise<ListingCreateResponse> {
      return client.request<ListingCreateResponse>("/vendor/listings", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
  };
}
