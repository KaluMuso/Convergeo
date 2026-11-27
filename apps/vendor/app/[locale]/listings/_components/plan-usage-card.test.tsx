import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "token" }, loading: false }),
}));

vi.mock("@vergeo/config", () => ({
  createApiClient: () => ({ request }),
}));

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}));

import { PlanUsageCard, type VendorPlanStatus } from "./plan-usage-card";

const FREE = {
  key: "free",
  name: "Free",
  price_ngwee: 0,
  annual_price_ngwee: 0,
  max_listings: 25,
  max_images_per_listing: 8,
  featured_slots: 0,
  analytics_depth: "basic",
  wholesale_tools: false,
};

const STARTER = {
  ...FREE,
  key: "starter",
  name: "Starter",
  price_ngwee: 4900,
  annual_price_ngwee: 49980,
  max_listings: 200,
};

function status(overrides: Partial<VendorPlanStatus>): VendorPlanStatus {
  return {
    enabled: true,
    plan: FREE,
    effective_max_listings: 25,
    max_images_per_listing: 8,
    listing_count: 3,
    remaining_listings: 22,
    at_limit: false,
    over_limit: false,
    limited_by: "plan",
    override_expires_at: null,
    upgrade_options: [],
    plans: [],
    annual_discount_pct: 15,
    trial_ends_at: null,
    in_trial: false,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  request.mockReset();
});

describe("PlanUsageCard", () => {
  it("renders nothing while the vendor_plans flag is off", async () => {
    request.mockResolvedValue({ enabled: false });
    const { container } = render(<PlanUsageCard locale="en" />);
    await waitFor(() => expect(request).toHaveBeenCalledWith("/vendor/plan"));
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing if the plan cannot be read (never blocks listings)", async () => {
    request.mockRejectedValue(new Error("down"));
    const { container } = render(<PlanUsageCard locale="en" />);
    await waitFor(() => expect(request).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("shows usage without an upgrade prompt below the limit", async () => {
    request.mockResolvedValue(status({}));
    render(<PlanUsageCard locale="en" />);
    expect(await screen.findByText('plans.usageActive:{"count":3,"max":25}')).toBeTruthy();
    expect(screen.queryByTestId("vendor-plan-upgrade")).toBeNull();
    expect(screen.getByText("plans.free")).toBeTruthy();
  });

  it("shows a friendly upgrade prompt with prices when the plan limit is reached", async () => {
    request.mockResolvedValue(
      status({
        listing_count: 27,
        at_limit: true,
        over_limit: true,
        remaining_listings: 0,
        upgrade_options: [STARTER, { ...STARTER, key: "pro", name: "Pro", max_listings: null }],
      }),
    );
    render(<PlanUsageCard locale="en" />);
    const prompt = await screen.findByTestId("vendor-plan-upgrade");
    expect(prompt.textContent).toContain("plans.overLimit");
    expect(prompt.textContent).toContain("plans.keepSelling");
    expect(prompt.textContent).toContain('"price":"K49.00"');
    expect(prompt.textContent).toContain("plans.optionUnlimited");
    expect(screen.getByText("plans.seePlans").closest("a")?.getAttribute("href")).toBe("/en/plan");
  });

  it("explains a KYC cap without offering paid upgrades", async () => {
    request.mockResolvedValue(status({ limited_by: "kyc", at_limit: true, listing_count: 30 }));
    render(<PlanUsageCard locale="en" />);
    expect(await screen.findByText("plans.kycLimit")).toBeTruthy();
    expect(screen.queryByTestId("vendor-plan-upgrade")).toBeNull();
  });
});
