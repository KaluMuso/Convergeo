import { describe, expect, it, vi } from "vitest";

// Regression for the live production bug: a request to a locale-less path
// (e.g. `/cart`, `/sw.js`) that slipped past the middleware matcher used to
// bind the raw path segment as `params.locale` (e.g. "cart"), and this page
// would start building interpolated messages with it — `IntlMessageFormat`
// throws for anything that isn't a valid BCP-47 tag, surfacing in production
// as `INVALID_MESSAGE` (5000+ occurrences, see apps/customer/middleware.ts).
// The page must now bail out via `notFound()` before any of that work runs.

const { loadHomeMerchDataMock } = vi.hoisted(() => ({ loadHomeMerchDataMock: vi.fn() }));

vi.mock("@vergeo/i18n", () => ({
  DEFAULT_LOCALE: "en",
  LOCALES: ["en", "bem", "nya", "fr", "zh"],
  loadNamespace: vi.fn().mockResolvedValue({}),
}));

vi.mock("@vergeo/ui/src/seo/json-ld", () => ({
  buildAbsoluteUrl: vi.fn(),
  buildCanonicalAlternates: vi.fn(),
  buildLocaleCanonical: vi.fn(),
  buildOrganizationJsonLd: vi.fn(),
  buildSearchActionUrlTemplate: vi.fn(),
  buildWebSiteJsonLd: vi.fn(),
  JsonLdScript: () => null,
}));

vi.mock("next-intl", () => ({
  createTranslator: () => (key: string) => key,
}));

vi.mock("next-intl/server", () => ({
  getMessages: vi.fn().mockResolvedValue({ common: {} }),
  setRequestLocale: vi.fn(),
}));

vi.mock("./_components/banner-row", () => ({ BannerRow: () => null }));
vi.mock("./_components/category-grid", () => ({ CategoryGrid: () => null }));
vi.mock("./_components/directory/vendor-ladder-labels", () => ({
  buildVendorLadderLabels: vi.fn(),
}));
vi.mock("./_components/events-row", () => ({ EventsRow: () => null }));
vi.mock("./_components/featured-collections", () => ({ FeaturedCollections: () => null }));
vi.mock("./_components/flash-deal", () => ({ FlashDeal: () => null }));
vi.mock("./_components/hero", () => ({ HomeHero: () => null }));
vi.mock("./_components/home-default", () => ({
  HomeHeroBand: () => null,
  HomeProductRail: () => null,
  HomeSellCta: () => null,
  HomeServicesRail: () => null,
  HomeVendorsRail: () => null,
  loadHomeDefaultData: vi.fn(),
  pickHeroVisualPublicId: vi.fn(),
}));
vi.mock("./_components/home-layout", () => ({ planHomeLayout: vi.fn() }));
vi.mock("./_components/home-recently-viewed-rail", () => ({
  HomeRecentlyViewedRail: () => null,
}));
vi.mock("./_components/home-trust-strip", () => ({ HomeTrustStrip: () => null }));
vi.mock("./_components/merch-data", () => ({
  loadHomeMerchData: loadHomeMerchDataMock,
  pickSlot: vi.fn(),
}));
vi.mock("./_components/merch-preview-banner", () => ({ MerchPreviewBanner: () => null }));

import ShopHomePage, { generateMetadata } from "./page";

describe("ShopHomePage invalid locale guard", () => {
  it("calls notFound() and never loads merch data for a bogus locale segment", async () => {
    await expect(
      ShopHomePage({
        params: Promise.resolve({ locale: "cart" }),
        searchParams: Promise.resolve({}),
      }),
    ).rejects.toThrow(/NEXT_HTTP_ERROR_FALLBACK;404|NEXT_NOT_FOUND/);

    expect(loadHomeMerchDataMock).not.toHaveBeenCalled();
  });

  it("does the same in generateMetadata for a bogus locale segment", async () => {
    await expect(
      generateMetadata({
        params: Promise.resolve({ locale: "sw.js" }),
        searchParams: Promise.resolve({}),
      }),
    ).rejects.toThrow(/NEXT_HTTP_ERROR_FALLBACK;404|NEXT_NOT_FOUND/);
  });
});
