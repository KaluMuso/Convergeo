import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

export type ListingCondition = "new" | "refurbished";
export type StockMode = "tracked" | "always_available";
export type ListingStatus = "draft" | "active" | "paused";

export type PriceTier = {
  min_qty: number;
  price_ngwee: number;
};

export type ListingSummary = {
  id: string;
  title: string;
  price_ngwee: number;
  compare_at_ngwee: number | null;
  condition: ListingCondition;
  stock_mode: StockMode;
  stock_qty: number | null;
  wholesale: boolean;
  price_tiers: PriceTier[] | null;
  moq: number;
  returnable: boolean;
  return_window_hours: number | null;
  status: ListingStatus | string;
  product_id: string | null;
};

export type ListingUpdatePayload = {
  price_ngwee?: number;
  compare_at_ngwee?: number | null;
  condition?: ListingCondition;
  stock_mode?: StockMode;
  stock_qty?: number | null;
  wholesale?: boolean;
  price_tiers?: PriceTier[] | null;
  moq?: number;
  returnable?: boolean;
  return_window_hours?: number | null;
  status?: ListingStatus;
};

export type CartRevalidationSummary = {
  triggered: boolean;
  affected_carts: number;
  has_changes: boolean;
};

export type ListingUpdateResponse = {
  listing: ListingSummary;
  cart_revalidation?: CartRevalidationSummary | null;
};

export type ListingDeleteResponse = {
  listing_id: string;
  deleted: boolean;
  paused_instead: boolean;
  status: string;
  message_key: string;
};

export function createManageClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    listListings(): Promise<ListingSummary[]> {
      return client.request<ListingSummary[]>("/vendor/listings");
    },

    getListing(listingId: string): Promise<ListingSummary> {
      return client.request<ListingSummary>(`/vendor/listings/${listingId}`);
    },

    updateListing(
      listingId: string,
      payload: ListingUpdatePayload,
    ): Promise<ListingUpdateResponse> {
      return client.request<ListingUpdateResponse>(`/vendor/listings/${listingId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    },

    adjustStock(listingId: string, delta: number): Promise<ListingUpdateResponse> {
      return client.request<ListingUpdateResponse>(`/vendor/listings/${listingId}/stock`, {
        method: "PATCH",
        body: JSON.stringify({ delta }),
      });
    },

    pauseListing(listingId: string): Promise<ListingUpdateResponse> {
      return client.request<ListingUpdateResponse>(`/vendor/listings/${listingId}/pause`, {
        method: "POST",
      });
    },

    unpauseListing(listingId: string): Promise<ListingUpdateResponse> {
      return client.request<ListingUpdateResponse>(`/vendor/listings/${listingId}/unpause`, {
        method: "POST",
      });
    },

    deleteListing(listingId: string): Promise<ListingDeleteResponse> {
      return client.request<ListingDeleteResponse>(`/vendor/listings/${listingId}`, {
        method: "DELETE",
      });
    },
  };
}
