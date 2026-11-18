import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "token" }, loading: false }),
}));
vi.mock("@vergeo/config", () => ({ createApiClient: () => ({ request }) }));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}));

import { PlanPicker } from "./plan-picker";

const plan = (
  key: string,
  price: number,
  annual: number,
  max: number | null,
) => ({
  key,
  name: key,
  price_ngwee: price,
  annual_price_ngwee: annual,
  max_listings: max,
  max_images_per_listing: 8,
  featured_slots: 0,
  analytics_depth: "basic",
  wholesale_tools: false,
});

afterEach(() => {
  cleanup();
  request.mockReset();
});

describe("PlanPicker", () => {
  it("shows monthly and annual prices with the discount", async () => {
    const free = plan("free", 0, 0, 20);
    request.mockResolvedValue({
      enabled: true,
      plan: free,
      plans: [
        free,
        plan("starter", 4900, 49980, 200),
        plan("business", 24900, 253980, null),
      ],
      annual_discount_pct: 15,
    });
    render(<PlanPicker locale="en" />);
    expect((await screen.findByTestId("plan-starter-annual")).textContent).toBe(
      'picker.perYear:{"price":"K499.80","pct":15}',
    );
    expect(screen.queryByTestId("plan-free-annual")).toBeNull();
    expect(screen.getByTestId("plan-free").textContent).toContain(
      "picker.current",
    );
    expect(screen.getByTestId("plan-business").textContent).toContain(
      "picker.listingsUnlimited",
    );
  });

  it("hides annual prices when the discount is zero", async () => {
    request.mockResolvedValue({
      enabled: true,
      plan: null,
      plans: [plan("starter", 4900, 58800, 200)],
      annual_discount_pct: 0,
    });
    render(<PlanPicker locale="en" />);
    await screen.findByTestId("plan-starter");
    expect(screen.queryByTestId("plan-starter-annual")).toBeNull();
  });

  it("explains when plans are off", async () => {
    request.mockResolvedValue({ enabled: false });
    render(<PlanPicker locale="en" />);
    expect(await screen.findByText("picker.unavailable")).toBeTruthy();
  });
});
