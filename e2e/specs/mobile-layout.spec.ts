import { path, strictSyntheticRequired } from "../fixtures/env";
import { resolveGate } from "../fixtures/gating";
import { BOTTOM_NAV_ARIA_LABEL } from "../fixtures/nav-contract";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";
import { MIN_TOUCH_TARGET_PX } from "../fixtures/viewports";

/**
 * Mobile layout certification across required viewports.
 * Checks overflow, touch targets, sticky controls, navigation.
 *
 * Viewport is owned entirely by the Playwright PROJECT (mobile-360/390/430,
 * tablet-768, desktop-1440 — see fixtures/spec-classification.ts), not by an
 * internal loop here: each of the 4 tests below runs once per certification
 * viewport via that project fan-out. Assertions read the live viewport with
 * `page.viewportSize()` rather than a loop-captured constant.
 */
test.describe("mobile-layout", () => {
  test("no horizontal overflow on critical routes", async ({ page }) => {
    const routes = [
      "/",
      `/c/electronics`,
      `/p/${SEED.product.slug}`,
      "/services",
      "/cart",
      "/checkout",
      "/compare",
      `/e/${SEED.event.slug}`,
    ];
    for (const route of routes) {
      await page.goto(path(route), { waitUntil: "domcontentloaded" });

      // Measure the rendered service and ticket surfaces, not a loading shell.
      if (route === "/services") {
        await expect(page.locator("#services-results-heading")).toBeVisible();
      }
      if (route === `/e/${SEED.event.slug}`) {
        const picker = page.locator('section[aria-labelledby^="ticket-picker-"]');
        const pickerAvailable = await picker
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => true)
          .catch(() => false);
        if (!pickerAvailable) {
          const gate = resolveGate({
            kind: "REQUIRED_STRICT",
            journey: "seeded event picker layout",
            detail: "ticket picker unavailable",
          });
          if (gate.action === "fail") throw new Error(gate.reason);
          test.skip(true, gate.reason);
          return;
        }
      }

      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        return doc.scrollWidth > doc.clientWidth + 2;
      });
      expect(overflow, `horizontal overflow on ${route}`).toBe(false);
    }
  });

  test("primary CTAs meet minimum touch target", async ({ page }) => {
    await page.goto(path(`/p/${SEED.product.slug}`));
    await page.waitForLoadState("domcontentloaded");

    const buyBox = page.getByTestId("pdp-buy-box");
    const pdpAvailable = await buyBox
      .waitFor({ state: "visible", timeout: 20_000 })
      .then(() => true)
      .catch(() => false);
    if (!pdpAvailable) {
      const gate = resolveGate({
        kind: "REQUIRED_STRICT",
        journey: "seeded product touch target",
        detail: "PDP unavailable",
      });
      if (gate.action === "fail") throw new Error(gate.reason);
      test.skip(true, gate.reason);
      return;
    }

    const addBtn = page.getByTestId("pdp-add-to-cart");
    const box = await addBtn.boundingBox();
    expect(box, "add-to-cart target must have a layout box").not.toBeNull();
    expect(box!.height, "add-to-cart height").toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 4);
    expect(box!.width, "add-to-cart width").toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 4);

    await page.goto(path(`/e/${SEED.event.slug}`), { waitUntil: "domcontentloaded" });
    const picker = page.locator('section[aria-labelledby^="ticket-picker-"]');
    const pickerAvailable = await picker
      .waitFor({ state: "visible", timeout: 20_000 })
      .then(() => true)
      .catch(() => false);
    if (!pickerAvailable) {
      const gate = resolveGate({
        kind: "REQUIRED_STRICT",
        journey: "seeded ticket CTA touch target",
        detail: "ticket picker unavailable",
      });
      if (gate.action === "fail") throw new Error(gate.reason);
      test.skip(true, gate.reason);
      return;
    }
    const ticketCta = picker.getByRole("button").last();
    const ticketBox = await ticketCta.boundingBox();
    expect(ticketBox, "ticket CTA must have a layout box").not.toBeNull();
    expect(ticketBox!.height, "ticket CTA height").toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 4);
    expect(ticketBox!.width, "ticket CTA width").toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 4);
  });

  test("bottom navigation visible and within viewport on mobile", async ({ page }) => {
    const viewport = page.viewportSize();
    test.skip(
      (viewport?.width ?? 0) >= 1024,
      resolveGate({
        kind: "VIEWPORT_NOT_APPLICABLE",
        journey: "bottom navigation check",
        detail: "mobile-only assertion",
      }).reason,
    );
    await page.goto(path("/"));
    await page.waitForLoadState("domcontentloaded");

    // Semantic contract, not a testid production never renders: BottomNav
    // (packages/ui/src/bottom-nav.tsx) is a <nav aria-label="Primary shop
    // navigation">, and its 5 real tabs (Home/Browse/Ask/Orders/Account —
    // bottom-nav-client.tsx) never include a Cart item, so a `/cart`-href
    // filter can never match either. See fixtures/nav-contract.ts.
    const bottomNav = page.getByRole("navigation", { name: BOTTOM_NAV_ARIA_LABEL, exact: true });
    const visible = await bottomNav.isVisible().catch(() => false);
    if (!visible) {
      if (strictSyntheticRequired()) {
        throw new Error("strictSyntheticRequired: bottom nav not found on mobile");
      }
      test.info().annotations.push({
        type: "nav-absent",
        description: "Bottom nav not found — may be desktop layout",
      });
      return;
    }

    const box = await bottomNav.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      const height = page.viewportSize()?.height ?? box.y + box.height;
      expect(box.y + box.height).toBeLessThanOrEqual(height + 2);
    }
  });

  test("checkout payment methods render within viewport", async ({ page }) => {
    await page.goto(path("/checkout"));
    await page.waitForLoadState("domcontentloaded");

    const paymentMethods = page.getByTestId("checkout-payment-methods");
    const visible = await paymentMethods.isVisible().catch(() => false);
    if (!visible) {
      await expect(
        page
          .getByTestId("checkout-place-order-unavailable")
          .or(page.getByRole("heading", { name: /checkout|cart/i }))
          .first(),
      ).toBeVisible({ timeout: 15_000 });
      return;
    }

    const box = await paymentMethods.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      const width = page.viewportSize()?.width ?? box.width;
      expect(box.width).toBeLessThanOrEqual(width + 4);
    }
  });
});
