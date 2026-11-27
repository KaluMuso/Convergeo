import { describe, expect, it } from "vitest";

import {
  ARCHETYPES,
  isBespoke,
  parseArchetype,
  parseAvailability,
  parseSchedule,
  parseStaff,
  vibeStyle,
} from "./archetypes";

describe("archetypes", () => {
  it("parses known archetypes and falls back to professional", () => {
    for (const key of ARCHETYPES) expect(parseArchetype(key)).toBe(key);
    expect(parseArchetype("castle")).toBe("professional");
    expect(parseArchetype(undefined)).toBe("professional");
    expect(parseArchetype(7)).toBe("professional");
  });

  it("ships bespoke layouts for four archetypes; the rest are generic", () => {
    const bespoke = ARCHETYPES.filter(isBespoke);
    expect(bespoke).toEqual(["accommodation", "appointment", "membership", "rental"]);
  });

  it("builds theme-following vibe variables from a packages/ui hue", () => {
    const style = vibeStyle("accommodation") as Record<string, string>;
    expect(style["--vibe"]).toMatch(/^#/);
    expect(style["--vibe-tint"]).toContain("var(--surface)");
  });

  it("defaults availability and tolerates garbage", () => {
    expect(parseAvailability({})).toBe("available");
    expect(parseAvailability({ availability: "limited" })).toBe("limited");
    expect(parseAvailability({ availability: "maybe" })).toBe("available");
  });

  it("sorts the class schedule and drops invalid rows", () => {
    const rows = parseSchedule({
      class_schedule: [
        { day: 2, start: "18:00", title: "Yoga" },
        { day: 1, start: "07:00", title: "Spin", capacity: 20, duration_min: 45 },
        { day: 9, start: "07:00", title: "Bad day" },
        { day: 1, start: "06:00", title: "Boxing" },
        { day: 1, title: "No start" },
      ],
    });
    expect(rows.map((r) => r.title)).toEqual(["Boxing", "Spin", "Yoga"]);
    expect(rows[1]?.capacity).toBe(20);
    expect(parseSchedule({ class_schedule: "x" })).toEqual([]);
  });

  it("parses the staff roster", () => {
    expect(parseStaff({ staff: [{ name: "Mwila", role: "Barber" }, { role: "x" }, 3] })).toEqual([
      { name: "Mwila", role: "Barber" },
    ]);
  });
});
