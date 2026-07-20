// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";

import { resetWishlistStoreForTests } from "../../../../../lib/wishlist-local";

import {
  isWishlisted,
  readWishlist,
  toggleWishlist,
  WISHLIST_STORAGE_KEY,
  writeWishlist,
} from "./wishlist-storage";

afterEach(() => {
  window.localStorage.clear();
  resetWishlistStoreForTests();
});

describe("wishlist-storage", () => {
  it("toggles wishlist membership for a product id", () => {
    expect(isWishlisted("p1")).toBe(false);
    expect(toggleWishlist("p1")).toBe(true);
    expect(isWishlisted("p1")).toBe(true);
    expect(toggleWishlist("p1")).toBe(false);
    expect(isWishlisted("p1")).toBe(false);
  });

  it("ignores corrupt localStorage payloads", () => {
    window.localStorage.setItem(WISHLIST_STORAGE_KEY, "not-json");
    expect(readWishlist()).toEqual({});
    writeWishlist({ p2: "2026-01-01T00:00:00.000Z" });
    expect(isWishlisted("p2")).toBe(true);
  });

  it("shares storage with slug-based PLP wishlist", () => {
    toggleWishlist("prod-uuid", "tecno-spark");
    const raw = JSON.parse(window.localStorage.getItem(WISHLIST_STORAGE_KEY) ?? "[]") as Array<{
      slug: string;
      productId?: string;
    }>;
    expect(
      raw.some((entry) => entry.slug === "tecno-spark" && entry.productId === "prod-uuid"),
    ).toBe(true);
  });
});
