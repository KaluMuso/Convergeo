import { describe, expect, it } from "vitest";

import { isDemoListingPublicId, shouldShowSampleListingBadge } from "./demo-listing";

describe("isDemoListingPublicId", () => {
  it("detects demo/ seed public IDs", () => {
    expect(isDemoListingPublicId("demo/products/itel-a70")).toBe(true);
    expect(isDemoListingPublicId("vergeo5/demo/products/itel-a70")).toBe(true);
    expect(isDemoListingPublicId("/demo/categories/phones")).toBe(true);
  });

  it("does not label real inventory as demo", () => {
    expect(isDemoListingPublicId("vendors/acme/listing-1")).toBe(false);
    expect(isDemoListingPublicId("campaign/summer-sale")).toBe(false);
    expect(isDemoListingPublicId("demodex/hero")).toBe(false);
    expect(isDemoListingPublicId(null)).toBe(false);
    expect(isDemoListingPublicId("")).toBe(false);
  });
});

describe("shouldShowSampleListingBadge", () => {
  it("hides sample badges in production by default", () => {
    expect(shouldShowSampleListingBadge({ NODE_ENV: "production" })).toBe(false);
  });

  it("shows sample badges outside production", () => {
    expect(shouldShowSampleListingBadge({ NODE_ENV: "development" })).toBe(true);
    expect(shouldShowSampleListingBadge({ NODE_ENV: "test" })).toBe(true);
  });

  it("honours the explicit public env flag", () => {
    expect(
      shouldShowSampleListingBadge({
        NODE_ENV: "production",
        NEXT_PUBLIC_SHOW_SAMPLE_LISTINGS: "true",
      }),
    ).toBe(true);
    expect(
      shouldShowSampleListingBadge({
        NODE_ENV: "development",
        NEXT_PUBLIC_SHOW_SAMPLE_LISTINGS: "0",
      }),
    ).toBe(false);
  });
});
