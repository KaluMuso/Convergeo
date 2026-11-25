// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ToastProvider } from "@vergeo/ui/src/toast";
import { afterEach, describe, expect, it } from "vitest";

import {
  resetWishlistStoreForTests,
  WISHLIST_STORAGE_KEY,
} from "../../../../../lib/wishlist-local";
import { SaveButton } from "./save-button";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  resetWishlistStoreForTests();
});

describe("SaveButton", () => {
  it("toggles aria-pressed and stores service kind", async () => {
    render(
      <ToastProvider copy={{ wishlistAdded: "Saved", wishlistRemoved: "Removed" }}>
        <SaveButton
          slug="plumber-lusaka"
          kind="service"
          addLabel="Save"
          removeLabel="Unsave"
          savedAnnounceLabel="Saved"
        />
      </ToastProvider>,
    );
    const button = screen.getByTestId("value-save-button");
    await act(async () => {
      fireEvent.click(button);
    });
    expect(button).toHaveAttribute("aria-pressed", "true");
    const stored = JSON.parse(window.localStorage.getItem(WISHLIST_STORAGE_KEY) ?? "[]");
    expect(stored[0]).toMatchObject({ slug: "plumber-lusaka", kind: "service" });
  });
});
