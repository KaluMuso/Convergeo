// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CategoryBanner } from "./category-banner";

vi.mock("@vergeo/ui/src/media/cloudinary-image-static", () => ({
  CloudinaryImageStatic: ({ publicId }: { publicId: string }) => (
    <img alt="" data-testid="cloudinary-image" data-public-id={publicId} />
  ),
}));

afterEach(() => {
  cleanup();
});

describe("CategoryBanner", () => {
  it("renders image, title and description", () => {
    render(
      <CategoryBanner
        banner={{
          imagePublicId: "categories/banners/rice",
          title: "Staples for less",
          description: "Mealie meal, rice and oil.",
        }}
      />,
    );
    expect(screen.getByTestId("cloudinary-image")).toHaveAttribute(
      "data-public-id",
      "categories/banners/rice",
    );
    expect(screen.getByText("Staples for less")).toBeInTheDocument();
    expect(screen.getByText("Mealie meal, rice and oil.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Staples for less" })).toBeInTheDocument();
  });

  it("renders a text-only banner without an image box", () => {
    render(<CategoryBanner banner={{ imagePublicId: null, title: "Fresh", description: null }} />);
    expect(screen.queryByTestId("category-banner-image")).not.toBeInTheDocument();
    expect(screen.getByText("Fresh")).toBeInTheDocument();
  });
});
