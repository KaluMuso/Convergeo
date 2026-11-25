"use client";

import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { type ComponentProps, type KeyboardEvent } from "react";

import type { PdpGalleryImage } from "./gallery";

export const GALLERY_THUMB_PX = 60;
export const GALLERY_THUMB_MAX = 6;

export type GalleryThumbnailsProps = {
  images: PdpGalleryImage[];
  currentIndex: number;
  layout: "vertical" | "horizontal";
  cloudName?: string;
  imageLabel: (index: number, total: number) => string;
  overflowLabel: (extra: number) => string;
  onSelect: (index: number) => void;
  onOpenOverflow: () => void;
};

export function GalleryThumbnails({
  images,
  currentIndex,
  layout,
  cloudName,
  imageLabel,
  overflowLabel,
  onSelect,
  onOpenOverflow,
}: GalleryThumbnailsProps) {
  if (images.length <= 1) {
    return null;
  }

  const visible = images.slice(0, GALLERY_THUMB_MAX);
  const extra = images.length - visible.length;

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta =
      layout === "vertical"
        ? event.key === "ArrowDown"
          ? 1
          : event.key === "ArrowUp"
            ? -1
            : 0
        : event.key === "ArrowRight"
          ? 1
          : event.key === "ArrowLeft"
            ? -1
            : 0;
    if (!delta) {
      return;
    }
    event.preventDefault();
    const next = Math.min(Math.max(index + delta, 0), images.length - 1);
    onSelect(next);
  };

  return (
    <MotionSafeWrapper
      data-testid="gallery-strip"
      className={
        layout === "vertical"
          ? "sticky top-20 flex w-[3.75rem] shrink-0 flex-col gap-2 self-start"
          : "flex gap-2 overflow-x-auto pb-1"
      }
      role="tablist"
      aria-orientation={layout === "vertical" ? "vertical" : "horizontal"}
    >
      {visible.map((image, index) => {
        const active = index === currentIndex;
        return (
          <button
            key={`${image.publicId}-${index}`}
            type="button"
            role="tab"
            aria-selected={active}
            aria-label={imageLabel(index + 1, images.length)}
            data-testid={`gallery-thumb-${index}`}
            onClick={() => onSelect(index)}
            onMouseEnter={() => onSelect(index)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={[
              "relative shrink-0 overflow-hidden rounded border bg-surface focus-visible:outline-none focus-visible:shadow-focusRing",
              layout === "vertical" ? "aspect-square w-full" : "h-[6.25rem] w-[6.25rem]",
              active ? "border-2 border-primary" : "border-border",
            ].join(" ")}
          >
            <CloudinaryImage
              publicId={image.publicId}
              alt=""
              width={128}
              ratio="1/1"
              cloudName={cloudName}
              className="h-full w-full object-contain"
            />
          </button>
        );
      })}
      {extra > 0 ? (
        <button
          type="button"
          data-testid="gallery-thumb-overflow"
          aria-label={overflowLabel(extra)}
          onClick={onOpenOverflow}
          className={[
            "flex shrink-0 items-center justify-center rounded border border-border bg-bg-2 text-sm font-medium text-text focus-visible:outline-none focus-visible:shadow-focusRing",
            layout === "vertical" ? "aspect-square w-full" : "h-[6.25rem] w-[6.25rem]",
          ].join(" ")}
        >
          +{extra}
        </button>
      ) : null}
    </MotionSafeWrapper>
  );
}

/** Passthrough wrapper so thumbnails can pick up motion-safe utilities. */
function MotionSafeWrapper({ className, children, ...rest }: ComponentProps<"div">) {
  return (
    <div className={["motion-safe", className].filter(Boolean).join(" ")} {...rest}>
      {children}
    </div>
  );
}
