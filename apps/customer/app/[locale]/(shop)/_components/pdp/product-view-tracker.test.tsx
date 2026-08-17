// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  recordListingPdpView: vi.fn(),
  recordRecentlyViewed: vi.fn(),
  recordRecentlyViewedOnServer: vi.fn(() => Promise.resolve()),
  track: vi.fn(),
}));

vi.mock("@vergeo/analytics", () => ({ track: mocks.track }));
vi.mock("../../../../../lib/engagement-api", () => ({
  recordRecentlyViewedOnServer: mocks.recordRecentlyViewedOnServer,
}));
vi.mock("../../../../../lib/listing-view-telemetry", () => ({
  recordListingPdpView: mocks.recordListingPdpView,
}));
vi.mock("../recently-viewed/use-recently-viewed", () => ({
  recordRecentlyViewed: mocks.recordRecentlyViewed,
}));

import { ProductViewTracker } from "./product-view-tracker";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProductViewTracker listing telemetry", () => {
  it("records the selected listing as a PDP view", () => {
    const listingId = "20000000-0000-4000-8000-000000000001";
    render(<ProductViewTracker productId="product-1" listingId={listingId} />);

    expect(mocks.recordListingPdpView).toHaveBeenCalledTimes(1);
    expect(mocks.recordListingPdpView).toHaveBeenCalledWith(listingId, "pdp");
  });

  it("does not invent a listing view when the PDP has no selected listing", () => {
    render(<ProductViewTracker productId="product-1" />);

    expect(mocks.recordListingPdpView).not.toHaveBeenCalled();
  });
});
