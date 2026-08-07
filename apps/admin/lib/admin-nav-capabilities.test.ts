import { describe, expect, it } from "vitest";

import { filterAdminNavGroups } from "../app/[locale]/_components/admin-nav-config";

import { resolveAdminNavCapabilities } from "./admin-nav-capabilities";

describe("admin-nav-capabilities", () => {
  it("keeps clips and intake visible for operational admin work", () => {
    const caps = resolveAdminNavCapabilities();
    const keys = filterAdminNavGroups(caps).flatMap((group) => group.items.map((item) => item.key));
    expect(keys).toContain("clips");
    expect(keys).toContain("intake");
  });

  it("omits empty groups when every item is filtered out", () => {
    const caps = resolveAdminNavCapabilities();
    const empty = { ...caps, home: false };
    const groups = filterAdminNavGroups(empty);
    expect(groups.some((group) => group.key === "overview")).toBe(false);
    expect(groups.length).toBeGreaterThan(0);
  });
});
