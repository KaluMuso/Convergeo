// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CloudinaryImageStatic } from "./cloudinary-image-static";

afterEach(() => {
  cleanup();
});

describe("CloudinaryImageStatic", () => {
  it("renders img with srcset, sizes, loading=lazy, and decoding=async", () => {
    render(
      <CloudinaryImageStatic
        publicId="catalog/phone.jpg"
        alt="Smartphone on display"
        cloudName="test-cloud"
      />,
    );

    const img = screen.getByRole("img", { name: "Smartphone on display" });
    expect(img).toHaveAttribute("srcset");
    expect(img.getAttribute("srcset")).toContain("360w");
    expect(img).toHaveAttribute("sizes");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("decoding", "async");
  });

  it("disables lazy loading when priority is set", () => {
    render(
      <CloudinaryImageStatic
        publicId="hero.jpg"
        alt="Hero banner"
        priority
        cloudName="test-cloud"
      />,
    );

    const img = screen.getByRole("img", { name: "Hero banner" });
    expect(img).toHaveAttribute("loading", "eager");
  });

  it("applies aspect-ratio on the container", () => {
    render(
      <CloudinaryImageStatic
        publicId="square.jpg"
        alt="Square product"
        ratio="4/3"
        cloudName="test-cloud"
      />,
    );

    const box = screen.getByTestId("cloudinary-image-box");
    expect(box).toHaveStyle({ aspectRatio: "4/3" });
  });

  it("reserves intrinsic dimensions from width + ratio to reduce CLS", () => {
    render(
      <CloudinaryImageStatic
        publicId="product.jpg"
        alt="Product"
        width={360}
        ratio="4/3"
        cloudName="test-cloud"
      />,
    );

    const img = screen.getByRole("img", { name: "Product" });
    expect(img).toHaveAttribute("width", "360");
    expect(img).toHaveAttribute("height", "270");
  });

  it("shows a labelled fallback when cloud name is missing", () => {
    render(
      <CloudinaryImageStatic
        publicId="catalog/phone.jpg"
        alt="Smartphone on display"
        fallbackLabel="No images yet"
      />,
    );

    expect(screen.getByTestId("cloudinary-image-fallback")).toHaveTextContent("No images yet");
    expect(screen.queryByRole("img", { name: "Smartphone on display" })).not.toBeInTheDocument();
  });
});
