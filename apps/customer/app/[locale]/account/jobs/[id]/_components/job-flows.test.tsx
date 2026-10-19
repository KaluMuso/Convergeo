// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { Suspense } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import servicesMessages from "../../../../../../../../packages/i18n/messages/en/services.json";
import JobPage from "../page";

import { AcceptFlow, previewDepositNgwee } from "./accept-flow";
import { CompleteConfirm } from "./complete-confirm";
import { canAcceptQuote, shouldShowCompletion } from "./job-status";
import { ServicePayments } from "./service-payments";

import type { ReactNode } from "react";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  push: vi.fn(),
  auth: {
    session: { user: { id: "account-1" }, access_token: "token-1" },
    generation: 1,
    loading: false,
    error: null,
  },
}));

vi.mock("../../../../../../lib/customer-session", () => ({
  customerAuth: {
    snapshot: () => mocks.auth,
  },
  useSession: () => mocks.auth,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));
vi.mock("./service-review-form", () => ({ ServiceReviewForm: () => null }));

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
  mocks.auth.generation = 1;
  mocks.auth.session = { user: { id: "account-1" }, access_token: "token-1" };
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
    expect(mocks.push).toHaveBeenCalledWith("/en/account/jobs/job-1");
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

describe("actual mounted job funding transition", () => {
  const quote = {
    id: "quote-1",
    amount_ngwee: 100000,
    message: null,
    expires_at: null,
    created_at: "2026-10-01T00:00:00Z",
    provider: null,
  };
  const leg = {
    id: "deposit",
    job_id: "job-1",
    order_id: "order-1",
    checkout_group_id: "group-1",
    leg: "deposit",
    amount_ngwee: 50000,
    status: "unpaid",
    payment_id: null,
    can_pay: true,
  };
  async function mountJob() {
    const params = Promise.resolve({ locale: "en", id: "job-1" });
    await act(async () => {
      renderWithServices(
        <Suspense fallback={null}>
          <JobPage params={params} />
        </Suspense>,
      );
      await params;
    });
  }

  it("a fresh accepted job renders funding through the real completion component", async () => {
    mocks.request.mockImplementation(async (path: string) => {
      if (path === "/jobs/job-1") return { id: "job-1", status: "accepted" };
      if (path === "/jobs/job-1/quotes")
        return { items: [{ ...quote, status: "accepted" }], view: "customer_compare" };
      if (path === "/jobs/job-1/payments") return [leg];
      throw new Error("Unexpected job destination endpoint");
    });
    await mountJob();
    expect(await screen.findByRole("region", { name: "Service payments" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Pay outstanding amount" }),
    ).toBeInTheDocument();
    expect(mocks.request.mock.calls.some(([path]) => path.endsWith("/accept"))).toBe(false);
  });

  it("success releases the real parent's pending marker and reaches funding without remount or a second acceptance", async () => {
    const user = userEvent.setup();
    let accepted = false;
    let resolveQuotes!: (value: {
      items: Array<typeof quote & { status: string }>;
      view: string;
    }) => void;
    const refreshedQuotes = new Promise((resolve) => {
      resolveQuotes = resolve;
    });
    mocks.request.mockImplementation(async (path: string) => {
      if (path === "/jobs/job-1") return { id: "job-1", status: accepted ? "accepted" : "quoted" };
      if (path === "/jobs/job-1/quotes")
        return accepted
          ? refreshedQuotes
          : { items: [{ ...quote, status: "submitted" }], view: "customer_compare" };
      if (path === "/jobs/job-1/quotes/quote-1/accept") {
        accepted = true;
        return { checkout_group_id: "group-1" };
      }
      if (path === "/jobs/job-1/payments") return [leg];
      throw new Error("Unexpected mounted acceptance endpoint");
    });
    await mountJob();
    await user.click(await screen.findByRole("button", { name: /pay deposit/i }));
    await waitFor(() =>
      expect(
        mocks.request.mock.calls.filter(([path]) => path === "/jobs/job-1/quotes"),
      ).toHaveLength(2),
    );
    // The accepted request stays guarded until the authoritative refresh removes it.
    await user.click(screen.getByRole("button", { name: /setting up your deposit/i }));
    expect(mocks.request.mock.calls.filter(([path]) => path.endsWith("/accept"))).toHaveLength(1);
    await act(async () =>
      resolveQuotes({ items: [{ ...quote, status: "accepted" }], view: "customer_compare" }),
    );
    expect(await screen.findByRole("region", { name: "Service payments" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Pay outstanding amount" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /setting up your deposit/i }),
    ).not.toBeInTheDocument();
  });
});

describe("mounted service balance funding", () => {
  it("discards a pre-initiation failed read after a newer pending read instead of submitting twice", async () => {
    const user = userEvent.setup();
    const failed = {
      id: "balance",
      checkout_group_id: "balance-group",
      leg: "balance",
      amount_ngwee: 70000,
      status: "failed",
      payment_id: "old-failed",
      can_pay: true,
    };
    const pending = { ...failed, status: "initiated", payment_id: "attempt-1", can_pay: false };
    let resolveOld!: (value: (typeof failed)[]) => void;
    const oldRead = new Promise<(typeof failed)[]>((resolve) => {
      resolveOld = resolve;
    });
    let reads = 0;
    mocks.request.mockImplementation((path: string) => {
      if (path === "/jobs/job-1/payments") {
        reads++;
        return reads === 1
          ? Promise.resolve([failed])
          : reads === 2
            ? oldRead
            : Promise.resolve([pending]);
      }
      if (path === "/payments/card/session") return Promise.resolve({ payment_id: "attempt-1" });
      throw new Error("Unexpected overlapping-read endpoint");
    });
    renderWithServices(<ServicePayments jobId="job-1" />);
    await screen.findByRole("button", { name: "Retry payment" });
    await user.selectOptions(screen.getByLabelText(/payment method/i), "card");
    await user.click(screen.getByRole("button", { name: "Refresh payment status" }));
    await user.click(screen.getByRole("button", { name: "Retry payment" }));
    await screen.findByText("Payment pending");
    await act(async () => resolveOld([failed]));
    const staleRetry = screen.queryByRole("button", { name: "Retry payment" });
    if (staleRetry) await user.click(staleRetry);
    expect(
      mocks.request.mock.calls.filter(([path]) => path === "/payments/card/session"),
    ).toHaveLength(1);
    expect(screen.getByText("Payment pending")).toBeInTheDocument();
  });

  it("only clears a successful initiation latch for a fresh terminal failure of that exact new attempt", async () => {
    const user = userEvent.setup();
    const leg = {
      id: "balance",
      checkout_group_id: "balance-group",
      leg: "balance",
      amount_ngwee: 70000,
      status: "failed",
      payment_id: "old-failed",
      can_pay: true,
    };
    let snapshot = leg;
    let starts = 0;
    mocks.request.mockImplementation(async (path: string) => {
      if (path === "/jobs/job-1/payments") return [snapshot];
      if (path === "/payments/card/session") {
        starts++;
        return { payment_id: `attempt-${starts}` };
      }
      throw new Error("Unexpected attempt-bound retry endpoint");
    });
    renderWithServices(<ServicePayments jobId="job-1" />);
    await screen.findByRole("button", { name: "Retry payment" });
    await user.selectOptions(screen.getByLabelText(/payment method/i), "card");
    await user.click(screen.getByRole("button", { name: "Retry payment" }));
    // Even a read started after mutation must not treat the old attempt's failure as retry permission.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Retry payment" })).toBeDisabled(),
    );
    await user.click(screen.getByRole("button", { name: "Refresh payment status" }));
    expect(screen.getByRole("button", { name: "Retry payment" })).toBeDisabled();
    snapshot = { ...leg, payment_id: "attempt-1" };
    await user.click(screen.getByRole("button", { name: "Refresh payment status" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Retry payment" })).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: "Retry payment" }));
    expect(starts).toBe(2);
  });

  it("ignores an older same-attempt terminal response after a newer pending poll has applied", async () => {
    const user = userEvent.setup();
    const original = {
      id: "balance",
      checkout_group_id: "balance-group",
      leg: "balance",
      amount_ngwee: 70000,
      status: "failed",
      payment_id: "old-failed",
      can_pay: true,
    };
    const pending = { ...original, status: "initiated", payment_id: "attempt-1", can_pay: false };
    let resolveOlder!: (value: (typeof original)[]) => void;
    const older = new Promise<(typeof original)[]>((resolve) => {
      resolveOlder = resolve;
    });
    let reads = 0;
    mocks.request.mockImplementation((path: string) => {
      if (path === "/jobs/job-1/payments") {
        reads++;
        return reads === 1
          ? Promise.resolve([original])
          : reads === 3
            ? older
            : Promise.resolve([pending]);
      }
      if (path === "/payments/card/session") return Promise.resolve({ payment_id: "attempt-1" });
      throw new Error("Unexpected sequenced-poll endpoint");
    });
    renderWithServices(<ServicePayments jobId="job-1" />);
    await screen.findByRole("button", { name: "Retry payment" });
    await user.selectOptions(screen.getByLabelText(/payment method/i), "card");
    await user.click(screen.getByRole("button", { name: "Retry payment" }));
    await screen.findByText("Payment pending");
    await user.click(screen.getByRole("button", { name: "Refresh payment status" }));
    await user.click(screen.getByRole("button", { name: "Refresh payment status" }));
    expect(reads).toBe(4);
    await act(async () => resolveOlder([{ ...original, payment_id: "attempt-1" }]));
    expect(screen.queryByRole("button", { name: "Retry payment" })).not.toBeInTheDocument();
    expect(screen.getByText("Payment pending")).toBeInTheDocument();
    expect(
      mocks.request.mock.calls.filter(([path]) => path === "/payments/card/session"),
    ).toHaveLength(1);
  });

  it("does not navigate from an initiation completed after an ABA auth transition", async () => {
    const user = userEvent.setup();
    let resolveAttempt!: (value: { payment_id: string }) => void;
    mocks.request.mockImplementation((path: string) => {
      if (path === "/jobs/job-1/payments")
        return Promise.resolve([
          {
            id: "balance",
            checkout_group_id: "balance-group",
            leg: "balance",
            amount_ngwee: 70000,
            status: "unpaid",
            payment_id: null,
            can_pay: true,
          },
        ]);
      if (path === "/payments/card/session")
        return new Promise((resolve) => {
          resolveAttempt = resolve;
        });
      throw new Error("Unexpected endpoint");
    });
    renderWithServices(<ServicePayments jobId="job-1" />);
    await screen.findByRole("button", { name: "Pay outstanding amount" });
    await user.selectOptions(screen.getByLabelText(/payment method/i), "card");
    await user.click(screen.getByRole("button", { name: "Pay outstanding amount" }));
    mocks.auth.generation = 3;
    resolveAttempt({ payment_id: "stale-attempt" });
    await waitFor(() =>
      expect(
        mocks.request.mock.calls.filter(([path]) => path === "/payments/card/session"),
      ).toHaveLength(1),
    );
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("carries the authorized job as a lookup hint when starting a card attempt", async () => {
    const user = userEvent.setup();
    mocks.request.mockImplementation(async (path: string) => {
      if (path === "/jobs/job-1/payments")
        return [
          {
            id: "balance",
            checkout_group_id: "balance-group",
            leg: "balance",
            amount_ngwee: 70000,
            status: "unpaid",
            payment_id: null,
            can_pay: true,
          },
        ];
      if (path === "/payments/card/session") return { payment_id: "card-attempt" };
      throw new Error("Unexpected endpoint");
    });
    renderWithServices(<ServicePayments jobId="job-1" />);
    await screen.findByRole("button", { name: "Pay outstanding amount" });
    await user.selectOptions(screen.getByLabelText(/payment method/i), "card");
    await user.dblClick(screen.getByRole("button", { name: "Pay outstanding amount" }));
    await waitFor(() =>
      expect(mocks.push).toHaveBeenCalledWith("/en/checkout/card/card-attempt?job=job-1"),
    );
    expect(
      mocks.request.mock.calls.filter(([path]) => path === "/payments/card/session"),
    ).toHaveLength(1);
  });

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
            payment_id: state === "unpaid" ? null : "balance-attempt",
            checkout_group_id: "distinct-balance-checkout",
            can_pay: state === "unpaid" || state === "failed",
          },
        ];
      if (path === "/payments/retry") {
        state = "ussd_pushed";
        return {
          status: state,
          payment_id: "balance-attempt",
          checkout_group_id: "distinct-balance-checkout",
        };
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
