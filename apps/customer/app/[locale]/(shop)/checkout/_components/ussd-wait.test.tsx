// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import { PaymentFailed } from "./payment-failed";
import { PendingPaymentShell, UssdWait } from "./ussd-wait";

import type { PaymentStatusPayload, PendingLabels } from "./ussd-wait";

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

/**
 * PendingPaymentShell harness.
 *
 * Only the shell's three real boundaries are replaced — the Supabase session,
 * the API client and the Next router. Everything else (formatK, the labels,
 * resolveMomoPollOutcome, the rendered surfaces) is the production code.
 *
 * `next/navigation` is mocked through nested closures so the factory, which
 * vi.mock hoists above these declarations, never reads them at module-load
 * time — only when the component actually renders.
 */
const routerReplace = vi.fn<(href: string) => void>();
const routerPush = vi.fn<(href: string) => void>();
const apiRequest = vi.fn<(endpoint: string) => Promise<unknown>>();

/**
 * Recorded SYNCHRONOUSLY, inside router.replace itself.
 *
 * This is the ordering evidence: if the redirect is issued from the polling
 * callback (the S2 behaviour) the confirming node has not been committed yet
 * and this reads false; if it is issued from an effect that runs after the
 * commit, the node is already in the DOM and it reads true.
 */
const redirect = {
  confirmingInDomAtFirstReplace: null as boolean | null,
  targets: [] as string[],
};

vi.mock("../../../../../lib/customer-session", () => ({
  useSession: () => ({ session: { access_token: "test-access-token" }, loading: false }),
}));

vi.mock("next/navigation", () => {
  // ONE stable router instance, like Next's own useRouter. A fresh object per
  // render would change the identity of every effect dependency that holds the
  // router and re-run those effects — a mock artefact that would mask, not
  // expose, the ordering defect under test.
  const router = {
    replace: (href: string) => {
      if (redirect.confirmingInDomAtFirstReplace === null) {
        redirect.confirmingInDomAtFirstReplace =
          document.querySelector('[data-testid="payment-confirming"]') !== null;
      }
      redirect.targets.push(href);
      routerReplace(href);
    },
    push: (href: string) => routerPush(href),
    refresh: () => {},
  };
  return { useRouter: () => router };
});

// Only createApiClient is replaced — the real ApiError class is kept so the
// shell's `instanceof ApiError` branches stay meaningful.
vi.mock("@vergeo/config", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vergeo/config")>();
  return {
    ...actual,
    createApiClient: () => ({
      request: (endpoint: string) => apiRequest(endpoint),
    }),
  };
});

vi.mock("../../../../../lib/api-base-url", () => ({
  resolveApiBaseUrl: () => "https://api.test.invalid",
  getApiBaseUrl: () => "https://api.test.invalid",
}));

const pendingMessages = checkoutMessages.checkout.pending;

const pendingLabels: PendingLabels = {
  pageTitle: pendingMessages.pageTitle,
  loading: pendingMessages.loading,
  error: pendingMessages.error,
  pollAria: pendingMessages.pollAria,
  successRedirect: pendingMessages.successRedirect,
  confirmingTitle: pendingMessages.confirmingTitle,
  confirmingBody: pendingMessages.confirmingBody,
  codTitle: pendingMessages.codTitle,
  codBody: pendingMessages.codBody,
  codCta: pendingMessages.codCta,
  viewOrder: pendingMessages.viewOrder,
  ussd: ussdLabels,
  failed: failedLabels,
};

function statusPayload(overrides: Partial<PaymentStatusPayload> = {}): PaymentStatusPayload {
  return {
    checkout_group_id: "chk-e2e-1",
    payment_id: "pay-1",
    status: "ussd_pushed",
    amount_ngwee: 25_000,
    rail: "mtn",
    cod: false,
    order_id: "order-9",
    payer_phone: "+260970000001",
    ...overrides,
  };
}

/** Render the shell with `GET /payments/status` answering with `payload`. */
function renderPendingShell(payload: PaymentStatusPayload) {
  redirect.confirmingInDomAtFirstReplace = null;
  redirect.targets = [];
  apiRequest.mockImplementation(async (endpoint: string) => {
    if (endpoint.startsWith("/payments/status")) {
      return payload;
    }
    throw new Error(`unexpected endpoint in this test: ${endpoint}`);
  });

  render(<PendingPaymentShell locale="en" groupId="chk-e2e-1" labels={pendingLabels} />);
  return { replace: routerReplace, redirect };
}

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

/**
 * Payment-confirming commit ordering (S2 regression).
 *
 * `PendingPaymentShell` used to call `setStatusPayload(payload)` and
 * `router.replace(orderRoute)` back to back inside the polling callback, so
 * navigation could begin before React committed the state that renders the
 * honest `payment-confirming` surface — the buyer, and the E2E certification,
 * could be moved off the pending page without that surface ever existing.
 *
 * The evidence is `redirect.confirmingInDomAtFirstReplace`, sampled inside
 * router.replace itself: it answers "was the confirming surface already in the
 * document when navigation was issued?". Against the S2 single-effect version
 * that is false; the split effect makes it true by construction, with no
 * sleep, timer or artificial delay.
 */
describe("PendingPaymentShell — provider success commits payment-confirming before redirect", () => {
  it("renders payment-confirming, claims nothing paid, and only then redirects", async () => {
    const { replace, redirect: observed } = renderPendingShell(
      statusPayload({ status: "success" }),
    );

    // The honest confirming surface exists.
    const confirming = await screen.findByTestId("payment-confirming");
    expect(confirming).toBeInTheDocument();
    expect(screen.getByText(pendingMessages.confirmingTitle)).toBeInTheDocument();

    // It is NOT a final-paid representation.
    expect(screen.queryByTestId("payment-success")).toBeNull();
    expect(screen.queryByTestId("payment-card-success")).toBeNull();
    expect(screen.queryByTestId("payment-cod")).toBeNull();
    expect(screen.queryByText(/you paid|paid upfront|payment complete|paid in full/i)).toBeNull();

    // The authoritative order redirect still happens…
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/en/account/orders/order-9");
    });
    expect(replace).toHaveBeenCalledTimes(1);

    // …and the confirming surface was committed BEFORE it was issued. This is
    // the assertion the S2 implementation cannot satisfy.
    expect(observed.confirmingInDomAtFirstReplace).toBe(true);
  });

  it("falls back to the order list when the payload carries no order id", async () => {
    const { replace, redirect: observed } = renderPendingShell(
      statusPayload({ status: "success", order_id: "" }),
    );

    await screen.findByTestId("payment-confirming");
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/en/account/orders");
    });
    expect(observed.confirmingInDomAtFirstReplace).toBe(true);
  });

  it("does not redirect while the provider is still pushing — ussd-wait holds", async () => {
    const { replace } = renderPendingShell(statusPayload({ status: "ussd_pushed" }));

    await screen.findByTestId("ussd-wait");
    expect(screen.queryByTestId("payment-confirming")).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it("keeps COD on its own honest surface — never the confirming one", async () => {
    const { replace } = renderPendingShell(statusPayload({ status: "pending", cod: true }));

    await screen.findByTestId("payment-cod");
    expect(screen.queryByTestId("payment-confirming")).toBeNull();
    // The COD hand-off is the pre-existing 2.5s timer, not an immediate jump.
    expect(replace).not.toHaveBeenCalled();
  });

  it("a failed payment neither confirms nor redirects", async () => {
    const { replace } = renderPendingShell(statusPayload({ status: "failed" }));

    await screen.findByTestId("payment-failed");
    expect(screen.queryByTestId("payment-confirming")).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });
});
