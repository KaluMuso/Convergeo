import { describe, expect, it } from "vitest";

import {
  allZero,
  exportFilename,
  grantsAllow,
  lusakaToday,
  periodQuery,
  ratingText,
  visibleTabs,
} from "./dashboards-data";

const tabsFor = (permissions: string[], v2 = false, unrestricted = false) =>
  visibleTabs({ permissions, unrestricted }, v2).map((entry) => entry.tab);

describe("analytics tabs by permission (D3)", () => {
  it("analytics.read sees operational tabs but not revenue", () => {
    expect(tabsFor(["analytics.read"])).toEqual([
      "users",
      "growth",
      "vendors",
      "servicesEvents",
      "performance",
    ]);
  });

  it("finance.read and finance.operate see revenue only", () => {
    expect(tabsFor(["finance.read"])).toEqual(["revenue"]);
    expect(tabsFor(["finance.operate"])).toEqual(["revenue"]);
  });

  it("v2 behaviour tabs appear only while analytics_v2 is enabled", () => {
    expect(tabsFor(["analytics.read"], true)).toEqual([
      "users",
      "growth",
      "vendors",
      "servicesEvents",
      "performance",
      "behaviour",
      "search",
      "products",
      "insights",
    ]);
    expect(tabsFor(["finance.read"], true)).toEqual(["revenue"]);
  });

  it("unrestricted admins see everything; no grants see nothing", () => {
    expect(tabsFor([], false, true)).toContain("revenue");
    expect(visibleTabs(null, true)).toEqual([]);
    expect(grantsAllow(null, "analytics")).toBe(false);
  });
});

describe("period query", () => {
  it("presets need no dates", () => {
    expect(periodQuery({ period: "today" })).toBe("period=today");
    expect(periodQuery({ period: "30d" })).toBe("period=30d");
  });

  it("custom needs a complete, ordered range", () => {
    expect(periodQuery({ period: "custom", from: "2026-11-01", to: "2026-11-13" })).toBe(
      "period=custom&from=2026-11-01&to=2026-11-13",
    );
    expect(periodQuery({ period: "custom", from: "2026-11-13", to: "2026-11-01" })).toBeNull();
    expect(periodQuery({ period: "custom", from: "2026-11-01" })).toBeNull();
    expect(periodQuery({ period: "custom", from: "13/11/2026", to: "2026-11-13" })).toBeNull();
  });
});

describe("helpers", () => {
  it("Lusaka today turns at 22:00 UTC", () => {
    expect(lusakaToday(new Date("2026-11-12T21:59:59Z"))).toBe("2026-11-12");
    expect(lusakaToday(new Date("2026-11-12T22:00:00Z"))).toBe("2026-11-13");
  });

  it("detects an all-zero series and formats ratings", () => {
    expect(allZero([{ day: "2026-11-13", a: 0, b: 0 }])).toBe(true);
    expect(allZero([{ day: "2026-11-13", a: 0, b: -500 }])).toBe(false);
    expect(ratingText(450)).toBe("4.5");
    expect(ratingText(433)).toBe("4.3");
    expect(exportFilename("revenue", { from: "2026-11-01", to: "2026-11-13" })).toBe(
      "vergeo5-revenue-2026-11-01-2026-11-13.csv",
    );
  });
});
