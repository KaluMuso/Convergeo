import { BASE_URL, LOCALE, path } from "../fixtures/env";
import { expect, test } from "../fixtures/test-base";

/**
 * E2E-GATE-04 — minimal browser proof that Playwright reaches the real customer
 * app, not a Vercel SSO/login interstitial, generic 404, or wrong portal.
 */
test.describe("staging-access-smoke", () => {
  test("home renders Convergeo customer app (not protection challenge)", async ({ page }) => {
    const isLocal = BASE_URL.includes("localhost") || BASE_URL.includes("127.0.0.1");
    test.skip(isLocal, "staging-access smoke runs against deployed staging only");

    await page.goto(path("/"), { waitUntil: "domcontentloaded" });

    const url = page.url();
    expect(url, "must stay on customer origin").toMatch(
      new RegExp(`^${BASE_URL.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`),
    );
    expect(url, "must not redirect to Vercel SSO").not.toMatch(/vercel\.com/i);

    const vercelLogin = page.getByRole("heading", { name: /log in to vercel|sign in to vercel/i });
    await expect(vercelLogin, "Vercel login page must not appear").toHaveCount(0);

    await expect(
      page
        .getByTestId("home-hero-brand")
        .or(page.getByTestId("home-hero-band"))
        .or(page.getByRole("link", { name: /vergeo/i }))
        .first(),
    ).toBeVisible({ timeout: 30_000 });

    const bodyText = (await page.locator("body").innerText()).toLowerCase();
    expect(bodyText, "404 shell must not pass smoke").not.toMatch(
      /page could not be found|this page could not be found/,
    );
  });
});
