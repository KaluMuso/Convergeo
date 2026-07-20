// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  resetLocalWishlistStoreForTests,
  useLocalWishlist,
  useLocalWishlistSlugs,
} from "./use-local-wishlist";

vi.mock("../../../../../lib/engagement-api", () => ({
  syncWishlistWithServer: vi.fn(async () => undefined),
}));

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
    const stored = JSON.parse(window.localStorage.getItem("vergeo5:wishlist:v2") ?? "[]") as Array<{
      slug: string;
    }>;
    expect(stored.some((entry) => entry.slug === "tecno-spark")).toBe(true);

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
    expect(window.localStorage.getItem("vergeo5:wishlist:v2")).toBeNull();
  });

  it("lists and removes saved slugs for the wishlist page", () => {
    const toggle = renderHook(() => useLocalWishlist("itel-a70"));
    act(() => {
      toggle.result.current.toggleWishlist();
    });

    const list = renderHook(() => useLocalWishlistSlugs());
    expect(list.result.current.slugs).toContain("itel-a70");

    act(() => {
      list.result.current.remove("itel-a70");
    });
    expect(list.result.current.slugs).not.toContain("itel-a70");
  });

  it("migrates legacy v1 slug arrays", () => {
    window.localStorage.setItem("vergeo5:wishlist:v1", JSON.stringify(["legacy-phone"]));
    const { result } = renderHook(() => useLocalWishlist("legacy-phone"));
    expect(result.current.isWishlisted).toBe(true);
  });
});
