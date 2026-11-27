/** Desktop hover magnifier: keep the lens square inside the main image bounds. */
export function magnifierLensRect(
  pointerX: number,
  pointerY: number,
  box: { width: number; height: number },
  lensSize: number,
): { left: number; top: number } {
  const half = lensSize / 2;
  return {
    left: Math.min(box.width - lensSize, Math.max(0, pointerX - half)),
    top: Math.min(box.height - lensSize, Math.max(0, pointerY - half)),
  };
}

/**
 * Background position (percentage) for a 2.5× zoom pane following the pointer.
 * Pointer coordinates are relative to the main image box (top-left origin).
 */
export function zoomPaneBackgroundPosition(
  pointerX: number,
  pointerY: number,
  box: { width: number; height: number },
): { xPercent: number; yPercent: number } {
  const xPercent = box.width > 0 ? (pointerX / box.width) * 100 : 50;
  const yPercent = box.height > 0 ? (pointerY / box.height) * 100 : 50;
  return { xPercent, yPercent };
}

export function isCoarsePointer(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(pointer: coarse)").matches;
}

export type ZoomRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

const MIN_PANE_WIDTH = 240;
const VIEWPORT_MARGIN = 8;
const BASE_ZOOM = 2.5;

export type ZoomLayout = {
  /** Fixed-position (viewport coordinates) rectangle of the zoom pane. */
  pane: { left: number; top: number; width: number; height: number };
  /** Magnification of the stage image inside the pane. */
  zoom: number;
  /** Lens size in stage pixels (pane size / zoom). */
  lens: { width: number; height: number };
};

/**
 * Amazon-style zoom geometry. The pane overlays the details column (`target`), so it
 * only exists when that column sits to the right of the image stage (two-column
 * layout). Single-column layouts (target below / overlapping the stage) return null and
 * the caller disables the lens entirely. All rects are viewport coordinates.
 */
export function computeZoomLayout(
  stage: ZoomRect,
  target: ZoomRect | null,
  viewport: { width: number; height: number },
): ZoomLayout | null {
  if (!target || stage.width < 1 || stage.height < 1) {
    return null;
  }
  const sideBySide = target.left >= stage.left + stage.width - 1;
  if (!sideBySide || target.width < MIN_PANE_WIDTH) {
    return null;
  }
  const top = Math.max(VIEWPORT_MARGIN, stage.top);
  const wanted = Math.max(stage.height, target.width * 1.25);
  const height = Math.min(wanted, viewport.height - top - VIEWPORT_MARGIN);
  if (height < MIN_PANE_WIDTH) {
    return null;
  }
  const width = Math.min(target.width, viewport.width - target.left - VIEWPORT_MARGIN);
  if (width < MIN_PANE_WIDTH) {
    return null;
  }
  // Keep the lens strictly smaller than the stage so it can always move.
  const zoom = Math.max(BASE_ZOOM, (width / stage.width) * 1.25, (height / stage.height) * 1.25);
  return {
    pane: { left: target.left, top, width, height },
    zoom,
    lens: { width: width / zoom, height: height / zoom },
  };
}

/** Rectangular lens (stage coordinates) centred on the pointer, clamped inside the stage. */
export function rectangularLens(
  pointerX: number,
  pointerY: number,
  stage: { width: number; height: number },
  lens: { width: number; height: number },
): { left: number; top: number } {
  return {
    left: Math.min(stage.width - lens.width, Math.max(0, pointerX - lens.width / 2)),
    top: Math.min(stage.height - lens.height, Math.max(0, pointerY - lens.height / 2)),
  };
}
