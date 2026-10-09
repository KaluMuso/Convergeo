import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  allowedEmailAcceptanceRequest,
  assertExpectedLoginLocation,
  emailAcceptanceConfig,
  isPasswordTokenRequest,
  STAGING_AUTH_ORIGIN,
} from "../../../e2e/email-acceptance/safety.ts";
import { runEmailAcceptance } from "../../ci/run-email-acceptance.mjs";

const ready = {
  E2E_EXPECT_SHA: "a".repeat(40),
  E2E_EMAIL_PROBE_SHA: "a".repeat(40),
  E2E_BASE_URL: "https://convergeo-customer-preview-vergeo-projects.vercel.app",
  E2E_VENDOR_BASE_URL:
    "https://convergeo-vendor-preview-vergeo-projects.vercel.app",
  E2E_CUSTOMER_EMAIL_PASSWORD: "synthetic-password-1",
  E2E_VENDOR_EMAIL_PASSWORD: "synthetic-password-2",
};

describe("email-only staging diagnostic", () => {
  it("binds fixed synthetic accounts and separate staging origins", () => {
    const config = emailAcceptanceConfig(ready);
    assert.match(config.customer.email, /^stg-rv-.*@staging\.vergeo5\.test$/);
    assert.match(config.vendor.email, /^stg-rv-.*@staging\.vergeo5\.test$/);
    assert.notEqual(config.customer.origin, config.vendor.origin);
  });

  it("rejects missing credentials, SHA, and non-staging origins before navigation", () => {
    for (const input of [
      { ...ready, E2E_EXPECT_SHA: "" },
      { ...ready, E2E_EMAIL_PROBE_SHA: "" },
      { ...ready, E2E_EMAIL_PROBE_SHA: "b".repeat(40) },
      { ...ready, E2E_CUSTOMER_EMAIL_PASSWORD: "" },
      { ...ready, E2E_VENDOR_EMAIL_PASSWORD: "" },
      { ...ready, E2E_BASE_URL: "https://www.vergeo5.com" },
      { ...ready, E2E_VENDOR_BASE_URL: "https://example.com" },
      { ...ready, E2E_VENDOR_BASE_URL: "https://attacker.vercel.app" },
      { ...ready, E2E_VENDOR_BASE_URL: ready.E2E_BASE_URL },
    ]) {
      assert.throws(() => emailAcceptanceConfig(input));
    }
  });

  it("allows only exact staging Auth password exchange and non-sensitive assets", () => {
    const portal = ready.E2E_BASE_URL;
    const allowed = (target, method = "GET", type = "fetch") =>
      allowedEmailAcceptanceRequest(new URL(target), method, type, portal);
    assert.equal(allowed(`${portal}/en/login`, "GET", "document"), true);
    assert.equal(
      allowed(
        `${STAGING_AUTH_ORIGIN}/auth/v1/token?grant_type=password`,
        "POST",
      ),
      true,
    );
    assert.equal(allowed(`${STAGING_AUTH_ORIGIN}/auth/v1/user`), true);
    assert.equal(
      allowed("https://fonts.gstatic.com/font.woff2", "GET", "font"),
      true,
    );
    assert.equal(
      allowed("https://res.cloudinary.com/demo/image.jpg", "GET", "image"),
      true,
    );
    assert.equal(
      allowedEmailAcceptanceRequest(
        new URL("https://res.cloudinary.com/demo/image.jpg"),
        "GET",
        "image",
        portal,
        false,
      ),
      false,
    );
    assert.equal(
      allowed("https://fonts.gstatic.com/script.js", "GET", "script"),
      false,
    );
    for (const target of [
      `${STAGING_AUTH_ORIGIN}/auth/v1/otp`,
      `${STAGING_AUTH_ORIGIN}/functions/v1/send-sms-otp`,
      "https://api.sandbox.lenco.co/access/v2/collections",
      "https://api.africastalking.com/version1/messaging",
      "https://api.staging.vergeo5.com/orders",
      "https://api.staging.vergeo5.com/internal/dispatch/tick",
      "https://dpadrlxukcjbewpqympu.supabase.co/auth/v1/token?grant_type=password",
      "https://www.vergeo5.com/en/login",
    ]) {
      assert.equal(allowed(target, "POST"), false, target);
    }
    assert.equal(
      allowed(
        `${STAGING_AUTH_ORIGIN}/auth/v1/token?grant_type=refresh_token`,
        "POST",
      ),
      false,
    );
  });

  it("rejects redirected login before either credential is filled", () => {
    assert.doesNotThrow(() =>
      assertExpectedLoginLocation(
        `${ready.E2E_BASE_URL}/en/login?next=%2Fen%2Faccount`,
        ready.E2E_BASE_URL,
      ),
    );
    assert.throws(() =>
      assertExpectedLoginLocation(
        "https://www.vergeo5.com/en/login",
        ready.E2E_BASE_URL,
      ),
    );
    assert.throws(() =>
      assertExpectedLoginLocation(
        `${ready.E2E_BASE_URL}/en/otp`,
        ready.E2E_BASE_URL,
      ),
    );
  });

  it("recognizes only password token requests for the intercepted dummy probe", () => {
    assert.equal(
      isPasswordTokenRequest(
        new URL(`${STAGING_AUTH_ORIGIN}/auth/v1/token?grant_type=password`),
        "POST",
      ),
      true,
    );
    assert.equal(
      isPasswordTokenRequest(
        new URL(`${STAGING_AUTH_ORIGIN}/auth/v1/otp`),
        "POST",
      ),
      false,
    );
  });

  it("refuses missing or wrong-SHA portal proof without launching Playwright", async () => {
    for (const outcome of [
      null,
      { verdict: "FAIL" },
      { verdict: "PASS", shaVerified: false },
    ]) {
      let launched = 0;
      await assert.rejects(
        runEmailAcceptance(ready, {
          probe: async () => outcome,
          execute: async () => {
            launched += 1;
            return 0;
          },
        }),
        /strict staging SHA probe failed/,
      );
      assert.equal(launched, 0);
    }
  });

  it("launches only after both strict portal probes pass", async () => {
    const portals = [];
    let launched = 0;
    const exitCode = await runEmailAcceptance(ready, {
      probe: async (env, { portal }) => {
        assert.equal(env.E2E_STRICT_SHA, "true");
        portals.push(portal);
        return { verdict: "PASS", shaVerified: true, shaSkipped: false };
      },
      execute: async (env) => {
        launched += 1;
        assert.equal(env.E2E_EMAIL_PROBE_SHA, ready.E2E_EXPECT_SHA);
        return 0;
      },
    });
    assert.deepEqual(portals, ["customer", "vendor"]);
    assert.equal(launched, 1);
    assert.equal(exitCode, 0);
  });
});
