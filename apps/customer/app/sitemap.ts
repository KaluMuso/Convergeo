import { LOCALES } from "@vergeo/i18n";
import { buildAbsoluteUrl, buildLocaleCanonical, getSiteUrl } from "@vergeo/ui/src/seo/json-ld";

import { SITEMAP_STATIC_SEGMENTS } from "../lib/seo/sitemap-eligibility";
import {
  fetchCategorySitemapSlugs,
  fetchProductSitemapSlugs,
  fetchServiceSitemapSlugs,
  fetchVendorSitemapSlugs,
} from "../lib/seo/sitemap-sources";

import { fetchEventSitemapSlugs } from "./sitemap-events";

import type { MetadataRoute } from "next";

const CHUNK_SIZE = 5000;

// "supplies" is intentionally omitted: the wholesale Supplies page is a B2B-gated
// route served with robots noindex,nofollow, so it must not be advertised in the
// sitemap. Search/compare/cart/checkout/account are also excluded (see eligibility).

function sitemapEntry(locale: string, ...segments: string[]): MetadataRoute.Sitemap[number] {
  const path = buildLocaleCanonical(locale, ...segments);
  return {
    url: buildAbsoluteUrl(path),
    lastModified: new Date(),
    changeFrequency: segments.length === 0 ? "daily" : "weekly",
    priority: segments.length === 0 ? 1 : segments[0] === "p" ? 0.8 : 0.6,
  };
}

type SitemapManifest = {
  productChunks: number;
};

let manifestPromise: Promise<SitemapManifest> | null = null;
let productSlugsPromise: Promise<string[]> | null = null;

async function getProductSlugs(): Promise<string[]> {
  if (!productSlugsPromise) {
    productSlugsPromise = fetchProductSitemapSlugs();
  }
  return productSlugsPromise;
}

async function getSitemapManifest(): Promise<SitemapManifest> {
  if (!manifestPromise) {
    manifestPromise = (async () => {
      const productSlugs = await getProductSlugs();
      const productChunks = Math.max(1, Math.ceil(productSlugs.length / CHUNK_SIZE));
      return { productChunks };
    })();
  }
  return manifestPromise;
}

export async function generateSitemaps() {
  const { productChunks } = await getSitemapManifest();
  const ids: Array<{ id: number }> = [{ id: 0 }];
  for (let chunk = 0; chunk < productChunks; chunk += 1) {
    ids.push({ id: chunk + 1 });
  }
  // After products: vendors, events, categories, services
  ids.push({ id: productChunks + 1 });
  ids.push({ id: productChunks + 2 });
  ids.push({ id: productChunks + 3 });
  ids.push({ id: productChunks + 4 });
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
  const serviceChunkId = productChunks + 4;

  if (id === 0) {
    const categorySlugs = await fetchCategorySitemapSlugs();
    const hasPublicCategories = categorySlugs.some((slug) => slug !== "all");
    const entries: MetadataRoute.Sitemap = [];
    for (const locale of LOCALES) {
      for (const segment of SITEMAP_STATIC_SEGMENTS) {
        // Omit the empty categories hub from the sitemap (page is also noindex).
        if (segment === "categories" && !hasPublicCategories) {
          continue;
        }
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
    const vendorSlugs = await fetchVendorSitemapSlugs();
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
    const categorySlugs = await fetchCategorySitemapSlugs();
    const entries: MetadataRoute.Sitemap = [];
    for (const locale of LOCALES) {
      for (const category of categorySlugs) {
        entries.push(sitemapEntry(locale, "c", category));
      }
    }
    return entries;
  }

  if (id === serviceChunkId) {
    const serviceSlugs = await fetchServiceSitemapSlugs();
    const entries: MetadataRoute.Sitemap = [];
    for (const locale of LOCALES) {
      for (const slug of serviceSlugs) {
        entries.push(sitemapEntry(locale, "s", slug));
      }
    }
    return entries;
  }

  return [];
}

export { getSiteUrl };
