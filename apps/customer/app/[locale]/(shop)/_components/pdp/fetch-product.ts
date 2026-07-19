import { createApiClient } from "@vergeo/config";

import { absoluteApiUrl, getApiBaseUrl } from "../../../../../lib/api-base-url";

import type { ListingCondition } from "./condition-badge";

export const PRODUCT_REVALIDATE_SECONDS = 3600;
export const PRODUCT_CACHE_TAG_PREFIX = "product:";

export type ProductImage = {
  public_id: string;
  position: number;
  listing_id: string;
};

export type VendorLocation = {
  landmark: string;
  lat: number;
  lng: number;
};

export type VendorSummary = {
  id: string;
  slug: string;
  display_name: string;
  preferred_badge: boolean;
  rating_avg: number | null;
  rating_count: number;
  location: VendorLocation | null;
};

export type Listing = {
  id: string;
  title: string;
  price_ngwee: number;
  condition: ListingCondition;
  stock_mode: "tracked" | "always_available";
  stock_qty: number | null;
  moq: number;
  wholesale: boolean;
  in_stock: boolean;
  vendor: VendorSummary;
  images: ProductImage[];
};

export type ProductDetail = {
  id: string;
  name: string;
  slug: string;
  brand: string | null;
  description: string | null;
  spec: Record<string, unknown>;
  category_id: string;
  images: ProductImage[];
  listings: Listing[];
  listing_count: number;
};

export type ProductFetchResult =
  | { kind: "product"; data: ProductDetail }
  | { kind: "redirect"; slug: string }
  | { kind: "not_found" }
  | { kind: "unavailable" };

export function productCacheTag(slug: string): string {
  return `${PRODUCT_CACHE_TAG_PREFIX}${slug}`;
}

function parseRedirectSlug(location: string, currentSlug: string): string | null {
  const pathOnly = location.split("?")[0] ?? location;
  const redirectedSlug = pathOnly.replace(/^\/products\//, "").replace(/\/$/, "");
  if (!redirectedSlug || redirectedSlug === currentSlug) {
    return null;
  }
  return redirectedSlug;
}

/**
 * Load a product for the PDP. Distinguishes:
 * - not_found: API confirmed the product does not exist (404)
 * - unavailable: network / 5xx / missing API base (safe retry UI, not a soft-404)
 */
export async function fetchProduct(slug: string): Promise<ProductFetchResult> {
  const url = absoluteApiUrl(`/products/${encodeURIComponent(slug)}`);
  if (!url) {
    return { kind: "unavailable" };
  }

  try {
    const response = await fetch(url, {
      next: {
        revalidate: PRODUCT_REVALIDATE_SECONDS,
        tags: [productCacheTag(slug), "products"],
      },
      redirect: "manual",
    });

    if (response.status === 301 || response.status === 302 || response.status === 308) {
      const location = response.headers.get("location");
      if (location) {
        const redirectedSlug = parseRedirectSlug(location, slug);
        if (redirectedSlug) {
          return { kind: "redirect", slug: redirectedSlug };
        }
      }
      return { kind: "not_found" };
    }

    if (response.status === 404) {
      return { kind: "not_found" };
    }

    if (!response.ok) {
      return { kind: "unavailable" };
    }

    return { kind: "product", data: (await response.json()) as ProductDetail };
  } catch {
    // Transient transport failure — try the shared client once before surfacing
    // an unavailable state (never collapse into a soft-404).
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl() });
      const data = await client.request<ProductDetail>(`/products/${encodeURIComponent(slug)}`);
      return { kind: "product", data };
    } catch (error) {
      const status =
        typeof error === "object" &&
        error !== null &&
        "status" in error &&
        typeof (error as { status: unknown }).status === "number"
          ? (error as { status: number }).status
          : null;
      if (status === 404) {
        return { kind: "not_found" };
      }
      return { kind: "unavailable" };
    }
  }
}
