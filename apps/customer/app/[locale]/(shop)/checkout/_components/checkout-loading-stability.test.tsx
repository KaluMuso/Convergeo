// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import type { CheckoutShellLabels } from "./step-fulfilment";

/**
 * Checkout loading layout-stability contract (Run #68 CLS).
 *
 * The checkout route's vitals sample sat at ~0.21 CLS against a 0.20 ceiling,
 * failing or passing on timing alone. The cause was structural: the
 * session-loading state rendered only a heading and a one-line "Loading…"
 * paragraph, then swapped in the full Stepper + first-step surface once
 * useSession resolved — a late shift of most of the viewport.
 *
 * These tests assert the geometry that arrives next is RESERVED while loading,
 * rather than asserting a CLS number (jsdom does no layout, and the E2E budget
 * is the place that measures). The invariant that was actually violated is
 * "the Stepper appears late", so that is what is pinned here.
 */

const sessionState = { session: null as { access_token: string } | null, loading: true };

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: sessionState.session, loading: sessionState.loading }),
}));

const push = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace, refresh: vi.fn() }),
}));

const { CheckoutShell } = await import("./step-fulfilment");

const messages = checkoutMessages.checkout;

// Nested groups are spread straight from the message catalogue so every leaf
// resolveLabels() reads is a real string. Renamed *Template keys are unused by
// the loading branch under test.
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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionState.session = null;
  sessionState.loading = true;
});

describe("checkout loading layout stability", () => {
  it("reserves the Stepper while the session is still resolving", () => {
    sessionState.loading = true;

    render(<CheckoutShell locale="en" labels={labels} />);

    // The exact geometry that used to arrive late and shift the page.
    expect(screen.getByText(messages.steps.contact)).toBeInTheDocument();
    expect(screen.getByText(messages.steps.fulfilment)).toBeInTheDocument();
    expect(screen.getByText(messages.steps.payment)).toBeInTheDocument();
    expect(screen.getByText(messages.steps.review)).toBeInTheDocument();
  });

  it("reserves the first-step surface while loading", () => {
    sessionState.loading = true;

    render(<CheckoutShell locale="en" labels={labels} />);

    expect(screen.getByTestId("checkout-loading-skeleton")).toBeInTheDocument();
  });

  it("keeps the page heading and outer rhythm identical to the resolved state", () => {
    sessionState.loading = true;
    const { container: loadingContainer } = render(<CheckoutShell locale="en" labels={labels} />);
    const loadingRoot = loadingContainer.firstElementChild;
    const loadingHeading = screen.getByRole("heading", { name: messages.pageTitle });
    expect(loadingHeading).toBeInTheDocument();

    cleanup();

    // Anonymous, resolved session: the real first-step surface.
    sessionState.loading = false;
    sessionState.session = null;
    const { container: resolvedContainer } = render(<CheckoutShell locale="en" labels={labels} />);
    const resolvedRoot = resolvedContainer.firstElementChild;

    // Same outer spacing class in both states — a different rhythm here is
    // itself a layout shift at the moment of the swap.
    expect(loadingRoot?.className).toBe(resolvedRoot?.className);
    expect(screen.getByRole("heading", { name: messages.pageTitle })).toBeInTheDocument();
  });

  it("announces loading accessibly without fabricating content", () => {
    sessionState.loading = true;

    render(<CheckoutShell locale="en" labels={labels} />);

    // Status still announced for assistive tech...
    const status = screen.getByText(messages.loading);
    expect(status).toHaveClass("sr-only");

    // ...while the placeholder shapes stay decorative: no skeleton may be
    // exposed as real content.
    const skeleton = screen.getByTestId("checkout-loading-skeleton");
    for (const placeholder of skeleton.querySelectorAll('[data-testid="skeleton"]')) {
      expect(placeholder.closest('[aria-hidden="true"]')).not.toBeNull();
    }
  });
});
