/**
 * Authenticated engagement sync helpers (wishlist + recently viewed).
 * Failures are non-blocking — local storage remains the offline source of truth.
 */

import { getApiBaseUrl } from "./api-base-url";
import { listWishlistEntries, replaceWishlistLocal, type WishlistEntry } from "./wishlist-local";

async function getAccessToken(): Promise<string | null> {
  try {
    const { createBrowserClient } = await import("@vergeo/auth/browser-client");
    const supabase = createBrowserClient();
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}

async function apiRequest<T>(
  path: string,
  init: RequestInit & { token: string },
): Promise<T | null> {
  const { token, ...rest } = init;
  try {
    const response = await fetch(`${getApiBaseUrl().replace(/\/$/, "")}${path}`, {
      ...rest,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(rest.headers ?? {}),
      },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

type ServerWishlistItem = {
  product_id: string;
  slug: string;
  name: string;
  created_at: string;
};

type ServerWishlistResponse = {
  items: ServerWishlistItem[];
};

/**
 * Merge local wishlist into server on login, then hydrate local from server.
 */
export async function syncWishlistWithServer(): Promise<void> {
  const token = await getAccessToken();
  if (!token) {
    return;
  }

  const local = listWishlistEntries();
  const server = await apiRequest<ServerWishlistResponse>("/account/wishlist", {
    method: "GET",
    token,
  });
  if (!server) {
    return;
  }

  const byProduct = new Map<string, WishlistEntry>();
  for (const item of server.items) {
    if (!item.product_id || !item.slug) {
      continue;
    }
    byProduct.set(item.product_id, {
      productId: item.product_id,
      slug: item.slug,
      savedAt: item.created_at || new Date().toISOString(),
    });
  }
  for (const entry of local) {
    if (entry.productId) {
      if (!byProduct.has(entry.productId)) {
        byProduct.set(entry.productId, entry);
      }
    }
  }

  const productIds = [...byProduct.keys()];
  const put = await apiRequest<ServerWishlistResponse>("/account/wishlist", {
    method: "PUT",
    token,
    body: JSON.stringify({ product_ids: productIds }),
  });
  const source = put?.items ?? server.items;
  replaceWishlistLocal(
    source
      .filter((item) => item.slug)
      .map((item) => ({
        productId: item.product_id,
        slug: item.slug,
        savedAt: item.created_at || new Date().toISOString(),
      })),
  );
}

export async function pushWishlistProductIds(productIds: string[]): Promise<void> {
  const token = await getAccessToken();
  if (!token) {
    return;
  }
  await apiRequest<ServerWishlistResponse>("/account/wishlist", {
    method: "PUT",
    token,
    body: JSON.stringify({ product_ids: productIds }),
  });
}

export async function recordRecentlyViewedOnServer(productId: string): Promise<void> {
  const token = await getAccessToken();
  if (!token || !productId) {
    return;
  }
  await apiRequest("/account/recently-viewed", {
    method: "POST",
    token,
    body: JSON.stringify({ product_id: productId }),
  });
}
