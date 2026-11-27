"use client";

import { cldUrl } from "@vergeo/ui/src/media/cloudinary-url";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { rectangularLens, type ZoomLayout } from "./zoom-math";

/** Long edge (px) of the Cloudinary source used inside the pane. */
const HI_RES_WIDTH = 2160;

export type HoverZoomPaneProps = {
  publicId: string;
  alt: string;
  cloudName?: string;
  /** Pointer position relative to the image stage (top-left origin). */
  pointer: { x: number; y: number } | null;
  /** Image stage size in px. */
  box: { width: number; height: number };
  /** Geometry from `computeZoomLayout`; null disables lens + pane. */
  layout: ZoomLayout | null;
  reducedMotion?: boolean;
};

/**
 * Amazon-style hover zoom: a rectangular lens over the stage plus a LARGE pane that
 * overlays the details/buy column. The pane is portalled to <body> with fixed
 * positioning so the stage's `overflow-hidden` (and any other ancestor overflow or
 * stacking context) can neither clip nor bury it.
 */
export function HoverZoomPane({
  publicId,
  alt,
  cloudName,
  pointer,
  box,
  layout,
  reducedMotion = false,
}: HoverZoomPaneProps) {
  const [hiResUrl, setHiResUrl] = useState<string | null>(null);
  useEffect(() => {
    setHiResUrl(cldUrl(publicId, { width: HI_RES_WIDTH, quality: "auto", cloudName }) || null);
  }, [cloudName, publicId]);

  if (!layout || !pointer || box.width < 1 || box.height < 1) {
    return null;
  }

  const lens = rectangularLens(pointer.x, pointer.y, box, layout.lens);
  // The pane image mirrors the stage's object-contain rendering at `zoom`x, shifted so
  // the lensed region fills the pane exactly.
  const offsetX = -lens.left * layout.zoom;
  const offsetY = -lens.top * layout.zoom;

  return (
    <>
      <div
        data-testid="pdp-gallery-zoom-lens"
        aria-hidden
        className="pointer-events-none absolute z-10 border border-primary/60 bg-primary/10"
        style={{
          left: lens.left,
          top: lens.top,
          width: layout.lens.width,
          height: layout.lens.height,
        }}
      />
      {typeof document !== "undefined"
        ? createPortal(
            <div
              data-testid="pdp-gallery-zoom-pane"
              aria-hidden
              className="pointer-events-none fixed z-50 overflow-hidden rounded-lg border border-border bg-surface shadow-lg"
              style={{
                left: layout.pane.left,
                top: layout.pane.top,
                width: layout.pane.width,
                height: layout.pane.height,
                transition: reducedMotion ? "none" : undefined,
              }}
            >
              {hiResUrl ? (
                // Plain <img>: hi-res Cloudinary source positioned by the lens maths (next/image cannot express this).
                <img
                  data-testid="pdp-gallery-zoom-image"
                  src={hiResUrl}
                  alt=""
                  draggable={false}
                  className="absolute left-0 top-0 max-w-none select-none object-contain"
                  style={{
                    width: box.width * layout.zoom,
                    height: box.height * layout.zoom,
                    transform: `translate(${offsetX}px, ${offsetY}px)`,
                  }}
                />
              ) : null}
              <span className="sr-only">{alt}</span>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
