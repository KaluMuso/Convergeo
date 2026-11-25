// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";

import {
  listWishlistEntries,
  resetWishlistStoreForTests,
  toggleWishlistLocal,
  WISHLIST_STORAGE_KEY,
  WISHLIST_STORAGE_KEY_V1,
} from "./wishlist-local";

afterEach(() => {
  resetWishlistStoreForTests();
  window.localStorage.clear();
});

describe("wishlist-local kind migration", () => {
  it("loads legacy v2 product entries without kind as product", () => {
    window.localStorage.setItem(
      WISHLIST_STORAGE_KEY,
      JSON.stringify([{ slug: "phone-a", savedAt: "2026-01-01T00:00:00.000Z" }]),
    );
    resetWishlistStoreForTests();
    expect(listWishlistEntries()[0]?.kind ?? "product").toBe("product");
  });

  it("stores service and event kinds", () => {
    toggleWishlistLocal({ slug: "plumber-joe", kind: "service" });
    toggleWishlistLocal({ slug: "market-fest", kind: "event" });
    const kinds = listWishlistEntries().map((e) => e.kind);
    expect(kinds).toEqual(expect.arrayContaining(["service", "event"]));
  });

  it("migrates legacy v1 slug array", () => {
    window.localStorage.setItem(WISHLIST_STORAGE_KEY_V1, JSON.stringify(["legacy-slug"]));
    resetWishlistStoreForTests();
    expect(listWishlistEntries()[0]?.slug).toBe("legacy-slug");
    expect(window.localStorage.getItem(WISHLIST_STORAGE_KEY_V1)).toBeNull();
  });
});
