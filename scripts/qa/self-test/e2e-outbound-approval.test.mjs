import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  blockUnapprovedCheckoutWrites,
  guardApprovedOtpRequests,
  guardApprovedPaymentRequests,
  guardCodWithoutProvider,
  missingCodApproval,
  missingOutboundApproval,
} from "../../../e2e/fixtures/outbound-approval.ts";

const sandbox = {
  GITHUB_RUN_ID: "1234",
  GITHUB_RUN_ATTEMPT: "2",
  E2E_APPROVED_RUN_ID: "1234",
  E2E_APPROVED_RUN_ATTEMPT: "2",
  E2E_STAGING_SETUP: "true",
  E2E_STRICT_SHA: "true",
  E2E_EXPECT_SHA: "a".repeat(40),
  STAGING_SUPABASE_PROJECT_ID: "iyasmrmbcrvlfxpzescb",
  STAGING_SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
  STAGING_API_HOST: "api.staging.vergeo5.com",
  E2E_BASE_URL: "https://customer.staging.vergeo5.com",
  E2E_APPROVED_CUSTOMER_ORIGIN: "https://customer.staging.vergeo5.com",
  E2E_APPROVED_API_ORIGIN: "https://api.staging.vergeo5.com",
  LENCO_SANDBOX: "1",
  LENCO_ENV: "sandbox",
  LENCO_SANDBOX_SECRET_KEY: "synthetic-only",
  LENCO_SANDBOX_MOMO_NUMBER: "0970000001",
  E2E_APPROVED_MOMO_NUMBER: "0970000001",
  E2E_APPROVED_MOMO_RAIL: "mtn",
  E2E_MOMO_PROVIDER_APPROVED: "1",
  E2E_PAID_TICKET_PROVIDER_APPROVED: "1",
  E2E_OTP_RECIPIENT_APPROVED: "1",
  E2E_APPROVED_CUSTOMER_PHONE: "+260970000001",
  E2E_APPROVED_VENDOR_PHONE: "+260970000004",
};

function fakePage() {
  const state = {
    handler: null,
    pattern: null,
    registrations: 0,
    aborted: 0,
    continued: 0,
    fulfilled: 0,
    fetched: 0,
  };
  return {
    state,
    page: {
      route: async (pattern, handler) => {
        state.registrations++;
        state.pattern = pattern;
        state.handler = handler;
      },
    },
    request: async (
      url,
      body = { payer_number: "0970000001", rail: "mtn", method: "momo", phone: "+260970000001" },
      status = 200,
    ) => {
      assert.match(url, state.pattern);
      const route = {
        request: () => ({ method: () => "POST", url: () => url, postDataJSON: () => body }),
        abort: async () => {
          state.aborted++;
        },
        continue: async () => {
          state.continued++;
        },
        fetch: async (options) => {
          assert.deepEqual(options, { maxRedirects: 0 });
          state.fetched++;
          return { status: () => status };
        },
        fulfill: async ({ response }) => {
          assert.equal(response.status(), status);
          state.fulfilled++;
        },
      };
      await state.handler(route);
    },
  };
}

test("unapproved credentials cannot install a checkout or OTP route", async () => {
  const money = fakePage();
  await assert.rejects(
    guardApprovedPaymentRequests(money.page, "momo", {
      ...sandbox,
      E2E_MOMO_PROVIDER_APPROVED: "",
    }),
    /E2E_MOMO_PROVIDER_APPROVED/,
  );
  assert.equal(money.state.registrations, 0);
  const otp = fakePage();
  await assert.rejects(
    guardApprovedOtpRequests(otp.page, "customer", "+260970000001", {
      ...sandbox,
      E2E_OTP_RECIPIENT_APPROVED: "",
    }),
    /E2E_OTP_RECIPIENT_APPROVED/,
  );
  assert.equal(otp.state.registrations, 0);
});

test("approved sandbox scope rejects production project, API, and customer origins", async () => {
  assert.ok(
    missingOutboundApproval("momo", {
      ...sandbox,
      STAGING_SUPABASE_URL: "https://dpadrlxukcjbewpqympu.supabase.co",
    }).length,
  );
  assert.ok(
    missingOutboundApproval("momo", {
      ...sandbox,
      E2E_BASE_URL: "https://www.vergeo5.com",
      E2E_APPROVED_CUSTOMER_ORIGIN: "https://www.vergeo5.com",
    }).length,
  );
  assert.ok(
    missingOutboundApproval("momo", {
      ...sandbox,
      E2E_BASE_URL: "https://convergeo-customer-git-production-vergeo-projects.vercel.app",
      E2E_APPROVED_CUSTOMER_ORIGIN:
        "https://convergeo-customer-git-production-vergeo-projects.vercel.app",
    }).length,
  );
  assert.ok(
    missingOutboundApproval("paid-ticket", {
      ...sandbox,
      STAGING_API_HOST: "api.vergeo5.com",
      E2E_APPROVED_API_ORIGIN: "https://api.vergeo5.com",
    }).length,
  );
  const money = fakePage();
  await guardApprovedPaymentRequests(money.page, "momo", sandbox);
  await money.request("https://api.vergeo5.com/payments/retry");
  assert.equal(money.state.aborted, 1);
  assert.equal(money.state.continued, 0);
  await money.request("https://api.vergeo5.com/orders");
  assert.equal(money.state.aborted, 2);
  // Direct misrouting uses the same path matcher but fails origin validation.
  await money.request("https://api.vergeo5.com/payments/retry");
  assert.equal(money.state.aborted, 3);
  await money.request("https://api.staging.vergeo5.com/payments/retry");
  assert.equal(money.state.fulfilled, 1);
  const otp = fakePage();
  await guardApprovedOtpRequests(otp.page, "customer", "+260970000001", sandbox);
  await otp.request("https://dpadrlxukcjbewpqympu.supabase.co/auth/v1/otp");
  assert.equal(otp.state.aborted, 1);
  assert.equal(otp.state.continued, 0);
});

test("hosted workflow has no provider or recipient approval injection", () => {
  const workflow = readFileSync(
    new URL("../../../.github/workflows/e2e.yml", import.meta.url),
    "utf8",
  );
  for (const key of [
    "E2E_PAID_TICKET_PROVIDER_APPROVED",
    "E2E_MOMO_PROVIDER_APPROVED",
    "E2E_OTP_RECIPIENT_APPROVED",
    "E2E_APPROVED_RUN_ID",
    "E2E_APPROVED_CUSTOMER_PHONE",
    "E2E_APPROVED_VENDOR_PHONE",
    "E2E_APPROVED_MOMO_NUMBER",
  ]) {
    assert.doesNotMatch(workflow, new RegExp(`^\\s+${key}:`, "m"));
  }
});

test("actual OTP recipient, payer, rail, and card requests fail closed", async () => {
  const otp = fakePage();
  await guardApprovedOtpRequests(otp.page, "customer", "+260970000001", sandbox);
  await otp.request("https://iyasmrmbcrvlfxpzescb.supabase.co/auth/v1/otp", {
    phone: "+260970000002",
  });
  await otp.request("https://iyasmrmbcrvlfxpzescb.supabase.co/auth/v1/otp", null);
  assert.equal(otp.state.aborted, 2);
  assert.equal(otp.state.continued, 0);
  await otp.request("https://iyasmrmbcrvlfxpzescb.supabase.co/auth/v1/otp");
  assert.equal(otp.state.fulfilled, 1);

  const money = fakePage();
  await guardApprovedPaymentRequests(money.page, "momo", sandbox);
  await money.request("https://api.staging.vergeo5.com/orders", {
    payer_number: "0970000002",
    rail: "mtn",
    method: "momo",
  });
  await money.request("https://api.staging.vergeo5.com/orders", {
    payer_number: "0970000001",
    rail: "airtel",
    method: "momo",
  });
  await money.request("https://api.staging.vergeo5.com/payments/retry", {
    payer_number: "0970000002",
    rail: "mtn",
  });
  await money.request("https://api.staging.vergeo5.com/payments/card/session");
  await money.request("https://api.staging.vergeo5.com/payments/card/payment-1/session");
  await money.request("https://api.staging.vergeo5.com/payments/card/payment-1/verify");
  await money.request("https://api.staging.vergeo5.com/orders", null);
  assert.equal(money.state.aborted, 7);
  assert.equal(money.state.continued, 0);
  await money.request("https://api.staging.vergeo5.com/orders");
  assert.equal(money.state.fulfilled, 1);
});

test("COD permits only COD order placement and blocks provider branches", async () => {
  const cod = fakePage();
  await guardCodWithoutProvider(cod.page, "+260970000001", sandbox);
  await cod.request("https://api.staging.vergeo5.com/orders", { method: "cod" });
  await cod.request("https://api.vergeo5.com/orders", { method: "cod" });
  await cod.request("https://api.staging.vergeo5.com/orders", { method: "momo" });
  await cod.request("https://api.staging.vergeo5.com/payments/retry");
  await cod.request("https://api.staging.vergeo5.com/payments/card/session");
  await cod.request("https://api.staging.vergeo5.com/payments/card/payment-1/session");
  assert.equal(cod.state.fulfilled, 1);
  assert.equal(cod.state.aborted, 5);
  assert.ok(
    missingCodApproval("+260970000001", { ...sandbox, E2E_BASE_URL: "https://www.vergeo5.com" })
      .length,
  );
  const unapproved = fakePage();
  await assert.rejects(
    guardCodWithoutProvider(unapproved.page, "+260970000001", {
      ...sandbox,
      E2E_APPROVED_API_ORIGIN: "",
    }),
    /E2E_APPROVED_API_ORIGIN/,
  );
  assert.equal(unapproved.state.registrations, 0);
});

test("checkout mount writes require the actual staging API origin", async () => {
  const money = fakePage();
  await guardApprovedPaymentRequests(money.page, "momo", sandbox);
  await money.request("https://api.vergeo5.com/checkout/session", null);
  await money.request("https://api.vergeo5.com/checkout/steps/contact", { phone: "+260970000001" });
  assert.equal(money.state.aborted, 2);
  await money.request("https://api.staging.vergeo5.com/checkout/session", null);
  await money.request("https://api.staging.vergeo5.com/checkout/steps/contact", {
    phone: "+260970000001",
  });
  await money.request("https://api.staging.vergeo5.com/checkout/steps/payment", {
    method: "momo",
    rail: "mtn",
    payer_number: "0970000001",
  });
  assert.equal(money.state.fulfilled, 3);
  await money.request("https://api.staging.vergeo5.com/checkout/steps/payment", {
    method: "momo",
    rail: "airtel",
    payer_number: "0970000001",
  });
  await money.request("https://api.staging.vergeo5.com/checkout/steps/payment", null);
  assert.equal(money.state.aborted, 4);
  await money.request("https://api.staging.vergeo5.com/checkout/pay", {});
  assert.equal(money.state.aborted, 5);

  const cod = fakePage();
  await guardCodWithoutProvider(cod.page, "+260970000001", sandbox);
  await cod.request("https://api.vergeo5.com/checkout/session", null);
  assert.equal(cod.state.aborted, 1);
  await cod.request("https://api.staging.vergeo5.com/checkout/session", null);
  await cod.request("https://api.staging.vergeo5.com/checkout/steps/payment", { method: "cod" });
  assert.equal(cod.state.fulfilled, 2);
  await cod.request("https://api.staging.vergeo5.com/checkout/steps/payment", {
    method: "momo",
    rail: "mtn",
    payer_number: "0970000001",
  });
  assert.equal(cod.state.aborted, 2);
  await cod.request("https://api.staging.vergeo5.com/checkout/pay", {});
  assert.equal(cod.state.aborted, 3);
});

test("browse-safe mock branch blocks all checkout, OTP, and provider POSTs", async () => {
  const mock = fakePage();
  await blockUnapprovedCheckoutWrites(mock.page);
  for (const url of [
    "https://api.staging.vergeo5.com/checkout/session",
    "https://api.staging.vergeo5.com/checkout/steps/contact",
    "https://api.staging.vergeo5.com/orders",
    "https://api.staging.vergeo5.com/payments/retry",
    "https://iyasmrmbcrvlfxpzescb.supabase.co/auth/v1/otp",
  ])
    await mock.request(url, null);
  assert.equal(mock.state.aborted, 5);
  assert.equal(mock.state.fetched, 0);
});

test("ticket approval permits only the browser ticket picker, not a product or duplicate payment", async () => {
  const paid = fakePage();
  await guardApprovedPaymentRequests(paid.page, "paid-ticket", sandbox);
  await paid.request("https://api.staging.vergeo5.com/tickets/checkout", {});
  await paid.request("https://api.staging.vergeo5.com/orders");
  await paid.request("https://api.staging.vergeo5.com/payments/retry");
  await paid.request("https://api.staging.vergeo5.com/payments/card/session");
  assert.equal(paid.state.fulfilled, 1);
  assert.equal(paid.state.aborted, 3);
});

test("approved browser POSTs never follow a 307/308 to another host", async () => {
  const cases = [
    [
      (page) => guardApprovedPaymentRequests(page, "momo", sandbox),
      "https://api.staging.vergeo5.com/orders",
      undefined,
    ],
    [
      (page) => guardApprovedPaymentRequests(page, "paid-ticket", sandbox),
      "https://api.staging.vergeo5.com/tickets/checkout",
      {},
    ],
    [
      (page) => guardApprovedOtpRequests(page, "customer", "+260970000001", sandbox),
      "https://iyasmrmbcrvlfxpzescb.supabase.co/auth/v1/otp",
      undefined,
    ],
    [
      (page) => guardCodWithoutProvider(page, "+260970000001", sandbox),
      "https://api.staging.vergeo5.com/orders",
      { method: "cod" },
    ],
  ];
  for (const [install, url, body] of cases) {
    const network = fakePage();
    await install(network.page);
    await network.request(url, body, 307);
    await network.request(url, body, 308);
    assert.equal(network.state.fetched, 2);
    assert.equal(network.state.aborted, 2);
    assert.equal(network.state.fulfilled, 0);
    assert.equal(network.state.continued, 0);
  }
});

test("checkout approval precedes the first placement action", () => {
  const spec = readFileSync(
    new URL("../../../e2e/specs/shop-checkout-momo.spec.ts", import.meta.url),
    "utf8",
  );
  assert.ok(
    spec.indexOf('missingOutboundApproval("momo")') < spec.indexOf("completeCheckout(page"),
  );
  assert.ok(
    spec.indexOf('guardApprovedPaymentRequests(page, "momo")') <
      spec.indexOf("completeCheckout(page"),
  );
  const cod = readFileSync(new URL("../../../e2e/specs/shop-cod.spec.ts", import.meta.url), "utf8");
  assert.ok(
    cod.indexOf("missingCodApproval(customerOtp.testPhone)") < cod.indexOf("completeCheckout(page"),
  );
  assert.ok(
    cod.indexOf('guardApprovedOtpRequests(page, "customer"') < cod.indexOf("completeCheckout(page"),
  );
  assert.ok(cod.indexOf("guardCodWithoutProvider(page)") < cod.indexOf("completeCheckout(page"));
  const critical = readFileSync(
    new URL("../../../e2e/specs/critical-path.spec.ts", import.meta.url),
    "utf8",
  );
  assert.ok(
    critical.indexOf('guardApprovedPaymentRequests(page, "momo")') <
      critical.indexOf('await page.goto(path("/checkout"))'),
  );
  assert.ok(
    critical.indexOf("blockUnapprovedCheckoutWrites(page)") <
      critical.indexOf('await page.goto(path("/checkout"))'),
  );
});
