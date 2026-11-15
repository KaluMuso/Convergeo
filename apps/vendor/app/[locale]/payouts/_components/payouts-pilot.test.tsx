// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";
import { isVendorPayoutsEnabled } from "../../../../lib/payouts-availability";

import { PayoutsView } from "./payouts-view";

const getBalances = vi.fn();
vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "t" }, user: null, loading: false }),
}));
vi.mock("../_lib/payouts-client", () => ({
  createPayoutsClient: () => ({ getBalances, getHistory: vi.fn() }),
}));

afterEach(() => {
  cleanup();
  getBalances.mockReset();
});

describe("isVendorPayoutsEnabled", () => {
  it("fails closed unless explicitly true", () => {
    expect(isVendorPayoutsEnabled(undefined)).toBe(false);
    expect(isVendorPayoutsEnabled("")).toBe(false);
    expect(isVendorPayoutsEnabled("false")).toBe(false);
    expect(isVendorPayoutsEnabled("yes")).toBe(false);
    expect(isVendorPayoutsEnabled("true")).toBe(true);
    expect(isVendorPayoutsEnabled(" 1 ")).toBe(true);
  });
});

describe("PayoutsView in the pilot", () => {
  it("explains payouts are off, shows no balances or buttons, and calls no API", () => {
    render(
      <NextIntlClientProvider locale="en" messages={{ vendor: vendorMessages }}>
        <PayoutsView locale="en" payoutsEnabled={false} />
      </NextIntlClientProvider>,
    );
    expect(screen.getByTestId("vendor-payouts-pilot")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Payouts aren't switched on during the pilot" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/K\d/)).not.toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(getBalances).not.toHaveBeenCalled();
  });
});
