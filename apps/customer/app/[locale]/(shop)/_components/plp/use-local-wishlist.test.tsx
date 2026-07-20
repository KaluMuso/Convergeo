// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { resetLocalWishlistStoreForTests, useLocalWishlist } from "./use-local-wishlist";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  resetLocalWishlistStoreForTests();
});

beforeEach(() => {
  window.localStorage.clear();
  resetLocalWishlistStoreForTests();
});

describe("useLocalWishlist", () => {
  it("toggles a product slug in localStorage", () => {
    const { result } = renderHook(() => useLocalWishlist("tecno-spark"));

    expect(result.current.isWishlisted).toBe(false);

    act(() => {
      result.current.toggleWishlist();
    });

    expect(result.current.isWishlisted).toBe(true);
    expect(JSON.parse(window.localStorage.getItem("vergeo5:wishlist:v1") ?? "[]")).toContain(
      "tecno-spark",
    );

    act(() => {
      result.current.toggleWishlist();
    });

    expect(result.current.isWishlisted).toBe(false);
  });

  it("stays disabled without a product slug", () => {
    const { result } = renderHook(() => useLocalWishlist(null));
    expect(result.current.enabled).toBe(false);
    act(() => {
      result.current.toggleWishlist();
    });
    expect(window.localStorage.getItem("vergeo5:wishlist:v1")).toBeNull();
  });
});
