import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ListingEditForm } from "./listing-edit-form";

const mocks = vi.hoisted(() => ({
  translate: (key: string) => key,
  session: { access_token: "test-token", user: { id: "owner" } },
  client: { getListing: vi.fn(), getStock: vi.fn(), updateListing: vi.fn() },
}));
vi.mock("next-intl", () => ({ useTranslations: () => mocks.translate }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: mocks.session, loading: false }),
}));
vi.mock("../_lib/manage-client", () => ({
  createManageClient: () => mocks.client,
}));
vi.mock("../../../_components/image-manager", () => ({
  ImageManager: () => null,
}));

const listing = {
  id: "listing",
  title: "Rice",
  product_id: "product",
  price_ngwee: 12000,
  compare_at_ngwee: null,
  product_class: "A",
  sale_unit: "each",
  unit_step_milli: 1000,
  min_steps: 1,
  condition: "new",
  fulfilment_mode: "stocked",
  stock_mode: "tracked",
  stock_qty: 10,
  wholesale: true,
  moq: 2,
  price_tiers: [
    { min_qty: 3, price_ngwee: 10000 },
    { min_qty: 6, price_ngwee: 8000 },
  ],
  returnable: false,
  return_window_hours: null,
  status: "active",
  images: [],
};

beforeEach(() => {
  mocks.client.getListing.mockResolvedValue(listing);
  mocks.client.getStock.mockResolvedValue({
    ...listing,
    listing_id: listing.id,
    branch_tracked: false,
    branches: [],
  });
  mocks.client.updateListing.mockResolvedValue({
    listing: { ...listing, stock_qty: 7, price_ngwee: 13000 },
  });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionStorage.clear();
});

it("keeps measured minimum steps disabled while price saves preserve their value", async () => {
  const measured = {
    ...listing,
    sale_unit: "kg",
    unit_step_milli: 250,
    min_steps: 4,
    wholesale: false,
    price_tiers: null,
  };
  mocks.client.getListing.mockResolvedValue(measured);
  render(<ListingEditForm locale="en" listingId="listing" />);
  const minimum = (await screen.findByLabelText(
    "listings.fields.minStepsLabel",
  )) as HTMLInputElement;
  expect(minimum.disabled).toBe(true);
  expect(minimum.value).toBe("4");
  fireEvent.change(screen.getByLabelText("listings.fields.priceLabel"), {
    target: { value: "130.00" },
  });
  fireEvent.click(screen.getByRole("button", { name: "listings.manage.edit.save" }));
  await waitFor(() => expect(mocks.client.updateListing).toHaveBeenCalledOnce());
  expect(mocks.client.updateListing.mock.calls[0]?.[1].min_steps).toBe(4);
});
