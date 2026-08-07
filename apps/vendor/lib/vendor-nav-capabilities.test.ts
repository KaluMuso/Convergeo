import { describe, expect, it } from "vitest";

import {
  buildVendorMobilePrimary,
  buildVendorMoreMenuGroups,
  filterVendorNavGroups,
  isVendorMoreMenuActive,
  resolveVendorActiveItem,
  VENDOR_NAV_GROUPS,
} from "../app/[locale]/_components/vendor-nav-config";

import type { VendorNavCapabilities } from "./nav-capabilities";

function allVisible(): VendorNavCapabilities {
  return {
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
    clips: true,
    reviews: true,
    profile: true,
    payouts: true,
    disputes: true,
    intake: true,
  };
}

describe("filterVendorNavGroups", () => {
  it("hides clips when the capability is off", () => {
    const groups = filterVendorNavGroups({ ...allVisible(), clips: false });
    const keys = groups.flatMap((group) => group.items.map((item) => item.key));
    expect(keys).not.toContain("clips");
  });

  it("shows clips when the capability is on", () => {
    const groups = filterVendorNavGroups({ ...allVisible(), clips: true });
    const keys = groups.flatMap((group) => group.items.map((item) => item.key));
    expect(keys).toContain("clips");
  });

  it("hides intake when disabled", () => {
    const groups = filterVendorNavGroups({ ...allVisible(), intake: false });
    const keys = groups.flatMap((group) => group.items.map((item) => item.key));
    expect(keys).not.toContain("intake");
  });

  it("omits empty groups after filtering", () => {
    const groups = filterVendorNavGroups({
      ...allVisible(),
      analytics: false,
      services: false,
      events: false,
      rfq: false,
      jobs: false,
      clips: false,
      reviews: false,
    });
    expect(groups.some((group) => group.key === "sell")).toBe(false);
  });
});

describe("mobile More menu", () => {
  it("excludes primary tabs from the More sheet", () => {
    const groups = filterVendorNavGroups(allVisible());
    const moreGroups = buildVendorMoreMenuGroups(groups);
    const keys = moreGroups.flatMap((group) => group.items.map((item) => item.key));
    expect(keys).not.toContain("home");
    expect(keys).not.toContain("orders");
    expect(keys).not.toContain("listings");
    expect(keys).toContain("scan");
  });

  it("omits More when no secondary items remain", () => {
    const caps = {
      ...allVisible(),
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
    const groups = filterVendorNavGroups(caps);
    expect(buildVendorMobilePrimary(groups)).toEqual(["home", "orders", "listings"]);
  });

  it("includes More when secondary items exist", () => {
    const groups = filterVendorNavGroups(allVisible());
    expect(buildVendorMobilePrimary(groups)).toContain("more");
  });

  it("resolves active state from filtered items only", () => {
    const groups = filterVendorNavGroups({ ...allVisible(), clips: false });
    expect(
      resolveVendorActiveItem(
        "/clips",
        groups.flatMap((g) => g.items),
      ),
    ).toBeUndefined();
    expect(isVendorMoreMenuActive("/analytics", groups)).toBe(true);
  });
});

describe("resolveVendorActiveItem", () => {
  it("uses the default catalog when no items are passed", () => {
    expect(resolveVendorActiveItem("/orders/abc")).toBe("orders");
    expect(
      resolveVendorActiveItem(
        "/",
        VENDOR_NAV_GROUPS.flatMap((g) => g.items),
      ),
    ).toBe("home");
  });
});
