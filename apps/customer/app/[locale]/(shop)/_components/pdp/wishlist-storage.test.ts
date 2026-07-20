// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";

import {
  isWishlisted,
  readWishlist,
  toggleWishlist,
  WISHLIST_STORAGE_KEY,
  writeWishlist,
} from "./wishlist-storage";

afterEach(() => {
  window.localStorage.clear();
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
});
