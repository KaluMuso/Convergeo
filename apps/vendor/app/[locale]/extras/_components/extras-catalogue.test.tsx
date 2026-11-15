import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
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

import { ExtrasCatalogue } from "./extras-catalogue";

const CATALOGUE = {
  extras: [
    {
      key: "store_design",
      name: "Store design",
      description: "We design your storefront.",
      pricing: "range",
      price_ngwee: 50000,
      price_max_ngwee: 500000,
      unit: "one_off",
      price_is_placeholder: false,
    },
    {
      key: "custom_domain",
      name: "Custom domain",
      description: "",
      pricing: "fixed",
      price_ngwee: 7500,
      price_max_ngwee: null,
      unit: "per_month",
      price_is_placeholder: true,
    },
  ],
  requests: [
    {
      id: "r1",
      extra_key: "custom_domain",
      quantity: 1,
      note: null,
      status: "quoted",
      quoted_price_ngwee: 9900,
      admin_note: null,
      created_at: null,
    },
  ],
};

afterEach(() => {
  cleanup();
  request.mockReset();
});

describe("ExtrasCatalogue", () => {
  it("lists extras with a Request button and shows open quotes", async () => {
    request.mockResolvedValue(CATALOGUE);
    render(<ExtrasCatalogue />);
    expect(await screen.findByTestId("extra-store_design")).toBeTruthy();
    expect(screen.getByText("indicativePrice")).toBeTruthy();
    expect(
      screen.getByTestId("extra-custom_domain-status").textContent,
    ).toContain('"K99.00"');
    expect(screen.getByText("actions.accept")).toBeTruthy();
  });

  it("sends a request and never a price", async () => {
    request
      .mockResolvedValueOnce(CATALOGUE)
      .mockResolvedValueOnce({})
      .mockResolvedValue(CATALOGUE);
    render(<ExtrasCatalogue />);
    const card = await screen.findByTestId("extra-store_design");
    fireEvent.click(card.querySelector("button") as HTMLButtonElement);
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/vendor/extras/requests", {
        method: "POST",
        body: JSON.stringify({ extra_key: "store_design" }),
      }),
    );
    expect(await screen.findByText("requested")).toBeTruthy();
  });

  it("shows the duplicate-request message from the API", async () => {
    request
      .mockResolvedValueOnce(CATALOGUE)
      .mockRejectedValueOnce({
        details: { message_key: "vendor.extras.errors.alreadyRequested" },
      });
    render(<ExtrasCatalogue />);
    const card = await screen.findByTestId("extra-store_design");
    fireEvent.click(card.querySelector("button") as HTMLButtonElement);
    expect(await screen.findByText("errors.alreadyRequested")).toBeTruthy();
  });
});
