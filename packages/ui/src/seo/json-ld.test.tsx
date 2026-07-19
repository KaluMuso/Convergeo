import { DEFAULT_LOCALE, SEO_INDEXABLE_LOCALES } from "@vergeo/i18n";
import { describe, expect, it } from "vitest";

import {
  buildBreadcrumbListJsonLd,
  buildCanonicalAlternates,
  buildEventJsonLd,
  buildLocalBusinessJsonLd,
  buildOrganizationJsonLd,
  buildProductJsonLd,
  buildLocaleCanonical,
  buildSearchActionUrlTemplate,
  buildWebSiteJsonLd,
  canBuildProductJsonLd,
  ngweeToZmwDecimal,
  stripCanonicalParams,
} from "./json-ld";

describe("ngweeToZmwDecimal", () => {
  it("converts 123456 ngwee to 1234.56 ZMW", () => {
    expect(ngweeToZmwDecimal(123456)).toBe("1234.56");
  });

  it("handles odd ngwee (single-digit minor units)", () => {
    expect(ngweeToZmwDecimal(100)).toBe("1.00");
    expect(ngweeToZmwDecimal(105)).toBe("1.05");
    expect(ngweeToZmwDecimal(1)).toBe("0.01");
  });

  it("handles zero", () => {
    expect(ngweeToZmwDecimal(0)).toBe("0.00");
  });

  it("rejects non-integer ngwee", () => {
    expect(() => ngweeToZmwDecimal(12.34)).toThrow(/integer/);
  });
});

describe("stripCanonicalParams", () => {
  it("strips query params from canonical paths", () => {
    expect(stripCanonicalParams("/en/c/electronics?sort=cheapest&min_price=1000")).toBe(
      "/en/c/electronics",
    );
  });

  it("strips hash fragments", () => {
    expect(stripCanonicalParams("/en/search?q=phone#results")).toBe("/en/search");
  });
});

describe("buildLocaleCanonical", () => {
  it("builds locale-prefixed paths without params", () => {
    expect(buildLocaleCanonical("en", "p", "itel-a70")).toBe("/en/p/itel-a70");
    expect(buildLocaleCanonical("bem", "supplies")).toBe("/bem/supplies");
  });
});

describe("buildCanonicalAlternates", () => {
  it("self-canonicalises unapproved locales but omits them from hreflang / x-default", () => {
    const alternates = buildCanonicalAlternates("bem", "p", "itel-a70");
    expect(alternates.canonical).toBe("/bem/p/itel-a70");
    expect(alternates.languages).toBeDefined();
    const languages = alternates.languages as Record<string, string>;
    for (const locale of SEO_INDEXABLE_LOCALES) {
      expect(languages[locale]).toBe(`https://vergeo5.com/${locale}/p/itel-a70`);
    }
    expect(languages.bem).toBeUndefined();
    expect(languages.nya).toBeUndefined();
    expect(languages["x-default"]).toBe(`https://vergeo5.com/${DEFAULT_LOCALE}/p/itel-a70`);
  });

  it("emits hreflang only for SEO-published locales by default", () => {
    const alternates = buildCanonicalAlternates("en", "p", "itel-a70");
    const languages = alternates.languages as Record<string, string>;
    expect(Object.keys(languages).sort()).toEqual([...SEO_INDEXABLE_LOCALES, "x-default"].sort());
    expect(languages.bem).toBeUndefined();
    expect(languages.nya).toBeUndefined();
  });

  it("omits locales that do not serve the page and still strips unapproved SEO locales", () => {
    const alternates = buildCanonicalAlternates("en", "p", "itel-a70", {
      availableLocales: ["en", "fr", "bem"],
    });
    const languages = alternates.languages as Record<string, string>;
    expect(Object.keys(languages).sort()).toEqual(["en", "fr", "x-default"].sort());
    expect(languages.bem).toBeUndefined();
    expect(languages["x-default"]).toBe("https://vergeo5.com/en/p/itel-a70");
  });
});

describe("buildProductJsonLd", () => {
  it("maps offers with exact ZMW decimal prices", () => {
    const input = {
      name: "Itel A70",
      slug: "itel-a70",
      locale: "en",
      brand: "Itel",
      imageUrls: ["https://res.cloudinary.com/demo/image/upload/itel.jpg"],
      offers: [
        {
          priceNgwee: 123456,
          inStock: true,
          sellerName: "Tech Hub Lusaka",
        },
        {
          priceNgwee: 125000,
          inStock: false,
          sellerName: "Mobile World",
        },
      ],
    };
    expect(canBuildProductJsonLd(input)).toBe(true);
    const jsonLd = buildProductJsonLd(input);

    expect(jsonLd["@type"]).toBe("Product");
    expect(jsonLd.name).toBe("Itel A70");
    expect(jsonLd.aggregateRating).toBeUndefined();
    const offers = jsonLd.offers as Array<Record<string, unknown>>;
    expect(offers).toHaveLength(2);
    expect(offers[0]?.price).toBe("1234.56");
    expect(offers[0]?.priceCurrency).toBe("ZMW");
    expect(offers[1]?.price).toBe("1250.00");
  });

  it("refuses Product JSON-LD without real image or seller offers", () => {
    expect(
      canBuildProductJsonLd({
        name: "Itel A70",
        slug: "itel-a70",
        locale: "en",
        offers: [],
      }),
    ).toBe(false);
    expect(
      canBuildProductJsonLd({
        name: "Itel A70",
        slug: "itel-a70",
        locale: "en",
        imageUrls: ["https://example.com/a.jpg"],
        offers: [{ priceNgwee: 100, inStock: true, sellerName: "" }],
      }),
    ).toBe(false);
  });
});

describe("buildOrganizationJsonLd / buildWebSiteJsonLd", () => {
  it("builds Organization without fabricating logo or socials", () => {
    const jsonLd = buildOrganizationJsonLd({ name: "Vergeo5" });
    expect(jsonLd).toEqual({
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "Vergeo5",
      url: "https://vergeo5.com",
    });
    expect(jsonLd.logo).toBeUndefined();
  });

  it("builds WebSite SearchAction from a real search urlTemplate", () => {
    const template = buildSearchActionUrlTemplate("en");
    expect(template).toBe("https://vergeo5.com/en/search?q={search_term_string}");
    const jsonLd = buildWebSiteJsonLd({
      name: "Vergeo5",
      searchUrlTemplate: template,
    });
    expect(jsonLd["@type"]).toBe("WebSite");
    const action = jsonLd.potentialAction as Record<string, unknown>;
    expect(action["@type"]).toBe("SearchAction");
    expect((action.target as Record<string, unknown>).urlTemplate).toBe(template);
  });
});

describe("buildLocalBusinessJsonLd", () => {
  it("matches LocalBusiness golden shape", () => {
    const jsonLd = buildLocalBusinessJsonLd({
      name: "Tech Hub Lusaka",
      slug: "tech-hub-lusaka",
      locale: "en",
      description: "Electronics retailer",
      landmark: "East Park Mall",
      lat: -15.4167,
      lng: 28.2833,
      aggregateRating: { ratingValue: 4.5, reviewCount: 12 },
    });

    expect(jsonLd).toMatchObject({
      "@context": "https://schema.org",
      "@type": "LocalBusiness",
      name: "Tech Hub Lusaka",
      url: "https://vergeo5.com/en/v/tech-hub-lusaka",
      geo: {
        "@type": "GeoCoordinates",
        latitude: -15.4167,
        longitude: 28.2833,
      },
      aggregateRating: {
        "@type": "AggregateRating",
        ratingValue: 4.5,
        reviewCount: 12,
      },
    });
  });
});

describe("buildEventJsonLd", () => {
  it("matches Event golden shape with ticket offers", () => {
    const jsonLd = buildEventJsonLd({
      name: "Zed Summer Festival",
      slug: "zed-summer-festival",
      locale: "en",
      venue: "Lusaka Showgrounds",
      instances: [{ startsAt: "2026-08-15T18:00:00+02:00" }],
      ticketTypes: [
        {
          name: "General Admission",
          priceNgwee: 15000,
          isFree: false,
          isSoldOut: false,
        },
      ],
      organiserName: "Zed Events",
      isFree: false,
    });

    expect(jsonLd).toMatchObject({
      "@type": "Event",
      name: "Zed Summer Festival",
      startDate: "2026-08-15T18:00:00+02:00",
      organizer: {
        "@type": "Organization",
        name: "Zed Events",
      },
    });

    const offers = jsonLd.offers as Record<string, unknown>;
    expect(offers.price).toBe("150.00");
    expect(offers.priceCurrency).toBe("ZMW");
  });
});

describe("buildBreadcrumbListJsonLd", () => {
  it("builds breadcrumb positions from category path", () => {
    const jsonLd = buildBreadcrumbListJsonLd("en", [
      { name: "Home", path: "" },
      { name: "Electronics", path: "c/electronics" },
    ]);

    const items = jsonLd.itemListElement as Array<Record<string, unknown>>;
    expect(items).toHaveLength(2);
    expect(items[0]).toMatchObject({
      position: 1,
      name: "Home",
      item: "https://vergeo5.com/en",
    });
    expect(items[1]).toMatchObject({
      position: 2,
      name: "Electronics",
      item: "https://vergeo5.com/en/c/electronics",
    });
  });
});
