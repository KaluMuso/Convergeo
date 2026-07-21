"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { CornerRibbon } from "@vergeo/ui/src/corner-ribbon";
import { PriceBlock } from "@vergeo/ui/src/price-block";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState, type ReactNode, type Ref } from "react";

import { addCartItem, openMiniCart, setLastAddedMessage } from "../cart/mini-cart-drawer";

import { ConditionBadge, type ListingCondition } from "./condition-badge";

import type { ListingPurchaseControls } from "./use-listing-purchase";

export type BuyBoxListing = {
  id: string;
  title: string;
  priceNgwee: number;
  condition: ListingCondition;
  stockMode: "tracked" | "always_available";
  stockQty: number | null;
  moq: number;
  inStock: boolean;
};

export type BuyBoxSellerSummary = {
  displayName: string;
  ratingLabel: string | null;
  preferred: boolean;
};

export type BuyBoxLabels = {
  priceLabel: string;
  quantityLabel: string;
  decreaseLabel: string;
  increaseLabel: string;
  decreaseSymbol: string;
  increaseSymbol: string;
  addToCartLabel: string;
  /** Shown while the add-to-cart request is in flight. */
  addingToCartLabel: string;
  /** Shown when add-to-cart fails (network / API) — never “coming soon”. */
  addToCartErrorLabel: string;
  inStockLabel: string;
  outOfStockLabel: string;
  alwaysAvailableLabel: string;
  singleVendorLabel: string;
  conditionNewLabel: string;
  conditionRefurbishedLabel: string;
};

export type BuyBoxProps = {
  listing: BuyBoxListing;
  labels: BuyBoxLabels;
  singleVendor: boolean;
  onAddedToCart?: () => void;
  /** Shared qty/ATC when sticky mobile bar is wired from the parent. */
  purchase?: ListingPurchaseControls;
  buyBoxRef?: Ref<HTMLElement | null>;
  seller?: BuyBoxSellerSummary | null;
  /** Required when `seller.preferred` is true. */
  preferredBadgeLabel?: string;
  /** Honest multi-seller price framing (lowest / delta). */
  priceContextLabel?: string | null;
  compareHref?: string | null;
  compareLabel?: string;
  wishlistSlot?: ReactNode;
};

export function getMaxQuantity(listing: BuyBoxListing): number | null {
  if (!listing.inStock) {
    return listing.moq;
  }
  if (listing.stockMode === "always_available") {
    return 99;
  }
  if (listing.stockQty === null) {
    return 99;
  }
  return Math.max(listing.moq, listing.stockQty);
}

export function clampQuantity(value: number, listing: BuyBoxListing): number {
  const min = Math.max(1, listing.moq);
  const max = getMaxQuantity(listing);
  if (max === null) {
    return Math.max(min, value);
  }
  return Math.min(Math.max(min, value), max);
}

export function getStockLabel(
  listing: BuyBoxListing,
  labels: Pick<BuyBoxLabels, "inStockLabel" | "outOfStockLabel" | "alwaysAvailableLabel"> & {
    lowStockLabel: (count: number) => string;
  },
): string {
  if (!listing.inStock) {
    return labels.outOfStockLabel;
  }
  if (listing.stockMode === "always_available") {
    return labels.alwaysAvailableLabel;
  }
  if (listing.stockQty !== null && listing.stockQty <= 5) {
    return labels.lowStockLabel(listing.stockQty);
  }
  return labels.inStockLabel;
}

export function BuyBox({
  listing,
  labels,
  singleVendor,
  onAddedToCart,
  purchase,
  buyBoxRef,
  seller,
  preferredBadgeLabel,
  priceContextLabel,
  compareHref,
  compareLabel,
  wishlistSlot,
}: BuyBoxProps) {
  const t = useTranslations("catalog");
  const [quantity, setQuantity] = useState(() => clampQuantity(listing.moq, listing));
  const [adding, setAdding] = useState(false);
  const [addedMessage, setAddedMessage] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  const maxQuantity = useMemo(() => getMaxQuantity(listing), [listing]);
  const localStockLabel = useMemo(
    () =>
      getStockLabel(listing, {
        ...labels,
        lowStockLabel: (count) => t("pdp.buyBox.lowStock", { count }),
      }),
    [listing, labels, t],
  );
  const conditionLabel =
    listing.condition === "new" ? labels.conditionNewLabel : labels.conditionRefurbishedLabel;

  const decrease = useCallback(() => {
    setQuantity((current) => clampQuantity(current - 1, listing));
  }, [listing]);

  const increase = useCallback(() => {
    setQuantity((current) => clampQuantity(current + 1, listing));
  }, [listing]);

  const handleAddToCart = useCallback(async () => {
    if (!listing.inStock || adding) {
      return;
    }

    setAdding(true);
    setAddError(null);
    setAddedMessage(null);

    try {
      await addCartItem(listing.id, quantity);
      setAddedMessage(labels.addToCartLabel);
      setLastAddedMessage(labels.addToCartLabel);
      openMiniCart();
      onAddedToCart?.();
    } catch {
      setAddError(labels.addToCartErrorLabel);
    } finally {
      setAdding(false);
    }
  }, [
    adding,
    labels.addToCartErrorLabel,
    labels.addToCartLabel,
    listing.id,
    listing.inStock,
    onAddedToCart,
    quantity,
  ]);

  const qty = purchase?.quantity ?? quantity;
  const onDecrease = purchase?.decrease ?? decrease;
  const onIncrease = purchase?.increase ?? increase;
  const atMin = purchase?.atMin ?? quantity <= Math.max(1, listing.moq);
  const atMax = purchase?.atMax ?? (maxQuantity !== null && quantity >= maxQuantity);
  const isAdding = purchase?.adding ?? adding;
  const errorMessage = purchase?.addError ?? addError;
  const successMessage = purchase?.addedMessage ?? addedMessage;
  const stockLabel = purchase?.stockLabel || localStockLabel;
  const onAdd = purchase?.handleAddToCart ?? (() => void handleAddToCart());

  return (
    <section
      ref={buyBoxRef}
      data-testid="pdp-buy-box"
      data-in-stock={listing.inStock ? "true" : "false"}
      className="flex flex-col gap-4 rounded border border-border bg-surface p-4"
      style={{ borderRadius: "var(--r)" }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <ConditionBadge condition={listing.condition} label={conditionLabel} />
        {singleVendor ? (
          <p className="text-sm text-text-2" data-testid="pdp-single-vendor">
            {labels.singleVendorLabel}
          </p>
        ) : null}
      </div>

      <div>
        <p className="text-sm text-text-2">{labels.priceLabel}</p>
        <PriceBlock ngwee={listing.priceNgwee} className="mt-0.5" />
        {priceContextLabel ? (
          <p className="mt-1 text-xs font-medium text-text-2" data-testid="pdp-price-context">
            {priceContextLabel}
          </p>
        ) : null}
        {/* Keep a test hook for the formatted price string used by existing tests. */}
        <p className="sr-only" data-testid="pdp-price">
          {formatK(listing.priceNgwee)}
        </p>
      </div>

      {seller ? (
        <div data-testid="pdp-buy-box-seller" className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-text">{seller.displayName}</p>
            {seller.preferred && preferredBadgeLabel ? (
              <CornerRibbon trust="preferred" trustLabel={preferredBadgeLabel} />
            ) : null}
          </div>
          {seller.ratingLabel ? <p className="text-xs text-text-2">{seller.ratingLabel}</p> : null}
        </div>
      ) : null}

      <p
        className={`text-sm font-medium ${listing.inStock ? "text-success" : "text-danger"}`}
        data-testid="pdp-stock-state"
      >
        {stockLabel}
      </p>

      {listing.moq > 1 ? (
        <p className="text-sm text-text-2" data-testid="pdp-moq">
          {t("pdp.buyBox.moq", { count: listing.moq })}
        </p>
      ) : null}

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium text-text">{labels.quantityLabel}</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label={labels.decreaseLabel}
            data-testid="pdp-qty-decrease"
            onClick={onDecrease}
            disabled={!listing.inStock || atMin || isAdding}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border bg-bg text-lg disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span aria-hidden="true">{labels.decreaseSymbol}</span>
          </button>
          <output
            data-testid="pdp-qty-value"
            className="min-w-12 text-center font-mono text-lg"
            aria-live="polite"
          >
            {qty}
          </output>
          <button
            type="button"
            aria-label={labels.increaseLabel}
            data-testid="pdp-qty-increase"
            onClick={onIncrease}
            disabled={!listing.inStock || atMax || isAdding}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border bg-bg text-lg disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span aria-hidden="true">{labels.increaseSymbol}</span>
          </button>
        </div>
      </div>

      <div className="flex items-stretch gap-2">
        <Button
          type="button"
          variant="primary"
          size="lg"
          className="min-w-0 flex-1"
          disabled={!listing.inStock || isAdding}
          loading={isAdding}
          loadingLabel={labels.addingToCartLabel}
          data-testid="pdp-add-to-cart"
          aria-label={listing.inStock ? labels.addToCartLabel : labels.outOfStockLabel}
          onClick={onAdd}
        >
          {labels.addToCartLabel}
        </Button>
        {wishlistSlot}
      </div>

      {compareHref && compareLabel ? (
        <Link
          href={compareHref}
          data-testid="pdp-buy-box-compare"
          className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {compareLabel}
        </Link>
      ) : null}

      <p className="sr-only" aria-live="polite">
        {successMessage}
      </p>
      {errorMessage ? (
        <p className="text-sm text-danger" role="alert" data-testid="pdp-add-to-cart-error">
          {errorMessage}
        </p>
      ) : null}
      {successMessage ? (
        <p className="text-sm font-medium text-success" data-testid="pdp-add-to-cart-success">
          {successMessage}
        </p>
      ) : null}
    </section>
  );
}
