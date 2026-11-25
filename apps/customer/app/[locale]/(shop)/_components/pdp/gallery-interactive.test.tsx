// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";

import { PdpInteractiveGallery } from "./pdp-interactive-gallery";
import { magnifierLensRect } from "./zoom-math";

afterEach(cleanup);

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: query.includes("coarse"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  });
});

function renderGallery(imageCount: number) {
  const images = Array.from({ length: imageCount }, (_, index) => ({
    publicId: `demo/img-${index}`,
    alt: `Alt ${index}`,
  }));
  return render(
    <NextIntlClientProvider locale="en" messages={{ catalog: catalogMessages }} onError={() => {}}>
      <PdpInteractiveGallery
        images={images}
        cloudName="test"
        emptyLabel="Empty"
        previousLabel="Previous"
        nextLabel="Next"
        indicatorLabel={(current, total) => `Image ${current} of ${total}`}
        lightboxLabels={{
          open: "Open",
          dialog: "Dialog",
          close: "Close",
          previous: "Previous",
          next: "Next",
          zoomIn: "Zoom in",
          zoomOut: "Zoom out",
          indicator: "Image {current} of {total}",
        }}
      />
    </NextIntlClientProvider>,
  );
}

describe("PdpInteractiveGallery", () => {
  it("switches main image when a thumbnail is clicked", async () => {
    renderGallery(3);
    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("Image 1 of 3");
    fireEvent.click(await screen.findByTestId("gallery-thumb-1"));
    await waitFor(() =>
      expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("Image 2 of 3"),
    );
  });

  it("shows +N overflow tile when more than six images", async () => {
    renderGallery(8);
    expect(await screen.findByTestId("gallery-thumb-overflow")).toHaveTextContent("+2");
  });

  it("omits the strip for a single image", () => {
    renderGallery(1);
    expect(screen.queryByTestId("gallery-strip")).not.toBeInTheDocument();
  });
});

describe("magnifier maths", () => {
  it("tracks pointer coordinates for the lens", () => {
    expect(magnifierLensRect(120, 80, { width: 400, height: 400 }, 80)).toEqual({
      left: 80,
      top: 40,
    });
  });
});
