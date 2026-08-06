import { describe, expect, it } from "vitest";

import {
  adminItemHref,
  resolveAdminActiveItem,
} from "../app/[locale]/_components/admin-nav-config";

describe("admin-nav-config", () => {
  it("builds locale-aware hrefs", () => {
    expect(adminItemHref("en", "")).toBe("/en");
    expect(adminItemHref("en", "kyc")).toBe("/en/kyc");
  });

  it("resolves nested admin routes", () => {
    expect(resolveAdminActiveItem("/kyc/123")).toBe("kyc");
    expect(resolveAdminActiveItem("/config/flags")).toBe("config");
    expect(resolveAdminActiveItem("/clips/analytics")).toBe("clips");
    expect(resolveAdminActiveItem("/")).toBe("home");
  });
});
