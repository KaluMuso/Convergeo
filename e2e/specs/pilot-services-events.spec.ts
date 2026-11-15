import { mockCartMerge } from "../fixtures/checkout-api-mock";
import { path, strictSyntheticRequired } from "../fixtures/env";
import { installMockBuyerSession } from "../fixtures/payment-fixtures";
import { expectNoRawI18n } from "../fixtures/raw-i18n";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

test.use({ serviceWorkers: "block", viewport: { width: 360, height: 800 } });

/**
 * Pilot journey 5.
 *
 *  - Services RFQ ("post a job"): the form is client-side, so with a mock buyer
 *    session and a mocked `POST /jobs` it is fully deterministic (no backend).
 *  - Events: ticket purchase as a guest, up to the documented stopping point.
 *    Events checkout is online-only (MoMo/card; ticket-checkout.tsx rejects COD
 *    orders and offers no COD method), so there is no COD leg. Paid settlement
 *    is the provider-gated event-ticket.spec.ts. The guest hits sign-in first.
 */
test.describe("pilot · services RFQ", () => {
  test("signed-in buyer posts a job and gets the honest acknowledgement", async ({ page }) => {
    await installMockBuyerSession(page);
    await mockCartMerge(page);
    const posted: Array<Record<string, unknown>> = [];
    await page.route("**/jobs", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      posted.push(route.request().postDataJSON() as Record<string, unknown>);
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          job: {
            id: "e2e00000-0000-4000-8000-0000000000j1",
            broadcast: {
              matched_count: 3,
              notified_count: 3,
              capped: false,
              no_match: false,
              admin_flagged: false,
              message_key: "sent",
            },
          },
        }),
      });
    });

    await page.goto(path("/services/post-job"));
    await expect(page.getByRole("heading", { name: /post a job/i })).toBeVisible();
    // Signed in: no "sign in to post" gate.
    await expect(page.getByText(/sign in to post your job/i)).toHaveCount(0);

    await page.getByLabel(/service category/i).selectOption("cleaning");
    await page
      .getByLabel(/what do you need done/i)
      .fill("Deep clean a three bedroom house in Woodlands");
    await page.getByLabel(/^area/i).fill("Lusaka, Woodlands");
    await page.getByLabel(/budget range/i).selectOption("500_2000");
    await page.getByRole("button", { name: /^post job$/i }).click();

    await expect(page.locator("form").getByRole("status")).toContainText(
      /we notified matching providers/i,
    );
    await expect(page.getByRole("button", { name: /post job/i })).toBeDisabled();
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({
      category: "cleaning",
      service_area: "Lusaka, Woodlands",
      budget_band: "500_2000",
    });
    await expectNoRawI18n(page, "main");
  });

  test("guest can fill the RFQ but is asked to sign in, and nothing is sent", async ({ page }) => {
    let sent = 0;
    await page.route("**/jobs", async (route) => {
      if (route.request().method() === "POST") sent += 1;
      await route.fallback();
    });
    await page.goto(path("/services/post-job"));
    await page
      .getByLabel(/what do you need done/i)
      .fill("Fix a leaking kitchen tap before Saturday");
    await page.getByLabel(/^area/i).fill("Lusaka");
    await page.getByRole("button", { name: /^post job$/i }).click();

    await expect(page.locator("form").getByRole("alert")).toContainText(
      /sign in to post your job/i,
    );
    await expect(page.getByRole("link", { name: /continue with phone/i })).toHaveAttribute(
      "href",
      /\/login\?next=/,
    );
    expect(sent).toBe(0);
  });
});

test.describe("pilot · event tickets (guest, up to sign-in)", () => {
  test("seeded event shows tickets; Get tickets as a guest asks to sign in", async ({ page }) => {
    await page.goto(path(`/e/${SEED.event.slug}`));
    const picker = page
      .getByRole("region", { name: new RegExp(SEED.event.title, "i") })
      .or(page.locator(`[aria-labelledby="ticket-picker-${SEED.event.slug}"]`));
    const visible = await picker
      .first()
      .waitFor({ state: "visible", timeout: 20_000 })
      .then(() => true)
      .catch(() => false);
    if (!visible && !strictSyntheticRequired()) {
      test.info().annotations.push({
        type: "event-skip",
        description: "seeded event not available on this target (local exploratory)",
      });
      return;
    }
    expect(visible, "seeded event ticket picker must render").toBe(true);

    await expect(page.getByText(SEED.event.ticketTypeName).first()).toBeVisible();
    await page.getByRole("button", { name: /get tickets|reserve free spot/i }).click();
    await expect(page.getByText(/sign in to get tickets/i).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /sign in to get tickets/i })).toHaveAttribute(
      "href",
      /\/login/,
    );
    await expectNoRawI18n(page, "main");
  });
});
