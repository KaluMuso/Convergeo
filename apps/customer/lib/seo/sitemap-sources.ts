import { createBrowserClient } from "@vergeo/auth/browser-client";

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
  slug: string;
  prohibited: boolean | null;
};

/**
 * Public category PLP slugs for the sitemap.
 * Includes `all` plus every non-prohibited category leaf/hub slug used by `/c/{slug}`.
 */
export async function fetchCategorySitemapSlugs(): Promise<string[]> {
  const slugs = new Set<string>(["all"]);
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();

  if (!url || !key) {
    return [...slugs];
  }

  try {
    // Anon public read (RLS categories_public_select). No cookie session needed.
    const client = createBrowserClient();
    const { data, error } = await client
      .from("categories")
      .select("slug, prohibited")
      .eq("prohibited", false);

    if (error || !Array.isArray(data)) {
      return [...slugs];
    }

    for (const row of data as CategoryRow[]) {
      if (row.prohibited) {
        continue;
      }
      if (typeof row.slug === "string" && isSitemapEligibleCategorySlug(row.slug)) {
        slugs.add(row.slug);
      }
    }
  } catch {
    return [...slugs];
  }

  return [...slugs].sort();
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
