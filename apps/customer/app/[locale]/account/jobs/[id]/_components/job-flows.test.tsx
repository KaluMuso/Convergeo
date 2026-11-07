// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import servicesMessages from "../../../../../../../../packages/i18n/messages/en/services.json";

import { AcceptFlow, previewDepositNgwee } from "./accept-flow";
import { CompleteConfirm } from "./complete-confirm";
import { canAcceptQuote, shouldShowCompletion } from "./job-status";
import { ServicePayments } from "./service-payments";

import type { ReactNode } from "react";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  push: vi.fn(),
}));

vi.mock("../../../../../../lib/customer-session", () => ({
  customerAuth: {
    snapshot: () => ({
      session: { user: { id: "account-1" }, access_token: "token-1" },
      generation: 1,
    }),
  },
  useSession: () => ({
    loading: false,
    session: { user: { id: "account-1" }, access_token: "token-1" },
    generation: 1,
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@vergeo/config", () => {
  class ApiError extends Error {
    code: string;
    status: number;

    constructor(code: string, message: string, options: { status?: number } = {}) {
      super(message);
      this.code = code;
      this.status = options.status ?? 503;
    }
  }

  return {
    ApiError,
    createApiClient: () => ({
      request: (...args: unknown[]) => mocks.request(...args),
    }),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderWithServices(ui: ReactNode) {
  return render(
    <NextIntlClientProvider
      locale="en"
      messages={{ services: servicesMessages }}
      onError={() => {}}
    >
      {ui}
    </NextIntlClientProvider>,
  );
}

describe("job quote flow helpers", () => {
  it("gates accept and customer completion on existing service job states", () => {
    expect(canAcceptQuote("quoted", "submitted")).toBe(true);
    expect(canAcceptQuote("accepted", "submitted")).toBe(false);
    expect(canAcceptQuote("quoted", "accepted")).toBe(false);

    expect(shouldShowCompletion("accepted", "accepted")).toBe(true);
    expect(shouldShowCompletion("completed", "accepted")).toBe(false);
    expect(shouldShowCompletion("accepted", "submitted")).toBe(false);
  });

  it("previews the integer-ngwee deposit and redirects to service-deposit checkout", async () => {
    const user = userEvent.setup();
    mocks.request.mockResolvedValue({
      checkout_group_id: "checkout-1",
      order_id: "order-1",
      deposit_ngwee: 60_000,
      balance_ngwee: 60_000,
      total_job_ngwee: 120_000,
    });

    renderWithServices(
      <AcceptFlow
        locale="en"
        jobId="job-1"
        quoteId="quote-1"
        vendorName="Clean Team"
        totalNgwee={120_000}
      />,
    );

    expect(previewDepositNgwee(120_001, 50)).toBe(60_001);
    await user.click(screen.getByRole("button", { name: /pay deposit/i }));

    await waitFor(() => {
      expect(mocks.request).toHaveBeenCalledWith("/jobs/job-1/quotes/quote-1/accept", {
        method: "POST",
        body: JSON.stringify({}),
      });
    });
    expect(mocks.push).toHaveBeenCalledWith("/en/checkout?session=checkout-1&kind=service_deposit");
  });

  it("lets the API block customer confirmation until the provider marks complete", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@vergeo/config");
    mocks.request.mockRejectedValue(
      new ApiError("invalid_transition", "Not marked", { status: 409 }),
    );

    renderWithServices(<CompleteConfirm jobId="job-1" allowConfirmAttempt />);

    await user.click(screen.getByRole("button", { name: /confirm work/i }));

    expect(await screen.findByText(/provider has not marked/i)).toBeInTheDocument();
    expect(mocks.request).toHaveBeenCalledWith("/jobs/job-1/confirm", {
      method: "POST",
      body: JSON.stringify({}),
    });
  });
});

describe("mounted service balance funding", () => {
  it("shows the genuine 30000 deposit and 70000 balance; pending prevents a second payment", async () => {
    const user = userEvent.setup();
    let state = "unpaid";
    mocks.request.mockImplementation(async (path: string) => {
      if (path.endsWith("/payments"))
        return [
          {
            id: "deposit",
            leg: "deposit",
            amount_ngwee: 30000,
            status: "paid",
            can_pay: false,
          },
          {
            id: "balance",
            leg: "balance",
            amount_ngwee: 70000,
            status: state,
            checkout_group_id: "distinct-balance-checkout",
            can_pay: state === "unpaid" || state === "failed",
          },
        ];
      if (path === "/payments/retry") {
        state = "ussd_pushed";
        return { status: state };
      }
      throw new Error("Unexpected API path");
    });
    renderWithServices(<ServicePayments jobId="job-1" />);
    expect(await screen.findByText(/remaining balance.*700/i)).toBeInTheDocument();
    expect(screen.getByText(/deposit.*300/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/mobile money number/i), "0971111111");
    await user.selectOptions(screen.getByLabelText(/payment method/i), "airtel");
    await user.click(screen.getByRole("button", { name: "Pay outstanding amount" }));
    await waitFor(() => expect(screen.getByText("Payment pending")).toBeInTheDocument());
    expect(
      screen.queryByRole("button", { name: "Pay outstanding amount" }),
    ).not.toBeInTheDocument();
    expect(mocks.request).toHaveBeenCalledWith("/payments/retry", {
      method: "POST",
      body: JSON.stringify({
        checkout_group_id: "distinct-balance-checkout",
        payer_number: "0971111111",
        rail: "airtel",
      }),
    });
    state = "failed";
    await user.click(screen.getByRole("button", { name: "Refresh payment status" }));
    expect(await screen.findByRole("button", { name: "Retry payment" })).toBeInTheDocument();
    state = "paid";
    await user.click(screen.getByRole("button", { name: "Refresh payment status" }));
    await waitFor(() => expect(screen.getAllByText("Paid and verified")).toHaveLength(2));
    expect(screen.queryByRole("button", { name: "Retry payment" })).not.toBeInTheDocument();
  });

  it("acknowledgement does not display paid or unlock a review", async () => {
    const user = userEvent.setup();
    const onConfirmed = vi.fn();
    mocks.request.mockImplementation(async (path: string) =>
      path.endsWith("/payments")
        ? []
        : {
            status: "awaiting_payment",
            balance_ngwee: 70000,
            released: false,
          },
    );
    renderWithServices(<CompleteConfirm jobId="job-1" providerMarked onConfirmed={onConfirmed} />);
    await user.click(screen.getByRole("button", { name: /confirm work/i }));
    expect(await screen.findByText(/work acknowledged/i)).toBeInTheDocument();
    expect(onConfirmed).not.toHaveBeenCalled();
    expect(screen.queryByText(/now leave a review/i)).not.toBeInTheDocument();
  });
});
