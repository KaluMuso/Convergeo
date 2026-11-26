"use client";

import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

const GalleryThumbnails = dynamic(
  () => import("./gallery-thumbnails").then((m) => m.GalleryThumbnails),
  { ssr: false },
);

import type { LightboxLabels } from "./lightbox";

const Lightbox = dynamic(() => import("./lightbox").then((mod) => mod.Lightbox), { ssr: false });

const HoverZoomPane = dynamic(
  () => import("./gallery-hover-zoom").then((mod) => mod.HoverZoomPane),
  { ssr: false },
);

export type PdpGalleryImage = {
  publicId: string;
  alt: string;
};

export type PdpGalleryProps = {
  images: PdpGalleryImage[];
  cloudName?: string;
  emptyLabel: string;
  previousLabel: string;
  nextLabel: string;
  indicatorLabel: (current: number, total: number) => string;
  activeIndex?: number;
  lightboxLabels?: LightboxLabels;
  productTitle?: string;
  variantSummary?: string;
};

function GalleryFallback({ label }: { label: string }) {
  return (
    <div
      data-testid="pdp-gallery-empty"
      className="relative flex aspect-square max-h-[min(100vw,28rem)] w-full flex-col items-center justify-end rounded-lg bg-bg-2 px-4 pb-4 text-center text-sm text-text-3"
      data-image-stage
      role="img"
      aria-label={label}
    >
      <span aria-hidden>{label}</span>
    </div>
  );
}

function isCoarsePointer(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(pointer: coarse)").matches;
}

export function PdpInteractiveGallery({
  images,
  cloudName,
  emptyLabel,
  previousLabel,
  nextLabel,
  indicatorLabel,
  activeIndex,
  lightboxLabels,
  productTitle,
  variantSummary,
}: PdpGalleryProps) {
  const t = useTranslations("catalog");
  const usableImages = useMemo(
    () => images.filter((image) => image.publicId.trim().length > 0),
    [images],
  );
  const [currentIndex, setCurrentIndex] = useState(0);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [targetIndex, setTargetIndex] = useState<number | undefined>(activeIndex);
  const [horizontalThumbs, setHorizontalThumbs] = useState(false);
  const [zoomActive, setZoomActive] = useState(false);
  const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);
  const [zoomReady, setZoomReady] = useState(false);
  const mainRef = useRef<HTMLDivElement>(null);
  const coarse = useMemo(() => isCoarsePointer(), []);

  useEffect(() => {
    setTargetIndex(activeIndex);
  }, [activeIndex]);

  useEffect(() => {
    const img = mainRef.current?.querySelector("img");
    if (!img) {
      return;
    }
    const apply = () => {
      if (img.naturalWidth > 0 && img.naturalHeight > 0) {
        setHorizontalThumbs(img.naturalWidth / img.naturalHeight > 4 / 3);
      }
    };
    apply();
    img.addEventListener("load", apply);
    return () => img.removeEventListener("load", apply);
  }, [currentIndex, usableImages]);

  useEffect(() => {
    if (targetIndex === undefined || usableImages.length === 0) {
      return;
    }
    const clamped = Math.min(Math.max(targetIndex, 0), usableImages.length - 1);
    setCurrentIndex(clamped);
  }, [targetIndex, usableImages.length]);

  const openLightbox = useCallback((index: number) => setLightboxIndex(index), []);
  const closeLightbox = useCallback((lastIndex: number) => {
    setLightboxIndex(null);
    setTargetIndex(lastIndex);
  }, []);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (coarse || !zoomActive) {
        return;
      }
      const rect = event.currentTarget.getBoundingClientRect();
      setPointer({
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
    },
    [coarse, zoomActive],
  );

  const onPointerLeave = useCallback(() => {
    setPointer(null);
    setZoomActive(false);
  }, []);

  const onPointerEnter = useCallback(() => {
    if (coarse) {
      return;
    }
    setZoomReady(true);
    setZoomActive(true);
  }, [coarse]);

  const go = useCallback(
    (delta: number) => {
      setCurrentIndex((index) => {
        const next = Math.min(Math.max(index + delta, 0), usableImages.length - 1);
        return next;
      });
    },
    [usableImages.length],
  );

  if (usableImages.length === 0) {
    return <GalleryFallback label={emptyLabel} />;
  }

  const image = usableImages[Math.min(currentIndex, usableImages.length - 1)]!;
  const box = mainRef.current?.getBoundingClientRect();
  const boxSize = box ? { width: box.width, height: box.height } : { width: 1, height: 1 };

  const thumbLabel = (current: number, total: number) =>
    t("pdp.gallery.thumbAria", { current, total });

  const layout = horizontalThumbs ? "horizontal" : "vertical";

  return (
    <div
      className="relative flex w-full flex-col gap-2 lg:flex-row lg:items-start lg:gap-3"
      data-testid="pdp-interactive-gallery"
    >
      {layout === "vertical" && usableImages.length > 1 ? (
        <GalleryThumbnails
          images={usableImages}
          currentIndex={currentIndex}
          layout="vertical"
          cloudName={cloudName}
          imageLabel={thumbLabel}
          overflowLabel={(extra) => t("pdp.gallery.moreImages", { count: extra })}
          onSelect={setCurrentIndex}
          onOpenOverflow={() => openLightbox(currentIndex)}
        />
      ) : null}

      <div className="relative min-w-0 flex-1">
        <div
          ref={mainRef}
          data-testid="gallery-strip"
          className="group relative aspect-square w-full max-h-[min(100vw,28rem)] overflow-hidden rounded-lg border border-border bg-surface lg:max-h-none"
          onPointerEnter={onPointerEnter}
          onPointerMove={onPointerMove}
          onPointerLeave={onPointerLeave}
        >
          <button
            type="button"
            className="relative block h-full w-full cursor-zoom-in focus-visible:outline-none focus-visible:shadow-focusRing"
            aria-label={t("pdp.gallery.openLightbox")}
            onClick={() => openLightbox(currentIndex)}
          >
            <CloudinaryImage
              publicId={image.publicId}
              alt={image.alt}
              cloudName={cloudName}
              width={720}
              sizes="(max-width: 1024px) 100vw, 480px"
              priority={currentIndex === 0}
              ratio="1/1"
              className="h-full w-full object-contain"
              fallbackLabel={emptyLabel}
            />
          </button>

          {zoomReady && !coarse ? (
            <HoverZoomPane
              publicId={image.publicId}
              alt={image.alt}
              cloudName={cloudName}
              pointer={pointer}
              box={boxSize}
            />
          ) : null}

          {lightboxLabels ? (
            <button
              type="button"
              data-testid="pdp-gallery-open-lightbox"
              aria-label={lightboxLabels.open}
              onClick={() => openLightbox(currentIndex)}
              className="absolute right-2 top-2 inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border bg-surface text-lg text-text shadow focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              <span aria-hidden>⤢</span>
            </button>
          ) : null}
        </div>

        {layout === "horizontal" ? (
          <GalleryThumbnails
            images={usableImages}
            currentIndex={currentIndex}
            layout="horizontal"
            cloudName={cloudName}
            imageLabel={thumbLabel}
            overflowLabel={(extra) => t("pdp.gallery.moreImages", { count: extra })}
            onSelect={setCurrentIndex}
            onOpenOverflow={() => openLightbox(currentIndex)}
          />
        ) : null}

        <p className="mt-1 text-center text-xs text-text-3 lg:text-left">
          <span className="lg:hidden">{t("pdp.gallery.tapToExpand")}</span>
          <span className="hidden lg:inline">{t("pdp.gallery.rolloverZoom")}</span>
        </p>

        <div className="mt-2 flex items-center justify-between gap-2 lg:hidden">
          <button
            type="button"
            aria-label={previousLabel}
            onClick={() => go(-1)}
            disabled={currentIndex === 0}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border bg-surface disabled:opacity-40"
          >
            <span aria-hidden>‹</span>
          </button>
          <p data-testid="gallery-indicator" className="text-sm text-text-2" aria-live="polite">
            {indicatorLabel(currentIndex + 1, usableImages.length)}
          </p>
          <button
            type="button"
            aria-label={nextLabel}
            onClick={() => go(1)}
            disabled={currentIndex === usableImages.length - 1}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border bg-surface disabled:opacity-40"
          >
            <span aria-hidden>›</span>
          </button>
        </div>
      </div>

      {lightboxLabels && lightboxIndex !== null ? (
        <Lightbox
          images={usableImages}
          initialIndex={lightboxIndex}
          cloudName={cloudName}
          labels={lightboxLabels}
          productTitle={productTitle}
          variantSummary={variantSummary}
          onClose={closeLightbox}
        />
      ) : null}
    </div>
  );
}
