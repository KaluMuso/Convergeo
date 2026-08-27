import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import { nationalNumberFromE164 } from "../../../e2e/fixtures/phone.ts";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

/**
 * RC-2 regression coverage (staging E2E run #52): auth-otp.spec.ts filled the
 * raw E.164 fixture phone into PhoneForm's national-number-only field, which
 * the app's own client-side normalizer then rejected before any OTP was ever
 * requested — a TEST_BUG, not a PhoneForm defect.
 */
describe("nationalNumberFromE164", () => {
  it("extracts the national number from a Zambian E.164 fixture phone", () => {
    assert.equal(nationalNumberFromE164("+260970000001"), "970000001");
  });

  it("accepts the '7' mobile prefix as well as '9'", () => {
    assert.equal(nationalNumberFromE164("+260771234567"), "771234567");
  });

  it("tolerates surrounding whitespace", () => {
    assert.equal(nationalNumberFromE164("  +260970000001  "), "970000001");
  });

  it("fails closed (throws) on a non-Zambian country code", () => {
    assert.throws(() => nationalNumberFromE164("+27970000001"));
  });

  it("fails closed (throws) on a national number that is too short", () => {
    assert.throws(() => nationalNumberFromE164("+26097000"));
  });

  it("fails closed (throws) on a national number that is too long", () => {
    assert.throws(() => nationalNumberFromE164("+2609700000011"));
  });

  it("fails closed (throws) on an already-national (no +260) number", () => {
    // The exact shape a caller must never pass — this is the function's job,
    // not the caller's, so a national-shaped input is a caller bug to catch
    // loudly rather than pass through unchanged.
    assert.throws(() => nationalNumberFromE164("970000001"));
  });

  it("fails closed (throws) on a mobile prefix other than 7 or 9", () => {
    assert.throws(() => nationalNumberFromE164("+260870000001"));
  });

  it("never silently returns a wrong-length string", () => {
    for (const bad of ["", "+260", "+2609", "not-a-phone", "+260abcdefghi"]) {
      assert.throws(() => nationalNumberFromE164(bad), `expected "${bad}" to throw`);
    }
  });
});

describe("OTP specs use the shared helper, not duplicated slice logic", () => {
  it("auth-otp.spec.ts fills the normalized national number, not the raw E.164 fixture", () => {
    const source = readFileSync(path.join(REPO_ROOT, "e2e/specs/auth-otp.spec.ts"), "utf8");
    assert.ok(
      source.includes("nationalNumberFromE164(customerOtp.testPhone)"),
      "auth-otp.spec.ts must fill nationalNumberFromE164(customerOtp.testPhone), not the raw E.164 phone",
    );
    assert.ok(
      !/phoneInput\.fill\(customerOtp\.testPhone\)/.test(source),
      "auth-otp.spec.ts must not reintroduce filling the raw E.164 fixture phone",
    );
  });

  it("otp-login.ts (vendor helper) uses the same helper instead of a magic slice(-9)", () => {
    const source = readFileSync(path.join(REPO_ROOT, "e2e/fixtures/otp-login.ts"), "utf8");
    assert.ok(
      source.includes("nationalNumberFromE164(vendorOtp.testPhone)"),
      "otp-login.ts must fill nationalNumberFromE164(vendorOtp.testPhone)",
    );
    assert.ok(
      !source.includes(".slice(-9)"),
      "otp-login.ts must not reintroduce the duplicated slice(-9) national-number logic",
    );
  });
});
