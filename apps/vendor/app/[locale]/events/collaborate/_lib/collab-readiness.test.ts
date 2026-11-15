import { describe, expect, it } from "vitest";

import {
  emptyChecklist,
  emptyDraft,
  kwachaToNgwee,
  ngweeToKwachaText,
  parsePercentInput,
  percentToBps,
  readinessPct,
  submitErrors,
  type Checklist,
} from "./collab-readiness";

const NOW = new Date("2026-11-15T10:00:00Z");

function complete(): Checklist {
  return {
    venue: { name: "Hall", landmark: "Near the mall", lat: -15.4, lng: 28.3 },
    schedule: {
      starts_at: "2026-12-01T18:00:00Z",
      ends_at: "2026-12-01T22:00:00Z",
    },
    capacity: { capacity: 200 },
    equipment: {
      sound: "ready",
      stage: "not_needed",
      power: "ready",
      seating: "ready",
      security: "ready",
    },
    permits: { status: "obtained", note: null },
    tiers: [{ name: "General", price_ngwee: 5000, qty_cap: 150 }],
  };
}

describe("readiness percentage (mirrors the API)", () => {
  it("is 0 for an empty checklist and 100 when every item is ready", () => {
    expect(readinessPct(emptyChecklist(), null)).toBe(0);
    expect(readinessPct(complete(), 2500)).toBe(100);
  });

  it("counts answered-but-not-ready equipment and permits as open", () => {
    const checklist = complete();
    checklist.equipment.stage = "needed";
    checklist.permits.status = "pending";
    expect(readinessPct(checklist, 2500)).toBe(Math.round((100 * 9) / 11));
    expect(readinessPct(checklist, null)).toBe(Math.round((100 * 8) / 11));
  });

  it("needs venue name, landmark and GPS together", () => {
    const checklist = complete();
    checklist.venue.lat = null;
    expect(readinessPct(checklist, 2500)).toBe(Math.round((100 * 10) / 11));
  });
});

describe("share and money parsing", () => {
  it("stores the share as integer basis points", () => {
    expect(percentToBps(25)).toBe(2500);
    expect(parsePercentInput("12.5")).toBe(1250);
    expect(parsePercentInput("12,5")).toBe(1250);
    expect(parsePercentInput("0")).toBe(0);
    expect(parsePercentInput("100")).toBe(10_000);
  });

  it("rejects out-of-range or malformed percentages", () => {
    for (const bad of ["", "abc", "101", "-1", "12.345", "1e2"]) {
      expect(parsePercentInput(bad)).toBeNull();
    }
  });

  it("converts kwacha text to integer ngwee without float drift", () => {
    expect(kwachaToNgwee("50")).toBe(5000);
    expect(kwachaToNgwee("19.99")).toBe(1999);
    expect(kwachaToNgwee("0.1")).toBe(10);
    expect(kwachaToNgwee("1.234")).toBeNull();
    expect(kwachaToNgwee("-5")).toBeNull();
    expect(ngweeToKwachaText(1999)).toBe("19.99");
    expect(ngweeToKwachaText(5000)).toBe("50");
  });
});

describe("submit validation", () => {
  const draft = { ...emptyDraft(), title: "Night", category: "music" };

  it("accepts a complete proposal, even with equipment still needed", () => {
    const checklist = complete();
    checklist.equipment.stage = "needed";
    expect(submitErrors(draft, checklist, 2500, NOW)).toEqual([]);
  });

  it("lists every missing item", () => {
    const fields = submitErrors(emptyDraft(), emptyChecklist(), null, NOW).map(
      (e) => e.field,
    );
    expect(fields).toEqual(
      expect.arrayContaining([
        "event_draft.title",
        "event_draft.category",
        "checklist.venue.name",
        "checklist.venue.landmark",
        "checklist.venue.gps",
        "checklist.schedule.starts_at",
        "checklist.capacity.capacity",
        "checklist.equipment.sound",
        "checklist.permits.status",
        "checklist.tiers",
        "revenue_share_bps",
      ]),
    );
  });

  it("checks the schedule and tier caps", () => {
    const past = complete();
    past.schedule = {
      starts_at: "2026-11-01T10:00:00Z",
      ends_at: "2026-11-01T12:00:00Z",
    };
    expect(submitErrors(draft, past, 100, NOW)).toContainEqual({
      field: "checklist.schedule.starts_at",
      code: "must_be_future",
    });
    const backwards = complete();
    backwards.schedule.ends_at = "2026-12-01T17:00:00Z";
    expect(submitErrors(draft, backwards, 100, NOW)).toContainEqual({
      field: "checklist.schedule.ends_at",
      code: "must_be_after_start",
    });
    const big = complete();
    big.tiers = [{ name: "VIP", price_ngwee: 100, qty_cap: 500 }];
    expect(submitErrors(draft, big, 100, NOW)).toContainEqual({
      field: "checklist.tiers.0.qty_cap",
      code: "exceeds_capacity",
    });
  });
});
