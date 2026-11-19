import { describe, expect, it } from "vitest";

import {
  filterAdminNavGroups,
  resolveAdminActiveItem,
} from "../app/[locale]/_components/admin-nav-config";

import { resolveAdminNavCapabilities } from "./admin-nav-capabilities";

describe("analytics nav entry", () => {
  it("is hidden without analytics or finance grants", () => {
    const keys = filterAdminNavGroups(resolveAdminNavCapabilities()).flatMap((group) =>
      group.items.map((item) => item.key),
    );
    expect(keys).not.toContain("analytics");
    expect(resolveAdminNavCapabilities(["products.manage"]).analytics).toBe(false);
  });

  it("follows analytics.read, finance.read and finance.operate (D3), not the v2 flag", () => {
    for (const permission of ["analytics.read", "finance.read", "finance.operate"]) {
      expect(resolveAdminNavCapabilities([permission]).analytics).toBe(true);
    }
    const overview = filterAdminNavGroups(resolveAdminNavCapabilities(["analytics.read"])).find(
      (group) => group.key === "overview",
    );
    expect(overview?.items.map((item) => item.key)).toEqual(["home", "analytics"]);
    expect(resolveAdminActiveItem("/analytics/revenue")).toBe("analytics");
  });
});
