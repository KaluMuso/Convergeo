"use client";

import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { TierPriceTable } from "@vergeo/ui/src/tier-price-table";
import Link from "next/link";
import { useMemo, useState } from "react";

import { MoqBadge } from "./moq-badge";
import {
  lineTotalNgwee,
  normalizeTiers,
  QtyPricePreview,
  selectUnitPriceNgwee,
  type ApiPriceTier,
  type PriceTier,
} from "./qty-price-preview";

export type SupplyListing = {
  id: string;
  title: string;
  productSlug: string | null;
  vendorName: string;
  priceNgwee: number;
  wholesale: boolean;
  moq: number;
  priceTiers: ApiPriceTier[] | null;
  imagePublicId: string | null;
};

export type TierPriceCardsLabels = {
  vendor: string;
  quantityLabel: string;
  decrease: string;
  increase: string;
  decreaseSymbol: string;
  increaseSymbol: string;
  noImage: string;
  viewListing: string;
  tierQuantityHeader: string;
  tierPriceHeader: string;
  moqBadge: string;
  moqTableLabel: string;
  previewLine: string;
};

export type TierPriceCardsProps = {
  locale: string;
  listings: SupplyListing[];
  labels: TierPriceCardsLabels;
  previewQty?: number;
};

export function filterWholesaleListings(listings: SupplyListing[]): SupplyListing[] {
  return listings.filter((listing) => listing.wholesale === true);
}

export function sortSupplyListings(
  listings: SupplyListing[],
  sort: "moq" | "unit_price",
  previewQty = 1,
): SupplyListing[] {
  const sorted = [...listings];

  if (sort === "moq") {
    return sorted.sort(
      (left, right) => left.moq - right.moq || left.title.localeCompare(right.title),
    );
  }

  return sorted.sort((left, right) => {
    const leftUnit = unitPriceAtQty(left, previewQty);
    const rightUnit = unitPriceAtQty(right, previewQty);
    return leftUnit - rightUnit || left.moq - right.moq || left.title.localeCompare(right.title);
  });
}

function unitPriceAtQty(listing: SupplyListing, qty: number): number {
  const tiers = normalizeTiers(listing.priceTiers, listing.priceNgwee);
  return selectUnitPriceNgwee(listing.priceNgwee, listing.wholesale, qty, tiers);
}

function listingHref(locale: string, listing: SupplyListing, qty: number): string {
  const params = new URLSearchParams({
    listing: listing.id,
    qty: String(qty),
  });
  if (listing.productSlug) {
    return `/${locale}/p/${listing.productSlug}?${params.toString()}`;
  }
  return `/${locale}/supplies?${params.toString()}`;
}

type SupplyCardProps = {
  locale: string;
  listing: SupplyListing;
  labels: TierPriceCardsLabels;
  initialQty: number;
};

function SupplyCard({ locale, listing, labels, initialQty }: SupplyCardProps) {
  const tiers = useMemo(
    () => normalizeTiers(listing.priceTiers, listing.priceNgwee),
    [listing.priceTiers, listing.priceNgwee],
  );
  const [qty, setQty] = useState(Math.max(initialQty, listing.moq));
  const unitPriceNgwee = selectUnitPriceNgwee(listing.priceNgwee, listing.wholesale, qty, tiers);
  const href = listingHref(locale, listing, qty);

  return (
    <article
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3"
      data-testid={`supply-card-${listing.id}`}
    >
      <div className="flex gap-3">
        {listing.imagePublicId ? (
          <CloudinaryImage
            publicId={listing.imagePublicId}
            alt={listing.title}
            width={96}
            ratio="1/1"
            sizes="96px"
            className="h-24 w-24 shrink-0 rounded-md object-cover"
          />
        ) : (
          <div
            aria-hidden
            className="flex h-24 w-24 shrink-0 items-center justify-center rounded-md bg-bg-2 text-xs text-text-3"
          >
            {labels.noImage}
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex items-start justify-between gap-2">
            <h2 className="line-clamp-2 text-base font-semibold text-text">{listing.title}</h2>
            <MoqBadge moq={listing.moq} label={labels.moqBadge} />
          </div>
          <p className="text-xs text-text-2">
            {labels.vendor.replace("{vendor}", listing.vendorName)}
          </p>
        </div>
      </div>

      <TierPriceTable
        tiers={tiers}
        moq={listing.moq}
        quantityHeader={labels.tierQuantityHeader}
        priceHeader={labels.tierPriceHeader}
        moqLabel={labels.moqTableLabel}
      />

      <div className="flex flex-col gap-2">
        <label className="text-xs font-medium text-text-2" htmlFor={`supply-qty-${listing.id}`}>
          {labels.quantityLabel}
        </label>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-md border border-border bg-bg text-lg text-text"
            aria-label={labels.decrease}
            onClick={() => setQty((current) => Math.max(listing.moq, current - 1))}
          >
            <span aria-hidden="true">{labels.decreaseSymbol}</span>
          </button>
          <input
            id={`supply-qty-${listing.id}`}
            type="number"
            min={listing.moq}
            step={1}
            value={qty}
            onChange={(event) => {
              const parsed = Number.parseInt(event.target.value, 10);
              if (Number.isInteger(parsed)) {
                setQty(Math.max(listing.moq, parsed));
              }
            }}
            className="h-11 w-full rounded-md border border-border bg-bg px-3 text-center font-mono text-sm text-text"
            inputMode="numeric"
          />
          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-md border border-border bg-bg text-lg text-text"
            aria-label={labels.increase}
            onClick={() => setQty((current) => current + 1)}
          >
            <span aria-hidden="true">{labels.increaseSymbol}</span>
          </button>
        </div>
        <QtyPricePreview
          qty={qty}
          unitPriceNgwee={unitPriceNgwee}
          lineTemplate={labels.previewLine}
        />
      </div>

      <Link
        href={href}
        className="flex h-11 items-center justify-center rounded-md bg-primary px-4 text-sm font-semibold text-surface no-underline"
      >
        {labels.viewListing}
      </Link>
    </article>
  );
}

export function TierPriceCards({ locale, listings, labels, previewQty = 1 }: TierPriceCardsProps) {
  const wholesaleListings = filterWholesaleListings(listings);

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2" data-testid="supplies-tier-cards">
      {wholesaleListings.map((listing) => (
        <SupplyCard
          key={listing.id}
          locale={locale}
          listing={listing}
          labels={labels}
          initialQty={Math.max(previewQty, listing.moq)}
        />
      ))}
    </div>
  );
}

export { lineTotalNgwee, normalizeTiers, selectUnitPriceNgwee, type PriceTier };
