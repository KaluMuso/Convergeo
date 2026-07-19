import { SEO_INDEXABLE_LOCALES } from "@vergeo/i18n";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/seo/sitemap-sources", () => ({
  fetchCategorySitemapSlugs: vi.fn(async () => ["all", "electronics"]),
  fetchProductSitemapSlugs: vi.fn(async () => ["itel-a70"]),
  fetchServiceSitemapSlugs: vi.fn(async () => []),
  fetchVendorSitemapSlugs: vi.fn(async () => []),
}));

vi.mock("../lib/seo/sitemap-events", () => ({
  fetchEventSitemapSlugs: vi.fn(async () => []),
}));

describe("sitemap root + chunk route handlers", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://vergeo5.com";
    vi.resetModules();
  });

  it("GET /sitemap.xml returns 200 sitemap index XML listing chunks", async () => {
    const { GET } = await import("./sitemap.xml/route");
    const response = await GET();
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toMatch(/application\/xml/);

    const body = await response.text();
    expect(body).toContain("<sitemapindex");
    expect(body).toContain("<loc>https://vergeo5.com/sitemap/0.xml</loc>");
    expect(body).toContain("<loc>https://vergeo5.com/sitemap/1.xml</loc>");
    expect(body).not.toContain("<urlset");
  });

  it("GET /sitemap/0.xml returns 200 urlset with indexable locales only", async () => {
    const { GET } = await import("./sitemap/[id]/route");
    const response = await GET(new Request("https://vergeo5.com/sitemap/0.xml"), {
      params: Promise.resolve({ id: "0.xml" }),
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toMatch(/application\/xml/);

    const body = await response.text();
    expect(body).toContain("<urlset");
    for (const locale of SEO_INDEXABLE_LOCALES) {
      expect(body).toContain(`https://vergeo5.com/${locale}</loc>`);
    }
    expect(body).not.toContain("/bem");
    expect(body).not.toContain("/nya");
    expect(body).not.toContain("/cart");
    expect(body).not.toContain("/checkout");
    expect(body).not.toContain("/search");
  });

  it("GET unknown chunk returns 404", async () => {
    const { GET } = await import("./sitemap/[id]/route");
    const response = await GET(new Request("https://vergeo5.com/sitemap/99.xml"), {
      params: Promise.resolve({ id: "99.xml" }),
    });
    expect(response.status).toBe(404);
  });
});
