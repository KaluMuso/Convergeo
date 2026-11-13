// @vitest-environment jsdom
/**
 * A cart over the COD cap while online payments are off can be paid no way at
 * all. The buyer is told at checkout start, not after filling in fulfilment.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import bemMessages from "../../../../../../../packages/i18n/messages/bem/checkout.json";
import enMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";
import frMessages from "../../../../../../../packages/i18n/messages/fr/checkout.json";
import nyaMessages from "../../../../../../../packages/i18n/messages/nya/checkout.json";
import zhMessages from "../../../../../../../packages/i18n/messages/zh/checkout.json";

import type { CheckoutShellLabels } from "./step-fulfilment";

const state = vi.hoisted(() => ({
  session: { access_token: "token", user: { id: "buyer", phone: "+260971000001" } },
  loading: false,
  generation: 1,
  error: null,
}));
const options = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock("../../../../../lib/customer-session", () => ({
  useSession: () => ({ ...state }),
  customerAuth: { snapshot: () => ({ ...state }) },
  getReadyCustomerSession: async () => state.session,
}));
vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {},
  createApiClient: () => ({
    request: (path: string) => {
      if (path === "/checkout/steps/contact") return Promise.resolve({ verified: true });
      if (path === "/checkout/session") {
        return Promise.resolve({
          session_id: "over-cap",
          expires_at: new Date(Date.now() + 900_000).toISOString(),
          reservation_ttl_min: 15,
          subtotal_ngwee: 80_000,
          contact_skipped: true,
          vendor_groups: [
            {
              vendor_id: "v1",
              vendor_name: "Kalingalinga Fabrics",
              items: [],
              subtotal_ngwee: 80_000,
              delivery_eligible: false,
              pickup_location: null,
            },
          ],
        });
      }
      if (path.startsWith("/checkout/steps/payment-options")) {
        return Promise.resolve(options.current);
      }
      return Promise.reject(new Error(`unexpected ${path}`));
    },
  }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

const { CheckoutShell } = await import("./step-fulfilment");

function labelsFor(catalogue: typeof enMessages): CheckoutShellLabels {
  const m = catalogue.checkout;
  return {
    pageTitle: m.pageTitle,
    stepAnnouncementTemplate: m.stepAnnouncement,
    doneIndicator: m.doneIndicator,
    steps: m.steps,
    contact: m.contact,
    fulfilment: m.fulfilment,
    payment: m.payment,
    review: m.review,
    countdown: { ...m.countdown, ariaLiveTemplate: m.countdown.ariaLive },
    reservationExpired: m.reservationExpired,
    loading: m.loading,
    error: m.error,
    emptyCart: m.emptyCart,
    backToCart: enMessages.checkout.backToCart,
    overCodCapTemplate: m.overCodCap,
  } as unknown as CheckoutShellLabels;
}

const payable = {
  session_id: "over-cap",
  subtotal_ngwee: 80_000,
  delivery_fee_ngwee: 0,
  total_ngwee: 80_000,
  cod_cap_ngwee: 50_000,
};

afterEach(() => {
  cleanup();
});

describe("checkout start over the COD cap", () => {
  it("says up front that nothing can take this total while online payment is off", async () => {
    options.current = { ...payable, cod_eligible: false, available_methods: [] };
    render(<CheckoutShell locale="en" labels={labelsFor(enMessages)} />);

    const notice = await screen.findByTestId("checkout-over-cod-cap");
    expect(notice).toHaveTextContent(enMessages.checkout.overCodCap.replace("{cap}", "K500.00"));
    expect(notice).toHaveRole("status");
    expect(screen.getByRole("link", { name: enMessages.checkout.backToCart })).toHaveAttribute(
      "href",
      "/en/cart",
    );
    expect(await screen.findByText("Kalingalinga Fabrics")).toBeInTheDocument();
  });

  it("stays quiet when some payment method can still take the order", async () => {
    options.current = { ...payable, cod_eligible: false, available_methods: ["momo", "card"] };
    render(<CheckoutShell locale="en" labels={labelsFor(enMessages)} />);

    expect(await screen.findByText("Kalingalinga Fabrics")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId("checkout-over-cod-cap")).toBeNull());
  });

  it.each([
    ["bem", bemMessages],
    ["nya", nyaMessages],
    ["fr", frMessages],
    ["zh", zhMessages],
  ])("has a %s notice that names the cap", (_locale, catalogue) => {
    const template = (catalogue as typeof enMessages).checkout.overCodCap;
    expect(template).toContain("{cap}");
    expect(template).not.toBe(enMessages.checkout.overCodCap);
  });
});
