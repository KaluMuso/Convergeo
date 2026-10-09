import { expect, test } from "../fixtures/test-base";
import {
  allowedEmailAcceptanceRequest,
  assertExpectedLoginLocation,
  emailAcceptanceConfig,
  isPasswordTokenRequest,
  STAGING_AUTH_ORIGIN,
} from "./safety";

/** Diagnostic only: this file is outside the protected 65-test certification matrix. */
for (const portal of ["customer", "vendor"] as const) {
  test(`${portal} synthetic email login reaches its protected route`, async ({
    page,
    context,
  }) => {
    // Config is checked before navigation. No account creation or reset occurs.
    const config = emailAcceptanceConfig(process.env)[portal];
    const blocked: string[] = [];
    const authProbeOrigins: string[] = [];
    let probingAuthOrigin = true;
    let credentialsMayBePresent = false;
    await context.route("**/*", async (route) => {
      const request = route.request();
      const target = new URL(request.url());
      if (
        probingAuthOrigin &&
        isPasswordTokenRequest(target, request.method())
      ) {
        // Dummy password only: discover the app's Auth target without sending.
        authProbeOrigins.push(target.origin);
        await route.abort();
        return;
      }
      if (
        allowedEmailAcceptanceRequest(
          target,
          request.method(),
          request.resourceType(),
          config.origin,
          !credentialsMayBePresent,
        )
      ) {
        // Preserve the shared per-origin Vercel bypass fixture's earlier route.
        await route.fallback();
      } else {
        // Never print a URL, query, body, or credential from a blocked request.
        blocked.push("unapproved request");
        await route.abort();
      }
    });

    await page.goto(
      `${config.origin}/en/login?next=${encodeURIComponent(config.next)}`,
    );
    assertExpectedLoginLocation(page.url(), config.origin);
    await page.getByRole("button", { name: /email/i }).click();
    assertExpectedLoginLocation(page.url(), config.origin);
    await page.locator('input[type="email"]').fill(config.email);
    const submit = page.locator('form button[type="submit"]');
    await page.locator('input[type="password"]').fill("e2e-auth-origin-probe");
    await submit.click();
    await expect.poll(() => authProbeOrigins.length).toBe(1);
    expect(authProbeOrigins).toEqual([STAGING_AUTH_ORIGIN]);
    expect(blocked).toEqual([]);
    await expect(submit).toBeEnabled();
    assertExpectedLoginLocation(page.url(), config.origin);

    probingAuthOrigin = false;
    credentialsMayBePresent = true;
    await page.locator('input[type="password"]').fill(config.password);
    await submit.click();
    await expect(page).toHaveURL(`${config.origin}${config.next}`, {
      timeout: 20_000,
    });
    expect(blocked).toEqual([]);
  });
}
