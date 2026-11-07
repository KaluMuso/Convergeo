// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@vergeo/config";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TicketCheckout } from "./ticket-checkout";

import type { CheckoutShellLabels } from "./step-fulfilment";

const GROUP = "00000000-0000-4000-8000-000000000001";
const ORDER = "00000000-0000-4000-8000-000000000002";
const PAYMENT = "00000000-0000-4000-8000-000000000003";
const { replace, request, loadTicketOrder, router } = vi.hoisted(() => ({
  replace: vi.fn(),
  request: vi.fn(),
  loadTicketOrder: vi.fn(),
  router: { replace: vi.fn() },
}));
const session: {
  loading: boolean;
  session: { access_token: string; user: { id: string } } | null;
} = {
  loading: false,
  session: { access_token: "test-token", user: { id: "buyer-id" } },
};

vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({ getBrowserClient: async () => ({}) }));
vi.mock("../../../../../lib/customer-session", () => ({ useSession: () => session }));
vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {
    constructor(public code: string) {
      super(code);
    }
  },
  createApiClient: () => ({ request }),
}));
vi.mock("../_lib/ticket-checkout", () => ({ loadTicketOrder }));

const labels = {
  pageTitle: "Checkout",
  loading: "Loading",
  error: "Checkout unavailable",
  contact: { sendOtp: "Sign in" },
  review: { total: "Total" },
  payment: {
    title: "Pay",
    momo: "Mobile money",
    card: "Card",
    railMtn: "MTN",
    railAirtel: "Airtel",
    payerLabel: "Payer number",
    payerPlaceholder: "Mobile number",
    cardExplainer: "Secure card",
    invalidPayer: "Invalid number",
    required: "Number required",
    loading: "Working",
    continue: "Continue",
    error: "Payment failed",
  },
} as CheckoutShellLabels;
const ticketLabels = {
  loginLabel: "Sign in",
  payLabel: "Get tickets",
  retryLabel: "Retry payment",
  cancelledLabel: "Payment cancelled",
  expiredLabel: "Payment timed out",
  ordersLabel: "View order",
};

function statusNotFound() {
  return new ApiError("payment.not_found", "No payment");
}

beforeEach(() => {
  session.session = { access_token: "test-token", user: { id: "buyer-id" } };
  router.replace = replace;
  request.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (path.startsWith("/payments/status")) throw statusNotFound();
    if (path.startsWith("/checkout/steps/payment-options"))
      return {
        session_id: GROUP,
        total_ngwee: 52_500,
        available_methods: ["momo", "card", "cod"],
      };
    if (path === "/checkout/steps/payment")
      return {
        session_id: GROUP,
        total_ngwee: 52_500,
        method: JSON.parse(String(options && (options as { body?: string }).body)).method,
      };
    if (path === "/payments/card/session")
      return { checkout_group_id: GROUP, payment_id: PAYMENT, amount_ngwee: 52_500 };
    if (path === "/payments/retry")
      return { checkout_group_id: GROUP, payment_id: PAYMENT, order_count: 1 };
    throw new Error(`Unexpected ${path}`);
  });
  loadTicketOrder.mockResolvedValue({
    groupId: GROUP,
    orderId: ORDER,
    title: "Evening ticket",
    qty: 2,
    totalNgwee: 52_500,
    status: "pending",
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ticket checkout mount", () => {
  it("rejects missing or malformed groups before API or payment", async () => {
    render(<TicketCheckout locale="en" groupId="bad" labels={labels} {...ticketLabels} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Checkout unavailable");
    expect(request).not.toHaveBeenCalled();
    expect(loadTicketOrder).not.toHaveBeenCalled();
  });

  it("fails closed when the existing ticket linkage is missing", async () => {
    loadTicketOrder.mockRejectedValue(new Error("missing item"));
    render(<TicketCheckout locale="en" groupId={GROUP} labels={labels} {...ticketLabels} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Checkout unavailable");
    expect(screen.queryByRole("button", { name: "Get tickets" })).not.toBeInTheDocument();
    expect(request.mock.calls.some(([path]) => path === "/checkout/steps/payment")).toBe(false);
  });

  it("does not offer COD and fails closed when only COD is available", async () => {
    request.mockImplementation(async (path: string) => {
      if (path.startsWith("/payments/status")) throw statusNotFound();
      return { session_id: GROUP, total_ngwee: 52_500, available_methods: ["cod"] };
    });
    render(<TicketCheckout locale="en" groupId={GROUP} labels={labels} {...ticketLabels} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Checkout unavailable");
    expect(screen.queryByText("Cash on Delivery")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Get tickets" })).not.toBeInTheDocument();
  });

  it("validates and starts one MoMo attempt for the existing group", async () => {
    const user = userEvent.setup();
    render(<TicketCheckout locale="en" groupId={GROUP} labels={labels} {...ticketLabels} />);
    const button = await screen.findByRole("button", { name: "Get tickets" });
    await user.click(button);
    expect(screen.getByRole("alert")).toHaveTextContent("Number required");
    await user.type(screen.getByLabelText("Payer number"), "971234567");
    await user.click(button);
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(`/en/checkout/pending/${GROUP}?ticket=1`),
    );
    const validation = request.mock.calls.find(([path]) => path === "/checkout/steps/payment");
    const initiation = request.mock.calls.find(([path]) => path === "/payments/retry");
    expect(JSON.parse(validation?.[1].body)).toMatchObject({ session_id: GROUP, method: "momo" });
    expect(JSON.parse(initiation?.[1].body)).toMatchObject({
      checkout_group_id: GROUP,
      rail: "mtn",
    });
    await user.click(button);
    expect(request.mock.calls.filter(([path]) => path === "/payments/retry")).toHaveLength(1);
  });

  it("uses the existing card session route and retains the ticket group", async () => {
    const user = userEvent.setup();
    render(<TicketCheckout locale="en" groupId={GROUP} labels={labels} {...ticketLabels} />);
    await user.click(await screen.findByLabelText("Card"));
    await user.click(screen.getByRole("button", { name: "Get tickets" }));
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(`/en/checkout/card/${PAYMENT}?group=${GROUP}`),
    );
    expect(request.mock.calls.some(([path]) => path === "/payments/retry")).toBe(false);
  });

  it("resumes an existing attempt on refresh without starting another", async () => {
    request.mockResolvedValue({
      checkout_group_id: GROUP,
      order_id: ORDER,
      payment_id: PAYMENT,
      status: "ussd_pushed",
      rail: "mtn",
      amount_ngwee: 52_500,
      cod: false,
    });
    render(<TicketCheckout locale="en" groupId={GROUP} labels={labels} {...ticketLabels} />);
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(`/en/checkout/pending/${GROUP}?ticket=1`),
    );
    expect(loadTicketOrder).toHaveBeenCalledWith({}, GROUP, "buyer-id", true);
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("shows an honest cancelled state without a dead retry or redirect loop", async () => {
    request.mockImplementation(async (path: string) => {
      if (path.startsWith("/payments/status"))
        return {
          checkout_group_id: GROUP,
          order_id: ORDER,
          payment_id: PAYMENT,
          status: "cancelled",
          rail: "mtn",
          amount_ngwee: 52_500,
          cod: false,
        };
      if (path.startsWith("/checkout/steps/payment-options"))
        return {
          session_id: GROUP,
          total_ngwee: 52_500,
          available_methods: ["momo", "card"],
        };
      throw new Error(`Unexpected ${path}`);
    });
    render(<TicketCheckout locale="en" groupId={GROUP} retry labels={labels} {...ticketLabels} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Payment cancelled");
    expect(screen.queryByRole("button", { name: "Retry payment" })).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
    expect(request.mock.calls.some(([path]) => path === "/checkout/steps/payment-options")).toBe(
      false,
    );
  });

  it("keeps the original Airtel rail on a terminal MoMo retry", async () => {
    request.mockImplementation(async (path: string) => {
      if (path.startsWith("/payments/status"))
        return {
          checkout_group_id: GROUP,
          order_id: ORDER,
          payment_id: PAYMENT,
          status: "failed",
          rail: "airtel",
          amount_ngwee: 52_500,
          cod: false,
        };
      if (path.startsWith("/checkout/steps/payment-options"))
        return {
          session_id: GROUP,
          total_ngwee: 52_500,
          available_methods: ["momo", "card"],
        };
      throw new Error(`Unexpected ${path}`);
    });
    render(<TicketCheckout locale="en" groupId={GROUP} retry labels={labels} {...ticketLabels} />);
    expect(await screen.findByRole("button", { name: "Retry payment" })).toBeInTheDocument();
    expect(screen.getByLabelText("Airtel")).toBeChecked();
    expect(screen.getByLabelText("MTN")).toBeDisabled();
    expect(screen.queryByLabelText("Card")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("rejects a status response linked to another order", async () => {
    request.mockResolvedValue({
      checkout_group_id: GROUP,
      order_id: "00000000-0000-4000-8000-000000000009",
      payment_id: PAYMENT,
      status: "success",
      rail: "card",
      amount_ngwee: 52_500,
      cod: false,
    });
    render(<TicketCheckout locale="en" groupId={GROUP} labels={labels} {...ticketLabels} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Checkout unavailable");
    expect(replace).not.toHaveBeenCalled();
  });

  it("rejects a mismatched initiation response without navigation", async () => {
    const user = userEvent.setup();
    request.mockImplementationOnce(async () => {
      throw statusNotFound();
    });
    request.mockImplementationOnce(async () => ({
      session_id: GROUP,
      total_ngwee: 52_500,
      available_methods: ["card"],
    }));
    request.mockImplementationOnce(async () => ({
      session_id: GROUP,
      total_ngwee: 52_500,
      method: "card",
    }));
    request.mockImplementationOnce(async () => ({
      checkout_group_id: GROUP,
      payment_id: PAYMENT,
      amount_ngwee: 1,
    }));
    render(<TicketCheckout locale="en" groupId={GROUP} labels={labels} {...ticketLabels} />);
    await user.click(await screen.findByRole("button", { name: "Get tickets" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Payment failed");
    expect(replace).not.toHaveBeenCalled();
  });

  it("stops before initiation if auth changes while validation is in flight", async () => {
    let release!: (value: unknown) => void;
    const validation = new Promise((resolve) => {
      release = resolve;
    });
    request.mockImplementationOnce(async () => {
      throw statusNotFound();
    });
    request.mockImplementationOnce(async () => ({
      session_id: GROUP,
      total_ngwee: 52_500,
      available_methods: ["card"],
    }));
    request.mockImplementationOnce(() => validation);
    const user = userEvent.setup();
    const view = render(
      <TicketCheckout locale="en" groupId={GROUP} labels={labels} {...ticketLabels} />,
    );
    await user.click(await screen.findByRole("button", { name: "Get tickets" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/checkout/steps/payment", expect.anything()),
    );
    session.session = null;
    view.rerender(<TicketCheckout locale="en" groupId={GROUP} labels={labels} {...ticketLabels} />);
    expect(screen.queryByRole("button", { name: "Get tickets" })).not.toBeInTheDocument();
    await act(async () => {
      release({ session_id: GROUP, total_ngwee: 52_500, method: "card" });
    });
    expect(request.mock.calls.some(([path]) => path === "/payments/card/session")).toBe(false);
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      `/${"en"}/login?next=${encodeURIComponent(`/en/checkout?group=${GROUP}`)}`,
    );
  });
});
