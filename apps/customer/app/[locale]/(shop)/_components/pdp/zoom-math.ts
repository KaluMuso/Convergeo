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
