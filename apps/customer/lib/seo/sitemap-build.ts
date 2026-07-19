/**
 * Sitemap chunk builders + XML serializers for the customer public sitemap.
 *
 * Next.js `generateSitemaps()` emits `/sitemap/{id}.xml` chunks but does not
 * reliably emit a root `/sitemap.xml` index (vercel/next.js#77304). Route
 * handlers under `app/sitemap.xml` and `app/sitemap/[id]` call into this module
 * so robots can keep advertising `/sitemap.xml`.
 */

import { buildAbsoluteUrl, buildLocaleCanonical, getSiteUrl } from "@vergeo/ui/src/seo/json-ld";

import { coerceSitemapId, sitemapLocales, SITEMAP_STATIC_SEGMENTS } from "./sitemap-eligibility";
import {
  fetchCategorySitemapSlugs,
  fetchProductSitemapSlugs,
  fetchServiceSitemapSlugs,
  fetchVendorSitemapSlugs,
} from "./sitemap-sources";

import { fetchEventSitemapSlugs } from "./sitemap-events";

import type { MetadataRoute } from "next";

export const SITEMAP_CHUNK_SIZE = 5000;

export type SitemapUrlEntry = MetadataRoute.Sitemap[number];

type SitemapManifest = {
  productChunks: number;
  chunkIds: number[];
};

let manifestPromise: Promise<SitemapManifest> | null = null;
let productSlugsPromise: Promise<string[]> | null = null;

/** Escape text for XML element / attribute content. */
export function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

/** Strip an optional `.xml` suffix from a dynamic route segment (`0.xml` → `0`). */
export function parseSitemapChunkSegment(raw: string): number | null {
  const trimmed = raw.trim();
  const withoutExt = trimmed.toLowerCase().endsWith(".xml")
    ? trimmed.slice(0, -".xml".length)
    : trimmed;
  return coerceSitemapId(withoutExt);
}

function sitemapEntry(locale: string, ...segments: string[]): SitemapUrlEntry {
  const path = buildLocaleCanonical(locale, ...segments);
  return {
    url: buildAbsoluteUrl(path),
    lastModified: new Date(),
    changeFrequency: segments.length === 0 ? "daily" : "weekly",
    priority: segments.length === 0 ? 1 : segments[0] === "p" ? 0.8 : 0.6,
  };
}

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
      const productChunks = Math.max(1, Math.ceil(productSlugs.length / SITEMAP_CHUNK_SIZE));
      const chunkIds: number[] = [0];
      for (let chunk = 0; chunk < productChunks; chunk += 1) {
        chunkIds.push(chunk + 1);
      }
      // After products: vendors, events, categories, services
      chunkIds.push(productChunks + 1);
      chunkIds.push(productChunks + 2);
      chunkIds.push(productChunks + 3);
      chunkIds.push(productChunks + 4);
      return { productChunks, chunkIds };
    })();
  }
  return manifestPromise;
}

/** Numeric chunk ids that should be listed in the sitemap index. */
export async function listSitemapChunkIds(): Promise<number[]> {
  const { chunkIds } = await getSitemapManifest();
  return chunkIds;
}

/** Absolute `/sitemap/{id}.xml` URLs for the sitemap index. */
export async function listSitemapChunkUrls(siteUrl: string = getSiteUrl()): Promise<string[]> {
  const base = siteUrl.replace(/\/$/, "");
  const ids = await listSitemapChunkIds();
  return ids.map((id) => `${base}/sitemap/${id}.xml`);
}

/**
 * Build one chunk's urlset entries. Returns `null` when the id is outside the
 * current manifest (caller should 404).
 */
export async function buildSitemapChunk(id: number): Promise<SitemapUrlEntry[] | null> {
  const { productChunks, chunkIds } = await getSitemapManifest();
  if (!chunkIds.includes(id)) {
    return null;
  }

  const vendorChunkId = productChunks + 1;
  const eventChunkId = productChunks + 2;
  const categoryChunkId = productChunks + 3;
  const serviceChunkId = productChunks + 4;

  if (id === 0) {
    const categorySlugs = await fetchCategorySitemapSlugs();
    const hasPublicCategories = categorySlugs.some((slug) => slug !== "all");
    const entries: SitemapUrlEntry[] = [];
    // Only SEO-published locales (not routable-but-unreviewed bem/nya).
    for (const locale of sitemapLocales()) {
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
    const start = chunkIndex * SITEMAP_CHUNK_SIZE;
    const chunk = productSlugs.slice(start, start + SITEMAP_CHUNK_SIZE);
    const entries: SitemapUrlEntry[] = [];
    for (const locale of sitemapLocales()) {
      for (const slug of chunk) {
        entries.push(sitemapEntry(locale, "p", slug));
      }
    }
    return entries;
  }

  if (id === vendorChunkId) {
    const vendorSlugs = await fetchVendorSitemapSlugs();
    const entries: SitemapUrlEntry[] = [];
    for (const locale of sitemapLocales()) {
      for (const slug of vendorSlugs) {
        entries.push(sitemapEntry(locale, "v", slug));
      }
    }
    return entries;
  }

  if (id === eventChunkId) {
    const eventSlugs = await fetchEventSitemapSlugs();
    const entries: SitemapUrlEntry[] = [];
    for (const locale of sitemapLocales()) {
      for (const slug of eventSlugs) {
        entries.push(sitemapEntry(locale, "e", slug));
      }
    }
    return entries;
  }

  if (id === categoryChunkId) {
    const categorySlugs = await fetchCategorySitemapSlugs();
    const entries: SitemapUrlEntry[] = [];
    for (const locale of sitemapLocales()) {
      for (const category of categorySlugs) {
        entries.push(sitemapEntry(locale, "c", category));
      }
    }
    return entries;
  }

  if (id === serviceChunkId) {
    const serviceSlugs = await fetchServiceSitemapSlugs();
    const entries: SitemapUrlEntry[] = [];
    for (const locale of sitemapLocales()) {
      for (const slug of serviceSlugs) {
        entries.push(sitemapEntry(locale, "s", slug));
      }
    }
    return entries;
  }

  return null;
}

function formatLastMod(value: SitemapUrlEntry["lastModified"]): string | null {
  if (!value) {
    return null;
  }
  if (value instanceof Date) {
    return value.toISOString();
  }
  return String(value);
}

/** Serialize urlset XML for a chunk (same shape Next metadata routes emit). */
export function toUrlsetXml(entries: SitemapUrlEntry[]): string {
  const body = entries
    .map((entry) => {
      const lines = [`<loc>${escapeXml(entry.url)}</loc>`];
      const lastmod = formatLastMod(entry.lastModified);
      if (lastmod) {
        lines.push(`<lastmod>${escapeXml(lastmod)}</lastmod>`);
      }
      if (entry.changeFrequency) {
        lines.push(`<changefreq>${escapeXml(entry.changeFrequency)}</changefreq>`);
      }
      if (typeof entry.priority === "number") {
        lines.push(`<priority>${entry.priority}</priority>`);
      }
      return `<url>\n${lines.join("\n")}\n</url>`;
    })
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${body}\n</urlset>\n`;
}

/** Serialize a sitemap index listing chunk locs. */
export function toSitemapIndexXml(chunkUrls: string[]): string {
  const body = chunkUrls
    .map((url) => `<sitemap>\n<loc>${escapeXml(url)}</loc>\n</sitemap>`)
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${body}\n</sitemapindex>\n`;
}

export const SITEMAP_XML_HEADERS = {
  "Content-Type": "application/xml; charset=utf-8",
  "Cache-Control": "public, max-age=0, must-revalidate",
} as const;

/** True when a sitemap URL path is a public, indexable customer discovery URL. */
export function isCanonicalPublicSitemapUrl(url: string, siteUrl: string = getSiteUrl()): boolean {
  const base = siteUrl.replace(/\/$/, "");
  if (!url.startsWith(`${base}/`)) {
    return false;
  }
  let path: string;
  try {
    path = new URL(url).pathname;
  } catch {
    return false;
  }
  if (path.includes("?") || path.includes("#")) {
    return false;
  }
  const parts = path.split("/").filter(Boolean);
  // /{locale} or /{locale}/{segment...}
  const locale = parts[0];
  if (!locale || !sitemapLocales().includes(locale)) {
    return false;
  }
  const rest = parts.slice(1);
  if (rest.length === 0) {
    return true;
  }
  const head = rest[0];
  const tail = rest.slice(1);
  if (!head) {
    return false;
  }
  if (head === "p" || head === "v" || head === "e" || head === "s") {
    return tail.length === 1 && Boolean(tail[0]);
  }
  if (head === "c") {
    return tail.length >= 1 && tail.every(Boolean);
  }
  return (SITEMAP_STATIC_SEGMENTS as readonly string[]).includes(head) && tail.length === 0;
}
