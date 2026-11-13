// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  recordListingPdpView: vi.fn(),
  recordRecentlyViewed: vi.fn(),
  recordRecentlyViewedOnServer: vi.fn(() => Promise.resolve()),
  getAccessToken: vi.fn(() => Promise.resolve<string | null>("tok")),
  track: vi.fn(),
}));

vi.mock("@vergeo/analytics", () => ({ track: mocks.track }));
vi.mock("../../../../../lib/engagement-api", () => ({
  recordRecentlyViewedOnServer: mocks.recordRecentlyViewedOnServer,
  getAccessToken: mocks.getAccessToken,
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
  vi.unstubAllEnvs();
});

describe("ProductViewTracker listing telemetry", () => {
  it("records the selected listing as a PDP view", () => {
    const listingId = "20000000-0000-4000-8000-000000000001";
    render(<ProductViewTracker productId="product-1" listingId={listingId} />);

    expect(mocks.recordListingPdpView).toHaveBeenCalledTimes(1);
    expect(mocks.recordListingPdpView).toHaveBeenCalledWith(listingId);
  });

  it("does not invent a listing view when the PDP has no selected listing", () => {
    render(<ProductViewTracker productId="product-1" />);

    expect(mocks.recordListingPdpView).not.toHaveBeenCalled();
  });

  it("v2: passes the session token so the API can exclude vendor self-views", async () => {
    vi.stubEnv("NEXT_PUBLIC_ANALYTICS_V2_TRACKING", "1");
    const listingId = "20000000-0000-4000-8000-000000000001";
    render(<ProductViewTracker productId="product-1" listingId={listingId} />);

    await vi.waitFor(() => expect(mocks.recordListingPdpView).toHaveBeenCalledTimes(1));
    expect(mocks.recordListingPdpView).toHaveBeenCalledWith(listingId, "tok");
  });
});
