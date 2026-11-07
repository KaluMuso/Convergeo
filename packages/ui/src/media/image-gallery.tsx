"use client";

import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import { CloudinaryImage } from "./cloudinary-image";
import type { ImageZoomLabels } from "./image-lightbox";

const ImageLightbox = lazy(() =>
  import("./image-lightbox").then((module) => ({
    default: module.ImageLightbox,
  })),
);

const MAX_IMAGES = 8;

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return reduced;
}

export type GalleryImage = {
  publicId: string;
  alt: string;
};

export type ImageGalleryProps = {
  images: GalleryImage[];
  cloudName?: string;
  ratio?: number | `${number}/${number}`;
  indicatorLabel: (current: number, total: number) => string;
  previousLabel: string;
  nextLabel: string;
  /** Label shown inside a slide when its Cloudinary asset fails to load. */
  imageFallbackLabel?: string;
  className?: string;
  /** Enable the accessible image viewer with translated labels. */
  zoomLabels?: ImageZoomLabels;
};

export function ImageGallery({
  images,
  cloudName,
  ratio = "4/3",
  indicatorLabel,
  previousLabel,
  nextLabel,
  imageFallbackLabel,
  className,
  zoomLabels,
}: ImageGalleryProps) {
  images = images.filter((image) => image.publicId.trim().length > 0);
  const galleryId = useId();
  const stripRef = useRef<HTMLDivElement>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [zoomOpen, setZoomOpen] = useState(false);
  const zoomTriggerRef = useRef<HTMLButtonElement>(null);
  const wasZoomOpen = useRef(false);
  useEffect(() => {
    // Native dialog makes the trigger inert until the viewer has unmounted.
    // Restore after that cleanup, including when product images change.
    if (wasZoomOpen.current && !zoomOpen) zoomTriggerRef.current?.focus();
    wasZoomOpen.current = zoomOpen;
  }, [zoomOpen]);
  const imageIdentity = JSON.stringify([cloudName, images.slice(0, MAX_IMAGES)]);
  const [previousIdentity, setPreviousIdentity] = useState(imageIdentity);
  // Close stale media before committing changed product/gallery props.
  if (previousIdentity !== imageIdentity) {
    setPreviousIdentity(imageIdentity);
    setCurrentIndex(0);
    setZoomOpen(false);
  }
  useEffect(() => {
    if (stripRef.current) stripRef.current.scrollLeft = 0;
  }, [imageIdentity]);
  const prefersReducedMotion = usePrefersReducedMotion();

  const cappedImages =
    images.length > MAX_IMAGES
      ? (() => {
          if (process.env.NODE_ENV !== "production") {
            console.warn(
              `[ImageGallery] Received ${images.length} images; hard-capping at ${MAX_IMAGES}.`,
            );
          }
          return images.slice(0, MAX_IMAGES);
        })()
      : images;

  const scrollToIndex = useCallback(
    (index: number) => {
      const strip = stripRef.current;
      if (strip) {
        const slide = strip.children.item(index) as HTMLElement | null;
        if (slide) {
          if (typeof slide.scrollIntoView === "function") {
            slide.scrollIntoView({
              behavior: prefersReducedMotion ? "auto" : "smooth",
              inline: "center",
              block: "nearest",
            });
          } else {
            strip.scrollLeft = slide.offsetLeft;
          }
        }
      }
      setCurrentIndex(index);
    },
    [prefersReducedMotion],
  );

  const goPrevious = useCallback(() => {
    const next = Math.max(0, currentIndex - 1);
    scrollToIndex(next);
  }, [currentIndex, scrollToIndex]);

  const goNext = useCallback(() => {
    const next = Math.min(cappedImages.length - 1, currentIndex + 1);
    scrollToIndex(next);
  }, [cappedImages.length, currentIndex, scrollToIndex]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goPrevious();
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        goNext();
      }
    },
    [goNext, goPrevious],
  );

  const handleScroll = useCallback(() => {
    const strip = stripRef.current;
    if (!strip || strip.children.length === 0) {
      return;
    }
    const center = strip.scrollLeft + strip.clientWidth / 2;
    let closest = 0;
    let closestDistance = Number.POSITIVE_INFINITY;
    for (let i = 0; i < strip.children.length; i += 1) {
      const child = strip.children.item(i) as HTMLElement;
      const childCenter = child.offsetLeft + child.offsetWidth / 2;
      const distance = Math.abs(center - childCenter);
      if (distance < closestDistance) {
        closestDistance = distance;
        closest = i;
      }
    }
    setCurrentIndex(closest);
  }, []);

  if (cappedImages.length === 0) {
    return null;
  }

  return (
    <div
      className={className}
      role="region"
      aria-roledescription="carousel"
      aria-label={indicatorLabel(currentIndex + 1, cappedImages.length)}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      style={{ display: "grid", gap: "var(--sp-3)" }}
    >
      <div style={{ position: "relative" }}>
        <div
          ref={stripRef}
          onScroll={zoomOpen ? undefined : handleScroll}
          data-testid="gallery-strip"
          style={{
            display: "flex",
            overflowX: "auto",
            scrollSnapType: "x mandatory",
            scrollBehavior: prefersReducedMotion ? "auto" : "smooth",
            gap: "var(--sp-2)",
            borderRadius: "var(--r)",
            WebkitOverflowScrolling: "touch",
          }}
        >
          {cappedImages.map((image, index) => (
            <div
              key={`${galleryId}-${image.publicId}-${index}`}
              data-testid={`gallery-slide-${index}`}
              style={{
                flex: "0 0 100%",
                scrollSnapAlign: "center",
              }}
            >
              <CloudinaryImage
                publicId={image.publicId}
                alt={image.alt}
                ratio={ratio}
                cloudName={cloudName}
                priority={index === 0}
                fallbackLabel={imageFallbackLabel}
              />
            </div>
          ))}
        </div>

        <div
          style={{
            position: "absolute",
            insetInline: "var(--sp-2)",
            top: "50%",
            transform: "translateY(-50%)",
            display: "flex",
            justifyContent: "space-between",
            pointerEvents: "none",
          }}
        >
          <button
            type="button"
            aria-label={previousLabel}
            onClick={goPrevious}
            disabled={currentIndex === 0}
            data-testid="gallery-prev"
            style={{
              pointerEvents: "auto",
              minHeight: "44px",
              minWidth: "44px",
            }}
          >
            ‹
          </button>
          <button
            type="button"
            aria-label={nextLabel}
            onClick={goNext}
            disabled={currentIndex === cappedImages.length - 1}
            data-testid="gallery-next"
            style={{
              pointerEvents: "auto",
              minHeight: "44px",
              minWidth: "44px",
            }}
          >
            ›
          </button>
        </div>
      </div>

      {zoomLabels ? (
        <button
          type="button"
          ref={zoomTriggerRef}
          aria-haspopup="dialog"
          onClick={() => setZoomOpen(true)}
          style={{
            minHeight: "44px",
            padding: "var(--sp-2)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r)",
            background: "var(--surface)",
            color: "var(--text)",
          }}
        >
          {zoomLabels.open}
        </button>
      ) : null}
      {zoomLabels && zoomOpen ? (
        <Suspense
          fallback={
            <button type="button" onClick={() => setZoomOpen(false)}>
              {zoomLabels.close}
            </button>
          }
        >
          <ImageLightbox
            images={cappedImages}
            initialIndex={currentIndex}
            cloudName={cloudName}
            labels={zoomLabels}
            previousLabel={previousLabel}
            nextLabel={nextLabel}
            indicatorLabel={indicatorLabel}
            fallbackLabel={imageFallbackLabel}
            onClose={(index) => {
              setZoomOpen(false);
              scrollToIndex(index);
            }}
          />
        </Suspense>
      ) : null}

      <p data-testid="gallery-indicator" aria-live="polite">
        {indicatorLabel(currentIndex + 1, cappedImages.length)}
      </p>

      <div
        data-testid="gallery-thumbs"
        style={{
          display: "flex",
          gap: "var(--sp-2)",
          overflowX: "auto",
          paddingBottom: "var(--sp-1)",
        }}
      >
        {cappedImages.map((image, index) => (
          <button
            key={`thumb-${galleryId}-${image.publicId}-${index}`}
            type="button"
            aria-label={image.alt}
            aria-current={index === currentIndex ? "true" : undefined}
            onClick={() => scrollToIndex(index)}
            data-testid={`gallery-thumb-${index}`}
            style={{
              flex: "0 0 auto",
              border:
                index === currentIndex ? "2px solid var(--primary)" : "1px solid var(--border)",
              borderRadius: "var(--r-sm)",
              padding: 0,
              minHeight: "44px",
              minWidth: "44px",
              overflow: "hidden",
            }}
          >
            <CloudinaryImage
              publicId={image.publicId}
              alt=""
              ratio={1}
              cloudName={cloudName}
              sizes="44px"
              fallbackLabel={imageFallbackLabel}
            />
          </button>
        ))}
      </div>
    </div>
  );
}
