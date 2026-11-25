"use client";

import { cldUrl } from "@vergeo/ui/src/media/cloudinary-url";
import { useEffect, useState, type CSSProperties } from "react";

import { magnifierLensRect, zoomPaneBackgroundPosition } from "./zoom-math";

const LENS_PX = 96;
const ZOOM_SCALE = 2.5;

export type HoverZoomPaneProps = {
  publicId: string;
  alt: string;
  cloudName?: string;
  pointer: { x: number; y: number } | null;
  box: { width: number; height: number };
  reducedMotion: boolean;
};

export function HoverZoomPane({
  publicId,
  alt,
  cloudName,
  pointer,
  box,
  reducedMotion,
}: HoverZoomPaneProps) {
  const [hiResUrl, setHiResUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!pointer) {
      return;
    }
    setHiResUrl(cldUrl(publicId, { width: 1600, quality: "auto", cloudName }) || null);
  }, [cloudName, pointer, publicId]);

  if (!pointer || box.width < 1 || box.height < 1) {
    return null;
  }

  const lens = magnifierLensRect(pointer.x, pointer.y, box, LENS_PX);
  const bg = zoomPaneBackgroundPosition(pointer.x, pointer.y, box);

  const lensStyle: CSSProperties = {
    left: lens.left,
    top: lens.top,
    width: LENS_PX,
    height: LENS_PX,
    borderStyle: "dashed",
  };

  const paneStyle: CSSProperties = {
    backgroundImage: hiResUrl ? `url(${hiResUrl})` : undefined,
    backgroundSize: `${ZOOM_SCALE * 100}%`,
    backgroundPosition: `${bg.xPercent}% ${bg.yPercent}%`,
    backgroundRepeat: "no-repeat",
  };

  return (
    <>
      <div
        data-testid="pdp-gallery-zoom-lens"
        aria-hidden
        className="pointer-events-none absolute z-10 border border-primary/60 bg-primary/10"
        style={lensStyle}
      />
      <div
        data-testid="pdp-gallery-zoom-pane"
        aria-hidden
        className="pointer-events-none absolute left-[calc(100%+0.5rem)] top-0 z-20 hidden h-full w-full min-w-0 overflow-hidden rounded border border-border bg-surface shadow lg:block"
        style={{
          ...paneStyle,
          transition: reducedMotion ? "none" : undefined,
        }}
      >
        <span className="sr-only">{alt}</span>
      </div>
    </>
  );
}
