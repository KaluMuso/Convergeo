import { SEO_INDEXABLE_LOCALES } from "@vergeo/i18n";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  escapeXml,
  isCanonicalPublicSitemapUrl,
  parseSitemapChunkSegment,
  toSitemapIndexXml,
  toUrlsetXml,
} from "./sitemap-build";

vi.mock("./sitemap-sources", () => ({
  fetchCategorySitemapSlugs: vi.fn(async () => ["all", "electronics"]),
  fetchProductSitemapSlugs: vi.fn(async () => ["itel-a70", "solar-lantern"]),
  fetchServiceSitemapSlugs: vi.fn(async () => ["plumbing-kitwe"]),
  fetchVendorSitemapSlugs: vi.fn(async () => ["tech-hub-lusaka"]),
}));

vi.mock("./sitemap-events", () => ({
  fetchEventSitemapSlugs: vi.fn(async () => ["lusaka-night-market"]),
}));

describe("parseSitemapChunkSegment", () => {
  it("accepts bare ids and .xml suffixes used by public chunk URLs", () => {
    expect(parseSitemapChunkSegment("0")).toBe(0);
    expect(parseSitemapChunkSegment("0.xml")).toBe(0);
    expect(parseSitemapChunkSegment("4.XML")).toBe(4);
    expect(parseSitemapChunkSegment("nope")).toBeNull();
  });
});

describe("sitemap XML serializers", () => {
  it("emits a sitemap index with application/xml-shaped locs", () => {
    const xml = toSitemapIndexXml([
      "https://vergeo5.com/sitemap/0.xml",
      "https://vergeo5.com/sitemap/1.xml",
    ]);
    expect(xml).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(xml).toContain("<sitemapindex");
    expect(xml).toContain("<loc>https://vergeo5.com/sitemap/0.xml</loc>");
    expect(xml).toContain("<loc>https://vergeo5.com/sitemap/1.xml</loc>");
    expect(xml).not.toContain("<urlset");
  });

  it("emits urlset entries and escapes XML-special characters", () => {
    const xml = toUrlsetXml([
      {
        url: "https://vergeo5.com/en/p/a&b",
        lastModified: new Date("2026-07-19T12:00:00.000Z"),
        changeFrequency: "weekly",
        priority: 0.8,
      },
    ]);
    expect(xml).toContain("<urlset");
    expect(xml).toContain("<loc>https://vergeo5.com/en/p/a&amp;b</loc>");
    expect(xml).toContain("<changefreq>weekly</changefreq>");
    expect(xml).toContain("<priority>0.8</priority>");
    expect(escapeXml(`<"&'>`)).toBe("&lt;&quot;&amp;&apos;&gt;");
  });
});

describe("chunked sitemap manifest", () => {
  const previousSiteUrl = process.env.NEXT_PUBLIC_SITE_URL;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://vergeo5.com";
    vi.resetModules();
  });

  afterEach(() => {
    if (previousSiteUrl === undefined) {
      delete process.env.NEXT_PUBLIC_SITE_URL;
    } else {
      process.env.NEXT_PUBLIC_SITE_URL = previousSiteUrl;
    }
  });

  it("lists static + product + entity chunks and resolves public chunk URLs", async () => {
    // Fresh module so manifest cache is empty under mocks.
    const mod = await import("./sitemap-build");
    const ids = await mod.listSitemapChunkIds();
    // 0 static, 1 product chunk (2 slugs), then vendor/event/category/service → 0..5
    expect(ids).toEqual([0, 1, 2, 3, 4, 5]);

    const urls = await mod.listSitemapChunkUrls("https://vergeo5.com");
    expect(urls).toEqual([
      "https://vergeo5.com/sitemap/0.xml",
      "https://vergeo5.com/sitemap/1.xml",
      "https://vergeo5.com/sitemap/2.xml",
      "https://vergeo5.com/sitemap/3.xml",
      "https://vergeo5.com/sitemap/4.xml",
      "https://vergeo5.com/sitemap/5.xml",
    ]);

    const indexXml = mod.toSitemapIndexXml(urls);
    expect(indexXml).toContain("https://vergeo5.com/sitemap/0.xml");
    expect(indexXml).toContain("https://vergeo5.com/sitemap/5.xml");
  });

  it("builds chunk 0 with SEO_INDEXABLE_LOCALES only (excludes bem/nya)", async () => {
    const mod = await import("./sitemap-build");
    const entries = await mod.buildSitemapChunk(0);
    expect(entries).not.toBeNull();
    const locs = (entries ?? []).map((entry) => entry.url);

    for (const locale of SEO_INDEXABLE_LOCALES) {
      expect(locs.some((url) => url === `https://vergeo5.com/${locale}`)).toBe(true);
    }
    expect(locs.some((url) => url.includes("/bem"))).toBe(false);
    expect(locs.some((url) => url.includes("/nya"))).toBe(false);

    // Policy: no search/cart/checkout/private/demo shells.
    for (const forbidden of [
      "/search",
      "/cart",
      "/checkout",
      "/account",
      "/compare",
      "/supplies",
      "/beta",
      "/ask",
      "/ui",
    ]) {
      expect(locs.some((url) => url.includes(forbidden))).toBe(false);
    }

    for (const url of locs) {
      expect(mod.isCanonicalPublicSitemapUrl(url, "https://vergeo5.com")).toBe(true);
    }
  });

  it("builds product chunk with canonical /p/{slug} URLs only", async () => {
    const mod = await import("./sitemap-build");
    const entries = await mod.buildSitemapChunk(1);
    expect(entries).not.toBeNull();
    const locs = (entries ?? []).map((entry) => entry.url);
    expect(locs).toEqual(
      expect.arrayContaining([
        "https://vergeo5.com/en/p/itel-a70",
        "https://vergeo5.com/fr/p/itel-a70",
        "https://vergeo5.com/zh/p/solar-lantern",
      ]),
    );
    expect(locs.every((url) => /\/(en|fr|zh)\/p\//.test(url))).toBe(true);
    expect(locs.some((url) => url.includes("/bem/") || url.includes("/nya/"))).toBe(false);
  });

  it("returns null for unknown chunk ids", async () => {
    const mod = await import("./sitemap-build");
    await expect(mod.buildSitemapChunk(99)).resolves.toBeNull();
  });
});

describe("isCanonicalPublicSitemapUrl", () => {
  it("accepts locale hubs and entity paths; rejects private/non-canonical", () => {
    expect(isCanonicalPublicSitemapUrl("https://vergeo5.com/en")).toBe(true);
    expect(isCanonicalPublicSitemapUrl("https://vergeo5.com/en/p/itel-a70")).toBe(true);
    expect(isCanonicalPublicSitemapUrl("https://vergeo5.com/fr/c/electronics")).toBe(true);
    expect(isCanonicalPublicSitemapUrl("https://vergeo5.com/bem")).toBe(false);
    expect(isCanonicalPublicSitemapUrl("https://vergeo5.com/en/cart")).toBe(false);
    expect(isCanonicalPublicSitemapUrl("https://vergeo5.com/en/search?q=phone")).toBe(false);
    expect(isCanonicalPublicSitemapUrl("https://evil.example/en")).toBe(false);
  });
});
