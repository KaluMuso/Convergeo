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
            details: {},
          },
        ],
      },
    });
    const user = userEvent.setup();

    render(<CustomerAuthBarrier labels={labels} />);
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "listing-a:cart.pickup_conflict",
    );
    await user.click(screen.getByRole("button", { name: labels.guestChoice }));

    expect(mocks.retry).toHaveBeenCalledWith({
      accept_price_changes: ["listing-b"],
      pickup_location_choices: { "listing-a": "location-guest" },
      remove_listing_ids: [],
    });
  });
});
