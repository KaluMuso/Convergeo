import { describe, expect, it } from "vitest";

import { deepMergeMessages, isFallbackMarker } from "./deep-merge";

describe("isFallbackMarker", () => {
  it("detects notifications-style __fallback leaves", () => {
    expect(isFallbackMarker({ __fallback: "en" })).toBe(true);
    expect(isFallbackMarker({ body: "hi" })).toBe(false);
    expect(isFallbackMarker("en")).toBe(false);
  });
});

describe("deepMergeMessages", () => {
  it("overlays locale strings onto English without dropping siblings", () => {
    const merged = deepMergeMessages(
      { title: "Search", tabs: { all: "All", products: "Products" } },
      { tabs: { all: "Fyonse" } },
    );
    expect(merged).toEqual({
      title: "Search",
      tabs: { all: "Fyonse", products: "Products" },
    });
  });

  it("skips __fallback markers so English remains", () => {
    const merged = deepMergeMessages(
      { order: { shipped: "Shipped" } },
      { order: { shipped: { __fallback: "en" } }, __fallback: "en" },
    );
    expect(merged).toEqual({ order: { shipped: "Shipped" } });
  });
});
