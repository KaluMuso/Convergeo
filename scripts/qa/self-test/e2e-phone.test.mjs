import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { after, describe, it } from "node:test";

import { nationalNumberFromE164 } from "../../../e2e/fixtures/phone.ts";

const originalFetch = globalThis.fetch;
let unexpectedNetworkCalls = 0;
globalThis.fetch = async () => {
  unexpectedNetworkCalls++;
  throw new Error("external I/O is forbidden in these helper tests");
};
after(() => {
  globalThis.fetch = originalFetch;
  assert.equal(unexpectedNetworkCalls, 0, "helper tests attempted external I/O");
});

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
  it("vendor helper gates before navigation; customer caller integration is a separate unit", () => {
    const vendor = readFileSync(path.join(REPO_ROOT, "e2e/fixtures/otp-login.ts"), "utf8");
    const guard = vendor.indexOf("if (!vendorOtpReady())");
    assert.ok(guard >= 0 && guard < vendor.indexOf("page.goto("));
  });

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

// Execute the allocated TS helpers through the repository's existing compiler,
// with explicit module substitutes. This exercises fixture behavior, not React
// rendering, Playwright/browser behavior, a hosted Auth service or delivery.
import ts from "typescript";
import vm from "node:vm";
import { SEED } from "../../../e2e/fixtures/seed.generated.ts";
import * as bypass from "../../../e2e/fixtures/portal-bypass.ts";
import { evaluatePhoneOtpSafety } from "../../ci/preflight-e2e-test-otp.mjs";

function loadTs(relative, modules, env = {}) {
  const source = readFileSync(path.join(REPO_ROOT, relative), "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const exports = {};
  vm.runInNewContext(
    code,
    {
      exports,
      URL,
      Promise,
      WeakMap,
      process: { env },
      require: (name) => {
        assert.ok(name in modules, `unexpected import ${name}`);
        return modules[name];
      },
    },
    { filename: relative },
  );
  return exports;
}
const SAFE_HELPER_ENV = {
  E2E_BASE_URL: "https://customer.example",
  E2E_VENDOR_BASE_URL: "https://vendor.example",
  E2E_VENDOR_TEST_OTP: "222222",
  E2E_CUSTOMER_TEST_OTP: "111111",
  SMS_OTP_TRANSPORT: "waha",
  WAHA_OTP_ENABLED: "true",
  STAGING_SMS_SANDBOX_ATTESTED: "true",
  STAGING_TEST_OTP_MAP_ATTESTED: "true",
};
function loadEnv(env) {
  return loadTs(
    "e2e/fixtures/env.ts",
    { "./portal-bypass": bypass, "./seed.generated": { SEED } },
    env,
  );
}
function loadLogin(env = SAFE_HELPER_ENV, change = {}) {
  const fixture = { ...loadEnv(env), ...change };
  const expectFake = (item) => ({
    toBeVisible: async () => assert.equal(item.visible, true),
    toHaveURL: async (expected) => assert.equal(item.current, expected),
  });
  return loadTs("e2e/fixtures/otp-login.ts", {
    "@playwright/test": { expect: expectFake },
    "./env": fixture,
    "./phone": { nationalNumberFromE164 },
  });
}
class FakePage {
  current = "about:blank";
  sends = 0;
  confirms = 0;
  typed = "";
  actions = [];
  outcome = "confirmed";
  interrupt = "";
  async goto(url) {
    this.actions.push("navigate");
    this.current = url;
  }
  getByRole(role, { name }) {
    const page = this;
    return {
      visible: true,
      first() {
        return this;
      },
      async fill(value) {
        page.actions.push("fill");
        if (typeof name === "string") page.typed = "";
        else assert.equal(value, "970000004");
      },
      async click() {
        if (role === "button") {
          page.sends++;
          page.current = "https://vendor.example/en/otp?phone=%2B260970000004";
          if (page.interrupt === "send") {
            page.interrupt = "";
            throw Error("raw-secret-marker");
          }
        } else if (page.interrupt === "entry") {
          page.interrupt = "";
          throw Error("raw-secret-marker");
        }
      },
    };
  }
  keyboard = {
    type: async (digit) => {
      this.actions.push("type");
      this.typed += digit;
      if (this.interrupt === "partial" && this.typed.length === 3) {
        this.interrupt = "";
        throw Error("raw-secret-marker");
      }
      if (this.typed.length === 6) {
        this.confirms++;
        if (this.outcome === "confirmed") this.current = "https://vendor.example/en/services";
        if (this.outcome === "wrong-origin") this.current = "https://other.example/en/services";
        if (this.interrupt === "verify") {
          this.interrupt = "";
          throw Error("raw-secret-marker");
        }
      }
    },
  };
  async waitForURL(predicate) {
    if (!predicate(new URL(this.current))) throw Error("raw-secret-marker");
  }
}

describe("executed phone fixture contracts", () => {
  it("invalid or customer-fallback portal origins fail safely before DOM actions", async () => {
    for (const origin of [
      "raw-secret-marker",
      "https://customer.example",
      "https://user:raw-secret-marker@vendor.example",
      "http://vendor.example",
    ]) {
      const page = new FakePage();
      const helper = loadLogin({ ...SAFE_HELPER_ENV, E2E_VENDOR_BASE_URL: origin });
      await assert.rejects(helper.loginVendorViaOtp(page), /valid distinct portal origin/);
      assert.deepEqual(page.actions, []);
      assert.equal(page.sends, 0);
    }
  });

  it("env and preflight transport/attestation gates agree and retain existing finance behavior", () => {
    for (const change of [
      {},
      { SMS_OTP_TRANSPORT: "" },
      { SMS_OTP_TRANSPORT: "disabled" },
      { SMS_OTP_TRANSPORT: "africas_talking" },
      { WAHA_OTP_ENABLED: "false" },
      { STAGING_SMS_SANDBOX_ATTESTED: "false" },
      { STAGING_TEST_OTP_MAP_ATTESTED: "" },
    ]) {
      const env = { ...SAFE_HELPER_ENV, ...change };
      const fixture = loadEnv(env);
      assert.equal(fixture.phoneOtpSafetyReady(), evaluatePhoneOtpSafety(env).verdict === "READY");
      assert.equal(fixture.vendorOtpReady(), fixture.phoneOtpSafetyReady());
      assert.equal(fixture.customerOtpReady(), fixture.phoneOtpSafetyReady());
      assert.equal(fixture.lencoSandboxReady(), false);
    }
    assert.equal(
      loadEnv({
        ...SAFE_HELPER_ENV,
        LENCO_SANDBOX: "true",
        LENCO_SANDBOX_SECRET_KEY: "synthetic",
      }).lencoSandboxReady(),
      true,
    );
  });
  it("disabled or invalid code declarations block before any DOM action", async () => {
    for (const change of [
      { SMS_OTP_TRANSPORT: "disabled" },
      { WAHA_OTP_ENABLED: "false" },
      { E2E_VENDOR_TEST_OTP: "12345" },
      { E2E_VENDOR_TEST_OTP: "" },
    ]) {
      const page = new FakePage();
      const helper = loadLogin({ ...SAFE_HELPER_ENV, ...change });
      await assert.rejects(helper.loginVendorViaOtp(page), /explicit attested transport/);
      assert.deepEqual(page.actions, []);
      assert.equal(page.sends, 0);
    }
  });
  it("invalid phone and unsafe or ungated destinations block before navigation", async () => {
    const page = new FakePage();
    const helper = loadLogin(SAFE_HELPER_ENV, {
      vendorOtp: { testPhone: "raw-secret-marker", staticCode: "222222" },
    });
    await assert.rejects(helper.loginVendorViaOtp(page), /fixture is invalid/);
    assert.deepEqual(page.actions, []);
    for (const next of [
      "https://other.example/en/services",
      "//other.example/en/services",
      "/en/health",
      "/en/login",
      "/en/reset-password",
      "/en/onboarding",
      "/en/file.txt",
      "/en/%2e%2e/services",
    ]) {
      const page = new FakePage();
      await assert.rejects(loadLogin().loginVendorViaOtp(page, { next }), /local protected route/);
      assert.deepEqual(page.actions, []);
    }
  });
  it("single-flight and repeated confirmed calls send and verify exactly once", async () => {
    const page = new FakePage();
    const helper = loadLogin();
    await Promise.all([helper.loginVendorViaOtp(page), helper.loginVendorViaOtp(page)]);
    await helper.loginVendorViaOtp(page);
    assert.equal(page.sends, 1);
    assert.equal(page.confirms, 1);
    assert.equal(page.typed, "222222");
  });
  it("delivery acceptance and invalid/expired verification never count as confirmation", async () => {
    for (const outcome of ["accepted", "invalid", "expired", "wrong-origin"]) {
      const page = new FakePage();
      page.outcome = outcome;
      const helper = loadLogin();
      await assert.rejects(helper.loginVendorViaOtp(page), /verification-started incomplete/);
      await assert.rejects(helper.loginVendorViaOtp(page), /verification-started incomplete/);
      assert.equal(page.sends, 1);
      assert.equal(page.confirms, 1);
    }
  });
  it("resume after an interrupted send or digit-entry preparation never resends", async () => {
    for (const phase of ["send", "entry", "partial"]) {
      const page = new FakePage();
      page.interrupt = phase;
      const helper = loadLogin();
      await assert.rejects(helper.loginVendorViaOtp(page), /incomplete/);
      await helper.loginVendorViaOtp(page);
      assert.equal(page.sends, 1);
      assert.equal(page.confirms, 1);
    }
  });
  it("resume after interrupted accepted verification awaits the route without repeating it", async () => {
    const page = new FakePage();
    page.interrupt = "verify";
    const helper = loadLogin();
    await assert.rejects(helper.loginVendorViaOtp(page), /verification-started incomplete/);
    await helper.loginVendorViaOtp(page);
    assert.equal(page.sends, 1);
    assert.equal(page.confirms, 1);
  });
  it("an uncertain send cannot silently trigger a new request on resume", async () => {
    const page = new FakePage();
    page.getByRole = (role, { name }) => ({
      visible: true,
      first() {
        return this;
      },
      fill: async () => {},
      click: async () => {
        if (role === "button") {
          page.sends++;
          throw Error("raw-secret-marker");
        }
      },
    });
    const helper = loadLogin();
    await assert.rejects(helper.loginVendorViaOtp(page), /request-started incomplete/);
    await assert.rejects(helper.loginVendorViaOtp(page), /request-started incomplete/);
    assert.equal(page.sends, 1);
  });
});
