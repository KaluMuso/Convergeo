import { expect, test } from "../fixtures/test-base";
import {
  emailAcceptanceConfig,
  forbiddenEmailAcceptanceRequest,
} from "./safety";

/** Diagnostic only: this file is outside the protected 65-test certification matrix. */
for (const portal of ["customer", "vendor"] as const) {
  test(`${portal} synthetic email login reaches its protected route`, async ({
    page,
    context,
  }) => {
    // Config is checked before navigation. No account creation or reset occurs.
    const config = emailAcceptanceConfig(process.env)[portal];
    const forbidden: string[] = [];
    await context.route(forbiddenEmailAcceptanceRequest, async (route) => {
      // No URL, query string, body, or credential may enter test output.
      forbidden.push("forbidden outbound request");
      await route.abort();
    });

    await page.goto(
      `${config.origin}/en/login?next=${encodeURIComponent(config.next)}`,
    );
    await page.getByRole("button", { name: /email/i }).click();
    await page.locator('input[type="email"]').fill(config.email);
    await page.locator('input[type="password"]').fill(config.password);
    await page.locator('form button[type="submit"]').click();
    await expect(page).toHaveURL(`${config.origin}${config.next}`, {
      timeout: 20_000,
    });
    expect(forbidden).toEqual([]);
  });
}
