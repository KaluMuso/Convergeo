import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

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

const removed = {
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
  wholesale: false,
  moq: 1,
  price_tiers: null,
  returnable: false,
  return_window_hours: null,
  status: "removed",
  images: [],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("shows the removed state instead of an editable form for a deleted listing", async () => {
  mocks.client.getListing.mockResolvedValue(removed);
  mocks.client.getStock.mockResolvedValue({
    ...removed,
    listing_id: removed.id,
    branch_tracked: false,
    branches: [],
  });
  render(<ListingEditForm locale="en" listingId="listing" />);
  expect(await screen.findByTestId("listing-removed-state")).toBeTruthy();
  expect(screen.getByText("listings.manage.removed.title")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "listings.manage.edit.save" })).toBeNull();
  expect(screen.queryByLabelText("listings.fields.priceLabel")).toBeNull();
});
