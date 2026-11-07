import { describe, expect, it } from "vitest";

import {
  formatVariantLabel,
  initialSelection,
  missingGroups,
  resolveVariant,
  selectValue,
  selectedOptionPairs,
  valueAvailability,
  type VariantOptionGroup,
} from "./variant-selection";

import { GROUPS, VARIANTS, variant } from "./variant-fixtures";

describe("valueAvailability", () => {
  it("treats every value with some in-stock variant as available before any pick", () => {
    for (const value of ["red", "blue"]) {
      expect(valueAvailability(GROUPS, VARIANTS, {}, "g-colour", value)).toBe("available");
    }
    expect(valueAvailability(GROUPS, VARIANTS, {}, "g-size", "m")).toBe("available");
  });

  it("marks combinations that exist only out of stock as sold out", () => {
    expect(valueAvailability(GROUPS, VARIANTS, { "g-colour": "red" }, "g-size", "m")).toBe(
      "soldOut",
    );
  });

  it("marks combinations the vendor does not offer as unavailable", () => {
    expect(valueAvailability(GROUPS, VARIANTS, { "g-colour": "red" }, "g-size", "l")).toBe(
      "unavailable",
    );
    expect(valueAvailability(GROUPS, VARIANTS, { "g-colour": "blue" }, "g-size", "s")).toBe(
      "unavailable",
    );
  });

  it("judges a value against the other groups only, so switching within a group works", () => {
    const picked = { "g-colour": "red", "g-size": "s" };
    expect(valueAvailability(GROUPS, VARIANTS, picked, "g-colour", "blue")).toBe("unavailable");
    expect(valueAvailability(GROUPS, VARIANTS, picked, "g-size", "m")).toBe("soldOut");
    expect(valueAvailability(GROUPS, VARIANTS, { "g-size": "m" }, "g-colour", "blue")).toBe(
      "available",
    );
  });
});

describe("resolveVariant / missingGroups", () => {
  it("resolves only when every group is picked", () => {
    expect(resolveVariant(GROUPS, VARIANTS, { "g-colour": "blue" })).toBeNull();
    expect(resolveVariant(GROUPS, VARIANTS, { "g-colour": "blue", "g-size": "m" })?.id).toBe(
      "blue-m",
    );
    expect(missingGroups(GROUPS, { "g-colour": "blue" }).map((group) => group.name)).toEqual([
      "Size",
    ]);
  });

  it("returns null for a complete but unoffered combination", () => {
    expect(resolveVariant(GROUPS, VARIANTS, { "g-colour": "red", "g-size": "l" })).toBeNull();
  });
});

describe("selectValue", () => {
  it("clears a pick in another group that no longer forms an offered combination", () => {
    const next = selectValue(GROUPS, VARIANTS, { "g-size": "s" }, "g-colour", "blue");
    expect(next).toEqual({ "g-colour": "blue" });
  });

  it("keeps compatible picks", () => {
    const next = selectValue(GROUPS, VARIANTS, { "g-size": "m" }, "g-colour", "blue");
    expect(next).toEqual({ "g-colour": "blue", "g-size": "m" });
  });
});

describe("initialSelection / labels", () => {
  it("preselects only single-choice groups", () => {
    const single: VariantOptionGroup[] = [
      { id: "g", name: "Colour", display: "pill", values: [{ id: "x", label: "Black", swatchHex: null }] },
    ];
    expect(initialSelection(single, [variant("v", ["x"])])).toEqual({ g: "x" });
    expect(initialSelection(GROUPS, VARIANTS)).toEqual({});
  });

  it("formats the chosen options with a localized template", () => {
    const pairs = selectedOptionPairs(GROUPS, { "g-colour": "red", "g-size": "s" });
    expect(formatVariantLabel(pairs, "{group}: {value}", " · ")).toBe("Colour: Red · Size: S");
  });
});
