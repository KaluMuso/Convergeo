import { describe, expect, it } from "vitest";

import {
  ANALYTICS_TABS,
  analyticsPath,
  barPercent,
  bpsToFraction,
  rangeEndingYesterday,
  relativeChange,
  splitSeconds,
} from "./analytics-data";

describe("analytics data helpers", () => {
  it("builds a UTC window that ends yesterday", () => {
    const now = new Date("2026-11-20T01:00:00Z");
    expect(rangeEndingYesterday(7, now)).toEqual({ from: "2026-11-13", to: "2026-11-19" });
    expect(rangeEndingYesterday(1, now)).toEqual({ from: "2026-11-19", to: "2026-11-19" });
  });

  it("maps every tab to an aggregate-only API path", () => {
    expect(ANALYTICS_TABS.map((t) => t.api)).toEqual([
      "overview",
      "search-demand",
      "products-funnel",
      "insights",
    ]);
    expect(analyticsPath("overview", { from: "2026-11-01", to: "2026-11-07" })).toBe(
      "/admin/analytics/overview?from=2026-11-01&to=2026-11-07",
    );
  });

  it("converts basis points and relative change for display", () => {
    expect(bpsToFraction(2500)).toBe(0.25);
    expect(relativeChange(120, 100)).toBeCloseTo(0.2);
    expect(relativeChange(5, 0)).toBeNull();
  });

  it("scales bars and splits durations", () => {
    expect(barPercent(50, 200)).toBe(25);
    expect(barPercent(1, 10_000)).toBe(1);
    expect(barPercent(0, 10)).toBe(0);
    expect(splitSeconds(125)).toEqual({ minutes: 2, seconds: 5 });
  });
});
