import { describe, expect, it } from "vitest";

import { normaliseVendorId, pilotPosture, validatePilotAdd } from "./pilot";

const A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

describe("normaliseVendorId", () => {
  it("accepts a UUID and normalises case and whitespace", () => {
    expect(normaliseVendorId(`  ${A.toUpperCase()} `)).toBe(A);
  });

  it("rejects anything that is not a UUID", () => {
    expect(normaliseVendorId("")).toBeNull();
    expect(normaliseVendorId("shop-a")).toBeNull();
    expect(normaliseVendorId(`${A}x`)).toBeNull();
  });
});

describe("pilotPosture", () => {
  it("is off whenever the clips flag is off, whatever the allowlist says", () => {
    expect(pilotPosture({ clips_enabled: false, allowlist_enforced: true })).toBe("off");
    expect(pilotPosture({ clips_enabled: false, allowlist_enforced: false })).toBe("off");
  });

  it("distinguishes a running pilot from an ended one", () => {
    expect(pilotPosture({ clips_enabled: true, allowlist_enforced: true })).toBe("pilot");
    expect(pilotPosture({ clips_enabled: true, allowlist_enforced: false })).toBe("open");
  });
});

describe("validatePilotAdd", () => {
  it("passes a new, valid vendor", () => {
    expect(validatePilotAdd(A, "anchor", [], 200)).toEqual({ ok: true, vendorId: A });
  });

  it("explains each refusal with an i18n key", () => {
    expect(validatePilotAdd("nope", "", [], 200)).toEqual({
      ok: false,
      errorKey: "errors.invalidId",
    });
    expect(validatePilotAdd(A, "x".repeat(281), [], 200)).toEqual({
      ok: false,
      errorKey: "errors.noteTooLong",
    });
    expect(validatePilotAdd(A, "", [A], 200)).toEqual({
      ok: false,
      errorKey: "errors.alreadyListed",
    });
    expect(validatePilotAdd(A, "", ["b", "c"], 2)).toEqual({ ok: false, errorKey: "errors.full" });
  });
});
