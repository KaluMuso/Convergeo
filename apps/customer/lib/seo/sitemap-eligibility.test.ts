import { describe, expect, it } from "vitest";

import {
  coerceSitemapId,
  isSitemapEligibleCategorySlug,
  isSitemapEligibleEntitySlug,
  isSitemapEligibleStaticSegment,
  ROBOTS_DISALLOW_SUFFIXES,
  robotsForRouteKind,
  SITEMAP_EXCLUDED_SEGMENTS,
  SITEMAP_STATIC_SEGMENTS,
} from "./sitemap-eligibility";

describe("coerceSitemapId", () => {
  it("coerces string metadata ids used by Next sitemap chunks", () => {
    expect(coerceSitemapId("0")).toBe(0);
    expect(coerceSitemapId("4")).toBe(4);
    expect(coerceSitemapId("nope")).toBeNull();
  });
});

describe("sitemap static eligibility", () => {
  it("includes public discovery hubs only", () => {
    expect([...SITEMAP_STATIC_SEGMENTS]).toEqual([
      "",
      "categories",
      "directory",
      "events",
      "services",
    ]);
    for (const segment of SITEMAP_STATIC_SEGMENTS) {
      expect(isSitemapEligibleStaticSegment(segment)).toBe(true);
    }
  });

  it("excludes search, transactional, private, and gated routes", () => {
    for (const segment of SITEMAP_EXCLUDED_SEGMENTS) {
      expect(isSitemapEligibleStaticSegment(segment)).toBe(false);
    }
    expect(isSitemapEligibleStaticSegment("search")).toBe(false);
    expect(isSitemapEligibleStaticSegment("cart")).toBe(false);
    expect(isSitemapEligibleStaticSegment("checkout")).toBe(false);
    expect(isSitemapEligibleStaticSegment("supplies")).toBe(false);
    expect(isSitemapEligibleStaticSegment("compare")).toBe(false);
  });
});

describe("sitemap entity / category slug eligibility", () => {
  it("accepts clean public slugs", () => {
    expect(isSitemapEligibleEntitySlug("itel-a70")).toBe(true);
    expect(isSitemapEligibleCategorySlug("electronics")).toBe(true);
    expect(isSitemapEligibleCategorySlug("all")).toBe(true);
  });

  it("rejects empty, query, and nested entity slugs", () => {
    expect(isSitemapEligibleEntitySlug("")).toBe(false);
    expect(isSitemapEligibleEntitySlug("foo?bar=1")).toBe(false);
    expect(isSitemapEligibleEntitySlug("a/b")).toBe(false);
    expect(isSitemapEligibleCategorySlug("  ")).toBe(false);
  });
});

describe("robots exclusions", () => {
  it("disallows private, transactional, search, beta, and supplies paths", () => {
    expect(ROBOTS_DISALLOW_SUFFIXES).toEqual(
      expect.arrayContaining([
        "/checkout",
        "/cart",
        "/account",
        "/search",
        "/ask",
        "/compare",
        "/supplies",
        "/services/post-job",
        "/beta",
        "/admin",
      ]),
    );
  });

  it("maps route kinds to honest index/noindex intent", () => {
    expect(robotsForRouteKind("public_catalogue")).toEqual({ index: true, follow: true });
    expect(robotsForRouteKind("parameterised_search")).toEqual({
      index: false,
      follow: false,
    });
    expect(robotsForRouteKind("transactional")).toEqual({ index: false, follow: false });
    expect(robotsForRouteKind("beta_only")).toEqual({ index: false, follow: false });
    expect(robotsForRouteKind("gated_b2b")).toEqual({ index: false, follow: false });
    expect(robotsForRouteKind("empty_or_missing")).toEqual({ index: false, follow: false });
  });
});
