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
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}));

import { PlanUsageCard, type VendorPlanStatus } from "./plan-usage-card";

const FREE = {
  key: "free",
  name: "Free",
  price_ngwee: 0,
  max_listings: 25,
  max_images_per_listing: 8,
  featured_slots: 0,
  analytics_depth: "basic",
  wholesale_tools: false,
};

const STARTER = { ...FREE, key: "starter", name: "Starter", price_ngwee: 4900, max_listings: 150 };

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
    const { container } = render(<PlanUsageCard />);
    await waitFor(() => expect(request).toHaveBeenCalledWith("/vendor/plan"));
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing if the plan cannot be read (never blocks listings)", async () => {
    request.mockRejectedValue(new Error("down"));
    const { container } = render(<PlanUsageCard />);
    await waitFor(() => expect(request).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("shows usage without an upgrade prompt below the limit", async () => {
    request.mockResolvedValue(status({}));
    render(<PlanUsageCard />);
    expect(await screen.findByText('plans.usage:{"count":3,"max":25}')).toBeTruthy();
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
    render(<PlanUsageCard />);
    const prompt = await screen.findByTestId("vendor-plan-upgrade");
    expect(prompt.textContent).toContain("plans.overLimit");
    expect(prompt.textContent).toContain("plans.keepSelling");
    expect(prompt.textContent).toContain('"price":"K49.00"');
    expect(prompt.textContent).toContain("plans.optionUnlimited");
  });

  it("explains a KYC cap without offering paid upgrades", async () => {
    request.mockResolvedValue(status({ limited_by: "kyc", at_limit: true, listing_count: 30 }));
    render(<PlanUsageCard />);
    expect(await screen.findByText("plans.kycLimit")).toBeTruthy();
    expect(screen.queryByTestId("vendor-plan-upgrade")).toBeNull();
  });
});
