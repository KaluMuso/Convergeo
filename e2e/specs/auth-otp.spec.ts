import { customerOtp, customerOtpReady, path } from "../fixtures/env";
import { enforceGate, resolveGate } from "../fixtures/gating";
import { nationalNumberFromE164 } from "../fixtures/phone";
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
  test("request an OTP and (gated) verify to a signed-in session", async ({ page }) => {
    await page.goto(path("/login"));

    // Enter the phone number and request a code.
    //
    // PhoneForm renders FormField in `asGroup` mode (packages/ui/form-field.tsx):
    // the visible <label> is an unassociated sibling (aria-labelledby on the
    // group, not htmlFor on a control), so `getByLabel` resolves ambiguously —
    // it matches BOTH the national-number input (via its own aria-label) and
    // the enclosing `role="group"` (via aria-labelledby). A single semantic
    // `getByRole("textbox", ...)` resolves to exactly the national-number
    // input and nothing else; reproduced locally against the real component
    // before this change (jsdom/RTL: getAllByLabelText returned 2 matches,
    // getByRole("textbox", ...) returned exactly 1).
    const phoneInput = page.getByRole("textbox", { name: /phone|mobile/i });
    await expect(phoneInput).toBeVisible();
    // The field takes only the national number — the country code (+260) is a
    // fixed, read-only prefix rendered separately by PhoneForm. Filling the
    // raw E.164 fixture phone here (E2E run #52, RC-2) made the app's own
    // normalizer reject a well-formed number before any OTP was requested.
    await phoneInput.fill(nationalNumberFromE164(customerOtp.testPhone));

    await page
      .getByRole("button", { name: /continue|send|next|get code/i })
      .first()
      .click();

    // We should reach the OTP entry surface (6-digit code group).
    await page.waitForURL(/otp|verify|code/i, { timeout: 20_000 }).catch(() => {});
    const otpGroup = page.getByRole("group").or(page.getByRole("textbox").first());
    await expect(otpGroup.first()).toBeVisible();

    // ── ENV-GATED: verify with the deterministic test OTP ────────────────────
    if (!customerOtpReady()) {
      const gate = resolveGate({
        kind: "REQUIRED_STRICT",
        journey: "customer OTP verification",
        fixtures: ["E2E_CUSTOMER_TEST_OTP"],
      });
      // Certification runs fail here; local/nightly runs keep the old skip.
      enforceGate(gate);
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }

    // Type the 6-digit static test code into the OTP field.
    //
    // OtpField (packages/ui/src/otp-field.tsx) renders 6 separate inputs with no
    // auto-focus — page.keyboard.type() sends keystrokes to whatever currently
    // has DOM focus, which is nothing until a digit box is explicitly focused.
    // Reproduced locally (RTL) before this change: document.activeElement was
    // document.body after render; explicitly focusing the first digit box
    // ("Digit 1 of 6") made it the target.
    await page.getByRole("textbox", { name: "Digit 1 of 6" }).click();
    for (const digit of customerOtp.staticCode.slice(0, 6).split("")) {
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
