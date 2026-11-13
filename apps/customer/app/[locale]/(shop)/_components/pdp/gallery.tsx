"use client";

import { ImageGallery } from "@vergeo/ui/src/media/image-gallery";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { LightboxLabels } from "./lightbox";

/** Lazy — the full-screen viewer only loads when a buyer opens it (3G budget). */
const Lightbox = dynamic(() => import("./lightbox").then((mod) => mod.Lightbox), {
  ssr: false,
});

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
  /** Slide to show (e.g. the chosen variant's photo). */
  activeIndex?: number;
  /** When provided, tapping an image opens the zoomable full-screen viewer. */
  lightboxLabels?: LightboxLabels;
};

function GalleryFallback({ label }: { label: string }) {
  return (
    // Compact neutral stage (not a giant empty box): glyph + small caption.
    <div
      data-testid="pdp-gallery-empty"
      className="relative flex aspect-[4/3] max-h-[260px] w-full flex-col items-center justify-end rounded-lg bg-bg-2 px-4 pb-4 text-center text-sm text-text-3 md:max-h-[340px]"
      data-image-stage
      role="img"
      aria-label={label}
    >
      <span aria-hidden>{label}</span>
    </div>
  );
}

export function PdpGallery({
  images,
  cloudName,
  emptyLabel,
  previousLabel,
  nextLabel,
  indicatorLabel,
  activeIndex,
  lightboxLabels,
}: PdpGalleryProps) {
  const t = useTranslations("catalog.pdp.gallery");
  const usableImages = images.filter((image) => image.publicId.trim().length > 0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  // Slide the strip should show: the caller's (variant photo) or, after the
  // viewer closes, the image the buyer ended on.
  const [targetIndex, setTargetIndex] = useState<number | undefined>(activeIndex);
  useEffect(() => {
    setTargetIndex(activeIndex);
  }, [activeIndex]);

  const openLightbox = useCallback((index: number) => setLightboxIndex(index), []);
  const closeLightbox = useCallback((lastIndex: number) => {
    setLightboxIndex(null);
    setTargetIndex(lastIndex);
  }, []);

  if (usableImages.length === 0) {
    return <GalleryFallback label={emptyLabel} />;
  }

  return (
    <div className="relative">
      <ImageGallery
        images={usableImages}
        cloudName={cloudName}
        ratio="4/3"
        indicatorLabel={indicatorLabel}
        previousLabel={previousLabel}
        nextLabel={nextLabel}
        imageFallbackLabel={emptyLabel}
        className="w-full"
        activeIndex={targetIndex}
        onIndexChange={setCurrentIndex}
        onImageActivate={lightboxLabels ? openLightbox : undefined}
        zoomLabels={
          lightboxLabels
            ? undefined
            : {
                open: t("zoomOpen"),
                close: t("zoomClose"),
                title: t("zoomTitle"),
                zoomIn: t("zoomIn"),
                zoomOut: t("zoomOut"),
              }
        }
      />
      {lightboxLabels ? (
        <button
          type="button"
          data-testid="pdp-gallery-open-lightbox"
          aria-label={lightboxLabels.open}
          onClick={() => openLightbox(currentIndex)}
          className="absolute right-2 top-2 inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border bg-surface text-lg text-text shadow focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          <span aria-hidden="true">⤢</span>
        </button>
      ) : null}
      {lightboxLabels && lightboxIndex !== null ? (
        <Lightbox
          images={usableImages}
          initialIndex={lightboxIndex}
          cloudName={cloudName}
          labels={lightboxLabels}
          onClose={closeLightbox}
        />
      ) : null}
    </div>
  );
}
