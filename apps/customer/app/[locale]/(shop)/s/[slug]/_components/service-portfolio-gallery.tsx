"use client";

import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import dynamic from "next/dynamic";
import { useCallback, useState } from "react";

import type { LightboxLabels } from "../../../_components/pdp/lightbox";

const Lightbox = dynamic(
  () => import("../../../_components/pdp/lightbox").then((mod) => mod.Lightbox),
  { ssr: false },
);

export type ServicePortfolioGalleryLabels = {
  heading: string;
  formatImageAlt: (position: number) => string;
  lightbox: LightboxLabels;
};

type ServicePortfolioGalleryProps = {
  title: string;
  /** All portfolio images including the hero (index 0). */
  publicIds: string[];
  labels: ServicePortfolioGalleryLabels;
};

export function ServicePortfolioGallery({
  title,
  publicIds,
  labels,
}: ServicePortfolioGalleryProps) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const extra = publicIds.slice(1);

  const closeLightbox = useCallback((lastIndex: number) => {
    setLightboxIndex(null);
    void lastIndex;
  }, []);

  if (extra.length === 0) {
    return null;
  }

  const images = publicIds.map((publicId, index) => ({
    publicId,
    alt: index === 0 ? title : labels.formatImageAlt(index + 1),
  }));

  return (
    <section className="flex flex-col gap-4" aria-labelledby="service-portfolio-heading">
      <h2 id="service-portfolio-heading" className="font-display text-h2 text-display-ink">
        {labels.heading}
      </h2>
      <ul className="grid list-none grid-cols-2 gap-3 p-0 md:grid-cols-3">
        {extra.map((publicId, index) => {
          const galleryIndex = index + 1;
          return (
            <li key={publicId} className="overflow-hidden rounded-lg border border-border">
              <button
                type="button"
                className="block w-full cursor-zoom-in focus-visible:outline-none focus-visible:shadow-focusRing"
                aria-label={labels.lightbox.open}
                onClick={() => setLightboxIndex(galleryIndex)}
              >
                <CloudinaryImageStatic
                  publicId={publicId}
                  alt={labels.formatImageAlt(galleryIndex + 1)}
                  width={480}
                  sizes="(max-width: 640px) 50vw, 33vw"
                  ratio="4/3"
                />
              </button>
            </li>
          );
        })}
      </ul>
      {lightboxIndex !== null ? (
        <Lightbox
          images={images}
          initialIndex={lightboxIndex}
          labels={labels.lightbox}
          onClose={closeLightbox}
        />
      ) : null}
    </section>
  );
}
