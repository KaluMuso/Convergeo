import { describe, expect, it } from "vitest";

import { countOverdue, dispatchCutoffClock, toneFor } from "./today-model";

describe("dispatchCutoffClock", () => {
  it("counts down to 14:00 Lusaka (12:00 UTC)", () => {
    const clock = dispatchCutoffClock(new Date("2026-11-13T08:30:00Z")); // 10:30 CAT
    expect(clock).toMatchObject({ passed: false, hours: 3, minutes: 30, urgent: false });
  });

  it("flags the last hour as urgent", () => {
    const clock = dispatchCutoffClock(new Date("2026-11-13T11:15:00Z")); // 13:15 CAT
    expect(clock).toMatchObject({ passed: false, hours: 0, minutes: 45, urgent: true });
  });

  it("is passed at and after 14:00 CAT", () => {
    expect(dispatchCutoffClock(new Date("2026-11-13T12:00:00Z")).passed).toBe(true);
    expect(dispatchCutoffClock(new Date("2026-11-13T20:00:00Z")).passed).toBe(true);
  });

  it("uses the Lusaka calendar day across UTC midnight", () => {
    // 23:30 UTC on the 12th is 01:30 CAT on the 13th: 12h30m to go.
    const clock = dispatchCutoffClock(new Date("2026-11-12T23:30:00Z"));
    expect(clock).toMatchObject({ passed: false, hours: 12, minutes: 30 });
  });
});

describe("counts and tone", () => {
  it("counts overdue SLA badges only", () => {
    expect(
      countOverdue([{ sla_badge: "overdue" }, { sla_badge: "on_track" }, { sla_badge: null }, {}]),
    ).toBe(1);
  });

  it("escalates only when there is work", () => {
    expect(toneFor(0, true)).toBe("clear");
    expect(toneFor(3, false)).toBe("attention");
    expect(toneFor(3, true)).toBe("urgent");
  });
});
