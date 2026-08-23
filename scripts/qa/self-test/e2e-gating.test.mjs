import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import { resolveGatePolicy } from "../../../e2e/fixtures/gating-policy.ts";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const SPEC_DIR = path.join(REPO_ROOT, "e2e", "specs");

/**
 * PR C contract: in an integrated-staging certification run, a required journey
 * that cannot execute must FAIL — never vanish into a green tick as a skip.
 * Everything genuinely optional must keep skipping.
 */

describe("gating policy — REQUIRED_STRICT", () => {
  const required = { kind: "REQUIRED_STRICT", journey: "vendor authenticated sell flow" };

  it("integrated-staging: missing required fixture → deterministic FAIL", () => {
    const verdict = resolveGatePolicy({
      ...required,
      fixtures: ["E2E_VENDOR_TEST_OTP"],
      strict: true,
    });
    assert.equal(verdict.action, "fail");
    assert.equal(verdict.kind, "REQUIRED_STRICT");
    assert.match(verdict.reason, /cannot be skipped in integrated-staging/);
    assert.match(verdict.reason, /E2E_VENDOR_TEST_OTP/);
  });

  it("integrated-staging: unavailable required journey (no fixture) → FAIL", () => {
    const verdict = resolveGatePolicy({
      kind: "REQUIRED_STRICT",
      journey: "checkout place-order -> payment surface",
      detail: "no payment surface appeared within 30s of place-order",
      strict: true,
    });
    assert.equal(verdict.action, "fail");
    assert.match(verdict.reason, /no payment surface appeared/);
  });

  it("local / nightly: the convenient skip behaviour is preserved", () => {
    const verdict = resolveGatePolicy({
      ...required,
      fixtures: ["E2E_VENDOR_TEST_OTP"],
      strict: false,
    });
    assert.equal(verdict.action, "skip");
    assert.equal(verdict.kind, "REQUIRED_STRICT");
  });

  it("is deterministic — same input, same verdict", () => {
    const input = { ...required, fixtures: ["E2E_VENDOR_TEST_OTP"], strict: true };
    assert.deepEqual(resolveGatePolicy(input), resolveGatePolicy(input));
  });
});

describe("gating policy — optional kinds never escalate", () => {
  for (const kind of ["OPTIONAL_GATE", "FEATURE_DISABLED", "VIEWPORT_NOT_APPLICABLE"]) {
    it(`${kind} skips even in integrated-staging`, () => {
      const verdict = resolveGatePolicy({
        kind,
        journey: "some optional leg",
        fixtures: ["LENCO_SANDBOX"],
        strict: true,
      });
      assert.equal(verdict.action, "skip");
      assert.equal(verdict.kind, kind);
    });

    it(`${kind} also skips locally`, () => {
      assert.equal(
        resolveGatePolicy({ kind, journey: "some optional leg", strict: false }).action,
        "skip",
      );
    });
  }

  it("a missing OPTIONAL fixture is an allowed skip, not a failure", () => {
    const verdict = resolveGatePolicy({
      kind: "OPTIONAL_GATE",
      journey: "Lenco sandbox charge (F9b)",
      fixtures: ["LENCO_SANDBOX"],
      strict: true,
    });
    assert.equal(verdict.action, "skip");
    assert.match(verdict.reason, /OPTIONAL_GATE/);
  });
});

describe("gating policy — the four kinds are distinguishable", () => {
  it("every verdict reports the kind that produced it", () => {
    const kinds = [
      "REQUIRED_STRICT",
      "OPTIONAL_GATE",
      "FEATURE_DISABLED",
      "VIEWPORT_NOT_APPLICABLE",
    ];
    const seen = kinds.map((kind) => resolveGatePolicy({ kind, journey: "j", strict: true }).kind);
    assert.deepEqual(seen, kinds);
  });

  it("only REQUIRED_STRICT can ever produce a failure", () => {
    const failing = [
      "REQUIRED_STRICT",
      "OPTIONAL_GATE",
      "FEATURE_DISABLED",
      "VIEWPORT_NOT_APPLICABLE",
    ].filter((kind) => resolveGatePolicy({ kind, journey: "j", strict: true }).action === "fail");
    assert.deepEqual(failing, ["REQUIRED_STRICT"]);
  });
});

describe("gating policy — secret hygiene", () => {
  it("reasons carry fixture NAMES, and the caller's values are never echoed", () => {
    // The API takes names; nothing in the policy can reach a value.
    const verdict = resolveGatePolicy({
      kind: "REQUIRED_STRICT",
      journey: "customer OTP verification",
      fixtures: ["E2E_CUSTOMER_TEST_OTP"],
      strict: true,
    });
    assert.match(verdict.reason, /E2E_CUSTOMER_TEST_OTP/);
    for (const secretish of ["123456", "sbp_", "postgres://", "service_role"]) {
      assert.ok(!verdict.reason.includes(secretish));
    }
  });

  it("no spec passes a credential VALUE into a gate", () => {
    // Guards against someone "helpfully" interpolating the missing value.
    const forbidden =
      /resolveGate\(\{[^}]*(customerOtp\.staticCode|vendorOtp\.staticCode|scannerPin|ticketPin\(\)|process\.env)/s;
    for (const file of readdirSync(SPEC_DIR).filter((f) => f.endsWith(".spec.ts"))) {
      const source = readFileSync(path.join(SPEC_DIR, file), "utf8");
      assert.ok(
        !forbidden.test(source),
        `${file} passes a credential value into resolveGate — pass the NAME only`,
      );
    }
  });
});

describe("PR C — required sites cannot regress to an unconditional skip", () => {
  const REQUIRED_SITES = [
    ["auth-otp.spec.ts", "customer OTP verification"],
    ["vendor-sell.spec.ts", "vendor authenticated sell flow"],
    ["event-ticket.spec.ts", "event scanner verify + duplicate-reject"],
    ["critical-path.spec.ts", "checkout place-order -> payment surface"],
  ];

  for (const [file, journey] of REQUIRED_SITES) {
    it(`${file} gates "${journey}" as REQUIRED_STRICT and enforces it`, () => {
      const source = readFileSync(path.join(SPEC_DIR, file), "utf8");
      assert.ok(source.includes(journey), `${file} lost its REQUIRED_STRICT journey label`);
      assert.ok(
        source.includes('kind: "REQUIRED_STRICT"'),
        `${file} no longer declares a REQUIRED_STRICT gate`,
      );
      // Strip comments first: a commented-out enforceGate() is exactly the
      // silent-skip regression this assertion exists to catch.
      const code = source
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .split("\n")
        .filter((line) => !line.trim().startsWith("//"))
        .join("\n");
      assert.ok(
        code.includes("enforceGate("),
        `${file} declares a required gate but never enforces it — it would silently skip`,
      );
    });
  }

  it("optional legs are still classified, not escalated", () => {
    const optional = [
      ["shop-checkout-momo.spec.ts", "OPTIONAL_GATE"],
      ["clips-feed.spec.ts", "FEATURE_DISABLED"],
      ["clips-commerce.spec.ts", "FEATURE_DISABLED"],
      ["mobile-layout.spec.ts", "VIEWPORT_NOT_APPLICABLE"],
    ];
    for (const [file, kind] of optional) {
      const source = readFileSync(path.join(SPEC_DIR, file), "utf8");
      assert.ok(source.includes(`kind: "${kind}"`), `${file} lost its ${kind} classification`);
      const code = source
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .split("\n")
        .filter((line) => !line.trim().startsWith("//"))
        .join("\n");
      assert.ok(
        !code.includes("enforceGate("),
        `${file} must not enforce — ${kind} is never a failure`,
      );
    }
  });
});
