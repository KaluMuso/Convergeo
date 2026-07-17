import { describe, expect, it } from "vitest";

import { attendeeNamesComplete, cleanedAttendeeNames, resizeNames } from "./attendee-names";

describe("resizeNames", () => {
  it("pads with empty strings up to qty", () => {
    expect(resizeNames([], 3)).toEqual(["", "", ""]);
    expect(resizeNames(["Ada"], 3)).toEqual(["Ada", "", ""]);
  });

  it("truncates extras above qty", () => {
    expect(resizeNames(["Ada", "Ben", "Cy"], 2)).toEqual(["Ada", "Ben"]);
  });

  it("clamps a negative qty to empty", () => {
    expect(resizeNames(["Ada"], -1)).toEqual([]);
  });
});

describe("attendeeNamesComplete", () => {
  it("requires a non-blank name for every ticket", () => {
    expect(attendeeNamesComplete(["Ada", "Ben"], 2)).toBe(true);
    expect(attendeeNamesComplete(["Ada", ""], 2)).toBe(false);
    expect(attendeeNamesComplete(["Ada", "   "], 2)).toBe(false);
  });

  it("ignores extra names beyond qty", () => {
    expect(attendeeNamesComplete(["Ada", "Ben", "Cy"], 2)).toBe(true);
  });

  it("is false for a non-positive quantity", () => {
    expect(attendeeNamesComplete(["Ada"], 0)).toBe(false);
  });
});

describe("cleanedAttendeeNames", () => {
  it("trims and returns exactly qty entries", () => {
    expect(cleanedAttendeeNames(["  Ada  ", "Ben"], 2)).toEqual(["Ada", "Ben"]);
    expect(cleanedAttendeeNames(["Ada"], 2)).toEqual(["Ada", ""]);
  });
});
