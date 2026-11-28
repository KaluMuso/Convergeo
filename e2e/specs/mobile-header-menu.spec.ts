import { path } from "../fixtures/env";
import { expect, test } from "../fixtures/test-base";
import { MIN_TOUCH_TARGET_PX } from "../fixtures/viewports";

/** Customer shop header + mobile mega-menu drawer at the 360px certification width. */
test.use({ viewport: { width: 360, height: 800 } });

const phoneMenuButton = (page: import("@playwright/test").Page) =>
  page
    .getByRole("navigation", { name: "Shop navigation", exact: true })
    .getByRole("button", { name: "Menu", exact: true });

test.describe("mobile header menu @ 360px", () => {
  test("header row does not overflow horizontally", async ({ page }) => {
    await page.goto(path("/"), { waitUntil: "domcontentloaded" });
    const header = page.getByTestId("shop-header");
    await expect(header).toBeVisible();

    const overflow = await page.evaluate(() => {
      const doc = document.documentElement;
      return doc.scrollWidth > doc.clientWidth + 2;
    });
    expect(overflow, "shop home horizontal overflow with header").toBe(false);
  });

  test("menu opener and drawer controls meet touch-target minimum", async ({ page }) => {
    await page.goto(path("/"), { waitUntil: "domcontentloaded" });
    const menuButton = phoneMenuButton(page);
    await expect(menuButton).toBeVisible();
    const openerBox = await menuButton.boundingBox();
    expect(openerBox).not.toBeNull();
    expect(openerBox!.height).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 2);
    expect(openerBox!.width).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 2);

    await menuButton.click();
    const dialog = page.getByRole("dialog", { name: "Main menu" });
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    const close = page.getByRole("button", { name: "Close menu" });
    const closeBox = await close.boundingBox();
    expect(closeBox).not.toBeNull();
    expect(closeBox!.height).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 2);
    expect(closeBox!.width).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET_PX - 2);

    const overflowWithDrawer = await page.evaluate(() => {
      const doc = document.documentElement;
      return doc.scrollWidth > doc.clientWidth + 2;
    });
    expect(overflowWithDrawer, "horizontal overflow with drawer open").toBe(false);
  });

  test("Escape closes the drawer and restores focus to the opener", async ({ page }) => {
    await page.goto(path("/"), { waitUntil: "domcontentloaded" });
    const menuButton = phoneMenuButton(page);
    await menuButton.click();
    const dialog = page.getByRole("dialog", { name: "Main menu" });
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(menuButton).toBeFocused();
  });

  test("Tab cycles focus inside the open drawer", async ({ page }) => {
    await page.goto(path("/"), { waitUntil: "domcontentloaded" });
    const menuButton = phoneMenuButton(page);
    await menuButton.click();
    const dialog = page.getByRole("dialog", { name: "Main menu" });
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    await page.keyboard.press("Tab");
    const activeInDialog = await page.evaluate(() => {
      const dialogEl = document.querySelector('[role="dialog"][aria-label="Main menu"]');
      return Boolean(dialogEl?.contains(document.activeElement));
    });
    expect(activeInDialog, "Tab should keep focus inside the drawer").toBe(true);
  });

  test("drawer closes after in-menu navigation", async ({ page }) => {
    await page.goto(path("/"), { waitUntil: "domcontentloaded" });
    await phoneMenuButton(page).click();
    const dialog = page.getByRole("dialog", { name: "Main menu" });
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    await page.getByRole("link", { name: "Deals", exact: true }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/en\/deals/);
  });
});
