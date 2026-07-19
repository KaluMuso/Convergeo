import { describe, expect, it } from "vitest";

import {
  MAX_SEARCH_QUERY_LENGTH,
  normalizeSearchQuery,
  parseSearchKind,
  parseSearchPage,
  resolveSearchPageView,
} from "./search-view";

import type { SearchResponse, TabCounts } from "./results-tabs";

const emptyResponse: SearchResponse = {
  query: "zzzznonexistent999",
  expanded_query: "zzzznonexistent999",
  page: 1,
  page_size: 20,
  total: 0,
  results: [],
  degraded: true,
};

const successResponse: SearchResponse = {
  query: "phone",
  expanded_query: "phone",
  page: 1,
  page_size: 20,
  total: 2,
  results: [
    {
      id: "1",
      entity_kind: "product",
      entity_id: "p1",
      title: "Itel A70",
      body: null,
      category_path: "electronics/phones",
      price_min_ngwee: 100,
      price_max_ngwee: 100,
      lat: null,
      lng: null,
      locale_terms: null,
      boost_signals: {},
      rrf_score: 1,
    },
  ],
  degraded: false,
};

const tabCounts: TabCounts = {
  all: 2,
  products: 2,
  services: 0,
  events: 0,
  vendors: 0,
};

describe("normalizeSearchQuery", () => {
  it("treats blank/whitespace as empty (idle landing)", () => {
    expect(normalizeSearchQuery(undefined)).toEqual({ status: "empty" });
    expect(normalizeSearchQuery("   ")).toEqual({ status: "empty" });
  });

  it("accepts a harmless query", () => {
    expect(normalizeSearchQuery(" phone ")).toEqual({ status: "ok", query: "phone" });
  });

  it("rejects oversized input as invalid (not as API empty)", () => {
    const tooLong = "a".repeat(MAX_SEARCH_QUERY_LENGTH + 1);
    expect(normalizeSearchQuery(tooLong)).toEqual({ status: "invalid", reason: "too_long" });
  });
});

describe("parseSearchKind / parseSearchPage", () => {
  it("preserves valid kind/page and soft-falls back for malformed values", () => {
    expect(parseSearchKind("products")).toBe("products");
    expect(parseSearchKind("nope")).toBe("all");
    expect(parseSearchKind(undefined)).toBe("all");
    expect(parseSearchPage("3")).toBe(3);
    expect(parseSearchPage("0")).toBe(1);
    expect(parseSearchPage("abc")).toBe(1);
  });
});

describe("resolveSearchPageView", () => {
  it("maps successful search to results", () => {
    const view = resolveSearchPageView({
      normalized: { status: "ok", query: "phone" },
      kind: "all",
      searchResponse: successResponse,
      tabCounts,
    });
    expect(view.status).toBe("results");
    if (view.status === "results") {
      expect(view.response.total).toBe(2);
      expect(view.tabCounts.products).toBe(2);
    }
  });

  it("maps zero-result API payload to empty (not unavailable)", () => {
    const view = resolveSearchPageView({
      normalized: { status: "ok", query: "zzzznonexistent999" },
      kind: "all",
      searchResponse: emptyResponse,
      tabCounts: { all: 0, products: 0, services: 0, events: 0, vendors: 0 },
    });
    expect(view).toMatchObject({ status: "zero", query: "zzzznonexistent999" });
  });

  it("maps null API response to unavailable (never fake zero results)", () => {
    const view = resolveSearchPageView({
      normalized: { status: "ok", query: "phone" },
      kind: "all",
      searchResponse: null,
      tabCounts: null,
    });
    expect(view).toEqual({ status: "unavailable", query: "phone" });
  });

  it("maps missing tab counts after a successful hit list to unavailable", () => {
    const view = resolveSearchPageView({
      normalized: { status: "ok", query: "phone" },
      kind: "all",
      searchResponse: successResponse,
      tabCounts: null,
    });
    expect(view.status).toBe("unavailable");
  });

  it("keeps malformed oversize query distinct from zero results", () => {
    const view = resolveSearchPageView({
      normalized: { status: "invalid", reason: "too_long" },
      kind: "all",
      searchResponse: null,
      tabCounts: null,
    });
    expect(view).toEqual({ status: "invalid", reason: "too_long" });
  });

  it("stays idle when there is no query", () => {
    expect(
      resolveSearchPageView({
        normalized: { status: "empty" },
        kind: "all",
        searchResponse: null,
        tabCounts: null,
      }),
    ).toEqual({ status: "idle" });
  });
});
