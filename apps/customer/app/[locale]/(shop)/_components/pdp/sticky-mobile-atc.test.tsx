// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StickyMobileAtc } from "./sticky-mobile-atc";

import type { BuyBoxLabels, BuyBoxListing } from "./buy-box";
import type { ListingPurchaseControls } from "./use-listing-purchase";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const labels: BuyBoxLabels = {
  priceLabel: "Price",
  quantityLabel: "Quantity",
  decreaseLabel: "Decrease",
  increaseLabel: "Increase",
  decreaseSymbol: "-",
  increaseSymbol: "+",
  addToCartLabel: "Add to cart",
  addingToCartLabel: "Adding…",
  addToCartErrorLabel: "Could not add to cart.",
  inStockLabel: "In stock",
  outOfStockLabel: "Out of stock",
  alwaysAvailableLabel: "Available",
  singleVendorLabel: "Single vendor",
  conditionNewLabel: "New",
  conditionRefurbishedLabel: "Refurbished",
};

const listing: BuyBoxListing = {
  id: "listing-1",
  title: "Tecno Spark",
  priceNgwee: 450_000,
  condition: "new",
  stockMode: "tracked",
  stockQty: 5,
  moq: 1,
  inStock: true,
};

function makePurchase(overrides: Partial<ListingPurchaseControls> = {}): ListingPurchaseControls {
  return {
    quantity: 2,
    decrease: vi.fn(),
    increase: vi.fn(),
    atMin: false,
    atMax: false,
    adding: false,
    addError: null,
    addedMessage: null,
    handleAddToCart: vi.fn(),
    stockLabel: "In stock",
    maxQuantity: 5,
    ...overrides,
  };
}

describe("StickyMobileAtc", () => {
  let observerCallback: IntersectionObserverCallback | null = null;

  beforeEach(() => {
    observerCallback = null;
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(cb: IntersectionObserverCallback) {
          observerCallback = cb;
        }
        observe = vi.fn();
        disconnect = vi.fn();
        unobserve = vi.fn();
        takeRecords = vi.fn(() => []);
        root = null;
        rootMargin = "";
        thresholds = [];
      },
    );
  });

  it("stays hidden while the buy box intersects the viewport", () => {
    const observeRef = createRef<HTMLElement | null>();
    observeRef.current = document.createElement("section");
    const purchase = makePurchase();

    render(
      <StickyMobileAtc
        listing={listing}
        labels={labels}
        purchase={purchase}
        observeRef={observeRef}
        ariaLabel="Quick add to cart"
      />,
    );

    expect(observerCallback).not.toBeNull();
    observerCallback?.(
      [
        {
          isIntersecting: true,
          target: observeRef.current!,
        } as unknown as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    );

    expect(screen.queryByTestId("pdp-sticky-mobile-atc")).not.toBeInTheDocument();
  });

  it("shows qty + ATC when buy box leaves the viewport and syncs controls", async () => {
    const user = userEvent.setup();
    const observeRef = createRef<HTMLElement | null>();
    observeRef.current = document.createElement("section");
    const purchase = makePurchase();

    render(
      <StickyMobileAtc
        listing={listing}
        labels={labels}
        purchase={purchase}
        observeRef={observeRef}
        ariaLabel="Quick add to cart"
      />,
    );

    observerCallback?.(
      [
        {
          isIntersecting: false,
          target: observeRef.current!,
        } as unknown as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    );

    expect(await screen.findByTestId("pdp-sticky-mobile-atc")).toBeInTheDocument();
    expect(screen.getByTestId("pdp-sticky-qty-value")).toHaveTextContent("2");
    expect(screen.getByTestId("pdp-sticky-price")).toHaveTextContent(/K/);

    await user.click(screen.getByTestId("pdp-sticky-qty-increase"));
    expect(purchase.increase).toHaveBeenCalled();

    await user.click(screen.getByTestId("pdp-sticky-add-to-cart"));
    expect(purchase.handleAddToCart).toHaveBeenCalled();
  });

  it("does not render when listing is out of stock", () => {
    const observeRef = createRef<HTMLElement | null>();
    observeRef.current = document.createElement("section");
    const purchase = makePurchase();

    render(
      <StickyMobileAtc
        listing={{ ...listing, inStock: false }}
        labels={labels}
        purchase={purchase}
        observeRef={observeRef}
        ariaLabel="Quick add to cart"
      />,
    );

    observerCallback?.(
      [
        {
          isIntersecting: false,
          target: observeRef.current!,
        } as unknown as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    );

    expect(screen.queryByTestId("pdp-sticky-mobile-atc")).not.toBeInTheDocument();
  });
});
