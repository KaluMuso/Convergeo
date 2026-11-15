import { strictSyntheticRequired } from "../fixtures/env";
import { expectNoRawI18n, watchI18nConsole } from "../fixtures/raw-i18n";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

test.use({ serviceWorkers: "block", viewport: { width: 360, height: 800 } });

/** packages/i18n LOCALES (en + the pilot's bem/nya/fr + zh). Kept literal on purpose:
 *  the e2e package is standalone; a drift here is caught by the matrix self-test. */
const SMOKE_LOCALES = ["en", "bem", "nya", "fr", "zh"] as const;

/**
 * Pilot journey 6: every locale renders home and the seeded PDP with no
 * unsubstituted ICU argument (`{distance}`), no printed message id, and no
 * next-intl failure in the browser console.
 */
for (const locale of SMOKE_LOCALES) {
  test.describe(`locale smoke · ${locale}`, () => {
    test(`${locale}: home renders without raw i18n`, async ({ page }) => {
      const i18nErrors = watchI18nConsole(page);
      const response = await page.goto(`/${locale}`);
      expect(response?.status() ?? 0).toBeLessThan(400);
      await expect(page.locator("html")).toHaveAttribute("lang", new RegExp(`^${locale}`, "i"));
      await expect(page.locator("main").first()).toBeVisible({ timeout: 30_000 });
      await expectNoRawI18n(page);
      expect(i18nErrors.messages).toEqual([]);
    });

    test(`${locale}: PDP renders without raw i18n`, async ({ page }) => {
      const i18nErrors = watchI18nConsole(page);
      const response = await page.goto(`/${locale}/p/${SEED.product.slug}`);
      expect(response?.status() ?? 0).toBeLessThan(500);
      const buyBox = page.getByTestId("pdp-buy-box");
      const loaded = await buyBox
        .waitFor({ state: "visible", timeout: 20_000 })
        .then(() => true)
        .catch(() => false);
      if (!loaded && strictSyntheticRequired()) {
        throw new Error(`strictSyntheticRequired: seeded PDP unavailable in ${locale}`);
      }
      if (!loaded) {
        test.info().annotations.push({
          type: "pdp-skip",
          description: "seeded PDP unavailable (local exploratory); scanning the fallback surface",
        });
      }
      await expect(page.locator("main").first()).toBeVisible();
      await expectNoRawI18n(page);
      expect(i18nErrors.messages).toEqual([]);
    });
  });
}
