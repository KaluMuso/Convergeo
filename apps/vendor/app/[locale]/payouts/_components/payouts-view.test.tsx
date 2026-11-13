import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it, vi } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";

import { PayoutsView } from "./payouts-view";

import type { PayoutBalances } from "../_lib/payouts-client";

const { getBalances, getHistory } = vi.hoisted(() => ({
  getBalances: vi.fn(),
  getHistory: vi.fn(),
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: { access_token: "test-token", user: { id: "vendor-1" } },
    loading: false,
  }),
}));
vi.mock("../_lib/payouts-client", () => ({
  createPayoutsClient: () => ({ getBalances, getHistory }),
}));

const copy = vendorMessages.payouts;

function balances(patch: Partial<PayoutBalances>): PayoutBalances {
  return {
    escrow_held_ngwee: 0,
    released_available_ngwee: 45_000,
    paid_out_ngwee: 0,
    payouts_blocked: false,
    payouts_paused: false,
    payout_hold_until: null,
    payout_msisdn: null,
    payout_rail: null,
    ...patch,
  };
}

function renderView() {
  return render(
    <NextIntlClientProvider locale="en" messages={{ vendor: { payouts: copy } }}>
      {/* The live screen (build flag on); the pilot notice is covered by payouts-pilot.test.tsx. */}
      <PayoutsView locale="en" payoutsEnabled />
    </NextIntlClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("tells the vendor plainly when payouts are switched off", async () => {
  getBalances.mockResolvedValue(balances({ payouts_paused: true }));
  getHistory.mockResolvedValue({ items: [] });

  renderView();

  const notice = await screen.findByTestId("payouts-paused-notice");
  expect(notice).toHaveTextContent(copy.paused.noticeTitle);
  expect(notice).toHaveTextContent(copy.paused.noticeBody);
  // The available balance stays visible next to the notice — honest, not hidden.
  expect(screen.getByText(copy.balances.released)).toBeInTheDocument();
});

it("shows no pause notice once payouts are running", async () => {
  getBalances.mockResolvedValue(balances({ payouts_paused: false }));
  getHistory.mockResolvedValue({ items: [] });

  renderView();

  expect(await screen.findByText(copy.balances.released)).toBeInTheDocument();
  expect(screen.queryByTestId("payouts-paused-notice")).not.toBeInTheDocument();
});

it("keeps the 24-hour method-change hold separate from the platform pause", async () => {
  getBalances.mockResolvedValue(balances({ payouts_blocked: true }));
  getHistory.mockResolvedValue({ items: [] });

  renderView();

  expect(await screen.findByText(copy.hold.noticeTitle)).toBeInTheDocument();
  expect(screen.queryByTestId("payouts-paused-notice")).not.toBeInTheDocument();
});
