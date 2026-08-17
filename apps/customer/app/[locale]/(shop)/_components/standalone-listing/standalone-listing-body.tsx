"use client";

import { useTranslations } from "next-intl";
import { useCallback } from "react";

import {
  BuyBox,
  listingRequiresQuote,
  type BuyBoxLabels,
  type BuyBoxListing,
} from "../pdp/buy-box";
import { PdpGallery, type PdpGalleryImage } from "../pdp/gallery";
import { RequestQuoteButton } from "../pdp/request-quote-button";

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
  const showQuote = listing.productClass === "E" || listingRequiresQuote(listing);

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
      <div className="flex flex-col gap-3">
        <BuyBox
          listing={listing}
          labels={buyBoxLabels}
          singleVendor={false}
          seller={{ displayName: sellerName, preferred: false, ratingLabel: null }}
          locale={locale}
        />
        {showQuote ? (
          <RequestQuoteButton
            locale={locale}
            listingId={listing.id}
            vendorName={sellerName}
            labels={{
              cta: t("pdp.requestQuote.cta"),
              dialogTitle: t("pdp.requestQuote.dialogTitle"),
              dialogHint: t("pdp.requestQuote.dialogHint"),
              detailsLabel: t("pdp.requestQuote.detailsLabel"),
              detailsPlaceholder: t("pdp.requestQuote.detailsPlaceholder"),
              submit: t("pdp.requestQuote.submit"),
              submitting: t("pdp.requestQuote.submitting"),
              cancel: t("pdp.requestQuote.cancel"),
              done: t("pdp.requestQuote.done"),
              successTitle: t("pdp.requestQuote.successTitle"),
              successBody: t("pdp.requestQuote.successBody"),
              successContinued: t("pdp.requestQuote.successContinued"),
              signInPrompt: t("pdp.requestQuote.signInPrompt"),
              signInCta: t("pdp.requestQuote.signInCta"),
              errors: {
                empty: t("pdp.requestQuote.errors.empty"),
                tooLong: t("pdp.requestQuote.errors.tooLong"),
                prohibited: t("pdp.requestQuote.errors.prohibited"),
                rateLimited: t("pdp.requestQuote.errors.rateLimited"),
                ownListing: t("pdp.requestQuote.errors.ownListing"),
                generic: t("pdp.requestQuote.errors.generic"),
                signInRequired: t("pdp.requestQuote.errors.signInRequired"),
              },
            }}
            className="w-full"
          />
        ) : null}
      </div>
    </div>
  );
}
