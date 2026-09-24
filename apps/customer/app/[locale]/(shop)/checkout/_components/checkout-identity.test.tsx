// @vitest-environment jsdom
/** Mounted regressions promoted from the independent A review. */
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import type { CheckoutShellLabels } from "./step-fulfilment";

const state = vi.hoisted(() => ({
  session: {
    access_token: "token-account-a",
    user: { id: "account-a", phone: "+260971000001" },
  } as { access_token: string; user: { id: string; phone: string } } | null,
  loading: false,
  generation: 1,
  error: null,
}));
const request = vi.hoisted(() => vi.fn());

vi.mock("../../../../../lib/customer-session", () => ({
  useSession: () => ({ ...state }),
  customerAuth: { snapshot: () => ({ ...state }) },
  getReadyCustomerSession: async () => state.session,
}));
vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {
    code: string;
    details: Record<string, unknown>;
    constructor(
      code: string,
      message: string,
      options: { details?: Record<string, unknown> } = {},
    ) {
      super(message);
      this.code = code;
      this.details = options.details ?? {};
    }
  },
  createApiClient: ({ getToken }: { getToken: () => string }) => ({
    request: (path: string, options: unknown) => request(getToken(), path, options),
  }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("./step-contact", () => ({ StepContact: () => null }));

const { CheckoutShell } = await import("./step-fulfilment");
const messages = checkoutMessages.checkout;
const labels = {
  pageTitle: messages.pageTitle,
  stepAnnouncementTemplate: messages.stepAnnouncement,
  doneIndicator: messages.doneIndicator,
  steps: messages.steps,
  contact: messages.contact,
  fulfilment: messages.fulfilment,
  payment: messages.payment,
  review: messages.review,
  countdown: { ...messages.countdown, ariaLiveTemplate: messages.countdown.ariaLive },
  reservationExpired: messages.reservationExpired,
  loading: messages.loading,
  error: messages.error,
  emptyCart: messages.emptyCart,
} as unknown as CheckoutShellLabels;

afterEach(() => {
  cleanup();
  request.mockReset();
  state.generation = 1;
  state.loading = false;
  state.session = {
    access_token: "token-account-a",
    user: { id: "account-a", phone: "+260971000001" },
  };
});

const checkout = (name: string) => ({
  session_id: `${name}-checkout`,
  expires_at: new Date(Date.now() + 900_000).toISOString(),
  reservation_ttl_min: 15,
  subtotal_ngwee: 10_000,
  contact_skipped: true,
  vendor_groups: [
    {
      vendor_id: name,
      vendor_name: name,
      items: [],
      subtotal_ngwee: 10_000,
      delivery_eligible: false,
      pickup_location: null,
    },
  ],
});

for (const nextAccount of ["account-b", "account-a"]) {
  for (const staleResult of ["success", "error"]) {
    it(`rejects stale ${staleResult} after logout and ${nextAccount} sign in`, async () => {
      let resolveA!: (value: unknown) => void;
      let rejectA!: (error: Error) => void;
      let resolveB!: (value: unknown) => void;
      request.mockReturnValueOnce(
        new Promise((resolve, reject) => {
          resolveA = resolve;
          rejectA = reject;
        }),
      );
      request.mockReturnValueOnce(
        new Promise((resolve) => {
          resolveB = resolve;
        }),
      );
      const view = render(<CheckoutShell locale="en" labels={labels} />);
      await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
      state.session = null;
      state.generation++;
      view.rerender(<CheckoutShell locale="en" labels={labels} />);
      state.session = {
        access_token: "new-token",
        user: { id: nextAccount, phone: "+260971000002" },
      };
      state.generation++;
      view.rerender(<CheckoutShell locale="en" labels={labels} />);
      await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
      await act(async () => {
        if (staleResult === "success") resolveA(checkout("Private A Vendor"));
        else rejectA(new Error("old failure"));
      });
      expect(screen.queryByText("Private A Vendor")).not.toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.getByTestId("checkout-loading-skeleton")).toBeInTheDocument();
      await act(async () => resolveB(checkout("Current Vendor")));
      expect(screen.getByText("Current Vendor")).toBeInTheDocument();
      expect(request).toHaveBeenCalledTimes(2);
      state.session = null;
      state.generation++;
      state.loading = true;
      view.rerender(<CheckoutShell locale="en" labels={labels} />);
      expect(screen.queryByText("Current Vendor")).not.toBeInTheDocument();
    });
  }
}
