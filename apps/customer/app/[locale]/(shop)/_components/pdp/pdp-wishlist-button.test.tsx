// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetWishlistStoreForTests } from "../../../../../lib/wishlist-local";

import { PdpWishlistButton } from "./pdp-wishlist-button";
import { WISHLIST_STORAGE_KEY } from "./wishlist-storage";

vi.mock("../../../../../lib/engagement-api", () => ({
  syncWishlistWithServer: vi.fn(async () => undefined),
}));

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  resetWishlistStoreForTests();
});

describe("PdpWishlistButton", () => {
  it("toggles accessible wishlist state", async () => {
    const user = userEvent.setup();
    render(
      <PdpWishlistButton
        productId="prod-1"
        productSlug="tecno-spark"
        addLabel="Save to wishlist"
        removeLabel="Remove from wishlist"
        savedAnnounceLabel="Saved to wishlist"
      />,
    );

    const button = screen.getByTestId("pdp-wishlist-toggle");
    expect(button).toHaveAttribute("aria-pressed", "false");
    expect(button).toHaveAccessibleName("Save to wishlist");

    await user.click(button);
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(button).toHaveAccessibleName("Remove from wishlist");
    expect(window.localStorage.getItem(WISHLIST_STORAGE_KEY)).toContain("tecno-spark");
    expect(window.localStorage.getItem(WISHLIST_STORAGE_KEY)).toContain("prod-1");
  });
});
