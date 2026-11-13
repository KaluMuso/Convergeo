// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import { StepPayment, type PaymentOptions } from "./step-payment";
import { StepReview, type ReviewStepLabels } from "./step-review";

import type { CheckoutSession } from "./step-fulfilment";

// UX pass 4: COD is explained in plain language and never borrows the
// escrow "you paid → held" promise, because nothing is charged online.

const c = checkoutMessages.checkout;

const options = vi.hoisted(() => ({
  current: null as unknown,
}));

vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
  createApiClient: () => ({
    request: vi.fn().mockImplementation(async () => options.current),
  }),
}));

const paymentLabels = {
  ...c.payment,
  codIneligible: (cap: string) => c.payment.codIneligible.replace("{cap}", cap),
  codGuide: c.payment.codGuide,
};

const reviewLabels: ReviewStepLabels = {
  ...c.review,
  qtyTemplate: c.review.qty,
  methodMomo: c.review.methodMomo,
  payerNumber: c.review.payerNumber,
  saleUnits: checkoutMessages.cart.saleUnits,
  madeToOrderLeadTime: checkoutMessages.cart.madeToOrderLeadTime,
  codGuide: c.review.codGuide,
};

const session: CheckoutSession = {
  session_id: "session-1",
  expires_at: "2099-01-01T00:00:00Z",
  reservation_ttl_min: 15,
  subtotal_ngwee: 40_000,
  contact_skipped: true,
  vendor_groups: [
    {
      vendor_id: "vendor-a",
      vendor_name: "Vendor A",
      subtotal_ngwee: 40_000,
      delivery_eligible: true,
      pickup_location: null,
      items: [
        {
          id: "line-1",
          listing_id: "listing-1",
          vendor_id: "vendor-a",
          qty: 1,
          unit_price_ngwee: 40_000,
          line_total_ngwee: 40_000,
          title_override: "Sample item",
        },
      ],
    },
  ],
};

const eligible: PaymentOptions = {
  session_id: "session-1",
  subtotal_ngwee: 40_000,
  delivery_fee_ngwee: 2_500,
  total_ngwee: 42_500,
  cod_cap_ngwee: 50_000,
  cod_eligible: true,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("COD guidance — payment step", () => {
  it("explains COD with the real total and cap once COD is selected", async () => {
    options.current = eligible;
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(
      <StepPayment
        locale="en"
        sessionId="session-1"
        accessToken="token"
        labels={paymentLabels}
        onComplete={vi.fn()}
      />,
    );

    await user.click(await screen.findByLabelText(c.payment.cod));
    const guide = screen.getByTestId("checkout-cod-guide");
    expect(within(guide).getByText(c.payment.codGuide.step1)).toBeInTheDocument();
    expect(
      within(guide).getByText(c.payment.codGuide.step2.replace("{amount}", "K425.00")),
    ).toBeInTheDocument();
    expect(
      within(guide).getByText(c.payment.codGuide.capNote.replace("{cap}", "K500.00")),
    ).toBeInTheDocument();
  });

  it("tells an over-cap buyer how to qualify and links back to the cart", async () => {
    options.current = { ...eligible, total_ngwee: 60_000, cod_eligible: false };
    render(
      <StepPayment
        locale="en"
        sessionId="session-1"
        accessToken="token"
        labels={paymentLabels}
        onComplete={vi.fn()}
      />,
    );

    const card = await screen.findByTestId("checkout-cod-unavailable");
    expect(
      within(card).getByText(
        c.payment.codGuide.overCap.replace("{total}", "K600.00").replace("{cap}", "K500.00"),
      ),
    ).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: c.payment.codGuide.editCart })).toHaveAttribute(
      "href",
      "/en/cart",
    );
  });
});

describe("COD guidance — review step", () => {
  it("shows COD steps instead of the escrow triad and names the delivery landmark", () => {
    render(
      <StepReview
        locale="en"
        session={session}
        totals={eligible}
        payment={{ method: "cod", rail: null, payer_number: null }}
        fulfilment={{
          landmark: "Woodlands, near the church",
          groups: [
            {
              vendor_id: "vendor-a",
              fulfilment: "delivery",
              delivery_zone: "lusaka_a",
              delivery_fee_ngwee: 2_500,
              subtotal_ngwee: 40_000,
            },
          ],
        }}
        labels={reviewLabels}
        onPlaceOrder={vi.fn()}
      />,
    );

    const steps = screen.getByTestId("checkout-review-cod-steps");
    expect(within(steps).getByText(c.review.codGuide.step1)).toBeInTheDocument();
    expect(
      within(steps).getByText(c.review.codGuide.step3.replace("{amount}", "K425.00")),
    ).toBeInTheDocument();
    expect(screen.queryByText(c.review.escrowStep1)).not.toBeInTheDocument();
    expect(screen.queryByText(c.review.escrowTitle)).not.toBeInTheDocument();
    expect(screen.getByTestId("review-fulfilment-vendor-a")).toHaveTextContent(
      c.review.codGuide.deliveryTo.replace("{landmark}", "Woodlands, near the church"),
    );
    expect(screen.getByTestId("checkout-place-order")).toHaveTextContent(
      c.review.codGuide.placeOrderCod,
    );
  });

  it("keeps the escrow explanation for online methods", () => {
    render(
      <StepReview
        locale="en"
        session={session}
        totals={eligible}
        payment={{ method: "momo", rail: "mtn", payer_number: "+260970000001" }}
        labels={reviewLabels}
        onPlaceOrder={vi.fn()}
      />,
    );

    expect(screen.getByText(c.review.escrowTitle)).toBeInTheDocument();
    expect(screen.queryByTestId("checkout-review-cod-steps")).not.toBeInTheDocument();
    expect(screen.getByTestId("checkout-place-order")).toHaveTextContent(c.review.placeOrder);
  });

  it("shows an applied coupon as a clear negative line above the total", () => {
    render(
      <StepReview
        locale="en"
        session={session}
        totals={{ ...eligible, discount_ngwee: 2_000, total_ngwee: 40_500, coupon_code: "SAVE20" }}
        payment={{ method: "momo", rail: "mtn", payer_number: "+260970000001" }}
        labels={{ ...reviewLabels, discount: c.review.discount }}
        onPlaceOrder={vi.fn()}
      />,
    );

    const line = screen.getByTestId("review-discount");
    expect(line).toHaveTextContent("Coupon SAVE20");
    expect(line).toHaveTextContent("−K20.00");
    expect(screen.getByText("K405.00")).toBeInTheDocument();
  });
});
