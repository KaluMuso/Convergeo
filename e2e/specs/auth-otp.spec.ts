import { BASE_URL, customerOtp, customerOtpReady, path } from "../fixtures/env";
import { enforceGate, resolveGate } from "../fixtures/gating";
import { nationalNumberFromE164 } from "../fixtures/phone";
import { expect, test } from "../fixtures/test-base";

/**
 * Critical path: phone OTP login.
 *
 * Both request and verification require the accepted U4a declarations.
 * The gate runs before navigation; static code presence alone is insufficient.
 * An exact protected account destination proves the existing session contract
 * when the deployed target and AccountLayout binding are separately verified.
 */
test.use({ trace: "off", video: "off", screenshot: "off" });

test.describe("auth · phone OTP", () => {
  test.describe.configure({ retries: 0 });
  test("request an OTP and (gated) verify to a signed-in session", async ({ page }) => {
    // Guard the request as well as verification, before any navigation.
    if (!customerOtpReady()) {
      const gate = resolveGate({
        kind: "REQUIRED_STRICT",
        journey: "customer OTP verification",
        fixtures: [
          "E2E_CUSTOMER_TEST_OTP",
          "SMS_OTP_TRANSPORT",
          "WAHA_OTP_ENABLED",
          "STAGING_SMS_SANDBOX_ATTESTED",
          "STAGING_TEST_OTP_MAP_ATTESTED",
        ],
      });
      // Certification runs fail here; local/nightly runs keep the old skip.
      enforceGate(gate);
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }

    let national: string;
    let origin: string;
    try {
      national = nationalNumberFromE164(customerOtp.testPhone);
      const configured = new URL(BASE_URL);
      if (
        configured.username ||
        configured.password ||
        !(
          configured.protocol === "https:" ||
          (configured.protocol === "http:" &&
            ["localhost", "127.0.0.1", "[::1]"].includes(configured.hostname))
        )
      ) {
        throw new Error("invalid origin");
      }
      origin = configured.origin;
    } catch {
      throw new Error("customer OTP requires a valid fixture and portal origin");
    }
    const account = new URL(path("/account"), origin).href;
    await page.goto(`${path("/login")}?next=${encodeURIComponent(path("/account"))}`);

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
    await phoneInput.fill(national);

    await page
      .getByRole("button", { name: /continue|send|next|get code/i })
      .first()
      .click();

    // We should reach the OTP entry surface (6-digit code group).
    await page.waitForURL(
      (url) =>
        url.origin === origin &&
        url.pathname === path("/otp") &&
        url.searchParams.get("phone") === customerOtp.testPhone,
      { timeout: 20_000 },
    );
    const otpGroup = page.getByRole("group").or(page.getByRole("textbox").first());
    await expect(otpGroup.first()).toBeVisible();

    // Type the 6-digit static test code into the OTP field.
    //
    // OtpField (packages/ui/src/otp-field.tsx) renders 6 separate inputs with no
    // auto-focus — page.keyboard.type() sends keystrokes to whatever currently
    // has DOM focus, which is nothing until a digit box is explicitly focused.
    // Reproduced locally (RTL) before this change: document.activeElement was
    // document.body after render; explicitly focusing the first digit box
    // ("Digit 1 of 6") made it the target.
    await page.getByRole("textbox", { name: "Digit 1 of 6" }).click();
    for (const digit of customerOtp.staticCode.split("")) {
      await page.keyboard.type(digit);
    }

    // No explicit Verify click — same reason as fixtures/otp-login.ts. The
    // Customer and Vendor OTP pages render the same shared OtpForm, whose
    // OtpField auto-submits on the sixth digit, so verification is already in
    // flight here. Clicking on top of it drove a duplicate verifyOtp for one
    // single-use code (Run #68). The bounded assertion below is unchanged.

    // AccountLayout calls getUser() and redirects anonymous users to login.
    // This exact protected-origin destination is required; send acceptance,
    // onboarding/recovery routes or an arbitrary off-auth URL cannot confirm it.
    await page.waitForURL((url) => url.href === account, { timeout: 20_000 });
    await expect(page.getByTestId("account-nav")).toBeVisible({ timeout: 20_000 });
    await expect(page).toHaveURL(account, { timeout: 20_000 });
  });
});
