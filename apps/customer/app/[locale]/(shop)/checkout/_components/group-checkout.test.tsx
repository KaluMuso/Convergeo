// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import { GroupCheckout, type GroupCheckoutLabels } from "./group-checkout";

import type { CheckoutGroupSummary } from "../_lib/group-checkout";

const GROUP = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const ORDER = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const JOB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const PAYMENT = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";

const routerReplace = vi.fn<(href: string) => void>();
const apiRequest = vi.fn<(endpoint: string, init?: RequestInit) => Promise<unknown>>();
const sessionState = {
  session: { access_token: "tok" } as { access_token: string } | null,
  loading: false,
};

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => sessionState,
}));

vi.mock("next/navigation", () => {
  const router = {
    replace: (href: string) => routerReplace(href),
    push: vi.fn(),
    refresh: vi.fn(),
  };
  return { useRouter: () => router };
});

vi.mock("@vergeo/config", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vergeo/config")>();
  return {
    ...actual,
    createApiClient: () => ({
      request: (endpoint: string, init?: RequestInit) => apiRequest(endpoint, init),
    }),
  };
});

vi.mock("../../../../../lib/api-base-url", () => ({
  resolveApiBaseUrl: () => "https://api.test.invalid",
  getApiBaseUrl: () => "https://api.test.invalid",
}));

const c = checkoutMessages.checkout;
const g = c.group;
const { codIneligible, ...paymentRest } = c.payment;

const labels: GroupCheckoutLabels = {
  pageTitle: g.pageTitle,
  loading: g.loading,
  error: g.error,
  loginRequired: g.loginRequired,
  forbidden: g.forbidden,
  notFound: g.notFound,
  expired: g.expired,
  notPayable: g.notPayable,
  ticketHeading: g.ticketHeading,
  serviceHeading: g.serviceHeading,
  providerLabel: g.providerLabel,
  tierLineTemplate: g.tierLine,
  subtotal: g.subtotal,
  platformFee: g.platformFee,
  total: g.total,
  serviceNote: g.serviceNote,
  payCtaTemplate: g.payCta,
  viewOrder: g.viewOrder,
  escrowTitle: c.review.escrowTitle,
  escrowSteps: [c.review.escrowStep1, c.review.escrowStep2, c.review.escrowStep3],
  payment: { ...paymentRest, codIneligibleTemplate: codIneligible },
};

function ticketSummary(overrides: Partial<CheckoutGroupSummary> = {}): CheckoutGroupSummary {
  return {
    checkout_group_id: GROUP,
    kind: "ticket",
    status: "pending",
    expired: false,
    payable: true,
    order_id: ORDER,
    subtotal_ngwee: 30_000,
    delivery_fee_ngwee: 0,
    platform_fee_ngwee: 1_500,
    total_ngwee: 31_500,
    lines: [
      {
        order_item_id: "item-1",
        item_kind: "ticket",
        title: "Jazz Night — VIP",
        qty: 2,
        unit_price_ngwee: 15_000,
        line_total_ngwee: 30_000,
        ticket_type_name: "VIP",
      },
    ],
    event: {
      event_id: "event-1",
      title: "Jazz Night",
      slug: "jazz-night",
      venue: "Lusaka Playhouse",
      starts_at: "2026-12-01T18:00:00+00:00",
    },
    service: null,
    available_methods: ["momo", "card"],
    ...overrides,
  };
}

function serviceSummary(overrides: Partial<CheckoutGroupSummary> = {}): CheckoutGroupSummary {
  return ticketSummary({
    kind: "service_deposit",
    subtotal_ngwee: 120_000,
    platform_fee_ngwee: 0,
    total_ngwee: 120_000,
    lines: [
      {
        order_item_id: "item-2",
        item_kind: "service_deposit",
        title: null,
        qty: 1,
        unit_price_ngwee: 120_000,
        line_total_ngwee: 120_000,
        ticket_type_name: null,
      },
    ],
    event: null,
    service: {
      job_id: JOB,
      quote_id: "quote-1",
      vendor_id: "vendor-1",
      vendor_name: "Mwila Plumbing",
      category: "plumbing",
    },
    ...overrides,
  });
}

/** Route the mocked API: group summary, latest payment status, payment starts. */
function mockApi(summary: CheckoutGroupSummary | Error, status: unknown = null) {
  apiRequest.mockImplementation(async (endpoint) => {
    if (endpoint.startsWith("/checkout/groups/")) {
      if (summary instanceof Error) throw summary;
      return summary;
    }
    if (endpoint.startsWith("/payments/status")) {
      if (status) return status;
      const { ApiError } = await import("@vergeo/config");
      throw new ApiError("payment.not_found", "none", { status: 404 });
    }
    if (endpoint === "/payments/retry") {
      return {
        checkout_group_id: GROUP,
        payment_id: PAYMENT,
        status: "ussd_pushed",
        order_count: 1,
      };
    }
    if (endpoint === "/payments/card/session") {
      return {
        checkout_group_id: GROUP,
        payment_id: PAYMENT,
        amount_ngwee: 31_500,
      };
    }
    throw new Error(`unexpected ${endpoint}`);
  });
}

afterEach(() => {
  cleanup();
  routerReplace.mockReset();
  apiRequest.mockReset();
  sessionState.session = { access_token: "tok" };
  sessionState.loading = false;
});

describe("GroupCheckout", () => {
  it("renders a paid-ticket group with tiers, buyer-paid fee and online rails only", async () => {
    mockApi(ticketSummary());
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);

    expect(await screen.findByTestId("group-summary-ticket")).toBeInTheDocument();
    expect(screen.getByText("Jazz Night")).toBeInTheDocument();
    expect(screen.getByText("VIP × 2")).toBeInTheDocument();
    expect(screen.getByTestId("group-platform-fee")).toHaveTextContent("15.00");
    expect(screen.getByTestId("group-total")).toHaveTextContent("315.00");
    expect(screen.getByText(c.payment.momo)).toBeInTheDocument();
    expect(screen.getByText(c.payment.card)).toBeInTheDocument();
    expect(screen.queryByText(c.payment.cod)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pay k\s?315\.00/i })).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledWith(`/checkout/groups/${GROUP}`, undefined);
  });

  it("renders a service group with the API amount and provider, no fee row", async () => {
    mockApi(serviceSummary());
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);

    expect(await screen.findByTestId("group-summary-service_deposit")).toBeInTheDocument();
    expect(screen.getByText("Mwila Plumbing")).toBeInTheDocument();
    expect(screen.getByTestId("group-total")).toHaveTextContent("1,200.00");
    expect(screen.queryByTestId("group-platform-fee")).not.toBeInTheDocument();
  });

  it("shows a friendly error when the group belongs to someone else (403)", async () => {
    const { ApiError } = await import("@vergeo/config");
    mockApi(new ApiError("forbidden", "no", { status: 403 }));
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);

    expect(await screen.findByTestId("group-checkout-error")).toHaveTextContent(g.forbidden);
    expect(screen.queryByRole("button", { name: /pay/i })).not.toBeInTheDocument();
  });

  it("blocks payment on an expired group", async () => {
    mockApi(ticketSummary({ status: "expired", expired: true, payable: false }));
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);

    expect(await screen.findByTestId("group-checkout-closed")).toHaveTextContent(g.expired);
    expect(screen.queryByText(c.payment.momo)).not.toBeInTheDocument();
  });

  it("rejects a malformed group id without calling the API", async () => {
    render(<GroupCheckout locale="en" groupId="not-a-uuid" labels={labels} />);
    expect(await screen.findByTestId("group-checkout-error")).toHaveTextContent(g.notFound);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("starts an Airtel MoMo push for the group and goes to the pending screen", async () => {
    const user = userEvent.setup();
    mockApi(ticketSummary());
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);

    await user.click(await screen.findByText(c.payment.railAirtel));
    await user.type(screen.getByLabelText(c.payment.nationalNumber), "971234567");
    await user.click(screen.getByRole("button", { name: /pay k\s?315\.00/i }));

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(`/en/checkout/pending/${GROUP}?kind=ticket`),
    );
    const retry = apiRequest.mock.calls.find(([endpoint]) => endpoint === "/payments/retry");
    expect(JSON.parse(String(retry?.[1]?.body))).toEqual({
      checkout_group_id: GROUP,
      payer_number: "+260971234567",
      rail: "airtel",
    });
  });

  it("opens the Lenco card session for a service group and keeps the job context", async () => {
    const user = userEvent.setup();
    mockApi(serviceSummary());
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);

    await user.click(await screen.findByText(c.payment.card));
    await user.click(screen.getByRole("button", { name: /pay k\s?1,200\.00/i }));

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(
        `/en/checkout/card/${PAYMENT}?group=${GROUP}&kind=service_deposit&job=${JOB}`,
      ),
    );
    expect(apiRequest).toHaveBeenCalledWith("/payments/card/session", {
      method: "POST",
      body: JSON.stringify({ checkout_group_id: GROUP }),
    });
  });

  it("validates the payer number before any payment call", async () => {
    const user = userEvent.setup();
    mockApi(ticketSummary());
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);

    await user.click(await screen.findByRole("button", { name: /pay k/i }));
    expect(await screen.findByText(c.payment.required)).toBeInTheDocument();
    expect(apiRequest.mock.calls.some(([e]) => e === "/payments/retry")).toBe(false);
  });

  it("resumes a live MoMo attempt instead of offering rails again", async () => {
    mockApi(ticketSummary(), {
      checkout_group_id: GROUP,
      payment_id: PAYMENT,
      status: "ussd_pushed",
      rail: "mtn",
      cod: false,
      order_id: ORDER,
    });
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(`/en/checkout/pending/${GROUP}?kind=ticket`),
    );
  });

  it("shows the payments-off notice when the API offers no online rail", async () => {
    mockApi(serviceSummary({ available_methods: [] }));
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);
    expect(await screen.findByTestId("checkout-payments-off")).toBeInTheDocument();
  });

  it("asks a signed-out buyer to sign in and come back to this group", async () => {
    sessionState.session = null;
    render(<GroupCheckout locale="en" groupId={GROUP} labels={labels} />);
    const link = await screen.findByRole("link", { name: g.loginRequired });
    expect(link.getAttribute("href")).toBe(
      `/en/login?next=${encodeURIComponent(`/en/checkout?group=${GROUP}`)}`,
    );
  });
});
