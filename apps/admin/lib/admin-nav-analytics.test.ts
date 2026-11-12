import { describe, expect, it } from "vitest";

import {
  filterAdminNavGroups,
  resolveAdminActiveItem,
} from "../app/[locale]/_components/admin-nav-config";

import { resolveAdminNavCapabilities } from "./admin-nav-capabilities";

describe("analytics nav entry (1B-05)", () => {
  it("is hidden by default so the nav is unchanged while the flag is off", () => {
    const keys = filterAdminNavGroups(resolveAdminNavCapabilities()).flatMap((group) =>
      group.items.map((item) => item.key),
    );
    expect(keys).not.toContain("analytics");
  });

  it("appears in the overview group once the status probe enables it", () => {
    const caps = { ...resolveAdminNavCapabilities(), analytics: true };
    const overview = filterAdminNavGroups(caps).find((group) => group.key === "overview");
    expect(overview?.items.map((item) => item.key)).toEqual(["home", "analytics"]);
    expect(resolveAdminActiveItem("/analytics/search")).toBe("analytics");
  });
});
