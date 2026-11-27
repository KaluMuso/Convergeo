import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
vi.mock("@vergeo/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: ({ alt }: { alt: string }) => <span>{alt}</span>,
}));

import { ImportPanel } from "./import-panel";
import { SourceCard } from "./source-card";

import type { SourcingItem } from "../_lib/source";

const LISTING: SourcingItem = {
  kind: "listing",
  id: "l1",
  title: "Bulk flour",
  image_public_id: null,
  image_url: null,
  price_ngwee: 5000,
  price_tiers: [
    { min_qty: 50, price_ngwee: 4000 },
    { min_qty: 10, price_ngwee: 4500 },
  ],
  moq: 10,
  wholesale: true,
  made_in_zambia: true,
  vendor_id: "v1",
  shop_name: "Bravo Foods",
  shop_slug: "bravo",
  landmark: "Cairo Road",
  verified: true,
  whatsapp_msisdn: "260977123456",
  supplier_types: [],
  service_category: null,
};

afterEach(() => {
  cleanup();
  request.mockReset();
});

describe("SourceCard", () => {
  it("shows ordered tier prices, MOQ, badges and a WhatsApp contact", () => {
    render(
      <ul>
        <SourceCard item={LISTING} />
      </ul>,
    );
    const text = document.body.textContent ?? "";
    expect(text.indexOf('"qty":10')).toBeLessThan(text.indexOf('"qty":50'));
    expect(screen.getByText('card.moq:{"qty":10}')).toBeTruthy();
    expect(screen.getByText("card.verified")).toBeTruthy();
    expect(screen.getByText("card.madeInZambia")).toBeTruthy();
    const link = screen.getByText("card.whatsapp").closest("a");
    expect(link?.getAttribute("href")).toContain("https://wa.me/260977123456?text=");
    expect(link?.getAttribute("rel")).toContain("noopener");
  });

  it("offers an RFQ on services and posts to the existing /rfq route", async () => {
    request.mockResolvedValue({});
    const service: SourcingItem = {
      ...LISTING,
      kind: "service",
      id: "s1",
      title: "Flyer printing",
      price_tiers: null,
      moq: null,
      whatsapp_msisdn: null,
    };
    render(
      <ul>
        <SourceCard item={service} />
      </ul>,
    );
    fireEvent.click(screen.getByText("card.requestQuote"));
    fireEvent.change(screen.getByLabelText("rfq.label"), {
      target: { value: "500 flyers" },
    });
    fireEvent.click(screen.getByText("rfq.send"));
    await waitFor(() => expect(request).toHaveBeenCalled());
    expect(request.mock.calls[0]?.[0]).toBe("/rfq");
    expect(JSON.parse(request.mock.calls[0]?.[1].body)).toEqual({
      service_id: "s1",
      requested_details: "500 flyers",
    });
  });
});

describe("ImportPanel", () => {
  it("labels quotes as estimates with separate ngwee lines and no payment action", async () => {
    request.mockResolvedValue([
      {
        id: "r1",
        title: "LED strips",
        description: null,
        reference_url: null,
        image_urls: [],
        quantity: 200,
        unit: "pcs",
        target_unit_price_ngwee: null,
        destination_city: null,
        status: "quoted",
        created_at: "2026-11-27T00:00:00Z",
        updated_at: "2026-11-27T00:00:00Z",
        latest_quote: {
          id: "q1",
          request_id: "r1",
          partner_label: "Partner X",
          product_ngwee: 700000,
          freight_ngwee: 150000,
          duty_ngwee: 120000,
          clearing_ngwee: 30000,
          other_ngwee: 0,
          total_ngwee: 1000000,
          lead_time_days: 35,
          valid_until: null,
          notes: null,
          is_estimate: true,
          created_at: "2026-11-27T00:00:00Z",
        },
      },
    ]);
    render(<ImportPanel />);
    expect(await screen.findByTestId("import-quote")).toBeTruthy();
    for (const key of ["product", "freight", "duty", "clearing", "total"]) {
      expect(screen.getByText(`import.quote.${key}`)).toBeTruthy();
    }
    expect(screen.getAllByText("import.estimateNotice").length).toBeGreaterThan(0);
    expect(screen.queryByText(/pay/i)).toBeNull();
  });

  it("does not send an invalid request", async () => {
    request.mockResolvedValue([]);
    render(<ImportPanel />);
    await screen.findByText("import.empty");
    fireEvent.click(screen.getAllByText("import.newRequest")[0] as HTMLElement);
    fireEvent.click(screen.getByText("import.submit"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(1);
  });
});
