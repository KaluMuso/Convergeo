// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@vergeo/config";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  retry: vi.fn(),
  signOut: vi.fn(),
  error: null as unknown,
}));

vi.mock("../../../lib/customer-session", () => ({
  useSession: () => ({ error: mocks.error, retry: mocks.retry }),
}));

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({ auth: { signOut: mocks.signOut } }),
}));

import { CustomerAuthBarrier } from "./customer-auth-barrier";

const labels = {
  title: "Resolve cart",
  body: "Choose what to keep",
  conflictLine: "{listing}:{code}",
  priceLine: "{item}: {previous} -> {current} x {quantity} = {total}",
  unnamedItem: "Item #{id}",
  wholesaleTerms: "Wholesale minimum {moq}",
  priceNeedsReview: "Review quote",
  accountChoice: "Keep account pickup",
  guestChoice: "Keep guest pickup",
  apply: "Apply choices",
  retry: "Retry",
  signOut: "Sign out",
  failure: "Merge failed",
};

afterEach(() => {
  cleanup();
  mocks.retry.mockReset();
  mocks.signOut.mockReset();
  mocks.error = null;
});

describe("CustomerAuthBarrier", () => {
  it("shows conflicts and submits an explicit pickup and price resolution", async () => {
    mocks.retry.mockResolvedValue(null);
    mocks.error = new ApiError("cart.merge_conflict", "conflict", {
      status: 409,
      details: {
        conflicts: [
          {
            listing_id: "listing-a",
            code: "cart.pickup_conflict",
            details: {
              user_pickup_location_id: "location-account",
              guest_pickup_location_id: "location-guest",
            },
          },
          {
            listing_id: "listing-b",
            code: "cart.price_changed",
            details: {
              item_name: "Copper pipe",
              previous_unit_prices_ngwee: [10000],
              current_unit_price_ngwee: 12000,
              current_line_total_ngwee: 24000,
              quantity: 2,
              proposal_token: "signed-price-terms",
            },
          },
        ],
      },
    });
    const user = userEvent.setup();

    render(<CustomerAuthBarrier labels={labels} />);
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Item #listing-:cart.pickup_conflict",
    );
    expect(screen.getByRole("dialog")).toHaveTextContent("Copper pipe: K100.00 -> K120.00 x 2 = K240.00");
    await user.click(screen.getByRole("button", { name: labels.guestChoice }));

    expect(mocks.retry).toHaveBeenCalledWith({
      accept_price_changes: ["listing-b"],
      accepted_price_proposals: { "listing-b": "signed-price-terms" },
      pickup_location_choices: { "listing-a": "location-guest" },
      remove_listing_ids: [],
    });
  });

  it("shows wholesale terms and requires explicit removal for a changed RFQ quote", async () => {
    mocks.retry.mockResolvedValue(null);
    mocks.error = new ApiError("cart.merge_conflict", "conflict", {
      status: 409,
      details: {
        conflicts: [{
          listing_id: "listing-rfq",
          code: "cart.price_changed",
          details: {
            item_name: "Steel rods",
            previous_unit_prices_ngwee: [10000],
            current_unit_price_ngwee: 12000,
            quantity: 3,
            wholesale: true,
            moq: 3,
            proposal_token: null,
          },
        }],
      },
    });
    render(<CustomerAuthBarrier labels={labels} />);
    expect(screen.getByRole("dialog")).toHaveTextContent("Steel rods: K100.00 -> K120.00 x 3 = K360.00");
    expect(screen.getByRole("dialog")).toHaveTextContent("Wholesale minimum 3 Review quote");
    await userEvent.setup().click(screen.getByRole("button", { name: labels.apply }));
    expect(mocks.retry).toHaveBeenCalledWith({
      accept_price_changes: [],
      accepted_price_proposals: {},
      pickup_location_choices: {},
      remove_listing_ids: ["listing-rfq"],
    });
  });
});
