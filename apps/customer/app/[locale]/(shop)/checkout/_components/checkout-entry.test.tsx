// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import type { GroupCheckoutLabels } from "./group-checkout";
import type { CheckoutShellLabels } from "./step-fulfilment";

const query = { value: "" };
const useSessionSpy = vi.fn(() => ({ session: null, loading: true }));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => useSessionSpy(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(query.value),
}));
vi.mock("./group-checkout", () => ({
  GroupCheckout: () => <div data-testid="group-checkout-stub" />,
}));

const { CheckoutEntry } = await import("./checkout-entry");

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
  countdown: messages.countdown,
  reservationExpired: messages.reservationExpired,
  loading: messages.loading,
  error: messages.error,
  emptyCart: messages.emptyCart,
} as unknown as CheckoutShellLabels;
const groupLabels = {
  pageTitle: "Group",
  loading: "Loading group",
} as unknown as GroupCheckoutLabels;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CheckoutEntry", () => {
  it("never mounts the cart shell (session hook) for a ?group= handoff", async () => {
    query.value = "group=2f1c1a52-6a39-4e6c-9d57-0a7a9b1d5f11";
    render(<CheckoutEntry locale="en" labels={labels} groupLabels={groupLabels} />);
    expect(await screen.findByTestId("group-checkout-stub")).toBeInTheDocument();
    expect(useSessionSpy).not.toHaveBeenCalled();
  });

  it("mounts the cart shell when there is no group", () => {
    query.value = "";
    render(<CheckoutEntry locale="en" labels={labels} groupLabels={groupLabels} />);
    expect(useSessionSpy).toHaveBeenCalled();
  });
});
