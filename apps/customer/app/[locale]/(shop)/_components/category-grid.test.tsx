// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { createTranslator } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../packages/i18n/messages/en/catalog.json";

import { CategoryGrid, readCategoryImageMap } from "./category-grid";

vi.mock("@vergeo/ui/src/media/cloudinary-image-static", () => ({
  CloudinaryImageStatic: ({ publicId }: { publicId: string }) => (
    <img alt="" data-testid="cloudinary-image" data-public-id={publicId} />
  ),
}));

afterEach(() => {
  cleanup();
});

const t = createTranslator({
  locale: "en",
  messages: { catalog: catalogMessages },
  namespace: "catalog",
}) as unknown as (key: string, values?: Record<string, string | number>) => string;

describe("readCategoryImageMap", () => {
  it("reads slug→publicId maps from merch payload", () => {
    const map = readCategoryImageMap({
      images: { electronics: "campaign/electronics-tile" },
      category_images: [{ slug: "fashion", image_public_id: "campaign/fashion-tile" }],
    });
    expect(map.get("electronics")).toBe("campaign/electronics-tile");
    expect(map.get("fashion")).toBe("campaign/fashion-tile");
  });
});

describe("CategoryGrid (CUST-HOME-01)", () => {
  it("renders accessible links with colour/icon fallback when no image is configured", () => {
    render(
      <CategoryGrid
        categories={[
          {
            id: "1",
            name: "Electronics",
            slug: "electronics",
            path: "electronics",
            position: 0,
            parent_id: null,
            prohibited: false,
          },
        ]}
        locale="en"
        t={t}
      />,
    );

    expect(screen.getByTestId("home-category-electronics")).toHaveAttribute(
      "href",
      "/en/c/electronics",
    );
    expect(screen.getByTestId("category-fallback-icon")).toBeInTheDocument();
    expect(screen.queryByTestId("category-image")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse Electronics" })).toBeInTheDocument();
  });

  it("uses a denser marketplace category grid on desktop", () => {
    render(
      <CategoryGrid
        categories={[
          {
            id: "1",
            name: "Electronics",
            slug: "electronics",
            path: "electronics",
            position: 0,
            parent_id: null,
            prohibited: false,
          },
        ]}
        locale="en"
        t={t}
      />,
    );
    const grid = screen.getByTestId("home-category-grid");
    expect(grid).toHaveClass("md:grid-cols-4", "lg:grid-cols-6", "xl:grid-cols-8");
  });

  it("uses an approved merch image when provided", () => {
    render(
      <CategoryGrid
        slot={{
          id: "cat-grid",
          slot_key: "category_grid",
          variant_key: "default",
          payload: { images: { electronics: "campaign/electronics-tile" } },
          schedule_from: null,
          schedule_to: null,
          position: 0,
          active: true,
        }}
        categories={[
          {
            id: "1",
            name: "Electronics",
            slug: "electronics",
            path: "electronics",
            position: 0,
            parent_id: null,
            prohibited: false,
          },
        ]}
        locale="en"
        t={t}
      />,
    );

    expect(screen.getByTestId("category-image")).toBeInTheDocument();
    expect(screen.getByTestId("cloudinary-image")).toHaveAttribute(
      "data-public-id",
      "campaign/electronics-tile",
    );
  });
});
