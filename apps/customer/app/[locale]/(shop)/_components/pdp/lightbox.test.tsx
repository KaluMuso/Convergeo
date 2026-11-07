// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Lightbox, clampPan, clampZoom, MAX_ZOOM, type LightboxLabels } from "./lightbox";

const labels: LightboxLabels = {
  open: "View full screen",
  dialog: "Image viewer",
  close: "Close viewer",
  previous: "Previous image",
  next: "Next image",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  indicator: "Image {current} of {total}",
};

const images = [
  { publicId: "demo/one", alt: "Dress front" },
  { publicId: "demo/two", alt: "Dress back" },
  { publicId: "demo/three", alt: "Dress detail" },
];

function mockReducedMotion(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: query.includes("reduce") ? matches : false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  });
}

// jsdom has no PointerEvent: without it fireEvent.pointer* drops clientX/pointerId.
if (typeof window.PointerEvent === "undefined") {
  class TestPointerEvent extends MouseEvent {
    pointerId: number;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
    }
  }
  Object.defineProperty(window, "PointerEvent", { value: TestPointerEvent, writable: true });
}

beforeEach(() => mockReducedMotion(false));
afterEach(() => cleanup());

function renderLightbox(onClose = vi.fn(), initialIndex = 0) {
  const view = render(
    <Lightbox
      images={images}
      initialIndex={initialIndex}
      cloudName="test-cloud"
      labels={labels}
      onClose={onClose}
    />,
  );
  return { ...view, onClose, dialog: screen.getByRole("dialog", { name: "Image viewer" }) };
}

describe("Lightbox", () => {
  it("is a labelled modal dialog that focuses its close button", () => {
    const { dialog } = renderLightbox();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Close viewer" })).toHaveFocus();
    expect(screen.getByTestId("pdp-lightbox-indicator")).toHaveTextContent("Image 1 of 3");
  });

  it("navigates with arrow keys and closes on Escape, reporting the last image", () => {
    const { dialog, onClose } = renderLightbox();
    fireEvent.keyDown(dialog, { key: "ArrowRight" });
    fireEvent.keyDown(dialog, { key: "ArrowRight" });
    fireEvent.keyDown(dialog, { key: "ArrowRight" });
    expect(screen.getByTestId("pdp-lightbox-indicator")).toHaveTextContent("Image 3 of 3");
    expect(screen.getByRole("img", { name: "Dress detail" })).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: "ArrowLeft" });
    expect(screen.getByTestId("pdp-lightbox-indicator")).toHaveTextContent("Image 2 of 3");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledWith(1);
  });

  it("zooms with buttons, keys and the wheel, clamped to the allowed range", () => {
    const { dialog } = renderLightbox();
    const stage = screen.getByTestId("pdp-lightbox-stage");
    expect(stage).toHaveAttribute("data-zoom", "1.00");
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(stage).toHaveAttribute("data-zoom", "2.00");
    fireEvent.keyDown(dialog, { key: "+" });
    fireEvent.keyDown(dialog, { key: "+" });
    fireEvent.keyDown(dialog, { key: "+" });
    expect(stage).toHaveAttribute("data-zoom", MAX_ZOOM.toFixed(2));
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeDisabled();

    fireEvent.keyDown(dialog, { key: "0" });
    expect(stage).toHaveAttribute("data-zoom", "1.00");
    fireEvent.wheel(stage, { deltaY: -100 });
    expect(Number(stage.getAttribute("data-zoom"))).toBeGreaterThan(1);
  });

  it("toggles zoom on a tap/click without movement", () => {
    renderLightbox();
    const stage = screen.getByTestId("pdp-lightbox-stage");
    fireEvent.pointerDown(stage, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerUp(stage, { pointerId: 1, clientX: 100, clientY: 100 });
    expect(stage).toHaveAttribute("data-zoom", "2.00");
    fireEvent.pointerDown(stage, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerUp(stage, { pointerId: 1, clientX: 100, clientY: 100 });
    expect(stage).toHaveAttribute("data-zoom", "1.00");
  });

  it("pinch-zooms with two pointers and swipes between images at 1x", () => {
    renderLightbox();
    const stage = screen.getByTestId("pdp-lightbox-stage");
    fireEvent.pointerDown(stage, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerDown(stage, { pointerId: 2, clientX: 200, clientY: 100 });
    fireEvent.pointerMove(stage, { pointerId: 2, clientX: 300, clientY: 100 });
    expect(Number(stage.getAttribute("data-zoom"))).toBeCloseTo(2, 1);
    fireEvent.pointerUp(stage, { pointerId: 2, clientX: 300, clientY: 100 });
    fireEvent.pointerUp(stage, { pointerId: 1, clientX: 100, clientY: 100 });

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "0" });
    fireEvent.pointerDown(stage, { pointerId: 3, clientX: 300, clientY: 100 });
    fireEvent.pointerMove(stage, { pointerId: 3, clientX: 150, clientY: 100 });
    fireEvent.pointerUp(stage, { pointerId: 3, clientX: 150, clientY: 100 });
    expect(screen.getByTestId("pdp-lightbox-indicator")).toHaveTextContent("Image 2 of 3");
  });

  it("traps Tab focus inside the dialog", () => {
    const { dialog } = renderLightbox(vi.fn(), 1);
    const close = screen.getByRole("button", { name: "Close viewer" });
    const next = screen.getByRole("button", { name: "Next image" });
    next.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(close.ownerDocument.activeElement).not.toBe(next);
    expect(dialog.contains(document.activeElement)).toBe(true);

    screen.getByRole("button", { name: "Zoom in" }).focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(next);
  });

  it("returns focus to the opener and restores scrolling when closed", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const { unmount } = renderLightbox();
    expect(document.body.style.overflow).toBe("hidden");
    unmount();
    expect(document.activeElement).toBe(opener);
    expect(document.body.style.overflow).toBe("");
    opener.remove();
  });

  it("drops the zoom transition when the user prefers reduced motion", () => {
    mockReducedMotion(true);
    renderLightbox();
    const layer = screen.getByTestId("pdp-lightbox-stage").firstElementChild as HTMLElement;
    expect(layer.style.transition).toBe("none");
  });
});

describe("zoom maths", () => {
  it("clamps zoom and pan so the image cannot leave the stage", () => {
    expect(clampZoom(0.2)).toBe(1);
    expect(clampZoom(9)).toBe(MAX_ZOOM);
    expect(clampPan({ x: 500, y: -500 }, 2, { width: 400, height: 300 })).toEqual({
      x: 200,
      y: -150,
    });
    expect(clampPan({ x: 50, y: 50 }, 1, { width: 400, height: 300 })).toEqual({ x: 0, y: 0 });
  });
});
