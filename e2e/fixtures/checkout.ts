import { expect, type Locator, type Page } from "@playwright/test";

import { customerOtp, customerOtpReady } from "./env";
import { nationalNumberFromE164 } from "./phone";
import { SEED } from "./seed";

/**
 * Drive the REAL deployed Customer checkout, step by step.
 *
 * S2's staging certification failed because `shop-cod.spec.ts` and
 * `shop-checkout-momo.spec.ts` reached /checkout and immediately went looking
 * for Payment controls, while the deployed app was still showing
 *
 *   Checkout
 *   Step 1 of 4
 *   Your contact details
 *
 * The app's actual contract is a four-step wizard —
 * Contact -> Fulfilment -> Payment -> Review -> Place order — driven by
 * `CheckoutShell` (apps/customer/.../checkout/_components/step-fulfilment.tsx).
 * The specs never advanced a single step, so the radio/`place order` locators
 * they used could not match anything, whatever the backend did.
 *
 * This fixture drives that real wizard. It fabricates nothing: no cookie,
 * session or localStorage injection, no `service_role` in the browser, no
 * hidden route, no mock. The only session it ever creates is the one the
 * deployed app mints from a real OTP verification.
 *
 * ── Locator strategy ────────────────────────────────────────────────────────
 * Every locator below is either a Checkout-owned `data-testid`/`id` that the
 * app already publishes, or a structural property of the checkout markup that
 * holds in every locale:
 *
 *   - `li[aria-current="step"]` is published ONLY by `packages/ui/src/stepper.tsx`,
 *     and Checkout is the only Customer surface that renders a Stepper. Its
 *     position in the list IS the current step, with no copy to read.
 *   - the Contact step is the only checkout surface whose phone input sits
 *     inside a `<form>`; the Payment step's payer input does not.
 *   - the Fulfilment step is the only surface with `name="fulfilment-<vendor>"`
 *     radios, and within a vendor group the delivery radio precedes pickup
 *     (StepFulfilment renders them in that order).
 *   - the Payment step publishes `checkout-payment-methods`,
 *     `checkout-cod-unavailable` and `payment-rail-{mtn,airtel}`.
 *   - the Review step publishes `#checkout-consent` and `checkout-place-order`.
 *
 * Nothing here matches on user-facing copy, so the helper cannot silently bind
 * to an unrelated global string the way run 35456698878's critical path bound
 * to "Loading categories…".
 */

/** Stepper order, as `CheckoutShell` builds it. */
export const CHECKOUT_STEPS = ["contact", "fulfilment", "payment", "review"] as const;
export type CheckoutStep = (typeof CHECKOUT_STEPS)[number];

export type CheckoutPaymentChoice = "cod" | "momo";
export type MomoRail = "mtn" | "airtel";

/** How the Contact step actually resolved on this target. */
export type ContactOutcome = "otp-verified" | "already-authenticated";

export type CheckoutOptions = {
  payment: CheckoutPaymentChoice;
  /** MoMo rail. Ignored for COD. */
  rail?: MomoRail;
  /** Payer MSISDN — E.164 (`+260…`) or a 9-digit national number. */
  payerPhone?: string;
  /** Budget for each step transition (real network + real API). */
  stepTimeout?: number;
};

export type CheckoutRun = {
  payment: CheckoutPaymentChoice;
  contact: ContactOutcome;
  /** What was actually chosen per vendor group. */
  fulfilment: Array<"delivery" | "pickup">;
  /** National number filled on the Payment step, when MoMo was chosen. */
  payerNationalNumber: string | null;
};

const DEFAULT_STEP_TIMEOUT = 30_000;

/** The Stepper's `<ol>` — the Checkout surface's own, locale-free step marker. */
const STEPPER_OL = 'ol:has(> li[aria-current="step"])';
/** The Contact step's OTP-request form (the Payment payer field is NOT in a form). */
const CONTACT_FORM = 'form:has(input[autocomplete="tel-national"])';
/** OtpField digit boxes (packages/ui/src/otp-field.tsx). */
const OTP_DIGITS = 'input[inputmode="numeric"][maxlength="1"]';
/** Per-vendor fulfilment radios (StepFulfilment). */
const FULFILMENT_RADIOS = 'input[type="radio"][name^="fulfilment-"]';

/**
 * The Checkout surface itself.
 *
 * Use this — never a bare `getByText(/checkout|loading|phone/i)` — to assert
 * that a page IS checkout. The Stepper is rendered by both the loading and the
 * loaded branch of `CheckoutShell`, so this is true from first paint.
 */
export function checkoutSurface(page: Page): Locator {
  return page.locator(STEPPER_OL);
}

/**
 * The `CheckoutShell` root: the Stepper's grandparent.
 *
 * Scoping to it keeps `getByRole("button")` away from the shop chrome (header,
 * bottom nav, cart badge) that surrounds the wizard.
 */
export function checkoutShell(page: Page): Locator {
  return page.locator(STEPPER_OL).locator("xpath=../..");
}

/** The Stepper entry for `step`, present only while that step is current. */
export function checkoutStepMarker(page: Page, step: CheckoutStep): Locator {
  const position = CHECKOUT_STEPS.indexOf(step) + 1;
  return page.locator(`${STEPPER_OL} > li:nth-child(${position})[aria-current="step"]`);
}

/** Wait until the wizard is on `step`. */
export async function waitForCheckoutStep(
  page: Page,
  step: CheckoutStep,
  timeout = DEFAULT_STEP_TIMEOUT,
): Promise<void> {
  await expect(checkoutStepMarker(page, step)).toBeVisible({ timeout });
}

/**
 * The step's own advance control.
 *
 * Each step renders its submit/continue Button last inside the shell
 * (StepContact "Send code", StepFulfilment "Continue", StepPayment "Continue
 * to review"), so the last button in the shell is that control by
 * construction — no label matching, no locale coupling. Review is addressed by
 * its `checkout-place-order` testid instead.
 */
function stepAdvanceButton(page: Page): Locator {
  return checkoutShell(page).getByRole("button").last();
}

/** Accept either `+260XXXXXXXXX` or a bare/leading-zero national number. */
function payerNationalNumber(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.startsWith("+")) {
    return nationalNumberFromE164(trimmed);
  }
  const national = /^0?([79]\d{8})$/.exec(trimmed);
  if (!national?.[1]) {
    throw new Error(
      `checkout fixture: "${trimmed}" is not a usable Zambian payer number ` +
        "(expected +260 E.164 or a 9-digit national number starting 7 or 9)",
    );
  }
  return national[1];
}

/**
 * Step 1 — Contact.
 *
 * Drives the app's own phone -> OTP -> verified-session path against the real
 * deployed Supabase, exactly as a buyer would. `OtpField` auto-submits the
 * moment the sixth digit lands and `StepContact` holds a synchronous
 * single-flight lock, so the Verify button is deliberately NOT clicked: doing
 * so would be a second submission of one single-use code (the PR #680 /
 * run #68 duplicate-verify defect).
 *
 * An already-authenticated synthetic Customer legitimately skips this step —
 * `CheckoutShell` starts at Fulfilment when `/checkout/session` reports
 * `contact_skipped`, and `StepContact` auto-completes when a session already
 * exists. That real application state is reported back as
 * "already-authenticated" rather than forced or faked.
 */
export async function completeContactStep(
  page: Page,
  timeout = DEFAULT_STEP_TIMEOUT,
): Promise<ContactOutcome> {
  const contactForm = page.locator(CONTACT_FORM);
  const fulfilment = page.locator(FULFILMENT_RADIOS).first();

  // `.or()` polls, so this absorbs the real /checkout/session round trip
  // without a sleep, a networkidle wait or an inflated timeout.
  await expect(contactForm.or(fulfilment).first()).toBeVisible({ timeout });

  if ((await page.locator(FULFILMENT_RADIOS).count()) > 0) {
    return "already-authenticated";
  }

  if (!customerOtpReady()) {
    throw new Error(
      "checkout fixture: the Contact step is required on this target but E2E_CUSTOMER_TEST_OTP " +
        "is not configured — callers must gate on customerOtpReady() before driving checkout",
    );
  }

  // The field takes the 9-digit national number only; +260 is a separate
  // read-only prefix input (the exact run #52 / RC-2 defect).
  const phoneInput = contactForm.locator('input[autocomplete="tel-national"]');
  await phoneInput.fill(nationalNumberFromE164(customerOtp.testPhone));
  await contactForm.locator('button[type="submit"]').click();

  // OtpField has no autofocus — keystrokes go to whatever holds DOM focus, so
  // the first digit box must be focused explicitly (PR #680).
  const digits = page.locator(OTP_DIGITS);
  await expect(digits).toHaveCount(6, { timeout });
  await digits.first().click();
  for (const digit of customerOtp.staticCode.slice(0, 6).split("")) {
    await page.keyboard.type(digit);
  }

  // Auto-submit -> real verifyOtp -> POST /checkout/steps/contact -> step 2.
  await waitForCheckoutStep(page, "fulfilment", timeout);
  return "otp-verified";
}

/**
 * Step 2 — Fulfilment.
 *
 * Preserves Delivery wherever the seeded listing supports it: the delivery
 * radio is `disabled` for a vendor group outside the Lusaka delivery zone
 * (`!group.delivery_eligible`), so a group that genuinely cannot be delivered
 * falls back to Pickup instead of being forced. The landmark is filled from
 * the canonical seed whenever any group is on Delivery, because
 * `StepFulfilment` only renders that field then.
 */
export async function completeFulfilmentStep(
  page: Page,
  timeout = DEFAULT_STEP_TIMEOUT,
): Promise<Array<"delivery" | "pickup">> {
  await waitForCheckoutStep(page, "fulfilment", timeout);
  const radios = page.locator(FULFILMENT_RADIOS);
  await expect(radios.first()).toBeVisible({ timeout });

  const groupNames = [
    ...new Set(
      await radios.evaluateAll((nodes) => nodes.map((node) => (node as HTMLInputElement).name)),
    ),
  ];
  if (groupNames.length === 0) {
    throw new Error("checkout fixture: the Fulfilment step rendered no vendor group");
  }

  const chosen: Array<"delivery" | "pickup"> = [];
  for (const name of groupNames) {
    // StepFulfilment renders delivery first, then pickup, per vendor group.
    const groupRadios = page.locator(`input[type="radio"][name="${name}"]`);
    const delivery = groupRadios.nth(0);
    const pickup = groupRadios.nth(1);
    if (await delivery.isEnabled()) {
      await delivery.check();
      chosen.push("delivery");
    } else {
      await pickup.check();
      chosen.push("pickup");
    }
  }

  if (chosen.includes("delivery")) {
    // The landmark field is the Fulfilment step's only textbox.
    const landmark = checkoutShell(page).getByRole("textbox");
    await expect(landmark).toHaveCount(1, { timeout });
    // The UI submits one landmark string. Include the seed's city so the
    // checkout zone resolver can identify this synthetic Lusaka address.
    await landmark.fill(`${SEED.address.landmark}, ${SEED.address.area}`);
  }

  await stepAdvanceButton(page).click();
  await expect(page.getByTestId("checkout-payment-methods")).toBeVisible({ timeout });
  await waitForCheckoutStep(page, "payment", timeout);
  return chosen;
}

/**
 * Step 3 — Payment.
 *
 * `StepPayment` renders its methods in a fixed order inside
 * `checkout-payment-methods` — mobile money, card, then cash on delivery when
 * the order is COD-eligible — so each is addressed by position rather than by
 * label. COD ineligibility is a real backend verdict (the K500 Zambia cap):
 * when the app says so through `checkout-cod-unavailable`, this fails loudly
 * instead of quietly paying a different way.
 */
export async function completePaymentStep(
  page: Page,
  options: CheckoutOptions,
): Promise<string | null> {
  const timeout = options.stepTimeout ?? DEFAULT_STEP_TIMEOUT;
  const methods = page.getByTestId("checkout-payment-methods");
  await expect(methods).toBeVisible({ timeout });

  const methodRadios = methods.locator('input[name="payment-method"]');
  let payer: string | null = null;

  if (options.payment === "cod") {
    if ((await page.getByTestId("checkout-cod-unavailable").count()) > 0) {
      throw new Error(
        "checkout fixture: the deployed app reports Cash on Delivery ineligible for this cart " +
          "(checkout-cod-unavailable) — the seeded order total must stay inside the K500 COD cap",
      );
    }
    await expect(methodRadios).toHaveCount(3, { timeout });
    await methodRadios.nth(2).check();
  } else {
    await methodRadios.nth(0).check();
    const rail = options.rail ?? "mtn";
    await page.getByTestId(`payment-rail-${rail}`).click();
    await expect(page.getByTestId(`payment-rail-${rail}`)).toHaveAttribute("data-selected", "true");

    payer = payerNationalNumber(options.payerPhone ?? SEED.address.phone);
    // The Payment step's payer field is the only tel-national input outside a
    // form (the Contact form is unmounted by this point).
    const payerInput = checkoutShell(page).locator('input[autocomplete="tel-national"]');
    await expect(payerInput).toHaveCount(1, { timeout });
    await payerInput.fill(payer);
  }

  // The chosen method's card is the one the app marks selected — proof the
  // click landed, with no copy read.
  await expect(methods.locator('[data-selected="true"]')).toHaveCount(1);

  await stepAdvanceButton(page).click();
  await waitForCheckoutStep(page, "review", timeout);
  return payer;
}

/**
 * Step 4 — Review, consent, place order.
 *
 * The payment choice is re-asserted on the Review surface without reading
 * copy: `StepReview` prints the payer number line only for MoMo, so its
 * presence (with the exact digits typed on the Payment step) or absence is a
 * locale-independent statement of which method is about to be placed. The
 * terminal surface below is the second, independent proof — COD and MoMo land
 * on different honest states.
 */
export async function placeOrderFromReview(
  page: Page,
  options: CheckoutOptions,
  payerNumber: string | null,
): Promise<void> {
  const timeout = options.stepTimeout ?? DEFAULT_STEP_TIMEOUT;
  const shell = checkoutShell(page);
  const placeOrder = page.getByTestId("checkout-place-order");
  await expect(placeOrder).toBeVisible({ timeout });

  if (options.payment === "momo") {
    if (!payerNumber) {
      throw new Error("checkout fixture: MoMo review reached without a payer number");
    }
    await expect(shell).toContainText(payerNumber);
  } else {
    await expect(shell).not.toContainText(payerNationalNumber(SEED.address.phone));
  }

  if ((await page.getByTestId("checkout-place-order-unavailable").count()) > 0) {
    throw new Error(
      "checkout fixture: the deployed app reports order placement unavailable " +
        "(checkout-place-order-unavailable) — a real backend state, not a locator problem",
    );
  }

  const consent = page.locator("#checkout-consent");
  await expect(consent).toBeVisible({ timeout });
  await consent.check();
  await expect(placeOrder).toBeEnabled({ timeout });
  await placeOrder.click();

  // The truthful terminal state. COD is "placed, pay the courier"; MoMo is the
  // USSD wait, or the confirming surface if the push already settled. Neither
  // is a local "paid" claim — payment-outcome honesty (CUST-08 / G4).
  const terminal =
    options.payment === "cod"
      ? page.getByTestId("payment-cod")
      : page.getByTestId("ussd-wait").or(page.getByTestId("payment-confirming"));

  try {
    await expect(terminal.first()).toBeVisible({ timeout: 60_000 });
  } catch (error) {
    // Only runs after the assertion has already failed and its budget has
    // already elapsed, so it cannot change pass/fail — it just makes the
    // failure legible instead of a bare locator timeout.
    const alerts = await page
      .locator('[role="alert"]')
      .allTextContents()
      .catch(() => [] as string[]);
    const reached = await page
      .getByTestId("payment-status-error")
      .count()
      .catch(() => 0);
    throw new Error(
      `place-order did not reach the ${options.payment} terminal surface. ` +
        `payment-status-error=${reached}; alerts=${JSON.stringify(alerts)}. ` +
        `Original: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

/**
 * Drive the whole deployed wizard: Contact -> Fulfilment -> Payment -> Review
 * -> Place order, ending on the truthful pending/confirmation surface.
 */
export async function completeCheckout(page: Page, options: CheckoutOptions): Promise<CheckoutRun> {
  const timeout = options.stepTimeout ?? DEFAULT_STEP_TIMEOUT;
  await expect(checkoutSurface(page)).toBeVisible({ timeout });

  const contact = await completeContactStep(page, timeout);
  const fulfilment = await completeFulfilmentStep(page, timeout);
  const payerNationalNumberUsed = await completePaymentStep(page, options);
  await placeOrderFromReview(page, options, payerNationalNumberUsed);

  return {
    payment: options.payment,
    contact,
    fulfilment,
    payerNationalNumber: payerNationalNumberUsed,
  };
}
