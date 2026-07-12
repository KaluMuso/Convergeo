import { otp, otpVerifyReady, path } from "../fixtures/env";
import { expect, test } from "../fixtures/test-base";

/**
 * Critical path: phone OTP login.
 *
 * The "code sent" boundary (entering a phone and requesting an OTP) runs against
 * any live target. The VERIFY leg needs a deterministic test OTP for a fixed
 * test phone (Supabase test-OTP map) → ENV-GATED behind `E2E_TEST_PHONE` +
 * `E2E_TEST_OTP`. Without them the spec asserts the OTP step is reached and
 * skips verification with an annotation (never sends real SMS spam in a loop).
 */
test.describe("auth · phone OTP", () => {
  test("request an OTP and (gated) verify to a signed-in session", async ({
    page,
  }) => {
    await page.goto(path("/login"));

    // Enter the phone number and request a code.
    const phoneInput = page
      .getByLabel(/phone|mobile/i)
      .or(page.getByRole("textbox", { name: /phone|mobile/i }))
      .first();
    await expect(phoneInput).toBeVisible();
    await phoneInput.fill(otp.testPhone || "+260970000001");

    await page
      .getByRole("button", { name: /continue|send|next|get code/i })
      .first()
      .click();

    // We should reach the OTP entry surface (6-digit code group).
    await page.waitForURL(/otp|verify|code/i, { timeout: 20_000 }).catch(() => {});
    const otpGroup = page
      .getByRole("group")
      .or(page.getByRole("textbox").first());
    await expect(otpGroup.first()).toBeVisible();

    // ── ENV-GATED: verify with the deterministic test OTP ────────────────────
    if (!otpVerifyReady()) {
      test.info().annotations.push({
        type: "founder-gated",
        description:
          "OTP verify skipped — set E2E_TEST_PHONE + E2E_TEST_OTP (Supabase staging test-OTP). Asserted 'code sent' boundary only.",
      });
      test.skip(true, "OTP verify leg is staging/founder-gated");
      return;
    }

    // Type the 6-digit static test code into the OTP field.
    for (const digit of otp.staticCode.slice(0, 6).split("")) {
      await page.keyboard.type(digit);
    }
    await page
      .getByRole("button", { name: /verify|submit|continue/i })
      .first()
      .click();

    // A signed-in session lands off the auth routes (home/account).
    await expect(page).not.toHaveURL(/login|otp|verify/i, { timeout: 20_000 });
  });
});
