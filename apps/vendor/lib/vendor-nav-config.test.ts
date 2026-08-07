import { describe, expect, it } from "vitest";

import {
  buildVendorMobilePrimary,
  filterVendorNavGroups,
  resolveVendorActiveItem,
  vendorItemHref,
} from "../app/[locale]/_components/vendor-nav-config";

describe("vendor-nav-config", () => {
  it("builds locale-aware hrefs", () => {
    expect(vendorItemHref("en", "")).toBe("/en");
    expect(vendorItemHref("en", "/orders")).toBe("/en/orders");
  });

  it("resolves nested routes to the longest matching nav item", () => {
    expect(resolveVendorActiveItem("/orders/abc")).toBe("orders");
    expect(resolveVendorActiveItem("/listings/new")).toBe("listings");
    expect(resolveVendorActiveItem("/analytics")).toBe("analytics");
    expect(resolveVendorActiveItem("/")).toBe("home");
  });

  it("hides clips when capability is disabled", () => {
    const caps = {
      home: true,
      orders: true,
      listings: true,
      scan: true,
      returns: true,
      analytics: true,
      services: true,
      events: true,
      rfq: true,
      jobs: true,
      clips: false,
      reviews: true,
      profile: true,
      payouts: true,
      disputes: true,
      intake: false,
    };
    const keys = filterVendorNavGroups(caps).flatMap((g) => g.items.map((i) => i.key));
    expect(keys).not.toContain("clips");
    expect(keys).not.toContain("intake");
  });

  it("omits More when every secondary destination is filtered out", () => {
    const caps = {
      home: true,
      orders: true,
      listings: true,
      scan: false,
      returns: false,
      analytics: false,
      services: false,
      events: false,
      rfq: false,
      jobs: false,
      clips: false,
      reviews: false,
      profile: false,
      payouts: false,
      disputes: false,
      intake: false,
    };
    expect(buildVendorMobilePrimary(filterVendorNavGroups(caps))).toEqual([
      "home",
      "orders",
      "listings",
    ]);
  });
});
