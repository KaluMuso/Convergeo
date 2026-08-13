"use client";

import { useTranslations } from "next-intl";
import { useCallback } from "react";

import { BuyBox, type BuyBoxLabels, type BuyBoxListing } from "../pdp/buy-box";
import { PdpGallery, type PdpGalleryImage } from "../pdp/gallery";

export type StandaloneListingBodyProps = {
  locale: string;
  listing: BuyBoxListing;
  images: PdpGalleryImage[];
  sellerName: string;
  cloudName?: string;
  galleryLabels: {
    empty: string;
    previous: string;
    next: string;
  };
  buyBoxLabels: BuyBoxLabels;
};

export function StandaloneListingBody({
  locale,
  listing,
  images,
  sellerName,
  cloudName,
  galleryLabels,
  buyBoxLabels,
}: StandaloneListingBodyProps) {
  const t = useTranslations("catalog");
  const indicatorLabel = useCallback(
    (current: number, total: number) => t("pdp.gallery.indicator", { current, total }),
    [t],
  );

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(20rem,0.9fr)] lg:items-start">
      <PdpGallery
        images={images}
        cloudName={cloudName}
        emptyLabel={galleryLabels.empty}
        previousLabel={galleryLabels.previous}
        nextLabel={galleryLabels.next}
        indicatorLabel={indicatorLabel}
      />
      <BuyBox
        listing={listing}
        labels={buyBoxLabels}
        singleVendor={false}
        seller={{ displayName: sellerName, preferred: false, ratingLabel: null }}
        locale={locale}
      />
    </div>
  );
}
