import { describe, expect, it } from "vitest";

import {
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
});
