"use client";

import { createApiClient } from "@vergeo/config";

import { getBrowserAccessToken } from "../../../../lib/access-token";
import { getApiBaseUrl } from "../../../../lib/api-base-url";

const API_BASE = getApiBaseUrl();

export const offersApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type AdminOfferType = "bxgy" | "bundle" | "buy_n_pay_m" | "free_gift";
export type AdminOfferStatus = "draft" | "active" | "paused" | "archived";
export type AdminOfferState = "live" | "admin_paused" | "scheduled" | "ended";

export type AdminOffer = {
  id: string;
  vendor_id: string;
  vendor_name: string | null;
  offer_type: AdminOfferType;
  title: string;
  status: AdminOfferStatus;
  starts_at: string | null;
  ends_at: string | null;
  gift_stock_total: number | null;
  gift_stock_reserved: number;
  per_customer_limit: number | null;
  max_applications_per_order: number;
  paused_by_admin: boolean;
  admin_note: string | null;
  live: boolean;
  cart_applicable: boolean;
};

export type AdminOfferList = {
  items: AdminOffer[];
  truncated: boolean;
};

export type AdminOfferFilters = {
  state: AdminOfferState | "all";
  status: AdminOfferStatus | "all";
  offerType: AdminOfferType | "all";
  q: string;
};

export const DEFAULT_FILTERS: AdminOfferFilters = {
  state: "all",
  status: "all",
  offerType: "all",
  q: "",
};

export const OFFER_STATES: AdminOfferState[] = ["live", "admin_paused", "scheduled", "ended"];
export const OFFER_STATUSES: AdminOfferStatus[] = ["draft", "active", "paused", "archived"];
export const OFFER_TYPES: AdminOfferType[] = ["bundle", "buy_n_pay_m", "bxgy", "free_gift"];

/** Query string for GET /admin/offers ("all" and blank filters are omitted). */
export function buildOffersQuery(filters: AdminOfferFilters): string {
  const params = new URLSearchParams();
  if (filters.state !== "all") {
    params.set("state", filters.state);
  }
  if (filters.status !== "all") {
    params.set("status", filters.status);
  }
  if (filters.offerType !== "all") {
    params.set("offer_type", filters.offerType);
  }
  const q = filters.q.trim().slice(0, 120);
  if (q) {
    params.set("q", q);
  }
  const query = params.toString();
  return query ? `/admin/offers?${query}` : "/admin/offers";
}

export function listOffers(filters: AdminOfferFilters): Promise<AdminOfferList> {
  return offersApi.request<AdminOfferList>(buildOffersQuery(filters));
}

/** Pause or lift an admin pause. The API writes one audit_log row per call. */
export function setOfferPaused(
  offerId: string,
  paused: boolean,
  note: string | null,
): Promise<AdminOffer> {
  return offersApi.request<AdminOffer>(
    `/admin/offers/${encodeURIComponent(offerId)}/${paused ? "pause" : "unpause"}`,
    { method: "POST", body: JSON.stringify({ note }) },
  );
}
