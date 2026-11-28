import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ListingEditForm } from "./listing-edit-form";

const mocks = vi.hoisted(() => ({
  translate: Object.assign((key: string) => key, { raw: () => ({}) }),
  session: { access_token: "test-token", user: { id: "owner" } },
  client: {
    getListing: vi.fn(),
    getStock: vi.fn(),
    updateListing: vi.fn(),
    // #762 variants editor: a listing without options.
    getVariants: vi.fn((listingId: string) =>
      Promise.resolve({
        listing_id: listingId,
        listing_price_ngwee: 0,
        stock_mode: "tracked",
        groups: [],
        variants: [],
      }),
    ),
    replaceVariants: vi.fn(),
  },
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
  mocks.client.getListing.mockResolvedValue({
    ...listing,
    free_delivery: true,
    weight_grams: 2500,
  });
  mocks.client.getStock.mockResolvedValue({
    ...listing,
    listing_id: listing.id,
    branch_tracked: false,
    branches: [],
  });
  mocks.client.updateListing.mockResolvedValue({ listing });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionStorage.clear();
});

async function save() {
  fireEvent.click(screen.getByRole("button", { name: "listings.manage.edit.save" }));
}

it("loads the saved free-delivery flag and weight, and sends edits on save", async () => {
  render(<ListingEditForm locale="en" listingId="listing" />);
  const toggle = (await screen.findByTestId("listing-free-delivery")) as HTMLInputElement;
  const weight = screen.getByTestId("listing-weight-grams") as HTMLInputElement;
  expect(toggle.checked).toBe(true);
  expect(weight.value).toBe("2500");

  fireEvent.click(toggle);
  fireEvent.change(weight, { target: { value: "" } });
  await save();
  await waitFor(() => expect(mocks.client.updateListing).toHaveBeenCalledOnce());
  const payload = mocks.client.updateListing.mock.calls[0]?.[1];
  expect(payload.free_delivery).toBe(false);
  expect(payload.weight_grams).toBeNull();
});

it("blocks saving a weight that is not a whole number of grams", async () => {
  render(<ListingEditForm locale="en" listingId="listing" />);
  const weight = await screen.findByTestId("listing-weight-grams");
  for (const bad of ["0", "-3", "1.5", "heavy", "10000001"]) {
    fireEvent.change(weight, { target: { value: bad } });
    await save();
    expect(await screen.findByText("listings.manage.edit.weightInvalid")).toBeTruthy();
  }
  expect(mocks.client.updateListing).not.toHaveBeenCalled();
});
