// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CloudinaryImage } from "./cloudinary-image";

afterEach(() => {
  cleanup();
});

describe("CloudinaryImage", () => {
  it("renders img with srcset, sizes, loading=lazy, and decoding=async", () => {
    render(
      <CloudinaryImage
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
      <CloudinaryImage publicId="hero.jpg" alt="Hero banner" priority cloudName="test-cloud" />,
    );

    const img = screen.getByRole("img", { name: "Hero banner" });
    expect(img).toHaveAttribute("loading", "eager");
  });

  it("applies aspect-ratio on the container", () => {
    render(
      <CloudinaryImage
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
      <CloudinaryImage
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

  it("reveals the image after load and shows a labelled fallback on error", () => {
    render(
      <CloudinaryImage
        publicId="catalog/phone.jpg"
        alt="Smartphone on display"
        cloudName="test-cloud"
        fallbackLabel="No images yet"
      />,
    );

    const img = screen.getByRole("img", { name: "Smartphone on display" });
    expect(img).toHaveStyle({ opacity: "0" });
    fireEvent.load(img);
    expect(img).toHaveStyle({ opacity: "1" });

    fireEvent.error(img);
    expect(screen.getByTestId("cloudinary-image-fallback")).toHaveTextContent("No images yet");
  });

  it("renders a visible, non-crashing fallback when the Cloudinary cloud name is missing", () => {
    // Models the production ops gap: NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME never set on
    // the Vercel customer project. cldUrl() soft-fails to "" and the card must show
    // a labelled fallback — never throw, never emit a broken <img> that 404s/hangs.
    const previous = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME;
    delete process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME;
    try {
      expect(() =>
        render(
          <CloudinaryImage
            publicId="catalog/phone.jpg"
            alt="Smartphone on display"
            fallbackLabel="Image unavailable"
          />,
        ),
      ).not.toThrow();

      const fallback = screen.getByTestId("cloudinary-image-fallback");
      expect(fallback).toHaveTextContent("Image unavailable");
      // Still exposed to AT as an image, but with no real <img> element.
      expect(fallback).toHaveAttribute("role", "img");
      expect(fallback).toHaveAttribute("aria-label", "Image unavailable");
      expect(screen.queryByRole("img", { name: "Smartphone on display" })).not.toBeInTheDocument();
      expect(document.querySelector("img")).toBeNull();
    } finally {
      if (previous === undefined) {
        delete process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME;
      } else {
        process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME = previous;
      }
    }
  });

  it("requires alt at the type level", () => {
    // @ts-expect-error alt is required
    render(<CloudinaryImage publicId="x.jpg" cloudName="test-cloud" />);
    expect(true).toBe(true);
  });
});
