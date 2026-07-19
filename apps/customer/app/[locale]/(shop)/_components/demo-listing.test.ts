import { describe, expect, it } from "vitest";

import { isDemoListingPublicId } from "./demo-listing";

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
