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
  previousLabel: string;
  nextLabel: string;
  indicatorLabel: (current: number, total: number) => string;
};

function GalleryFallback({ label }: { label: string }) {
  return (
    <div
      data-testid="pdp-gallery-empty"
      className="flex aspect-[4/3] items-center justify-center rounded border border-border bg-surface px-4 text-center text-sm text-text-2"
      style={{ borderRadius: "var(--r)" }}
      role="img"
      aria-label={label}
    >
      {label}
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
  const usableImages = images.filter((image) => image.publicId.trim().length > 0);

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
      className="w-full"
    />
  );
}
