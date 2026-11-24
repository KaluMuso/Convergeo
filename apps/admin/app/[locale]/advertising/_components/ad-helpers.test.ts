import { describe, expect, it } from "vitest";

import {
  fromLusakaInput,
  isEditable,
  isValidReason,
  isValidWindow,
  toLusakaInput,
} from "./ad-helpers";

describe("Africa/Lusaka schedule helpers", () => {
  it("shows a UTC instant as Lusaka wall-clock time (UTC+2) regardless of browser zone", () => {
    expect(toLusakaInput("2026-11-13T06:00:00.000Z")).toBe("2026-11-13T08:00");
    expect(toLusakaInput("2026-12-31T23:30:00Z")).toBe("2027-01-01T01:30");
    expect(toLusakaInput(null)).toBe("");
    expect(toLusakaInput("not a date")).toBe("");
  });

  it("parses a typed Lusaka time back to the UTC instant", () => {
    expect(fromLusakaInput("2026-11-13T08:00")).toBe("2026-11-13T06:00:00.000Z");
    expect(fromLusakaInput("")).toBeNull();
    expect(fromLusakaInput("13/11/2026 08:00")).toBeNull();
  });

  it("round-trips", () => {
    const iso = "2026-11-20T15:45:00.000Z";
    expect(fromLusakaInput(toLusakaInput(iso))).toBe(iso);
  });

  it("requires end after start", () => {
    expect(isValidWindow("2026-11-13T06:00:00Z", "2026-11-13T07:00:00Z")).toBe(true);
    expect(isValidWindow("2026-11-13T06:00:00Z", "2026-11-13T06:00:00Z")).toBe(false);
    expect(isValidWindow(null, "2026-11-13T06:00:00Z")).toBe(false);
  });

  it("locks ended placements and requires a removal reason", () => {
    expect(isEditable("ended")).toBe(false);
    expect(isEditable("paused")).toBe(true);
    expect(isValidReason("  ")).toBe(false);
    expect(isValidReason("Advertiser withdrew")).toBe(true);
  });
});
