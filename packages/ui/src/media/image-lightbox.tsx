"use client";

import { useRef, useState, type CSSProperties } from "react";

import { Modal } from "../modal";

import { cldUrl } from "./cloudinary-url";

import type { GalleryImage } from "./image-gallery";

export type ImageZoomLabels = {
  open: string;
  close: string;
  title: string;
  zoomIn: string;
  zoomOut: string;
};

const controlStyle: CSSProperties = {
  minWidth: "44px",
  minHeight: "44px",
  padding: "var(--sp-2)",
  border: "1px solid var(--border)",
  borderRadius: "var(--r)",
  background: "var(--surface)",
  color: "var(--text)",
};

export function ImageLightbox({
  images,
  initialIndex,
  cloudName,
  labels,
  previousLabel,
  nextLabel,
  indicatorLabel,
  fallbackLabel,
  onClose,
}: {
  images: GalleryImage[];
  initialIndex: number;
  cloudName?: string;
  labels: ImageZoomLabels;
  previousLabel: string;
  nextLabel: string;
  indicatorLabel: (current: number, total: number) => string;
  fallbackLabel?: string;
  onClose: (index: number) => void;
}) {
  const [index, setIndex] = useState(initialIndex);
  const [enlarged, setEnlarged] = useState(false);
  const [failed, setFailed] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const image = images[index]!;
  const src = cldUrl(image.publicId, { width: 2160, cloudName });
  const unavailable = failed || !src;

  function resetView() {
    setEnlarged(false);
    setFailed(false);
    if (viewportRef.current) {
      viewportRef.current.scrollTop = 0;
      viewportRef.current.scrollLeft = 0;
    }
  }

  function navigate(offset: number) {
    const next = Math.max(0, Math.min(images.length - 1, index + offset));
    if (next === index) return;
    resetView();
    setIndex(next);
  }

  return (
    <Modal
      open
      title={labels.title}
      onClose={() => onClose(index)}
      panelStyle={{
        width: "min(100% - var(--sp-4), 72rem)",
        maxHeight: "94dvh",
        padding: "var(--sp-3)",
        margin: "var(--sp-2)",
      }}
    >
      <div
        onKeyDown={(event) => {
          // Portals bubble through the gallery: never navigate both carousels.
          event.stopPropagation();
          // Let the scrollable enlarged image consume arrows for keyboard panning.
          if (enlarged && event.target === viewportRef.current) return;
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            navigate(event.key === "ArrowLeft" ? -1 : 1);
          }
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "var(--sp-2)",
            flexWrap: "wrap",
            marginBottom: "var(--sp-2)",
          }}
        >
          <button type="button" style={controlStyle} onClick={() => onClose(index)}>
            {labels.close}
          </button>
          <button
            type="button"
            style={controlStyle}
            disabled={unavailable}
            aria-pressed={enlarged}
            onClick={() => {
              if (enlarged) resetView();
              else setEnlarged(true);
            }}
          >
            {enlarged ? labels.zoomOut : labels.zoomIn}
          </button>
        </div>
        <div
          ref={viewportRef}
          role="region"
          aria-label={image.alt || labels.title}
          tabIndex={0}
          data-testid="image-zoom-viewport"
          style={{
            overflow: "auto",
            height: "55dvh",
            borderRadius: "var(--r)",
            background: "var(--bg-2)",
            overscrollBehavior: "contain",
          }}
        >
          {unavailable ? (
            <p role="status" style={{ padding: "var(--sp-4)" }}>
              {fallbackLabel ?? image.alt}
            </p>
          ) : (
            <img
              key={src}
              src={src}
              alt={image.alt}
              onError={() => {
                setFailed(true);
                setEnlarged(false);
              }}
              draggable={false}
              style={{
                display: "block",
                width: enlarged ? "200%" : "100%",
                height: enlarged ? "200%" : "100%",
                maxWidth: "none",
                objectFit: "contain",
              }}
            />
          )}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--sp-2)",
            marginTop: "var(--sp-2)",
          }}
        >
          <button
            type="button"
            style={controlStyle}
            aria-label={previousLabel}
            disabled={index === 0}
            onClick={() => navigate(-1)}
          >
            ‹
          </button>
          <p aria-live="polite" aria-atomic="true">
            {indicatorLabel(index + 1, images.length)}
          </p>
          <button
            type="button"
            style={controlStyle}
            aria-label={nextLabel}
            disabled={index === images.length - 1}
            onClick={() => navigate(1)}
          >
            ›
          </button>
        </div>
      </div>
    </Modal>
  );
}
