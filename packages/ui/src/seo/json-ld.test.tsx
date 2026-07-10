import { describe, expect, it } from "vitest";

import {
  buildBreadcrumbListJsonLd,
  buildEventJsonLd,
  buildLocalBusinessJsonLd,
  buildProductJsonLd,
  buildLocaleCanonical,
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

describe("buildProductJsonLd", () => {
  it("maps offers with exact ZMW decimal prices", () => {
    const jsonLd = buildProductJsonLd({
      name: "Itel A70",
      slug: "itel-a70",
      locale: "en",
      brand: "Itel",
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
    });

    expect(jsonLd["@type"]).toBe("Product");
    expect(jsonLd.name).toBe("Itel A70");
    const offers = jsonLd.offers as Array<Record<string, unknown>>;
    expect(offers).toHaveLength(2);
    expect(offers[0]?.price).toBe("1234.56");
    expect(offers[0]?.priceCurrency).toBe("ZMW");
    expect(offers[1]?.price).toBe("1250.00");
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
