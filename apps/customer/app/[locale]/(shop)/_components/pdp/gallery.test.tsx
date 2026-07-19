// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";

import { PdpGallery } from "./gallery";

afterEach(() => {
  cleanup();
});

function renderGallery(
  images: Array<{ publicId: string; alt: string }>,
  options?: { withCatalog?: boolean },
) {
  const indicator = (current: number, total: number) => `Image ${current} of ${total}`;
  const tree = (
    <PdpGallery
      images={images}
      cloudName="test-cloud"
      emptyLabel="No images yet"
      previousLabel="Previous image"
      nextLabel="Next image"
      indicatorLabel={indicator}
    />
  );

  if (options?.withCatalog === false) {
    return render(tree);
  }

  return render(
    <NextIntlClientProvider locale="en" messages={{ catalog: catalogMessages }} onError={() => {}}>
      {tree}
    </NextIntlClientProvider>,
  );
}

describe("PdpGallery", () => {
  it("renders the primary image and a human indicator when media is available", () => {
    renderGallery([{ publicId: "demo/categories/mobile-phones", alt: "Itel A70" }]);

    const img = screen.getByRole("img", { name: "Itel A70" });
    expect(img).toHaveAttribute(
      "src",
      expect.stringContaining("demo/categories/mobile-phones"),
    );
    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("Image 1 of 1");
    expect(screen.queryByTestId("pdp-gallery-empty")).not.toBeInTheDocument();
  });

  it("shows a labelled fallback stage when media is absent", () => {
    renderGallery([]);

    expect(screen.getByTestId("pdp-gallery-empty")).toHaveTextContent("No images yet");
    expect(screen.queryByTestId("gallery-strip")).not.toBeInTheDocument();
  });

  it("shows a labelled fallback when the image fails to load", () => {
    renderGallery([{ publicId: "missing/asset", alt: "Broken product" }]);

    const img = screen.getByRole("img", { name: "Broken product" });
    fireEvent.error(img);

    expect(screen.getByTestId("cloudinary-image-fallback")).toHaveTextContent("No images yet");
  });
});

describe("catalog gallery i18n", () => {
  it("resolves catalog.pdp.gallery.indicator through the catalog namespace", () => {
    render(
      <NextIntlClientProvider
        locale="en"
        messages={{ catalog: catalogMessages }}
        onError={() => {}}
      >
        <PdpGallery
          images={[{ publicId: "demo/phone", alt: "Phone" }]}
          cloudName="test-cloud"
          emptyLabel="No images yet"
          previousLabel="Previous"
          nextLabel="Next"
          indicatorLabel={(current, total) => {
            const template = (catalogMessages as { pdp: { gallery: { indicator: string } } }).pdp
              .gallery.indicator;
            return template.replace("{current}", String(current)).replace("{total}", String(total));
          }}
        />
      </NextIntlClientProvider>,
    );

    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("Image 1 of 1");
    expect(screen.queryByText("catalog.pdp.gallery.indicator")).not.toBeInTheDocument();
  });
});
