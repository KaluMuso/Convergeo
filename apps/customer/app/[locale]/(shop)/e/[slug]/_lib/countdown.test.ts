import { describe, expect, it } from "vitest";

import { eventCountdownState } from "./countdown";

describe("eventCountdownState", () => {
  it("marks past events as ended", () => {
    const state = eventCountdownState(
      "2020-01-01T18:00:00+02:00",
      new Date("2020-01-01T22:00:00Z").getTime(),
      new Date("2025-06-01T12:00:00Z"),
    );
    expect(state).toEqual({ kind: "ended" });
  });

  it("uses Lusaka calendar day for today vs future", () => {
    const now = new Date("2026-09-12T10:00:00Z");
    const state = eventCountdownState(
      "2026-09-12T20:00:00+02:00",
      new Date("2026-09-12T23:00:00+02:00").getTime(),
      now,
      "en",
    );
    expect(state?.kind).toBe("today");
  });

  it("counts whole days until start in Lusaka", () => {
    const now = new Date("2026-09-10T12:00:00Z");
    const state = eventCountdownState(
      "2026-09-13T18:00:00+02:00",
      new Date("2026-09-13T22:00:00+02:00").getTime(),
      now,
      "en",
    );
    expect(state).toEqual({ kind: "days", days: 3 });
  });
});
