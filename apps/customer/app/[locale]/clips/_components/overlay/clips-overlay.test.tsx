// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import clipsMessages from "../../../../../../../packages/i18n/messages/en/clips.json";

/**
 * M17-P05 — the shoppable overlay.
 *
 * The claims: it does not obstruct the clip or its play control, it opens an
 * accessible sheet that can always be escaped, it prices through the shared
 * `formatK()` from integer ngwee, and it adds to cart through **the existing
 * cart function** — asserted by spying on that exact module, so a second cart
 * would fail this file rather than pass review.
 */

const addCartItemMock = vi.fn();
vi.mock("../../../(shop)/_components/cart/mini-cart-drawer", () => ({
  addCartItem: (...args: unknown[]) => addCartItemMock(...args),
}));

import { ClipOverlay } from "./clip-overlay";

import type { Clip } from "../types";

function clip(overrides: Partial<Clip> = {}): Clip {
  return {
    id: "c1",
    caption: "solar lamp",
    poster_url: "https://res.cloudinary.com/demo/c1.webp",
    duration_s: 20,
    renditions: {},
    like_count: 0,
    comment_count: 0,
    view_count: 0,
    published_at: "2026-07-27T10:00:00Z",
    vendor: { vendor_id: "v1", display_name: "Alpha Traders", slug: "alpha" },
    listings: [{ listing_id: "l1", title: "Solar lamp", price_ngwee: 123_456 }],
    ...overrides,
  };
}

function renderOverlay(subject: Clip = clip()) {
  return render(
    <NextIntlClientProvider locale="en" messages={{ clips: clipsMessages }} onError={() => {}}>
      <ClipOverlay clip={subject} locale="en" />
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  addCartItemMock.mockReset();
  addCartItemMock.mockResolvedValue({ items: [] });
});

afterEach(cleanup);

// --- Non-obstructive ---------------------------------------------------------
describe("the overlay is non-obstructive", () => {
  it("renders a single chip and no sheet until it is tapped", () => {
    renderOverlay();

    expect(screen.getByTestId("clip-shop-trigger")).toBeInTheDocument();
    expect(screen.queryByTestId("clip-product-sheet")).toBeNull();
  });

  it("renders nothing at all for a clip with no linked listings", () => {
    const { container } = renderOverlay(clip({ listings: [] }));

    expect(container).toBeEmptyDOMElement();
  });

  it("announces itself as a dialog trigger for assistive tech", () => {
    renderOverlay();

    const trigger = screen.getByTestId("clip-shop-trigger");
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});

// --- The sheet ---------------------------------------------------------------
describe("the product sheet", () => {
  it("opens as an aria-modal dialog and closes on Escape", async () => {
    const user = userEvent.setup();
    renderOverlay();

    await user.click(screen.getByTestId("clip-shop-trigger"));
    const sheet = screen.getByTestId("clip-product-sheet");
    expect(sheet).toHaveAttribute("aria-modal", "true");
    expect(sheet).toHaveAttribute("role", "dialog");

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByTestId("clip-product-sheet")).toBeNull());
  });

  it("restores focus to the trigger when it closes", async () => {
    const user = userEvent.setup();
    renderOverlay();

    const trigger = screen.getByTestId("clip-shop-trigger");
    await user.click(trigger);
    await user.click(screen.getByTestId("clip-sheet-close"));

    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("moves focus into the sheet on open", async () => {
    const user = userEvent.setup();
    renderOverlay();

    await user.click(screen.getByTestId("clip-shop-trigger"));

    await waitFor(() => expect(screen.getByTestId("clip-product-sheet")).toHaveFocus());
  });

  it("prices through the shared formatter from integer ngwee", async () => {
    const user = userEvent.setup();
    renderOverlay();

    await user.click(screen.getByTestId("clip-shop-trigger"));

    // 123_456 ngwee is K1,234.56 — the shared formatK, never local maths.
    expect(screen.getByTestId("clip-listing-price")).toHaveTextContent("1,234.56");
  });

  it("renders an XSS attempt in a listing title as text", async () => {
    const user = userEvent.setup();
    const payload = '<img src=x onerror="alert(1)">';
    renderOverlay(clip({ listings: [{ listing_id: "l1", title: payload, price_ngwee: 1000 }] }));

    await user.click(screen.getByTestId("clip-shop-trigger"));

    const title = screen.getByTestId("clip-listing-title");
    expect(title).toHaveTextContent(payload);
    expect(title.querySelector("img")).toBeNull();
  });

  it("keeps a real PDP link so the commerce path is never JS-exclusive", async () => {
    const user = userEvent.setup();
    renderOverlay();

    await user.click(screen.getByTestId("clip-shop-trigger"));

    expect(screen.getByTestId("clip-listing-link")).toHaveAttribute("href", "/en/l/l1");
  });
});

// --- One cart ----------------------------------------------------------------
describe("add to cart", () => {
  it("calls the existing cart function, with the clip id as attribution", async () => {
    const user = userEvent.setup();
    renderOverlay();

    await user.click(screen.getByTestId("clip-shop-trigger"));
    await user.click(screen.getByTestId("clip-add-to-cart"));

    await waitFor(() => expect(addCartItemMock).toHaveBeenCalledWith("l1", 1, "c1"));
  });

  it("surfaces a cart failure rather than pretending it worked", async () => {
    const user = userEvent.setup();
    addCartItemMock.mockRejectedValue(new Error("out of stock"));
    renderOverlay();

    await user.click(screen.getByTestId("clip-shop-trigger"));
    await user.click(screen.getByTestId("clip-add-to-cart"));

    await waitFor(() => expect(screen.getByTestId("clip-add-failed")).toBeInTheDocument());
  });

  it("does not fetch listings — they are already in the feed payload", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    renderOverlay();

    await user.click(screen.getByTestId("clip-shop-trigger"));

    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

// --- i18n --------------------------------------------------------------------
describe("i18n", () => {
  it("uses only keys M17-P04 seeded under clips.overlay", () => {
    const overlay = (clipsMessages as { overlay: Record<string, string> }).overlay;

    for (const key of [
      "shopThisClip",
      "title",
      "close",
      "addToCart",
      "added",
      "adding",
      "viewProduct",
      "empty",
      "failed",
    ]) {
      expect(overlay[key]).toBeTruthy();
    }
  });
});
