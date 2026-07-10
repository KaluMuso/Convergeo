// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import { StepPayment, type PaymentOptions } from "./step-payment";
import { StepReview } from "./step-review";

import type { CheckoutSession } from "./step-fulfilment";

const paymentLabels = {
  title: checkoutMessages.checkout.payment.title,
  subtitle: checkoutMessages.checkout.payment.subtitle,
  momo: checkoutMessages.checkout.payment.momo,
  card: checkoutMessages.checkout.payment.card,
  cod: checkoutMessages.checkout.payment.cod,
  railMtn: checkoutMessages.checkout.payment.railMtn,
  railAirtel: checkoutMessages.checkout.payment.railAirtel,
  payerLabel: checkoutMessages.checkout.payment.payerLabel,
  payerHelp: checkoutMessages.checkout.payment.payerHelp,
  payerPlaceholder: checkoutMessages.checkout.payment.payerPlaceholder,
  countryCode: checkoutMessages.checkout.payment.countryCode,
  nationalNumber: checkoutMessages.checkout.payment.nationalNumber,
  cardExplainer: checkoutMessages.checkout.payment.cardExplainer,
  codIneligible: (cap: string) =>
    checkoutMessages.checkout.payment.codIneligible.replace("{cap}", cap),
  continue: checkoutMessages.checkout.payment.continue,
  loading: checkoutMessages.checkout.payment.loading,
  required: checkoutMessages.checkout.payment.required,
  invalidPayer: checkoutMessages.checkout.payment.invalidPayer,
  railRequired: checkoutMessages.checkout.payment.railRequired,
  codRejected: checkoutMessages.checkout.payment.codRejected,
  railRejected: checkoutMessages.checkout.payment.railRejected,
  error: checkoutMessages.checkout.payment.error,
};

const reviewLabels = {
  title: checkoutMessages.checkout.review.title,
  subtitle: checkoutMessages.checkout.review.subtitle,
  lineItems: checkoutMessages.checkout.review.lineItems,
  qtyTemplate: checkoutMessages.checkout.review.qty,
  subtotal: checkoutMessages.checkout.review.subtotal,
  deliveryFees: checkoutMessages.checkout.review.deliveryFees,
  total: checkoutMessages.checkout.review.total,
  paymentMethod: checkoutMessages.checkout.review.paymentMethod,
  methodMomo: checkoutMessages.checkout.review.methodMomo,
  methodCard: checkoutMessages.checkout.review.methodCard,
  methodCod: checkoutMessages.checkout.review.methodCod,
  railMtn: checkoutMessages.checkout.review.railMtn,
  railAirtel: checkoutMessages.checkout.review.railAirtel,
  payerNumber: checkoutMessages.checkout.review.payerNumber,
  escrowTitle: checkoutMessages.checkout.review.escrowTitle,
  escrowStep1: checkoutMessages.checkout.review.escrowStep1,
  escrowStep2: checkoutMessages.checkout.review.escrowStep2,
  escrowStep3: checkoutMessages.checkout.review.escrowStep3,
  consentLabel: checkoutMessages.checkout.review.consentLabel,
  consentRequired: checkoutMessages.checkout.review.consentRequired,
  placeOrder: checkoutMessages.checkout.review.placeOrder,
  loading: checkoutMessages.checkout.review.loading,
};

const sampleSession: CheckoutSession = {
  session_id: "session-1",
  expires_at: "2099-01-01T00:00:00Z",
  reservation_ttl_min: 15,
  subtotal_ngwee: 60_000,
  contact_skipped: true,
  vendor_groups: [
    {
      vendor_id: "vendor-a",
      vendor_name: "Vendor A",
      subtotal_ngwee: 60_000,
      delivery_eligible: true,
      pickup_location: null,
      items: [
        {
          id: "line-1",
          listing_id: "listing-1",
          vendor_id: "vendor-a",
          qty: 1,
          unit_price_ngwee: 60_000,
          line_total_ngwee: 60_000,
          title_override: "Sample item",
        },
      ],
    },
  ],
};

const totalsAboveCap: PaymentOptions = {
  session_id: "session-1",
  subtotal_ngwee: 60_000,
  delivery_fee_ngwee: 0,
  total_ngwee: 60_000,
  cod_cap_ngwee: 50_000,
  cod_eligible: false,
};

vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
  createApiClient: () => ({
    request: vi.fn().mockResolvedValue(totalsAboveCap),
  }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("StepPayment", () => {
  it("hides COD option above cap and shows ineligibility message", async () => {
    render(
      <StepPayment
        locale="en"
        sessionId="session-1"
        accessToken="token"
        labels={paymentLabels}
        onComplete={vi.fn()}
      />,
    );

    expect(await screen.findByText(checkoutMessages.checkout.payment.momo)).toBeInTheDocument();
    expect(screen.queryByLabelText(checkoutMessages.checkout.payment.cod)).not.toBeInTheDocument();
    expect(
      screen.getByText(checkoutMessages.checkout.payment.codIneligible.replace("{cap}", "K500.00")),
    ).toBeInTheDocument();
  });
});

describe("StepReview", () => {
  it("requires consent before place order can proceed", async () => {
    const user = userEvent.setup();
    const onPlaceOrder = vi.fn();

    render(
      <StepReview
        locale="en"
        session={sampleSession}
        totals={totalsAboveCap}
        payment={{ method: "card", rail: null, payer_number: null }}
        labels={reviewLabels}
        onPlaceOrder={onPlaceOrder}
      />,
    );

    const placeOrderButton = screen.getByRole("button", {
      name: checkoutMessages.checkout.review.placeOrder,
    });
    expect(placeOrderButton).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: reviewLabels.consentLabel }));
    expect(placeOrderButton).not.toBeDisabled();

    await user.click(placeOrderButton);
    expect(onPlaceOrder).toHaveBeenCalledTimes(1);
  });

  it("shows escrow trust copy", () => {
    render(
      <StepReview
        locale="en"
        session={sampleSession}
        totals={totalsAboveCap}
        payment={{ method: "cod", rail: null, payer_number: null }}
        labels={reviewLabels}
      />,
    );

    expect(screen.getByText(checkoutMessages.checkout.review.escrowStep1)).toBeInTheDocument();
    expect(screen.getByText(checkoutMessages.checkout.review.escrowStep2)).toBeInTheDocument();
    expect(screen.getByText(checkoutMessages.checkout.review.escrowStep3)).toBeInTheDocument();
  });
});
