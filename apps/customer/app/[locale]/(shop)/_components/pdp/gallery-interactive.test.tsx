// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";

import { PdpInteractiveGallery } from "./pdp-interactive-gallery";
import { computeZoomLayout, magnifierLensRect } from "./zoom-math";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

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
    expect(screen.queryByTestId("gallery-thumb-strip")).not.toBeInTheDocument();
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

describe("computeZoomLayout", () => {
  const stage = { left: 0, top: 100, width: 640, height: 640 };
  const viewport = { width: 1280, height: 900 };

  it("overlays the details column when it sits to the right of the stage", () => {
    const layout = computeZoomLayout(
      stage,
      { left: 672, top: 100, width: 416, height: 500 },
      viewport,
    );
    expect(layout).not.toBeNull();
    expect(layout!.pane.left).toBe(672);
    expect(layout!.pane.width).toBe(416);
    expect(layout!.pane.height).toBeGreaterThanOrEqual(640);
    expect(layout!.lens.width).toBeLessThan(stage.width);
    expect(layout!.lens.height).toBeLessThan(stage.height);
  });

  it("disables the lens in a single-column layout (details below the stage)", () => {
    expect(
      computeZoomLayout(
        { left: 0, top: 0, width: 716, height: 716 },
        { left: 0, top: 740, width: 716, height: 500 },
        { width: 755, height: 900 },
      ),
    ).toBeNull();
    expect(computeZoomLayout(stage, null, viewport)).toBeNull();
  });

  it("keeps the pane inside the viewport vertically", () => {
    const layout = computeZoomLayout(
      { ...stage, top: 300 },
      { left: 672, top: 300, width: 416, height: 400 },
      { width: 1280, height: 800 },
    );
    expect(layout!.pane.top + layout!.pane.height).toBeLessThanOrEqual(800);
  });
});

describe("hover zoom pane", () => {
  function mockRects(stageRect: DOMRect, targetRect: DOMRect | null) {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
      this: Element,
    ) {
      if (this.getAttribute("data-testid") === "gallery-strip") return stageRect;
      if (this.hasAttribute("data-pdp-zoom-target")) return targetRect ?? stageRect;
      return stageRect;
    });
  }
  const rect = (left: number, top: number, width: number, height: number) =>
    ({
      left,
      top,
      width,
      height,
      right: left + width,
      bottom: top + height,
      x: left,
      y: top,
    }) as DOMRect;

  function mountWithColumn(withTarget: boolean) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
    const { container } = renderGallery(2);
    const root = document.createElement("div");
    root.setAttribute("data-pdp-zoom-root", "");
    container.parentElement!.appendChild(root);
    root.appendChild(container);
    if (withTarget) {
      const target = document.createElement("div");
      target.setAttribute("data-pdp-zoom-target", "");
      root.appendChild(target);
    }
    return screen.getByTestId("gallery-strip");
  }

  it("portals a large pane over the right column when two-column", () => {
    mockRects(rect(0, 100, 640, 640), rect(672, 100, 416, 500));
    Object.defineProperty(window, "innerWidth", {
      value: 1280,
      configurable: true,
    });
    Object.defineProperty(window, "innerHeight", {
      value: 900,
      configurable: true,
    });
    const stage = mountWithColumn(true);
    fireEvent.pointerEnter(stage);
    fireEvent.pointerMove(stage, { clientX: 300, clientY: 400 });
    return waitFor(() => {
      fireEvent.pointerMove(stage, { clientX: 300, clientY: 400 });
      const pane = screen.getByTestId("pdp-gallery-zoom-pane");
      expect(pane.parentElement).toBe(document.body);
      expect(pane.style.left).toBe("672px");
      expect(screen.getByTestId("pdp-gallery-zoom-lens")).toBeInTheDocument();
    });
  });

  it("renders no lens or pane in a single-column layout", async () => {
    mockRects(rect(0, 0, 716, 716), rect(0, 740, 716, 500));
    Object.defineProperty(window, "innerWidth", {
      value: 755,
      configurable: true,
    });
    const stage = mountWithColumn(true);
    fireEvent.pointerEnter(stage);
    fireEvent.pointerMove(stage, { clientX: 300, clientY: 400 });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("pdp-gallery-zoom-lens")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pdp-gallery-zoom-pane")).not.toBeInTheDocument();
  });
});
