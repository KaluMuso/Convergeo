"use client";

import { ImageGallery } from "@vergeo/ui/src/media/image-gallery";
import { useTranslations } from "next-intl";

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
}: PdpGalleryProps) {
  const t = useTranslations("catalog.pdp.gallery");
  const usableImages = images.filter(
    (image) => image.publicId.trim().length > 0,
  );

  if (usableImages.length === 0) {
    return <GalleryFallback label={emptyLabel} />;
  }

  return (
    <ImageGallery
      images={usableImages}
      cloudName={cloudName}
      ratio="4/3"
      indicatorLabel={indicatorLabel}
      previousLabel={previousLabel}
      nextLabel={nextLabel}
      imageFallbackLabel={emptyLabel}
      zoomLabels={{
        open: t("zoomOpen"),
        close: t("zoomClose"),
        title: t("zoomTitle"),
        zoomIn: t("zoomIn"),
        zoomOut: t("zoomOut"),
      }}
      className="w-full"
    />
  );
}
