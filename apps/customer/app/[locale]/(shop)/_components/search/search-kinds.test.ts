import { describe, expect, it } from "vitest";

import { SEARCH_KINDS, searchTabKinds, isSearchKind } from "./search-kinds";

/**
 * CUST-SEARCH-01 — digest `3273208722` / `TypeError: SEARCH_KINDS is not iterable`.
 * These constants must remain in a non-`"use client"` module so Server Components
 * can spread them when building tab-count fan-out.
 */
describe("SEARCH_KINDS server-safe export (CUST-SEARCH-01)", () => {
  it("is a real iterable array (regression for digest 3273208722)", () => {
    expect(Array.isArray(SEARCH_KINDS)).toBe(true);
    expect(typeof SEARCH_KINDS[Symbol.iterator]).toBe("function");
    expect([...SEARCH_KINDS]).toEqual(["products", "services", "events", "vendors"]);
  });

  it("builds tab kinds via spread without throwing", () => {
    const kinds = searchTabKinds();
    expect(kinds).toEqual(["all", "products", "services", "events", "vendors"]);
    // Exact previously failing pattern from search/page.tsx fetchTabCounts:
    const fanOut = ["all", ...SEARCH_KINDS];
    expect(fanOut).toHaveLength(5);
  });

  it("validates kind query params", () => {
    expect(isSearchKind("products")).toBe(true);
    expect(isSearchKind("supplies")).toBe(false);
    expect(isSearchKind("all")).toBe(false);
  });
});
