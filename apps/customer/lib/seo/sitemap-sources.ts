import { createBrowserClient } from "@vergeo/auth/browser-client";

import {
  categoryPathsEligibleForSitemap,
  type CategorySitemapRow,
} from "./category-listing-eligibility";
import { isSitemapEligibleCategorySlug, isSitemapEligibleEntitySlug } from "./sitemap-eligibility";

import { getApiBaseUrl } from "../api-base-url";

type CatalogListResponse = {
  items: Array<{ product_slug: string | null }>;
  next_cursor: string | null;
};

type DirectoryListResponse = {
  items: Array<{ slug: string }>;
  total: number;
  page: number;
  page_size: number;
};

type ServicesListResponse = {
  items: Array<{ slug: string }>;
};

type CategoryRow = {
  path: string;
  prohibited: boolean | null;
  show_in_customer?: boolean | null;
};

type ListingProjectionRow = {
  category_path: string | null;
  updated_at: string;
};

/**
 * Public category PLP paths for the sitemap (`all` plus categories that have
 * live listings on the category or any descendant).
 */
export async function fetchCategorySitemapEntries(): Promise<CategorySitemapRow[]> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();

  const allEntry: CategorySitemapRow = { path: "all" };
  if (!url || !key) {
    return [allEntry];
  }

  try {
    // Anon public read (RLS categories_public_select + search_documents_public_select).
    const client = createBrowserClient();
    const [categoriesResult, listingsResult] = await Promise.all([
      client.from("categories").select("path, prohibited, show_in_customer"),
      client
        .from("search_documents")
        .select("category_path, updated_at")
        .eq("entity_kind", "product")
        .eq("is_public", true)
        .not("category_path", "is", null),
    ]);

    if (categoriesResult.error || !Array.isArray(categoriesResult.data)) {
      return [allEntry];
    }

    const categories = (categoriesResult.data as CategoryRow[])
      .filter((row) => typeof row.path === "string" && row.path.trim().length > 0)
      // Blocked/draft rows are hidden by RLS; vendor-only nodes have no customer page.
      .filter((row) => row.show_in_customer !== false)
      .map((row) => ({
        path: row.path.trim(),
        prohibited: row.prohibited === true,
      }));

    const listingStamps = (listingsResult.data as ListingProjectionRow[] | null)
      ?.filter(
        (row): row is { category_path: string; updated_at: string } =>
          typeof row.category_path === "string" &&
          row.category_path.trim().length > 0 &&
          typeof row.updated_at === "string",
      )
      .map((row) => ({
        category_path: row.category_path.trim(),
        updated_at: row.updated_at,
      }));

    const eligible = categoryPathsEligibleForSitemap(categories, listingStamps ?? []).filter(
      (row) => isSitemapEligibleCategorySlug(row.path),
    );

    return [allEntry, ...eligible];
  } catch {
    return [allEntry];
  }
}

/** Back-compat helper returning path strings only. */
export async function fetchCategorySitemapSlugs(): Promise<string[]> {
  const entries = await fetchCategorySitemapEntries();
  return entries.map((entry) => entry.path);
}

export async function fetchProductSitemapSlugs(): Promise<string[]> {
  const slugs = new Set<string>();
  let cursor: string | null = null;
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    return [];
  }

  try {
    for (let page = 0; page < 200; page += 1) {
      const params = new URLSearchParams({ limit: "48" });
      if (cursor) {
        params.set("cursor", cursor);
      }

      const response = await fetch(`${baseUrl}/catalog/listings?${params.toString()}`, {
        next: { revalidate: 3600 },
      });
      if (!response.ok) {
        break;
      }

      const payload = (await response.json()) as CatalogListResponse;
      for (const item of payload.items) {
        if (item.product_slug && isSitemapEligibleEntitySlug(item.product_slug)) {
          slugs.add(item.product_slug);
        }
      }

      cursor = payload.next_cursor;
      if (!cursor) {
        break;
      }
    }
  } catch {
    return [];
  }

  return [...slugs].sort();
}

export async function fetchVendorSitemapSlugs(): Promise<string[]> {
  const slugs: string[] = [];
  let page = 1;
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    return [];
  }

  try {
    while (page <= 200) {
      const response = await fetch(`${baseUrl}/directory?page=${page}&page_size=48`, {
        next: { revalidate: 3600 },
      });
      if (!response.ok) {
        break;
      }

      const payload = (await response.json()) as DirectoryListResponse;
      for (const item of payload.items) {
        if (isSitemapEligibleEntitySlug(item.slug)) {
          slugs.push(item.slug);
        }
      }

      const fetched = page * payload.page_size;
      if (fetched >= payload.total || payload.items.length === 0) {
        break;
      }
      page += 1;
    }
  } catch {
    return [];
  }

  return slugs;
}

/** Active public service detail slugs from GET /services. */
export async function fetchServiceSitemapSlugs(): Promise<string[]> {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    return [];
  }

  try {
    const response = await fetch(`${baseUrl}/services`, {
      next: { revalidate: 3600 },
    });
    if (!response.ok) {
      return [];
    }
    const payload = (await response.json()) as ServicesListResponse;
    return payload.items
      .map((item) => item.slug)
      .filter((slug) => isSitemapEligibleEntitySlug(slug))
      .sort();
  } catch {
    return [];
  }
}
