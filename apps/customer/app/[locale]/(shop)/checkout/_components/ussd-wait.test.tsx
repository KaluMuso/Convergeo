// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import { PaymentFailed } from "./payment-failed";
import { UssdWait } from "./ussd-wait";

const ussdLabels = {
  title: checkoutMessages.checkout.ussd.title,
  subtitle: checkoutMessages.checkout.ussd.subtitle,
  amountLabel: checkoutMessages.checkout.ussd.amountLabel,
  mtnHelp: checkoutMessages.checkout.ussd.mtnHelp,
  airtelHelp: checkoutMessages.checkout.ussd.airtelHelp,
  genericHelp: checkoutMessages.checkout.ussd.genericHelp,
  waiting: checkoutMessages.checkout.ussd.waiting,
  doNotClose: checkoutMessages.checkout.ussd.doNotClose,
  pollAria: checkoutMessages.checkout.pending.pollAria,
};

const failedLabels = {
  timeoutTitle: checkoutMessages.checkout.pending.timeoutTitle,
  timeoutBody: checkoutMessages.checkout.pending.timeoutBody,
  retry: checkoutMessages.checkout.pending.retry,
  retrying: checkoutMessages.checkout.pending.retrying,
  retryError: checkoutMessages.checkout.pending.retryError,
  cancelledTitle: checkoutMessages.checkout.pending.cancelledTitle,
  cancelledBody: checkoutMessages.checkout.pending.cancelledBody,
  cancelledCta: checkoutMessages.checkout.pending.cancelledCta,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("UssdWait", () => {
  it("renders waiting state with formatted amount", () => {
    render(<UssdWait locale="en" amountNgwee={25_000} rail="mtn" labels={ussdLabels} />);

    expect(screen.getByTestId("ussd-wait")).toBeInTheDocument();
    expect(screen.getByText(checkoutMessages.checkout.ussd.title)).toBeInTheDocument();
    expect(screen.getByText("K250.00")).toBeInTheDocument();
    expect(
      screen.getByText(checkoutMessages.checkout.ussd.mtnHelp.replace("{amount}", "K250.00")),
    ).toBeInTheDocument();
  });
});

describe("PaymentFailed state transitions", () => {
  it("renders expired/failed retry UI", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();

    render(
      <PaymentFailed
        locale="en"
        amountNgwee={25_000}
        variant="expired"
        labels={failedLabels}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByTestId("payment-expired")).toBeInTheDocument();
    const retryButton = screen.getByTestId("payment-retry-button");
    await user.click(retryButton);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders cancelled guidance", () => {
    render(
      <PaymentFailed
        locale="en"
        amountNgwee={25_000}
        variant="cancelled"
        labels={failedLabels}
        onBackToCheckout={vi.fn()}
      />,
    );

    expect(screen.getByTestId("payment-cancelled")).toBeInTheDocument();
    expect(screen.getByText(checkoutMessages.checkout.pending.cancelledTitle)).toBeInTheDocument();
  });

  it("shows retry error message", () => {
    render(
      <PaymentFailed
        locale="en"
        amountNgwee={25_000}
        variant="failed"
        labels={failedLabels}
        errorMessage={failedLabels.retryError}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByTestId("payment-failed-error")).toHaveTextContent(failedLabels.retryError);
  });
});
