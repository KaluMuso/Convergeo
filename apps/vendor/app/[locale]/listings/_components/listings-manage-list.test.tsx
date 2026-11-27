// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ListingsManageList } from "./listings-manage-list";

const mocks = vi.hoisted(() => ({
  session: { access_token: "token" },
  listings: [
    {
      id: "with-photo",
      title: "With cover",
      price_ngwee: 10000,
      compare_at_ngwee: null,
      condition: "new",
      stock_mode: "tracked",
      stock_qty: 3,
      status: "active",
      product_id: "p1",
      images: [{ id: "img-1", cloudinary_public_id: "listings/cover", position: 1 }],
    },
    {
      id: "no-photo",
      title: "Missing cover",
      price_ngwee: 5000,
      compare_at_ngwee: null,
      condition: "new",
      stock_mode: "always_available",
      stock_qty: null,
      status: "draft",
      product_id: "p2",
      images: [],
    },
  ],
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: mocks.session, loading: false }),
}));

vi.mock("../[id]/edit/_lib/manage-client", () => ({
  createManageClient: () => ({
    listListings: vi.fn(async () => mocks.listings),
  }),
}));

vi.mock("./plan-usage-card", () => ({ PlanUsageCard: () => null }));
vi.mock("./listing-guide", () => ({
  ListingStatusGuide: () => null,
  ListingTipsPanel: () => null,
  ListingVisibilityHint: () => null,
}));

vi.mock("@vergeo/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: ({ publicId }: { publicId: string }) => (
    <img data-testid="listing-cover" alt="" src={publicId} />
  ),
}));

afterEach(() => {
  cleanup();
});

describe("ListingsManageList", () => {
  it("shows a cover thumbnail or an add-photo link", async () => {
    render(<ListingsManageList locale="en" />);
    expect(await screen.findByTestId("listing-cover")).toHaveAttribute("src", "listings/cover");
    const addPhoto = screen.getByRole("link", { name: "listings.manage.addPhotoLink" });
    expect(addPhoto).toHaveAttribute("href", "/en/listings/no-photo/edit#photos");
  });

  it("gives status its own full-width row instead of a narrow column beside the thumbnail", async () => {
    render(<ListingsManageList locale="en" />);
    await screen.findByTestId("listing-cover");
    const rows = screen.getAllByTestId("listing-status-row");
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      // The row is a direct child of the card, a sibling of (never inside) the
      // image + title row, so it spans the card's full width at 360px.
      const card = row.parentElement;
      expect(card).not.toBeNull();
      expect(row.closest(".items-start")).toBeNull();
      expect(row.className).toContain("flex-col");
    }
  });
});
