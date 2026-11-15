import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type OfferType = "bxgy" | "bundle" | "buy_n_pay_m" | "free_gift";
export type OfferStatus = "draft" | "active" | "paused" | "archived";
export type OfferItemRole = "trigger" | "reward" | "anchor" | "addon" | "eligible";
export type OfferItemKind = "product" | "service" | "event";
export type BundlePricing = "addon_percent_off" | "fixed_price";

export const OFFER_TYPES: OfferType[] = ["bxgy", "bundle", "buy_n_pay_m", "free_gift"];

export type OfferItem = {
  role: OfferItemRole;
  item_kind: OfferItemKind;
  ref_id: string;
  qty: number;
  title?: string | null;
  unit_price_ngwee?: number | null;
  available?: boolean;
};

export type Offer = {
  id: string;
  vendor_id: string;
  offer_type: OfferType;
  title: string;
  status: OfferStatus;
  starts_at: string | null;
  ends_at: string | null;
  buy_qty: number | null;
  get_qty: number | null;
  bundle_pricing: BundlePricing | null;
  addon_percent_off: number | null;
  bundle_price_ngwee: number | null;
  buy_n: number | null;
  pay_m: number | null;
  gift_stock_total: number | null;
  gift_stock_reserved: number;
  gift_stock_available: number | null;
  max_applications_per_order: number;
  per_customer_limit: number | null;
  paused_by_admin: boolean;
  live: boolean;
  cart_applicable: boolean;
  items: OfferItem[];
};

export type OfferPayload = {
  offer_type: OfferType;
  title: string;
  status: Exclude<OfferStatus, "archived">;
  starts_at?: string | null;
  ends_at?: string | null;
  buy_qty?: number | null;
  get_qty?: number | null;
  bundle_pricing?: BundlePricing | null;
  addon_percent_off?: number | null;
  bundle_price_ngwee?: number | null;
  buy_n?: number | null;
  pay_m?: number | null;
  gift_stock_total?: number | null;
  max_applications_per_order?: number;
  per_customer_limit?: number | null;
  items: Array<Pick<OfferItem, "role" | "item_kind" | "ref_id" | "qty">>;
};

export type OfferPreview = {
  applies: boolean;
  list_total_ngwee: number;
  pay_ngwee: number;
  savings_ngwee: number;
  gift_qty: number;
  gift_value_ngwee: number;
};

export type PickerOption = {
  kind: OfferItemKind;
  id: string;
  title: string;
  price_ngwee: number | null;
};

/** Roles a type uses, and which kinds each role accepts (mirrors the API rules). */
export const TYPE_ROLES: Record<
  OfferType,
  Array<{ role: OfferItemRole; kinds: OfferItemKind[]; max: number }>
> = {
  bxgy: [
    { role: "trigger", kinds: ["product", "service", "event"], max: 20 },
    { role: "reward", kinds: ["product"], max: 1 },
  ],
  free_gift: [
    { role: "trigger", kinds: ["product", "service", "event"], max: 20 },
    { role: "reward", kinds: ["product"], max: 1 },
  ],
  bundle: [
    { role: "anchor", kinds: ["product"], max: 1 },
    { role: "addon", kinds: ["product"], max: 5 },
  ],
  buy_n_pay_m: [{ role: "eligible", kinds: ["product"], max: 20 }],
};

/** Largest per-customer limit the API accepts (offers_per_customer_limit_check). */
export const MAX_PER_CUSTOMER_LIMIT = 1000;

/**
 * Parse the "uses per customer" input: blank = unlimited (null), a whole number
 * 1..1000 = that limit, anything else = "invalid" (the form blocks saving).
 */
export function parsePerCustomerLimit(raw: string): number | null | "invalid" {
  const value = raw.trim();
  if (value === "") {
    return null;
  }
  if (!/^\d+$/.test(value)) {
    return "invalid";
  }
  const parsed = Number.parseInt(value, 10);
  return parsed >= 1 && parsed <= MAX_PER_CUSTOMER_LIMIT ? parsed : "invalid";
}

/** Strip fields that do not belong to the chosen type (the API rejects them). */
export function payloadForType(payload: OfferPayload): OfferPayload {
  const base: OfferPayload = {
    offer_type: payload.offer_type,
    title: payload.title.trim(),
    status: payload.status,
    starts_at: payload.starts_at ?? null,
    ends_at: payload.ends_at ?? null,
    max_applications_per_order: payload.max_applications_per_order ?? 1,
    per_customer_limit: payload.per_customer_limit ?? null,
    items: payload.items.filter((item) =>
      TYPE_ROLES[payload.offer_type].some((spec) => spec.role === item.role),
    ),
  };
  switch (payload.offer_type) {
    case "bxgy":
      return {
        ...base,
        buy_qty: payload.buy_qty ?? null,
        get_qty: payload.get_qty ?? null,
        gift_stock_total: payload.gift_stock_total ?? null,
      };
    case "free_gift":
      return { ...base, gift_stock_total: payload.gift_stock_total ?? null };
    case "bundle":
      return payload.bundle_pricing === "fixed_price"
        ? {
            ...base,
            bundle_pricing: "fixed_price",
            bundle_price_ngwee: payload.bundle_price_ngwee ?? null,
          }
        : {
            ...base,
            bundle_pricing: "addon_percent_off",
            addon_percent_off: payload.addon_percent_off ?? null,
          };
    case "buy_n_pay_m":
      return { ...base, buy_n: payload.buy_n ?? null, pay_m: payload.pay_m ?? null };
  }
}

export function createOffersClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  return {
    list(): Promise<{ items: Offer[]; max_discount_pct: number; max_active_offers: number }> {
      return client.request("/vendor/offers");
    },
    get(id: string): Promise<Offer> {
      return client.request(`/vendor/offers/${encodeURIComponent(id)}`);
    },
    create(payload: OfferPayload): Promise<Offer> {
      return client.request("/vendor/offers", {
        method: "POST",
        body: JSON.stringify(payloadForType(payload)),
      });
    },
    update(id: string, payload: OfferPayload): Promise<Offer> {
      return client.request(`/vendor/offers/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(payloadForType(payload)),
      });
    },
    archive(id: string): Promise<Offer> {
      return client.request(`/vendor/offers/${encodeURIComponent(id)}`, { method: "DELETE" });
    },
    preview(payload: OfferPayload): Promise<OfferPreview> {
      return client.request("/vendor/offers/preview", {
        method: "POST",
        body: JSON.stringify(payloadForType(payload)),
      });
    },
    async pickerOptions(): Promise<PickerOption[]> {
      const [listings, services, events] = await Promise.all([
        client
          .request<Array<{ id: string; title: string; price_ngwee: number; status: string }>>(
            "/vendor/listings",
          )
          .catch(() => []),
        client
          .request<{
            items: Array<{ id: string; title: string; from_price_ngwee: number | null }>;
          }>("/vendor/services")
          .catch(() => ({ items: [] })),
        client
          .request<{ items: Array<{ id: string; title: string; status: string }> }>(
            "/organiser/events",
          )
          .catch(() => ({ items: [] })),
      ]);
      return [
        ...listings
          .filter((row) => row.status !== "removed")
          .map((row) => ({
            kind: "product" as const,
            id: row.id,
            title: row.title,
            price_ngwee: row.price_ngwee,
          })),
        ...services.items.map((row) => ({
          kind: "service" as const,
          id: row.id,
          title: row.title,
          price_ngwee: row.from_price_ngwee,
        })),
        ...events.items
          .filter((row) => row.status !== "cancelled" && row.status !== "completed")
          .map((row) => ({
            kind: "event" as const,
            id: row.id,
            title: row.title,
            price_ngwee: null,
          })),
      ];
    },
  };
}

/** ISO instant -> value for <input type="datetime-local"> in the browser's zone. */
export function isoToLocalInput(iso: string | null): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

/** <input type="datetime-local"> value -> ISO instant with offset, or null. */
export function localInputToIso(value: string): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}
