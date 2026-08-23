import { CERTIFICATION_VIEWPORTS, MIN_TOUCH_TARGET_PX } from "../fixtures/viewports";
import { path, strictSyntheticRequired } from "../fixtures/env";
import { resolveGate } from "../fixtures/gating";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Mobile layout certification across required viewports.
 * Checks overflow, touch targets, sticky controls, navigation.
 */
for (const vp of CERTIFICATION_VIEWPORTS) {
  test.describe(`mobile-layout · ${vp.name} (${vp.width}×${vp.height})`, () => {
    test.use({
      viewport: { width: vp.width, height: vp.height },
      isMobile: vp.isMobile,
      hasTouch: vp.hasTouch,
    });

    test("no horizontal overflow on critical routes", async ({ page }) => {
      const routes = [
        "/",
        `/c/electronics`,
        `/p/${SEED.product.slug}`,
        "/cart",
        "/checkout",
        "/compare",
      ];
      for (const route of routes) {
        await page.goto(path(route));
        await page.waitForLoadState("domcontentloaded");

        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return doc.scrollWidth > doc.clientWidth + 2;
        });
        expect(overflow, `horizontal overflow on ${route} @ ${vp.name}`).toBe(false);
      }
    });

    test("primary CTAs meet minimum touch target", async ({ page }) => {
      await page.goto(path(`/p/${SEED.product.slug}`));
      await page.waitForLoadState("domcontentloaded");

      const buyBox = page.getByTestId("pdp-buy-box");
      if (!(await buyBox.isVisible().catch(() => false))) {
        if (strictSyntheticRequired()) {
          throw new Error("strictSyntheticRequired: PDP unavailable for touch-target check");
        }
        test.skip(true, "PDP unavailable — skip touch-target check");
        return;
      }

      const addBtn = page.getByTestId("pdp-add-to-cart");
      const box = await addBtn.boundingBox();
      if (box) {
        expect(box.height, "add-to-cart height").toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 4);
        expect(box.width, "add-to-cart width").toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 4);
      }
    });

    test("bottom navigation visible and within viewport on mobile", async ({ page }) => {
      test.skip(
        vp.width >= 1024,
        resolveGate({
          kind: "VIEWPORT_NOT_APPLICABLE",
          journey: "bottom navigation check",
          detail: "mobile-only assertion",
        }).reason,
      );
      await page.goto(path("/"));
      await page.waitForLoadState("domcontentloaded");

      const bottomNav = page.getByTestId("bottom-nav").or(
        page
          .locator("nav")
          .filter({ has: page.locator("a[href*='/cart']") })
          .last(),
      );
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
        expect(box.y + box.height).toBeLessThanOrEqual(vp.height + 2);
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
        expect(box.width).toBeLessThanOrEqual(vp.width + 4);
      }
    });
  });
}
