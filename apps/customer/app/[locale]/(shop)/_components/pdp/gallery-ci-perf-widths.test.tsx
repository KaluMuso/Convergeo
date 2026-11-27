// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";

import { HoverZoomPane } from "./gallery-hover-zoom";
import { PdpInteractiveGallery } from "./pdp-interactive-gallery";

/**
 * The CI perf harness serves a fixed set of image widths (cldUrl throws on any
 * other width). Every width the PDP gallery requests must be in that set, or
 * the PDP renders an error boundary and the content-readiness gate fails.
 */
describe("PDP gallery under the CI perf image fixture", () => {
  beforeAll(() => {
    vi.stubEnv("NEXT_PUBLIC_CI_PERF_HARNESS", "1");
    vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", "preview");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "http://localhost:3000");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://10.0.0.5:8000");
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
  });
  afterEach(cleanup);

  it("renders a priority main image and thumbnails from the fixture loader", async () => {
    render(
      <NextIntlClientProvider locale="en" messages={{ catalog: catalogMessages }}>
        <PdpInteractiveGallery
          images={[
            { publicId: "ci-perf/smartphone-x1", alt: "Smartphone X1" },
            { publicId: "ci-perf/smartphone-x1", alt: "Smartphone X1 back" },
          ]}
          emptyLabel="No image"
          previousLabel="Previous"
          nextLabel="Next"
          indicatorLabel={(c, t) => `${c} / ${t}`}
        />
      </NextIntlClientProvider>,
    );
    const root = screen.getByTestId("pdp-interactive-gallery");
    const main = root.querySelector("img");
    expect(main?.getAttribute("src")).toBe("/api/ci-perf-media?width=720");
    expect(main?.getAttribute("loading")).toBe("eager");
    expect(main?.style.opacity).toBe("1");
    expect((await screen.findAllByTestId("gallery-thumb-0")).length).toBeGreaterThan(0);
    fireEvent.pointerEnter(root.querySelector(".group")!);
  });

  it("hover zoom pane requests a fixture-supported width", () => {
    expect(() =>
      render(
        <HoverZoomPane
          publicId="ci-perf/smartphone-x1"
          alt="x"
          pointer={{ x: 10, y: 10 }}
          box={{ width: 400, height: 400 }}
          layout={{
            pane: { left: 420, top: 0, width: 400, height: 500 },
            zoom: 2.5,
            lens: { width: 160, height: 200 },
          }}
        />,
      ),
    ).not.toThrow();
  });
});
