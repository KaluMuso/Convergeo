import { portalBypassConfig } from "../fixtures/env";
import { applyPortalBypass, resolveBypassSecret } from "../fixtures/portal-bypass";
import { expect, test } from "../fixtures/test-base";
import {
  allowedEmailAcceptanceRequest,
  assertEmailCaptureDisabled,
  assertEmptyEmailContext,
  assertFreshPasswordReceipt,
  isExactPasswordTokenRequest,
  assertExpectedLoginLocation,
  emailAcceptanceConfig,
  isPasswordTokenRequest,
  STAGING_AUTH_ORIGIN,
} from "./safety";

/** Diagnostic only: this file is outside the protected 65-test certification matrix. */
for (const portal of ["customer", "vendor"] as const) {
  test(`${portal} synthetic email login reaches its protected route`, async ({ page, context }) => {
    // Config is checked before navigation. No account creation or reset occurs.
    assertEmailCaptureDisabled(process.env);
    const config = emailAcceptanceConfig(process.env)[portal];
    // Count only; never attach/assert storage contents or private error causes.
    assertEmptyEmailContext(await context.storageState());
    try {
      const blocked: string[] = [];
      const authProbeOrigins: string[] = [];
      let probingAuthOrigin = true;
      let credentialsMayBePresent = false;
      let passwordRequests = 0;
      await context.routeWebSocket("**/*", async (socket) => {
        blocked.push("unapproved connection");
        await socket.close();
      });
      await context.route("**/*", async (route) => {
        const request = route.request();
        const target = new URL(request.url());
        if (probingAuthOrigin && isPasswordTokenRequest(target, request.method())) {
          // Dummy password only: discover the app's Auth target without sending.
          authProbeOrigins.push(target.origin);
          await route.abort();
          return;
        }
        if (credentialsMayBePresent && isPasswordTokenRequest(target, request.method())) {
          passwordRequests += 1;
          if (passwordRequests !== 1) {
            blocked.push("duplicate password exchange");
            await route.abort();
            return;
          }
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
          // Reuse the shared exact-origin/allHeaders helper. Terminal fetches
          // refuse redirects: routing only intercepts the first hop of a chain.
          await applyPortalBypass(
            {
              request: () => request,
              fallback: async (options) => {
                const response = await route.fetch({
                  ...options,
                  maxRedirects: 0,
                  maxRetries: 0,
                  timeout: 20_000,
                });
                try {
                  if (response.status() >= 300 && response.status() < 400) {
                    blocked.push("unapproved redirect");
                    await route.abort();
                    return;
                  }
                  await route.fulfill({ response });
                } finally {
                  await response.dispose();
                }
              },
            },
            (target) => resolveBypassSecret(target, portalBypassConfig()),
          );
        } else {
          // Never print a URL, query, body, or credential from a blocked request.
          blocked.push("unapproved request");
          await route.abort();
        }
      });

      await page.goto(`${config.origin}/en/login?next=${encodeURIComponent(config.next)}`);
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
      const attemptStartedAt = Math.floor(Date.now() / 1000);
      const receipt = page
        .waitForResponse(
          (response) =>
            isExactPasswordTokenRequest(new URL(response.url()), response.request().method()),
          { timeout: 20_000 },
        )
        .then(async (response) => {
          if (!response.ok()) throw new Error("password exchange failed");
          assertFreshPasswordReceipt(
            await response.json(),
            config.email,
            Math.floor(Date.now() / 1000),
            attemptStartedAt,
          );
        });
      // Observe rejection immediately, including if fill/click fails before await.
      void receipt.catch(() => {});
      await page.locator('input[type="password"]').fill(config.password);
      await submit.click();
      await receipt;
      await expect(page).toHaveURL(`${config.origin}${config.next}`, {
        timeout: 20_000,
      });
      if (portal === "customer") {
        await expect(page.getByTestId("account-nav")).toBeVisible();
      } else {
        // Rendered only after useSession resolves a session; no navigation/click.
        await expect(page.locator('main header a[href="/en/services/new"]')).toBeVisible();
      }
      await expect(page).toHaveURL(`${config.origin}${config.next}`);
      expect(passwordRequests).toBe(1);
      expect(blocked).toEqual([]);
    } catch {
      // Playwright locator call logs can include filled values. Keep no cause.
      throw new Error(`${portal} email/password diagnostic failed`);
    }
  });
}
