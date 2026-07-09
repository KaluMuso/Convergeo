"use client";

import { ImageGallery } from "@vergeo/ui/src/media/image-gallery";

export type PdpGalleryImage = {
  publicId: string;
  alt: string;
};

export type PdpGalleryProps = {
  images: PdpGalleryImage[];
  cloudName?: string;
  emptyLabel: string;
  indicatorLabel: (current: number, total: number) => string;
  previousLabel: string;
  nextLabel: string;
};

export function PdpGallery({
  images,
  cloudName,
  emptyLabel,
  indicatorLabel,
  previousLabel,
  nextLabel,
}: PdpGalleryProps) {
  if (images.length === 0) {
    return (
      <div
        data-testid="pdp-gallery-empty"
        className="flex aspect-[4/3] items-center justify-center rounded bg-bg-2 text-text-3"
        style={{ borderRadius: "var(--r)" }}
      >
        {emptyLabel}
      </div>
    );
  }

  return (
    <ImageGallery
      images={images}
      cloudName={cloudName}
      ratio="4/3"
      indicatorLabel={indicatorLabel}
      previousLabel={previousLabel}
      nextLabel={nextLabel}
      className="w-full"
    />
  );
}
