import { LOCALES } from "@vergeo/i18n";
import { buildAbsoluteUrl, buildLocaleCanonical, getSiteUrl } from "@vergeo/ui/src/seo/json-ld";

import { fetchEventSitemapSlugs } from "./sitemap-events";

import type { MetadataRoute } from "next";

const CHUNK_SIZE = 5000;

// "supplies" is intentionally omitted: the wholesale Supplies page is a B2B-gated
// route served with robots noindex,nofollow, so it must not be advertised in the
// sitemap.
const STATIC_SHOP_SEGMENTS = ["", "search", "directory", "events"] as const;

const CATEGORY_SLUGS = [
  "all",
  "electronics",
  "fashion-beauty",
  "home-living",
  "groceries",
] as const;

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

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function sitemapEntry(locale: string, ...segments: string[]): MetadataRoute.Sitemap[number] {
  const path = buildLocaleCanonical(locale, ...segments);
  return {
    url: buildAbsoluteUrl(path),
    lastModified: new Date(),
    changeFrequency: segments.length === 0 ? "daily" : "weekly",
    priority: segments.length === 0 ? 1 : segments[0] === "p" ? 0.8 : 0.6,
  };
}

async function fetchProductSlugs(): Promise<string[]> {
  const slugs = new Set<string>();
  let cursor: string | null = null;

  try {
    for (let page = 0; page < 200; page += 1) {
      const params = new URLSearchParams({ limit: "48" });
      if (cursor) {
        params.set("cursor", cursor);
      }

      const response = await fetch(`${getApiBaseUrl()}/catalog/listings?${params.toString()}`, {
        next: { revalidate: 3600 },
      });
      if (!response.ok) {
        break;
      }

      const payload = (await response.json()) as CatalogListResponse;
      for (const item of payload.items) {
        if (item.product_slug) {
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

async function fetchVendorSlugs(): Promise<string[]> {
  const slugs: string[] = [];
  let page = 1;

  try {
    while (page <= 200) {
      const response = await fetch(`${getApiBaseUrl()}/directory?page=${page}&page_size=48`, {
        next: { revalidate: 3600 },
      });
      if (!response.ok) {
        break;
      }

      const payload = (await response.json()) as DirectoryListResponse;
      for (const item of payload.items) {
        slugs.push(item.slug);
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

type SitemapManifest = {
  productChunks: number;
};

let manifestPromise: Promise<SitemapManifest> | null = null;

async function getSitemapManifest(): Promise<SitemapManifest> {
  if (!manifestPromise) {
    manifestPromise = (async () => {
      const productSlugs = await fetchProductSlugs();
      const productChunks = Math.max(1, Math.ceil(productSlugs.length / CHUNK_SIZE));
      return { productChunks };
    })();
  }
  return manifestPromise;
}

async function getProductSlugs(): Promise<string[]> {
  return fetchProductSlugs();
}

export async function generateSitemaps() {
  const { productChunks } = await getSitemapManifest();
  const ids: Array<{ id: number }> = [{ id: 0 }];
  for (let chunk = 0; chunk < productChunks; chunk += 1) {
    ids.push({ id: chunk + 1 });
  }
  ids.push({ id: productChunks + 1 });
  ids.push({ id: productChunks + 2 });
  ids.push({ id: productChunks + 3 });
  return ids;
}

export default async function sitemap(props: {
  id: Promise<number>;
}): Promise<MetadataRoute.Sitemap> {
  const id = await props.id;
  const { productChunks } = await getSitemapManifest();
  const vendorChunkId = productChunks + 1;
  const eventChunkId = productChunks + 2;
  const categoryChunkId = productChunks + 3;

  if (id === 0) {
    const entries: MetadataRoute.Sitemap = [];
    for (const locale of LOCALES) {
      for (const segment of STATIC_SHOP_SEGMENTS) {
        entries.push(segment ? sitemapEntry(locale, segment) : sitemapEntry(locale));
      }
    }
    return entries;
  }

  if (id >= 1 && id <= productChunks) {
    const productSlugs = await getProductSlugs();
    const chunkIndex = id - 1;
    const start = chunkIndex * CHUNK_SIZE;
    const chunk = productSlugs.slice(start, start + CHUNK_SIZE);
    const entries: MetadataRoute.Sitemap = [];
    for (const locale of LOCALES) {
      for (const slug of chunk) {
        entries.push(sitemapEntry(locale, "p", slug));
      }
    }
    return entries;
  }

  if (id === vendorChunkId) {
    const vendorSlugs = await fetchVendorSlugs();
    const entries: MetadataRoute.Sitemap = [];
    for (const locale of LOCALES) {
      for (const slug of vendorSlugs) {
        entries.push(sitemapEntry(locale, "v", slug));
      }
    }
    return entries;
  }

  if (id === eventChunkId) {
    const eventSlugs = await fetchEventSitemapSlugs();
    const entries: MetadataRoute.Sitemap = [];
    for (const locale of LOCALES) {
      for (const slug of eventSlugs) {
        entries.push(sitemapEntry(locale, "e", slug));
      }
    }
    return entries;
  }

  if (id === categoryChunkId) {
    const entries: MetadataRoute.Sitemap = [];
    for (const locale of LOCALES) {
      for (const category of CATEGORY_SLUGS) {
        entries.push(sitemapEntry(locale, "c", category));
      }
    }
    return entries;
  }

  return [];
}

export { getSiteUrl };
