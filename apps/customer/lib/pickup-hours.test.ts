import { describe, expect, it } from "vitest";

import { formatPickupHours } from "./pickup-hours";

describe("formatPickupHours", () => {
  it("renders per-day {open, close} objects, never [object Object]", () => {
    const out = formatPickupHours(
      { tue: { open: "09:00", close: "17:00" }, mon: { open: "08:00", close: "16:30" } },
      "en",
      "Closed",
    );
    expect(out).toBe("Mon 08:00–16:30, Tue 09:00–17:00");
    expect(out).not.toContain("[object Object]");
  });

  it("uses the translated closed label and tolerates strings/arrays", () => {
    const out = formatPickupHours(
      { sun: { closed: true }, sat: "9-1", fri: [{ open: "08:00", close: "12:00" }] },
      "en",
      "Fermé",
    );
    expect(out).toBe("Fri 08:00–12:00, Sat 9-1, Sun Fermé");
  });

  it("is locale aware for weekday names", () => {
    expect(formatPickupHours({ mon: { open: "08:00", close: "16:00" } }, "fr", "Fermé")).toMatch(
      /^lun/i,
    );
  });

  it("falls back to a dash when empty", () => {
    expect(formatPickupHours({}, "en", "Closed")).toBe("—");
  });
});
