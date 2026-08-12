import { describe, expect, it } from "vitest";

import { effectiveInstanceEndMs, isPastEventInstance } from "./instance-time";

const NOW = new Date("2026-09-12T20:30:00Z").getTime();

describe("event instance end times", () => {
  it("uses an explicit end when deciding whether a multi-day instance is past", () => {
    const instance = {
      starts_at: "2026-09-10T18:00:00Z",
      ends_at: "2026-09-13T18:00:00Z",
    };
    expect(effectiveInstanceEndMs(instance)).toBe(new Date(instance.ends_at).getTime());
    expect(isPastEventInstance(instance, NOW)).toBe(false);
  });

  it("falls back to start plus two hours for legacy instances", () => {
    const instance = { starts_at: "2026-09-12T18:00:00Z", ends_at: null };
    expect(effectiveInstanceEndMs(instance)).toBe(new Date("2026-09-12T20:00:00Z").getTime());
    expect(isPastEventInstance(instance, NOW)).toBe(true);
  });

  it("ignores an invalid end before the start and fails open for malformed dates", () => {
    expect(
      effectiveInstanceEndMs({
        starts_at: "2026-09-12T18:00:00Z",
        ends_at: "2026-09-12T17:00:00Z",
      }),
    ).toBe(new Date("2026-09-12T20:00:00Z").getTime());
    expect(isPastEventInstance({ starts_at: "not-a-date", ends_at: null }, NOW)).toBe(false);
  });
});
