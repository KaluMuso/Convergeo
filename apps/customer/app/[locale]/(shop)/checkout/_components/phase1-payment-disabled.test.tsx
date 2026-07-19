// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createTranslator } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import bemCheckout from "../../../../../../../packages/i18n/messages/bem/checkout.json";
import nyaCheckout from "../../../../../../../packages/i18n/messages/nya/checkout.json";

import { StepPayment, type PaymentOptions } from "./step-payment";

const paymentOptions: PaymentOptions = {
  session_id: "session-1",
  subtotal_ngwee: 60_000,
  delivery_fee_ngwee: 0,
  total_ngwee: 60_000,
  cod_cap_ngwee: 50_000,
  cod_eligible: true,
};

const requestMock = vi.fn();

vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, options: { status?: number } = {}) {
      super(message);
      this.code = code;
      this.status = options.status ?? 503;
    }
  },
  createApiClient: () => ({
    request: (...args: unknown[]) => requestMock(...args),
  }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function labelsFor(messages: typeof bemCheckout, locale: string) {
  const t = createTranslator({
    locale,
    messages: { checkout: messages },
    namespace: "checkout",
  });
  return {
    title: t("checkout.payment.title"),
    subtitle: t("checkout.payment.subtitle"),
    momo: t("checkout.payment.momo"),
    card: t("checkout.payment.card"),
    cod: t("checkout.payment.cod"),
    railMtn: t("checkout.payment.railMtn"),
    railAirtel: t("checkout.payment.railAirtel"),
    payerLabel: t("checkout.payment.payerLabel"),
    payerHelp: t("checkout.payment.payerHelp"),
    payerPlaceholder: t("checkout.payment.payerPlaceholder"),
    countryCode: t("checkout.payment.countryCode"),
    nationalNumber: t("checkout.payment.nationalNumber"),
    cardExplainer: t("checkout.payment.cardExplainer"),
    codIneligible: (cap: string) => t("checkout.payment.codIneligible", { cap }),
    continue: t("checkout.payment.continue"),
    loading: t("checkout.payment.loading"),
    required: t("checkout.payment.required"),
    invalidPayer: t("checkout.payment.invalidPayer"),
    railRequired: t("checkout.payment.railRequired"),
    codRejected: t("checkout.payment.codRejected"),
    railRejected: t("checkout.payment.railRejected"),
    error: t("checkout.payment.error"),
    paymentsDisabled: t("checkout.payment.paymentsDisabled"),
  };
}

describe("Phase-1 payment-disabled UI (bem/nya)", () => {
  it.each([
    ["bem", bemCheckout],
    ["nya", nyaCheckout],
  ] as const)("%s shows localised paymentsDisabled alert", async (locale, messages) => {
    const { ApiError } = await import("@vergeo/config");
    requestMock.mockImplementation(async (path: string, init?: { method?: string }) => {
      if (String(path).includes("payment-options")) {
        return paymentOptions;
      }
      if (init?.method === "POST") {
        throw new ApiError("payments_disabled", "Online payment is temporarily unavailable.", {
          status: 503,
        });
      }
      throw new Error(`unexpected ${path}`);
    });

    const labels = labelsFor(messages, locale);
    const user = userEvent.setup();
    render(
      <StepPayment
        locale={locale}
        sessionId="session-1"
        accessToken="token"
        labels={labels}
        onComplete={vi.fn()}
      />,
    );

    expect(await screen.findByText(labels.momo)).toBeInTheDocument();
    await user.click(screen.getByLabelText(labels.card));
    await user.click(screen.getByRole("button", { name: labels.continue }));

    await waitFor(() => {
      expect(screen.getByTestId("checkout-payment-error")).toHaveTextContent(
        messages.checkout.payment.paymentsDisabled,
      );
    });
    expect(screen.getByTestId("checkout-payment-error")).not.toHaveTextContent(
      "Online payment is temporarily unavailable",
    );
  });
});
