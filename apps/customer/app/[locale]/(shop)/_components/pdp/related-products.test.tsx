// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

import { RelatedProducts } from "./related-products";

afterEach(() => {
  cleanup();
});

const labels = {
  heading: "More in this category",
  vendorFallback: "Same category",
  noReviews: "No reviews yet",
  reviewCount: "({count})",
  quickAdd: "Quick add",
  wishlist: "Save",
  mediaEmpty: "No images yet",
};

describe("RelatedProducts", () => {
  it("uses ProductCard when a from-price exists and skips fabricated K0 for unpriced items", () => {
    render(
      <RelatedProducts
        locale="en"
        labels={labels}
        items={[
          {
            slug: "priced",
            name: "Priced phone",
            image_public_id: "demo/phone",
            from_price_ngwee: 250_000,
          },
          {
            slug: "unpriced",
            name: "Unpriced accessory",
            image_public_id: null,
            from_price_ngwee: null,
          },
        ]}
      />,
    );

    expect(screen.getByTestId("pdp-related")).toBeInTheDocument();
    expect(screen.getByTestId("product-card")).toBeInTheDocument();
    expect(screen.getByTestId("pdp-related-unpriced")).toBeInTheDocument();
    expect(screen.getByText("Unpriced accessory")).toBeInTheDocument();
  });
});
