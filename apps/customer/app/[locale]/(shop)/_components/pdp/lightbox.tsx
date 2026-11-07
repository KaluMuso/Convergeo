"use client";

import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";

import { formatPdpGalleryIndicator } from "./gallery-labels";

export const MIN_ZOOM = 1;
export const MAX_ZOOM = 4;
/** Zoom applied by a click/tap or the + button. */
export const STEP_ZOOM = 2;

export type LightboxLabels = {
  /** Accessible name of the "view full screen" control on the gallery. */
  open: string;
  dialog: string;
  close: string;
  previous: string;
  next: string;
  zoomIn: string;
  zoomOut: string;
  /** ICU-style template with {current} and {total}. */
  indicator: string;
};

export type LightboxProps = {
  images: Array<{ publicId: string; alt: string }>;
  initialIndex: number;
  cloudName?: string;
  labels: LightboxLabels;
  onClose: (lastIndex: number) => void;
};

export function clampZoom(value: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
}

/** Keep the pan offset inside the zoomed image so it can't be dragged off-screen. */
export function clampPan(
  offset: { x: number; y: number },
  zoom: number,
  box: { width: number; height: number },
): { x: number; y: number } {
  const maxX = ((zoom - 1) * box.width) / 2;
  const maxY = ((zoom - 1) * box.height) / 2;
  return {
    x: Math.min(maxX, Math.max(-maxX, offset.x)),
    y: Math.min(maxY, Math.max(-maxY, offset.y)),
  };
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return reduced;
}

const FOCUSABLE = 'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/**
 * Full-screen image viewer with zoom. Dependency-free:
 * - touch: pinch to zoom, drag to pan, swipe left/right (at 1x) to change image
 * - desktop: wheel to zoom, click to toggle zoom, drag to pan
 * - keyboard: ←/→ change image, +/- zoom, 0 resets, Escape closes; focus is trapped
 *   and returned to the opener on close.
 */
export function Lightbox({ images, initialIndex, cloudName, labels, onClose }: LightboxProps) {
  const total = images.length;
  const [index, setIndex] = useState(() => Math.min(Math.max(initialIndex, 0), total - 1));
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const reducedMotion = usePrefersReducedMotion();
  const dialogRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<Element | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{
    startDistance: number;
    startZoom: number;
    startX: number;
    startY: number;
    startPan: { x: number; y: number };
    moved: boolean;
  } | null>(null);

  const stageBox = useCallback(() => {
    const rect = stageRef.current?.getBoundingClientRect();
    return { width: rect?.width || 1, height: rect?.height || 1 };
  }, []);

  const applyZoom = useCallback(
    (next: number) => {
      const clamped = clampZoom(next);
      setZoom(clamped);
      setPan((current) => (clamped === MIN_ZOOM ? { x: 0, y: 0 } : clampPan(current, clamped, stageBox())));
    },
    [stageBox],
  );

  const go = useCallback(
    (delta: number) => {
      setIndex((current) => Math.min(Math.max(current + delta, 0), total - 1));
      setZoom(MIN_ZOOM);
      setPan({ x: 0, y: 0 });
    },
    [total],
  );

  const close = useCallback(() => onClose(index), [index, onClose]);

  // Focus management + body scroll lock.
  useEffect(() => {
    openerRef.current = document.activeElement;
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      const opener = openerRef.current;
      if (opener instanceof HTMLElement) {
        opener.focus();
      }
    };
  }, []);

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      switch (event.key) {
        case "Escape":
          event.preventDefault();
          close();
          return;
        case "ArrowLeft":
          event.preventDefault();
          go(-1);
          return;
        case "ArrowRight":
          event.preventDefault();
          go(1);
          return;
        case "+":
        case "=":
          event.preventDefault();
          applyZoom(zoom + 1);
          return;
        case "-":
          event.preventDefault();
          applyZoom(zoom - 1);
          return;
        case "0":
          event.preventDefault();
          applyZoom(MIN_ZOOM);
          return;
        case "Tab": {
          const nodes = dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
          if (!nodes || nodes.length === 0) {
            return;
          }
          const first = nodes[0];
          const last = nodes[nodes.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
          return;
        }
        default:
      }
    },
    [applyZoom, close, go, zoom],
  );

  const onWheel = useCallback(
    (event: ReactWheelEvent<HTMLDivElement>) => {
      event.preventDefault();
      applyZoom(zoom * (event.deltaY < 0 ? 1.2 : 1 / 1.2));
    },
    [applyZoom, zoom],
  );

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.currentTarget.setPointerCapture?.(event.pointerId);
      pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const points = [...pointers.current.values()];
      const [a, b] = points;
      gesture.current = {
        startDistance: a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0,
        startZoom: zoom,
        startX: event.clientX,
        startY: event.clientY,
        startPan: pan,
        moved: gesture.current?.moved ?? false,
      };
      if (points.length === 1 && gesture.current) {
        gesture.current.moved = false;
      }
    },
    [pan, zoom],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (!pointers.current.has(event.pointerId) || !gesture.current) {
        return;
      }
      pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const points = [...pointers.current.values()];
      const start = gesture.current;
      if (points.length >= 2 && start.startDistance > 0) {
        const [a, b] = points;
        if (a && b) {
          start.moved = true;
          applyZoom((start.startZoom * Math.hypot(a.x - b.x, a.y - b.y)) / start.startDistance);
        }
        return;
      }
      const dx = event.clientX - start.startX;
      const dy = event.clientY - start.startY;
      if (Math.abs(dx) > 6 || Math.abs(dy) > 6) {
        start.moved = true;
      }
      if (zoom > MIN_ZOOM) {
        setPan(clampPan({ x: start.startPan.x + dx, y: start.startPan.y + dy }, zoom, stageBox()));
      }
    },
    [applyZoom, stageBox, zoom],
  );

  const onPointerUp = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const start = gesture.current;
      pointers.current.delete(event.pointerId);
      if (pointers.current.size > 0 || !start) {
        return;
      }
      gesture.current = null;
      const dx = event.clientX - start.startX;
      if (!start.moved) {
        // Tap / click toggles zoom.
        applyZoom(zoom > MIN_ZOOM ? MIN_ZOOM : STEP_ZOOM);
        return;
      }
      if (zoom === MIN_ZOOM && Math.abs(dx) > 50) {
        go(dx < 0 ? 1 : -1);
      }
    },
    [applyZoom, go, zoom],
  );

  const image = images[index];
  if (!image) {
    return null;
  }

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={labels.dialog}
      data-testid="pdp-lightbox"
      onKeyDown={onKeyDown}
      className="fixed inset-0 z-50 flex flex-col text-bg"
      style={{ backgroundColor: "color-mix(in srgb, var(--text) 94%, transparent)" }}
    >
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <p aria-live="polite" data-testid="pdp-lightbox-indicator" className="text-sm">
          {formatPdpGalleryIndicator(labels.indicator, index + 1, total)}
        </p>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={labels.zoomOut}
            data-testid="pdp-lightbox-zoom-out"
            onClick={() => applyZoom(zoom - 1)}
            disabled={zoom <= MIN_ZOOM}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded text-xl disabled:opacity-40"
          >
            <span aria-hidden="true">−</span>
          </button>
          <button
            type="button"
            aria-label={labels.zoomIn}
            data-testid="pdp-lightbox-zoom-in"
            onClick={() => applyZoom(zoom + 1)}
            disabled={zoom >= MAX_ZOOM}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded text-xl disabled:opacity-40"
          >
            <span aria-hidden="true">+</span>
          </button>
          <button
            ref={closeRef}
            type="button"
            aria-label={labels.close}
            data-testid="pdp-lightbox-close"
            onClick={close}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded text-xl"
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>
      </div>

      <div
        ref={stageRef}
        data-testid="pdp-lightbox-stage"
        data-zoom={zoom.toFixed(2)}
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden"
        style={{ touchAction: "none", cursor: zoom > MIN_ZOOM ? "zoom-out" : "zoom-in" }}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div
          className="w-full max-w-3xl"
          style={{
            transform: `translate3d(${pan.x}px, ${pan.y}px, 0) scale(${zoom})`,
            transition: reducedMotion ? "none" : "transform var(--dur, 160ms) var(--ease-out, ease-out)",
          }}
        >
          <CloudinaryImage
            publicId={image.publicId}
            alt={image.alt}
            ratio="4/3"
            cloudName={cloudName}
            width={1600}
            sizes="100vw"
            priority
          />
        </div>
      </div>

      {total > 1 ? (
        <div className="flex items-center justify-between px-3 py-2">
          <button
            type="button"
            aria-label={labels.previous}
            data-testid="pdp-lightbox-prev"
            onClick={() => go(-1)}
            disabled={index === 0}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded text-2xl disabled:opacity-40"
          >
            <span aria-hidden="true">‹</span>
          </button>
          <button
            type="button"
            aria-label={labels.next}
            data-testid="pdp-lightbox-next"
            onClick={() => go(1)}
            disabled={index === total - 1}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded text-2xl disabled:opacity-40"
          >
            <span aria-hidden="true">›</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
