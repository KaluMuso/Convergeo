import {
  ADMIN_BASE_URL,
  BASE_URL,
  path,
  requireVendorBaseUrl,
  str,
  urlOn,
  vendorOtp,
  vendorOtpReady,
} from "../fixtures/env";
import { resolveGate } from "../fixtures/gating";
import { loginVendorViaOtp } from "../fixtures/otp-login";
import { missingOutboundApproval } from "../fixtures/outbound-approval";
import { expectNoRawI18n } from "../fixtures/raw-i18n";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

test.use({
  serviceWorkers: "block",
  trace: "off",
  video: "off",
  screenshot: "off",
});

/**
 * Pilot journeys 3 + 4 (vendor and admin portals, separate origins).
 *
 * Vendor: same approved-vendor OTP gate as vendor-sell.spec.ts (which remains
 * the REQUIRED_STRICT owner of the confirm -> status-advances transition chain,
 * so this file does not repeat it and does not mutate the seeded order). This
 * file adds the read surfaces around it: orders inbox and payouts.
 *
 * Admin: no admin persona exists in the canonical seed or the hosted workflow
 * (and no admin preflight probe: staging-probe contract), so these legs run
 * only when a separately provisioned operator account is supplied:
 *   E2E_ADMIN_BASE_URL (explicit, distinct from the customer origin),
 *   E2E_ADMIN_TEST_EMAIL, E2E_ADMIN_TEST_PASSWORD.
 * Otherwise they skip with a founder-gated annotation. Never invented here.
 */
test.describe("pilot · vendor inbox and payouts", () => {
  test.describe.configure({ retries: 0 });

  // Playwright requires the destructuring pattern for the fixtures argument.
  // eslint-disable-next-line no-empty-pattern
  test.beforeEach(({}, testInfo) => {
    const missingApproval = missingOutboundApproval("otp", process.env, {
      persona: "vendor",
      recipientPhone: vendorOtp.testPhone,
    });
    if (!vendorOtpReady() || missingApproval.length) {
      const gate = resolveGate({
        kind: "OPTIONAL_GATE",
        journey: `pilot vendor portal reads (${testInfo.title})`,
        fixtures: [
          ...(!vendorOtpReady()
            ? [
                "E2E_VENDOR_TEST_OTP",
                "SMS_OTP_TRANSPORT",
                "WAHA_OTP_ENABLED",
                "STAGING_SMS_SANDBOX_ATTESTED",
                "STAGING_TEST_OTP_MAP_ATTESTED",
              ]
            : []),
          ...missingApproval,
        ],
      });
      testInfo.annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
    }
  });

  test("orders inbox lists the vendor's orders with machine-readable status", async ({ page }) => {
    const origin = requireVendorBaseUrl();
    await loginVendorViaOtp(page, { next: path("/orders") });
    const cards = page.getByTestId("vendor-order-card-link");
    await expect(cards.first()).toBeVisible({ timeout: 30_000 });
    await expect(cards.first()).toHaveAttribute("data-order-id", /.+/);
    await expect(cards.first()).toHaveAttribute(
      "data-order-status",
      /^(placed|confirmed|processing|ready|shipped|delivered|completed|cancelled)$/,
    );
    await expect(page.getByText(SEED.codOrder.productName).first()).toBeVisible();
    await expectNoRawI18n(page, "main");
    expect(origin).toBeTruthy();
  });

  test("payouts page loads the ledger-backed view without raw i18n", async ({ page }) => {
    const origin = requireVendorBaseUrl();
    await loginVendorViaOtp(page);
    await page.goto(urlOn(origin, "/payouts"));
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: /balances/i })).toBeVisible();
    await expectNoRawI18n(page, "main");
  });

  test.fixme("payouts page tells the vendor payouts are disabled for the pilot", async ({
    page,
  }) => {
    // FINDING: the API kill switch (services/api/app/services/payouts/gate.py,
    // PAYOUTS_ENABLED default off -> 503 payouts_disabled) has NO vendor-facing
    // message. apps/vendor/app/[locale]/payouts/_components/payouts-view.tsx
    // renders balances/history/statement and only a 24h "payouts paused after
    // MoMo number change" notice (payouts_blocked); nothing references
    // payouts_disabled and no i18n key mentions the pilot. Remove fixme once a
    // pilot-disabled notice exists and update the matcher below.
    const origin = requireVendorBaseUrl();
    await loginVendorViaOtp(page);
    await page.goto(urlOn(origin, "/payouts"));
    await expect(
      page.getByRole("status").filter({ hasText: /pilot|not yet available|disabled/i }),
    ).toBeVisible();
  });
});

function adminConfig(): { origin: string; email: string; password: string } | null {
  const configured = str("E2E_ADMIN_BASE_URL");
  const email = str("E2E_ADMIN_TEST_EMAIL");
  const password = process.env.E2E_ADMIN_TEST_PASSWORD ?? "";
  if (!configured || !email || !password) return null;
  try {
    const origin = new URL(configured).origin;
    if (origin === new URL(BASE_URL).origin || origin !== new URL(ADMIN_BASE_URL).origin) {
      return null;
    }
    return { origin, email, password };
  } catch {
    return null;
  }
}

test.describe("pilot · admin operator", () => {
  test.describe.configure({ retries: 0 });

  test("operator finds the order in order search and the KYC review page loads", async ({
    page,
  }, testInfo) => {
    const config = adminConfig();
    if (!config) {
      const gate = resolveGate({
        kind: "OPTIONAL_GATE",
        journey: "pilot admin operator (orders search, KYC queue)",
        fixtures: ["E2E_ADMIN_BASE_URL", "E2E_ADMIN_TEST_EMAIL", "E2E_ADMIN_TEST_PASSWORD"],
      });
      testInfo.annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }

    // Admin login is email + password (phone sign-in is disabled for admin).
    await page.goto(urlOn(config.origin, "/login"));
    await page.getByLabel(/email address/i).fill(config.email);
    await page.getByLabel(/^password/i).fill(config.password);
    await page.locator("form button[type='submit']").click();
    await expect(page).not.toHaveURL(/\/login/, { timeout: 30_000 });

    // Orders: operator search by vendor shows the seeded vendor's orders.
    await page.goto(urlOn(config.origin, "/orders"));
    await expect(page.getByRole("heading", { level: 1, name: /order operations/i })).toBeVisible();
    await page.getByLabel(/vendor slug or name/i).fill(SEED.vendor.slug);
    await page.getByRole("button", { name: /search orders/i }).click();
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    await expect(rows.first()).toContainText(SEED.vendor.slug);
    await expectNoRawI18n(page, "main");

    // KYC: the review queue page loads (rows or the honest empty state).
    await page.goto(urlOn(config.origin, "/kyc"));
    await expect(page.getByRole("heading", { level: 1, name: /kyc review queue/i })).toBeVisible();
    await expect(
      page
        .getByText(/no pending kyc submissions/i)
        .or(page.locator("table tbody tr").first())
        .first(),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/permission denied/i)).toHaveCount(0);
    await expectNoRawI18n(page, "main");
  });
});
