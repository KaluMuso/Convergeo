import { readFileSync } from "node:fs";

import { path } from "../fixtures/env";
import {
  FIXTURE_GROUP_ID,
  FIXTURE_ORDER_ID,
  FIXTURE_PAYMENT_ID,
  FORBIDDEN_SUCCESS_COPY,
  assertNoAccidentalRealMoney,
  cardVerifyFixture,
  installMockBuyerSession,
  mockCardVerify,
  mockPaymentRetry,
  mockPaymentStatus,
  paymentMockMode,
  statusFixture,
} from "../fixtures/payment-fixtures";
import { expect, test } from "../fixtures/test-base";

import type { Route } from "@playwright/test";

const checkoutMessages = JSON.parse(
  readFileSync(new URL("../../packages/i18n/messages/en/checkout.json", import.meta.url), "utf8"),
) as {
  checkout: {
    card: { successBody: string };
    pending: { confirmingBody: string };
  };
};

/**
 * VB-P07 / S6 / G4 — checkout honesty: pending/failed/unknown must never render
 * as paid/completed/successful without authoritative server confirmation.
 *
 * Default: deterministic mocked provider fixtures (CI-safe, no secrets).
 * Deployed sandbox: set `E2E_DEPLOYED_TARGET=1` + `LENCO_SANDBOX` to exercise
 * live initiation; honesty assertions below remain mock-driven so CI stays green.
 */
test.describe("checkout · false-success", () => {
  test.beforeEach(() => {
    assertNoAccidentalRealMoney();
    test.info().annotations.push({
      type: "mode",
      description: paymentMockMode()
        ? "payment-mock (deterministic CI fixtures)"
        : "deployed-target available — honesty cases still use fixtures; live pay is VE-P07",
    });
  });

  test("pending MoMo collection is never shown as paid or successful", async ({ page }) => {
    await installMockBuyerSession(page);
    await mockPaymentStatus(page, statusFixture({ status: "ussd_pushed", cod: false }));

    await page.goto(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));

    await expect(page.getByTestId("ussd-wait")).toBeVisible();
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expect(page.getByTestId("payment-cod")).toHaveCount(0);
    await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Approve payment" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Check your phone" })).toBeVisible();
  });

  test("failed collection stays failed with a useful retry — never paid", async ({ page }) => {
    await installMockBuyerSession(page);
    await mockPaymentStatus(page, statusFixture({ status: "failed", cod: false }));
    const retry = await mockPaymentRetry(page, {
      payment_id: FIXTURE_PAYMENT_ID,
      status: "ussd_pushed",
      order_count: 1,
    });

    await page.goto(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));

    await expect(page.getByTestId("payment-failed")).toBeVisible();
    await expect(page.getByTestId("ussd-wait")).toHaveCount(0);
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);

    const retryButton = page.getByTestId("payment-retry-button");
    await expect(retryButton).toBeVisible();
    await expect(retryButton).toBeEnabled();
    // Retry promises a fresh prompt — not that payment already succeeded.
    await expect(retryButton).toHaveText(/retry payment/i);
    await retryButton.click();
    await expect.poll(() => retry.calls).toBeGreaterThan(0);
    await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);
  });

  test("timed-out / expired collection fails honestly with retry", async ({ page }) => {
    await installMockBuyerSession(page);
    await mockPaymentStatus(page, statusFixture({ status: "expired", cod: false }));
    await mockPaymentRetry(page, {
      payment_id: FIXTURE_PAYMENT_ID,
      status: "ussd_pushed",
      order_count: 1,
    });

    await page.goto(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));

    await expect(page.getByTestId("payment-expired")).toBeVisible();
    await expect(page.getByRole("heading", { name: /payment timed out/i })).toBeVisible();
    await expect(page.getByTestId("payment-retry-button")).toBeVisible();
    await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);
  });

  test("unknown provider status stays waiting — never invents success", async ({ page }) => {
    await installMockBuyerSession(page);
    await mockPaymentStatus(page, statusFixture({ status: "provider_unknown_xyz", cod: false }));

    await page.goto(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));

    await expect(page.getByTestId("ussd-wait")).toBeVisible();
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);
  });

  test("refreshing a pending result does not convert it into success", async ({ page }) => {
    await installMockBuyerSession(page);
    let polls = 0;
    await mockPaymentStatus(page, () => {
      polls += 1;
      // Authoritative server evidence stays pending across reload.
      return statusFixture({ status: "initiated", cod: false });
    });

    await page.goto(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));
    await expect(page.getByTestId("ussd-wait")).toBeVisible();
    const pollsBefore = polls;

    await page.reload();
    await expect(page.getByTestId("ussd-wait")).toBeVisible();
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);
    expect(polls).toBeGreaterThan(pollsBefore);
  });

  test("MoMo provider success shows confirming — not a final paid claim", async ({ page }) => {
    // Keep the shared guard tied to the real English catalogue: it must catch
    // terminal success semantics while allowing the honest transitional copy.
    expect(checkoutMessages.checkout.card.successBody).toMatch(FORBIDDEN_SUCCESS_COPY);
    expect(checkoutMessages.checkout.pending.confirmingBody).not.toMatch(FORBIDDEN_SUCCESS_COPY);

    await installMockBuyerSession(page);
    await mockPaymentStatus(page, statusFixture({ status: "success", cod: false }));

    /**
     * Order-navigation isolation — deliberate, and scoped to THIS test.
     *
     * On a `success` poll the app correctly calls `router.replace` to
     * `/account/orders/{order_id}` (ussd-wait.tsx): the order page, not this
     * one, is where escrow/ledger state is authoritative. That destination is
     * out of contract here. This spec's subject is payment-outcome HONESTY —
     * that a provider success renders as "confirming", never as a final paid
     * claim. Real purchase/order integration is other journeys' job.
     *
     * Following the redirect would drag this assertion into Account
     * server-auth and order-data behaviour using FIXTURE_ORDER_ID, which the
     * canonical staging seed deliberately never creates (scripts/seed_staging.py
     * seeds no orders or payments), so the destination could only ever resolve
     * to an unauthenticated/not-found surface — Run #68 captured exactly that:
     * a final snapshot of the Customer "Sign in" page instead of the confirming
     * state. That is an artefact of the fixture, not a product defect, and it
     * must not be papered over by weakening Account authentication, enabling
     * NEXT_PUBLIC_E2E_MOCK_SESSION on deployed staging, adding a production
     * test bypass, changing Customer middleware, or suppressing the redirect in
     * application code. None of those happen here.
     *
     * Instead the navigation is observed and held at the network boundary —
     * the narrowest mechanism available — which both PROVES the app attempted
     * the correct destination and keeps the confirming surface available while
     * it is asserted. The held request is aborted only during cleanup. Route
     * interception covers the RSC fetch and any document-navigation fallback
     * alike.
     */
    const orderRoutePattern = "**/account/orders**";
    const orderNavigations: string[] = [];
    const heldNavigationSettlements = new Set<Promise<void>>();
    let releaseOrderNavigation!: () => void;
    const orderNavigationBarrier = new Promise<void>((resolve) => {
      releaseOrderNavigation = resolve;
    });
    const holdOrderNavigation = async (route: Route) => {
      let markSettled!: () => void;
      const settled = new Promise<void>((resolve) => {
        markSettled = resolve;
      });
      heldNavigationSettlements.add(settled);

      try {
        // Recording the exact request URL is also the test-controlled signal
        // that the application genuinely attempted its order hand-off.
        orderNavigations.push(route.request().url());
        await orderNavigationBarrier;
        await route.abort();
      } finally {
        markSettled();
        heldNavigationSettlements.delete(settled);
      }
    };

    // Register before loading the pending page so no order hand-off can race
    // past the observation boundary.
    await page.route(orderRoutePattern, holdOrderNavigation);

    try {
      await page.goto(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));

      // Wait until router.replace has reached the held network boundary. From
      // this point through the assertions below, the browser remains on the
      // real pending page and its inherently transient confirming surface.
      await expect.poll(() => orderNavigations.length, { timeout: 10_000 }).toBeGreaterThan(0);
      await expect(page).toHaveURL(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));

      const confirming = page.getByTestId("payment-confirming");
      await expect(confirming).toBeVisible({ timeout: 10_000 });
      await expect(confirming.getByText(/not a final paid confirmation/i).first()).toBeVisible();
      await expect(page.getByTestId("ussd-wait")).toHaveCount(0);
      await expect(page.getByTestId("payment-card-success")).toHaveCount(0);
      await expect(confirming.getByRole("heading", { name: /order confirmed/i })).toHaveCount(0);
      await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);

      // "Confirming" is a transition, not a terminal screen: the attempted
      // destinations must all target the exact locale-prefixed fixture order
      // path. A matching ID in a query string is not routing evidence.
      const expectedOrderPath = path(`/account/orders/${FIXTURE_ORDER_ID}`);
      expect(
        orderNavigations.every(
          (recordedUrl) => new URL(recordedUrl).pathname === expectedOrderPath,
        ),
      ).toBe(true);
    } finally {
      // Always release the barrier, even after a failed assertion. Removing
      // this test's handler prevents later requests from joining the hold;
      // every request already inside it is then aborted and allowed to settle.
      releaseOrderNavigation();
      await page.unroute(orderRoutePattern, holdOrderNavigation);
      await Promise.allSettled([...heldNavigationSettlements]);
    }
  });

  test("COD confirmation never uses MoMo/card prepaid success copy", async ({ page }) => {
    await installMockBuyerSession(page);
    await mockPaymentStatus(page, statusFixture({ status: "cod", cod: true, payment_id: null }));

    await page.goto(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));

    await expect(page.getByTestId("payment-cod")).toBeVisible();
    await expect(page.getByText(/pay on delivery/i)).toBeVisible();
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expect(page.getByTestId("ussd-wait")).toHaveCount(0);
    await expect(page.getByText(/you paid|paid upfront|payment is held/i)).toHaveCount(0);
    await expect(page.getByRole("link", { name: /view order/i })).toBeVisible();
  });

  test("card: provider success without order_confirmed stays pending (not paid)", async ({
    page,
  }) => {
    await installMockBuyerSession(page);
    const verify = await mockCardVerify(
      page,
      cardVerifyFixture({
        status: "success",
        order_confirmed: false,
        verified: false,
      }),
    );

    await page.goto(path(`/checkout/card/${FIXTURE_PAYMENT_ID}?status=success`));

    await expect(page.getByTestId("payment-card-pending")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("payment-card-success")).toHaveCount(0);
    // Card page may render i18n keys when namespaces are flat — assert via testid.
    await expect(page.getByTestId("payment-card-pending")).toContainText(
      /pending|still processing|waiting|checkout\.card\.pending/i,
    );
    // Status-check action — no false promise of completion (re-verify control).
    await expect(page.locator("main").getByRole("button").first()).toBeVisible();
    expect(verify.calls).toBeGreaterThan(0);
  });

  test("card: duplicate verify callback does not create a second success surface", async ({
    page,
  }) => {
    await installMockBuyerSession(page);
    const verify = await mockCardVerify(
      page,
      cardVerifyFixture({
        status: "success",
        order_confirmed: true,
        verified: true,
      }),
    );

    await page.goto(path(`/checkout/card/${FIXTURE_PAYMENT_ID}?status=success`));
    await expect(page.getByTestId("payment-card-success")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("payment-card-success")).toHaveCount(1);
    await expect(page.getByTestId("payment-card-pending")).toHaveCount(0);

    // Client retry of the same verify — still a single success representation.
    await page.goto(path(`/checkout/card/${FIXTURE_PAYMENT_ID}?status=success`));
    await expect(page.getByTestId("payment-card-success")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("payment-card-success")).toHaveCount(1);
    await expect(page.getByTestId("payment-card-pending")).toHaveCount(0);
    expect(verify.calls).toBeGreaterThanOrEqual(2);
  });

  test("card failed result offers retry without claiming success", async ({ page }) => {
    await installMockBuyerSession(page);
    await mockCardVerify(
      page,
      cardVerifyFixture({
        status: "failed",
        order_confirmed: false,
        retry_checkout: true,
      }),
    );

    await page.goto(path(`/checkout/card/${FIXTURE_PAYMENT_ID}?status=failed`));

    await expect(page.getByTestId("payment-card-failed")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page
        .getByRole("link", { name: /back to payment|retry/i })
        .or(page.locator('a[href*="/checkout"]').first()),
    ).toBeVisible();
    await expect(page.getByTestId("payment-card-success")).toHaveCount(0);
    await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);
  });
});
