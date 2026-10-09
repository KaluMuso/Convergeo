import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  emailAcceptanceConfig,
  forbiddenEmailAcceptanceRequest,
} from "../../../e2e/email-acceptance/safety.ts";

const ready = {
  E2E_EXPECT_SHA: "a".repeat(40),
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

  it("forbids OTP, providers, orders, and dispatch while allowing password auth", () => {
    for (const target of [
      "https://staging.supabase.co/auth/v1/otp",
      "https://staging.supabase.co/functions/v1/send-sms-otp",
      "https://api.sandbox.lenco.co/access/v2/collections",
      "https://api.africastalking.com/version1/messaging",
      "https://api.staging.vergeo5.com/orders",
      "https://api.staging.vergeo5.com/internal/dispatch/tick",
    ]) {
      assert.equal(
        forbiddenEmailAcceptanceRequest(new URL(target)),
        true,
        target,
      );
    }
    assert.equal(
      forbiddenEmailAcceptanceRequest(
        new URL("https://staging.supabase.co/auth/v1/token"),
      ),
      false,
    );
  });
});
