"use client";

import { ImageGallery, type GalleryImage } from "@vergeo/ui/src/media/image-gallery";
import { Modal } from "@vergeo/ui/src/modal";

export type ReviewPhotoLightboxProps = {
  images: GalleryImage[];
  cloudName?: string;
  title: string;
  previousLabel: string;
  nextLabel: string;
  indicatorTemplate: string;
  onClose: () => void;
};

/**
 * Review-photo lightbox. Split out of ReviewsSection and loaded on first photo
 * tap, so the Modal + gallery code stays out of the PDP first-load bundle.
 */
export function ReviewPhotoLightbox({
  images,
  cloudName,
  title,
  previousLabel,
  nextLabel,
  indicatorTemplate,
  onClose,
}: ReviewPhotoLightboxProps) {
  return (
    <Modal
      open={images.length > 0}
      onClose={onClose}
      title={title}
      data-testid="review-photo-lightbox"
    >
      {images.length > 0 ? (
        <ImageGallery
          images={images}
          cloudName={cloudName}
          previousLabel={previousLabel}
          nextLabel={nextLabel}
          indicatorLabel={(current, total) =>
            indicatorTemplate
              .replace("{current}", String(current))
              .replace("{total}", String(total))
          }
        />
      ) : null}
    </Modal>
  );
}
