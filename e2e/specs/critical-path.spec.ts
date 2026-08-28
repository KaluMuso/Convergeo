import { clickAddToCartAndAwaitOutcome } from "../fixtures/add-to-cart";
import {
  BASE_URL,
  LOCALE,
  customerOtpReady,
  flag,
  lencoSandboxReady,
  path,
  strictSyntheticRequired,
} from "../fixtures/env";
import { enforceGate, resolveGate } from "../fixtures/gating";
import { completeSandboxMomoPush, sandboxEnabled } from "../fixtures/lenco";
import {
  FIXTURE_GROUP_ID,
  assertNoAccidentalRealMoney,
  installMockBuyerSession,
  mockPaymentStatus,
  paymentMockMode,
  statusFixture,
} from "../fixtures/payment-fixtures";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * VE-P07 / G16 / S7 — highest-value browse-safe critical path.
 *
 * Credential-free (CI mock): locale home → browse/search → (optional PDP/cart)
 * → checkout shell or fixture confirmation matching authoritative mock status.
 * Deployed sandbox: continues through MoMo when `LENCO_SANDBOX` + OTP/session
 * env are present. Never enables production real-money rails.
 */
test.describe("critical-path", () => {
  test("browse → cart → checkout honesty matches backend mode", async ({ page }) => {
    assertNoAccidentalRealMoney();
    test.info().annotations.push({
      type: "mode",
      description: paymentMockMode()
        ? "payment-mock / browse-safe CI"
        : "deployed-target (sandbox pay gated on LENCO_SANDBOX)",
    });
    test.info().annotations.push({
      type: "env-guard",
      description: `BASE_URL host checked; LENCO_SANDBOX=${lencoSandboxReady() ? "ready" : "absent"}; mock=${paymentMockMode()}`,
    });

    // 1. Locale-prefixed customer app.
    await page.goto(path("/"));
    await expect(page).toHaveURL(new RegExp(`/${LOCALE}(/|$)`));
    await expect(
      page
        .getByTestId("home-hero-brand")
        .or(page.getByTestId("home-hero-band"))
        .or(page.getByRole("link", { name: /vergeo/i }))
        .first(),
    ).toBeVisible({ timeout: 30_000 });

    // 2. Browse categories or search (honest empty/unavailable is success).
    await page.goto(path("/c/electronics"));
    const browseSurface = page
      .getByTestId("listing-grid")
      .or(page.getByTestId("plp-empty"))
      .or(page.getByTestId("plp-unavailable"))
      .or(page.getByTestId("plp-results-count"))
      .or(page.getByRole("heading", { name: /electronics|categor|browse|results/i }));
    const plpReady = await browseSurface
      .first()
      .waitFor({ state: "visible", timeout: 20_000 })
      .then(() => true)
      .catch(() => false);

    if (!plpReady) {
      await page.goto(path(`/search?q=${encodeURIComponent(SEED.searchTerm)}`));
      await expect(
        page
          .getByTestId("search-results-list")
          .or(page.getByTestId("search-unavailable"))
          .or(page.getByTestId("search-invalid-query"))
          .or(page.getByTestId("search-query-summary"))
          .or(page.getByRole("search"))
          .first(),
      ).toBeVisible({ timeout: 30_000 });
    }

    // 3. Open a PDP fixture (seed slug — non-demo when inventory exists).
    await page.goto(path(`/p/${SEED.product.slug}`));
    const buyBox = page.getByTestId("pdp-buy-box");
    // E2E run #52 (RC-5): an immediate isVisible() sampled the DOM before the
    // PDP finished rendering, misread a genuinely-present buy box as absent,
    // and silently fell through to the payment-mock confirmation branch below
    // — passing without ever exercising a real add-to-cart/cart leg. Strict
    // mode now waits (bounded, not sleep) for the required synthetic PDP;
    // local browse-safe mode keeps the instant honest-fallback read.
    const pdpAvailable = strictSyntheticRequired()
      ? await buyBox
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => true)
          .catch(() => false)
      : await buyBox.isVisible().catch(() => false);

    if (!pdpAvailable) {
      if (strictSyntheticRequired()) {
        throw new Error(
          `strictSyntheticRequired: seeded PDP ${SEED.product.slug} unavailable — the critical-path journey ` +
            "requires the real add-to-cart/cart/checkout leg and must not fall through to payment-mock " +
            "confirmation as a substitute",
        );
      }
      test.info().annotations.push({
        type: "inventory",
        description: `PDP ${SEED.product.slug} unavailable on this target (empty/demo-excluded catalogue). Browse legs asserted; ATC/checkout continue via payment-mock confirmation.`,
      });
    } else {
      await expect(page.getByTestId("pdp-price")).toBeVisible();

      // 4. Add to cart.
      await clickAddToCartAndAwaitOutcome(page, test.info(), { timeout: 20_000 });

      // 5. Reach cart + checkout.
      await page.goto(path("/cart"));
      await expect(page.getByTestId("cart-page")).toBeVisible();
      await page.goto(path("/checkout"));
      await expect(
        page
          .getByRole("heading", { name: /checkout|payment|delivery|contact/i })
          .or(page.getByText(/sign in|phone|loading/i))
          .first(),
      ).toBeVisible({ timeout: 30_000 });
    }

    // 6–7. Payment branch appropriate to environment — UI must match authoritative state.
    if (paymentMockMode()) {
      // Browse-safe / payments-disabled / invite beta: prove confirmation UI tracks
      // the mock status API (COD placed ≠ MoMo paid).
      await installMockBuyerSession(page);
      await mockPaymentStatus(page, statusFixture({ status: "cod", cod: true, payment_id: null }));
      await page.goto(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));
      await expect(page.getByTestId("payment-cod")).toBeVisible();
      await expect(page.getByText(/pay on delivery/i)).toBeVisible();
      await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
      await expect(page.getByText(/you paid|paid upfront/i)).toHaveCount(0);
      return;
    }

    // Deployed-target sandbox pay (F9b) — requires live session + Lenco sandbox.
    if (!sandboxEnabled() || !customerOtpReady()) {
      // OPTIONAL: real sandbox money is a founder gate (F9b). Never escalated,
      // even in certification — browse/cart were asserted above.
      const gate = resolveGate({
        kind: "OPTIONAL_GATE",
        journey: "deployed sandbox MoMo settle (F9b)",
        fixtures: ["LENCO_SANDBOX", "E2E_CUSTOMER_TEST_OTP"],
      });
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }

    if (!pdpAvailable) {
      const gate = resolveGate({
        kind: "OPTIONAL_GATE",
        journey: "sandbox settle",
        detail: "no buyable PDP on the deployed target",
      });
      test.skip(true, gate.reason);
      return;
    }

    // Continue checkout → MoMo when the place-order path is wired on the target.
    await page.goto(path("/checkout"));
    const momo = page.locator('[name="payment-method"][value="momo"]');
    if (await momo.count()) {
      await momo
        .first()
        .check()
        .catch(async () => {
          await page
            .getByRole("radio", { name: /mobile money|momo/i })
            .first()
            .click();
        });
    }
    await page
      .getByRole("button", { name: /pay|place order|checkout/i })
      .first()
      .click()
      .catch(() => {
        /* place-order may still be shell-incomplete on some SHAs */
      });

    const pendingOrWait = page
      .getByTestId("ussd-wait")
      .or(page.getByTestId("payment-confirming"))
      .or(page.getByTestId("payment-cod"));
    const reachedPay = await pendingOrWait
      .first()
      .waitFor({ state: "visible", timeout: 30_000 })
      .then(() => true)
      .catch(() => false);

    if (!reachedPay) {
      // Reached only when the Lenco sandbox leg is ACTIVE (see the F9b gate
      // above), so by this point the pay path is supposed to work. Skipping
      // here disguised a real product failure as an absent optional gate.
      const gate = resolveGate({
        kind: "REQUIRED_STRICT",
        journey: "checkout place-order -> payment surface",
        detail: "no payment surface appeared within 30s of place-order",
      });
      enforceGate(gate);
      test.info().annotations.push({ type: "gap", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }

    await completeSandboxMomoPush(page);
    // Authoritative success is order_confirmed / escrow — confirming or orders page.
    await expect(
      page
        .getByTestId("payment-confirming")
        .or(page.getByTestId("payment-card-success"))
        .or(page.getByRole("heading", { name: /order|confirming/i }))
        .first(),
    ).toBeVisible({ timeout: 90_000 });
  });

  test("refuses production real-money configuration in the test runner", async () => {
    // Meta-guard: the suite itself must not be pointed at live Lenco.
    expect(() => assertNoAccidentalRealMoney()).not.toThrow();
    expect(flag("LENCO_LIVE")).toBe(false);
    expect(String(process.env.LENCO_ENV ?? "").toLowerCase()).not.toMatch(/^(live|production)$/);
    // Document the target for artifacts without printing secrets.
    test.info().annotations.push({
      type: "target",
      description: `E2E_BASE_URL host=${safeHost(BASE_URL)}; sandboxReady=${lencoSandboxReady()}`,
    });
  });
});

function safeHost(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return "invalid-url";
  }
}
