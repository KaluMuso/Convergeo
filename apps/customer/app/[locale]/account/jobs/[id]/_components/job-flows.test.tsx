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

import type { ReactNode } from "react";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  push: vi.fn(),
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    loading: false,
    session: { access_token: "token-1" },
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

  it("accepts without computing a deposit and redirects to the group checkout", async () => {
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
    // The amount due is the API's (pilot: 100% upfront) — no client-side deposit preview.
    expect(screen.queryByText(/deposit due now/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /accept and pay/i }));

    await waitFor(() => {
      expect(mocks.request).toHaveBeenCalledWith("/jobs/job-1/quotes/quote-1/accept", {
        method: "POST",
        body: JSON.stringify({}),
      });
    });
    expect(mocks.push).toHaveBeenCalledWith("/en/checkout?group=checkout-1");
  });

  it("lets the API block customer confirmation until the provider marks complete", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@vergeo/config");
    mocks.request.mockRejectedValue(
      new ApiError("invalid_transition", "Not marked", { status: 409 }),
    );

    renderWithServices(<CompleteConfirm jobId="job-1" balanceNgwee={60_000} allowConfirmAttempt />);

    await user.click(screen.getByRole("button", { name: /confirm and pay/i }));

    expect(await screen.findByText(/provider has not marked/i)).toBeInTheDocument();
    expect(mocks.request).toHaveBeenCalledWith("/jobs/job-1/confirm", {
      method: "POST",
      body: JSON.stringify({}),
    });
  });

  it("renders the API balance due and hides the balance line when it is zero", () => {
    const { rerender } = renderWithServices(
      <CompleteConfirm jobId="job-1" balanceNgwee={125_000} allowConfirmAttempt />,
    );
    expect(screen.getByText(/balance due on completion/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm and pay/i })).toBeInTheDocument();

    rerender(
      <NextIntlClientProvider locale="en" messages={{ services: servicesMessages }}>
        <CompleteConfirm jobId="job-1" balanceNgwee={0} allowConfirmAttempt />
      </NextIntlClientProvider>,
    );
    expect(screen.queryByText(/balance due on completion/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm the work is done/i })).toBeInTheDocument();
  });
});
