// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ListingEditForm } from "./listing-edit-form";

const mocks = vi.hoisted(() => ({
  translate: Object.assign((key: string) => key, { raw: () => ({}) }),
  session: { access_token: "test-token", user: { id: "owner" } },
  client: {
    getListing: vi.fn(),
    getStock: vi.fn(),
    updateListing: vi.fn(),
    getVariants: vi.fn(() =>
      Promise.resolve({
        listing_id: "draft-listing",
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
vi.mock("../../../_components/image-manager", () => ({ ImageManager: () => null }));

const draftListing = {
  id: "draft-listing",
  title: "Draft",
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
  status: "draft",
  images: [],
};

beforeEach(() => {
  mocks.client.getListing.mockResolvedValue(draftListing);
  mocks.client.getStock.mockResolvedValue({
    ...draftListing,
    listing_id: draftListing.id,
    branch_tracked: false,
    branches: [],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ListingEditForm publish guard", () => {
  it("blocks publishing a draft with zero photos", async () => {
    render(<ListingEditForm locale="en" listingId="draft-listing" />);
    const publish = await screen.findByRole("button", {
      name: "listings.manage.edit.publishListing",
    });
    fireEvent.click(publish);
    expect(mocks.client.updateListing).not.toHaveBeenCalled();
    expect(screen.getByText("listings.manage.addPhotoFirst")).toBeInTheDocument();
  });
});
