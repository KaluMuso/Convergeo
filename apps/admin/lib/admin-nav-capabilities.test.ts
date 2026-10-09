import { describe, expect, it } from "vitest";

import { filterAdminNavGroups } from "../app/[locale]/_components/admin-nav-config";

import { resolveAdminNavCapabilities } from "./admin-nav-capabilities";

describe("admin-nav-capabilities", () => {
  it("keeps legacy operations visible only for unrestricted admins", () => {
    const caps = resolveAdminNavCapabilities([], true);
    const keys = filterAdminNavGroups(caps).flatMap((group) => group.items.map((item) => item.key));
    expect(keys).toContain("clips");
    expect(keys).toContain("intake");
  });

  it("omits empty groups when every item is filtered out", () => {
    const caps = resolveAdminNavCapabilities([], true);
    const empty = { ...caps, home: false };
    const groups = filterAdminNavGroups(empty);
    expect(groups.some((group) => group.key === "overview")).toBe(false);
    expect(groups.length).toBeGreaterThan(0);
  });

  it("shows only granted destinations to a restricted role", () => {
    const caps = resolveAdminNavCapabilities(["finance.read"]);
    const keys = filterAdminNavGroups(caps).flatMap((group) => group.items.map((item) => item.key));
    expect(keys).toEqual(["orders"]);
    expect(caps.roles).toBe(false);
    expect(caps.events).toBe(false);
  });
});
