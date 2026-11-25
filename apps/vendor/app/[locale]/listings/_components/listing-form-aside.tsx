"use client";

import { useTranslations } from "next-intl";

import { CloudinaryImage } from "../../../../../../packages/ui/src/media/cloudinary-image";
import { PriceBlock } from "../new/_lib/ui";

import { ListingTipsPanel, ListingVisibilityHint } from "./listing-guide";
import { ListingProductStatusChip } from "./listing-product-status";

type ListingFormAsideProps = {
  title: string;
  priceNgwee: number;
  listingStatus: string;
  productStatus?: string | null;
  coverPublicId?: string | null;
  showTips?: boolean;
};

/** Sticky right column on wide screens: preview card + moderation truth + tips. */
export function ListingFormAside({
  title,
  priceNgwee,
  listingStatus,
  productStatus,
  coverPublicId,
  showTips = true,
}: ListingFormAsideProps) {
  const t = useTranslations("vendor");
  return (
    <>
      <section
        className="rounded-xl border border-border bg-surface p-4 shadow-1"
        data-testid="listing-form-preview"
        aria-labelledby="listing-form-preview-heading"
      >
        <h2 id="listing-form-preview-heading" className="text-sm font-semibold text-text">
          {t("listings.formAside.previewHeading")}
        </h2>
        <div className="mt-3 flex gap-3">
          {coverPublicId ? (
            <CloudinaryImage
              publicId={coverPublicId}
              alt={t("listings.formAside.previewPhotoAlt")}
              width={72}
              ratio={1}
              className="size-[72px] shrink-0 rounded-lg object-cover"
            />
          ) : (
            <div
              aria-hidden
              className="flex size-[72px] shrink-0 items-center justify-center rounded-lg border border-dashed border-border bg-bg-2 text-micro text-text-3"
            >
              {t("listings.formAside.noPhoto")}
            </div>
          )}
          <div className="min-w-0 space-y-1">
            <p className="truncate text-sm font-medium text-text">{title}</p>
            <PriceBlock ngwee={priceNgwee} />
            <ListingVisibilityHint status={listingStatus} />
            <ListingProductStatusChip listingStatus={listingStatus} productStatus={productStatus} />
          </div>
        </div>
      </section>
      {showTips ? <ListingTipsPanel /> : null}
    </>
  );
}
