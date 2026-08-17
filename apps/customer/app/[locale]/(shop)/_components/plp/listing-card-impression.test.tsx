// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const telemetry = vi.hoisted(() => ({
  queueListingImpression: vi.fn(),
}));

vi.mock("../../../../../lib/listing-view-telemetry", () => telemetry);
vi.mock("./use-local-wishlist", () => ({
  useLocalWishlist: () => ({
    isWishlisted: false,
    toggleWishlist: vi.fn(),
    enabled: false,
  }),
}));

import { ListingCard } from "./listing-card";

const LISTING_ID = "20000000-0000-4000-8000-000000000001";

let emitEntries: ((entries: IntersectionObserverEntry[]) => void) | null = null;
const observe = vi.fn();
const disconnect = vi.fn();

class MockIntersectionObserver implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = "0px";
  readonly thresholds = [0, 0.5];

  constructor(callback: IntersectionObserverCallback) {
    emitEntries = (entries) => callback(entries, this);
  }

  disconnect = disconnect;
  observe = observe;
  takeRecords = vi.fn(() => []);
  unobserve = vi.fn();
}

const labels = {
  vendor: "Sold by {vendor}",
  noReviews: "No reviews",
  reviewCount: "({count})",
  quickAdd: "Quick add",
  wishlist: "Save",
  outOfStock: "Out of stock",
};

function emitVisibility(ratio: number): void {
  const target = screen.getByTestId("listing-card");
  const bounds = target.getBoundingClientRect();
  act(() => {
    emitEntries?.([
      {
        target,
        isIntersecting: ratio > 0,
        intersectionRatio: ratio,
        boundingClientRect: bounds,
        intersectionRect: bounds,
        rootBounds: null,
        time: 0,
      },
    ]);
  });
}

describe("ListingCard impression eligibility", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
    telemetry.queueListingImpression.mockReset();
    observe.mockClear();
    disconnect.mockClear();
    emitEntries = null;
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("queues only after at least 50% remains visible for one continuous second", () => {
    render(
      <ListingCard
        locale="en"
        labels={labels}
        listing={{
          id: LISTING_ID,
          title: "Phone",
          productSlug: "phone",
          vendorName: "Alpha",
          priceNgwee: 100_000,
          condition: "new",
          inStock: true,
          imagePublicId: null,
          rating: 0,
          reviewCount: 0,
          distanceM: null,
          belowMedian: false,
          deliveryAvailable: false,
          pickupAvailable: false,
        }}
      />,
    );

    expect(observe).toHaveBeenCalledWith(screen.getByTestId("listing-card"));
    emitVisibility(0.5);
    act(() => vi.advanceTimersByTime(600));
    emitVisibility(0.49);
    act(() => vi.advanceTimersByTime(600));
    expect(telemetry.queueListingImpression).not.toHaveBeenCalled();

    emitVisibility(0.5);
    act(() => vi.advanceTimersByTime(999));
    expect(telemetry.queueListingImpression).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));

    expect(telemetry.queueListingImpression).toHaveBeenCalledTimes(1);
    expect(telemetry.queueListingImpression).toHaveBeenCalledWith(LISTING_ID, "unknown");
    expect(disconnect).toHaveBeenCalled();
  });
});
